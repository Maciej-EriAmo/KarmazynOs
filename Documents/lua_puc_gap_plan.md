# Plan implementacji: bliżej PUC-Rio bez zmiany fizyki Karmazyn

**Pakiet:** `karmazyn_lua` 1.0.0 → linia **1.1.x** (opcjonalnie 1.2)

### Ostrzeżenie nadrzędne (nie paragraf „zakaz”)

Fizyka jądra (T × reach-GC × bąbel × brak ambient authority) to **warunek życia systemu**, nie „tabu dla formalności”.

> **Destabilizacja jądra = śmierć prawidłowego działania.**  
> Chcesz grzebać w fizyce (T, vacuum, reach, rooty, haki GC, granica gościa) — szykuj się na to, że system **przestanie działać poprawnie**: utrata pamięci, zombie, nieszczelny sandbox, losowy GC, śmierć sesji.  
> Nikt nie stoi z pałką „nie wolno”. **Konsekwencja jest fizyczna, nie administracyjna.**

Plan 1.1–1.2 **zakłada** pracę **nad** jądrem (gość Lua), nie **w** jądrze — bo to tańsza droga do zgodności z PUC-Rio przy żywym systemie.  
Wejście w `kernel/` jest możliwe, ale to **zmiana konstytucji**: osobna decyzja, osobny audyt, pełna świadomość ryzyka.

**Zakres (z listy):**

1. Pełniejszy `debug` (`getinfo`, lokale/upvalues — bezpiecznie)  
2. Twardsze integer/float + weak / `__gc`  
3. `string.dump` — **domyślnie nie** (sandbox)  
4. Patterny / `format` / `pack` edge case’y  
5. `coroutine.isyieldable` / `close`  
6. Oficjalny **subset** testów `lua-tests` (nie cały suite)

---

## 0. Kryteria zdrowia systemu (Definition of Done)

PR z tej listy **domyślnie** utrzymują żywą fizykę. Jeśli celowo ją ruszasz — oznacz PR jako **KERNEL-PHYSICS**, uzasadnij i zaakceptuj, że możesz zabić system.

| # | Kryterium zdrowia | Jak weryfikować | Jeśli złamiesz… |
|---|-------------------|-----------------|-----------------|
| P1 | Gość bez ambient FS / `dofile` / `loadfile` / `os.execute` / system `package.path` | `III_GuestContract` | nieszczelna piaskownica = kompromitacja modelu |
| P2 | Tabela = Bubble; życie = **reach × T** | II_Architecture | „pamięć Lua” rozjeżdża się z jądrem → zombie / utrata stanu |
| P3 | Haki reach: `register_*` (`name=guest`), bez stackowania | `hook_names()` | GC kłamie → śmierć lub wycieki |
| P4 | `debug.*` nie jest backdoorem do Store / pathów hosta | kontrakt debug | „diagnostyka” = eskalacja → koniec zaufania do sesji |
| P5 | `collectgarbage` mapuje na settle + weak/`__gc`, **nie** omija vacuum | test root vs sierota | sztuczny GC niszczy fizykę T |
| P6 | `string.dump` / `load b` nie w gościu (default) | testy negatywne | bytecode omija audyt hosta |
| P7 | `test_lua_release.py` zielony | bramka | regresja 1.0 |

**Domyślna ścieżka planu:** projekcja semantyki Lua **na** istniejący substrat.  
**Ścieżka ryzykowna:** diff w `kernel/` — dozwolona świadomie, z ostrzeżeniem o końcu prawidłowego działania.

---

## 1. Architektura warstw (kontekst planu)

```
┌──────────────────────────────────────────────────────────────┐
│  Programista Lua (skrypt / tool)                             │
│  widzi: język + stdlib + debug* + karmazyn.*                 │
├──────────────────────────────────────────────────────────────┤
│  karmazyn_lua 1.x — gość                                     │
│  evaluator / values / liby  |  debug facade (read-only)      │
├──────────────────────────────────────────────────────────────┤
│  Host (boot, CLI, project searcher) — jedyny FS              │
├──────────────────────────────────────────────────────────────┤
│  karmazyn_kernel / Store — FIZYKA (T, reach, bąble)          │
│  Grzebanie tu = ryzyko śmierci systemu (ostrzeżenie, nie tabu)│
└──────────────────────────────────────────────────────────────┘
```

---

## 2. Fazy implementacji (kolejność)

### Faza A — Fundament diagnostyki i reguł (niskie ryzyko fizyki)

**Cel:** lepszy debug + coroutine 5.4 bez C/FS.

| PR | Zakres | Pliki (orientacyjnie) | Testy | Ryzyko fizyki |
|----|--------|------------------------|-------|----------------|
| **A1** | `debug.getinfo` (subset levels/options) | `evaluator.py` | unit: source, name, what, nups | niskie |
| **A2** | `debug.getlocal` / `setlocal` (tylko ramki Lua; **bez** setlocal na upvalues hosta) | `evaluator.py`, `values.py` | unit + pcall | średnie (mutacja locale) |
| **A3** | `debug.getupvalue` / `setupvalue` (tylko `LuaFunction`) | j.w. | unit | średnie |
| **A4** | `coroutine.isyieldable`, `coroutine.close` (5.4) | `evaluator.py`, `LuaThread` | unit | niskie |
| **A5** | Kontrakt: lista dozwolonych kluczy `debug.*`; zakaz escape | `test_lua.py` III | contract | — |

**Poza A (na razie):** `debug.sethook`, `getregistry`, `debug.debug`, dostęp do C stack / Python frames.

**getinfo — dozwolone pola (v1):**  
`source`, `short_src`, `linedefined`, `lastlinedefined`, `what` (`Lua`/`C`/`main`), `name`, `namewhat`, `nups`, `currentline` (gdy dostępne z `_cur_line` / chunk).  

**Zakazane w getinfo/debug:**  
ścieżki absolutne hosta (tylko chunkname `@rel` / `=[C]`), id atomów Store, `repr` obiektów jądra.

**setlocal/setupvalue — reguła fizyki:**  
wolno mutować wartości w ramach Lua; **nie wolno** przez debug odłączać rootów Store, kasować bąbli, zmieniać T atomów jądra.

---

### Faza B — Integer / float + weak + `__gc` (wysoka wartość, kontrola fizyki)

| PR | Zakres | Uwagi fizyki |
|----|--------|----------------|
| **B1** | Spójny model int/float: `math.type`, operatory, `//`, bitowe, porównania | bez zmiany Store; tylko values/evaluator |
| **B2** | Tabela testów „dual number” (jak 5.3/5.4) | regresja |
| **B3** | `__mode` k/v — pełniejsze czyszczenie przy `collectgarbage` / settle | **mapowanie na reach**, nie osobny heap GC omijający T |
| **B4** | `__gc` — kolejność finalizacji, jednokrotność, błędy w finalizerze | finalizer **nie** może reanimować poza reach bez root; inaczej łamie P2 |
| **B5** | `collectgarbage("count"|"step"|"collect"|"isrunning"|…)` — subset | `collect` = weak clear + __gc + `store.settle(N)` **bez** force-delete rootów |

**Reguła B (ostrzeżenie fizyki):**

> Słabość i finalizacja **bezpiecznie** żyją jako warstwa gościa **na wierzchu** reach-GC.  
> Osobny „Lua GC niezależny od T/reach” = konkurencyjna fizyka → system przestaje być Karmazynem (niespójna śmierć obiektów, utrata TOMB, dziury w piaskownicy).  
> Jeśli to zrobisz, nie dziw się, że „wszystko się sypie”.

---

### Faza C — string patterns / format / pack (niskie ryzyko fizyki)

| PR | Zakres |
|----|--------|
| **C1** | Audit `_lua_pattern.py` vs manual 5.4: `%b`, `%f`, captures, empty matches |
| **C2** | `string.format`: szerokości, precyzje, `%q`, `%a`/`%A` (opcjonalnie), błędy jak Lua |
| **C3** | `string.pack` / `unpack` / `packsize`: endian, alignment, `z`, `s`, `c`, `x`, błędy size |
| **C4** | Testy golden z wybranych `strings.lua` / `pm.lua` (po adaptacji) |

**string.dump (pkt 3 listy):**

| Opcja | Decyzja 1.x |
|-------|-------------|
| **Default** | **NIE implementować** w gościu |
| Alternatywa host-only | Host może serializować źródło (już ma pliki) — nie bytecode |
| `load(chunk, name, "b")` | **zostaje odrzucane** (już jest) |

W planie implementacji: jawny test „dump/binary forbidden” + wpis w Known limits.  
**Nie otwierać bytecode** — omija audyt chunków i model piaskownicy.

---

### Faza D — Subset oficjalnych `lua-tests`

| PR | Zakres |
|----|--------|
| **D1** | Szkielet `LUA/puc_subset/` + runner `software/run_puc_subset.py` |
| **D2** | Manifest `puc_subset.toml` / `.json`: plik → status (`pass` / `skip` / `adapt`) |
| **D3** | Pierwsza paczka: arytmetyka, tabele, string podstawowy, coroutine podstawowy |
| **D4** | Skip lista: wszystko co wymaga `io` plików, `os.execute`, `debug` pełnego, `loadfile`, C, UTF-8 edge z FS |
| **D5** | Integracja opcjonalna: `test_lua_release.py --with-puc` (nie blokuje 1.0 gate domyślnie; blokuje 1.1) |

**Źródło testów:** oficjalne `lua-tests` (licencja MIT) — **skopiować wybrane pliki** z atrybucją, nie cały tree.  
**Adaptacja:** preambuła hosta ustawia `_VERSION`, mock `print`, brak `dofile` → inline lub `load` ze stringa wstrzykniętego przez runner.

**Zasada:** fail w `pass`-suite = regresja; `skip` musi mieć powód w manifeście (sandbox / not implemented).

---

## 3. Harmonogram (orientacyjny)

| Faza | Czas | Milestone |
|------|------|-----------|
| A1–A5 | 1–2 tyg. | `1.1.0-debug` — debug subset + coroutine 5.4 |
| B1–B5 | 2–3 tyg. | `1.1.0` lub `1.2.0` — numbers + weak/gc gościa |
| C1–C4 | 1–2 tyg. | string fidelity ↑ |
| D1–D5 | równolegle od A/C | puc_subset CI optional → required w 1.2 |

**Nie łączyć B4 (__gc) z refaktorem jądra w jednym PR** — bo wtedy nie da się oddzielić „sypie się gość” od „zabiłem fizykę”. Osobny PR, osobny review pod P2/P5, jawna etykieta KERNEL-PHYSICS jeśli ruszasz Store.

---

## 4. Kryteria akceptacji per faza

### A (debug + coroutine)

- [ ] `debug.getinfo(1, "nSl")` działa na funkcji Lua  
- [ ] `getlocal`/`getupvalue` nie wyciekają poza funkcje Lua  
- [ ] `setupvalue` nie psuje reach (test: upvalue table bound → survives settle)  
- [ ] `coroutine.isyieldable()` / `close` zgodne z 5.4 w happy path  
- [ ] `type(debug.getregistry)` == nil **lub** registry **bez** Store  

### B (numbers + weak + gc)

- [ ] Suite dual-number bez regresji bitowych/`//`  
- [ ] Weak keys: po utracie reach + collectgarbage wpis znika  
- [ ] `__gc` wołane raz; błąd w finalizerze nie rujnuje Store  
- [ ] Rooted table **nie** dostaje vacuum mimo `collectgarbage("collect")`  

### C (string)

- [ ] Wybrane testy pattern/format/pack zielone  
- [ ] `string.dump` nie istnieje lub error „not supported”  
- [ ] `load(..., "b")` nadal nil+msg  

### D (puc subset)

- [ ] ≥ N plików `pass` (cel startowy: 5–10 małych)  
- [ ] Manifest skip z uzasadnieniem sandbox/fizyka  
- [ ] Runner nie wymaga zapisu na FS gościa  

---

## 5. Kolejność PR (szczegółowa lista)

1. **PR-A1** `debug.getinfo` + testy + kontrakt pól  
2. **PR-A4** `coroutine.isyieldable` + `close` (szybkie, niezależne)  
3. **PR-A2/A3** get/set local & upvalue + test reach  
4. **PR-A5** kontrakt debug (brak escape)  
5. **PR-B1/B2** integer/float hardening  
6. **PR-B3/B4/B5** weak + __gc + collectgarbage mapowanie  
7. **PR-C*** string fidelity (może iść równolegle do B1)  
8. **PR-D1** runner + 3 pierwsze pliki subset  
9. **PR-D*** rozszerzanie manifestu  

**string.dump:** tylko dokument „wprost nie robimy” + testy negatywne (nie PR implementacyjny).

---

## 6. Ryzyka

| Ryzyko | Mitygacja |
|--------|-----------|
| Debug = backdoor do jądra | whitelist pól; zero Store w userdata |
| __gc reanimuje świat poza reach | finalizer tylko Lua; po __gc ponowny settle; brak set_root z gościa |
| Weak tables vs T | clear weak przy collect **i** przy vacuum; nie trzymać extra roots |
| puc-tests wymagają io | skip + adapt loader hosta |
| Scope creep „pełna 5.5” | milestone 1.1/1.2 = lista A–D, nie cały manual |
| „Poprawię GC w kernel przy okazji string.pack” | mieszanie warstw → nie da się zdiagnozować; system umiera po cichu |

---

## 7. Poza domyślnym torem (świadomy wybór ryzyka)

Te rzeczy **nie są „zakazane paragrafem”** — są **poza bezpieczną ścieżką 1.1**, bo psują model albo fizykę:

- C API / `userdata` C / `package.loadlib`  
- `io` na prawdziwy FS z gościa  
- `os.execute` / shell  
- bytecode / `string.dump` w gościu  
- przepisanie reguł T, vacuum, retained TOMB „żeby było jak w Lua”

Jeśli idziesz w to: **szykuj się na koniec prawidłowego działania**, pełny audyt jądra i brak gwarancji, że KarmazynOS nadal jest KarmazynOS.

---

## 8. Definition of Done całego toru

- Fazy A+B+C+D w stanie „pass” wg §4  
- `test_lua_release.py` zielony  
- Nowy gate opcjonalny `run_puc_subset.py` z rosnącym `pass`  
- Dokument [lua_arch_for_programmers.md](lua_arch_for_programmers.md) zaktualizowany o debug/numbers  
- Domyślnie **brak** diffu `kernel/` w PR gościa; każdy diff jądra = etykieta **KERNEL-PHYSICS** + akceptacja ryzyka śmierci systemu  

---

*Plan dla programistów i agentów implementujących 1.1.x.  
Fizyka nie jest zakazana — jest **śmiertelnie wrażliwa**.*
