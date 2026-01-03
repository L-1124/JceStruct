"""JCE解码器实现.

该模块提供用于零复制读取的`DataReader`和
用于无模式解析的`GenericDecoder`.
"""

import math
import struct
from typing import Any, cast

from jce.const import (
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
from jce.exceptions import JceDecodeError, JcePartialDataError
from jce.log import get_hexdump, logger
from jce.options import OPT_LITTLE_ENDIAN, OPT_ZERO_COPY

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


class DataReader:
    """JCE二进制数据的零复制读取器.

    包装memoryview以提供流式读取功能,而无需
    不必要时复制数据.
    """

    __slots__ = ("_len", "_little_endian", "_pos", "_view")

    def __init__(self, data: bytes | bytearray | memoryview, option: int = 0):
        """初始化DataReader.

        Args:
            data: 要读取的二进制数据.
            option: 选项位掩码(用于检查OPT_LITTLE_ENDIAN).
        """
        self._view = memoryview(data)
        self._pos = 0
        self._len = len(data)
        self._little_endian = bool(option & OPT_LITTLE_ENDIAN)

    def read_bytes(
        self, length: int, zero_copy: bool = False
    ) -> bytes | memoryview:
        """读取字节序列.

        Args:
            length: 要读取的字节数.
            zero_copy: 如果为True,则返回memoryview切片.

        Returns:
            包含数据的bytes或memoryview.

        Raises:
            JcePartialDataError: 如果没有足够的数据可用.
        """
        if self._pos + length > self._len:
            raise JcePartialDataError("Not enough data to read bytes")

        start = self._pos
        self._pos += length
        view = self._view[start : self._pos]
        return view if zero_copy else view.tobytes()

    def read_u8(self) -> int:
        """读取无符号8位整数."""
        if self._pos + 1 > self._len:
            raise JcePartialDataError("Not enough data to read u8")
        val = self._view[self._pos]
        self._pos += 1
        return val

    def peek_u8(self) -> int:
        """查看下一个无符号8位整数而不移动指针."""
        if self._pos + 1 > self._len:
            raise JcePartialDataError("Not enough data to peek u8")
        return self._view[self._pos]

    def skip(self, length: int) -> None:
        """跳过指定数量的字节."""
        if self._pos + length > self._len:
            raise JcePartialDataError("Not enough data to skip")
        self._pos += length

    def read_int1(self) -> int:
        """读取有符号1字节整数."""
        # struct.unpack对于有符号数比手动位操作更快
        return cast(
            int,
            self._unpack(
                _STRUCT_B if not self._little_endian else _STRUCT_B_LE, 1
            )[0],
        )

    def read_int2(self) -> int:
        """读取有符号2字节整数."""
        return cast(
            int,
            self._unpack(
                _STRUCT_H if not self._little_endian else _STRUCT_H_LE, 2
            )[0],
        )

    def read_int4(self) -> int:
        """读取有符号4字节整数."""
        return cast(
            int,
            self._unpack(
                _STRUCT_I if not self._little_endian else _STRUCT_I_LE, 4
            )[0],
        )

    def read_int8(self) -> int:
        """读取有符号8字节整数."""
        return cast(
            int,
            self._unpack(
                _STRUCT_Q if not self._little_endian else _STRUCT_Q_LE, 8
            )[0],
        )

    def read_float(self) -> float:
        """读取4字节浮点数."""
        if self._pos + 4 > self._len:
            raise JcePartialDataError("Not enough data to read float")

        start = self._pos
        self._pos += 4
        buf = self._view[start : self._pos]

        # 根据字节序选项进行主要解码
        primary = (_STRUCT_f_LE if self._little_endian else _STRUCT_f).unpack(
            buf
        )[0]

        # 如果已经是小端,直接返回
        if self._little_endian:
            return cast(float, primary)

        # 备用:当大端产生不可信的值时,尝试小端
        alt = _STRUCT_f_LE.unpack(buf)[0]
        if not math.isfinite(primary) and math.isfinite(alt):
            return cast(float, alt)

        if math.isfinite(alt):
            # 当主值异常大时,更喜欢较小幅度的值
            if abs(primary) > 1e9 and abs(alt) <= 1e6:
                return cast(float, alt)

        return cast(float, primary)

    def read_double(self) -> float:
        """读取8字节双精度浮点数."""
        if self._pos + 8 > self._len:
            raise JcePartialDataError("Not enough data to read double")

        start = self._pos
        self._pos += 8
        buf = self._view[start : self._pos]

        primary = (_STRUCT_d_LE if self._little_endian else _STRUCT_d).unpack(
            buf
        )[0]

        if self._little_endian:
            return cast(float, primary)

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
        if self._pos + size > self._len:
            raise JcePartialDataError(f"Not enough data to unpack {size} bytes")
        # memoryview can be passed directly to unpack_from
        val = packer.unpack_from(self._view, self._pos)
        self._pos += size
        return val

    @property
    def eof(self) -> bool:
        """检查是否到达流末尾."""
        return self._pos >= self._len


class GenericDecoder:
    """JCE数据的无模式解码器.

    根据标签和类型将JCE二进制数据解析为Python dicts和lists.
    """

    def __init__(self, reader: DataReader, option: int = 0):
        self._reader = reader
        self._option = option
        self._recursion_limit = 100
        self._zero_copy = bool(option & OPT_ZERO_COPY)

    def decode(self, suppress_log: bool = False) -> dict[int, Any]:
        """将整个流解码为标签字典."""
        if not suppress_log:
            logger.debug("GenericDecoder: 开始解码 %d 字节", self._reader._len)
        try:
            result = {}
            while not self._reader.eof:
                tag, type_id = self._read_head()
                if type_id == JCE_STRUCT_END:
                    break

                value = self._read_value(type_id)
                result[tag] = value

            if not suppress_log:
                logger.debug("GenericDecoder: 成功解码 %d 个标签", len(result))
            return result
        except Exception as e:
            if not suppress_log:
                logger.error("GenericDecoder: 解码错误: %s", e)
                if hasattr(self._reader, "_view") and hasattr(
                    self._reader, "_pos"
                ):
                    logger.error(
                        get_hexdump(self._reader._view, self._reader._pos)
                    )  # type: ignore
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
        elif type_id == JCE_INT1:
            return self._reader.read_int1()
        elif type_id == JCE_INT2:
            return self._reader.read_int2()
        elif type_id == JCE_INT4:
            return self._reader.read_int4()
        elif type_id == JCE_INT8:
            return self._reader.read_int8()
        elif type_id == JCE_FLOAT:
            return self._reader.read_float()
        elif type_id == JCE_DOUBLE:
            return self._reader.read_double()
        elif type_id == JCE_STRING1:
            length = self._reader.read_u8()
            return self._reader.read_bytes(length, self._zero_copy)
        elif type_id == JCE_STRING4:
            length = self._reader.read_int4()  # Length is always 4 bytes int
            return self._reader.read_bytes(length, self._zero_copy)
        elif type_id == JCE_LIST:
            return self._read_list()
        elif type_id == JCE_MAP:
            return self._read_map()
        elif type_id == JCE_STRUCT_BEGIN:
            return self._read_struct()
        elif type_id == JCE_STRUCT_END:
            pass
        elif type_id == JCE_SIMPLE_LIST:
            return self._read_simple_list()
        else:
            raise JceDecodeError(f"Unknown JCE Type ID: {type_id}")

    def _read_list(self) -> list[Any]:
        self._check_recursion()
        self._recursion_limit -= 1
        try:
            length = self._read_integer_generic()
            result = []
            for _ in range(length):
                _tag, type_id = self._read_head()
                result.append(self._read_value(type_id))
            return result
        finally:
            self._recursion_limit += 1

    def _read_map(self) -> dict[Any, Any]:
        self._check_recursion()
        self._recursion_limit -= 1
        try:
            length = self._read_integer_generic()
            result: dict[Any, Any] = {}
            for _ in range(length):
                # 读取键
                _k_tag, k_type = self._read_head()
                key = self._read_value(k_type)

                # 读取值
                _v_tag, v_type = self._read_head()
                val = self._read_value(v_type)

                # 处理不可哈希的键
                if isinstance(key, (dict, list)):
                    key = self._freeze_key(key)

                result[key] = val
            return result
        finally:
            self._recursion_limit += 1

    def _read_struct(self) -> dict[int, Any]:
        self._check_recursion()
        self._recursion_limit -= 1
        try:
            result = {}
            while True:
                # 窥视以检查STRUCT_END
                b = self._reader.peek_u8()
                type_id = b & 0x0F
                tag = (b & 0xF0) >> 4
                if tag == 15:
                    # 需要读取下一个字节来确定,但peek只给出1个字节.
                    # 如果标签是15,类型在第一个字节中.
                    pass

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
        # 头部(已读) -> 类型(0) -> 长度 -> 数据
        type_tag, type_id = self._read_head()
        if type_id != JCE_INT1 and type_tag != 0:
            pass

        # "Type Byte"实际上是指示元素类型的JCE头部.
        # 对于SimpleList,必须是BYTE.
        if type_id != JCE_INT1:  # INT1是0,是BYTE类型id
            raise JceDecodeError(
                f"SimpleList expected BYTE type, got {type_id}"
            )

        length = self._read_integer_generic()
        return self._reader.read_bytes(length, self._zero_copy)

    def _read_integer_generic(self) -> int:
        """Read an integer for Length fields (which are JCE encoded integers)."""
        _tag, type_id = self._read_head()
        return cast(int, self._read_value(type_id))

    def _check_recursion(self):
        if self._recursion_limit <= 0:
            raise RecursionError("JCE recursion limit exceeded")

    def _freeze_key(self, obj: Any) -> Any:
        """Convert mutable objects to immutable ones for use as dict keys."""
        if isinstance(obj, dict):
            return tuple(
                sorted((k, self._freeze_key(v)) for k, v in obj.items())
            )
        elif isinstance(obj, list):
            return tuple(self._freeze_key(x) for x in obj)
        return obj


class SchemaDecoder:
    """基于模式的JCE数据解码器.

    使用字段定义将JCE数据解码为JceStruct实例.
    此解码器针对已知模式进行了优化 - 它仅解析
    定义在目标类中的字段,并跳过未知字段.
    """

    def __init__(self, reader: DataReader, target_cls: Any, option: int = 0):
        self._reader = reader
        self._target_cls = target_cls
        self._option = option
        self._fields = getattr(target_cls, "__jce_fields__", {})
        # 构建jce_id -> (field_name, field_type)的映射以快速查找
        self._field_map: dict[int, tuple[str, Any]] = {
            field.jce_id: (name, field.jce_type)
            for name, field in self._fields.items()
        }
        self._recursion_limit = 100
        self._zero_copy = bool(option & OPT_ZERO_COPY)

    def decode(self) -> Any:
        """将流解码为target_cls实例."""
        result = self.decode_to_dict()
        return self._target_cls.model_validate(result)

    def decode_to_dict(self) -> dict[str, Any]:
        """将流解码为字典(仅包含Schema中定义的字段)."""
        logger.debug("SchemaDecoder: 开始解码为 %s", self._target_cls.__name__)
        try:
            result: dict[str, Any] = {}

            while not self._reader.eof:
                tag, type_id = self._read_head()

                # 检查是否是结构体的结束
                if type_id == JCE_STRUCT_END:
                    break

                # 检查我们的模式中是否有该字段
                if tag in self._field_map:
                    field_name, _expected_type = self._field_map[tag]
                    # 根据类型解码值
                    value = self._read_value(type_id)
                    result[field_name] = value
                else:
                    # 跳过该字段,因为它不在我们的模式中
                    logger.debug(
                        "SchemaDecoder: 跳过未知标签 %d (类型 %d)", tag, type_id
                    )
                    self._skip_value(type_id)

            logger.debug("SchemaDecoder: 成功解码 %d 个字段", len(result))
            return result
        except Exception as e:
            logger.error(
                "SchemaDecoder: 解码 %s 时出错: %s",
                self._target_cls.__name__,
                e,
            )
            if hasattr(self._reader, "_view") and hasattr(self._reader, "_pos"):
                logger.error(get_hexdump(self._reader._view, self._reader._pos))  # type: ignore
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
        """根据类型ID读取值."""
        if type_id == JCE_ZERO_TAG:
            return 0
        elif type_id == JCE_INT1:
            return self._reader.read_int1()
        elif type_id == JCE_INT2:
            return self._reader.read_int2()
        elif type_id == JCE_INT4:
            return self._reader.read_int4()
        elif type_id == JCE_INT8:
            return self._reader.read_int8()
        elif type_id == JCE_FLOAT:
            return self._reader.read_float()
        elif type_id == JCE_DOUBLE:
            return self._reader.read_double()
        elif type_id == JCE_STRING1:
            length = self._reader.read_u8()
            return self._reader.read_bytes(length, self._zero_copy)
        elif type_id == JCE_STRING4:
            length = self._reader.read_int4()
            return self._reader.read_bytes(length, self._zero_copy)
        elif type_id == JCE_LIST:
            return self._read_list()
        elif type_id == JCE_MAP:
            return self._read_map()
        elif type_id == JCE_STRUCT_BEGIN:
            return self._read_struct()
        elif type_id == JCE_SIMPLE_LIST:
            return self._read_simple_list()
        else:
            raise JceDecodeError(f"Unknown JCE Type ID: {type_id}")

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
            self._reader.skip(length)
        elif type_id == JCE_LIST:
            self._skip_list()
        elif type_id == JCE_MAP:
            self._skip_map()
        elif type_id == JCE_STRUCT_BEGIN:
            self._skip_struct()
        elif type_id == JCE_SIMPLE_LIST:
            self._skip_simple_list()

    def _read_list(self) -> list[Any]:
        """读取列表值."""
        self._check_recursion()
        self._recursion_limit -= 1
        try:
            length = self._read_integer_generic()
            result = []
            for _ in range(length):
                _tag, type_id = self._read_head()
                result.append(self._read_value(type_id))
            return result
        finally:
            self._recursion_limit += 1

    def _skip_list(self) -> None:
        """跳过列表值."""
        length = self._read_integer_generic()
        for _ in range(length):
            _tag, type_id = self._read_head()
            self._skip_value(type_id)

    def _read_map(self) -> dict[Any, Any]:
        """读取映射值."""
        self._check_recursion()
        self._recursion_limit -= 1
        try:
            length = self._read_integer_generic()
            result: dict[Any, Any] = {}
            for _ in range(length):
                _k_tag, k_type = self._read_head()
                key = self._read_value(k_type)
                _v_tag, v_type = self._read_head()
                val = self._read_value(v_type)
                # 处理不可哈希的键
                if isinstance(key, (dict, list)):
                    key = self._freeze_key(key)
                result[key] = val
            return result
        finally:
            self._recursion_limit += 1

    def _skip_map(self) -> None:
        """跳过映射值."""
        length = self._read_integer_generic()
        for _ in range(length):
            _k_tag, k_type = self._read_head()
            self._skip_value(k_type)
            _v_tag, v_type = self._read_head()
            self._skip_value(v_type)

    def _read_struct(self) -> dict[int, Any]:
        """将嵌套结构体读取为字典."""
        self._check_recursion()
        self._recursion_limit -= 1
        try:
            result = {}
            while True:
                b = self._reader.peek_u8()
                type_id = b & 0x0F
                if type_id == JCE_STRUCT_END:
                    self._reader.read_u8()
                    break
                tag, type_id = self._read_head()
                result[tag] = self._read_value(type_id)
            return result
        finally:
            self._recursion_limit += 1

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

    def _read_simple_list(self) -> bytes | memoryview:
        """读取简单列表(字节数组)."""
        _type_tag, type_id = self._read_head()
        if type_id != JCE_INT1:
            raise JceDecodeError(
                f"SimpleList expected BYTE type, got {type_id}"
            )
        length = self._read_integer_generic()
        return self._reader.read_bytes(length, self._zero_copy)

    def _skip_simple_list(self) -> None:
        """跳过简单列表."""
        _type_tag, _type_id = self._read_head()
        length = self._read_integer_generic()
        self._reader.skip(length)

    def _read_integer_generic(self) -> int:
        """读取长度字段的整数(JCE编码整数)."""
        _tag, type_id = self._read_head()
        return cast(int, self._read_value(type_id))

    def _check_recursion(self) -> None:
        """检查递归深度以防止堆栈溢出."""
        if self._recursion_limit <= 0:
            raise RecursionError("JCE recursion limit exceeded")

    def _freeze_key(self, obj: Any) -> Any:
        """将可变对象转换为不可变对象以用作字典键."""
        if isinstance(obj, dict):
            return tuple(
                sorted((k, self._freeze_key(v)) for k, v in obj.items())
            )
        elif isinstance(obj, list):
            return tuple(self._freeze_key(x) for x in obj)
        return obj
