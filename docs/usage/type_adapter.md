# TypeAdapter

`JceTypeAdapter` 类似于 Pydantic 的 `TypeAdapter`，它允许你对任何 Python 类型（不仅仅是 `JceStruct` 子类）执行 JCE 序列化和反序列化操作。

这在处理像 `list[int]`、`dict[str, User]` 这样的顶层容器，或者直接处理基础类型时非常有用。

## 基本用法

### 序列化

```python title="serialization.py"
from jce import JceTypeAdapter

# 定义一个处理 int 列表的适配器
adapter = JceTypeAdapter(list[int])

# 序列化
data = adapter.dump_jce([1, 2, 3])
print(data.hex())
```

### 反序列化

```python title="deserialization.py"
# 反序列化
restored = adapter.validate_jce(data)
assert restored == [1, 2, 3]
```

## 支持的类型

`JceTypeAdapter` 支持所有 JceStruct 支持的类型提示，包括：

* **基础类型**: `int`, `float`, `str`, `bool`, `bytes`
* **容器**: `list[T]`, `dict[K, V]`, `tuple[...]`
* **嵌套结构**: `list[User]`, `dict[int, User]`
* **泛型**: `Box[T]` (需要先实例化类型，如 `Box[int]`)

## 基础类型与 Tag 0

当使用 `JceTypeAdapter` 处理**基础类型**（如 `int` 或 `str`）时，JCE 协议要求所有数据必须包含 Tag。默认情况下，适配器会将这些基础类型包装在 **Tag 0** 中。

```python title="primitive.py"
adapter = JceTypeAdapter(int)

# 实际上编码为 {0: 123}
data = adapter.dump_jce(123)
```

如果你需要从非 Tag 0 的位置读取数据，可以指定 `jce_id` 参数：

```python title="custom_tag.py"
# 假设数据实际上在 Tag 5
val = adapter.validate_jce(data, jce_id=5)
```

## 性能

`JceTypeAdapter` 在初始化时会构建类型特定的序列化/反序列化器。因此，建议**创建一次适配器实例并重复使用**，而不是每次操作都重新创建，以获得最佳性能。

```python title="best_practice.py"
# 推荐做法：模块级变量
user_list_adapter = JceTypeAdapter(list[User])

def process_data(data: bytes):
    users = user_list_adapter.validate_jce(data)
    ...
```
