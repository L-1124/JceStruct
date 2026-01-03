"""JCE协议序列化库.

提供了JceStruct定义、序列化(dumps)和反序列化(loads)功能.
"""

from . import types
from .api import dumps, loads
from .exceptions import (
    JceDecodeError,
    JceEncodeError,
    JceError,
    JcePartialDataError,
)
from .options import (
    OPT_LITTLE_ENDIAN,
    OPT_NETWORK_BYTE_ORDER,
    OPT_OMIT_DEFAULT,
    OPT_SERIALIZE_NONE,
    OPT_STRICT_MAP,
    OPT_ZERO_COPY,
)
from .types import JceField, JceStruct

__all__ = [
    "OPT_LITTLE_ENDIAN",
    "OPT_NETWORK_BYTE_ORDER",
    "OPT_OMIT_DEFAULT",
    "OPT_SERIALIZE_NONE",
    "OPT_STRICT_MAP",
    "OPT_ZERO_COPY",
    "JceDecodeError",
    "JceEncodeError",
    "JceError",
    "JceField",
    "JcePartialDataError",
    "JceStruct",
    "dumps",
    "loads",
    "types",
]
