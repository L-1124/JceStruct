"""JCE编码器实现.

该模块提供用于高效缓冲管理的`DataWriter`和
用于将Python对象序列化为JCE的`JceEncoder`.
"""

import struct
from collections.abc import Callable
from typing import Any

from jce.const import (
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
from jce.exceptions import JceEncodeError
from jce.options import OPT_LITTLE_ENDIAN, OPT_OMIT_DEFAULT

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

    def __init__(self, option: int = 0):
        self._buffer = bytearray()
        # 根据初始化时的字节序选择打包器
        if option & OPT_LITTLE_ENDIAN:
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
            # 检查64位范围
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

    def write_list(
        self, tag: int, value: list[Any], encoder: "JceEncoder"
    ) -> None:
        """写一个列表."""
        self.write_head(tag, JCE_LIST)
        self.write_int(0, len(value))
        for item in value:
            encoder.encode_value(item, tag=0)

    def write_map(
        self, tag: int, value: dict[Any, Any], encoder: "JceEncoder"
    ) -> None:
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

    def __init__(
        self, option: int = 0, default: Callable[[Any], Any] | None = None
    ):
        self._writer = DataWriter(option)
        self._option = option
        self._default = default
        # 跟踪正在编码的对象以检测循环引用
        self._encoding_stack: set[int] = set()

    def encode(self, obj: Any) -> bytes:
        """将对象编码为字节."""
        if hasattr(obj, "__jce_fields__"):
            self._encode_struct_fields(obj)
        elif isinstance(obj, dict):
            self._encode_dict_as_struct(obj)
        else:
            self.encode_value(obj, tag=0)

        return self._writer.get_bytes()

    def encode_value(self, value: Any, tag: int) -> None:
        """使用标签编码单个值.

        Args:
            value: 要编码的值.
            tag: JCE标签ID.

        Raises:
            JceEncodeError: 如果检测到循环引用或类型无法编码.
        """
        if value is None:
            return

        # Check for circular references in container types
        if isinstance(value, (list, dict)) or hasattr(value, "__jce_fields__"):
            obj_id = id(value)
            if obj_id in self._encoding_stack:
                raise JceEncodeError(
                    f"Circular reference detected while encoding {type(value).__name__}"
                )
            self._encoding_stack.add(obj_id)
            try:
                self._encode_container(value, tag)
            finally:
                self._encoding_stack.discard(obj_id)
        else:
            # Primitive types - no circular reference possible
            self._encode_primitive(value, tag)

    def _encode_primitive(self, value: Any, tag: int) -> None:
        """编码原始(非容器)值."""
        if isinstance(value, bool):
            # Bool被编码为INT(0或1)
            self._writer.write_int(tag, int(value))
        elif isinstance(value, int):
            self._writer.write_int(tag, value)
        elif isinstance(value, float):
            # Float还是Double? Python float是double.
            # 为了精度,我们默认为DOUBLE(类型5)?
            # 1.md says FLOAT(4 bytes) and DOUBLE(8 bytes).
            # Python float is C double.
            self._writer.write_double(tag, value)
        elif isinstance(value, str):
            self._writer.write_string(tag, value)
        elif isinstance(value, (bytes, bytearray, memoryview)):
            self._writer.write_bytes(tag, bytes(value))
        else:
            if self._default:
                new_val = self._default(value)
                self.encode_value(new_val, tag)
            else:
                raise JceEncodeError(f"Cannot encode type: {type(value)}")

    def _encode_container(self, value: Any, tag: int) -> None:
        """编码容器类型(列表、字典或结构体)."""
        if isinstance(value, list):
            self._writer.write_list(tag, value, self)
        elif isinstance(value, dict):
            self._writer.write_map(tag, value, self)
        elif hasattr(value, "__jce_fields__"):
            # 嵌套结构体
            self._writer.write_struct_begin(tag)
            self._encode_struct_fields(value)
            self._writer.write_struct_end()
        else:
            raise JceEncodeError(f"Cannot encode container type: {type(value)}")

    def _encode_struct_fields(self, obj: Any) -> None:
        # 遍历JceStruct字段
        fields = getattr(obj, "__jce_fields__", {})
        # fields is dict[str, JceModelField]

        for name, field in fields.items():
            val = getattr(obj, name)

            # Check default value
            if self._option & OPT_OMIT_DEFAULT:
                # 需要检查val == default
                pass

            self.encode_value(val, field.jce_id)

    def _encode_dict_as_struct(self, obj: dict[Any, Any]) -> None:
        # 键必须是int(标签)
        for tag, val in obj.items():
            if not isinstance(tag, int):
                raise JceEncodeError(
                    f"Dict keys must be int tags for struct encoding, got {type(tag)}"
                )
            self.encode_value(val, tag)
