"""JCE流式处理模块.

该模块提供用于网络协议和流处理的 Writer 和 Reader 类.
支持增量编码和解码.
"""

import struct
from collections.abc import Generator
from typing import Any, cast

import jce_core
from jce_core import LengthPrefixedReader as _RustLengthPrefixedReader

from .api import BytesMode, dumps, loads
from .config import JceConfig
from .options import JceOption
from .struct import JceDict, JceStruct


class JceStreamWriter:
    """JCE流式写入器.

    允许增量序列化多个对象到同一个缓冲区.
    """

    def __init__(
        self,
        option: JceOption = JceOption.NONE,
        default: Any = None,
        context: dict[str, Any] | None = None,
    ):
        """初始化流式写入器.

        Args:
            option: JCE 选项 (如字节序).
            default: 自定义序列化函数 (用于处理未知类型).
            context: 序列化上下文.
        """
        self._config = JceConfig.from_params(
            option=option,
            default=default,
            context=context,
        )
        self._buffer = bytearray()

    def pack(self, obj: Any) -> None:
        """序列化对象并追加到缓冲区."""
        data = dumps(
            obj,
            option=self._config.flags,
            default=self._config.default,
            context=self._config.context,
            exclude_unset=self._config.exclude_unset,
        )
        self._buffer.extend(data)

    def write(self, obj: Any) -> None:
        """序列化对象并追加到缓冲区."""
        self.pack(obj)

    def pack_bytes(self, data: bytes) -> None:
        """直接追加原始字节."""
        self._buffer.extend(data)

    def write_bytes(self, data: bytes) -> None:
        """直接追加原始字节."""
        self.pack_bytes(data)

    def get_buffer(self) -> bytes:
        """获取缓冲区数据的副本."""
        return bytes(self._buffer)

    def clear(self) -> None:
        """清空缓冲区."""
        self._buffer.clear()


class JceStreamReader:
    """JCE流式读取器.

    支持通过 feed_data() 方法输入数据.
    """

    def __init__(
        self,
        target: Any,
        option: JceOption = JceOption.NONE,
        max_buffer_size: int = 10 * 1024 * 1024,  # 10MB
        context: dict[str, Any] | None = None,
        bytes_mode: str = "auto",
    ):
        """初始化流式读取器.

        Args:
            target: 目标类型 (JceStruct 子类或 dict).
            option: JCE 选项.
            max_buffer_size: 最大缓冲区大小 (防止内存耗尽).
            context: 反序列化上下文.
            bytes_mode: 字节处理模式 ("auto", "string", "raw").
        """
        self._target = target
        self._option = option
        self._buffer = bytearray()
        self._max_buffer_size = max_buffer_size
        self._context = context
        self._bytes_mode = bytes_mode

    def feed(self, data: bytes | bytearray | memoryview) -> None:
        """输入数据到内部缓冲区."""
        if len(self._buffer) + len(data) > self._max_buffer_size:
            raise BufferError("JceStreamReader buffer exceeded max size")
        self._buffer.extend(data)

    def feed_data(self, data: bytes | bytearray | memoryview) -> None:
        """输入数据到内部缓冲区."""
        self.feed(data)

    def __iter__(self) -> Generator[Any, None, None]:
        """迭代解析出的对象.

        纯 JCE 流不支持连续对象解析, 因为没有外部定界符.
        请使用 LengthPrefixedStreamReader.
        """
        raise NotImplementedError("Use LengthPrefixedUnpacker for stream decoding")


class LengthPrefixedWriter(JceStreamWriter):
    """带长度前缀的写入器.

    在序列化数据前自动添加长度头部，用于解决 TCP 粘包问题。
    格式: `[Length][Data]`

    Args:
        option: JCE 选项.
        default: 默认序列化函数.
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

    def __init__(
        self,
        option: JceOption = JceOption.NONE,
        default: Any = None,
        context: dict[str, Any] | None = None,
        length_type: int = 4,  # 1, 2, 或 4 字节
        inclusive_length: bool = True,  # 长度包含头部本身
        little_endian_length: bool = False,  # 长度字段字节序
    ):
        """初始化带长度前缀的写入器.

        Args:
            option: JCE 选项.
            default: 默认序列化函数.
            context: 序列化上下文.
            length_type: 长度字段字节数 (1, 2, 4).
            inclusive_length: 长度是否包含头部本身.
            little_endian_length: 长度字段是否使用小端序.
        """
        super().__init__(option, default, context)
        if length_type not in {1, 2, 4}:
            raise ValueError("length_type must be 1, 2, or 4")
        self._length_type = length_type
        self._inclusive_length = inclusive_length
        self._little_endian_length = little_endian_length

    def pack(self, obj: Any) -> None:
        """序列化对象, 添加长度前缀, 并追加到缓冲区."""
        # 1. 编码包体
        body = dumps(
            obj,
            option=self._config.flags,
            default=self._config.default,
            context=self._config.context,
            exclude_unset=self._config.exclude_unset,
        )

        # 2. 计算长度

        length = len(body)
        if self._inclusive_length:
            length += self._length_type

        # 3. 编码长度头
        header = self._pack_length(length)

        # 4. 追加
        self._buffer.extend(header)
        self._buffer.extend(body)

    def _pack_length(self, length: int) -> bytes:
        endian = "<" if self._little_endian_length else ">"
        if self._length_type == 1:
            if length > 255:
                raise ValueError(f"Packet too large for 1-byte length: {length}")
            return struct.pack(f"{endian}B", length)
        elif self._length_type == 2:
            if length > 65535:
                raise ValueError(f"Packet too large for 2-byte length: {length}")
            return struct.pack(f"{endian}H", length)
        else:  # 4
            if length > 4294967295:
                raise ValueError(f"Packet too large for 4-byte length: {length}")
            return struct.pack(f"{endian}I", length)


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
        max_buffer_size: int = 10 * 1024 * 1024,
        context: dict[str, Any] | None = None,
        length_type: int = 4,
        inclusive_length: bool = True,
        little_endian_length: bool = False,
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
