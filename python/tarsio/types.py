"""JCE 类型定义."""

from enum import IntEnum


class TarsType(IntEnum):
    """Tars 数据类型枚举.

    对应 Tars 协议中的底层 Tag 类型值.
    """

    BYTE = 0
    SHORT = 1
    INT = 2
    LONG = 3
    FLOAT = 4
    DOUBLE = 5
    STRING1 = 6  # 长度 < 256 的字符串
    STRING4 = 7  # 长度 > 256 的字符串
    MAP = 8
    LIST = 9
    STRUCT = 10  # 自定义结构体起始
    STRUCT_END = 11  # 自定义结构体结束 (Tag 0)
    ZERO_TAG = 12  # 数字 0 的特殊优化
    SIMPLE_LIST = 13  # byte 数组 (bytes)

    # 辅助类型 (不直接对应 Wire Type，但在 Schema 中使用)
    VOID = 99


# Aliases
Type = TarsType

BYTE = TarsType.BYTE
SHORT = TarsType.SHORT
INT = TarsType.INT
LONG = TarsType.LONG
FLOAT = TarsType.FLOAT
DOUBLE = TarsType.DOUBLE
STRING1 = TarsType.STRING1
STRING4 = TarsType.STRING4
MAP = TarsType.MAP
LIST = TarsType.LIST
STRUCT_BEGIN = TarsType.STRUCT
STRUCT_END = TarsType.STRUCT_END
ZERO_TAG = TarsType.ZERO_TAG
SIMPLE_LIST = TarsType.SIMPLE_LIST

# Derived types
BOOL = BYTE
BYTES = SIMPLE_LIST
INT8 = BYTE
INT16 = SHORT
INT32 = INT
INT64 = LONG
STRING = STRING1  # Default to short string
