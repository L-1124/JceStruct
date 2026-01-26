"""测试 JCE 命令行工具."""

import json
import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from jce import JceField, JceStruct, dumps, types

try:
    from jce.__main__ import cli
except ImportError:
    pytest.skip("click not installed", allow_module_level=True)


class SimpleCliStruct(JceStruct):
    """CLI 测试用简单结构体."""

    name: str = JceField(jce_id=1, jce_type=types.STRING1)
    val: int = JceField(jce_id=2, jce_type=types.INT32)


class ComplexCliStruct(JceStruct):
    """CLI 测试用复杂结构体."""

    id: int = JceField(jce_id=0, jce_type=types.INT32)
    data: bytes = JceField(jce_id=1, jce_type=types.BYTES)
    items: list[int] = JceField(jce_id=2, jce_type=types.LIST)
    mapping: dict[str, str] = JceField(jce_id=3, jce_type=types.MAP)


@pytest.fixture
def runner() -> CliRunner:
    """提供 Click CLI 测试运行器.

    Returns:
        CliRunner 实例.
    """
    return CliRunner()


def strip_ansi(text: str) -> str:
    """去除 ANSI 转义序列."""
    ansi_escape = re.compile(r"\x1B(?:[@-Z\-_]|\[[0-?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text)


# --- 基础 CLI 功能测试 ---


def test_cli_help(runner: CliRunner) -> None:
    """--help 选项应显示帮助信息."""
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "Usage:" in result.output


def test_cli_missing_input(runner: CliRunner) -> None:
    """未提供输入参数时应报错并提示用法."""
    result = runner.invoke(cli, [])

    assert result.exit_code != 0
    assert "必须指定" in result.output


def test_cli_mutual_exclusion(runner: CliRunner) -> None:
    """同时提供参数和文件时应报错."""
    with runner.isolated_filesystem():
        Path("test.bin").write_text("00", encoding="utf-8")

        result = runner.invoke(cli, ["00", "-f", "test.bin"])

        assert result.exit_code != 0
        assert "不能同时指定" in result.output


def test_cli_decode_hex_string(runner: CliRunner) -> None:
    """应能正确解码命令行参数提供的十六进制字符串."""
    result = runner.invoke(cli, ["0064"])

    assert result.exit_code == 0
    assert "100" in result.output


def test_cli_decode_file(runner: CliRunner) -> None:
    """应能正确从文件中读取并解码数据."""
    with runner.isolated_filesystem():
        Path("data.txt").write_text("0064", encoding="utf-8")

        result = runner.invoke(cli, ["-f", "data.txt"])

        assert result.exit_code == 0
        assert "100" in result.output


def test_cli_output_file(runner: CliRunner) -> None:
    """应能将解码结果保存到指定文件."""
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["0064", "-o", "out.txt"])

        assert result.exit_code == 0
        content = Path("out.txt").read_text(encoding="utf-8")
        assert "100" in content


def test_cli_format_json(runner: CliRunner) -> None:
    """--format json 选项应输出合法的 JSON 数据."""
    result = runner.invoke(cli, ["0064", "--format", "json"])

    assert result.exit_code == 0
    # 去除ANSI码后解析JSON
    clean_output = strip_ansi(result.output)
    data = json.loads(clean_output)
    assert str(data["0"]) == "100" or data["0"] == 100


def test_cli_invalid_hex(runner: CliRunner) -> None:
    """提供无效的十六进制字符串时应报错."""
    result = runner.invoke(cli, ["zz"])

    assert result.exit_code != 0
    assert "无效的十六进制格式" in result.output


def test_cli_decode_error(runner: CliRunner) -> None:
    """解码过程中发生错误时应优雅退出并显示错误信息."""
    result = runner.invoke(cli, ["0201"])

    assert result.exit_code != 0
    assert "解码失败" in result.output


def test_cli_verbose_output(runner: CliRunner) -> None:
    """-v 选项应在出错时显示详细堆栈信息."""
    result = runner.invoke(cli, ["0201", "-v"])

    assert result.exit_code != 0
    assert "Traceback" in result.output


def test_cli_bytes_mode(runner: CliRunner) -> None:
    """--bytes-mode 选项应能控制字节数据的显示方式."""
    hex_data = "060376616c"

    result = runner.invoke(cli, [hex_data, "--bytes-mode", "raw"])

    assert result.exit_code == 0
    assert "b'val'" in result.output or "val" in result.output


# --- Tree 格式输出测试 ---


def test_cli_tree_simple(runner: CliRunner) -> None:
    """简单结构体的树状输出应正确显示字段."""
    data = SimpleCliStruct(name="test", val=123)
    encoded = dumps(data).hex()

    result = runner.invoke(cli, [encoded, "--format", "tree"])

    assert result.exit_code == 0
    clean_output = strip_ansi(result.output)
    # Rich 树格式检查
    assert "[1] String: 'test'" in clean_output
    assert "[2] int: 123" in clean_output


def test_cli_tree_recursive_simplelist(runner: CliRunner) -> None:
    """SimpleList 的递归解析应正确显示嵌套结构."""
    inner = SimpleCliStruct(name="inner", val=999)
    inner_bytes = dumps(inner)
    outer = ComplexCliStruct(
        id=100, data=inner_bytes, items=[1, 2, 3], mapping={"key": "val"}
    )
    encoded = dumps(outer).hex()

    result = runner.invoke(cli, [encoded, "--format", "tree"])

    assert result.exit_code == 0
    clean_output = strip_ansi(result.output)

    assert "[0] int: 100" in clean_output
    assert "[1] JceStruct" in clean_output or "[1] Map" in clean_output

    if "[1] JceStruct" in clean_output:
        assert "[1] String: 'inner'" in clean_output
        assert "[2] int: 999" in clean_output
    else:
        # Fallback to Map representation if decoded as generic dict
        assert "Key int: 1" in clean_output
        assert "Value String: 'inner'" in clean_output
        assert "Key int: 2" in clean_output
        assert "Value int: 999" in clean_output

    assert "[2] List (len=3)" in clean_output
    assert "[0] int: 1" in clean_output
    assert "Key String: 'key'" in clean_output
    assert "Value String: 'val'" in clean_output


def test_cli_tree_invalid_data(runner: CliRunner) -> None:
    """无效数据的树状输出应报错."""
    result = runner.invoke(cli, ["ZZZZ", "--format", "tree"])
    assert result.exit_code != 0
    assert "无效的十六进制格式" in result.output

    result = runner.invoke(cli, ["0E", "--format", "tree"])
    assert result.exit_code != 0
    assert "解码失败" in result.output


def test_cli_tree_output_file(runner: CliRunner, tmp_path: Path) -> None:
    """树状输出应能正确保存到文件."""
    data = SimpleCliStruct(name="file_test", val=456)
    encoded = dumps(data).hex()
    output_file = tmp_path / "output.txt"

    result = runner.invoke(
        cli, [encoded, "--format", "tree", "--output", str(output_file)]
    )

    assert result.exit_code == 0
    assert f"结果已保存到: {output_file}" in result.output
    content = output_file.read_text(encoding="utf-8")

    assert "[1] String: 'file_test'" in content
    assert "[2] int: 456" in content


# --- 文件格式检测测试 ---


def test_cli_file_hex_with_spaces(runner: CliRunner, tmp_path: Path) -> None:
    """应能读取带空格的十六进制文件."""
    hex_file = tmp_path / "test_hex.txt"
    hex_file.write_text("00 64", encoding="utf-8")

    result = runner.invoke(cli, ["-f", str(hex_file), "--format", "json"])

    assert result.exit_code == 0
    clean_output = strip_ansi(result.output)
    assert "100" in clean_output or "64" in clean_output


def test_cli_file_hex_without_spaces(runner: CliRunner, tmp_path: Path) -> None:
    """应能读取无空格的十六进制文件."""
    hex_file = tmp_path / "test_hex_no_spaces.txt"
    hex_file.write_text("0064", encoding="utf-8")

    result = runner.invoke(cli, ["-f", str(hex_file), "--format", "json"])

    assert result.exit_code == 0
    clean_output = strip_ansi(result.output)
    assert "100" in clean_output or "64" in clean_output


def test_cli_file_binary(runner: CliRunner, tmp_path: Path) -> None:
    """应能自动检测并读取二进制文件."""
    bin_file = tmp_path / "test_binary.bin"
    bin_file.write_bytes(bytes.fromhex("0064"))

    result = runner.invoke(cli, ["-f", str(bin_file), "--format", "json"])

    assert result.exit_code == 0
    clean_output = strip_ansi(result.output)
    assert "100" in clean_output or "64" in clean_output


def test_cli_file_hex_verbose_shows_text_mode(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Verbose 模式应显示十六进制文件使用文本模式读取."""
    hex_file = tmp_path / "test_hex.txt"
    hex_file.write_text("00 64", encoding="utf-8")

    result = runner.invoke(cli, ["-f", str(hex_file), "-v", "--format", "json"])

    assert result.exit_code == 0
    assert "文本模式" in result.output


def test_cli_file_binary_verbose_shows_binary_mode(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Verbose 模式应显示二进制文件使用二进制模式读取."""
    bin_file = tmp_path / "test_binary.bin"
    bin_file.write_bytes(bytes.fromhex("0064"))

    result = runner.invoke(cli, ["-f", str(bin_file), "-v", "--format", "json"])

    assert result.exit_code == 0
    assert "二进制模式" in result.output


def test_cli_file_multiline_hex(runner: CliRunner, tmp_path: Path) -> None:
    """应能处理多行十六进制文件."""
    hex_file = tmp_path / "multiline.txt"
    hex_file.write_text(
        """
        00
        64
        """,
        encoding="utf-8",
    )

    result = runner.invoke(cli, ["-f", str(hex_file), "--format", "json"])

    assert result.exit_code == 0
    clean_output = strip_ansi(result.output)
    assert "100" in clean_output or "64" in clean_output


def test_cli_file_non_hex_treated_as_binary(runner: CliRunner, tmp_path: Path) -> None:
    """包含非十六进制字符的文本文件应被当作二进制处理."""
    invalid_file = tmp_path / "invalid.txt"
    invalid_file.write_text("Hello World! 这不是十六进制", encoding="utf-8")

    result = runner.invoke(cli, ["-f", str(invalid_file), "-v"])

    assert "二进制模式" in result.output


# --- 大文件流式读取测试 ---


def test_cli_file_large_binary_triggers_chunked_reading(
    runner: CliRunner, tmp_path: Path
) -> None:
    """大二进制文件应触发分块读取模式."""
    large_file = tmp_path / "large.bin"
    # 创建 >10MB 的有效JCE数据
    # 使用简单的单字节值重复,确保解码不会失败
    single_value = bytes.fromhex("0064")  # {0: 100}
    # 重复约6M次 = ~12MB
    data = single_value * (6 * 1024 * 1024)
    large_file.write_bytes(data)

    result = runner.invoke(cli, ["-f", str(large_file), "-v"])

    # 验证触发了分块读取
    assert "使用分块读取" in result.output
    assert "二进制模式" in result.output


def test_cli_file_large_hex_triggers_chunked_reading(
    runner: CliRunner, tmp_path: Path
) -> None:
    """大十六进制文本文件应触发分块读取模式."""
    large_file = tmp_path / "large.hex"
    # 创建 >10MB 的十六进制文本
    # 每行一个简单的hex值
    hex_line = "00 64\n"
    # 大约需要 10MB / 6 bytes ≈ 1.7M 行
    lines = [hex_line] * (2 * 1024 * 1024)  # 2M行 ≈ 12MB
    large_file.write_text("".join(lines), encoding="utf-8")

    result = runner.invoke(cli, ["-f", str(large_file), "-v"])

    # 验证触发了分块读取
    assert "使用分块读取" in result.output
    assert "文本模式" in result.output
