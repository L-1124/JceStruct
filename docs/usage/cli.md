# 命令行工具 (CLI)

JceStruct 内置了一个强大的命令行工具，用于快速检查、调试和转换 JCE 编码的数据。

## 启用 CLI

CLI 依赖于 `click` 库。如果你在安装时选择了 `[cli]` 额外依赖，就可以直接使用：

```bash
jce --help
```

## 使用方法

### 1. 解码十六进制字符串

直接将 hex 字符串作为参数传递：

```bash
# 解码 Struct (默认)
jce "00 64"
# > {0: 100}

# 解码 Map (需要完整 Map 头)
jce "08 01 00 64"
# > {0: 100}
```

### 2. 读取文件

使用 `-f` 或 `--file` 参数读取包含纯二进制数据或 hex 文本的文件：

```bash
jce -f payload.bin
```

### 3. 输出格式化

默认输出为 Python `pprint` 格式。你可以通过 `--format` 参数选择不同的输出风格：

- **pretty**: (默认) Python 字典格式。
- **json**: 标准 JSON 格式
- **tree**: 层次化树状视图

### 4. 详细模式

使用 `-v` 或 `--verbose` 查看详细的调试信息，包括原始 hex 数据、解码字节数等。

```bash
jce "00 64" -v
# [INFO] Input size: 2 bytes
# [DEBUG] Hex: 00 64
# {0: 100}
```

## 参数参考

```text
Usage: jce [OPTIONS] [ENCODED]

  JCE 编解码命令行工具.

Options:
  -f, --file FILE                从文件读取十六进制编码数据
  --format [pretty|json|tree]    输出格式  [default: pretty]
  -o, --output FILE       将输出保存到文件
  -v, --verbose           显示详细的解码过程信息
  --bytes-mode [auto|string|raw]
                          字节处理模式  [default: auto]
  --help                  Show this message and exit.
```
