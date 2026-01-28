"""JCE类型适配器.

提供类似于 Pydantic TypeAdapter 的接口,
用于处理泛型类型和基础类型的 Tarsio 序列化/反序列化.
"""

from typing import (
    Any,
    Generic,
    TypeVar,
    cast,
)

from pydantic import BaseModel, TypeAdapter

from .api import dumps, loads
from .options import Option
from .struct import StructDict

T = TypeVar("T")


class TarsTypeAdapter(Generic[T]):
    """JCE 类型适配器.

    用于处理泛型类型和基础类型的 Tarsio 序列化/反序列化。
    类似于 `pydantic.TypeAdapter`，但针对 Tarsio 协议。

    支持的类型:
        - `Struct` 子类 (声明式结构体)
        - `StructDict` (匿名结构体)
        - 基础类型 (`int`, `str`, `bytes` 等)
        - 容器类型 (`list`, `dict` 等)

    Examples:
        >>> adapter = TarsTypeAdapter(list[int])
        >>> data = adapter.dump_tars([1, 2, 3])
        >>> result = adapter.validate_tars(data, id=0)
        >>> assert result == [1, 2, 3]
    """

    def __init__(self, type_: type[T] | Any):
        """初始化 JCE 类型适配器.

        Args:
            type_: 目标类型 (如 Struct 子类, list[int], int 等).
        """
        self._type = type_
        self._pydantic_adapter = TypeAdapter(type_)

        # 预先判断是否为结构体类型
        # 1. Pydantic Model (Struct)
        # 2. StructDict (显式匿名结构体)
        # 如果 type_ 是泛型别名 (如 list[int]), issubclass 会报错, 需处理异常
        self._is_struct = False
        try:
            if isinstance(type_, type) and issubclass(type_, BaseModel | StructDict):
                self._is_struct = True
        except TypeError:
            pass  # type_ 是泛型实例 (如 list[int]), 不是类

    def validate_tars(
        self, data: bytes, *, option: Option = Option.NONE, id: int = 0
    ) -> T:
        """验证并反序列化 Tarsio 数据.

        Args:
            data: JCE 字节数据.
            option: JCE 选项 (字节序等).
            id: 目标数据的 Tag ID (仅对非结构体类型有效).
                对于结构体类型 (Struct/StructDict), 此参数被忽略。
                对于基础类型和容器，指定数据所在的 Tag ID。

        Returns:
            反序列化后的对象.

        Raises:
            ValueError: 如果指定的 id 不存在于数据中。

        Examples:
            >>> # 结构体类型
            >>> adapter = TarsTypeAdapter(User)
            >>> user = adapter.validate_tars(data)
            >>>
            >>> # 基础类型 (需要指定 Tag ID)
            >>> adapter = TarsTypeAdapter(list[int])
            >>> numbers = adapter.validate_tars(data, id=0)
        """
        parsed_dict = loads(data, option=Option(option))

        if self._is_struct:
            # Case A: 结构体 (Struct 或 StructDict)
            # 整个 dict 就是结构体的数据源 (Tag-Value 映射)
            value = parsed_dict
        else:
            # Case B: 基本类型或容器 (数据被包裹在单个 Tag 中)
            # 例如: List[int], Dict[int, str], int, str
            if id not in parsed_dict:
                raise ValueError(f"No data found at id {id}")
            value = parsed_dict[id]

        # 3. 使用 Pydantic TypeAdapter 进行转换
        # 优化: 如果 Rust 已经返回了正确的实例 (Struct/StructDict), 则跳过 Pydantic 验证
        if self._is_struct and type(value) is self._type:
            return cast(T, value)

        return self._pydantic_adapter.validate_python(value)

    def dump_tars(self, obj: T, *, option: Option = Option.NONE) -> bytes:
        """序列化为 Tarsio 数据.

        Args:
            obj: 要序列化的对象 (符合类型定义).
            option: JCE 选项.

        Returns:
            bytes: 序列化后的二进制数据.
        """
        # 直接调用 dumps, JceEncoder 会自动识别 StructDict vs dict
        return dumps(obj, option=Option(option))
