"""JCE 结构体定义模块."""

import re
import types as stdlib_types
import warnings
from collections.abc import Callable
from typing import (
    Any,
    ClassVar,
    Literal,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
)

from pydantic import AliasChoices, AliasPath, BaseModel, Field, model_validator
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined, core_schema
from typing_extensions import Self, dataclass_transform

from .config import BytesMode
from .options import JceOption
from .types import (
    JceType,
)

S = TypeVar("S", bound="JceStruct")


class JceDict(dict[int, Any]):
    r"""JCE 结构体简写 (Anonymous Struct).

    这是一个 `dict` 的子类，用于显式标记数据应被编码为 JCE 结构体 (Struct)，而不是 JCE 映射 (Map)。
    在 JCE 协议中，Struct 和 Map 是两种完全不同的类型。

    行为区别:
        - `JceDict({0: 1})`: 编码为 JCE Struct。也就是一系列 Tag-Value 对，没有头部长度信息，通常更紧凑。
          要求键必须是 `int` (Tag ID)。
        - `dict({0: 1})`: 编码为 JCE Map (Type ID 8)。包含 Map 长度头，且键值对包含 Key Tag 和 Value Tag。

    约束:
        - 键 (Key): 必须是 `int` 类型，代表 JCE 的 Tag ID (0-255)。
        - 值 (Value): 可以是任意可序列化的 JCE 类型。

    Examples:
        >>> from jce import dumps, JceDict
        >>> # 编码为 Struct (Tag 0: 100) -> Hex: 00 64
        >>> dumps(JceDict({0: 100}))
        b'\x00d'

        >>> # 编码为 Map -> Hex: 08 01 00 64 ... (包含 Map 头信息)
        >>> dumps({0: 100})
        b'\x08\x01\x00d...'
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """初始化 JceDict 并验证所有键为 int 类型."""
        super().__init__(*args, **kwargs)
        for key in self.keys():
            if not isinstance(key, int):
                raise TypeError(
                    f"JceDict keys must be int (Tag ID), got {type(key).__name__}. "
                    f"Use regular dict for Map encoding."
                )

    def __setitem__(self, key: int, value: Any) -> None:
        """设置键值对时验证键为 int 类型."""
        if not isinstance(key, int):
            raise TypeError(
                f"JceDict keys must be int (Tag ID), got {type(key).__name__}. "
                f"Use regular dict for Map encoding."
            )
        super().__setitem__(key, value)

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any):
        return core_schema.no_info_after_validator_function(
            cls,
            core_schema.dict_schema(
                keys_schema=core_schema.int_schema(),
                values_schema=core_schema.any_schema(),
            ),
        )


def JceField(
    default: Any = PydanticUndefined,
    *,
    jce_id: int,
    jce_type: type[JceType] | None = None,
    default_factory: Callable[[], Any] | Callable[[dict[str, Any]], Any] | None = None,
    alias: str | None = None,
    alias_priority: int | None = None,
    validation_alias: str | AliasPath | AliasChoices | None = None,
    serialization_alias: str | None = None,
    title: str | None = None,
    field_title_generator: Callable[[str, FieldInfo], str] | None = None,
    description: str | None = None,
    examples: list[Any] | None = None,
    exclude: bool | None = None,
    exclude_if: Callable[[Any], bool] | None = None,
    discriminator: str | Any | None = None,
    deprecated: str | bool | None = None,
    json_schema_extra: dict[str, Any] | Callable[[dict[str, Any]], None] | None = None,
    frozen: bool | None = None,
    validate_default: bool | None = None,
    repr: bool | None = None,
    init: bool | None = None,
    init_var: bool | None = None,
    kw_only: bool | None = None,
    pattern: str | re.Pattern[str] | None = None,
    strict: bool | None = None,
    coerce_numbers_to_str: bool | None = None,
    gt: float | None = None,
    ge: float | None = None,
    lt: float | None = None,
    le: float | None = None,
    multiple_of: float | None = None,
    allow_inf_nan: bool | None = None,
    max_digits: int | None = None,
    decimal_places: int | None = None,
    min_length: int | None = None,
    max_length: int | None = None,
    union_mode: Literal["smart", "left_to_right"] | None = None,
    fail_fast: bool | None = None,
    **extra: Any,
) -> Any:
    """创建 JCE 结构体字段配置.

    这是一个 Pydantic `Field` 的包装函数，主要用于注入 JCE 协议序列化所需的
    元数据（如 `jce_id`）。它必须用于 `JceStruct` 的每一个字段定义中。

    Args:
        default: 字段的静态默认值。
            如果未提供此参数且未提供 `default_factory`，则该字段在初始化时为**必填**。
        jce_id: JCE 协议中的 Tag ID (必须 >= 0)。
            这是 JCE 序列化的核心标识，同一个结构体内的 ID 不能重复。
        jce_type: [可选] 显式指定 JCE 类型，用于覆盖默认的类型推断。
            *   指定 `types.INT1` 可强制将 int 编码为单字节。
            *   指定 `types.BYTES` 可强制将复杂对象（如 JceStruct/JceDict）**先序列化为二进制**再作为 SimpleList 存储 (Binary Blob 模式)。
        default_factory: 用于生成默认值的无参可调用对象。
            对于可变类型（如 `list`, `dict`），**必须**使用此参数而不是 `default`。
        alias: 字段别名 (Pydantic).
        alias_priority: 别名优先级 (Pydantic).
        validation_alias: 验证别名 (Pydantic).
        serialization_alias: 序列化别名 (Pydantic).
        title: 字段标题 (Pydantic).
        field_title_generator: 标题生成器 (Pydantic).
        description: 字段描述 (Pydantic).
        examples: 示例值 (Pydantic).
        exclude: 是否从序列化中排除 (Pydantic).
        exclude_if: 条件排除 (Pydantic).
        discriminator: 联合类型鉴别器 (Pydantic).
        deprecated: 废弃标记 (Pydantic).
        json_schema_extra: 额外的 JSON Schema 数据 (Pydantic).
        frozen: 是否冻结 (Pydantic).
        validate_default: 是否验证默认值 (Pydantic).
        repr: 是否包含在 repr 中 (Pydantic).
        init: 是否包含在 __init__ 中 (Pydantic).
        init_var: 是否作为 InitVar (Pydantic).
        kw_only: 是否仅限关键字参数 (Pydantic).
        pattern: 正则表达式模式 (Pydantic).
        strict: 严格模式 (Pydantic).
        coerce_numbers_to_str: 强制数字转字符串 (Pydantic).
        gt: Greater than (Pydantic).
        ge: Greater than or equal (Pydantic).
        lt: Less than (Pydantic).
        le: Less than or equal (Pydantic).
        multiple_of: 倍数 (Pydantic).
        allow_inf_nan: 允许 Inf/NaN (Pydantic).
        max_digits: 最大位数 (Pydantic).
        decimal_places: 小数位数 (Pydantic).
        min_length: 最小长度 (Pydantic).
        max_length: 最大长度 (Pydantic).
        union_mode: 联合模式 (Pydantic).
        fail_fast: 快速失败 (Pydantic).
        **extra: 传递给 Pydantic `Field` 的其他参数.

    Returns:
        Any: 包含 JCE 元数据的 Pydantic FieldInfo 对象。

    Raises:
        ValueError: 如果 `jce_id` 小于 0。

    Examples:
        >>> from jce import JceStruct, JceField, types
        >>> class User(JceStruct):
        ...     # 1. 必填字段 (Tag 0)
        ...     uid: int = JceField(jce_id=0)
        ...
        ...     # 2. 带默认值的字段 (Tag 1)
        ...     name: str = JceField("Anonymous", jce_id=1)
        ...
        ...     # 3. 列表字段，需使用 factory (Tag 2)
        ...     items: list[int] = JceField(default_factory=list, jce_id=2)
        ...
        ...     # 4. 显式指定 JCE 类型 (Tag 3)
        ...     # 即使是 int，也强制按 Byte (INT1) 编码
        ...     flags: int = JceField(jce_id=3, jce_type=types.INT1)
        ...
        ...     # 5. 使用 Pydantic 的验证参数 (Tag 4)
        ...     age: int = JceField(jce_id=4, gt=0, lt=150, description="Age")
    """
    if jce_id < 0:
        raise ValueError(f"Invalid JCE ID: {jce_id}")

    # 构造 JCE 元数据
    final_extra = {
        "jce_id": jce_id,
        "jce_type": jce_type,
    }

    # 合并显式传入的 json_schema_extra
    if json_schema_extra is not None:
        if isinstance(json_schema_extra, dict):
            final_extra.update(json_schema_extra)
        # 注意: 如果 json_schema_extra 是 callable, 当前 JceStruct 实现可能不支持提取 jce_id
        # JceModelField.from_field_info 会忽略 callable extra
        # 建议用户始终使用 dict 形式的 extra

    # 显式参数收集 (仅收集非 None 值)
    field_args = {
        "alias": alias,
        "alias_priority": alias_priority,
        "validation_alias": validation_alias,
        "serialization_alias": serialization_alias,
        "title": title,
        "field_title_generator": field_title_generator,
        "description": description,
        "examples": examples,
        "exclude": exclude,
        "exclude_if": exclude_if,
        "discriminator": discriminator,
        "deprecated": deprecated,
        "frozen": frozen,
        "validate_default": validate_default,
        "repr": repr,
        "init": init,
        "init_var": init_var,
        "kw_only": kw_only,
        "pattern": pattern,
        "strict": strict,
        "coerce_numbers_to_str": coerce_numbers_to_str,
        "gt": gt,
        "ge": ge,
        "lt": lt,
        "le": le,
        "multiple_of": multiple_of,
        "allow_inf_nan": allow_inf_nan,
        "max_digits": max_digits,
        "decimal_places": decimal_places,
        "min_length": min_length,
        "max_length": max_length,
        "union_mode": union_mode,
        "fail_fast": fail_fast,
    }

    # Cast extra to dict to allow assignment, bypassing Unpack[_EmptyKwargs] restriction
    kwargs_dict = cast(dict[str, Any], extra)

    # 将非 None 的显式参数合并到 kwargs
    for k, v in field_args.items():
        if v is not None:
            kwargs_dict[k] = v

    # 将合并后的 extra 放回 kwargs
    kwargs_dict["json_schema_extra"] = final_extra

    if default is not PydanticUndefined:
        kwargs_dict["default"] = default

    if default_factory is not None:
        kwargs_dict["default_factory"] = default_factory

    # cast call to Any to avoid type checking issues with Field return type
    return cast(Any, Field)(**kwargs_dict)


class JceModelField:
    """表示一个 JceStruct 模型字段的元数据.

    存储了解析后的 JCE ID 和 JCE 类型信息。
    """

    def __init__(self, jce_id: int, jce_type: type[JceType] | Any):
        """初始化 JCE 模型字段元数据.

        Args:
            jce_id: JCE Tag ID.
            jce_type: JCE 类型类.
        """
        self.jce_id = jce_id
        self.jce_type = jce_type

    @classmethod
    def from_field_info(cls, field_info: FieldInfo, annotation: Any) -> Self:
        """从 FieldInfo 创建 JceModelField.

        Args:
            field_info: Pydantic 字段信息.
            annotation: 字段类型注解.

        Returns:
            JceModelField: 创建的 JCE 字段元数据对象.
        """
        extra = field_info.json_schema_extra or {}
        if callable(extra):
            extra = {}

        # 直接获取,因为 JceField 保证了这些键存在
        jce_id = extra.get("jce_id")
        jce_type = extra.get("jce_type")

        if jce_id is None:
            raise ValueError("jce_id is missing")

        jce_id_int = cast(int, jce_id)
        jce_type_cls = cast(type[JceType], jce_type)

        if jce_type is None:
            jce_type_cls, inferred_struct = cls._infer_jce_type_from_annotation(
                annotation
            )

            # 如果推断出的是 JceStruct, jce_type_cls 会是 None, inferred_struct 会是 Struct 类
            if jce_type_cls is None and inferred_struct is not None:
                # Use the struct class itself as the type
                jce_type_cls = inferred_struct
            elif jce_type_cls is None:
                if annotation is Any:
                    # 如果是 Any, 允许不指定 jce_type, 编码时将使用运行时推断
                    return cls(jce_id_int, None)
                if isinstance(annotation, TypeVar):
                    from . import types

                    jce_type_cls = cast(type[JceType], types.BYTES)
                else:
                    # Check for Union types
                    origin = get_origin(annotation)
                    if origin is Union or origin is stdlib_types.UnionType:
                        raise TypeError(f"Union type not supported: {annotation}")
                    raise TypeError(f"Unsupported type for {annotation}")
        elif not (isinstance(jce_type_cls, type) and issubclass(jce_type_cls, JceType)):
            if not issubclass(jce_type_cls, JceType):
                raise TypeError(f"Invalid jce_type: {jce_type}")

        return cls(jce_id_int, jce_type_cls)

    @staticmethod
    def _infer_jce_type_from_annotation(
        annotation: Any,
    ) -> tuple[type[JceType] | None, Any]:
        """从 Python 类型注解推断 JCE 类型."""
        from typing import get_args, get_origin

        from . import types

        # 处理 Optional/Union
        origin = get_origin(annotation)
        args = get_args(annotation)

        if origin is Union or origin is stdlib_types.UnionType:
            # 移除 None,取第一个非 None 类型
            non_none_args = [a for a in args if a is not type(None)]
            if len(non_none_args) == 1:
                return JceModelField._infer_jce_type_from_annotation(non_none_args[0])
            # 多重 Union 不支持
            return None, None

        # 检查是否为类(避免对 GenericAlias 调用 issubclass)
        is_class = isinstance(annotation, type)

        # 基础类型映射
        if is_class:
            if issubclass(annotation, bool):
                return types.INT, None
            if issubclass(annotation, int):
                return types.INT, None
            if issubclass(annotation, float):
                return types.DOUBLE, None
            if issubclass(annotation, str):
                return types.STRING, None
            if issubclass(annotation, bytes):
                return types.BYTES, None
            if issubclass(annotation, JceStruct):
                return None, annotation  # Struct 本身
            if issubclass(annotation, JceDict):
                # JceDict 应该被视为匿名结构体 (Struct)
                return None, JceStruct

        # 处理 TypeVar (泛型)
        if isinstance(annotation, TypeVar):
            return cast(type[JceType], types.BYTES), None

        # 集合类型
        if origin is list or (is_class and issubclass(annotation, list)):
            return types.LIST, get_args(annotation)[0] if args else None
        if origin is dict or (is_class and issubclass(annotation, dict)):
            return types.MAP, get_args(annotation) if args else None

        # 处理显式标注的 JceType 子类
        if isinstance(annotation, type) and issubclass(annotation, JceType):
            return annotation, None

        return None, None


def prepare_fields(fields: dict[str, FieldInfo]) -> dict[str, JceModelField]:
    """准备 JCE 字段映射.

    遍历 Pydantic 的 fields，提取 JCE 元数据并验证完整性。
    """
    jce_fields = {}
    for name, field in fields.items():
        extra = field.json_schema_extra
        if isinstance(extra, dict) and "jce_id" in extra:
            jce_fields[name] = JceModelField.from_field_info(field, field.annotation)
        else:
            # 只有显式排除的字段才允许没有 JCE 配置
            is_excluded = field.exclude is True
            if not is_excluded:
                raise ValueError(
                    f"Field '{name}' is missing JCE configuration. "
                    f"Use JceField(jce_id=N) to configure it."
                )
    return dict(sorted(jce_fields.items(), key=lambda item: item[1].jce_id))


@dataclass_transform(kw_only_default=True, field_specifiers=(JceField,))
class JceStructMeta(type(BaseModel)):
    """JceStruct 的元类,用于收集 JCE 字段信息."""

    def __new__(  # noqa: D102
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ):
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        if name != "JceStruct":
            cls.__jce_fields__ = prepare_fields(cls.model_fields)

            # 收集自定义序列化器/反序列化器
            cls.__jce_serializers__ = {}
            for attr_name, attr_value in namespace.items():
                func = attr_value
                if isinstance(func, classmethod | staticmethod):
                    func = func.__func__

                target = getattr(func, "__jce_serializer_target__", None)
                if target:
                    cls.__jce_serializers__[target] = attr_name

        return cls


class JceStruct(BaseModel, JceType, metaclass=JceStructMeta):
    """JCE 结构体基类.

    继承自 `pydantic.BaseModel`，提供了声明式的 JCE 结构体定义方式。
    用户应通过继承此类，配合 `JceField` 来定义协议结构。

    核心特性:
        1. **声明式定义**: 使用 Python 类型注解定义字段类型。
        2. **自动 Tag 管理**: 通过 `JceField(jce_id=...)` 绑定 JCE 协议的 Tag。
        3. **数据验证**: 利用 Pydantic 进行运行时数据校验。
        4. **序列化/反序列化**: 提供 `model_dump_jce()` 和 `model_validate_jce()` 方法。
        5. **泛型支持**: 支持 `Generic[T]` 定义通用结构体。

    Examples:
        **基础用法:**
        >>> from jce import JceStruct, JceField
        >>> class User(JceStruct):
        ...     uid: int = JceField(jce_id=0)
        ...     name: str = JceField(jce_id=1)

        **嵌套结构体:**
        >>> class Group(JceStruct):
        ...     gid: int = JceField(jce_id=0)
        ...     owner: User = JceField(jce_id=1)  # 嵌套 User

        **序列化:**
        >>> user = User(uid=1001, name="Alice")
        >>> data = user.model_dump_jce()

        **反序列化:**
        >>> user_new = User.model_validate_jce(data)
        >>> assert user_new.name == "Alice"

    Note:
        所有字段必须通过 `JceField` 显式指定 `jce_id`，否则会抛出 ValueError (除非字段被标记为 excluded)。
    """

    __jce_fields__: ClassVar[dict[str, "JceModelField"]] = {}
    __jce_serializers__: ClassVar[dict[str, str]] = {}
    __jce_core_schema_cache__: ClassVar[list[tuple] | None] = None

    @classmethod
    def __get_jce_core_schema__(cls) -> list[tuple]:
        """获取用于 jce_core (Rust) 的结构体 Schema.

        Returns:
            list[tuple]: Schema 列表, 每个元素为:
                (field_name, tag_id, jce_type_code, default_value, has_serializer, has_deserializer)
        """
        if cls.__jce_core_schema_cache__ is not None:
            return cls.__jce_core_schema_cache__

        from . import types

        # 类型映射表: JceType 类 -> JCE 类型码
        type_map = {
            types.INT: 0,  # Int1 (Rust 会自动提升)
            types.INT8: 0,
            types.INT16: 1,
            types.INT32: 2,
            types.INT64: 3,
            types.FLOAT: 4,
            types.DOUBLE: 5,
            types.STRING: 6,
            types.STRING1: 6,
            types.STRING4: 7,
            types.MAP: 8,
            types.LIST: 9,
            types.BYTES: 13,  # SimpleList
        }

        schema = []
        for name, field_info in cls.model_fields.items():
            if name not in cls.__jce_fields__:
                continue

            jce_info = cls.__jce_fields__[name]
            tag = jce_info.jce_id
            jce_type_cls = jce_info.jce_type

            # 确定类型码
            if isinstance(jce_type_cls, type) and issubclass(jce_type_cls, JceStruct):
                type_code = 10  # StructBegin
            elif jce_type_cls is None:
                type_code = 255  # 运行时推断 (Any)
            else:
                type_code = type_map.get(jce_type_cls, 0)

            # 确定默认值
            if field_info.default_factory is not None:
                # 如果有 default_factory, 设置为 None, 避免 Rust 端错误地 OMIT_DEFAULT
                default_val = None
            elif field_info.default is PydanticUndefined:
                default_val = None
            else:
                default_val = field_info.default

            has_serializer = name in cls.__jce_serializers__

            schema.append(
                (
                    name,
                    tag,
                    type_code,
                    default_val,
                    has_serializer,
                )
            )

        cls.__jce_core_schema_cache__ = schema
        return schema

    @property
    def __jce_schema__(self) -> list[tuple]:
        """Rust 绑定兼容属性."""
        return self.__class__.__get_jce_core_schema__()

    def encode(
        self,
        option: JceOption = JceOption.NONE,
        context: dict[str, Any] | None = None,
        exclude_unset: bool = False,
    ) -> bytes:
        """序列化当前对象为 JCE 字节. (Deprecated).

        Deprecated:
            Use `model_dump_jce()` instead.
        """
        warnings.warn(
            "Use model_dump_jce() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.model_dump_jce(
            option=option, context=context, exclude_unset=exclude_unset
        )

    @classmethod
    def decode(
        cls: type[S],
        data: bytes | bytearray | memoryview,
        option: JceOption = JceOption.NONE,
        context: dict[str, Any] | None = None,
    ) -> S:
        """从字节反序列化为对象. (Deprecated).

        Deprecated:
            Use `model_validate_jce()` instead.
        """
        warnings.warn(
            "Use model_validate_jce() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        from .api import loads

        return loads(data, target=cls, option=option, context=context)

    @classmethod
    def from_bytes(
        cls, data: bytes | bytearray | memoryview
    ) -> tuple[dict[Any, Any], int]:
        """将 JCE 字节解析为标签字典和消耗的长度.

        此方法主要供内部使用或高级调试，通常用户应使用 `model_validate_jce`。

        Args:
            data: JCE 字节数据.

        Returns:
            tuple[dict[Any, Any], int]: (解析出的标签字典, 消耗的字节长度)
        """
        from .api import loads

        # 使用 loads 解析为 JceDict (Struct 语义)
        # 注意: loads 返回的是解析后的对象，不直接返回消耗的长度
        # 但为了保持兼容性，我们假设它消耗了全部数据
        result = loads(data, target=JceDict)
        return result, len(data)

    def model_dump_jce(
        self,
        option: JceOption = JceOption.NONE,
        context: dict[str, Any] | None = None,
        exclude_unset: bool = False,
    ) -> bytes:
        """序列化为 JCE 字节数据.

        Args:
            option: JCE 编码选项 (如字节序 `JceOption.LITTLE_ENDIAN`).
            context: 序列化上下文，可传递给自定义序列化器 (`@jce_field_serializer`).
            exclude_unset: 是否排除未设置的字段 (Pydantic 行为).
                如果为 True，只有在初始化时显式赋值的字段才会被序列化.

        Returns:
            bytes: 序列化后的二进制数据.
        """
        from .api import dumps

        # 1. 从 model_config 读取配置
        config = self.model_config
        default_option = config.get("jce_option", JceOption.NONE)
        omit_default = config.get("jce_omit_default", False)

        # 2. 合并 Option (参数 > model_config)
        # 注意: 参数传递的 option 通常应该能够覆盖 model_config，或者进行组合
        # 这里选择 OR 操作进行组合
        final_option = option | default_option

        # 3. 处理 omit_default
        if omit_default:
            final_option |= JceOption.OMIT_DEFAULT

        return dumps(
            self,
            option=final_option,
            context=context,
            exclude_unset=exclude_unset,
        )

    @classmethod
    def model_validate_jce(
        cls: type[S],
        data: bytes | bytearray | memoryview | JceDict,
        option: JceOption = JceOption.NONE,
        context: dict[str, Any] | None = None,
    ) -> S:
        """验证 JCE 数据并创建实例.

        支持从 二进制数据 (bytes) 或 JceDict (Tag 字典) 创建实例.
        注意：**不支持** 从普通 `dict` (如 `{0: xxx}`) 验证为 Struct，必须使用 `JceDict`。

        Args:
            data: 输入数据 (bytes 或者是预解析的 JceDict).
            option: JCE 选项 (如字节序).
            context: 验证上下文.

        Returns:
            S: 结构体实例.

        Raises:
            JceDecodeError: 字节数据解析失败.
            ValidationError: 数据结构不符合模型定义.
        """
        # 从 model_config 读取配置
        config = cls.model_config
        default_option = config.get("jce_option", JceOption.NONE)
        bytes_mode = cast(BytesMode, config.get("jce_bytes_mode", "auto"))

        final_option = option | default_option

        if isinstance(data, bytes | bytearray | memoryview):
            from .api import loads

            return loads(
                data,
                target=cls,
                option=final_option,
                context=context,
                bytes_mode=bytes_mode,
            )

        return cls.model_validate(data, context=context)

    @classmethod
    def _auto_unpack_bytes_field(
        cls, field_name: str, jce_info: "JceModelField", value: Any
    ) -> Any:
        """自动解包 JCE 实际类型为 bytes 但是类型注解不是 bytes 的字段."""
        if not isinstance(value, bytes | bytearray | memoryview):
            return value

        try:
            field_info = cls.model_fields[field_name]
            annotation = field_info.annotation
            origin = get_origin(annotation)

            if origin is Union or origin is stdlib_types.UnionType:
                args = get_args(annotation)
                non_none = [a for a in args if a is not type(None)]
                if len(non_none) == 1:
                    annotation = non_none[0]
                    origin = get_origin(annotation)

            from .api import loads

            if isinstance(annotation, type) and issubclass(annotation, JceStruct):
                val = loads(value, target=annotation)
                if isinstance(val, annotation):
                    return val
                return annotation.model_validate(val)

            # 显式 target=JceDict (API现在只支持JceDict作为通用容器)
            # 因为 JceDict 是 dict 的子类，所以如果 annotation 是 dict，这也可以工作
            if annotation is dict or origin is dict:
                # loads 默认返回 JceDict (其行为类似 Struct, 或者是包装后的普通dict)
                # 这对于 dict 类型的字段通常也是可接受的
                return loads(value)

            if annotation is list or origin is list:
                # loads 对于 JCE_LIST 类型数据会返回 list
                # 即使 target=JceDict，底层的 GenericDecoder 遇到 List 也会返回 List
                # (注意: 这里假设 loads/GenericDecoder 逻辑能够处理非 Struct 根节点)
                # 如果 GenericDecoder.decode() 强行返回 JceDict，那么这里需要小心
                # 但根据 decoder.py 的逻辑，如果它是 List，应该能被正确处理
                val = loads(value)

                # 处理 List 包装壳: {tag: [item...]}
                # 这种情况通常发生在其被解码为 Struct (JceDict) 时
                if isinstance(val, dict) and len(val) == 1:
                    tag = next(iter(val))
                    if tag == jce_info.jce_id:
                        return val[tag]
                return val

        except Exception as e:
            warnings.warn(f"Auto-unpack failed for {field_name}: {e}")
            pass

        return value

    @model_validator(mode="before")
    @classmethod
    def _jce_pre_validate(cls, value: Any) -> Any:
        """验证前钩子: 负责 Bytes 解码和 Tag 映射."""
        if isinstance(value, bytes | bytearray | memoryview):
            try:
                from .api import loads

                return loads(value, target=cls)
            except Exception as e:
                raise TypeError(f"Failed to decode JCE bytes: {e}") from e

        # 处理 dict 类型 (包括 JceDict 和由 Rust 返回的普通 dict)
        if isinstance(value, dict) and not isinstance(value, JceStruct):
            # 如果字典包含整数键, 说明它可能是一个 JCE 结构体数据 (Tag-Value 映射)
            # 我们检查是否存在任何在模型中定义的 Tag
            tag_map = {f.jce_id: name for name, f in cls.__jce_fields__.items()}

            # 判断是否需要进行 Tag -> Name 映射
            # 只要发现有一个整数键对应模型中的 Tag，我们就认为需要映射
            needs_mapping = any(
                isinstance(k, int) and k in tag_map for k in value.keys()
            )

            if needs_mapping:
                new_value: dict[Any, Any] = dict(value)
                for tag, val in list(value.items()):
                    if isinstance(tag, int) and tag in tag_map:
                        field_name = tag_map[tag]
                        jce_info = cls.__jce_fields__[field_name]

                        val = cls._auto_unpack_bytes_field(field_name, jce_info, val)
                        new_value[field_name] = val

                        # 移除原始 Tag 键 (除非 field_name 碰巧也是这个 tag, 这通常不会发生)
                        if str(field_name) != str(tag):
                            new_value.pop(tag, None)
                return new_value

        return value
