"""Tests for circular reference detection in JCE encoder."""

from typing import Any

import pytest

from jce import JceEncodeError, dumps


def test_circular_list():
    """Test that circular references in lists are detected."""
    circular_list = [1, 2, 3]
    circular_list.append(circular_list)  # type: ignore[arg-type]  # Intentional circular reference

    with pytest.raises(JceEncodeError, match="Circular reference detected"):
        dumps({0: circular_list})


def test_circular_dict():
    """Test that circular references in dicts are detected."""
    circular_dict = {"a": 1, "b": 2}
    circular_dict["self"] = circular_dict  # type: ignore[assignment]  # Intentional circular reference

    with pytest.raises(JceEncodeError, match="Circular reference detected"):
        dumps({0: circular_dict})


def test_nested_circular():
    """Test that deeply nested circular references are detected."""
    list1 = [1, 2]
    list2 = [3, 4, list1]
    list1.append(list2)  # type: ignore[arg-type]  # Intentional circular reference

    with pytest.raises(JceEncodeError, match="Circular reference detected"):
        dumps({0: list1})


def test_non_circular_nested():
    """Test that non-circular nested structures work fine."""
    # This should NOT raise an error
    shared_list = [1, 2, 3]
    container = {
        0: shared_list,
        1: shared_list,  # Same object referenced twice, but no cycle
    }

    # This should encode successfully
    result = dumps(container)
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_deep_nesting_no_circle():
    """Test that deep nesting without circles works."""
    deeply_nested: dict[str, Any] = {"level": 1}
    current = deeply_nested
    for i in range(2, 10):
        current["next"] = {"level": i}  # type: ignore[assignment]
        current = current["next"]

    # This should encode successfully
    result = dumps({0: deeply_nested})
    assert isinstance(result, bytes)
    assert len(result) > 0
