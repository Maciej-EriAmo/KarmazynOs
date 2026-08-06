//! K0 preprocessor: line `#include "path.k0"` (relative to including file).
//! Own compiler feature — not the C preprocessor.

use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};

pub fn load_with_includes(entry: &Path) -> Result<String, String> {
    let mut seen = HashSet::new();
    load_rec(entry, &mut seen, 0)
}

fn load_rec(path: &Path, seen: &mut HashSet<PathBuf>, depth: u32) -> Result<String, String> {
    if depth > 32 {
        return Err("include nesting too deep (>32)".into());
    }
    let canon = path
        .canonicalize()
        .unwrap_or_else(|_| path.to_path_buf());
    if !seen.insert(canon.clone()) {
        return Err(format!("circular include: {}", path.display()));
    }
    let text = fs::read_to_string(path).map_err(|e| format!("read {}: {e}", path.display()))?;
    let base = path
        .parent()
        .map(Path::to_path_buf)
        .unwrap_or_else(|| PathBuf::from("."));
    let mut out = String::new();
    for (lineno, line) in text.lines().enumerate() {
        let trimmed = line.trim();
        if let Some(rest) = trimmed.strip_prefix("#include") {
            let rest = rest.trim();
            let rel = parse_include_path(rest).map_err(|e| {
                format!("{}:{}: {e}", path.display(), lineno + 1)
            })?;
            let child = base.join(rel);
            if !child.exists() {
                return Err(format!(
                    "{}:{}: include not found: {}",
                    path.display(),
                    lineno + 1,
                    child.display()
                ));
            }
            let nested = load_rec(&child, seen, depth + 1)?;
            out.push_str(&format!("// --- begin include {} ---\n", child.display()));
            out.push_str(&nested);
            if !nested.ends_with('\n') {
                out.push('\n');
            }
            out.push_str(&format!("// --- end include {} ---\n", child.display()));
        } else {
            out.push_str(line);
            out.push('\n');
        }
    }
    Ok(out)
}

fn parse_include_path(rest: &str) -> Result<String, String> {
    let rest = rest.trim();
    if let Some(s) = rest.strip_prefix('"').and_then(|s| s.strip_suffix('"')) {
        if s.is_empty() {
            return Err("empty include path".into());
        }
        return Ok(s.to_string());
    }
    if let Some(s) = rest.strip_prefix('<').and_then(|s| s.strip_suffix('>')) {
        if s.is_empty() {
            return Err("empty include path".into());
        }
        return Ok(s.to_string());
    }
    Err("include expects \"path.k0\"".into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn include_expands() {
        let dir = std::env::temp_dir().join(format!("kcc_inc_{}", std::process::id()));
        let _ = fs::create_dir_all(&dir);
        let lib = dir.join("lib.k0");
        let main = dir.join("main.k0");
        fs::write(&lib, "fn one() -> i32 { return 1; }\n").unwrap();
        fs::write(
            &main,
            "#include \"lib.k0\"\nfn main() -> i32 { return one(); }\n",
        )
        .unwrap();
        let s = load_with_includes(&main).expect("load");
        assert!(s.contains("fn one()"));
        assert!(s.contains("fn main()"));
        let _ = fs::remove_file(&lib);
        let _ = fs::remove_file(&main);
        let _ = fs::remove_dir(&dir);
    }
}
