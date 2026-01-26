"""JCE序列化和反序列化的配置选项.

该模块定义了用于控制 `dumps` 和 `loads` 函数行为的选项标志.
"""

from enum import IntFlag


class JceOption(IntFlag):
    """JCE 配置选项标志.

    可以使用位运算组合多个选项:
        option = JceOption.LITTLE_ENDIAN | JceOption.ZERO_COPY
    """

    # 默认行为: 网络字节序(大端模式)
    NONE = 0x0000

    # 强制小端字节序(非标准JCE)
    LITTLE_ENDIAN = 0x0001

    # 强制严格的JCE映射要求: 键标签=0, 值标签=1
    STRICT_MAP = 0x0002

    # 允许序列化None值(默认情况下通常跳过)
    SERIALIZE_NONE = 0x0004

    # 零复制模式: 在可能的地方返回memoryview切片而不是字节
    ZERO_COPY = 0x0010

    # 在序列化过程中省略默认值以节省带宽
    OMIT_DEFAULT = 0x0020
