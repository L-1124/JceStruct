"""JCE API模块.

提供用于 JCE 序列化和反序列化的高级接口 `dumps`, `loads`, `dump`, `load`.
支持 JceStruct 对象、JceDict 以及普通 Python 类型的编解码。
"""

from typing import IO, Any, Literal, TypeVar, cast, overload

import jce_core

from .config import JceConfig
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


def _is_safe_text(text: str) -> bool:
    """检查字符串是否主要由可打印字符组成 (用于 auto 模式)."""
    if not text:
        return True
    # 允许常见的控制字符
    allowed = {"\n", "\r", "\t"}
    for char in text:
        if char in allowed:
            continue
        # 检查是否为不可打印字符 (C0 控制字符)
        if ord(char) < 32 or ord(char) == 127:
            return False
    return True


def convert_bytes_recursive(
    obj: Any, mode: BytesMode = "auto", option: JceOption = JceOption.NONE
) -> Any:
    """递归处理对象中的 bytes (从 decoder.py 移植)."""
    if mode == "raw":
        return obj

    if isinstance(obj, bytes | bytearray | memoryview):
        data = bytes(obj)
        if mode == "string":
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError:
                return data
        elif mode == "auto":
            # 1. 尝试 UTF-8 且是 "安全" 的文本
            try:
                text = data.decode("utf-8")
                if _is_safe_text(text):
                    return text
            except UnicodeDecodeError:
                pass

            # 2. 尝试作为 JCE 结构解析 (递归)
            # 只有当数据看起来像 JCE 结构时才尝试 (简单的启发式: 长度 > 0)
            if len(data) > 0:
                try:
                    # 尝试解析为 JceDict
                    # 注意: 这里递归调用 loads 会导致无限递归如果解析成功但结果还是 bytes
                    # 所以我们需要小心。
                    # 实际上，如果它是嵌套 JCE，loads_generic 会返回 dict
                    decoded = jce_core.loads_generic(data, int(option), None)
                    if isinstance(decoded, dict) and len(decoded) > 0:
                        # 递归处理解码后的内容
                        return convert_bytes_recursive(decoded, mode, option)
                except Exception:
                    pass

            return data

    if isinstance(obj, list):
        return [convert_bytes_recursive(v, mode, option) for v in obj]

    if isinstance(obj, dict):
        # JceDict 或 dict
        # 递归处理键和值
        res = {
            convert_bytes_recursive(k, mode, option): convert_bytes_recursive(
                v, mode, option
            )
            for k, v in obj.items()
        }

        # 启发式判断: 如果所有键都是整数, 且它不是一个 Map (或者我们处于 auto 模式),
        # 将其转换为 JceDict 以支持 test_jcedict_as_nested_struct
        if res and all(isinstance(k, int) for k in res.keys()):
            if not isinstance(res, JceDict):
                return JceDict(res)

        if isinstance(obj, JceDict) and not isinstance(res, JceDict):
            return JceDict(res)
        return res

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

    if isinstance(obj, JceStruct):
        # 使用 Rust 核心进行序列化
        if default is None:
            # 内部使用的 EXCLUDE_UNSET 标志位 (64)
            raw_options = int(config.option)
            if config.exclude_unset:
                raw_options |= 64

            return jce_core.dumps(
                obj,
                obj.__get_jce_core_schema__(),
                raw_options,
                config.context if config.context is not None else {},
            )
    elif (
        isinstance(
            obj, JceDict | dict | list | tuple | str | int | float | bytes | bool
        )
        and default is None
    ):
        # 使用 Rust 核心进行通用序列化
        return jce_core.dumps_generic(
            obj,
            int(config.option),
            config.context if config.context is not None else {},
        )

    raise NotImplementedError(
        "Legacy Python encoder has been removed. Please use JceStruct or supported types."
    )


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
    # 通用解码
    if target is JceDict or target is dict:
        # 使用 Rust 核心进行通用反序列化
        result = jce_core.loads_generic(
            bytes(data),
            int(option),
            context if context is not None else {},
        )
        # Rust 返回的是 dict, 需要转换为 JceDict
        if not isinstance(result, JceDict):
            result = JceDict(result)

        # 2. 递归处理 bytes (保持 JceDict 类型)
        final_result = convert_bytes_recursive(result, mode=bytes_mode, option=option)

        # 3. 如目标为 dict，则递归将 JceDict 转换为普通 dict
        if target is dict:
            return cast(dict[int, Any], _jcedict_to_plain_dict(final_result))
        return cast(JceDict, final_result)

    # Schema 模式
    if issubclass(target, JceStruct):
        # 使用 Rust 核心进行反序列化
        raw_dict = jce_core.loads(
            bytes(data),
            target.__get_jce_core_schema__(),
            int(option),
            context if context is not None else {},
        )
        # Rust 返回的是 dict, 需要通过 Pydantic 验证
        return target.model_validate(raw_dict, context=context)

    raise NotImplementedError("Legacy Python decoder has been removed.")


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
