"""JCE 结构体定义模块."""

import copy
import keyword
import sys
from collections.abc import Callable
from typing import (
    Annotated,
    Any,
    ClassVar,
    Literal,
    TypeVar,
    final,
    get_args,
    get_origin,
    get_type_hints,
)

if sys.version_info >= (3, 11):
    from typing import Self, dataclass_transform
else:
    from typing_extensions import Self, dataclass_transform

from .types import TarsType

types = Literal[
    TarsType.BYTE,
    TarsType.SHORT,
    TarsType.INT,
    TarsType.LONG,
    TarsType.FLOAT,
    TarsType.DOUBLE,
    TarsType.STRING1,
    TarsType.STRING4,
    TarsType.MAP,
    TarsType.LIST,
    TarsType.STRUCT,
    TarsType.STRUCT_END,
    TarsType.ZERO_TAG,
    TarsType.SIMPLE_LIST,
]

S = TypeVar("S", bound="Struct")


@final
class UndefinedType:
    """表示未定义的默认值 (Sentinel Object).

    用于区分 '字段缺失' 和 '字段值为 None' 的情况。
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "Undefined"

    def __copy__(self) -> Self:
        """浅拷贝：直接返回单例本身."""
        return self

    def __deepcopy__(self, memo: Any) -> Self:
        """深拷贝：直接返回单例本身，忽略 memo."""
        return self

    def __reduce__(self) -> str:
        """支持 Pickle 序列化：确保反序列化后仍是同一个全局实例."""
        return "Undefined"

    def __bool__(self) -> bool:
        """使其在布尔上下文中为 False，类似 None."""
        return False


Undefined = UndefinedType()


class StructDict(dict[int, Any]):
    r"""JCE 结构体简写 (Anonymous Struct).

    这是一个 `dict` 的子类，用于显式标记数据应被编码为 JCE 结构体 (Struct)，而不是 JCE 映射 (Map)。
    在 Tarsio 协议中，Struct 和 Map 是两种完全不同的类型。

    行为区别:
        - `StructDict({0: 1})`: 编码为 JCE Struct。也就是一系列 Tag-Value 对，没有头部长度信息，通常更紧凑。
          要求键必须是 `int` (Tag ID)。
        - `dict({0: 1})`: 编码为 JCE Map (Type ID 8)。包含 Map 长度头，且键值对包含 Key Tag 和 Value Tag。

    约束:
        - 键 (Key): 必须是 `int` 类型，代表 JCE 的 Tag ID (0-255)。
        - 值 (Value): 可以是任意可序列化的 JCE 类型。


    Examples:
        >>> from tarsio import dumps, StructDict
        >>> # 编码为 Struct (Tag 0: 100) -> Hex: 00 64
        >>> dumps(StructDict({0: 100}))
        b'\x00d'

        >>> # 编码为 Map -> Hex: 08 01 00 64 ... (包含 Map 头信息)
        >>> dumps({0: 100})
        b'\x08\x01\x00d...'
    """


class FieldInfo:
    """统一的元数据容器.

    包含了 JCE Tag、默认值、默认工厂以及所有的校验参数。
    Rust 内核将直接读取此对象的属性来生成 CompiledSchema。
    """

    __slots__ = (
        "default",
        "default_factory",
        "ge",
        "gt",
        "le",
        "lt",
        "max_len",
        "min_len",
        "tag",
        "tars_type",
    )

    def __init__(
        self,
        tag: int | None = None,
        tars_type: Any | None = None,
        default: Any = Undefined,
        default_factory: Callable[[], Any] | None = None,
        *,
        gt: float | None = None,
        lt: float | None = None,
        ge: float | None = None,
        le: float | None = None,
        min_len: int | None = None,
        max_len: int | None = None,
    ):
        self.tag = tag
        self.tars_type = tars_type
        self.default = default
        self.default_factory = default_factory
        # 校验参数
        self.gt = gt
        self.lt = lt
        self.ge = ge
        self.le = le
        self.min_len = min_len
        self.max_len = max_len


def Field(
    default: Any = Undefined,
    id: int | None = None,
    tars_type: types | None = None,
    *,
    default_factory: Callable[[], Any] | None = None,
    gt: float | None = None,
    lt: float | None = None,
    ge: float | None = None,
    le: float | None = None,
    min_len: int | None = None,
    max_len: int | None = None,
) -> Any:
    """创建 JCE 结构体字段的配置元数据.

    此函数用于定义 `tarsio.Struct` 子类中的字段属性。它可以指定字段的 JCE Tag ID、
    默认值以及特定的 JCE 类型映射。

    通常与 Python 的类型注解配合使用，既可以直接赋值给字段，也可以作为 `Annotated` 的元数据使用。

    Args:
        default (Any, optional): 字段的默认值。
            如果字段在反序列化过程中缺失，将使用此值。
            如果未提供且字段非 Optional，反序列化缺失字段时可能会报错。
            默认为 `UndefinedType` (表示无默认值)。
        id (int | None, optional): JCE 协议中的 Tag ID (0-255)。
            这是 JCE 二进制流中标识字段的关键索引。
            如果为 `None`，Tarsio 将根据字段定义的顺序自动分配 ID。
            **强烈建议在生产环境显式指定此值以保证协议兼容性。**
        tars_type (type[types.Type] | None, optional): 显式指定 JCE 底层类型。
            通常情况下 Tarsio 会根据 Python 类型注解自动推断 (例如 `int` -> `JCE_INT`)。
            仅在需要强制指定特殊类型（如强制使用 `short` 而非 `int`）时使用。
        default_factory (Callable[[], Any] | None, optional): 默认值工厂函数。
            用于动态生成默认值（如 `list`），与 `default` 互斥。
        gt (float | None, optional): 数值验证，大于 (`>`)。
        lt (float | None, optional): 数值验证，小于 (`<`)。
        ge (float | None, optional): 数值验证，大于等于 (`>=`)。
        le (float | None, optional): 数值验证，小于等于 (`<=`)。
        min_len (int | None, optional): 长度验证，最小长度。
        max_len (int | None, optional): 长度验证，最大长度。


    Returns:
        Any: 返回一个 `FieldInfo` 实例，包含了字段的所有元数据配置。
             (在类型检查器中，它表现为 `Any` 以避免赋值类型报错)

    Raises:
        ValueError: 当提供的 `id` 小于 0 时抛出。

    Examples:
        **基础用法 (显式 ID):**
        ```python
        class User(Struct):
            # 定义 Tag 为 0 的字段，无默认值
            uid: int = Field(id=0)

            # 定义 Tag 为 1 的字段，默认值为 "Unknown"
            name: str = Field("Unknown", id=1)
        ```

        **自动分配 ID (仅限原型开发):**
        ```python
        class Simple(Struct):
            # 自动分配 Tag 0
            x: int
            # 自动分配 Tag 1
            y: int
        ```

        **配合 Annotated 使用 (推荐):**
        ```python
        from typing import Annotated


        class Product(Struct):
            # 将配置元数据放入类型注解中
            price: Annotated[int, Field(id=2)]
        ```
    """
    if id is not None and id < 0:
        raise ValueError(f"Invalid JCE ID: {id}")
    return FieldInfo(
        tag=id,
        default=default,
        tars_type=tars_type,
        default_factory=default_factory,
        gt=gt,
        lt=lt,
        ge=ge,
        le=le,
        min_len=min_len,
        max_len=max_len,
    )


@dataclass_transform(field_specifiers=(Field,))
class Struct:
    """JCE 结构体基类.

    所有 JCE 结构体均应继承自该类。
    """

    __slots__ = ()
    __tars_schema__: ClassVar[list[tuple[str, FieldInfo, type]]]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._compile_schema()
        cls._generate_init()

    @classmethod
    def _compile_schema(cls):
        schema = []
        hints = get_type_hints(cls, include_extras=True)

        next_auto_tag = 0

        for name, annotation in hints.items():
            if name.startswith("_"):
                continue

            # --- 解析逻辑---
            field_info = None
            real_type = annotation

            # 1. 检查赋值 (name: int = Field(...))
            value_on_class = getattr(cls, name, ...)
            if isinstance(value_on_class, FieldInfo):
                field_info = value_on_class

            # 2. 检查 Annotated (name: Annotated[int, Field(...)])
            if get_origin(annotation) is Annotated:
                args = get_args(annotation)
                real_type = args[0]
                for meta in args[1:]:
                    if isinstance(meta, FieldInfo):
                        field_info = meta
                        break

            # 如果前面都没找到 FieldInfo，但这不是一个普通的 ClassVar
            if field_info is None:
                # 如果有默认值 (name: int = 1)，创建一个带默认值的 FieldInfo
                if value_on_class is not ...:
                    field_info = FieldInfo(tag=None, default=value_on_class)
                else:
                    # 纯类型定义 (name: int)，创建一个空的 FieldInfo
                    field_info = FieldInfo(tag=None, default=Undefined)

            final_info = copy.copy(field_info)

            if final_info.tag is None:
                final_info.tag = next_auto_tag

            # 更新计数器
            next_auto_tag = final_info.tag + 1

            schema.append((name, final_info, real_type))

        # 依然按 Tag 排序，确保 Rust 读取顺序正确
        schema.sort(key=lambda x: x[1].tag)
        cls.__tars_schema__ = schema

    @classmethod
    def __get_core_schema__(cls):
        """返回用于 Rust 核心编译的 Schema 列表."""
        return cls.__tars_schema__

    @classmethod
    def _generate_init(cls):
        schema = cls.__tars_schema__

        # 1. 准备参数容器
        args_required = []
        args_optional = []

        # 2. 准备执行上下文 (Local Namespace)
        namespace = {}

        # 3. 准备函数体代码
        body_lines = []

        existing_fields = set()

        for name, field_info, _ in schema:
            existing_fields.add(name)
            if not name.isidentifier():
                raise ValueError(
                    f"Unsafe field name: '{name}'. Must be a valid Python identifier."
                )

            if keyword.iskeyword(name):
                raise ValueError(
                    f"Unsafe field name: '{name}'. Cannot use Python keywords."
                )
            body_lines.append(f"self.{name} = {name}")

            if field_info.default is Undefined:
                # Case 1: 必填参数
                args_required.append(name)
            elif field_info.default_factory is not None:
                injection_key = f"__tars_default_fac_{name}"
                namespace[injection_key] = field_info.default_factory
                # 使用 Undefined 作为哨兵
                k_undef = "__Undefined"
                namespace[k_undef] = Undefined
                args_optional.append(f"{name}={k_undef}")
                body_lines.pop()
                body_lines.append(
                    f"self.{name} = {injection_key}() if {name} is {k_undef} else {name}"
                )
            else:
                injection_key = f"__tars_default_{name}"

                if injection_key in existing_fields:
                    raise ValueError(
                        f"Field name '{name}' causes an internal naming conflict. "
                        f"Please rename it."
                    )
                namespace[injection_key] = field_info.default
                args_optional.append(f"{name}={injection_key}")
        # 4. 组装代码
        all_args = args_required + args_optional
        args_str = ", ".join(all_args)
        if not body_lines:
            body_lines = ["pass"]
        if hasattr(cls, "__post_init__"):
            body_lines.append("self.__post_init__()")
        # 5. 编译与挂载
        code_str = f"def __init__(self, {args_str}):\n    " + "\n    ".join(body_lines)
        exec(code_str, {}, namespace)
        init_func = namespace["__init__"]
        init_func.__qualname__ = f"{cls.__name__}.__init__"
        cls.__init__ = init_func
