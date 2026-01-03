"""JCE命令行工具."""

import argparse
import json
import sys
from pathlib import Path

from jce import loads


def main():
    """运行 JCE 命令行工具."""
    parser = argparse.ArgumentParser(
        description="JCE 编解码命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 直接解码十六进制数据
  python -m jce "0a0b0c"
  
  # 从文件读取十六进制数据
  python -m jce -f input.hex
  
  # 以 JSON 格式输出结果
  python -m jce -f input.hex --format json
  
  # 将输出保存到文件
  python -m jce -f input.hex -o output.json
        """,
    )

    # 输入参数
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "encoded",
        nargs="?",
        metavar="ENCODED",
        type=str,
        help="编码数据 (十六进制格式)",
    )
    input_group.add_argument(
        "-f",
        "--file",
        metavar="FILE",
        type=str,
        help="从文件读取十六进制编码数据",
    )

    # 输出选项
    parser.add_argument(
        "--format",
        choices=["pretty", "json"],
        default="pretty",
        help="输出格式 (默认: pretty)",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        type=str,
        help="将输出保存到文件 (如不指定则输出到控制台)",
    )

    # 调试选项
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="显示详细的解码过程信息",
    )

    args = parser.parse_args()

    try:
        # 获取输入数据
        if args.file:
            file_path = Path(args.file)
            if not file_path.exists():
                print(f"错误: 文件 '{args.file}' 不存在", file=sys.stderr)
                sys.exit(1)
            hex_data = file_path.read_text().strip()
        else:
            hex_data = args.encoded

        if args.verbose:
            print(f"[DEBUG] 原始十六进制数据: {hex_data}", file=sys.stderr)

        # 验证十六进制格式
        try:
            encoded_bytes = bytes.fromhex(hex_data)
        except ValueError as e:
            print(f"错误: 无效的十六进制格式 - {e}", file=sys.stderr)
            sys.exit(1)

        if args.verbose:
            print(
                f"[DEBUG] 解码后的字节数: {len(encoded_bytes)}",
                file=sys.stderr,
            )

        # 解码
        result = loads(encoded_bytes, dict)

        # 格式化输出
        if args.format == "json":
            output = json.dumps(result, indent=2, ensure_ascii=False)
        else:
            import pprint

            output = pprint.pformat(result, width=100)

        # 输出结果
        if args.output:
            output_path = Path(args.output)
            output_path.write_text(output, encoding="utf-8")
            print(f"结果已保存到: {args.output}", file=sys.stderr)
        else:
            print(output)

    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
