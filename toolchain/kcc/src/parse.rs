//! K0 recursive-descent parser.

use crate::ast::*;
use crate::lex::{Lexer, Tok};

pub struct Parser<'a> {
    lx: Lexer<'a>,
    cur: Tok,
}

impl<'a> Parser<'a> {
    pub fn new(src: &'a str) -> Result<Self, String> {
        let mut lx = Lexer::new(src);
        let cur = lx.next_tok()?;
        Ok(Self { lx, cur })
    }

    fn bump(&mut self) -> Result<(), String> {
        self.cur = self.lx.next_tok()?;
        Ok(())
    }

    fn eat(&mut self, t: &Tok) -> Result<(), String> {
        if &self.cur == t {
            self.bump()
        } else {
            Err(format!(
                "line {}: expected {:?}, got {:?}",
                self.lx.line, t, self.cur
            ))
        }
    }

    pub fn parse_program(&mut self) -> Result<Program, String> {
        let mut items = Vec::new();
        while self.cur != Tok::Eof {
            items.push(self.parse_item()?);
        }
        Ok(Program { items })
    }

    fn parse_item(&mut self) -> Result<Item, String> {
        match &self.cur {
            Tok::Fn => Ok(Item::Fn(self.parse_fn()?)),
            other => Err(format!(
                "line {}: expected fn, got {:?}",
                self.lx.line, other
            )),
        }
    }

    fn parse_fn(&mut self) -> Result<FnDef, String> {
        self.eat(&Tok::Fn)?;
        let name = self.expect_ident()?;
        self.eat(&Tok::LParen)?;
        let mut params = Vec::new();
        if self.cur != Tok::RParen {
            loop {
                let pname = self.expect_ident()?;
                self.eat(&Tok::Colon)?;
                let ty = self.parse_type()?;
                params.push((pname, ty));
                if self.cur == Tok::Comma {
                    self.bump()?;
                    continue;
                }
                break;
            }
        }
        self.eat(&Tok::RParen)?;
        let ret = if self.cur == Tok::Arrow {
            self.bump()?;
            self.parse_type()?
        } else {
            Type::I32
        };
        let body = self.parse_block()?;
        Ok(FnDef {
            name,
            params,
            ret,
            body,
        })
    }

    fn parse_type(&mut self) -> Result<Type, String> {
        // [T; N]
        if self.cur == Tok::LBracket {
            self.bump()?;
            let elem = self.parse_type()?;
            self.eat(&Tok::Semi)?;
            let len = match &self.cur {
                Tok::Int(n) if *n > 0 && *n <= 4096 => *n as u32,
                other => {
                    return Err(format!(
                        "line {}: expected array length 1..4096, got {:?}",
                        self.lx.line, other
                    ))
                }
            };
            self.bump()?;
            self.eat(&Tok::RBracket)?;
            if matches!(elem, Type::Array { .. }) {
                return Err(format!(
                    "line {}: nested arrays not supported yet",
                    self.lx.line
                ));
            }
            return Ok(Type::Array {
                elem: Box::new(elem),
                len,
            });
        }
        let t = match &self.cur {
            Tok::TyI32 => Type::I32,
            Tok::TyI64 => Type::I64,
            Tok::TyF64 => Type::F64,
            Tok::TyBool => Type::Bool,
            other => {
                return Err(format!(
                    "line {}: expected type, got {:?}",
                    self.lx.line, other
                ))
            }
        };
        self.bump()?;
        Ok(t)
    }

    fn parse_block(&mut self) -> Result<Block, String> {
        self.eat(&Tok::LBrace)?;
        let mut stmts = Vec::new();
        while self.cur != Tok::RBrace && self.cur != Tok::Eof {
            stmts.push(self.parse_stmt()?);
        }
        self.eat(&Tok::RBrace)?;
        Ok(Block { stmts })
    }

    fn parse_stmt(&mut self) -> Result<Stmt, String> {
        match &self.cur {
            Tok::Let => {
                self.bump()?;
                let name = self.expect_ident()?;
                let ty = if self.cur == Tok::Colon {
                    self.bump()?;
                    Some(self.parse_type()?)
                } else {
                    None
                };
                let init = if self.cur == Tok::Assign {
                    self.bump()?;
                    Some(self.parse_expr()?)
                } else if matches!(ty, Some(Type::Array { .. })) {
                    None // zero-init array
                } else {
                    return Err(format!(
                        "line {}: let requires initializer (except fixed arrays)",
                        self.lx.line
                    ));
                };
                self.eat(&Tok::Semi)?;
                Ok(Stmt::Let { name, ty, init })
            }
            Tok::Return => {
                self.bump()?;
                let e = if self.cur == Tok::Semi {
                    None
                } else {
                    Some(self.parse_expr()?)
                };
                self.eat(&Tok::Semi)?;
                Ok(Stmt::Return(e))
            }
            Tok::If => {
                self.bump()?;
                let cond = self.parse_expr()?;
                let then_b = self.parse_block()?;
                let else_b = if self.cur == Tok::Else {
                    self.bump()?;
                    Some(self.parse_block()?)
                } else {
                    None
                };
                Ok(Stmt::If {
                    cond,
                    then_b,
                    else_b,
                })
            }
            Tok::While => {
                self.bump()?;
                let cond = self.parse_expr()?;
                let body = self.parse_block()?;
                Ok(Stmt::While { cond, body })
            }
            Tok::Ident(_) => {
                let name = self.expect_ident()?;
                // name[index] = value
                if self.cur == Tok::LBracket {
                    self.bump()?;
                    let index = self.parse_expr()?;
                    self.eat(&Tok::RBracket)?;
                    self.eat(&Tok::Assign)?;
                    let value = self.parse_expr()?;
                    self.eat(&Tok::Semi)?;
                    return Ok(Stmt::IndexAssign {
                        name,
                        index,
                        value,
                    });
                }
                if self.cur == Tok::Assign {
                    self.bump()?;
                    let value = self.parse_expr()?;
                    self.eat(&Tok::Semi)?;
                    return Ok(Stmt::Assign { name, value });
                }
                let expr = if self.cur == Tok::LParen {
                    self.bump()?;
                    let mut args = Vec::new();
                    if self.cur != Tok::RParen {
                        loop {
                            args.push(self.parse_expr()?);
                            if self.cur == Tok::Comma {
                                self.bump()?;
                                continue;
                            }
                            break;
                        }
                    }
                    self.eat(&Tok::RParen)?;
                    Expr::Call { name, args }
                } else if self.cur == Tok::LBracket {
                    // name[i] as expr stmt (unusual)
                    self.bump()?;
                    let index = self.parse_expr()?;
                    self.eat(&Tok::RBracket)?;
                    Expr::Index {
                        base: Box::new(Expr::Ident(name)),
                        index: Box::new(index),
                    }
                } else {
                    Expr::Ident(name)
                };
                let expr = self.finish_expr(expr)?;
                self.eat(&Tok::Semi)?;
                Ok(Stmt::Expr(expr))
            }
            _ => {
                let e = self.parse_expr()?;
                self.eat(&Tok::Semi)?;
                Ok(Stmt::Expr(e))
            }
        }
    }

    fn finish_expr(&mut self, left: Expr) -> Result<Expr, String> {
        // continue binary ops after primary already parsed
        self.parse_binop_rest(left, 0)
    }

    fn parse_expr(&mut self) -> Result<Expr, String> {
        self.parse_binop(0)
    }

    fn parse_binop(&mut self, min_prec: u8) -> Result<Expr, String> {
        let left = self.parse_unary()?;
        self.parse_binop_rest(left, min_prec)
    }

    fn parse_binop_rest(&mut self, mut left: Expr, min_prec: u8) -> Result<Expr, String> {
        loop {
            let Some((op, prec, right_assoc)) = self.bin_op_info() else {
                break;
            };
            if prec < min_prec {
                break;
            }
            self.bump()?;
            let next_min = if right_assoc { prec } else { prec + 1 };
            let right = self.parse_binop(next_min)?;
            left = Expr::Binary {
                op,
                left: Box::new(left),
                right: Box::new(right),
            };
        }
        Ok(left)
    }

    fn bin_op_info(&self) -> Option<(BinOp, u8, bool)> {
        match self.cur {
            Tok::OrOr => Some((BinOp::Or, 1, false)),
            Tok::AndAnd => Some((BinOp::And, 2, false)),
            Tok::Eq => Some((BinOp::Eq, 3, false)),
            Tok::Ne => Some((BinOp::Ne, 3, false)),
            Tok::Lt => Some((BinOp::Lt, 4, false)),
            Tok::Le => Some((BinOp::Le, 4, false)),
            Tok::Gt => Some((BinOp::Gt, 4, false)),
            Tok::Ge => Some((BinOp::Ge, 4, false)),
            Tok::Plus => Some((BinOp::Add, 5, false)),
            Tok::Minus => Some((BinOp::Sub, 5, false)),
            Tok::Star => Some((BinOp::Mul, 6, false)),
            Tok::Slash => Some((BinOp::Div, 6, false)),
            Tok::Percent => Some((BinOp::Rem, 6, false)),
            _ => None,
        }
    }

    fn parse_unary(&mut self) -> Result<Expr, String> {
        match &self.cur {
            Tok::Minus => {
                self.bump()?;
                let e = self.parse_unary()?;
                Ok(Expr::Unary {
                    op: UnOp::Neg,
                    expr: Box::new(e),
                })
            }
            Tok::Not => {
                self.bump()?;
                let e = self.parse_unary()?;
                Ok(Expr::Unary {
                    op: UnOp::Not,
                    expr: Box::new(e),
                })
            }
            _ => self.parse_primary(),
        }
    }

    fn parse_primary(&mut self) -> Result<Expr, String> {
        match &self.cur.clone() {
            Tok::Int(n) => {
                let n = *n;
                self.bump()?;
                Ok(Expr::Int(n))
            }
            Tok::Float(f) => {
                let f = *f;
                self.bump()?;
                Ok(Expr::Float(f))
            }
            Tok::True => {
                self.bump()?;
                Ok(Expr::Bool(true))
            }
            Tok::False => {
                self.bump()?;
                Ok(Expr::Bool(false))
            }
            Tok::Ident(name) => {
                let name = name.clone();
                self.bump()?;
                let mut expr = if self.cur == Tok::LParen {
                    self.bump()?;
                    let mut args = Vec::new();
                    if self.cur != Tok::RParen {
                        loop {
                            args.push(self.parse_expr()?);
                            if self.cur == Tok::Comma {
                                self.bump()?;
                                continue;
                            }
                            break;
                        }
                    }
                    self.eat(&Tok::RParen)?;
                    Expr::Call { name, args }
                } else {
                    Expr::Ident(name)
                };
                // postfix index: a[i]
                while self.cur == Tok::LBracket {
                    self.bump()?;
                    let index = self.parse_expr()?;
                    self.eat(&Tok::RBracket)?;
                    expr = Expr::Index {
                        base: Box::new(expr),
                        index: Box::new(index),
                    };
                }
                Ok(expr)
            }
            Tok::LParen => {
                self.bump()?;
                let e = self.parse_expr()?;
                self.eat(&Tok::RParen)?;
                Ok(e)
            }
            other => Err(format!(
                "line {}: expected expression, got {:?}",
                self.lx.line, other
            )),
        }
    }

    fn expect_ident(&mut self) -> Result<String, String> {
        match &self.cur {
            Tok::Ident(s) => {
                let s = s.clone();
                self.bump()?;
                Ok(s)
            }
            other => Err(format!(
                "line {}: expected identifier, got {:?}",
                self.lx.line, other
            )),
        }
    }
}

pub fn parse(src: &str) -> Result<Program, String> {
    let mut p = Parser::new(src)?;
    p.parse_program()
}
