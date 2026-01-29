use std::fmt;

#[derive(Debug, Clone)]
enum PathItem {
    Field(String),
    Index(usize),
    Key(String),
    Tag(u8),
}

/// 错误上下文，用于跟踪序列化/反序列化路径以提供精确的错误信息 (JSONPath 风格)。
#[derive(Debug, Clone, Default)]
pub struct ErrorContext {
    stack: Vec<PathItem>,
}

impl ErrorContext {
    pub fn new() -> Self {
        Self {
            stack: Vec::with_capacity(8),
        }
    }

    /// 进入结构体字段
    pub fn push_field(&mut self, name: &str) {
        self.stack.push(PathItem::Field(name.to_string()));
    }

    /// 进入列表索引
    pub fn push_index(&mut self, index: usize) {
        self.stack.push(PathItem::Index(index));
    }

    /// 进入字典键
    pub fn push_key(&mut self, key: &str) {
        self.stack.push(PathItem::Key(key.to_string()));
    }

    /// 进入未知字段 (仅 Tag)
    pub fn push_tag(&mut self, tag: u8) {
        self.stack.push(PathItem::Tag(tag));
    }

    pub fn pop(&mut self) {
        self.stack.pop();
    }

    pub fn current_field(&self) -> Option<&str> {
        match self.stack.last() {
            Some(PathItem::Field(name)) => Some(name),
            _ => None,
        }
    }
}

impl fmt::Display for ErrorContext {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "$")?;
        for item in &self.stack {
            match item {
                PathItem::Field(name) => write!(f, ".{}", name)?,
                PathItem::Index(idx) => write!(f, "[{}]", idx)?,
                PathItem::Key(key) => write!(f, "[\"{}\"]", key)?,
                PathItem::Tag(tag) => write!(f, "<tag:{}>", tag)?,
            }
        }
        Ok(())
    }
}
