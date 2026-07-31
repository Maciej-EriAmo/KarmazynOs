# karmazyn_kentry — Multiboot2 entry (L3 / faza F + R5)

**Status:** R5 — serial + `SlabStore` demo  
**Robi:**
- COM1 → `KARMAZYN_KENTRY_OK`
- Multiboot2 magic / cmdline dump (gdy bootloader)
- static `karmazyn_slab::SlabStore` — atom / root / tick / `SLAB_ATOMS=… REAPED=… LIVE=…` + `SLAB_OK`

**Nie robi:** pełny host `Store` (HashMap), Python, Lua, GUI  

Z0: prawo T×reach w `native/karmazyn_slab` (re-export w substrate).  
kentry linkuje **ten sam** crate — nie duplikuje GC.

## Build

```bash
rustup target add x86_64-unknown-none
cd boot/kentry
cargo build --release --target x86_64-unknown-none
```

ELF: `target/x86_64-unknown-none/release/karmazyn_kentry`

Na Windows link `x86_64-unknown-none` bywa kapryśny (lld/gnu).  
Wtedy: buduj w WSL/Linux CI; lokalnie weryfikuj markery w źródle/ELF:

```bash
rg "KARMAZYN_KENTRY_OK|SLAB_OK" boot/kentry/src/main.rs
# po build:
# strings ELF | findstr SLAB
```

## QEMU + GRUB (gdy masz ISO tooling)

```bash
# szkic — pełne ISO = faza E; tu ręczny grub-mkrescue gdy dostępne:
# multiboot2 /boot/karmazyn_kentry
qemu-system-x86_64 -cdrom karmazyn-kentry.iso -serial stdio -display none
# expect: KARMAZYN_KENTRY_OK … SLAB_OK
```

## Punkty sukcesu

| ID | Stan |
|----|------|
| SF.1 źródła + Cargo.toml | ✅ |
| SF.2 QEMU serial | ⏳ gdy toolchain + ISO |
| SF.3 brak CPython | ✅ |
| R5 SlabStore link + serial stats | ✅ `SLAB_OK` |
| SG.* pełny Store | ❌ faza G |
