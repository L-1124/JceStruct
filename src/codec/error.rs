use thiserror::Error;

/// JCE 编解码错误枚举。
#[derive(Error, Debug, PartialEq)]
pub enum Error {
    #[error("Error at offset {offset}: {msg}")]
    /// 自定义错误信息。
    Custom { offset: usize, msg: String },

    #[error("Unexpected end of buffer at offset {offset}")]
    /// 缓冲区溢出 (读取越界)。
    BufferOverflow { offset: usize },

    #[error("Invalid type {type_id} at offset {offset}")]
    /// 无效的 JCE 类型 ID。
    InvalidType { offset: usize, type_id: u8 },
}

impl Error {
    /// 创建一个新的自定义错误。
    pub fn new(offset: usize, msg: impl Into<String>) -> Self {
        Self::Custom {
            offset,
            msg: msg.into(),
        }
    }
}

pub type Result<T> = std::result::Result<T, Error>;
