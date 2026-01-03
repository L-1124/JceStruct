"""JCE基础类型测试."""

from jce import types


def test_byte_encode() -> None:
    """测试字节编码."""
    byte = types.BYTE.to_bytes(jce_id=0, value=b"a")
    assert byte == bytes.fromhex("00 61")

    byte = types.BYTE.to_bytes(jce_id=15, value=b"a")
    assert byte == bytes.fromhex("f0 0f 61")

    byte = types.BYTE.to_bytes(jce_id=0, value=b"\x00")
    assert byte == bytes.fromhex("0c")


def test_byte_decode() -> None:
    """测试字节解码."""
    byte, length = types.BYTE.from_bytes(bytes.fromhex("00 61")[1:])
    assert byte == b"a"
    assert length == 1

    byte, length = types.BYTE.from_bytes(bytes.fromhex("f0 0f 61")[2:])
    assert byte == b"a"
    assert length == 1


def test_bool_encode() -> None:
    """测试布尔值编码."""
    byte = types.BOOL.to_bytes(jce_id=0, value=True)
    assert byte == bytes.fromhex("00 01")

    byte = types.BOOL.to_bytes(jce_id=0, value=False)
    assert byte == bytes.fromhex("0c")


def test_bool_decode() -> None:
    """测试布尔值解码."""
    boolean, length = types.BOOL.from_bytes(bytes.fromhex("00 01")[1:])
    assert boolean
    assert length == 1


def test_bool_validate() -> None:
    """测试布尔值验证."""
    assert types.BOOL.validate(True)
    assert not types.BOOL.validate(False)
    assert types.BOOL.validate(1)
    assert not types.BOOL.validate(0)


def test_int_encode() -> None:
    """测试整数编码."""
    byte = types.INT.to_bytes(jce_id=0, value=1)
    assert byte == bytes.fromhex("00 01")

    byte = types.INT.to_bytes(jce_id=0, value=255)
    assert byte == bytes.fromhex("01 00 ff")

    byte = types.INT.to_bytes(jce_id=0, value=65535)
    assert byte == bytes.fromhex("02 00 00 ff ff")

    byte = types.INT.to_bytes(jce_id=0, value=4294967295)
    assert byte == bytes.fromhex("03 00 00 00 00 ff ff ff ff")

    byte = types.INT.to_bytes(jce_id=0, value=0)
    assert byte == bytes.fromhex("0c")


def test_int_decode() -> None:
    """测试整数解码."""
    integer, length = types.INT8.from_bytes(bytes.fromhex("00 01")[1:])
    assert integer == 1
    assert length == 1

    integer, length = types.INT16.from_bytes(bytes.fromhex("01 00 ff")[1:])
    assert integer == 255
    assert length == 2

    integer, length = types.INT32.from_bytes(
        bytes.fromhex("02 00 00 ff ff")[1:]
    )
    assert integer == 65535
    assert length == 4

    integer, length = types.INT64.from_bytes(
        bytes.fromhex("03 00 00 00 00 ff ff ff ff")[1:]
    )
    assert integer == 4294967295
    assert length == 8


def test_float_encode() -> None:
    """测试浮点数编码."""
    byte = types.FLOAT.to_bytes(jce_id=0, value=1.0)
    assert byte == bytes.fromhex("04 3f 80 00 00")


def test_float_decode() -> None:
    """测试浮点数解码."""
    float_, length = types.FLOAT.from_bytes(bytes.fromhex("04 3f 80 00 00")[1:])
    assert float_ == 1.0
    assert length == 4


def test_float_validate() -> None:
    """测试浮点数验证."""
    assert types.FLOAT.validate(1.0) == 1.0
    assert types.FLOAT.validate(1) == 1.0


def test_double_encode() -> None:
    """测试双精度浮点数编码."""
    byte = types.DOUBLE.to_bytes(jce_id=0, value=1.0)
    assert byte == bytes.fromhex("05 3f f0 00 00 00 00 00 00")


def test_double_decode() -> None:
    """测试双精度浮点数解码."""
    double, length = types.DOUBLE.from_bytes(
        bytes.fromhex("05 3f f0 00 00 00 00 00 00")[1:]
    )
    assert double == 1.0
    assert length == 8


def test_double_validate() -> None:
    """测试双精度浮点数验证."""
    assert types.DOUBLE.validate(1.0) == 1.0
    assert types.DOUBLE.validate(1) == 1.0


def test_string_encode() -> None:
    """测试字符串编码."""
    byte = types.STRING.to_bytes(jce_id=0, value="a")
    assert byte == bytes.fromhex("06 01 61")

    byte = types.STRING.to_bytes(jce_id=0, value="a" * 256)
    assert byte == bytes.fromhex("07 00 00 01 00" + "61" * 256)


def test_string_decode() -> None:
    """测试字符串解码."""
    string, length = types.STRING1.from_bytes(bytes.fromhex("06 01 61")[1:])
    assert string == "a"
    assert length == 2

    string, length = types.STRING4.from_bytes(
        bytes.fromhex("07 00 00 01 00" + "61" * 256)[1:]
    )
    assert string == "a" * 256
    assert length == 260


def test_map_encode() -> None:
    """测试Map编码."""
    byte = types.MAP.to_bytes(jce_id=0, value={"a": 1})
    assert byte == bytes.fromhex("08 00 01 06 01 61 10 01")


def test_map_decode() -> None:
    """测试Map解码."""
    # The encoded data represents {"a": 1, "b": 2}
    # GenericDecoder decodes to actual types, not raw bytes
    raw = {
        b"a": 1,  # GenericDecoder returns bytes for strings
        b"b": 2,
    }
    encoded = bytes.fromhex("08 00 02 06 01 61 10 01 06 01 62 10 02")
    map_, length = types.MAP.from_bytes(encoded[1:])
    assert map_ == raw
    assert length == len(encoded) - 1


def test_map_validate() -> None:
    """测试Map验证."""
    raw = {
        "a": 1,
        "b": 2,
    }
    assert types.MAP.validate(raw) == raw
    assert types.MAP.validate(types.MAP(raw)) == raw  # type: ignore


def test_list_encode() -> None:
    """测试列表编码."""
    byte = types.LIST.to_bytes(jce_id=0, value=[1, 2])
    assert byte == bytes.fromhex("09 00 02 00 01 00 02")


def test_list_decode() -> None:
    """测试列表解码."""
    # The encoded data represents [1, 2] (integers)
    # GenericDecoder decodes to actual integer types
    raw = [1, 2]
    encoded = bytes.fromhex("09 00 02 00 01 00 02")
    list_, length = types.LIST.from_bytes(encoded[1:])
    assert list_ == raw
    assert length == len(encoded) - 1


def test_list_validate() -> None:
    """测试列表验证."""
    raw = [1, 2]
    assert types.LIST.validate(raw) == raw
    assert types.LIST.validate(types.LIST(raw)) == raw  # type: ignore


def test_bytes_encode() -> None:
    """测试Bytes编码."""
    byte = types.BYTES.to_bytes(jce_id=0, value=b"a")
    assert byte == bytes.fromhex("0d 00 00 01 61")


def test_bytes_decode() -> None:
    """测试Bytes解码."""
    byte, length = types.BYTES.from_bytes(bytes.fromhex("0d 00 00 01 61")[1:])
    assert byte == b"a"
    assert length == 4


def test_bytes_validate() -> None:
    """测试Bytes验证."""
    assert types.BYTES.validate(b"a") == b"a"
