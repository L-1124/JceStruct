# JceStruct Rust 核心指南 (`src/`)

本目录包含 JCE 协议的核心编解码实现，通过 PyO3 暴露给 Python。

## 核心模块

- **`serde.rs`**: 核心编解码逻辑 (`dumps`/`loads`)。涉及递归深度控制 (`MAX_DEPTH = 100`)。
- **`reader.rs` / `writer.rs`**: 底层位流操作。
- **`stream.rs`**: 流式处理逻辑 (`LengthPrefixedReader/Writer`)。
- **`lib.rs`**: PyO3 模块入口，导出 `_jce_core`。
- **`consts.rs`**: JCE 协议类型常量。
- **`error.rs`**: 错误定义与到 Python 异常的映射。

## 编码规范

- **安全**: 严禁使用 `panic!`、`unwrap()` 或 `expect()`。所有错误必须转换为 `PyResult` 并传播。
- **性能**: 核心循环应避免不必要的内存分配。
- **风格**: 遵循标准 `rustfmt`。
- **互操作**:
    - 错误映射: 使用 `map_decode_error` 确保 Rust 错误能准确转换为 Python 的 `JceDecodeError`。
    - 上下文: 通过 `Bound<PyAny>` 传递序列化上下文。

## 测试

- 使用 `cargo test` 进行 Rust 单元测试。
- 重点关注 `serde.rs` 中的极限情况（深度嵌套、超大整数、损坏数据）。

## 父文档
参见 [../AGENTS.md](../AGENTS.md) 了解项目全局约定。
