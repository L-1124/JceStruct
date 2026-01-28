use crate::codec::consts::JceType;
use crate::codec::endian::Endianness;
use crate::codec::error::{Error, Result};
use byteorder::ReadBytesExt;
use std::io::Cursor;
use std::marker::PhantomData;

/// 一个轻量级的 JCE 结构扫描器，仅用于验证二进制数据的结构合法性，不分配任何内存。
pub struct JceScanner<'a, E: Endianness> {
    cursor: Cursor<&'a [u8]>,
    depth: usize,
    max_depth: usize,
    _phantom: PhantomData<E>,
}

impl<'a, E: Endianness> JceScanner<'a, E> {
    pub fn new(bytes: &'a [u8]) -> Self {
        Self {
            cursor: Cursor::new(bytes),
            depth: 0,
            max_depth: 100,
            _phantom: PhantomData,
        }
    }

    #[inline]
    pub fn is_end(&self) -> bool {
        self.cursor.position() >= self.cursor.get_ref().len() as u64
    }

    /// 验证整个 Struct 结构。
    pub fn validate_struct(&mut self) -> Result<()> {
        if self.depth > self.max_depth {
            return Err(Error::new(
                self.cursor.position() as usize,
                "Max recursion depth exceeded",
            ));
        }
        self.depth += 1;

        while !self.is_end() {
            let (_tag, jce_type) = self.read_head()?;
            if jce_type == JceType::StructEnd {
                self.depth -= 1;
                return Ok(());
            }
            self.skip_field(jce_type)?;
        }

        // If we reached end without StructEnd, it's only okay if we are at root depth 1
        // (for raw packets that are just a sequence of fields)
        if self.depth == 1 {
            Ok(())
        } else {
            Err(Error::BufferOverflow {
                offset: self.cursor.position() as usize,
            })
        }
    }

    #[inline]
    fn read_head(&mut self) -> Result<(u8, JceType)> {
        let pos = self.cursor.position();
        let b = self.cursor.read_u8().map_err(|_| Error::BufferOverflow {
            offset: pos as usize,
        })?;
        let type_id = b & 0x0F;
        let mut tag = (b & 0xF0) >> 4;
        if tag == 15 {
            tag = self.cursor.read_u8().map_err(|_| Error::BufferOverflow {
                offset: self.cursor.position() as usize,
            })?;
        }
        let jce_type = JceType::try_from(type_id).map_err(|id| Error::InvalidType {
            offset: pos as usize,
            type_id: id,
        })?;
        Ok((tag, jce_type))
    }

    fn skip_field(&mut self, jce_type: JceType) -> Result<()> {
        match jce_type {
            JceType::Int1 => self.skip(1),
            JceType::Int2 => self.skip(2),
            JceType::Int4 => self.skip(4),
            JceType::Int8 => self.skip(8),
            JceType::Float => self.skip(4),
            JceType::Double => self.skip(8),
            JceType::String1 => {
                let len = self.cursor.read_u8().map_err(|_| Error::BufferOverflow {
                    offset: self.cursor.position() as usize,
                })?;
                self.skip(len as u64)
            }
            JceType::String4 => {
                let len = self
                    .cursor
                    .read_u32::<E>()
                    .map_err(|_| Error::BufferOverflow {
                        offset: self.cursor.position() as usize,
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
                let t = self.cursor.read_u8().map_err(|_| Error::BufferOverflow {
                    offset: self.cursor.position() as usize,
                })?;
                if t != 0 {
                    return Err(Error::new(
                        self.cursor.position() as usize,
                        "SimpleList must contain Byte",
                    ));
                }
                let len = self.read_size()?;
                self.skip(len as u64)
            }
            JceType::StructBegin => self.validate_struct(),
            JceType::StructEnd => Ok(()),
            JceType::ZeroTag => Ok(()),
        }
    }

    #[inline]
    fn skip(&mut self, len: u64) -> Result<()> {
        let pos = self.cursor.position();
        let new_pos = pos + len;
        if new_pos > self.cursor.get_ref().len() as u64 {
            return Err(Error::BufferOverflow {
                offset: pos as usize,
            });
        }
        self.cursor.set_position(new_pos);
        Ok(())
    }

    fn read_size(&mut self) -> Result<i32> {
        let (_, t) = self.read_head()?;
        match t {
            JceType::ZeroTag => Ok(0),
            JceType::Int1 => Ok(self.cursor.read_i8().map_err(|_| Error::BufferOverflow {
                offset: self.cursor.position() as usize,
            })? as i32),
            JceType::Int2 => Ok(self
                .cursor
                .read_i16::<E>()
                .map_err(|_| Error::BufferOverflow {
                    offset: self.cursor.position() as usize,
                })? as i32),
            JceType::Int4 => {
                Ok(self
                    .cursor
                    .read_i32::<E>()
                    .map_err(|_| Error::BufferOverflow {
                        offset: self.cursor.position() as usize,
                    })?)
            }
            _ => Err(Error::new(
                self.cursor.position() as usize,
                "Invalid size type",
            )),
        }
    }
}
