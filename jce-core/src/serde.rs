use crate::consts::JceType;
use crate::error::JceDecodeError;
use crate::reader::JceReader;
use crate::writer::JceWriter;
use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyFloat, PyInt, PyList, PyString, PyTuple};

/// 递归深度限制
const MAX_DEPTH: usize = 100;

/// OMIT_DEFAULT 选项标志
const OPT_OMIT_DEFAULT: i32 = 32;

/// EXCLUDE_UNSET 选项标志 (内部使用)
const OPT_EXCLUDE_UNSET: i32 = 64;

/// Bytes handling mode
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum BytesMode {
    Raw = 0,
    String = 1,
    Auto = 2,
}

impl From<u8> for BytesMode {
    fn from(v: u8) -> Self {
        match v {
            1 => BytesMode::String,
            2 => BytesMode::Auto,
            _ => BytesMode::Raw,
        }
    }
}

fn check_safe_text(data: &[u8]) -> bool {
    // 1. Check for illegal ASCII control characters first (fastest rejection)
    for &b in data {
        if b < 32 {
            // Allow \t (9), \n (10), \r (13)
            if b != 9 && b != 10 && b != 13 {
                return false;
            }
        } else if b == 127 {
            return false;
        }
    }
    // 2. Try UTF-8 decoding
    std::str::from_utf8(data).is_ok()
}

#[pyfunction]
#[pyo3(signature = (obj, schema, options=0, context=None))]
pub fn dumps(
    py: Python<'_>,
    obj: Py<PyAny>,
    schema: &Bound<'_, PyList>,
    options: i32,
    context: Option<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
    let mut writer = JceWriter::new();
    if options & 1 != 0 {
        writer.set_little_endian(true);
    }
    let context_bound = match context {
        Some(ctx) => ctx.into_bound(py),
        None => PyDict::new(py).into_any(),
    };

    encode_struct(
        py,
        &mut writer,
        obj.bind(py),
        schema,
        options,
        &context_bound,
        0,
    )?;

    Ok(PyBytes::new(py, writer.get_buffer()).into())
}

#[pyfunction]
#[pyo3(signature = (obj, options=0, context=None))]
pub fn dumps_generic(
    py: Python<'_>,
    obj: Py<PyAny>,
    options: i32,
    context: Option<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
    let mut writer = JceWriter::new();
    if options & 1 != 0 {
        writer.set_little_endian(true);
    }
    let context_bound = match context {
        Some(ctx) => ctx.into_bound(py),
        None => PyDict::new(py).into_any(),
    };
    let obj_bound = obj.bind(py);

    let type_name = obj_bound.get_type().name()?.to_string();
    if type_name == "JceDict" {
        if let Ok(dict) = obj_bound.cast::<PyDict>() {
            encode_generic_struct(py, &mut writer, dict, options, &context_bound, 0)?;
        } else {
            return Err(PyTypeError::new_err("JceDict must be a dict-like object"));
        }
    } else {
        // Always wrap in Tag 0 for generic dumps to match legacy behavior
        // and ensure consistent return structure (e.g. {0: value})
        encode_generic_field(py, &mut writer, 0, obj_bound, options, &context_bound, 0)?;
    }

    Ok(PyBytes::new(py, writer.get_buffer()).into())
}

#[pyfunction]
#[pyo3(signature = (data, schema, options=0, context=None))]
pub fn loads(
    py: Python<'_>,
    data: &[u8],
    schema: &Bound<'_, PyList>,
    options: i32,
    context: Option<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
    let mut reader = JceReader::new(data, options);
    let context_bound = match context {
        Some(ctx) => ctx.into_bound(py),
        None => PyDict::new(py).into_any(),
    };

    decode_struct(py, &mut reader, schema, options, &context_bound, 0)
}

#[pyfunction]
#[pyo3(signature = (data, options=0, bytes_mode=2, context=None))]
pub fn loads_generic(
    py: Python<'_>,
    data: &[u8],
    options: i32,
    bytes_mode: u8,
    context: Option<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
    let mut reader = JceReader::new(data, options);
    let context_bound = match context {
        Some(ctx) => ctx.into_bound(py),
        None => PyDict::new(py).into_any(),
    };

    let mode = BytesMode::from(bytes_mode);
    decode_generic_struct(py, &mut reader, options, mode, &context_bound, 0)
}

fn encode_struct(
    py: Python<'_>,
    writer: &mut JceWriter,
    obj: &Bound<'_, PyAny>,
    schema: &Bound<'_, PyList>,
    options: i32,
    context: &Bound<'_, PyAny>,
    depth: usize,
) -> PyResult<()> {
    if depth > MAX_DEPTH {
        return Err(PyValueError::new_err("Max recursion depth exceeded"));
    }

    for item in schema.iter() {
        let tuple = item
            .cast::<PyTuple>()
            .map_err(|_| PyTypeError::new_err("Schema item must be a tuple"))?;

        // schema: (name, tag, type, default, has_serializer, has_deserializer)
        let name: String = tuple.get_item(0)?.extract()?;
        let tag: u8 = tuple.get_item(1)?.extract()?;
        let jce_type_code: u8 = tuple.get_item(2)?.extract()?;
        let default_val = tuple.get_item(3)?;
        let has_serializer: bool = tuple.get_item(4)?.extract()?;

        let mut value = obj.getattr(&name)?;

        // Check if field is set (for exclude_unset)
        if (options & OPT_EXCLUDE_UNSET) != 0 {
            if let Ok(model_fields_set) = obj.getattr("model_fields_set") {
                let is_set: bool = model_fields_set
                    .call_method1("__contains__", (&name,))?
                    .extract()?;
                if !is_set {
                    continue;
                }
            }
        }

        // Check OMIT_DEFAULT
        if (options & OPT_OMIT_DEFAULT) != 0 {
            if value.eq(default_val)? {
                continue;
            }
        }

        // Call serializer hook if present
        if has_serializer {
            let serializers = obj.getattr("__jce_serializers__")?;
            let serializer_name: String = serializers.get_item(&name)?.extract()?;
            let serializer_func = obj.getattr(&serializer_name)?;
            value = serializer_func.call1((value, context))?;
        }

        if jce_type_code == 255 {
            encode_generic_field(py, writer, tag, &value, options, context, depth + 1)?;
            continue;
        }

        let jce_type = JceType::try_from(jce_type_code)
            .map_err(|id| PyValueError::new_err(format!("Invalid JCE type code: {}", id)))?;

        encode_field(
            py,
            writer,
            tag,
            &value,
            jce_type,
            options,
            context,
            depth + 1,
        )?;
    }
    Ok(())
}

fn encode_generic_struct(
    py: Python<'_>,
    writer: &mut JceWriter,
    dict: &Bound<'_, PyDict>,
    options: i32,
    context: &Bound<'_, PyAny>,
    depth: usize,
) -> PyResult<()> {
    if depth > MAX_DEPTH {
        return Err(PyValueError::new_err("Max recursion depth exceeded"));
    }

    for (key, value) in dict.iter() {
        let tag: u8 = key.extract().map_err(|_| {
            PyTypeError::new_err("JceDict keys must be int tags for struct encoding")
        })?;
        encode_generic_field(py, writer, tag, &value, options, context, depth + 1)?;
    }
    Ok(())
}

fn encode_generic_field(
    py: Python<'_>,
    writer: &mut JceWriter,
    tag: u8,
    value: &Bound<'_, PyAny>,
    options: i32,
    context: &Bound<'_, PyAny>,
    depth: usize,
) -> PyResult<()> {
    if value.is_none() {
        return Ok(());
    }

    if let Ok(val) = value.cast::<PyInt>() {
        let v: i64 = val.extract()?;
        writer.write_int(tag, v);
    } else if let Ok(val) = value.cast::<PyFloat>() {
        let v: f64 = val.extract()?;
        writer.write_double(tag, v);
    } else if let Ok(val) = value.cast::<PyString>() {
        let v: String = val.extract()?;
        writer.write_string(tag, &v);
    } else if let Ok(val) = value.cast::<PyBytes>() {
        writer.write_bytes(tag, val.as_bytes());
    } else if let Ok(val) = value.cast::<PyList>() {
        writer.write_tag(tag, JceType::List);
        writer.write_int(0, val.len() as i64);
        for item in val.iter() {
            encode_generic_field(py, writer, 0, &item, options, context, depth + 1)?;
        }
    } else if let Ok(val) = value.cast::<PyDict>() {
        let type_name = value.get_type().name()?.to_string();
        if type_name == "JceDict" {
            writer.write_tag(tag, JceType::StructBegin);
            encode_generic_struct(py, writer, val, options, context, depth + 1)?;
            writer.write_tag(0, JceType::StructEnd);
        } else {
            writer.write_tag(tag, JceType::Map);
            writer.write_int(0, val.len() as i64);
            for (k, v) in val.iter() {
                encode_generic_field(py, writer, 0, &k, options, context, depth + 1)?;
                encode_generic_field(py, writer, 1, &v, options, context, depth + 1)?;
            }
        }
    } else if let Ok(schema_method) = value.getattr("__get_jce_core_schema__") {
        let schema = schema_method.call0()?.cast_into::<PyList>()?;
        writer.write_tag(tag, JceType::StructBegin);
        encode_struct(py, writer, value, &schema, options, context, depth + 1)?;
        writer.write_tag(0, JceType::StructEnd);
    } else if let Ok(schema) = value.getattr("__jce_schema__") {
        if let Ok(schema_list) = schema.cast::<PyList>() {
            writer.write_tag(tag, JceType::StructBegin);
            encode_struct(py, writer, value, schema_list, options, context, depth + 1)?;
            writer.write_tag(0, JceType::StructEnd);
        } else {
            return Err(PyTypeError::new_err(
                "JceStruct __jce_schema__ must be a list",
            ));
        }
    } else {
        return Err(PyTypeError::new_err(format!(
            "Unsupported type for generic encoding: {}",
            value.get_type()
        )));
    }

    Ok(())
}

fn encode_field(
    py: Python<'_>,
    writer: &mut JceWriter,
    tag: u8,
    value: &Bound<'_, PyAny>,
    jce_type: JceType,
    options: i32,
    context: &Bound<'_, PyAny>,
    depth: usize,
) -> PyResult<()> {
    if value.is_none() {
        return Ok(());
    }

    match jce_type {
        JceType::Int1 | JceType::Int2 | JceType::Int4 | JceType::Int8 | JceType::ZeroTag => {
            let val: i64 = value.extract()?;
            writer.write_int(tag, val);
        }
        JceType::Float => {
            let val: f32 = value.extract()?;
            writer.write_float(tag, val);
        }
        JceType::Double => {
            let val: f64 = value.extract()?;
            writer.write_double(tag, val);
        }
        JceType::String1 | JceType::String4 => {
            let val: String = value.extract()?;
            writer.write_string(tag, &val);
        }
        JceType::SimpleList => {
            if let Ok(val) = value.cast::<PyBytes>() {
                writer.write_bytes(tag, val.as_bytes());
            } else {
                // Binary Blob 模式: 自动序列化非字节对象
                let serialized = dumps_generic(
                    py,
                    value.clone().into(),
                    options,
                    Some(context.clone().into()),
                )?;
                let bytes = serialized.bind(py).cast::<PyBytes>()?;
                writer.write_bytes(tag, bytes.as_bytes());
            }
        }
        JceType::List => {
            let val = value.cast::<PyList>()?;
            writer.write_tag(tag, JceType::List);
            writer.write_int(0, val.len() as i64);
            for item in val.iter() {
                encode_generic_field(py, writer, 0, &item, options, context, depth + 1)?;
            }
        }
        JceType::Map => {
            let val = value.cast::<PyDict>()?;
            writer.write_tag(tag, JceType::Map);
            writer.write_int(0, val.len() as i64);
            for (k, v) in val.iter() {
                encode_generic_field(py, writer, 0, &k, options, context, depth + 1)?;
                encode_generic_field(py, writer, 1, &v, options, context, depth + 1)?;
            }
        }
        JceType::StructBegin => {
            writer.write_tag(tag, JceType::StructBegin);
            let type_name = value.get_type().name()?.to_string();
            if type_name == "JceDict" {
                if let Ok(dict) = value.cast::<PyDict>() {
                    encode_generic_struct(py, writer, dict, options, context, depth + 1)?;
                } else {
                    return Err(PyTypeError::new_err("JceDict must be a dict-like object"));
                }
            } else {
                let nested_schema = value.getattr("__jce_schema__")?.cast_into::<PyList>()?;
                encode_struct(py, writer, value, &nested_schema, options, context, depth)?;
            }
            writer.write_tag(0, JceType::StructEnd);
        }
        _ => {
            return Err(PyValueError::new_err(format!(
                "Unsupported JCE type for encoding: {:?}",
                jce_type
            )))
        }
    }
    Ok(())
}

pub(crate) fn decode_struct(
    py: Python<'_>,
    reader: &mut JceReader,
    schema: &Bound<'_, PyList>,
    options: i32,
    context: &Bound<'_, PyAny>,
    depth: usize,
) -> PyResult<Py<PyAny>> {
    if depth > MAX_DEPTH {
        return Err(PyValueError::new_err("Max recursion depth exceeded"));
    }

    let result_dict = PyDict::new(py);

    // Map tag to schema item for quick lookup
    let mut tag_map = std::collections::HashMap::new();
    let schema_items: Vec<Bound<'_, PyTuple>> = schema
        .iter()
        .map(|item| item.cast_into::<PyTuple>())
        .collect::<Result<Vec<_>, _>>()?;

    for tuple in &schema_items {
        let tag: u8 = tuple.get_item(1)?.extract()?;
        tag_map.insert(tag, tuple);
    }

    while !reader.is_end() {
        let (tag, jce_type) = match reader.read_head() {
            Ok(h) => h,
            Err(e) => return Err(map_decode_error(e)),
        };

        if jce_type == JceType::StructEnd {
            break;
        }

        if let Some(tuple) = tag_map.get(&tag) {
            let name: String = tuple.get_item(0)?.extract()?;
            let jce_type_code: u8 = tuple.get_item(2)?.extract()?;
            let _has_deserializer: bool = tuple.get_item(5)?.extract()?;

            let value = if jce_type_code == 255 {
                // Generic field in struct, use default BytesMode::Auto (2)
                decode_generic_field(
                    py,
                    reader,
                    jce_type,
                    options,
                    BytesMode::Auto,
                    context,
                    depth + 1,
                )?
            } else {
                let expected_type = JceType::try_from(jce_type_code).map_err(|id| {
                    PyValueError::new_err(format!("Invalid JCE type code in schema: {}", id))
                })?;

                decode_field(
                    py,
                    reader,
                    jce_type,
                    expected_type,
                    options,
                    context,
                    depth + 1,
                )?
            };
            result_dict.set_item(name, value)?;
        } else {
            if let Err(e) = reader.skip_field(jce_type) {
                return Err(map_decode_error(e));
            }
        }
    }

    // Fill defaults for missing fields
    for tuple in &schema_items {
        let name: String = tuple.get_item(0)?.extract()?;
        if !result_dict.contains(&name)? {
            let default_val = tuple.get_item(3)?;
            result_dict.set_item(name, default_val)?;
        }
    }

    Ok(result_dict.into())
}

pub(crate) fn decode_generic_struct(
    py: Python<'_>,
    reader: &mut JceReader,
    options: i32,
    bytes_mode: BytesMode,
    context: &Bound<'_, PyAny>,
    depth: usize,
) -> PyResult<Py<PyAny>> {
    if depth > MAX_DEPTH {
        return Err(PyValueError::new_err("Max recursion depth exceeded"));
    }

    let result_dict = PyDict::new(py);

    while !reader.is_end() {
        let (tag, jce_type) = match reader.read_head() {
            Ok(h) => h,
            Err(e) => return Err(map_decode_error(e)),
        };

        if jce_type == JceType::StructEnd {
            break;
        }

        let value = decode_generic_field(
            py,
            reader,
            jce_type,
            options,
            bytes_mode,
            context,
            depth + 1,
        )?;
        result_dict.set_item(tag, value)?;
    }

    Ok(result_dict.into())
}

fn decode_generic_field(
    py: Python<'_>,
    reader: &mut JceReader,
    jce_type: JceType,
    options: i32,
    bytes_mode: BytesMode,
    context: &Bound<'_, PyAny>,
    depth: usize,
) -> PyResult<Py<PyAny>> {
    match jce_type {
        JceType::Int1 | JceType::Int2 | JceType::Int4 | JceType::Int8 | JceType::ZeroTag => {
            let val = reader.read_int(jce_type).map_err(map_decode_error)?;
            Ok(val.into_pyobject(py)?.into())
        }
        JceType::Float => {
            let val = reader.read_float().map_err(map_decode_error)?;
            Ok(val.into_pyobject(py)?.into())
        }
        JceType::Double => {
            let val = reader.read_double().map_err(map_decode_error)?;
            Ok(val.into_pyobject(py)?.into())
        }
        JceType::String1 | JceType::String4 => {
            let val = reader.read_string(jce_type).map_err(map_decode_error)?;
            Ok(val.into_pyobject(py)?.into())
        }
        JceType::SimpleList => {
            let t = reader.read_u8().map_err(map_decode_error)?;
            if t != 0 {
                return Err(PyValueError::new_err(format!(
                    "SimpleList must contain type Byte (0), got {}",
                    t
                )));
            }
            let len = reader.read_size().map_err(map_decode_error)? as usize;
            let buf = reader.read_bytes(len).map_err(map_decode_error)?;

            match bytes_mode {
                BytesMode::Raw => Ok(PyBytes::new(py, &buf).into()),
                BytesMode::String => match std::str::from_utf8(&buf) {
                    Ok(s) => Ok(s.into_pyobject(py)?.into()),
                    Err(_) => Ok(PyBytes::new(py, &buf).into()),
                },
                BytesMode::Auto => {
                    // 1. Try safe text
                    if check_safe_text(&buf) {
                        // Safe to unwrap because check_safe_text confirmed it's valid UTF-8
                        let s = unsafe { std::str::from_utf8_unchecked(&buf) };
                        return Ok(s.into_pyobject(py)?.into());
                    }

                    // 2. Try nested JCE (if not empty)
                    if !buf.is_empty() {
                        // Try to decode as generic struct
                        let mut inner_reader = JceReader::new(&buf, options);
                        match decode_generic_struct(
                            py,
                            &mut inner_reader,
                            options,
                            bytes_mode,
                            context,
                            depth + 1,
                        ) {
                            Ok(res) => {
                                if let Ok(dict) = res.bind(py).cast::<PyDict>() {
                                    if !dict.is_empty() {
                                        return Ok(res);
                                    }
                                }
                            }
                            Err(_) => {
                                // Parsing failed, ignore and treat as bytes
                            }
                        }
                    }

                    Ok(PyBytes::new(py, &buf).into())
                }
            }
        }
        JceType::List => {
            let (_, t) = reader.read_head().map_err(map_decode_error)?;
            let len = reader.read_int(t).map_err(map_decode_error)? as usize;
            let list = PyList::empty(py);
            for _ in 0..len {
                let (_, it) = reader.read_head().map_err(map_decode_error)?;
                let item =
                    decode_generic_field(py, reader, it, options, bytes_mode, context, depth + 1)?;
                list.append(item)?;
            }
            Ok(list.into())
        }
        JceType::Map => {
            let (_, t) = reader.read_head().map_err(map_decode_error)?;
            let len = reader.read_int(t).map_err(map_decode_error)? as usize;
            let dict = PyDict::new(py);
            for _ in 0..len {
                let (_, kt) = reader.read_head().map_err(map_decode_error)?;
                let key =
                    decode_generic_field(py, reader, kt, options, bytes_mode, context, depth + 1)?;
                let (_, vt) = reader.read_head().map_err(map_decode_error)?;
                let value =
                    decode_generic_field(py, reader, vt, options, bytes_mode, context, depth + 1)?;
                dict.set_item(key, value)?;
            }
            Ok(dict.into())
        }
        JceType::StructBegin => {
            decode_generic_struct(py, reader, options, bytes_mode, context, depth)
        }
        _ => {
            if let Err(e) = reader.skip_field(jce_type) {
                return Err(map_decode_error(e));
            }
            Ok(py.None())
        }
    }
}

fn decode_field(
    py: Python<'_>,
    reader: &mut JceReader,
    actual_type: JceType,
    _expected_type: JceType,
    options: i32,
    context: &Bound<'_, PyAny>,
    depth: usize,
) -> PyResult<Py<PyAny>> {
    match actual_type {
        JceType::Int1 | JceType::Int2 | JceType::Int4 | JceType::Int8 | JceType::ZeroTag => {
            let val = reader.read_int(actual_type).map_err(map_decode_error)?;
            Ok(val.into_pyobject(py)?.into())
        }
        JceType::Float => {
            let val = reader.read_float().map_err(map_decode_error)?;
            Ok(val.into_pyobject(py)?.into())
        }
        JceType::Double => {
            let val = reader.read_double().map_err(map_decode_error)?;
            Ok(val.into_pyobject(py)?.into())
        }
        JceType::String1 | JceType::String4 => {
            let val = reader.read_string(actual_type).map_err(map_decode_error)?;
            Ok(val.into_pyobject(py)?.into())
        }
        JceType::SimpleList => {
            let t = reader.read_u8().map_err(map_decode_error)?;
            if t != 0 {
                return Err(PyValueError::new_err(format!(
                    "SimpleList must contain type Byte (0), got {}",
                    t
                )));
            }
            let len = reader.read_size().map_err(map_decode_error)? as usize;

            let buf = reader.read_bytes(len).map_err(map_decode_error)?;
            Ok(PyBytes::new(py, &buf).into())
        }
        JceType::List => {
            let len = reader.read_size().map_err(map_decode_error)? as usize;
            let list = PyList::empty(py);
            for _ in 0..len {
                let (_, it) = reader.read_head().map_err(map_decode_error)?;
                let item = decode_generic_field(
                    py,
                    reader,
                    it,
                    options,
                    BytesMode::Auto,
                    context,
                    depth + 1,
                )?;
                list.append(item)?;
            }
            Ok(list.into())
        }
        JceType::Map => {
            let len = reader.read_size().map_err(map_decode_error)? as usize;
            let dict = PyDict::new(py);
            for _ in 0..len {
                let (_, kt) = reader.read_head().map_err(map_decode_error)?;
                let key = decode_generic_field(
                    py,
                    reader,
                    kt,
                    options,
                    BytesMode::Auto,
                    context,
                    depth + 1,
                )?;
                let (_, vt) = reader.read_head().map_err(map_decode_error)?;
                let value = decode_generic_field(
                    py,
                    reader,
                    vt,
                    options,
                    BytesMode::Auto,
                    context,
                    depth + 1,
                )?;
                dict.set_item(key, value)?;
            }
            Ok(dict.into())
        }
        JceType::StructBegin => {
            decode_generic_struct(py, reader, options, BytesMode::Auto, context, depth)
        }
        _ => {
            reader.skip_field(actual_type).map_err(map_decode_error)?;
            Ok(py.None())
        }
    }
}

fn map_decode_error(err: JceDecodeError) -> PyErr {
    Python::attach(|py| {
        if let Ok(module) = py.import("jce.exceptions") {
            if let Ok(cls) = module.getattr("JceDecodeError") {
                if let Ok(err_obj) = cls.call1((err.to_string(),)) {
                    return PyErr::from_value(err_obj);
                }
            }
        }
        PyValueError::new_err(err.to_string())
    })
}
