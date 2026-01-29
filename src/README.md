# Rust 核心 (`src/`)

本目录是 Tars/JCE 协议的 Rust 实现, 通过 PyO3 暴露给 Python 包 `tarsio` 使用。

## 快速入口

* Python 扩展入口: [lib.rs](./lib.rs)
* 纯 Rust 编解码内核: [codec/](./codec/)
* PyO3 绑定层: [bindings/](./bindings/)

## 关键数据流

* 序列化: `serializer::dumps` / `serializer::dumps_generic` → `codec::writer` 写入二进制
* 反序列化: `deserializer::loads` / `deserializer::loads_generic` → `codec::reader` 读取二进制
* 流式场景: `bindings::stream::LengthPrefixedReader/Writer` 处理长度前缀与粘包/分片

## 目录结构

```text
src/
  bindings/      # PyO3 绑定层 (Python <-> Rust)
  codec/         # 纯 Rust 编解码内核 (不依赖 Python)
  lib.rs         # Python 扩展模块入口
  AGENTS.md      # Rust 核心开发指南
```

## 约束与约定

* 纯 Rust 内核与 Python 绑定层必须隔离: `codec/` 不依赖 PyO3。
* 性能优先: 热路径避免多余分配, 以预编译 Schema、tag 查找表、字符串驻留减少运行期开销。
* 错误处理: 尽量在 `codec/` 层保持纯 Rust 错误, 在 `bindings/` 层转换为 Python 异常。

## 测试

```bash
cargo test
uv run python -m pytest
```
