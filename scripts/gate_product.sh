#!/usr/bin/env bash
# gate_product.sh — Enterprise G0 gate (exit 0 = pass)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT:$ROOT/archiwum/kernel_python:$ROOT/software:$ROOT/native${PYTHONPATH:+:$PYTHONPATH}"
export KARMAZYN_SUBSTRATE="${KARMAZYN_SUBSTRATE:-python}"
export KARMAZYN_LUA="${KARMAZYN_LUA:-$ROOT/LUA}"

step() {
  echo ""
  echo "== $1 =="
  shift
  "$@"
  echo "OK: $1"
}

echo "KarmazynOs gate_product  root=$ROOT  substrate=$KARMAZYN_SUBSTRATE"

if [[ "${SKIP_CARGO:-}" != "1" ]]; then
  step "cargo test slab" cargo test --manifest-path "$ROOT/native/karmazyn_slab/Cargo.toml" -q
  step "cargo test substrate" cargo test --manifest-path "$ROOT/native/karmazyn_substrate/Cargo.toml" -q
  step "cargo test lisp" cargo test --manifest-path "$ROOT/native/karmazyn_lisp/Cargo.toml" -q
  step "cargo test shell" cargo test --manifest-path "$ROOT/native/karmazyn_shell/Cargo.toml" -q
  step "cargo test kcc" cargo test --manifest-path "$ROOT/toolchain/kcc/Cargo.toml" -q
fi

step "kernel_boundary" python "$ROOT/kernel_boundary.py" "$ROOT/archiwum/kernel_python" "$ROOT/software"
step "unittest io+host" python -m unittest software.test_io_thermal software.test_host_tools -q

if [[ "${SKIP_STUDIO:-}" != "1" ]]; then
  step "unittest studio" python -m unittest software.test_studio_sdl -q
fi

if [[ "${SKIP_LUA:-}" != "1" && -f "$ROOT/software/test_lua_release.py" ]]; then
  step "lua release" python "$ROOT/software/test_lua_release.py"
fi

echo ""
echo "========================================"
echo "  GATE PRODUCT PASS"
echo "========================================"
