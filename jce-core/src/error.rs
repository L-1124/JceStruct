use thiserror::Error;

/// JCE 解码错误.
#[derive(Error, Debug, PartialEq)]
pub enum JceDecodeError {
    #[error("Error at {path}: {msg}")]
    DecodeError { path: String, msg: String },

    #[error("Unexpected end of buffer at {path}")]
    BufferOverflow { path: String },

    #[error("Invalid type {type_id} at {path}")]
    InvalidType { path: String, type_id: u8 },
}

impl JceDecodeError {
    /// 创建一个新的解码错误.
    pub fn new(path: impl Into<String>, msg: impl Into<String>) -> Self {
        JceDecodeError::DecodeError {
            path: path.into(),
            msg: msg.into(),
        }
    }
}
