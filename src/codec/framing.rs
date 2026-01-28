use thiserror::Error;

/// JCE 分帧错误定义
#[derive(Debug, Error, PartialEq, Clone)]
pub enum FrameError {
    #[error("Frame length {0} is invalid (less than header length {1})")]
    InvalidLength(usize, usize),
    #[error("Frame length {0} exceeds limit {1}")]
    FrameTooLarge(usize, usize),
}

/// JCE 流式分帧逻辑 (纯 Rust 实现).
///
/// 该模块负责处理带长度前缀的数据帧解析，不依赖任何 Python 组件。
#[derive(Debug, Clone, Copy)]
pub struct JceFramer {
    pub length_type: u8,
    pub inclusive_length: bool,
    pub little_endian: bool,
    pub max_frame_size: usize,
}

impl JceFramer {
    /// 创建一个新的分帧器.
    ///
    /// # Params
    /// * `length_type`: 长度头字节数 (1, 2, 4)
    /// * `inclusive_length`: 长度值是否包含头部本身
    /// * `little_endian`: 长度值是否为小端序
    /// * `max_frame_size`: 允许的最大帧大小 (字节)，超过此值将返回错误
    ///
    /// # Panics
    /// 如果 `length_type` 不是 1, 2, 或 4，则 panic。
    pub fn new(
        length_type: u8,
        inclusive_length: bool,
        little_endian: bool,
        max_frame_size: usize,
    ) -> Self {
        assert!(
            matches!(length_type, 1 | 2 | 4),
            "length_type must be 1, 2, or 4"
        );
        Self {
            length_type,
            inclusive_length,
            little_endian,
            max_frame_size,
        }
    }

    /// 检查缓冲区是否包含完整的帧.
    ///
    /// # Returns
    /// - `Ok(Some(packet_len))`: 发现完整数据包，返回包总长度。
    /// - `Ok(None)`: 缓冲区数据不足以构成完整包（或不足以解析头部）。
    /// - `Err(FrameError)`: 头部数据表明帧非法（长度过小或过大）。
    pub fn check_frame(&self, buffer: &[u8]) -> Result<Option<usize>, FrameError> {
        let header_len = self.length_type as usize;

        // 1. 检查是否有足够的字节读取头部
        if buffer.len() < header_len {
            return Ok(None);
        }

        // 2. 解析长度字段
        let length_bytes = &buffer[..header_len];
        let length_val: usize = match self.length_type {
            1 => length_bytes[0] as usize,
            2 => {
                let b: [u8; 2] = length_bytes.try_into().unwrap();
                if self.little_endian {
                    u16::from_le_bytes(b) as usize
                } else {
                    u16::from_be_bytes(b) as usize
                }
            }
            4 => {
                let b: [u8; 4] = length_bytes.try_into().unwrap();
                if self.little_endian {
                    u32::from_le_bytes(b) as usize
                } else {
                    u32::from_be_bytes(b) as usize
                }
            }
            _ => unreachable!(), // 构造函数已断言
        };

        // 3. 计算实际包大小
        let packet_size = if self.inclusive_length {
            length_val
        } else {
            length_val + header_len
        };

        // 4. 逻辑校验: Inclusive 模式下，长度不能小于头部本身 (防止下溢)
        if self.inclusive_length && packet_size < header_len {
            return Err(FrameError::InvalidLength(packet_size, header_len));
        }

        // 5. 安全校验: 防止超大包 (OOM 攻击/恶意数据)
        if packet_size > self.max_frame_size {
            return Err(FrameError::FrameTooLarge(packet_size, self.max_frame_size));
        }

        // 6. 检查缓冲区是否完整
        if buffer.len() < packet_size {
            Ok(None)
        } else {
            Ok(Some(packet_size))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_frame_check_u4_be_inclusive() {
        let framer = JceFramer::new(4, true, false, 1024);
        // Length 10 (0x0000000A), inclusive -> packet is 10 bytes
        let mut data = vec![0x00, 0x00, 0x00, 0x0A];
        data.extend(vec![0xFF; 6]); // 4 bytes header + 6 bytes body = 10 bytes

        assert_eq!(framer.check_frame(&data), Ok(Some(10)));

        // Incomplete body
        assert_eq!(framer.check_frame(&data[..9]), Ok(None));

        // Incomplete header
        assert_eq!(framer.check_frame(&data[..2]), Ok(None));
    }

    #[test]
    fn test_frame_check_u4_le_exclusive() {
        let framer = JceFramer::new(4, false, true, 1024);
        // Length 6 (0x06000000), exclusive -> body is 6 bytes -> total 10 bytes
        let mut data = vec![0x06, 0x00, 0x00, 0x00];
        data.extend(vec![0xFF; 6]);

        assert_eq!(framer.check_frame(&data), Ok(Some(10)));
    }

    #[test]
    fn test_invalid_length_inclusive() {
        let framer = JceFramer::new(4, true, false, 1024);
        // Length 2 (0x00000002). Header is 4. Inclusive mode requires len >= 4.
        let data = vec![0x00, 0x00, 0x00, 0x02, 0xFF, 0xFF];

        match framer.check_frame(&data) {
            Err(FrameError::InvalidLength(2, 4)) => (),
            res => panic!("Expected InvalidLength error, got {:?}", res),
        }
    }

    #[test]
    fn test_frame_too_large() {
        let framer = JceFramer::new(4, true, false, 100);
        // Length 101
        let data = vec![0x00, 0x00, 0x00, 0x65]; // 101

        match framer.check_frame(&data) {
            Err(FrameError::FrameTooLarge(101, 100)) => (),
            res => panic!("Expected FrameTooLarge error, got {:?}", res),
        }
    }
}
