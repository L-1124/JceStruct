pub mod bindings;
pub mod codec;

use pyo3::prelude::*;

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(bindings::serde::dumps, m)?)?;
    m.add_function(wrap_pyfunction!(bindings::serde::loads, m)?)?;
    m.add_function(wrap_pyfunction!(bindings::serde::dumps_generic, m)?)?;
    m.add_function(wrap_pyfunction!(bindings::serde::loads_generic, m)?)?;
    m.add_class::<bindings::stream::LengthPrefixedReader>()?;
    m.add_class::<bindings::stream::LengthPrefixedWriter>()?;
    Ok(())
}
