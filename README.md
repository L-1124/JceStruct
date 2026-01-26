# JceStruct

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Pydantic v2](https://img.shields.io/badge/pydantic-v2-blue.svg)](https://docs.pydantic.dev/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Documentation](https://img.shields.io/badge/docs-mkdocs-blue)](https://L-1124.github.io/JceStruct/)

**JceStruct** 是一个Python JCE (Jce Encoding) 协议实现，基于 **Pydantic v2** 构建。JCE 是腾讯 Tars 框架使用的高效二进制序列化协议。

## 📖 官方文档

详细的使用指南和 API 参考请查阅 [文档](https://L-1124.github.io/JceStruct/)。

## ✨ 核心特性

- **🛡️ 类型安全**: 基于 Pydantic v2，提供完整的类型提示和运行时验证。
- **⚡ 高性能**: **Rust 核心驱动**，提供极速的编解码性能；支持智能整数压缩、零值优化、字节数组优化、零拷贝读取。
- **🧩 灵活性**: 支持 Schema (JceStruct) 和无 Schema (dict/JceDict) 两种模式。
- **🌊 流式处理**: 提供 [`LengthPrefixedWriter/Reader`](docs/usage/streams.md) 支持增量打包和长度前缀协议。
- **📂 文件支持**: 提供 `dump`/`load` 直接读写文件类对象（IO[bytes]）。
- **🔌 上下文**: 支持序列化上下文传递 (`context`) 和字段钩子 (`@jce_field_serializer`).
- **🧬 泛型支持**: 完整支持 Python `Generic[T]` 类型系统。
- **🛠️ CLI 工具**: 基于 Click 的强大命令行工具，支持文件读写、格式化输出和调试。
- **🛡️ 安全防护**: 递归深度限制、容器大小限制，防止 DoS 攻击。

## 📦 安装

```bash
# 使用 uv (推荐)
$ uv add "git+https://github.com/L-1124/JceStruct.git"

# 使用 pip
$ pip install git+https://github.com/L-1124/JceStruct.git
```

## 🚀 快速开始

### 基础示例

```python
from jce import JceField, JceStruct, dumps, loads

# 定义数据模型
class User(JceStruct):
    uid: int = JceField(jce_id=0)
    name: str = JceField(jce_id=1)
    tags: list[str] = JceField(jce_id=2, default_factory=list)

# 序列化
user = User(uid=1001, name="Alice", tags=["admin"])
encoded = dumps(user)
print(f"Encoded hex: {encoded.hex().upper()}")
# > Encoded hex: 0003E91605416C696365290001160561646D696E

# 反序列化
restored = loads(encoded, User)
assert restored.name == "Alice"
assert restored.tags == ["admin"]
```

### 流式处理 (TCP 粘包/拆包)

针对网络流式数据，JceStruct 提供了 `LengthPrefixedWriter` 和 `LengthPrefixedReader`，支持处理常见的“长度+数据”协议格式。

```python
from jce.stream import LengthPrefixedWriter, LengthPrefixedReader

# 1. 写入 (Writer) - 自动添加长度头
writer = LengthPrefixedWriter(length_type=4)
writer.pack(User(uid=1, name="A"))
writer.pack(User(uid=2, name="B"))
data = writer.get_buffer()

# 2. 读取 (Reader) - 处理粘包/拆包
reader = LengthPrefixedReader(target=User, length_type=4)
reader.feed(data) # 模拟接收数据

for user in reader:
    print(f"Received user: {user.name}")
```

### 字段钩子与上下文

通过 `@jce_field_serializer` 和 `context` 参数，你可以灵活控制字段的序列化逻辑（例如加密敏感字段）。

```python
from jce import JceStruct, JceField, jce_field_serializer, SerializationInfo, dumps

class SecretConfig(JceStruct):
    password: str = JceField(jce_id=0)

    @jce_field_serializer("password")
    def encrypt_password(self, value, info: SerializationInfo):
        # 从上下文获取密钥进行加密
        key = info.context.get("key", "default")
        return f"encrypted({value}, {key})"

cfg = SecretConfig(password="123456")
encoded = dumps(cfg, context={"key": "my-secret-key"})
```

## 🛠️ CLI 工具

安装 `git+https://github.com/L-1124/JceStruct.git[cli]` 后，你可以使用 `jce` 命令直接在终端调试数据。

```bash
# 解码 Hex 字符串
$ jce "0C 00 01"

# 从文件读取并以 JSON 格式输出
$ jce -f data.bin --format json


# 查看详细的解码过程 (Verbose 模式)
$ jce "0C" -v

# 以 Tree 格式输出
$ jce "0C" --format tree
```

## 🤝 开发与贡献

1. 克隆仓库：`git clone https://github.com/L-1124/JceStruct.git`
2. 安装环境：`uv sync`
3. 运行测试：`uv run pytest`
4. 代码检查：`uv run ruff check .`

## 📄 协议文档

详细的 JCE 协议规范请参阅 [JCE_PROTOCOL.md](JCE_PROTOCOL.md)。

## ⚖️ 许可

本项目采用 **MIT 许可证**。详情请参阅 [LICENSE](LICENSE) 文件。
