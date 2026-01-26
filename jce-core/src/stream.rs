use crate::serde::{decode_generic_struct, decode_struct, BytesMode};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyList};

#[pyclass(subclass)]
pub struct LengthPrefixedReader {
    buffer: Vec<u8>,
    length_type: u8,
    inclusive_length: bool,
    little_endian: bool,
    options: i32,
    bytes_mode: BytesMode,
    target_schema: Option<Py<PyList>>,
    context: Option<Py<PyAny>>,
    max_buffer_size: usize,
}

#[pymethods]
impl LengthPrefixedReader {
    #[new]
    #[pyo3(signature = (target, option=0, max_buffer_size=10485760, context=None, length_type=4, inclusive_length=true, little_endian_length=false, bytes_mode=2))]
    fn new(
        py: Python<'_>,
        target: &Bound<'_, PyAny>,
        option: i32,
        max_buffer_size: usize,
        context: Option<Py<PyAny>>,
        length_type: u8,
        inclusive_length: bool,
        little_endian_length: bool,
        bytes_mode: u8,
    ) -> PyResult<Self> {
        if ![1, 2, 4].contains(&length_type) {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "length_type must be 1, 2, or 4",
            ));
        }

        // Try to get schema if target is JceStruct
        let mut target_schema = None;
        if let Ok(schema_method) = target.getattr("__get_jce_core_schema__") {
            if let Ok(schema) = schema_method.call0() {
                if let Ok(schema_list) = schema.downcast::<PyList>() {
                    target_schema = Some(schema_list.clone().unbind());
                }
            }
        }

        Ok(LengthPrefixedReader {
            buffer: Vec::with_capacity(4096),
            length_type,
            inclusive_length,
            little_endian: little_endian_length,
            options: option,
            bytes_mode: BytesMode::from(bytes_mode),
            target_schema,
            context,
            max_buffer_size,
        })
    }

    fn feed(&mut self, data: &[u8]) -> PyResult<()> {
        if self.buffer.len() + data.len() > self.max_buffer_size {
            return Err(pyo3::exceptions::PyBufferError::new_err(
                "JceStreamReader buffer exceeded max size",
            ));
        }
        self.buffer.extend_from_slice(data);
        Ok(())
    }

    fn __iter__(slf: PyRef<'_, Self>) -> PyRef<'_, Self> {
        slf
    }

    fn __next__(mut slf: PyRefMut<'_, Self>) -> PyResult<Option<PyObject>> {
        let length_type = slf.length_type as usize;
        let inclusive = slf.inclusive_length;
        let little_endian = slf.little_endian;

        if slf.buffer.len() < length_type {
            return Ok(None);
        }

        let length_bytes = &slf.buffer[..length_type];
        let length: usize = match length_type {
            1 => length_bytes[0] as usize,
            2 => {
                let b: [u8; 2] = length_bytes.try_into().unwrap();
                if little_endian {
                    u16::from_le_bytes(b) as usize
                } else {
                    u16::from_be_bytes(b) as usize
                }
            }
            4 => {
                let b: [u8; 4] = length_bytes.try_into().unwrap();
                if little_endian {
                    u32::from_le_bytes(b) as usize
                } else {
                    u32::from_be_bytes(b) as usize
                }
            }
            _ => unreachable!(),
        };

        let packet_size = if inclusive {
            length
        } else {
            length + length_type
        };

        if slf.buffer.len() < packet_size {
            return Ok(None);
        }

        // Extract body
        let body_start = length_type;
        let body_end = packet_size;
        let body_data = &slf.buffer[body_start..body_end];

        // Clone context for the call
        let py = slf.py();
        let context_bound = match &slf.context {
            Some(ctx) => ctx.bind(py).clone(),
            None => pyo3::types::PyDict::new(py).into_any(),
        };

        // Decode
        let reader = &mut crate::reader::JceReader::new(body_data, slf.options);
        let result = if let Some(schema) = &slf.target_schema {
            decode_struct(py, reader, schema.bind(py), slf.options, &context_bound, 0)
        } else {
            decode_generic_struct(py, reader, slf.options, slf.bytes_mode, &context_bound, 0)
        };

        // Remove consumed bytes regardless of success/failure (or should we?)
        // If decoding fails, we probably want to consume the bad packet anyway to avoid infinite loop
        // But PyResult will return early on Err.
        // Let's drain FIRST? No, we need body_data reference.
        // We must perform drain AFTER decode but BEFORE returning.

        match result {
            Ok(obj) => {
                slf.buffer.drain(..packet_size);
                Ok(Some(obj.into()))
            }
            Err(e) => {
                // If decoding fails, what should we do?
                // Python implementation raises JceDecodeError.
                // We should probably raise too, but the buffer state is tricky.
                // Standard behavior: if it's a valid framed packet but invalid content,
                // we should probably consume it so next call tries next packet?
                // Or let the user decide?
                // Let's follow Python: it raises, state is undefined/unchanged?
                // Python's `del self._buffer[:packet_size]` happens AFTER decode in the generator.
                // If decode raises, the buffer is NOT consumed.
                Err(e)
            }
        }
    }
}
