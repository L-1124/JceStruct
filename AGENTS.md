# JceStruct Agent 指南

本文档为在 JceStruct 仓库工作的 AI Agent 提供必要的上下文和规则。

**包名**: `jce` (Python 模块)  未发布到pypi
**当前版本**: `1.0.0`

## 1. 环境与命令

### 1.1 包管理

- **工具**: `uv`
- **依赖**: 在 `pyproject.toml` 中管理 (requires-python >= 3.10)。
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

- **工具**: `ruff` (在 `pyproject.toml` 中配置)。
- **配置**:
  - 行长: 88 字符。
  - Python 目标: 3.10。
  - 文档风格: Google 约定。
  - 检查规则: E, F, B, I, UP, SIM, RUF, C4, PT, RET, ARG, ERA, PL, TRY, PERF, D。
- **命令**:
  - 检查: `uv run ruff check .`
  - 格式化: `uv run ruff format .`
  - 自动修复: `uv run ruff check --fix .`

### 1.4 构建

- **后端**: `hatchling`。
- **构建命令**: `python -m build` (或 `hatch build`)。

## 2. 代码风格与约定

### 2.1 通用

- **语言**: 文档字符串和注释应使用 **中文**。
- **符号**: 使用英文符号
- **缩进**: 4 个空格。
- **行长**: 软限制约 80-88 字符 (由 Ruff 强制执行)。

### 2.2 命名

- **类**: `PascalCase` (例如 `JceStruct`, `JceField`)。
- **函数/方法**: `snake_case` (例如 `model_validate`, `to_bytes`)。
- **变量**: `snake_case`。
- **常量**: `UPPER_SNAKE_CASE` (例如 `OPT_LITTLE_ENDIAN`)。
- **私有**: 使用单下划线前缀 `_` (例如 `_buffer`)。

### 2.3 导入

- **风格**: **相对导入** (例如 `from .types import INT`)。
- **排序**: 标准库 -> 第三方 (`pydantic`) -> 本地 (`jce`)。
- **分组**: 多行导入使用圆括号。

### 2.4 类型提示

- **严格性**: 高。所有函数签名和字段都使用类型提示。
- **工具**: `pydantic` v2.0+ 是数据建模的核心。
- **泛型**: 使用 `list[T]`, `dict[K, V]` (Python 3.9+ 风格)。
- **联合类型**: **不支持** (除了 `Optional[T]`)。
  - `T | None`: 支持。
  - `T1 | T2`: 定义时抛出 `TypeError` 以防止歧义。
- **Bytes 模式**: `loads` 和 `load` 函数支持 `bytes_mode` 参数:
  - `"raw"`: 保持原始字节。
  - `"string"`: 尝试转为 UTF-8 字符串。
  - `"auto"`: (默认) 智能模式, 尝试解析嵌套 JCE, 失败则转字符串, 最后保持原始字节。
- **JceStruct**: 字段必须使用带有 `jce_id` 的 `JceField`。

  ```python
  class User(JceStruct):
      uid: int = JceField(jce_id=0, jce_type=types.INT)
  ```

### 2.5 错误处理

- **基类**: `JceError` (在 `jce.exceptions` 中)。
- **具体错误**:
  - `JceEncodeError`: 编码失败。
  - `JceDecodeError`: 解码失败。
  - `JcePartialDataError`: 数据不完整(流处理时常用)。
  - `JceTypeError`: 类型不匹配。
  - `JceValueError`: 值无效或超出范围。
- **模式**: 使用描述性消息抛出具体异常。

### 2.6 日志

- **Logger**: 使用 `jce.log.logger`。
- **模式**: 如果有助于调试，在抛出异常前记录错误/警告。

## 3. 架构与模式

### 3.1 核心组件

- **`jce/__init__.py`**: 公开 API 入口, 导出所有核心类和函数。
- **`jce/api.py`**: 公开 API 层。提供 `dumps`/`loads` (字节操作) 和 `dump`/`load` (文件 IO), 支持 `bytes_mode` 和 `context`。
- **`jce/stream.py`**: 流式序列化支持。提供 `JceStreamWriter` / `JceStreamReader` 基类, 以及支持网络协议的 `LengthPrefixedWriter` / `LengthPrefixedReader`。
- **`jce/context.py`**: 序列化上下文定义 (`SerializationInfo`, `DeserializationInfo`)。
- **`jce/config.py`**: 配置对象 (`JceConfig`), 统一管理选项、上下文和 bytes_mode。
- **`jce/options.py`**: 选项标志常量定义 (`JceOption` IntFlag)。
- **`jce/struct.py`**: `JceStruct` 基类、`JceField` 工厂函数、`JceDict` 匿名结构体类。
- **`jce/types.py`**: JCE 类型定义 (`JceType` 基类及各类型实现)。
- **`jce/encoder.py`**: 二进制编码逻辑核心 (`DataWriter`, `JceEncoder`)。
- **`jce/decoder.py`**: 二进制解码逻辑核心 (`DataReader`, `GenericDecoder`, `SchemaDecoder`, `NodeDecoder`, `JceNode`)。
- **`jce/adapter.py`**: 类型适配器 (`JceTypeAdapter`), 提供类似 Pydantic TypeAdapter 的接口。
- **`jce/exceptions.py`**: 异常定义 (6 个异常类)。
- **`jce/const.py`**: JCE 协议常量定义 (类型码、魔数等)。
- **`jce/log.py`**: 日志配置。
- **`jce/__main__.py`**: CLI 工具入口 (可选依赖 click)。

### 3.2 协议实现

- 遵循 JCE (腾讯 Tars) 协议规范。
- 默认支持 **大端序**。
- 实现了特定优化，如 `Zero Tag` (0x0C) 和 `Simple List` (0x0D)。

### 3.3 数据建模

- 继承自 `JceStruct`。
- 使用类型注解和 `JceField` 定义字段。
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

## 4. 文档

- **Docstrings**: Google 风格。
- **语言**: **中文，但是使用半角标点**。
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

## 5. Git 与工作流

- **提交**: 使用约定式提交 (feat, fix, docs, test, chore)。
- **PR**: 提交前确保通过测试并通过代码检查。
- **发布**:
  - 通过 GitHub Actions 自动执行 (`release.yml`)。
  - 通过推送标签触发 (例如 `git tag v0.2.0 && git push origin v0.2.0`)。
  - 使用 `uv build` 和 Trusted Publishing (OIDC) 发布到 PyPI。
  - 创建带有自动生成说明的 GitHub Release。

## 6. 测试约定

### 6.1 测试风格

- **框架**: `pytest` (v9.0.2+)。
- **风格**: 使用函数式测试 (`def test_xxx()`), 而非类式 (`class TestXxx:`).
- **位置**: `tests/` 目录 (扁平结构, 所有测试文件位于同一层级)。

### 6.2 命名约定

- **测试函数**: `test_<function>_<expected_behavior>`
  - 例: `test_loads_with_bytes_mode_raw_preserves_bytes`
  - 例: `test_field_serializer_transforms_value_on_encode`
  - 例: `test_cli_help`
- **Fixtures**: 使用 `@pytest.fixture` 提供共享 setup, 遵循 snake_case 命名。

### 6.3 文档字符串

- **语言**: **中文**。
- **内容**: 描述测试的预期行为, 不需要描述实现细节。
- **格式**: 单行, 简洁明了。
- **示例**:

  ```python
  def test_loads_with_invalid_data_raises_decode_error():
      """loads() 应该在数据无效时抛出 JceDecodeError."""
      ...
  ```

### 6.4 结构

```python
"""模块级文档字符串, 描述测试文件覆盖的功能."""

import pytest

from jce import ...


@pytest.fixture
def sample_struct():
    """提供测试用的示例结构体."""
    return SomeStruct(...)


def test_function_expected_behavior(sample_struct):
    """函数应该在特定条件下产生预期结果."""
    # Arrange (准备)
    ...
    
    # Act (执行)
    result = function_under_test(...)
    
    # Assert (断言)
    assert result == expected
```

### 6.5 最佳实践

- **独立性**: 每个测试函数应独立运行, 不依赖其他测试的状态。
- **Fixtures 优于 Setup**: 使用 `@pytest.fixture` 而非在测试函数开头重复 setup 代码。
- **显式断言**: 使用清晰的断言, 避免 `assert result` 这类模糊断言。
- **边界情况**: 覆盖边界条件和错误路径。
- **未使用参数**: API 要求但测试不使用的参数, 使用 `_` 代替。

  ```python
  def serialize_value(self, value: str, _):
      return value.upper()
  ```

## 7. 文档生成 (MkDocs)

项目使用 **MkDocs** (Material Theme) 生成静态文档网站。

### 7.1 结构

文档源文件位于 `docs/` 目录：

- **`docs/api/`**: 自动生成的 API 参考文档 (使用 `mkdocstrings`)。
  - 对应源码模块结构 (如 `api.md`, `struct.md`, `fields.md`)。
- **`docs/usage/`**: 用户指南、核心概念和教程。
  - `models.md`: 定义结构体。
  - `serialization.md`: 序列化与 API。
  - `cli.md`: 命令行工具使用说明。
- **`docs/index.md`**: 项目主页和快速开始。
- **`mkdocs.yml`**: MkDocs 配置文件。

### 7.2 命令

- **安装依赖**:
  ```bash
  uv add --group docs mkdocs-material mkdocstrings[python]
  # 或同步环境
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

### 7.3 编写规范

- **API 文档**:
  使用 `mkdocstrings` 语法引用 Python 对象：
  ```markdown
  ::: jce.JceStruct
      
  ```
- **概念文档**:
  专注于"如何做" (How-to) 和"为什么" (Why)。代码块应可运行。
- **交叉引用**:
  链接到其他文档页面或 API 定义。
