# Fields

JceStruct 的核心是字段定义。就像 Pydantic 一样，我们使用 `JceField` 来定义结构体的属性。

## JceField

`JceField` 是 `Field` 的 JCE 特定版本。它增加了一个必须的参数 `jce_id` (Tag)。

```python title="definition.py"
from jce import JceField

name: str = JceField(jce_id=1, default="unknown", description="User Name")
```

### 参数

* `jce_id` (int, required): JCE 协议中的 Tag ID，必须唯一。
* `jce_type` (JceType, optional): 显式指定 JCE 类型（如 `types.FLOAT`）。
* `default`: 默认值。
* `default_factory`: 默认值工厂函数 (如 `list`)。
* `alias`: 别名 (用于 `model_dump(by_alias=True)`)。
* `description`: 字段描述，用于文档生成。

## 字段装饰器

你可以使用装饰器来定制特定字段的序列化逻辑。

### @jce_field_serializer

自定义字段的序列化逻辑。

```python title="serializer.py"
from jce import JceStruct, JceField, jce_field_serializer, SerializationInfo

class Timestamp(JceStruct):
    dt: int = JceField(jce_id=0)

    @jce_field_serializer("dt")
    def serialize_dt(self, value: int, info: SerializationInfo) -> int:
        # 假设我们需要在编码前做一些转换
        return value + 1000
```
