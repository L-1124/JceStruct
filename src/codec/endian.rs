use byteorder::{BigEndian, LittleEndian};

pub trait Endianness: byteorder::ByteOrder + Copy + Default + 'static {
    const IS_LITTLE: bool;
}

impl Endianness for BigEndian {
    const IS_LITTLE: bool = false;
}

impl Endianness for LittleEndian {
    const IS_LITTLE: bool = true;
}
