"""JCE 结构体定义模块."""

import re
import types as stdlib_types
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

from pydantic import AliasChoices, AliasPath, BaseModel, ValidationInfo, model_validator
from pydantic import Field as PydanticField
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined, core_schema
from typing_extensions import Self, dataclass_transform

from . import types
from .options import Option

S = TypeVar("S", bound="Struct")


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

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any):
        return core_schema.no_info_after_validator_function(
            cls,
            core_schema.dict_schema(
                keys_schema=core_schema.int_schema(),
                values_schema=core_schema.any_schema(),
            ),
        )


def Field(
    default: Any = PydanticUndefined,
    *,
    id: int,
    tars_type: type[types.Type] | None = None,
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

    这是一个 Pydantic `Field` 的包装函数，主要用于注入 Tarsio 协议序列化所需的
    元数据（如 `id`）。它必须用于 `Struct` 的每一个字段定义中。

    Args:
        default: 字段的静态默认值。
            如果未提供此参数且未提供 `default_factory`，则该字段在初始化时为**必填**。
        id: Tarsio 协议中的 Tag ID (必须 >= 0)。
            这是 Tarsio 序列化的核心标识，同一个结构体内的 ID 不能重复。
        tars_type: [可选] 显式指定 JCE 类型，用于覆盖默认的类型推断。
            *   指定 `types.INT1` 可强制将 int 编码为单字节。
            *   指定 `types.BYTES` 可强制将复杂对象（如 Struct/StructDict）**先序列化为二进制**再作为 SimpleList 存储 (Binary Blob 模式)。
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
        ValueError: 如果 `id` 小于 0。

    Examples:
        >>> from tarsio import Struct, Field, types
        >>> class User(Struct):
        ...     # 1. 必填字段 (Tag 0)
        ...     uid: int = Field(id=0)
        ...
        ...     # 2. 带默认值的字段 (Tag 1)
        ...     name: str = Field("Anonymous", id=1)
        ...
        ...     # 3. 列表字段，需使用 factory (Tag 2)
        ...     items: list[int] = Field(default_factory=list, id=2)
        ...
        ...     # 4. 显式指定 JCE 类型 (Tag 3)
        ...     # 即使是 int，也强制按 Byte (INT1) 编码
        ...     flags: int = Field(id=3, tars_type=types.INT1)
        ...
        ...     # 5. 使用 Pydantic 的验证参数 (Tag 4)
        ...     age: int = Field(id=4, gt=0, lt=150, description="Age")
    """
    if id < 0:
        raise ValueError(f"Invalid JCE ID: {id}")

    # 构造 JCE 元数据
    final_extra = {
        "id": id,
        "tars_type": tars_type,
    }

    # 合并显式传入的 json_schema_extra
    if json_schema_extra is not None:
        if isinstance(json_schema_extra, dict):
            final_extra.update(json_schema_extra)

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
    return cast(Any, PydanticField)(**kwargs_dict)


class ModelField:
    """表示一个 Struct 模型字段的元数据.

    存储了解析后的 JCE ID 和 JCE 类型信息。
    """

    __slots__ = ("id", "tars_type")

    def __init__(self, id: int, tars_type: type[types.Type] | Any):
        self.id = id
        self.tars_type = tars_type

    @classmethod
    def from_field_info(cls, field_info: FieldInfo, annotation: Any) -> Self:
        """从 FieldInfo 创建 ModelField."""
        extra = field_info.json_schema_extra or {}
        if callable(extra):
            extra = {}

        id: int | None = cast(int | None, extra.get("id"))
        tars_type: type[types.Type] | None = cast(
            type[types.Type] | None, extra.get("tars_type")
        )

        if id is None:
            raise ValueError("id is missing")

        # 如果未显式指定 tars_type，则尝试推断
        if tars_type is None:
            tars_type = cls._infer_tars_type_from_annotation(annotation)

            # 如果推断结果为 None，且注解不是 Any，说明遇到了不支持的类型
            if tars_type is None and annotation is not Any:
                origin = get_origin(annotation)
                if origin is Union or origin is stdlib_types.UnionType:
                    raise TypeError(f"Union type not supported: {annotation}")
                raise TypeError(f"Unsupported type for {annotation}")

        # 验证 tars_type (忽略 None/Any)
        if tars_type is not None:
            # 允许: JCE Type 子类 (包括 Struct) 或 显式指定的 JCE Type
            if not (isinstance(tars_type, type) and issubclass(tars_type, types.Type)):
                raise TypeError(f"Invalid tars_type: {tars_type}")

        return cls(cast(int, id), tars_type)

    @staticmethod
    def _infer_tars_type_from_annotation(
        annotation: Any,
    ) -> type[types.Type] | None:
        """从 Python 类型注解推断 JCE 类型.

        统一处理所有类型映射逻辑，包括泛型、基础类型和结构体。
        """
        # 1. 处理 Any (运行时推断)
        if annotation is Any:
            return None

        # 2. 处理 TypeVar (泛型视为 Bytes)
        if isinstance(annotation, TypeVar):
            return cast(type[types.Type], types.BYTES)

        # 3. 处理 Optional/Union (解包)
        origin = get_origin(annotation)
        args = get_args(annotation)

        if origin is Union or origin is stdlib_types.UnionType:
            non_none_args = [a for a in args if a is not type(None)]
            if len(non_none_args) == 1:
                return ModelField._infer_tars_type_from_annotation(non_none_args[0])
            return None  # 多重 Union 不支持

        # 4. 检查具体类映射
        is_class = isinstance(annotation, type)

        if is_class:
            # 基础类型映射
            if issubclass(annotation, (bool, int)):
                return types.INT
            if issubclass(annotation, float):
                return types.DOUBLE
            if issubclass(annotation, str):
                return types.STRING
            if issubclass(annotation, bytes):
                return types.BYTES

            # StructDict 特殊处理
            if issubclass(annotation, StructDict):
                return Struct

            # JCE 类型 (types.Type 子类)
            # 包括: Struct 子类, 以及显式标注的 types.INT1 等
            if issubclass(annotation, types.Type):
                return annotation

        # 5. 集合类型
        if origin is list or (is_class and issubclass(annotation, list)):
            return types.LIST
        if origin is dict or (is_class and issubclass(annotation, dict)):
            return types.MAP

        return None


def prepare_fields(fields: dict[str, FieldInfo]) -> dict[str, ModelField]:
    """准备 JCE 字段映射.

    遍历 Pydantic 的 fields，提取 JCE 元数据并验证完整性。
    """
    jce_fields = {}
    for name, field in fields.items():
        extra = field.json_schema_extra
        if isinstance(extra, dict) and "id" in extra:
            jce_fields[name] = ModelField.from_field_info(field, field.annotation)
        else:
            # 只有显式排除的字段才允许没有 JCE 配置
            is_excluded = field.exclude is True
            if not is_excluded:
                raise ValueError(
                    f"Field '{name}' is missing JCE configuration. "
                    f"Use Field(id=N) to configure it."
                )
    return dict(sorted(jce_fields.items(), key=lambda item: item[1].id))


@dataclass_transform(kw_only_default=True, field_specifiers=(Field,))
class StructMeta(type(BaseModel)):
    """Struct 的元类,用于收集 JCE 字段信息."""

    def __new__(  # noqa: D102
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ):
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)

        # 仅对用户定义的 Struct 子类执行 JCE 字段收集
        if name != "Struct":
            # 调用内部静态方法进行字段解析
            cls.__tars_fields__ = mcs._prepare_fields(cls.model_fields)

            # 预计算 Tag 到字段名的映射
            cls.__tars_tag_map__ = {
                f.id: field_name for field_name, f in cls.__tars_fields__.items()
            }

            # 收集自定义序列化器/反序列化器
            cls.__tars_serializers__ = {}
            for attr_name, attr_value in namespace.items():
                func = attr_value
                if isinstance(func, classmethod | staticmethod):
                    func = func.__func__

                target = getattr(func, "__tars_serializer_target__", None)
                if target:
                    cls.__tars_serializers__[target] = attr_name

        return cls

    @staticmethod
    def _prepare_fields(fields: dict[str, FieldInfo]) -> dict[str, ModelField]:
        """准备 JCE 字段映射 (Static Internal Helper).

        遍历 Pydantic 的 fields，提取 JCE 元数据并验证完整性。
        此方法是纯函数，不依赖类状态，因此定义为 staticmethod。
        """
        jce_fields = {}

        for name, info in fields.items():
            # 1. 优先检查是否被显式排除 (exclude=True)
            if info.exclude is True:
                continue

            # 2. 尝试提取 JCE 元数据
            try:
                # 复用 ModelField 的校验逻辑
                model_field = ModelField.from_field_info(info, info.annotation)
                jce_fields[name] = model_field

            except ValueError as e:
                # 3. 增强错误上下文
                if "id is missing" in str(e):
                    raise ValueError(
                        f"Field '{name}' is missing JCE configuration. "
                        f"Use Field(id=N) to configure it, or use Field(exclude=True) to ignore it."
                    ) from e
                raise

        # 4. 按 Tag ID 排序
        return dict(sorted(jce_fields.items(), key=lambda item: item[1].id))


class Struct(BaseModel, types.Type, metaclass=StructMeta):
    """JCE 结构体基类.

    继承自 `pydantic.BaseModel`，提供了声明式的 JCE 结构体定义方式。
    用户应通过继承此类，配合 `Field` 来定义协议结构。

    核心特性:
        1. **声明式定义**: 使用 Python 类型注解定义字段类型。
        2. **自动 Tag 管理**: 通过 `Field(id=...)` 绑定 Tarsio 协议的 Tag。
        3. **数据验证**: 利用 Pydantic 进行运行时数据校验。
        4. **序列化/反序列化**: 提供 `model_dump_tars()` 和 `model_validate_tars()` 方法。
        5. **泛型支持**: 支持 `Generic[T]` 定义通用结构体。

    Configuration:
        支持在 `model_config` 中配置以下 Tarsio 专用选项:

        - **tars_option** (*Option*): 全局 JCE 选项标志 (如 `Option.LITTLE_ENDIAN`).
        - **tars_omit_default** (*bool*): 是否在序列化时自动省略等于默认值的字段.

    Examples:
        **基础用法:**
        >>> from tarsio import Struct, Field
        >>> class User(Struct):
        ...     uid: int = Field(id=0)
        ...     name: str = Field(id=1)

        **嵌套结构体:**
        >>> class Group(Struct):
        ...     gid: int = Field(id=0)
        ...     owner: User = Field(id=1)  # 嵌套 User

        **序列化:**
        >>> user = User(uid=1001, name="Alice")
        >>> data = user.model_dump_tars()

        **反序列化:**
        >>> user_new = User.model_validate_tars(data)
        >>> assert user_new.name == "Alice"

    Note:
        所有字段必须通过 `Field` 显式指定 `id`，否则会抛出 ValueError (除非字段被标记为 excluded)。
    """

    __tars_fields__: ClassVar[dict[str, "ModelField"]] = {}
    __tars_tag_map__: ClassVar[dict[int, str]] = {}
    __tars_serializers__: ClassVar[dict[str, str]] = {}
    __core_schema_cache__: ClassVar[list[tuple] | None] = None

    def __bytes__(self) -> bytes:
        """支持 bytes(obj) 语法."""
        return self.model_dump_tars()

    @classmethod
    def __get_core_schema__(cls) -> list[tuple]:
        """获取用于 core (Rust) 的结构体 Schema.

        Returns:
            list[tuple]: Schema 列表, 每个元素为:
                (field_name, tag_id, tars_type_code, default_value, has_serializer)
        """
        if cls.__core_schema_cache__ is not None:
            return cls.__core_schema_cache__

        from . import types

        # (JCE Type Code 定义)
        type_map = {
            types.INT: 0,
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
            types.BYTES: 13,  # SimpleList (Blob)
        }

        schema = []
        for name, jce_info in cls.__tars_fields__.items():
            # 1. 提取基础信息
            tag = jce_info.id
            tars_type_cls = jce_info.tars_type

            # 2. 获取 Pydantic 字段信息 (仅用于获取默认值)
            # 注意：如果 __tars_fields__ 是在 prepare 时生成的，
            # 这里的顺序和 model_fields 是一致的。
            field_info = cls.model_fields[name]

            # 3. 确定类型码
            if isinstance(tars_type_cls, type) and issubclass(tars_type_cls, Struct):
                type_code = 10  # StructBegin
            elif tars_type_cls is None:
                type_code = 255  # 运行时推断 (Any)
            else:
                type_code = type_map.get(tars_type_cls, 0)

            # 4. 确定默认值 (用于 OMIT_DEFAULT)
            if (
                field_info.default_factory is not None
                or field_info.default is PydanticUndefined
            ):
                default_val = None
            else:
                default_val = field_info.default

            # 5. 检查自定义序列化器
            has_serializer = name in cls.__tars_serializers__

            # 6. 构建 Tuple
            schema.append(
                (
                    name,
                    tag,
                    type_code,
                    default_val,
                    has_serializer,
                )
            )

        cls.__core_schema_cache__ = schema
        return schema

    @model_validator(mode="before")
    @classmethod
    def _tars_pre_validate(cls, value: Any, info: ValidationInfo) -> Any:
        """验证前钩子: 负责 Bytes 解码和 Tag 映射.

        1. Bytes -> 调用 Rust 解码 -> Dict
        2. Tag Dict -> Python 循环映射 -> Name Dict (含 Blob 自动解包)
        3. Name Dict -> 直接放行
        """
        if isinstance(value, bytes | bytearray):
            try:
                from ._core import loads

                context = info.context or {}
                config = cls.model_config

                # 合并配置: 优先使用 context 中的 option，其次是 config 中的
                explicit_option = context.get("tars_option", Option.NONE)
                default_option = config.get("tars_option", Option.NONE)

                # Rust loads 返回的是标准字典 (Name-Keyed)，可以直接通过
                return loads(
                    bytes(value),
                    cls,
                    int(explicit_option | default_option),
                )
            except Exception as e:
                raise TypeError(
                    f"Failed to decode JCE bytes for {cls.__name__}: {e}"
                ) from e
        if isinstance(value, dict):
            if any(isinstance(k, int) for k in value):
                tag_map = cls.__tars_tag_map__
                new_value = {}

                for k, v in value.items():
                    if isinstance(k, int) and k in tag_map:
                        field_name = tag_map[k]
                        new_value[field_name] = v

                    else:
                        new_value[k] = v

                return new_value

        return value

    def model_dump_tars(
        self,
        option: Option = Option.NONE,
        context: dict[str, Any] | None = None,
        exclude_unset: bool = False,
    ) -> bytes:
        """序列化为 JCE 格式二进制数据.

        Args:
            option: JCE 序列化选项 (如 OMIT_DEFAULT, LITTLE_ENDIAN).
            context: 上下文传递给序列化器.
            exclude_unset: 是否排除未设置的字段

        Returns:
            bytes: JCE 二进制数据.
        """
        # 延迟导入以避免循环依赖
        from .api import dumps

        # 1. 准备配置
        config = self.model_config

        # 1. 基础 Option
        final_option = option | config.get("tars_option", Option.NONE)

        # 2. 处理 Omit Default
        if config.get("tars_omit_default", False):
            final_option |= Option.OMIT_DEFAULT

        # 3. 处理 Exclude Unset (新增修复)
        if exclude_unset:
            final_option |= Option.EXCLUDE_UNSET

        # 3. 调用 Rust 内核
        # 注意: self 已经是实例，dumps 会自动提取 __tars_compiled_schema__
        return dumps(
            self,
            option=final_option,
            context=context,
        )

    @classmethod
    def model_validate_tars(
        cls: type[S],
        data: bytes | bytearray | memoryview | dict[Any, Any],
        option: Option = Option.NONE,
        context: dict[str, Any] | None = None,
    ) -> S:
        """JCE 反序列化入口 (推荐使用).

        相比原生的 model_validate，此方法允许传递 JCE 特定的 option。

        Args:
            data: 输入数据 (bytes 或 dict).
            option: JCE 选项 (如 LITTLE_ENDIAN).
            context: 上下文.

        Returns:
            Struct 实例.
        """
        # 构建上下文，将 option 注入进去
        # _tars_pre_validate 会从 info.context 中读取 'tars_option'
        ctx = context.copy() if context else {}
        if option != Option.NONE:
            ctx["tars_option"] = option

        return cls.model_validate(data, context=ctx)
