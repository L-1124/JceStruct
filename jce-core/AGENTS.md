# jce-core Agent 指南

**父文档**: [../AGENTS.md](../AGENTS.md)

JCE 协议的 Rust 核心扩展, 通过 PyO3 + maturin 构建为 Python 模块.

## 概览

```tree
jce-core/
├── src/              # Rust 源码
│   ├── lib.rs        # PyO3 模块入口
│   ├── serde.rs      # 编解码核心 (dumps/loads)
│   ├── reader.rs     # JCE 读取器
│   ├── writer.rs     # JCE 写入器
│   ├── stream.rs     # LengthPrefixed 流处理
│   ├── consts.rs     # 协议常量/类型码
│   └── error.rs      # 错误类型
├── python/jce_core/  # Python 包装层
├── Cargo.toml        # Rust 依赖
└── pyproject.toml    # maturin 构建配置
```

## 快速导航

| 任务           |               位置              | 备注                                            |
|----------------|:-------------------------------:|-------------------------------------------------|
| 添加 PyO3 函数 |           `src/lib.rs`          | `#[pyfunction]` + `m.add_function`              |
| 编解码逻辑     |          `src/serde.rs`         | `dumps`/`loads`/`dumps_generic`/`loads_generic` |
| 流式处理       |         `src/stream.rs`         | `LengthPrefixedReader`/`Writer`                 |
| 错误映射       | `src/serde.rs:map_decode_error` | Rust → Python 异常                              |
| Python 重导出  |  `python/jce_core/__init__.py`  | 导入 `._jce_core`                               |

## 命令

```bash
# 开发构建 (从 jce-core/ 目录)
maturin develop                   # 构建并安装到当前 venv

# 也可从根目录用 uv
cd .. && uv sync                  # uv 会自动构建 workspace 成员

# Rust 测试
cargo test                        # 运行 Rust 单元测试
cargo clippy                      # Lint

# Stub 生成
cargo run --bin stub_gen          # 生成 .pyi 类型提示文件

# Release 构建
maturin build --release           # 生成 wheel
```

## 架构要点

### PyO3 绑定

- 模块名: `jce_core._jce_core`
- 入口: `src/lib.rs` 的 `#[pymodule] fn _jce_core`

### 导出函数

|                         函数                        | 用途           |
|:---------------------------------------------------:|----------------|
|        `dumps(obj, schema, options, context)`       | Schema 编码    |
|       `loads(data, schema, options, context)`       | Schema 解码    |
|        `dumps_generic(obj, options, context)`       | 无 Schema 编码 |
| `loads_generic(data, options, bytes_mode, context)` | 无 Schema 解码 |
|               `decode_safe_text(data)`              | UTF-8 安全检测 |

### 导出类

| 类                     |         用途        |
|------------------------|:-------------------:|
| `LengthPrefixedReader` | 流式读取 (粘包处理) |
| `LengthPrefixedWriter` | 流式写入 (长度前缀) |

### 关键常量

```rust
const MAX_DEPTH: usize = 100;      // 递归深度限制
const OPT_OMIT_DEFAULT: i32 = 32;  // 省略默认值
const OPT_EXCLUDE_UNSET: i32 = 64; // 排除未设置字段
```

### 错误处理

- Rust 错误通过 `map_decode_error` 映射到 Python `jce.exceptions.JceDecodeError`
- 回退到 `PyValueError`

## 代码规范

### Rust 风格

- 遵循 Rust 标准风格 (rustfmt)
- 使用 `thiserror` 定义错误类型
- 公开函数添加文档注释

### 与 Python 交互

- 使用 `Bound<'_, PyAny>` 处理 Python 对象
- `PyResult<T>` 作为返回类型
- 通过 `context` 参数传递序列化上下文

## 构建系统

### maturin 配置 (pyproject.toml)

```toml
[tool.maturin]
module-name = "jce_core._jce_core"
features = ["pyo3/extension-module"]
python-source = "python"
bindings = "pyo3"
```

### uv workspace

- 根目录 `pyproject.toml` 通过 `[tool.uv.sources]` 引用本包
- `cache-keys` 包含 Rust 源文件, 确保 Cargo 变更触发重建

## 反模式

| 禁止                 |              原因             |
|----------------------|:-----------------------------:|
| 直接 `panic!`        | 应返回 `PyResult` 或 `Result` |
| 忽略 `PyResult` 错误 |       会导致 Python 崩溃      |
| 硬编码缓冲区大小     |     使用动态分配或配置常量    |
