# KarmazynOs — start projektu (enterprise wave)

**Data startu fali:** 2026-07-31  
**Status L1:** domykane — `scripts/gate_product.ps1` + `scripts/dry_run_l1.ps1`  
**Zasada nadrzędna:** **Z0** — Rust pisze od razu pod substrat (`native/karmazyn_substrate`)  
**Kanon (co wolno twierdzić):** [`Documents/KANON.md`](Documents/KANON.md)

### Język (obietnice vs nośnik)

| Mówimy | Nie mówimy (dopóki L4) |
|--------|-------------------------|
| Product **host** runtime | „Samodzielny OS” / bootowalny Karmazyn |
| ISO GRUB dla kentry (marker serial) | „Mamy OS” / obraz do promptu `karmazyn>` |
| Studio SDL na hoście | „Desktop OS” |

---

## Co domknięte z listy „gorzej”

| # | Temat | Status |
|---|--------|--------|
| 1 | L1 gate + dry-run | `gate_product` + `dry_run_l1.ps1` |
| 2 | Plany ≠ egzekucja | banner na `grub_loader_plan.md`: PLAN ONLY |
| 3 | string id vs u32 | host `_id_alias` (logical → Store id) |
| 4 | Holon pamięć | osobny profil trwałości; digest/remember |
| 5 | Enterprise P0 | boundary, CI, install, sandbox |

---

## Jak zacząć pracę dzisiaj

```powershell
cd C:\Users\drwis\KarmazynOs

python sandbox/bootstrap_sandbox.py
.\scripts\gate_product.ps1 -SkipLua
.\scripts\dry_run_l1.ps1 -SkipGate   # lub pełny dry-run bez -SkipGate

$env:PYTHONPATH = "$PWD;$PWD\software;$PWD\kernel;$PWD\native"
$env:KARMAZYN_SUBSTRATE = "native"
python software/karmazyn_boot.py
# lub
python software/karmazyn_studio.py
```

---

## Backlog (kolejność) — zgodnie z planem Rust

1. Utrzymać G0 + dry_run_l1 zielone (`verify_rebuild` + gate: slab→substrate→shell→kcc)  
2. **Rust roadmap** — `Documents/rust_roadmap_tech.md` ✅  
3. **kentry F** — `boot/kentry` marker ELF ✅; QEMU serial ✅ (`boot/kentry/qemu_serial.ps1`, PVH bez płyty)  
4. **BootConfig** — `karmazyn_bootcfg.py` ✅ (faza B parser + :info)  
5. **ISO kentry + GRUB** ✅ (marker serial, `scripts/build_kentry_iso.ps1`); obraz produktu do promptu `karmazyn>` nadal później; **Store freestanding G** po alloc design  


Szczegóły: `Documents/build_deploy_plan.md` · `Documents/rust_roadmap_tech.md`.

---

## Scope projektu (co jest / nie jest)

| Jest (L1 host) | Nie jest (jeszcze) |
|----------------|---------------------|
| Runtime host + Rust Store default | Bootowalny samodzielny OS |
| Matryca I/O Stage 1 | Serial/VESA bare-metal |
| Studio SDL (opcjonalnie pygame) | ISO produktu do promptu `karmazyn>` |
| Plany L2–L4 na papierze | Twierdzenie „OS w produkcji” |

---

## Właścicielstwo (robocze)

| Obszar | Path |
|--------|------|
| Substrat Rust | `native/karmazyn_substrate/` |
| Host / boot / I/O | `software/` |
| Plany / recenzje | `Documents/` |
| Piaskownica | `sandbox/work/` (local) |
