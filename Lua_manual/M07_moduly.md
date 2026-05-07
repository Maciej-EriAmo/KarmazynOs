# Moduł 7: Moduły

> *"Dobry moduł to kontrakt: tu jest API, tu są niezmienniki, tu jest co możesz zmienić jutro bez psucia kodu kogoś innego."*

Po opanowaniu języka czas na **organizację kodu**. Moduły to mechanizm Lua do dzielenia kodu na pliki, eksportowania API, zarządzania zależnościami, ukrywania szczegółów implementacyjnych. Zamykają Część I kursu — od Modułu 8 zaczynamy embedding w C i KarmazynOS-specific tematy.

**Przewidywany czas:** 4-5 godzin pracy.

**Lekcje:**
1. `require`, `package.path`, jak Lua szuka modułów
2. Pisanie modułu — wzorzec `local M = {}` ... `return M`
3. Prywatny stan modułu, singleton, factory
4. Design API, hot reload, dependency injection

Plus **Sprawdzian Modułu 7** — 6 zadań w tym mini system pluginów i własny module loader dla KarmazynOS.

---

## Lekcja 7.1: `require`, `package.path`, jak Lua szuka modułów

### Cel

Używasz `require` do ładowania modułów. Wiesz, gdzie Lua szuka plików (`package.path`). Rozumiesz cache `require`-a. Dostosowujesz ścieżki do swojego projektu.

### Materiał

#### `require "modulename"` — podstawa

```lua
-- W pliku main.lua:
local m = require "mymodule"
-- albo:
local m = require("mymodule")    -- nawiasy opcjonalne
```

`require` szuka pliku `mymodule.lua`, ładuje go, wykonuje, **zwraca wartość** zwróconą przez plik. Wyniki są **cachowane** — drugie `require "mymodule"` nie ładuje pliku ponownie, zwraca to samo co pierwsze.

#### Co `require` robi krok po kroku

1. **Sprawdza cache** (`package.loaded`):
   - jeśli `package.loaded["mymodule"]` istnieje → zwraca go
2. **Szuka pliku** w `package.path`:
   - rozdziela na sekcje przez `;`
   - dla każdej sekcji zamienia `?` na `mymodule`
   - sprawdza czy plik istnieje
3. **Ładuje i wykonuje plik**:
   - kompiluje do funkcji
   - wywołuje funkcję
4. **Cachuje wynik**:
   - `package.loaded["mymodule"] = wynik`
   - jeśli plik nie zwrócił niczego → cache `true`
5. **Zwraca wynik**

#### `package.path` — gdzie szuka

```lua
print(package.path)
-- np. "./?.lua;/usr/local/share/lua/5.4/?.lua;/usr/local/share/lua/5.4/?/init.lua;..."
```

Format: ścieżki rozdzielone `;`, gdzie `?` to placeholder na nazwę modułu.

Przykładowy `package.path`:
```
./?.lua                              -- ./mymodule.lua
./?/init.lua                         -- ./mymodule/init.lua
/usr/local/share/lua/5.4/?.lua       -- /usr/local/share/lua/5.4/mymodule.lua
/usr/local/share/lua/5.4/?/init.lua  -- /usr/local/share/lua/5.4/mymodule/init.lua
```

`require "mymodule"` → próbuje każdą ścieżkę w kolejności, pierwsza pasująca wygrywa.

#### Moduł w podkatalogu

```lua
require "hss.session"
-- szuka:
-- ./hss/session.lua
-- ./hss/session/init.lua
-- /usr/local/share/lua/5.4/hss/session.lua
-- ...
```

Kropka w nazwie modułu = separator katalogu. Lua zamienia `.` na `/` (lub `\` na Windows) w ścieżce.

#### `init.lua` — pakiet

Gdy nazwa modułu = nazwa katalogu, Lua szuka też `init.lua`:

```
hss/
  init.lua          -- moduł "hss"
  session.lua       -- moduł "hss.session"
  atom.lua          -- moduł "hss.atom"
```

```lua
require "hss"           -- ładuje hss/init.lua
require "hss.session"   -- ładuje hss/session.lua
```

Ten układ jest typowy dla większych projektów — każdy podmoduł w osobnym pliku, `init.lua` jako "fasada" eksportująca wszystko.

#### Modyfikacja `package.path`

```lua
-- Dodaj własną ścieżkę:
package.path = "./mylib/?.lua;" .. package.path

-- Albo pełna kontrola:
package.path = "/home/maciej/karmazyn/lua/?.lua;" ..
               "/home/maciej/karmazyn/lua/?/init.lua;" ..
               package.path

-- Teraz require znajdzie moduły z karmazyn/lua/
local hss = require "hss"
```

W KarmazynOS centralna konfiguracja na początku skryptu hosta:

```lua
package.path = "/etc/holonos/policies/?.lua;" ..
               "/etc/holonos/lib/?.lua;" ..
               package.path
```

#### `package.loaded` — cache

```lua
local m = require "mymodule"
-- równoważne:
print(package.loaded["mymodule"])    -- ten sam obiekt
print(package.loaded["mymodule"] == m)    -- true

-- Dwa require zwracają tę samą referencję:
local m2 = require "mymodule"
print(m == m2)    -- true
```

To znaczy: **moduł to singleton**. Cały program widzi tę samą instancję `m`. Jeśli `m.counter = 5`, kolejne `require` widzą `5`, nie świeży 0.

#### Wymuszenie reloadu

```lua
package.loaded["mymodule"] = nil
local m = require "mymodule"    -- ładuje od nowa
```

To jest **hot reload** w prymitywnej formie. W produkcji niebezpieczne (stare referencje wskazują na poprzednią wersję), ale dla developmentu — niezbędne. Lekcja 7.4 omówi szczegóły.

#### `dofile` i `loadfile` — bez cache, bez ścieżki

```lua
-- dofile: wykonaj plik teraz, zwróć rezultat
local result = dofile("/etc/config.lua")

-- loadfile: skompiluj plik do funkcji, nie wykonuj
local fn, err = loadfile("/etc/config.lua")
if fn then
    local result = fn()    -- wykonaj
end
```

Różnice od `require`:
- **Bez cache** — każde wywołanie ładuje od nowa.
- **Bez `package.path`** — pełna ścieżka.
- **Dla `loadfile`** — separacja kompilacji i wykonania (przydatne dla sandboxa, M10).

W sandboxowanym kontekście (KarmazynOS) preferujesz `loadfile` — kontrolujesz kompilację i wykonujesz w okrojonym środowisku.

#### `package.searchers` — własne mechanizmy

`require` używa **searchers** — funkcji decydujących "gdzie szukać modułu". Domyślne:

1. Sprawdź cache (`package.loaded`).
2. Szukaj w `package.path` (Lua files).
3. Szukaj w `package.cpath` (C libraries — DLL/.so).
4. ... (mniej istotne)

Możesz dodać własny searcher:

```lua
-- Własny searcher: szukaj w Redis, w pliku ZIP, w bazie danych...
local function my_searcher(modname)
    local code = fetch_from_redis(modname)
    if not code then return "not found in Redis" end
    return loadstring(code, modname)    -- zwraca skompilowaną funkcję
end

table.insert(package.searchers, 2, my_searcher)
```

W KarmazynOS przyda się dla loadowania polityk z bazy konfiguracji, nie z plików.

### Pułapki

1. **Cache** — modyfikacja modułu przez jeden plik widoczna wszędzie. Świadomie.
2. **Modyfikacja `package.path`** — wpływa na wszystkie kolejne `require`. Zwykle robisz to na początku.
3. **Zła nazwa pliku** — `require "MyModule"` szuka `MyModule.lua` (case-sensitive na Linux/Mac).
4. **Cykliczne `require`** — A wymaga B, B wymaga A. `require` zwraca **częściowo zainicjalizowany** moduł (tylko to, co A już zdążyło ustawić przed `require "B"`).
5. **`require` w pętli** — wystarczy raz; cache zapamiętuje.

### Zadania

**Zadanie 7.1.1**  
Sprawdź swój `package.path`. Wypisz każdą ścieżkę osobno (split na `;`). Następnie dodaj na początek ścieżkę `./lib/?.lua` i sprawdź różnicę.

**Zadanie 7.1.2**  
Stwórz plik `/tmp/lua_test_mod.lua` z zawartością `return {x = 42, hello = function() print("hi") end}`. Następnie z REPL-a (lub innego skryptu) załaduj go przez `dofile` i `loadfile`. Wywołaj `hello()`.

**Zadanie 7.1.3**  
Napisz funkcję `module_path(modname)`, która zwraca pełną ścieżkę pliku, w którym Lua znalazłaby moduł (lub `nil` jeśli nie znajdzie). Hint: `package.searchpath`.

```lua
print(module_path("string"))   -- nil (string to wbudowany, nie plik)
print(module_path("mymodule")) -- np. "./mymodule.lua"
```

**Zadanie 7.1.4**  
Cykliczna zależność — napisz dwa moduły A i B w `/tmp/`, gdzie A wymaga B i odwrotnie. Załaduj A przez `require`. Wyjaśnij co widzisz.

**Zadanie 7.1.5**  
Napisz `safe_require(modname)`, który zwraca `module` lub `nil, err` (zamiast rzucać error). Standardowy "nil + msg" idiom.

```lua
local m, err = safe_require("nonexistent")
print(m, err)    -- nil   "...module 'nonexistent' not found..."
```

---

### Rozwiązania

#### Rozwiązanie 7.1.1

```lua
-- inspect_path.lua
print("--- Default package.path ---")
for path in package.path:gmatch("[^;]+") do
    print(path)
end

print()
print("--- Adding ./lib/?.lua ---")
package.path = "./lib/?.lua;" .. package.path

for path in package.path:gmatch("[^;]+") do
    print(path)
end
```

Output (przykład Termux):
```
--- Default package.path ---
/data/data/com.termux/files/usr/share/lua/5.4/?.lua
/data/data/com.termux/files/usr/share/lua/5.4/?/init.lua
/data/data/com.termux/files/usr/lib/lua/5.4/?.lua
/data/data/com.termux/files/usr/lib/lua/5.4/?/init.lua
./?.lua
./?/init.lua

--- Adding ./lib/?.lua ---
./lib/?.lua
/data/data/com.termux/files/usr/share/lua/5.4/?.lua
...
```

`gmatch("[^;]+")` — wzorzec "nie-średnik, jeden lub więcej". Klasyczny split.

#### Rozwiązanie 7.1.2

```lua
-- test_dofile_loadfile.lua

-- Najpierw stwórz plik:
local f = io.open("/tmp/lua_test_mod.lua", "w")
f:write([[
return {
    x = 42,
    hello = function() print("hi from module") end
}
]])
f:close()

print("--- dofile ---")
local m1 = dofile("/tmp/lua_test_mod.lua")
print(m1.x)        -- 42
m1.hello()         -- hi from module

print("--- loadfile ---")
local fn, err = loadfile("/tmp/lua_test_mod.lua")
if not fn then
    print("error:", err)
else
    local m2 = fn()
    print(m2.x)    -- 42
    m2.hello()     -- hi from module
end

-- Cleanup:
os.remove("/tmp/lua_test_mod.lua")

-- Pułapka cache:
print("--- dofile NIE używa cache ---")
local f = io.open("/tmp/lua_test_mod.lua", "w")
f:write("return {x = 1}")
f:close()
local a = dofile("/tmp/lua_test_mod.lua")
print(a.x)    -- 1

local f = io.open("/tmp/lua_test_mod.lua", "w")
f:write("return {x = 999}")
f:close()
local b = dofile("/tmp/lua_test_mod.lua")
print(b.x)    -- 999  (! załadowane od nowa)

os.remove("/tmp/lua_test_mod.lua")
```

`dofile` ładuje za każdym razem od nowa — odpowiednie dla "config files" które mogą się zmieniać. `loadfile` daje funkcję — pozwala wykonać wielokrotnie albo opóźnić.

#### Rozwiązanie 7.1.3

```lua
-- module_path.lua
local function module_path(modname)
    return package.searchpath(modname, package.path)
end

print(module_path("string"))     -- nil  (built-in)
print(module_path("hss"))         -- nil lub ścieżka jeśli istnieje
print(module_path("nonexistent")) -- nil

-- Stwórz testowy moduł i sprawdź:
package.path = "/tmp/?.lua;" .. package.path

local f = io.open("/tmp/test_mod.lua", "w")
f:write("return {}")
f:close()

print(module_path("test_mod"))   -- "/tmp/test_mod.lua"

os.remove("/tmp/test_mod.lua")
```

`package.searchpath(modname, path)` to wbudowane API — robi dokładnie to czego potrzeba. Iteruje po sekcjach `path`, podstawia `?`, zwraca pierwszą istniejącą ścieżkę lub `nil, err`.

#### Rozwiązanie 7.1.4

```lua
-- cyclic_test.lua

-- Stwórz dwa moduły:
local f = io.open("/tmp/mod_a.lua", "w")
f:write([[
local M = {}
M.name = "A"
M.b_initial = nil

print("loading A")
local B = require "mod_b"
print("A: B.name =", B.name)
M.b_initial = B.name

return M
]])
f:close()

local f = io.open("/tmp/mod_b.lua", "w")
f:write([[
local M = {}
M.name = "B"
M.a_initial = nil

print("loading B")
local A = require "mod_a"
print("B: A.name =", A.name)
M.a_initial = A.name

return M
]])
f:close()

package.path = "/tmp/?.lua;" .. package.path

print("--- Test cycle ---")
local A = require "mod_a"
print("A.b_initial =", A.b_initial)
print("A.name =", A.name)

local B = require "mod_b"
print("B.a_initial =", B.a_initial)

os.remove("/tmp/mod_a.lua")
os.remove("/tmp/mod_b.lua")
```

```
--- Test cycle ---
loading A
loading B
B: A.name = nil       (! A jeszcze niegotowy)
A: B.name = B
A.b_initial = B
A.name = A
B.a_initial = nil    (! było nil w momencie ładowania B)
```

**Co się dzieje:**
1. `require "mod_a"` — A zaczyna się ładować, ale nic jeszcze nie zwrócił.
2. A robi `require "mod_b"`.
3. B zaczyna się ładować, robi `require "mod_a"`.
4. Ale A jest już w `package.loaded` (jako "ładuje się") — Lua zwraca **częściowo zainicjalizowany** moduł.
5. W tym momencie A ma tylko `M.name = "A"` (linia przed `require "mod_b"`). `M.b_initial` jeszcze nil.
6. B widzi `A = {name = "A", b_initial = nil}`. **A.name = "A"**, **A.b_initial = nil**.
7. B kończy się, zwraca pełny `M`.
8. A wznawia, dostaje pełny B, kończy.

**Wniosek:** unikaj cyklicznych zależności. Jeśli trzeba — rozdziel wspólne API do trzeciego modułu, oba zależne od niego.

#### Rozwiązanie 7.1.5

```lua
-- safe_require.lua
local function safe_require(modname)
    local ok, m = pcall(require, modname)
    if ok then return m end
    return nil, m   -- m to errmsg
end

-- Test:
local m, err = safe_require("nonexistent_module_xyz")
print(m, err)
-- nil   ...:module 'nonexistent_module_xyz' not found:
--             no field package.preload['nonexistent_module_xyz']
--             no file '...'
--             ...

local m, err = safe_require("string")
print(m, err)
-- table: 0x...   nil

-- Use case: opcjonalna zależność
local socket = safe_require("socket")
if socket then
    print("LuaSocket available")
else
    print("LuaSocket not available, using fallback")
end
```

To pattern dla **opcjonalnych zależności**. Nie chcesz crashować jeśli biblioteka nie jest zainstalowana — chcesz fallback.

W KarmazynOS przyda się dla pluginów: `local plugin = safe_require("plugin_" .. name)` — jeśli pluginu nie ma, kontynuuj bez niego.

### Sprawdź się

- [ ] Wiem, że `require` cache'uje wyniki w `package.loaded`
- [ ] Pamiętam, że kropka w nazwie = separator katalogu
- [ ] Umiem zmodyfikować `package.path` na początku skryptu
- [ ] Znam różnicę `require` (cache, searchpath) vs `dofile`/`loadfile`
- [ ] Wiem, że cykliczne require dają częściowo zainicjalizowany moduł
- [ ] Umiem napisać `safe_require` przez `pcall`

---

## Lekcja 7.2: Pisanie modułu — wzorzec `local M = {}`

### Cel

Piszesz idiomatyczny moduł Lua. Eksportujesz funkcje publiczne, ukrywasz prywatne. Znasz różne style pisania modułów i wybierasz właściwy.

### Materiał

#### Kanoniczny wzorzec

```lua
-- file: hss/atom.lua

local M = {}    -- "module table"

-- Funkcje prywatne (lokalne, nie eksportowane):
local function _validate_phi(phi)
    return type(phi) == "number" and phi >= 0 and phi <= 1
end

-- Funkcje publiczne — w M:
function M.new(sig, phi)
    if not _validate_phi(phi) then
        error("phi must be in [0, 1]", 2)
    end
    return {sig = sig, phi = phi, alive = true}
end

function M.kill(atom)
    atom.alive = false
    atom.phi = 0
end

function M.is_alive(atom)
    return atom.alive
end

-- Stałe modułu:
M.MAX_PHI = 1.0
M.VERSION = "1.0.0"

return M    -- ZWROT na końcu — to jest kluczowe
```

Użycie:

```lua
local atom = require "hss.atom"

local a = atom.new("abc", 0.7)
print(atom.is_alive(a))       -- true
print(atom.MAX_PHI)            -- 1.0
print(atom.VERSION)            -- "1.0.0"

atom.kill(a)
print(atom.is_alive(a))        -- false
```

Klucze tej konwencji:
1. **`local M = {}` na początku** — tabela którą będziesz eksportować.
2. **Funkcje prywatne `local function _name`** — z prefixem `_` jako konwencja "nie ruszaj z zewnątrz". Niewidoczne poza plikiem.
3. **Funkcje publiczne `function M.name(...)`** — w tabeli M.
4. **`return M` na końcu** — to jest co `require` dostanie.

#### Wzorzec z OOP (klasa jako moduł)

Gdy moduł reprezentuje klasę:

```lua
-- file: hss/session.lua

local Session = {}
Session.__index = Session

-- Konstruktor:
function Session.new(sig)
    return setmetatable({
        sig = sig,
        atoms = {},
        epoch = 0,
        alive = true,
    }, Session)
end

-- Metody:
function Session:add_atom(atom)
    self.atoms[#self.atoms + 1] = atom
    return #self.atoms
end

function Session:tick(dt)
    self.epoch = self.epoch + 1
    -- ...
end

function Session:__tostring()
    return string.format("Session<%s, atoms=%d>", self.sig, #self.atoms)
end

-- Stała modułu:
Session.VERSION = "1.0"

return Session
```

Użycie:

```lua
local Session = require "hss.session"

local s = Session.new("abc")
s:add_atom({phi = 0.5})
print(s)                   -- Session<abc, atoms=1>
print(Session.VERSION)     -- "1.0"
```

To jest **najczęstszy** wzorzec dla większych systemów. Klasa = moduł = plik.

#### Wzorzec "namespace + factory"

Gdy moduł zawiera wiele klas pokrewnych:

```lua
-- file: hss/init.lua

local Atom = require "hss.atom"
local Session = require "hss.session"
local Bubble = require "hss.bubble"

return {
    Atom = Atom,
    Session = Session,
    Bubble = Bubble,
    
    -- Wygodne fabryki:
    new_session = Session.new,
    new_atom = Atom.new,
    
    -- Stałe wspólne:
    VERSION = "1.0.0",
    PHI_MAX = 1.0,
    PHI_MIN = 0.0,
}
```

Użycie:

```lua
local hss = require "hss"

local s = hss.new_session("user-1")
local a = hss.Atom.new("abc", 0.7)
s:add_atom(a)
```

To jest **fasada** — jeden import daje dostęp do wszystkiego. Wygoda za cenę wczesnego ładowania (wszystkie podmoduły wczytane przy `require "hss"`).

**Lazy fasada** (lekcja 4.1, lazy loader):

```lua
local M = setmetatable({}, {
    __index = function(t, k)
        local mod = require("hss." .. k:lower())
        rawset(t, k, mod)
        return mod
    end
})

return M
```

Wtedy `hss.Atom` ładuje `hss.atom` dopiero przy pierwszym użyciu.

#### Wzorzec "moduł jako funkcja"

Czasami moduł to **jedna funkcja konfiguracyjna**:

```lua
-- file: hss/policy_loader.lua

return function(path)
    local f = assert(io.open(path, "r"))
    local content = f:read("*a")
    f:close()
    -- ...parse, validate, return policy table
    return parsed_policy
end
```

Użycie:

```lua
local load_policy = require "hss.policy_loader"

local p = load_policy("/etc/holonos/default.lua")
```

`require` zwraca to co plik zwrócił — może to być funkcja, klasa, tabela, cokolwiek. Często widzisz to dla "single-purpose" modułów.

#### Stary wzorzec — `module(...)` (NIE używaj)

W Lua 5.1 i wczesnych 5.2 był wzorzec:

```lua
-- DEPRECATED:
module(..., package.seeall)

function foo() ... end       -- automatycznie globalne w module
function bar() ... end
```

`module()` zmieniało globalny środowisko, automatycznie dodawało wpisy do `package.loaded`. **Usunięte w 5.2+**.

Jeśli widzisz w starym kodzie — zastąp wzorcem `local M = {}`. Czystszy, eksplicytny.

#### Multiple returns z `require`

```lua
-- Można zwrócić wiele rzeczy?
return M, "extra"    -- ?

-- require zwraca tylko PIERWSZY:
local m, extra = require "mymodule"
print(extra)    -- nil
```

`require` zwraca tylko pierwszy result. Jeśli potrzebujesz wielu — pakuj w tabelę:

```lua
return {main = M, extra = "abc"}
```

#### Nazewnictwo plików — konwencje

```
snake_case.lua          -- preferowany styl
kebab-case.lua          -- działa, ale '-' w nazwie modułu wymaga []
PascalCase.lua          -- działa, mniej idiomatyczne
camelCase.lua           -- mniej spotykane
```

`require "kebab-case"` działa? Sprawdźmy:

```lua
-- Działa technicznie, ale:
local m = require "kebab-case"  -- OK
-- Ale:
require "abc.kebab-case"        -- problem? sprawdź kropkę
```

W praktyce: trzymaj się `snake_case` lub jednowyrazowych. Bezbólowe.

#### Konwencja struktury katalogów

Dla większego projektu:

```
karmazyn/
├── init.lua                 -- moduł "karmazyn"
├── hss/
│   ├── init.lua             -- moduł "karmazyn.hss"
│   ├── atom.lua             -- "karmazyn.hss.atom"
│   ├── session.lua          -- "karmazyn.hss.session"
│   └── bubble.lua
├── policy/
│   ├── init.lua
│   ├── parser.lua
│   └── validator.lua
├── util/
│   ├── init.lua
│   ├── set.lua              -- moduł Set z M2/M4
│   └── stream.lua           -- Stream library z M6
└── lib/
    └── 3rd_party_deps.lua
```

Z `package.path = "./?.lua;./?/init.lua;..."` — `require "karmazyn.hss.atom"` znajdzie `karmazyn/hss/atom.lua`.

### Pułapki

1. **Brak `return M`** — moduł nie eksportuje nic. `require` cache'uje `true`, nie tabelę.
2. **`function foo()` bez `local`** — globalna! Zaśmieca `_G`.
3. **`M.foo = function() ... end` vs `function M.foo() ... end`** — semantycznie identyczne, drugie czytelniejsze.
4. **Modyfikowanie modułu z innego pliku** — działa (cache), ale to "global state at distance" — anti-pattern.
5. **`require` w środku funkcji** — działa, ale ładowanie odbywa się leniwie. Świadomie.

### Zadania

**Zadanie 7.2.1**  
Napisz moduł `lib/queue.lua` (klasa Queue z M2 Sprawdzian 2). Stwórz strukturę `./lib/queue.lua`, dodaj do `package.path`, zaimportuj i przetestuj.

**Zadanie 7.2.2**  
Napisz moduł `lib/timer.lua` z funkcjami:
- `now()` — bieżący czas (os.time())
- `tic()` — zapamiętaj czas
- `toc()` — zwróć ile sekund minęło od ostatniego `tic`

Plus prywatna zmienna `_last_tic` — schowana w closure.

**Zadanie 7.2.3**  
Stwórz pakiet `karmazyn` z `init.lua`:
- `karmazyn/init.lua` — fasada
- `karmazyn/atom.lua` — klasa Atom
- `karmazyn/session.lua` — klasa Session

Fasada eksportuje obie klasy plus `karmazyn.VERSION`.

**Zadanie 7.2.4**  
Lazy fasada — przepisz Zadanie 7.2.3 tak, by podmoduły ładowały się dopiero przy pierwszym użyciu (przez `__index = function`).

**Zadanie 7.2.5**  
Moduł `lib/log.lua` — singleton logger. Ma metody `:info()`, `:warn()`, `:error()`. Wszystkie skrypty `require "log"` dostają tę samą instancję. Demonstracja: ustaw `log.level = "WARN"` w jednym pliku — drugi widzi.

---

### Rozwiązania

#### Rozwiązanie 7.2.1

```lua
-- /tmp/lib/queue.lua
local Queue = {}
Queue.__index = Queue

function Queue.new()
    return setmetatable({head = 1, tail = 0}, Queue)
end

function Queue:enqueue(v)
    self.tail = self.tail + 1
    self[self.tail] = v
end

function Queue:dequeue()
    if self.head > self.tail then return nil end
    local v = self[self.head]
    self[self.head] = nil
    self.head = self.head + 1
    return v
end

function Queue:peek()
    if self.head > self.tail then return nil end
    return self[self.head]
end

function Queue:size()
    return self.tail - self.head + 1
end

function Queue:empty()
    return self.head > self.tail
end

function Queue:__tostring()
    local items = {}
    for i = self.head, self.tail do
        items[#items + 1] = tostring(self[i])
    end
    return "Queue[" .. table.concat(items, ", ") .. "]"
end

return Queue
```

```lua
-- main_test.lua

-- Setup struktury:
os.execute("mkdir -p /tmp/lib")

-- (zapisz queue.lua jak powyżej, lub użyj io.open)

-- Dodaj ścieżkę:
package.path = "/tmp/?.lua;/tmp/?/init.lua;" .. package.path

local Queue = require "lib.queue"

local q = Queue.new()
q:enqueue("a")
q:enqueue("b")
q:enqueue("c")
print(q)              -- Queue[a, b, c]
print(q:size())       -- 3
print(q:dequeue())    -- "a"
print(q:dequeue())    -- "b"
print(q:size())       -- 1
```

`require "lib.queue"` szuka `lib/queue.lua` (kropka → /). `package.path = "/tmp/?.lua"` tłumaczy `lib.queue` na `/tmp/lib/queue.lua`.

#### Rozwiązanie 7.2.2

```lua
-- lib/timer.lua
local _last_tic = nil    -- prywatne, nie eksportowane

local M = {}

function M.now()
    return os.time()
end

function M.tic()
    _last_tic = os.time()
end

function M.toc()
    if _last_tic == nil then
        return nil, "tic not called"
    end
    return os.time() - _last_tic
end

function M.reset()
    _last_tic = nil
end

return M
```

```lua
-- test:
local timer = require "lib.timer"

print(timer.now())     -- np. 1731234567

timer.tic()
-- ... robi coś przez kilka sekund
print(timer.toc())     -- 0 lub więcej (zależnie od czasu)

local elapsed, err = timer.toc()
-- elapsed: liczba sekund

timer.reset()
print(timer.toc())     -- nil   "tic not called"
```

`_last_tic` jako lokalna w pliku → niedostępne z zewnątrz. To **module-level private state**.

**Pułapka:** ponieważ moduł jest singleton, `_last_tic` jest **dzielony globalnie**. Dwa różne miejsca w kodzie wywołujące `tic()` → drugi nadpisuje pierwszy.

Dla "per-instance" timer-a — Lekcja 7.3 (factory pattern).

#### Rozwiązanie 7.2.3

```lua
-- karmazyn/atom.lua
local Atom = {}
Atom.__index = Atom

function Atom.new(sig, phi)
    return setmetatable({sig = sig, phi = phi or 0.0, alive = true}, Atom)
end

function Atom:__tostring()
    return string.format("Atom<%s, phi=%.3f>", self.sig, self.phi)
end

return Atom
```

```lua
-- karmazyn/session.lua
local Session = {}
Session.__index = Session

function Session.new(sig)
    return setmetatable({sig = sig, atoms = {}}, Session)
end

function Session:add_atom(a)
    self.atoms[#self.atoms + 1] = a
end

function Session:__tostring()
    return string.format("Session<%s, atoms=%d>", self.sig, #self.atoms)
end

return Session
```

```lua
-- karmazyn/init.lua
local Atom = require "karmazyn.atom"
local Session = require "karmazyn.session"

return {
    Atom = Atom,
    Session = Session,
    
    -- Convenient factories:
    new_atom = Atom.new,
    new_session = Session.new,
    
    -- Constants:
    VERSION = "1.0.0",
    PHI_MAX = 1.0,
    PHI_MIN = 0.0,
}
```

```lua
-- main_test.lua
package.path = "/tmp/?.lua;/tmp/?/init.lua;" .. package.path

local karmazyn = require "karmazyn"

print(karmazyn.VERSION)    -- 1.0.0

local s = karmazyn.new_session("user-1")
local a = karmazyn.new_atom("abc", 0.7)
s:add_atom(a)
print(s)    -- Session<user-1, atoms=1>
print(a)    -- Atom<abc, phi=0.700>

-- Też przez explicit class:
local another_atom = karmazyn.Atom.new("def", 0.4)
s:add_atom(another_atom)
print(s)    -- Session<user-1, atoms=2>
```

Fasada `karmazyn` daje 1 punkt importu, klient nie musi pamiętać które są podmoduły.

#### Rozwiązanie 7.2.4

```lua
-- karmazyn/init.lua (lazy version)

local M = {}

-- Stałe od razu (cheap):
M.VERSION = "1.0.0"
M.PHI_MAX = 1.0
M.PHI_MIN = 0.0

-- Mapowanie eksportowanych klas → ścieżek modułów:
local class_modules = {
    Atom = "karmazyn.atom",
    Session = "karmazyn.session",
}

setmetatable(M, {
    __index = function(t, k)
        local modpath = class_modules[k]
        if not modpath then return nil end
        local mod = require(modpath)
        rawset(t, k, mod)    -- cache
        return mod
    end
})

-- Convenient factories — też lazy via __index:
function M.new_atom(...)
    return M.Atom.new(...)
end

function M.new_session(...)
    return M.Session.new(...)
end

return M
```

```lua
-- Test:
local karmazyn = require "karmazyn"

-- W tym momencie karmazyn.atom NIE jest jeszcze załadowany!
print("VERSION:", karmazyn.VERSION)    -- 1.0.0
print("Atom in package.loaded?", package.loaded["karmazyn.atom"])    -- nil

-- Pierwsze użycie ładuje:
local a = karmazyn.new_atom("abc", 0.7)
print("Atom in package.loaded?", package.loaded["karmazyn.atom"])    -- table: 0x...

print(a)    -- Atom<abc, phi=0.700>
```

Korzyść: dla dużych projektów z wieloma podmodułami, użytkownik importujący tylko 1-2 nie płaci za ładowanie 50.

W KarmazynOS to nie jest problem (mały kod), ale dla bibliotek pomocniczych z dziesiątkami klas — wartościowe.

#### Rozwiązanie 7.2.5

```lua
-- lib/log.lua

local levels = {DEBUG = 1, INFO = 2, WARN = 3, ERROR = 4}

local M = {
    level = "INFO",
    output = print,
}

local function _should_log(level)
    return levels[level] >= levels[M.level]
end

local function _log(level, msg)
    if not _should_log(level) then return end
    M.output(string.format("[%s] %s", level, msg))
end

function M.debug(msg) _log("DEBUG", msg) end
function M.info(msg)  _log("INFO", msg) end
function M.warn(msg)  _log("WARN", msg) end
function M.error(msg) _log("ERROR", msg) end

return M
```

```lua
-- file_a.lua
local log = require "lib.log"
log.info("z file_a")
log.debug("debug — nie wyświetla bo level=INFO")
```

```lua
-- file_b.lua
local log = require "lib.log"
log.warn("z file_b")
log.level = "DEBUG"   -- zmienia globalnie!
log.debug("teraz wyświetla")
```

```lua
-- main.lua
package.path = "./?.lua;" .. package.path

local log = require "lib.log"

log.info("main start")
require "file_a"
log.debug("po file_a — nie wyświetla")
require "file_b"
log.debug("po file_b — wyświetla, bo file_b zmieniło level")
```

Output:
```
[INFO] main start
[INFO] z file_a
[WARN] z file_b
[DEBUG] teraz wyświetla
[DEBUG] po file_b — wyświetla, bo file_b zmieniło level
```

Singleton state — zmiana w `file_b` widoczna wszędzie. Zarówno **funkcjonalność** jak i **niebezpieczeństwo** singletona.

W produkcyjnym KarmazynOS — log może być per-session (każda sesja ma własny logger przez factory) zamiast globalny. Patrz Lekcja 7.3.

### Sprawdź się

- [ ] Pamiętam zawsze `return M` na końcu pliku
- [ ] Wiem, jak zorganizować pakiet z `init.lua`
- [ ] Umiem napisać lazy fasadę z `__index = function`
- [ ] Rozumiem singleton-naturę modułów (cache w `package.loaded`)
- [ ] Wiem, kiedy moduł jako klasa, kiedy jako namespace, kiedy jako funkcja
- [ ] Pamiętam pułapkę globalnego state w module

---

## Lekcja 7.3: Prywatny stan modułu, singleton, factory

### Cel

Rozróżniasz "moduł jako singleton" od "moduł jako fabryka instancji". Wybierasz właściwy wzorzec dla problemu. Znasz wady i zalety każdego.

### Materiał

#### Singleton — moduł trzymający stan

```lua
-- lib/cache.lua
local M = {}

local _cache = {}      -- prywatne, dzielone przez wszystkich klientów

function M.get(key)
    return _cache[key]
end

function M.set(key, value)
    _cache[key] = value
end

function M.clear()
    _cache = {}
end

return M
```

```lua
-- file_a.lua
local cache = require "lib.cache"
cache.set("user", "Anna")

-- file_b.lua
local cache = require "lib.cache"
print(cache.get("user"))    -- "Anna"   (! ten sam cache!)
```

**Singleton jest naturalnym domyślnym wzorcem** dla modułów Lua. Ale ma wady:
- **Trudne testowanie** — testy widzą stan z innych testów (chyba że robisz `:clear()` przed każdym).
- **Trudne wielokrotne instancje** — jeśli potrzebujesz dwóch cache'ów, jeden moduł nie wystarcza.
- **Globalny state at distance** — modyfikacja z dowolnego miejsca wpływa wszędzie.

#### Factory — moduł produkujący instancje

```lua
-- lib/cache_factory.lua
local Cache = {}
Cache.__index = Cache

function Cache.new()
    return setmetatable({_data = {}}, Cache)
end

function Cache:get(key)
    return self._data[key]
end

function Cache:set(key, value)
    self._data[key] = value
end

function Cache:clear()
    self._data = {}
end

return Cache
```

```lua
-- file_a.lua
local Cache = require "lib.cache_factory"
local cache_a = Cache.new()
cache_a:set("user", "Anna")

-- file_b.lua
local Cache = require "lib.cache_factory"
local cache_b = Cache.new()
print(cache_b:get("user"))    -- nil  (! niezależne)
```

Każde `Cache.new()` to świeża instancja. Klient sam decyduje czy chce singleton (jeden global `cache`) czy wiele.

#### Mieszany — singleton z optionalną instancją

```lua
-- lib/cache_hybrid.lua
local Cache = {}
Cache.__index = Cache

function Cache.new()
    return setmetatable({_data = {}}, Cache)
end

function Cache:get(key) return self._data[key] end
function Cache:set(key, value) self._data[key] = value end
function Cache:clear() self._data = {} end

-- Default singleton:
local _default = Cache.new()

return setmetatable({
    Cache = Cache,           -- klasa do tworzenia własnych
    -- Singleton API (skróty):
    get = function(k) return _default:get(k) end,
    set = function(k, v) _default:set(k, v) end,
    clear = function() _default:clear() end,
    default = _default,      -- bezpośredni dostęp
}, {__index = Cache})
```

```lua
local cache = require "lib.cache_hybrid"

-- Użycie singleton:
cache.set("user", "Anna")
print(cache.get("user"))    -- "Anna"

-- Albo własna instancja:
local my_cache = cache.Cache.new()
my_cache:set("user", "Bartek")
print(my_cache:get("user"))    -- "Bartek"
print(cache.get("user"))        -- "Anna" (singleton nietknięty)
```

To pattern z bibliotek typu Pythonowy `logging` — globalny default, ale możesz tworzyć własne logger-y.

#### Closure-based moduł — prawdziwie prywatny

```lua
-- lib/counter.lua

local function make_counter(initial)
    local count = initial or 0
    
    return {
        inc = function() count = count + 1; return count end,
        dec = function() count = count - 1; return count end,
        get = function() return count end,
        reset = function() count = initial or 0 end,
    }
end

return make_counter
```

```lua
local make_counter = require "lib.counter"

local c1 = make_counter(10)
local c2 = make_counter()

c1.inc(); c1.inc()
print(c1.get())    -- 12
print(c2.get())    -- 0

-- Niemożliwe sięgnąć do count z zewnątrz:
print(c1.count)         -- nil (! nie ma)
print(rawget(c1, "count"))    -- nil
```

`count` w closure — **niedostępne z zewnątrz**. To prawdziwa prywatność, nie konwencja jak prefix `_`.

Trade-off:
- **Plus:** prawdziwa enkapsulacja, klient nie może zepsuć stanu.
- **Minus:** brak introspekcji (`for k, v in pairs(c1) do` nie pokaże `count`), brak metatable (każda instancja ma swoje funkcje, więcej pamięci).

#### Module config przy ładowaniu

Czasami chcesz parametryzować moduł przy require:

```lua
-- lib/db.lua
local M = {}

local _config = {
    host = "localhost",
    port = 5432,
    user = "anonymous",
}

function M.configure(opts)
    for k, v in pairs(opts) do
        _config[k] = v
    end
end

function M.get_config()
    return _config
end

function M.connect()
    -- użyj _config
    print("connecting to " .. _config.host .. ":" .. _config.port)
end

return M
```

```lua
local db = require "lib.db"
db.configure({host = "production.db.example.com", port = 5433})
db.connect()
```

To pattern "global config". Wada — `configure` musi być wywołane przed pierwszym `connect()`. Nie ma kontroli nad kolejnością przy złożonych zależnościach.

Lepszy pattern — **factory z config**:

```lua
-- lib/db_factory.lua
local DB = {}
DB.__index = DB

function DB.new(config)
    return setmetatable({
        host = config.host or "localhost",
        port = config.port or 5432,
        user = config.user or "anonymous",
    }, DB)
end

function DB:connect()
    print("connecting to " .. self.host .. ":" .. self.port)
end

return DB
```

```lua
local DB = require "lib.db_factory"
local db = DB.new({host = "production.db.example.com", port = 5433})
db:connect()
```

Cały config zna w jednym miejscu (przy konstrukcji). Brak hidden state.

#### Singleton zalety i kiedy używać

**Używaj singleton dla:**
- Naturalnie pojedynczych zasobów: log globalny, config aplikacji, registry
- Hot path gdzie tworzenie instancji byłoby kosztowne
- Małych narzędzi (helpers) bez stanu

**Unikaj singleton dla:**
- Czegokolwiek co testujesz jednostkowo
- Czegokolwiek czego klient może chcieć wielu
- Stanu który może być "zatruty" przez błędne kody innych modułów

W KarmazynOS:
- **Singleton:** logger globalny, registry sesji
- **Factory:** Session, Atom, Bubble (każda sesja własna instancja), policy parser

#### Anti-pattern: modyfikacja modułu z zewnątrz

```lua
-- BAD: monkey-patching
local atom = require "hss.atom"
function atom.new_method()
    print("bad practice — added from outside")
end

-- Teraz każdy klient atom widzi new_method
```

**Działa**, bo moduł to zwykła tabela. **Anti-pattern**, bo:
- Klient nie wie które metody są "oryginalne", które dodane.
- Kolejność ładowania ma znaczenie — kto pierwszy doda, ten wygrywa.
- Konflikt nazw nie jest sprawdzany.

Wyjątek: monkey-patching dla **testowania** (mock funkcji modułu — opisane w 7.4 dependency injection).

### Pułapki

1. **Singleton w testach** — stan przecieka między testami. `teardown` dla każdego testu.
2. **Closure module + wiele instancji** — koszt pamięci (każda instancja własne funkcje). Dla 1000+ instancji preferuj OOP z metatable.
3. **`module.foo` global modification** — zmienia dla wszystkich. Świadomie.
4. **Lazy state** (np. `_config`) — niezainicjowany przy require. Funkcje muszą sprawdzać.

### Zadania

**Zadanie 7.3.1**  
Przepisz `lib/timer.lua` z 7.2.2 jako **factory** — `make_timer()` zwraca obiekt z `:tic()`, `:toc()`, `:reset()`. Każda instancja ma własny `_last_tic`. Pokaż 2 niezależne timery.

**Zadanie 7.3.2**  
Mieszany pattern dla `lib/log.lua` — singleton API (jak w 7.2.5) **plus** `log.Logger.new(prefix)` dla custom loggerów z prefixem.

```lua
local log = require "lib.log"
log.info("global")           -- [INFO] global

local hss_log = log.Logger.new("[HSS] ")
hss_log:info("local message")    -- [HSS] [INFO] local message
```

**Zadanie 7.3.3**  
Closure-based prywatny — napisz `lib/secret_box.lua` z funkcjami `make_box(secret)`, `:set(value)`, `:get(secret_attempt)`. `:get` zwraca wartość tylko jeśli `secret_attempt == secret`, inaczej `nil`. Sekret musi być prawdziwie prywatny.

```lua
local make_box = require "lib.secret_box"
local box = make_box("mypass")
box:set("treasure")
print(box:get("wrong"))    -- nil
print(box:get("mypass"))   -- "treasure"

-- Niemożliwe sięgnąć:
for k, v in pairs(box) do print(k, v) end    -- tylko funkcje, nie sekret
```

**Zadanie 7.3.4**  
Konfigurowalny moduł — `lib/cache_ttl.lua` z `Cache.new(default_ttl)` (TTL w sekundach). Metoda `:set(k, v, custom_ttl)` (custom_ttl override default). `:get(k)` zwraca nil jeśli wygasł.

**Zadanie 7.3.5**  
Wzorzec "registry pattern" — `lib/registry.lua` jako singleton z metodami `:register(name, value)`, `:get(name)`, `:names()`, `:unregister(name)`. Plus `:on_register(fn)` — listener wywoływany przy każdej rejestracji.

---

### Rozwiązania

#### Rozwiązanie 7.3.1

```lua
-- lib/timer_factory.lua
local Timer = {}
Timer.__index = Timer

function Timer.new()
    return setmetatable({_last_tic = nil}, Timer)
end

function Timer:tic()
    self._last_tic = os.time()
end

function Timer:toc()
    if self._last_tic == nil then
        return nil, "tic not called"
    end
    return os.time() - self._last_tic
end

function Timer:reset()
    self._last_tic = nil
end

-- Convenient: make_timer() jako shortcut
local M = {}
M.Timer = Timer
M.make_timer = Timer.new

-- Albo bardziej minimalny:
-- return Timer.new

return M
```

```lua
-- test:
local timer_lib = require "lib.timer_factory"

local t1 = timer_lib.make_timer()
local t2 = timer_lib.Timer.new()

t1:tic()
-- ... krótka pauza
-- t2:tic() w innym czasie
t2:tic()

-- Każdy ma własny stan:
print(t1:toc())    -- np. 0
print(t2:toc())    -- 0
```

Każda instancja ma własne `_last_tic` — stan jest **per-obiekt**, nie globalny. Można mieć 1000 timerów bez kolizji.

#### Rozwiązanie 7.3.2

```lua
-- lib/log_hybrid.lua

local levels = {DEBUG = 1, INFO = 2, WARN = 3, ERROR = 4}

-- Klasa Logger:
local Logger = {}
Logger.__index = Logger

function Logger.new(prefix, level)
    return setmetatable({
        prefix = prefix or "",
        level = level or "INFO",
        output = print,
    }, Logger)
end

function Logger:_should_log(level)
    return levels[level] >= levels[self.level]
end

function Logger:_log(level, msg)
    if not self:_should_log(level) then return end
    self.output(string.format("%s[%s] %s", self.prefix, level, msg))
end

function Logger:debug(msg) self:_log("DEBUG", msg) end
function Logger:info(msg)  self:_log("INFO", msg) end
function Logger:warn(msg)  self:_log("WARN", msg) end
function Logger:error(msg) self:_log("ERROR", msg) end

-- Default singleton:
local _default = Logger.new()

-- Module API:
local M = {
    Logger = Logger,
    
    -- Singleton shortcuts:
    debug = function(msg) _default:debug(msg) end,
    info = function(msg) _default:info(msg) end,
    warn = function(msg) _default:warn(msg) end,
    error = function(msg) _default:error(msg) end,
    
    -- Configuracja singleton:
    set_level = function(level) _default.level = level end,
    set_output = function(fn) _default.output = fn end,
    
    default = _default,
}

return M
```

```lua
-- test:
local log = require "lib.log_hybrid"

-- Singleton:
log.info("global message")
-- [INFO] global message

log.set_level("DEBUG")
log.debug("now visible")
-- [DEBUG] now visible

-- Custom logger z prefixem:
local hss_log = log.Logger.new("[HSS] ")
hss_log:info("local message")
-- [HSS] [INFO] local message

local critical = log.Logger.new("!!! ", "WARN")
critical:debug("nie pokazuje")
critical:warn("alarm")
-- !!! [WARN] alarm

-- Singleton wciąż niezmienny:
log.info("still working")
-- [INFO] still working
```

Pattern daje wygodę singleton + elastyczność factory. Najlepsze z obu światów.

#### Rozwiązanie 7.3.3

```lua
-- lib/secret_box.lua

local function make_box(secret)
    local _value = nil       -- prywatne
    local _secret = secret   -- prywatne
    
    return {
        set = function(self, v)
            _value = v
        end,
        get = function(self, attempt)
            if attempt == _secret then
                return _value
            end
            return nil
        end,
    }
end

return make_box
```

```lua
-- test:
local make_box = require "lib.secret_box"

local box = make_box("mypass")
box:set("treasure")

print(box:get("wrong"))     -- nil
print(box:get("mypass"))    -- "treasure"

-- Niemożliwe sięgnąć — closure jest naprawdę prywatny:
for k, v in pairs(box) do
    print(k, v)
end
-- set   function: 0x...
-- get   function: 0x...
-- (! brak _value, _secret)

-- Próba inspect przez metatable:
print(getmetatable(box))    -- nil (brak metatable)

-- Próba przez debug.getupvalue (wymaga znajomości funkcji):
-- ! debug.getupvalue MOŻE pokazać upvalues funkcji set/get
local i = 1
while true do
    local name, val = debug.getupvalue(box.get, i)
    if not name then break end
    print(i, name, val)
    i = i + 1
end
-- 1   _secret   "mypass"
-- 2   _value    "treasure"
```

**Pułapka:** `debug.getupvalue` może wyciągnąć upvalues. To znaczy: closure-based privacy **nie jest pełna** w obecności `debug` library.

W KarmazynOS sandbox (Moduł 10) `debug` jest **wycięte z `_ENV`** — wtedy closure jest naprawdę prywatne. W normalnym kodzie — masz "convention privacy", nie kryptograficzną.

Dla "prawdziwie prywatnego" w obecności debug — trzymaj sekret w C-side userdata (Moduł 9).

#### Rozwiązanie 7.3.4

```lua
-- lib/cache_ttl.lua
local Cache = {}
Cache.__index = Cache

function Cache.new(default_ttl)
    return setmetatable({
        default_ttl = default_ttl or 60,
        _data = {},
        _timestamps = {},
    }, Cache)
end

function Cache:set(key, value, custom_ttl)
    self._data[key] = value
    local ttl = custom_ttl or self.default_ttl
    self._timestamps[key] = os.time() + ttl
end

function Cache:get(key)
    local expires_at = self._timestamps[key]
    if expires_at == nil then return nil end
    if os.time() >= expires_at then
        self._data[key] = nil
        self._timestamps[key] = nil
        return nil
    end
    return self._data[key]
end

function Cache:has(key)
    return self:get(key) ~= nil
end

function Cache:clear()
    self._data = {}
    self._timestamps = {}
end

function Cache:size()
    -- Sweep wygasłych:
    local now = os.time()
    local count = 0
    for k, expires_at in pairs(self._timestamps) do
        if now >= expires_at then
            self._data[k] = nil
            self._timestamps[k] = nil
        else
            count = count + 1
        end
    end
    return count
end

return Cache
```

```lua
-- test:
local Cache = require "lib.cache_ttl"

local c = Cache.new(2)    -- default TTL 2s

c:set("short", "expires fast", 1)
c:set("normal", "default ttl")
c:set("long", "lasting", 100)

print(c:get("short"))     -- "expires fast"
print(c:get("normal"))    -- "default ttl"
print(c:size())           -- 3

-- (czekamy 2 sekundy w prawdziwym teście)
-- Symulujemy upływ czasu:
for k in pairs(c._timestamps) do
    c._timestamps[k] = c._timestamps[k] - 5    -- "5 sekund minęło"
end

print(c:get("short"))     -- nil  (TTL 1s minął)
print(c:get("normal"))    -- nil  (TTL 2s minął)
print(c:get("long"))      -- "lasting"  (TTL 100s, OK)
print(c:size())           -- 1
```

Per-key TTL z `custom_ttl` parameter. Lazy expiration — sprawdzamy przy `get`/`size`. Dla aktywnego sweep'a — osobny background task (M11).

#### Rozwiązanie 7.3.5

```lua
-- lib/registry.lua

local Registry = {}
Registry.__index = Registry

function Registry.new()
    return setmetatable({
        _items = {},
        _listeners = {},
    }, Registry)
end

function Registry:register(name, value)
    if self._items[name] ~= nil then
        return false, "already registered: " .. name
    end
    self._items[name] = value
    -- Notify listeners:
    for _, fn in ipairs(self._listeners) do
        fn(name, value, "register")
    end
    return true
end

function Registry:unregister(name)
    local value = self._items[name]
    if value == nil then return false, "not registered: " .. name end
    self._items[name] = nil
    for _, fn in ipairs(self._listeners) do
        fn(name, value, "unregister")
    end
    return true
end

function Registry:get(name)
    return self._items[name]
end

function Registry:names()
    local list = {}
    for name in pairs(self._items) do list[#list + 1] = name end
    table.sort(list)
    return list
end

function Registry:on_register(fn)
    self._listeners[#self._listeners + 1] = fn
end

-- Singleton default:
local _default = Registry.new()

return setmetatable({
    Registry = Registry,
    register = function(name, value) return _default:register(name, value) end,
    unregister = function(name) return _default:unregister(name) end,
    get = function(name) return _default:get(name) end,
    names = function() return _default:names() end,
    on_register = function(fn) _default:on_register(fn) end,
    default = _default,
}, {__index = Registry})
```

```lua
-- test:
local registry = require "lib.registry"

-- Listener (singleton):
registry.on_register(function(name, value, action)
    print(string.format("[REG] %s: %s = %s", action, name, tostring(value)))
end)

registry.register("plugin_a", {version = 1})
-- [REG] register: plugin_a = table: 0x...

registry.register("plugin_b", "string-value")
-- [REG] register: plugin_b = string-value

print(table.concat(registry.names(), ", "))
-- plugin_a, plugin_b

print(registry.get("plugin_a").version)    -- 1

registry.unregister("plugin_a")
-- [REG] unregister: plugin_a = table: 0x...

print(registry.get("plugin_a"))    -- nil

-- Custom registry (factory):
local my_reg = registry.Registry.new()
my_reg:register("foo", "bar")
print(my_reg:get("foo"))    -- "bar"
print(registry.get("foo"))  -- nil  (singleton ≠ my_reg)
```

W KarmazynOS — registry sesji aktywnych, registry pluginów, registry typów atomów. Każdy z własnym listenerem na wydarzenia.

### Sprawdź się

- [ ] Wiem, kiedy wybrać singleton, kiedy factory, kiedy hybrid
- [ ] Umiem zrobić moduł factory z `Cls.new()` zwracającym instancje
- [ ] Pamiętam, że singleton ma globalny state (testowanie!)
- [ ] Wiem, że closure-based privacy nie jest pełna w obecności debug
- [ ] Umiem napisać moduł z konfigurowalną domyślną instancją + factory

---

## Lekcja 7.4: Design API, hot reload, dependency injection

### Cel

Projektujesz dobre API modułu — minimal, intuicyjne, stabilne. Implementujesz hot reload dla developmentu. Używasz dependency injection dla testowalnego kodu.

### Materiał

#### Dobre API — zasady

1. **Minimal surface** — eksportuj tylko to, czego klient potrzebuje. Mniej powierzchnia = łatwiej utrzymać.
2. **Consistent naming** — `snake_case` dla funkcji, `PascalCase` dla klas. `:method()` dla metod, `.func()` dla statycznych.
3. **Predictable error handling** — wybierz: error-throwing (`assert(io.open)`) lub nil+errmsg (`io.open`). Trzymaj się jednego.
4. **Immutability gdzie sensowne** — funkcje zwracające nowe wartości, nie modyfikujące argumenty.
5. **Document via examples** — komentarze pokazujące "jak używać".

#### Anatomia dobrego modułu

```lua
-- hss/atom.lua

--[[
    hss.atom — atom Φ-space dla HSS
    
    USAGE:
        local atom = require "hss.atom"
        local a = atom.new("abc", 0.7)
        atom.fade(a, 0.5)
        if atom.is_alive(a) then ... end
    
    STABILITY:
        atom.new           — stable (1.0+)
        atom.is_alive      — stable (1.0+)
        atom.fade          — stable (1.0+)
        atom._internal     — internal, may change
]]

local M = {
    VERSION = "1.0.0",
    PHI_THRESHOLD_DEAD = 1e-6,
}

-- Walidacja argumentów (private):
local function _validate_phi(phi)
    if type(phi) ~= "number" then
        error("phi must be number, got " .. type(phi), 3)
    end
    if phi < 0 or phi > 1 then
        error("phi must be in [0, 1], got " .. phi, 3)
    end
end

-- Public API:

--- Tworzy nowy atom.
-- @param sig string — sygnatura (niepusty)
-- @param phi number — początkowa wartość phi w [0, 1]
-- @return table — nowy atom
function M.new(sig, phi)
    if type(sig) ~= "string" or #sig == 0 then
        error("sig must be non-empty string", 2)
    end
    _validate_phi(phi)
    return {sig = sig, phi = phi, alive = true}
end

--- Sprawdza czy atom żyje.
function M.is_alive(atom)
    return atom.alive and atom.phi > M.PHI_THRESHOLD_DEAD
end

--- Zmniejsza phi atomu o factor.
-- @param atom table
-- @param factor number — w [0, 1]
function M.fade(atom, factor)
    _validate_phi(factor)
    atom.phi = atom.phi * factor
    if atom.phi < M.PHI_THRESHOLD_DEAD then
        atom.alive = false
        atom.phi = 0
    end
end

--- Zwraca string-reprezentację atomu.
function M.format(atom)
    return string.format("Atom<%s, phi=%.4f, %s>",
        atom.sig, atom.phi, atom.alive and "alive" or "dead")
end

return M
```

Co się tu dzieje:
- **Dokumentacja na początku** — ogólny opis + usage + stability.
- **Stałe wyeksponowane** — `VERSION`, `PHI_THRESHOLD_DEAD`. Klient może sprawdzić.
- **Walidacja przed logiką** — error z `level` wskazującym na callera.
- **Komentarze nad funkcjami** — `@param`, `@return` (LuaDoc-style).
- **Bez `_` na publicznych** — `M.new`, `M.is_alive`. Tylko `_internal` ma underscore.

To jest produkcyjna jakość API.

#### Wersjonowanie API

```lua
-- hss/atom.lua
local M = {}
M.VERSION = "1.2.3"
M.API_VERSION = 1   -- breaking changes bumpują

function M.check_compatibility(required_api)
    if M.API_VERSION ~= required_api then
        error(string.format(
            "API version mismatch: required %d, have %d",
            required_api, M.API_VERSION), 2)
    end
end

return M
```

```lua
-- klient:
local atom = require "hss.atom"
atom.check_compatibility(1)    -- rzuca jeśli moduł zmienił API

-- ... dalej kod używający atom
```

W większych projektach to ważne. Daje klientom ostrzeżenie "moduł zmienił się niekompatybilnie", zamiast "tajemniczy błąd 6 funkcji niżej".

#### Hot reload — wymuszone przeładowanie

Podczas developmentu:

```lua
-- hot_reload.lua
local function reload(modname)
    package.loaded[modname] = nil
    return require(modname)
end

local atom = require "hss.atom"
-- ... edytujesz hss/atom.lua ...
atom = reload "hss.atom"    -- nowa wersja
```

**Pułapka:** stare instancje (atomy stworzone przed reloadem) **nie** widzą nowego API. Zostają z metatable'em starej wersji.

```lua
local Session = require "lib.session"
local s = Session.new("abc")    -- używa starej Session

Session = reload "lib.session"
local s2 = Session.new("def")    -- używa nowej

s:method()      -- używa STAREJ session.method
s2:method()     -- używa NOWEJ
```

Dla pełnego "live update" trzeba zmigrować stare instancje. Skomplikowane. Hot reload zwykle stosujemy dla **bibliotek bezstanowych** (utility functions) lub w trakcie developmentu (akceptujemy że stary stan może być "stale").

#### File watcher + auto reload

```lua
-- lib/file_watcher.lua
local M = {}

local _watched = {}    -- {modname → {file, last_mtime}}

local function _get_mtime(path)
    local f = io.popen("stat -c %Y " .. path .. " 2>/dev/null")
    if not f then return nil end
    local mtime = tonumber(f:read("*l"))
    f:close()
    return mtime
end

function M.watch(modname)
    local path = package.searchpath(modname, package.path)
    if not path then return false, "module not found" end
    _watched[modname] = {path = path, mtime = _get_mtime(path)}
    return true
end

function M.check_all()
    local reloaded = {}
    for modname, info in pairs(_watched) do
        local current = _get_mtime(info.path)
        if current and current > info.mtime then
            package.loaded[modname] = nil
            local ok, mod = pcall(require, modname)
            if ok then
                info.mtime = current
                reloaded[#reloaded + 1] = modname
                print("[reload] " .. modname)
            else
                print("[reload error] " .. modname .. ": " .. mod)
            end
        end
    end
    return reloaded
end

return M
```

Use case w developmencie:

```lua
local watcher = require "lib.file_watcher"
watcher.watch("hss.atom")
watcher.watch("hss.session")

-- W main loop aplikacji:
while true do
    watcher.check_all()
    -- ... rób co rób
end
```

Gdy edytujesz `hss/atom.lua` — watcher to wykrywa, reloduje. **Tylko dla developmentu** — produkcja nie powinna tego potrzebować (deploy → restart).

#### Dependency injection (DI)

Anty-pattern:

```lua
-- BAD: hardcoded zależności
local logger = require "lib.log"

local function process_atom(atom)
    logger.info("processing " .. atom.sig)    -- ! couple z konkretnym loggerem
    -- ... logic
end
```

Problem: nie da się przetestować `process_atom` bez zalogowania do globalnego loggera. Test loguje wszystko — śmieci.

Lepiej:

```lua
-- GOOD: logger jako argument
local function process_atom(atom, logger)
    logger:info("processing " .. atom.sig)
    -- ... logic
end

-- Production:
process_atom(atom, require("lib.log").default)

-- Test:
local mock_log = {info = function(self, msg) end}    -- silent
process_atom(atom, mock_log)
```

To jest **dependency injection**. Funkcja nie tworzy zależności — dostaje je z zewnątrz.

#### DI w klasach

```lua
-- hss/session.lua
local Session = {}
Session.__index = Session

function Session.new(opts)
    return setmetatable({
        sig = opts.sig,
        atoms = {},
        logger = opts.logger,    -- injected
        clock = opts.clock or os.time,    -- injected (default os.time)
    }, Session)
end

function Session:add_atom(atom)
    self.atoms[#self.atoms + 1] = atom
    self.logger:info("atom added: " .. atom.sig)
    atom.added_at = self.clock()
end

return Session
```

```lua
-- Production:
local s = Session.new({
    sig = "user-1",
    logger = require("lib.log").default,
})

-- Test:
local fake_clock = function() return 1000 end
local mock_logger = {info = function() end}
local s = Session.new({
    sig = "test",
    logger = mock_logger,
    clock = fake_clock,
})
s:add_atom({sig = "x"})
assert(s.atoms[1].added_at == 1000)
```

Klasa testowalna bez prawdziwego zegara, prawdziwego loggera, prawdziwych I/O.

#### DI container (advanced)

W większych systemach — moduł "container" zarządzający wszystkimi zależnościami:

```lua
-- lib/container.lua
local Container = {}
Container.__index = Container

function Container.new()
    return setmetatable({_factories = {}, _instances = {}}, Container)
end

function Container:register(name, factory)
    self._factories[name] = factory
end

function Container:get(name)
    if self._instances[name] then return self._instances[name] end
    local factory = self._factories[name]
    if not factory then return nil, "not registered: " .. name end
    self._instances[name] = factory(self)
    return self._instances[name]
end

return Container
```

```lua
-- main.lua
local Container = require "lib.container"
local c = Container.new()

c:register("logger", function() return require("lib.log").Logger.new() end)
c:register("clock", function() return os.time end)
c:register("session_factory", function(c)
    return function(sig)
        return Session.new({
            sig = sig,
            logger = c:get("logger"),
            clock = c:get("clock"),
        })
    end
end)

-- Use:
local make_session = c:get("session_factory")
local s = make_session("user-1")

-- Test (osobny container):
local test_c = Container.new()
test_c:register("logger", function() return mock_logger end)
test_c:register("clock", function() return fake_clock end)
test_c:register("session_factory", ...)    -- ten sam factory
```

Container daje jedno miejsce do "wstrzyknięcia mocków" — cały graf zależności wymienia się w testach przez podstawienie containera.

W KarmazynOS to przydaje się gdy host ma wiele serwisów: `logger`, `metrics`, `tracer`, `session_registry` — wszystkie wstrzykiwane przez container.

### Pułapki

1. **Hot reload + state** — nowy moduł, stare instancje. Pamiętaj.
2. **DI bez containera** — łańcuch konstrukcji ręczny. Skaluje się słabo.
3. **DI z containerem** — overhead konceptualny. Dla małych skryptów overkill.
4. **`@param`/`@return`** — to dla ludzi i tooling. Lua nie egzekwuje.
5. **API z `_internal`** — klient i tak czasem sięgnie. Convention is not enforcement.

### Zadania

**Zadanie 7.4.1**  
Napisz moduł `lib/dev_reload.lua` z funkcją `reload(modname)`. Dodaj logging — kto reloadował, kiedy, ile razy łącznie.

**Zadanie 7.4.2**  
Refaktor — weź istniejącą `Session` i zrób ją testowalną. Wstrzyknij `logger`, `clock`, `id_generator`. Napisz dwa testy: production (real time) i mock (controlled time).

**Zadanie 7.4.3**  
Module `lib/version_check.lua` z funkcją `check(modname, expected_version)`:
- ładuje moduł, sprawdza `M.VERSION`
- semver compare: major mismatch → error, minor/patch < required → warning

```lua
local check = require "lib.version_check"
check("hss.atom", "1.2.0")    -- OK jeśli >=1.2.0 i major=1
```

**Zadanie 7.4.4**  
DI Container z pełną funkcjonalnością:
- `:register(name, factory)`
- `:register_singleton(name, factory)` — różnica od factory: zawsze ta sama instancja
- `:get(name)` 
- `:has(name)`
- `:reset()` — czyści wszystkie instances (nie factories)

**Zadanie 7.4.5**  
Plugin loader — `lib/plugins.lua`:
- ścieżka do katalogu plugins/
- ładuje wszystkie `*.lua` z katalogu
- każdy plugin to moduł z `name`, `version`, `init(config)` 
- `:load_all()` — ładuje wszystkie
- `:get(name)` — zwraca załadowany plugin
- emituje events `loaded`, `failed`

---

### Rozwiązania

#### Rozwiązanie 7.4.1

```lua
-- lib/dev_reload.lua

local M = {
    history = {},   -- lista {modname, time, success}
}

function M.reload(modname)
    local was_loaded = package.loaded[modname] ~= nil
    package.loaded[modname] = nil
    
    local ok, mod = pcall(require, modname)
    
    table.insert(M.history, {
        modname = modname,
        time = os.time(),
        success = ok,
        was_loaded = was_loaded,
    })
    
    if ok then
        print(string.format("[reload] %s — OK (%d total reloads)",
            modname, #M.history))
        return mod
    else
        print(string.format("[reload] %s — FAILED: %s", modname, mod))
        return nil, mod
    end
end

function M.stats()
    local successful = 0
    local failed = 0
    for _, entry in ipairs(M.history) do
        if entry.success then successful = successful + 1
        else failed = failed + 1 end
    end
    return {
        total = #M.history,
        successful = successful,
        failed = failed,
    }
end

function M.recent(n)
    n = n or 10
    local result = {}
    local start = math.max(1, #M.history - n + 1)
    for i = start, #M.history do
        result[#result + 1] = M.history[i]
    end
    return result
end

return M
```

```lua
-- test:
local dev_reload = require "lib.dev_reload"

-- (zakładamy że hss.atom istnieje)
local atom = dev_reload.reload "hss.atom"
-- [reload] hss.atom — OK (1 total reloads)

dev_reload.reload "hss.atom"
-- [reload] hss.atom — OK (2 total reloads)

dev_reload.reload "nonexistent"
-- [reload] nonexistent — FAILED: ...

local stats = dev_reload.stats()
print(stats.total, stats.successful, stats.failed)
-- 3   2   1

for _, e in ipairs(dev_reload.recent(3)) do
    print(os.date("%H:%M:%S", e.time), e.modname, e.success)
end
```

W developmencie — łatwo zobaczyć ile razy reloadowałeś, co padło. Useful dla debugging "czemu mój reload nie działa".

#### Rozwiązanie 7.4.2

```lua
-- karmazyn/session.lua

local Session = {}
Session.__index = Session

function Session.new(opts)
    opts = opts or {}
    return setmetatable({
        sig = opts.sig or error("sig required", 2),
        atoms = {},
        logger = opts.logger or {info = function() end, error = function() end},
        clock = opts.clock or os.time,
        id_generator = opts.id_generator or function()
            return "auto-" .. os.time()
        end,
        created_at = nil,    -- ustawimy poniżej
    }, Session)
end

function Session:_init()
    self.created_at = self.clock()
end

function Session.new_initialized(opts)
    local self = Session.new(opts)
    self:_init()
    self.logger:info("session initialized: " .. self.sig)
    return self
end

function Session:add_atom(data)
    local atom = {
        id = self.id_generator(),
        sig = data.sig,
        phi = data.phi,
        added_at = self.clock(),
    }
    self.atoms[#self.atoms + 1] = atom
    self.logger:info("atom added: " .. atom.id)
    return atom
end

function Session:age()
    return self.clock() - self.created_at
end

return Session
```

```lua
-- test_production.lua
local Session = require "karmazyn.session"

-- Production: real dependencies
local log = require("lib.log").default
local s = Session.new_initialized({
    sig = "user-1",
    logger = log,
})

s:add_atom({sig = "abc", phi = 0.7})
print(s:age())    -- ~ 0
```

```lua
-- test_unit.lua
local Session = require "karmazyn.session"

-- Mock dependencies:
local log_calls = {}
local mock_logger = {
    info = function(self, msg) table.insert(log_calls, {"info", msg}) end,
    error = function(self, msg) table.insert(log_calls, {"error", msg}) end,
}

local fake_time = 1000
local fake_clock = function() return fake_time end

local id_counter = 0
local fake_id_gen = function()
    id_counter = id_counter + 1
    return "test-id-" .. id_counter
end

local s = Session.new_initialized({
    sig = "test-session",
    logger = mock_logger,
    clock = fake_clock,
    id_generator = fake_id_gen,
})

assert(s.created_at == 1000)

fake_time = 1100
local atom = s:add_atom({sig = "abc", phi = 0.7})

assert(atom.id == "test-id-1")
assert(atom.added_at == 1100)
assert(s:age() == 100)

-- Sprawdź log:
assert(#log_calls == 2)
assert(log_calls[1][2] == "session initialized: test-session")
assert(log_calls[2][2] == "atom added: test-id-1")

print("All tests passed!")
```

**Test jednostkowy jest deterministyczny** — `fake_clock` daje pełną kontrolę nad "czasem". `fake_id_gen` daje przewidywalne ID. `mock_logger` zbiera calls do późniejszej weryfikacji.

W produkcji — wszystkie real. W testach — controlled. To jest fundamentalny zysk z DI.

#### Rozwiązanie 7.4.3

```lua
-- lib/version_check.lua

local function _parse_semver(s)
    local major, minor, patch = s:match("(%d+)%.(%d+)%.(%d+)")
    if not major then return nil, "invalid semver: " .. s end
    return {
        major = tonumber(major),
        minor = tonumber(minor),
        patch = tonumber(patch),
    }
end

local function _compare(a, b)
    -- Returns: -1 (a<b), 0 (a==b), 1 (a>b)
    if a.major ~= b.major then return a.major < b.major and -1 or 1 end
    if a.minor ~= b.minor then return a.minor < b.minor and -1 or 1 end
    if a.patch ~= b.patch then return a.patch < b.patch and -1 or 1 end
    return 0
end

local M = {}

function M.check(modname, expected_version_str)
    local mod = require(modname)
    if not mod.VERSION then
        error("module " .. modname .. " has no VERSION", 2)
    end
    
    local actual = _parse_semver(mod.VERSION)
    local expected = _parse_semver(expected_version_str)
    
    if not actual then
        error("module " .. modname .. " has invalid VERSION: " .. mod.VERSION, 2)
    end
    if not expected then
        error("invalid expected version: " .. expected_version_str, 2)
    end
    
    -- Major mismatch — fatal:
    if actual.major ~= expected.major then
        error(string.format(
            "%s major version mismatch: have %s, expected %s",
            modname, mod.VERSION, expected_version_str), 2)
    end
    
    -- Minor/patch — must be >=:
    if _compare(actual, expected) < 0 then
        print(string.format(
            "[WARN] %s version %s is older than expected %s",
            modname, mod.VERSION, expected_version_str))
    end
    
    return mod
end

function M.parse(s)
    return _parse_semver(s)
end

return M
```

```lua
-- test:
local check = require "lib.version_check"

-- (Zakładamy hss.atom z VERSION = "1.2.3")

-- OK:
local atom = check.check("hss.atom", "1.0.0")    -- 1.2.3 >= 1.0.0 i major == 1

-- Warning (older than expected):
check.check("hss.atom", "1.5.0")
-- [WARN] hss.atom version 1.2.3 is older than expected 1.5.0

-- Error (major mismatch):
local ok, err = pcall(check.check, "hss.atom", "2.0.0")
print(err)
-- ...:hss.atom major version mismatch: have 1.2.3, expected 2.0.0
```

Semver compatibility check. W większych projektach zapobiega "subtelnym crashom" gdy biblioteka się ściera niekompatybilnie.

#### Rozwiązanie 7.4.4

```lua
-- lib/container.lua

local Container = {}
Container.__index = Container

function Container.new()
    return setmetatable({
        _factories = {},
        _singletons = {},     -- mapa: name → true if singleton
        _instances = {},
    }, Container)
end

function Container:register(name, factory)
    self._factories[name] = factory
    self._singletons[name] = false
end

function Container:register_singleton(name, factory)
    self._factories[name] = factory
    self._singletons[name] = true
end

function Container:has(name)
    return self._factories[name] ~= nil
end

function Container:get(name)
    if self._singletons[name] and self._instances[name] then
        return self._instances[name]
    end
    
    local factory = self._factories[name]
    if not factory then return nil, "not registered: " .. name end
    
    local instance = factory(self)
    
    if self._singletons[name] then
        self._instances[name] = instance
    end
    
    return instance
end

function Container:reset()
    self._instances = {}
end

function Container:names()
    local list = {}
    for name in pairs(self._factories) do list[#list + 1] = name end
    table.sort(list)
    return list
end

return Container
```

```lua
-- test:
local Container = require "lib.container"

local c = Container.new()

-- Singleton: jedna instancja
c:register_singleton("logger", function()
    print("creating logger")
    return {info = print}
end)

-- Factory: nowa za każdym razem
c:register("session", function(container)
    print("creating session")
    return {
        id = os.time(),
        logger = container:get("logger"),
    }
end)

print("--- pierwszy access logger ---")
local log1 = c:get("logger")
-- creating logger

print("--- drugi access logger (cached) ---")
local log2 = c:get("logger")
-- (nic — cached singleton)
print(log1 == log2)    -- true

print("--- pierwsza session ---")
local s1 = c:get("session")
-- creating session

print("--- druga session (nowa) ---")
local s2 = c:get("session")
-- creating session
print(s1 == s2)    -- false

-- Obie sessions używają tego samego loggera (singleton):
print(s1.logger == s2.logger)    -- true
```

Singleton dla "shared infrastructure" (logger, db connection, config). Factory dla "per-request objects" (session, request handler).

#### Rozwiązanie 7.4.5

```lua
-- lib/plugins.lua

local PluginLoader = {}
PluginLoader.__index = PluginLoader

function PluginLoader.new(plugins_dir)
    return setmetatable({
        plugins_dir = plugins_dir,
        plugins = {},      -- name → plugin module
        listeners = {},    -- event → list of fn
    }, PluginLoader)
end

function PluginLoader:on(event, fn)
    if not self.listeners[event] then self.listeners[event] = {} end
    table.insert(self.listeners[event], fn)
end

function PluginLoader:_emit(event, ...)
    if self.listeners[event] then
        for _, fn in ipairs(self.listeners[event]) do fn(...) end
    end
end

function PluginLoader:_list_files()
    -- Prosta implementacja — używamy os.popen z ls:
    local f = io.popen("ls " .. self.plugins_dir .. "/*.lua 2>/dev/null")
    if not f then return {} end
    local files = {}
    for line in f:lines() do
        local name = line:match("([^/]+)%.lua$")
        if name then files[#files + 1] = name end
    end
    f:close()
    return files
end

function PluginLoader:load_all(config)
    config = config or {}
    
    -- Add plugins_dir to package.path:
    local old_path = package.path
    package.path = self.plugins_dir .. "/?.lua;" .. package.path
    
    local files = self:_list_files()
    for _, name in ipairs(files) do
        local ok, mod = pcall(require, name)
        if ok then
            -- Validate plugin shape:
            if type(mod) ~= "table" or type(mod.name) ~= "string" then
                self:_emit("failed", name, "invalid plugin: missing 'name' field")
            elseif type(mod.init) ~= "function" then
                self:_emit("failed", name, "invalid plugin: missing 'init' function")
            else
                -- Initialize:
                local init_ok, init_err = pcall(mod.init, config)
                if init_ok then
                    self.plugins[mod.name] = mod
                    self:_emit("loaded", mod.name, mod.version or "?")
                else
                    self:_emit("failed", name, "init failed: " .. init_err)
                end
            end
        else
            self:_emit("failed", name, "load failed: " .. mod)
        end
    end
    
    -- Restore path:
    package.path = old_path
    
    return self.plugins
end

function PluginLoader:get(name)
    return self.plugins[name]
end

function PluginLoader:names()
    local list = {}
    for name in pairs(self.plugins) do list[#list + 1] = name end
    table.sort(list)
    return list
end

return PluginLoader
```

```lua
-- Test:
-- Najpierw stwórz plugins/:
os.execute("mkdir -p /tmp/test_plugins")

-- Plugin 1 (poprawny):
local f = io.open("/tmp/test_plugins/plugin_a.lua", "w")
f:write([[
return {
    name = "plugin_a",
    version = "1.0",
    init = function(config)
        print("plugin_a init with config:", config.mode or "default")
    end,
    do_something = function() return "result from a" end,
}
]])
f:close()

-- Plugin 2 (z błędem):
local f = io.open("/tmp/test_plugins/plugin_broken.lua", "w")
f:write([[
return {
    name = "plugin_broken",
    init = function() error("init failure") end,
}
]])
f:close()

-- Plugin 3 (invalid shape):
local f = io.open("/tmp/test_plugins/plugin_invalid.lua", "w")
f:write([[return {description = "no name"}]])
f:close()

-- Plugin 4:
local f = io.open("/tmp/test_plugins/plugin_b.lua", "w")
f:write([[
return {
    name = "plugin_b",
    version = "2.1",
    init = function() print("plugin_b init") end,
}
]])
f:close()

-- Test:
local PluginLoader = require "lib.plugins"

local loader = PluginLoader.new("/tmp/test_plugins")

loader:on("loaded", function(name, version)
    print(string.format("[OK] %s v%s loaded", name, version))
end)

loader:on("failed", function(name, reason)
    print(string.format("[FAIL] %s: %s", name, reason))
end)

loader:load_all({mode = "production"})

print("--- Loaded plugins ---")
for _, name in ipairs(loader:names()) do
    local p = loader:get(name)
    print(name, p.version)
end

-- Cleanup:
os.execute("rm -rf /tmp/test_plugins")
```

Output:
```
plugin_a init with config: production
[OK] plugin_a v1.0 loaded
[FAIL] plugin_broken: init failed: ...:init failure
[FAIL] plugin_invalid: invalid plugin: missing 'name' field
plugin_b init
[OK] plugin_b v2.1 loaded
--- Loaded plugins ---
plugin_a   1.0
plugin_b   2.1
```

W KarmazynOS dokładnie ten pattern dla:
- Plugin filtrów Φ-space (każdy filtr to plugin)
- Plugin transformów atomów
- Plugin protokołów komunikacji

### Sprawdź się

- [ ] Wiem, jak zaprojektować dobre API (minimal, consistent, documented)
- [ ] Pamiętam pułapki hot reload (stare instancje)
- [ ] Umiem napisać DI container z singleton vs factory
- [ ] Umiem zrobić plugin loader z events
- [ ] Wiem, czemu DI ułatwia testowanie
- [ ] Znam wzorzec semver compatibility check

---

## Sprawdzian Modułu 7

Sześć zadań — moduł integracyjny z poprzednich. Po nim zamykasz Część I kursu.

### Zadania

**Sprawdzian 1** — Pełen pakiet `karmazyn`  
Zbuduj strukturę:
```
karmazyn/
├── init.lua
├── atom.lua            (klasa Atom z M4)
├── session.lua         (klasa Session z M4)
├── stream.lua          (Stream library z M6)
└── util/
    ├── init.lua
    ├── set.lua
    └── queue.lua
```

`init.lua` jest fasadą eksportującą wszystko. Lazy loading przez `__index`. Versioning. Test importujący różne ścieżki.

**Sprawdzian 2** — Logger z poziomami i targetami  
Moduł `lib/log_advanced.lua`:
- klasa `Logger` z poziomami DEBUG/INFO/WARN/ERROR
- multiple targets (console, file, in-memory)
- targets implementują interface `:write(level, msg, timestamp)`
- format jako template ze zmiennymi (`{level}`, `{msg}`, `{time}`)
- singleton + factory hybrid

**Sprawdzian 3** — Hot-reloadable plugin system  
Plugin system z M7.4.5, plus:
- `:reload(name)` — przeładowuje pojedynczy plugin
- `:reload_all()` — wszystkie
- `:watch_changes()` — wykrywa zmiany plików, automatycznie reloduje
- każdy plugin ma `cleanup` callback wywoływany przed reloadem

**Sprawdzian 4** — Module loader dla KarmazynOS  
`hss/loader.lua` — własny module searcher:
- ładuje moduły z `/etc/holonos/policies/` (zamiast standardowego `package.path`)
- waliduje schemat każdego modułu (musi mieć `name`, `version`, `apply` function)
- budżet pamięci per moduł (mierzony przez `collectgarbage("count")` przed/po)
- moduł nie może wczytać więcej niż `max_kb` przy ładowaniu

**Sprawdzian 5** — DI Container z lifecycle  
Pełny DI container:
- `:register_singleton(name, factory)`
- `:register_transient(name, factory)`  
- `:register_scoped(name, factory)` — singleton w obrębie scope
- `:create_scope()` — zwraca sub-container z własnymi scoped instances
- `:dispose()` — wywołuje `:close()` lub `:dispose()` na każdej instancji która ma

**Sprawdzian 6** — Mini "package manager" w pamięci  
`lib/pm.lua` — manager pakietów:
- `:install(name, source_code)` — kompiluje source, zapisuje
- `:uninstall(name)` — usuwa
- `:require(name)` — ładuje (z własnego rejestru, nie z dysku)
- `:list()` — wszystkie zainstalowane
- pakiety mogą dependować na siebie (`require "other_pkg"` w środku)
- detection cykli, wersjonowanie

```lua
local pm = require "lib.pm"

pm:install("greet", [[
local M = {}
function M.hello(name) return "Hello, " .. name end
return M
]])

local greet = pm:require("greet")
print(greet.hello("Maciej"))    -- "Hello, Maciej"
```

---

### Rozwiązania sprawdzianu

#### Sprawdzian 1

```lua
-- karmazyn/atom.lua
local Atom = {}
Atom.__index = Atom

function Atom.new(sig, phi)
    return setmetatable({
        sig = sig,
        phi = phi or 0.0,
        alive = true,
    }, Atom)
end

function Atom:fade(rate)
    self.phi = self.phi * rate
    if self.phi < 1e-6 then self.alive = false end
end

function Atom:__tostring()
    return string.format("Atom<%s, phi=%.4f>", self.sig, self.phi)
end

return Atom
```

```lua
-- karmazyn/session.lua
local Session = {}
Session.__index = Session

function Session.new(sig)
    return setmetatable({sig = sig, atoms = {}}, Session)
end

function Session:add_atom(atom)
    self.atoms[#self.atoms + 1] = atom
end

function Session:tick(rate)
    for i = #self.atoms, 1, -1 do
        self.atoms[i]:fade(rate)
        if not self.atoms[i].alive then
            table.remove(self.atoms, i)
        end
    end
end

function Session:__tostring()
    return string.format("Session<%s, atoms=%d>", self.sig, #self.atoms)
end

return Session
```

```lua
-- karmazyn/stream.lua
local Stream = {}
Stream.__index = Stream

local function _stream(gen)
    return setmetatable({_gen = gen}, Stream)
end

function Stream.from_range(a, b, step)
    return _stream(coroutine.wrap(function()
        for i = a, b, step or 1 do coroutine.yield(i) end
    end))
end

function Stream.from_table(t)
    return _stream(coroutine.wrap(function()
        for _, v in ipairs(t) do coroutine.yield(v) end
    end))
end

function Stream:map(fn)
    local prev = self._gen
    return _stream(coroutine.wrap(function()
        while true do
            local v = prev()
            if v == nil then return end
            coroutine.yield(fn(v))
        end
    end))
end

function Stream:filter(predicate)
    local prev = self._gen
    return _stream(coroutine.wrap(function()
        while true do
            local v = prev()
            if v == nil then return end
            if predicate(v) then coroutine.yield(v) end
        end
    end))
end

function Stream:to_table()
    local r = {}
    while true do
        local v = self._gen()
        if v == nil then return r end
        r[#r + 1] = v
    end
end

return Stream
```

```lua
-- karmazyn/util/set.lua (z M2)
local Set = {}
Set.__index = Set

function Set.new(...)
    local s = setmetatable({_data = {}, _size = 0}, Set)
    for _, v in ipairs({...}) do
        if not s._data[v] then
            s._data[v] = true
            s._size = s._size + 1
        end
    end
    return s
end

function Set:add(v)
    if not self._data[v] then
        self._data[v] = true
        self._size = self._size + 1
    end
end

function Set:contains(v) return self._data[v] == true end
function Set:size() return self._size end

return Set
```

```lua
-- karmazyn/util/queue.lua (z M2)
local Queue = {}
Queue.__index = Queue

function Queue.new() return setmetatable({head=1, tail=0}, Queue) end
function Queue:enqueue(v) self.tail = self.tail + 1; self[self.tail] = v end
function Queue:dequeue()
    if self.head > self.tail then return nil end
    local v = self[self.head]; self[self.head] = nil; self.head = self.head + 1
    return v
end

return Queue
```

```lua
-- karmazyn/util/init.lua
return {
    Set = require "karmazyn.util.set",
    Queue = require "karmazyn.util.queue",
}
```

```lua
-- karmazyn/init.lua
local M = {}

-- Stałe od razu (cheap):
M.VERSION = "1.0.0"
M.API_VERSION = 1
M.PHI_MAX = 1.0
M.PHI_MIN = 0.0

-- Mapa: lazy-loaded klasy → ścieżki
local lazy_modules = {
    Atom = "karmazyn.atom",
    Session = "karmazyn.session",
    Stream = "karmazyn.stream",
    util = "karmazyn.util",
}

setmetatable(M, {
    __index = function(t, k)
        local modpath = lazy_modules[k]
        if not modpath then return nil end
        local mod = require(modpath)
        rawset(t, k, mod)
        return mod
    end
})

-- Convenient factories:
function M.new_atom(sig, phi) return M.Atom.new(sig, phi) end
function M.new_session(sig) return M.Session.new(sig) end

-- Compatibility check:
function M.check_api(required)
    if required ~= M.API_VERSION then
        error(string.format("API version mismatch: required %d, have %d",
            required, M.API_VERSION), 2)
    end
end

return M
```

```lua
-- main_test.lua
package.path = "/tmp/?.lua;/tmp/?/init.lua;" .. package.path

-- Test 1: import fasady
local karmazyn = require "karmazyn"
karmazyn.check_api(1)
print(karmazyn.VERSION)    -- 1.0.0

-- Test 2: lazy loading
print("loaded before access:", package.loaded["karmazyn.atom"])    -- nil
local a = karmazyn.new_atom("abc", 0.7)
print("loaded after access:", package.loaded["karmazyn.atom"])     -- table

-- Test 3: bezpośredni import
local Stream = require "karmazyn.stream"
local result = Stream.from_range(1, 10):filter(function(x) return x % 2 == 0 end):to_table()
for _, v in ipairs(result) do io.write(v, " ") end
print()    -- 2 4 6 8 10

-- Test 4: util submodule
local util = karmazyn.util
local s = util.Set.new("a", "b", "c")
print(s:size())    -- 3

-- Test 5: full pipeline
local sess = karmazyn.new_session("test-session")
for i = 1, 5 do
    sess:add_atom(karmazyn.new_atom("atom-" .. i, 0.5 + i * 0.1))
end
print(sess)    -- Session<test-session, atoms=5>
sess:tick(0.5)
print(sess)
```

Pełna struktura projektu — fasada, lazy loading, podpakiety, version check. To produkcyjny szkielet.

#### Sprawdzian 2

```lua
-- lib/log_advanced.lua

local levels = {DEBUG = 1, INFO = 2, WARN = 3, ERROR = 4}

-- Targets:
local ConsoleTarget = {}
ConsoleTarget.__index = ConsoleTarget

function ConsoleTarget.new(stream)
    return setmetatable({stream = stream or io.stdout}, ConsoleTarget)
end

function ConsoleTarget:write(level, msg, timestamp)
    self.stream:write(msg .. "\n")
end


local FileTarget = {}
FileTarget.__index = FileTarget

function FileTarget.new(path)
    local f, err = io.open(path, "a")
    if not f then error("cannot open log file: " .. err, 2) end
    return setmetatable({file = f, path = path}, FileTarget)
end

function FileTarget:write(level, msg, timestamp)
    self.file:write(msg .. "\n")
    self.file:flush()
end

function FileTarget:close()
    if self.file then self.file:close(); self.file = nil end
end


local MemoryTarget = {}
MemoryTarget.__index = MemoryTarget

function MemoryTarget.new(capacity)
    return setmetatable({
        entries = {},
        capacity = capacity or 1000,
    }, MemoryTarget)
end

function MemoryTarget:write(level, msg, timestamp)
    table.insert(self.entries, {level = level, msg = msg, time = timestamp})
    if #self.entries > self.capacity then
        table.remove(self.entries, 1)
    end
end

function MemoryTarget:get_all()
    return self.entries
end


-- Logger:
local Logger = {}
Logger.__index = Logger

function Logger.new(opts)
    opts = opts or {}
    return setmetatable({
        level = opts.level or "INFO",
        targets = opts.targets or {ConsoleTarget.new()},
        format = opts.format or "[{level}] {time} {msg}",
        time_fn = opts.time_fn or function()
            return os.date("%Y-%m-%d %H:%M:%S")
        end,
    }, Logger)
end

function Logger:_format(level, msg, timestamp)
    local result = self.format
    result = result:gsub("{level}", level)
    result = result:gsub("{msg}", msg)
    result = result:gsub("{time}", timestamp)
    return result
end

function Logger:_log(level, msg)
    if levels[level] < levels[self.level] then return end
    local timestamp = self.time_fn()
    local formatted = self:_format(level, msg, timestamp)
    for _, target in ipairs(self.targets) do
        target:write(level, formatted, timestamp)
    end
end

function Logger:debug(msg) self:_log("DEBUG", msg) end
function Logger:info(msg)  self:_log("INFO", msg) end
function Logger:warn(msg)  self:_log("WARN", msg) end
function Logger:error(msg) self:_log("ERROR", msg) end

function Logger:add_target(target)
    table.insert(self.targets, target)
end

function Logger:set_level(level)
    self.level = level
end

-- Default singleton:
local _default = Logger.new()

-- Module API:
local M = {
    Logger = Logger,
    ConsoleTarget = ConsoleTarget,
    FileTarget = FileTarget,
    MemoryTarget = MemoryTarget,
    
    -- Singleton shortcuts:
    debug = function(msg) _default:debug(msg) end,
    info = function(msg) _default:info(msg) end,
    warn = function(msg) _default:warn(msg) end,
    error = function(msg) _default:error(msg) end,
    
    set_level = function(l) _default:set_level(l) end,
    add_target = function(t) _default:add_target(t) end,
    
    default = _default,
}

return M
```

```lua
-- test:
local log = require "lib.log_advanced"

-- Singleton:
log.info("default to console")
-- [INFO] 2026-05-06 15:30:00 default to console

-- Custom logger z multiple targets:
local mem_target = log.MemoryTarget.new(10)
local custom = log.Logger.new({
    level = "DEBUG",
    targets = {
        log.ConsoleTarget.new(),
        mem_target,
    },
    format = "{time} | {level} | {msg}",
})

custom:info("logging to console AND memory")
custom:debug("debug also")

-- Sprawdź pamięć:
for _, e in ipairs(mem_target:get_all()) do
    print("memory:", e.level, e.msg)
end

-- File target:
local file_logger = log.Logger.new({
    targets = {
        log.FileTarget.new("/tmp/test.log"),
    },
})
file_logger:warn("written to file")

-- Cleanup:
os.remove("/tmp/test.log")
```

Multiple targets + format templates + singleton/factory hybrid. To produkcyjny logger jak w większych projektach (winston, log4j style).

#### Sprawdzian 3

```lua
-- lib/plugin_system.lua

local PluginSystem = {}
PluginSystem.__index = PluginSystem

local function _get_mtime(path)
    local f = io.popen("stat -c %Y " .. path .. " 2>/dev/null")
    if not f then return nil end
    local mtime = tonumber(f:read("*l"))
    f:close()
    return mtime
end

function PluginSystem.new(plugins_dir)
    return setmetatable({
        dir = plugins_dir,
        plugins = {},   -- name → {mod, file, mtime, config}
        listeners = {},
    }, PluginSystem)
end

function PluginSystem:on(event, fn)
    if not self.listeners[event] then self.listeners[event] = {} end
    table.insert(self.listeners[event], fn)
end

function PluginSystem:_emit(event, ...)
    if self.listeners[event] then
        for _, fn in ipairs(self.listeners[event]) do fn(...) end
    end
end

function PluginSystem:_load_one(file_name, config)
    local file_path = self.dir .. "/" .. file_name .. ".lua"
    
    -- Bezpośrednie ładowanie pliku:
    local fn, err = loadfile(file_path)
    if not fn then
        return nil, "load failed: " .. err
    end
    
    local ok, mod = pcall(fn)
    if not ok then
        return nil, "exec failed: " .. mod
    end
    
    if type(mod) ~= "table" or type(mod.name) ~= "string" then
        return nil, "missing 'name' field"
    end
    if type(mod.init) ~= "function" then
        return nil, "missing 'init' function"
    end
    
    local init_ok, init_err = pcall(mod.init, config)
    if not init_ok then
        return nil, "init failed: " .. init_err
    end
    
    return {
        mod = mod,
        file = file_path,
        mtime = _get_mtime(file_path),
        config = config,
    }
end

function PluginSystem:load_all(config)
    config = config or {}
    
    local f = io.popen("ls " .. self.dir .. "/*.lua 2>/dev/null")
    if not f then return end
    
    for line in f:lines() do
        local name = line:match("([^/]+)%.lua$")
        if name then
            local plugin, err = self:_load_one(name, config)
            if plugin then
                self.plugins[plugin.mod.name] = plugin
                self:_emit("loaded", plugin.mod.name)
            else
                self:_emit("failed", name, err)
            end
        end
    end
    f:close()
end

function PluginSystem:reload(name)
    local plugin = self.plugins[name]
    if not plugin then return false, "not loaded: " .. name end
    
    -- Cleanup:
    if plugin.mod.cleanup then
        local ok, err = pcall(plugin.mod.cleanup)
        if not ok then
            self:_emit("cleanup_failed", name, err)
        end
    end
    
    -- Re-load:
    local file_name = plugin.file:match("([^/]+)%.lua$")
    local new_plugin, err = self:_load_one(file_name, plugin.config)
    if not new_plugin then
        self:_emit("reload_failed", name, err)
        return false, err
    end
    
    self.plugins[name] = new_plugin
    self:_emit("reloaded", name)
    return true
end

function PluginSystem:reload_all()
    local names = {}
    for name in pairs(self.plugins) do names[#names + 1] = name end
    for _, name in ipairs(names) do
        self:reload(name)
    end
end

function PluginSystem:check_changes()
    -- Sprawdź mtimes, reload zmienionych:
    for name, plugin in pairs(self.plugins) do
        local current_mtime = _get_mtime(plugin.file)
        if current_mtime and current_mtime > plugin.mtime then
            self:reload(name)
        end
    end
end

function PluginSystem:get(name)
    local p = self.plugins[name]
    return p and p.mod or nil
end

function PluginSystem:names()
    local list = {}
    for name in pairs(self.plugins) do list[#list + 1] = name end
    table.sort(list)
    return list
end

return PluginSystem
```

```lua
-- test:
os.execute("mkdir -p /tmp/plugins_v2")

local f = io.open("/tmp/plugins_v2/sample.lua", "w")
f:write([[
return {
    name = "sample",
    version = "1.0",
    state = nil,
    init = function(config)
        print("sample initialized")
        -- (state setup) 
    end,
    cleanup = function()
        print("sample cleanup")
    end,
    do_work = function(x) return x * 2 end,
}
]])
f:close()

local PS = require "lib.plugin_system"
local sys = PS.new("/tmp/plugins_v2")

sys:on("loaded", function(name) print("[loaded]", name) end)
sys:on("reloaded", function(name) print("[reloaded]", name) end)

sys:load_all({})
-- sample initialized
-- [loaded] sample

local p = sys:get("sample")
print(p.do_work(21))    -- 42

-- Update plik:
local f = io.open("/tmp/plugins_v2/sample.lua", "w")
f:write([[
return {
    name = "sample",
    version = "1.1",
    init = function() print("sample v1.1 initialized") end,
    cleanup = function() print("sample v1.1 cleanup") end,
    do_work = function(x) return x * 100 end,
}
]])
f:close()

-- Czekaj sekundę, żeby mtime się zmienił:
os.execute("sleep 1")

sys:check_changes()
-- sample cleanup
-- sample v1.1 initialized
-- [reloaded] sample

local p = sys:get("sample")
print(p.do_work(21))    -- 2100

-- Cleanup:
os.execute("rm -rf /tmp/plugins_v2")
```

Pełen plugin system z hot reload — fundament dla extensibility w KarmazynOS.

#### Sprawdzian 4

```lua
-- hss/loader.lua

local M = {}

local POLICIES_DIR = "/etc/holonos/policies"

local function _validate_module(mod)
    if type(mod) ~= "table" then return false, "not a table" end
    if type(mod.name) ~= "string" then return false, "missing 'name'" end
    if type(mod.version) ~= "string" then return false, "missing 'version'" end
    if type(mod.apply) ~= "function" then return false, "missing 'apply' function" end
    return true
end

function M.load(name, opts)
    opts = opts or {}
    local max_kb = opts.max_kb or 1024    -- default 1MB
    
    local file_path = POLICIES_DIR .. "/" .. name .. ".lua"
    
    -- Pre-load memory baseline:
    collectgarbage("collect")
    local mem_before = collectgarbage("count")
    
    -- Load:
    local fn, err = loadfile(file_path)
    if not fn then return nil, "load: " .. err end
    
    local ok, mod = pcall(fn)
    if not ok then return nil, "exec: " .. mod end
    
    -- Memory check:
    collectgarbage("collect")
    local mem_after = collectgarbage("count")
    local used_kb = mem_after - mem_before
    
    if used_kb > max_kb then
        return nil, string.format(
            "memory exceeded: used %.1fKB, limit %dKB", used_kb, max_kb)
    end
    
    -- Schema validation:
    local valid, val_err = _validate_module(mod)
    if not valid then return nil, "schema: " .. val_err end
    
    return mod, {used_kb = used_kb, file = file_path}
end

function M.load_all(opts)
    local results = {}
    local f = io.popen("ls " .. POLICIES_DIR .. "/*.lua 2>/dev/null")
    if not f then return results end
    
    for line in f:lines() do
        local name = line:match("([^/]+)%.lua$")
        if name then
            local mod, info_or_err = M.load(name, opts)
            results[name] = {
                ok = mod ~= nil,
                module = mod,
                info_or_err = info_or_err,
            }
        end
    end
    f:close()
    
    return results
end

return M
```

```lua
-- test:
os.execute("mkdir -p /etc/holonos/policies 2>/dev/null || sudo mkdir -p /etc/holonos/policies")

-- Symulacja przez tmpdir:
local TEST_DIR = "/tmp/holonos_test/policies"
os.execute("mkdir -p " .. TEST_DIR)

-- Override paths:
local function load_with_dir(name, opts)
    -- Implementacja używa stałej POLICIES_DIR — przepisana zmienna:
    package.loaded["hss.loader"] = nil
    
    -- Stwórz tymczasowy modified loader:
    -- (W produkcji parametryzujesz POLICIES_DIR jak normalna zmienna)
    return require "hss.loader".load(name, opts)
end

-- Plugin OK:
local f = io.open(TEST_DIR .. "/policy_basic.lua", "w")
f:write([[
return {
    name = "basic",
    version = "1.0",
    apply = function(session) end,
    config = {
        cpu_ms = 500,
        mem_kb = 4096,
    },
}
]])
f:close()

-- Plugin invalid (no name):
local f = io.open(TEST_DIR .. "/policy_invalid.lua", "w")
f:write([[
return {
    version = "1.0",
    apply = function() end,
}
]])
f:close()

-- Plugin "memory bomb":
local f = io.open(TEST_DIR .. "/policy_heavy.lua", "w")
f:write([[
local big = {}
for i = 1, 100000 do
    big[i] = string.rep("x", 100)
end
return {
    name = "heavy",
    version = "1.0",
    apply = function() end,
    _data = big,
}
]])
f:close()

-- (W produkcji — wywołujesz hss.loader.load("policy_basic", {max_kb = 512}))

print("Test struktury — w produkcji ścieżka byłaby parametryczna")

os.execute("rm -rf /tmp/holonos_test")
```

W rzeczywistym kodzie `POLICIES_DIR` byłby parametrem (DI). Przekład pełen funkcjonalności tu — schema validation, memory budget, helpful errors.

#### Sprawdzian 5

```lua
-- lib/container_full.lua

local Container = {}
Container.__index = Container

local SCOPE_SINGLETON = "singleton"
local SCOPE_TRANSIENT = "transient"
local SCOPE_SCOPED = "scoped"

function Container.new(parent)
    return setmetatable({
        _factories = {},
        _scopes = {},          -- name → "singleton" | "transient" | "scoped"
        _instances = {},
        _parent = parent,
        _children = {},        -- list of child containers
    }, Container)
end

function Container:register_singleton(name, factory)
    self._factories[name] = factory
    self._scopes[name] = SCOPE_SINGLETON
end

function Container:register_transient(name, factory)
    self._factories[name] = factory
    self._scopes[name] = SCOPE_TRANSIENT
end

function Container:register_scoped(name, factory)
    self._factories[name] = factory
    self._scopes[name] = SCOPE_SCOPED
end

function Container:_find_registration(name)
    if self._factories[name] then
        return self._factories[name], self._scopes[name], self
    end
    if self._parent then
        return self._parent:_find_registration(name)
    end
    return nil
end

function Container:get(name)
    local factory, scope, owner = self:_find_registration(name)
    if not factory then return nil, "not registered: " .. name end
    
    if scope == SCOPE_SINGLETON then
        if owner._instances[name] then return owner._instances[name] end
        local instance = factory(self)
        owner._instances[name] = instance
        return instance
    elseif scope == SCOPE_TRANSIENT then
        return factory(self)
    elseif scope == SCOPE_SCOPED then
        -- W bieżącym scope (this), nie owner:
        if self._instances[name] then return self._instances[name] end
        local instance = factory(self)
        self._instances[name] = instance
        return instance
    end
end

function Container:has(name)
    return self:_find_registration(name) ~= nil
end

function Container:create_scope()
    local child = Container.new(self)
    table.insert(self._children, child)
    return child
end

function Container:dispose()
    -- Najpierw dzieci:
    for _, child in ipairs(self._children) do
        child:dispose()
    end
    self._children = {}
    
    -- Potem własne instances:
    for name, instance in pairs(self._instances) do
        if type(instance) == "table" then
            if type(instance.dispose) == "function" then
                pcall(instance.dispose, instance)
            elseif type(instance.close) == "function" then
                pcall(instance.close, instance)
            end
        end
    end
    self._instances = {}
end

return Container
```

```lua
-- test:
local Container = require "lib.container_full"

local root = Container.new()

-- Singleton: jedna instancja globalna:
root:register_singleton("logger", function()
    print("creating logger")
    return {
        log = function(self, msg) print("[LOG]", msg) end,
        dispose = function(self) print("disposing logger") end,
    }
end)

-- Transient: nowa za każdym razem:
root:register_transient("request_id", function()
    return "req-" .. os.time() .. "-" .. math.random(1000)
end)

-- Scoped: jedna per scope:
root:register_scoped("session", function(c)
    print("creating session")
    return {
        id = "sess-" .. os.time(),
        logger = c:get("logger"),
        close = function(self) print("closing session " .. self.id) end,
    }
end)

print("--- Root container ---")
local log1 = root:get("logger")    -- creating logger
local log2 = root:get("logger")    -- (cached)
print(log1 == log2)                -- true

local req1 = root:get("request_id")
local req2 = root:get("request_id")
print(req1 ~= req2)                -- true (transient)

local s1 = root:get("session")     -- creating session
local s2 = root:get("session")     -- (cached in root scope)
print(s1 == s2)                    -- true

print("--- Child scope ---")
local scope = root:create_scope()
local s3 = scope:get("session")    -- creating session (! nowa scoped)
print(s3 ~= s1)                    -- true (różny scope)

local log3 = scope:get("logger")
print(log3 == log1)                -- true (singleton inherited)

print("--- Dispose ---")
root:dispose()
-- closing session sess-...   (z root scope)
-- closing session sess-...   (z child scope)
-- disposing logger
```

Pełny container z lifecycle — singleton, transient, scoped. Hierarchical scopes. Dispose pattern. To jest **dokładnie** jak działa Microsoft.Extensions.DependencyInjection w .NET.

#### Sprawdzian 6

```lua
-- lib/pm.lua

local PM = {}
PM.__index = PM

function PM.new()
    return setmetatable({
        installed = {},      -- name → {source, compiled, version}
        loading = {},        -- name → bool (cycle detection)
        loaded = {},         -- name → module
    }, PM)
end

function PM:install(name, source_code, version)
    version = version or "1.0.0"
    self.installed[name] = {
        source = source_code,
        compiled = nil,    -- compile lazily
        version = version,
    }
    -- Invalidate cache:
    self.loaded[name] = nil
end

function PM:uninstall(name)
    if not self.installed[name] then return false, "not installed" end
    self.installed[name] = nil
    self.loaded[name] = nil
end

function PM:require(name)
    -- Sprawdź cache:
    if self.loaded[name] then return self.loaded[name] end
    
    -- Sprawdź czy zainstalowany:
    local pkg = self.installed[name]
    if not pkg then
        error("package not installed: " .. name, 2)
    end
    
    -- Cycle detection:
    if self.loading[name] then
        error("cyclic dependency: " .. name, 2)
    end
    self.loading[name] = true
    
    -- Compile:
    if not pkg.compiled then
        local fn, err = load(pkg.source, name, "t",
            -- Custom env: replace require with our own
            setmetatable({
                require = function(other_name)
                    return self:require(other_name)
                end,
            }, {__index = _G})
        )
        if not fn then
            self.loading[name] = nil
            error("compile failed: " .. err, 2)
        end
        pkg.compiled = fn
    end
    
    -- Execute:
    local ok, mod = pcall(pkg.compiled)
    self.loading[name] = nil
    
    if not ok then
        error("exec failed: " .. mod, 2)
    end
    
    self.loaded[name] = mod
    return mod
end

function PM:list()
    local list = {}
    for name, pkg in pairs(self.installed) do
        list[#list + 1] = {name = name, version = pkg.version}
    end
    table.sort(list, function(a, b) return a.name < b.name end)
    return list
end

function PM:reload(name)
    self.loaded[name] = nil
    -- Compile się może być nieaktualny — zostaje invalidate:
    if self.installed[name] then
        self.installed[name].compiled = nil
    end
    return self:require(name)
end

return PM
```

```lua
-- test:
local PM = require "lib.pm"
local pm = PM.new()

-- Install:
pm:install("greet", [[
local M = {}
function M.hello(name) return "Hello, " .. name .. "!" end
return M
]], "1.0")

pm:install("util", [[
local M = {}
function M.uppercase(s) return s:upper() end
return M
]])

-- Cross-dependency:
pm:install("greet_loud", [[
local greet = require "greet"
local util = require "util"
local M = {}
function M.shout(name)
    return util.uppercase(greet.hello(name))
end
return M
]])

-- Test:
local greet = pm:require("greet")
print(greet.hello("Maciej"))    -- Hello, Maciej!

local greet_loud = pm:require("greet_loud")
print(greet_loud.shout("Anna"))    -- HELLO, ANNA!

-- List:
for _, p in ipairs(pm:list()) do
    print(p.name, p.version)
end
-- greet         1.0
-- greet_loud    1.0.0
-- util          1.0.0

-- Cycle detection:
pm:install("cycle_a", "local b = require 'cycle_b'; return {}")
pm:install("cycle_b", "local a = require 'cycle_a'; return {}")

local ok, err = pcall(function() pm:require("cycle_a") end)
print(ok, err)
-- false   ...:cyclic dependency: cycle_a

-- Uninstall:
pm:uninstall("greet_loud")
print(#pm:list())    -- 2 (greet + util zostały)

-- Reload:
pm:install("greet", [[
local M = {}
function M.hello(name) return "Howdy, " .. name end
return M
]])
local greet_v2 = pm:reload("greet")
print(greet_v2.hello("Maciej"))    -- Howdy, Maciej

-- Old reference?
print(greet.hello("World"))    -- Hello, World!  (! stary moduł)
print(pm.loaded["greet"] == greet_v2)    -- true (nowy w cache)
```

W pamięci package manager z dependency resolution + cycle detection + reload. **Wszystko bez dotykania filesystem**. To dokładnie pattern dla KarmazynOS gdzie polityki/skrypty mogą przyjść z dowolnego źródła (DB, sieć, runtime configuration), nie z plików.

---

## Co dalej?

Zamknięta jest **Część I** kursu — fundamenty języka Lua. Wiesz wszystko, co potrzebne do pisania dowolnie skomplikowanego kodu w Lua.

Od **Modułu 8** zaczyna się **Część II** — embedding w C i KarmazynOS-specific tematy. Pokażesz jak host w C tworzy `lua_State`, ładuje skrypty, ogranicza zasoby, łapie błędy. To jest sedno dla Twojego projektu HSS.

→ **Moduł 8: C API podstawy** — `lua_State`, stos, `luaL_dostring`, wywołania w obie strony, walidacja argumentów, podstawy `luaL_check*`.
