use pyo3::prelude::*;
use pyo3::types::{PyCapsule, PyList, PyString, PyTuple};

use crate::codec::consts::JCE_TYPE_GENERIC;

#[derive(Debug, Clone)]
pub struct Validators {
    pub gt: Option<f64>,
    pub lt: Option<f64>,
    pub ge: Option<f64>,
    pub le: Option<f64>,
    pub min_len: Option<usize>,
    pub max_len: Option<usize>,
}

#[derive(Debug)]
pub struct FieldDef {
    pub name: String,
    pub py_name: Py<PyString>,
    pub tag: u8,
    pub jce_type: u8,
    pub type_ref: Py<PyAny>,
    pub default_val: Py<PyAny>,
    pub validators: Option<Validators>,
}

#[derive(Debug)]
pub struct CompiledSchema {
    pub fields: Vec<FieldDef>,
    pub tag_lookup: [Option<usize>; 256], // Map tag -> index in fields
}

/// 剥离 Optional/Union，获取真正的类型
/// 例如: Optional[int] -> int
///
/// 处理逻辑:
/// 1. 检查 `__origin__` 是否为 Union/UnionType。
/// 2. 遍历 `__args__`，移除 NoneType。
/// 3. 如果剩余参数只有一个，则递归解包该参数。
/// 4. 否则返回原始类型 (多重 Union 暂不处理或视为原始类型)。
fn unwrap_optional<'py>(
    py: Python<'py>,
    type_ref: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    if let Ok(origin) = type_ref.getattr("__origin__")
        && let Ok(origin_name) = origin.getattr("__name__")
    {
        let name: String = origin_name.extract()?;
        if name == "Union" || name == "UnionType" {
            let args = type_ref.getattr("__args__")?.cast::<PyTuple>()?.clone();
            let mut non_none_args = Vec::new();
            let none_type = py.get_type::<pyo3::types::PyNone>();
            for arg in args.iter() {
                if !arg.is(&none_type) {
                    non_none_args.push(arg);
                }
            }
            if non_none_args.len() == 1 {
                return unwrap_optional(py, &non_none_args[0]);
            }
        }
    }
    Ok(type_ref.clone())
}

pub(crate) fn resolve_jce_type(py: Python<'_>, raw_type: &Bound<'_, PyAny>) -> PyResult<u8> {
    let type_ref = unwrap_optional(py, raw_type)?;
    if type_ref.is(py.get_type::<pyo3::types::PyBool>()) {
        return Ok(0); // BYTE
    }
    if type_ref.is(py.get_type::<pyo3::types::PyInt>()) {
        return Ok(2); // INT
    }
    if type_ref.is(py.get_type::<pyo3::types::PyFloat>()) {
        return Ok(5); // DOUBLE
    }
    if type_ref.is(py.get_type::<pyo3::types::PyString>()) {
        return Ok(6); // STRING1
    }
    if type_ref.is(py.get_type::<pyo3::types::PyBytes>()) {
        return Ok(13); // SIMPLE_LIST
    }
    // Duck Typing: 检查 __tars_schema__
    if type_ref.hasattr("__tars_schema__")? {
        return Ok(10); // STRUCT
    }
    // 泛型检查
    if let Ok(origin) = type_ref.getattr("__origin__") {
        if origin.is(py.get_type::<pyo3::types::PyList>()) {
            return Ok(9); // LIST
        }
        if origin.is(py.get_type::<pyo3::types::PyDict>()) {
            return Ok(8); // MAP
        }
    }
    // 原生容器类型
    if type_ref.is(py.get_type::<pyo3::types::PyList>()) {
        return Ok(9);
    }
    if type_ref.is(py.get_type::<pyo3::types::PyDict>()) {
        return Ok(8);
    }
    // 默认兜底
    Ok(JCE_TYPE_GENERIC) // Generic
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

        // 接收 3 元素: (name, field_info, raw_type)
        if tuple.len() != 3 {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "Schema item must be (name, info, type)",
            ));
        }

        // 1. 字段名处理
        let name: String = tuple.get_item(0)?.extract()?;
        let py_name = PyString::intern(py, &name)
            .into_any()
            .unbind()
            .extract::<Py<PyString>>(py)?;

        // 2. 字段元数据 (Tag, 默认值, 校验器)
        let field_info = tuple.get_item(1)?;
        let tag: u8 = field_info.getattr("tag")?.extract()?;
        let default_val = field_info.getattr("default")?.unbind();

        // 提取校验规则
        // 辅助闭包: 从属性提取 Option<f64>
        let extract_opt = |name: &str| -> PyResult<Option<f64>> {
            match field_info.getattr(name) {
                Ok(val) => val.extract(),
                Err(_) => Ok(None), // 兼容旧版本: 属性不存在则视为 None
            }
        };

        // 数值比较统一使用 f64
        let gt = extract_opt("gt")?;
        let lt = extract_opt("lt")?;
        let ge = extract_opt("ge")?;
        let le = extract_opt("le")?;

        let min_len: Option<usize> = match field_info.getattr("min_len") {
            Ok(val) => val.extract()?,
            Err(_) => None,
        };
        let max_len: Option<usize> = match field_info.getattr("max_len") {
            Ok(val) => val.extract()?,
            Err(_) => None,
        };

        let validators = if gt.is_some()
            || lt.is_some()
            || ge.is_some()
            || le.is_some()
            || min_len.is_some()
            || max_len.is_some()
        {
            Some(Validators {
                gt,
                lt,
                ge,
                le,
                min_len,
                max_len,
            })
        } else {
            None
        };

        // 3. 类型推断
        let raw_type = tuple.get_item(2)?;
        let jce_type = resolve_jce_type(py, &raw_type)?;

        // 保存解包后的类型引用 (例如 Optional[User] -> User)
        let type_ref = unwrap_optional(py, &raw_type)?.unbind();

        // 重复 Tag 检查
        if tag_lookup[tag as usize].is_some() {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "Duplicate tag {}",
                tag
            )));
        }
        tag_lookup[tag as usize] = Some(idx);

        fields.push(FieldDef {
            name,
            py_name,
            tag,
            jce_type,
            type_ref,
            default_val,
            validators,
        });
    }

    let compiled = CompiledSchema { fields, tag_lookup };
    let capsule = PyCapsule::new(py, compiled, None)?;
    Ok(capsule.into())
}

#[cfg(test)]
mod tests {
    use super::*;
    use pyo3::types::PyModule;
    use std::ffi::CString;

    #[test]
    fn test_compile_schema() {
        #[allow(deprecated)]
        pyo3::prepare_freethreaded_python();
        Python::attach(|py| -> PyResult<()> {
            let code = r#"
class FieldInfo:
    def __init__(self, tag, default=None, gt=None, lt=None, ge=None, le=None, min_len=None, max_len=None):
        self.tag = tag
        self.default = default
        self.gt = gt
        self.lt = lt
        self.ge = ge
        self.le = le
        self.min_len = min_len
        self.max_len = max_len
"#;
            let code = CString::new(code).unwrap();
            let filename = CString::new("test_schema.py").unwrap();
            let module_name = CString::new("test_schema").unwrap();
            let module = PyModule::from_code(py, &code, &filename, &module_name)?;
            let field_info_cls = module.getattr("FieldInfo")?;

            let schema_list = PyList::empty(py);
            let info_uid = field_info_cls.call1((0u8, 0i64))?;
            let info_name = field_info_cls.call1((1u8, "unknown"))?;
            schema_list.append(("uid", info_uid, py.get_type::<pyo3::types::PyInt>()))?;
            schema_list.append(("name", info_name, py.get_type::<pyo3::types::PyString>()))?;

            let capsule = compile_schema(py, &schema_list)?;
            let bound = capsule.bind(py);

            let ptr = bound
                .pointer_checked(None)
                .map_err(|_| pyo3::exceptions::PyValueError::new_err("Capsule pointer error"))?;
            let schema: &CompiledSchema = unsafe { &*(ptr.as_ptr() as *const CompiledSchema) };

            assert_eq!(schema.fields.len(), 2);
            assert_eq!(schema.fields[0].name, "uid");
            assert_eq!(schema.tag_lookup[0], Some(0));
            assert_eq!(schema.tag_lookup[1], Some(1));
            Ok(())
        })
        .unwrap();
    }

    #[test]
    fn test_duplicate_tag() {
        #[allow(deprecated)]
        pyo3::prepare_freethreaded_python();
        Python::attach(|py| -> PyResult<()> {
            let code = r#"
class FieldInfo:
    def __init__(self, tag, default=None):
        self.tag = tag
        self.default = default
"#;
            let code = CString::new(code).unwrap();
            let filename = CString::new("test_schema_dup.py").unwrap();
            let module_name = CString::new("test_schema_dup").unwrap();
            let module = PyModule::from_code(py, &code, &filename, &module_name)?;
            let field_info_cls = module.getattr("FieldInfo")?;

            let schema_list = PyList::empty(py);
            let info1 = field_info_cls.call1((0u8, 0i64))?;
            let info2 = field_info_cls.call1((0u8, 0i64))?;
            schema_list.append(("f1", info1, py.get_type::<pyo3::types::PyInt>()))?;
            schema_list.append(("f2", info2, py.get_type::<pyo3::types::PyInt>()))?;

            let res = compile_schema(py, &schema_list);
            assert!(res.is_err());
            Ok(())
        })
        .unwrap();
    }
}
