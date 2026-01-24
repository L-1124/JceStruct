"""测试 JCE 泛型支持."""

from typing import Generic, TypeVar

import pytest
from pydantic import ValidationError

from jce import JceField, JceStruct, dumps, loads, types

T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")


class Box(JceStruct, Generic[T]):
    """基础泛型容器."""

    value: T = JceField(jce_id=0)


class Pair(JceStruct, Generic[K, V]):
    """双类型泛型容器."""

    key: K = JceField(jce_id=0)
    value: V = JceField(jce_id=1)


class User(JceStruct):
    """测试用的普通结构体."""

    uid: int = JceField(jce_id=0)
    name: str = JceField(jce_id=1)


def test_generic_primitive() -> None:
    """Box[int] 应能正确处理基础类型的泛型参数."""
    box = Box[int](value=100)
    data = dumps(box)

    assert data.hex().upper() == "0064"

    restored = loads(data, Box[int])
    assert restored.value == 100
    assert isinstance(restored.value, int)


def test_generic_struct() -> None:
    """Box[User] 应能正确处理嵌套结构体的泛型参数."""
    user = User(uid=1, name="A")
    box = Box[User](value=user)

    data = dumps(box)

    restored = loads(data, Box[User])
    assert restored.value.uid == 1
    assert restored.value.name == "A"
    assert isinstance(restored.value, User)


def test_generic_multi_type() -> None:
    """Pair[int, str] 应能处理多个泛型参数."""
    pair = Pair[int, str](key=1, value="test")
    data = dumps(pair)

    restored = loads(data, Pair[int, str])
    assert restored.key == 1
    assert restored.value == "test"


def test_generic_inheritance() -> None:
    """继承自泛型类的具体子类应能正确解析类型."""

    class IntBox(Box[int]):
        pass

    box = IntBox(value=999)
    data = dumps(box)

    restored = loads(data, IntBox)
    assert restored.value == 999

    bad_data = bytes.fromhex("0603616263")  # Tag 0 = String "abc"

    with pytest.raises((ValidationError, TypeError)):
        loads(bad_data, IntBox)


def test_nested_generics() -> None:
    """Box[Box[int]] 应能处理多层嵌套泛型."""
    inner = Box[int](value=42)
    outer = Box[Box[int]](value=inner)

    data = dumps(outer)

    restored = loads(data, Box[Box[int]])
    assert restored.value.value == 42
    assert isinstance(restored.value, Box)


def test_generic_list_field() -> None:
    """Box[list[int]] 应能处理泛型列表字段."""
    box = Box[list[int]](value=[1, 2, 3])
    data = dumps(box)

    restored = loads(data, Box[list[int]])
    assert restored.value == [1, 2, 3]


def test_generic_base_fields_discovery() -> None:
    """从泛型基类发现字段 (覆盖 SchemaDecoder.__init__ 中的逻辑)."""

    class Base(JceStruct, Generic[T]):
        base_field: int = JceField(jce_id=0, jce_type=types.INT32)

    class Derived(Base[int]):
        pass

    data = Derived(base_field=999)
    encoded = dumps(data)

    decoded = loads(encoded, Derived)
    assert decoded.base_field == 999
