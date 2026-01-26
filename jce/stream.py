"""JCE流式处理模块.

该模块提供用于网络协议和流处理的 Writer 和 Reader 类.
支持增量编码和解码.
"""

from typing import Any, cast

from jce_core import (
    LengthPrefixedReader as _RustLengthPrefixedReader,
)
from jce_core import (
    LengthPrefixedWriter as _RustLengthPrefixedWriter,
)

from .options import JceOption
from .struct import JceDict, JceStruct


class LengthPrefixedWriter(_RustLengthPrefixedWriter):
    """带长度前缀的写入器.

    在序列化数据前自动添加长度头部，用于解决 TCP 粘包问题。
    格式: `[Length][Data]`

    该类使用 Rust 核心实现以获得高性能。

    Args:
        option: JCE 选项.
        default: 默认序列化函数 (暂不支持，保留参数兼容性).
        context: 序列化上下文.
        length_type: 长度字段的字节数 (1, 2, 或 4).
            - 1: 1字节长度 (Max 255)
            - 2: 2字节长度 (Max 65535)
            - 4: 4字节长度 (Max 4GB)
        inclusive_length: 长度值是否包含头部本身的长度.
            - True: TotalSize (Header + Body)
            - False: BodySize
        little_endian_length: 长度字段是否使用小端序.
    """

    def __new__(
        cls,
        option: JceOption = JceOption.NONE,
        default: Any = None,  # noqa: ARG004
        context: dict[str, Any] | None = None,
        length_type: int = 4,
        inclusive_length: bool = True,
        little_endian_length: bool = False,
    ):
        """创建 LengthPrefixedWriter 实例."""
        return super().__new__(  # type: ignore
            cls,
            length_type=length_type,
            inclusive_length=inclusive_length,
            little_endian_length=little_endian_length,
            options=int(option),
            context=context if context is not None else {},
        )

    def __init__(
        self,
        option: JceOption = JceOption.NONE,
        default: Any = None,
        context: dict[str, Any] | None = None,
        length_type: int = 4,  # 1, 2, 或 4 字节
        inclusive_length: bool = True,  # 长度包含头部本身
        little_endian_length: bool = False,  # 长度字段字节序
    ):
        """初始化带长度前缀的写入器."""
        # Rust 核心已完成初始化
        pass


class LengthPrefixedReader(_RustLengthPrefixedReader):
    """带长度前缀的读取器.

    自动处理 TCP 粘包/拆包，从流中提取完整的数据包并反序列化。
    该类使用 Rust 核心实现以获得高性能。

    Usage:
        >>> reader = LengthPrefixedReader(target=MyStruct)
        >>> reader.feed(received_bytes)
        >>> for obj in reader:
        ...     process(obj)
    """

    _target: Any
    _context: dict[str, Any] | None
    _option: JceOption
    _bytes_mode: str

    def __new__(
        cls,
        target: Any,
        option: JceOption = JceOption.NONE,
        max_buffer_size: int = 10 * 1024 * 1024,
        context: dict[str, Any] | None = None,
        length_type: int = 4,
        inclusive_length: bool = True,
        little_endian_length: bool = False,
        bytes_mode: str = "auto",
    ):
        """创建 LengthPrefixedReader 实例."""
        # 映射 BytesMode 字符串为 Rust 需要的整数
        mode_int = 2  # default auto

        if bytes_mode == "raw":
            mode_int = 0
        elif bytes_mode == "string":
            mode_int = 1

        # 调用 Rust 核心的 __new__ (对应 Rust 中的 #[new])
        return super().__new__(  # type: ignore
            cls,
            target=target,
            option=int(option),
            max_buffer_size=max_buffer_size,
            context=context if context is not None else {},
            length_type=length_type,
            inclusive_length=inclusive_length,
            little_endian_length=little_endian_length,
            bytes_mode=mode_int,
        )

    def __init__(
        self,
        target: Any,
        option: JceOption = JceOption.NONE,
        max_buffer_size: int = 10 * 1024 * 1024,  # noqa: ARG002
        context: dict[str, Any] | None = None,
        length_type: int = 4,  # noqa: ARG002
        inclusive_length: bool = True,  # noqa: ARG002
        little_endian_length: bool = False,  # noqa: ARG002
        bytes_mode: str = "auto",
    ):
        """初始化带长度前缀的读取器.

        Args:
            target: 目标类型.
            option: JCE 选项.
            max_buffer_size: 最大缓冲区大小.
            context: 上下文.
            length_type: 长度字段字节数.
            inclusive_length: 长度是否包含头部.
            little_endian_length: 长度字段是否小端序.
            bytes_mode: 字节处理模式.
        """
        # 注意：基类初始化已在 __new__ 中由 Rust 核心完成
        self._target = target
        self._context = context
        self._option = option
        self._bytes_mode = bytes_mode

    def feed_data(self, data: bytes | bytearray | memoryview) -> None:
        """输入数据到内部缓冲区 (向后兼容)."""
        self.feed(cast(bytes, data))

    def __next__(self) -> Any:
        """获取下一个解析出的对象.

        Returns:
            Any: 解析出的对象实例.
        """
        obj = super().__next__()

        # 后处理逻辑: 支持 Pydantic 验证和 JceDict 包装
        if isinstance(self._target, type) and issubclass(self._target, JceStruct):
            return self._target.model_validate(obj, context=self._context)
        if self._target is JceDict:
            return JceDict(obj)
        return obj
