//! K0 lexer.

#[derive(Debug, Clone, PartialEq)]
pub enum Tok {
    Ident(String),
    Int(i64),
    Float(f64),
    /// Keywords
    Fn,
    Let,
    Return,
    If,
    Else,
    While,
    True,
    False,
    /// Types
    TyI32,
    TyI64,
    TyF64,
    TyBool,
    /// Punct
    LParen,
    RParen,
    LBrace,
    RBrace,
    LBracket,
    RBracket,
    Comma,
    Colon,
    Semi,
    Arrow,
    Assign,
    Plus,
    Minus,
    Star,
    Slash,
    Percent,
    Eq,
    Ne,
    Lt,
    Le,
    Gt,
    Ge,
    AndAnd,
    OrOr,
    Not,
    Eof,
}

pub struct Lexer<'a> {
    src: &'a [u8],
    i: usize,
    pub line: usize,
}

impl<'a> Lexer<'a> {
    pub fn new(src: &'a str) -> Self {
        Self {
            src: src.as_bytes(),
            i: 0,
            line: 1,
        }
    }

    fn peek(&self) -> Option<u8> {
        self.src.get(self.i).copied()
    }

    fn bump(&mut self) -> Option<u8> {
        let c = self.peek()?;
        self.i += 1;
        if c == b'\n' {
            self.line += 1;
        }
        Some(c)
    }

    fn skip_ws_comments(&mut self) {
        loop {
            while let Some(c) = self.peek() {
                if c == b' ' || c == b'\t' || c == b'\r' || c == b'\n' {
                    self.bump();
                } else {
                    break;
                }
            }
            if self.peek() == Some(b'/') && self.src.get(self.i + 1) == Some(&b'/') {
                while let Some(c) = self.bump() {
                    if c == b'\n' {
                        break;
                    }
                }
                continue;
            }
            break;
        }
    }

    pub fn next_tok(&mut self) -> Result<Tok, String> {
        self.skip_ws_comments();
        let Some(c) = self.peek() else {
            return Ok(Tok::Eof);
        };
        // multi-char ops
        if c == b'-' && self.src.get(self.i + 1) == Some(&b'>') {
            self.bump();
            self.bump();
            return Ok(Tok::Arrow);
        }
        if c == b'=' && self.src.get(self.i + 1) == Some(&b'=') {
            self.bump();
            self.bump();
            return Ok(Tok::Eq);
        }
        if c == b'!' && self.src.get(self.i + 1) == Some(&b'=') {
            self.bump();
            self.bump();
            return Ok(Tok::Ne);
        }
        if c == b'<' && self.src.get(self.i + 1) == Some(&b'=') {
            self.bump();
            self.bump();
            return Ok(Tok::Le);
        }
        if c == b'>' && self.src.get(self.i + 1) == Some(&b'=') {
            self.bump();
            self.bump();
            return Ok(Tok::Ge);
        }
        if c == b'&' && self.src.get(self.i + 1) == Some(&b'&') {
            self.bump();
            self.bump();
            return Ok(Tok::AndAnd);
        }
        if c == b'|' && self.src.get(self.i + 1) == Some(&b'|') {
            self.bump();
            self.bump();
            return Ok(Tok::OrOr);
        }

        match c {
            b'(' => {
                self.bump();
                Ok(Tok::LParen)
            }
            b')' => {
                self.bump();
                Ok(Tok::RParen)
            }
            b'{' => {
                self.bump();
                Ok(Tok::LBrace)
            }
            b'}' => {
                self.bump();
                Ok(Tok::RBrace)
            }
            b'[' => {
                self.bump();
                Ok(Tok::LBracket)
            }
            b']' => {
                self.bump();
                Ok(Tok::RBracket)
            }
            b',' => {
                self.bump();
                Ok(Tok::Comma)
            }
            b':' => {
                self.bump();
                Ok(Tok::Colon)
            }
            b';' => {
                self.bump();
                Ok(Tok::Semi)
            }
            b'=' => {
                self.bump();
                Ok(Tok::Assign)
            }
            b'+' => {
                self.bump();
                Ok(Tok::Plus)
            }
            b'-' => {
                self.bump();
                Ok(Tok::Minus)
            }
            b'*' => {
                self.bump();
                Ok(Tok::Star)
            }
            b'/' => {
                self.bump();
                Ok(Tok::Slash)
            }
            b'%' => {
                self.bump();
                Ok(Tok::Percent)
            }
            b'<' => {
                self.bump();
                Ok(Tok::Lt)
            }
            b'>' => {
                self.bump();
                Ok(Tok::Gt)
            }
            b'!' => {
                self.bump();
                Ok(Tok::Not)
            }
            b'0'..=b'9' => self.number(),
            b'a'..=b'z' | b'A'..=b'Z' | b'_' => self.ident_or_kw(),
            _ => Err(format!(
                "line {}: unexpected character {:?}",
                self.line, c as char
            )),
        }
    }

    fn number(&mut self) -> Result<Tok, String> {
        let start = self.i;
        while matches!(self.peek(), Some(b'0'..=b'9')) {
            self.bump();
        }
        let mut is_float = false;
        if self.peek() == Some(b'.') {
            is_float = true;
            self.bump();
            while matches!(self.peek(), Some(b'0'..=b'9')) {
                self.bump();
            }
        }
        let s = std::str::from_utf8(&self.src[start..self.i]).unwrap();
        if is_float {
            let v: f64 = s
                .parse()
                .map_err(|_| format!("line {}: bad float {s}", self.line))?;
            Ok(Tok::Float(v))
        } else {
            let v: i64 = s
                .parse()
                .map_err(|_| format!("line {}: bad int {s}", self.line))?;
            Ok(Tok::Int(v))
        }
    }

    fn ident_or_kw(&mut self) -> Result<Tok, String> {
        let start = self.i;
        while matches!(
            self.peek(),
            Some(b'a'..=b'z' | b'A'..=b'Z' | b'0'..=b'9' | b'_')
        ) {
            self.bump();
        }
        let s = std::str::from_utf8(&self.src[start..self.i]).unwrap();
        Ok(match s {
            "fn" => Tok::Fn,
            "let" => Tok::Let,
            "return" => Tok::Return,
            "if" => Tok::If,
            "else" => Tok::Else,
            "while" => Tok::While,
            "true" => Tok::True,
            "false" => Tok::False,
            "i32" => Tok::TyI32,
            "i64" => Tok::TyI64,
            "f64" => Tok::TyF64,
            "bool" => Tok::TyBool,
            _ => Tok::Ident(s.to_string()),
        })
    }
}
