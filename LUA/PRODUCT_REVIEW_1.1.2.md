# Surowa recenzja — karmazyn_lua **1.1.2**

**Data:** 2026-07-31  
| Wersja | Score (gość Karmazyn) |
|--------|------------------------|
| 1.1.0 (przed P0) | **6.5 / B−** |
| 1.1.1 (P0) | **8.0 / B+** |
| **1.1.2 (P1 quality)** | **8.3–8.5 / B+** |

**Drop-in PUC Lua:** nadal **3/10** (celowo).

---

## 1. Werdykt

**1.1.2 to solidny production guest.**  
P0 domknięte w 1.1.1; P1 z recenzji (count, __gc diag, puc×13, reach roots, upvalue) domknięte w 1.1.2.

Nadal **nie** jest to „Lua kompletna”.  
**Jest** wiarygodnym gościem skryptowym KarmazynOS z uczciwym kontraktem i realnymi poprawkami po surowej recenzji.

**Ship: tak.**  
**Udawać PUC: nie.**

---

## 2. Co zrobiono od 1.1.1 → 1.1.2

| Issue | Status |
|-------|--------|
| `collectgarbage("count")` = cały Store | **Naprawione** — graf G + live envs, wynik w „KB” (n/1024) |
| `__gc` połyka błędy | **Naprawione** — `[__gc error] …` w `_out` |
| `_bubble_reachable` tylko G | **Lepsze** — G + roots + active_envs |
| `getupvalue` mylące (_ENV first) | **Lepsze** — pomija `_ENV` |
| puc_subset = 5 | **13** plików |
| matrix idea „vector from hologram” | **Nota STUB** |

Bramka: unit **165** · kombajn **97** · puc **13** · host · matrix · **RELEASE OK 1.1.2**.

---

## 3. Scorecard

| Kryterium | 1.1.1 | **1.1.2** | Komentarz |
|-----------|-------|-----------|-----------|
| Happy-path | 8 | **8** | stabilne |
| GC / bloki | 8 | **8.5** | count + reach + __gc diag |
| Sandbox | 9 | **9** | bez zmian |
| DX / API | 7 | **7.5** | upvalue mniej kłamie |
| Host | 7 | **7.5** | stub oznaczony |
| Głębokość testów | 7 | **8** | puc 13; wciąż nie 50+ |
| Uczciwość production | 8 | **8.5** | proces recenzja→fix działa |
| **Średnia** | **8.0** | **~8.4** | |

---

## 4. Co nadal jest słabe (P2 / dług)

| ID | Problem | Priorytet |
|----|---------|-----------|
| P2-1 | puc_subset 13 ≪ oficjalne lua-tests | średni |
| P2-2 | count to heurystyka grafu, nie bajty VM | niski |
| P2-3 | `__gc` error nie przerywa skryptu (tylko log) | niski/świadomy |
| P2-4 | dual number / format edge | średni |
| P2-5 | performance: atom na pole tabeli | średni (skala) |
| P2-6 | dwa drzewa LUA workspace/monorepo | organizacyjne |
| P2-7 | generate_from_idea nadal stub (teraz opisany) | feature OS |
| P2-8 | upvalues = model bąbla, nie sloty PUC | dokumentacja |

**Żaden z P2 nie dyskwalifikuje production guest.**

---

## 5. Co jest naprawdę dobre

1. Sandbox i granica host/gość.  
2. P0 naprawione i w teście (nested GC, eval_line).  
3. P1 nie zamiecione pod dywan — count, __gc, puc, nota stub.  
4. Proces: recenzja → lista → patch → bramka → kolejna recenzja.  
5. Pure-Lua ekosystem działa (json, inspect).

---

## 6. Jedno zdanie

**1.1.2 to dojrzały production guest w swoim zakresie: po dwóch turach surowej recenzji nie ma już milczącego GC ani kłamliwego count, a pozostały dług to jakość i skala — nie wiarygodność rdzenia.**
