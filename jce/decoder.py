"""JCE解码器实现.

该模块提供用于零复制读取的`DataReader`和
用于无模式解析的`GenericDecoder`.
"""

import math
import struct
from collections.abc import Callable
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

JceDeserializer = Callable[[type[Any], Any, DeserializationInfo], Any]

F = TypeVar("F", bound=JceDeserializer)


def jce_field_deserializer(field_name: str):
    """装饰器: 注册字段的自定义 JCE 反序列化方法.

    被装饰的方法应是类方法 (@classmethod), 接受参数:
    - cls: 类本身
    - value: 原始值 (可能是基础类型或 bytes)
    - info: DeserializationInfo 上下文信息

    Args:
        field_name: 要自定义反序列化的字段名称.

    Usage:
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
        try:
            val = self._view[self._pos]
            self._pos += 1
            return val
        except IndexError:
            raise JcePartialDataError("Not enough data to read u8") from None

    def peek_u8(self) -> int:
        """查看下一个无符号8位整数而不移动指针."""
        try:
            return self._view[self._pos]
        except IndexError:
            raise JcePartialDataError("Not enough data to peek u8") from None

    def skip(self, length: int) -> None:
        """跳过指定数量的字节."""
        if length < 0:
            raise JceDecodeError(f"Cannot skip negative bytes: {length}")
        if self._pos + length > self.length:
            raise JcePartialDataError("Not enough data to skip")
        self._pos += length

    def read_int1(self) -> int:
        """读取有符号1字节整数."""
        try:
            val = self._view[self._pos]
            self._pos += 1
            return val if val <= 127 else val - 256
        except IndexError:
            raise JcePartialDataError("Not enough data to read int1") from None

    def read_int2(self) -> int:
        """读取有符号2字节整数."""
        return cast(
            int,
            self._unpack(_STRUCT_H if not self._little_endian else _STRUCT_H_LE, 2)[0],
        )

    def read_int4(self) -> int:
        """读取有符号4字节整数."""
        return cast(
            int,
            self._unpack(_STRUCT_I if not self._little_endian else _STRUCT_I_LE, 4)[0],
        )

    def read_int8(self) -> int:
        """读取有符号8字节整数."""
        return cast(
            int,
            self._unpack(_STRUCT_Q if not self._little_endian else _STRUCT_Q_LE, 8)[0],
        )

    def read_float(self) -> float:
        """读取4字节浮点数."""
        if self._pos + 4 > self.length:
            raise JcePartialDataError("Not enough data to read float")

        start = self._pos
        self._pos += 4
        buf = self._view[start : self._pos]

        # 始终使用小端读取如果启用了 OPT_LITTLE_ENDIAN
        if self._little_endian:
            return cast(float, _STRUCT_f_LE.unpack(buf)[0])

        # 使用启发式逻辑处理可能的字节序错误
        primary = _STRUCT_f.unpack(buf)[0]
        alt = _STRUCT_f_LE.unpack(buf)[0]
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

        start = self._pos
        self._pos += 8
        buf = self._view[start : self._pos]

        if self._little_endian:
            return cast(float, _STRUCT_d_LE.unpack(buf)[0])

        primary = _STRUCT_d.unpack(buf)[0]
        alt = _STRUCT_d_LE.unpack(buf)[0]
        if not math.isfinite(primary) and math.isfinite(alt):
            return cast(float, alt)

        if math.isfinite(alt):
            if abs(primary) > 1e18 and abs(alt) <= 1e12:
                return cast(float, alt)
            if abs(primary) < 1e-30 and abs(alt) <= 1e6:
                return cast(float, alt)

        return cast(float, primary)

    def _unpack(self, packer: struct.Struct, size: int) -> tuple[Any, ...]:
        if self._pos + size > self.length:
            raise JcePartialDataError(f"Not enough data to unpack {size} bytes")
        # memoryview 可以直接传递给 unpack_from
        val = packer.unpack_from(self._view, self._pos)
        self._pos += size
        return val

    @property
    def eof(self) -> bool:
        """检查是否到达流末尾."""
        return self._pos >= self.length


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
            result = JceDict()
            while not self._reader.eof:
                tag, type_id = self._read_head()
                if type_id == JCE_STRUCT_END:
                    break

                value = self._read_value(type_id)
                result[tag] = value

            if not suppress_log:
                logger.debug("[GenericDecoder] 成功解码 %d 个标签", len(result))
            return result

        except Exception as e:
            if not suppress_log:
                logger.error("[GenericDecoder] 解码错误: %s", e)
            raise

    def _read_head(self) -> tuple[int, int]:
        """从头部读取Tag和Type."""
        b = self._reader.read_u8()
        type_id = b & 0x0F
        tag = (b & 0xF0) >> 4
        if tag == 15:
            tag = self._reader.read_u8()
        return tag, type_id

    def _read_value(self, type_id: int) -> Any:
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
        if type_id == JCE_LIST:
            return self._read_list()
        if type_id == JCE_MAP:
            return self._read_map()
        if type_id == JCE_STRUCT_BEGIN:
            return self._read_struct()
        if type_id == JCE_STRUCT_END:
            pass
        elif type_id == JCE_SIMPLE_LIST:
            return self._read_simple_list()
        else:
            raise JceDecodeError(f"Unknown JCE Type ID: {type_id}")

    def _read_list(self) -> list[Any]:
        """读取列表值."""
        self._check_recursion()
        self._recursion_limit -= 1
        try:
            size = self._read_integer_generic()
            result: list[Any] = []
            for _ in range(size):
                _tag, type_id = self._read_head()
                value = self._read_value(type_id)
                result.append(value)
            return result
        finally:
            self._recursion_limit += 1

    def _read_map(self) -> dict[Any, Any]:
        """读取映射值."""
        self._check_recursion()
        self._recursion_limit -= 1
        try:
            length = self._read_integer_generic()
            result: dict[Any, Any] = {}
            for _ in range(length):
                # 读取键 (Tag 0)
                k_tag, k_type = self._read_head()
                if k_tag != 0:
                    raise JceDecodeError(f"Expected Map Key Tag 0, got {k_tag}")
                key = self._read_value(k_type)

                # 读取值 (Tag 1)
                v_tag, v_type = self._read_head()
                if v_tag != 1:
                    raise JceDecodeError(f"Expected Map Value Tag 1, got {v_tag}")
                val = self._read_value(v_type)

                # 处理不可哈希的键
                if isinstance(key, dict | list):
                    key = self._freeze_key(key)

                result[key] = val
            return result
        finally:
            self._recursion_limit += 1

    def _read_struct(self) -> JceDict:
        """读取结构体值."""
        self._check_recursion()
        self._recursion_limit -= 1
        try:
            result = JceDict()
            while True:
                # 窥视以检查STRUCT_END
                b = self._reader.peek_u8()
                type_id = b & 0x0F
                tag = (b & 0xF0) >> 4

                if type_id == JCE_STRUCT_END:
                    self._reader.read_u8()  # 消费STRUCT_END头部
                    break

                # 不是结束,正常读取
                tag, type_id = self._read_head()
                result[tag] = self._read_value(type_id)
            return result
        finally:
            self._recursion_limit += 1

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
        "_context",
        "_field_map",
        "_fields",
        "_target_cls",
    )

    _target_cls: Any
    _fields: dict[str, Any]
    _context: dict[str, Any]
    _field_map: dict[int, tuple[str, Any]]

    def __init__(
        self,
        reader: DataReader,
        target_cls: Any,
        option: int = 0,
        context: dict[str, Any] | None = None,
    ):
        super().__init__(reader, option)
        self._target_cls = target_cls
        self._context = context or {}

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
