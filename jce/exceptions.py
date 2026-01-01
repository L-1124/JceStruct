"""JCE特定的异常类.

该模块为JCE库定义了异常层次结构.
"""


class JceError(Exception):
    """所有JCE异常的基类."""

    pass


class JceEncodeError(JceError):
    """序列化失败时抛出.

    这可能发生在对象不匹配JceStruct定义，
    或如果值超出指定JCE类型的范围.
    """

    pass


class JceDecodeError(JceError):
    """反序列化失败时抛出.

    这可能发生在输入数据被截断、格式错误，
    或标签不符合预期模式时.
    """

    pass


class JcePartialDataError(JceDecodeError):
    """输入数据不完整时抛出.

    这对于流处理很有用，在这种情况下稍后可能会获得更多数据.
    """

    pass
