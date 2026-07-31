# Surowa recenzja produktu — karmazyn_lua **1.1.0**

**Data:** 2026-07-31  
**Werdykt (stan recenzji):** bramka zielona ≠ produkt dojrzały.  
**Ocena ogólna (przed P0):** **B− / 6.5/10** jako *gość skryptowy Karmazyn*.  
**Po 1.1.1 (P0-1/P0-2):** cel **~8/10** na ten zakres — patrz CHANGELOG 1.1.1.  
**Jako „Lua produkcyjna uniwersalna”:** **3/10** (i słusznie nie cel).

---

## 1. Executive summary

1.1.0 jest **użytecznym, celowo ograniczonym gościem** z dobrą architekturą sandboxa i realnymi testami.  
Marketingowo „production” jest **przedwczesne** w kilku miejscach: milczące uszkodzenia stanu po GC, zanieczyszczenie `G` przez `eval_line`, cienki puc_subset, i host/tools, które niedawno kłamały na skali T.

**Nie odrzucać 1.1.0.**  
**Nie sprzedawać go jako „gotowe jak PUC”.**  
**Zamknąć 3–5 bugów P0 zanim hasło „production” będzie uczciwe.**

---

## 2. Co jest naprawdę dobre (nie odejmować)

| Obszar | Ocena | Dlaczego |
|--------|-------|----------|
| Sandbox / zero ambient authority | **A** | Brak FS/shell/C z gościa — to *cecha*, nie dziura |
| Montaż na Store / φ / caps | **A−** | Spójny model Karmazyn, nie „interpreter obok OS” |
| Metatabele / multi-value / bitops | **B+** | Solidny podzbiór; unit + kombajn trzymają |
| Pure-Lua z sieci (json, inspect) | **B+** | Realny dowód użyteczności |
| Kierunek hosta `karmazyn.*` | **B** | Dobra granica host/gość (po naprawie T i list_atoms) |
| Kultura bramek | **B** | unit + kombajn + puc + host + matrix w jednym miejscu |
| Dokumentacja kontraktu 1.1 | **B** | CONTRACT mówi wprost czego nie ma |

To nie jest hobby-parser. To jest **świadomy produkt z granicami**.

---

## 3. Werdykt po warstwach

### 3.1 Poprawność języka — **B**

- Arytmetyka, tabele, coroutine podstawowe, string pack: wyglądają dobrze.  
- **puc_subset = 5 plików** to **teatr regresji**, nie sieć bezpieczeństwa. PUC-Rio ma setki; wy 5.  
- Edge case’y string patterns / format / dual number: pokrycie **cienkie**.

### 3.2 Pamięć / GC — **D+ (najsłabsze ogniwo)**

**Krytyczne:**

1. **`extra_reach` obejmuje tylko ramki wywołań (`_active_envs`), nie bloki `do`/`for`/`if`.**  
   Locale zagnieżdżonego bloku mogą **zniknąć po `collectgarbage`** bez błędu albo ze „undeclared global”.

   Zmierzone:

   ```lua
   do
     local x = 42
     collectgarbage("collect")
     return x   -- wynik: nil (milcząca korupcja), nie 42
   end
   ```

   To jest **bug produkcyjny**, nie nit. Każdy skrypt z `do … local … collectgarbage` jest zagrożony.  
   Testy omijają to przez trzymanie locale na scope chunka/funkcji — **łatwizna testowa**.

2. **`_bubble_reachable` jest uproszczeniem** (BFS z G + env_of). Może kłamać względem prawdziwego reach jądra → weak/`__gc` w edge case’ach.

3. **`__gc` połyka wyjątki** (`except Exception: pass`) — finalizer, który pada, ginie po cichu.

4. **`collectgarbage("count")` = `len(store.atoms())`** — liczy **cały heap** (w tym silnik `aN`), nie „pamięć Lua użytkownika”. Narzędzia diagnostyczne będą kłamać.

### 3.3 API / DX — **C+**

1. **`eval_line` wykonuje locale na `G`.**  
   Zmierzone: `local z=9` zostaje widoczne w kolejnej linii jako `z`.  
   To **zanieczyszcza globalne środowisko REPL** i psuje intuicję Lua.  
   `debug.getupvalue` na domknięciu z `eval_line` widzi **globalne builtin’y** (print, type…), nie upvalue użytkownika.

2. **Dwa światy: `eval_line` vs `run_source`.**  
   Testy i narzędzia mieszają je — produkt jest niespójny w głowie użytkownika.

3. **Upvalues ≠ PUC.** Dokumentujemy to, ale API `debug.getupvalue` **sugeruje** zgodność, której nie ma. To jest **API smell**.

### 3.4 Host / tools — **B−**

- Naprawa skali T i cache proxy: **dobrze, ale spóźniona** — wcześniej tools pokazywały TOMB przy „ciepłych” atomach.  
- `list_atoms` filtr `a\d+` + rejestr Φ: OK, ale **kruchy** (użytkownik `create_atom("a12")` jest w konflikcie z silnikiem).  
- Proxy hosta nadal alokuje bąble w Store (cache łagodzi, nie usuwa problemu).  
- `generate_from_idea` — placeholder; tools go używają — **fałszywa funkcjonalność**.  
- hologramy/agenci — stub sesji; matrix „pass” **nie znaczy „działa w produkcji OS”**.

### 3.5 Bezpieczeństwo / sandbox — **A−**

- Celowo brak C/FS/shell: **mocne**.  
- `string.dump` zabroniony: **mocne**.  
- Ryzyko: host API zbyt szeroki w przyszłości; debug setlocal/setupvalue to **mutacja stanu** (akceptowalne, ale dokumentować).  
- `except Exception` w wielu miejscach: **twardość hosta tak, observability nie**.

### 3.6 Jakość release / marketing — **C**

- „Production guest” przy milczącym GC bug w blokach: **przesada**.  
- Bramka zielona: **dobra**, ale nie wykrywa (1).  
- README wcześniej 1.0 vs kod 1.1 — naprawione, ale pokazuje pośpiech.  
- `puc_subset` 5 plików w bramce: **fałszywe poczucie bezpieczeństwa**.

---

## 4. Ranking problemów (surowo)

### P0 — napraw przed dumnym „production” (blokery wiarygodności)

| ID | Problem | Skutek | Fix |
|----|---------|--------|-----|
| **P0-1** | Nested block locales giną / stają się nil po GC | milcząca korupcja skryptów | `_active_envs` = **cały łańcuch żywych env** (call + do/for/if), nie tylko call |
| **P0-2** | `eval_line` sika po `G` localami | REPL i testy kłamią; wycieki stanu | osobny scope chunka na linię (jak `run_source`) albo czyszczenie |
| **P0-3** | Brak testu regresji na P0-1 | bug wróci | `test_nested_block_locals_survive_gc` **musi padać dziś, przechodzić po fix** |

### P1 — produkt twardy (1.1.1 / 1.1.2)

| ID | Problem | Fix |
|----|---------|-----|
| **P1-1** | puc_subset za mały | 20–40 plików + manifest skip z powodami |
| **P1-2** | `collectgarbage("count")` mylący | osobna metryka gościa vs `store.stats` |
| **P1-3** | `__gc` połyka błędy | log do hosta / drugi wynik / debug |
| **P1-4** | `_bubble_reachable` uproszczenie | zbliżyć do reach jądra lub nie udawać full weak |
| **P1-5** | Host `generate_from_idea` placeholder | usunąć z „pass” matrix albo oznaczyć stub |
| **P1-6** | API debug upvalue mylące | docs + ewentualnie `debug.upvalueid` honesty / nups=env size |

### P2 — polish / długi ogon

| ID | Problem |
|----|---------|
| **P2-1** | Dual number / format / pattern edge |
| **P2-2** | Spójne linie we wszystkich ścieżkach błędu (nie tylko error()) |
| **P2-3** | Performance: alokacja atomów na każde pole tabeli |
| **P2-4** | Dwa katalogi LUA (workspace vs monorepo) — ryzyko dryfu |
| **P2-5** | top/nano skip OK, ale man/docs niech nie obiecują automatyki |

---

## 5. Co bramka **nie** łapie (ważne)

Zielone:

- unit 162  
- kombajn 95  
- puc 5  
- host + matrix  

**Nie łapie:**

- milczącego `x=nil` po GC w `do`  
- zanieczyszczenia `G` w REPL  
- zgodności z prawdziwym `lua-tests`  
- semantyki weak kluczy vs wartości w edge case’ach  
- obciążenia (duże tabele, głębokie call)  
- spójności workspace `C:\Users\drwis\LUA` vs `Kernel Karmazyn\LUA`

**Wniosek:** bramka mierzy **„nie zepsuliśmy znanych ścieżek”**, nie **„produkt jest twardy”**.

---

## 6. Ocena „czy to dobry produkt?”

### Tak, jeśli:

- Gość skryptowy w OS z piaskownicą.  
- Tools lua_bin + pure-Lua logika.  
- Host trzyma FS i politykę.  
- Autorzy czytają CONTRACT_1.1.

### Nie, jeśli:

- Obiecujecie „drop-in Lua 5.5”.  
- Ktoś polega na `collectgarbage` + zagnieżdżonych localach jak w PUC.  
- Ktoś buduje długi REPL na `eval_line` bez izolacji scope.  
- Ktoś ufa `list_atoms` / `get_resources` jako „pamięć aplikacji” bez zrozumienia Store.

---

## 7. Rekomendacja produktowa (twarda)

1. **Natychmiast (przed marketingiem 1.1.0 production):**  
   - Fix **P0-1** (active envs dla bloków).  
   - Fix **P0-2** (`eval_line` scope).  
   - Testy, które **dziś padają**, po fixie przechodzą.  
   - Patch **1.1.1** albo wstrzymaj etykietę „production” na README.

2. **Potem 1.1.2:** puc_subset ×4–8, count metryka, `__gc` observability.

3. **Nie róbcie:** C modules, ambient FS, udawania pełnego PUC — to zniszczy to, co jest wartością produktu.

---

## 8. Scorecard

| Kryterium | Score | Komentarz |
|-----------|-------|-----------|
| Poprawność happy-path | 8/10 | silne |
| Poprawność edge (GC/bloki) | 3/10 | **czerwone** |
| Sandbox / bezpieczeństwo modelu | 9/10 | celowa siła |
| DX / spójność API | 5/10 | eval_line vs run_source |
| Host surface | 7/10 | po fix T; stuby zostają |
| Testy / bramka | 6/10 | szeroko, nie głęboko |
| Dokumentacja kontraktu | 8/10 | dobre |
| Uczciwość „production” | 4/10 | za wcześnie bez P0 |

**Średnia ważona (produkt Karmazyn): ~6.5/10.**  
**Po P0-1/P0-2: realnie ~8/10** na ten zakres.

---

## 9. Jedno zdanie na koniec

**Macie dobry kierunek i solidny szkielet; najgorsze, co możecie zrobić, to ogłosić „production” przy milczącej korupcji locale po GC i udawać, że 5 plików puc_subset to tarcza.**  
Naprawcie P0, zaostrzcie testy, wtedy 1.1 będzie produktem, z którego można być dumnym — nie tylko bramką, która świeci na zielono.
