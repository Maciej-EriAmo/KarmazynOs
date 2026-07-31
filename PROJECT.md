# KarmazynOs — start projektu (enterprise wave)

**Data startu fali:** 2026-07-31  
**Cel najbliższy:** **L1 Product host** (powtarzalny build + gate + Studio/REPL)  
**Zasada nadrzędna:** **Z0** — Rust pisze od razu pod substrat (`native/karmazyn_substrate`)

---

## Co zostało wdrożone z recenzji enterprise

| # | Działanie | Status |
|---|-----------|--------|
| 1 | `kernel_boundary`: `karmazyn_backend` ∈ KERNEL | done |
| 2 | `karmazyn_io` → progi T przez `karmazyn_kernel` | done |
| 3 | `scripts/gate_product.ps1` / `.sh` | done |
| 4 | `Documents/install_product.md` | done |
| 5 | CI `.github/workflows/gate.yml` | done |
| 6 | Native `create_atom` + `KARMAZYN_STRICT_IDS` | done |
| 7 | Piaskownica `sandbox/` | done |
| 8 | Docs: plans, mapa Rust, recenzja, Stage1, Studio | done |
| 9 | I/O Stage1 + Studio SDL (mapa T tło) | done (sesja) |

---

## Jak zacząć pracę dzisiaj

```powershell
cd C:\Users\drwis\KarmazynOs

# 1) piaskownica
python sandbox/bootstrap_sandbox.py

# 2) gate
.\scripts\gate_product.ps1 -SkipLua

# 3) Product path
$env:PYTHONPATH = "$PWD;$PWD\software;$PWD\kernel;$PWD\native"
$env:KARMAZYN_SUBSTRATE = "native"
python software/karmazyn_boot.py
# lub
python software/karmazyn_studio.py
```

---

## Backlog (kolejność)

1. **Utrzymać G0 zielony** na każdym PR  
2. Domknąć lustro root vs software (jeden path)  
3. BootConfig (faza B planu)  
4. Tag **L1** po zielonym gate na czystej VM  
5. ISO / GRUB dopiero po L1  

Szczegóły: `Documents/build_deploy_plan.md`.

---

## Scope projektu (co jest / nie jest)

| Jest | Nie jest (jeszcze) |
|------|---------------------|
| Runtime host + Rust Store default | Bootowalny samodzielny OS |
| Matryca I/O Stage 1 | Serial/VESA bare-metal |
| Studio SDL | Enterprise multi-tenant |
| Plany L2–L4 | Obietnica „ISO w produkcji” |

---

## Właścicielstwo (robocze)

| Obszar | Path |
|--------|------|
| Substrat Rust | `native/karmazyn_substrate/` |
| Host / boot / I/O | `software/` |
| Plany / recenzje | `Documents/` |
| Piaskownica | `sandbox/work/` (local) |
