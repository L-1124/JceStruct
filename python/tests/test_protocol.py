"""JCE 协议兼容性测试.

该文件包含确定的输入和预期的十六进制输出。
注意：
1. Python float 默认编码为 JCE DOUBLE (8字节)。
2. 长度字段 (Length) 本身也是 JCE Integer，因此包含 Tag/Type 头部 (通常是 00)。
3. 根对象如果是 dict[int, Any]，会被视为 Struct (Tag=Key) 而不是 Map。
"""

import pytest
from jce import JceField, JceOption, JceStruct, dumps

# --- 辅助结构体定义 ---


class User(JceStruct):
    """基础用户结构体."""

    uid: int = JceField(jce_id=0)
    name: str = JceField(jce_id=1)


class ComplexStruct(JceStruct):
    """包含嵌套和默认值的复杂结构体."""

    flag: bool = JceField(jce_id=0)
    nums: list[int] = JceField(jce_id=1)
    extra: dict[str, str] | None = JceField(jce_id=2, default=None)


class MapContainer(JceStruct):
    """专门用于测试 Map 编码的容器."""

    # 使用 Tag 0，类型为 Map
    data: dict[int, list[int]] = JceField(jce_id=0)


# --- 测试数据 ---

PRIMITIVE_CASES = [
    # Zero Tag (Tag 0, Type 12) -> 0C
    (0, "0C", "Zero Tag"),
    # INT1 (Tag 0, Type 0) -> 00 + 01
    (1, "0001", "INT1 正数"),
    (-1, "00FF", "INT1 负数"),
    # INT2 (Tag 0, Type 1) -> 01 + 0100 (256 Big Endian)
    (256, "010100", "INT2 大端序"),
    # INT4 (Tag 0, Type 2) -> 02 + 00010000 (65536)
    (65536, "0200010000", "INT4"),
    # Float (默认转为 DOUBLE)
    # Python float -> JCE DOUBLE (Tag 0, Type 5)
    # 1.5 -> 0x3FF8000000000000 (IEEE 754 Double)
    # 结果: 05 + 3FF8000000000000
    (1.5, "053FF8000000000000", "Float (转为 Double)"),
    # String1 (Tag 0, Type 6) -> 06 + 长度(01) + 'a'
    ("a", "060161", "String1 ASCII"),
    ("", "0600", "String1 空"),
    ("你", "0603E4BDA0", "String1 UTF-8"),
    # SimpleList (Bytes)
    # Tag 0, Type 13 (SimpleList) -> 0D
    # 头(Type 0, Tag 0) -> 00
    # 长度(2) 转为 INT1(Tag 0) -> 00 02  <-- 修正点: 长度也是 Integer，带头部 00
    # Data -> CA FE
    (b"\xca\xfe", "0D000002CAFE", "SimpleList (Bytes)"),
]

STRUCT_CASES = [
    # User(uid=100, name="test")
    # Tag 0: 00 64
    # Tag 1: 16 04 74657374
    (User(uid=100, name="test"), "0064160474657374", "简单结构体"),
    # ComplexStruct(flag=True, nums=[1, 2])
    # Tag 0 (flag): 00 01
    # Tag 1 (nums): LIST(Type 9) -> 19
    #   长度 2 (转为 INT1 Tag 0) -> 00 02  <-- 修正点: 长度头部
    #   项 0: 00 01
    #   项 1: 00 02
    (
        ComplexStruct(flag=True, nums=[1, 2]),
        "000119000200010002",
        "包含列表的复杂结构体",
    ),
]

OPTION_CASES = [
    # 小端序 (Little Endian)
    # 256 -> 00 01 (Tag 0, Type 1 INT2) -> 01 0001
    (256, "010001", JceOption.LITTLE_ENDIAN, "小端序选项"),
]

# --- 测试函数 ---


@pytest.mark.parametrize(("value", "expected", "desc"), PRIMITIVE_CASES)
def test_protocol_primitives(value, expected, desc):
    """基础类型的序列化结果应严格符合协议标准."""
    actual = dumps(value)
    assert actual.hex().upper() == expected, f"Failed: {desc}"


@pytest.mark.parametrize(("obj", "expected", "desc"), STRUCT_CASES)
def test_protocol_structs(obj, expected, desc):
    """结构体的序列化结果应严格符合协议标准."""
    actual = dumps(obj)
    assert actual.hex().upper() == expected, f"Failed: {desc}"


@pytest.mark.parametrize(("value", "expected", "option", "desc"), OPTION_CASES)
def test_protocol_options(value, expected, option, desc):
    """不同选项下的序列化结果应符合预期."""
    actual = dumps(value, option=option)
    assert actual.hex().upper() == expected, f"Failed: {desc}"


def test_protocol_omit_default():
    """开启 OMIT_DEFAULT 选项时应省略与默认值相等的字段."""

    class DefaultConfig(JceStruct):
        a: int = JceField(jce_id=0, default=1)
        b: int = JceField(jce_id=1, default=2)

    # 全是默认值 -> 空
    obj1 = DefaultConfig(a=1, b=2)
    assert len(dumps(obj1, option=JceOption.OMIT_DEFAULT)) == 0

    # 部分默认值 -> 10 03 (Tag 1, Val 3)
    obj2 = DefaultConfig(a=1, b=3)
    assert dumps(obj2, option=JceOption.OMIT_DEFAULT).hex().upper() == "1003"


def test_protocol_nested_map():
    """Map 的序列化结构 (Key-Value Pairs) 应符合协议标准."""
    # 输入: {10: [1]}
    # Map (Tag 0): Type 8 -> 08
    # 长度 1 (转为 INT1 Tag 0) -> 00 01
    # 键 (Tag 0): INT1(10) -> 00 0A
    # 值 (Tag 1): LIST(Type 9) -> 19
    #   列表长度 1 (转为 INT1 Tag 0) -> 00 01
    #   项 (Tag 0): INT1(1) -> 00 01

    container = MapContainer(data={10: [1]})

    # 08 0001 000A 19 0001 0001
    expected = "080001000A1900010001"

    actual = dumps(container)
    assert actual.hex().upper() == expected
