
def dumps(
    obj: object,
    schema: list[tuple[str, int, int, object, bool, bool]],
    options: int = 0,
    context: dict[str, object] | None = None,
) -> bytes:
    """使用 Schema 将 JceStruct 对象序列化为字节流.

    Args:
        obj: 要序列化的 JceStruct 实例.
        schema: 描述字段的元组列表：
            (name, tag, type, default, has_serializer, has_deserializer).
        options: 序列化选项（例如，用于控制字节序的位标志）.
        context: 传递给字段序列化器的可选上下文字典.

    Returns:
        bytes: 序列化后的 JCE 数据.
    """
    ...

def dumps_generic(
    obj: object, options: int = 0, context: dict[str, object] | None = None
) -> bytes:
    """不使用 Schema 将任意 Python 对象序列化为 JCE 字节流.

    Args:
        obj: 要序列化的对象（dict, list, int, str 等）.
             如果 dict 的键是整数且范围在 0-255，则被视为 JceStruct 处理.
        options: 序列化选项.
        context: 可选的上下文字典.

    Returns:
        bytes: 序列化后的 JCE 数据.
    """
    ...

def loads(
    data: bytes,
    schema: list[tuple[str, int, int, object, bool, bool]],
    options: int = 0,
    context: dict[str, object] | None = None,
) -> dict[str, object]:
    """使用 Schema 将 JCE 字节流反序列化为字典.

    Args:
        data: 二进制 JCE 数据.
        schema: 目标结构的 Schema 定义.
        options: 反序列化选项.
        context: 传递给字段反序列化器的可选上下文字典.

    Returns:
        dict[str, object]: 包含解析后字段的字典.
    """
    ...

def loads_generic(
    data: bytes, options: int = 0, context: dict[str, object] | None = None
) -> dict[int, object]:
    """不使用 Schema 将 JCE 字节流反序列化为标签字典.

    Args:
        data: 二进制 JCE 数据.
        options: 反序列化选项.
        context: 可选的上下文字典.

    Returns:
        dict[int, object]: 映射标签到解析值的字典（类似 JceDict 的结构）.
    """
    ...
