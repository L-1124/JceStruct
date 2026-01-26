"""JCE类型适配器.

提供类似于 Pydantic TypeAdapter 的接口,
用于处理泛型类型和基础类型的 JCE 序列化/反序列化.
"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, TypeAdapter

from .api import dumps, loads
from .options import JceOption
from .struct import JceDict

T = TypeVar("T")


class JceTypeAdapter(Generic[T]):
    """JCE 类型适配器.

    用于处理泛型类型和基础类型的 JCE 序列化/反序列化。
    类似于 `pydantic.TypeAdapter`，但针对 JCE 协议。

    支持的类型:
        - `JceStruct` 子类 (声明式结构体)
        - `JceDict` (匿名结构体)
        - 基础类型 (`int`, `str`, `bytes` 等)
        - 容器类型 (`list`, `dict` 等)

    Examples:
        >>> adapter = JceTypeAdapter(list[int])
        >>> data = adapter.dump_jce([1, 2, 3])
        >>> result = adapter.validate_jce(data, jce_id=0)
        >>> assert result == [1, 2, 3]
    """

    def __init__(self, type_: type[T] | Any):
        """初始化 JCE 类型适配器.

        Args:
            type_: 目标类型 (如 JceStruct 子类, list[int], int 等).
        """
        self._type = type_
        self._pydantic_adapter = TypeAdapter(type_)

        # 预先判断是否为结构体类型
        # 1. Pydantic Model (JceStruct)
        # 2. JceDict (显式匿名结构体)
        # 如果 type_ 是泛型别名 (如 list[int]), issubclass 会报错, 需处理异常
        self._is_struct = False
        try:
            if isinstance(type_, type) and issubclass(type_, BaseModel | JceDict):
                self._is_struct = True
        except TypeError:
            pass  # type_ 是泛型实例 (如 list[int]), 不是类

    def validate_jce(
        self, data: bytes, *, option: JceOption = JceOption.NONE, jce_id: int = 0
    ) -> T:
        """验证并反序列化 JCE 数据.

        Args:
            data: JCE 字节数据.
            option: JCE 选项 (字节序等).
            jce_id: 目标数据的 Tag ID (仅对非结构体类型有效).
                对于结构体类型 (JceStruct/JceDict), 此参数被忽略。
                对于基础类型和容器，指定数据所在的 Tag ID。

        Returns:
            反序列化后的对象.

        Raises:
            ValueError: 如果指定的 jce_id 不存在于数据中。

        Examples:
            >>> # 结构体类型
            >>> adapter = JceTypeAdapter(User)
            >>> user = adapter.validate_jce(data)
            >>>
            >>> # 基础类型 (需要指定 Tag ID)
            >>> adapter = JceTypeAdapter(list[int])
            >>> numbers = adapter.validate_jce(data, jce_id=0)
        """
        parsed_dict = loads(data, option=JceOption(option))

        if self._is_struct:
            # Case A: 结构体 (JceStruct 或 JceDict)
            # 整个 dict 就是结构体的数据源 (Tag-Value 映射)
            value = parsed_dict
        else:
            # Case B: 基本类型或容器 (数据被包裹在单个 Tag 中)
            # 例如: List[int], Dict[int, str], int, str
            if jce_id not in parsed_dict:
                raise ValueError(f"No data found at jce_id {jce_id}")
            value = parsed_dict[jce_id]

        # 3. 使用 Pydantic TypeAdapter 进行转换
        return self._pydantic_adapter.validate_python(value)

    def dump_jce(self, obj: T, *, option: JceOption = JceOption.NONE) -> bytes:
        """序列化为 JCE 数据."""
        # 直接调用 dumps, JceEncoder 会自动识别 JceDict vs dict
        return dumps(obj, option=JceOption(option))
