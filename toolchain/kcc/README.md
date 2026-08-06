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

Gate (TB.1–TB.3 + 0.4 type-unify / return-paths):

```powershell
.\toolchain\verify_kcc.ps1
# → KCC_VERIFY_OK  (builds with --safe)
```

## K0 language (0.4)

- `fn name(a: ty, …) -> ty { … }`
- types: `i32` `i64` `f64` `bool` · fixed arrays `[f64; 8]`
- `let x: ty = expr;` · `let a: [T; N];` (zero-init) · `x = expr;` · `a[i] = expr;`
- `if cond { } else { }` · `while cond { }`
- ops: `+ - * / %` comparisons `&& || !`
- calls: `foo(1, 2.0)` · index: `a[i]`
- `#include "other.k0"` (relative, circular-safe)
- array **params** → C pointers (helpers can mutate tables)

### Semantics (0.3 → 0.4)

| Check | Notes |
|-------|--------|
| undeclared / redef / arity | 0.3 |
| `%` not on f64 | 0.3 |
| `--safe` array bounds → abort | 0.3 |
| **type-unify** let/assign/index/call/return | 0.4 — i32↔i64, int→f64; bool/array exact |
| **return-path** | 0.4 — every path must `return` (if/else both arms count) |

Not yet: structs, nested arrays, true modules/packages, strings, self-host of kcc in K0.

## Next

1. ~~TB.2 / TB.2e / type-unify return-paths (0.4)~~ done.  
2. Optional: golden reach store_mini ↔ slab.  
3. Self-host: rewrite `kcc` in K0 (TB.4, long).  
4. Optional: own backend without gcc (TB.5).

See `Documents/TOR_B_TOOLCHAIN.pl.md`.
