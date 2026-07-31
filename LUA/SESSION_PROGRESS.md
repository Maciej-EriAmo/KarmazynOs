# Postęp prac — karmazyn_lua (dla przyszłych sesji)

**Ostatnia aktualizacja:** 2026-07-31  
**Wersja:** **1.1.2** (production guest)  
**Workspace roboczy:** `C:\Users\drwis\LUA`  
**Monorepo git:** `C:\Users\drwis\KarmazynOs` (remote `origin` → `https://github.com/Maciej-EriAmo/KarmazynOs`)  
**Ostatni commit:** `7111d54` — *Release karmazyn_lua 1.1.2 production guest.* (pushed to `origin/main`)  
**Kernel (sibling):** `C:\Users\drwis\Kernel Karmazyn` (host edits + site-packages path)

> **Uwaga:** `C:\Users\drwis\LUA` **nie ma** `.git`. Commit/push idzie z **KarmazynOs** po `robocopy` workspace → `KarmazynOs/LUA`.  
> `Kernel Karmazyn\LUA` może być **niezsynchronizowany** — porównaj `__version__` przed pracą.

---

## Stan na dziś

| Gate | Wynik (1.1.2) |
|------|----------------|
| unit `_run_tests.py` | ~165 OK |
| kombajn | 97/97 |
| puc_subset | 13/13 |
| `release_1_1.py` | OK |
| host tools + lua_bin matrix | OK (idea = STUB note) |

### Co jest „production guest”

- Sandbox: brak ambient FS / C modules / bytecode  
- Host `karmazyn.*` (T skala 0..T_MAX, list_atoms = surface Φ)  
- debug subset, coroutine isyieldable/close  
- P0: GC bloków (`do`/`for`/…) + izolowany `eval_line`  
- P1: count gościa, __gc log, puc×13, reach roots  

### Dokumenty

| Plik | Treść |
|------|--------|
| `CONTRACT_1.1.md` | kontrakt skryptów |
| `RELEASE_1.1.0.md` | checklista release |
| `GAP_CLOSE_PLAN.md` | plan A–D (done) |
| `PRODUCT_REVIEW_1.1.0.md` | surowa recenzja (stara) |
| `PRODUCT_REVIEW_1.1.1.md` | po P0 |
| `PRODUCT_REVIEW_1.1.2.md` | po P1 — **aktualna ocena ~8.4/10** |
| `SESSION_PROGRESS.md` | ten plik |

### Bramka

```bash
cd C:\Users\drwis\LUA
python release_1_1.py
# monorepo:
cd C:\Users\drwis\KarmazynOs
python software/test_lua_release.py
```

---

## Co zostało do szlifu (kolejne sesje)

### Fala 1.1.3 (zalecana następna)

1. **puc_subset 13 → 30–50**  
2. **Docs** upvalue = model bąbla (CONTRACT już częściowo)  
3. **Sync** kanoniczna kopia: workspace → monorepo (i ewentualnie Kernel LUA)  

### Fala 1.1.4

4. Golden string/format/pack edge  
5. Dual number battery  
6. `__gc` policy + weak k/kv golden  

### Gdy boli skala

7. Performance: atom na pole / proxy hosta  

### OS (nie „Lua done”)

8. `generate_from_idea` prawdziwy vs matrix skip  
9. hologramy/agenci — feature complete  

### Świadomie NIE

- C modules, ambient FS, bytecode, pełny PUC 1:1  

Szczegóły: ostatnia odpowiedź „co pozostało do szlifu” + `PRODUCT_REVIEW_1.1.2.md`.

---

## Kluczowe fixy (pamięć techniczna)

| ID | Fix | Gdzie |
|----|-----|--------|
| extra_reach core aid | sid `"a12"` → `store._aid` | `evaluator._guest_extra_reach` |
| P0-1 block GC | `_push_live_env` / `_block_env` na do/if/for/… | `evaluator` |
| P0-2 eval_line | scope + `_ENV=G`, nie locale na G | `eval_line` |
| Host T 1.1 | T_MAX scale, no silent 0..1 (po recenzji: absolute) | `karmazyn_host` |
| list_atoms | surface Φ + proxy cache | `karmazyn_host` |
| count | graf gościa / 1024 | `collectgarbage("count")` |
| __gc errors | `[__gc error]` w `_out` | `gc_step` |

---

## Pliki poza `LUA/` (host)

- `KarmazynOs/software/karmazyn_host.py` (lub Kernel mirror)  
- `software/test_lua_release.py` — akceptuje 1.1.x + puc  
- `software/lua_bin_matrix.py` — idea STUB  
- `lua_bin/memviz.lua`, `ls.lua`, `cat.lua`, `top.lua`, `touch.lua`  

---

## Szybki start nowej sesji

1. Przeczytaj **ten plik** + `PRODUCT_REVIEW_1.1.2.md`.  
2. `cd C:\Users\drwis\LUA` → `python release_1_1.py`.  
3. Pracuj w workspace; **przed pushem** zsynchronizuj do `KarmazynOs`.  
4. Następna sensowna robota: **puc_subset rozbudowa** albo **sync monorepo + release notes**.
