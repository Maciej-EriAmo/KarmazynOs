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

## Compile critical law (.k0)

```powershell
# thermal: thresholds, state_code, decay_n, heat, tick_t
.\target\release\kcc.exe examples\thermal.k0 --cc -o ..\..\out\kcc\thermal_smoke

# tick skeleton: cool_until_dead / heat revive (T only)
.\target\release\kcc.exe examples\tick_skeleton.k0 --cc -o ..\..\out\kcc\tick_skeleton

# mini atom table (fixed arrays, pin/vacuum)
.\target\release\kcc.exe examples\atom_table.k0 --cc -o ..\..\out\kcc\atom_table

# mini Store: roots + binds + reach + settle vacuum
.\target\release\kcc.exe examples\store_mini.k0 --cc -o ..\..\out\kcc\store_mini
```

Gate (TB.1–TB.3: kcc + both .k0 + Rust/Python golden):

```powershell
.\toolchain\verify_kcc.ps1
# → KCC_VERIFY_OK
```

## K0 language (0.1)

- `fn name(a: ty, …) -> ty { … }`
- types: `i32` `i64` `f64` `bool` · fixed arrays `[f64; 8]`
- `let x: ty = expr;` · `let a: [T; N];` (zero-init) · `x = expr;` · `a[i] = expr;`
- `if cond { } else { }` · `while cond { }`
- ops: `+ - * / %` comparisons `&& || !`
- calls: `foo(1, 2.0)` · index: `a[i]`

- `#include "other.k0"` (relative, circular-safe)
- array **params** → C pointers (helpers can mutate tables)

Not yet: structs, nested arrays, true modules/packages, strings, self-host of kcc in K0.

## Next

1. ~~TB.2 / TB.2b / TB.3~~ done (thermal, tick, atom_table, golden).  
2. Array params / multi-file K0 modules — optional.  
3. Self-host: rewrite `kcc` in K0 (TB.4, long).  
4. Optional: own backend without gcc (TB.5).

See `Documents/TOR_B_TOOLCHAIN.pl.md`.
