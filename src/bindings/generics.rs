use pyo3::intern;
use pyo3::prelude::*;
use pyo3::types::PyTuple;

/// 解析泛型类型为具体类型。
///
/// 根据上下文解析 `TypeVar` 或泛型别名。
/// 例如: 如果 `target_type` 是 `T` (TypeVar) 且 `context_type` 是 `Response[User]`,
/// 则返回 `User`.
///
/// 同时处理嵌套泛型: `List[T]` -> `List[User]`.
pub fn resolve_concrete_type<'py>(
    py: Python<'py>,
    target_type: &Bound<'py, PyAny>,
    context_type: Option<&Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    let Some(context) = context_type else {
        return Ok(target_type.clone());
    };

    // 1. 尝试解析 TypeVar (直接在上下文中找到)
    if let Some(resolved) = try_resolve_typevar(py, target_type, context)? {
        return Ok(resolved);
    }

    // 2. 如果 target_type 是 GenericAlias (例如 List[T])，递归解析其参数
    if let Ok(args) = target_type.getattr(intern!(py, "__args__"))
        && let Ok(origin) = target_type.getattr(intern!(py, "__origin__"))
        && let Ok(args_tuple) = args.cast_into::<PyTuple>()
    {
        let mut resolved_args = Vec::with_capacity(args_tuple.len());
        let mut changed = false;

        for arg in args_tuple.iter() {
            let resolved = resolve_concrete_type(py, &arg, Some(context))?;
            if !resolved.is(&arg) {
                changed = true;
            }
            resolved_args.push(resolved);
        }

        if changed {
            let resolved_args_tuple = PyTuple::new(py, resolved_args)?;
            // 构造新类型: Origin[Arg1, Arg2]
            // Python 中: origin.__getitem__(args)
            return origin.get_item(resolved_args_tuple);
        }
    }

    Ok(target_type.clone())
}

/// 辅助函数：检查 type_var 是否在上下文参数中，并返回对应的实参。
fn try_resolve_typevar<'py>(
    py: Python<'py>,
    target_type: &Bound<'py, PyAny>,
    context: &Bound<'py, PyAny>,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    // 检查上下文是否具有 __origin__ (是否为 GenericAlias)
    if let Ok(origin) = context.getattr(intern!(py, "__origin__"))
        && let Ok(params) = origin.getattr(intern!(py, "__parameters__"))
    {
        // 获取 origin 的参数 (例如 [T])
        if let Ok(params_tuple) = params.cast_into::<PyTuple>() {
            // 在 params 中查找 target_type
            for (i, param) in params_tuple.iter().enumerate() {
                // 使用相等性检查 (TypeVar 实例通常是单例)
                if param.eq(target_type)? {
                    // 找到匹配。从上下文中获取相应的 arg
                    if let Ok(args) = context.getattr(intern!(py, "__args__"))
                        && let Ok(args_tuple) = args.cast_into::<PyTuple>()
                        && let Ok(arg) = args_tuple.get_item(i)
                    {
                        return Ok(Some(arg.clone()));
                    }
                }
            }
        }
    }
    Ok(None)
}
