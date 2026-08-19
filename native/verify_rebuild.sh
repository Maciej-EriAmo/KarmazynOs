#!/usr/bin/env bash
# Tor B — LFS/Gentoo pattern, language = Rust, compiler slot = rustc.
# Rebuilds critical crates in order. No Python. No gcc.
#
#   ./native/verify_rebuild.sh
# → REBUILD_OK

set -euo pipefail

NATIVE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$NATIVE/.." && pwd)"
SLAB="$NATIVE/karmazyn_slab"
SUB="$NATIVE/karmazyn_substrate"
LISP="$NATIVE/karmazyn_lisp"
SHELL_DIR="$NATIVE/karmazyn_shell"
KCC="$ROOT/toolchain/kcc"

echo "=== KarmazynOS rebuild (LFS pattern, rustc) ==="
echo "host compiler: rustc (gcc slot). language: Rust (not C)."

command -v rustc >/dev/null || { echo "need rustc"; exit 1; }
command -v cargo >/dev/null || { echo "need cargo"; exit 1; }
echo "rustc: $(rustc --version)"
echo "cargo: $(cargo --version)"

crate_test() {
  local dir="$1" label="$2"
  echo ""
  echo "[$label] cargo test --release  ($dir)"
  ( cd "$dir" && cargo test --release )
}

crate_test "$SLAB" "1/5 slab"
crate_test "$SUB" "2/5 substrate"

echo ""
echo "[2b] stage1_bootstrap example"
( cd "$SUB" && cargo run --example stage1_bootstrap --release )

echo ""
crate_test "$LISP" "3/5 lisp"

echo ""
echo "[4/5] karmazyn_shell cargo build --release"
( cd "$SHELL_DIR" && cargo build --release )
SHELL_BIN="$SHELL_DIR/target/release/karmazyn_shell"
[[ -x "$SHELL_BIN" ]] || { echo "shell binary missing"; exit 1; }
"$SHELL_BIN" --version

crate_test "$KCC" "5/5 kcc (rustc-built tool)"

echo ""
echo "=== REBUILD_OK ==="
echo "Order: slab → substrate → shell → kcc. rustc only. No gcc, no Python."
echo "kcc here is a Rust package, not a C backend."
exit 0
