"""JCE API模块.

为JCE序列化提供`loads`和`dumps`函数.
"""

from typing import TYPE_CHECKING, Any, TypeVar, cast, overload

from jce.decoder import DataReader, GenericDecoder, SchemaDecoder
from jce.encoder import JceEncoder
from jce.options import OPT_NETWORK_BYTE_ORDER

if TYPE_CHECKING:
    from jce.types import JceStruct

T = TypeVar("T", bound="JceStruct")


def _is_valid_printable_string(s: str, ascii_only: bool = False) -> bool:
    if not s:
        return True

    if ascii_only:
        # 仅ASCII可打印字符(32-127)
        return all(32 <= ord(c) < 127 for c in s)
    else:
        # 可打印字符或控制字符\n\t\r
        return all(c.isprintable() or c in "\n\t\r" for c in s)


def _auto_convert_bytes(data: Any, smart: bool = True) -> Any:
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if isinstance(key, bytes):
                try:
                    decoded_key = key.decode("utf-8")
                    if _is_valid_printable_string(
                        decoded_key, ascii_only=False
                    ):
                        key = decoded_key
                except UnicodeDecodeError:
                    pass
            result[key] = _auto_convert_bytes(value, smart)
        return result

    elif isinstance(data, list):
        return [_auto_convert_bytes(item, smart) for item in data]

    elif isinstance(data, bytes):
        if not smart:
            return list(data)

        # 空字节串直接转为空字符串
        if len(data) == 0:
            return ""

        # 优先尝试作为JCE数据解析(用于SimpleList等嵌入的JCE结构)
        try:
            reader = DataReader(data, option=0)
            decoder = GenericDecoder(reader, option=0)
            parsed = decoder.decode()
            return _auto_convert_bytes(parsed, smart=True)
        except Exception:
            pass

        # 如果JCE解析失败，尝试作为纯文本字符串(仅ASCII可打印)
        try:
            decoded = data.decode("utf-8")
            if _is_valid_printable_string(decoded, ascii_only=True):
                return decoded
        except UnicodeDecodeError:
            pass

        return data

    else:
        return data


def dumps(
    obj: Any,
    option: int = OPT_NETWORK_BYTE_ORDER,
    default: Any | None = None,
) -> bytes:
    """序列化对象为JCE字节.

    Args:
        obj: 要序列化的对象(JceStruct或dict).
        option: 格式化选项(例如OPT_LITTLE_ENDIAN).
        default: 未知类型的默认函数.

    Returns:
        JCE编码的字节.
    """
    encoder = JceEncoder(option, default)
    return encoder.encode(obj)


@overload
def loads(
    data: bytes | bytearray | memoryview,
    target: type[T],
    option: int = OPT_NETWORK_BYTE_ORDER,
) -> T: ...


@overload
def loads(
    data: bytes | bytearray | memoryview,
    target: type[dict[Any, Any]] = dict,
    option: int = OPT_NETWORK_BYTE_ORDER,
) -> dict[int, Any]: ...


def loads(
    data: bytes | bytearray | memoryview,
    target: type[T] | type[dict[Any, Any]] = dict,
    option: int = OPT_NETWORK_BYTE_ORDER,
) -> T | dict[int, Any]:
    """反序列化JCE字节为对象.

    Args:
        data: 二进制数据.
        target: 目标类(JceStruct子类或dict).
        option: 格式化选项(例如OPT_LITTLE_ENDIAN).

    Returns:
        目标类的实例或dict.
    """
    reader = DataReader(data, option)

    # 使用'is'检查dict，这是常见的模式，或使用'issubclass'安全检查
    if target is dict:
        decoder = GenericDecoder(reader, option)
        result = decoder.decode()
        return _auto_convert_bytes(result, smart=True)
    else:
        # 假设target是JceStruct子类
        # 我们需要帮助类型检查器，因为T被绑定到JceStruct
        # 但此处的target被严格检查.
        # 但是，SchemaDecoder接受Any target_cls.
        decoder = SchemaDecoder(reader, target, option)
        return cast(T, decoder.decode())
