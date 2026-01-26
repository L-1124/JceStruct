"""JCE日志记录器."""

import binascii
import logging

logger = logging.getLogger("jce")


def get_hexdump(
    data: bytes | bytearray | memoryview, pos: int, window: int = 16
) -> str:
    """获取指定位置周围数据的十六进制转储."""
    start = max(0, pos - window)
    end = min(len(data), pos + window)
    chunk = data[start:end]

    hex_str = binascii.hexlify(chunk).decode("ascii")
    # 每2个字符插入空格
    hex_str = " ".join(hex_str[i : i + 2] for i in range(0, len(hex_str), 2))

    return f"位置 {pos} 的上下文 (显示 {start}-{end}):\n{hex_str}"
