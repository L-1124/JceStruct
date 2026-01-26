"""JCE特定的异常类.

该模块为JCE库定义了异常层次结构.
"""


class JceError(Exception):
    """所有 JCE 异常的基类."""

    pass


class JceEncodeError(JceError):
    """序列化失败时抛出.

    Case:
        - 对象不匹配 `JceStruct` 定义.
        - 值超出指定 JCE 类型的范围 (如 `INT1` 存了 300).
        - 循环引用.
    """

    pass


class JceDecodeError(JceError):
    """反序列化失败时抛出.

    Case:
        - 输入数据被截断.
        - 格式错误 (如魔数不匹配).
        - 标签 (Tag) 不符合预期.
    """

    def __init__(
        self,
        msg: str,
        loc: list[str | int] | None = None,
    ) -> None:
        """初始化解码错误.

        Args:
            msg: 错误描述信息.
            loc: 错误发生的位置路径 (Tag ID 或 索引).
        """
        super().__init__(msg)
        self.loc = loc or []

    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.loc:
            # 格式化为 dotted path
            loc_str = ".".join(str(x) for x in self.loc)
            return f"{base_msg} (at {loc_str})"
        return base_msg


class JcePartialDataError(JceDecodeError):
    """输入数据不完整时抛出.

    通常在使用非阻塞 I/O 或流式解析时抛出，表示需要更多数据才能完成解析。
    """

    pass


class JceTypeError(JceEncodeError, TypeError):
    """类型不匹配时抛出."""

    pass


class JceValueError(JceEncodeError, ValueError):
    """值无效时抛出 (如超出范围)."""

    pass
