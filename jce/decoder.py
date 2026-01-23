"""JCE解码器实现.

该模块提供用于零复制读取的`DataReader`和
用于无模式解析的`GenericDecoder`.
"""

import contextlib
import math
import struct
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar, cast

from .const import (
    JCE_DOUBLE,
    JCE_FLOAT,
    JCE_INT1,
    JCE_INT2,
    JCE_INT4,
    JCE_INT8,
    JCE_LIST,
    JCE_MAP,
    JCE_SIMPLE_LIST,
    JCE_STRING1,
    JCE_STRING4,
    JCE_STRUCT_BEGIN,
    JCE_STRUCT_END,
    JCE_ZERO_TAG,
)
from .context import DeserializationInfo
from .exceptions import JceDecodeError, JcePartialDataError
from .log import logger
from .options import JceOption
from .struct import JceDict


def _is_safe_text(s: str) -> bool:
    r"""智能判断字符串是否为'人类可读文本'.

    允许:
      - 所有可打印字符 (包括中文, Emoji, 拉丁文等)
      - 常用排版控制符 (\n, \r, \t)
    拒绝:
      - 二进制控制符 (\x00, \x01, \x07 等), 这些通常意味着数据是 binary blob
    """
    if not s:
        return True

    # 快速路径: 如果全是 ASCII, 使用快速检查
    if s.isascii():
        # 允许 32-126 (可打印) 和 9, 10, 13 (\t, \n, \r)
        return all(32 <= ord(c) <= 126 or c in "\n\r\t" for c in s)

    # Unicode 路径: 使用 isprintable (它对中文/Emoji 返回 True)
    # 并额外豁免常见的排版字符
    return all(c.isprintable() or c in "\n\r\t" for c in s)


def convert_bytes_recursive(
    data: Any, mode: str = "auto", option: int = JceOption.NONE
) -> Any:
    """递归转换数据中的字节对象 (内部帮助函数)."""
    if mode == "raw":
        return data

    if isinstance(data, dict):
        if isinstance(data, JceDict):
            result = JceDict()
        else:
            result = {}

        for key, value in data.items():
            # 递归处理 Key (Key 必须是 Hashable)
            if isinstance(key, bytes):
                try:
                    decoded_key = key.decode("utf-8")
                    if _is_safe_text(decoded_key):
                        key = decoded_key
                except UnicodeDecodeError:
                    pass

            # 递归处理 Value
            converted_val = convert_bytes_recursive(value, mode, option)

            # 只有普通 dict 才需要将 key 转为 str (JceDict key 必须是 int)
            if not isinstance(result, JceDict) and isinstance(key, dict | list):
                key = str(key)

            result[key] = converted_val  # type: ignore
        return result

    if isinstance(data, list):
        return [convert_bytes_recursive(item, mode, option) for item in data]

    if isinstance(data, bytes):
        if len(data) == 0:
            return ""

        if mode == "string":
            try:
                decoded = data.decode("utf-8")
                return decoded if _is_safe_text(decoded) else data
            except UnicodeDecodeError:
                return data

        # AUTO 模式: 优先尝试 UTF-8 文本（避免将普通文本误判为 JCE 二进制）
        try:
            decoded = data.decode("utf-8")
            if _is_safe_text(decoded):
                return decoded
        except UnicodeDecodeError:
            pass

        # 如果不是可读文本，再尝试识别为 JCE 结构
        if len(data) >= 1 and (data[0] & 0x0F) <= 13:
            try:
                reader = DataReader(data, option=option)
                decoder = GenericDecoder(reader, option=option)
                parsed = decoder.decode(suppress_log=True)
                return convert_bytes_recursive(parsed, mode="auto", option=option)
            except (JceDecodeError, JcePartialDataError, RecursionError):
                pass

        return data

    return data


JceDeserializer = Callable[[type[Any], Any, DeserializationInfo], Any]


F = TypeVar("F", bound=JceDeserializer)


def jce_field_deserializer(field_name: str):
    """装饰器: 注册字段的自定义 JCE 反序列化方法.

    Args:
        field_name (str): 要自定义反序列化的字段名称。

    Examples:
        ```python
        @jce_field_deserializer("password")
        def deserialize_password(cls, value: Any, info: DeserializationInfo) -> Any:
            return decrypt(value)
        ```
    """

    def decorator(func: F) -> F:
        # 标记函数, 稍后在元类中处理
        from typing import cast

        cast(Any, func).__jce_deserializer_target__ = field_name
        return func

    return decorator


# 预编译的结构体打包器,用于性能优化
_STRUCT_B = struct.Struct(">b")
_STRUCT_H = struct.Struct(">h")
_STRUCT_I = struct.Struct(">i")
_STRUCT_Q = struct.Struct(">q")
_STRUCT_f = struct.Struct(">f")
_STRUCT_d = struct.Struct(">d")

_STRUCT_B_LE = struct.Struct("<b")
_STRUCT_H_LE = struct.Struct("<h")
_STRUCT_I_LE = struct.Struct("<i")
_STRUCT_Q_LE = struct.Struct("<q")
_STRUCT_f_LE = struct.Struct("<f")
_STRUCT_d_LE = struct.Struct("<d")

# 安全限制
MAX_STRING_LENGTH = 100 * 1024 * 1024  # 100MB
MAX_CONTAINER_SIZE = 10_000_000  # 1000万元素


class DataReader:
    """JCE二进制数据的零复制读取器.

    包装memoryview以提供流式读取功能,而无需
    不必要时复制数据.
    """

    __slots__ = ("_little_endian", "_pos", "_view", "length")

    _view: memoryview
    _pos: int
    length: int
    _little_endian: bool

    def __init__(self, data: bytes | bytearray | memoryview, option: int = 0):
        """初始化DataReader.

        Args:
            data: 要读取的二进制数据.
            option: 选项位掩码.
        """
        self._view = memoryview(data)
        self._pos = 0
        self.length = len(data)
        self._little_endian = bool(option & JceOption.LITTLE_ENDIAN)

    def read_bytes(self, length: int, zero_copy: bool = False) -> bytes | memoryview:
        """读取字节序列.

        Args:
            length: 要读取的字节数.
            zero_copy: 如果为True, 则返回 memoryview 切片.

        Returns:
            包含数据的bytes或memoryview.

        Raises:
            JcePartialDataError: 如果没有足够的数据可用.
        """
        if length < 0:
            raise JceDecodeError(f"Cannot read negative bytes: {length}")

        if self._pos + length > self.length:
            raise JcePartialDataError("Not enough data to read bytes")

        start = self._pos
        self._pos += length
        view = self._view[start : self._pos]
        return view if zero_copy else view.tobytes()

    def read_u8(self) -> int:
        """读取无符号8位整数."""
        if self._pos >= self.length:
            raise JcePartialDataError("Not enough data to read u8")
        val = self._view[self._pos]
        self._pos += 1
        return val

    def peek_u8(self) -> int:
        """查看下一个无符号8位整数而不移动指针."""
        if self._pos >= self.length:
            raise JcePartialDataError("Not enough data to peek u8")
        return self._view[self._pos]

    def skip(self, length: int) -> None:
        """跳过指定数量的字节."""
        if length < 0:
            raise JceDecodeError(f"Cannot skip negative bytes: {length}")
        new_pos = self._pos + length
        if new_pos > self.length:
            raise JcePartialDataError("Not enough data to skip")
        self._pos = new_pos

    def read_int1(self) -> int:
        """读取有符号1字节整数."""
        if self._pos >= self.length:
            raise JcePartialDataError("Not enough data to read int1")
        val = self._view[self._pos]
        self._pos += 1
        return val if val <= 127 else val - 256

    def read_int2(self) -> int:
        """读取有符号2字节整数."""
        if self._pos + 2 > self.length:
            raise JcePartialDataError("Not enough data to read int2")
        val = (
            _STRUCT_H.unpack_from(self._view, self._pos)[0]
            if not self._little_endian
            else _STRUCT_H_LE.unpack_from(self._view, self._pos)[0]
        )
        self._pos += 2
        return cast(int, val)

    def read_int4(self) -> int:
        """读取有符号4字节整数."""
        if self._pos + 4 > self.length:
            raise JcePartialDataError("Not enough data to read int4")
        val = (
            _STRUCT_I.unpack_from(self._view, self._pos)[0]
            if not self._little_endian
            else _STRUCT_I_LE.unpack_from(self._view, self._pos)[0]
        )
        self._pos += 4
        return cast(int, val)

    def read_int8(self) -> int:
        """读取有符号8字节整数."""
        if self._pos + 8 > self.length:
            raise JcePartialDataError("Not enough data to read int8")
        val = (
            _STRUCT_Q.unpack_from(self._view, self._pos)[0]
            if not self._little_endian
            else _STRUCT_Q_LE.unpack_from(self._view, self._pos)[0]
        )
        self._pos += 8
        return cast(int, val)

    def read_float(self) -> float:
        """读取4字节浮点数."""
        if self._pos + 4 > self.length:
            raise JcePartialDataError("Not enough data to read float")

        if self._little_endian:
            val = _STRUCT_f_LE.unpack_from(self._view, self._pos)[0]
            self._pos += 4
            return cast(float, val)

        # 优化读取: 避免切片,直接使用 unpack_from
        primary = _STRUCT_f.unpack_from(self._view, self._pos)[0]
        alt = _STRUCT_f_LE.unpack_from(self._view, self._pos)[0]
        self._pos += 4

        if not math.isfinite(primary) and math.isfinite(alt):
            return cast(float, alt)

        if math.isfinite(alt):
            # 当主值异常大时, 使用较小幅度的值
            if abs(primary) > 1e9 and abs(alt) <= 1e6:
                return cast(float, alt)

        return cast(float, primary)

    def read_double(self) -> float:
        """读取8字节双精度浮点数."""
        if self._pos + 8 > self.length:
            raise JcePartialDataError("Not enough data to read double")

        if self._little_endian:
            val = _STRUCT_d_LE.unpack_from(self._view, self._pos)[0]
            self._pos += 8
            return cast(float, val)

        primary = _STRUCT_d.unpack_from(self._view, self._pos)[0]
        alt = _STRUCT_d_LE.unpack_from(self._view, self._pos)[0]
        self._pos += 8

        if not math.isfinite(primary) and math.isfinite(alt):
            return cast(float, alt)

        if math.isfinite(alt):
            if abs(primary) > 1e18 and abs(alt) <= 1e12:
                return cast(float, alt)
            if abs(primary) < 1e-30 and abs(alt) <= 1e6:
                return cast(float, alt)

        return cast(float, primary)

    @property
    def eof(self) -> bool:
        """检查是否到达流末尾."""
        return self._pos >= self.length


# 解码状态常量
_STATE_LIST_ITEM = 1
_STATE_MAP_KEY = 2
_STATE_MAP_VALUE = 3
_STATE_STRUCT_FIELD = 4


class GenericDecoder:
    """JCE数据的无模式解码器.

    根据标签和类型将JCE二进制数据解析为Python dicts和lists.
    """

    __slots__ = (
        "_freeze_cache",
        "_option",
        "_reader",
        "_recursion_limit",
        "_zero_copy",
    )

    _reader: DataReader
    _option: int
    _recursion_limit: int
    _zero_copy: bool
    _freeze_cache: dict[int, Any]

    def __init__(self, reader: DataReader, option: int = 0):
        self._reader = reader
        self._option = option
        self._recursion_limit = 100
        self._zero_copy = bool(option & JceOption.ZERO_COPY)
        self._freeze_cache = {}  # 缓存以提高性能

    def decode(self, suppress_log: bool = False) -> JceDict:
        """将整个流解码为标签字典."""
        if not suppress_log:
            logger.debug("[GenericDecoder] 开始解码 %d 字节", self._reader.length)

        try:
            # 迭代解码实现
            root = JceDict()
            # 状态: 0=读取Tag/Type, 1=读取Value

            while not self._reader.eof:
                tag, type_id = self._read_head()
                if type_id == JCE_STRUCT_END:
                    break

                value = self._read_value(type_id)
                root[tag] = value

            if not suppress_log:
                logger.debug("[GenericDecoder] 成功解码 %d 个标签", len(root))
            return root

        except Exception as e:
            if not suppress_log:
                logger.error("[GenericDecoder] 解码错误: %s", e)
            raise

    def _read_value(self, type_id: int) -> Any:
        # 这个方法仍然被调用，我们需要确保它不会递归调用 _read_list/_read_map/_read_struct
        # 如果是容器类型，我们需要使用新的迭代读取方法。

        if type_id == JCE_LIST:
            return self._read_list_iterative()
        if type_id == JCE_MAP:
            return self._read_map_iterative()
        if type_id == JCE_STRUCT_BEGIN:
            return self._read_struct_iterative()

        # 基本类型保持不变
        if type_id == JCE_ZERO_TAG:
            return 0
        if type_id == JCE_INT1:
            return self._reader.read_int1()
        if type_id == JCE_INT2:
            return self._reader.read_int2()
        if type_id == JCE_INT4:
            return self._reader.read_int4()
        if type_id == JCE_INT8:
            return self._reader.read_int8()
        if type_id == JCE_FLOAT:
            return self._reader.read_float()
        if type_id == JCE_DOUBLE:
            return self._reader.read_double()
        if type_id == JCE_STRING1:
            length = self._reader.read_u8()
            return self._reader.read_bytes(length, self._zero_copy)
        if type_id == JCE_STRING4:
            length = self._reader.read_int4()
            if length < 0:
                raise JceDecodeError(f"String4 length cannot be negative: {length}")
            if length > MAX_STRING_LENGTH:
                raise JceDecodeError(
                    f"String4 length {length} exceeds max limit {MAX_STRING_LENGTH}"
                )
            return self._reader.read_bytes(length, self._zero_copy)
        if type_id == JCE_STRUCT_END:
            pass
        elif type_id == JCE_SIMPLE_LIST:
            return self._read_simple_list()
        else:
            raise JceDecodeError(f"Unknown JCE Type ID: {type_id}")

    def _read_list_iterative(self) -> list[Any]:
        """迭代方式读取列表."""
        return self._decode_iterative(JCE_LIST)

    def _read_map_iterative(self) -> dict[Any, Any]:
        return self._decode_iterative(JCE_MAP)

    def _read_struct_iterative(self) -> JceDict:
        return self._decode_iterative(JCE_STRUCT_BEGIN)

    def _decode_iterative(self, start_type: int) -> Any:
        """核心迭代解析循环."""
        # 栈帧结构: [container, state, size, index, key]
        # state 使用模块级常量: _STATE_*

        stack = []
        root_result: Any = None

        # 初始化根容器
        if start_type == JCE_LIST:
            length = self._read_integer_generic()
            root_result = []
            if length > 0:
                stack.append([root_result, _STATE_LIST_ITEM, length, 0, None])
        elif start_type == JCE_MAP:
            length = self._read_integer_generic()
            root_result = {}
            if length > 0:
                stack.append([root_result, _STATE_MAP_KEY, length, 0, None])
        elif start_type == JCE_STRUCT_BEGIN:
            root_result = JceDict()
            stack.append(
                [root_result, _STATE_STRUCT_FIELD, 0, 0, None]
            )  # Struct 大小未知

        if not stack:
            return root_result

        while stack:
            frame = stack[-1]
            container, state, size, index, key = frame

            # --- LIST 处理 ---
            if state == _STATE_LIST_ITEM:
                if index >= size:
                    stack.pop()
                    continue

                # 准备读取下一个元素
                _tag, type_id = self._read_head()

                # 检查是否是容器类型
                if type_id in {JCE_LIST, JCE_MAP, JCE_STRUCT_BEGIN}:
                    # 创建新容器并压栈
                    new_container = self._create_container(type_id)
                    container.append(new_container)

                    # 更新当前帧索引 (因为下次回来就是下一个元素了)
                    frame[3] += 1

                    # 压入新帧
                    self._push_stack(stack, new_container, type_id)
                else:
                    # 基本类型，直接读取并追加
                    val = self._read_primitive(type_id)
                    container.append(val)
                    frame[3] += 1

            # --- MAP 处理 ---
            elif state == _STATE_MAP_KEY:
                if index >= size:
                    stack.pop()
                    continue

                # 读取 Key
                k_tag, k_type = self._read_head()
                if k_tag != 0:
                    raise JceDecodeError(f"Expected Map Key Tag 0, got {k_tag}")

                if k_type in {JCE_LIST, JCE_MAP, JCE_STRUCT_BEGIN}:
                    # Key 是容器类型：先构建容器并入栈解码，完成后再读取对应的 Value
                    new_container = self._create_container(k_type)
                    frame[4] = new_container  # 保存 Key 容器
                    frame[1] = _STATE_MAP_VALUE  # Key 解码完成后转去读 Value
                    self._push_stack(stack, new_container, k_type)
                else:
                    key_val = self._read_primitive(k_type)
                    if isinstance(key_val, dict | list):
                        key_val = self._freeze_key(key_val)
                    frame[4] = key_val  # 保存 Key
                    frame[1] = _STATE_MAP_VALUE  # 转去读 Value

            elif state == _STATE_MAP_VALUE:
                # 此时 frame[4] 已经是 Key 了
                curr_key = frame[4]

                v_tag, v_type = self._read_head()
                if v_tag != 1:
                    raise JceDecodeError(f"Expected Map Value Tag 1, got {v_tag}")

                if v_type in {JCE_LIST, JCE_MAP, JCE_STRUCT_BEGIN}:
                    new_container = self._create_container(v_type)

                    # 如果 Key 也是容器（现在已填满），需要冻结它才能作为字典键
                    if isinstance(curr_key, dict | list):
                        curr_key = self._freeze_key(curr_key)

                    container[curr_key] = new_container

                    # 准备读下一个 Entry
                    frame[1] = _STATE_MAP_KEY
                    frame[3] += 1
                    frame[4] = None

                    self._push_stack(stack, new_container, v_type)
                else:
                    val = self._read_primitive(v_type)

                    if isinstance(curr_key, dict | list):
                        curr_key = self._freeze_key(curr_key)

                    container[curr_key] = val

                    # 准备读下一个 Entry
                    frame[1] = _STATE_MAP_KEY
                    frame[3] += 1
                    frame[4] = None

            # --- STRUCT 处理 ---
            elif state == _STATE_STRUCT_FIELD:
                b = self._reader.peek_u8()
                type_id = b & 0x0F

                if type_id == JCE_STRUCT_END:
                    self._reader.read_u8()  # Consume END
                    stack.pop()
                    continue

                tag, type_id = self._read_head()

                if type_id in {JCE_LIST, JCE_MAP, JCE_STRUCT_BEGIN}:
                    new_container = self._create_container(type_id)
                    container[tag] = new_container
                    self._push_stack(stack, new_container, type_id)
                else:
                    val = self._read_primitive(type_id)
                    container[tag] = val

        return root_result

    def _read_head(self) -> tuple[int, int]:
        """从头部读取Tag和Type."""
        b = self._reader.read_u8()
        type_id = b & 0x0F
        tag = (b & 0xF0) >> 4
        if tag == 15:
            tag = self._reader.read_u8()
        return tag, type_id

    def _create_container(self, type_id: int) -> Any:
        if type_id == JCE_LIST:
            return []
        if type_id == JCE_MAP:
            return {}
        if type_id == JCE_STRUCT_BEGIN:
            return JceDict()
        raise JceDecodeError(f"Cannot create container for type {type_id}")

    def _push_stack(self, stack: list, container: Any, type_id: int):
        if type_id == JCE_LIST:
            length = self._read_integer_generic()
            if length > 0:
                stack.append([container, _STATE_LIST_ITEM, length, 0, None])
        elif type_id == JCE_MAP:
            length = self._read_integer_generic()
            if length > 0:
                stack.append([container, _STATE_MAP_KEY, length, 0, None])
        elif type_id == JCE_STRUCT_BEGIN:
            # 注意：这里对容器的栈行为是刻意不对称的。
            # - LIST / MAP：只有在 length > 0 时才压栈，因为没有元素时无需再读取任何数据。
            # - STRUCT：即使是空结构体也必须压栈，以便后续正确消费 JCE_STRUCT_END 标记。
            stack.append([container, _STATE_STRUCT_FIELD, 0, 0, None])

    def _read_primitive(self, type_id: int) -> Any:
        """读取基本类型 (非容器)."""
        if type_id == JCE_ZERO_TAG:
            return 0
        if type_id == JCE_INT1:
            return self._reader.read_int1()
        if type_id == JCE_INT2:
            return self._reader.read_int2()
        if type_id == JCE_INT4:
            return self._reader.read_int4()
        if type_id == JCE_INT8:
            return self._reader.read_int8()
        if type_id == JCE_FLOAT:
            return self._reader.read_float()
        if type_id == JCE_DOUBLE:
            return self._reader.read_double()
        if type_id == JCE_STRING1:
            length = self._reader.read_u8()
            return self._reader.read_bytes(length, self._zero_copy)
        if type_id == JCE_STRING4:
            length = self._reader.read_int4()
            if length < 0:
                raise JceDecodeError(f"String4 length cannot be negative: {length}")
            if length > MAX_STRING_LENGTH:
                raise JceDecodeError(
                    f"String4 length {length} exceeds max limit {MAX_STRING_LENGTH}"
                )
            return self._reader.read_bytes(length, self._zero_copy)
        if type_id == JCE_SIMPLE_LIST:
            return self._read_simple_list()

        # Should not reach here for containers if logic is correct
        raise JceDecodeError(f"Unexpected type id in _read_primitive: {type_id}")

    def _read_simple_list(self) -> bytes | memoryview:
        """读取简单列表(字节数组)."""
        # 头部(已读) -> 类型(0) -> 长度 -> 数据
        _type_tag, type_id = self._read_head()
        if type_id != JCE_INT1:  # INT1是0,是BYTE类型id
            raise JceDecodeError(f"SimpleList expected BYTE type, got {type_id}")

        length = self._read_integer_generic()
        return self._reader.read_bytes(length, self._zero_copy)

    def _read_integer_generic(self) -> int:
        """读取长度字段的整数(JCE编码整数)."""
        _tag, type_id = self._read_head()
        val = self._read_value(type_id)
        if not isinstance(val, int):
            raise JceDecodeError(
                f"Expected integer for length, got {type(val).__name__}"
            )
        if val < 0:
            raise JceDecodeError(f"Container length cannot be negative: {val}")
        if val > MAX_CONTAINER_SIZE:
            raise JceDecodeError(
                f"Container size {val} exceeds max limit {MAX_CONTAINER_SIZE}"
            )
        return val

    def _check_recursion(self):
        if self._recursion_limit <= 0:
            raise RecursionError("JCE recursion limit exceeded")

    def _freeze_key(self, obj: Any) -> Any:
        """将可变对象转换为不可变对象以用作字典键."""
        # 对于不可变类型, 直接返回
        if isinstance(obj, str | int | float | bool | type(None) | bytes):
            return obj

        obj_id = id(obj)
        if obj_id in self._freeze_cache:
            return self._freeze_cache[obj_id]

        if isinstance(obj, dict):
            # 将 dict items 转换为 list, 显式标注类型以消除 Unknown
            items: list[tuple[Any, Any]] = [
                (k, self._freeze_key(v)) for k, v in cast(dict[Any, Any], obj).items()
            ]
            # 排序以保证确定性
            items.sort(key=lambda x: str(x[0]))
            result = tuple(items)
        elif isinstance(obj, list):
            result = tuple(self._freeze_key(x) for x in cast(list[Any], obj))
        else:
            result = obj

        self._freeze_cache[obj_id] = result
        return result

    def _skip_value(self, type_id: int) -> None:
        """跳过值而不解码(用于未知字段)."""
        if type_id == JCE_ZERO_TAG:
            pass  # No data to skip
        elif type_id == JCE_INT1:
            self._reader.skip(1)
        elif type_id == JCE_INT2:
            self._reader.skip(2)
        elif type_id == JCE_INT4:
            self._reader.skip(4)
        elif type_id == JCE_INT8:
            self._reader.skip(8)
        elif type_id == JCE_FLOAT:
            self._reader.skip(4)
        elif type_id == JCE_DOUBLE:
            self._reader.skip(8)
        elif type_id == JCE_STRING1:
            length = self._reader.read_u8()
            self._reader.skip(length)
        elif type_id == JCE_STRING4:
            length = self._reader.read_int4()
            if length < 0:
                raise JceDecodeError(f"String4 length cannot be negative: {length}")
            if length > MAX_STRING_LENGTH:
                raise JceDecodeError(
                    f"String4 length {length} exceeds max limit {MAX_STRING_LENGTH}"
                )
            self._reader.skip(length)
        elif type_id == JCE_LIST:
            self._skip_list()
        elif type_id == JCE_MAP:
            self._skip_map()
        elif type_id == JCE_STRUCT_BEGIN:
            self._skip_struct()
        elif type_id == JCE_SIMPLE_LIST:
            self._skip_simple_list()

    def _skip_list(self) -> None:
        """跳过列表值."""
        length = self._read_integer_generic()
        for _ in range(length):
            _tag, type_id = self._read_head()
            self._skip_value(type_id)

    def _skip_map(self) -> None:
        """跳过映射值."""
        length = self._read_integer_generic()
        for _ in range(length):
            _k_tag, k_type = self._read_head()
            self._skip_value(k_type)
            _v_tag, v_type = self._read_head()
            self._skip_value(v_type)

    def _skip_struct(self) -> None:
        """跳过嵌套结构体."""
        while True:
            b = self._reader.peek_u8()
            type_id = b & 0x0F
            if type_id == JCE_STRUCT_END:
                self._reader.read_u8()
                break
            _tag, type_id = self._read_head()
            self._skip_value(type_id)

    def _skip_simple_list(self) -> None:
        """跳过简单列表."""
        _type_tag, _type_id = self._read_head()
        length = self._read_integer_generic()
        self._reader.skip(length)


class SchemaDecoder(GenericDecoder):
    """基于模式的JCE数据解码器.

    使用字段定义将JCE数据解码为JceStruct实例.
    针对已知模式进行优化,仅解析定义在目标类中的字段.
    """

    __slots__ = (
        "_bytes_mode",
        "_context",
        "_field_map",
        "_fields",
        "_target_cls",
    )

    _target_cls: Any
    _fields: dict[str, Any]
    _context: dict[str, Any]
    _field_map: dict[int, tuple[str, Any]]
    _bytes_mode: str

    def __init__(
        self,
        reader: DataReader,
        target_cls: Any,
        option: int = 0,
        context: dict[str, Any] | None = None,
        bytes_mode: str = "auto",
    ):
        super().__init__(reader, option)
        self._target_cls = target_cls
        self._context = context or {}
        self._bytes_mode = bytes_mode

        # 获取字段,对于泛型类需要从原始类获取
        self._fields = getattr(target_cls, "__jce_fields__", {})

        # 如果字段为空,尝试从泛型起源或MRO获取
        if not self._fields:
            # 检查 __orig_bases__ 以找到泛型基类
            for base in getattr(target_cls, "__orig_bases__", []):
                from typing import get_origin

                origin = get_origin(base)
                if origin and hasattr(origin, "__jce_fields__"):
                    self._fields = origin.__jce_fields__
                    break
            # 如果还是没有,尝试 MRO
            if not self._fields:
                for base in target_cls.__mro__[1:]:  # 跳过自身
                    if hasattr(base, "__jce_fields__"):
                        base_fields = getattr(base, "__jce_fields__", {})
                        if base_fields:
                            self._fields = base_fields
                            break

        self._field_map = {
            field.jce_id: (name, field.jce_type) for name, field in self._fields.items()
        }

    def decode(self, suppress_log: bool = False) -> Any:
        """将流解码为target_cls实例."""
        result = self.decode_to_dict(suppress_log=suppress_log)
        return self._target_cls.model_validate(result)

    def decode_to_dict(self, suppress_log: bool = False) -> dict[str, Any]:
        """将流解码为字典(仅包含Schema中定义的字段)."""
        if not suppress_log:
            logger.debug("[SchemaDecoder] 开始解码 %s", self._target_cls.__name__)
        deserializers = getattr(self._target_cls, "__jce_deserializers__", {})

        try:
            result: dict[str, Any] = {}

            while not self._reader.eof:
                tag, type_id = self._read_head()

                if type_id == JCE_STRUCT_END:
                    break

                if tag in self._field_map:
                    field_name, expected_type = self._field_map[tag]

                    try:
                        from .struct import JceStruct

                        # 递归处理 Struct
                        if (
                            isinstance(expected_type, type)
                            and issubclass(expected_type, JceStruct)
                            and type_id == JCE_STRUCT_BEGIN
                        ):
                            inner_decoder = SchemaDecoder(
                                self._reader,
                                expected_type,
                                self._option,
                                self._context,
                            )
                            value = inner_decoder.decode_to_dict(
                                suppress_log=suppress_log
                            )
                        # 处理 Struct 列表
                        elif type_id == JCE_LIST:
                            value = self._decode_list_field(
                                field_name, type_id, suppress_log=suppress_log
                            )
                        # 普通值
                        else:
                            value = self._read_value(type_id)

                        # 如果是 Any 字段 (expected_type 为 None), 应用 bytes_mode 转换
                        if expected_type is None:
                            value = convert_bytes_recursive(
                                value, mode=self._bytes_mode, option=self._option
                            )

                        # 应用反序列化器

                        value = self._apply_deserializer(
                            field_name, value, tag, deserializers
                        )

                        # 自动解包 BYTES 字段
                        if hasattr(self._target_cls, "_auto_unpack_bytes_field"):
                            jce_info = self._fields[field_name]
                            value = self._target_cls._auto_unpack_bytes_field(
                                field_name, jce_info, value
                            )

                        result[field_name] = value
                    except JceDecodeError as e:
                        e.loc.insert(0, field_name)
                        raise
                else:
                    logger.debug(
                        "[SchemaDecoder] 跳过未知标签 %d (类型 %d)",
                        tag,
                        type_id,
                    )
                    self._skip_value(type_id)

            if not suppress_log:
                logger.debug("[SchemaDecoder] 成功解码 %d 个字段", len(result))
            return result
        except Exception as e:
            if not isinstance(e, JceDecodeError) and not suppress_log:
                logger.error(
                    "[SchemaDecoder] 解码 %s 时出错: %s",
                    self._target_cls.__name__,
                    e,
                )
            raise

    def _decode_list_field(
        self, field_name: str, type_id: int, suppress_log: bool = False
    ) -> Any:
        # 处理列表字段解码逻辑的辅助函数.
        from typing import get_args, get_origin

        from .struct import JceStruct

        field_info = self._target_cls.model_fields[field_name]
        annotation = field_info.annotation

        # Unpack Optional/Union
        origin = get_origin(annotation)
        # 注意: 如果我们严格检查类型, 则需要导入 'Union',
        # 但这里我们依赖基本比较或 'typing' 导入.
        # 假设简单的解包逻辑如原始代码所示:
        args = get_args(annotation)
        if args and type(None) in args:  # Optional check
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                annotation = non_none[0]
                origin = get_origin(annotation)

        if (origin is list or annotation is list) and get_args(annotation):
            item_type = get_args(annotation)[0]
            if isinstance(item_type, type) and issubclass(item_type, JceStruct):
                return self._read_list_of_structs(item_type, suppress_log=suppress_log)

        return self._read_value(type_id)

    def _apply_deserializer(
        self,
        field_name: str,
        value: Any,
        tag: int,
        deserializers: dict[str, str],
    ) -> Any:
        # 检查是否有字段反序列化器
        if field_name in deserializers:
            deserializer_name = deserializers[field_name]
            deserializer_func = getattr(self._target_cls, deserializer_name)

            info = DeserializationInfo(
                option=self._option,
                context=self._context,
                field_name=field_name,
                jce_id=tag,
            )

            try:
                value = deserializer_func(value, info)
            except TypeError as e:
                # 检查是否是因为缺少 cls 参数(用户忘记添加 @classmethod)
                if "missing 1 required positional argument" in str(e):
                    raise TypeError(
                        f"Field deserializer '{deserializer_name}' must be a @classmethod or @staticmethod. "
                        f"Instance methods are not supported since deserialization occurs before instance creation."
                    ) from e
                raise
        return value

    def _read_list_of_structs(
        self, item_type: Any, suppress_log: bool = False
    ) -> list[dict[str, Any]]:
        """读取结构体列表."""
        self._check_recursion()
        self._recursion_limit -= 1
        try:
            length = self._read_integer_generic()
            result: list[dict[str, Any]] = []
            for _ in range(length):
                _tag, type_id = self._read_head()
                if type_id == JCE_STRUCT_BEGIN:
                    inner_decoder = SchemaDecoder(
                        self._reader, item_type, self._option, self._context
                    )
                    result.append(
                        inner_decoder.decode_to_dict(suppress_log=suppress_log)
                    )
                else:
                    result.append(self._read_struct_fallback(type_id, item_type))
            return result

        finally:
            self._recursion_limit += 1

    def _read_struct_fallback(self, type_id: int, item_type: Any) -> dict[str, Any]:
        """列表中的结构体读取失败时的回退处理 (减少嵌套)."""
        from typing import cast

        val = self._read_value(type_id)
        if isinstance(val, dict):
            # 尝试将 int keys 转换为 field names
            val_dict = cast(dict[int, Any], val)
            id_map: dict[int, str] = {
                f.jce_id: name for name, f in item_type.__jce_fields__.items()
            }
            new_val: dict[str, Any] = {}
            for k, v in val_dict.items():
                if k in id_map:
                    new_val[id_map[k]] = v
                else:
                    new_val[str(k)] = v
            return new_val
        else:
            return {"_raw_value": val}


@dataclass
class JceNode:
    """JCE 节点类, 用于表示解码后的树状结构."""

    tag: int | None
    type_id: int
    value: Any
    length: int | None = None

    @property
    def type_name(self) -> str:
        """获取类型名称 (如 'Int', 'Struct')."""
        from .const import (
            JCE_DOUBLE,
            JCE_FLOAT,
            JCE_INT1,
            JCE_INT2,
            JCE_INT4,
            JCE_INT8,
            JCE_LIST,
            JCE_MAP,
            JCE_SIMPLE_LIST,
            JCE_STRING1,
            JCE_STRING4,
            JCE_STRUCT_BEGIN,
            JCE_ZERO_TAG,
        )

        mapping = {
            JCE_INT1: "Byte",
            JCE_INT2: "Short",
            JCE_INT4: "Int",
            JCE_INT8: "Long",
            JCE_FLOAT: "Float",
            JCE_DOUBLE: "Double",
            JCE_STRING1: "Str",
            JCE_STRING4: "Str",
            JCE_MAP: "Map",
            JCE_LIST: "List",
            JCE_STRUCT_BEGIN: "Struct",
            JCE_ZERO_TAG: "Zero",
            JCE_SIMPLE_LIST: "SimpleList",
        }
        return mapping.get(self.type_id, "Unknown")


class NodeDecoder(GenericDecoder):
    """JCE数据到节点树的解码器."""

    def decode(self, suppress_log: bool = False) -> list[JceNode]:  # type: ignore[override]
        """将流解码为节点列表."""
        if not suppress_log:
            logger.debug("[NodeDecoder] 开始解码 %d 字节", self._reader.length)

        nodes = []
        try:
            while not self._reader.eof:
                tag, type_id = self._read_head()
                if type_id == JCE_STRUCT_END:
                    break
                nodes.append(self._read_node(tag, type_id))

            if not suppress_log:
                logger.debug("[NodeDecoder] 成功解码 %d 个节点", len(nodes))

        except JcePartialDataError as e:
            if not suppress_log:
                logger.debug("[NodeDecoder] 数据不完整 (EOF): %s", e)
        except Exception as e:
            if not suppress_log:
                logger.error("[NodeDecoder] 解码错误: %s", e)
            raise

        return nodes

    def _read_node(self, tag: int | None, type_id: int) -> JceNode:
        """读取单个节点 (迭代实现)."""
        from .const import (
            JCE_DOUBLE,
            JCE_FLOAT,
            JCE_INT1,
            JCE_INT2,
            JCE_INT4,
            JCE_INT8,
            JCE_LIST,
            JCE_MAP,
            JCE_SIMPLE_LIST,
            JCE_STRING1,
            JCE_STRING4,
            JCE_STRUCT_BEGIN,
            JCE_ZERO_TAG,
        )

        # 1. 处理简单类型 (非容器)
        if type_id in {
            JCE_INT1,
            JCE_INT2,
            JCE_INT4,
            JCE_INT8,
            JCE_FLOAT,
            JCE_DOUBLE,
            JCE_ZERO_TAG,
        }:
            value = self._read_value(type_id)
            return JceNode(tag, type_id, value)

        if type_id == JCE_STRING1:
            length = self._reader.read_u8()
            value = self._reader.read_bytes(length, self._zero_copy)
            # 只有 bytes 才有 decode 方法
            if isinstance(value, bytes):
                with contextlib.suppress(UnicodeDecodeError):
                    value = value.decode("utf-8")
            elif isinstance(value, memoryview):
                # memoryview 需要转 bytes 才能 decode
                with contextlib.suppress(UnicodeDecodeError):
                    value_bytes = value.tobytes()
                    value = value_bytes.decode("utf-8")
            return JceNode(tag, type_id, value, length)

        if type_id == JCE_STRING4:
            length = self._reader.read_int4()
            if length < 0:
                raise JceDecodeError(f"String4 length negative: {length}")
            if length > MAX_STRING_LENGTH:
                raise JceDecodeError("String4 too long")
            value = self._reader.read_bytes(length, self._zero_copy)

            if isinstance(value, bytes):
                with contextlib.suppress(UnicodeDecodeError):
                    value = value.decode("utf-8")
            elif isinstance(value, memoryview):
                with contextlib.suppress(UnicodeDecodeError):
                    value_bytes = value.tobytes()
                    value = value_bytes.decode("utf-8")
            return JceNode(tag, type_id, value, length)

        if type_id == JCE_SIMPLE_LIST:
            _tag, type_ = self._read_head()
            if type_ != 0:
                raise JceDecodeError("SimpleList expected Byte type")
            length = self._read_integer_generic()
            data = self._reader.read_bytes(length, self._zero_copy)
            value = data

            # 尝试递归解析 SimpleList (Bytes -> JCE)
            # 这里是解析 bytes 内容，不是结构递归，所以可以保留递归调用(实例化新Decoder)
            if len(data) > 0 and (data[0] & 0x0F) <= 13:
                try:
                    sub_reader = DataReader(data)
                    sub_nodes = NodeDecoder(sub_reader).decode(suppress_log=True)
                    if sub_nodes:
                        value = sub_nodes
                except Exception:
                    pass
            return JceNode(tag, type_id, value, length)

        # 2. 处理容器类型 (迭代状态机)
        if type_id not in {JCE_LIST, JCE_MAP, JCE_STRUCT_BEGIN}:
            raise JceDecodeError(f"Unknown type {type_id}")

        # 迭代核心逻辑
        return self._read_node_iterative(tag, type_id)

    def _read_node_iterative(self, root_tag: int | None, root_type: int) -> JceNode:
        """迭代读取容器节点."""
        from .const import (
            JCE_LIST,
            JCE_MAP,
            JCE_STRUCT_BEGIN,
            JCE_STRUCT_END,
        )

        # 初始化根节点
        root_length = 0
        root_value: list[Any] = []

        if root_type == JCE_LIST:
            root_length = self._read_integer_generic()
            initial_state = _STATE_LIST_ITEM
        elif root_type == JCE_MAP:
            root_length = self._read_integer_generic()
            initial_state = _STATE_MAP_KEY
        elif root_type == JCE_STRUCT_BEGIN:
            initial_state = _STATE_STRUCT_FIELD
        else:
            raise JceDecodeError(f"Invalid container type: {root_type}")

        root_node = JceNode(root_tag, root_type, root_value, root_length)

        # 栈帧: [node, state, size, index, temp_key_node]
        # node: 当前正在填充的 JceNode (value 必须是 list)
        stack = [[root_node, initial_state, root_length, 0, None]]

        while stack:
            frame = stack[-1]
            curr_node, state, size, index, key_node = frame

            # --- List ---
            if state == _STATE_LIST_ITEM:
                if index >= size:
                    stack.pop()
                    continue

                # 读取列表项头部
                sub_tag, sub_type = self._read_head()

                # 递归(迭代)处理子节点
                if sub_type in {JCE_LIST, JCE_MAP, JCE_STRUCT_BEGIN}:
                    new_node = self._create_container_node(sub_tag, sub_type)
                    curr_node.value.append(new_node)

                    frame[3] += 1  # index++
                    self._push_node_stack(stack, new_node, sub_type)
                else:
                    # 基础类型直接读取
                    child = self._read_node(sub_tag, sub_type)
                    curr_node.value.append(child)
                    frame[3] += 1

            # --- Map ---
            elif state == _STATE_MAP_KEY:
                if index >= size:
                    stack.pop()
                    continue

                # 读取 Key
                k_tag, k_type = self._read_head()
                if k_type in (JCE_LIST, JCE_MAP, JCE_STRUCT_BEGIN):
                    new_node = self._create_container_node(k_tag, k_type)

                    frame[4] = new_node  # 保存 Key node
                    frame[1] = _STATE_MAP_VALUE  # 转到 Value 状态

                    self._push_node_stack(stack, new_node, k_type)
                else:
                    k_node = self._read_node(k_tag, k_type)
                    frame[4] = k_node
                    frame[1] = _STATE_MAP_VALUE

            elif state == _STATE_MAP_VALUE:
                # 读取 Value
                # frame[4] 是 key_node
                curr_key = frame[4]

                v_tag, v_type = self._read_head()

                if v_type in (JCE_LIST, JCE_MAP, JCE_STRUCT_BEGIN):
                    new_node = self._create_container_node(v_tag, v_type)
                    curr_node.value.append((curr_key, new_node))

                    frame[1] = _STATE_MAP_KEY  # 回到 Key 状态
                    frame[3] += 1  # index++
                    frame[4] = None

                    self._push_node_stack(stack, new_node, v_type)
                else:
                    v_node = self._read_node(v_tag, v_type)
                    curr_node.value.append((curr_key, v_node))

                    frame[1] = _STATE_MAP_KEY
                    frame[3] += 1
                    frame[4] = None

            # --- Struct ---
            elif state == _STATE_STRUCT_FIELD:
                b = self._reader.peek_u8()
                type_id = b & 0x0F

                if type_id == JCE_STRUCT_END:
                    self._reader.read_u8()
                    stack.pop()
                    continue

                sub_tag, sub_type = self._read_head()

                if sub_type in (JCE_LIST, JCE_MAP, JCE_STRUCT_BEGIN):
                    new_node = self._create_container_node(sub_tag, sub_type)
                    curr_node.value.append(new_node)
                    self._push_node_stack(stack, new_node, sub_type)
                else:
                    child = self._read_node(sub_tag, sub_type)
                    curr_node.value.append(child)

        return root_node

    def _create_container_node(self, tag: int | None, type_id: int) -> JceNode:
        """创建容器节点骨架."""
        from .const import JCE_LIST, JCE_MAP

        length = 0
        if type_id in (JCE_LIST, JCE_MAP):
            length = self._read_integer_generic()

        return JceNode(tag, type_id, value=[], length=length)

    def _push_node_stack(self, stack: list, node: JceNode, type_id: int):
        from .const import JCE_LIST, JCE_MAP, JCE_STRUCT_BEGIN

        if type_id == JCE_LIST:
            # node.length 已经在 _create_container_node 中读取
            length = node.length if node.length is not None else 0
            if length > 0:
                stack.append([node, _STATE_LIST_ITEM, length, 0, None])
        elif type_id == JCE_MAP:
            length = node.length if node.length is not None else 0
            if length > 0:
                stack.append([node, _STATE_MAP_KEY, length, 0, None])
        elif type_id == JCE_STRUCT_BEGIN:
            stack.append([node, _STATE_STRUCT_FIELD, 0, 0, None])
