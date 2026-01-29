use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use crate::codec::error::Error;

/// 将 Rust 核心错误转换为 Python 异常。
///
/// 尝试抛出 `tarsio.exceptions.DecodeError`，如果失败则回退到 `ValueError`。
impl From<Error> for PyErr {
    fn from(err: Error) -> PyErr {
        let msg = match &err {
            Error::Custom { offset, msg } => format!("{} (at offset {})", msg, offset),
            Error::BufferOverflow { offset } => {
                format!("Buffer overflow (at offset {})", offset)
            }
            Error::InvalidType { offset, type_id } => {
                format!("Invalid type ID: {} (at offset {})", type_id, offset)
            }
        };

        Python::attach(|py| {
            let decode_error = py
                .import("tarsio.exceptions")
                .and_then(|m| m.getattr("DecodeError"))
                .and_then(|cls| cls.call1((msg.clone(),)));

            if let Ok(err_obj) = decode_error {
                return PyErr::from_value(err_obj);
            }
            PyValueError::new_err(msg)
        })
    }
}
