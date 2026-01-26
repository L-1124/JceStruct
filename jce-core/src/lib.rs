pub mod consts;
pub mod error;
pub mod reader;
pub mod serde;
pub mod stream;
pub mod writer;

use pyo3::prelude::*;
use pyo3::types::PyBytes;
use pyo3_stub_gen::define_stub_info_gatherer;
use pyo3_stub_gen::derive::*;

#[pymodule]
fn _jce_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(serde::dumps, m)?)?;
    m.add_function(wrap_pyfunction!(serde::loads, m)?)?;
    m.add_function(wrap_pyfunction!(serde::dumps_generic, m)?)?;
    m.add_function(wrap_pyfunction!(serde::loads_generic, m)?)?;
    m.add_function(wrap_pyfunction!(decode_safe_text, m)?)?;
    m.add_class::<stream::LengthPrefixedReader>()?;
    m.add_class::<stream::LengthPrefixedWriter>()?;
    Ok(())
}

define_stub_info_gatherer!(stub_info);

/// 将字节数据解码为字符串，安全处理编码问题。
///
/// 尝试使用 UTF-8 解码。如果包含非法的 ASCII 控制字符（\t, \n, \r 除外）
/// 或无效的 UTF-8 序列，则返回 None。
///
/// Args:
///     data: 要解码的字节数据。
///
/// Returns:
///     Optional[str]: 解码后的字符串，如果无效则返回 None。
#[gen_stub_pyfunction]
#[pyfunction]
fn decode_safe_text(data: &Bound<'_, PyBytes>) -> Option<String> {
    let data = data.as_bytes();
    // 1. Check for illegal ASCII control characters first (fastest rejection)
    for &b in data {
        if b < 32 {
            // Allow \t (9), \n (10), \r (13)
            if b != 9 && b != 10 && b != 13 {
                return None;
            }
        } else if b == 127 {
            return None;
        }
    }

    // 2. Try UTF-8 decoding
    match std::str::from_utf8(data) {
        Ok(s) => Some(s.to_string()),
        Err(_) => None,
    }
}
