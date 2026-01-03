"""JCE通用编解码测试."""

from jce import JceField, JceStruct, dumps, loads, types


class SimpleStruct(JceStruct):
    """简单测试结构体."""

    a: int = JceField(jce_id=0, jce_type=types.INT)
    b: str = JceField(jce_id=1, jce_type=types.STRING)


def test_dumps_loads_struct() -> None:
    """测试结构体序列化和反序列化."""
    s = SimpleStruct(a=123, b="hello")
    data = dumps(s)

    # Load as Struct
    s2 = loads(data, SimpleStruct)
    assert s.a == s2.a
    assert s.b == s2.b

    # Load as dict
    d = loads(data, dict)
    assert d[0] == 123
    assert d[1] == "hello"  # Generic decoder decoded string


def test_dumps_dict() -> None:
    """测试字典序列化."""
    # Dump a dict as if it was a struct
    d = {0: 123, 1: "hello"}
    data = dumps(d)

    # Load back
    d2 = loads(data, dict)
    assert d2[0] == 123
    assert d2[1] == "hello"


def test_nested_generic() -> None:
    """测试嵌套通用类型."""
    # Struct with list
    # We can't easily define nested struct without JceStruct classes for dumps yet
    # unless we construct the dict manually with tags.

    # {0: [1, 2, 3]} -> Tag 0 is List of Ints
    d = {0: [1, 2, 3]}
    data = dumps(d)

    d2 = loads(data, dict)
    assert d2[0] == [1, 2, 3]
