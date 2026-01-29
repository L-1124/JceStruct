use crate::bindings::deserializer::{BytesMode, decode_generic_struct, decode_struct_dict};
use crate::bindings::error::ErrorContext;
use crate::bindings::serializer::{encode_generic_field, encode_generic_struct, encode_struct};
use crate::codec::endian::Endianness;
use crate::codec::framing::JceFramer;
use crate::codec::reader::JceReader;
use crate::codec::writer::JceWriter;
use byteorder::{BigEndian, LittleEndian};
use bytes::{BufMut, BytesMut};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList};

/// 从流缓冲区读取带长度前缀的 JCE 数据包.
///
/// 处理 TCP 粘包和数据包分片问题.
#[pyclass(subclass)]
pub struct LengthPrefixedReader {
    buffer: BytesMut,
    framer: JceFramer,
    options: i32,
    bytes_mode: BytesMode,
    target_schema: Option<Py<PyList>>,
    target_cls: Option<Py<PyAny>>,
    context: Option<Py<PyAny>>,
    max_buffer_size: usize,
}

#[pymethods]
impl LengthPrefixedReader {
    #[new]
    #[pyo3(signature = (target, option=0, max_buffer_size=10485760, context=None, length_type=4, inclusive_length=true, little_endian_length=false, bytes_mode=2))]
    #[allow(clippy::too_many_arguments)]
    /// 创建一个新的 LengthPrefixedReader.
    ///
    /// Args:
    ///     target (type | StructDict): 目标类型 (Struct 类或 StructDict).
    ///     option (int): JCE 选项.
    ///     max_buffer_size (int): 最大缓冲区大小 (默认 10MB).
    ///     context (dict | None): 反序列化上下文.
    ///     length_type (int): 长度头字节数 (1, 2, 4).
    ///     inclusive_length (bool): 长度是否包含头部本身.
    ///     little_endian_length (bool): 长度头是否为小端序.
    ///     bytes_mode (int): 字节处理模式 (0=Raw, 1=String, 2=Auto).
    fn new(
        _py: Python<'_>,
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

        let mut target_schema = None;
        let target_cls = Some(target.clone().unbind());

        if let Ok(schema_method) = target.getattr("__get_core_schema__")
            && let Ok(schema) = schema_method.call0()
            && let Ok(schema) = schema.cast::<PyList>()
        {
            target_schema = Some(schema.clone().unbind());
        }

        Ok(LengthPrefixedReader {
            buffer: BytesMut::with_capacity(4096),
            framer: JceFramer::new(
                length_type,
                inclusive_length,
                little_endian_length,
                max_buffer_size,
            ),
            options: option,
            bytes_mode: BytesMode::from(bytes_mode),
            target_schema,
            target_cls,
            context,
            max_buffer_size,
        })
    }

    /// 向缓冲区追加数据.
    ///
    /// Args:
    ///     data (bytes): 要追加的二进制数据.
    ///
    /// Raises:
    ///     BufferError: 如果缓冲区超过最大大小.
    fn feed(&mut self, data: &Bound<'_, PyBytes>) -> PyResult<()> {
        let data = data.as_bytes();
        if self.buffer.len() + data.len() > self.max_buffer_size {
            return Err(pyo3::exceptions::PyBufferError::new_err(
                "Reader buffer exceeded max size",
            ));
        }
        self.buffer.extend_from_slice(data);
        Ok(())
    }

    fn __iter__(slf: PyRef<'_, Self>) -> PyRef<'_, Self> {
        slf
    }

    /// 获取下一个完整的数据包.
    ///
    /// Returns:
    ///     Any | None: 解析后的对象, 或者 None (如果数据不足).
    ///
    /// Raises:
    ///     ValueError: 如果数据包格式错误.
    fn __next__(mut slf: PyRefMut<'_, Self>) -> PyResult<Option<Py<PyAny>>> {
        let framer = slf.framer;
        match framer.check_frame(&slf.buffer) {
            Ok(Some(packet_size)) => {
                let header_len = framer.length_type as usize;
                let packet = slf.buffer.split_to(packet_size);
                let body_data = &packet[header_len..];
                let py = slf.py();

                if slf.options & 1 == 0 {
                    let mut reader = JceReader::<BigEndian>::new(body_data);
                    Self::decode_packet(py, &mut slf, &mut reader)
                } else {
                    let mut reader = JceReader::<LittleEndian>::new(body_data);
                    Self::decode_packet(py, &mut slf, &mut reader)
                }
            }
            Ok(None) => Ok(None),
            Err(e) => Err(pyo3::exceptions::PyValueError::new_err(format!(
                "JCE frame error: {e}"
            ))),
        }
    }

    /// 清空缓冲区.
    fn clear(&mut self) {
        self.buffer.clear();
    }
}

impl LengthPrefixedReader {
    /// 解码单个数据包.
    ///
    /// 内部使用，处理粘包后的完整数据体.
    /// 如果提供了 target_schema，则按 Struct 解码；否则按 Generic 解码.
    fn decode_packet<E: Endianness>(
        py: Python<'_>,
        slf: &mut LengthPrefixedReader,
        reader: &mut JceReader<E>,
    ) -> PyResult<Option<Py<PyAny>>> {
        let mut context = ErrorContext::new();
        if let Some(schema) = &slf.target_schema {
            let dict =
                decode_struct_dict(py, reader, schema.bind(py), slf.options, 0, &mut context)?;
            let kwargs = PyDict::new(py);
            if let Some(ctx) = &slf.context {
                kwargs.set_item("context", ctx.bind(py))?;
            }
            if let Some(target_cls) = &slf.target_cls {
                let instance =
                    target_cls
                        .bind(py)
                        .call_method("model_validate", (dict,), Some(&kwargs))?;
                return Ok(Some(instance.unbind()));
            }
            return Ok(Some(dict));
        }

        let result =
            decode_generic_struct(py, reader, slf.options, slf.bytes_mode, 0, &mut context);
        match result {
            Ok(obj) => {
                if let Some(target_cls) = &slf.target_cls {
                    let instance = target_cls.bind(py).call1((obj,))?;
                    return Ok(Some(instance.unbind()));
                }
                Ok(Some(obj))
            }
            Err(e) => Err(e),
        }
    }
}

#[pyclass(subclass)]
pub struct LengthPrefixedWriter {
    buffer: BytesMut,
    length_type: u8,
    inclusive_length: bool,
    little_endian: bool,
    options: i32,
}

#[pymethods]
impl LengthPrefixedWriter {
    #[new]
    #[pyo3(signature = (length_type=4, inclusive_length=true, little_endian_length=false, options=0))]
    /// 创建一个新的 LengthPrefixedWriter.
    ///
    /// Args:
    ///     length_type (int): 长度头字节数 (1, 2, 4).
    ///     inclusive_length (bool): 长度是否包含头部本身.
    ///     little_endian_length (bool): 长度头是否为小端序.
    ///     options (int): JCE 选项.
    fn new(
        length_type: u8,
        inclusive_length: bool,
        little_endian_length: bool,
        options: i32,
    ) -> PyResult<Self> {
        if ![1, 2, 4].contains(&length_type) {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "length_type must be 1, 2, or 4",
            ));
        }
        Ok(LengthPrefixedWriter {
            buffer: BytesMut::with_capacity(4096),
            length_type,
            inclusive_length,
            little_endian: little_endian_length,
            options,
        })
    }

    /// 打包一个对象 (兼容 API).
    ///
    /// Args:
    ///     py (Python): Python 解释器.
    ///     obj (Any): 要序列化的对象.
    fn pack(&mut self, py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<()> {
        self.write(py, obj)
    }

    fn write(&mut self, py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<()> {
        let options = self.options;

        let payload = if options & 1 == 0 {
            let mut writer = JceWriter::<Vec<u8>, BigEndian>::new();
            Self::encode_obj(py, &mut writer, obj, options)?;
            writer.get_buffer().to_vec()
        } else {
            let mut writer =
                JceWriter::<Vec<u8>, LittleEndian>::with_buffer(Vec::with_capacity(128));
            Self::encode_obj(py, &mut writer, obj, options)?;
            writer.get_buffer().to_vec()
        };

        self.append_packet(&payload)
    }

    /// 将原始字节作为数据包写入.
    ///
    /// Args:
    ///     data (bytes): 原始数据 payload.
    fn write_bytes(&mut self, data: &Bound<'_, PyBytes>) -> PyResult<()> {
        self.append_packet(data.as_bytes())
    }

    /// 获取当前缓冲区内容.
    ///
    /// Returns:
    ///     bytes: 缓冲区数据的副本.
    fn get_buffer(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        Ok(PyBytes::new(py, &self.buffer).into())
    }

    /// 清空缓冲区.
    fn clear(&mut self) {
        self.buffer.clear();
    }
}

impl LengthPrefixedWriter {
    /// 编码单个对象到 writer.
    ///
    /// 自动推断对象类型 (Struct vs Dict vs Generic) 并调用相应的编码函数.
    fn encode_obj<B: BufMut, E: Endianness>(
        py: Python<'_>,
        writer: &mut JceWriter<B, E>,
        obj: &Bound<'_, PyAny>,
        options: i32,
    ) -> PyResult<()> {
        let mut error_context = ErrorContext::new();
        let result = if let Ok(schema_method) = obj.getattr("__get_core_schema__") {
            let schema = schema_method.call0()?.cast_into::<PyList>()?;
            encode_struct(py, writer, obj, &schema, options, &mut error_context, 0)
        } else if let Ok(type_name) = obj.get_type().name() {
            if type_name == "StructDict" {
                let dict = obj.cast::<PyDict>()?;
                encode_generic_struct(py, writer, dict, options, &mut error_context, 0)
            } else {
                encode_generic_field(py, writer, 0, obj, options, &mut error_context, 0)
            }
        } else {
            encode_generic_field(py, writer, 0, obj, options, &mut error_context, 0)
        };
        result.map_err(|e| PyValueError::new_err(format!("{} at {}", e, error_context)))
    }

    /// 为 Payload 添加长度前缀并写入缓冲区.
    ///
    /// 处理长度计算 (Inclusive/Exclusive) 和字节序 (Big/Little).
    fn append_packet(&mut self, payload: &[u8]) -> PyResult<()> {
        let header_len = self.length_type as usize;
        let total_len = if self.inclusive_length {
            payload.len() + header_len
        } else {
            payload.len()
        };

        match self.length_type {
            1 => {
                if total_len > 255 {
                    return Err(pyo3::exceptions::PyValueError::new_err(
                        "Packet too large for 1-byte length",
                    ));
                }
                self.buffer.put_u8(total_len as u8);
            }
            2 => {
                if total_len > 65535 {
                    return Err(pyo3::exceptions::PyValueError::new_err(
                        "Packet too large for 2-byte length",
                    ));
                }
                if self.little_endian {
                    self.buffer.put_u16_le(total_len as u16);
                } else {
                    self.buffer.put_u16(total_len as u16);
                }
            }
            4 => {
                if total_len > 4294967295 {
                    return Err(pyo3::exceptions::PyValueError::new_err(
                        "Packet too large for 4-byte length",
                    ));
                }
                if self.little_endian {
                    self.buffer.put_u32_le(total_len as u32);
                } else {
                    self.buffer.put_u32(total_len as u32);
                }
            }
            _ => {
                return Err(pyo3::exceptions::PyValueError::new_err(
                    "Invalid length type",
                ));
            }
        }
        self.buffer.put_slice(payload);
        Ok(())
    }
}
