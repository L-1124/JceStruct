pub mod bindings;
pub mod codec;

use crate::bindings::{deserializer, serializer};
use pyo3::prelude::*;

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(serializer::dumps, m)?)?;
    m.add_function(wrap_pyfunction!(deserializer::loads, m)?)?;
    m.add_function(wrap_pyfunction!(serializer::dumps_generic, m)?)?;
    m.add_function(wrap_pyfunction!(deserializer::loads_generic, m)?)?;
    m.add_class::<bindings::stream::LengthPrefixedReader>()?;
    m.add_class::<bindings::stream::LengthPrefixedWriter>()?;
    Ok(())
}
