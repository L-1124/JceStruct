"""测试 JCE 解码器."""

import struct
from typing import Any

import pytest

from jce import (
    JceDecodeError,
    JceDict,
    JceField,
    JceOption,
    JceStruct,
    dumps,
    jce_field_deserializer,
    loads,
    types,
)
from jce.const import (
    JCE_DOUBLE,
    JCE_FLOAT,
    JCE_INT1,
    JCE_INT2,
    JCE_INT4,
    JCE_INT8,
    JCE_LIST,
    JCE_MAP,
    JCE_SIMPLE_LIST,
    JCE_STRING1,
    JCE_STRING4,
    JCE_STRUCT_BEGIN,
    JCE_ZERO_TAG,
)
from jce.decoder import (
    MAX_STRING_LENGTH,
    DataReader,
    GenericDecoder,
    JceNode,
    NodeDecoder,
)
from jce.exceptions import JcePartialDataError


class TargetStruct(JceStruct):
    """只包含 Tag 0 和 Tag 2 的结构体."""

    f0: int = JceField(jce_id=0)
    f2: int = JceField(jce_id=2)


# --- DataReader 测试 ---


def test_reader_basic_read() -> None:
    """read_bytes() 应能正确读取指定长度并移动指针."""
    data = b"\x01\x02\x03\x04"
    reader = DataReader(data)

    assert reader.read_bytes(1) == b"\x01"
    assert reader._pos == 1
    assert reader.read_bytes(2) == b"\x02\x03"
    assert reader._pos == 3


def test_reader_partial_data_error() -> None:
    """read_bytes() 在数据不足时应抛出 JcePartialDataError."""
    data = b"\x01"
    reader = DataReader(data)
    reader.read_bytes(1)

    with pytest.raises(JcePartialDataError):
        reader.read_bytes(1)

    reader = DataReader(b"\x01")
    reader.read_bytes(1)
    with pytest.raises(JcePartialDataError):
        reader.read_u8()


def test_reader_peek() -> None:
    """peek_u8() 应返回下一个字节但不移动指针."""
    data = b"\x01\x02"
    reader = DataReader(data)

    assert reader.peek_u8() == 0x01
    assert reader._pos == 0
    assert reader.read_u8() == 0x01
    assert reader._pos == 1


def test_reader_skip() -> None:
    """skip() 应正确移动指针且在越界时抛出错误."""
    data = b"\x01\x02\x03"
    reader = DataReader(data)

    reader.skip(2)
    assert reader._pos == 2
    assert reader.read_u8() == 0x03

    with pytest.raises(JcePartialDataError):
        reader.skip(10)


def test_reader_eof() -> None:
    """Reader 应正确报告 EOF 状态."""
    data = b"\x01\x02"
    reader = DataReader(data)

    assert not reader.eof
    reader.read_bytes(2)
    assert reader.eof


def test_reader_zero_copy_mode() -> None:
    """Reader 在零拷贝模式下应返回 memoryview."""
    data = b"\x01\x02\x03\x04"
    reader = DataReader(data, option=int(JceOption.ZERO_COPY))

    result = reader.read_bytes(2, zero_copy=True)

    assert isinstance(result, memoryview)
    assert bytes(result) == b"\x01\x02"


# --- Head 解析测试 ---


def test_decode_long_tag() -> None:
    """Decoder 应能正确解析 Tag >= 15 的长标签."""
    data = b"\xf0\x14\x01"
    reader = DataReader(data)
    decoder = GenericDecoder(reader)

    res = decoder.decode()

    assert res == {20: 1}


def test_decode_invalid_type_head() -> None:
    """Decoder 遇到未知的 Type ID 应抛出 JceDecodeError."""
    data = b"\x0e"
    reader = DataReader(data)
    decoder = GenericDecoder(reader)

    with pytest.raises(JceDecodeError, match="Unknown JCE Type ID"):
        decoder.decode()


# --- Skip Logic 测试 ---


def test_skip_unknown_fields_primitive() -> None:
    """Decoder 应能跳过结构体中未定义的基础类型字段."""
    data_0 = dumps(JceDict({0: 10}))
    data_1 = dumps(JceDict({1: 99999999999}))
    data_2 = dumps(JceDict({2: 20}))
    full_data = data_0 + data_1 + data_2

    obj = TargetStruct.model_validate_jce(full_data)

    assert obj.f0 == 10
    assert obj.f2 == 20


def test_skip_recursive_container() -> None:
    """Decoder 应能递归跳过复杂的容器 (List/Map) 字段."""
    complex_data = JceDict({1: [[1, 2], [3, 4]]})
    data_complex = dumps(complex_data)
    data_0 = dumps(JceDict({0: 10}))
    data_2 = dumps(JceDict({2: 20}))
    full_data = data_0 + data_complex + data_2

    obj = TargetStruct.model_validate_jce(full_data)

    assert obj.f0 == 10
    assert obj.f2 == 20


def test_skip_struct() -> None:
    """Decoder 应能跳过嵌套的结构体字段."""
    struct_data = JceDict({1: JceDict({10: 100, 11: 200})})
    data_struct = dumps(struct_data)
    data_0 = dumps(JceDict({0: 10}))
    data_2 = dumps(JceDict({2: 20}))
    full_data = data_0 + data_struct + data_2

    obj = TargetStruct.model_validate_jce(full_data)

    assert obj.f0 == 10
    assert obj.f2 == 20


def test_skip_unknown_fields_complex() -> None:
    """Decoder 应能跳过复杂的未知字段 (Map, SimpleList, List)."""

    class FullStruct(JceStruct):
        f0: int = JceField(jce_id=0, jce_type=types.INT32)
        f1: dict[str, str] = JceField(jce_id=1, jce_type=types.MAP)
        f2: bytes = JceField(jce_id=2, jce_type=types.BYTES)
        f3: list[int] = JceField(jce_id=3, jce_type=types.LIST)

    class PartialStruct(JceStruct):
        f0: int = JceField(jce_id=0, jce_type=types.INT32)

    data = FullStruct(f0=123, f1={"key": "val"}, f2=b"\xca\xfe", f3=[1, 2, 3])
    encoded = dumps(data)

    decoded = loads(encoded, PartialStruct)

    assert decoded.f0 == 123


# --- 异常处理测试 ---


def test_decode_truncated_string() -> None:
    """读取长度不足的字符串时应抛出 JcePartialDataError."""
    data = bytes.fromhex("0605616263")
    reader = DataReader(data)
    decoder = GenericDecoder(reader)

    with pytest.raises(JcePartialDataError):
        decoder.decode()


def test_decode_truncated_primitive() -> None:
    """读取长度不足的基础类型时应抛出 JcePartialDataError."""
    data = bytes.fromhex("0201")
    reader = DataReader(data)
    decoder = GenericDecoder(reader)

    with pytest.raises(JcePartialDataError):
        decoder.decode()


# --- 浮点数解码测试 ---


def test_decode_float_normal() -> None:
    """Decoder 应能正确解码标准的 Float 数据."""
    data = JceDict({0: 3.14})
    encoded = dumps(data)
    reader = DataReader(encoded)
    decoder = GenericDecoder(reader)

    result = decoder.decode()

    assert abs(result[0] - 3.14) < 0.01


def test_decode_double_normal() -> None:
    """Decoder 应能正确解码标准的 Double 数据."""
    data = JceDict({0: 3.141592653589793})
    encoded = dumps(data)
    reader = DataReader(encoded)
    decoder = GenericDecoder(reader)

    result = decoder.decode()

    assert abs(result[0] - 3.141592653589793) < 1e-10


def test_decode_float_little_endian() -> None:
    """Decoder 应支持小端序浮点数解码."""
    data = JceDict({0: 2.718})
    encoded = dumps(data, option=JceOption.LITTLE_ENDIAN)
    reader = DataReader(encoded, option=int(JceOption.LITTLE_ENDIAN))
    decoder = GenericDecoder(reader, option=int(JceOption.LITTLE_ENDIAN))

    result = decoder.decode()

    assert abs(result[0] - 2.718) < 0.01


def test_decode_float_partial_data() -> None:
    """读取长度不足的浮点数时应抛出 JcePartialDataError."""
    data = bytes.fromhex("04ffff")
    reader = DataReader(data)
    decoder = GenericDecoder(reader)

    with pytest.raises(JcePartialDataError):
        decoder.decode()


def test_decode_double_partial_data() -> None:
    """读取长度不足的双精度浮点数时应抛出 JcePartialDataError."""
    data = bytes.fromhex("05ffffffff")
    reader = DataReader(data)
    decoder = GenericDecoder(reader)

    with pytest.raises(JcePartialDataError):
        decoder.decode()


def test_float_heuristic_infinite_primary() -> None:
    """read_float() 在大端序为 Inf 但小端序正常时应自动选择小端序."""
    inf_be = struct.pack(">f", float("inf"))
    val_le = struct.unpack("<f", inf_be)[0]
    reader = DataReader(inf_be)

    assert reader.read_float() == val_le


def test_float_heuristic_magnitude() -> None:
    """read_float() 在大端序值过大但小端序合理时应自动选择小端序."""
    data = b"\x50\x00\x00\x00"
    val_le = struct.unpack("<f", data)[0]
    reader = DataReader(data)

    assert reader.read_float() == val_le


def test_double_heuristic_magnitude() -> None:
    """read_double() 在大端序值过大但小端序合理时应自动选择小端序."""
    data = b"\x60" + b"\x00" * 7
    val_le = struct.unpack("<d", data)[0]
    reader = DataReader(data)

    assert reader.read_double() == val_le


# --- Map 解码测试 ---


def test_decode_map_normal() -> None:
    """Decoder 应能正确解码 Map 数据."""
    data = JceDict({0: {1: "value1", 2: "value2"}})
    encoded = dumps(data)
    reader = DataReader(encoded)
    decoder = GenericDecoder(reader)

    result = decoder.decode()

    assert isinstance(result[0], dict)
    assert 1 in result[0] or "1" in result[0]


def test_decode_simple_list_normal() -> None:
    """Decoder 应能正确解码 SimpleList (bytes) 数据."""
    data = JceDict({0: b"hello"})
    encoded = dumps(data)
    reader = DataReader(encoded)
    decoder = GenericDecoder(reader)

    result = decoder.decode()

    assert isinstance(result[0], bytes | memoryview)


# --- 递归深度测试 ---


def test_decode_moderate_nesting() -> None:
    """Decoder 应能处理合理深度的递归嵌套."""
    nested: Any = [0]
    for _ in range(10):
        nested = [nested]
    data = JceDict({0: nested})
    encoded = dumps(data)
    reader = DataReader(encoded)
    decoder = GenericDecoder(reader)

    result = decoder.decode()

    assert isinstance(result, dict)


def test_deeply_nested_structure() -> None:
    """Decoder 应能正确处理深度嵌套结构 (迭代式实现不应抛出 RecursionError)."""
    depth = 150
    # Layer: Head(List, Tag0), LenHead(Int1, Tag0), LenValue(1)
    layer = bytes.fromhex("09 00 01")
    # Tail: ItemHead(Int1, Tag0), ItemValue(0)
    data = layer * depth + bytes.fromhex("00 00")

    reader = DataReader(data)
    decoder = GenericDecoder(reader)

    # 只要不抛出 RecursionError 且能解码成功即可
    result = decoder.decode()

    assert isinstance(result, dict)
    assert 0 in result

    # 验证嵌套深度
    curr = result[0]
    count = 0
    while isinstance(curr, list):
        count += 1
        if len(curr) > 0:
            curr = curr[0]
        else:
            break

    # 最内层是 0 (int)
    assert curr == 0
    assert count == depth


# --- 整数解码测试 ---


def test_decode_int_with_bytes_value() -> None:
    """整数类型的 validate 方法应能自动转换 bytes 输入."""
    result = types.INT.validate(b"\x00\x00\x00\x01")

    assert result == 1


INT_DECODE_CASES = [
    (0, "零值"),
    (127, "INT1最大值"),
    (128, "需要INT2"),
    (32767, "INT2最大值"),
    (32768, "需要INT4"),
    (2147483647, "INT4最大值"),
    (2147483648, "需要INT8"),
    (-1, "负数"),
    (-128, "INT1最小值"),
    (-129, "需要INT2负数"),
]


@pytest.mark.parametrize(
    ("value", "desc"),
    INT_DECODE_CASES,
    ids=[c[1] for c in INT_DECODE_CASES],
)
def test_decode_various_int_sizes(value: int, desc: str) -> None:
    """Decoder 应能正确处理各种大小和符号的整数."""
    data = JceDict({0: value})
    encoded = dumps(data)
    reader = DataReader(encoded)
    decoder = GenericDecoder(reader)

    result = decoder.decode()

    assert result[0] == value, f"失败: {desc}"


# --- String 解码测试 ---


def test_string4_negative_length() -> None:
    """解码 String4 时若长度为负数应抛出 JceDecodeError."""
    head = (0 << 4) | 7
    length = struct.pack(">i", -1)
    data = bytes([head]) + length

    with pytest.raises(JceDecodeError, match="negative"):
        loads(data, target=dict)


def test_string4_max_length_exceeded() -> None:
    """解码 String4 时若长度超过限制应抛出 JceDecodeError."""
    head = (0 << 4) | 7
    length = struct.pack(">i", MAX_STRING_LENGTH + 1)
    data = bytes([head]) + length

    with pytest.raises(JceDecodeError, match="exceeds max limit"):
        loads(data, target=dict)


# --- _freeze_key 测试 ---


def test_freeze_key_nested() -> None:
    """_freeze_key() 应能冻结嵌套的 list 和 dict 以作为字典键."""
    reader = DataReader(b"")
    decoder = GenericDecoder(reader)
    mutable_key: dict[int, Any] = {1: [2, 3], 4: {5: 6}}

    frozen = decoder._freeze_key(mutable_key)

    assert isinstance(frozen, tuple)
    d = {frozen: "value"}
    assert d[frozen] == "value"
    assert frozen[0][0] == 1
    assert frozen[0][1] == (2, 3)
    assert frozen[1][0] == 4
    assert frozen[1][1] == ((5, 6),)


# --- SchemaDecoder 测试 ---


def test_struct_fallback_in_list() -> None:
    """SchemaDecoder 在列表元素类型不匹配时应尝试回退到字典模式."""

    class Item(JceStruct):
        a: int = JceField(jce_id=0, jce_type=types.INT)

    class Container(JceStruct):
        items: list[Item] = JceField(jce_id=1, jce_type=types.LIST)

    list_tag_head = bytes([(1 << 4) | 9])
    list_len = b"\x00\x01"
    item_head = b"\x08"
    map_len = b"\x00\x01"
    key_part = b"\x00\x00"
    val_part = b"\x10\x64"
    payload = list_tag_head + list_len + item_head + map_len + key_part + val_part

    container = loads(payload, Container)

    assert len(container.items) == 1
    assert container.items[0].a == 100


def test_deserializer_missing_cls() -> None:
    """字段反序列化器如果没有声明为 @classmethod 应抛出 TypeError."""

    class BadStruct(JceStruct):
        f: int = JceField(jce_id=0, jce_type=types.INT)

        @jce_field_deserializer("f")  # type: ignore[arg-type]
        def bad_deserializer(self, value: int, _: Any) -> int:
            return value

    data = dumps({0: 123})

    with pytest.raises(TypeError, match="must be a @classmethod"):
        loads(data, BadStruct)


# --- NodeDecoder 及 JceNode 测试 ---


def test_jcenode_type_name() -> None:
    """JceNode.type_name 属性应正确映射类型 ID 到名称."""
    cases = [
        (JCE_INT1, "Byte"),
        (JCE_INT2, "Short"),
        (JCE_INT4, "Int"),
        (JCE_INT8, "Long"),
        (JCE_FLOAT, "Float"),
        (JCE_DOUBLE, "Double"),
        (JCE_STRING1, "Str"),
        (JCE_STRING4, "Str"),
        (JCE_MAP, "Map"),
        (JCE_LIST, "List"),
        (JCE_STRUCT_BEGIN, "Struct"),
        (JCE_ZERO_TAG, "Zero"),
        (JCE_SIMPLE_LIST, "SimpleList"),
        (99, "Unknown"),
    ]

    for type_id, expected in cases:
        node = JceNode(tag=0, type_id=type_id, value=None)
        assert node.type_name == expected


def test_node_decode_unknown_type() -> None:
    """NodeDecoder 解码未知类型应抛出错误."""
    data = bytes([(0 << 4) | 14])
    reader = DataReader(data)
    decoder = NodeDecoder(reader)

    with pytest.raises(JceDecodeError, match="Unknown JCE Type ID"):
        decoder.decode()


def test_node_decode_simple_list_invalid_type() -> None:
    """NodeDecoder 解码 SimpleList 类型不匹配时应抛出错误."""
    data = bytes.fromhex("0D 01")
    reader = DataReader(data)
    decoder = NodeDecoder(reader)

    with pytest.raises(JceDecodeError, match="SimpleList expected Byte type"):
        decoder.decode()


def test_node_decode_struct_in_tree() -> None:
    """NodeDecoder 应能正确解码嵌套结构体的树状结构."""
    data = bytes.fromhex("0A 1C 0B")
    reader = DataReader(data)
    decoder = NodeDecoder(reader)

    nodes = decoder.decode()

    assert len(nodes) == 1
    struct_node = nodes[0]
    assert struct_node.type_id == JCE_STRUCT_BEGIN
    assert isinstance(struct_node.value, list)
    assert len(struct_node.value) == 1
    assert struct_node.value[0].type_id == JCE_ZERO_TAG


def test_node_decode_map_in_tree() -> None:
    """NodeDecoder 应能正确解码 Map 的树状结构."""
    data = bytes.fromhex("08 00 01 00 01 10 02")
    reader = DataReader(data)
    decoder = NodeDecoder(reader)

    nodes = decoder.decode()

    assert len(nodes) == 1
    map_node = nodes[0]
    assert map_node.type_id == JCE_MAP
    assert isinstance(map_node.value, list)
    assert len(map_node.value) == 1
    key_node, val_node = map_node.value[0]
    assert key_node.value == 1
    assert val_node.value == 2


def test_node_decode_string_utf8_error_handling() -> None:
    """NodeDecoder 解码 String 时的 UTF-8 错误应回退到 bytes."""
    data = bytes.fromhex("06 01 FF")
    reader = DataReader(data)
    decoder = NodeDecoder(reader)

    nodes = decoder.decode()

    assert nodes[0].type_id == JCE_STRING1
    assert isinstance(nodes[0].value, bytes | memoryview)
    assert bytes(nodes[0].value) == b"\xff"

    data = bytes.fromhex("07 00 00 00 01 FF")
    reader = DataReader(data)
    decoder = NodeDecoder(reader)
    nodes = decoder.decode()
    assert nodes[0].type_id == JCE_STRING4
    assert isinstance(nodes[0].value, bytes | memoryview)


def test_node_decode_string4_errors() -> None:
    """NodeDecoder 解码 String4 的长度错误应正确处理."""
    data = bytes.fromhex("07 FF FF FF FF")
    reader = DataReader(data)
    decoder = NodeDecoder(reader)

    with pytest.raises(JceDecodeError, match="negative"):
        decoder.decode()

    data = bytes.fromhex("07 7F FF FF FF")
    reader = DataReader(data)
    decoder = NodeDecoder(reader)
    with pytest.raises(JceDecodeError, match="too long"):
        decoder.decode()


def test_node_simple_list_recursion_failure_fallback() -> None:
    """NodeDecoder 解码 SimpleList 递归失败时应回退到 bytes."""
    data = bytes.fromhex("0D 00 00 01 FF")
    reader = DataReader(data)
    decoder = NodeDecoder(reader)

    nodes = decoder.decode()

    assert nodes[0].type_id == JCE_SIMPLE_LIST
    assert isinstance(nodes[0].value, bytes | memoryview)
    assert bytes(nodes[0].value) == b"\xff"
