# 类型存根文件 - 手动维护
# 基于 Rust PyO3 绑定的类型定义

from collections.abc import Iterator
from typing import Any, Generic, TypeVar, overload

T = TypeVar("T")

__all__ = [
    "LengthPrefixedReader",
    "LengthPrefixedWriter",
    "dumps",
    "dumps_generic",
    "loads",
    "loads_generic",
]

class LengthPrefixedReader(Generic[T]):
    """从流缓冲区读取带长度前缀的 Tarsio 数据包.

    处理 TCP 粘包和数据包分片问题.

    Examples:
        >>> reader = LengthPrefixedReader(target=MyStruct, length_type=4)
        >>> reader.feed(data_chunk)
        >>> for packet in reader:
        ...     print(packet)
    """

    @overload
    def __new__(
        cls,
        target: type[T],
        option: int = 0,
        max_buffer_size: int = 10485760,
        context: dict[str, Any] | None = None,
        length_type: int = 4,
        inclusive_length: bool = True,
        little_endian_length: bool = False,
        bytes_mode: int = 2,
    ) -> LengthPrefixedReader[T]: ...
    @overload
    def __new__(
        cls,
        target: Any,
        option: int = 0,
        max_buffer_size: int = 10485760,
        context: dict[str, Any] | None = None,
        length_type: int = 4,
        inclusive_length: bool = True,
        little_endian_length: bool = False,
        bytes_mode: int = 2,
    ) -> LengthPrefixedReader[Any]: ...
    def __new__(
        cls,
        target: Any,
        option: int = 0,
        max_buffer_size: int = 10485760,
        context: dict[str, Any] | None = None,
        length_type: int = 4,
        inclusive_length: bool = True,
        little_endian_length: bool = False,
        bytes_mode: int = 2,
    ) -> LengthPrefixedReader[Any]:
        """初始化读取器.

        Args:
            target: 用于解码的目标类（Struct 子类）或 None（通用解码）.
            option: 解码选项（位标志）.
            max_buffer_size: 允许的最大缓冲区大小（字节），防止 DoS 攻击.
            context: 反序列化上下文.
            length_type: 长度前缀的字节大小（1、2 或 4）.
            inclusive_length: 长度值是否包含长度前缀本身.
            little_endian_length: 长度前缀是否为小端序.
            bytes_mode: 通用解码的字节处理模式（0: Raw, 1: String, 2: Auto）.

        Raises:
            ValueError: 如果 length_type 不是 1、2 或 4.
        """

    def feed(self, data: bytes) -> None:
        """将数据追加到内部缓冲区.

        Args:
            data: 要追加的字节数据.

        Raises:
            BufferError: 如果缓冲区超过 max_buffer_size.
        """

    def __iter__(self) -> Iterator[T]:
        """返回迭代器自身."""

    def __next__(self) -> T:
        """迭代缓冲区中的完整数据包.

        Returns:
            从缓冲区解码的对象（Struct 实例或 dict）.

        Raises:
            StopIteration: 当没有完整数据包可用时.
            ValueError: 如果数据包格式错误.
        """

    def clear(self) -> None:
        """清空内部缓冲区."""

class LengthPrefixedWriter:
    """写入带长度前缀的 Tarsio 数据包.

    辅助类，用于将数据打包成带长度头的流传输格式.

    Examples:
        >>> writer = LengthPrefixedWriter(length_type=4)
        >>> writer.pack(my_struct)
        >>> data = writer.get_buffer()
    """

    def __new__(
        cls,
        length_type: int = 4,
        inclusive_length: bool = True,
        little_endian_length: bool = False,
        options: int = 0,
    ) -> LengthPrefixedWriter:
        """初始化写入器.

        Args:
            length_type: 长度前缀的字节大小（1、2 或 4）.
            inclusive_length: 长度值是否包含长度前缀本身.
            little_endian_length: 长度前缀是否为小端序.
            options: 序列化选项（位标志）.

        Raises:
            ValueError: 如果 length_type 不是 1、2 或 4.
        """

    def pack(self, obj: Any) -> None:
        """将对象打包成带长度前缀的数据包.

        使用 JCE 编码对象并将数据包追加到缓冲区.

        Args:
            obj: 要打包的对象（Struct 实例或 dict/StructDict）.

        Raises:
            TypeError: 如果对象类型不支持序列化.
            ValueError: 如果数据太大无法放入长度前缀.
        """

    def write(self, obj: Any) -> None:
        """Pack 的别名."""

    def write_bytes(self, data: bytes) -> None:
        """将原始字节作为带长度前缀的数据包写入.

        Args:
            data: 原始字节负载.
        """

    def get_buffer(self) -> bytes:
        """获取当前缓冲区内容.

        Returns:
            累积的缓冲区内容（所有已打包数据包的字节串联）.
        """

    def clear(self) -> None:
        """清空内部缓冲区."""

def dumps(
    obj: Any,
    schema: list[Any] | type,
    options: int = 0,
) -> bytes:
    """将 Struct 序列化为字节.

    Args:
        obj: 要序列化的 Struct 实例.
        schema: 从 Struct 派生的 schema 列表 (id, field_info) 或 Struct 类.
        options: 序列化选项（位标志）.

    Returns:
        序列化后的 JCE 字节数据.

    Raises:
        TypeError: 如果对象类型与 schema 不匹配.
        ValueError: 如果字段值无效.
    """

def dumps_generic(
    data: Any,
    options: int = 0,
) -> bytes:
    """将通用对象序列化为字节，无需 schema.

    Args:
        data: 要序列化的对象（键为整数 tag 的 dict 或 StructDict）.
        options: 序列化选项（位标志）.

    Returns:
        序列化后的 JCE 字节数据.

    Raises:
        TypeError: 如果 obj 不是 dict 或键不是整数.
    """

@overload
def loads(
    data: bytes,
    target: type[T],
    options: int = 0,
) -> T: ...
@overload
def loads(
    data: bytes,
    target: None = None,
    options: int = 0,
) -> dict[int, Any]: ...
def loads(
    data: bytes,
    target: Any | None = None,
    options: int = 0,
) -> Any:
    """将字节反序列化为 JceStruct.

    Args:
        data: 要反序列化的 JCE 字节数据.
        target: 目标 JceStruct 类或 None. 如果为 None，则等同于 loads_generic.
        options: 反序列化选项.

    Returns:
        instance: 实例化的 JceStruct 对象或字典.

    Raises:
        ValueError: 如果数据格式无效或解码失败.
    """

def loads_generic(
    data: bytes,
    options: int = 0,
    bytes_mode: int = 2,
) -> dict[int, Any]:
    """将字节反序列化为通用字典（StructDict），无需 schema.

    Args:
        data: 要反序列化的 JCE 字节数据.
        options: 反序列化选项（位标志）.
        bytes_mode: 处理字节的模式 (0: Raw, 1: String, 2: Auto).

    Returns:
        包含反序列化数据的字典 (tag -> 值，兼容 StructDict).

    Raises:
        ValueError: 如果数据格式无效或解码失败.
    """
