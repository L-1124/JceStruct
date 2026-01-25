use crate::consts::JceType;

/// JCE 编码器，用于将数据序列化为二进制格式.
pub struct JceWriter {
    buffer: Vec<u8>,
}

impl JceWriter {
    /// 创建一个新的 JceWriter.
    pub fn new() -> Self {
        Self {
            buffer: Vec::with_capacity(128),
        }
    }

    /// 获取编码后的字节流.
    pub fn get_buffer(&self) -> &[u8] {
        &self.buffer
    }

    /// 写入 Tag 和类型信息.
    pub fn write_tag(&mut self, tag: u8, type_id: JceType) {
        let type_val = type_id as u8;
        if tag < 15 {
            // 低 4 位是类型，高 4 位是 Tag
            let header = (tag << 4) | type_val;
            self.buffer.push(header);
        } else {
            // 高 4 位全 1 (15)，接着写入 Tag 字节，低 4 位是类型
            let header = (15 << 4) | type_val;
            self.buffer.push(header);
            self.buffer.push(tag);
        }
    }

    /// 写入整数.
    pub fn write_int(&mut self, tag: u8, value: i64) {
        if value == 0 {
            self.write_tag(tag, JceType::ZeroTag);
        } else if value >= i8::MIN as i64 && value <= i8::MAX as i64 {
            self.write_tag(tag, JceType::Int1);
            self.buffer.push(value as u8);
        } else if value >= i16::MIN as i64 && value <= i16::MAX as i64 {
            self.write_tag(tag, JceType::Int2);
            self.buffer.extend_from_slice(&(value as i16).to_be_bytes());
        } else if value >= i32::MIN as i64 && value <= i32::MAX as i64 {
            self.write_tag(tag, JceType::Int4);
            self.buffer.extend_from_slice(&(value as i32).to_be_bytes());
        } else {
            self.write_tag(tag, JceType::Int8);
            self.buffer.extend_from_slice(&value.to_be_bytes());
        }
    }

    /// 写入单精度浮点数.
    pub fn write_float(&mut self, tag: u8, value: f32) {
        self.write_tag(tag, JceType::Float);
        self.buffer.extend_from_slice(&value.to_be_bytes());
    }

    /// 写入双精度浮点数.
    pub fn write_double(&mut self, tag: u8, value: f64) {
        self.write_tag(tag, JceType::Double);
        self.buffer.extend_from_slice(&value.to_be_bytes());
    }

    /// 写入字符串.
    pub fn write_string(&mut self, tag: u8, value: &str) {
        let bytes = value.as_bytes();
        let len = bytes.len();
        if len <= 255 {
            self.write_tag(tag, JceType::String1);
            self.buffer.push(len as u8);
        } else {
            self.write_tag(tag, JceType::String4);
            self.buffer.extend_from_slice(&(len as u32).to_be_bytes());
        }
        self.buffer.extend_from_slice(bytes);
    }

    /// 写入字节数组 (SimpleList).
    pub fn write_bytes(&mut self, tag: u8, value: &[u8]) {
        self.write_tag(tag, JceType::SimpleList);
        self.write_tag(0, JceType::Int1);
        // 强制写入 Int1 0，不使用 ZeroTag 优化
        self.buffer.push(0);
        self.write_int(0, value.len() as i64);
        self.buffer.extend_from_slice(value);
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
        // Tag 0, SimpleList (13/0x0D) -> 0x0D
        // Tag 0, Int1 (0) -> 0x00
        // Value 0 (Int1) -> 0x00
        // Tag 0, Int1 (0), Value 3 -> 0x00 0x03
        // Data -> 0x61 0x62 0x63
        // Result: 0D 00 00 00 03 61 62 63
        assert_eq!(writer.get_buffer(), b"\x0d\x00\x00\x00\x03abc");
    }

    #[test]
    fn test_high_tag() {
        let mut writer = JceWriter::new();
        writer.write_int(15, 1);
        assert_eq!(writer.get_buffer(), b"\xf0\x0f\x01"); // Tag 15, Int1, Value 1
    }
}
