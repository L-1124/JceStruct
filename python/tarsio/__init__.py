"""Tarsio协议序列化库.

提供了Struct定义、序列化(dumps)和反序列化(loads)功能.
"""

# from .adapter import TarsTypeAdapter
# from .api import BytesMode, dump, dumps, load, loads
from ._core import (
    LengthPrefixedReader,
    LengthPrefixedWriter,
    dumps,
    dumps_generic,
    loads,
    loads_generic,
)

# from .config import Config
# from .context import (
#     SerializationInfo,
#     field_serializer,
# )
from .exceptions import (
    DecodeError,
    EncodeError,
    PartialDataError,
    TarsError,
    TarsTypeError,
    TarsValueError,
)
from .options import Option

# from .stream import (
#     LengthPrefixedReader,
#     LengthPrefixedWriter,
# )
from .struct import Field, Struct, StructDict
from .types import (
    BOOL,
    BYTE,
    BYTES,
    DOUBLE,
    FLOAT,
    INT,
    INT8,
    INT16,
    INT32,
    INT64,
    LIST,
    MAP,
    STRING,
    STRING1,
    STRING4,
    STRUCT_BEGIN,
    STRUCT_END,
    ZERO_TAG,
    Type,
)

__all__ = [
    "BOOL",
    "BYTE",
    "BYTES",
    "DOUBLE",
    "FLOAT",
    "INT",
    "INT8",
    "INT16",
    "INT32",
    "INT64",
    "LIST",
    "MAP",
    "STRING",
    "STRING1",
    "STRING4",
    "STRUCT_BEGIN",
    "STRUCT_END",
    "ZERO_TAG",
    # "BytesMode",
    # "Config",
    "DecodeError",
    "EncodeError",
    "Field",
    "LengthPrefixedReader",
    "LengthPrefixedWriter",
    "Option",
    "PartialDataError",
    # "SerializationInfo",
    "Struct",
    "StructDict",
    "TarsError",
    # "TarsTypeAdapter",
    "TarsTypeError",
    "TarsValueError",
    "Type",
    # "dump",
    "dumps",
    "dumps_generic",
    # "field_serializer",
    # "load",
    "loads",
    "loads_generic",
]
