//! kcc jako biblioteka: frontend K0 (lexer, parser, semantyka) i codegen C99.
//!
//! Program `kcc` (main.rs) czyta pliki i woła `cc`. Shell Karmazyna
//! (minister kcc w KANON) linkuje tę bibliotekę: źródło bierze z bąbli kodu
//! (`load_with_loader`), wynik C zostaje w Store, bez procesów.

pub mod ast;
pub mod codegen_c;
pub mod lex;
pub mod parse;
pub mod preprocess;
pub mod sem;

pub const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Źródło K0 (już po `#include`) → C99. `safe` = kontrola granic tablic.
pub fn compile(src: &str, safe: bool) -> Result<String, String> {
    let prog = parse::parse(src)?;
    sem::check(&prog)?;
    codegen_c::emit_c(&prog, safe)
}

#[cfg(test)]
mod tests {
    #[test]
    fn hello_compiles_to_c_main() {
        let c = super::compile("fn main() -> i32 {\n    return 0;\n}\n", false).unwrap();
        assert!(c.contains("main"), "{c}");
        assert!(super::compile("fn main() -> i32 { return x; }", false).is_err());
    }
}
