# Różnice architektoniczne: PUC-Rio Lua vs `karmazyn_lua`

**Dla programistów** piszących skrypty i narzędzia na KarmazynOS.  
**Wersja gościa:** 1.0.0+ · **Substrat:** `karmazyn_kernel` (T × reach-GC × Bubble)

---

## 1. Jednym zdaniem

**PUC-Rio** = interpreter C z heapem Lua, plikami i (opcjonalnie) C modules.  
**karmazyn_lua** = język Lua-podobny, którego **wartości żyją w fizyce Karmazyn** (atomy, bąble, temperatura, osiągalność). Host (Python/boot) jest jedynym mostem do świata zewnętrznego.

Nie oczekuj `lua.exe` 1:1. Oczekuj **semantyki skryptowej** + **gwarancji piaskownicy**.

---

## 2. Mapa pojęć

| Pojęcie Lua (PUC-Rio) | Odpowiednik Karmazyn | Uwaga |
|----------------------|----------------------|--------|
| Tabela | **Bubble** (+ pola jako atomy/wiązania) | GC nie jest mark-and-sweep „czystego Lua” |
| Globalne `_G` / `_ENV` | Bubble-korzeń sesji (`set_root`) | Utrata reach + zimno → vacuum |
| Domknięcie / upvalue | Bubble env + hak `env_of` | Rejestr `register_env_of(name="guest")` |
| Stack call | Ramki + `extra_reach` | Locale chronione w trakcie call |
| `require` + `package.path` | preload / memory / **project host** | Dysku szuka **host**, nie gość |
| `io` / pliki | Wirtualne IO sesji **lub** host tools | Brak `io.open` na FS |
| `os.execute` | **Brak** | Cel: zero ambient authority |
| C `userdata` / `.so` | **Brak** | Substrat Python/Rust, nie C API Lua |
| `debug` pełny | Subset + whitelista | Nie ujawnia jądra |
| GC `collectgarbage` | weak/`__gc` gościa + **settle** jądra | Nie omija T/reach |

---

## 3. Fizyka: ostrzeżenie, nie regulamin

Nikt nie „zakazuje” ci grzebać w jądrze.  
**Destabilizacja fizyki = śmierć prawidłowego działania systemu.**

Jeśli ruszasz T, vacuum, reach, rooty, haki GC albo dajesz gościowi ambient authority — szykuj się na to, że:

- sesje zaczynają gubić stan albo trzymać zombie,  
- GC kłamie,  
- piaskownica przestaje być piaskownicą,  
- „Karmazyn” staje się zwykłym interpreterem z dziurami.

Programista skryptów i domyślna linia stdlib **pracują na** fizyce, nie **przeciw** niej. Obowiązuje (jako warunek życia, nie tabu):

### 3.1 Temperatura (T)

- Atomy stygną; użycie ogrzewa.  
- **KIEDY** coś może stać się kandydatem do usunięcia — decyduje T (i progi HOT/WARM/COLD/TOMB).

### 3.2 Osiągalność (reach)

- **CZY** wolno usunąć — decyduje graf: korzenie, parent bąbli, `env_of`, `extra_reach`.  
- Zimny + nieosiągalny → **vacuum**.  
- Zimny + osiągalny → **retained TOMB** (retencja, nie „magiczne nieśmiertelne”).

### 3.3 Bąbel = granica

- Sesja gościa = bąbel(-e) + polityka φ/caps.  
- **Brak** ambient FS, shell, C modules z gościa.

### 3.4 Host ma władzę, gość ma język

```
Host (boot, CLI, project searcher, karmazyn_host)
        │  wpuszcza źródła, IO, tools
        ▼
Gość Lua  ──eval──►  wartości na Store
        │
        ▼
Fizyka jądra (bez wyjątków z debug/collectgarbage)
```

**Wniosek dla kodu:**  
`debug`, `collectgarbage`, weak, `__gc` powinny **obserwować i porządkować warstwę Lua**.  
Jeśli pozwolą na `set_root` z gościa, dysk, bytecode albo heap poza reach — to nie „feature”, to **strzał w fizykę**. System może dalej „coś robić”, ale nie będzie już wiarygodnym Karmazynem.

---

## 4. Jak pisać programy (praktyka)

### 4.1 Jak w Lua…

```lua
local t = {1, 2, name = "x"}
function f(a, b) return a + b, a * b end
local x, y = f(2, 3)
for k, v in pairs(t) do ... end
setmetatable(o, { __index = proto })
```

### 4.2 Inaczej niż w PUC-Rio

| Chcesz | W PUC-Rio | Na Karmazyn |
|--------|-----------|-------------|
| Wczytać plik `.lua` | `dofile` / `require "x"` z path | host: `run_lua.py` / `:run` / `require` po montażu projektu |
| Moduł z dysku | `package.path` | katalog projektu / `package.preload` / memory buffer edytora |
| Plik danych | `io.open` | `karmazyn.fs` (mini, sesja) lub tool hosta — **nie** pełny FS |
| Proces OS | `os.execute` | **niedostępne** |
| Debug produkcyjny | `debug.getinfo` pełny | subset (plan 1.1); bez wnętrza Store |
| Trwałość po restarcie | plik / DB | bąble-korzenie / consolidate / światy hosta — nie „plik obok skryptu” |

### 4.3 Narzędzia OS

```text
karmazyn> :tool ls
```

Skrypty w `lua_bin/` wołają **`karmazyn.*`** (host API 1.0).  
To nie jest stdlib PUC-Rio — to **API systemu**.

---

## 5. Model wartości (dla implementatorów)

| Typ Lua | Reprezentacja |
|---------|----------------|
| nil | `None` |
| boolean | `bool` |
| number | `int` / `float` (dual — twardnieje w 1.1) |
| string | `str` |
| table | `Bubble` |
| function | `LuaFunction` (env = Bubble) |
| thread | `LuaThread` |
| userdata | **brak** (C) |

Metatabele: pola `__index`, `__newindex`, arytmetyka, `call`, `eq`, `len`, `tostring`, … na Bubble.

**GC:**  
osiągalność z G + env domknięć + ramki; temperatura atomów na substracie.  
Weak/`__gc` (rozwój 1.1) = **warstwa gościa**, nie drugi GC.

---

## 6. `require` i searchery (ważne)

Kolejność (1.0):

1. **preload** — tools / `lua_bin` jako preload  
2. **memory** — bufory edytora (`put_buffer`)  
3. **project** — pliki pod rootem projektu (host czyta)

**Nie ma** `package.path` w stylu Uniksa.  
Bez projektu `lua_bin` **nie** staje się `ev.project` (tylko preload) — unikamy mylenia tools z aplikacją.

---

## 7. Debug — kontrakt (1.0 dziś / 1.1 plan)

| Dziś (1.0) | Plan 1.1 |
|------------|----------|
| `debug.traceback` (uproszczony) | + `getinfo`, `getlocal`/`setlocal`, `getupvalue`/`setupvalue` (subset) |

**Zawsze zakazane:**

- ujawnianie `Store`, atom id jądra, pathów absolutnych hosta,  
- `getregistry` z dostępem do wnętrza,  
- hooki pozwalające na mutate fizyki T/root.

---

## 8. Błędy i chunkname

- Preferowane: `@rel/path.lua:line:col: message` (parse mocny).  
- Runtime: nazwy ramek + częściowo linie (`_cur_line`).  
- Nie zakładaj numerów linii jak w `luac -l` / pełnym debug info z bytecode.

---

## 9. Caps / φ

Sesja może dostać **caps** (`default` / `strict` / `compute` / …):  
które liby std (`math`, `os`, …) wolno załadować.  

To **polityka sesji**, nie flaga PUC-Rio.  
`strict` bez `os` = twardsza piaskownica.

---

## 10. Checklista dla PR „bliżej PUC-Rio”

Zanim zmergujesz feature z listy debug/numbers/string/coroutine/tests:

1. Czy gość nadal bez FS/shell/binary load (albo wiesz, że otwierasz dziurę)?  
2. Czy reach × T nadal decyduje o życiu tabel?  
3. Czy haki to `register_*` a nie ciche nadpisanie `_env_of` ze stackowaniem?  
4. Czy debug nie jest backdoorem do jądra?  
5. Czy `test_lua_release.py` zielony?  
6. Czy jest diff w `kernel/`? Jeśli tak — etykieta **KERNEL-PHYSICS**, audyt, akceptacja: *może zabić system*.

Jeśli łamiesz 1–5 przez pomyłkę → **stop i popraw**.  
Jeśli łamiesz świadomie fizykę → nie „stop bo zakaz”, tylko **świadomy pogrzeb gwarancji**.

---

## 11. Szybkie FAQ

**Q: Czy mogę polegać na `__gc` jak w 5.4?**  
A: Częściowo; pełniejsza semantyka w planie 1.1. Nie używaj finalizera do „uratowania” danych poza korzeniem sesji.

**Q: Czy `require "cjson"` zadziała?**  
A: Nie jak w LuaRocks. Tylko to, co host włoży w preload/project.

**Q: Czy to Lua 5.5?**  
A: Etykieta zgodności podzbioru (`_VERSION`). Nie pełna implementacja PUC-Rio 5.5.

**Q: Gdzie jest „prawdziwy” dysk?**  
A: Po stronie hosta (Python/boot). Gość dostaje treść, nie ścieżki OS.

---

## 12. Powiązane dokumenty

| Dokument | Treść |
|----------|--------|
| [lua_puc_gap_plan.md](lua_puc_gap_plan.md) | Plan PR 1.1 (debug, numbers, string, coro, puc subset) |
| [tools_lua.md](tools_lua.md) | Jak pisać `:tool` |
| [lua_bin_status.md](lua_bin_status.md) | Macierz narzędzi |
| [../LUA/README.md](../LUA/README.md) | Pakiet 1.0 |

---

*Fizyka nie jest zakazem — jest warunkiem życia.  
Język jest gościem. Zepsuj gospodarzowi prawa przyrody: nie dziw się, że umiera.*
