"""JCE编码器循环引用检测测试."""

from typing import Any

import pytest

from jce import JceEncodeError, dumps


def test_circular_list():
    """测试列表中检测循环引用."""
    circular_list: list[Any] = [1, 2, 3]
    circular_list.append(circular_list)

    with pytest.raises(JceEncodeError, match="Circular reference detected"):
        dumps({0: circular_list})


def test_circular_dict():
    """测试字典中检测循环引用."""
    circular_dict: dict[str, Any] = {"a": 1, "b": 2}
    circular_dict["self"] = circular_dict

    with pytest.raises(JceEncodeError, match="Circular reference detected"):
        dumps({0: circular_dict})


def test_nested_circular():
    """测试深度嵌套中检测循环引用."""
    list1: list[Any] = [1, 2]
    list2: list[Any] = [3, 4, list1]
    list1.append(list2)

    with pytest.raises(JceEncodeError, match="Circular reference detected"):
        dumps({0: list1})


def test_non_circular_nested():
    """测试非循环嵌套结构正常工作."""
    # 这不应引发错误
    shared_list = [1, 2, 3]
    container = {
        0: shared_list,
        1: shared_list,  # 同一对象引用两次, 但无循环
    }

    # 这应成功编码
    result = dumps(container)
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_deep_nesting_no_circle():
    """测试无循环的深度嵌套正常工作."""
    deeply_nested: dict[str, Any] = {"level": 1}
    current = deeply_nested
    for i in range(2, 10):
        current["next"] = {"level": i}
        current = current["next"]

    # 这应成功编码
    result = dumps({0: deeply_nested})
    assert isinstance(result, bytes)
    assert len(result) > 0
