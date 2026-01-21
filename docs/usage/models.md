# 定义模型

在 JceStruct 中，数据模型是通过继承 `JceStruct` 并使用 Python 类型提示来定义的。这与 Pydantic 的使用方式非常相似，但增加了一个关键概念：**JCE ID (Tag)**。

## 基础结构体

每个字段必须通过 `JceField` 指定一个唯一的 `jce_id`。这是 JCE 协议的要求，用于在二进制流中标识字段。

```python
from jce import JceStruct, JceField

class Product(JceStruct):
    id: int = JceField(jce_id=0)
    name: str = JceField(jce_id=1)
    price: float = JceField(jce_id=2)
```

!!! warning "Tag 唯一性"
    在一个结构体内，`jce_id` 必须是唯一的且为非负整数。通常从 0 开始递增。

## 支持的类型

JceStruct 支持多种 Python 原生类型，并自动映射到 JCE 类型：

| Python 类型 | JCE 类型 | 说明 |
| :--- | :--- | :--- |
| `int` | `INT1/2/4/8` | 根据数值大小自动选择最优编码 |
| `float` | `FLOAT/DOUBLE` | 默认编码为 `DOUBLE` (8字节) |
| `str` | `STRING1/4` | UTF-8 编码字符串 |
| `bytes` | `SIMPLE_LIST` | 对应 JCE 的 `byte[]` |
| `bool` | `INT1` | `True`=1, `False`=0 |
| `list[T]` | `LIST` | 列表容器 |
| `dict[K, V]` | `MAP` | 字典容器 |

### 显式指定类型

虽然 JceStruct 会自动推断类型，但你也可以显式指定 JCE 类型（通常用于 `float` vs `double`）：

```python
from jce import types

class Metrics(JceStruct):
    # 强制使用 4 字节 FLOAT
    cpu_usage: float = JceField(jce_id=0, jce_type=types.FLOAT)
```

## 嵌套结构体

你可以在一个结构体中嵌套另一个 `JceStruct`：

```python
class Address(JceStruct):
    city: str = JceField(jce_id=0)
    street: str = JceField(jce_id=1)

class User(JceStruct):
    uid: int = JceField(jce_id=0)
    address: Address = JceField(jce_id=1)  # 嵌套
```

### 嵌套结构体 vs 二进制数据块

在定义字段时，有两种处理复杂对象的常见模式。

#### 模式 A：标准嵌套 (Nested Struct)
这是最常用的方式，直接将结构体作为字段类型。

*   **代码**: `param: User = JceField(jce_id=2)`
*   **行为**: 编码为 **JCE Struct (Type 10)**。内容是内联的，以 `STRUCT_BEGIN (0x0A)` 开始，`STRUCT_END (0x0B)` 结束。
*   **适用场景**: 标准的嵌套模型，接收方已知其定义。

#### 模式 B：二进制透传 (Binary Blob)
如果你希望将某个对象先序列化为二进制流，再存入字段中（例如作为一个通用的“Payload”字段），可以显式指定 `jce_type=BYTES`。

*   **代码**: `param: User = JceField(jce_id=2, jce_type=types.BYTES)`
*   **行为**: 编码为 **SimpleList (Type 13)**。JceStruct 会**自动先将对象序列化为 bytes**，然后存入字节数组中。
*   **适用场景**: 不透明负载、延迟解析、或协议中的缓冲区字段。

## 容器类型 (List & Map)

JceStruct 完整支持泛型容器：

```python
class Group(JceStruct):
    # 基础类型列表
    scores: list[int] = JceField(jce_id=0)
    
    # 结构体列表
    members: list[User] = JceField(jce_id=1)
    
    # 字典 (JCE Map)
    config: dict[str, str] = JceField(jce_id=2)
```

## 泛型支持 (Generics)

JceStruct 支持定义泛型结构体，这在定义通用的响应包装器时非常有用。

```python
from typing import Generic, TypeVar
from jce import JceStruct, JceField

T = TypeVar("T")

class Response(JceStruct, Generic[T]):
    code: int = JceField(jce_id=0)
    message: str = JceField(jce_id=1)
    data: T = JceField(jce_id=2)  # 泛型字段

# 具体化
class UserResponse(Response[User]):
    pass

# 或者直接使用
resp = Response[User](code=0, message="OK", data=user)
```

## 默认值与工厂

你可以使用 `default` 或 `default_factory` 来设置字段默认值：

```python
class Config(JceStruct):
    version: int = JceField(jce_id=0, default=1)
    tags: list[str] = JceField(jce_id=1, default_factory=list)
```

!!! tip "Optional 字段"
    对于可选字段，推荐使用 `T | None` (Python 3.10+) 并设置 `default=None`。

    ```python
    extra: str | None = JceField(jce_id=3, default=None)
    ```

## 下一步

- 了解如何 [序列化与反序列化](serialization.md) 模型。
- 深入了解 [字段配置与钩子](fields.md)。

