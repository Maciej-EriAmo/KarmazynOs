//! Semantic checks for K0 (before codegen).
//!
//! Catches: unknown fn, wrong arity, undeclared locals, redefs,
//! index of non-array, `%` on floating types.

use crate::ast::*;
use std::collections::HashMap;

pub fn check(prog: &Program) -> Result<(), String> {
    let mut fns: HashMap<String, (usize, Type)> = HashMap::new();
    for item in &prog.items {
        let Item::Fn(f) = item;
        if fns.contains_key(&f.name) {
            return Err(format!("redefinition of function `{}`", f.name));
        }
        if matches!(f.ret, Type::Array { .. }) {
            return Err(format!("function `{}` cannot return an array", f.name));
        }
        fns.insert(f.name.clone(), (f.params.len(), f.ret.clone()));
    }

    for item in &prog.items {
        let Item::Fn(f) = item;
        check_fn(f, &fns)?;
    }
    Ok(())
}

fn check_fn(f: &FnDef, fns: &HashMap<String, (usize, Type)>) -> Result<(), String> {
    let mut locals: HashMap<String, Type> = HashMap::new();
    for (n, t) in &f.params {
        if locals.contains_key(n) {
            return Err(format!("fn `{}`: duplicate param `{}`", f.name, n));
        }
        locals.insert(n.clone(), t.clone());
    }
    check_block(&f.body, &mut locals, fns, &f.name)?;
    Ok(())
}

fn check_block(
    b: &Block,
    locals: &mut HashMap<String, Type>,
    fns: &HashMap<String, (usize, Type)>,
    fn_name: &str,
) -> Result<(), String> {
    // block-scoped: snapshot keys, restore after (simple shadowing ban for MVP)
    let snapshot: Vec<String> = locals.keys().cloned().collect();
    let mut declared_here: Vec<String> = Vec::new();

    for st in &b.stmts {
        match st {
            Stmt::Let { name, ty, init } => {
                if locals.contains_key(name) {
                    return Err(format!(
                        "fn `{fn_name}`: redeclaration of `{name}`"
                    ));
                }
                let t = match ty {
                    Some(t) => t.clone(),
                    None => {
                        let e = init.as_ref().ok_or_else(|| {
                            format!("fn `{fn_name}`: let `{name}` needs type or init")
                        })?;
                        expr_type(e, locals, fns)?
                    }
                };
                if let Some(e) = init {
                    check_expr(e, locals, fns, fn_name)?;
                    // soft: allow assign-compat later
                    let _ = expr_type(e, locals, fns)?;
                }
                if matches!(t, Type::Array { .. }) && init.is_some() {
                    return Err(format!(
                        "fn `{fn_name}`: array `{name}` must use zero-init (no initializer)"
                    ));
                }
                locals.insert(name.clone(), t);
                declared_here.push(name.clone());
            }
            Stmt::Assign { name, value } => {
                if !locals.contains_key(name) {
                    return Err(format!(
                        "fn `{fn_name}`: assign to undeclared `{name}`"
                    ));
                }
                check_expr(value, locals, fns, fn_name)?;
            }
            Stmt::IndexAssign { name, index, value } => {
                let Some(t) = locals.get(name) else {
                    return Err(format!(
                        "fn `{fn_name}`: index-assign undeclared `{name}`"
                    ));
                };
                if !matches!(t, Type::Array { .. }) {
                    return Err(format!(
                        "fn `{fn_name}`: `{name}` is not an array"
                    ));
                }
                check_expr(index, locals, fns, fn_name)?;
                check_expr(value, locals, fns, fn_name)?;
            }
            Stmt::Return(e) => {
                if let Some(ex) = e {
                    check_expr(ex, locals, fns, fn_name)?;
                }
            }
            Stmt::Expr(e) => check_expr(e, locals, fns, fn_name)?,
            Stmt::If {
                cond,
                then_b,
                else_b,
            } => {
                check_expr(cond, locals, fns, fn_name)?;
                check_block(then_b, locals, fns, fn_name)?;
                if let Some(eb) = else_b {
                    check_block(eb, locals, fns, fn_name)?;
                }
            }
            Stmt::While { cond, body } => {
                check_expr(cond, locals, fns, fn_name)?;
                check_block(body, locals, fns, fn_name)?;
            }
        }
    }

    // pop block-local names (params stay)
    for n in declared_here {
        if !snapshot.contains(&n) {
            // only remove if introduced in this block — but nested blocks share map
            // and may re-add; simple MVP: keep all (function-scoped like C)
            let _ = n;
        }
    }
    Ok(())
}

fn check_expr(
    e: &Expr,
    locals: &HashMap<String, Type>,
    fns: &HashMap<String, (usize, Type)>,
    fn_name: &str,
) -> Result<(), String> {
    match e {
        Expr::Int(_) | Expr::Float(_) | Expr::Bool(_) => Ok(()),
        Expr::Ident(n) => {
            if locals.contains_key(n) {
                Ok(())
            } else {
                Err(format!("fn `{fn_name}`: undeclared `{n}`"))
            }
        }
        Expr::Index { base, index } => {
            check_expr(base, locals, fns, fn_name)?;
            check_expr(index, locals, fns, fn_name)?;
            match base.as_ref() {
                Expr::Ident(n) => {
                    let Some(t) = locals.get(n) else {
                        return Err(format!("fn `{fn_name}`: undeclared `{n}`"));
                    };
                    if !matches!(t, Type::Array { .. }) {
                        return Err(format!("fn `{fn_name}`: `{n}` is not an array"));
                    }
                }
                _ => {
                    return Err(format!(
                        "fn `{fn_name}`: index base must be an identifier"
                    ));
                }
            }
            Ok(())
        }
        Expr::Unary { expr, .. } => check_expr(expr, locals, fns, fn_name),
        Expr::Binary { op, left, right } => {
            check_expr(left, locals, fns, fn_name)?;
            check_expr(right, locals, fns, fn_name)?;
            if *op == BinOp::Rem {
                let lt = expr_type(left, locals, fns)?;
                let rt = expr_type(right, locals, fns)?;
                if matches!(lt, Type::F64) || matches!(rt, Type::F64) {
                    return Err(format!(
                        "fn `{fn_name}`: `%` not allowed on f64 (C has no float remainder)"
                    ));
                }
            }
            Ok(())
        }
        Expr::Call { name, args } => {
            let Some((arity, _)) = fns.get(name) else {
                return Err(format!("fn `{fn_name}`: unknown function `{name}`"));
            };
            if args.len() != *arity {
                return Err(format!(
                    "fn `{fn_name}`: `{name}` expects {arity} args, got {}",
                    args.len()
                ));
            }
            for a in args {
                check_expr(a, locals, fns, fn_name)?;
            }
            Ok(())
        }
    }
}

fn expr_type(
    e: &Expr,
    locals: &HashMap<String, Type>,
    fns: &HashMap<String, (usize, Type)>,
) -> Result<Type, String> {
    Ok(match e {
        Expr::Int(_) => Type::I64,
        Expr::Float(_) => Type::F64,
        Expr::Bool(_) => Type::Bool,
        Expr::Ident(n) => locals
            .get(n)
            .cloned()
            .ok_or_else(|| format!("undeclared `{n}`"))?,
        Expr::Index { base, .. } => match base.as_ref() {
            Expr::Ident(n) => match locals.get(n) {
                Some(Type::Array { elem, .. }) => *elem.clone(),
                Some(_) => return Err(format!("`{n}` is not an array")),
                None => return Err(format!("undeclared `{n}`")),
            },
            _ => Type::I64,
        },
        Expr::Unary { op: UnOp::Not, .. } => Type::Bool,
        Expr::Unary { expr, .. } => expr_type(expr, locals, fns)?,
        Expr::Binary { op, left, right } => match op {
            BinOp::Eq | BinOp::Ne | BinOp::Lt | BinOp::Le | BinOp::Gt | BinOp::Ge | BinOp::And
            | BinOp::Or => Type::Bool,
            _ => {
                let l = expr_type(left, locals, fns)?;
                let r = expr_type(right, locals, fns)?;
                if matches!(l, Type::F64) || matches!(r, Type::F64) {
                    Type::F64
                } else if matches!(l, Type::I64) || matches!(r, Type::I64) {
                    Type::I64
                } else {
                    Type::I32
                }
            }
        },
        Expr::Call { name, .. } => fns
            .get(name)
            .map(|(_, t)| t.clone())
            .ok_or_else(|| format!("unknown function `{name}`"))?,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parse::parse;

    #[test]
    fn rejects_undeclared() {
        let p = parse("fn main() -> i32 { return x; }").unwrap();
        assert!(check(&p).unwrap_err().contains("undeclared"));
    }

    #[test]
    fn rejects_unknown_fn() {
        let p = parse("fn main() -> i32 { return foo(1); }").unwrap();
        assert!(check(&p).unwrap_err().contains("unknown function"));
    }

    #[test]
    fn rejects_bad_arity() {
        let p = parse(
            "fn add(a: i64, b: i64) -> i64 { return a + b; }\nfn main() -> i32 { return add(1); }\n",
        )
        .unwrap();
        assert!(check(&p).unwrap_err().contains("expects 2"));
    }

    #[test]
    fn rejects_float_rem() {
        let p = parse("fn main() -> i32 { let x: f64 = 3.0 % 2.0; return 0; }").unwrap();
        assert!(check(&p).unwrap_err().contains("%"));
    }

    #[test]
    fn accepts_thermal_snippet() {
        let p = parse(
            r#"
fn state_code(t: f64) -> i32 {
    if t >= 70.0 { return 3; }
    return 0;
}
fn main() -> i32 { return state_code(80.0); }
"#,
        )
        .unwrap();
        check(&p).expect("ok");
    }
}
