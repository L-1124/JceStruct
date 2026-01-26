"""JCE协议序列化库.

提供了JceStruct定义、序列化(dumps)和反序列化(loads)功能.
"""

from .adapter import JceTypeAdapter
from .api import BytesMode, dump, dumps, load, loads
from .config import JceConfig
from .context import (
    SerializationInfo,
    jce_field_serializer,
)
from .exceptions import (
    JceDecodeError,
    JceEncodeError,
    JceError,
    JcePartialDataError,
    JceTypeError,
    JceValueError,
)
from .options import JceOption
from .stream import (
    LengthPrefixedReader,
    LengthPrefixedWriter,
)
from .struct import JceDict, JceField, JceStruct
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
    STRUCT_END,
    STRUCT_START,
    ZERO_TAG,
    JceType,
)

__version__ = "0.2.2"

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
    "STRUCT_END",
    "STRUCT_START",
    "ZERO_TAG",
    "BytesMode",
    "JceConfig",
    "JceDecodeError",
    "JceDict",
    "JceEncodeError",
    "JceError",
    "JceField",
    "JceOption",
    "JcePartialDataError",
    "JceStruct",
    "JceType",
    "JceTypeAdapter",
    "JceTypeError",
    "JceValueError",
    "LengthPrefixedReader",
    "LengthPrefixedWriter",
    "SerializationInfo",
    "__version__",
    "dump",
    "dumps",
    "jce_field_serializer",
    "load",
    "loads",
]
