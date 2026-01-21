"""JCE序列化上下文.

该模块定义了在序列化和反序列化过程中传递的上下文信息.
这允许自定义序列化逻辑访问外部状态(如配置、密钥等).
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SerializationInfo:
    """传递给自定义序列化函数的上下文信息.

    Attributes:
        option: 序列化选项(位掩码)
        context: 用户提供的上下文数据
        field_name: 当前字段的名称
        jce_id: 当前字段的JCE ID
    """

    # 序列化选项(位掩码)
    option: int = 0
    # 用户提供的上下文数据
    context: dict[str, Any] = field(default_factory=dict)
    # 当前字段的名称
    field_name: str | None = None
    # 当前字段的JCE ID
    jce_id: int | None = None


@dataclass
class DeserializationInfo:
    """传递给自定义反序列化函数的上下文信息.

    Attributes:
        option: 反序列化选项(位掩码)
        context: 用户提供的上下文数据
        field_name: 当前字段的名称
        jce_id: 当前字段的JCE ID
    """

    # 反序列化选项(位掩码)
    option: int = 0
    # 用户提供的上下文数据
    context: dict[str, Any] = field(default_factory=dict)
    # 当前字段的名称
    field_name: str | None = None
    # 当前字段的JCE ID
    jce_id: int | None = None
