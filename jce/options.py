"""JCE序列化和反序列化的配置选项.

该模块定义了用于控制 `dumps` 和 `loads` 函数行为的位掩码常量.
"""

# 默认行为：网络字节序（大端模式）
OPT_NETWORK_BYTE_ORDER = 0x0000

# 强制小端字节序（非标准JCE）
OPT_LITTLE_ENDIAN = 0x0001

# 强制严格的JCE映射要求：键标签=0，值标签=1
OPT_STRICT_MAP = 0x0002

# 允许序列化None值（默认情况下通常跳过）
OPT_SERIALIZE_NONE = 0x0004

# 调试选项：将输出格式化为缩进的十六进制字符串（尚未实现）
OPT_INDENT_2 = 0x0008

# 零复制模式：在可能的地方返回memoryview切片而不是字节
OPT_ZERO_COPY = 0x0010

# 在序列化过程中省略默认值以节省带宽
OPT_OMIT_DEFAULT = 0x0020
