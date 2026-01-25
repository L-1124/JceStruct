use crate::consts::JceType;
use crate::error::JceDecodeError;
use byteorder::{BigEndian, LittleEndian, ReadBytesExt};
use std::io::Cursor;

/// JCE 数据读取器.
pub struct JceReader<'a> {
    cursor: Cursor<&'a [u8]>,
    little_endian: bool,
}

impl<'a> JceReader<'a> {
    /// 创建一个新的读取器.
    pub fn new(bytes: &'a [u8], options: i32) -> Self {
        Self {
            cursor: Cursor::new(bytes),
            little_endian: options & 1 != 0,
        }
    }

    /// 获取当前偏移量.
    pub fn position(&self) -> u64 {
        self.cursor.position()
    }

    /// 检查是否已到达末尾.
    pub fn is_end(&self) -> bool {
        self.cursor.position() >= self.cursor.get_ref().len() as u64
    }

    /// 读取头部信息 (Tag 和 Type).
    pub fn read_head(&mut self) -> Result<(u8, JceType), JceDecodeError> {
        let pos = self.position();
        let b = self
            .cursor
            .read_u8()
            .map_err(|_| JceDecodeError::BufferOverflow {
                path: format!("offset {}", pos),
            })?;

        let type_id = b & 0x0F;
        let mut tag = (b & 0xF0) >> 4;

        if tag == 15 {
            tag = self
                .cursor
                .read_u8()
                .map_err(|_| JceDecodeError::BufferOverflow {
                    path: format!("offset {}", self.position()),
                })?;
        }

        let jce_type = JceType::try_from(type_id).map_err(|id| JceDecodeError::InvalidType {
            path: format!("offset {}", pos),
            type_id: id,
        })?;

        Ok((tag, jce_type))
    }

    /// 预览头部信息而不移动指针.
    pub fn peek_head(&mut self) -> Result<(u8, JceType), JceDecodeError> {
        let pos = self.position();
        let res = self.read_head();
        self.cursor.set_position(pos);
        res
    }

    /// 读取整数.
    pub fn read_int(&mut self, type_id: JceType) -> Result<i64, JceDecodeError> {
        let pos = self.position();
        match type_id {
            JceType::ZeroTag => Ok(0),
            JceType::Int1 => {
                let v = self
                    .cursor
                    .read_i8()
                    .map_err(|_| JceDecodeError::BufferOverflow {
                        path: format!("offset {}", pos),
                    })?;
                Ok(v as i64)
            }
            JceType::Int2 => {
                let v = if self.little_endian {
                    self.cursor.read_i16::<LittleEndian>()
                } else {
                    self.cursor.read_i16::<BigEndian>()
                }
                .map_err(|_| JceDecodeError::BufferOverflow {
                    path: format!("offset {}", pos),
                })?;
                Ok(v as i64)
            }
            JceType::Int4 => {
                let v = if self.little_endian {
                    self.cursor.read_i32::<LittleEndian>()
                } else {
                    self.cursor.read_i32::<BigEndian>()
                }
                .map_err(|_| JceDecodeError::BufferOverflow {
                    path: format!("offset {}", pos),
                })?;
                Ok(v as i64)
            }
            JceType::Int8 => {
                let v = if self.little_endian {
                    self.cursor.read_i64::<LittleEndian>()
                } else {
                    self.cursor.read_i64::<BigEndian>()
                }
                .map_err(|_| JceDecodeError::BufferOverflow {
                    path: format!("offset {}", pos),
                })?;
                Ok(v)
            }
            _ => Err(JceDecodeError::new(
                format!("offset {}", pos),
                format!("Cannot read int from type {:?}", type_id),
            )),
        }
    }

    /// 读取单精度浮点数.
    pub fn read_float(&mut self) -> Result<f32, JceDecodeError> {
        let pos = self.position();
        if self.little_endian {
            self.cursor.read_f32::<LittleEndian>()
        } else {
            self.cursor.read_f32::<BigEndian>()
        }
        .map_err(|_| JceDecodeError::BufferOverflow {
            path: format!("offset {}", pos),
        })
    }

    /// 读取双精度浮点数.
    pub fn read_double(&mut self) -> Result<f64, JceDecodeError> {
        let pos = self.position();
        if self.little_endian {
            self.cursor.read_f64::<LittleEndian>()
        } else {
            self.cursor.read_f64::<BigEndian>()
        }
        .map_err(|_| JceDecodeError::BufferOverflow {
            path: format!("offset {}", pos),
        })
    }

    /// 读取字符串.
    pub fn read_string(&mut self, type_id: JceType) -> Result<String, JceDecodeError> {
        let pos = self.position();
        let len = match type_id {
            JceType::String1 => {
                self.cursor
                    .read_u8()
                    .map_err(|_| JceDecodeError::BufferOverflow {
                        path: format!("offset {}", pos),
                    })? as usize
            }
            JceType::String4 => {
                let len = if self.little_endian {
                    self.cursor.read_u32::<LittleEndian>()
                } else {
                    self.cursor.read_u32::<BigEndian>()
                }
                .map_err(|_| JceDecodeError::BufferOverflow {
                    path: format!("offset {}", pos),
                })?;
                len as usize
            }
            _ => {
                return Err(JceDecodeError::new(
                    format!("offset {}", pos),
                    format!("Cannot read string from type {:?}", type_id),
                ))
            }
        };

        let mut buf = vec![0u8; len];
        let current_pos = self.position();
        std::io::Read::read_exact(&mut self.cursor, &mut buf).map_err(|_| {
            JceDecodeError::BufferOverflow {
                path: format!("offset {}", current_pos),
            }
        })?;

        String::from_utf8(buf).map_err(|e| {
            JceDecodeError::new(
                format!("offset {}", current_pos),
                format!("Invalid UTF-8 string: {}", e),
            )
        })
    }

    /// 跳过当前字段.
    pub fn skip_field(&mut self, type_id: JceType) -> Result<(), JceDecodeError> {
        let pos = self.position();
        match type_id {
            JceType::Int1 => self.skip(1),
            JceType::Int2 => self.skip(2),
            JceType::Int4 => self.skip(4),
            JceType::Int8 => self.skip(8),
            JceType::Float => self.skip(4),
            JceType::Double => self.skip(8),
            JceType::String1 => {
                let len = self
                    .cursor
                    .read_u8()
                    .map_err(|_| JceDecodeError::BufferOverflow {
                        path: format!("offset {}", pos),
                    })?;
                self.skip(len as u64)
            }
            JceType::String4 => {
                let len = if self.little_endian {
                    self.cursor.read_u32::<LittleEndian>()
                } else {
                    self.cursor.read_u32::<BigEndian>()
                }
                .map_err(|_| JceDecodeError::BufferOverflow {
                    path: format!("offset {}", pos),
                })?;
                self.skip(len as u64)
            }
            JceType::Map => {
                let size = self.read_size()?;
                for _ in 0..size * 2 {
                    let (_, t) = self.read_head()?;
                    self.skip_field(t)?;
                }
                Ok(())
            }
            JceType::List => {
                let size = self.read_size()?;
                for _ in 0..size {
                    let (_, t) = self.read_head()?;
                    self.skip_field(t)?;
                }
                Ok(())
            }
            JceType::SimpleList => {
                let t = self.read_u8()?;
                if t != 0 {
                    return Err(JceDecodeError::new(
                        format!("offset {}", self.position()),
                        format!("SimpleList must contain Byte (0), got {}", t),
                    ));
                }
                let len = self.read_size()?;
                self.skip(len as u64)
            }
            JceType::StructBegin => {
                loop {
                    let (_, t) = self.read_head()?;
                    if t == JceType::StructEnd {
                        break;
                    }
                    self.skip_field(t)?;
                }
                Ok(())
            }
            JceType::StructEnd => Ok(()),
            JceType::ZeroTag => Ok(()),
        }
    }

    /// 读取字节数组.
    pub fn read_bytes(&mut self, len: usize) -> Result<Vec<u8>, JceDecodeError> {
        let pos = self.position();
        let mut buf = vec![0u8; len];
        std::io::Read::read_exact(&mut self.cursor, &mut buf).map_err(|_| {
            JceDecodeError::BufferOverflow {
                path: format!("offset {}", pos),
            }
        })?;
        Ok(buf)
    }

    fn skip(&mut self, len: u64) -> Result<(), JceDecodeError> {
        let pos = self.position();
        let new_pos = pos + len;
        if new_pos > self.cursor.get_ref().len() as u64 {
            return Err(JceDecodeError::BufferOverflow {
                path: format!("offset {}", pos),
            });
        }
        self.cursor.set_position(new_pos);
        Ok(())
    }

    /// 读取一个字节.
    pub fn read_u8(&mut self) -> Result<u8, JceDecodeError> {
        let pos = self.position();
        self.cursor
            .read_u8()
            .map_err(|_| JceDecodeError::BufferOverflow {
                path: format!("offset {}", pos),
            })
    }

    /// 读取 JCE 容器的大小 (List/Map/SimpleList 长度).
    pub fn read_size(&mut self) -> Result<i32, JceDecodeError> {
        let (_, t) = self.read_head()?;
        self.read_int(t).map(|v| v as i32)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_read_head() {
        // Tag 1, Type Int1 (0)
        let data = b"\x10";
        let mut reader = JceReader::new(data, 0);
        let (tag, t) = reader.read_head().unwrap();
        assert_eq!(tag, 1);
        assert_eq!(t, JceType::Int1);

        // Tag 15, Type Int1 (0) -> 2-byte header
        let data = b"\xF0\x0F";
        let mut reader = JceReader::new(data, 0);
        let (tag, t) = reader.read_head().unwrap();
        assert_eq!(tag, 15);
        assert_eq!(t, JceType::Int1);
    }

    #[test]
    fn test_read_int() {
        // Int1: 0
        // Int2: 1 (0x00 0x01)
        // Int4: 1 (0x00 0x00 0x00 0x01)
        // Int8: 1 (0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x01)
        let data = b"\x00\x00\x01\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x01";
        let mut reader = JceReader::new(data, 0);
        assert_eq!(reader.read_int(JceType::Int1).unwrap(), 0);
        assert_eq!(reader.read_int(JceType::Int2).unwrap(), 1);
        assert_eq!(reader.read_int(JceType::Int4).unwrap(), 1);
        assert_eq!(reader.read_int(JceType::Int8).unwrap(), 1);
        assert_eq!(reader.read_int(JceType::ZeroTag).unwrap(), 0);
    }

    #[test]
    fn test_read_string() {
        let data = b"\x05Hello\x00\x00\x00\x05World";
        let mut reader = JceReader::new(data, 0);
        assert_eq!(reader.read_string(JceType::String1).unwrap(), "Hello");
        assert_eq!(reader.read_string(JceType::String4).unwrap(), "World");
    }

    #[test]
    fn test_skip_field() {
        // StructBegin (10), Tag 1, Int1 (0), Value 1, StructEnd (11)
        // Tag 1, Type 10 (StructBegin) -> 0x1A
        // Tag 1, Type 0 (Int1) -> 0x10
        // Value 1 -> 0x01
        // Tag 0, Type 11 (StructEnd) -> 0x0B
        let data = b"\x1A\x10\x01\x0B";
        let mut reader = JceReader::new(data, 0);
        let (tag, t) = reader.read_head().unwrap();
        assert_eq!(tag, 1);
        assert_eq!(t, JceType::StructBegin);
        reader.skip_field(t).unwrap();
        assert!(reader.is_end());
    }

    #[test]
    fn test_little_endian() {
        // Int2: 1 in Little Endian (0x01 0x00)
        let data = b"\x01\x00";
        let mut reader = JceReader::new(data, 1); // OPT_LITTLE_ENDIAN = 1
        assert_eq!(reader.read_int(JceType::Int2).unwrap(), 1);

        // Int4: 1 in Little Endian (0x01 0x00 0x00 0x00)
        let data = b"\x01\x00\x00\x00";
        let mut reader = JceReader::new(data, 1);
        assert_eq!(reader.read_int(JceType::Int4).unwrap(), 1);

        // String4: "A" with length 1 in Little Endian (0x01 0x00 0x00 0x00 'A')
        let data = b"\x01\x00\x00\x00A";
        let mut reader = JceReader::new(data, 1);
        assert_eq!(reader.read_string(JceType::String4).unwrap(), "A");
    }
}
