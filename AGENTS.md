# Tarsio (formerly JceStruct)

基于 Pydantic v2 的 Tars/JCE 协议实现。
Rust 核心 (PyO3/maturin) + Python API。混合 Python/Rust 单体仓库。

## 项目结构

```tree
Tarsio/
├── python/tarsio/     # Python 包 (公开 API) → 见 python/AGENTS.md
├── python/tests/      # Pytest 测试套件 → 见 python/AGENTS.md
├── src/               # Rust 核心 (PyO3) → 见 src/AGENTS.md
├── docs/              # MkDocs 文档 (api/, usage/)
├── Cargo.toml         # 根 Rust crate
├── pyproject.toml     # Maturin 配置 + 打包
└── .github/workflows/ # CI 工作流
```

## 快速导航

| 领域 | 指南入口 | 关键内容 |
| :--- | :--- | :--- |
| **Python API** | [python/AGENTS.md](python/AGENTS.md) | `Struct`, `dumps`/`loads`, 建模规范 |
| **Rust 核心** | [src/AGENTS.md](src/AGENTS.md) | `codec` (内核), `bindings` (绑定) |
| **测试套件** | [python/AGENTS.md](python/AGENTS.md) | `test_protocol.py`, pytest 策略 |
| **项目文档** | `docs/` | MkDocs Material, 使用手册 |

## 全局命令

```bash
# 环境初始化
uv sync                      # 安装 Python 依赖并触发 Rust 编译

# 文档服务
uv run --group docs mkdocs serve  # 本地实时预览
```

## 全局规范 (强制)

* **语言**: 文档/注释使用中文, 标点使用英文 (半角)。
* **风格**: Python 遵循 Ruff (88 行长), Rust 遵循 rustfmt。
* **提交**: 禁止在未经明确请求时执行 git 提交。
* **Panic**: Rust 严禁 `panic!`, 需返回 `PyResult`。

## 构建与安装 (uv workspace)

```bash
# 环境同步 (安装 Python 依赖并编译 Rust 核心)
uv sync

# 可编辑安装
uv pip install -e .[cli]

# 代码质量
uv run --group linting ruff check .
uv run --group linting ruff format .
uv run --group linting basedpyright
```

## 测试

```bash
uv run pytest                 # Python 全量测试
cargo test                    # Rust 单元测试
```

## 子目录指南

* [**`src/AGENTS.md`**](src/AGENTS.md) — Rust 编解码引擎细节。
* [**`python/AGENTS.md`**](python/AGENTS.md) — Python API 建模、Serialization 以及测试规范。
