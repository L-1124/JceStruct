# JceStruct Agent 指南

本文档为在 JceStruct 仓库工作的 AI Agent 提供必要的上下文和规则。

**包名**: `jce` (Python 模块)  
**当前版本**: `jce/__init__.py` 中的 `__version__` 变量。

**`AGENTS.md` 更新规则**:

- 本文件由 AI Agent 维护和更新。
- 每次修改后，AI Agent 应更新此文件以反映最新的代码结构和约定。
- AI Agent 应确保文档内容与实际代码保持一致，避免过时或错误的信息。

## 1. 环境与命令

### 1.1 包管理

- **工具**: `uv`
- **依赖**: 位于 `pyproject.toml`
- **安装**: `uv pip install -e .` 或 `uv pip install -e .[cli]` (包含 CLI 工具)。
- **开发依赖**: `uv sync --all-groups --all-extras` 。

### 1.2 测试

- **框架**: `pytest` (v9.0.0+)。
- **位置**: `tests/` 目录 (扁平结构, 无子目录)。
- **覆盖率**: 使用 `pytest-cov` 插件。
- **命令**:
  - 运行所有测试: `uv run pytest` 自带覆盖率报告。
  - 运行单个文件: `uv run pytest tests/test_struct.py`
  - 运行单个用例: `uv run pytest tests/test_struct.py::test_struct_defaults`
  - 详细模式: `uv run pytest -v`
  - 覆盖率报告: `uv run pytest --cov=jce --cov-report=term-missing`

### 1.3 代码检查与格式化

- **工具**: `ruff`
- **配置**: `pyproject.toml`
- **命令**:
  - 检查: `uv run ruff check .`
  - 格式化: `uv run ruff format .`
  - 自动修复: `uv run ruff check --fix .`

### 1.4 构建

- **后端**: `hatchling`。
- **构建命令**: `uv build`。

## 2. 代码风格与约定

### 2.1 通用

- **语言**: 文档字符串和注释应使用 **中文**，但是使用英文符号
- **缩进**: 4 个空格。
- **行长**: 软限制约 80-88 字符 (由 Ruff 强制执行)。

### 2.2 注释和文档字符串

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

#### 2.2.1 源码注释规范 (Google Style Docstrings)

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

### 2.3 命名

- **类**: `PascalCase` (例如 `JceStruct`, `JceField`)。
- **函数/方法**: `snake_case` (例如 `model_validate`, `to_bytes`)。
- **变量**: `snake_case`。
- **常量**: `UPPER_SNAKE_CASE` (例如 `OPT_LITTLE_ENDIAN`)。
- **私有**: 使用单下划线前缀 `_` (例如 `_buffer`)。

### 2.4 导入

- **风格**: **相对导入** (例如 `from .types import INT`)。
- **排序**: 标准库 -> 第三方 (`pydantic`) -> 本地 (`jce`)。
- **分组**: 多行导入使用圆括号。

### 2.5 类型提示

- **严格性**: 高。所有函数签名和字段都使用类型提示。
- **工具**: `pydantic` v2.0+ 是数据建模的核心。
- **泛型**: 使用 `list[T]`, `dict[K, V]` (Python 3.10+ 风格)。

## 3. 架构与模式

### 3.1 核心组件

- **`jce/__init__.py`**: 公开 API 入口, 导出所有核心类和函数。
- **`jce/api.py`**: 公开 API 层。提供 `dumps`/`loads` (字节操作) 和 `dump`/`load` (文件 IO), 支持 `bytes_mode` 和 `context`。
- **`jce/jce_core`**: (Rust 核心) 提供高性能的二进制编解码逻辑。
- **`jce/stream.py`**: 流式序列化支持。提供 `JceStreamWriter` / `JceStreamReader` 基类, 以及支持网络协议的 `LengthPrefixedWriter` / `LengthPrefixedReader`。
- **`jce/context.py`**: 序列化上下文定义 (`SerializationInfo`, `DeserializationInfo`)。
- **`jce/config.py`**: 配置对象 (`JceConfig`), 统一管理选项、上下文和 bytes_mode。
- **`jce/options.py`**: 选项标志常量定义 (`JceOption` IntFlag)。
- **`jce/struct.py`**: `JceStruct` 基类、`JceField` 工厂函数、`JceDict` 匿名结构体类。
- **`jce/types.py`**: JCE 类型定义 (`JceType` 基类及各类型实现)。
- **`jce/adapter.py`**: 类型适配器 (`JceTypeAdapter`), 提供类似 Pydantic TypeAdapter 的接口。
- **`jce/exceptions.py`**: 异常定义 (6 个异常类)。
- **`jce/const.py`**: JCE 协议常量定义 (类型码、魔数等)。
- **`jce/log.py`**: 日志配置。
- **`jce/__main__.py`**: CLI 工具入口 (需要可选依赖 click)。
- **`jce/adapter.py`**: 类型适配器 (`JceTypeAdapter`), 提供类似 Pydantic TypeAdapter 的接口。
- **`jce/exceptions.py`**: 异常定义 (6 个异常类)。
- **`jce/const.py`**: JCE 协议常量定义 (类型码、魔数等)。
- **`jce/log.py`**: 日志配置。
- **`jce/__main__.py`**: CLI 工具入口 (需要可选依赖 click)。

### 3.2 协议实现

- 遵循 JCE (腾讯 Tars) 协议规范(`JCE_PROTOCOL.md`)。
- 默认支持 **大端序**。
- 实现了特定优化，如 `Zero Tag` (0x0C) 和 `Simple List` (0x0D)。

### 3.3 数据建模

- `JceStruct` 继承自 `pydantic.BaseModel`。
- 使用类型注解和 `JceField` 定义字段。
- **联合类型**: **不支持** (除了 `Optional[T]`)。
  - `T | None`: 支持。
  - `T1 | T2`: 定义时抛出 `TypeError` 以防止歧义。
- **自动解析 Bytes(SimpleList) 模式**: `loads` 和 `load` 函数支持 `bytes_mode` 参数:
  - `"raw"`: 保持原始字节。
  - `"string"`: 尝试转为 UTF-8 字符串。
  - `"auto"`: (默认) 智能模式, 尝试解析嵌套 JCE, 失败则转字符串, 最后保持原始字节。
- `jce_id` (标签) 是强制性的，且在结构体中必须唯一。
- **JceDict**: 用于匿名结构体 (键必须是 int, 代表 Tag ID)。
  - `JceDict({0: 100})` -> 编码为 JCE Struct。
  - `dict({0: 100})` -> 编码为 JCE Map。

### 3.4 Pydantic 兼容性

- **计算字段**: 逻辑上支持，但从 `model_json_schema()` 中排除 (标准 Pydantic 行为)。
- **IDE 支持**: `JceField` 依赖类属性注解进行 IDE 类型推断。
- **验证**: `model_validate` 和 `model_dump` 表现为标准 Pydantic v2 方法。

### 3.5 流式 API

针对网络流式数据, 提供长度前缀支持:

- **`LengthPrefixedWriter`**: 自动计算并添加长度头。
  - `pack(obj)`: 序列化并存入缓冲区。
  - `get_buffer()`: 获取打包后的字节流。
- **`LengthPrefixedReader`**: 增量解析带长度头的字节流。
  - `feed(data)`: 输入新到达的字节。
  - `for obj in unpacker:`: 迭代解析出完整对象。

### 3.6 字段自定义

通过装饰器自定义特定字段的编解码行为:

- **`@jce_field_serializer(field_name)`**:
  - 签名: `def method(self, value, info: SerializationInfo)`
  - 在编码前转换字段值。
- **`@jce_field_deserializer(field_name)`**:
  - 签名: `def method(cls, value, info: DeserializationInfo)`
  - 在解码后转换字段值。
- **Context**: 编解码函数可通过 `context` 参数传递外部状态, 在钩子中通过 `info.context` 访问。

### 3.6 错误处理

- **基类**: `JceError` (在 `jce.exceptions` 中)。
- **具体错误**:
  - `JceEncodeError`: 编码失败。
  - `JceDecodeError`: 解码失败。
  - `JcePartialDataError`: 数据不完整(流处理时常用)。
  - `JceTypeError`: 类型不匹配。
  - `JceValueError`: 值无效或超出范围。
- **模式**: 使用描述性消息抛出具体异常。

### 3.7 日志

- **Logger**: 使用 `jce.log.logger`。
- **模式**: 如果有助于调试，在抛出异常前记录错误/警告。

## 4. 测试约定

### 4.1 测试风格

- **框架**: 强制使用 `pytest` (v9.0.2+)。
- **模式**: 采用**函数式测试** (`def test_xxx()`)，禁止使用类式测试 (`class TestXxx`) 以保持代码简洁。
- **位置**: 所有测试文件位于根目录的 `tests/` 文件夹下，采用**扁平结构**（不创建子目录）。
- **原子性**: 测试函数必须短小且聚焦。一个测试函数只验证一个行为，严禁编写“万能测试函数”。

### 4.2 命名约定

- **测试文件**: `test_<被测模块>.py`
  - 例: `struct.py`  `test_struct.py`
- **测试函数**: `test_<被测函数>_<预期行为>`
  - 例: `test_loads_with_invalid_data_raises_decode_error`
- **Fixtures**: 遵循 `snake_case`，名称应反映其提供的对象或状态。

### 4.3 文档字符串与注释

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

### 4.5 进阶最佳实践

#### 1. 参数化测试 (Parametrize)

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

#### 2. 异常捕获

- 必须使用 `pytest.raises`。
- **严禁**使用宽泛的 `Exception`，必须指明具体的异常类（如 `ValueError`, `JceDecodeError`）。
- 建议使用 `match` 参数校验异常信息关键词。

#### 3. Warnings 处理

- 使用 `pytest.warns` 捕获预期的警告。
- **禁止**忽略警告或使用 `warnings` 模块手动捕获

#### 4. I/O 处理

- **内存化**: 涉及文件读取的测试，优先使用 `io.BytesIO` 或 `io.StringIO`。
- **临时文件**: 若必须操作物理文件，使用 pytest 内置的 `tmp_path` fixture。

#### 5. 显式断言

- 避免 `assert result`（除非结果本身是布尔值）。
- 使用 `assert result == expected`、`assert "key" in dict` 等明确的比较。
- 涉及浮点数对比时，使用 `pytest.approx()`。

### 4.6 核心协议测试 (Fundamental)

`test_protocol.py` 是库的**根本性测试**，必须保证 100% 通过。它定义了 JCE 协议实现的基准，任何破坏此文件测试用例的修改均被视为破坏性变更。

- **测试目标**: 验证确定的输入与预期的十六进制输出（Hex）完全一致。
- **断言要求**:
- 编码测试：断言生成的 bytes 转为 hex 字符串后与预期值完全匹配。
- 解码测试：断言从预期 hex 字符串还原的对象与原始对象等值。

## 5. 文档生成 (MkDocs)

项目使用 **MkDocs** (Material Theme) 生成静态文档网站。

### 5.1 结构

文档源文件位于 `docs/` 目录：

- **`docs/api/`**: 自动生成的 API 参考文档 (使用 `mkdocstrings`)。
  - 对应源码模块结构 (如 `api.md`, `struct.md`, `fields.md`)。
- **`docs/usage/`**: 用户指南、核心概念和教程。
  - `models.md`: 定义结构体。
  - `serialization.md`: 序列化与 API。
  - `cli.md`: 命令行工具使用说明。
- **`docs/index.md`**: 项目主页和快速开始。
- **`mkdocs.yml`**: MkDocs 配置文件。

### 5.2 命令

- **安装依赖**:

  ```bash
  uv sync --all-groups
  ```

- **本地预览**:
  启动实时重载的本地服务器：

  ```bash
  uv run mkdocs serve
  ```

  访问: `http://127.0.0.1:8000`

- **构建静态站**:
  生成 HTML 文件到 `site/` 目录：

  ```bash
  uv run mkdocs build
  ```

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

#### 5.3.2 概念与指南文档 (Concept & Guides)

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

- **Admonitions (提示框)**: 善用不同级别的提示来突出重点：
- `!!! note`: 一般信息。
- `!!! warning`: 技术陷阱或不建议的操作（如 Union 类型限制）。
- `??? info`: 展开式信息，用于存放协议底层的 Hex 细节。

#### 5.3.3 交叉引用与链接 (Cross-referencing)

- **API 相互引用**: 在文档中使用反引号包裹标识符，`mkdocstrings` 通常会自动建立链接。例如：`参考 [JceStruct][jce.struct.JceStruct] 以获取更多信息`。
- **外部链接**: 引用 Pydantic 或 Python 标准库文档时，使用标准 Markdown 链接。
- **内部跳转**: 使用相对路径链接到其他文档页面：`[查看序列化指南](../usage/serialization.md)`。

---

### 5.4 文档范例与覆盖准则

#### 5.4.1 文档语言要求

- **双语处理**: 虽然主要使用中文描述，但关键的技术术语（如 `Schema-less`, `Payload`, `Tag ID`）应保留英文，或在括号中标注。

#### 5.4.2 必须文档化的对象 (Public API)

凡是设计用于外部调用的“公共接口”，都必须有完整的文档字符串（docstrings）。

- 导出模块 (Public Modules)：作为包入口的 **init**.py。打算让用户通过 import 直接使用的 .py 文件。文档应说明该模块的用途及包含的主要工具。
- 公共类 (Public Classes)：所有不以 _开头的类。文档应说明类的功能、初始化参数（**init**）以及重要的属性。
- 公共函数与方法 (Public Functions & Methods)：模块层级的全局函数。类中的公共方法（不以_ 开头）。
- 判定标准： 只要这个函数被定义在 **all** 列表中，或者被预期在模块外调用，就必须写文档。

#### 5.4.3 建议文档化的对象 (Internal logic)

虽然这些对象不直接对最终用户开放，但为了团队协作和长期维护，应当编写文档:

- 复杂的私有方法 (Complex Private Methods)：虽然以 _开头，但如果逻辑极其复杂、算法深奥，必须记录其内部逻辑，防止后人（包括你自己）不敢修改。
- 抽象基类与接口 (Abstract Base Classes)：即便这些类不直接实例化，也需要说明子类必须实现哪些方法。
- 模块级变量 (Constants/Globals)：重要的配置常量或全局状态，应说明其含义和取值范围。

## 6. Git 与工作流

- **Commit**: 使用 `Conventional Commits` 规范 Commit Message。
- **PR**: Commit 前确保通过测试并通过代码检查
  - 运行 `uv run pytest` 运行测试
  - 运行 `uv run ruff check` 检查代码风格
  - 运行 `uvx basedpyright` 检查类型注解
  - 检查文档字符串完整性
  - 检查 `AGENTS.md` 是否需要更新
