# PyO3 绑定层 (`src/bindings/`)

本目录负责 Rust 与 Python 解释器交互, 将 `codec/` 的纯 Rust 能力包装为 Python API 可用的序列化/反序列化函数与流式工具。

## 核心职责

* Schema 驱动: 将 Python 端 `__tars_schema__` 预编译为 Rust 内部结构, 降低热路径分支与反射开销。
* 高性能属性访问: 字段名使用 `PyString::intern` 驻留, 并缓存为 `Py<PyString>`。
* 字段级校验: 反序列化时在 “解码完成但尚未 setattr” 的窗口执行校验。
* 错误上下文: 反序列化出错时提供字段路径, 便于定位问题。

## 文件导览

* [serializer.rs](./serializer.rs)
    * Python 导出: `dumps`, `dumps_generic`
    * 热路径: `encode_struct` / `encode_generic_struct` / `encode_generic_field`
    * 性能点: TLS writer 复用缓冲区, 减少重复分配

* [deserializer.rs](./deserializer.rs)
    * Python 导出: `loads`, `loads_generic`
    * 热路径: `decode_struct_instance` / `decode_struct_dict` / `decode_generic_struct`
    * 集成点: 在 `setattr` 前调用 [validator.rs](./validator.rs)

* [schema.rs](./schema.rs)
    * `compile_schema`: 将 Python schema 列表编译为 `CompiledSchema`
    * `FieldDef`: 缓存 `tag`, `jce_type`, `type_ref`, `default_val`, `validators`
    * `tag_lookup`: `[Option<usize>; 256]` 做 O(1) tag 路由

* [validator.rs](./validator.rs)
    * 校验器: 支持数值(gt/lt/ge/le) 与长度(min_len/max_len)
    * 策略: `FieldDef.validators` 为 `None` 时不触发调用, 避免无规则字段的额外成本

* [stream.rs](./stream.rs)
    * `LengthPrefixedReader`: 面向 TCP 的长度前缀解码(处理粘包/分片)
    * `LengthPrefixedWriter`: 将 payload 包装为长度前缀帧

* [generics.rs](./generics.rs)
    * `resolve_concrete_type`: 在泛型上下文中解析 `TypeVar` 的具体类型
    * 使用 `intern!` 减少属性名查找开销

* [error.rs](./error.rs)
    * `ErrorContext`: 跟踪反序列化路径, 拼接为 `field[tag](Type)` 形式的链路

* [exceptions.rs](./exceptions.rs)
    * Python 侧异常类型/映射(供 bindings 层统一抛出)

## 扩展指南

### 新增 Field 元数据(例如新的校验参数)

1. Python 侧将元数据挂到 `FieldInfo`(只作为 schema 元数据)。
2. 在 [schema.rs](./schema.rs) 的 `compile_schema` 中提取该元数据并存入 `FieldDef` 的紧凑结构。
3. 在 [serializer.rs](./serializer.rs) 或 [deserializer.rs](./deserializer.rs) 的热路径中使用该信息(优先在 decode/encode 的单次循环中完成, 避免额外遍历)。

### 新增类型支持

优先扩展 `codec/` 的读写能力, 再在 bindings 层进行 Python 类型映射与 Schema 推导。
