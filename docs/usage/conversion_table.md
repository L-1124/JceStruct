# 类型转换表

本文档详细列出了 Python 类型与 JCE 协议类型之间的映射关系。

## 基础类型映射

| Python Type  | JCE Type ID | JCE Type Name                | 说明                         |
|:-------------|:------------|:-----------------------------|:-----------------------------|
| `int` (小)   | 0           | `INT1`                       | -128 <= x <= 127             |
| `int` (中)   | 1           | `INT2`                       | -32768 <= x <= 32767         |
| `int` (大)   | 2           | `INT4`                       | -2^31 <= x <= 2^31-1         |
| `int` (超大) | 3           | `INT8`                       | -2^63 <= x <= 2^63-1         |
| `float`      | 4           | `FLOAT`                      | 4字节单精度浮点数            |
| `float`      | 5           | `DOUBLE`                     | 8字节双精度浮点数 (**默认**) |
| `str` (短)   | 6           | `STRING1`                    | 长度 <= 255 的字符串         |
| `str` (长)   | 7           | `STRING4`                    | 长度 > 255 的字符串          |
| `dict`       | 8           | `MAP`                        | 键值对集合                   |
| `list`       | 9           | `LIST`                       | 元素列表                     |
| `Struct`     | 10, 11      | `STRUCT_BEGIN`, `STRUCT_END` | 结构体开始与结束标记         |
| `int` (0)    | 12          | `ZERO_TAG`                   | 数值 0 的特殊优化            |
| `bytes`      | 13          | `SIMPLE_LIST`                | 字节数组 (byte[])            |

## 详细转换规则

### 整数 (int)

Tarsio 会根据整数的实际值自动选择最节省空间的 JCE 类型进行编码：

* `0`: 编码为 `ZERO_TAG` (Type 12)，不占用 Value 字节。
* `-128 ~ 127`: 编码为 `INT1` (Type 0)。
* `-32768 ~ 32767`: 编码为 `INT2` (Type 1)。
* `-2147483648 ~ 2147483647`: 编码为 `INT4` (Type 2)。
* 更大范围: 编码为 `INT8` (Type 3)。

### 浮点数 (float)

* **编码**: 默认情况下，Python 的 `float` 会被编码为 JCE `DOUBLE` (Type 5)，以保持最高精度。如果显式指定了 `tars_type=types.FLOAT`，则会编码为 4 字节 `FLOAT`。
* **解码**: 自动识别 `FLOAT` 或 `DOUBLE` 类型并转换为 Python `float`。

### 字符串 (str)

* **编码**: 自动根据 UTF-8 编码后的字节长度选择 `STRING1` (Type 6) 或 `STRING4` (Type 7)。
* **解码**: 自动读取长度并解码 UTF-8 内容。

### 字节 (bytes)

* **编码**: 始终映射为 JCE `SIMPLE_LIST` (Type 13)。这是 JCE 协议中专门用于优化 `byte[]` 的类型，比普通的 `LIST<BYTE>` 更紧凑。
* **解码**: `SIMPLE_LIST` 会被直接解码为 Python `bytes` 对象。

### 列表 (list)

* **编码**: 映射为 JCE `LIST` (Type 9)。Tarsio 会检查列表元素的类型。如果所有元素都是相同的基础类型或结构体，它会进行优化。
* **注意**: JCE `LIST` 包含长度信息。

### 字典 (dict)

* **编码**: 映射为 JCE `MAP` (Type 8)。JCE Map 是有序的 Key-Value 对序列。
* **限制**: JCE Map 的 Key 可以是任何基本类型，但通常建议使用 `int` 或 `str`。

### 结构体 (Struct)

* **编码**: 实际上结构体在 JCE 中通常不使用 `STRUCT_BEGIN` / `STRUCT_END` 包装，除非它是作为另一个对象的字段值。
* **嵌套**: 当 `Struct` 作为字段被序列化时，它通常被展平为一系列 Tag-Value 对。但在 `LIST` 或 `MAP` 中，它可能会被标记界定。Tarsio 的具体实现倾向于兼容标准 Tars 行为。
