"""JCE数据类型模块.

本模块定义了JCE协议支持的所有数据类型,包括基本类型(INT、STRING等)
和复杂类型(LIST、MAP等)。
"""

from typing import (
    Any,
    TypeVar,
)

from .const import (
    JCE_STRUCT_BEGIN,
    JCE_STRUCT_END,
    JCE_ZERO_TAG,
)

ZERO_TAG = JCE_ZERO_TAG
STRUCT_START = JCE_STRUCT_BEGIN
STRUCT_END = JCE_STRUCT_END

T = TypeVar("T", bound="JceType")
VT = TypeVar("VT", bound="JceType")


class JceType:
    """JCE 数据类型的基类.

    所有具体的 JCE 类型（如 `INT`, `STRING`, `LIST` 等）都继承自此类。
    通常用户不需要直接使用此类，而是使用具体的子类来定义 `JceStruct` 的字段类型。
    """

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> Any:
        from pydantic_core import core_schema

        return core_schema.any_schema()


class INT(JceType):
    """JCE 整数类型 (抽象基类).

    对应 JCE 协议中的所有整数类型 (byte, short, int, long)。
    在定义字段时，建议使用具体的子类 (`INT8`, `INT16`, `INT32`, `INT64`)
    以明确数据范围，也可以使用 `INT` 让编码器自动根据值的大小选择最节省空间的类型。
    """


class INT8(INT):
    """1 字节整数 (Char/Byte).

    对应 JCE 协议中的 `byte` 类型 (Type ID 0 或 1).
    范围: -128 到 127.
    """


class INT16(INT):
    """2 字节整数 (Short).

    对应 JCE 协议中的 `short` 类型 (Type ID 1).
    范围: -32768 到 32767.
    """


class INT32(INT):
    """4 字节整数 (Int).

    对应 JCE 协议中的 `int` 类型 (Type ID 2).
    范围: -2147483648 到 2147483647.
    """


class INT64(INT):
    """8 字节整数 (Long).

    对应 JCE 协议中的 `long` 类型 (Type ID 3).
    范围: -9223372036854775808 到 9223372036854775807.
    """


class BYTE(JceType):
    """字节类型 (无符号).

    这通常作为一个特殊标记使用，或者在 SimpleList 中表示元素类型。
    在 JCE 协议中，没有单独的 Unsigned Byte 类型，通常映射为 `INT8`。
    """


class BOOL(JceType):
    """JCE 布尔类型.

    JCE 协议原生不支持 bool，此类型在序列化时映射为 `INT8` (Type ID 0/1)。
    True -> 1, False -> 0.
    """


class FLOAT(JceType):
    """JCE 单精度浮点数 (Float).

    对应 JCE 协议中的 `float` 类型 (Type ID 4)。
    占用 4 字节。
    """


class DOUBLE(JceType):
    """JCE 双精度浮点数 (Double).

    对应 JCE 协议中的 `double` 类型 (Type ID 5)。
    占用 8 字节。
    """


class STRING(JceType):
    """JCE 字符串类型 (String).

    对应 JCE 协议中的 `String1` (Type ID 6) 或 `String4` (Type ID 7)。
    编码器会根据字符串长度自动选择：
    - 长度 <= 255: 使用 `String1` (1字节长度前缀).
    - 长度 > 255: 使用 `String4` (4字节长度前缀).
    """


class STRING1(STRING):
    """短字符串 (String1).

    对应 JCE 协议中的 `String1` 类型 (Type ID 6)。
    最大长度 255 字节。
    """


class STRING4(STRING):
    """长字符串 (String4).

    对应 JCE 协议中的 `String4` 类型 (Type ID 7)。
    最大长度 4GB (理论值)。
    """


class BYTES(JceType):
    """JCE 字节数组类型.

    对应 JCE 协议中的 `SimpleList` 类型 (Type ID 13).
    专门用于传输二进制数据 (`bytes` 或 `bytearray`).
    它比普通的 `LIST` (Type ID 9) 更紧凑，因为不需要为每个字节写入 Tag/Type。
    """


class LIST(JceType):
    """JCE 列表类型 (List).

    对应 JCE 协议中的 `List` 类型 (Type ID 9)。
    用于表示同质或异质的元素列表。
    """


class MAP(JceType):
    """JCE 映射类型 (Map).

    对应 JCE 协议中的 `Map` 类型 (Type ID 8)。
    用于表示键值对集合。
    """
