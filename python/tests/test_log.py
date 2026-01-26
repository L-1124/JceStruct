"""测试 JCE 日志模块."""

import logging

from jce.log import get_hexdump, logger


def test_logger_config() -> None:
    """验证 Logger 默认配置不包含 Handler 且名称正确."""
    assert logger.name == "jce"
    assert not logger.handlers
    assert logger.level == logging.NOTSET


def test_get_hexdump_basic() -> None:
    """get_hexdump() 应正确格式化十六进制数据."""
    data = b"\x01\x02\x03"
    dump = get_hexdump(data, pos=1, window=1)

    assert "01 02" in dump.lower()


def test_get_hexdump_boundaries() -> None:
    """get_hexdump() 应正确处理数据起始和结束边界."""
    data = b"\xaa\xbb\xcc"

    dump_start = get_hexdump(data, pos=0, window=1)
    assert "aa" in dump_start.lower()

    dump_end = get_hexdump(data, pos=2, window=1)
    assert "bb cc" in dump_end.lower()


def test_get_hexdump_empty() -> None:
    """get_hexdump() 应能处理空字节输入而不报错."""
    dump = get_hexdump(b"", pos=0)
    assert dump
    assert "位置" in dump


def test_get_hexdump_large_window() -> None:
    """get_hexdump() 应能处理窗口大于数据长度的情况."""
    data = b"\x01"
    dump = get_hexdump(data, pos=0, window=10)
    assert "01" in dump


def test_get_hexdump_out_of_bounds_pos() -> None:
    """get_hexdump() 应能优雅处理越界的位置参数."""
    data = b"\x01"
    try:
        dump = get_hexdump(data, pos=10)
        assert dump
    except IndexError:
        pass
