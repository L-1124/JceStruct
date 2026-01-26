# JceStruct Agent 指南

**Generated:** 2026-01-26
**Commit:** 3d3f530
**Branch:** feat/rust-core

本文档为在 JceStruct 仓库工作的 AI Agent 提供必要的上下文和规则.

**包名**: `jce` (Python 模块)
**当前版本**: `jce/__init__.py` 中的 `__version__` 变量

## 概览

JceStruct 是基于 Pydantic v2 的 JCE 协议 Python 实现, 核心编解码由 Rust 扩展 (`jce-core`) 驱动.

```tree
JceStruct/
├── jce/              # Python 包 (公开 API)
├── jce-core/         # Rust 核心扩展 (PyO3/maturin) → 见 jce-core/AGENTS.md
├── tests/            # pytest 测试 (扁平结构)
├── docs/             # MkDocs 文档源
└── .github/workflows # CI: testing.yml, release.yml
```

## 快速导航

| 任务       | 位置                |                 备注                 |
|------------|---------------------|:------------------------------------:|
| 定义结构体 | `jce/struct.py`     |  `JceStruct`, `JceField`, `JceDict`  |
| 序列化 API | `jce/api.py`        |    `dumps`/`loads`, `dump`/`load`    |
| 类型定义   | `jce/types.py`      | `INT`, `BYTES`, `STRING` 等 JCE 类型 |
| 流式处理   | `jce/stream.py`     |    `LengthPrefixedReader`/`Writer`   |
| CLI 工具   | `jce/__main__.py`   |    Click-based, 需 `[cli]` extras    |
| 异常       | `jce/exceptions.py` |              6 个异常类              |
| Rust 核心  | `jce-core/src/`     |          编解码、流处理实现          |
| 协议规范   | `JCE_PROTOCOL.md`   |             协议格式参考             |

## 命令

```bash
# 包管理 (uv)
uv sync --all-groups --all-extras   # 安装所有依赖
uv pip install -e .[cli]            # 安装含 CLI

# 测试
uv run pytest                       # 运行测试 (含覆盖率)
uv run pytest tests/test_struct.py  # 单文件
uv run pytest -k "test_loads"       # 按名称过滤

# 代码检查
uv run ruff check .                 # Lint
uv run ruff format .                # 格式化
uvx basedpyright                    # 类型检查

# 文档
uv run mkdocs serve                 # 本地预览 http://127.0.0.1:8000
uv run mkdocs build                 # 构建到 site/

# Rust 核心 (在 jce-core/ 下)
maturin develop                     # 开发构建
cargo test                          # Rust 测试
```

## 代码规范

### 语言与风格

- **文档/注释**: 中文, 半角标点
- **Docstrings**: Google 风格
- **行长**: 88 字符 (Ruff 强制)
- **缩进**: 4 空格

### 测试命名

| 类型      | 规范               |             示例             |
|-----------|--------------------|:----------------------------:|
| 类        | `PascalCase`       |    `JceStruct`, `JceField`   |
| 函数/方法 | `snake_case`       | `model_validate`, `to_bytes` |
| 常量      | `UPPER_SNAKE_CASE` |      `OPT_LITTLE_ENDIAN`     |
| 私有      | `_` 前缀           |           `_buffer`          |

### 导入

- **相对导入**: `from .types import INT`
- **排序**: 标准库 → 第三方 (pydantic) → 本地 (jce)

### 类型提示

- 严格使用, 所有公开 API 必须标注
- 泛型: `list[T]`, `dict[K, V]` (Python 3.10+ 风格)

## 架构要点

### 核心组件

| 模块              |                     职责                     |
|-------------------|:--------------------------------------------:|
| `jce/__init__.py` |      公开 API 入口, 导出所有核心类/函数      |
| `jce/api.py`      |  高层 API (`dumps`/`loads`), 桥接 Rust 核心  |
| `jce/struct.py`   | `JceStruct` 基类, `JceField` 工厂, `JceDict` |
| `jce/types.py`    |     JCE 类型定义 (`JceType` 及各类型实现)    |
| `jce/stream.py`   |           流式 API (基于 Rust 核心)          |
| `jce_core`        |           Rust 扩展: 编解码、流处理          |

### 数据建模

- `JceStruct` 继承自 `pydantic.BaseModel`
- 使用类型注解 + `JceField` 定义字段
- `jce_id` (Tag) 必填且在结构体内唯一

### 联合类型限制

- `T | None`: 支持
- `T1 | T2`: **不支持** (定义时抛 `TypeError`)

### JceDict vs dict

- `JceDict({0: 100})` → 编码为 JCE Struct
- `dict({0: 100})` → 编码为 JCE Map
- **警告**: 传错类型给 `Any` 字段会导致解码失败

### bytes_mode 参数

- `"raw"`: 保持原始字节
- `"string"`: 尝试 UTF-8 转换
- `"auto"`: (默认) 智能模式, 尝试嵌套解析

### 流式 API

- `LengthPrefixedWriter`: 自动添加长度头
- `LengthPrefixedReader`: 处理 TCP 粘包/拆包

## 测试约定

### 风格

- **框架**: pytest (v9.0+)
- **模式**: 函数式 (`def test_xxx()`), 禁止类式
- **位置**: `tests/` (扁平结构, 无子目录)
- **原子性**: 一个函数只验证一个行为

### 命名

- **文件**: `test_<模块>.py`
- **函数**: `test_<函数>_<预期行为>`

### 核心协议测试

`test_protocol.py` 是根本性测试, 必须 100% 通过. 任何破坏其用例的修改视为破坏性变更.

### 参数化

使用 `pytest.mark.parametrize` + `ids` 增强可读性:

```python
@pytest.mark.parametrize(
    ("val", "expected"),
    [(1, b"\x01"), (127, b"\x7f")],
    ids=["small_int", "max_byte_int"]
)
def test_int_encoding_variants(val: int, expected: bytes) -> None:
    """测试不同范围整数的编码结果."""
    ...
```

## 反模式 (禁止)

| 类别     |                                禁止操作                               |
|----------|:---------------------------------------------------------------------:|
| 类型安全 | `as any`, `@ts-ignore` (仅 Python 类型: 禁止 `# type: ignore` 无说明) |
| 异常处理 |                           空 `except: pass`                           |
| 测试     |                         删除失败测试使其"通过"                        |
| Tag ID   |                         结构体内重复 `jce_id`                         |

## 文档 (MkDocs)

### 结构

- `docs/api/`: API 参考 (mkdocstrings 自动生成)
- `docs/usage/`: 用户指南
- `docs/index.md`: 主页

### 编写规范

- 使用 `::: jce.struct.JceStruct` 语法引用 API
- Admonitions: `!!! warning`, `!!! note`
- 代码块指定语言 + 可选 `title`

## Git 工作流

- **Commit**: Conventional Commits 规范
- **PR 前检查**:
  - `uv run pytest` 测试通过
  - `uv run ruff check` 无错误
  - `uvx basedpyright` 类型检查通过
  - 文档字符串完整
  - `AGENTS.md` 是否需更新

## 子目录指南

- [`jce-core/AGENTS.md`](jce-core/AGENTS.md) - Rust 核心扩展构建与开发
