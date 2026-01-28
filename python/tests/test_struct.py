"""测试 JCE 结构体.

覆盖 tarsio.struct 模块的核心特性:
1. Struct 定义与字段配置 (default, default_factory)
2. 显式反序列化 (model_validate_tars)
3. 自动解包机制 (_auto_unpack_bytes_field)
4. 对象方法 (encode, decode)
5. 字段编码模式 (Nested/Blob/Any)
6. Union 类型支持 (Union[T, None], T | None)
"""

from typing import Any

import pytest
from pydantic import ValidationError
from tarsio import BYTES, Field, Struct, StructDict, dumps

# --- 辅助模型 ---


class SimpleUser(Struct):
    """基础测试用户结构体."""

    uid: int = Field(id=0)
    name: str = Field(id=1, default="unknown")


class FactoryUser(Struct):
    """测试 default_factory 的结构体."""

    tags: list[str] = Field(id=0, default_factory=list)
    scores: list[int] = Field(id=1, default_factory=lambda: [100])


class NestedUser(Struct):
    """测试嵌套的结构体."""

    info: SimpleUser = Field(id=0)


class BlobContainer(Struct):
    """测试自动解包: 字段声明为 Struct, 但实际数据可能是 bytes."""

    inner: SimpleUser = Field(id=0)


# --- 测试用例 ---


def test_struct_defaults() -> None:
    """Struct 应正确处理字段默认值和 factory."""
    # 标准 Pydantic 用法: 关键字参数
    u1 = SimpleUser(uid=1)
    assert u1.uid == 1
    assert u1.name == "unknown"

    u2 = FactoryUser()
    assert u2.tags == []
    assert u2.scores == [100]


def test_struct_validate_from_bytes() -> None:
    """model_validate_tars() 应支持从 bytes 直接反序列化."""
    # SimpleUser(uid=100, name="test") -> 00 64 ...
    raw_bytes = bytes.fromhex("0064160474657374")

    u = SimpleUser.model_validate_tars(raw_bytes)

    assert u.uid == 100
    assert u.name == "test"


def test_struct_validate_from_tag_dict() -> None:
    """model_validate_tars() 应支持从 StructDict (Tag-Map) 反序列化."""
    # 模拟 JCE 解码器的中间产物: StructDict({0: 100, ...})
    raw_dict = StructDict({0: 100, 1: "test"})

    u = SimpleUser.model_validate_tars(raw_dict)

    assert u.uid == 100
    assert u.name == "test"


def test_auto_unpack_nested_bytes() -> None:
    """当字段定义为 Struct 但数据是 bytes 时应自动尝试解包."""
    inner_bytes = bytes.fromhex("0063")  # uid=99

    # 构造包含 bytes 的 Tag-Dict
    raw_data = StructDict({0: inner_bytes})

    # 通过 model_validate_tars 解析
    container = BlobContainer.model_validate_tars(raw_data)

    assert isinstance(container.inner, SimpleUser)
    assert container.inner.uid == 99


def test_struct_methods() -> None:
    """model_dump_tars() 和 model_validate_tars() 应互为逆操作."""
    u = SimpleUser(uid=123)
    data = u.model_dump_tars()

    # 验证新旧方法是等价的
    u2 = SimpleUser.model_validate_tars(data)

    assert u2 == u
    assert u.model_dump_tars() == data


def test_validation_error() -> None:
    """缺失必填字段时应抛出 ValidationError."""
    with pytest.raises(ValidationError):
        SimpleUser()  # type: ignore[call-arg]


# --- 字段编码模式测试 ---


class NestedPattern(Struct):
    """模式 A: 标准嵌套结构体."""

    param: StructDict = Field(id=2)


class BlobPattern(Struct):
    """模式 B: 二进制 Blob (透传)."""

    param: StructDict = Field(id=2, tars_type=BYTES)


class AnyPattern(Struct):
    """模式 C: Any 类型 (动态推断)."""

    param: Any = Field(id=2)


class SafeAnyPattern(Struct):
    """模式 D: Any + 显式 BYTES (安全 Blob)."""

    param: Any = Field(id=2, tars_type=BYTES)


@pytest.fixture
def inner_data() -> StructDict:
    """提供测试用的标准内部数据 {0: 100}.

    Returns:
        StructDict({0: 100}).
    """
    return StructDict({0: 100})


def test_pattern_nested_struct(inner_data: StructDict) -> None:
    """模式 A 应编码为 JCE Struct (Tag 2, Type 10)."""
    obj = NestedPattern(param=inner_data)
    encoded = dumps(obj)

    assert encoded.startswith(b"\x2a")  # Tag 2, Type 10 (StructBegin)
    assert encoded.endswith(b"\x0b")  # Type 11 (StructEnd)
    assert b"\x00\x64" in encoded  # 内部数据 (Tag 0: 100)


def test_pattern_binary_blob(inner_data: StructDict) -> None:
    """模式 B 应编码为 SimpleList (Tag 2, Type 13)."""
    obj = BlobPattern(param=inner_data)
    encoded = dumps(obj)

    assert encoded.startswith(b"\x2d")  # Tag 2, Type 13 (SimpleList)
    assert b"\x00\x02\x00\x64" in encoded  # 长度 + 数据载荷


def test_pattern_any_with_jcedict(inner_data: StructDict) -> None:
    """模式 C 传入 StructDict 时应推断为 STRUCT."""
    obj = AnyPattern(param=inner_data)
    encoded = dumps(obj)

    assert encoded.startswith(b"\x2a")  # Tag 2, Type 10 (StructBegin)


def test_pattern_any_with_dict() -> None:
    """模式 C 传入 dict 时应推断为 MAP."""
    inner_dict = {0: 100}
    obj = AnyPattern(param=inner_dict)
    encoded = dumps(obj)

    assert encoded.startswith(b"\x28")  # Tag 2, Type 8 (Map)


def test_pattern_any_with_bytes_mode(inner_data: StructDict) -> None:
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
    """Field 应能透传其他参数给 Pydantic Field."""

    class ValidatedUser(Struct):
        age: int = Field(id=0, gt=0, lt=150, description="Age")

    # 1. 验证 description
    schema = ValidatedUser.model_json_schema()
    assert schema["properties"]["age"]["description"] == "Age"

    # 2. 验证 gt (大于)
    with pytest.raises(ValidationError):
        ValidatedUser(age=0)  # gt=0

    # 3. 验证 lt (小于)
    with pytest.raises(ValidationError):
        ValidatedUser(age=150)  # lt=150

    # 4. 正常情况
    u = ValidatedUser(age=25)
    assert u.age == 25


def test_jce_field_full_parameters() -> None:
    """验证 Field 的扩展参数能正确传递给 Pydantic."""
    import math

    class ComplexUser(Struct):
        # 1. 别名与排除
        name: str = Field(id=0, alias="username", exclude=True)

        # 2. 字符串约束
        code: str = Field(id=1, min_length=3, max_length=5, pattern=r"^[A-Z]+$")

        # 3. 数值约束
        score: float = Field(id=2, ge=0, le=100, multiple_of=0.5)

        # 4. 特殊约束
        ratio: float = Field(id=3, allow_inf_nan=False)

        # 5. 冻结字段
        fixed: int = Field(id=4, default=10, frozen=True)

    # 测试 1: Alias (别名)
    # 使用 alias 初始化
    u = ComplexUser(username="Admin", code="ABC", score=50.0, ratio=1.0)
    assert u.name == "Admin"

    # 测试 2: Exclude (排除)
    # model_dump 应该排除该字段
    dump_dict = u.model_dump()
    assert "name" not in dump_dict
    assert "code" in dump_dict

    # 测试 3: 字符串约束
    with pytest.raises(ValidationError, match="should have at least 3 characters"):
        ComplexUser(username="A", code="AB", score=50.0, ratio=1.0)

    with pytest.raises(ValidationError, match="should have at most 5 characters"):
        ComplexUser(username="A", code="ABCDEF", score=50.0, ratio=1.0)

    with pytest.raises(ValidationError, match="should match pattern"):
        ComplexUser(username="A", code="abc", score=50.0, ratio=1.0)

    # 测试 4: 数值约束
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        # -0.5 是 0.5 的倍数，因此只有 ge=0 失败
        ComplexUser(username="A", code="ABC", score=-0.5, ratio=1.0)

    with pytest.raises(ValidationError, match="less than or equal to 100"):
        # 100.5 是 0.5 的倍数，因此只有 le=100 失败
        ComplexUser(username="A", code="ABC", score=100.5, ratio=1.0)

    with pytest.raises(ValidationError, match=r"multiple of 0.5"):
        # 50.1 >=0 且 <=100，因此只有 multiple_of 失败
        ComplexUser(username="A", code="ABC", score=50.1, ratio=1.0)

    # 测试 5: allow_inf_nan (允许 Inf/NaN)
    with pytest.raises(ValidationError, match="finite number"):
        ComplexUser(username="A", code="ABC", score=50.0, ratio=math.nan)

    # 测试 6: Frozen (冻结)
    # Frozen 字段在赋值时应该报错 (Pydantic v2 行为可能需要 ConfigDict(validate_assignment=True) 或者只在 model 层面 frozen)
    # Field(frozen=True) 通常意味着该字段不可修改
    with pytest.raises(ValidationError, match="frozen"):
        u.fixed = 20


# --- Union 类型支持测试 ---


def test_union_none_syntax() -> None:
    """测试 Python 3.10+ T | None 语法."""

    class Model(Struct):
        f1: int | None = Field(id=0)
        f2: str | None = Field(id=1)

    m = Model(f1=123, f2="abc")
    assert m.f1 == 123
    assert m.f2 == "abc"

    encoded = m.model_dump_tars()
    decoded = Model.model_validate_tars(encoded)
    assert decoded.f1 == 123
    assert decoded.f2 == "abc"


def test_optional_alias_syntax() -> None:
    """测试 Optional[T] 别名 (应与 T | None 行为一致)."""

    class Model(Struct):
        f1: int | None = Field(id=0)

    m = Model(f1=123)
    assert m.f1 == 123


def test_union_polymorphic_error() -> None:
    """测试 A | B (当两者均不为 None 时) 应抛出 TypeError."""
    with pytest.raises(TypeError, match="Union type not supported"):

        class Model(Struct):
            f1: int | str = Field(id=0)


def test_union_multiple_error() -> None:
    """测试 A | B | None 应抛出 TypeError."""
    with pytest.raises(TypeError, match="Union type not supported"):

        class Model(Struct):
            f1: int | str | None = Field(id=0)
