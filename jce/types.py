"""JCE数据类型模块.

本模块定义了JCE协议支持的所有数据类型,包括基本类型(INT、STRING等)
和复杂类型(LIST、MAP、STRUCT等)。每个类型都实现了序列化和反序列化
接口,用于JCE二进制数据的编码和解码。
"""
import abc
import struct
import warnings
from collections.abc import Iterable, Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    TypeVar,
    Union,
    cast,
    get_origin,
)

from pydantic import BaseModel, Field, GetCoreSchemaHandler, model_validator
from pydantic._internal._model_construction import ModelMetaclass
from pydantic.fields import FieldInfo
from pydantic_core import CoreSchema, PydanticUndefined, core_schema

T = TypeVar("T", bound="JceType")
VT = TypeVar("VT", bound="JceType")
S = TypeVar("S", bound="JceStruct")
T_INT = TypeVar("T_INT", bound="INT")
T_STRING = TypeVar("T_STRING", bound="STRING")


class _empty_meta(type):
    def __bool__(cls):
        return False


class _empty(metaclass=_empty_meta):
    pass


def JceField(
    default: Any = PydanticUndefined,
    *,
    jce_id: int,
    jce_type: type["JceType"] | None = None,
    default_factory: Any | None = None,
    alias: str | None = None,
    title: str | None = None,
    description: str | None = None,
    const: bool | None = None,
    gt: float | None = None,
    ge: float | None = None,
    lt: float | None = None,
    le: float | None = None,
    multiple_of: float | None = None,
    min_length: int | None = None,
    max_length: int | None = None,
    pattern: str | None = None,
    **extra: Any,
) -> Any:
    """为JceStruct字段创建一个Pydantic Field配置.

    此函数返回一个Pydantic Field实例,并通过json_schema_extra
    将JCE特定的元数据(jce_id和jce_type)附加到字段中.

    Args:
        default: 字段的默认值. 如果未提供,则为PydanticUndefined.
        jce_id: JCE协议中的字段标识符(0-15或更高).
        jce_type: 该字段的JCE类型(例如LIST、MAP、STRING). 如果为None,将从类型注解推断.
        default_factory: 用于生成默认值的可调用对象.
        alias: 该字段在JSON序列化中的替代名称.
        title: 字段的标题.
        description: 字段的描述.
        const: 字段的常量值(将放入json_schema_extra).
        gt: 大于约束(仅适用于数值).
        ge: 大于等于约束(仅适用于数值).
        lt: 小于约束(仅适用于数值).
        le: 小于等于约束(仅适用于数值).
        multiple_of: 倍数约束(仅适用于数值).
        min_length: 最小长度约束(仅适用于字符串/集合).
        max_length: 最大长度约束(仅适用于字符串/集合).
        pattern: 正则表达式模式约束(仅适用于字符串).
        **extra: 传递给Pydantic Field()的额外关键字参数.

    Returns:
        Pydantic FieldInfo实例,包含jce_id和jce_type在json_schema_extra中.

    Raises:
        ValueError: 如果jce_id为负数.
        TypeError: 如果jce_type不是JceType的子类.

    Examples:
        >>> class MyStruct(JceStruct):
        ...     name: str = JceField(jce_id=0, default="")
        ...     count: int = JceField(jce_id=1, jce_type=INT, default=0)
        ...     items: list = JceField(jce_id=2, jce_type=LIST, default_factory=list)
    """
    if jce_id < 0:
        raise ValueError(f"Invalid JCE ID: {jce_id}")

    if jce_type is not None:
        if not issubclass(cast(type, cast(Any, jce_type)), JceType):
            raise TypeError(f"Invalid JCE type: {jce_type}")

    json_schema_extra = extra.pop("json_schema_extra", {})
    if not isinstance(json_schema_extra, dict):
        json_schema_extra = {}
    json_schema_extra.update({"jce_id": jce_id, "jce_type": jce_type})

    # 如果提供了const,则添加到json_schema_extra
    if const is not None:
        json_schema_extra["const"] = const

    # 构建Field kwargs - 仅包括非None的约束值
    field_kwargs = {
        "default": default,
        "default_factory": default_factory,
        "alias": alias,
        "title": title,
        "description": description,
        "json_schema_extra": json_schema_extra,
    }

    # 如果提供了数值约束,添加它们
    if gt is not None:
        field_kwargs["gt"] = gt
    if ge is not None:
        field_kwargs["ge"] = ge
    if lt is not None:
        field_kwargs["lt"] = lt
    if le is not None:
        field_kwargs["le"] = le
    if multiple_of is not None:
        field_kwargs["multiple_of"] = multiple_of

    # 如果提供了字符串/集合约束,添加它们
    if min_length is not None:
        field_kwargs["min_length"] = min_length
    if max_length is not None:
        field_kwargs["max_length"] = max_length
    if pattern is not None:
        field_kwargs["pattern"] = pattern

    # 合并额外的kwargs
    field_kwargs.update(cast(dict[str, Any], extra))

    return Field(**field_kwargs)


class JceModelField:
    """表示一个JceStruct模型字段的元数据.

    此类存储JCE字段的基本信息,包括其标识符和类型.
    它用于在模型元类中注册和验证字段.

    Attributes:
        jce_id: JCE协议中的字段标识符.
        jce_type: 字段的JCE数据类型(必须是JceType的子类).

    Raises:
        NotJceModelField: 在from_field_info中,当字段不是有效的JCE字段时抛出.
    """

    class NotJceModelField(Exception):
        """表示该字段不是JceStruct字段的异常."""

        pass

    def __init__(self, jce_id: int, jce_type: type["JceType"]):
        """初始化JceModelField实例.

        Args:
            jce_id: JCE字段的数值标识符(必须非负).
            jce_type: 字段的JCE类型(必须是JceType的子类).

        Raises:
            ValueError: 如果jce_id不是非负整数或jce_type不是JceType的子类.
        """
        if not isinstance(jce_id, int) or jce_id < 0:
            raise ValueError("Invalid JCE ID")
        # JceType在这里是不完整的类型?
        # 使用简单的验证
        if not issubclass(cast(type, cast(Any, jce_type)), JceType):
            raise ValueError("Invalid JCE Type")
        self.jce_id: int = jce_id
        self.jce_type: type[JceType] = jce_type

    def __str__(self) -> str:
        return f"<JceModelField id:{self.jce_id} type:{self.jce_type}>"

    @classmethod
    def from_field_info(
        cls, field_info: FieldInfo, annotation: Any
    ) -> "JceModelField":
        """从Pydantic FieldInfo创建JceModelField实例.

        此方法提取json_schema_extra中存储的jce_id和jce_type信息,
        并创建一个JceModelField实例来表示JCE字段元数据.

        Args:
            field_info: 来自Pydantic的FieldInfo实例.
            annotation: 字段的类型注解.

        Returns:
            包含从field_info中提取的jce_id和jce_type的JceModelField实例.

        Raises:
            NotJceModelField: 如果jce_id缺失或jce_type不是有效的JceType.
        """
        extra = field_info.json_schema_extra or {}
        if not isinstance(extra, dict):
            extra = {}
        jce_id = cast(int | None, extra.get("jce_id"))
        jce_type = extra.get("jce_type")

        # 如果没有显式指定jce_type,尝试从注解推断
        if jce_type is None:
            jce_type = cls._infer_jce_type_from_annotation(annotation)

        if jce_id is None or not (
            isinstance(jce_type, type) and issubclass(jce_type, JceType)
        ):
            raise cls.NotJceModelField
        return cls(jce_id, jce_type)

    @staticmethod
    def _infer_jce_type_from_annotation(
        annotation: Any,
    ) -> type["JceType"] | None:
        """从类型注解推断JceType.

        Args:
            annotation: 字段的类型注解.

        Returns:
            推断出的JceType子类,如果无法推断则返回None.
        """
        import sys

        # 获取当前模块,这样可以访问后面定义的类
        current_module = sys.modules[__name__]

        origin = get_origin(annotation)

        is_union = origin is Union
        if not is_union and sys.version_info >= (3, 10):
            import types

            is_union = origin is types.UnionType

        if is_union:
            non_none_args = [
                arg
                for arg in getattr(annotation, "__args__", ())
                if arg is not type(None)
            ]
            if len(non_none_args) == 1:
                annotation = non_none_args[0]
                origin = get_origin(annotation)

        # 检查是否已经是JceType子类
        try:
            if isinstance(annotation, type) and issubclass(annotation, JceType):
                return annotation
        except (TypeError, NameError):
            pass

        # 处理泛型类型(如list[X])
        if origin is not None:
            if isinstance(origin, type) and issubclass(
                cast(type, origin), JceType
            ):
                return cast(type["JceType"], origin)
            if origin is list:
                return getattr(current_module, "LIST", None)  # type: ignore
            elif origin is dict:
                return getattr(current_module, "MAP", None)  # type: ignore

        # 基本类型映射
        type_names = {
            int: "INT",
            str: "STRING",
            float: "DOUBLE",
            bool: "BOOL",
            bytes: "BYTES",
        }

        if annotation in type_names:
            return getattr(current_module, type_names[annotation], None)  # type: ignore

        return None


def prepare_fields(fields: dict[str, FieldInfo]) -> dict[str, JceModelField]:
    """从Pydantic模型字段字典准备JCE字段映射.

    该函数遍历Pydantic FieldInfo字典,为每个字段调用
    JceModelField.from_field_info()以提取JCE元数据.
    无法识别的字段会被跳过,验证错误会被记录为警告.

    Args:
        fields: Pydantic模型字段的字典,其中键是字段名称,
                值是FieldInfo实例.

    Returns:
        JceModelField实例的有序字典,按jce_id排序.
        跳过了非JCE字段.
    """
    jce_fields: dict[str, JceModelField] = {}
    parse_errors = []
    for name, field in fields.items():
        try:
            jce_fields[name] = JceModelField.from_field_info(
                field, field.annotation
            )
        except JceModelField.NotJceModelField:
            # 跳过非JCE字段
            continue
        except ValueError as e:
            # 记录解析错误,稍后处理
            parse_errors.append((name, e))

    for name, error in parse_errors:
        warnings.warn(f"Error when parsing JCE field `{name}`: {error!r}")

    return dict(sorted(jce_fields.items(), key=lambda item: item[1].jce_id))


class JceType(abc.ABC):
    """JCE数据类型的抽象基类.

    所有JCE支持的类型(如INT、STRING、LIST等)都应继承此类.
    它定义了序列化和反序列化JCE数据的接口.

    Subclasses must implement:
        to_bytes: 将值编码为JCE二进制格式.
        from_bytes: 从JCE二进制格式解码值.
        validate: 验证和转换输入值为该类型.
    """

    @classmethod
    def head_byte(cls, jce_id: int, jce_type: int) -> bytes:
        """生成JCE头字节."""
        if jce_id < 15:
            return bytes([jce_id << 4 | jce_type])
        else:
            return bytes([0xF0 | jce_type, jce_id])

    @classmethod
    @abc.abstractmethod
    def to_bytes(cls, jce_id: int, value: Any) -> bytes:
        """将值编码为JCE二进制格式."""
        raise NotImplementedError

    @classmethod
    @abc.abstractmethod
    def from_bytes(cls, data: bytes, **extra: Any) -> tuple[Any, int]:
        """从JCE二进制格式解码值."""
        raise NotImplementedError

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        """获取Pydantic核心模式."""
        origin = get_origin(source_type)
        if origin is None:
            return core_schema.no_info_plain_validator_function(cls.validate)

        args = getattr(source_type, "__args__", ())
        if args and args[0] is not Any:
            items_schema = handler(args[0])
            return core_schema.chain_schema([
                core_schema.list_schema(items_schema=items_schema),
                core_schema.no_info_plain_validator_function(
                    cls.validate_after_pydantic
                ),
            ])

        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate_after_pydantic(cls, v):
        """Pydantic验证后的处理."""
        new_instance = cls()
        for item in v:
            if isinstance(item, JceType):
                # 确保new_instance支持append(它应该是LIST)
                if isinstance(new_instance, list):
                    new_instance.append(item)
            else:
                try:
                    item_type = guess_jce_type(item)
                    item = item_type(item)  # type: ignore
                except TypeError:
                    pass
                if isinstance(new_instance, list):
                    new_instance.append(item)
        return new_instance

    @classmethod
    def validate(cls: type[T], value: Any) -> T:
        """验证和转换输入值."""
        return value


class BYTE(JceType, bytes):
    """JCE字节类型,表示单个字节值.

    该类继承自bytes,用于在JCE协议中编码和解码单个字节值.
    BYTE值在JCE格式中具有类型代码0.

    Attributes:
        __jce_type__: 元组(0,),指定JCE类型代码.
    """

    __jce_type__ = (0,)

    @classmethod
    def to_bytes(cls, jce_id: int, value: bytes) -> bytes:
        """将字节值编码为JCE格式."""
        if len(value) != 1:
            raise ValueError(f"Invalid byte value: {value!r}")
        if value == b"\x00":
            return ZERO_TAG.to_bytes(jce_id, None)
        return cls.head_byte(jce_id, cls.__jce_type__[0]) + value

    @classmethod
    def from_bytes(cls, data: bytes, **extra: Any) -> tuple[bytes, int]:
        """从JCE格式解码字节值."""
        return struct.unpack_from(">c", data)[0], 1

    @classmethod
    def validate(cls, value: Any) -> "BYTE":
        """验证值并返回JceType实例.

        Args:
            value: 要验证的值.

        Returns:
            JceType实例.
        """
        if isinstance(value, cls):
            return value
        # raise NotImplementedError(f"{cls.__name__} must implement validate")
        return cast("BYTE", value)  # 应该由子类实现


class BOOL(JceType, int):
    """JCE布尔类型,表示真假值.

    该类继承自int,用于在JCE协议中编码和解码布尔值.
    内部表示为0(假)或1(真).

    Attributes:
        __jce_type__: 元组(0,),指定JCE类型代码.

    Note:
        BOOL值在JCE中实际编码为单个字节,0表示False,非0表示True.
    """

    __jce_type__ = (0,)

    def __new__(cls, value: Any = None) -> "BOOL":
        """创建布尔JCE类型实例."""
        return super().__new__(cls, bool(value))

    def __str__(self) -> str:
        return "True" if self else "False"

    __repr__ = __str__

    @classmethod
    def to_bytes(cls, jce_id: int, value: bool) -> bytes:  # type: ignore[override]
        """将布尔值编码为JCE格式."""
        return BYTE.to_bytes(jce_id, bytes([value]))

    @classmethod
    def from_bytes(cls, data: bytes, **extra: Any) -> tuple[bool, int]:  # type: ignore[override]
        """从JCE格式解码布尔值."""
        return struct.unpack_from(">?", data)[0], 1

    @classmethod
    def validate(cls, value: Any) -> "BOOL":
        """验证和转换布尔值."""
        if isinstance(value, bytes):
            if len(value) != 1:
                raise ValueError(f"Invalid byte length: {len(value)}")
            value, _ = cls.from_bytes(value)
        elif not isinstance(value, int):
            raise TypeError(f"Invalid value type: {type(value)}")
        return cls(value)


class INT(JceType, int):
    """JCE整数类型,支持多种整数大小.

    该类继承自int,根据值范围自动选择最佳编码格式.
    - 范围 [-128, 127]: 1字节编码
    - 范围 [-32768, 32767]: 2字节编码
    - 范围 [-2147483648, 2147483647]: 4字节编码
    - 其他: 8字节编码

    Attributes:
        __jce_type__: 元组(1, 2, 3),指定可能的JCE类型代码.

    Note:
        子类INT8, INT16, INT32, INT64分别用于固定大小的整数.
    """

    __jce_type__ = (1, 2, 3)

    @classmethod
    def to_bytes(cls, jce_id: int, value: int) -> bytes:  # type: ignore[override]
        """将整数值编码为JCE格式."""
        if -128 <= value <= 127:
            return BYTE.to_bytes(jce_id, struct.pack(">b", value))
        elif -32768 <= value <= 32767:
            return cls.head_byte(jce_id, cls.__jce_type__[0]) + struct.pack(
                ">h", value
            )
        elif -2147483648 <= value <= 2147483647:
            return cls.head_byte(jce_id, cls.__jce_type__[1]) + struct.pack(
                ">i", value
            )
        return cls.head_byte(jce_id, cls.__jce_type__[2]) + struct.pack(
            ">q", value
        )

    @classmethod
    def from_bytes(cls, data: bytes, **extra: Any) -> tuple[int, int]:  # type: ignore[override]
        """从JCE格式解码整数值."""
        raise NotImplementedError

    @classmethod
    def validate(cls: type[T_INT], value: Any) -> T_INT:
        """验证和转换整数值."""
        if isinstance(value, bytes):
            length = len(value)
            if length == 1:
                value, _ = INT8.from_bytes(value)
            elif length == 2:
                value, _ = INT16.from_bytes(value)
            elif length == 4:
                value, _ = INT32.from_bytes(value)
            elif length == 8:
                value, _ = INT64.from_bytes(value)
            else:
                raise ValueError(
                    f"Invalid value length: {value!r}(length {8 * length})"
                )
        elif not isinstance(value, int):
            raise TypeError(f"Invalid value type: {type(value)}")
        return cls(value)


class INT8(INT):
    """8位有符号整数类型(-128 ~ 127).

    用于编码一个字节的整数值.
    每个值仅占1字节空间.
    """

    @classmethod
    def from_bytes(cls, data: bytes, **extra: Any) -> tuple[int, int]:  # type: ignore[override]
        """从JCE格式解码8位整数."""
        return struct.unpack_from(">b", data)[0], 1


class INT16(INT):
    """16位有符号整数类型(-32768 ~ 32767).

    用于编码一个字的整数值.
    每个值仅占2字节空间.
    """

    @classmethod
    def from_bytes(cls, data: bytes, **extra: Any) -> tuple[int, int]:  # type: ignore[override]
        """从JCE格式解码16位整数."""
        return struct.unpack_from(">h", data)[0], 2


class INT32(INT):
    """32位有符号整数类型(-2147483648 ~ 2147483647).

    用于编码一个双字的整数值.
    每个值仅占4字节空间.
    """

    @classmethod
    def from_bytes(cls, data: bytes, **extra: Any) -> tuple[int, int]:  # type: ignore[override]
        """从JCE格式解码32位整数."""
        return struct.unpack_from(">i", data)[0], 4


class INT64(INT):
    """64位有符号整数类型(-9223372036854775808 ~ 9223372036854775807).

    用于编码一个四字的整数值.
    每个值仅占8字节空间.
    """

    @classmethod
    def from_bytes(cls, data: bytes, **extra: Any) -> tuple[int, int]:  # type: ignore[override]
        """从JCE格式解码64位整数."""
        return struct.unpack_from(">q", data)[0], 8


class FLOAT(JceType, float):
    """JCE单精度浮点类型.

    该类继承自float,用于在JCE协议中编码和解码单精度浮点数.
    使用IEEE 754 32位格式存储.

    Attributes:
        __jce_type__: 元组(4,),指定JCE类型代码.
    """

    __jce_type__ = (4,)

    @classmethod
    def to_bytes(cls, jce_id: int, value: float) -> bytes:
        """将浮点数值编码为JCE格式."""
        return cls.head_byte(jce_id, cls.__jce_type__[0]) + struct.pack(
            ">f", value
        )

    @classmethod
    def from_bytes(cls, data: bytes, **extra: Any) -> tuple[float, int]:
        """从JCE格式解码浮点数值."""
        return struct.unpack_from(">f", data)[0], 4

    @classmethod
    def validate(cls, value: Any) -> "FLOAT":
        """验证和转换浮点数值."""
        if isinstance(value, bytes):
            value, _ = cls.from_bytes(value)
        elif isinstance(value, (float, int)):
            value = float(value)
        else:
            raise TypeError(f"Invalid value type: {type(value)}")
        return cls(value)


class DOUBLE(JceType, float):
    """JCE双精度浮点类型.

    该类继承自float,用于在JCE协议中编码和解码双精度浮点数.
    使用IEEE 754 64位格式存储,提供比FLOAT更高的精度.

    Attributes:
        __jce_type__: 元组(5,),指定JCE类型代码.
    """

    __jce_type__ = (5,)

    @classmethod
    def to_bytes(cls, jce_id: int, value: float) -> bytes:
        """将双精度浮点数值编码为JCE格式."""
        return cls.head_byte(jce_id, cls.__jce_type__[0]) + struct.pack(
            ">d", value
        )

    @classmethod
    def from_bytes(cls, data: bytes, **extra: Any) -> tuple[float, int]:
        """从JCE格式解码双精度浮点数值."""
        return struct.unpack_from(">d", data)[0], 8

    @classmethod
    def validate(cls, value: Any) -> "DOUBLE":
        """验证和转换双精度浮点数值."""
        if isinstance(value, bytes):
            value, _ = cls.from_bytes(value)
        elif isinstance(value, (float, int)):
            value = float(value)
        else:
            raise TypeError(f"Invalid value type: {type(value)}")
        return cls(value)


class STRING(JceType, str):
    """JCE字符串类型,支持多种长度编码格式.

    该类继承自str,用于在JCE协议中编码和解码字符串.
    根据字符串长度自动选择编码格式:
    - 长度 < 256: 使用1字节长度前缀
    - 长度 >= 256: 使用4字节长度前缀

    Attributes:
        __jce_type__: 元组(6, 7),指定可能的JCE类型代码.

    Note:
        子类STRING1和STRING4分别对应1字节和4字节长度前缀.
    """

    __jce_type__ = (6, 7)

    @classmethod
    def to_bytes(cls, jce_id: int, value: str) -> bytes:
        """将字符串编码为JCE格式."""
        byte = value.encode()
        if len(byte) < 256:
            return (
                cls.head_byte(jce_id, cls.__jce_type__[0])
                + struct.pack(">B", len(byte))
                + byte
            )
        return (
            cls.head_byte(jce_id, cls.__jce_type__[1])
            + struct.pack(">I", len(byte))
            + byte
        )

    @classmethod
    def from_bytes(cls, data: bytes, **extra: Any) -> tuple[str, int]:
        """从JCE格式解码字符串值."""
        raise NotImplementedError

    @classmethod
    def validate(cls: type[T_STRING], value: Any) -> T_STRING:
        """验证和转换字符串值."""
        if isinstance(value, bytes):
            value = value.decode()
        elif not isinstance(value, str):
            raise TypeError(f"Invalid value type: {type(value)}")
        return cls(value)


class STRING1(STRING):
    """使用1字节长度前缀的JCE字符串子类.

    用于编码长度小于256字符的字符串,经济而高效.
    字符串长度存储在1个字节中,最大支持255个字符.

    Args:
        value: 待编码的字符串值.

    Raises:
        ValueError: 如果字符串超过255字节长度.
    """

    @classmethod
    def from_bytes(cls, data: bytes, **extra: Any) -> tuple[str, int]:
        """从JCE格式解码使用1字节长度前缀的字符串."""
        length = struct.unpack_from(">B", data)[0]
        return data[1 : length + 1].decode(), length + 1


class STRING4(STRING):
    """使用4字节长度前缀的JCE字符串子类.

    用于编码长度大于等于256字符的字符串,支持更长的内容.
    字符串长度存储在4个字节中(网络字节序),最大支持4GB大小的字符串.

    Args:
        value: 待编码的字符串值.

    Note:
        对于长度小于256的字符串,应使用STRING1以节省空间.
    """

    @classmethod
    def from_bytes(cls, data: bytes, **extra: Any) -> tuple[str, int]:
        """从JCE格式解码使用4字节长度前缀的字符串."""
        length = struct.unpack_from(">I", data)[0]
        return data[4 : length + 4].decode(), length + 4


class MAP(JceType, dict[T, VT]):
    """JCE映射类型,用于歘储键值对.

    该类继承自dict,用于在JCE协议中编码和解码映射/字典数据.
    字典的每个键和值都是分别编码的JCE数据,使用不同的标签(键使用0,值使用1).

    Attributes:
        __jce_type__: 元组(8,),指定JCE类型代码.

    Type Parameters:
        T: 键的类型,必须是JceType子类.
        VT: 值的类型,必须是JceType子类.

    Example:
        >>> # 使用预定群类型
        >>> from jce.types import MAP, INT, STRING
        >>> map_data = MAP[INT, STRING](
        ...     {INT(1): STRING("hello"), INT(2): STRING("world")}
        ... )
    """

    __jce_type__ = (8,)

    @classmethod
    def to_bytes(cls, jce_id: int, value: dict[T, VT]) -> bytes:  # type: ignore[override]
        """将MAP编码为JCE格式."""
        from jce.const import JCE_MAP
        from jce.encoder import DataWriter

        writer = DataWriter()
        writer.write_head(jce_id, JCE_MAP)
        writer.write_int(0, len(value))

        # 直接将每个键值对编码到writer中
        for k, v in value.items():
            # 使用标签0编码键
            if isinstance(k, JceType):
                # 为JceType键使用to_bytes
                k_encoded = k.to_bytes(0, k)
                writer._buffer.extend(k_encoded)
            else:
                # 对于原始类型,尝试猜测类型并编码
                k_type = guess_jce_type(k)
                k_encoded = k_type.to_bytes(0, k)
                writer._buffer.extend(k_encoded)

            # 使用标签1编码值
            if isinstance(v, JceType):
                v_encoded = v.to_bytes(1, v)
                writer._buffer.extend(v_encoded)
            else:
                v_type = guess_jce_type(v)
                v_encoded = v_type.to_bytes(1, v)
                writer._buffer.extend(v_encoded)

        return writer.get_bytes()

    @classmethod
    def from_bytes(
        cls, data: bytes, **extra: Any
    ) -> tuple[dict[Any, Any], int]:  # type: ignore[override]
        """从JCE格式解码MAP值."""
        from jce.decoder import DataReader, GenericDecoder

        reader = DataReader(data)
        decoder = GenericDecoder(reader)

        # 读取计数(MAP编码中的第一个字段)
        _, count_type = decoder._read_head()
        data_count = decoder._read_value(count_type)

        result = {}
        for _ in range(data_count):
            _, k_type = decoder._read_head()
            key = decoder._read_value(k_type)
            _, v_type = decoder._read_head()
            value = decoder._read_value(v_type)
            result[key] = value

        return result, reader._pos

    @classmethod
    def validate(cls, value: Any) -> "MAP[Any, Any]":
        """验证和转换MAP值."""
        if isinstance(value, cls):
            return value  # type: ignore

        if isinstance(value, bytes):
            value, _ = cls.from_bytes(value)
        elif not isinstance(value, Mapping):
            raise TypeError(f"Invalid MAP type: {type(value)}")

        new_instance: dict[Any, Any] = cls()
        for key, val in value.items():
            if not isinstance(key, JceType):
                try:
                    key_type = guess_jce_type(key)
                except TypeError:
                    raise TypeError(
                        f"Invalid MAP key: {key}({type(key)})"
                    ) from None
                key = key_type.validate(key)  # type: ignore
            if not isinstance(val, JceType):
                try:
                    value_type = guess_jce_type(val)
                except TypeError:
                    raise TypeError(
                        f"Invalid MAP value: {val}({type(val)})"
                    ) from None
                val = value_type.validate(val)  # type: ignore

            new_instance[key] = val  # type: ignore

        return cast(MAP[Any, Any], new_instance)


class LIST(JceType, list[T]):
    """JCE列表类型,用于歘储有序元素集合.

    该类继承自list,用于在JCE协议中编码和解码数组/列表数据.
    列表中的每个元素都是JCE类型,所有元素应该是相同的类型.

    Attributes:
        __jce_type__: 元组(9,),指定JCE类型代码.

    Type Parameters:
        T: 元素的类型,必须是JceType子类.

    Example:
        >>> # 使用预定穡类型
        >>> from jce.types import LIST, INT
        >>> list_data = LIST[INT]([INT(1), INT(2), INT(3)])

    Note:
        使用JceField标注时激活列表,必须明确指定`jce_type=LIST`参数.
    """

    __jce_type__ = (9,)

    @classmethod
    def to_bytes(cls, jce_id: int, value: list[T]) -> bytes:  # type: ignore[override]
        """将LIST编码为JCE格式."""
        from jce.const import JCE_LIST
        from jce.encoder import DataWriter

        writer = DataWriter()
        writer.write_head(jce_id, JCE_LIST)
        writer.write_int(0, len(value))

        # 直接将每个项目编码到writer中
        for v in value:
            if isinstance(v, JceType):
                item_encoded = v.to_bytes(0, v)
                writer._buffer.extend(item_encoded)
            else:
                v_type = guess_jce_type(v)
                item_encoded = v_type.to_bytes(0, v)
                writer._buffer.extend(item_encoded)

        return writer.get_bytes()

    @classmethod
    def from_bytes(cls, data: bytes, **extra: Any) -> tuple[list[Any], int]:  # type: ignore[override]
        """从JCE格式解码LIST值."""
        from jce.decoder import DataReader, GenericDecoder

        reader = DataReader(data)
        decoder = GenericDecoder(reader)

        # 读取计数(LIST编码中的第一个字段)
        _, count_type = decoder._read_head()
        list_count = decoder._read_value(count_type)

        result = []
        for _ in range(list_count):
            _, type_id = decoder._read_head()
            item = decoder._read_value(type_id)
            result.append(item)

        return result, reader._pos

    @classmethod
    def validate(cls, value: Any) -> "LIST[Any]":
        """验证和转换LIST值."""
        if isinstance(value, cls):
            return value  # type: ignore

        if isinstance(value, bytes):
            value, _ = cls.from_bytes(value)
        elif not isinstance(value, Iterable):
            raise TypeError(f"Invalid LIST type: {type(value)}")

        new_instance: list[Any] = cls()  # 显式强转/类型提示以帮助检查器
        for item in value:
            if not isinstance(item, JceType):
                try:
                    item_type = guess_jce_type(item)
                except TypeError:
                    raise TypeError(
                        f"Invalid LIST item type: {type(item)}"
                    ) from None
                item = item_type(item)  # type: ignore
            new_instance.append(item)  # type: ignore
        return cast(LIST[Any], new_instance)


class STRUCT_START(JceType):
    """JCE结构体开始标记.

    在JCE编码格式中标记结构体(自定义对象)的开始.
    不包含实际数据,仅用于分隔符作用.

    Attributes:
        __jce_type__: 元组(10,),指定JCE类型代码为10.
    """

    __jce_type__ = (10,)

    @classmethod
    def to_bytes(cls, jce_id: int, value: Any = None) -> bytes:
        """编码结构体开始标记."""
        return cls.head_byte(jce_id, cls.__jce_type__[0])

    @classmethod
    def from_bytes(
        cls, data: bytes, **extra: Any
    ) -> tuple[dict[int, Any], int]:
        """解码结构体开始标记."""
        return JceStruct.from_bytes(data, **extra)

    @classmethod
    def validate(cls, value: Any) -> Any:
        """验证结构体开始标记."""
        return value


class STRUCT_END(JceType):
    """JCE结构体结束标记.

    在JCE编码格式中标记结构体(自定义对象)的结束.
    不包含实际数据,仅用于分隔符作用.

    Attributes:
        __jce_type__: 元组(11,),指定JCE类型代码为11.
    """

    __jce_type__ = (11,)

    @classmethod
    def to_bytes(cls, jce_id: int, value: Any = None) -> bytes:
        """编码结构体结束标记."""
        return cls.head_byte(jce_id, cls.__jce_type__[0])

    @classmethod
    def from_bytes(cls, data: bytes, **extra: Any) -> tuple[None, int]:
        """解码结构体结束标记."""
        return None, 0

    @classmethod
    def validate(cls, value: Any) -> Any:
        """验证结构体结束标记."""
        return value


class ZERO_TAG(JceType, bytes):
    """JCE零值标记,用于表示零值或空值.

    在JCE协议中,某些类型(如BYTE)的零值可以用此标记代替,
    以节省编码空间,减少序列化数据大小.

    Attributes:
        __jce_type__: 元组(12,),指定JCE类型代码为12.
    """

    __jce_type__ = (12,)

    @classmethod
    def to_bytes(cls, jce_id: int, value: Any = None) -> bytes:
        """编码零值标记."""
        return cls.head_byte(jce_id, cls.__jce_type__[0])

    @classmethod
    def from_bytes(cls, data: bytes, **extra: Any) -> tuple[bytes, int]:
        """解码零值标记."""
        return bytes([0]), 0


class BYTES(JceType, bytes):
    """JCE原始字节数组类型.

    该类继承自bytes,用于在JCE协议中编码和解码原始字节数据.
    与BYTE(单个字节)不同,BYTES用于表示任意长度的字节序列.

    Attributes:
        __jce_type__: 元组(13,),指定JCE类型代码为13.

    Note:
        在JCE中,BYTES采用头字节+嵌套STRUCT_START+长度+数据+STRUCT_END的格式编码.
    """

    __jce_type__ = (13,)

    @classmethod
    def to_bytes(cls, jce_id: int, value: bytes) -> bytes:
        """将字节序列编码为JCE格式."""
        return (
            cls.head_byte(jce_id, cls.__jce_type__[0])
            + cls.head_byte(0, 0)
            + INT32.to_bytes(0, len(value))
            + value
        )

    @classmethod
    def from_bytes(cls, data: bytes, **extra: Any) -> tuple[bytes, int]:
        """从JCE格式解码字节序列."""
        from jce.decoder import DataReader, GenericDecoder

        reader = DataReader(data)
        decoder = GenericDecoder(reader)

        # 读取元素类型头(应为BYTE/INT1)
        _, _ = decoder._read_head()
        # 读取长度
        _, length_type = decoder._read_head()
        byte_length = decoder._read_value(length_type)

        # 读取实际的字节
        result = reader.read_bytes(byte_length, zero_copy=False)
        if isinstance(result, memoryview):
            result = bytes(result)

        return result, reader._pos

    @classmethod
    def validate(cls, value: Any) -> "BYTES":
        """验证和转换字节序列值."""
        value = cls(value)
        return value


class JceMetaclass(ModelMetaclass):
    """Pydantic模型的JCE扩展元类.

    该元类在Pydantic的ModelMetaclass基础上扩展,自动为JceStruct类进行JCE相关的初始化:
    1. 收集和验证JCE字段定义
    2. 建立JCE字段ID到字段类型的映射
    3. 设置默认的JCE类型映射表(__jce_default_type__)

    在JceStruct的每个子类创建时自动执行,无需用户手动干预.

    Attributes:
        __jce_fields__: 从model_fields中提取的有效JCE字段的字典,按jce_id排序.
        __jce_default_type__: 映射JCE类型ID到对应JceType类的字典,用于解码时的类型推断.

    Raises:
        TypeError: 如果jce_default_type中的任何值不是JceType的子类.

    Note:
        用户不应直接使用此元类,而应继承JceStruct类来获得自动的JCE支持.
    """

    def __new__(mcs, name, bases, namespace):  # type: ignore  # noqa: D102
        cls = super().__new__(mcs, name, bases, namespace)  # type: ignore

        config = getattr(cls, "model_config", {})

        default_type = config.get(
            "jce_default_type",
            {
                0: BYTE,
                1: INT16,
                2: INT32,
                3: INT64,
                4: FLOAT,
                5: DOUBLE,
                6: STRING1,
                7: STRING4,
                8: MAP,
                9: LIST,
                10: STRUCT_START,
                11: STRUCT_END,
                12: ZERO_TAG,
                13: BYTES,
            },
        )

        if any(not issubclass(x, JceType) for x in default_type.values()):
            raise TypeError(f'Invalid default jce type in struct "{name}"')

        setattr(cls, "__jce_default_type__", default_type)

        if hasattr(cls, "model_fields"):
            fields = prepare_fields(cls.model_fields)
            setattr(cls, "__jce_fields__", fields)

        return cls


class JceStruct(BaseModel, JceType, metaclass=JceMetaclass):
    """JCE结构体的基类,用于定义和操作JCE编码的数据结构.

    JceStruct结合了Pydantic的数据验证能力和JCE协议支持.
    继承此类的每个子类都应通过JceField()定义其字段.

    使用元类JceMetaclass自动处理JCE字段的注册和初始化.
    字段必须具有jce_id来指定在JCE二进制格式中的位置.

    Examples:
        >>> class Person(JceStruct):
        ...     name: str = JceField(jce_id=0, default="")
        ...     age: int = JceField(jce_id=1, default=0)
        ...
        >>> person = Person(name="Alice", age=30)
        >>> data = person.encode()  # 序列化为JCE字节
        >>> restored = Person.decode(data)  # 从JCE字节反序列化
    """

    if TYPE_CHECKING:
        __jce_fields__: dict[str, JceModelField]
        __jce_default_type__: dict[int, type[JceType]]

    def __getitem__(self, key):
        return getattr(self, key)

    def encode(self) -> bytes:
        """编码为JCE二进制格式."""
        from jce.api import dumps

        return dumps(self)

    @classmethod
    def to_bytes(cls: type[S], jce_id: int, value: S) -> bytes:
        """将结构体编码为JCE字节."""
        from jce.api import dumps
        from jce.const import JCE_STRUCT_BEGIN, JCE_STRUCT_END
        from jce.encoder import DataWriter

        writer = DataWriter()
        writer.write_head(jce_id, JCE_STRUCT_BEGIN)
        writer._buffer.extend(dumps(value))
        writer.write_head(0, JCE_STRUCT_END)
        return writer.get_bytes()

    @classmethod
    def decode(cls: type[S], data: bytes, **extra: Any) -> S:
        """从JCE二进制格式解码."""
        from jce.decoder import DataReader, GenericDecoder

        # 使用GenericDecoder直接获取原始dict,避免api.loads的自动类型转换
        reader = DataReader(data)
        decoder = GenericDecoder(reader)
        raw_data = decoder.decode()

        # 递归注入extra的辅助函数
        def inject_extra(obj: Any):
            if isinstance(obj, dict):
                obj.update(extra)
                for v in obj.values():
                    inject_extra(v)
            elif isinstance(obj, list):
                for v in obj:
                    inject_extra(v)

        if extra:
            inject_extra(raw_data)

        return cls.validate(raw_data)

    @classmethod
    def decode_list(
        cls: type[S], data: bytes, jce_id: int, **extra: Any
    ) -> list[S]:
        """解码列表数据."""
        from jce.decoder import DataReader, GenericDecoder

        reader = DataReader(data)
        decoder = GenericDecoder(reader)
        d = decoder.decode()
        result_list = d.get(jce_id)

        if result_list is None:
            return []

        if not isinstance(result_list, list):
            raise TypeError(f"Value at jce_id {jce_id} is not a list")

        # 递归注入extra的辅助函数
        def inject_extra(obj: Any):
            if isinstance(obj, dict):
                obj.update(extra)
                for v in obj.values():
                    inject_extra(v)
            elif isinstance(obj, list):
                for v in obj:
                    inject_extra(v)

        if extra:
            inject_extra(result_list)

        return [cls.model_validate(item) for item in result_list]

    @classmethod
    def from_bytes(
        cls, data: bytes, **extra: Any
    ) -> tuple[dict[int, JceType], int]:
        """从JCE字节格式解码结构体."""
        from jce.decoder import DataReader, GenericDecoder

        reader = DataReader(data)
        decoder = GenericDecoder(reader)

        # GenericDecoder.decode读取直到EOF或STRUCT_END.
        result = decoder.decode()

        # 如果我们在STRUCT_END停止,我们需要消费它?
        # GenericDecoder.decode在STRUCT_END处中断,但不消费它?
        # 让我们检查GenericDecoder.decode.
        # "if type_id == JCE_STRUCT_END: break"
        # 它读取head. 所以head被消费.

        offset = reader._pos
        return result, offset

    @classmethod
    def validate(cls: type[S], value: Any) -> S:
        """验证和转换结构体值."""
        # validate应该返回cls的实例(S)
        return cls.model_validate(value)  # type: ignore

    @model_validator(mode="before")
    @classmethod
    def _jce_pre_validate(cls, value: Any) -> Any:
        """JCE前验证处理."""
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            raise TypeError(f"Invalid value type: {type(value)}")

        values = {}
        for field_name in cls.model_fields.keys():
            if field_name in cls.__jce_fields__:
                jce_info = cls.__jce_fields__[field_name]
                data = value.get(jce_info.jce_id, _empty)
                if data is _empty:
                    data = value.get(field_name, _empty)
                if data is _empty:
                    continue
                # 我们不在这里手动验证,让Pydantic处理它
                values[field_name] = data
            else:
                data = value.get(field_name, _empty)
                if data is _empty:
                    continue
                values[field_name] = data
        return values


def get_jce_type(jce_id: int) -> type[JceType]:
    """根据JCE ID获取对应的JCE类型."""
    return JceStruct.__jce_default_type__[jce_id]


def guess_jce_type(value: Any) -> type[JceType]:
    """根据Python值的类型推断相应的JCE类型.

    该函数尝试将Python内置类型映射到相应的JCE类型.
    它首先检查精确的类型匹配,然后检查isinstance关系,
    最后检查值是否是JceStruct实例.

    Args:
        value: 要推断JCE类型的Python值.

    Returns:
        适合该值的JceType子类.

    Raises:
        TypeError: 如果值的类型无法映射到任何JCE类型.

    类型映射:
        bytes -> BYTE
        bool -> BOOL
        int -> INT
        float -> FLOAT
        str -> STRING
        dict -> MAP
        list -> LIST
        JceStruct子类 -> 该子类本身
    """
    types: dict[type, type[JceType]] = {
        bytes: BYTE,
        bool: BOOL,
        int: INT,
        float: FLOAT,
        str: STRING,
        dict: MAP,
        list: LIST,
    }
    t = type(value)
    if t in types:
        return types[t]

    for py_type, jce_type in types.items():
        if isinstance(value, py_type):
            return jce_type

    if isinstance(value, JceStruct):
        return value.__class__

    raise TypeError(f"Cannot guess JceType for {type(value)}")
