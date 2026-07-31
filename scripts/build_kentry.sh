#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/boot/kentry"
rustup target add x86_64-unknown-none >/dev/null 2>&1 || true
cargo build --release --target x86_64-unknown-none
ELF="target/x86_64-unknown-none/release/karmazyn_kentry"
test -f "$ELF"
grep -a -q "KARMAZYN_KENTRY_OK" "$ELF"
grep -a -q "SLAB_OK" "$ELF"
echo "OK kentry ELF=$ELF size=$(wc -c < "$ELF") MARKER=yes SLAB=yes"
