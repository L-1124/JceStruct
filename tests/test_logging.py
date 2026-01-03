"""JCE日志记录测试."""

import logging

import pytest

from jce import JceField, JceStruct, types


class SimpleStruct(JceStruct):
    """测试用的简单结构体."""

    name: types.STRING = JceField(jce_id=1)
    age: types.INT = JceField(jce_id=2)


def test_logging_success(caplog: pytest.LogCaptureFixture) -> None:
    """测试成功编码和解码的日志记录."""
    caplog.set_level(logging.DEBUG, logger="jce")

    # Test Encoding Success Log
    s = SimpleStruct(name="Alice", age=30)
    data = s.encode()

    assert "JceEncoder: 开始编码类型为 SimpleStruct 的对象" in caplog.text
    assert "JceEncoder: 成功编码" in caplog.text

    # Test Decoding Success Log
    caplog.clear()
    SimpleStruct.decode(data)

    assert "SchemaDecoder: 开始解码为 SimpleStruct" in caplog.text
    assert "SchemaDecoder: 成功解码" in caplog.text


def test_logging_error_hexdump(caplog: pytest.LogCaptureFixture) -> None:
    """测试解码错误时的十六进制上下文转储."""
    caplog.set_level(logging.ERROR, logger="jce")

    # Create malformed data (truncated string)
    # Tag 1 (String1), Length 5, Content "Alic" (missing 'e')
    data = bytes.fromhex("16 05 41 6c 69 63")

    with pytest.raises(Exception):
        SimpleStruct.decode(data)

    assert "SchemaDecoder: 解码 SimpleStruct 时出错" in caplog.text
    assert "上下文 (显示 0-6):" in caplog.text
    # Hexdump content check
    assert "16 05 41 6c 69 63" in caplog.text


def test_logging_unknown_field(caplog: pytest.LogCaptureFixture) -> None:
    """测试解码时跳过未知字段的日志记录."""
    caplog.set_level(logging.DEBUG, logger="jce")

    # Existing field: Tag 1 (String) = "A"
    # Unknown field: Tag 3 (Int1) = 1
    # Existing field: Tag 2 (Int) = 10
    data = bytes.fromhex("16 01 41 30 01 20 0A")

    SimpleStruct.decode(data)

    assert "SchemaDecoder: 跳过未知标签 3" in caplog.text
