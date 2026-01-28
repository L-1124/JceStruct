use thiserror::Error;

#[derive(Error, Debug, PartialEq)]
pub enum Error {
    #[error("Error at offset {offset}: {msg}")]
    Custom { offset: usize, msg: String },

    #[error("Unexpected end of buffer at offset {offset}")]
    BufferOverflow { offset: usize },

    #[error("Invalid type {type_id} at offset {offset}")]
    InvalidType { offset: usize, type_id: u8 },
}

impl Error {
    pub fn new(offset: usize, msg: impl Into<String>) -> Self {
        Self::Custom {
            offset,
            msg: msg.into(),
        }
    }
}

pub type Result<T> = std::result::Result<T, Error>;
