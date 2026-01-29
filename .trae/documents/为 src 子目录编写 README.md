## 目标

* 为 `f:/source/Tarsio/src` 下每个文件夹补齐 README.md, 让读者快速理解职责边界、关键数据流与扩展点。
* 同步更新 `src/AGENTS.md`, 使其与当前代码结构一致(移除已删除的 serde.rs 叙述)。

## 将新增/更新的文档

### 1) 新增 src/README.md

* 结构尽量短而可导航(标题 + 目标/功能 + 快速使用 + 目录导览 + 常见问题)。
* 内容要点:
    * `codec/`(纯 Rust 内核)、`bindings/`(PyO3 绑定层)、`lib.rs`(Python 扩展入口)。
    * 核心数据流:
        * `serializer::dumps` → `codec::writer`
        * `deserializer::loads` → `codec::reader`
    * 构建与测试入口: `cargo test`, `uv run python -m pytest`。

### 2) 新增 src/bindings/README.md

* 说明 bindings 层职责: Python 对象 ↔ Rust, Schema 预编译与缓存, 反序列化路径追踪, 流式读写。
* 文件导览(逐一说明用途与关联):
    * `serializer.rs`: `dumps`/`dumps_generic` 与 encode 热路径, TLS writer 复用。
    * `deserializer.rs`: `loads`/`loads_generic` 与 decode 热路径, 在 setattr 前执行校验。
    * `schema.rs`: `compile_schema`, `FieldDef`, `tag_lookup`, 字符串驻留, Validators 编译期提取。
    * `validator.rs`: 字段级校验(数值/长度), 仅在存在规则时触发。
    * `stream.rs`: LengthPrefixedReader/Writer(粘包/分片)。
    * `generics.rs`: 泛型实参解析(TypeVar → concrete)。
    * `error.rs`: ErrorContext(路径追踪)。
    * `exceptions.rs`: Python 异常封装/转换(如有)。
* 追加扩展指南: 新增 Field 元数据 → schema 编译 → decode/encode 使用。

### 3) 新增 src/codec/README.md

* 说明 codec 层定位: 完全不依赖 Python, 提供 JCE 基元/容器/结构体读写与校验。
* 文件导览:
    * `consts.rs`: `JceType` 与常量(含 `JCE_TYPE_GENERIC`)。
    * `endian.rs`: 编译期端序特化。
    * `reader.rs`: 读取 head/int/string/list/map/skip。
    * `writer.rs`: 写入字段与结构体。
    * `framing.rs`: 长度帧处理。
    * `scanner.rs`: 非分配结构探测/校验。
    * `error.rs`: 纯 Rust 错误类型。

### 4) 更新 src/AGENTS.md

* 修正 bindings 章节的“快速导航”:
    * 移除 `serde.rs` 描述。
    * 增补 `serializer.rs` / `deserializer.rs` / `validator.rs` 的职责说明。
    * 确认提到 `schema.rs`(预编译 Schema + tag_lookup + interning) 与 `stream.rs`(BytesMut 流处理)。
* 保留并校准全局规范:
    * 严禁 `panic!`。
    * codec 层错误与 bindings 层 PyErr 转换策略(保持与当前实现一致)。

## 文档风格约定

* 全中文说明, 半角标点。
* README 保持“短而有用”: 先让人 30 秒理解项目, 再给到入口/目录/扩展点。
* 目录结构用代码块展示, 避免过长(只展示核心目录)。

## 验证

* 新增/更新文档后:
    * 跑 `cargo test` 确认 Rust 侧无影响。
    * 跑 `uv run python -m pytest` 确认 Python 测试全绿。

确认后我会直接创建 3 个 README.md 并更新 src/AGENTS.md。
