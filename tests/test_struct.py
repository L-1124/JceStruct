"""测试 JCE 结构体.

覆盖 jce.struct 模块的核心特性:
1. JceStruct 定义与字段配置 (default, default_factory)
2. 显式反序列化 (model_validate_jce)
3. 自动解包机制 (_auto_unpack_bytes_field)
4. 对象方法 (encode, decode)
5. 字段编码模式 (Nested/Blob/Any)
"""

from typing import Any

import pytest
from pydantic import ValidationError

from jce import BYTES, JceDict, JceField, JceStruct, dumps

# --- 辅助模型 ---


class SimpleUser(JceStruct):
    """基础测试用户结构体."""

    uid: int = JceField(jce_id=0)
    name: str = JceField(jce_id=1, default="unknown")


class FactoryUser(JceStruct):
    """测试 default_factory 的结构体."""

    tags: list[str] = JceField(jce_id=0, default_factory=list)
    scores: list[int] = JceField(jce_id=1, default_factory=lambda: [100])


class NestedUser(JceStruct):
    """测试嵌套的结构体."""

    info: SimpleUser = JceField(jce_id=0)


class BlobContainer(JceStruct):
    """测试自动解包: 字段声明为 Struct, 但实际数据可能是 bytes."""

    inner: SimpleUser = JceField(jce_id=0)


# --- 测试用例 ---


def test_struct_defaults() -> None:
    """JceStruct 应正确处理字段默认值和 factory."""
    # 标准 Pydantic 用法: 关键字参数
    u1 = SimpleUser(uid=1)
    assert u1.uid == 1
    assert u1.name == "unknown"

    u2 = FactoryUser()
    assert u2.tags == []
    assert u2.scores == [100]


def test_struct_validate_from_bytes() -> None:
    """model_validate_jce() 应支持从 bytes 直接反序列化."""
    # SimpleUser(uid=100, name="test") -> 00 64 ...
    raw_bytes = bytes.fromhex("0064160474657374")

    u = SimpleUser.model_validate_jce(raw_bytes)

    assert u.uid == 100
    assert u.name == "test"


def test_struct_validate_from_tag_dict() -> None:
    """model_validate_jce() 应支持从 JceDict (Tag-Map) 反序列化."""
    # 模拟 JCE 解码器的中间产物: JceDict({0: 100, ...})
    raw_dict = JceDict({0: 100, 1: "test"})

    u = SimpleUser.model_validate_jce(raw_dict)

    assert u.uid == 100
    assert u.name == "test"


def test_auto_unpack_nested_bytes() -> None:
    """当字段定义为 Struct 但数据是 bytes 时应自动尝试解包."""
    inner_bytes = bytes.fromhex("0063")  # uid=99

    # 构造包含 bytes 的 Tag-Dict
    raw_data = JceDict({0: inner_bytes})

    # 通过 model_validate_jce 解析
    container = BlobContainer.model_validate_jce(raw_data)

    assert isinstance(container.inner, SimpleUser)
    assert container.inner.uid == 99


def test_struct_methods() -> None:
    """model_dump_jce() 和 model_validate_jce() 应互为逆操作."""
    u = SimpleUser(uid=123)
    data = u.model_dump_jce()

    # 验证新旧方法是等价的
    u2 = SimpleUser.model_validate_jce(data)

    assert u2 == u
    assert u.model_dump_jce() == data


def test_from_bytes_shortcut() -> None:
    """from_bytes() 应返回解码后的字典和消耗长度."""
    data = bytes.fromhex("0001")
    res_dict, _ = SimpleUser.from_bytes(data)

    assert isinstance(res_dict, JceDict)
    assert res_dict == {0: 1}


def test_validation_error() -> None:
    """缺失必填字段时应抛出 ValidationError."""
    with pytest.raises(ValidationError):
        SimpleUser()  # type: ignore[call-arg]


def test_jcedict_key_validation_init() -> None:
    """JceDict 初始化时应拒绝非 int 类型的键."""
    # 正常情况: 所有键都是 int
    d1 = JceDict({0: 100, 1: "test"})
    assert d1[0] == 100
    assert d1[1] == "test"

    # 异常情况: 包含非 int 键
    with pytest.raises(TypeError, match="keys must be int"):
        JceDict({"name": "value"})

    with pytest.raises(TypeError, match="keys must be int"):
        JceDict({0: 100, "key": "value"})


def test_jcedict_key_validation_setitem() -> None:
    """JceDict 赋值时应拒绝非 int 类型的键."""
    d = JceDict()

    # 正常: int 键
    d[0] = 100
    assert d[0] == 100

    # 异常: str 键
    with pytest.raises(TypeError, match="keys must be int"):
        d["name"] = "value"  # type: ignore[arg]

    # 异常: float 键
    with pytest.raises(TypeError, match="keys must be int"):
        d[1.5] = "value"  # type: ignore[arg]


# --- 字段编码模式测试 ---


class NestedPattern(JceStruct):
    """模式 A: 标准嵌套结构体."""

    param: JceDict = JceField(jce_id=2)


class BlobPattern(JceStruct):
    """模式 B: 二进制 Blob (透传)."""

    param: JceDict = JceField(jce_id=2, jce_type=BYTES)


class AnyPattern(JceStruct):
    """模式 C: Any 类型 (动态推断)."""

    param: Any = JceField(jce_id=2)


class SafeAnyPattern(JceStruct):
    """模式 D: Any + 显式 BYTES (安全 Blob)."""

    param: Any = JceField(jce_id=2, jce_type=BYTES)


@pytest.fixture
def inner_data() -> JceDict:
    """提供测试用的标准内部数据 {0: 100}.

    Returns:
        JceDict({0: 100}).
    """
    return JceDict({0: 100})


def test_pattern_nested_struct(inner_data: JceDict) -> None:
    """模式 A 应编码为 JCE Struct (Tag 2, Type 10)."""
    obj = NestedPattern(param=inner_data)
    encoded = dumps(obj)

    assert encoded.startswith(b"\x2a")  # Tag 2, Type 10 (StructBegin)
    assert encoded.endswith(b"\x0b")  # Type 11 (StructEnd)
    assert b"\x00\x64" in encoded  # 内部数据 (Tag 0: 100)


def test_pattern_binary_blob(inner_data: JceDict) -> None:
    """模式 B 应编码为 SimpleList (Tag 2, Type 13)."""
    obj = BlobPattern(param=inner_data)
    encoded = dumps(obj)

    assert encoded.startswith(b"\x2d")  # Tag 2, Type 13 (SimpleList)
    assert b"\x00\x02\x00\x64" in encoded  # Length + Payload


def test_pattern_any_with_jcedict(inner_data: JceDict) -> None:
    """模式 C 传入 JceDict 时应推断为 STRUCT."""
    obj = AnyPattern(param=inner_data)
    encoded = dumps(obj)

    assert encoded.startswith(b"\x2a")  # Tag 2, Type 10 (StructBegin)


def test_pattern_any_with_dict() -> None:
    """模式 C 传入 dict 时应推断为 MAP."""
    inner_dict = {0: 100}
    obj = AnyPattern(param=inner_dict)
    encoded = dumps(obj)

    assert encoded.startswith(b"\x28")  # Tag 2, Type 8 (Map)


def test_pattern_any_with_bytes_mode(inner_data: JceDict) -> None:
    """模式 D (Any + BYTES) 应始终作为 Blob 编码."""
    obj = SafeAnyPattern(param=inner_data)
    encoded = dumps(obj)

    assert encoded.startswith(b"\x2d")  # Tag 2, Type 13 (SimpleList)


def test_any_field_inference_consistency() -> None:
    """验证 Any 字段的类型推断一致性."""
    # int -> INT (100 适合 1 字节)
    assert dumps(AnyPattern(param=100)).startswith(b"\x20")

    # str -> STRING
    assert dumps(AnyPattern(param="a")).startswith(b"\x26")  # Tag 2, Type 6 (STRING1)

    # bytes -> SIMPLE_LIST
    assert dumps(AnyPattern(param=b"a")).startswith(b"\x2d")  # Tag 2, Type 13


def test_jce_field_with_extra_kwargs() -> None:
    """JceField 应能透传其他参数给 Pydantic Field."""

    class ValidatedUser(JceStruct):
        age: int = JceField(jce_id=0, gt=0, lt=150, description="Age")

    # 1. 验证 description
    schema = ValidatedUser.model_json_schema()
    assert schema["properties"]["age"]["description"] == "Age"

    # 2. 验证 gt (Greater Than)
    with pytest.raises(ValidationError):
        ValidatedUser(age=0)  # gt=0

    # 3. 验证 lt (Less Than)
    with pytest.raises(ValidationError):
        ValidatedUser(age=150)  # lt=150

    # 4. 正常情况
    u = ValidatedUser(age=25)
    assert u.age == 25


def test_jce_field_full_parameters() -> None:
    """验证 JceField 的扩展参数能正确传递给 Pydantic."""
    import math

    class ComplexUser(JceStruct):
        # 1. 别名与排除
        name: str = JceField(jce_id=0, alias="username", exclude=True)

        # 2. 字符串约束
        code: str = JceField(jce_id=1, min_length=3, max_length=5, pattern=r"^[A-Z]+$")

        # 3. 数值约束
        score: float = JceField(jce_id=2, ge=0, le=100, multiple_of=0.5)

        # 4. 特殊约束
        ratio: float = JceField(jce_id=3, allow_inf_nan=False)

        # 5. 冻结字段
        fixed: int = JceField(jce_id=4, default=10, frozen=True)

    # 测试 1: Alias (别名)
    # 使用 alias 初始化
    u = ComplexUser(username="Admin", code="ABC", score=50.0, ratio=1.0)
    assert u.name == "Admin"

    # 测试 2: Exclude (排除)
    # model_dump 应该排除该字段
    dump_dict = u.model_dump()
    assert "name" not in dump_dict
    assert "code" in dump_dict

    # 测试 3: String constraints (字符串约束)
    with pytest.raises(ValidationError, match="should have at least 3 characters"):
        ComplexUser(username="A", code="AB", score=50.0, ratio=1.0)

    with pytest.raises(ValidationError, match="should have at most 5 characters"):
        ComplexUser(username="A", code="ABCDEF", score=50.0, ratio=1.0)

    with pytest.raises(ValidationError, match="should match pattern"):
        ComplexUser(username="A", code="abc", score=50.0, ratio=1.0)

    # 测试 4: Number constraints (数值约束)
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        # -0.5 is a multiple of 0.5, so only ge=0 fails
        ComplexUser(username="A", code="ABC", score=-0.5, ratio=1.0)

    with pytest.raises(ValidationError, match="less than or equal to 100"):
        # 100.5 is multiple of 0.5, so only le=100 fails
        ComplexUser(username="A", code="ABC", score=100.5, ratio=1.0)

    with pytest.raises(ValidationError, match=r"multiple of 0.5"):
        # 50.1 is >=0 and <=100, so only multiple_of fails
        ComplexUser(username="A", code="ABC", score=50.1, ratio=1.0)

    # 测试 5: allow_inf_nan (允许 Inf/NaN)
    with pytest.raises(ValidationError, match="finite number"):
        ComplexUser(username="A", code="ABC", score=50.0, ratio=math.nan)

    # 测试 6: Frozen (冻结)
    # Frozen 字段在赋值时应该报错 (Pydantic v2 行为可能需要 ConfigDict(validate_assignment=True) 或者只在 model 层面 frozen)
    # Field(frozen=True) 通常意味着该字段不可修改
    with pytest.raises(ValidationError, match="frozen"):
        u.fixed = 20
