<div align="center">
  <h1 style="margin-top: 20px;">JceStruct</h1>

  <h2>基于 Pydantic 的高性能 Python JCE 编解码库</h2>

  <div align="center">
    <a href="./LICENSE"><img alt="License" src="https://img.shields.io/badge/LICENSE-MIT-green"/></a>
    <img alt="Python" src="https://img.shields.io/badge/python-3.10+-blue.svg"/>
  </div>
</div>

## 什么是 JCE？

查看 [JCE 协议详解](./JCE_PROTOCOL.md)

### 基础示例

```python
from jce import JceField, JceStruct, dumps, loads, types

# 定义数据模型
class User(JceStruct):
    uid: int = JceField(jce_id=0, jce_type=types.INT)
    name: str = JceField(jce_id=1, jce_type=types.STRING)

# 序列化
user = User(uid=1001, name="Alice")
encoded = dumps(user)
print(f"Encoded hex: {encoded.hex()}")

# 反序列化
restored = loads(encoded, User)
assert restored.name == "Alice"
```

## 功能演示

### 1. 复杂嵌套结构

JceStruct 完美处理嵌套结构和泛型列表。

```python
class Server(JceStruct):
    host: str = JceField(jce_id=1)
    port: int = JceField(jce_id=2)

class ServerList(JceStruct):
    # 支持泛型类型提示
    servers: list[Server] = JceField(jce_id=2, jce_type=types.LIST)

# 自动编码嵌套对象
payload = ServerList(servers=[
    Server(host="192.168.1.1", port=8080),
    Server(host="192.168.1.2", port=8081)
]).encode()

# 解码回对象
data = ServerList.decode(payload)
print(f"Server 1: {data.servers[0].host}:{data.servers[0].port}")
```

### 2. 命令行调试工具

内置 CLI 工具方便快速查看十六进制 JCE 数据的结构。

```bash
# 直接解码 Hex 字符串
$ python -m jce "160472636e62211f40860472636e62"

# 输出结果
{
    1: 'rcnb',
    2: 8000,
    8: 'rcnb'
}
```

### 3. 无模式 (Dict) 编解码

无需定义 `JceStruct` 模型，直接处理原始字典数据，适用于动态结构或快速原型。

```python
from jce import dumps, loads

# 编码：使用字典，键为 JCE Tag ID (int)
raw_data = {
    0: 123,
    1: "JceStruct",
    2: [1, 2, 3],
    3: {"inner_tag": "inner_value"}
}
encoded = dumps(raw_data)

# 解码：指定 target=dict (默认为 dict)
# 库会自动尝试将嵌套的字节/SimpleList 转换为可读字典或字符串
decoded = loads(encoded, target=dict)

print(decoded[0])  # 123
print(decoded[1])  # "JceStruct"
```

## 许可

本项目采用 **MIT 许可证** - 详情请参阅 [LICENSE](LICENSE) 文件。
