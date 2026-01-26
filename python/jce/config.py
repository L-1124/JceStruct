"""JCE 配置对象."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from .options import JceOption

BytesMode = Literal["raw", "string", "auto"]


@dataclass(frozen=True)
class JceConfig:
    """JCE 序列化/反序列化配置 (不可变).

    这是所有配置的统一容器, 在 API 入口层创建,
    然后传递给 Encoder/Decoder 内核.

    Attributes:
        flags: JCE 选项标志 (IntFlag).
        default: 未知类型的默认序列化处理函数.
        context: 用户提供的上下文数据.
        exclude_unset: 是否排除未设置的字段 (仅 Pydantic 模型).
        bytes_mode: 反序列化时字节数据的处理模式.
    """

    flags: JceOption = JceOption.NONE
    default: Callable[[Any], Any] | None = None
    context: dict[str, Any] = field(default_factory=dict)
    exclude_unset: bool = False
    bytes_mode: BytesMode = "auto"

    @classmethod
    def from_params(
        cls,
        option: JceOption = JceOption.NONE,
        default: Callable[[Any], Any] | None = None,
        context: dict[str, Any] | None = None,
        exclude_unset: bool = False,
        bytes_mode: BytesMode = "auto",
    ) -> "JceConfig":
        """从参数构建配置对象.

        Args:
            option: JceOption 枚举.
            default: 未知类型的默认序列化处理函数.
            context: 用户提供的上下文数据.
            exclude_unset: 是否排除未设置的字段.
            bytes_mode: 反序列化时字节数据的处理模式.

        Returns:
            JceConfig: 配置对象.
        """
        # 处理 context None
        ctx = context if context is not None else {}

        return cls(
            flags=option,
            default=default,
            context=ctx,
            exclude_unset=exclude_unset,
            bytes_mode=bytes_mode,
        )

    @property
    def is_little_endian(self) -> bool:
        """是否使用小端字节序."""
        return bool(self.flags & JceOption.LITTLE_ENDIAN)

    @property
    def is_strict_map(self) -> bool:
        """是否强制严格的 Map 标签."""
        return bool(self.flags & JceOption.STRICT_MAP)

    @property
    def serialize_none(self) -> bool:
        """是否序列化 None 值."""
        return bool(self.flags & JceOption.SERIALIZE_NONE)

    @property
    def zero_copy(self) -> bool:
        """是否使用零复制模式."""
        return bool(self.flags & JceOption.ZERO_COPY)

    @property
    def omit_default(self) -> bool:
        """是否省略默认值."""
        return bool(self.flags & JceOption.OMIT_DEFAULT)

    @property
    def option(self) -> int:
        """返回 int 形式的 option 值 (用于传递给底层 DataReader/DataWriter)."""
        return int(self.flags)
