"""JCE命令行工具."""

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from . import loads

if TYPE_CHECKING:
    import click as click_module
else:
    try:
        import click as click_module
    except ImportError:
        click_module = None  # type: ignore[assignment]

click = click_module


if click:

    def _decode_and_print(
        hex_data: str,
        output_format: str,
        output_file: str | None,
        verbose: bool,
        bytes_mode: str,
    ) -> None:
        """解码并输出结果."""

        def _validate_bytes_mode(mode: str) -> None:
            """验证 bytes-mode 参数."""
            if mode not in {"auto", "string", "raw"}:
                raise click.BadParameter("bytes-mode 只能为 auto/string/raw")

        if verbose:
            click.echo(f"[DEBUG] 原始十六进制数据: {hex_data}", err=True)

        # 验证十六进制格式
        try:
            encoded_bytes = bytes.fromhex(hex_data)
        except ValueError as e:
            if verbose:
                import traceback

                traceback.print_exc(file=sys.stderr)
            raise click.BadParameter(f"无效的十六进制格式 - {e}") from e

        if verbose:
            click.echo(f"[DEBUG] 解码后的字节数: {len(encoded_bytes)}", err=True)

        # 解码
        try:
            _validate_bytes_mode(bytes_mode)
            # CLI 输出总是普通 dict，避免暴露内部 JceDict 语义
            result = loads(
                encoded_bytes,
                target=dict,  # type: ignore[arg-type]
                bytes_mode=bytes_mode,  # type: ignore[arg-type]
            )
        except Exception as e:
            if verbose:
                import traceback

                traceback.print_exc(file=sys.stderr)
            raise click.ClickException(f"解码失败: {e}") from e

        # 格式化输出
        def _json_default(obj: object) -> object:
            if isinstance(obj, bytes | bytearray | memoryview):
                return bytes(obj).hex()
            return str(obj)

        if output_format == "json":
            output = json.dumps(
                result, indent=2, ensure_ascii=False, default=_json_default
            )
        else:
            import pprint

            output = pprint.pformat(result, width=100)

        # 输出结果
        if output_file:
            output_path = Path(output_file)
            output_path.write_text(output, encoding="utf-8")
            click.echo(f"结果已保存到: {output_file}", err=True)
        else:
            click.echo(output)

    @click.command(help="JCE 编解码命令行工具")
    @click.argument("encoded", required=False)
    @click.option(
        "-f",
        "--file",
        "file_path",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        help="从文件读取十六进制编码数据",
    )
    @click.option(
        "--format",
        "output_format",
        type=click.Choice(["pretty", "json"]),
        default="pretty",
        show_default=True,
        help="输出格式",
    )
    @click.option(
        "-o",
        "--output",
        "output_file",
        type=click.Path(dir_okay=False, writable=True),
        help="将输出保存到文件 (如不指定则输出到控制台)",
    )
    @click.option(
        "-v",
        "--verbose",
        is_flag=True,
        help="显示详细的解码过程信息",
    )
    @click.option(
        "--bytes-mode",
        type=click.Choice(["auto", "string", "raw"]),
        default="auto",
        show_default=True,
        help="字节处理模式: auto/string/raw",
    )
    def cli(
        encoded: str | None,
        file_path: Path | None,
        output_format: str,
        output_file: str | None,
        verbose: bool,
        bytes_mode: str,
    ) -> None:
        """JCE 编解码命令行工具.

        Examples:
          # 直接解码十六进制数据
          python -m jce "0a0b0c"

          # 从文件读取十六进制数据
          python -m jce -f input.hex

          # 以 JSON 格式输出结果
          python -m jce -f input.hex --format json
        """
        # 互斥参数检查
        if encoded and file_path:
            raise click.UsageError("不能同时指定 ENCODED 数据和 --file 参数")
        if not encoded and not file_path:
            raise click.UsageError("必须指定 ENCODED 数据或 --file 参数")

        # 获取输入数据
        if file_path:
            hex_data = file_path.read_text().strip()
        else:
            assert encoded is not None
            hex_data = encoded

        _decode_and_print(hex_data, output_format, output_file, verbose, bytes_mode)

    def main() -> None:
        """入口函数."""
        cli()

else:

    def main() -> None:
        """入口函数 (缺少 click)."""
        print("错误: 未安装 'click' 模块.", file=sys.stderr)
        print(
            '请运行 "pip install "jcestruct2[cli]"" 或使用 uv: "uv pip install "jcestruct2[cli]"" 安装命令行支持.',
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
