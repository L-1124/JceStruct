use crate::bindings::schema::Validators;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

#[inline]
pub fn validate_f64(field_name: &str, v: f64, rules: &Validators) -> PyResult<()> {
    if let Some(target) = rules.gt
        && v <= target
    {
        return Err(validation_error(field_name, "greater than", target));
    }
    if let Some(target) = rules.lt
        && v >= target
    {
        return Err(validation_error(field_name, "less than", target));
    }
    if let Some(target) = rules.ge
        && v < target
    {
        return Err(validation_error(
            field_name,
            "greater than or equal to",
            target,
        ));
    }
    if let Some(target) = rules.le
        && v > target
    {
        return Err(validation_error(
            field_name,
            "less than or equal to",
            target,
        ));
    }
    Ok(())
}

#[inline]
pub fn validate_len(field_name: &str, len: usize, rules: &Validators) -> PyResult<()> {
    if let Some(min) = rules.min_len
        && len < min
    {
        return Err(validation_error(field_name, "min length", min as f64));
    }
    if let Some(max) = rules.max_len
        && len > max
    {
        return Err(validation_error(field_name, "max length", max as f64));
    }
    Ok(())
}

#[inline]
/// 执行字段级验证规则 (Python 对象版本)。
pub fn validate(
    _py: Python<'_>,
    val: &Bound<'_, PyAny>,
    rules: &Validators,
    field_name: &str,
) -> PyResult<()> {
    // 1. 数值验证 (int/float)
    if rules.gt.is_some() || rules.lt.is_some() || rules.ge.is_some() || rules.le.is_some() {
        // 尝试提取为 f64
        if let Ok(v) = val.extract::<f64>() {
            validate_f64(field_name, v, rules)?;
        }
    }

    // 2. 长度验证 (str/bytes/list/dict)
    if (rules.min_len.is_some() || rules.max_len.is_some())
        && let Ok(len) = val.len()
    {
        validate_len(field_name, len, rules)?;
    }

    Ok(())
}

/// 构造验证错误信息。
fn validation_error(field: &str, reason: &str, target: f64) -> PyErr {
    PyValueError::new_err(format!(
        "Validation failed for field '{}': expected {} {}",
        field, reason, target
    ))
}
