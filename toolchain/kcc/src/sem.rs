//! Semantic checks for K0 (before codegen).
//!
//! Catches: unknown fn, wrong arity, undeclared locals, redefs,
//! index of non-array, `%` on floating types,
//! **type-unify** (let/assign/index/call/return), **return-path** coverage.

use crate::ast::*;
use std::collections::HashMap;

/// Function signature: (param types, return type).
type FnSig = (Vec<Type>, Type);

pub fn check(prog: &Program) -> Result<(), String> {
    let mut fns: HashMap<String, FnSig> = HashMap::new();
    for item in &prog.items {
        let Item::Fn(f) = item;
        if fns.contains_key(&f.name) {
            return Err(format!("redefinition of function `{}`", f.name));
        }
        if matches!(f.ret, Type::Array { .. }) {
            return Err(format!("function `{}` cannot return an array", f.name));
        }
        let params: Vec<Type> = f.params.iter().map(|(_, t)| t.clone()).collect();
        fns.insert(f.name.clone(), (params, f.ret.clone()));
    }

    for item in &prog.items {
        let Item::Fn(f) = item;
        check_fn(f, &fns)?;
    }
    Ok(())
}

fn check_fn(f: &FnDef, fns: &HashMap<String, FnSig>) -> Result<(), String> {
    let mut locals: HashMap<String, Type> = HashMap::new();
    for (n, t) in &f.params {
        if locals.contains_key(n) {
            return Err(format!("fn `{}`: duplicate param `{}`", f.name, n));
        }
        locals.insert(n.clone(), t.clone());
    }
    check_block(&f.body, &mut locals, fns, &f.name, &f.ret, 0)?;
    if !returns_on_all_paths(&f.body) {
        return Err(format!(
            "fn `{}`: not all control-flow paths return a value (return type `{}`)",
            f.name,
            type_name(&f.ret)
        ));
    }
    Ok(())
}

/// True if every execution path through `b` ends in `return` (or if/else both return).
fn returns_on_all_paths(b: &Block) -> bool {
    for st in &b.stmts {
        match st {
            Stmt::Return(_) => return true,
            Stmt::If {
                then_b,
                else_b,
                ..
            } => {
                let t_ok = returns_on_all_paths(then_b);
                let e_ok = else_b
                    .as_ref()
                    .map(returns_on_all_paths)
                    .unwrap_or(false);
                if t_ok && e_ok {
                    return true;
                }
            }
            _ => {}
        }
    }
    false
}

/// Assignment / argument / return compatibility (not full C promotion).
fn types_compatible(expected: &Type, got: &Type) -> bool {
    if expected == got {
        return true;
    }
    match (expected, got) {
        // integer family
        (Type::I32, Type::I64) | (Type::I64, Type::I32) => true,
        (Type::I32, Type::I32) | (Type::I64, Type::I64) => true,
        // int → float (literals often typed as i64)
        (Type::F64, Type::I32) | (Type::F64, Type::I64) => true,
        // arrays: exact only (pointer decay handled at call site by same elem+len)
        (Type::Array { elem: e1, len: n1 }, Type::Array { elem: e2, len: n2 }) => {
            n1 == n2 && types_compatible(e1, e2)
        }
        _ => false,
    }
}

fn type_name(t: &Type) -> String {
    match t {
        Type::I32 => "i32".into(),
        Type::I64 => "i64".into(),
        Type::F64 => "f64".into(),
        Type::Bool => "bool".into(),
        Type::Array { elem, len } => format!("[{}; {}]", type_name(elem), len),
    }
}

fn expect_type(
    expected: &Type,
    got: &Type,
    fn_name: &str,
    what: &str,
) -> Result<(), String> {
    if types_compatible(expected, got) {
        Ok(())
    } else {
        Err(format!(
            "fn `{fn_name}`: {what}: expected `{}`, got `{}`",
            type_name(expected),
            type_name(got)
        ))
    }
}

fn check_block(
    b: &Block,
    locals: &mut HashMap<String, Type>,
    fns: &HashMap<String, FnSig>,
    fn_name: &str,
    ret_ty: &Type,
    loop_depth: u32,
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
                    let got = expr_type(e, locals, fns)?;
                    expect_type(
                        &t,
                        &got,
                        fn_name,
                        &format!("let `{name}` initializer"),
                    )?;
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
                let Some(dst) = locals.get(name).cloned() else {
                    return Err(format!(
                        "fn `{fn_name}`: assign to undeclared `{name}`"
                    ));
                };
                check_expr(value, locals, fns, fn_name)?;
                let got = expr_type(value, locals, fns)?;
                expect_type(
                    &dst,
                    &got,
                    fn_name,
                    &format!("assign to `{name}`"),
                )?;
            }
            Stmt::IndexAssign { name, index, value } => {
                let Some(t) = locals.get(name).cloned() else {
                    return Err(format!(
                        "fn `{fn_name}`: index-assign undeclared `{name}`"
                    ));
                };
                let Type::Array { elem, .. } = t else {
                    return Err(format!(
                        "fn `{fn_name}`: `{name}` is not an array"
                    ));
                };
                check_expr(index, locals, fns, fn_name)?;
                let idx_t = expr_type(index, locals, fns)?;
                if !matches!(idx_t, Type::I32 | Type::I64) {
                    return Err(format!(
                        "fn `{fn_name}`: array index must be integer, got `{}`",
                        type_name(&idx_t)
                    ));
                }
                check_expr(value, locals, fns, fn_name)?;
                let got = expr_type(value, locals, fns)?;
                expect_type(
                    &elem,
                    &got,
                    fn_name,
                    &format!("index-assign `{name}[…]`"),
                )?;
            }
            Stmt::Return(e) => match e {
                Some(ex) => {
                    check_expr(ex, locals, fns, fn_name)?;
                    let got = expr_type(ex, locals, fns)?;
                    expect_type(ret_ty, &got, fn_name, "return value")?;
                }
                None => {
                    return Err(format!(
                        "fn `{fn_name}`: bare `return` not allowed (expected `{}`)",
                        type_name(ret_ty)
                    ));
                }
            },
            Stmt::Expr(e) => check_expr(e, locals, fns, fn_name)?,
            Stmt::If {
                cond,
                then_b,
                else_b,
            } => {
                check_expr(cond, locals, fns, fn_name)?;
                let ct = expr_type(cond, locals, fns)?;
                // allow bool or numeric (C truthiness of ints / comparisons already bool)
                if !matches!(ct, Type::Bool | Type::I32 | Type::I64 | Type::F64) {
                    return Err(format!(
                        "fn `{fn_name}`: if condition has type `{}`",
                        type_name(&ct)
                    ));
                }
                check_block(then_b, locals, fns, fn_name, ret_ty, loop_depth)?;
                if let Some(eb) = else_b {
                    check_block(eb, locals, fns, fn_name, ret_ty, loop_depth)?;
                }
            }
            Stmt::While { cond, body } => {
                check_expr(cond, locals, fns, fn_name)?;
                let ct = expr_type(cond, locals, fns)?;
                if !matches!(ct, Type::Bool | Type::I32 | Type::I64 | Type::F64) {
                    return Err(format!(
                        "fn `{fn_name}`: while condition has type `{}`",
                        type_name(&ct)
                    ));
                }
                check_block(body, locals, fns, fn_name, ret_ty, loop_depth + 1)?;
            }
            Stmt::For {
                init,
                cond,
                step,
                body,
            } => {
                if let Some(ini) = init {
                    // reuse match arms by wrapping as single-stmt block
                    check_block(
                        &Block {
                            stmts: vec![(**ini).clone()],
                        },
                        locals,
                        fns,
                        fn_name,
                        ret_ty,
                        loop_depth,
                    )?;
                }
                if let Some(c) = cond {
                    check_expr(c, locals, fns, fn_name)?;
                    let ct = expr_type(c, locals, fns)?;
                    if !matches!(ct, Type::Bool | Type::I32 | Type::I64 | Type::F64) {
                        return Err(format!(
                            "fn `{fn_name}`: for condition has type `{}`",
                            type_name(&ct)
                        ));
                    }
                }
                check_block(body, locals, fns, fn_name, ret_ty, loop_depth + 1)?;
                if let Some(st) = step {
                    check_block(
                        &Block {
                            stmts: vec![(**st).clone()],
                        },
                        locals,
                        fns,
                        fn_name,
                        ret_ty,
                        loop_depth + 1,
                    )?;
                }
            }
            Stmt::Break => {
                if loop_depth == 0 {
                    return Err(format!(
                        "fn `{fn_name}`: `break` outside of loop"
                    ));
                }
            }
            Stmt::Continue => {
                if loop_depth == 0 {
                    return Err(format!(
                        "fn `{fn_name}`: `continue` outside of loop"
                    ));
                }
            }
        }
    }

    // pop block-local names (params stay) — MVP function-scoped like C
    for n in declared_here {
        if !snapshot.contains(&n) {
            let _ = n;
        }
    }
    Ok(())
}

fn check_expr(
    e: &Expr,
    locals: &HashMap<String, Type>,
    fns: &HashMap<String, FnSig>,
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
                    let idx_t = expr_type(index, locals, fns)?;
                    if !matches!(idx_t, Type::I32 | Type::I64) {
                        return Err(format!(
                            "fn `{fn_name}`: array index must be integer, got `{}`",
                            type_name(&idx_t)
                        ));
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
        Expr::Unary { op, expr } => {
            check_expr(expr, locals, fns, fn_name)?;
            let t = expr_type(expr, locals, fns)?;
            match op {
                UnOp::Not => {
                    if !matches!(t, Type::Bool | Type::I32 | Type::I64) {
                        return Err(format!(
                            "fn `{fn_name}`: `!` needs bool/int, got `{}`",
                            type_name(&t)
                        ));
                    }
                }
                UnOp::Neg => {
                    if !matches!(t, Type::I32 | Type::I64 | Type::F64) {
                        return Err(format!(
                            "fn `{fn_name}`: unary `-` needs numeric, got `{}`",
                            type_name(&t)
                        ));
                    }
                }
            }
            Ok(())
        }
        Expr::Binary { op, left, right } => {
            check_expr(left, locals, fns, fn_name)?;
            check_expr(right, locals, fns, fn_name)?;
            let lt = expr_type(left, locals, fns)?;
            let rt = expr_type(right, locals, fns)?;
            match op {
                BinOp::And | BinOp::Or => {
                    if !matches!(lt, Type::Bool | Type::I32 | Type::I64)
                        || !matches!(rt, Type::Bool | Type::I32 | Type::I64)
                    {
                        return Err(format!(
                            "fn `{fn_name}`: `&&`/`||` need bool/int operands"
                        ));
                    }
                }
                BinOp::Rem => {
                    if matches!(lt, Type::F64) || matches!(rt, Type::F64) {
                        return Err(format!(
                            "fn `{fn_name}`: `%` not allowed on f64 (C has no float remainder)"
                        ));
                    }
                    if !matches!(lt, Type::I32 | Type::I64)
                        || !matches!(rt, Type::I32 | Type::I64)
                    {
                        return Err(format!(
                            "fn `{fn_name}`: `%` needs integer operands"
                        ));
                    }
                }
                BinOp::Add | BinOp::Sub | BinOp::Mul | BinOp::Div => {
                    if matches!(lt, Type::Bool)
                        || matches!(rt, Type::Bool)
                        || matches!(lt, Type::Array { .. })
                        || matches!(rt, Type::Array { .. })
                    {
                        return Err(format!(
                            "fn `{fn_name}`: arithmetic on non-numeric type"
                        ));
                    }
                }
                BinOp::Eq | BinOp::Ne | BinOp::Lt | BinOp::Le | BinOp::Gt | BinOp::Ge => {
                    // allow same family (int/float/bool)
                    let ok = types_compatible(&lt, &rt)
                        || types_compatible(&rt, &lt)
                        || (matches!(lt, Type::I32 | Type::I64 | Type::F64)
                            && matches!(rt, Type::I32 | Type::I64 | Type::F64));
                    if !ok {
                        return Err(format!(
                            "fn `{fn_name}`: compare `{}` vs `{}`",
                            type_name(&lt),
                            type_name(&rt)
                        ));
                    }
                }
            }
            Ok(())
        }
        Expr::Call { name, args } => {
            let Some((params, _)) = fns.get(name) else {
                return Err(format!("fn `{fn_name}`: unknown function `{name}`"));
            };
            if args.len() != params.len() {
                return Err(format!(
                    "fn `{fn_name}`: `{name}` expects {} args, got {}",
                    params.len(),
                    args.len()
                ));
            }
            for (i, a) in args.iter().enumerate() {
                check_expr(a, locals, fns, fn_name)?;
                let got = expr_type(a, locals, fns)?;
                expect_type(
                    &params[i],
                    &got,
                    fn_name,
                    &format!("arg {} of `{name}`", i + 1),
                )?;
            }
            Ok(())
        }
    }
}

fn expr_type(
    e: &Expr,
    locals: &HashMap<String, Type>,
    fns: &HashMap<String, FnSig>,
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

    #[test]
    fn rejects_type_mismatch_assign() {
        let p = parse(
            r#"
fn main() -> i32 {
    let x: bool = true;
    x = 1;
    return 0;
}
"#,
        )
        .unwrap();
        let e = check(&p).unwrap_err();
        assert!(e.contains("expected") || e.contains("assign"), "{e}");
    }

    #[test]
    fn rejects_bad_call_arg_type() {
        let p = parse(
            r#"
fn needs_bool(b: bool) -> i32 { return 0; }
fn main() -> i32 { return needs_bool(1.5); }
"#,
        )
        .unwrap();
        let e = check(&p).unwrap_err();
        assert!(e.contains("arg") || e.contains("expected"), "{e}");
    }

    #[test]
    fn rejects_missing_return_path() {
        let p = parse(
            r#"
fn f(x: i32) -> i32 {
    if x > 0 {
        return 1;
    }
}
fn main() -> i32 { return f(1); }
"#,
        )
        .unwrap();
        let e = check(&p).unwrap_err();
        assert!(e.contains("not all control-flow paths return"), "{e}");
    }

    #[test]
    fn accepts_if_else_both_return() {
        let p = parse(
            r#"
fn f(x: i32) -> i32 {
    if x > 0 {
        return 1;
    } else {
        return 0;
    }
}
fn main() -> i32 { return f(1); }
"#,
        )
        .unwrap();
        check(&p).expect("ok");
    }

    #[test]
    fn rejects_wrong_return_type() {
        let p = parse(
            r#"
fn f() -> i32 {
    return true;
}
fn main() -> i32 { return f(); }
"#,
        )
        .unwrap();
        let e = check(&p).unwrap_err();
        assert!(e.contains("return value") || e.contains("expected"), "{e}");
    }

    #[test]
    fn allows_int_to_f64_let() {
        let p = parse(
            r#"
fn main() -> i32 {
    let x: f64 = 3;
    return 0;
}
"#,
        )
        .unwrap();
        check(&p).expect("int→f64 ok");
    }
}
