//! kcc — Karmazyn own compiler (K0 → C99).
//!
//! Policy (Tor B):
//! - **Own:** this frontend + codegen (and later self-host in K0).
//! - **Foreign OK:** editor, OS, host stage0 `rustc` (only to build `kcc` once), `gcc`/`cc` as linker/assembler.
//!
//!   cargo run --release -- examples/thermal.k0 -o out/thermal.c
//!   cargo run --release -- examples/thermal.k0 --cc -o out/thermal
//!   cargo run --release -- examples/store_mini.k0 --safe --cc -o out/store_mini

mod ast;
mod codegen_c;
mod lex;
mod parse;
mod preprocess;
mod sem;

use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{self, Command};

fn main() {
    if let Err(e) = run() {
        eprintln!("kcc: {e}");
        process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let args: Vec<String> = env::args().skip(1).collect();
    if args.is_empty() || args.iter().any(|a| a == "-h" || a == "--help") {
        print_help();
        return Ok(());
    }

    let mut input: Option<PathBuf> = None;
    let mut output: Option<PathBuf> = None;
    let mut invoke_cc = false;
    let mut dump_ast = false;
    let mut safe = false;
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "-o" | "--output" => {
                i += 1;
                if i >= args.len() {
                    return Err("-o requires a path".into());
                }
                output = Some(PathBuf::from(&args[i]));
            }
            "--cc" => invoke_cc = true,
            "--dump-ast" => dump_ast = true,
            "--safe" => safe = true,
            "-h" | "--help" => {
                print_help();
                return Ok(());
            }
            s if s.starts_with('-') => return Err(format!("unknown flag {s}")),
            s => {
                if input.is_some() {
                    return Err("multiple input files not supported yet".into());
                }
                input = Some(PathBuf::from(s));
            }
        }
        i += 1;
    }

    let input = input.ok_or("missing input .k0 file")?;
    let src = preprocess::load_with_includes(&input)?;
    let prog = parse::parse(&src)?;
    if dump_ast {
        println!("{prog:#?}");
        return Ok(());
    }

    sem::check(&prog)?;
    let c_src = codegen_c::emit_c(&prog, safe)?;
    let c_path = match &output {
        Some(p) if p.extension().and_then(|e| e.to_str()) == Some("c") => p.clone(),
        Some(p) if invoke_cc => p.with_extension("c"),
        Some(p) => {
            if p.extension().is_none() {
                p.with_extension("c")
            } else {
                p.clone()
            }
        }
        None => {
            let mut p = input.clone();
            p.set_extension("c");
            p
        }
    };

    if let Some(parent) = c_path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    fs::write(&c_path, &c_src).map_err(|e| format!("write {}: {e}", c_path.display()))?;
    eprintln!(
        "kcc: wrote {}{}",
        c_path.display(),
        if safe { " (safe bounds)" } else { "" }
    );

    if invoke_cc {
        let bin = output.unwrap_or_else(|| {
            let mut p = input.clone();
            p.set_extension("");
            p
        });
        let bin = if bin.extension().and_then(|e| e.to_str()) == Some("c") {
            bin.with_extension("")
        } else {
            bin
        };
        compile_c(&c_path, &bin)?;
        eprintln!("kcc: linked {}", bin.display());
    }

    Ok(())
}

fn compile_c(c_path: &Path, bin: &Path) -> Result<(), String> {
    if let Some(parent) = bin.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let ccs = ["gcc", "clang", "cc"];
    let mut last = String::new();
    for cc in ccs {
        let mut cmd = Command::new(cc);
        cmd.arg(c_path).arg("-O2").arg("-o").arg(bin).arg("-lm");
        match cmd.status() {
            Ok(st) if st.success() => return Ok(()),
            Ok(st) => last = format!("{cc} exit {st}"),
            Err(e) => last = format!("{cc}: {e}"),
        }
    }
    Err(format!(
        "failed to invoke C compiler (foreign env). last: {last}"
    ))
}

fn print_help() {
    println!(
        "kcc 0.6.1 — Karmazyn own compiler (K0 → C99)

USAGE:
  kcc <file.k0> [-o out.c]
  kcc <file.k0> --cc -o out_binary
  kcc <file.k0> --safe --cc -o out_binary
  kcc <file.k0> --dump-ast

FLAGS:
  --safe     emit array bounds checks (abort on OOB)
  --cc       link with foreign gcc/clang
  --dump-ast print AST and exit

LANGUAGE:
  #include \"other.k0\"
  fixed arrays [T; N], a[i], array params
  for (init; cond; step) {{ }}  break;  continue;   (TB.3c / 0.5)
  struct Name {{ field: ty … }}  p.f  p.a.b = e  return struct  (TB.3d+ / 0.6.1)
  sem: undeclared, arity, no f64 %, type-unify, return-paths, break-in-loop, fields

POLICY:
  Own:     K0 frontend + codegen
  Foreign: editor, OS, stage0 rustc, gcc link

See: Documents/TOR_B_TOOLCHAIN.pl.md
"
    );
}

#[cfg(test)]
mod tests {
    use crate::codegen_c::emit_c;
    use crate::parse::parse;
    use crate::sem;

    #[test]
    fn parse_thermal_and_emit() {
        let src = r#"
fn state_code(t: f64) -> i32 {
    if t >= 70.0 {
        return 3;
    } else {
        if t >= 30.0 {
            return 2;
        } else {
            if t >= 2.0 {
                return 1;
            } else {
                return 0;
            }
        }
    }
}

fn add(a: i64, b: i64) -> i64 {
    return a + b;
}
"#;
        let p = parse(src).expect("parse");
        sem::check(&p).expect("sem");
        let c = emit_c(&p, false).expect("emit");
        assert!(c.contains("k0_state_code"));
        assert!(c.contains("k0_add"));
        assert!(c.contains("70"));
    }

    #[test]
    fn binop_precedence() {
        let p = parse("fn f() -> i64 { return 1 + 2 * 3; }").unwrap();
        sem::check(&p).unwrap();
        let c = emit_c(&p, false).unwrap();
        assert!(c.contains("*"));
    }

    #[test]
    fn array_zero_and_index() {
        let src = r#"
fn main() -> i32 {
    let a: [i64; 4];
    a[0] = 7;
    a[1] = a[0] + 1;
    return a[1];
}
"#;
        let p = parse(src).expect("parse");
        sem::check(&p).expect("sem");
        let c = emit_c(&p, false).expect("emit");
        assert!(c.contains("int64_t a[4]"));
        assert!(c.contains("memset"));
    }

    #[test]
    fn array_param_emits_pointer() {
        let src = r#"
fn sum2(a: [i64; 2]) -> i64 {
    return a[0] + a[1];
}
fn main() -> i32 {
    let a: [i64; 2];
    a[0] = 1;
    a[1] = 2;
    return sum2(a);
}
"#;
        let p = parse(src).expect("parse");
        sem::check(&p).expect("sem");
        let c = emit_c(&p, false).expect("emit");
        assert!(c.contains("int64_t *"));
        assert!(c.contains("k0_sum2"));
    }

    #[test]
    fn safe_emits_abort_guard() {
        let src = r#"
fn main() -> i32 {
    let a: [i64; 2];
    a[0] = 1;
    return a[0];
}
"#;
        let p = parse(src).unwrap();
        sem::check(&p).unwrap();
        let c = emit_c(&p, true).unwrap();
        assert!(c.contains("abort"));
        assert!(c.contains("stdlib.h"));
    }

    #[test]
    fn for_loop_emits_c_for() {
        let src = r#"
fn main() -> i32 {
    let s: i64 = 0;
    for (let i: i64 = 0; i < 5; i = i + 1) {
        s = s + i;
    }
    return s;
}
"#;
        let p = parse(src).expect("parse for");
        sem::check(&p).expect("sem for");
        let c = emit_c(&p, false).expect("emit for");
        assert!(c.contains("for ("), "expected C for: {c}");
        assert!(c.contains("i ="), "step assign missing: {c}");
        assert!(c.contains('+') || c.contains(" + "), "increment missing: {c}");
    }

    #[test]
    fn struct_define_field_access() {
        let src = r#"
struct Point {
    x: i64
    y: i64
}
fn main() -> i32 {
    let p: Point;
    p.x = 10;
    p.y = 20;
    return p.x + p.y;
}
"#;
        let p = parse(src).expect("parse struct");
        sem::check(&p).expect("sem struct");
        let c = emit_c(&p, false).expect("emit struct");
        assert!(c.contains("typedef struct Point"), "missing typedef: {c}");
        assert!(c.contains("p.x"), "missing field: {c}");
        assert!(c.contains("memset"), "struct zero-init: {c}");
    }

    #[test]
    fn struct_return_and_nested() {
        let src = r#"
struct Point { x: i64 y: i64 }
struct Box { p: Point }
fn mk(x: i64) -> Point {
    let p: Point;
    p.x = x;
    p.y = x;
    return p;
}
fn main() -> i32 {
    let b: Box;
    b.p = mk(3);
    b.p.x = b.p.x + 1;
    return b.p.x + b.p.y;
}
"#;
        let p = parse(src).expect("parse nested");
        sem::check(&p).expect("sem nested");
        let c = emit_c(&p, false).expect("emit nested");
        assert!(c.contains("typedef struct Point"), "{c}");
        assert!(c.contains("typedef struct Box"), "{c}");
        assert!(c.contains("b.p.x"), "nested assign: {c}");
        assert!(c.contains("Point k0_mk"), "return struct proto: {c}");
    }

    #[test]
    fn struct_rejects_unknown_field() {
        let src = r#"
struct Point { x: i64 }
fn main() -> i32 {
    let p: Point;
    p.y = 1;
    return 0;
}
"#;
        let p = parse(src).unwrap();
        let e = sem::check(&p).unwrap_err();
        assert!(e.contains("no field") || e.contains("y"), "{e}");
    }

    #[test]
    fn break_continue_in_loop() {
        let src = r#"
fn main() -> i32 {
    let s: i64 = 0;
    let i: i64 = 0;
    while i < 10 {
        i = i + 1;
        if i == 3 {
            continue;
        }
        if i == 7 {
            break;
        }
        s = s + i;
    }
    return s;
}
"#;
        let p = parse(src).expect("parse");
        sem::check(&p).expect("sem");
        let c = emit_c(&p, false).expect("emit");
        assert!(c.contains("break;"));
        assert!(c.contains("continue;"));
    }

    #[test]
    fn break_outside_loop_rejected() {
        let src = r#"
fn main() -> i32 {
    break;
    return 0;
}
"#;
        let p = parse(src).unwrap();
        let err = sem::check(&p).unwrap_err();
        assert!(err.contains("break"), "{err}");
    }
}
