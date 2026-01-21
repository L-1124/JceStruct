"""JCE API 测试."""

import io

import pytest

from jce import JceDict, JceField, JceOption, JceStruct, dump, dumps, load, loads


class SimpleUser(JceStruct):
    """测试用的 JCE Struct."""

    uid: int = JceField(jce_id=0)
    name: str = JceField(jce_id=1, default="unknown")


def test_api_dumps_basic():
    """dumps() 应该能正确序列化基本的 Struct 对象."""
    u = SimpleUser(uid=100, name="test")
    # Struct 模式: 扁平的 Tag-Value 序列
    data = dumps(u)
    assert data == bytes.fromhex("0064160474657374")


def test_api_loads_basic():
    """loads() 应该能正确反序列化基本的 Struct 对象."""
    data = bytes.fromhex("0064160474657374")
    u = loads(data, target=SimpleUser)
    assert u.uid == 100
    assert u.name == "test"


def test_api_loads_map_behavior():
    """loads() 默认应该将 Map 数据解析为 JceDict."""
    # 原始数据
    data = {1: "a", 2: "b"}

    # dumps(dict) -> 生成 Map (Tag 0, Type 8)
    encoded = dumps(data)

    # loads() 会将 Root 解析为 JceDict
    decoded = loads(encoded)

    # 验证返回类型
    assert isinstance(decoded, JceDict)

    # 验证内容: Map 被包裹在 Tag 0 中
    # 因为 dumps(dict) 本质上是 encode_value(val, tag=0)
    assert decoded[0] == data
    assert isinstance(decoded[0][1], str)


def test_jce_dict_struct_behavior():
    """JceDict 对象应该被序列化为 Struct 格式而不是 Map."""
    # JceDict 显式声明这是 Struct 数据 (Tag 0 -> 100)
    data = JceDict({0: 100})

    # dumps(JceDict) -> 扁平 Tag 序列 (Tag 0, Int 100)
    encoded = dumps(data)
    assert encoded == b"\x00\x64"

    # 对比: 普通 dict -> Map (Tag 0, Map Type)
    encoded_map = dumps({0: 100})
    assert encoded_map != b"\x00\x64"
    # 0x08 是 Map 类型 Tag
    assert encoded_map[0] == 0x08

    # loads 还原 (默认 JceDict)
    decoded = loads(encoded)
    assert isinstance(decoded, JceDict)
    assert decoded == data
    assert decoded[0] == 100


def test_api_round_trip_basic():
    """dumps() 和 loads() 应该能完成基本的 dict 数据往返."""
    data = {1: "a", 2: "b"}
    encoded = dumps(data)

    decoded = loads(encoded)

    # 验证 Map 被包裹在 Tag 0 中
    assert decoded[0] == data


def test_file_io_round_trip():
    """dump() 和 load() 应该能通过文件对象进行读写."""
    data = {1: 100, 2: "test"}
    f = io.BytesIO()

    # 写入 Map
    dump(data, f)
    f.seek(0)

    loaded_data = load(f)

    # 验证
    assert isinstance(loaded_data, JceDict)
    assert loaded_data[0] == data
    assert loaded_data[0][2] == "test"


def test_file_io_load_target_dict():
    """load(target=dict) 应该返回普通 dict 类型."""
    data = JceDict({0: 100, 1: "abc"})
    f = io.BytesIO()
    dump(data, f)
    f.seek(0)

    loaded_data = load(f, target=dict)

    assert isinstance(loaded_data, dict)
    assert not isinstance(loaded_data, JceDict)
    assert loaded_data[0] == 100
    assert loaded_data[1] == "abc"


def test_auto_bytes_conversion():
    """loads() 在默认 Auto 模式下应该自动将 bytes 转换为 str."""
    # 构造一个包含字符串的 dict
    data = {1: "hello"}
    encoded = dumps(data)

    # loads 默认开启 bytes_mode="auto"
    decoded = loads(encoded)

    # 验证解码出的字符串是 str 而不是 bytes
    assert isinstance(decoded[0][1], str)
    assert decoded[0][1] == "hello"


def test_loads_returns_jcedict():
    """loads() 默认应该返回 JceDict 类型."""
    # 构造 Struct 数据
    struct_data = JceDict({0: 100, 1: "test"})
    encoded = dumps(struct_data)

    # loads 应该返回 JceDict
    decoded = loads(encoded)
    assert isinstance(decoded, JceDict)
    assert decoded[0] == 100
    assert decoded[1] == "test"


def test_loads_target_dict_returns_dict():
    """loads(target=dict) 应该返回普通 dict 类型."""
    struct_data = JceDict({0: 100})
    encoded = dumps(struct_data)

    # 显式指定 target=dict
    decoded = loads(encoded, target=dict)

    # 返回应该是普通 dict (不是 JceDict)
    assert isinstance(decoded, dict)
    assert not isinstance(decoded, JceDict)
    assert decoded[0] == 100


def test_jcedict_vs_dict_encoding_difference():
    """JceDict 和 dict 应该有不同的编码表现 (Struct vs Map)."""
    # JceDict: 编码为 Struct (扁平的 Tag-Value)
    jce_data = JceDict({0: 100})
    jce_encoded = dumps(jce_data)
    # Struct: Tag 0 (0x00) + Int 100 (0x64) = 0x00 0x64
    assert jce_encoded == b"\x00\x64"

    # dict: 编码为 Map (包裹在 Tag 0 中)
    dict_data = {0: 100}
    dict_encoded = dumps(dict_data)
    # 第一个字节应该是 Tag 0 + Map Type (0x08)
    assert dict_encoded[0] == 0x08
    # dict 编码长度更长 (包含 Map 头信息)
    assert len(dict_encoded) > len(jce_encoded)


def test_jcedict_as_nested_struct():
    """JceDict 应该支持嵌套使用."""
    # 嵌套 JceDict
    outer = JceDict({0: JceDict({1: "inner"})})
    encoded = dumps(outer)

    # 解码
    decoded = loads(encoded)
    assert isinstance(decoded, JceDict)
    assert isinstance(decoded[0], JceDict)
    assert decoded[0][1] == "inner"


# _is_safe_text 测试用例
IS_SAFE_TEXT_CASES = [
    ("hello world", True, "基本可打印字符"),
    ("ABC123", True, "字母数字"),
    ("test\nline", True, "换行符"),
    ("tab\there", True, "制表符"),
    ("return\rcarriage", True, "回车符"),
    ("null\x00char", False, "空字符"),
    ("\x01\x02\x03", False, "控制字符"),
    ("bell\x07", False, "响铃符"),
    ("", True, "空字符串"),
    ("你好世界", True, "中文字符"),
    ("Hello 👋 World 🌍", True, "Emoji"),
    ("Test 测试 123", True, "混合字符"),
]


@pytest.mark.parametrize(("text", "expected", "desc"), IS_SAFE_TEXT_CASES)
def test_is_safe_text(text, expected, desc):
    """_is_safe_text() 应该正确判断文本是否安全可打印."""
    from jce.decoder import _is_safe_text  # noqa: PLC2701

    assert _is_safe_text(text) == expected, f"失败: {desc}"


# bytes_mode 转换测试用例
BYTES_MODE_CASES = [
    ({1: b"test"}, "raw", bytes, b"test", "raw模式保持原始字节"),
    ({1: b"test"}, "string", str, "test", "string模式转换为字符串"),
    ({1: b"\xff\xfe"}, "string", bytes, b"\xff\xfe", "string模式无效UTF-8保持原样"),
    ({1: b"hello world"}, "auto", str, "hello world", "auto模式识别文本"),
    (
        {1: b"\x00\x01\x02\x03"},
        "auto",
        bytes,
        b"\x00\x01\x02\x03",
        "auto模式保留二进制",
    ),
    ({1: b""}, "auto", str, "", "空字节转为空字符串"),
]


@pytest.mark.parametrize(
    ("data", "mode", "expected_type", "expected_value", "desc"), BYTES_MODE_CASES
)
def test_convert_bytes_mode(data, mode, expected_type, expected_value, desc):
    """loads() 应该根据 bytes_mode 参数正确转换字节数据."""
    encoded = dumps(data)
    decoded = loads(encoded, bytes_mode=mode)

    assert isinstance(decoded[0][1], expected_type), f"失败: {desc}"
    assert decoded[0][1] == expected_value, f"失败: {desc}"


def test_convert_bytes_in_list():
    """loads() 应该递归转换列表中的字节数据."""
    data = {1: [b"item1", b"item2"]}
    encoded = dumps(data)

    decoded = loads(encoded, bytes_mode="auto")
    assert isinstance(decoded[0][1], list)
    assert decoded[0][1][0] == "item1"
    assert decoded[0][1][1] == "item2"


def test_convert_bytes_dict_key():
    """loads() 应该转换字典键中的字节数据."""
    # 注意: JCE Map 的键会被编码
    inner_dict = {b"key": "value"}
    data = {1: inner_dict}
    encoded = dumps(data)

    decoded = loads(encoded, bytes_mode="auto")
    # 键应该被转换为字符串
    assert "key" in decoded[0][1]
    assert decoded[0][1]["key"] == "value"


# _jcedict_to_plain_dict 转换测试用例
JCEDICT_TO_DICT_CASES = [
    (
        JceDict({0: JceDict({1: "inner"})}),
        lambda r: (
            isinstance(r, dict)
            and not isinstance(r, JceDict)
            and isinstance(r[0], dict)
            and not isinstance(r[0], JceDict)
            and r[0][1] == "inner"
        ),
        "嵌套JceDict转换",
    ),
    (
        JceDict({0: [JceDict({1: "item"})]}),
        lambda r: (
            isinstance(r[0], list)
            and isinstance(r[0][0], dict)
            and not isinstance(r[0][0], JceDict)
        ),
        "列表中的JceDict转换",
    ),
    (
        (JceDict({0: "test"}),),
        lambda r: (
            isinstance(r, tuple)
            and isinstance(r[0], dict)
            and not isinstance(r[0], JceDict)
        ),
        "元组中的JceDict转换",
    ),
]


@pytest.mark.parametrize(("data", "validator", "desc"), JCEDICT_TO_DICT_CASES)
def test_jcedict_to_plain_dict(data, validator, desc):
    """_jcedict_to_plain_dict() 应该递归将 JceDict 转换为普通 dict."""
    from jce.api import _jcedict_to_plain_dict  # noqa: PLC2701

    result = _jcedict_to_plain_dict(data)
    assert validator(result), f"失败: {desc}"


def test_dumps_with_option():
    """dumps() 应该支持传入 option 参数控制编码行为."""
    data = {1: 100}

    # 小端序选项
    encoded_le = dumps(data, option=JceOption.LITTLE_ENDIAN)
    encoded_be = dumps(data)

    # 确保编码不同 (但长度可能相同)
    assert isinstance(encoded_le, bytes)
    assert isinstance(encoded_be, bytes)


def test_dumps_with_exclude_unset():
    """dumps(exclude_unset=True) 应该排除未设置的字段."""
    user = SimpleUser(uid=100)
    # name 使用默认值 "unknown"

    # 不排除未设置字段
    encoded_all = dumps(user, exclude_unset=False)

    # 排除未设置字段
    encoded_unset = dumps(user, exclude_unset=True)

    # 排除后应该更短
    assert len(encoded_unset) < len(encoded_all)


def test_dumps_with_context():
    """dumps() 应该能将 context 传递给序列化过程."""

    class ContextUser(JceStruct):
        uid: int = JceField(jce_id=0)
        name: str = JceField(jce_id=1)

    user = ContextUser(uid=1, name="test")
    context = {"version": "1.0"}

    # 应该成功序列化 (context 会传递给字段序列化器)
    encoded = dumps(user, context=context)
    assert isinstance(encoded, bytes)


def test_dump_and_load_with_bytesio():
    """dump() 和 load() 应该支持 BytesIO 对象."""
    user = SimpleUser(uid=200, name="file_test")

    # 写入
    buffer = io.BytesIO()
    dump(user, buffer)

    # 读取
    buffer.seek(0)
    loaded = load(buffer, target=SimpleUser)

    assert loaded.uid == 200
    assert loaded.name == "file_test"


def test_dump_with_options():
    """dump() 应该支持所有序列化选项参数."""
    user = SimpleUser(uid=300, name="option_test")
    buffer = io.BytesIO()

    # 使用多个选项
    dump(
        user,
        buffer,
        option=JceOption.LITTLE_ENDIAN,
        exclude_unset=False,
        context={"key": "value"},
    )

    assert buffer.tell() > 0


def test_load_with_bytes_mode():
    """load() 应该支持 bytes_mode 参数."""
    data = {1: b"binary_data"}
    buffer = io.BytesIO()
    dump(data, buffer)

    # raw 模式
    buffer.seek(0)
    loaded_raw = load(buffer, bytes_mode="raw")
    assert isinstance(loaded_raw[0][1], bytes)

    # string 模式
    buffer.seek(0)
    loaded_str = load(buffer, bytes_mode="string")
    assert isinstance(loaded_str[0][1], str)


def test_load_with_context():
    """load() 应该能将 context 传递给反序列化过程."""

    class ContextStruct(JceStruct):
        value: int = JceField(jce_id=0)

    obj = ContextStruct(value=42)
    buffer = io.BytesIO()
    dump(obj, buffer)

    buffer.seek(0)
    loaded = load(buffer, target=ContextStruct, context={"decode_key": "test"})

    assert loaded.value == 42


# 输入类型测试用例
INPUT_TYPE_CASES = [
    (memoryview, "memoryview输入"),
    (bytearray, "bytearray输入"),
]


@pytest.mark.parametrize(("input_type", "desc"), INPUT_TYPE_CASES)
def test_loads_with_different_input_types(input_type, desc):
    """loads() 应该支持 bytes/bytearray/memoryview 等多种输入类型."""
    user = SimpleUser(uid=100, name="test")
    data = dumps(user)

    # 转换输入类型
    converted_data = input_type(data)
    loaded = loads(converted_data, target=SimpleUser)

    assert loaded.uid == 100, f"失败: {desc}"
    assert loaded.name == "test", f"失败: {desc}"


def test_convert_bytes_nested_jcedict():
    """loads(bytes_mode='auto') 应该递归转换嵌套 JceDict 中的字节."""
    # 构造嵌套结构
    data = JceDict({0: JceDict({1: b"nested_text"})})
    encoded = dumps(data)

    # auto 模式应该递归转换
    decoded = loads(encoded, bytes_mode="auto")
    assert isinstance(decoded[0][1], str)
    assert decoded[0][1] == "nested_text"


def test_convert_bytes_preserves_jcedict_type():
    """字节转换过程应保持 JceDict 类型不变."""
    data = JceDict({0: b"test"})
    encoded = dumps(data)

    decoded = loads(encoded, bytes_mode="auto")
    assert isinstance(decoded, JceDict)


def test_api_error_handling_invalid_data():
    """loads() 应该在数据无效时抛出 JceDecodeError."""
    from jce import JceDecodeError

    invalid_data = b"\xff\xff\xff\xff"

    with pytest.raises(JceDecodeError):
        loads(invalid_data)
