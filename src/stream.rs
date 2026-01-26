use crate::serde::{
    decode_generic_struct, decode_struct, encode_generic_field, encode_generic_struct,
    encode_struct, BytesMode,
};
use crate::writer::JceWriter;
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList};

/// 从流缓冲区读取带长度前缀的 JCE 数据包.
///
/// 处理 TCP 粘包和数据包分片问题.
#[pyclass(subclass)]
pub struct LengthPrefixedReader {
    buffer: Vec<u8>,
    length_type: u8,
    inclusive_length: bool,
    little_endian: bool,
    options: i32,
    bytes_mode: BytesMode,
    target_schema: Option<Py<PyList>>,
    max_buffer_size: usize,
}

#[pymethods]
impl LengthPrefixedReader {
    /// 初始化读取器.
    ///
    /// Args:
    ///     target: 用于解码的目标类（JceStruct 子类）或通用结构.
    ///     option: 解码选项.
    ///     max_buffer_size: 允许的最大缓冲区大小（字节），防止 DoS 攻击.
    ///     length_type: 长度前缀的字节大小（1、2 或 4）.
    ///     inclusive_length: 长度值是否包含长度前缀本身.
    ///     little_endian_length: 长度前缀是否为小端序.
    ///     bytes_mode: 通用解码的字节处理模式（0: Raw, 1: String, 2: Auto）.
    #[new]
    #[pyo3(signature = (target, option=0, max_buffer_size=10485760, length_type=4, inclusive_length=true, little_endian_length=false, bytes_mode=2))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        _py: Python<'_>,
        target: &Bound<'_, PyAny>,
        option: i32,
        max_buffer_size: usize,
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
        #[allow(clippy::collapsible_if)]
        if let Ok(schema_method) = target.getattr("__get_jce_core_schema__") {
            if let Ok(schema) = schema_method.call0() {
                if let Ok(schema_list) = schema.cast::<PyList>() {
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
            max_buffer_size,
        })
    }

    /// 将数据追加到内部缓冲区.
    ///
    /// Args:
    ///     data: 要追加的字节数据.
    ///
    /// Raises:
    ///     BufferError: 如果缓冲区超过 max_buffer_size.
    fn feed(&mut self, data: &Bound<'_, PyBytes>) -> PyResult<()> {
        let data = data.as_bytes();
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

    /// 迭代缓冲区中的完整数据包.
    ///
    /// Yields:
    ///     从缓冲区解码的对象（JceStruct 或 dict）.
    fn __next__(mut slf: PyRefMut<'_, Self>) -> PyResult<Option<Py<PyAny>>> {
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

        // Decode
        let reader = &mut crate::reader::JceReader::new(body_data, slf.options);
        let result = if let Some(schema) = &slf.target_schema {
            decode_struct(py, reader, schema.bind(py), slf.options, 0)
        } else {
            decode_generic_struct(py, reader, slf.options, slf.bytes_mode, 0)
        };

        match result {
            Ok(obj) => {
                slf.buffer.drain(..packet_size);
                Ok(Some(obj))
            }
            Err(e) => Err(e),
        }
    }
}

/// 写入带长度前缀的 JCE 数据包.
///
/// 辅助类，用于将数据打包成带长度头的流传输格式.
#[pyclass(subclass)]
pub struct LengthPrefixedWriter {
    buffer: Vec<u8>,
    length_type: u8,
    inclusive_length: bool,
    little_endian: bool,
    options: i32,
    context: Option<Py<PyAny>>,
}

#[pymethods]
impl LengthPrefixedWriter {
    /// 初始化写入器.
    ///
    /// Args:
    ///     length_type: 长度前缀的字节大小（1、2 或 4）.
    ///     inclusive_length: 长度值是否包含长度前缀本身.
    ///     little_endian_length: 长度前缀是否为小端序.
    ///     options: 序列化选项.
    ///     context: 用于序列化的可选上下文.
    #[new]
    #[pyo3(signature = (length_type=4, inclusive_length=true, little_endian_length=false, options=0, context=None))]
    fn new(
        length_type: u8,
        inclusive_length: bool,
        little_endian_length: bool,
        options: i32,
        context: Option<Py<PyAny>>,
    ) -> PyResult<Self> {
        if ![1, 2, 4].contains(&length_type) {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "length_type must be 1, 2, or 4",
            ));
        }
        Ok(LengthPrefixedWriter {
            buffer: Vec::with_capacity(4096),
            length_type,
            inclusive_length,
            little_endian: little_endian_length,
            options,
            context,
        })
    }

    /// 将对象打包成带长度前缀的数据包.
    ///
    /// 使用 JCE 编码对象并将数据包追加到缓冲区.
    ///
    /// Args:
    ///     obj: 要打包的对象（JceStruct 或 dict）.
    #[pyo3(signature = (obj))]
    fn pack(&mut self, py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<()> {
        self.write(py, obj)
    }

    #[pyo3(signature = (obj))]
    fn write(&mut self, py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<()> {
        let mut writer = JceWriter::new();
        if self.options & 1 != 0 {
            writer.set_little_endian(true);
        }

        let context_bound = match &self.context {
            Some(ctx) => ctx.bind(py).clone(),
            None => PyDict::new(py).into_any(),
        };

        // Determine how to encode
        // 1. Try JceStruct (has __get_jce_core_schema__)
        if let Ok(schema_method) = obj.getattr("__get_jce_core_schema__") {
            let schema = schema_method.call0()?.cast_into::<PyList>()?;
            encode_struct(
                py,
                &mut writer,
                obj,
                &schema,
                self.options,
                &context_bound,
                0,
            )?;
        }
        // 2. Try JceDict (generic struct)
        else if let Ok(type_name) = obj.get_type().name() {
            if type_name == "JceDict" {
                if let Ok(dict) = obj.cast::<PyDict>() {
                    encode_generic_struct(py, &mut writer, dict, self.options, &context_bound, 0)?;
                } else {
                    return Err(pyo3::exceptions::PyTypeError::new_err(
                        "JceDict must be a dict-like object",
                    ));
                }
            } else {
                encode_generic_field(py, &mut writer, 0, obj, self.options, &context_bound, 0)?;
            }
        } else {
            encode_generic_field(py, &mut writer, 0, obj, self.options, &context_bound, 0)?;
        }

        let payload = writer.get_buffer();
        self.append_packet(payload)
    }

    /// 将原始字节作为带长度前缀的数据包写入.
    ///
    /// Args:
    ///     data: 原始字节负载.
    #[pyo3(signature = (data))]
    fn pack_bytes(&mut self, data: &Bound<'_, PyBytes>) -> PyResult<()> {
        self.write_bytes(data)
    }

    /// pack_bytes 的别名.
    #[pyo3(signature = (data))]
    fn write_bytes(&mut self, data: &Bound<'_, PyBytes>) -> PyResult<()> {
        self.append_packet(data.as_bytes())
    }

    /// 获取当前缓冲区内容.
    ///
    /// Returns:
    ///     bytes: 累积的缓冲区内容.
    fn get_buffer(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        Ok(PyBytes::new(py, &self.buffer).into())
    }

    /// 清空内部缓冲区.
    fn clear(&mut self) {
        self.buffer.clear();
    }
}

impl LengthPrefixedWriter {
    fn append_packet(&mut self, payload: &[u8]) -> PyResult<()> {
        let payload_len = payload.len();
        let header_len = self.length_type as usize;
        let total_len = if self.inclusive_length {
            payload_len + header_len
        } else {
            payload_len
        };

        // Write length
        match self.length_type {
            1 => {
                if total_len > 255 {
                    return Err(pyo3::exceptions::PyValueError::new_err(
                        "Packet too large for 1-byte length",
                    ));
                }
                self.buffer.push(total_len as u8);
            }
            2 => {
                if total_len > 65535 {
                    return Err(pyo3::exceptions::PyValueError::new_err(
                        "Packet too large for 2-byte length",
                    ));
                }
                let bytes = (total_len as u16).to_be_bytes(); // Default BE
                if self.little_endian {
                    self.buffer
                        .extend_from_slice(&(total_len as u16).to_le_bytes());
                } else {
                    self.buffer.extend_from_slice(&bytes);
                }
            }
            4 => {
                if total_len > 4294967295 {
                    return Err(pyo3::exceptions::PyValueError::new_err(
                        "Packet too large for 4-byte length",
                    ));
                }
                let bytes = (total_len as u32).to_be_bytes();
                if self.little_endian {
                    self.buffer
                        .extend_from_slice(&(total_len as u32).to_le_bytes());
                } else {
                    self.buffer.extend_from_slice(&bytes);
                }
            }
            _ => {
                return Err(pyo3::exceptions::PyValueError::new_err(
                    "Invalid length type",
                ));
            }
        }

        self.buffer.extend_from_slice(payload);
        Ok(())
    }
}
