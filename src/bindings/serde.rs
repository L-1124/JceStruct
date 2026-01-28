use crate::bindings::schema::{CompiledSchema, compile_schema};
use crate::codec::consts::JceType;
use crate::codec::reader::JceReader;
use crate::codec::writer::JceWriter;
use byteorder::{BigEndian, LittleEndian};
use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyCapsule, PyDict, PyList, PyTuple, PyType};
use std::cell::RefCell;

thread_local! {
    static TLS_WRITER: RefCell<JceWriter<Vec<u8>, BigEndian>> = RefCell::new(JceWriter::new());
}

const MAX_DEPTH: usize = 100;
const OPT_OMIT_DEFAULT: i32 = 32;
const OPT_EXCLUDE_UNSET: i32 = 64;

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
    for &b in data {
        if b < 32 {
            if b != 9 && b != 10 && b != 13 {
                return false;
            }
        } else if b == 127 {
            return false;
        }
    }
    std::str::from_utf8(data).is_ok()
}

fn get_or_compile_schema(
    py: Python<'_>,
    schema_or_type: &Bound<'_, PyAny>,
) -> PyResult<Option<Py<PyCapsule>>> {
    if let Ok(capsule) = schema_or_type.cast::<PyCapsule>() {
        return Ok(Some(capsule.clone().unbind()));
    }
    if let Ok(cls) = schema_or_type.cast::<PyType>() {
        if let Ok(cached) = cls.getattr("__tars_compiled_schema__")
            && let Ok(capsule) = cached.cast::<PyCapsule>()
        {
            return Ok(Some(capsule.clone().unbind()));
        }
        let schema_list_method = cls.getattr("__get_core_schema__")?;
        let schema_list = schema_list_method.call0()?;
        let list = schema_list.cast::<PyList>()?;
        let capsule = compile_schema(py, list)?;
        cls.setattr("__tars_compiled_schema__", &capsule)?;
        return Ok(Some(capsule));
    }
    Ok(None)
}

#[pyfunction]
#[pyo3(signature = (obj, schema, options=0, context=None))]
pub fn dumps(
    py: Python<'_>,
    obj: &Bound<'_, PyAny>,
    schema: &Bound<'_, PyAny>,
    options: i32,
    context: Option<&Bound<'_, PyAny>>,
) -> PyResult<Py<PyBytes>> {
    let context_bound = match context {
        Some(ctx) => ctx.clone(),
        None => PyDict::new(py).into_any(),
    };
    let bytes = if options & 1 == 0 {
        TLS_WRITER.with(|cell| {
            if let Ok(mut writer) = cell.try_borrow_mut() {
                writer.clear();
                encode_struct(py, &mut *writer, obj, schema, options, &context_bound, 0)?;
                Ok::<Vec<u8>, PyErr>(writer.get_buffer().to_vec())
            } else {
                let mut writer = JceWriter::<Vec<u8>, BigEndian>::new();
                encode_struct(py, &mut writer, obj, schema, options, &context_bound, 0)?;
                Ok(writer.get_buffer().to_vec())
            }
        })?
    } else {
        let mut writer = JceWriter::<Vec<u8>, LittleEndian>::with_buffer(Vec::with_capacity(128));
        encode_struct(py, &mut writer, obj, schema, options, &context_bound, 0)?;
        writer.get_buffer().to_vec()
    };
    Ok(PyBytes::new(py, &bytes).into())
}

#[pyfunction]
#[pyo3(signature = (data, options=0, context=None))]
pub fn dumps_generic(
    py: Python<'_>,
    data: &Bound<'_, PyAny>,
    options: i32,
    context: Option<&Bound<'_, PyAny>>,
) -> PyResult<Py<PyBytes>> {
    let context_bound = match context {
        Some(ctx) => ctx.clone(),
        None => PyDict::new(py).into_any(),
    };
    let bytes = if options & 1 == 0 {
        TLS_WRITER.with(|cell| {
            if let Ok(mut writer) = cell.try_borrow_mut() {
                writer.clear();
                if let Ok(dict) = data.cast::<PyDict>() {
                    encode_generic_struct(py, &mut *writer, dict, options, &context_bound, 0)?;
                } else {
                    encode_generic_field(py, &mut *writer, 0, data, options, &context_bound, 0)?;
                }
                Ok::<Vec<u8>, PyErr>(writer.get_buffer().to_vec())
            } else {
                let mut writer = JceWriter::<Vec<u8>, BigEndian>::new();
                if let Ok(dict) = data.cast::<PyDict>() {
                    encode_generic_struct(py, &mut writer, dict, options, &context_bound, 0)?;
                } else {
                    encode_generic_field(py, &mut writer, 0, data, options, &context_bound, 0)?;
                }
                Ok(writer.get_buffer().to_vec())
            }
        })?
    } else {
        let mut writer = JceWriter::<Vec<u8>, LittleEndian>::with_buffer(Vec::with_capacity(128));
        if let Ok(dict) = data.cast::<PyDict>() {
            encode_generic_struct(py, &mut writer, dict, options, &context_bound, 0)?;
        } else {
            encode_generic_field(py, &mut writer, 0, data, options, &context_bound, 0)?;
        }
        writer.get_buffer().to_vec()
    };
    Ok(PyBytes::new(py, &bytes).into())
}

#[pyfunction]
#[pyo3(signature = (data, target, options=0, context=None))]
pub fn loads(
    py: Python<'_>,
    data: &Bound<'_, PyBytes>,
    target: &Bound<'_, PyAny>,
    options: i32,
    context: Option<&Bound<'_, PyAny>>,
) -> PyResult<Py<PyAny>> {
    let bytes = data.as_bytes();
    let dict = if options & 1 == 0 {
        decode_struct(
            py,
            &mut JceReader::<BigEndian>::new(bytes),
            target,
            options,
            0,
        )?
    } else {
        decode_struct(
            py,
            &mut JceReader::<LittleEndian>::new(bytes),
            target,
            options,
            0,
        )?
    };
    let kwargs = PyDict::new(py);
    if let Some(ctx) = context {
        kwargs.set_item("context", ctx)?;
    }
    Ok(target
        .call_method("model_validate", (dict,), Some(&kwargs))?
        .unbind())
}

#[pyfunction]
#[pyo3(signature = (data, options=0, bytes_mode=2))]
pub fn loads_generic(
    py: Python<'_>,
    data: &Bound<'_, PyBytes>,
    options: i32,
    bytes_mode: u8,
) -> PyResult<Py<PyAny>> {
    let bytes = data.as_bytes();
    let mode = BytesMode::from(bytes_mode);
    if options & 1 == 0 {
        decode_generic_struct(
            py,
            &mut JceReader::<BigEndian>::new(bytes),
            options,
            mode,
            0,
        )
    } else {
        decode_generic_struct(
            py,
            &mut JceReader::<LittleEndian>::new(bytes),
            options,
            mode,
            0,
        )
    }
}

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
        self.write_tag(tag, type_id)
    }
    #[inline]
    fn write_int(&mut self, tag: u8, value: i64) {
        self.write_int(tag, value)
    }
    #[inline]
    fn write_float(&mut self, tag: u8, value: f32) {
        self.write_float(tag, value)
    }
    #[inline]
    fn write_double(&mut self, tag: u8, value: f64) {
        self.write_double(tag, value)
    }
    #[inline]
    fn write_string(&mut self, tag: u8, value: &str) {
        self.write_string(tag, value)
    }
    #[inline]
    fn write_bytes(&mut self, tag: u8, value: &[u8]) {
        self.write_bytes(tag, value)
    }
}

pub(crate) fn encode_struct<W: JceWriterTrait>(
    py: Python<'_>,
    writer: &mut W,
    obj: &Bound<'_, PyAny>,
    schema: &Bound<'_, PyAny>,
    options: i32,
    context: &Bound<'_, PyAny>,
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
        return encode_struct_compiled(py, writer, obj, compiled, options, context, depth);
    }
    let schema_list = schema.cast::<PyList>()?;
    for item in schema_list.iter() {
        let tuple = item.cast::<PyTuple>()?;
        let name: String = tuple.get_item(0)?.extract()?;
        let tag: u8 = tuple.get_item(1)?.extract()?;
        let jce_type_code: u8 = tuple.get_item(2)?.extract()?;
        let default_val = tuple.get_item(3)?;
        let value = obj.getattr(&name)?;
        if value.is_none() {
            continue;
        }
        if (options & OPT_EXCLUDE_UNSET) != 0
            && let Ok(model_fields_set) = obj.getattr("model_fields_set")
            && !model_fields_set
                .call_method1("__contains__", (&name,))?
                .extract::<bool>()?
        {
            continue;
        }
        if (options & OPT_OMIT_DEFAULT) != 0 && value.eq(&default_val)? {
            continue;
        }
        if jce_type_code == 255 {
            encode_generic_field(py, writer, tag, &value, options, context, depth + 1)?;
        } else {
            let jce_type = JceType::try_from(jce_type_code).unwrap();
            encode_field(
                py,
                writer,
                tag,
                jce_type,
                &value,
                options,
                context,
                depth + 1,
            )?;
        }
    }
    Ok(())
}

fn encode_struct_compiled<W: JceWriterTrait>(
    py: Python<'_>,
    writer: &mut W,
    obj: &Bound<'_, PyAny>,
    schema: &CompiledSchema,
    options: i32,
    context: &Bound<'_, PyAny>,
    depth: usize,
) -> PyResult<()> {
    for field in &schema.fields {
        // Optimization: Use interned py_name for getattr
        let value = obj.getattr(field.py_name.bind(py))?;
        if value.is_none() {
            continue;
        }
        if (options & OPT_OMIT_DEFAULT) != 0 && value.eq(field.default_val.bind(py))? {
            continue;
        }
        if field.tars_type == 255 {
            encode_generic_field(py, writer, field.tag, &value, options, context, depth + 1)?;
        } else {
            let jce_type = JceType::try_from(field.tars_type).unwrap_or(JceType::ZeroTag);
            encode_field(
                py,
                writer,
                field.tag,
                jce_type,
                &value,
                options,
                context,
                depth + 1,
            )?;
        }
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn encode_field<W: JceWriterTrait>(
    py: Python<'_>,
    writer: &mut W,
    tag: u8,
    jce_type: JceType,
    value: &Bound<'_, PyAny>,
    options: i32,
    context: &Bound<'_, PyAny>,
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
                encode_generic_field(py, writer, 0, &k, options, context, depth + 1)?;
                encode_generic_field(py, writer, 1, &v, options, context, depth + 1)?;
            }
        }
        JceType::List => {
            let list = value.cast::<PyList>()?;
            writer.write_tag(tag, JceType::List);
            writer.write_int(0, list.len() as i64);
            for item in list {
                encode_generic_field(py, writer, 0, &item, options, context, depth + 1)?;
            }
        }
        JceType::SimpleList => {
            if let Ok(bytes) = value.cast::<PyBytes>() {
                writer.write_bytes(tag, bytes.as_bytes());
            } else {
                let inner_bytes = if options & 1 == 0 {
                    let mut bytes_out = Vec::new();
                    let mut done = false;
                    TLS_WRITER.with(|cell| {
                        if let Ok(mut writer) = cell.try_borrow_mut() {
                            writer.clear();
                            if let Ok(dict) = value.cast::<PyDict>() {
                                encode_generic_struct(
                                    py,
                                    &mut *writer,
                                    dict,
                                    options,
                                    context,
                                    depth + 1,
                                )?;
                            } else if let Ok(schema_method) = value.getattr("__get_core_schema__") {
                                encode_struct(
                                    py,
                                    &mut *writer,
                                    value,
                                    &schema_method.call0()?,
                                    options,
                                    context,
                                    depth + 1,
                                )?;
                            } else {
                                encode_generic_field(
                                    py,
                                    &mut *writer,
                                    0,
                                    value,
                                    options,
                                    context,
                                    depth + 1,
                                )?;
                            }
                            bytes_out = writer.get_buffer().to_vec();
                            done = true;
                        }
                        Ok::<(), PyErr>(())
                    })?;
                    if !done {
                        let mut w = JceWriter::<Vec<u8>, BigEndian>::new();
                        if let Ok(dict) = value.cast::<PyDict>() {
                            encode_generic_struct(py, &mut w, dict, options, context, depth + 1)?;
                        } else if let Ok(schema_method) = value.getattr("__get_core_schema__") {
                            encode_struct(
                                py,
                                &mut w,
                                value,
                                &schema_method.call0()?,
                                options,
                                context,
                                depth + 1,
                            )?;
                        } else {
                            encode_generic_field(
                                py,
                                &mut w,
                                0,
                                value,
                                options,
                                context,
                                depth + 1,
                            )?;
                        }
                        bytes_out = w.get_buffer().to_vec();
                    }
                    bytes_out
                } else {
                    let mut w =
                        JceWriter::<Vec<u8>, LittleEndian>::with_buffer(Vec::with_capacity(128));
                    if let Ok(dict) = value.cast::<PyDict>() {
                        encode_generic_struct(py, &mut w, dict, options, context, depth + 1)?;
                    } else if let Ok(schema_method) = value.getattr("__get_core_schema__") {
                        encode_struct(
                            py,
                            &mut w,
                            value,
                            &schema_method.call0()?,
                            options,
                            context,
                            depth + 1,
                        )?;
                    } else {
                        encode_generic_field(py, &mut w, 0, value, options, context, depth + 1)?;
                    }
                    w.get_buffer().to_vec()
                };
                writer.write_bytes(tag, &inner_bytes);
            }
        }
        JceType::StructBegin => {
            writer.write_tag(tag, JceType::StructBegin);
            if let Ok(schema_method) = value.getattr("__get_core_schema__") {
                encode_struct(
                    py,
                    writer,
                    value,
                    &schema_method.call0()?,
                    options,
                    context,
                    depth + 1,
                )?;
            } else if let Ok(dict) = value.cast::<PyDict>() {
                encode_generic_struct(py, writer, dict, options, context, depth + 1)?;
            } else {
                return Err(PyTypeError::new_err("Cannot encode as struct"));
            }
            writer.write_tag(0, JceType::StructEnd);
        }
        _ => return Err(PyValueError::new_err("Unsupported type")),
    }
    Ok(())
}

pub(crate) fn encode_generic_struct<W: JceWriterTrait>(
    py: Python<'_>,
    writer: &mut W,
    data: &Bound<'_, PyDict>,
    options: i32,
    context: &Bound<'_, PyAny>,
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
                t_str.parse::<u8>().unwrap_or(255)
            } else {
                tag_str.parse::<u8>().unwrap_or(255)
            }
        };
        if tag != 255 {
            items.push((tag, v));
        }
    }
    items.sort_by_key(|(t, _)| *t);
    for (tag, value) in items {
        encode_generic_field(py, writer, tag, &value, options, context, depth + 1)?;
    }
    Ok(())
}

pub(crate) fn encode_generic_field<W: JceWriterTrait>(
    py: Python<'_>,
    writer: &mut W,
    tag: u8,
    value: &Bound<'_, PyAny>,
    options: i32,
    context: &Bound<'_, PyAny>,
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
        for item in l {
            encode_generic_field(py, writer, 0, &item, options, context, depth + 1)?;
        }
    } else if let Ok(d) = value.cast::<PyDict>() {
        let type_name = value.get_type().name()?;
        if type_name.to_str()? == "StructDict" {
            writer.write_tag(tag, JceType::StructBegin);
            encode_generic_struct(py, writer, d, options, context, depth + 1)?;
            writer.write_tag(0, JceType::StructEnd);
        } else {
            writer.write_tag(tag, JceType::Map);
            writer.write_int(0, d.len() as i64);
            for (k, v) in d {
                encode_generic_field(py, writer, 0, &k, options, context, depth + 1)?;
                encode_generic_field(py, writer, 1, &v, options, context, depth + 1)?;
            }
        }
    } else if let Ok(schema_method) = value.getattr("__get_core_schema__") {
        writer.write_tag(tag, JceType::StructBegin);
        encode_struct(
            py,
            writer,
            value,
            &schema_method.call0()?,
            options,
            context,
            depth + 1,
        )?;
        writer.write_tag(0, JceType::StructEnd);
    } else {
        return Err(PyTypeError::new_err("Cannot infer type"));
    }
    Ok(())
}

pub(crate) fn decode_struct<'a, E: crate::codec::endian::Endianness>(
    py: Python<'_>,
    reader: &mut JceReader<'a, E>,
    schema: &Bound<'_, PyAny>,
    options: i32,
    depth: usize,
) -> PyResult<Py<PyAny>> {
    if depth > MAX_DEPTH {
        return Err(PyValueError::new_err("Depth exceeded"));
    }
    if let Some(capsule_py) = get_or_compile_schema(py, schema)? {
        let capsule = capsule_py.bind(py);
        let ptr = capsule
            .pointer_checked(None)
            .map_err(|_| PyValueError::new_err("Invalid capsule"))?;
        let compiled = unsafe { &*(ptr.as_ptr() as *mut CompiledSchema) };
        return decode_struct_compiled(py, reader, compiled, options, depth);
    }
    let schema_list = schema.cast::<PyList>()?;
    let result_dict = PyDict::new(py);
    let mut tag_map = std::collections::HashMap::new();
    let schema_items: Vec<Bound<'_, PyTuple>> = schema_list
        .iter()
        .map(|item| item.cast_into::<PyTuple>())
        .collect::<Result<Vec<_>, _>>()?;
    for tuple in &schema_items {
        tag_map.insert(tuple.get_item(1)?.extract::<u8>()?, tuple);
    }
    while !reader.is_end() {
        let (tag, jce_type) = reader.read_head()?;
        if jce_type == JceType::StructEnd {
            break;
        }
        if let Some(tuple) = tag_map.get(&tag) {
            let name: String = tuple.get_item(0)?.extract()?;
            let jce_type_code: u8 = tuple.get_item(2)?.extract()?;
            let value = if jce_type_code == 255 {
                decode_generic_field(py, reader, jce_type, options, BytesMode::Auto, depth + 1)?
            } else {
                decode_field(
                    py,
                    reader,
                    jce_type,
                    JceType::try_from(jce_type_code).unwrap(),
                    options,
                    depth + 1,
                )?
            };
            result_dict.set_item(name, value)?;
        } else {
            reader.skip_field(jce_type)?;
        }
    }
    for tuple in &schema_items {
        let name: String = tuple.get_item(0)?.extract()?;
        if !result_dict.contains(&name)? {
            result_dict.set_item(name, tuple.get_item(3)?)?;
        }
    }
    Ok(result_dict.into())
}

fn decode_struct_compiled<'a, E: crate::codec::endian::Endianness>(
    py: Python<'_>,
    reader: &mut JceReader<'a, E>,
    schema: &CompiledSchema,
    options: i32,
    depth: usize,
) -> PyResult<Py<PyAny>> {
    let result_dict = PyDict::new(py);
    while !reader.is_end() {
        let (tag, jce_type) = reader.read_head()?;
        if jce_type == JceType::StructEnd {
            break;
        }
        // Optimization: Use tag_lookup array
        if let Some(field_idx) = schema.tag_lookup[tag as usize] {
            let field = &schema.fields[field_idx];
            let value = if field.tars_type == 255 {
                decode_generic_field(py, reader, jce_type, options, BytesMode::Auto, depth + 1)?
            } else {
                decode_field(
                    py,
                    reader,
                    jce_type,
                    JceType::try_from(field.tars_type).unwrap(),
                    options,
                    depth + 1,
                )?
            };
            result_dict.set_item(field.py_name.bind(py), value)?;
        } else {
            reader.skip_field(jce_type)?;
        }
    }
    for field in &schema.fields {
        if !result_dict.contains(field.py_name.bind(py))? {
            result_dict.set_item(field.py_name.bind(py), field.default_val.bind(py))?;
        }
    }
    Ok(result_dict.into())
}

fn decode_field<'a, E: crate::codec::endian::Endianness>(
    py: Python<'_>,
    reader: &mut JceReader<'a, E>,
    actual_type: JceType,
    expected_type: JceType,
    options: i32,
    depth: usize,
) -> PyResult<Py<PyAny>> {
    let is_compatible = match expected_type {
        JceType::Int1 | JceType::Int2 | JceType::Int4 | JceType::Int8 => matches!(
            actual_type,
            JceType::Int1 | JceType::Int2 | JceType::Int4 | JceType::Int8 | JceType::ZeroTag
        ),
        JceType::Float => actual_type == JceType::Float,
        JceType::Double => actual_type == JceType::Double || actual_type == JceType::Float,
        JceType::String1 | JceType::String4 => {
            matches!(actual_type, JceType::String1 | JceType::String4)
        }
        _ => actual_type == expected_type,
    };
    if !is_compatible && actual_type != JceType::StructEnd {
        return decode_generic_field(py, reader, actual_type, options, BytesMode::Auto, depth);
    }
    match expected_type {
        JceType::Int1 | JceType::Int2 | JceType::Int4 | JceType::Int8 => Ok(reader
            .read_int(actual_type)?
            .into_pyobject(py)?
            .unbind()
            .into_any()),
        JceType::Float => Ok(reader.read_float()?.into_pyobject(py)?.unbind().into_any()),
        JceType::Double => Ok(reader.read_double()?.into_pyobject(py)?.unbind().into_any()),
        JceType::String1 | JceType::String4 => Ok(reader
            .read_string(actual_type)?
            .into_pyobject(py)?
            .unbind()
            .into_any()),
        JceType::Map => decode_map(py, reader, options, BytesMode::Auto, depth),
        JceType::List => decode_list(py, reader, options, BytesMode::Auto, depth),
        JceType::SimpleList => {
            let (_, t) = reader.read_head()?;
            if t != JceType::Int1 {
                reader.skip_field(JceType::SimpleList)?;
                return Ok(py.None());
            }
            let size = reader.read_size()?;
            Ok(PyBytes::new(py, reader.read_bytes(size as usize)?).into())
        }
        JceType::StructBegin => decode_generic_struct(py, reader, options, BytesMode::Auto, depth),
        _ => Err(PyValueError::new_err("Unsupported type")),
    }
}

fn decode_map<'a, E: crate::codec::endian::Endianness>(
    py: Python<'_>,
    reader: &mut JceReader<'a, E>,
    options: i32,
    bytes_mode: BytesMode,
    depth: usize,
) -> PyResult<Py<PyAny>> {
    let size = reader.read_size()?;
    let dict = PyDict::new(py);
    for _ in 0..size {
        let (_, ktype) = reader.read_head()?;
        let key = decode_generic_field(py, reader, ktype, options, bytes_mode, depth + 1)?;
        let (_, vtype) = reader.read_head()?;
        let value = decode_generic_field(py, reader, vtype, options, bytes_mode, depth + 1)?;
        dict.set_item(key, value)?;
    }
    Ok(dict.into())
}

fn decode_list<'a, E: crate::codec::endian::Endianness>(
    py: Python<'_>,
    reader: &mut JceReader<'a, E>,
    options: i32,
    bytes_mode: BytesMode,
    depth: usize,
) -> PyResult<Py<PyAny>> {
    let size = reader.read_size()?;
    let list = PyList::empty(py);
    for _ in 0..size {
        let (_, t) = reader.read_head()?;
        list.append(decode_generic_field(
            py,
            reader,
            t,
            options,
            bytes_mode,
            depth + 1,
        )?)?;
    }
    Ok(list.into())
}

pub(crate) fn decode_generic_struct<'a, E: crate::codec::endian::Endianness>(
    py: Python<'_>,
    reader: &mut JceReader<'a, E>,
    options: i32,
    bytes_mode: BytesMode,
    depth: usize,
) -> PyResult<Py<PyAny>> {
    if depth > MAX_DEPTH {
        return Err(PyValueError::new_err("Depth exceeded"));
    }
    let dict = PyDict::new(py);
    while !reader.is_end() {
        let (tag, jce_type) = reader.read_head()?;
        if jce_type == JceType::StructEnd {
            break;
        }
        dict.set_item(
            tag,
            decode_generic_field(py, reader, jce_type, options, bytes_mode, depth + 1)?,
        )?;
    }
    Ok(dict.into())
}

fn decode_generic_field<'a, E: crate::codec::endian::Endianness>(
    py: Python<'_>,
    reader: &mut JceReader<'a, E>,
    jce_type: JceType,
    options: i32,
    bytes_mode: BytesMode,
    depth: usize,
) -> PyResult<Py<PyAny>> {
    match jce_type {
        JceType::Int1 | JceType::Int2 | JceType::Int4 | JceType::Int8 => Ok(reader
            .read_int(jce_type)?
            .into_pyobject(py)?
            .unbind()
            .into_any()),
        JceType::Float => Ok(reader.read_float()?.into_pyobject(py)?.unbind().into_any()),
        JceType::Double => Ok(reader.read_double()?.into_pyobject(py)?.unbind().into_any()),
        JceType::String1 | JceType::String4 => Ok(reader
            .read_string(jce_type)?
            .into_pyobject(py)?
            .unbind()
            .into_any()),
        JceType::Map => decode_map(py, reader, options, bytes_mode, depth),
        JceType::List => decode_list(py, reader, options, bytes_mode, depth),
        JceType::SimpleList => {
            let (_, t) = reader.read_head()?;
            if t != JceType::Int1 {
                reader.skip_field(JceType::SimpleList)?;
                return Ok(py.None());
            }
            let size = reader.read_size()?;
            let bytes = reader.read_bytes(size as usize)?;
            match bytes_mode {
                BytesMode::Raw => Ok(PyBytes::new(py, bytes).into()),
                BytesMode::String => {
                    if let Ok(s) = std::str::from_utf8(bytes) {
                        Ok(s.into_pyobject(py)?.unbind().into_any())
                    } else {
                        Ok(PyBytes::new(py, bytes).into())
                    }
                }
                BytesMode::Auto => {
                    if check_safe_text(bytes) {
                        Ok(String::from_utf8_lossy(bytes)
                            .into_pyobject(py)?
                            .unbind()
                            .into_any())
                    } else {
                        // Optimization: Use JceScanner for zero-allocation probing
                        let mut scanner = crate::codec::scanner::JceScanner::<E>::new(bytes);
                        if scanner.validate_struct().is_ok() && scanner.is_end() {
                            let mut probe = JceReader::<E>::new(bytes);
                            if let Ok(obj) = decode_generic_struct(
                                py,
                                &mut probe,
                                options,
                                BytesMode::Auto,
                                depth + 1,
                            ) {
                                return Ok(obj);
                            }
                        }
                        Ok(PyBytes::new(py, bytes).into())
                    }
                }
            }
        }
        JceType::StructBegin => decode_generic_struct(py, reader, options, bytes_mode, depth),
        JceType::ZeroTag => Ok(0i64.into_pyobject(py)?.unbind().into_any()),
        JceType::StructEnd => Ok(py.None()),
    }
}
