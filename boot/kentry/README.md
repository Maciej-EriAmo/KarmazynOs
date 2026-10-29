# karmazyn_kentry — Multiboot2 entry (L3 / faza F + R5)

**Status:** R5 — serial + `SlabStore` demo  
**Robi:**
- COM1 → `KARMAZYN_KENTRY_OK`
- Multiboot2 magic / cmdline dump (gdy bootloader)
- static `karmazyn_slab::SlabStore` — orphan vacuum + rooted retain; `SLAB_OK` **tylko** gdy oba OK

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

## QEMU serial (SF.2, bez ISO)

Multiboot2 zostawia CPU w 32-bit protected mode. `src/boot.s` włącza long mode
(tożsamościowe 1 GiB) i woła `kmain`.

```powershell
.\scripts\build_kentry.ps1
.\boot\kentry\qemu_serial.ps1
# exit 0 tylko gdy serial ma KARMAZYN_KENTRY_OK i SLAB_OK
# exit 2: brak qemu-system-x86_64 (PATH albo $env:QEMU_BIN)
```

QEMU 11 ładuje ELF notatką PVH (`.note.Xen`, wejście `_start`).
Multiboot2 zostaje w obrazie dla GRUB. Skrypt bierze serial COM1
do pliku i ubija QEMU — pętla `hlt` nie wraca.
Na hoście dev: QEMU 11.1 w `C:\Program Files\qemu` (PATH użytkownika).

## ISO GRUB (marker serial)

Jest ISO GRUB dla kentry (marker serial). Nie jest obrazem do promptu `karmazyn>`.

```powershell
.\scripts\build_kentry_iso.ps1
.\boot\kentry\qemu_iso.ps1
# exit 0: KARMAZYN_KENTRY_OK, MB2_MAGIC_OK, karmazyn.kentry=1, SLAB_OK
```

Wynik: `out/karmazyn-kentry.iso` (katalog `out/` jest w `.gitignore`).
GRUB 2.12 for Windows: `GRUB_DIR` albo `%LOCALAPPDATA%\KarmazynOs\grub-2.12-for-windows`.
xorriso: `XORRISO` albo `C:\msys64\usr\bin\xorriso.exe`.
Paczka GRUB 2.14 for Windows ma `i386-pc/kernel.img` z VMA 0 zamiast 0x9000 — `grub-mkimage` jej nie bierze.
Menu: `boot/grub/grub.cfg` (`multiboot2 /boot/karmazyn_kentry`).

## Punkty sukcesu

| ID | Stan |
|----|------|
| SF.1 źródła + Cargo.toml | ✅ |
| SF.2 QEMU serial | ✅ `qemu_serial.ps1` — `KARMAZYN_KENTRY_OK` i `SLAB_OK` |
| SF.4 cmdline Multiboot | ✅ z płyty: `CMDLINE=karmazyn.kentry=1` (`qemu_iso.ps1`) |
| ISO GRUB kentry | ✅ marker serial; nie prompt produktu |
| SF.3 brak CPython | ✅ |
| R5 SlabStore link + serial stats | ✅ `SLAB_OK` |
| SG.* pełny Store | ❌ faza G |
