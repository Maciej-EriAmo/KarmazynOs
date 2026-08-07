# Domknięcie obejść substratu (król bez uzurpatorów)

**Status:** living · **Data:** 2026-08-07  
**Powiązania:** [`KANON.md`](KANON.md) (król / minister), `karmazyn_backend.py`

---

## 1. Cel

**Jedyny magazyn prawdy stanu A/B/T/reach = substrat (preferencyjnie native Rust).**  
Wszystko inne = minister przez **szew** `open_store` / C ABI / rlib — nie drugi Store.

---

## 2. Wektory obejścia (dziś)

| # | Ścieżka | Ryzyko |
|---|--------|--------|
| V1 | `from karmazyn_substrate import Store` **bez** `open_store` | omija politykę backendu |
| V2 | cichy fallback `native` → Python gdy brak DLL | „myślałem że native” |
| V3 | `KARMAZYN_SUBSTRATE=python` w product | legalny rescue → uzurpacja gdy domyślne |
| V4 | `Store` w Pythonie z inną semantyką feature | dryf prawa |
| V5 | lokalne `dict` / AtomStore udające GC | drugi magazyn |
| V6 | Holon JSON jako „baza” bez świadomości mirror | mylenie SE z jądrem |
| V7 | dwa repo native (Os vs DBase) rozjechane | dwa ciała króla |

---

## 3. Poziomy uszczelnienia

| Poziom | Co | Status |
|--------|-----|--------|
| **S0** | KANON: król / minister | ✅ |
| **S1** | `open_store` = **jedyny** zalecany konstruktor product | ⚠ dyscyplina |
| **S2** | **`KARMAZYN_SUBSTRATE_STRICT=1`** — bez cichego fallbacku; python tylko z allow | ✅ w `karmazyn_backend` |
| **S3** | CI / grep: zakaz `from karmazyn_substrate import Store` poza testami/golden | 📋 |
| **S4** | Product API bez re-export surowego Store | 📋 |
| **S5** | Jedna binarka / jeden pin wersji native w Os+DBase | 📋 |
| **S6** | (daleko) uniemożliwienie importu Python Store w product wheel | 📋 |

---

## 4. STRICT (S2) — kontrakt

Env:

```text
KARMAZYN_SUBSTRATE_STRICT=1
# opcjonalnie w testach golden:
KARMAZYN_ALLOW_PYTHON_SUBSTRATE=1
KARMAZYN_SUBSTRATE=python
```

| Sytuacja | STRICT=0 (dziś soft) | STRICT=1 |
|----------|----------------------|----------|
| native dostępny, auto | native | native |
| native **brak**, auto | **cichy** Python | **RuntimeError** — zbuduj most |
| `SUBSTRATE=python` | Python | wymaga `ALLOW_PYTHON_SUBSTRATE=1` inaczej błąd |
| jawne `backend="python"` w kodzie | Python | to samo co env (allow) |

**Product / boot / Studio / Cynober:** w profilu produkcyjnym ustawiać STRICT=1.  
**Golden / compat tests:** ALLOW_PYTHON + ewentualnie SUBSTRATE=python.

---

## 5. S3 — reguła importów (do CI)

**Dozwolone w product:**

```python
from karmazyn_backend import open_store, backend_info
# lub
from karmazyn_kernel import open_store
s = open_store(thermal=True)
```

**Tylko testy / golden / bench:**

```python
from karmazyn_substrate import Store  # reference
```

**Zakaz w `software/` product (docelowo lint):**

- bezpośredni `Store()` z pure-Python bez allow  
- własny dict atomów z tick/gc na boku  

---

## 6. Ministrów nie zamykamy — zamykamy **uzurpatorów**

| Minister | Szew (OK) | Obejście (źle) |
|----------|-----------|----------------|
| Karmin_DB | `open_store` → native | własna baza bez Store |
| Holon | mirror API | Holon jako jedyny Store świata |
| Studio | open_store / kernel | lokalny dict „atomów” |
| Shell | rlib Store | — (to sys, OK) |
| C client | `ksub_*` | własny GC w C |

---

## 7. Checklista wdrożenia

- [x] S0 KANON król/minister  
- [x] S2 STRICT w `karmazyn_backend`  
- [ ] Boot/Studio: w product default STRICT=1 (gdy native available)  
- [ ] CI grep V1  
- [ ] Pin/sync native Os ↔ DBase  
- [ ] Document ALLOW tylko dla golden  

---

## 8. Jedna linia

**Zamykamy nie dostęp do jądra — zamykamy budowę drugiego jądra.**  
Ministrowie wołają króla przez szew; bez cichego „Python zamiast Rusta”, bez `Store()` bokiem w product.
