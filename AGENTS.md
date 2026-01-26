# JceStruct

基于 Pydantic v2 的 JCE 协议实现。Rust 核心 (PyO3/maturin) + Python API。混合 Python/Rust 单体仓库。

## 项目结构

```tree
JceStruct/
├── python/jce/        # Python 包 (公开 API) → 见 python/AGENTS.md
├── python/tests/      # Pytest 测试套件 (扁平结构, test_*.py 模式)
├── src/               # Rust 核心 (PyO3 扩展: dumps/loads/stream)
├── docs/              # MkDocs 文档 (api/, usage/)
├── Cargo.toml         # 根 Rust crate (edition 2024, cdylib+rlib)
├── pyproject.toml     # Maturin 配置 + 打包
└── .github/workflows/ # CI: uv 编排的测试 + 发布
```

## 快速导航

| 任务            | 位置                                        | 备注                                       |
|-----------------|---------------------------------------------|--------------------------------------------|
| 定义结构体      | `python/jce/struct.py`                      | `JceStruct`, `JceField`, `JceDict`         |
| 序列化/反序列化 | `python/jce/api.py`                         | `dumps`/`loads`, `dump`/`load`             |
| 流式处理        | `python/jce/stream.py` + `src/stream.rs`    | TCP 粘包/拆包, LengthPrefixed              |
| Rust 编解码     | `src/serde.rs`                              | 核心逻辑: `dumps`/`loads`, `MAX_DEPTH=100` |
| 错误处理        | `src/error.rs` + `python/jce/exceptions.py` | Rust → Python 映射                         |
| 类型常量        | `src/consts.rs` + `python/jce/const.py`     | JCE 协议类型码                             |
| CLI 工具        | `python/jce/__main__.py`                    | 基于 Click, hex 解码/格式化                |
| 测试            | `python/tests/test_protocol.py`             | 核心协议验证 (根测试)                      |
| 构建配置        | `pyproject.toml` (maturin) + `Cargo.toml`   | 模块名: `jce._jce_core`                    |
| CI/CD           | `.github/workflows/`                        | uv sync, git-cliff changelog               |
| 文档            | `docs/` (源) + `site/` (构建)               | MkDocs Material, 中文                      |

## 命令

```bash
# 环境 (uv workspace)
uv sync                      # 安装所有 (Python + Rust 构建)

# Rust 核心
cargo test                   # Rust 单元测试
cargo clippy                 # Lint

# 文档
uv run --group docs mkdocs serve          # 预览 http://127.0.0.1:8000
uv run --group docs mkdocs build          # 生成到 site/

# 构建
uv build                     # Wheel (通过 maturin)
```

## 规范约定

**语言与风格:**

- 文档/注释: 中文, 半角标点
- Docstrings: Google 风格
- 行长: 88 (Ruff 强制)
- 命名: `snake_case` (函数), `PascalCase` (类), `UPPER_SNAKE_CASE` (常量)

**测试:**

- 框架: pytest ≥9.0
- 风格: 函数式 (`def test_*()`), 禁止类式
- 位置: `python/tests/` (扁平结构)
- 发现: `test_*.py` 模式
- 参数化: `pytest.mark.parametrize` 配合 `ids`
- **根测试**: `test_protocol.py` 必须 100% 通过 (破坏 = 破坏性变更)

**Python/Rust 互操作:**

- 模块名: `jce._jce_core` (maturin → PyO3)
- 错误映射: `src/serde.rs:map_decode_error` → `jce.exceptions.JceDecodeError`
- 上下文传递: Rust `context: Bound<PyAny>` ↔ Python `SerializationInfo`
- 流式处理: Rust `LengthPrefixedReader/Writer` ↔ Python 包装器在 `jce/stream.py`

## 反模式 (本项目禁止)

| 类别       | 禁止操作                            | 原因                               |
|------------|-------------------------------------|------------------------------------|
| 类型安全   | `as any`, `# type: ignore` (无说明) | 破坏类型保证                       |
| Rust panic | Rust 代码中 `panic!`                | 应返回 `PyResult` 或 `Result`      |
| 异常处理   | 空 `except: pass`                   | 静默失败                           |
| 测试       | 删除失败测试                        | 掩盖 bug                           |
| JCE 标签   | 结构体内重复 `jce_id`               | 协议违规                           |
| Git        | 未经明确要求提交                    | 禁止主动提交 (见 python/AGENTS.md) |

## 架构说明

**混合单体仓库:**

- Rust crate **位于仓库根目录** (`src/` + `Cargo.toml`)
- 无 Cargo `[workspace]` 节 (单 crate 设置, 尽管多语言)
- Python 包在 `python/jce/`, 测试在 `python/tests/`
- Maturin 从根 Rust crate 构建扩展模块 `jce._jce_core`

**构建系统:**

- **maturin** (PyO3 扩展构建器): `module-name = "jce._jce_core"`, `python-source = "python"`
- **uv**: Python 依赖 + Rust 构建触发的工作区编排器
- **Ruff**: Lint + 格式化 (88 行长, 广泛规则集加忽略项)
- **CI**: 基于 uv (`uv sync` → `uv run pytest`), git-cliff 生成 changelog

**关键限制:**

- `MAX_DEPTH = 100` (递归深度, `src/serde.rs`)
- 联合类型: `T | None` ✓, `T1 | T2` ✗ (定义时抛 `TypeError`)

## uv 环境特别说明

**问题**: venv 中 `cargo test` 失败
**修复**:

```bash
python -c "import sys; print(sys.base_prefix)"  # 查找 uv Python 基目录
export PATH="/f/uv/python/cpython-3.12.11-windows-x86_64-none:$PATH"
cargo test
```

**受影响**: `cargo test`, `cargo run --bin stub_gen`
**不受影响**: `maturin develop`, `maturin build` (延迟绑定)

相关: [uv#11006](https://github.com/astral-sh/uv/issues/11006), [PyO3#3589](https://github.com/PyO3/pyo3/issues/3589)

## 子目录指南

- [`python/AGENTS.md`](python/AGENTS.md) — Python 包详情, 数据建模, 测试协议
