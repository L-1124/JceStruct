use byteorder::{BigEndian, LittleEndian};

/// 字节序特征。
///
/// 定义了编解码过程中使用的字节序 (大端或小端)。
pub trait Endianness: byteorder::ByteOrder + Copy + Default + 'static {
    /// 是否为小端序。
    const IS_LITTLE: bool;
}

impl Endianness for BigEndian {
    const IS_LITTLE: bool = false;
}

impl Endianness for LittleEndian {
    const IS_LITTLE: bool = true;
}
