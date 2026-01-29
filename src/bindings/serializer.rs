use crate::bindings::error::ErrorContext;
use crate::bindings::schema::{CompiledSchema, compile_schema, resolve_jce_type};
use crate::codec::consts::{JCE_TYPE_GENERIC, JceType};
use crate::codec::writer::JceWriter;
use byteorder::{BigEndian, LittleEndian};
use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyCapsule, PyDict, PyList, PyTuple, PyType};
use std::cell::RefCell;

thread_local! {
    /// 线程局部写入器，用于复用缓冲区以提升性能。
    static TLS_WRITER: RefCell<JceWriter<Vec<u8>, BigEndian>> = RefCell::new(JceWriter::new());
}

/// 最大递归深度，防止栈溢出。
const MAX_DEPTH: usize = 100;
/// 选项：忽略默认值。
const OPT_OMIT_DEFAULT: i32 = 32;
/// 选项：仅序列化已设置的字段（Pydantic）。
const OPT_EXCLUDE_UNSET: i32 = 64;

/// 获取或编译 Schema。
fn get_or_compile_schema(
    py: Python<'_>,
    schema_or_type: &Bound<'_, PyAny>,
) -> PyResult<Option<Py<PyCapsule>>> {
    if let Ok(capsule) = schema_or_type.cast::<PyCapsule>() {
        return Ok(Some(capsule.clone().unbind()));
    }

    let cls_bound = if let Ok(origin) = schema_or_type.getattr("__origin__") {
        origin
    } else {
        schema_or_type.clone()
    };

    if let Ok(cls) = cls_bound.cast::<PyType>() {
        if let Ok(cached) = cls.getattr("__tars_compiled_schema__")
            && let Ok(capsule) = cached.cast::<PyCapsule>()
        {
            return Ok(Some(capsule.clone().unbind()));
        }
        let schema_list = cls.getattr("__tars_schema__")?;
        let list = schema_list.cast::<PyList>()?;
        let capsule = compile_schema(py, list)?;
        cls.setattr("__tars_compiled_schema__", &capsule)?;
        return Ok(Some(capsule));
    }
    Ok(None)
}

/// JCE 写入器抽象接口，支持不同字节序的静态分发。
pub(crate) trait JceWriterTrait {
    fn write_tag(&mut self, tag: u8, type_id: JceType);
    fn write_int(&mut self, tag: u8, value: i64);
    fn write_float(&mut self, tag: u8, value: f32);
    fn write_double(&mut self, tag: u8, value: f64);
    fn write_string(&mut self, tag: u8, value: &str);
    fn write_bytes(&mut self, tag: u8, value: &[u8]);
}

impl<B: bytes::BufMut, E: crate::codec::endian::Endianness> JceWriterTrait for JceWriter<B, E> {
    #[inline]
    fn write_tag(&mut self, tag: u8, type_id: JceType) {
        self.write_tag(tag, type_id);
    }
    #[inline]
    fn write_int(&mut self, tag: u8, value: i64) {
        self.write_int(tag, value);
    }
    #[inline]
    fn write_float(&mut self, tag: u8, value: f32) {
        self.write_float(tag, value);
    }
    #[inline]
    fn write_double(&mut self, tag: u8, value: f64) {
        self.write_double(tag, value);
    }
    #[inline]
    fn write_string(&mut self, tag: u8, value: &str) {
        self.write_string(tag, value);
    }
    #[inline]
    fn write_bytes(&mut self, tag: u8, value: &[u8]) {
        self.write_bytes(tag, value);
    }
}

/// 使用 TLS 写入器执行编码任务。
fn with_writer<F>(options: i32, f: F) -> PyResult<Vec<u8>>
where
    F: FnOnce(&mut dyn JceWriterTrait) -> PyResult<()>,
{
    if options & 1 == 0 {
        TLS_WRITER.with(|cell| {
            if let Ok(mut writer) = cell.try_borrow_mut() {
                writer.clear();
                f(&mut *writer)?;
                Ok(writer.get_buffer().to_vec())
            } else {
                let mut writer = JceWriter::<Vec<u8>, BigEndian>::new();
                f(&mut writer)?;
                Ok(writer.get_buffer().to_vec())
            }
        })
    } else {
        let mut writer = JceWriter::<Vec<u8>, LittleEndian>::with_buffer(Vec::with_capacity(128));
        f(&mut writer)?;
        Ok(writer.get_buffer().to_vec())
    }
}

/// 根据 Python 对象类型自动推断并执行编码。
fn encode_infer(
    py: Python<'_>,
    writer: &mut dyn JceWriterTrait,
    value: &Bound<'_, PyAny>,
    options: i32,
    error_context: &mut ErrorContext,
    depth: usize,
) -> PyResult<()> {
    if let Ok(dict) = value.cast::<PyDict>() {
        encode_generic_struct(py, writer, dict, options, error_context, depth)
    } else if let Ok(schema_list) = value.getattr("__tars_schema__") {
        encode_struct(
            py,
            writer,
            value,
            &schema_list,
            options,
            error_context,
            depth,
        )
    } else {
        encode_generic_field(py, writer, 0, value, options, error_context, depth)
    }
}

#[pyfunction]
#[pyo3(signature = (obj, schema=None, options=0))]
/// 序列化 Python 对象为 JCE 二进制格式 (基于 Schema)。
pub fn dumps(
    py: Python<'_>,
    obj: &Bound<'_, PyAny>,
    schema: Option<&Bound<'_, PyAny>>,
    options: i32,
) -> PyResult<Py<PyBytes>> {
    let mut error_context = ErrorContext::new();
    let result = with_writer(options, |writer| {
        if let Some(s) = schema {
            encode_struct(py, writer, obj, s, options, &mut error_context, 0)
        } else if let Ok(schema_list) = obj.getattr("__tars_schema__") {
            encode_struct(
                py,
                writer,
                obj,
                &schema_list,
                options,
                &mut error_context,
                0,
            )
        } else {
            encode_infer(py, writer, obj, options, &mut error_context, 0)
        }
    });
    let bytes = result.map_err(|e| PyValueError::new_err(format!("{} at {}", e, error_context)))?;
    Ok(PyBytes::new(py, &bytes).into())
}

#[pyfunction]
#[pyo3(signature = (data, options=0))]
/// 序列化 Python 对象为 JCE 二进制格式 (自动探测类型)。
pub fn dumps_generic(
    py: Python<'_>,
    data: &Bound<'_, PyAny>,
    options: i32,
) -> PyResult<Py<PyBytes>> {
    let mut error_context = ErrorContext::new();
    let result = with_writer(options, |writer| {
        encode_infer(py, writer, data, options, &mut error_context, 0)
    });
    let bytes = result.map_err(|e| PyValueError::new_err(format!("{} at {}", e, error_context)))?;
    Ok(PyBytes::new(py, &bytes).into())
}

/// 将 Python 对象编码为 JCE 结构体。
pub(crate) fn encode_struct(
    py: Python<'_>,
    writer: &mut dyn JceWriterTrait,
    obj: &Bound<'_, PyAny>,
    schema: &Bound<'_, PyAny>,
    options: i32,
    error_context: &mut ErrorContext,
    depth: usize,
) -> PyResult<()> {
    if depth > MAX_DEPTH {
        return Err(PyValueError::new_err("Depth exceeded"));
    }
    if let Some(capsule_py) = get_or_compile_schema(py, schema)? {
        let capsule = capsule_py.bind(py);
        let ptr = capsule
            .pointer_checked(None)
            .map_err(|_| PyValueError::new_err("Invalid capsule"))?;
        let compiled = unsafe { &*(ptr.as_ptr() as *mut CompiledSchema) };
        return encode_struct_compiled(py, writer, obj, compiled, options, error_context, depth);
    }
    let schema_list = schema.cast::<PyList>()?;
    for item in schema_list.iter() {
        let tuple = item.cast::<PyTuple>()?;
        let name: String = tuple.get_item(0)?.extract()?;
        error_context.push_field(&name);
        let (tag, jce_type_code, default_val) = if tuple.len() == 3 {
            let info = tuple.get_item(1)?;
            let tag: u8 = info.getattr("tag")?.extract()?;
            let default = info.getattr("default")?;
            let raw_type = tuple.get_item(2)?;
            let jce_type = resolve_jce_type(py, &raw_type)?;
            (tag, jce_type, default)
        } else {
            let tag: u8 = tuple.get_item(1)?.extract()?;
            let jce_type_code: u8 = tuple.get_item(2)?.extract()?;
            let default_val = tuple.get_item(3)?;
            (tag, jce_type_code, default_val)
        };

        let value = match obj.getattr(&name) {
            Ok(v) => v,
            Err(e) => {
                error_context.pop();
                return Err(e);
            }
        };
        if value.is_none() {
            error_context.pop();
            continue;
        }
        if (options & OPT_EXCLUDE_UNSET) != 0
            && let Ok(model_fields_set) = obj.getattr("model_fields_set")
            && !model_fields_set
                .call_method1("__contains__", (&name,))?
                .extract::<bool>()?
        {
            error_context.pop();
            continue;
        }
        if (options & OPT_OMIT_DEFAULT) != 0 && value.eq(&default_val)? {
            error_context.pop();
            continue;
        }
        if jce_type_code == JCE_TYPE_GENERIC {
            encode_generic_field(py, writer, tag, &value, options, error_context, depth + 1)?;
        } else {
            let jce_type = JceType::try_from(jce_type_code).unwrap();
            encode_field(
                py,
                writer,
                tag,
                jce_type,
                &value,
                options,
                error_context,
                depth + 1,
            )?;
        }
        error_context.pop();
    }
    Ok(())
}

/// 使用预编译 Schema 编码结构体。
///
/// 相比解释模式，这里避免了大量 Python 对象属性访问和元组解包开销。
fn encode_struct_compiled(
    py: Python<'_>,
    writer: &mut dyn JceWriterTrait,
    obj: &Bound<'_, PyAny>,
    schema: &CompiledSchema,
    options: i32,
    error_context: &mut ErrorContext,
    depth: usize,
) -> PyResult<()> {
    // 预先获取 model_fields_set 集合 (如果需要)
    let fields_set = if (options & OPT_EXCLUDE_UNSET) != 0 {
        obj.getattr("model_fields_set").ok()
    } else {
        None
    };
    for field in &schema.fields {
        error_context.push_field(&field.name);
        // 检查字段是否被设置
        if let Some(fs) = &fields_set
            && !fs.contains(field.py_name.bind(py))?
        {
            error_context.pop();
            continue;
        }
        let value = match obj.getattr(field.py_name.bind(py)) {
            Ok(v) => v,
            Err(e) => {
                error_context.pop();
                return Err(e);
            }
        };
        if value.is_none() {
            error_context.pop();
            continue;
        }
        // 检查默认值
        if (options & OPT_OMIT_DEFAULT) != 0 && value.eq(field.default_val.bind(py))? {
            error_context.pop();
            continue;
        }
        if field.jce_type == JCE_TYPE_GENERIC {
            encode_generic_field(
                py,
                writer,
                field.tag,
                &value,
                options,
                error_context,
                depth + 1,
            )?;
        } else {
            let jce_type = JceType::try_from(field.jce_type).unwrap_or(JceType::ZeroTag);
            encode_field(
                py,
                writer,
                field.tag,
                jce_type,
                &value,
                options,
                error_context,
                depth + 1,
            )?;
        }
        error_context.pop();
    }
    Ok(())
}

/// 编码单个字段。
#[allow(clippy::too_many_arguments)]
fn encode_field(
    py: Python<'_>,
    writer: &mut dyn JceWriterTrait,
    tag: u8,
    jce_type: JceType,
    value: &Bound<'_, PyAny>,
    options: i32,
    error_context: &mut ErrorContext,
    depth: usize,
) -> PyResult<()> {
    match jce_type {
        JceType::Int1 | JceType::Int2 | JceType::Int4 | JceType::Int8 => {
            writer.write_int(tag, value.extract()?)
        }
        JceType::Float => writer.write_float(tag, value.extract()?),
        JceType::Double => writer.write_double(tag, value.extract()?),
        JceType::String1 | JceType::String4 => {
            writer.write_string(tag, &value.extract::<String>()?)
        }
        JceType::Map => {
            let dict = value.cast::<PyDict>()?;
            writer.write_tag(tag, JceType::Map);
            writer.write_int(0, dict.len() as i64);
            for (k, v) in dict {
                error_context.push_key("?");
                encode_generic_field(py, writer, 0, &k, options, error_context, depth + 1)?;
                error_context.pop();

                let key_str = k.str()?.to_str()?.to_string();
                error_context.push_key(&key_str);
                encode_generic_field(py, writer, 1, &v, options, error_context, depth + 1)?;
                error_context.pop();
            }
        }
        JceType::List => {
            let list = value.cast::<PyList>()?;
            writer.write_tag(tag, JceType::List);
            writer.write_int(0, list.len() as i64);
            for (i, item) in list.iter().enumerate() {
                error_context.push_index(i);
                encode_generic_field(py, writer, 0, &item, options, error_context, depth + 1)?;
                error_context.pop();
            }
        }
        JceType::SimpleList => {
            if let Ok(bytes) = value.cast::<PyBytes>() {
                writer.write_bytes(tag, bytes.as_bytes());
            } else {
                let inner_bytes = with_writer(options, |w| {
                    encode_infer(py, w, value, options, error_context, depth + 1)
                })?;
                writer.write_bytes(tag, &inner_bytes);
            }
        }
        JceType::StructBegin => {
            writer.write_tag(tag, JceType::StructBegin);
            if let Ok(schema_list) = value.getattr("__tars_schema__") {
                encode_struct(
                    py,
                    writer,
                    value,
                    &schema_list,
                    options,
                    error_context,
                    depth + 1,
                )?;
            } else if let Ok(dict) = value.cast::<PyDict>() {
                encode_generic_struct(py, writer, dict, options, error_context, depth + 1)?;
            } else {
                return Err(PyTypeError::new_err("Cannot encode as struct"));
            }
            writer.write_tag(0, JceType::StructEnd);
        }
        _ => return Err(PyValueError::new_err("Unsupported type")),
    }
    Ok(())
}

/// 无模式编码 Python 字典为 JCE 结构体。
pub(crate) fn encode_generic_struct(
    py: Python<'_>,
    writer: &mut dyn JceWriterTrait,
    data: &Bound<'_, PyDict>,
    options: i32,
    error_context: &mut ErrorContext,
    depth: usize,
) -> PyResult<()> {
    if depth > MAX_DEPTH {
        return Err(PyValueError::new_err("Depth exceeded"));
    }
    let mut items: Vec<(u8, Bound<'_, PyAny>)> = Vec::with_capacity(data.len());
    for (k, v) in data {
        let tag = if let Ok(t) = k.extract::<u8>() {
            t
        } else {
            let tag_str: String = k.extract()?;
            if let Some((t_str, _)) = tag_str.split_once(':') {
                t_str.parse::<u8>().unwrap_or(JCE_TYPE_GENERIC)
            } else {
                tag_str.parse::<u8>().unwrap_or(JCE_TYPE_GENERIC)
            }
        };
        if tag != JCE_TYPE_GENERIC {
            items.push((tag, v));
        }
    }
    items.sort_by_key(|(t, _)| *t);
    for (tag, value) in items {
        error_context.push_tag(tag);
        encode_generic_field(py, writer, tag, &value, options, error_context, depth + 1)?;
        error_context.pop();
    }
    Ok(())
}

/// 无模式编码 Python 对象为 JCE 字段。
pub(crate) fn encode_generic_field(
    py: Python<'_>,
    writer: &mut dyn JceWriterTrait,
    tag: u8,
    value: &Bound<'_, PyAny>,
    options: i32,
    error_context: &mut ErrorContext,
    depth: usize,
) -> PyResult<()> {
    if let Ok(v) = value.extract::<i64>() {
        writer.write_int(tag, v);
    } else if let Ok(v) = value.extract::<f64>() {
        writer.write_double(tag, v);
    } else if let Ok(b) = value.cast::<PyBytes>() {
        writer.write_bytes(tag, b.as_bytes());
    } else if let Ok(s) = value.extract::<String>() {
        writer.write_string(tag, &s);
    } else if let Ok(l) = value.cast::<PyList>() {
        writer.write_tag(tag, JceType::List);
        writer.write_int(0, l.len() as i64);
        for (i, item) in l.iter().enumerate() {
            error_context.push_index(i);
            encode_generic_field(py, writer, 0, &item, options, error_context, depth + 1)?;
            error_context.pop();
        }
    } else if let Ok(d) = value.cast::<PyDict>() {
        if value.get_type().name()?.to_str()? == "StructDict" {
            writer.write_tag(tag, JceType::StructBegin);
            encode_generic_struct(py, writer, d, options, error_context, depth + 1)?;
            writer.write_tag(0, JceType::StructEnd);
        } else {
            writer.write_tag(tag, JceType::Map);
            writer.write_int(0, d.len() as i64);
            for (k, v) in d {
                error_context.push_key("?");
                encode_generic_field(py, writer, 0, &k, options, error_context, depth + 1)?;
                error_context.pop();

                let key_str = k.str()?.to_str()?.to_string();
                error_context.push_key(&key_str);
                encode_generic_field(py, writer, 1, &v, options, error_context, depth + 1)?;
                error_context.pop();
            }
        }
    } else if let Ok(schema_list) = value.getattr("__tars_schema__") {
        writer.write_tag(tag, JceType::StructBegin);
        encode_struct(
            py,
            writer,
            value,
            &schema_list,
            options,
            error_context,
            depth + 1,
        )?;
        writer.write_tag(0, JceType::StructEnd);
    } else {
        return Err(PyTypeError::new_err("Cannot infer type"));
    }
    Ok(())
}
