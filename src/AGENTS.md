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
    * `serializer.rs`: 序列化实现 (`dumps`, `dumps_generic`), 负责 encode 热路径与 TLS writer 复用。
    * `deserializer.rs`: 反序列化实现 (`loads`, `loads_generic`), 负责 decode 热路径并在赋值前执行字段校验。
    * `schema.rs`: 预编译 Schema, 支持字符串驻留与 Tag 路由, 在编译期提取 Validators 元数据。
    * `validator.rs`: 字段级校验 (数值/长度), 仅在字段存在规则时触发。
    * `stream.rs`: 基于 `BytesMut` 的零移动流处理器。
    * `error.rs`: 反序列化路径追踪 (ErrorContext)。
    * `generics.rs`: 泛型实参解析 (TypeVar -> concrete)。
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
* 重点关注 decode/encode 的极限情况（深度嵌套、超大整数、损坏数据）。

## 父文档

参见 [../AGENTS.md](../AGENTS.md) 了解项目全局约定。
