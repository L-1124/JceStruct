"""JCE命令行工具."""

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from . import BytesMode, loads

if TYPE_CHECKING:
    import click as click_module
else:
    try:
        import click as click_module
    except ImportError:
        click_module = None

click = click_module

# 流式读取配置
FILE_SIZE_THRESHOLD = 10 * 1024 * 1024  # 10MB
CHUNK_SIZE = 8 * 1024 * 1024  # 8MB


if click:

    def _read_binary_file(file_path: Path, verbose: bool) -> bytes:
        """读取二进制文件,大文件使用分块以控制内存.

        Args:
            file_path: 文件路径.
            verbose: 是否显示详细信息.

        Returns:
            文件内容的bytes.
        """
        file_size = file_path.stat().st_size

        if file_size > FILE_SIZE_THRESHOLD:
            if verbose:
                click.echo(f"[DEBUG] 文件大小 {file_size} 字节,使用分块读取", err=True)

            chunks = []
            with open(file_path, "rb") as f:
                while chunk := f.read(CHUNK_SIZE):
                    chunks.append(chunk)
            return b"".join(chunks)
        return file_path.read_bytes()

    def _read_hex_file(file_path: Path, verbose: bool) -> bytes:
        """读取并解析十六进制文本文件.

        Args:
            file_path: 文件路径.
            verbose: 是否显示详细信息.

        Returns:
            解析后的bytes.

        Raises:
            ValueError: 如果文件内容不是有效的十六进制字符串.
        """
        file_size = file_path.stat().st_size

        if file_size > FILE_SIZE_THRESHOLD:
            if verbose:
                click.echo(f"[DEBUG] 文件大小 {file_size} 字节,使用分块读取", err=True)

            hex_parts = []
            with open(file_path, encoding="utf-8") as f:
                for line in f:
                    hex_parts.append(line.strip())
            hex_data = "".join(hex_parts)
        else:
            hex_data = file_path.read_text(encoding="utf-8").strip()

        # 验证并清理
        cleaned = "".join(hex_data.split())
        if not all(c in "0123456789abcdefABCDEF" for c in cleaned):
            raise ValueError("不是有效的十六进制字符串")

        return bytes.fromhex(cleaned)

    def _decode_and_print(
        data: bytes,
        output_format: str,
        output_file: str | None,
        verbose: bool,
        bytes_mode: str,
    ) -> None:
        """解码并输出结果."""
        # 延迟导入以避免循环依赖
        from .decoder import DataReader, JceNode, NodeDecoder

        def _print_node_tree(nodes: list[JceNode], file: Any = None) -> None:
            """递归打印节点树."""

            def _print_recursive(node: JceNode, prefix: str, indent_level: int) -> None:
                indent = "   " * indent_level

                # 计算当前标签
                if node.tag is not None:
                    current_id = f"{prefix}{node.tag}"
                else:
                    # 对于列表/Map元素，如果没有标签，使用prefix作为ID
                    current_id = prefix

                # 计算类型名称
                type_str = node.type_name
                if node.length is not None:
                    type_str += f"={node.length}"

                # 打印逻辑
                if node.type_name == "Struct":
                    click.echo(f"{indent}[{current_id}]┓", file=file)
                    for child in cast(list[JceNode], node.value):
                        _print_recursive(
                            child,
                            prefix=f"{current_id}.",
                            indent_level=indent_level + 1,
                        )
                    click.echo(f"{indent}[{current_id}]┛", file=file)

                elif node.type_name == "List":
                    click.echo(f"{indent}[{current_id}]({type_str})", file=file)
                    for i, child in enumerate(cast(list[JceNode], node.value)):
                        _print_recursive(
                            child,
                            prefix=f"{current_id}[{i}]",
                            indent_level=indent_level + 1,
                        )

                elif node.type_name == "Map":
                    click.echo(f"{indent}[{current_id}]({type_str})", file=file)
                    for i, (k, v) in enumerate(
                        cast(list[tuple[JceNode, JceNode]], node.value)
                    ):
                        _print_recursive(
                            k,
                            prefix=f"{current_id}[{i}].key",
                            indent_level=indent_level + 1,
                        )
                        _print_recursive(
                            v,
                            prefix=f"{current_id}[{i}].val",
                            indent_level=indent_level + 1,
                        )

                elif node.type_name == "SimpleList":
                    val = node.value
                    if isinstance(val, list):
                        # 递归解析成功的 SimpleList
                        click.echo(f"{indent}[{current_id}]({type_str})┓", file=file)
                        for child in cast(list[JceNode], val):
                            # 递归打印子节点
                            _print_recursive(
                                child,
                                prefix=f"{current_id}.",
                                indent_level=indent_level + 1,
                            )
                        click.echo(f"{indent}[{current_id}]┛", file=file)
                    else:
                        # 普通字节数组
                        val_str = bytes(val).hex(" ").upper()
                        click.echo(
                            f"{indent}[{current_id}]({type_str}):{val_str}", file=file
                        )

                else:
                    # 值格式化
                    val = node.value
                    if isinstance(val, bytes | bytearray | memoryview):
                        val_str = bytes(val).hex(" ").upper()
                    else:
                        val_str = str(val)

                    click.echo(
                        f"{indent}[{current_id}]({type_str}):{val_str}", file=file
                    )

            for node in nodes:
                _print_recursive(node, prefix="", indent_level=0)

        def _validate_bytes_mode(mode: str) -> None:
            """验证 bytes-mode 参数."""
            if mode not in {"auto", "string", "raw"}:
                raise click.BadParameter("bytes-mode 只能为 auto/string/raw")

        if verbose:
            click.echo(f"[DEBUG] 数据大小: {len(data)} 字节", err=True)

        if output_format == "tree":
            try:
                reader = DataReader(data)
                decoder = NodeDecoder(reader)
                nodes = decoder.decode(suppress_log=not verbose)

                if output_file:
                    with open(output_file, "w", encoding="utf-8") as f:
                        _print_node_tree(nodes, file=f)
                    click.echo(f"结果已保存到: {output_file}", err=True)
                else:
                    _print_node_tree(nodes)
                return
            except Exception as e:
                if verbose:
                    import traceback

                    traceback.print_exc(file=sys.stderr)
                raise click.ClickException(f"Tree解码失败: {e}") from e

        # 解码
        try:
            _validate_bytes_mode(bytes_mode)
            result = loads(
                data,
                target=dict,
                bytes_mode=cast(BytesMode, bytes_mode),
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
        type=click.Choice(["pretty", "json", "tree"]),
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
          jce "0a0b0c"

          # 从文件读取十六进制数据
          jce -f input.hex

          # 以 JSON 格式输出结果
          jce -f input.hex --format json
        """
        # 互斥参数检查
        if encoded and file_path:
            raise click.UsageError("不能同时指定 ENCODED 数据和 --file 参数")
        if not encoded and not file_path:
            raise click.UsageError("必须指定 ENCODED 数据或 --file 参数")

        # 获取二进制数据
        if file_path:
            try:
                # 尝试hex文本模式
                data = _read_hex_file(file_path, verbose)
                if verbose:
                    click.echo("[DEBUG] 从文件读取十六进制数据 (文本模式)", err=True)
            except (UnicodeDecodeError, ValueError):
                # 降级到二进制模式
                data = _read_binary_file(file_path, verbose)
                if verbose:
                    click.echo("[DEBUG] 从文件读取二进制数据 (二进制模式)", err=True)
        else:
            # 命令行参数: hex字符串
            assert encoded is not None
            try:
                data = bytes.fromhex(encoded)
            except ValueError as e:
                if verbose:
                    import traceback

                    traceback.print_exc(file=sys.stderr)
                raise click.BadParameter(f"无效的十六进制格式 - {e}") from e

        _decode_and_print(data, output_format, output_file, verbose, bytes_mode)

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
