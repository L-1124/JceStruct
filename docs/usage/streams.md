# 流式处理

在网络编程（如 TCP 通信）中，常常需要处理**粘包**（多个数据包合并接收）和**拆包**（一个数据包分多次接收）的问题。JceStruct 提供了专门的流式读写器来解决这些问题。

## 长度前缀协议

JceStruct 实现了 `LengthPrefixedReader` 和 `LengthPrefixedWriter`，支持处理带有长度头部的 JCE 数据流。

### 写入 (Writer)

`LengthPrefixedWriter` 会自动在数据前添加长度头。

!!! note "前提条件"
    本节示例假设你已经定义了 `User` 结构体。详见 [定义模型](models.md)。

```python title="writer.py"
from jce.stream import LengthPrefixedWriter
# from my_models import User

# 初始化 Writer
writer = LengthPrefixedWriter(
    length_type=4,              # 4字节头 (INT4)
    little_endian_length=False, # 大端序
    inclusive_length=True       # 长度包含头部本身
)

# 假设我们定义了 User 结构体 (参见 models.md)
user1 = User(uid=1, name="Alice")
user2 = User(uid=2, name="Bob")

# 写入多个包
writer.pack(user1)
writer.pack(user2)

# 获取完整的字节流 (用于发送)
buffer = writer.get_buffer()
# > [Len][Body][Len][Body]...
# socket.send(buffer)
```

### 读取 (Reader)

`LengthPrefixedReader` 是一个迭代器，它维护内部缓冲区，自动处理分片数据，仅当接收到完整的数据包时才产出对象。

```python title="reader.py"
from jce.stream import LengthPrefixedReader

reader = LengthPrefixedReader(
    target=User,  # 目标结构体
    length_type=4,
    inclusive_length=True
)

# 模拟接收数据 (分片到达)
# 假设 buffer 是 [Packet1_PartA] (数据不完整)
reader.feed(buffer_part_a)

# 此时数据不足，没有任何输出
assert list(reader) == []

# 接收剩余部分
# [Packet1_PartB][Packet2] (补全包1，且包含包2)
reader.feed(buffer_part_b)

# 此时可以迭代出完整的对象
for user in reader:
    print(f"Received: {user.name}")
    # > Received: Alice
    # > Received: Bob
```
