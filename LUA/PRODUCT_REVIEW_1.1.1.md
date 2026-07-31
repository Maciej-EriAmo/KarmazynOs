# Surowa recenzja — karmazyn_lua **1.1.1** (powtórka)

**Data:** 2026-07-31  
**Poprzednia ocena (1.1.0 przed P0):** B− / ~6.5/10  
**Ta ocena (1.1.1):** **B+ / ~8.0/10** jako gość skryptowy Karmazyn  
**Jako drop-in Lua PUC:** nadal **3/10** (celowo)

---

## 1. Werdykt

**1.1.1 zasługuje na etykietę „production guest” w modelu Karmazyn** — pod warunkiem, że nie kłamiecie o zakresie.

Blokery z recenzji 1.1.0 (**P0-1 milczący GC w blokach**, **P0-2 brudzenie G przez eval_line**) są **naprawione i zmierzone**.  
Bramka release jest zielona. Produkt jest **wiarygodniejszy**, nie „idealny”.

---

## 2. Co się zmieniło względem poprzedniej recenzji

| Issue | 1.1.0 | 1.1.1 (zmierzono) |
|-------|-------|-------------------|
| `do local x; collectgarbage; return x` | **nil / korupcja** | **42** |
| `for` + local + GC | ryzyko | **OK (s=60)** |
| `eval_line`: `local z=9` potem `return z` | wyciek na G | **brak wycieku** (błąd/nil) |
| Global `g=3` między liniami | OK | **OK** |
| error: value vs traceback | częściowo | **value czysty; tb z chunk:line** |
| unit / kombajn / release | zielone (ślepe na P0) | zielone **z testami P0** |

To nie jest „marketing fix” — to realna zmiana semantyki GC i REPL.

---

## 3. Scorecard 1.1.1

| Kryterium | 1.1.0 | **1.1.1** | Komentarz |
|-----------|-------|-----------|-----------|
| Happy-path język | 8 | **8** | bez regresji |
| GC / bloki | **3** | **8** | P0-1 zamknięte; weak/__gc nadal uproszczone |
| Sandbox | 9 | **9** | bez zmian — siła produktu |
| DX / spójność API | 5 | **7** | eval_line = chunk semantics; upvalue model nadal inny niż PUC |
| Host surface | 7 | **7** | T-scale OK; stuby (idea) zostają |
| Testy głębokość | 6 | **7** | P0 w unit+kombajn; puc_subset nadal 5 plików |
| Uczciwość „production” | **4** | **8** | po P0 można mówić production *guest* |
| **Średnia ważona (Karmazyn)** | **6.5** | **~8.0** | |

---

## 4. Co jest dobre (utrzymać)

1. **Sandbox jako kontrakt**, nie wypadek.  
2. **Host / gość** — jasna granica; `karmazyn.*` nie udaje FS.  
3. **Happy-path + pure-Lua** (json, inspect) — realna użyteczność.  
4. **Kultura bramek** + CONTRACT + recenzja → poprawka → 1.1.1 (to jest dojrzały proces).  
5. **P0 zamknięte w kodzie**, nie w dokumentacji.

---

## 5. Co nadal jest słabe (bez owijania)

### P1 — nie blokuje ship, ale nie spać na tym

| ID | Problem | Ryzyko |
|----|---------|--------|
| **P1-1** | `puc_subset` = **5** plików | fałszywe poczucie „blisko PUC” |
| **P1-2** | `collectgarbage("count")` = cały Store | diagnostyka kłamie (~140+ przy pustym skrypcie) |
| **P1-3** | `__gc` połyka wyjątki (`except: pass`) | finalizer pada po cichu |
| **P1-4** | `_bubble_reachable` uproszczenie | weak/__gc edge case’y vs jądro |
| **P1-5** | Host stubs (`generate_from_idea`) w matrix „pass” | fałszywa funkcja OS |
| **P1-6** | `debug.getupvalue` = env bąbla, nie sloty PUC | mylące API (docs OK, API nadal pachnie) |
| **P1-7** | Dwa drzewa LUA (workspace vs monorepo) | dryf wersji |
| **P1-8** | `except Exception` w GC/host ścieżkach | twardość > observability |

### P2 — polish

- Dual number / format / pattern edge  
- Performance (atom na pole)  
- Głębsze linie we wszystkich error paths  
- top/nano skip — OK, byle docs nie obiecywały automatyki

### Poza zakresem (nie liczyć jako dług)

- C modules, ambient FS, bytecode, pełny lua-tests — **nie robić** w tym torze.

---

## 6. Bramka (stan teraz)

```
version = 1.1.1
unit OK (164)
kombajn 97/97
puc_subset 5/5
host OK
lua_bin 27 pass / 2 skip
RELEASE OK
```

**Interpretacja:** produkt nie jest „popsuty na znanych ścieżkach”.  
**Nadal nie znaczy:** „wszystkie semantyki Lua są domknięte”.

---

## 7. Czy to dobry produkt?

| Pytanie | Odpowiedź |
|---------|-----------|
| Ship jako domyślny gość KarmazynOS? | **Tak (1.1.1)** |
| Ship jako uniwersalna Lua? | **Nie** |
| Zaufać skryptom z `collectgarbage` + zagnieżdżonymi localami? | **Tak — to właśnie naprawiono** |
| Zaufać `eval_line` jak pełnemu plikowi między liniami z `local`? | **Nie — i dobrze: locale nie przechodzą; globale tak** |
| Ufać `collectgarbage("count")` / matrix idea? | **Nie bez zastrzeżeń** |

---

## 8. Rekomendacja

1. **Traktuj 1.1.1 jako production guest baseline.**  
2. **Następny sensowny release 1.1.2:** puc_subset ≥20, count metryka gościa, `__gc` nie połyka błędów w ciszy.  
3. **Nie wracaj** do C modules / ambient FS „dla zgodności”.  
4. **Synchronizuj** monorepo `Kernel Karmazyn/LUA` z workspace, jeśli to dwa copy.

---

## 9. Jedno zdanie

**1.1.0 obiecywało production za wcześnie; 1.1.1 naprawia to, co realnie dyskwalifikowało zaufanie (GC bloków + brudny REPL) — produkt jest w końcu uczciwie produkcyjny w swoim zakresie, z wciąż cienką siatką testów PUC i kilkoma kłamstwami diagnostycznymi do posprzątania w 1.1.2.**
