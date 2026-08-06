#!/usr/bin/env bash
# KarmazynOS Stage 3 starter — build homogeneous core from rustc+Cargo only.
# No Python required. Mirror of bootstrap_from_scratch.ps1.
#
#   ./native/bootstrap_from_scratch.sh
#   ./native/bootstrap_from_scratch.sh --skip-c --skip-shell-smoke

set -euo pipefail

SKIP_C=0
SKIP_SHELL=0
for a in "$@"; do
  case "$a" in
    --skip-c) SKIP_C=1 ;;
    --skip-shell-smoke) SKIP_SHELL=1 ;;
    -h|--help)
      echo "Usage: $0 [--skip-c] [--skip-shell-smoke]"
      exit 0
      ;;
  esac
done

NATIVE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$NATIVE/.." && pwd)"
SUB="$NATIVE/karmazyn_substrate"
SHELL_DIR="$NATIVE/karmazyn_shell"
OUT="$ROOT/out"
SNAP="$OUT/bootstrap_demo.ksub"

echo "=== KarmazynOS bootstrap from scratch (Stage 3 starter) ==="
echo "root: $ROOT"

command -v rustc >/dev/null || { echo "need rustc"; exit 1; }
command -v cargo >/dev/null || { echo "need cargo"; exit 1; }
echo "rustc: $(rustc --version)"
echo "cargo: $(cargo --version)"

# Stage 1 (inline subset — Windows uses stage1_verify.ps1)
echo ""
echo "[stage1] karmazyn_slab tests"
( cd "$NATIVE/karmazyn_slab" && cargo test --release )

echo "[stage1] karmazyn_substrate tests + stage1_bootstrap"
( cd "$SUB" && cargo test --release && cargo run --example stage1_bootstrap --release && cargo build --release )

if [[ "$SKIP_C" -eq 0 ]] && command -v gcc >/dev/null 2>&1; then
  echo "[stage1] C ABI smoke"
  gcc "$NATIVE/c_smoke/stage1_c_smoke.c" \
    -I"$SUB/include" -L"$SUB/target/release" -lkarmazyn_substrate \
    -o "$SUB/target/release/stage1_c_smoke"
  export LD_LIBRARY_PATH="$SUB/target/release${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  "$SUB/target/release/stage1_c_smoke"
else
  echo "[stage1] C smoke skipped"
fi

echo ""
echo "[shell] cargo build --release"
( cd "$SHELL_DIR" && cargo build --release )

SHELL_BIN="$SHELL_DIR/target/release/karmazyn_shell"
if [[ ! -x "$SHELL_BIN" ]]; then
  echo "shell binary missing: $SHELL_BIN" >&2
  exit 1
fi

if [[ "$SKIP_SHELL" -eq 0 ]]; then
  echo ""
  echo "[shell smoke] save/load snapshot"
  mkdir -p "$OUT"
  rm -f "$SNAP"
  "$SHELL_BIN" \
    -e "atom var hello 50" \
    -e "bubble root" \
    -e "root 0" \
    -e "bind 0 hi 0" \
    -e "save $SNAP" \
    -e quit
  [[ -f "$SNAP" ]] || { echo "snapshot not written"; exit 1; }
  "$SHELL_BIN" -e "load $SNAP" -e stats -e "lookup 0 hi" -e quit
  echo "  snapshot: $SNAP"
fi

echo ""
echo "=== BOOTSTRAP_FROM_SCRATCH_OK ==="
echo "Kernel:  $SUB/target/release/"
echo "Shell:   $SHELL_BIN"
echo "Docs:    Documents/BOOTSTRAP_STAGES.pl.md"
exit 0
