"""JCE API模块.

提供用于 JCE 序列化和反序列化的高级接口 `dumps`, `loads`, `dump`, `load`.
支持 JceStruct 对象、JceDict 以及普通 Python 类型的编解码。
"""

from typing import IO, Any, Literal, TypeVar, cast, overload

from .config import JceConfig
from .decoder import (
    DataReader,
    GenericDecoder,
    SchemaDecoder,
    convert_bytes_recursive,
)
from .encoder import JceEncoder
from .options import JceOption
from .struct import JceDict, JceStruct

T = TypeVar("T", bound=JceStruct)
BytesMode = Literal["raw", "string", "auto"]


def _jcedict_to_plain_dict(obj: Any) -> Any:
    """递归将 JceDict 转换为普通 dict.

    - JceDict -> dict（保持 int 键不变）
    - list/tuple -> 列表内元素递归转换
    - 普通 dict -> 值递归转换（键保持原样）
    - 其他类型 -> 原样返回
    """
    if isinstance(obj, JceDict):
        return {k: _jcedict_to_plain_dict(v) for k, v in obj.items()}
    if isinstance(obj, dict):
        return {k: _jcedict_to_plain_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jcedict_to_plain_dict(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_jcedict_to_plain_dict(v) for v in obj)
    return obj


@overload
def dumps(
    obj: JceStruct,
    option: JceOption = JceOption.NONE,
    default: Any | None = None,
    context: dict[str, Any] | None = None,
    exclude_unset: bool = False,
) -> bytes: ...


@overload
def dumps(
    obj: Any,
    option: JceOption = JceOption.NONE,
    default: Any | None = None,
    context: dict[str, Any] | None = None,
    exclude_unset: bool = False,
) -> bytes: ...


def dumps(
    obj: Any,
    option: JceOption = JceOption.NONE,
    default: Any | None = None,
    context: dict[str, Any] | None = None,
    exclude_unset: bool = False,
) -> bytes:
    """序列化对象为 JCE 字节数据.

    Args:
        obj: 要序列化的 Python 对象. 支持 `JceStruct` 实例, `JceDict`, `dict`, `list` 等.
        option: 序列化选项 (如 `JceOption.LITTLE_ENDIAN`).
        default: 自定义序列化函数, 用于处理无法默认序列化的类型.
            函数签名应为 `def default(obj: Any) -> Any`.
        context: 序列化上下文字典.
            这个字典会传递给字段的自定义序列化器 (`@jce_field_serializer`)，
            用于传递外部状态（如数据库连接、配置等）。
        exclude_unset: 是否排除未显式设置的字段.
            仅对 JceStruct (Pydantic 模型) 有效. 默认为 False.

    Returns:
        bytes: 序列化后的二进制数据.

    Examples:
        >>> from jce import dumps, JceStruct, JceField
        >>> class User(JceStruct):
        ...     uid: int = JceField(jce_id=0)
        >>> user = User(uid=123)
        >>> dumps(user).hex()
        '02007b'
    """
    config = JceConfig.from_params(
        option=option,
        default=default,
        context=context,
        exclude_unset=exclude_unset,
    )
    encoder = JceEncoder(config)
    return encoder.encode(obj)


@overload
def dump(
    obj: JceStruct,
    fp: IO[bytes],
    option: JceOption = JceOption.NONE,
    default: Any | None = None,
    context: dict[str, Any] | None = None,
    exclude_unset: bool = False,
) -> None: ...


@overload
def dump(
    obj: Any,
    fp: IO[bytes],
    option: JceOption = JceOption.NONE,
    default: Any | None = None,
    context: dict[str, Any] | None = None,
    exclude_unset: bool = False,
) -> None: ...


def dump(
    obj: Any,
    fp: IO[bytes],
    option: JceOption = JceOption.NONE,
    default: Any | None = None,
    context: dict[str, Any] | None = None,
    exclude_unset: bool = False,
) -> None:
    """序列化对象为 JCE 字节并写入文件.

    Args:
        obj: 要序列化的对象.
        fp: 文件类对象, 必须实现 `write(bytes)` 方法.
        option: 序列化选项.
        default: 未知类型的默认处理函数.
        context: 序列化上下文.
        exclude_unset: 是否排除未设置的字段 (仅 JceStruct).
    """
    fp.write(
        dumps(
            obj,
            option=option,
            default=default,
            context=context,
            exclude_unset=exclude_unset,
        )
    )


@overload
def loads(
    data: bytes | bytearray | memoryview,
    target: type[T],
    option: JceOption = JceOption.NONE,
    *,
    bytes_mode: BytesMode = "auto",
    context: dict[str, Any] | None = None,
) -> T: ...


@overload
def loads(
    data: bytes | bytearray | memoryview,
    target: type[JceDict] = JceDict,
    option: JceOption = JceOption.NONE,
    *,
    bytes_mode: BytesMode = "auto",
    context: dict[str, Any] | None = None,
) -> JceDict: ...


@overload
def loads(
    data: bytes | bytearray | memoryview,
    target: type[dict],
    option: JceOption = JceOption.NONE,
    *,
    bytes_mode: BytesMode = "auto",
    context: dict[str, Any] | None = None,
) -> dict[int, Any]: ...


def loads(
    data: bytes | bytearray | memoryview,
    target: type[T] | type[JceDict] | type[dict] = JceDict,
    option: JceOption = JceOption.NONE,
    *,
    bytes_mode: BytesMode = "auto",
    context: dict[str, Any] | None = None,
) -> T | JceDict | dict[int, Any]:
    """反序列化 JCE 字节为 Python 对象.

    Args:
        data: 输入的二进制数据 (bytes, bytearray 或 memoryview).
        target: 目标类型.
            - `JceStruct` 子类: 尝试解析并验证为该结构体实例.
            - `JceDict` (默认): 解析为 JceDict 实例 (Struct 语义).
            - `dict`: 解析为普通 dict（将 JceDict 递归转换为 dict）。
        option: 反序列化选项 (如 `JceOption.LITTLE_ENDIAN`).
        bytes_mode: 字节数据的处理模式 (仅对通用解析 target=JceDict/dict 有效).
            - `'raw'`: 保持所有 bytes 类型不变.
            - `'string'`: 尝试将 **所有** bytes 解码为 UTF-8 字符串.
            - `'auto'`: 智能模式 (推荐).
              1. 无损解码: 优先尝试 UTF-8 解码.
              2. JCE 探测: 尝试作为嵌套 JCE 结构解析.
              3. 回退: 保持为 bytes.
        context: 反序列化上下文.
            传递给 `JceStruct` 的验证器或自定义反序列化器 (`@jce_field_deserializer`).

    Returns:
        T: 目标类型实例 (如果 target=JceStruct).
        JceDict: 结构体数据 (如果 target=JceDict).
        dict: 字典数据 (如果 target=dict).

    Raises:
        JceDecodeError: 数据格式错误.
        JcePartialDataError: 数据不完整.
    """
    reader = DataReader(data, option)

    # 通用解码
    if target is JceDict or target is dict:
        decoder = GenericDecoder(reader, option)
        # 1. 解码
        result = decoder.decode()
        # 2. 递归处理 bytes (保持 JceDict 类型)
        final_result = convert_bytes_recursive(result, mode=bytes_mode, option=option)
        # 3. 如目标为 dict，则递归将 JceDict 转换为普通 dict
        if target is dict:
            return cast(dict[int, Any], _jcedict_to_plain_dict(final_result))
        return cast(JceDict, final_result)

    # Schema 模式
    decoder = SchemaDecoder(reader, target, option, context, bytes_mode=bytes_mode)
    return cast(T, decoder.decode())


@overload
def load(
    fp: IO[bytes],
    target: type[T],
    option: JceOption = JceOption.NONE,
    *,
    bytes_mode: BytesMode = "auto",
    context: dict[str, Any] | None = None,
) -> T: ...


@overload
def load(
    fp: IO[bytes],
    target: type[JceDict] = JceDict,
    option: JceOption = JceOption.NONE,
    *,
    bytes_mode: BytesMode = "auto",
    context: dict[str, Any] | None = None,
) -> JceDict: ...


@overload
def load(
    fp: IO[bytes],
    target: type[dict],
    option: JceOption = JceOption.NONE,
    *,
    bytes_mode: BytesMode = "auto",
    context: dict[str, Any] | None = None,
) -> dict[int, Any]: ...


def load(
    fp: IO[bytes],
    target: type[T] | type[JceDict] | type[dict] = JceDict,
    option: JceOption = JceOption.NONE,
    *,
    bytes_mode: BytesMode = "auto",
    context: dict[str, Any] | None = None,
) -> T | JceDict | dict[int, Any]:
    """从文件读取并反序列化 JCE 数据.

    封装了 `read()` 和 `loads()`.

    Args:
        fp: 打开的二进制文件对象.
        target: 目标类型.
        option: JCE 选项.
        bytes_mode: 字节处理模式.
        context: 上下文.

    Returns:
        解析后的对象.
    """
    data = fp.read()
    return loads(
        data,
        target=target,
        option=option,
        bytes_mode=bytes_mode,
        context=context,
    )
