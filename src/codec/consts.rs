/// JCE 数据类型枚举.
///
/// 遵循 JCE 协议规范，使用 `#[repr(u8)]` 以匹配协议中的字节值.
#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum JceType {
    Int1 = 0,
    Int2 = 1,
    Int4 = 2,
    Int8 = 3,
    Float = 4,
    Double = 5,
    String1 = 6,
    String4 = 7,
    Map = 8,
    List = 9,
    StructBegin = 10,
    StructEnd = 11,
    ZeroTag = 12,
    SimpleList = 13,
}

/// 泛型标记 (非 JCE 规范，仅供内部使用)
pub const JCE_TYPE_GENERIC: u8 = 255;

impl TryFrom<u8> for JceType {
    type Error = u8;

    #[inline]
    fn try_from(value: u8) -> Result<Self, Self::Error> {
        match value {
            0 => Ok(JceType::Int1),
            1 => Ok(JceType::Int2),
            2 => Ok(JceType::Int4),
            3 => Ok(JceType::Int8),
            4 => Ok(JceType::Float),
            5 => Ok(JceType::Double),
            6 => Ok(JceType::String1),
            7 => Ok(JceType::String4),
            8 => Ok(JceType::Map),
            9 => Ok(JceType::List),
            10 => Ok(JceType::StructBegin),
            11 => Ok(JceType::StructEnd),
            12 => Ok(JceType::ZeroTag),
            13 => Ok(JceType::SimpleList),
            _ => Err(value),
        }
    }
}

// 常量定义，与 Python 端保持一致
pub const JCE_INT1: u8 = 0;
pub const JCE_INT2: u8 = 1;
pub const JCE_INT4: u8 = 2;
pub const JCE_INT8: u8 = 3;
pub const JCE_FLOAT: u8 = 4;
pub const JCE_DOUBLE: u8 = 5;
pub const JCE_STRING1: u8 = 6;
pub const JCE_STRING4: u8 = 7;
pub const JCE_MAP: u8 = 8;
pub const JCE_LIST: u8 = 9;
pub const JCE_STRUCT_BEGIN: u8 = 10;
pub const JCE_STRUCT_END: u8 = 11;
pub const JCE_ZERO_TAG: u8 = 12;
pub const JCE_SIMPLE_LIST: u8 = 13;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_jce_type_values() {
        assert_eq!(JceType::Int1 as u8, 0);
        assert_eq!(JceType::Int2 as u8, 1);
        assert_eq!(JceType::Int4 as u8, 2);
        assert_eq!(JceType::Int8 as u8, 3);
        assert_eq!(JceType::Float as u8, 4);
        assert_eq!(JceType::Double as u8, 5);
        assert_eq!(JceType::String1 as u8, 6);
        assert_eq!(JceType::String4 as u8, 7);
        assert_eq!(JceType::Map as u8, 8);
        assert_eq!(JceType::List as u8, 9);
        assert_eq!(JceType::StructBegin as u8, 10);
        assert_eq!(JceType::StructEnd as u8, 11);
        assert_eq!(JceType::ZeroTag as u8, 12);
        assert_eq!(JceType::SimpleList as u8, 13);
    }

    #[test]
    fn test_try_from_u8() {
        assert_eq!(JceType::try_from(0), Ok(JceType::Int1));
        assert_eq!(JceType::try_from(13), Ok(JceType::SimpleList));
        assert_eq!(JceType::try_from(14), Err(14));
    }
}
