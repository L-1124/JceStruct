# JceStruct Python 指南 (`python/`)

本目录包含 Python 源代码、测试及相关规范。

## 数据建模 (核心)

使用 `JceStruct` 和 `JceField` 定义协议模型：

```python
from jce import JceStruct, JceField

class MyModel(JceStruct):
    id: int = JceField(jce_id=0)
    name: str = JceField(jce_id=1, default="")
```

- **`jce_id`**: 必须唯一且连续。
- **类型支持**:
  - 基础类型: `int`, `str`, `bytes`, `float`, `bool`。
  - 容器: `list[T]`, `dict[K, V]`。
  - 联合类型: 仅支持 `T | None`。
- **`JceDict`**: 用于需要显式编码为 Struct 而非 Map 的字典场景。

## 关键模块职责

- **`struct.py`**: `JceStruct` 与 `JceField` 的实现核心。
- **`api.py`**: `dumps`/`loads` 高层入口。
- **`adapter.py`**: `JceTypeAdapter` 用于动态或非 `JceStruct` 类型。
- **`stream.py`**: 包装 Rust 流处理类。
- **`exceptions.py`**: 统一定义 Python 侧异常。

## 测试规范 (`python/tests/`)

- **根测试**: `test_protocol.py` 是核心，修改逻辑后必须 100% 通过。
- **回归策略**: 任何 Bug 修复必须伴随一个新的测试用例。
- **参数化**: 广泛使用 `@pytest.mark.parametrize` 覆盖数据边界。
- **运行**: `uv run pytest`。

## 规范

- **类型检查**: 必须通过 `basedpyright`。
- **风格**: 使用 Google 风格 Docstrings，必须通过 `ruff` 检查。
- **导入**: 内部引用使用相对导入。

## 父文档

参见 [../AGENTS.md](../AGENTS.md) 了解项目全局约定与构建指南。
