# kcc — Karmazyn own compiler (K0 → C99)

**Policy**

| Own | Foreign (allowed) |
|-----|-------------------|
| K0 language + lexer/parser/codegen | Editor, OS, IDE |
| `kcc` driver | **stage0** `rustc`/`cargo` — only to *build* `kcc` once |
| Critical sources in `.k0` | `gcc`/`clang` as **linker**/assembler (env) |

This is **Tor B seed**: important law (`thermal.k0`) is compiled by **kcc**, not by rustc.

## Build kcc (stage0 — foreign rustc, once)

```powershell
cd toolchain\kcc
cargo build --release
cargo test --release
```

## Compile critical thermal law

```powershell
# emit C only (own compiler product)
.\target\release\kcc.exe examples\thermal.k0 -o ..\..\out\kcc\thermal.c

# emit C + link with foreign gcc
.\target\release\kcc.exe examples\thermal.k0 --cc -o ..\..\out\kcc\thermal_smoke
```

Gate:

```powershell
.\toolchain\verify_kcc.ps1
# → KCC_VERIFY_OK
```

## K0 language (0.1)

- `fn name(a: ty, …) -> ty { … }`
- types: `i32` `i64` `f64` `bool`
- `let x: ty = expr;` · `x = expr;` · `return expr;`
- `if cond { } else { }` · `while cond { }`
- ops: `+ - * / %` comparisons `&& || !`
- calls: `foo(1, 2.0)`

Not yet: structs, arrays, pointers, modules, strings, self-host of kcc in K0.

## Next

1. More critical `.k0` (decay/tick skeleton).  
2. ABI header shared with substrate (`state_code` ↔ `state_for_t`).  
3. Self-host: rewrite `kcc` in K0 (long).  
4. Optional: own backend (no gcc) later — not required for “own compiler” if frontend+IR are ours and C is portable IL.

See `Documents/TOR_B_TOOLCHAIN.pl.md`.
