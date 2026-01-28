use crate::codec::consts::JceType;
use crate::codec::endian::Endianness;
use byteorder::BigEndian;
use bytes::BufMut;
use std::marker::PhantomData;

/// JCE 编码器，用于将数据序列化为二进制格式.
pub struct JceWriter<B = Vec<u8>, E = BigEndian> {
    buffer: B,
    _phantom: PhantomData<E>,
}

impl Default for JceWriter<Vec<u8>, BigEndian> {
    fn default() -> Self {
        Self::new()
    }
}

impl JceWriter<Vec<u8>, BigEndian> {
    /// 创建一个新的 JceWriter.
    pub fn new() -> Self {
        Self {
            buffer: Vec::with_capacity(128),
            _phantom: PhantomData,
        }
    }
}

impl<B: BufMut, E: Endianness> JceWriter<B, E> {
    /// 使用指定的缓冲区创建 JceWriter.
    pub fn with_buffer(buffer: B) -> Self {
        Self {
            buffer,
            _phantom: PhantomData,
        }
    }

    /// 获取编码后的字节流.
    #[inline]
    pub fn get_buffer(&self) -> &[u8]
    where
        B: AsRef<[u8]>,
    {
        self.buffer.as_ref()
    }

    /// 写入 Tag 和类型信息.
    #[inline]
    pub fn write_tag(&mut self, tag: u8, type_id: JceType) {
        let type_val = type_id as u8;
        if tag < 15 {
            // 低 4 位是类型，高 4 位是 Tag
            let header = (tag << 4) | type_val;
            self.buffer.put_u8(header);
        } else {
            // 高 4 位全 1 (15)，接着写入 Tag 字节，低 4 位是类型
            let header = (15 << 4) | type_val;
            self.buffer.put_u8(header);
            self.buffer.put_u8(tag);
        }
    }

    /// 写入整数.
    #[inline]
    pub fn write_int(&mut self, tag: u8, value: i64) {
        if value == 0 {
            self.write_tag(tag, JceType::ZeroTag);
        } else if value >= i8::MIN as i64 && value <= i8::MAX as i64 {
            self.write_tag(tag, JceType::Int1);
            self.buffer.put_u8(value as u8);
        } else if value >= i16::MIN as i64 && value <= i16::MAX as i64 {
            self.write_tag(tag, JceType::Int2);
            if E::IS_LITTLE {
                self.buffer.put_i16_le(value as i16);
            } else {
                self.buffer.put_i16(value as i16);
            }
        } else if value >= i32::MIN as i64 && value <= i32::MAX as i64 {
            self.write_tag(tag, JceType::Int4);
            if E::IS_LITTLE {
                self.buffer.put_i32_le(value as i32);
            } else {
                self.buffer.put_i32(value as i32);
            }
        } else {
            self.write_tag(tag, JceType::Int8);
            if E::IS_LITTLE {
                self.buffer.put_i64_le(value);
            } else {
                self.buffer.put_i64(value);
            }
        }
    }

    /// 写入单精度浮点数.
    #[inline]
    pub fn write_float(&mut self, tag: u8, value: f32) {
        self.write_tag(tag, JceType::Float);
        if E::IS_LITTLE {
            self.buffer.put_f32_le(value);
        } else {
            self.buffer.put_f32(value);
        }
    }

    /// 写入双精度浮点数.
    #[inline]
    pub fn write_double(&mut self, tag: u8, value: f64) {
        self.write_tag(tag, JceType::Double);
        if E::IS_LITTLE {
            self.buffer.put_f64_le(value);
        } else {
            self.buffer.put_f64(value);
        }
    }

    /// 写入字符串.
    #[inline]
    pub fn write_string(&mut self, tag: u8, value: &str) {
        let bytes = value.as_bytes();
        let len = bytes.len();
        if len <= 255 {
            self.write_tag(tag, JceType::String1);
            self.buffer.put_u8(len as u8);
        } else {
            self.write_tag(tag, JceType::String4);
            if E::IS_LITTLE {
                self.buffer.put_u32_le(len as u32);
            } else {
                self.buffer.put_u32(len as u32);
            }
        }
        self.buffer.put_slice(bytes);
    }

    /// 写入字节数组 (SimpleList).
    #[inline]
    pub fn write_bytes(&mut self, tag: u8, value: &[u8]) {
        self.write_tag(tag, JceType::SimpleList);
        // Element type byte: 0 for Byte
        self.buffer.put_u8(0);
        // 写入长度，使用 write_int (Tag 0)
        self.write_int(0, value.len() as i64);
        self.buffer.put_slice(value);
    }
}

impl<E: Endianness> JceWriter<Vec<u8>, E> {
    /// 重置 Writer (针对 Vec 的特化实现).
    pub fn clear(&mut self) {
        self.buffer.clear();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_write_int_zero() {
        let mut writer = JceWriter::new();
        writer.write_int(0, 0);
        assert_eq!(writer.get_buffer(), b"\x0c"); // Tag 0, ZeroTag
    }

    #[test]
    fn test_write_int_small() {
        let mut writer = JceWriter::new();
        writer.write_int(0, 1);
        assert_eq!(writer.get_buffer(), b"\x00\x01"); // Tag 0, Int1, Value 1
    }

    #[test]
    fn test_write_int_16() {
        let mut writer = JceWriter::new();
        writer.write_int(0, 256);
        assert_eq!(writer.get_buffer(), b"\x01\x01\x00"); // Tag 0, Int2, Value 256 (0x0100)
    }

    #[test]
    fn test_write_string() {
        let mut writer = JceWriter::new();
        writer.write_string(0, "a");
        assert_eq!(writer.get_buffer(), b"\x06\x01\x61"); // Tag 0, String1, Len 1, 'a'
    }

    #[test]
    fn test_write_bytes() {
        let mut writer = JceWriter::new();
        writer.write_bytes(0, b"abc");
        assert_eq!(writer.get_buffer(), b"\x0d\x00\x00\x03abc");
    }

    #[test]
    fn test_high_tag() {
        let mut writer = JceWriter::new();
        writer.write_int(15, 1);
        assert_eq!(writer.get_buffer(), b"\xf0\x0f\x01"); // Tag 15, Int1, Value 1
    }
}
