"""JCE API模块.

提供用于 Tarsio 序列化和反序列化的高级接口 `dumps`, `loads`, `dump`, `load`.
支持 Struct 对象、StructDict 以及普通 Python 类型的编解码。
"""

from typing import IO, Any, Literal, TypeVar, cast, overload

from . import _core as core
from .config import Config
from .options import Option
from .struct import Struct, StructDict

T = TypeVar("T", bound=Struct)
BytesMode = Literal["raw", "string", "auto"]


@overload
def dumps(
    obj: Struct,
    option: Option = Option.NONE,
    context: dict[str, Any] | None = None,
    exclude_unset: bool = False,
) -> bytes: ...


@overload
def dumps(
    obj: Any,
    option: Option = Option.NONE,
    context: dict[str, Any] | None = None,
    exclude_unset: bool = False,
) -> bytes: ...


def dumps(
    obj: Any,
    option: Option = Option.NONE,
    context: dict[str, Any] | None = None,
    exclude_unset: bool = False,
) -> bytes:
    """序列化对象为 JCE 字节数据.

    Args:
        obj: 要序列化的 Python 对象. 支持 `Struct` 实例, `StructDict`, `dict`, `list` 等.
        option: 序列化选项 (如 `Option.LITTLE_ENDIAN`).
        context: 序列化上下文字典.
            这个字典会传递给字段的自定义序列化器 (`@field_serializer`)，
            用于传递外部状态（如数据库连接、配置等）。
        exclude_unset: 是否排除未显式设置的字段.
            仅对 Struct (Pydantic 模型) 有效. 默认为 False.

    Returns:
        bytes: 序列化后的二进制数据.

    Examples:
        >>> from tarsio import dumps, Struct, Field
        >>> class User(Struct):
        ...     uid: int = Field(id=0)
        >>> user = User(uid=123)
        >>> dumps(user).hex()
        '02007b'
    """
    config = Config.from_params(
        option=option,
        context=context,
        exclude_unset=exclude_unset,
    )

    if isinstance(obj, Struct):
        # 使用 Rust 核心进行序列化
        # 内部使用的 EXCLUDE_UNSET 标志位 (64)
        raw_options = int(config.option)
        if config.exclude_unset:
            raw_options |= 64

        return core.dumps(
            obj,
            obj.__get_core_schema__(),
            raw_options,
            config.context if config.context is not None else {},
        )

    # 使用 Rust 核心进行通用序列化
    # Rust 核心会自动处理 StructDict (作为 Struct) 和 其他类型 (包装在 Tag 0 中)
    data_to_dump = obj
    if not isinstance(obj, StructDict):
        data_to_dump = {0: obj}

    return core.dumps_generic(
        data_to_dump,
        int(config.option),
        config.context if config.context is not None else {},
    )


@overload
def dump(
    obj: Struct,
    fp: IO[bytes],
    option: Option = Option.NONE,
    context: dict[str, Any] | None = None,
    exclude_unset: bool = False,
) -> None: ...


@overload
def dump(
    obj: Any,
    fp: IO[bytes],
    option: Option = Option.NONE,
    context: dict[str, Any] | None = None,
    exclude_unset: bool = False,
) -> None: ...


def dump(
    obj: Any,
    fp: IO[bytes],
    option: Option = Option.NONE,
    context: dict[str, Any] | None = None,
    exclude_unset: bool = False,
) -> None:
    """序列化对象为 JCE 字节并写入文件.

    Args:
        obj: 要序列化的对象.
        fp: 文件类对象, 必须实现 `write(bytes)` 方法.
        option: 序列化选项.
        context: 序列化上下文.
        exclude_unset: 是否排除未设置的字段 (仅 Struct).
    """
    fp.write(
        dumps(
            obj,
            option=option,
            context=context,
            exclude_unset=exclude_unset,
        )
    )


@overload
def loads(
    data: bytes | bytearray | memoryview,
    target: type[T],
    option: Option = Option.NONE,
    *,
    bytes_mode: BytesMode = "auto",
    context: dict[str, Any] | None = None,
) -> T: ...


@overload
def loads(
    data: bytes | bytearray | memoryview,
    target: type[StructDict] = StructDict,
    option: Option = Option.NONE,
    *,
    bytes_mode: BytesMode = "auto",
    context: dict[str, Any] | None = None,
) -> StructDict: ...


@overload
def loads(
    data: bytes | bytearray | memoryview,
    target: type[dict],
    option: Option = Option.NONE,
    *,
    bytes_mode: BytesMode = "auto",
    context: dict[str, Any] | None = None,
) -> dict[int, Any]: ...


def loads(
    data: bytes | bytearray | memoryview,
    target: type[T] | type[StructDict] | type[dict] = StructDict,
    option: Option = Option.NONE,
    *,
    bytes_mode: BytesMode = "auto",
    context: dict[str, Any] | None = None,
) -> T | StructDict | dict[int, Any]:
    """反序列化 JCE 字节为 Python 对象.

    Args:
        data: 输入的二进制数据 (bytes, bytearray 或 memoryview).
        target: 目标类型.
            - `Struct` 子类: 尝试解析并验证为该结构体实例.
            - `StructDict` (默认): 解析为 StructDict 实例 (Struct 语义).
            - `dict`: 解析为普通 dict（将 StructDict 递归转换为 dict）。
        option: 反序列化选项 (如 `Option.LITTLE_ENDIAN`).
        bytes_mode: 字节数据的处理模式 (仅对通用解析 target=StructDict/dict 有效).
            - `'raw'`: 保持所有 bytes 类型不变.
            - `'string'`: 尝试将 **所有** bytes 解码为 UTF-8 字符串.
            - `'auto'`: 智能模式 (推荐).
              1. 无损解码: 优先尝试 UTF-8 解码.
              2. JCE 探测: 尝试作为嵌套 JCE 结构解析.
              3. 回退: 保持为 bytes.
        context: Pydantic 验证器上下文.

    Returns:
        T: 目标类型实例 (如果 target=Struct).
        StructDict: 结构体数据 (如果 target=StructDict).
        dict: 字典数据 (如果 target=dict).

    Raises:
        DecodeError: 数据格式错误.
        PartialDataError: 数据不完整.
    """
    # 通用解码
    if target is StructDict or target is dict:
        # Map BytesMode string to integer for Rust
        mode_int = 2  # default auto
        if bytes_mode == "raw":
            mode_int = 0
        elif bytes_mode == "string":
            mode_int = 1

        # 使用 Rust 核心进行通用反序列化
        result = core.loads_generic(
            bytes(data),
            int(option),
            mode_int,
        )

        # 3. 如目标为 dict，则直接返回 (Rust 已经返回了纯 dict)
        if target is dict:
            return cast(dict[int, Any], result)

        # 4. 默认目标为 StructDict，需要将顶层转换为 StructDict
        if not isinstance(result, StructDict):
            result = StructDict(result)
        return cast(StructDict, result)

    # Schema 模式
    if issubclass(target, Struct):
        # 使用 Rust 核心进行反序列化并直接实例化
        # 注意: core.loads 现在直接返回实例
        return core.loads(
            bytes(data),
            target,
            int(option),
            context,
        )

    raise NotImplementedError("Please use Struct or supported types.")


@overload
def load(
    fp: IO[bytes],
    target: type[T],
    option: Option = Option.NONE,
    *,
    bytes_mode: BytesMode = "auto",
    context: dict[str, Any] | None = None,
) -> T: ...


@overload
def load(
    fp: IO[bytes],
    target: type[StructDict] = StructDict,
    option: Option = Option.NONE,
    *,
    bytes_mode: BytesMode = "auto",
    context: dict[str, Any] | None = None,
) -> StructDict: ...


@overload
def load(
    fp: IO[bytes],
    target: type[dict],
    option: Option = Option.NONE,
    *,
    bytes_mode: BytesMode = "auto",
    context: dict[str, Any] | None = None,
) -> dict[int, Any]: ...


def load(
    fp: IO[bytes],
    target: type[T] | type[StructDict] | type[dict] = StructDict,
    option: Option = Option.NONE,
    *,
    bytes_mode: BytesMode = "auto",
    context: dict[str, Any] | None = None,
) -> T | StructDict | dict[int, Any]:
    """从文件读取并反序列化 Tarsio 数据.

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
