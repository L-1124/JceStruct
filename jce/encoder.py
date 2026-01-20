"""JCE编码器实现.

该模块提供用于高效缓冲管理的`DataWriter`和
用于将Python对象序列化为JCE的`JceEncoder`.
"""

import struct
from collections.abc import Callable
from typing import Any, TypeVar

from .config import JceConfig
from .const import (
    JCE_DOUBLE,
    JCE_FLOAT,
    JCE_INT1,
    JCE_INT2,
    JCE_INT4,
    JCE_INT8,
    JCE_LIST,
    JCE_MAP,
    JCE_SIMPLE_LIST,
    JCE_STRING1,
    JCE_STRING4,
    JCE_STRUCT_BEGIN,
    JCE_STRUCT_END,
    JCE_ZERO_TAG,
)
from .context import SerializationInfo
from .exceptions import JceEncodeError
from .log import logger
from .options import JceOption

JceSerializer = Callable[[Any, Any, SerializationInfo], Any]

F = TypeVar("F", bound=JceSerializer)


def jce_field_serializer(field_name: str):
    """装饰器: 注册字段的自定义 JCE 序列化方法.

    被装饰的方法应接受两个参数:
    - self: 实例本身
    - value: 字段值
    - info: SerializationInfo 上下文信息

    Args:
        field_name: 要自定义序列化的字段名称.

    Usage:
        ```python
        @jce_field_serializer("password")
        def serialize_password(self, value: Any, info: SerializationInfo) -> Any:
            return encrypt(value)
        ```
    """

    def decorator(func: F) -> F:
        from typing import cast

        cast(Any, func).__jce_serializer_target__ = field_name
        return func

    return decorator


# 预编译的结构体打包器
_PACK_B = struct.Struct(">b").pack
_PACK_H = struct.Struct(">h").pack
_PACK_I = struct.Struct(">i").pack
_PACK_Q = struct.Struct(">q").pack
_PACK_f = struct.Struct(">f").pack
_PACK_d = struct.Struct(">d").pack

_PACK_B_LE = struct.Struct("<b").pack
_PACK_H_LE = struct.Struct("<h").pack
_PACK_I_LE = struct.Struct("<i").pack
_PACK_Q_LE = struct.Struct("<q").pack
_PACK_f_LE = struct.Struct("<f").pack
_PACK_d_LE = struct.Struct("<d").pack


class DataWriter:
    """JCE二进制数据的高效写入器."""

    __slots__ = (
        "_buffer",
        "_pack_b",
        "_pack_d",
        "_pack_f",
        "_pack_h",
        "_pack_i",
        "_pack_q",
    )

    _buffer: bytearray
    _pack_b: Callable[[int], bytes]
    _pack_h: Callable[[int], bytes]
    _pack_i: Callable[[int], bytes]
    _pack_q: Callable[[int], bytes]
    _pack_f: Callable[[float], bytes]
    _pack_d: Callable[[float], bytes]

    def __init__(self, option: int = 0):
        self._buffer = bytearray()
        # 根据字节序选择对应的打包器
        if option & JceOption.LITTLE_ENDIAN:
            self._pack_b = _PACK_B_LE
            self._pack_h = _PACK_H_LE
            self._pack_i = _PACK_I_LE
            self._pack_q = _PACK_Q_LE
            self._pack_f = _PACK_f_LE
            self._pack_d = _PACK_d_LE
        else:
            self._pack_b = _PACK_B
            self._pack_h = _PACK_H
            self._pack_i = _PACK_I
            self._pack_q = _PACK_Q
            self._pack_f = _PACK_f
            self._pack_d = _PACK_d

    def get_bytes(self) -> bytes:
        """返回累积的字节."""
        return bytes(self._buffer)

    def write_head(self, tag: int, type_id: int) -> None:
        """写入JCE头部(Tag + Type)."""
        if tag < 15:
            self._buffer.append((tag << 4) | type_id)
        else:
            self._buffer.append(0xF0 | type_id)
            self._buffer.append(tag)

    def write_int(self, tag: int, value: int) -> None:
        """写入带有JCE压缩的整数."""
        if value == 0:
            self.write_head(tag, JCE_ZERO_TAG)
        elif -128 <= value <= 127:
            self.write_head(tag, JCE_INT1)
            self._buffer.extend(self._pack_b(value))
        elif -32768 <= value <= 32767:
            self.write_head(tag, JCE_INT2)
            self._buffer.extend(self._pack_h(value))
        elif -2147483648 <= value <= 2147483647:
            self.write_head(tag, JCE_INT4)
            self._buffer.extend(self._pack_i(value))
        else:
            if not (-9223372036854775808 <= value <= 9223372036854775807):
                raise JceEncodeError(f"Integer out of range: {value}")
            self.write_head(tag, JCE_INT8)
            self._buffer.extend(self._pack_q(value))

    def write_float(self, tag: int, value: float) -> None:
        """写入浮点数."""
        self.write_head(tag, JCE_FLOAT)
        self._buffer.extend(self._pack_f(value))

    def write_double(self, tag: int, value: float) -> None:
        """写入双精度浮点数."""
        self.write_head(tag, JCE_DOUBLE)
        self._buffer.extend(self._pack_d(value))

    def write_string(self, tag: int, value: str) -> None:
        """写入字符串."""
        data = value.encode("utf-8")
        length = len(data)
        if length <= 255:
            self.write_head(tag, JCE_STRING1)
            self._buffer.append(length)
            self._buffer.extend(data)
        elif length > 4294967295:
            # Python len是int.
            raise JceEncodeError(f"String too long: {length}")
        else:
            self.write_head(tag, JCE_STRING4)
            # STRING4的长度始终是大端4字节
            self._buffer.extend(struct.pack(">I", length))
            self._buffer.extend(data)

    def write_bytes(self, tag: int, value: bytes) -> None:
        """将字节写作SIMPLE_LIST."""
        self.write_head(tag, JCE_SIMPLE_LIST)
        self.write_head(0, JCE_INT1)  # 元素类型(BYTE=0),标签=0
        self.write_int(0, len(value))  # 列表长度
        self._buffer.extend(value)

    def write_list(self, tag: int, value: list[Any], encoder: "JceEncoder") -> None:
        """写一个列表."""
        self.write_head(tag, JCE_LIST)
        self.write_int(0, len(value))
        for item in value:
            encoder.encode_value(item, tag=0)

    def write_map(self, tag: int, value: dict[Any, Any], encoder: "JceEncoder") -> None:
        """写一个映射."""
        self.write_head(tag, JCE_MAP)
        self.write_int(0, len(value))
        for k, v in value.items():
            encoder.encode_value(k, tag=0)
            encoder.encode_value(v, tag=1)

    def write_struct_begin(self, tag: int) -> None:
        """结构体开始标记(用于以后扩展)."""
        self.write_head(tag, JCE_STRUCT_BEGIN)

    def write_struct_end(self) -> None:
        """结构体结束标记(用于以后扩展)."""
        self.write_head(0, JCE_STRUCT_END)


class JceEncoder:
    """具有循环引用检测的递归JCE编码器."""

    __slots__ = (
        "_config",
        "_encoding_stack",
        "_writer",
    )

    _writer: DataWriter
    _config: JceConfig

    def __init__(self, config: JceConfig):
        self._config = config
        self._writer = DataWriter(self._config.option)
        # 跟踪正在编码的对象以检测循环引用
        self._encoding_stack: set[int] = set()

    def encode(self, obj: Any, target_type: Any = None) -> bytes:
        """编码入口."""
        try:
            from .struct import JceDict

            if hasattr(obj, "__jce_fields__"):
                self._encode_struct_fields(obj)
            elif isinstance(obj, JceDict):
                # 显式 JceDict -> 作为 Struct 编码
                self._encode_dict_as_struct(obj)
            else:
                # 其他所有情况 (包括普通 dict, list) -> 作为值编码 (dict -> Map)
                self.encode_value(obj, tag=0, target_type=target_type)

            return self._writer.get_bytes()
        except Exception as e:
            logger.error("Encoding failed: %s", e)
            raise

    def encode_value(self, value: Any, tag: int, target_type: Any = None) -> None:
        """使用标签编码单个值.

        Args:
            value: 要编码的值.
            tag: JCE标签ID.
            target_type: 目标 JCE 类型 (可选, 用于自动转换).

        Raises:
            JceEncodeError: 如果检测到循环引用或类型无法编码.
        """
        if value is None:
            return
        # 尝试根据 target_type 进行自动类型转换
        if target_type is not None:
            # 延迟导入以避免循环引用
            from . import types

            # 安全检查 target_type 是否为类
            is_class = isinstance(target_type, type)

            # 万能 BYTES 处理
            if is_class and issubclass(target_type, types.BYTES):
                if isinstance(value, bytes | bytearray | memoryview):
                    self._writer.write_bytes(tag, bytes(value))
                    return
                elif isinstance(value, str):
                    self._writer.write_bytes(tag, value.encode("utf-8"))
                    return
                elif isinstance(value, int):  # Handle byte value as int
                    self._writer.write_bytes(tag, bytes([value]))
                    return
                else:
                    # 对于 dict/list/tuple, 跳过 bytes() 尝试,
                    # 因为 bytes(dict) 会只序列化 key, 这通常不是预期的.
                    if not isinstance(value, dict | list | tuple):
                        # 尝试调用 __bytes__
                        try:
                            self._writer.write_bytes(tag, bytes(value))
                            return
                        except TypeError:
                            pass

                    # 特殊处理: 如果是 JceStruct, dict, list 等, 尝试递归序列化为 bytes
                    from .api import dumps

                    try:
                        # 使用当前选项和上下文进行递归序列化
                        serialized = dumps(
                            value,
                            option=self._config.flags,
                            default=self._config.default,
                            context=self._config.context,
                        )
                        self._writer.write_bytes(tag, serialized)
                        return
                    except Exception:
                        pass

                    # 如果都失败了,抛出明确错误
                    raise JceEncodeError(
                        f"Cannot convert {type(value)} to BYTES. It must be bytes, str, or implement __bytes__, or be a serializable JCE object."
                    )

            if is_class and issubclass(target_type, types.FLOAT):
                if isinstance(value, float | int):
                    self._writer.write_float(tag, float(value))
                    return

            if is_class and issubclass(target_type, types.DOUBLE):
                if isinstance(value, float | int):
                    self._writer.write_double(tag, float(value))
                    return

            if is_class and issubclass(target_type, types.INT):
                if isinstance(value, bytes) and len(value) == 1:
                    # 特殊情况: 单元测试将 bytes 传递给 INT
                    self._writer.write_int(tag, value[0])
                    return

        # 检查容器类型中的循环引用
        if isinstance(value, list | dict) or hasattr(value, "__jce_fields__"):
            obj_id = id(value)
            if obj_id in self._encoding_stack:
                raise JceEncodeError(f"Circular reference in {type(value)}")

            self._encoding_stack.add(obj_id)
            try:
                self._encode_container(value, tag)
            finally:
                self._encoding_stack.discard(obj_id)
        else:
            self._encode_primitive(value, tag)

    def _encode_primitive(self, value: Any, tag: int) -> None:
        """编码原始(非容器)值."""
        if isinstance(value, bool):
            self._writer.write_int(tag, int(value))
        elif isinstance(value, int):
            self._writer.write_int(tag, value)
        elif isinstance(value, float):
            self._writer.write_double(tag, value)
        elif isinstance(value, str):
            self._writer.write_string(tag, value)
        elif isinstance(value, bytes | bytearray | memoryview):
            self._writer.write_bytes(tag, bytes(value))
        elif self._config.default:
            new_val = self._config.default(value)
            self.encode_value(new_val, tag)
        else:
            raise JceEncodeError(f"Cannot encode type: {type(value)}")

    def _encode_container(self, value: Any, tag: int) -> None:
        """编码容器类型(列表、字典或结构体)."""
        if isinstance(value, list):
            self._writer.write_list(tag, value, self)
            return
        elif isinstance(value, dict):
            from .struct import JceDict

            if isinstance(value, JceDict):
                self._writer.write_struct_begin(tag)
                self._encode_dict_as_struct(value)
                self._writer.write_struct_end()
            else:
                self._writer.write_map(tag, value, self)
            return
        elif hasattr(value, "__jce_fields__"):
            self._writer.write_struct_begin(tag)
            self._encode_struct_fields(value)
            self._writer.write_struct_end()
            return
        else:
            raise JceEncodeError(f"Cannot encode container type: {type(value)}")

    def _encode_struct_fields(self, obj: Any) -> None:
        # 获取字段,对于泛型类需要从原始类获取
        fields = getattr(obj, "__jce_fields__", {})

        # 如果字段为空,尝试从泛型起源获取(处理 Box[T] 这样的情况)
        if not fields:
            obj_class = type(obj)
            # 检查 __orig_bases__ 以找到泛型基类
            for base in getattr(obj_class, "__orig_bases__", []):
                from typing import get_origin

                origin = get_origin(base)
                if origin and hasattr(origin, "__jce_fields__"):
                    fields = origin.__jce_fields__
                    break
            # 如果还是没有,尝试 MRO
            if not fields:
                for base in obj_class.__mro__[1:]:  # 跳过自身
                    if hasattr(base, "__jce_fields__"):
                        base_fields = getattr(base, "__jce_fields__", {})
                        if base_fields:
                            fields = base_fields
                            break

        serializers = getattr(obj, "__jce_serializers__", {})

        # 获取Pydantic模型字段信息以访问默认值
        # 注意: 应该从类访问 model_fields 而不是实例
        model_fields = getattr(type(obj), "model_fields", {})

        # 获取已设置的字段集合 (用于 exclude_unset)
        model_fields_set = getattr(obj, "model_fields_set", set())

        for name, field in fields.items():
            # exclude_unset 检查
            if self._config.exclude_unset and name not in model_fields_set:
                continue

            val = getattr(obj, name)

            # 如果设置了 OPT_OMIT_DEFAULT, 则检查默认值
            if self._config.omit_default:
                if name in model_fields:
                    pydantic_field = model_fields[name]
                    # 如果字段有默认值且当前值等于默认值,则跳过编码
                    from pydantic_core import PydanticUndefined

                    if pydantic_field.default is not PydanticUndefined:
                        if val == pydantic_field.default:
                            continue

            # 检查是否有字段序列化器
            if name in serializers:
                serializer_name = serializers[name]
                serializer_func = getattr(obj, serializer_name)
                info = SerializationInfo(
                    option=self._config.option,
                    context=self._config.context,
                    field_name=name,
                    jce_id=field.jce_id,
                )
                val = serializer_func(val, info)

            # 传递目标类型元数据给 encode_value
            self.encode_value(val, field.jce_id, target_type=field.jce_type)

    def _encode_dict_as_struct(self, obj: dict[Any, Any]) -> None:
        """仅将 JceDict 编码为 Struct 字段序列."""
        for tag, val in obj.items():
            # JceDict 必须保证 Key 是 Int
            if not isinstance(tag, int):
                raise JceEncodeError(
                    f"JceDict keys must be int tags for struct encoding, got {type(tag)}"
                )
            self.encode_value(val, tag)
