pub mod consts;
pub mod error;
pub mod reader;
pub mod serde;
pub mod writer;

use pyo3::prelude::*;

#[pymodule]
fn _jce_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(serde::dumps, m)?)?;
    m.add_function(wrap_pyfunction!(serde::loads, m)?)?;
    m.add_function(wrap_pyfunction!(serde::dumps_generic, m)?)?;
    m.add_function(wrap_pyfunction!(serde::loads_generic, m)?)?;
    m.add_function(wrap_pyfunction!(decode_safe_text, m)?)?;
    Ok(())
}

#[pyfunction]
fn decode_safe_text(data: &[u8]) -> Option<String> {
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
