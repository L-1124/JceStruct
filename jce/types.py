"""JCE数据类型模块.

本模块定义了JCE协议支持的所有数据类型,包括基本类型(INT、STRING等)
和复杂类型(LIST、MAP等)。
"""

import abc
import struct
from typing import (
    Any,
    TypeVar,
    cast,
)

from .const import (
    JCE_STRUCT_BEGIN,
    JCE_STRUCT_END,
    JCE_ZERO_TAG,
)

# 导出别名
ZERO_TAG = JCE_ZERO_TAG
STRUCT_START = JCE_STRUCT_BEGIN
STRUCT_END = JCE_STRUCT_END

T = TypeVar("T", bound="JceType")
VT = TypeVar("VT", bound="JceType")


class JceType(abc.ABC):
    """JCE 数据类型的基类.

    所有具体的 JCE 类型（如 `INT`, `STRING`, `LIST` 等）都继承自此类。
    通常用户不需要直接使用此类，而是使用具体的子类来定义 `JceStruct` 的字段类型。
    """

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> Any:
        from pydantic_core import core_schema

        return core_schema.any_schema()

    @classmethod
    @abc.abstractmethod
    def from_bytes(cls, data: bytes) -> tuple[Any, int]:
        """从字节反序列化.

        Args:
            data: 输入字节数据.

        Returns:
            tuple[Any, int]: (解析出的值, 消耗的字节数).
        """
        raise NotImplementedError

    @classmethod
    def to_bytes(cls, tag: int, value: Any) -> bytes:
        """将值序列化为 JCE 字节.

        Args:
            tag: JCE 标签 (Tag ID).
            value: 待序列化的值.

        Returns:
            bytes: 序列化后的字节.
        """
        from .config import JceConfig
        from .encoder import JceEncoder

        config = JceConfig.from_params()
        encoder = JceEncoder(config)
        encoder.encode_value(value, tag, target_type=cls)
        return encoder._writer.get_bytes()

    @classmethod
    def validate(cls, value: Any) -> Any:
        """验证值是否符合类型要求.

        Args:
            value: 待验证的值.

        Returns:
            Any: 验证后的值.

        Raises:
            ValueError: 值无效时.
            TypeError: 类型不匹配时.
        """
        # 基本验证
        if cls is BOOL:
            if not isinstance(value, bool) and not (
                isinstance(value, int) and value in {0, 1}
            ):
                raise ValueError(f"Invalid BOOL value: {value}")
        elif issubclass(cls, INT):
            if isinstance(value, bytes):
                try:
                    return int.from_bytes(value, "big")
                except Exception:
                    pass
            if not isinstance(value, int):
                raise TypeError(f"Expected int, got {type(value).__name__}")
        return value


class INT(JceType):
    """JCE 整数类型 (抽象基类).

    对应 JCE 协议中的所有整数类型 (byte, short, int, long)。
    在定义字段时，建议使用具体的子类 (`INT8`, `INT16`, `INT32`, `INT64`)
    以明确数据范围，也可以使用 `INT` 让编码器自动根据值的大小选择最节省空间的类型。
    """

    pass


class INT8(INT):
    """1 字节整数 (Char/Byte).

    对应 JCE 协议中的 `byte` 类型 (Type ID 0 或 1).
    范围: -128 到 127.
    """

    @classmethod
    def from_bytes(cls, data: bytes) -> tuple[int, int]:
        """从字节解析."""
        return struct.unpack_from(">b", data)[0], 1


class INT16(INT):
    """2 字节整数 (Short).

    对应 JCE 协议中的 `short` 类型 (Type ID 1).
    范围: -32768 到 32767.
    """

    @classmethod
    def from_bytes(cls, data: bytes) -> tuple[int, int]:
        """从字节解析."""
        return struct.unpack_from(">h", data)[0], 2


class INT32(INT):
    """4 字节整数 (Int).

    对应 JCE 协议中的 `int` 类型 (Type ID 2).
    范围: -2147483648 到 2147483647.
    """

    @classmethod
    def from_bytes(cls, data: bytes) -> tuple[int, int]:
        """从字节解析."""
        return struct.unpack_from(">i", data)[0], 4


class INT64(INT):
    """8 字节整数 (Long).

    对应 JCE 协议中的 `long` 类型 (Type ID 3).
    范围: -9223372036854775808 到 9223372036854775807.
    """

    @classmethod
    def from_bytes(cls, data: bytes) -> tuple[int, int]:
        """从字节解析."""
        return struct.unpack_from(">q", data)[0], 8


class BYTE(JceType):
    """字节类型 (无符号).

    这通常作为一个特殊标记使用，或者在 SimpleList 中表示元素类型。
    在 JCE 协议中，没有单独的 Unsigned Byte 类型，通常映射为 `INT8`。
    """

    @classmethod
    def from_bytes(cls, data: bytes) -> tuple[bytes, int]:
        """从字节解析."""
        return data[:1], 1

    @classmethod
    def to_bytes(cls, tag: int, value: Any) -> bytes:
        """序列化为字节."""
        if isinstance(value, bytes) and len(value) == 1:
            val_int = value[0]
            if val_int == 0:
                return bytes([(tag << 4) | 12])  # Zero Tag
            head = (tag << 4) | 0  # Type 0 (BYTE)
            return bytes([head]) + value

        from .config import JceConfig
        from .encoder import JceEncoder

        config = JceConfig.from_params()
        encoder = JceEncoder(config)
        encoder.encode_value(value, tag, target_type=cls)
        return encoder._writer.get_bytes()


class BOOL(JceType):
    """JCE 布尔类型.

    JCE 协议原生不支持 bool，此类型在序列化时映射为 `INT8` (Type ID 0/1)。
    True -> 1, False -> 0.
    """

    @classmethod
    def from_bytes(cls, data: bytes) -> tuple[bool, int]:
        """从字节解析."""
        val, length = INT8.from_bytes(data)
        return bool(val), length


class FLOAT(JceType):
    """JCE 单精度浮点数 (Float).

    对应 JCE 协议中的 `float` 类型 (Type ID 4)。
    占用 4 字节。
    """

    @classmethod
    def from_bytes(cls, data: bytes) -> tuple[float, int]:
        """从字节解析."""
        return struct.unpack_from(">f", data)[0], 4


class DOUBLE(JceType):
    """JCE 双精度浮点数 (Double).

    对应 JCE 协议中的 `double` 类型 (Type ID 5)。
    占用 8 字节。
    """

    @classmethod
    def from_bytes(cls, data: bytes) -> tuple[float, int]:
        """从字节解析."""
        return struct.unpack_from(">d", data)[0], 8


class STRING(JceType):
    """JCE 字符串类型 (String).

    对应 JCE 协议中的 `String1` (Type ID 6) 或 `String4` (Type ID 7)。
    编码器会根据字符串长度自动选择：
    - 长度 <= 255: 使用 `String1` (1字节长度前缀).
    - 长度 > 255: 使用 `String4` (4字节长度前缀).
    """

    pass


class STRING1(STRING):
    """短字符串 (String1).

    对应 JCE 协议中的 `String1` 类型 (Type ID 6)。
    最大长度 255 字节。
    """

    @classmethod
    def from_bytes(cls, data: bytes) -> tuple[str | bytes, int]:
        """从字节解析."""
        length = data[0]
        content = data[1 : 1 + length]
        try:
            return content.decode("utf-8"), 1 + length
        except UnicodeDecodeError:
            return content, 1 + length


class STRING4(STRING):
    """长字符串 (String4).

    对应 JCE 协议中的 `String4` 类型 (Type ID 7)。
    最大长度 4GB (理论值)。
    """

    @classmethod
    def from_bytes(cls, data: bytes) -> tuple[str | bytes, int]:
        """从字节解析."""
        length = struct.unpack_from(">i", data)[0]
        content = data[4 : 4 + length]
        try:
            return content.decode("utf-8"), 4 + length
        except UnicodeDecodeError:
            return content, 4 + length


class BYTES(JceType):
    """JCE 字节数组类型.

    对应 JCE 协议中的 `SimpleList` 类型 (Type ID 13).
    专门用于传输二进制数据 (`bytes` 或 `bytearray`).
    它比普通的 `LIST` (Type ID 9) 更紧凑，因为不需要为每个字节写入 Tag/Type。
    """

    @classmethod
    def from_bytes(cls, data: bytes) -> tuple[bytes, int]:
        """占位实现: 满足 JceType 接口约束.

        注意: 真实的 BYTES (SimpleList) 解析逻辑由 decoder.py 处理,
        因为涉及到复杂的 Tag/Length 结构，无法简单通过静态方法解析.
        """
        if not data:
            return b"", 0
        return data[:1], 1


class LIST(JceType):
    """JCE 列表类型 (List).

    对应 JCE 协议中的 `List` 类型 (Type ID 9)。
    用于表示同质或异质的元素列表。
    """

    @classmethod
    def validate(cls, value: Any) -> Any:
        """验证列表类型."""
        if not isinstance(value, list):
            raise TypeError("Invalid LIST type")
        for item in value:
            # 检查有效的 JCE 类型 (基本检查)
            if (
                not isinstance(item, int | float | str | bytes | bool | list | dict)
                and not hasattr(item, "__jce_fields__")
                and item is not None
            ):
                raise TypeError(f"Invalid LIST item type: {type(item)}")
        return value


class MAP(JceType):
    """JCE 映射类型 (Map).

    对应 JCE 协议中的 `Map` 类型 (Type ID 8)。
    用于表示键值对集合。
    """

    @classmethod
    def validate(cls, value: Any) -> Any:
        """验证映射类型."""
        if not isinstance(value, dict):
            raise TypeError("Invalid MAP type")
        for k, v in value.items():
            if not isinstance(k, int | str | float | bytes | bool) and k is not None:
                raise TypeError(f"Invalid MAP key: {type(k)}")
            if (
                not isinstance(v, int | float | str | bytes | bool | list | dict)
                and not hasattr(v, "__jce_fields__")
                and v is not None
            ):
                raise TypeError(f"Invalid MAP value: {type(v)}")
        return value


def guess_jce_type(value: Any) -> type[JceType]:
    """根据值猜测 JCE 类型."""
    if isinstance(value, bool):
        return INT
    if isinstance(value, int):
        return INT
    if isinstance(value, float):
        return DOUBLE
    if isinstance(value, str):
        return STRING
    if isinstance(value, bytes | bytearray | memoryview):
        return BYTES
    if isinstance(value, list):
        return LIST
    if isinstance(value, dict):
        # JceDict 被视为结构体类型，返回其类型本身
        # 普通 dict 被视为 MAP 类型
        from .struct import JceDict

        if isinstance(value, JceDict):
            return cast(type[JceType], JceDict)
        return MAP
    if hasattr(value, "__jce_fields__"):
        return type(value)  # 返回特定的 JceStruct 类
    raise TypeError(f"Unknown JCE type for {type(value)}")
