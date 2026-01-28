# Tarsio

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Pydantic v2](https://img.shields.io/badge/pydantic-v2-blue.svg)](https://docs.pydantic.dev/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

**Tarsio** 是一个现代化的 Python Tars (JCE) 协议实现，基于 Pydantic v2 构建。它提供了类型安全、高性能且易于使用的 API，用于处理腾讯 Tars 框架的二进制序列化协议。

---

## 核心特性

* **类型安全**: 基于 Pydantic v2，提供完整的 IDE 自动补全和运行时类型检查。
* **高性能**: 针对 JCE 协议优化的编解码核心，支持零内存拷贝读取。
* **开发体验**: 声明式模型定义，像写普通 Python 类一样定义二进制结构。
* **灵活性**: 支持 Schema (Struct) 和无 Schema (dict/StructDict) 两种模式。
* **流式处理**: 内置 `LengthPrefixedReader`，轻松处理 TCP 粘包/拆包。
* **工具丰富**: 提供强大的 CLI 工具，支持格式化查看、文件转换和调试。

## 文档导航

* [**定义模型**](usage/models.md): 学习如何定义结构体、字段和类型。
* [**字段详解**](usage/fields.md): 深入了解 `Field` 和序列化钩子。
* [**序列化**](usage/serialization.md): 掌握 `dumps`/`loads` 和高级选项。
* [**流式处理**](usage/streams.md): 处理网络通信中的粘包与拆包。
* [**CLI 工具**](usage/cli.md): 使用命令行快速调试二进制数据。

## 快速开始

### 安装

使用 `pip` 或 `uv` 进行安装：

```bash title="Terminal"
# 安装核心库
uv add git+https://github.com/l-1124/Tarsio.git

# 安装包含 CLI 工具的版本
uv add "git+https://github.com/l-1124/Tarsio.git[cli]"
```

### 定义与序列化

```python title="quickstart.py"
from tarsio import Struct, Field, types, dumps, loads

# 1. 定义结构体
class User(Struct):
    uid: int = Field(id=0)
    name: str = Field(id=1)
    tags: list[str] = Field(id=2, default_factory=list)

# 2. 序列化 (Object -> Bytes)
user = User(uid=10086, name="Alice", tags=["admin", "dev"])
data = dumps(user)
print(f"Hex: {data.hex()}")

# 3. 反序列化 (Bytes -> Object)
user_restored = loads(data, User)
assert user_restored.name == "Alice"
```
