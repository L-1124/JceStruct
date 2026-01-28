use pyo3::prelude::*;
use pyo3::types::{PyCapsule, PyList, PyString, PyTuple};

#[derive(Debug)]
pub struct FieldDef {
    pub name: String,
    pub py_name: Py<PyString>, // Interned Python string，用于 getattr/setattr
    pub tag: u8,
    pub tars_type: u8,
    pub default_val: Py<PyAny>,
    pub has_serializer: bool,
}

#[derive(Debug)]
pub struct CompiledSchema {
    pub fields: Vec<FieldDef>,
    pub tag_lookup: [Option<usize>; 256], // Map tag -> index in fields
}

/// 编译 Schema 以加速序列化/反序列化.
///
/// 将 Python 中的 Schema 列表 (`[(name, tag, type, default, has_ser), ...]`)
/// 转换为 Rust 内部的高效结构 `CompiledSchema`.
///
/// 优化点:
/// 1. 字符串驻留 (Interning): 减少 Python 字符串创建开销.
/// 2. Tag 查找表 (O(1)): 使用数组直接索引 Tag，避免线性扫描.
pub fn compile_schema(py: Python<'_>, schema_list: &Bound<'_, PyList>) -> PyResult<Py<PyCapsule>> {
    let mut fields = Vec::with_capacity(schema_list.len());
    let mut tag_lookup = [None; 256];

    for (idx, item) in schema_list.iter().enumerate() {
        let tuple = item
            .cast::<PyTuple>()
            .map_err(|_| pyo3::exceptions::PyTypeError::new_err("Schema item must be a tuple"))?;

        if tuple.len() != 5 {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "Schema item must have 5 elements, got {}",
                tuple.len()
            )));
        }

        let name: String = tuple.get_item(0)?.extract()?;
        // Intern the string for faster getattr
        let py_name = PyString::intern(py, &name)
            .into_any()
            .unbind()
            .extract::<Py<PyString>>(py)?;

        let tag: u8 = tuple.get_item(1)?.extract()?;
        let tars_type_code: u8 = tuple.get_item(2)?.extract()?;
        let default_val = tuple.get_item(3)?.unbind();
        let has_serializer: bool = tuple.get_item(4)?.extract()?;

        if tag_lookup[tag as usize].is_some() {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "Duplicate tag {} in schema",
                tag
            )));
        }

        tag_lookup[tag as usize] = Some(idx);
        fields.push(FieldDef {
            name,
            py_name,
            tag,
            tars_type: tars_type_code,
            default_val,
            has_serializer,
        });
    }

    let compiled = CompiledSchema { fields, tag_lookup };
    let capsule = PyCapsule::new(py, compiled, None)?;
    Ok(capsule.into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_compile_schema() {
        #[allow(deprecated)]
        pyo3::prepare_freethreaded_python();
        Python::attach(|py| {
            let schema_list = PyList::empty(py);

            schema_list.append(("uid", 0, 0, 0, false)).unwrap();
            schema_list
                .append(("name", 1, 6, "unknown", false))
                .unwrap();

            let capsule = compile_schema(py, &schema_list).unwrap();
            let bound = capsule.bind(py);

            let ptr = bound.pointer_checked(None).expect("Capsule pointer error");
            let schema: &CompiledSchema = unsafe { &*(ptr.as_ptr() as *const CompiledSchema) };
            assert_eq!(schema.fields.len(), 2);
            assert_eq!(schema.fields[0].name, "uid");
            assert_eq!(schema.tag_lookup[0], Some(0));
            assert_eq!(schema.tag_lookup[1], Some(1));
        });
    }

    #[test]
    fn test_duplicate_tag() {
        #[allow(deprecated)]
        pyo3::prepare_freethreaded_python();
        Python::attach(|py| {
            let schema_list = PyList::empty(py);
            schema_list.append(("f1", 0, 0, 0, false)).unwrap();
            schema_list.append(("f2", 0, 0, 0, false)).unwrap();

            let res = compile_schema(py, &schema_list);
            assert!(res.is_err());
        });
    }
}
