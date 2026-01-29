use crate::bindings::error::ErrorContext;
use crate::bindings::generics::resolve_concrete_type;
use crate::bindings::schema::{CompiledSchema, Validators, compile_schema, resolve_jce_type};
use crate::bindings::validator::{validate, validate_f64, validate_len};
use crate::codec::consts::{JCE_TYPE_GENERIC, JceType};
use crate::codec::reader::JceReader;
use byteorder::{BigEndian, LittleEndian};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyCapsule, PyDict, PyList, PyTuple, PyType};

/// 最大递归深度，防止栈溢出。
const MAX_DEPTH: usize = 100;

/// 字节数据反序列化模式。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum BytesMode {
    /// 始终返回 `bytes`。
    Raw = 0,
    /// 尝试 UTF-8 解码，成功则返回 `str`，失败返回 `bytes`。
    String = 1,
    /// 智能探测：
    /// 1. 尝试 UTF-8 解码且无控制字符 -> `str`。
    /// 2. 尝试递归解析为 JCE 结构体 -> `dict`。
    /// 3. 否则 -> `bytes`。
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

/// 检查字节序列是否为安全的文本 (无控制字符且为有效 UTF-8)。
///
/// 用于 `BytesMode::Auto` 判定是否应转换为字符串。
/// 允许的控制字符: `\t` (9), `\n` (10), `\r` (13)。
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
    simdutf8::basic::from_utf8(data).is_ok()
}

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

#[pyfunction]
#[pyo3(signature = (data, target=None, options=0))]
/// 反序列化 JCE 二进制数据。
///
/// 参数:
/// - `data`: JCE 格式的字节流。
/// - `target`: 目标类型 (类或 `typing.Type`)，可选。如果提供，将尝试匹配 Schema 并实例化。
/// - `options`: 反序列化选项 (如字节序)。
pub fn loads(
    py: Python<'_>,
    data: &Bound<'_, PyBytes>,
    target: Option<&Bound<'_, PyAny>>,
    options: i32,
) -> PyResult<Py<PyAny>> {
    loads_impl(py, data, target, options, 2)
}

#[pyfunction]
#[pyo3(signature = (data, options=0, bytes_mode=2))]
/// 反序列化 JCE 二进制数据为通用字典 (无模式)。
///
/// 当不知道数据结构时使用此函数，返回包含 Tag/Value 的字典。
///
/// 参数:
/// - `bytes_mode`: 控制 `SimpleList<byte>` 的解析行为 (0=Raw, 1=String, 2=Auto)。
pub fn loads_generic(
    py: Python<'_>,
    data: &Bound<'_, PyBytes>,
    options: i32,
    bytes_mode: u8,
) -> PyResult<Py<PyAny>> {
    loads_impl(py, data, None, options, bytes_mode)
}

/// 反序列化核心实现。
///
/// 根据 `options` 选择大小端序读取器。
fn loads_impl(
    py: Python<'_>,
    data: &Bound<'_, PyBytes>,
    target: Option<&Bound<'_, PyAny>>,
    options: i32,
    bytes_mode: u8,
) -> PyResult<Py<PyAny>> {
    let bytes = data.as_bytes();
    let mode = BytesMode::from(bytes_mode);
    let mut context = ErrorContext::new();

    let result = if options & 1 == 0 {
        let mut reader = JceReader::<BigEndian>::new(bytes);
        decode_dispatch(py, &mut reader, target, options, mode, &mut context)
    } else {
        let mut reader = JceReader::<LittleEndian>::new(bytes);
        decode_dispatch(py, &mut reader, target, options, mode, &mut context)
    };

    result.map_err(|e| PyValueError::new_err(format!("{} at {}", e, context)))
}

/// 根据目标类型分发反序列化逻辑。
fn decode_dispatch<'a, E: crate::codec::endian::Endianness>(
    py: Python<'_>,
    reader: &mut JceReader<'a, E>,
    target: Option<&Bound<'_, PyAny>>,
    options: i32,
    mode: BytesMode,
    context: &mut ErrorContext,
) -> PyResult<Py<PyAny>> {
    match target {
        Some(t) => {
            if t.cast::<PyType>().is_ok() || t.getattr("__origin__").is_ok() {
                decode_struct_instance(py, reader, t, options, context)
            } else {
                decode_struct_dict(py, reader, t, options, 0, context)
            }
        }
        None => decode_generic_struct(py, reader, options, mode, 0, context),
    }
}

/// 反序列化 JCE 结构体为 Python 字典 (带模式引导)。
///
/// 当 `target` 为字典类型 (如 `TypedDict`) 或手动构造的 Schema List 时使用。
pub(crate) fn decode_struct_dict<'a, E: crate::codec::endian::Endianness>(
    py: Python<'_>,
    reader: &mut JceReader<'a, E>,
    schema: &Bound<'_, PyAny>,
    options: i32,
    depth: usize,
    context: &mut ErrorContext,
) -> PyResult<Py<PyAny>> {
    if depth > MAX_DEPTH {
        return Err(PyValueError::new_err("Depth exceeded"));
    }
    // 优先尝试预编译 Schema
    if let Some(capsule_py) = get_or_compile_schema(py, schema)? {
        let capsule = capsule_py.bind(py);
        let ptr = capsule
            .pointer_checked(None)
            .map_err(|_| PyValueError::new_err("Invalid capsule"))?;
        let compiled = unsafe { &*(ptr.as_ptr() as *mut CompiledSchema) };
        return decode_struct_dict_compiled(py, reader, compiled, options, depth, context);
    }
    // 降级: 解析 Schema List
    let schema_list = schema.cast::<PyList>()?;
    let result_dict = PyDict::new(py);
    // 建立 Tag -> Schema Item 映射
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
            context.push_field(&name);

            // 递归解码字段
            let value = if jce_type_code == JCE_TYPE_GENERIC {
                decode_generic_field(
                    py,
                    reader,
                    jce_type,
                    options,
                    BytesMode::Auto,
                    depth + 1,
                    context,
                )?
            } else {
                decode_field(
                    py,
                    reader,
                    jce_type,
                    JceType::try_from(jce_type_code).unwrap(),
                    None,
                    None, // No validation for struct dict fallback
                    options,
                    depth + 1,
                    context,
                )?
            };
            result_dict.set_item(name, value)?;
            context.pop();
        } else {
            // 跳过 Schema 中未定义的字段 (未知 Tag)
            reader.skip_field(jce_type)?;
        }
    }
    // 填充默认值
    for tuple in &schema_items {
        let name: String = tuple.get_item(0)?.extract()?;
        if !result_dict.contains(&name)? {
            result_dict.set_item(name, tuple.get_item(3)?)?;
        }
    }
    Ok(result_dict.into())
}

/// 使用预编译 Schema 解码为字典。
fn decode_struct_dict_compiled<'a, E: crate::codec::endian::Endianness>(
    py: Python<'_>,
    reader: &mut JceReader<'a, E>,
    schema: &CompiledSchema,
    options: i32,
    depth: usize,
    context: &mut ErrorContext,
) -> PyResult<Py<PyAny>> {
    let result_dict = PyDict::new(py);
    while !reader.is_end() {
        let (tag, jce_type) = reader.read_head()?;
        if jce_type == JceType::StructEnd {
            break;
        }
        if let Some(field_idx) = schema.tag_lookup[tag as usize] {
            let field = &schema.fields[field_idx];
            context.push_field(&field.name);
            let value = if field.jce_type == JCE_TYPE_GENERIC {
                decode_generic_field(
                    py,
                    reader,
                    jce_type,
                    options,
                    BytesMode::Auto,
                    depth + 1,
                    context,
                )?
            } else {
                decode_field(
                    py,
                    reader,
                    jce_type,
                    JceType::try_from(field.jce_type).unwrap(),
                    Some(field.type_ref.bind(py)),
                    None, // No validation here to match legacy behavior, or we could add field.validators.as_ref()
                    options,
                    depth + 1,
                    context,
                )?
            };
            result_dict.set_item(field.py_name.bind(py), value)?;
            context.pop();
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

/// 反序列化 JCE 结构体并实例化 Python 对象。
pub(crate) fn decode_struct_instance<'a, E: crate::codec::endian::Endianness>(
    py: Python<'_>,
    reader: &mut JceReader<'a, E>,
    target_cls: &Bound<'_, PyAny>,
    options: i32,
    context: &mut ErrorContext,
) -> PyResult<Py<PyAny>> {
    let (actual_cls, context_type) = if let Ok(origin) = target_cls.getattr("__origin__") {
        (origin, Some(target_cls))
    } else {
        (target_cls.clone(), Some(target_cls))
    };
    let instance = actual_cls.call_method1("__new__", (&actual_cls,))?;
    let capsule_opt = get_or_compile_schema(py, &actual_cls)?;
    if let Some(capsule_py) = capsule_opt {
        let capsule = capsule_py.bind(py);
        let ptr = capsule
            .pointer_checked(None)
            .map_err(|_| PyValueError::new_err("Invalid capsule"))?;
        let compiled = unsafe { &*(ptr.as_ptr() as *mut CompiledSchema) };
        return decode_struct_instance_compiled(
            py,
            reader,
            &instance,
            compiled,
            options,
            0,
            context,
            context_type,
        );
    }
    Err(PyValueError::new_err(
        "Could not compile schema for target class",
    ))
}

/// 使用预编译 Schema 实例化对象。
///
/// **关键逻辑**:
/// 1. 遍历二进制流中的 Tag。
/// 2. 匹配 Schema 中的字段定义。
/// 3. 如果字段是 Generic，尝试根据上下文推断具体类型 (处理 `T` 等泛型)。
/// 4. 执行验证 (Validators)。
/// 5. 设置对象属性。
#[allow(clippy::too_many_arguments)]
fn decode_struct_instance_compiled<'a, E: crate::codec::endian::Endianness>(
    py: Python<'_>,
    reader: &mut JceReader<'a, E>,
    instance: &Bound<'_, PyAny>,
    schema: &CompiledSchema,
    options: i32,
    depth: usize,
    context: &mut ErrorContext,
    context_type: Option<&Bound<'_, PyAny>>,
) -> PyResult<Py<PyAny>> {
    if depth > MAX_DEPTH {
        return Err(PyValueError::new_err("Depth exceeded"));
    }
    while !reader.is_end() {
        let (tag, jce_type) = reader.read_head()?;
        if jce_type == JceType::StructEnd {
            break;
        }
        if let Some(field_idx) = schema.tag_lookup[tag as usize] {
            let field = &schema.fields[field_idx];
            context.push_field(&field.name);

            let value = if field.jce_type == JCE_TYPE_GENERIC {
                // 尝试解析泛型字段的具体类型
                let field_type_ref = field.type_ref.bind(py);
                if let Ok(resolved) = resolve_concrete_type(py, field_type_ref, context_type)
                    && let Ok(resolved_jce) = resolve_jce_type(py, &resolved)
                    && resolved_jce != JCE_TYPE_GENERIC
                {
                    // 成功推断出具体类型，按该类型解码
                    let expected_type = JceType::try_from(resolved_jce).unwrap_or(JceType::ZeroTag);
                    decode_field(
                        py,
                        reader,
                        jce_type,
                        expected_type,
                        Some(&resolved),
                        field.validators.as_ref(), // Pass validators
                        options,
                        depth + 1,
                        context,
                    )?
                } else {
                    // 无法推断，使用通用解码
                    let v = decode_generic_field(
                        py,
                        reader,
                        jce_type,
                        options,
                        BytesMode::Auto,
                        depth + 1,
                        context,
                    )?;
                    // Fallback validation for generic fields
                    if let Some(rules) = &field.validators {
                        validate(py, v.bind(py), rules, &field.name)?;
                    }
                    v
                }
            } else {
                // 处理标准字段 (可能包含嵌套泛型)
                let field_type_ref = field.type_ref.bind(py);
                let resolved_type = resolve_concrete_type(py, field_type_ref, context_type)?;
                decode_field(
                    py,
                    reader,
                    jce_type,
                    JceType::try_from(field.jce_type).unwrap(),
                    Some(&resolved_type),
                    field.validators.as_ref(), // Pass validators
                    options,
                    depth + 1,
                    context,
                )?
            };

            // Remove separate validate call since it's now inline/handled
            instance.setattr(field.py_name.bind(py), value)?;
            context.pop();
        } else {
            reader.skip_field(jce_type)?;
        }
    }
    // 填充默认值
    for field in &schema.fields {
        if !instance.hasattr(field.py_name.bind(py))? {
            instance.setattr(field.py_name.bind(py), field.default_val.bind(py))?;
        }
    }
    Ok(instance.clone().unbind())
}

/// 解码单个字段。
#[allow(clippy::too_many_arguments)]
fn decode_field<'a, E: crate::codec::endian::Endianness>(
    py: Python<'_>,
    reader: &mut JceReader<'a, E>,
    actual_type: JceType,
    expected_type: JceType,
    expected_py_type: Option<&Bound<'_, PyAny>>,
    validators: Option<&Validators>,
    options: i32,
    depth: usize,
    context: &mut ErrorContext,
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
        // Generic field fallback (no in-place validation here, relies on caller)
        return decode_generic_field(
            py,
            reader,
            actual_type,
            options,
            BytesMode::Auto,
            depth,
            context,
        );
    }
    match expected_type {
        JceType::Int1 | JceType::Int2 | JceType::Int4 | JceType::Int8 => {
            let val = reader.read_int(actual_type)?;
            if let Some(rules) = validators {
                validate_f64(context.current_field().unwrap_or("?"), val as f64, rules)?;
            }
            Ok(val.into_pyobject(py)?.unbind().into_any())
        }
        JceType::Float => {
            let val = reader.read_float()?;
            if let Some(rules) = validators {
                validate_f64(context.current_field().unwrap_or("?"), val as f64, rules)?;
            }
            Ok(val.into_pyobject(py)?.unbind().into_any())
        }
        JceType::Double => {
            let val = reader.read_double()?;
            if let Some(rules) = validators {
                validate_f64(context.current_field().unwrap_or("?"), val, rules)?;
            }
            Ok(val.into_pyobject(py)?.unbind().into_any())
        }
        JceType::String1 | JceType::String4 => {
            let val = reader.read_string(actual_type)?;
            if let Some(rules) = validators {
                validate_len(context.current_field().unwrap_or("?"), val.len(), rules)?;
            }
            Ok(val.into_pyobject(py)?.unbind().into_any())
        }
        JceType::Map => decode_map(py, reader, options, BytesMode::Auto, depth, context),
        JceType::List => decode_list(py, reader, options, BytesMode::Auto, depth, context),
        JceType::SimpleList => {
            let (_, t) = reader.read_head()?;
            if t != JceType::Int1 {
                reader.skip_field(JceType::SimpleList)?;
                return Ok(py.None());
            }
            let size = reader.read_size()?;
            if let Some(rules) = validators {
                validate_len(context.current_field().unwrap_or("?"), size as usize, rules)?;
            }
            Ok(PyBytes::new(py, reader.read_bytes(size as usize)?).into())
        }
        JceType::StructBegin => {
            if let Some(cls) = expected_py_type {
                decode_struct_instance(py, reader, cls, options, context)
            } else {
                decode_generic_struct(py, reader, options, BytesMode::Auto, depth, context)
            }
        }
        _ => Err(PyValueError::new_err("Unsupported type")),
    }
}

/// 解码 JCE Map 为 Python 字典。
fn decode_map<'a, E: crate::codec::endian::Endianness>(
    py: Python<'_>,
    reader: &mut JceReader<'a, E>,
    options: i32,
    bytes_mode: BytesMode,
    depth: usize,
    context: &mut ErrorContext,
) -> PyResult<Py<PyAny>> {
    let size = reader.read_size()?;
    let dict = PyDict::new(py);
    for _ in 0..size {
        let (_, ktype) = reader.read_head()?;
        let key = decode_generic_field(py, reader, ktype, options, bytes_mode, depth + 1, context)?;
        let (_, vtype) = reader.read_head()?;
        let value =
            decode_generic_field(py, reader, vtype, options, bytes_mode, depth + 1, context)?;
        dict.set_item(key, value)?;
    }
    Ok(dict.into())
}

/// 解码 JCE List 为 Python 列表。
fn decode_list<'a, E: crate::codec::endian::Endianness>(
    py: Python<'_>,
    reader: &mut JceReader<'a, E>,
    options: i32,
    bytes_mode: BytesMode,
    depth: usize,
    context: &mut ErrorContext,
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
            context,
        )?)?;
    }
    Ok(list.into())
}

/// 无模式解码 JCE 结构体为 Python 字典。
pub(crate) fn decode_generic_struct<'a, E: crate::codec::endian::Endianness>(
    py: Python<'_>,
    reader: &mut JceReader<'a, E>,
    options: i32,
    bytes_mode: BytesMode,
    depth: usize,
    context: &mut ErrorContext,
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
        context.push_tag(tag);
        dict.set_item(
            tag,
            decode_generic_field(
                py,
                reader,
                jce_type,
                options,
                bytes_mode,
                depth + 1,
                context,
            )?,
        )?;
        context.pop();
    }
    Ok(dict.into())
}

/// 无模式字段探测解码。
fn decode_generic_field<'a, E: crate::codec::endian::Endianness>(
    py: Python<'_>,
    reader: &mut JceReader<'a, E>,
    jce_type: JceType,
    options: i32,
    bytes_mode: BytesMode,
    depth: usize,
    context: &mut ErrorContext,
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
        JceType::Map => decode_map(py, reader, options, bytes_mode, depth, context),
        JceType::List => decode_list(py, reader, options, bytes_mode, depth, context),
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
                        let mut scanner = crate::codec::scanner::JceScanner::<E>::new(bytes);
                        if scanner.validate_struct().is_ok() && scanner.is_end() {
                            let mut probe = JceReader::<E>::new(bytes);
                            if let Ok(obj) = decode_generic_struct(
                                py,
                                &mut probe,
                                options,
                                BytesMode::Auto,
                                depth + 1,
                                context,
                            ) {
                                return Ok(obj);
                            }
                        }
                        Ok(PyBytes::new(py, bytes).into())
                    }
                }
            }
        }
        JceType::StructBegin => {
            decode_generic_struct(py, reader, options, bytes_mode, depth, context)
        }
        JceType::ZeroTag => Ok(0i64.into_pyobject(py)?.unbind().into_any()),
        JceType::StructEnd => Ok(py.None()),
    }
}
