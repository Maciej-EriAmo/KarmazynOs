# karmazyn_kentry — Multiboot2 entry (L3 / faza F)

**Status:** szkielet MVP  
**Robi:** serial COM1 → `KARMAZYN_KENTRY_OK`  
**Nie robi:** Store, GC, Python, Lua, GUI  

Z0: pełne prawo substratu **zostaje** w `native/karmazyn_substrate`.  
kentry **nie** implementuje tick — to faza G (po designie alokatora: `Documents/rust_roadmap_tech.md` §4).

## Build

```bash
rustup target add x86_64-unknown-none
# z roota monorepo (linker.ld ścieżka względem cwd cargo bywa myląca — buduj z boot/kentry):
cd boot/kentry
cargo build --release --target x86_64-unknown-none
```

ELF: `target/x86_64-unknown-none/release/karmazyn_kentry`

Na Windows link `x86_64-unknown-none` bywa kapryśny (lld/gnu).  
Wtedy: buduj w WSL/Linux CI; lokalnie weryfikuj marker w źródle:

```bash
rg "KARMAZYN_KENTRY_OK" boot/kentry/src/main.rs
```

## QEMU + GRUB (gdy masz ISO tooling)

```bash
# szkic — pełne ISO = faza E; tu ręczny grub-mkrescue gdy dostępne:
# multiboot2 /boot/karmazyn_kentry
qemu-system-x86_64 -cdrom karmazyn-kentry.iso -serial stdio -display none
# expect: KARMAZYN_KENTRY_OK
```

## Punkty sukcesu

| ID | Stan |
|----|------|
| SF.1 źródła + Cargo.toml | ✅ ten katalog |
| SF.2 QEMU serial | ⏳ gdy toolchain + ISO |
| SF.3 brak CPython | ✅ |
| SG.* Store | ❌ nie ten crate (jeszcze) |
