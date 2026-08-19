//! Mini-Lisp guest. Same seams as `karmazyn_exec.py`:
//!   eval_line(str) -> str
//!   env = Bubble (root)
//!   vars = atoms; value on the atom (token + payload blob)
//!   env_of(closure_token) -> captured bubble  (P6)
//!   call frame = temporary root
//!
//! Closures live **on the atom** (payload), not a side heap. Vacuum and
//! snapshot take them with the atom — Python `metadata["v"]` maturity.

use karmazyn_substrate::{BubbleId, Store, T_INIT};
use std::cell::Cell;

const TAG: u64 = 3;
const TAG_IMM: u64 = 0;
const TAG_INT: u64 = 1;
const TAG_CLOS: u64 = 2;
const TAG_FLOAT: u64 = 3;

const IMM_NIL: u64 = 0;
const IMM_FALSE: u64 = 4;
const IMM_TRUE: u64 = 8;
const IMM_BUILTIN_BASE: u64 = 16;

#[derive(Clone, Debug)]
pub enum Expr {
    Int(i64),
    Float(f64),
    Bool(bool),
    Symbol(String),
    List(Vec<Expr>),
}

#[derive(Clone, Debug)]
pub enum Value {
    Nil,
    Bool(bool),
    Int(i64),
    Float(f64),
    Builtin(&'static str),
    Closure {
        params: Vec<String>,
        body: Expr,
        env: BubbleId,
    },
}

fn pack(v: &Value) -> (u64, Option<Vec<u8>>) {
    match v {
        Value::Nil => (IMM_NIL, None),
        Value::Bool(false) => (IMM_FALSE, None),
        Value::Bool(true) => (IMM_TRUE, None),
        Value::Int(n) => (((*n as u64) << 2) | TAG_INT, None),
        Value::Builtin(name) => {
            let id = builtin_id(name).unwrap_or(0);
            (IMM_BUILTIN_BASE + (id << 2), None)
        }
        Value::Float(n) => (TAG_FLOAT, Some(n.to_le_bytes().to_vec())),
        Value::Closure { params, body, env } => {
            (((*env as u64) << 2) | TAG_CLOS, Some(encode_closure(params, body, *env)))
        }
    }
}

fn unpack(tok: u64, payload: Option<&[u8]>) -> Option<Value> {
    match tok & TAG {
        TAG_INT => Some(Value::Int((tok as i64) >> 2)),
        TAG_CLOS => decode_closure(payload?),
        TAG_FLOAT => {
            let b = payload?;
            if b.len() != 8 {
                return None;
            }
            let mut a = [0u8; 8];
            a.copy_from_slice(b);
            Some(Value::Float(f64::from_le_bytes(a)))
        }
        TAG_IMM => match tok {
            IMM_NIL => Some(Value::Nil),
            IMM_FALSE => Some(Value::Bool(false)),
            IMM_TRUE => Some(Value::Bool(true)),
            t if t >= IMM_BUILTIN_BASE => {
                let id = (t - IMM_BUILTIN_BASE) >> 2;
                Some(Value::Builtin(builtin_name(id)?))
            }
            _ => None,
        },
        _ => None,
    }
}

fn env_of_token(tok: u64) -> Option<BubbleId> {
    if tok & TAG == TAG_CLOS {
        Some((tok >> 2) as BubbleId)
    } else {
        None
    }
}

const E_INT: u8 = 0;
const E_FLOAT: u8 = 1;
const E_TRUE: u8 = 2;
const E_FALSE: u8 = 3;
const E_SYM: u8 = 4;
const E_LIST: u8 = 5;

fn encode_closure(params: &[String], body: &Expr, env: BubbleId) -> Vec<u8> {
    let mut b = Vec::new();
    b.extend_from_slice(&(env).to_le_bytes());
    b.extend_from_slice(&(params.len() as u16).to_le_bytes());
    for p in params {
        let raw = p.as_bytes();
        b.extend_from_slice(&(raw.len() as u16).to_le_bytes());
        b.extend_from_slice(raw);
    }
    write_expr(&mut b, body);
    b
}

fn decode_closure(blob: &[u8]) -> Option<Value> {
    let mut i = 0;
    let env = read_u32(blob, &mut i)?;
    let n = read_u16(blob, &mut i)? as usize;
    let mut params = Vec::with_capacity(n);
    for _ in 0..n {
        params.push(read_str(blob, &mut i)?);
    }
    let body = read_expr(blob, &mut i)?;
    Some(Value::Closure {
        params,
        body,
        env,
    })
}

fn write_expr(b: &mut Vec<u8>, e: &Expr) {
    match e {
        Expr::Int(n) => {
            b.push(E_INT);
            b.extend_from_slice(&n.to_le_bytes());
        }
        Expr::Float(n) => {
            b.push(E_FLOAT);
            b.extend_from_slice(&n.to_le_bytes());
        }
        Expr::Bool(true) => b.push(E_TRUE),
        Expr::Bool(false) => b.push(E_FALSE),
        Expr::Symbol(s) => {
            b.push(E_SYM);
            let raw = s.as_bytes();
            b.extend_from_slice(&(raw.len() as u16).to_le_bytes());
            b.extend_from_slice(raw);
        }
        Expr::List(xs) => {
            b.push(E_LIST);
            b.extend_from_slice(&(xs.len() as u16).to_le_bytes());
            for x in xs {
                write_expr(b, x);
            }
        }
    }
}

fn read_expr(blob: &[u8], i: &mut usize) -> Option<Expr> {
    let tag = read_u8(blob, i)?;
    match tag {
        E_INT => Some(Expr::Int(read_i64(blob, i)?)),
        E_FLOAT => {
            let mut a = [0u8; 8];
            a.copy_from_slice(read_slice(blob, i, 8)?);
            Some(Expr::Float(f64::from_le_bytes(a)))
        }
        E_TRUE => Some(Expr::Bool(true)),
        E_FALSE => Some(Expr::Bool(false)),
        E_SYM => Some(Expr::Symbol(read_str(blob, i)?)),
        E_LIST => {
            let n = read_u16(blob, i)? as usize;
            let mut xs = Vec::with_capacity(n);
            for _ in 0..n {
                xs.push(read_expr(blob, i)?);
            }
            Some(Expr::List(xs))
        }
        _ => None,
    }
}

fn read_u8(b: &[u8], i: &mut usize) -> Option<u8> {
    let x = *b.get(*i)?;
    *i += 1;
    Some(x)
}

fn read_u16(b: &[u8], i: &mut usize) -> Option<u16> {
    let s = read_slice(b, i, 2)?;
    Some(u16::from_le_bytes([s[0], s[1]]))
}

fn read_u32(b: &[u8], i: &mut usize) -> Option<u32> {
    let s = read_slice(b, i, 4)?;
    Some(u32::from_le_bytes([s[0], s[1], s[2], s[3]]))
}

fn read_i64(b: &[u8], i: &mut usize) -> Option<i64> {
    let s = read_slice(b, i, 8)?;
    let mut a = [0u8; 8];
    a.copy_from_slice(s);
    Some(i64::from_le_bytes(a))
}

fn read_slice<'a>(b: &'a [u8], i: &mut usize, n: usize) -> Option<&'a [u8]> {
    let end = i.checked_add(n)?;
    let s = b.get(*i..end)?;
    *i = end;
    Some(s)
}

fn read_str(b: &[u8], i: &mut usize) -> Option<String> {
    let n = read_u16(b, i)? as usize;
    let s = read_slice(b, i, n)?;
    String::from_utf8(s.to_vec()).ok()
}

fn builtin_id(name: &str) -> Option<u64> {
    Some(match name {
        "+" => 0,
        "-" => 1,
        "*" => 2,
        "/" => 3,
        "=" => 4,
        "<" => 5,
        ">" => 6,
        "<=" => 7,
        ">=" => 8,
        "not" => 9,
        "print" => 10,
        _ => return None,
    })
}

fn builtin_name(id: u64) -> Option<&'static str> {
    Some(match id {
        0 => "+",
        1 => "-",
        2 => "*",
        3 => "/",
        4 => "=",
        5 => "<",
        6 => ">",
        7 => "<=",
        8 => ">=",
        9 => "not",
        10 => "print",
        _ => return None,
    })
}

/// Same mount object boot expects: `eval_line` + `env`.
pub struct Evaluator {
    env: Cell<BubbleId>,
}

impl Evaluator {
    pub fn env(&self) -> BubbleId {
        self.env.get()
    }
}

impl Evaluator {
    pub fn new(store: &Store) -> Self {
        Self::mount(store, "repl")
    }

    pub fn mount(store: &Store, env_label: &str) -> Self {
        let env = store.bubble_new(env_label, None);
        Self::attach(store, env)
    }

    /// Re-bind guest hooks to an existing env bubble (after snapshot load).
    pub fn attach(store: &Store, env: BubbleId) -> Self {
        store.set_root(env);
        store.register_env_of("guest", env_of_token);
        store.unregister_extra_reach("guest");
        Self { env: Cell::new(env) }
    }

    pub fn attach_repl(store: &Store) -> Self {
        let found = store.bubble_ids().into_iter().find(|id| {
            store.bubble_label(*id).as_deref() == Some("repl")
        });
        match found {
            Some(id) => Self::attach(store, id),
            None => Self::new(store),
        }
    }

    pub fn remount_repl(&self, store: &Store) {
        let ev = Self::attach_repl(store);
        self.env.set(ev.env());
    }

    /// Public seam: never panics; errors as `blad: …` (Python contract).
    pub fn eval_line(&self, store: &Store, line: &str) -> String {
        let line = line.split_once(';').map(|(a, _)| a).unwrap_or(line).trim();
        if line.is_empty() {
            return String::new();
        }
        match parse(line).and_then(|e| self.eval(store, &e, self.env())) {
            Ok(v) => fmt(&v),
            Err(e) => format!("blad: {e}"),
        }
    }

    fn eval(&self, store: &Store, x: &Expr, env: BubbleId) -> Result<Value, String> {
        match x {
            Expr::Int(n) => Ok(Value::Int(*n)),
            Expr::Float(n) => Ok(Value::Float(*n)),
            Expr::Bool(b) => Ok(Value::Bool(*b)),
            Expr::Symbol(name) => self.lookup(store, env, name),
            Expr::List(items) if items.is_empty() => Err("nie umiem wykonac: ()".into()),
            Expr::List(items) => self.eval_list(store, items, env),
        }
    }

    fn lookup(&self, store: &Store, env: BubbleId, name: &str) -> Result<Value, String> {
        if let Some(aid) = store.lookup(env, name) {
            if let Some(tok) = store.atom_value_token(aid) {
                let pay = store.atom_payload(aid);
                if let Some(v) = unpack(tok, pay.as_deref()) {
                    return Ok(v);
                }
            }
        }
        if let Some(id) = builtin_id(name) {
            if let Some(bn) = builtin_name(id) {
                return Ok(Value::Builtin(bn));
            }
        }
        Err(format!("NameError: '{name}' nieznane"))
    }

    fn bind_val(
        &self,
        store: &Store,
        env: BubbleId,
        name: &str,
        val: &Value,
        s: &str,
    ) -> Result<(), String> {
        let (tok, blob) = pack(val);
        let aid = store.atom_new(s, name, T_INIT);
        store.atom_set_guest(aid, tok, blob);
        store.bind(env, name, aid).map_err(|e| e.to_string())
    }

    fn eval_list(&self, store: &Store, items: &[Expr], env: BubbleId) -> Result<Value, String> {
        let Expr::Symbol(head) = &items[0] else {
            return self.apply_head(store, &items[0], &items[1..], env);
        };
        match head.as_str() {
            "define" => {
                if items.len() != 3 {
                    return Err("SyntaxError: uzycie: (define nazwa wyrazenie)".into());
                }
                let Expr::Symbol(name) = &items[1] else {
                    return Err("SyntaxError: uzycie: (define nazwa wyrazenie)".into());
                };
                let val = self.eval(store, &items[2], env)?;
                self.bind_val(store, env, name, &val, "var")?;
                Ok(val)
            }
            "set!" => {
                if items.len() != 3 {
                    return Err("SyntaxError: uzycie: (set! nazwa wyrazenie)".into());
                }
                let Expr::Symbol(name) = &items[1] else {
                    return Err("SyntaxError: uzycie: (set! nazwa wyrazenie)".into());
                };
                let aid = store
                    .lookup(env, name)
                    .ok_or_else(|| format!("NameError: set!: '{name}' nie istnieje"))?;
                let val = self.eval(store, &items[2], env)?;
                let (tok, blob) = pack(&val);
                store.atom_set_guest(aid, tok, blob);
                Ok(val)
            }
            "if" => {
                if items.len() != 3 && items.len() != 4 {
                    return Err("SyntaxError: uzycie: (if warunek to [else])".into());
                }
                if truthy(&self.eval(store, &items[1], env)?) {
                    self.eval(store, &items[2], env)
                } else if items.len() == 4 {
                    self.eval(store, &items[3], env)
                } else {
                    Ok(Value::Nil)
                }
            }
            "begin" => {
                let mut last = Value::Nil;
                for sub in &items[1..] {
                    last = self.eval(store, sub, env)?;
                }
                Ok(last)
            }
            "lambda" => {
                if items.len() != 3 {
                    return Err("SyntaxError: uzycie: (lambda (params...) cialo)".into());
                }
                let Expr::List(ps) = &items[1] else {
                    return Err("SyntaxError: uzycie: (lambda (params...) cialo)".into());
                };
                let mut params = Vec::new();
                for p in ps {
                    let Expr::Symbol(s) = p else {
                        return Err("SyntaxError: parametry lambda musza byc symbolami".into());
                    };
                    params.push(s.clone());
                }
                Ok(Value::Closure {
                    params,
                    body: items[2].clone(),
                    env,
                })
            }
            "and" => {
                let mut last = Value::Bool(true);
                for sub in &items[1..] {
                    last = self.eval(store, sub, env)?;
                    if !truthy(&last) {
                        return Ok(last);
                    }
                }
                Ok(last)
            }
            "or" => {
                let mut last = Value::Bool(false);
                for sub in &items[1..] {
                    last = self.eval(store, sub, env)?;
                    if truthy(&last) {
                        return Ok(last);
                    }
                }
                Ok(last)
            }
            _ => self.apply_head(store, &items[0], &items[1..], env),
        }
    }

    fn apply_head(
        &self,
        store: &Store,
        head: &Expr,
        args_e: &[Expr],
        env: BubbleId,
    ) -> Result<Value, String> {
        let fnv = self.eval(store, head, env)?;
        let mut args = Vec::new();
        for a in args_e {
            args.push(self.eval(store, a, env)?);
        }
        match fnv {
            Value::Closure {
                params,
                body,
                env: cenv,
            } => self.apply_closure(store, &params, &body, cenv, &args),
            Value::Builtin(name) => apply_builtin(name, &args),
            _ => Err(format!(
                "SyntaxError: nie da sie wywolac: {}",
                expr_repr(head)
            )),
        }
    }

    fn apply_closure(
        &self,
        store: &Store,
        params: &[String],
        body: &Expr,
        cenv: BubbleId,
        args: &[Value],
    ) -> Result<Value, String> {
        if params.len() != args.len() {
            return Err(format!(
                "TypeError: zla liczba argumentow: oczekiwano {}, podano {}",
                params.len(),
                args.len()
            ));
        }
        let local = store.bubble_new("call", Some(cenv));
        store.set_root(local);
        for (p, val) in params.iter().zip(args.iter()) {
            let _ = self.bind_val(store, local, p, val, "arg");
        }
        let out = self.eval(store, body, local);
        store.unset_root(local);
        out
    }
}

fn apply_builtin(name: &str, args: &[Value]) -> Result<Value, String> {
    match name {
        "+" => fold_nums(args, 0.0, |a, b| a + b),
        "*" => fold_nums(args, 1.0, |a, b| a * b),
        "-" => {
            if args.is_empty() {
                return Err("-: brak argumentow".into());
            }
            if args.len() == 1 {
                return Ok(from_f64(-num(&args[0])?));
            }
            let mut acc = num(&args[0])?;
            for a in &args[1..] {
                acc -= num(a)?;
            }
            Ok(from_f64(acc))
        }
        "/" => {
            if args.len() < 2 {
                return Err("/: potrzeba 2 argumentow".into());
            }
            let mut acc = num(&args[0])?;
            for a in &args[1..] {
                let d = num(a)?;
                if d == 0.0 {
                    return Err("ZeroDivisionError: dzielenie przez zero".into());
                }
                acc /= d;
            }
            Ok(Value::Float(acc))
        }
        "=" => cmp2(args, |a, b| (a - b).abs() < 1e-12),
        "<" => cmp2(args, |a, b| a < b),
        ">" => cmp2(args, |a, b| a > b),
        "<=" => cmp2(args, |a, b| a <= b),
        ">=" => cmp2(args, |a, b| a >= b),
        "not" => {
            if args.len() != 1 {
                return Err("not: 1 argument".into());
            }
            Ok(Value::Bool(!truthy(&args[0])))
        }
        "print" => {
            println!("{}", args.iter().map(fmt).collect::<Vec<_>>().join(" "));
            Ok(Value::Nil)
        }
        _ => Err(format!("brak builtin {name}")),
    }
}

fn num(v: &Value) -> Result<f64, String> {
    match v {
        Value::Int(n) => Ok(*n as f64),
        Value::Float(n) => Ok(*n),
        _ => Err(format!("oczekiwano liczby, jest {}", fmt(v))),
    }
}

fn fold_nums(args: &[Value], start: f64, op: fn(f64, f64) -> f64) -> Result<Value, String> {
    if args.is_empty() {
        return Ok(from_f64(start));
    }
    let mut acc = num(&args[0])?;
    for a in &args[1..] {
        acc = op(acc, num(a)?);
    }
    Ok(from_f64(acc))
}

fn cmp2(args: &[Value], op: fn(f64, f64) -> bool) -> Result<Value, String> {
    if args.len() != 2 {
        return Err("porownanie: 2 argumenty".into());
    }
    Ok(Value::Bool(op(num(&args[0])?, num(&args[1])?)))
}

fn from_f64(n: f64) -> Value {
    if n.fract() == 0.0 && n.abs() < (i64::MAX as f64) {
        Value::Int(n as i64)
    } else {
        Value::Float(n)
    }
}

fn truthy(v: &Value) -> bool {
    match v {
        Value::Nil | Value::Bool(false) | Value::Int(0) => false,
        Value::Float(n) if *n == 0.0 => false,
        _ => true,
    }
}

fn expr_repr(e: &Expr) -> String {
    match e {
        Expr::Symbol(s) => format!("'{s}'"),
        Expr::Int(n) => n.to_string(),
        Expr::Float(n) => n.to_string(),
        Expr::Bool(true) => "#t".into(),
        Expr::Bool(false) => "#f".into(),
        Expr::List(_) => "<list>".into(),
    }
}

pub fn fmt(v: &Value) -> String {
    match v {
        Value::Nil => "()".into(),
        Value::Bool(true) => "#t".into(),
        Value::Bool(false) => "#f".into(),
        Value::Int(n) => n.to_string(),
        Value::Float(n) => n.to_string(),
        Value::Builtin(_) => "<builtin>".into(),
        Value::Closure { params, .. } => format!("<closure ({})>", params.join(" ")),
    }
}

pub fn parse(src: &str) -> Result<Expr, String> {
    let mut toks = tokenize(src);
    if toks.is_empty() {
        return Err("puste wyrazenie".into());
    }
    let expr = read(&mut toks)?;
    if !toks.is_empty() {
        return Err(format!("SyntaxError: nadmiarowe tokeny: {}", toks.join(" ")));
    }
    Ok(expr)
}

fn tokenize(src: &str) -> Vec<String> {
    src.replace('(', " ( ")
        .replace(')', " ) ")
        .split_whitespace()
        .map(str::to_string)
        .collect()
}

fn read(toks: &mut Vec<String>) -> Result<Expr, String> {
    if toks.is_empty() {
        return Err("SyntaxError: nieoczekiwany koniec wejscia".into());
    }
    let tok = toks.remove(0);
    if tok == "(" {
        let mut lst = Vec::new();
        while !toks.is_empty() && toks[0] != ")" {
            lst.push(read(toks)?);
        }
        if toks.is_empty() {
            return Err("SyntaxError: brak ')' — niezamknieta lista".into());
        }
        toks.remove(0);
        return Ok(Expr::List(lst));
    }
    if tok == ")" {
        return Err("SyntaxError: nieoczekiwane ')'".into());
    }
    Ok(atomize(&tok))
}

fn atomize(tok: &str) -> Expr {
    if tok == "#t" {
        return Expr::Bool(true);
    }
    if tok == "#f" {
        return Expr::Bool(false);
    }
    if let Ok(n) = tok.parse::<i64>() {
        return Expr::Int(n);
    }
    if let Ok(n) = tok.parse::<f64>() {
        return Expr::Float(n);
    }
    Expr::Symbol(tok.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use karmazyn_substrate::Store;

    fn ev(lines: &[&str]) -> Vec<String> {
        let store = Store::new(true);
        let lisp = Evaluator::new(&store);
        lines.iter().map(|l| lisp.eval_line(&store, l)).collect()
    }

    #[test]
    fn define_and_add() {
        assert_eq!(
            ev(&["(define x 10)", "(define y (+ x 5))", "(+ x y)"]),
            ["10", "15", "25"]
        );
    }

    #[test]
    fn lambda_immediate() {
        assert_eq!(ev(&["((lambda (a b) (* a b)) 6 7)"]), ["42"]);
    }

    #[test]
    fn closure_add10() {
        let o = ev(&[
            "(define add (lambda (a) (lambda (b) (+ a b))))",
            "(define add10 (add 10))",
            "(add10 5)",
        ]);
        assert_eq!(o.last().unwrap(), "15");
    }

    #[test]
    fn fact5() {
        let o = ev(&[
            "(define fact (lambda (n) (if (< n 2) 1 (* n (fact (- n 1))))))",
            "(fact 5)",
        ]);
        assert_eq!(o.last().unwrap(), "120");
    }

    #[test]
    fn counter() {
        let o = ev(&[
            "(define mk (lambda () (begin (define n 0) (lambda () (begin (set! n (+ n 1)) n)))))",
            "(define c (mk))",
            "(c)",
            "(c)",
            "(c)",
        ]);
        assert_eq!(&o[2..], ["1", "2", "3"]);
    }

    #[test]
    fn specials_and_set_value() {
        let o = ev(&[
            "(define x 1)",
            "(or 0 5)",
            "(and 1 2 3)",
            "(if #t 1 0)",
            "(if #f 1 0)",
            "(+ 1 (set! x 7))",
            "(+ 2 3) ; komentarz",
        ]);
        assert_eq!(&o[1..], ["5", "3", "1", "0", "8", "5"]);
    }

    #[test]
    fn vars_are_atoms() {
        let store = Store::new(true);
        let lisp = Evaluator::new(&store);
        lisp.eval_line(&store, "(define x 10)");
        let aid = store.lookup(lisp.env(), "x").expect("atom x");
        assert!(store.has_atom(aid));
        let tok = store.atom_value_token(aid).unwrap();
        assert_eq!(tok & TAG, TAG_INT);
        assert!(store.atom_payload(aid).is_none());
    }

    #[test]
    fn lambda_payload_on_atom() {
        let store = Store::new(false);
        let lisp = Evaluator::new(&store);
        lisp.eval_line(&store, "(define f (lambda (x) (+ x 1)))");
        let aid = store.lookup(lisp.env(), "f").unwrap();
        let tok = store.atom_value_token(aid).unwrap();
        assert_eq!(tok & TAG, TAG_CLOS);
        assert!(store.atom_payload(aid).unwrap().len() > 0);
    }

    #[test]
    fn portable_golden_file() {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../testy/lisp_golden.txt");
        let text = std::fs::read_to_string(&path).unwrap_or_else(|e| {
            panic!("missing portable golden {}: {e}", path.display())
        });
        let sessions = parse_golden_text(&text);
        assert!(!sessions.is_empty(), "no sessions in golden");
        for (name, steps) in sessions {
            let store = Store::new(true);
            let lisp = Evaluator::new(&store);
            for (src, expect, needle) in steps {
                let got = lisp.eval_line(&store, &src);
                if let Some(n) = needle {
                    assert!(
                        got.starts_with("blad:") && got.to_ascii_lowercase().contains(&n.to_ascii_lowercase()),
                        "[{name}] {src}: expected blad containing {n:?}, got {got:?}"
                    );
                } else if let Some(exp) = expect {
                    assert_eq!(got, exp, "[{name}] {src}");
                }
            }
        }
    }

    fn parse_golden_text(text: &str) -> Vec<(String, Vec<(String, Option<String>, Option<String>)>)> {
        let mut sessions = Vec::new();
        let mut name = String::from("?");
        let mut steps: Vec<(String, Option<String>, Option<String>)> = Vec::new();
        let mut pending: Option<String> = None;
        let flush_pending = |pending: &mut Option<String>,
                             steps: &mut Vec<(String, Option<String>, Option<String>)>,
                             expect: Option<String>,
                             needle: Option<String>| {
            if let Some(src) = pending.take() {
                steps.push((src, expect, needle));
            }
        };
        for raw in text.lines() {
            let s = raw.trim();
            if s.is_empty() || s == "#" || s.starts_with("# ") {
                continue;
            }
            if let Some(rest) = s.strip_prefix("===") {
                if let Some(src) = pending.take() {
                    steps.push((src, None, None));
                }
                if !steps.is_empty() {
                    sessions.push((name.clone(), std::mem::take(&mut steps)));
                }
                name = rest.trim().to_string();
                continue;
            }
            if let Some(rest) = s.strip_prefix(">>>") {
                if let Some(src) = pending.take() {
                    steps.push((src, None, None));
                }
                pending = Some(rest.trim().to_string());
                continue;
            }
            if let Some(rest) = s.strip_prefix('!') {
                let src = pending.take().expect("orphan !");
                steps.push((src, None, Some(rest.trim().to_string())));
                continue;
            }
            let src = pending.take().expect("orphan expect");
            steps.push((src, Some(s.to_string()), None));
        }
        if let Some(src) = pending.take() {
            steps.push((src, None, None));
        }
        let _ = flush_pending;
        if !steps.is_empty() {
            sessions.push((name, steps));
        }
        sessions
    }

    #[test]
    fn closure_survives_snapshot() {
        let store = Store::new(false);
        let lisp = Evaluator::new(&store);
        lisp.eval_line(&store, "(define add (lambda (a) (lambda (b) (+ a b))))");
        lisp.eval_line(&store, "(define add10 (add 10))");
        assert_eq!(lisp.eval_line(&store, "(add10 5)"), "15");
        let text = store.export_snapshot().to_text();
        assert!(text.contains("PAYLOAD"));
        let s2 = Store::new(false);
        s2.import_snapshot(&karmazyn_substrate::StoreSnapshot::from_text(&text).unwrap());
        let lisp2 = Evaluator::attach_repl(&s2);
        assert_eq!(lisp2.eval_line(&s2, "(add10 7)"), "17");
    }
}
