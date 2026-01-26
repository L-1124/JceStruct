"""测试 JCE 流式处理.

覆盖 jce.stream 模块的核心特性:
1. 基础流读写 (Buffer management)
2. 长度前缀协议 (LengthPrefixedWriter/Reader)
3. 网络场景模拟 (粘包、拆包)
4. 边界条件 (Max buffer size, Length limits)
"""

import struct
from typing import cast

import pytest
from jce import JceDict, JceField, JceStruct
from jce.stream import (
    LengthPrefixedReader,
    LengthPrefixedWriter,
)


class StreamMsg(JceStruct):
    """用于流传输测试的简单消息."""

    id: int = JceField(jce_id=0)
    data: str = JceField(jce_id=1)


# --- 基础流写入器测试 ---


def test_stream_writer_basic() -> None:
    """LengthPrefixedWriter 应能正确缓存和清空数据."""
    writer = LengthPrefixedWriter()
    msg = StreamMsg(id=1, data="a")

    writer.write(msg)
    writer.write_bytes(b"\xff")

    buf = writer.get_buffer()
    assert len(buf) > 0
    assert buf.endswith(b"\xff")

    writer.clear()
    assert len(writer.get_buffer()) == 0


# --- 基础流读取器测试 ---


def test_stream_reader_basic() -> None:
    """LengthPrefixedReader 应能正确接收数据并执行缓冲区检查."""
    reader = LengthPrefixedReader(target=JceDict)

    reader.feed(b"\x00\x01")

    # LengthPrefixedReader 是可迭代的，如果没有完整包，迭代应为空
    assert list(reader) == []

    small_reader = LengthPrefixedReader(target=JceDict, max_buffer_size=5)
    small_reader.feed(b"123")

    with pytest.raises(BufferError, match="max size"):
        small_reader.feed(b"456")


def test_stream_reader_with_jcedict_target() -> None:
    """LengthPrefixedReader 应支持 JceDict 作为 target."""
    reader = LengthPrefixedReader(target=JceDict)

    reader.feed(b"\x00\x64")

    assert reader._target == JceDict  # type: ignore


# --- 长度前缀协议测试 ---


def test_length_prefixed_round_trip_defaults() -> None:
    """LengthPrefixedWriter/Reader 默认配置下应能正确处理粘包."""
    writer = LengthPrefixedWriter()
    msg1 = StreamMsg(id=1, data="hello")
    msg2 = StreamMsg(id=2, data="world")

    writer.pack(msg1)
    writer.pack(msg2)

    full_data = writer.get_buffer()

    reader = LengthPrefixedReader(target=StreamMsg)
    reader.feed(full_data)

    packets = cast(list[StreamMsg], list(reader))
    assert len(packets) == 2
    assert packets[0].id == 1
    assert packets[0].data == "hello"
    assert packets[1].id == 2
    assert packets[1].data == "world"


def test_length_prefixed_custom_config() -> None:
    """LengthPrefixedWriter/Reader 应支持自定义长度头配置."""
    writer = LengthPrefixedWriter(
        length_type=2, little_endian_length=True, inclusive_length=False
    )

    msg = StreamMsg(id=1, data="a")
    writer.pack(msg)
    data = writer.get_buffer()

    body_len = len(data) - 2
    header_val = struct.unpack("<H", data[:2])[0]
    assert header_val == body_len

    reader = LengthPrefixedReader(
        target=StreamMsg,
        length_type=2,
        little_endian_length=True,
        inclusive_length=False,
    )
    reader.feed(data)
    packets = cast(list[StreamMsg], list(reader))
    assert len(packets) == 1
    assert packets[0].data == "a"


def test_length_prefixed_fragmentation() -> None:
    """LengthPrefixedReader 应能处理数据分片到达 (拆包)."""
    writer = LengthPrefixedWriter()
    writer.pack(StreamMsg(id=1, data="long_message"))
    full_data = writer.get_buffer()

    reader = LengthPrefixedReader(target=StreamMsg)

    reader.feed(full_data[:5])
    assert list(reader) == []

    reader.feed(full_data[5:])
    packets = cast(list[StreamMsg], list(reader))
    assert len(packets) == 1
    assert packets[0].data == "long_message"


def test_reader_partial_header() -> None:
    """LengthPrefixedReader 应能处理头部尚未接收完整的情况."""
    reader = LengthPrefixedReader(target=dict, length_type=4)

    reader.feed(b"\x00\x00")
    assert list(reader) == []

    reader = LengthPrefixedReader(target=dict, length_type=4, inclusive_length=True)

    reader.feed(b"\x00\x00")
    assert list(reader) == []

    reader.feed(b"\x00\x06")
    assert list(reader) == []

    reader.feed(b"\x00\x01")

    packets = list(reader)
    assert len(packets) == 1
    assert packets[0] == {0: 1}


def test_length_prefixed_reader_with_jcedict() -> None:
    """LengthPrefixedReader 应支持 JceDict 作为 target."""
    writer = LengthPrefixedWriter()
    test_data = JceDict({0: 100, 1: "test"})
    writer.pack(test_data)

    reader = LengthPrefixedReader(target=JceDict)
    reader.feed(writer.get_buffer())

    packets = list(reader)
    assert len(packets) == 1
    assert isinstance(packets[0], JceDict)
    assert packets[0][0] == 100
    assert packets[0][1] == "test"


# --- 异常边界测试 ---


def test_writer_length_limit() -> None:
    """LengthPrefixedWriter 在包大小超过 Header 表示范围时应抛出 ValueError."""
    writer = LengthPrefixedWriter(length_type=1)

    large_msg = StreamMsg(id=1, data="x" * 300)

    with pytest.raises(ValueError, match="Packet too large"):
        writer.pack(large_msg)


def test_invalid_length_type() -> None:
    """Stream 组件初始化时应校验 length_type 参数."""
    with pytest.raises(ValueError, match="length_type must be"):
        LengthPrefixedWriter(length_type=3)

    with pytest.raises(ValueError, match="length_type must be"):
        LengthPrefixedReader(target=dict, length_type=3)
