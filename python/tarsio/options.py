"""JCE序列化和反序列化的配置选项.

该模块定义了用于控制 `dumps` 和 `loads` 函数行为的选项标志.
"""

from enum import IntFlag


class Option(IntFlag):
    """JCE 序列化/反序列化配置选项.

    用于微调 `dumps` 和 `loads` 的行为。
    """

    # 默认行为:
    # 1. 网络字节序 (Big-Endian)
    # 2. 字符串使用 UTF-8 编码
    # 3. 写入默认值 (保守策略，保证接收方一定能收到数据)
    NONE = 0x00

    # --- 序列化选项 (Serialize Options) ---

    # 忽略默认值:
    # 如果字段值等于默认值 (如 0, "", False)，则不写入该 Tag。
    # 这是 JCE 协议推荐的压缩方式，能显著减少包大小。
    OMIT_DEFAULT = 0x01

    # --- 反序列化选项 (Deserialize Options) ---

    # 零拷贝模式:
    # 对于 bytes 类型，返回 memoryview 切片而不是复制内存。
    # 警告: 原始 buffer 释放后，访问该 memoryview 会导致错误，需谨慎使用。
    ZERO_COPY = 0x02
