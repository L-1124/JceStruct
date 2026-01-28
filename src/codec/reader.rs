use crate::codec::consts::JceType;
use crate::codec::endian::Endianness;
use crate::codec::error::{Error, Result};
use byteorder::ReadBytesExt;
use std::borrow::Cow;
use std::io::Cursor;
use std::marker::PhantomData;

/// JCE 数据读取器.
pub struct JceReader<'a, E: Endianness> {
    cursor: Cursor<&'a [u8]>,
    depth: usize,
    _phantom: PhantomData<E>,
}

impl<'a, E: Endianness> JceReader<'a, E> {
    /// 创建一个新的读取器.
    pub fn new(bytes: &'a [u8]) -> Self {
        Self {
            cursor: Cursor::new(bytes),
            depth: 0,
            _phantom: PhantomData,
        }
    }

    /// 获取当前偏移量.
    #[inline]
    pub fn position(&self) -> u64 {
        self.cursor.position()
    }

    /// 检查是否已到达末尾.
    #[inline]
    pub fn is_end(&self) -> bool {
        self.cursor.position() >= self.cursor.get_ref().len() as u64
    }

    /// 读取头部信息 (Tag 和 Type).
    #[inline]
    pub fn read_head(&mut self) -> Result<(u8, JceType)> {
        let pos = self.position();
        let b = self.cursor.read_u8().map_err(|_| Error::BufferOverflow {
            offset: pos as usize,
        })?;

        let type_id = b & 0x0F;
        let mut tag = (b & 0xF0) >> 4;

        if tag == 15 {
            tag = self.cursor.read_u8().map_err(|_| Error::BufferOverflow {
                offset: self.position() as usize,
            })?;
        }

        let jce_type = JceType::try_from(type_id).map_err(|id| Error::InvalidType {
            offset: pos as usize,
            type_id: id,
        })?;

        Ok((tag, jce_type))
    }

    /// 预览头部信息而不移动指针.
    pub fn peek_head(&mut self) -> Result<(u8, JceType)> {
        let pos = self.position();
        let res = self.read_head();
        self.cursor.set_position(pos);
        res
    }

    /// 读取整数.
    #[inline]
    pub fn read_int(&mut self, type_id: JceType) -> Result<i64> {
        let pos = self.position();
        match type_id {
            JceType::ZeroTag => Ok(0),
            JceType::Int1 => {
                let v = self.cursor.read_i8().map_err(|_| Error::BufferOverflow {
                    offset: pos as usize,
                })?;
                Ok(v as i64)
            }
            JceType::Int2 => {
                let v = self
                    .cursor
                    .read_i16::<E>()
                    .map_err(|_| Error::BufferOverflow {
                        offset: pos as usize,
                    })?;
                Ok(v as i64)
            }
            JceType::Int4 => {
                let v = self
                    .cursor
                    .read_i32::<E>()
                    .map_err(|_| Error::BufferOverflow {
                        offset: pos as usize,
                    })?;
                Ok(v as i64)
            }
            JceType::Int8 => {
                let v = self
                    .cursor
                    .read_i64::<E>()
                    .map_err(|_| Error::BufferOverflow {
                        offset: pos as usize,
                    })?;
                Ok(v)
            }
            _ => Err(Error::new(
                pos as usize,
                format!("Cannot read int from type {:?}", type_id),
            )),
        }
    }

    /// 读取单精度浮点数.
    #[inline]
    pub fn read_float(&mut self) -> Result<f32> {
        let pos = self.position();
        self.cursor
            .read_f32::<E>()
            .map_err(|_| Error::BufferOverflow {
                offset: pos as usize,
            })
    }

    /// 读取双精度浮点数.
    #[inline]
    pub fn read_double(&mut self) -> Result<f64> {
        let pos = self.position();
        self.cursor
            .read_f64::<E>()
            .map_err(|_| Error::BufferOverflow {
                offset: pos as usize,
            })
    }

    /// 读取字符串 (零拷贝).
    pub fn read_string(&mut self, type_id: JceType) -> Result<Cow<'a, str>> {
        let pos = self.position();
        let len = match type_id {
            JceType::String1 => self.cursor.read_u8().map_err(|_| Error::BufferOverflow {
                offset: pos as usize,
            })? as usize,
            JceType::String4 => {
                let len = self
                    .cursor
                    .read_u32::<E>()
                    .map_err(|_| Error::BufferOverflow {
                        offset: pos as usize,
                    })?;
                len as usize
            }
            _ => {
                return Err(Error::new(
                    pos as usize,
                    format!("Cannot read string from type {:?}", type_id),
                ));
            }
        };

        let start = self.cursor.position() as usize;
        let end = start + len;
        let data = self.cursor.get_ref();

        if end > data.len() {
            return Err(Error::BufferOverflow { offset: start });
        }

        let slice = &data[start..end];
        let s = std::str::from_utf8(slice)
            .map_err(|e| Error::new(start, format!("Invalid UTF-8 string: {}", e)))?;

        self.cursor.set_position(end as u64);
        Ok(Cow::Borrowed(s))
    }

    /// 跳过当前字段.
    pub fn skip_field(&mut self, type_id: JceType) -> Result<()> {
        if self.depth > 100 {
            return Err(Error::new(
                self.position() as usize,
                "Max recursion depth exceeded in skip_field",
            ));
        }

        self.depth += 1;
        let res = self.do_skip_field(type_id);
        self.depth -= 1;
        res
    }

    /// 实际的跳过逻辑.
    ///
    /// 递归处理容器类型 (Map, List, Struct).
    fn do_skip_field(&mut self, type_id: JceType) -> Result<()> {
        let pos = self.position();
        match type_id {
            JceType::Int1 => self.skip(1),
            JceType::Int2 => self.skip(2),
            JceType::Int4 => self.skip(4),
            JceType::Int8 => self.skip(8),
            JceType::Float => self.skip(4),
            JceType::Double => self.skip(8),
            JceType::String1 => {
                let len = self.cursor.read_u8().map_err(|_| Error::BufferOverflow {
                    offset: pos as usize,
                })?;
                self.skip(len as u64)
            }
            JceType::String4 => {
                let len = self
                    .cursor
                    .read_u32::<E>()
                    .map_err(|_| Error::BufferOverflow {
                        offset: pos as usize,
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
                    return Err(Error::new(
                        self.position() as usize,
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

    /// 读取字节数组 (零拷贝).
    pub fn read_bytes(&mut self, len: usize) -> Result<&'a [u8]> {
        let pos = self.position() as usize;
        let data = self.cursor.get_ref();
        let end = pos + len;

        if end > data.len() {
            return Err(Error::BufferOverflow { offset: pos });
        }

        let slice = &data[pos..end];
        self.cursor.set_position(end as u64);
        Ok(slice)
    }

    /// 跳过指定长度的字节.
    ///
    /// 检查边界，更新游标位置.
    fn skip(&mut self, len: u64) -> Result<()> {
        let pos = self.position();
        let new_pos = pos + len;
        if new_pos > self.cursor.get_ref().len() as u64 {
            return Err(Error::BufferOverflow {
                offset: pos as usize,
            });
        }
        self.cursor.set_position(new_pos);
        Ok(())
    }

    /// 读取一个字节.
    #[inline]
    pub fn read_u8(&mut self) -> Result<u8> {
        let pos = self.position();
        self.cursor.read_u8().map_err(|_| Error::BufferOverflow {
            offset: pos as usize,
        })
    }

    /// 读取 JCE 容器的大小 (List/Map/SimpleList 长度).
    /// 读取容器大小 (Size).
    ///
    /// JCE 中大小也是一个 Tag 为 0 的整数，但类型可能是 Int1/2/4.
    /// 此方法自动解析并返回 i32 大小.
    #[inline]
    pub fn read_size(&mut self) -> Result<i32> {
        let (_, t) = self.read_head()?;
        self.read_int(t).map(|v| v as i32)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use byteorder::{BigEndian, LittleEndian};

    #[test]
    fn test_read_head() {
        // Tag 1, Type Int1 (0)
        let data = b"\x10";
        let mut reader = JceReader::<BigEndian>::new(data);
        let (tag, t) = reader.read_head().unwrap();
        assert_eq!(tag, 1);
        assert_eq!(t, JceType::Int1);

        // Tag 15, Type Int1 (0) -> 2-byte header
        let data = b"\xF0\x0F";
        let mut reader = JceReader::<BigEndian>::new(data);
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
        let mut reader = JceReader::<BigEndian>::new(data);
        assert_eq!(reader.read_int(JceType::Int1).unwrap(), 0);
        assert_eq!(reader.read_int(JceType::Int2).unwrap(), 1);
        assert_eq!(reader.read_int(JceType::Int4).unwrap(), 1);
        assert_eq!(reader.read_int(JceType::Int8).unwrap(), 1);
        assert_eq!(reader.read_int(JceType::ZeroTag).unwrap(), 0);
    }

    #[test]
    fn test_read_string() {
        let data = b"\x05Hello\x00\x00\x00\x05World";
        let mut reader = JceReader::<BigEndian>::new(data);
        assert_eq!(reader.read_string(JceType::String1).unwrap(), "Hello");
        assert_eq!(reader.read_string(JceType::String4).unwrap(), "World");
    }

    #[test]
    fn test_skip_field() {
        let data = b"\x1A\x10\x01\x0B";
        let mut reader = JceReader::<BigEndian>::new(data);
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
        let mut reader = JceReader::<LittleEndian>::new(data);
        assert_eq!(reader.read_int(JceType::Int2).unwrap(), 1);

        // Int4: 1 in Little Endian (0x01 0x00 0x00 0x00)
        let data = b"\x01\x00\x00\x00";
        let mut reader = JceReader::<LittleEndian>::new(data);
        assert_eq!(reader.read_int(JceType::Int4).unwrap(), 1);

        // String4: "A" with length 1 in Little Endian (0x01 0x00 0x00 0x00 'A')
        let data = b"\x01\x00\x00\x00A";
        let mut reader = JceReader::<LittleEndian>::new(data);
        assert_eq!(reader.read_string(JceType::String4).unwrap(), "A");
    }
}
