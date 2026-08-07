# SESSION_CONTINUE — KarmazynOs (kontynuacja)

**Data:** 2026-08-07 (koniec sesji)  
**Repo Os:** `main` @ ok. **`5741598`** (+ KANON/SEAL/shell/lifecycle w historii)  
**DBase:** backend STRICT zsynchronizowany (`033914b`)  
**Holon:** `C:\Users\drwis\Karmin_Ae` → `python agent_boot.py --project Karmazyn`  
**Kanon:** [`KANON.md`](KANON.md) · uszczelnienie: [`SUBSTRATE_SEAL.md`](SUBSTRATE_SEAL.md)

---

## Model (nie gubić)

| | |
|--|--|
| **Król** | tylko **substrat** (A/B/T/reach) |
| **Minister** | DB, Holon, Studio, shell, języki — przez **szwy** |
| **Rust** | kości + wykonanie silnika |
| **Userspace** | klient; nie włada A/B (są niżej) |
| **Shell / ksub** | operator sys, nie wzorzec product |
| **Atom** | `(S, E, T)` — **S = sygnatura** |
| **Zamrożenie** | projekcja poza Store (nie = TOMB) |
| **TOMB** | zimny atom w jądrze; **vacuum** = zanik |

---

## Co domknięte w tej linii sesji

| Obszar | Stan |
|--------|------|
| kcc 0.6.1 + TB.4 P0–3 | pause (P4 nie gonić) |
| shell 0.3.2 + lifecycle T×reach | STAGE2 green |
| heat WRITE / strdup / dead code | fix |
| KANON król/minister/userspace | docs |
| SUBSTRATE_SEAL + STRICT | `KARMAZYN_SUBSTRATE_STRICT=1` |
| Karmin_DB | minister skarbu; `open_store` → native |

### Env uszczelnienia

```text
KARMAZYN_SUBSTRATE_STRICT=1
# golden only:
# KARMAZYN_ALLOW_PYTHON_SUBSTRATE=1
# KARMAZYN_SUBSTRATE=python
```

---

## Bramki

```powershell
cd C:\Users\drwis\KarmazynOs
.\native\stage1_verify.ps1
.\native\stage2_verify.ps1
.\toolchain\verify_kcc.ps1
```

---

## Next (gdy wrócisz)

1. **Opc.** product: STRICT default gdy native; CI grep `import Store` bokiem  
2. **Opc.** View / export JSON (projekcja user zone)  
3. **Opc.** dopisać do KANON § sygnatura S + zamrożenie vs TOMB (ustalone słownie)  
4. **Nie** TB.4 Phase 4 z inercji  
5. **Stop** — bramki zielone wystarczą  

---

## Untracked (nie commitować w torze A/B)

`out/`, `dist/`, bubble WIP, media w DBase  

---

*Sesja zamknięta w Holon (close + fact). Start: boot Karmazyn + KANON.md.*
