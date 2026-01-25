from typing import Any

def dumps(
    obj: Any,
    schema: list[tuple[str, int, int, Any, bool, bool]],
    options: int = 0,
    context: dict[str, Any] | None = None,
) -> bytes: ...
def dumps_generic(
    obj: Any, options: int = 0, context: dict[str, Any] | None = None
) -> bytes: ...
def loads(
    data: bytes,
    schema: list[tuple[str, int, int, Any, bool, bool]],
    options: int = 0,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]: ...
def loads_generic(
    data: bytes, options: int = 0, context: dict[str, Any] | None = None
) -> dict[int, Any]: ...
