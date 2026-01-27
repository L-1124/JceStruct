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

## 代码风格与约定

### 通用

- **语言**: 文档字符串和注释应使用 **中文**，但是使用英文符号
- **缩进**: 4 个空格。
- **行长**: 软限制约 80-88 字符 (由 Ruff 强制执行)。

### 注释和文档字符串

- **语言**: **中文，但是使用半角标点**。
- **Docstrings**: Google 风格。
- **示例**:

  ```python
  def encode(self) -> bytes:
      """序列化当前对象.

      Returns:
          bytes: JCE格式的二进制数据.

      Raises:
          JceEncodeError: 编码失败时抛出.
      """
  ```

#### 源码注释规范 (Google Style Docstrings)

所有**公共类**和**方法**必须包含符合 Google Style 的注释，这是文档生成的基石。

- **语言**: 中文描述，半角标点。
- **结构要求**:

1. **简述**: 第一行提供简洁的功能描述。
2. **详细描述**: （可选）如有复杂逻辑，在简述后空一行编写。
3. **Args**: 列出参数名、类型及说明。
4. **Returns**: 说明返回值的类型及含义。
5. **Raises**: 列出可能抛出的异常类（如 `JceDecodeError`）。
6. **Examples**: 提供一个可直接运行的代码片段。

- **标准示例**:

```python
def loads(data: bytes, jce_struct: type[T], bytes_mode: str = "auto") -> T:
    """从字节序列反序列化为 JceStruct 对象.

    Args:
        data: 符合 JCE 协议的二进制数据.
        jce_struct: 目标 JceStruct 类.
        bytes_mode: 字节处理模式, 可选 "auto", "raw", "string".

    Returns:
        T: 实例化的 JceStruct 对象.

    Raises:
        JceDecodeError: 当数据格式非法或长度不足时抛出.

    Examples:
        >>> user = jce.loads(b"\x00\x01\x15...", User)
        >>> print(user.uid)
    """

```

### 命名

- **类**: `PascalCase` (例如 `JceStruct`, `JceField`)。
- **函数/方法**: `snake_case` (例如 `model_validate`, `to_bytes`)。
- **变量**: `snake_case`。
- **常量**: `UPPER_SNAKE_CASE` (例如 `OPT_LITTLE_ENDIAN`)。
- **私有**: 使用单下划线前缀 `_` (例如 `_buffer`)。

### 导入

- **风格**: **相对导入** (例如 `from .types import INT`)。
- **排序**: 标准库 -> 第三方 (`pydantic`) -> 本地 (`jce`)。
- **分组**: 多行导入使用圆括号。

### 类型提示

- **严格性**: 高。所有函数签名和字段都使用类型提示。
- **工具**: `pydantic` v2.0+ 是数据建模的核心。
- **泛型**: 使用 `list[T]`, `dict[K, V]` (Python 3.10+ 风格)。

## 测试规范 (`python/tests/`)

### 测试风格

- **框架**: 使用 `pytest` (v9.0.2+)。
- **模式**: 采用**函数式测试** (`def test_xxx()`)，禁止使用类式测试 (`class TestXxx`) 以保持代码简洁。
- **位置**: 所有测试文件位于根目录的 `tests/` 文件夹下，采用**扁平结构**（不创建子目录）。
- **原子性**: 测试函数必须短小且聚焦。一个测试函数只验证一个行为，严禁编写“万能测试函数”。

### 命名约定

- **测试文件**: `test_<被测模块>.py`
  - 例: `struct.py`  `test_struct.py`
- **测试函数**: `test_<被测函数>_<预期行为>`
  - 例: `test_loads_with_invalid_data_raises_decode_error`
- **Fixtures**: 遵循 `snake_case`，名称应反映其提供的对象或状态。

### 文档字符串与注释

- **测试函数**:
  - 使用**单行中文**。
  - 描述预期行为，不描述实现细节。
- **Fixtures 与辅助函数**:
  - 必须遵循 **Google Style** 注释规范。
  - 包含 `Args`、`Returns` 或 `Yields` 声明。
- **类型注解**:
  - 测试函数统一标注返回值为 `-> None`。
  - Fixtures 必须标注返回值类型。

### 4.4 标准结构示例

```python
"""测试 JCE 编解码器的核心功能."""

import pytest
from io import BytesIO
from typing import Generator
from jce import JceStruct, JceDecodeError, fields

class User(JceStruct):
    """用于测试的简单结构体."""
    uid: int = fields.Int(1)
    name: str = fields.String(2)

@pytest.fixture
def sample_user() -> User:
    """提供一个预置的 User 实例。

    Returns:
        初始化后的 User 对象。
    """
    return User(uid=12345, name="Gemini")

@pytest.fixture
def mock_stream() -> Generator[BytesIO, None, None]:
    """提供内存字节流环境。

    Yields:
        BytesIO 实例。
    """
    stream = BytesIO()
    yield stream
    stream.close()

def test_user_encode_returns_correct_bytes(sample_user: User) -> None:
    """User 结构体应该能正确编码为字节流."""
    # Arrange (准备)
    expected_prefix = b"\x01\x15"  # 假设的编码开头

    # Act (执行)
    result = sample_user.encode()

    # Assert (断言)
    assert isinstance(result, bytes)
    assert result.startswith(expected_prefix)

def test_decode_with_truncated_data_raises_error() -> None:
    """当数据被截断时，decode 应该抛出 JceDecodeError."""
    invalid_data = b"\x01"

    with pytest.raises(JceDecodeError, match="Unexpected end of buffer"):
        User.decode(invalid_data)

```

### 进阶最佳实践

#### 参数化测试 (Parametrize)

当测试多个输入输出时，必须使用参数化并提供 `ids` 以增强报告可读性。

```python
@pytest.mark.parametrize(
    ("val","expected"),
    [(1, b"\x01"), (127, b"\x7f")],
    ids=["small_int", "max_byte_int"]
)
def test_int_encoding_variants(val: int, expected: bytes) -> None:
    """测试不同范围整数的编码结果."""
    ...

```

#### 异常捕获

- 必须使用 `pytest.raises`。
- **严禁**使用宽泛的 `Exception`，必须指明具体的异常类（如 `ValueError`, `JceDecodeError`）。
- 建议使用 `match` 参数校验异常信息关键词。

#### Warnings 处理

- 使用 `pytest.warns` 捕获预期的警告。
- **禁止**忽略警告或使用 `warnings` 模块手动捕获

#### I/O 处理

- **内存化**: 涉及文件读取的测试，优先使用 `io.BytesIO` 或 `io.StringIO`。
- **临时文件**: 若必须操作物理文件，使用 pytest 内置的 `tmp_path` fixture。

#### 显式断言

- 避免 `assert result`（除非结果本身是布尔值）。
- 使用 `assert result == expected`、`assert "key" in dict` 等明确的比较。
- 涉及浮点数对比时，使用 `pytest.approx()`。

### 核心协议测试 (Fundamental)

`test_protocol.py` 是库的**根本性测试**，必须保证 100% 通过。它定义了 JCE 协议实现的基准，任何破坏此文件测试用例的修改均被视为破坏性变更。

- **测试目标**: 验证确定的输入与预期的十六进制输出（Hex）完全一致。
- **断言要求**:
- 编码测试：断言生成的 bytes 转为 hex 字符串后与预期值完全匹配。
- 解码测试：断言从预期 hex 字符串还原的对象与原始对象等值。

## 规范

- **类型检查**: 必须通过 `basedpyright`。
- **风格**: 使用 Google 风格 Docstrings，必须通过 `ruff` 检查。
- **导入**: 内部引用使用相对导入。

## 文档生成 (MkDocs)

项目使用 **MkDocs** (Material Theme) 生成静态文档网站。

### 结构

文档源文件位于 `docs/` 目录：

- **`docs/api/`**: 自动生成的 API 参考文档 (使用 `mkdocstrings`)。
  - 对应源码模块结构 (如 `api.md`, `struct.md`, `fields.md`)。
- **`docs/usage/`**: 用户指南、核心概念和教程。
  - `models.md`: 定义结构体。
  - `serialization.md`: 序列化与 API。
  - `cli.md`: 命令行工具使用说明。
- **`docs/index.md`**: 项目主页和快速开始。
- **`mkdocs.yml`**: MkDocs 配置文件。

### 5.3 文档编写规范 (Documentation Standards)

本节定义了如何编写高质量的自动化文档，确保“代码即文档”的理念得以落地。

**语法**: 使用标准 Markdown 语法，结合 MkDocs Material Theme 的扩展功能（如 Admonitions, 代码块标题等）。
**扩展语法**: `PyMdown Extensions`，需在 `mkdocs.yml` 中启用。
**扩展**: 位于 `mkdocs.yml` 中的 `plugins` 和 `markdown_extensions` 配置。

#### 5.3.1 API 参考文档 (API Reference)

API 文档应通过 `mkdocstrings` 自动从源码中提取，保持同步。

- **引用语法**: 在 `docs/api/` 目录下的 `.md` 文件中，使用 `::: <identifier>` 语法。
- **控制范围**:
- 使用 `options` 过滤掉不必要的私有成员（以 `_` 开头但非 `__init__`）。
- **示例**:

```markdown
# JceStruct 核心类

::: jce.struct.JceStruct
    options:
      members:
        - __init__
        - model_validate
        - encode
        - decode

```

#### 概念与指南文档 (Concept & Guides)

位于 `docs/usage/`，侧重于高层逻辑和最佳实践。

- **How-to 导向**: 每个页面应解决一个具体问题（例如：“如何处理动态长度前缀”）。
- **代码块增强**:
- 必须指定语言标识符（`python`, `bash`, `toml`）。
- 使用 `title` 属性标注文件名（可选）。

```python title="example.py"
# 示例代码应具备完整性
from jce import JceStruct, JceField
...

```

#### 交叉引用与链接 (Cross-referencing)

- **API 相互引用**: 在文档中使用反引号包裹标识符，`mkdocstrings` 通常会自动建立链接。例如：`参考 [JceStruct][jce.struct.JceStruct] 以获取更多信息`。
- **外部链接**: 引用 Pydantic 或 Python 标准库文档时，使用标准 Markdown 链接。
- **内部跳转**: 使用相对路径链接到其他文档页面：`[查看序列化指南](../usage/serialization.md)`。

---

- **Admonitions (提示框)**: 善用不同级别的提示来突出重点：
- `!!! note`: 一般信息。
- `!!! warning`: 技术陷阱或不建议的操作（如 Union 类型限制）。
- `??? info`: 展开式信息，用于存放协议底层的 Hex 细节。

## 父文档

参见 [../AGENTS.md](../AGENTS.md) 了解项目全局约定与构建指南。
