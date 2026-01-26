# JceStruct Python 包指南

**包名**: `jce` (Python 模块)
**版本**: `jce/__init__.py` 中的 `__version__` (当前 0.2.2)

## 概览

基于 Pydantic v2 的 JCE 协议 Python API。Rust 核心 (`jce-core`, PyO3/maturin) 处理编解码。

```tree
python/
├── jce/           # 公开 API 包
│   ├── __init__.py    # API 导出 (dumps/loads/JceStruct/...)
│   ├── api.py         # 高层序列化/反序列化
│   ├── struct.py      # JceStruct 基类, JceField, JceDict
│   ├── types.py       # JCE 类型定义 (INT, BYTES, STRING, ...)
│   ├── stream.py      # LengthPrefixedReader/Writer 包装器
│   ├── adapter.py     # JceTypeAdapter (动态 schema)
│   ├── context.py     # SerializationInfo, @jce_field_serializer
│   ├── exceptions.py  # 6 个异常类
│   ├── config.py      # JceConfig
│   ├── options.py     # JceOption 常量
│   ├── const.py       # 协议常量
│   ├── log.py         # 十六进制转储辅助工具
│   └── __main__.py    # CLI 入口点 (Click)
└── tests/         # Pytest 测试套件 (扁平结构)
    ├── test_protocol.py  # **根测试** (必须 100% 通过)
    ├── test_struct.py
    ├── test_api.py
    ├── test_stream.py
    ├── test_adapter.py
    ├── test_generics.py
    ├── test_cli.py
    └── test_log.py
```

## 快速导航

| 任务            | 文件            | 关键符号                                       |
|-----------------|-----------------|------------------------------------------------|
| 定义结构体      | `struct.py`     | `JceStruct`, `JceField()`, `JceDict`           |
| 序列化          | `api.py`        | `dumps(obj, context={})`                       |
| 反序列化        | `api.py`        | `loads(data, schema, bytes_mode="auto")`       |
| 流式处理 (粘包) | `stream.py`     | `LengthPrefixedReader`, `LengthPrefixedWriter` |
| 类型适配器      | `adapter.py`    | `JceTypeAdapter` (运行时 schema)               |
| 字段钩子        | `context.py`    | `@jce_field_serializer("field_name")`          |
| 异常            | `exceptions.py` | `JceDecodeError`, `JceEncodeError` (共 6 个)   |
| JCE 类型        | `types.py`      | `INT`, `BYTES`, `STRING`, `LIST`, `MAP`, ...   |
| 配置            | `config.py`     | `JceConfig(...)`                               |
| CLI             | `__main__.py`   | `jce "0C 00 01" --format json`                 |

## 命令

```bash
# 安装
uv sync                      # 完整工作区 (Python + Rust)
uv pip install -e .[cli]     # 可编辑模式含 CLI

# 测试
uv run pytest                       # 所有测试 + 覆盖率
uv run pytest tests/test_struct.py  # 单个文件
uv run pytest -k test_loads         # 按名称过滤

# Lint/格式化/类型检查
uv run --group linting ruff check .          # Lint
uv run --group linting ruff format .         # 格式化
uv run --group linting basedpyright             # 类型检查

# 文档
uv run --group docs mkdocs serve          # 本地预览 (http://127.0.0.1:8000)
uv run --group docs mkdocs build          # 构建到 site/
```

## 代码风格

- **语言**: 中文 docstrings/注释 (中文, 半角标点)
- **Docstrings**: Google 风格
- **行长**: 88 (Ruff 强制)
- **缩进**: 4 空格
- **命名**:
  - 类: `PascalCase` (`JceStruct`, `JceField`)
  - 函数/方法: `snake_case` (`model_validate`, `to_bytes`)
  - 常量: `UPPER_SNAKE_CASE` (`OPT_LITTLE_ENDIAN`)
  - 私有: `_` 前缀 (`_buffer`)
- **导入**:
  - 相对导入: `from .types import INT`
  - 顺序: 标准库 → 第三方 (pydantic) → 本地 (jce)
- **类型提示**: 公开 API 必须标注; `list[T]`, `dict[K, V]` (3.10+ 风格)

## 数据建模

**JceStruct 基础:**

```python
from jce import JceStruct, JceField

class User(JceStruct):
    uid: int = JceField(jce_id=0)
    name: str = JceField(jce_id=1, default="")
    tags: list[str] = JceField(jce_id=2, default_factory=list)
```

- 继承 `pydantic.BaseModel`
- `jce_id` (Tag) **必填**且在结构体内**唯一**
- 字段类型: 类型注解 + `JceField(...)`

**联合类型:**

- `T | None`: ✓ 支持
- `T1 | T2`: ✗ 类定义时抛出 `TypeError`

**JceDict vs dict:**

- `JceDict({0: 100})` → 编码为 JCE Struct
- `dict({0: 100})` → 编码为 JCE Map
- **警告**: 给 `Any` 字段传错类型 → 解码失败

**bytes_mode 参数:**

- `"raw"`: 保持原始字节
- `"string"`: 尝试 UTF-8 解码
- `"auto"` (默认): 智能模式, 尝试嵌套解析

**流式 API:**

- `LengthPrefixedWriter`: 自动添加长度头
- `LengthPrefixedReader`: 处理 TCP 粘包/拆包

## 测试约定

**风格:**

- 框架: pytest ≥9.0
- 模式: 函数式 (`def test_xxx()`), **禁止**类式
- 位置: `tests/` (扁平, 无子目录)
- 原子性: 一个测试 = 一个行为

**命名:**

- 文件: `test_<模块>.py`
- 函数: `test_<函数>_<预期行为>`

**核心协议测试:**

- `test_protocol.py` 是**根测试**—必须 100% 通过
- 破坏 `test_protocol.py` = 破坏性变更

**参数化:**

```python
@pytest.mark.parametrize(
    ("val", "expected"),
    [(1, b"\x01"), (127, b"\x7f")],
    ids=["small_int", "max_byte_int"]
)
def test_int_encoding_variants(val: int, expected: bytes) -> None:
    ...
```

## 反模式 (禁止)

| 类别     | 禁止操作                  | 原因         |
|----------|---------------------------|--------------|
| 类型安全 | `# type: ignore` (无说明) | 破坏类型保证 |
| 异常处理 | 空 `except: pass`         | 静默失败     |
| 测试     | 删除失败测试以"通过"      | 掩盖 bug     |
| Tag ID   | 结构体内重复 `jce_id`     | 协议违规     |
| Git 提交 | 未经明确用户请求提交      | 禁止主动提交 |

## 架构

**核心组件:**

| 模块               | 职责                                               |
|--------------------|----------------------------------------------------|
| `__init__.py`      | API 入口, 导出所有公开符号                         |
| `api.py`           | 高层 API (`dumps`/`loads`), 桥接 Rust 核心         |
| `struct.py`        | `JceStruct` 基类, `JceField` 工厂, `JceDict`       |
| `types.py`         | JCE 类型定义 (`JceType`, `INT`, `BYTES`, ...)      |
| `stream.py`        | 流式 API (包装 Rust `LengthPrefixedReader/Writer`) |
| `_jce_core` (Rust) | 编解码引擎, 流处理                                 |

**跨语言集成:**

- **错误映射**: Rust `JceDecodeError` → Python `jce.exceptions.JceDecodeError` (通过 `src/serde.rs:map_decode_error`)
- **上下文传递**: Rust `context: Bound<PyAny>` ↔ Python `SerializationInfo`
- **流式处理**: Rust 类通过 PyO3 暴露给 Python (`#[pyclass]`)

**关键限制:**

- `MAX_DEPTH = 100` (Rust `src/serde.rs`, 递归深度上限)
- 联合类型: 仅支持 `T | None`

## Git 工作流

**提交规范:**

- Conventional Commits 格式
- **禁止**在未经明确用户请求时提交

**PR 检查清单:**

- `uv run pytest` 通过
- `uv run ruff check` 清洁
- `uvx basedpyright` 通过
- Docstrings 完整
- 如约定变更需更新 `AGENTS.md`

## 文档 (MkDocs)

**结构:**

- `docs/api/`: API 参考 (mkdocstrings 自动生成)
- `docs/usage/`: 用户指南
- `docs/index.md`: 主页

**编写:**

- API 引用: `::: jce.struct.JceStruct` 语法
- 提示框: `!!! warning`, `!!! note`
- 代码块: 指定语言 + 可选 `title`

## 父文档

参见 [../AGENTS.md](../AGENTS.md) 了解 Rust 核心 (`src/`) 和项目级约定。
