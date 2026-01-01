# JceStruct

JceStruct 是一个基于 Pydantic 的 JCE 编解码工具包，支持零拷贝读取、循环引用检测，并提供与 JceStruct 模型的无缝互转。

## 核心特性

- JCE 二进制与 Python 对象互转：`dumps`/`loads`，支持直接读写 `dict` 或自定义 `JceStruct`。
- 基于 Pydantic v2 的模型定义：用 `JceField` 标注 `jce_id`/`jce_type`，自动完成校验和类型推断。
- 零拷贝/小端模式等编解码选项，兼容泛型无模式解析与已知模式解析。
- 循环引用检测、防止递归爆栈，包含丰富的类型实现（整型、字符串、MAP、LIST、BYTES 等）。
- 附带命令行工具，可直接把十六进制编码的 JCE 数据解码为可读结构。

## 安装

使用 uv（推荐）：

```bash
uv pip install JceStruct
```

在本地仓库直接安装：

```bash
uv pip install .
```

## 快速上手

定义结构体并完成编解码：

```python
from jce import JceField, JceStruct, dumps, loads, types

class User(JceStruct):
    uid: int = JceField(jce_id=0, jce_type=types.INT)
    name: str = JceField(jce_id=1, jce_type=types.STRING)

user = User(uid=1001, name="Alice")
encoded = dumps(user)
restored = loads(encoded, User)
assert restored == user

# 通用解码为 dict（键为 jce_id）
raw = loads(encoded, dict)
print(raw)  # {0: 1001, 1: 'Alice'}
```

嵌套结构与列表：

```python
class Server(JceStruct):
    host: str = JceField(jce_id=1)
    port: int = JceField(jce_id=2)

class ServerList(JceStruct):
    servers: types.LIST[Server] = JceField(jce_id=2)

payload = ServerList(servers=[Server(host="example.com", port=8080)]).encode()
parsed = ServerList.decode(payload)
```

命令行解码十六进制数据：

```bash
python -m jce "160472636e62211f40860472636e62"
# 输出: {1: 'rcnb', 2: 8000, 8: 'rcnb'}
```

## 主要 API

- `dumps(obj, option=OPT_NETWORK_BYTE_ORDER, default=None) -> bytes`：序列化 `JceStruct` 或 `{jce_id: value}` dict。
- `loads(data, target=dict, option=OPT_NETWORK_BYTE_ORDER)`：反序列化为 `dict` 或指定的 `JceStruct` 子类，自动处理文本/嵌套 JCE 字节。
- `JceStruct.encode()/decode()/decode_list()`：模型级快捷方法，支持额外字段注入。
- 核心类型位于 `jce.types`：`INT/INT8/INT16/INT32/INT64`、`STRING/STRING1/STRING4`、`MAP`、`LIST`、`BYTES`、`BOOL` 等。

## 编解码选项

- `OPT_NETWORK_BYTE_ORDER`（默认）：大端序。
- `OPT_LITTLE_ENDIAN`：启用小端序。
- `OPT_STRICT_MAP`：严格要求 MAP 键/值标签为 0/1。
- `OPT_ZERO_COPY`：尽可能返回 `memoryview`，减少拷贝。
- `OPT_OMIT_DEFAULT`：序列化时省略默认值（逻辑占位，部分功能待扩展）。

## 异常与安全

- 循环引用检测：列表/字典/结构体出现自引用时抛出 `JceEncodeError`。
- `JceDecodeError`/`JcePartialDataError`：检测未知类型或数据截断。
- 浮点解码提供小端兜底策略，尽量避免异常值。

## 许可

MIT License。
