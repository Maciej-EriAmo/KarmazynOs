# Instalacja Product host (L1) — KarmazynOs

**Czas docelowy:** ≤ 30 min na czystej maszynie  
**Kompilator:** `rustc` (stable) + cargo  
**Z0:** prawo Store powstaje w crate Rust, nie w Pythonie.

---

## 1. Wymagania

| Składnik | Wersja | Po co |
|----------|--------|--------|
| Git | dowolny | klon |
| Python | 3.10+ (test 3.14 OK) | host, boot, Studio |
| rustup / rustc | stable | substrat native |
| MSVC **lub** MinGW | Windows link | `x86_64-pc-windows-msvc` / `gnu` |
| pip | — | maturin, numpy (opc.), pygame (Studio) |

Linux/macOS: typowy `build-essential` / Xcode CLT zamiast MSVC.

---

## 2. Klon

```bash
git clone https://github.com/Maciej-EriAmo/KarmazynOs
cd KarmazynOs
```

---

## 3. Python env (zalecane venv)

```bash
python -m venv .venv
# Windows:
.\.venv\Scripts\Activate.ps1
# Unix:
# source .venv/bin/activate

pip install -U pip
pip install numpy maturin
pip install pygame   # tylko Studio SDL
```

---

## 4. Rust + native substrate

```bash
# jeśli brak rustc:
#   Windows: https://rustup.rs/
#   rustup default stable

# Windows (MSVC default):
.\native\build_native.ps1

# Linux/macOS:
./native/build_native.sh
```

**Sukces:** `python -c "from karmazyn_backend import native_available; assert native_available()"`  
(z `PYTHONPATH` jak poniżej).

Linker:

| Target rustup | Potrzeba |
|---------------|----------|
| `x86_64-pc-windows-msvc` | VS Build Tools (C++) |
| `x86_64-pc-windows-gnu` | MinGW + `rustup default stable-gnu` |

---

## 5. PYTHONPATH (sesja)

```powershell
# Windows PowerShell
$env:PYTHONPATH = "$PWD;$PWD\software;$PWD\kernel;$PWD\native"
$env:KARMAZYN_SUBSTRATE = "native"   # Product
```

```bash
export PYTHONPATH="$PWD:$PWD/archiwum/kernel_python:$PWD/software:$PWD/native"
export KARMAZYN_SUBSTRATE=native
```

Albo: `python start.py` (ustawia path w podprocesie).

---

## 6. Gate Product (G0)

```powershell
.\scripts\gate_product.ps1
# szybciej bez Lua:
.\scripts\gate_product.ps1 -SkipLua
```

```bash
chmod +x scripts/gate_product.sh
./scripts/gate_product.sh
# SKIP_LUA=1 SKIP_STUDIO=1 ./scripts/gate_product.sh
```

**Sukces:** `GATE PRODUCT PASS`, exit 0.

---

## 7. Start

```bash
python start.py                  # menu
python start.py --studio         # Studio SDL (mapa T tło)
python karmazyn_boot.py          # REPL
python software/karmazyn_studio.py --check   # smoke bez okna
```

W REPL: `:io` → `stage=1`; `:hot` → matryca.

Rescue (gdy native padnie — świadomie):

```bash
set KARMAZYN_SUBSTRATE=python
# opcjonalnie: KARMAZYN_IO_OPTIONAL=1
```

---

## 8. Piaskownica

```bash
# izolowany katalog roboczy + gate
python sandbox/bootstrap_sandbox.py
# potem:
cd sandbox/work
# … eksperymenty; nie commitować work/ do main bez review
```

Zob. `sandbox/README.md`.

---

## 9. Znane limity (L1)

- Host tools ze **string id** w testach = backend **python**; Product Store = **u32** w Rust.
- Studio wymaga pygame; headless = `--check`.
- Brak ISO/GRUB w L1 (faza E planu).
- `KARMAZYN_STRICT_IDS=1` → NativeStore odrzuca string id przy `create_atom`.

---

## 10. Docs

| Plik | Temat |
|------|--------|
| `Documents/build_deploy_plan.md` | fazy L0–L4, Z0 |
| `Documents/rust_substrate_map.md` | mapa Rust |
| `Documents/enterprise_review_raw.md` | recenzja |
| `Documents/io_stage1.md` | matryca I/O |
| `Documents/studio_sdl.md` | Studio |
