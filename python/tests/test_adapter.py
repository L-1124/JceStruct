"""测试 JCE 类型适配器."""

import pytest
from jce import JceDict, JceField, JceStruct, dumps
from jce.adapter import JceTypeAdapter


class User(JceStruct):
    """用户信息."""

    uid: int = JceField(jce_id=0)
    name: str = JceField(jce_id=1)


def test_adapter_struct_knowledge() -> None:
    """JceTypeAdapter 应能自动识别 Struct 中的 Tag ID."""
    adapter = JceTypeAdapter(User)
    user = User(uid=100, name="Alice")
    data = adapter.dump_jce(user)

    user_restored = adapter.validate_jce(data)

    assert user_restored.uid == 100
    assert user_restored.name == "Alice"


def test_adapter_primitive_default_tag() -> None:
    """JceTypeAdapter 对于基础类型默认使用 Tag 0."""
    adapter = JceTypeAdapter(int)
    data = adapter.dump_jce(123)

    val = adapter.validate_jce(data)

    assert val == 123


def test_adapter_primitive_custom_tag() -> None:
    """JceTypeAdapter 应支持指定非 0 的 Tag."""
    adapter = JceTypeAdapter(int)
    data = dumps(JceDict({5: 999}))

    with pytest.raises(ValueError, match="No data found at jce_id 0"):
        adapter.validate_jce(data)

    val = adapter.validate_jce(data, jce_id=5)

    assert val == 999


def test_adapter_generic_list() -> None:
    """JceTypeAdapter 应支持泛型 list[int]."""
    adapter = JceTypeAdapter(list[int])
    input_list = [1, 2, 3]
    data = adapter.dump_jce(input_list)

    restored = adapter.validate_jce(data)

    assert restored == input_list


def test_adapter_list_of_structs() -> None:
    """JceTypeAdapter 应支持结构体列表 list[User]."""
    adapter = JceTypeAdapter(list[User])
    users = [User(uid=1, name="A"), User(uid=2, name="B")]
    data = adapter.dump_jce(users)

    restored = adapter.validate_jce(data)

    assert len(restored) == 2
    assert restored[0].name == "A"
    assert restored[1].uid == 2


def test_adapter_generic_dict() -> None:
    """JceTypeAdapter 应支持泛型 dict[int, str] (JCE Map)."""
    adapter = JceTypeAdapter(dict[int, str])
    input_map = {100: "ok", 404: "not found"}
    data = adapter.dump_jce(input_map)

    restored = adapter.validate_jce(data)

    assert restored == input_map


def test_adapter_not_struct_type() -> None:
    """JceTypeAdapter 应能正确区分 Struct 和非 Struct 类型."""
    adapter = JceTypeAdapter(list[int])
    assert adapter._is_struct is False

    adapter2 = JceTypeAdapter(User)
    assert adapter2._is_struct is True
