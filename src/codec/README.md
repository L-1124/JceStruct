# 纯 Rust 编解码内核 (`src/codec/`)

本目录实现 Tars/JCE 协议的核心编解码逻辑, 不依赖 PyO3, 可被 bindings 层直接复用。

## 设计目标

* 可复用: 与 Python 绑定层隔离, 便于独立测试与复用。
* 高性能: 以静态分发与最小拷贝为导向, 避免多余分配。
* 可校验: 提供结构探测与跳过能力, 支持向前/向后兼容的数据流处理。

## 文件导览

* [consts.rs](./consts.rs)
    * `JceType`: 协议类型枚举(带 `TryFrom<u8>`)
    * 常量: `JCE_*` 与内部标记 `JCE_TYPE_GENERIC`

* [endian.rs](./endian.rs)
    * `Endianness` 抽象, 通过泛型在编译期特化大端/小端实现

* [reader.rs](./reader.rs)
    * `JceReader`: 读取 head、int、float、double、string、list/map 及 `skip_field`

* [writer.rs](./writer.rs)
    * `JceWriter`: 写入字段与结构体边界, 面向 bytes buffer 的高效输出

* [framing.rs](./framing.rs)
    * `JceFramer`: 长度前缀帧校验(粘包/分片/最大包长)

* [scanner.rs](./scanner.rs)
    * `JceScanner`: 非分配式的结构探测/校验, 支持快速判断 bytes 是否为可解码 struct

* [error.rs](./error.rs)
    * codec 层错误定义, 供 bindings 层转换为 Python 异常

## 与 bindings 的边界

* codec 层只处理字节与协议语义。
* Python 类型推导、Schema 编译、字段级校验与错误路径拼接属于 bindings 层。
