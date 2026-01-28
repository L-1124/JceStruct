# Tarsio Rust 核心指南 (`src/`)

本目录包含 Tars/JCE 协议的核心编解码实现，通过 PyO3 暴露给 Python。

## 核心结构

* **`codec/` (纯 Rust 内核)**:
    * 不依赖 PyO3, 实现高性能协议逻辑。
    * `reader.rs` / `writer.rs`: 零拷贝/零分配位流操作。
    * `endian.rs`: 编译期字节序特化。
    * `scanner.rs`: 非分配式结构校验。
    * `error.rs`: 物理层错误定义。
* **`bindings/` (Python 绑定层)**:
    * 负责 Rust 与 Python 对象 (`Bound<PyAny>`) 的转换。
    * `serde.rs`: 核心序列化逻辑, 采用泛型静态分发。
    * `schema.rs`: 预编译 Schema, 支持字符串驻留与 Tag 路由。
    * `stream.rs`: 基于 `BytesMut` 的零移动流处理器。
* **`lib.rs`**: 模块入口。

## 编码规范

* **安全**: 严禁 `panic!`。`codec` 层返回 `codec::error::Result`, `bindings` 层负责将其转换为 `PyResult`。
* **性能**:
    * 优先使用 `read_bytes_slice` 和 `Cow` 减少拷贝。
    * 泛型函数以支持静态分发。
    * 使用 `bytes` crate 管理流缓冲区。
* **风格**: 遵循 `rustfmt`。

## 测试

* 使用 `cargo test` 进行 Rust 单元测试。
* 重点关注 `serde.rs` 中的极限情况（深度嵌套、超大整数、损坏数据）。

## 父文档

参见 [../AGENTS.md](../AGENTS.md) 了解项目全局约定。
