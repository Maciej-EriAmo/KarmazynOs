# Lua dla architektów systemów

## Kurs przyspieszony pod KarmazynOS

> *"Lua to nie język. Lua to mechanizm rozszerzania innego języka."* — Roberto Ierusalimschy (autor Lua), parafraza

---

## 0. Dlaczego Lua nadaje się na lingua franca KarmazynOS

Zanim cokolwiek napiszesz w Lua, warto zrozumieć **czym Lua nie jest**: nie jest językiem aplikacyjnym general-purpose w stylu Pythona. Jest językiem **embedded scripting** — projektowanym od pierwszej linii kodu z myślą o tym, że host jest C/C++, a Lua interpretuje skrypty *wewnątrz* tego hosta.

Stąd wynikają konkretne właściwości:

| Cecha | Wartość | Dlaczego dla KarmazynOS to istotne |
|---|---|---|
| Rozmiar interpretera | ~250 KB statically linked | Mieści się gdziekolwiek, nawet w initramfs |
| Footprint pamięci | ~30 KB minimalna instancja `lua_State` | Możesz mieć 1000 instancji per session |
| Sandboxing | Wbudowany, deterministyczny | `_ENV` daje per-skrypt kompletną izolację |
| GC | Incremental mark-and-sweep | Nie blokuje hosta na długo |
| Korutyny | Symetryczne, zero-cost | Cooperative multitasking bez wątków OS |
| C API | Stack-based, ~50 funkcji | Nie potrzebujesz FFI ani bindingów |
| Brak zależności | tylko ANSI C | Skompilujesz to wszędzie, nawet w kernelu (Lunatik) |

**Konsekwencja dla KarmazynOS / HSS:** Lua może być warstwą gdzie "techpriest" pisze rytuały konfiguracyjne, polityki HSS, hooki LSM (przez Lunatik lub user-space helper), albo skrypty multi-agent pipeline. Każda sesja może mieć własny `lua_State` z odpowiednio przyciętym `_ENV` i twardymi limitami CPU/pamięci. To dokładnie pasuje do filozofii Φ-space.

---

## 1. Podstawy w pigułce (rzeczy, które Cię zaskoczą)

Składnia jest banalna, więc nie będę jej referował od zera. Zamiast tego — **pułapki** dla kogoś przychodzącego z Pythona/C:

### 1.1 Komentarze

```lua
-- jednoliniowy
--[[
  wieloliniowy
  blok komentarza
]]
--[==[ wieloliniowy z poziomem zagnieżdżenia ]==]  -- przydatne gdy w środku jest ]]
```

### 1.2 Zmienne są domyślnie GLOBALNE

To jest punkt #1 do zapamiętania. **Zawsze pisz `local`.**

```lua
x = 10        -- globalna! Wpisana do _G (lub _ENV)
local y = 20  -- lokalna do bloku/funkcji
```

W KarmazynOS to ma znaczenie bezpieczeństwa: skrypt, który zapomniał `local`, dziurawi środowisko. Linter z `-Wstrict-globals` to obowiązek.

### 1.3 Typy

```lua
nil       -- jak None/NULL
boolean   -- true / false
number    -- domyślnie 64-bit float; od 5.3 osobno integer i float
string    -- niezmienne, internowane
table     -- JEDYNA struktura danych (sic!)
function  -- first-class
thread    -- korutyna
userdata  -- opaque pointer z C
```

### 1.4 Tylko `nil` i `false` są fałszywe

```lua
if 0 then print("0 jest prawdziwe!") end   -- wypisze
if "" then print("pusty string też!") end  -- wypisze
```

Pułapka po Pythonie/C. W Pythonie `0` jest falsy, w C `0` jest false. W Lua **tylko `nil` i `false`**.

### 1.5 Operatory, które wyglądają inaczej

```lua
~=    -- nierówność (NIE !=)
..    -- konkatenacja stringów
#t    -- długość tabeli/stringa
and / or / not   -- logiczne, nie &&/||/!
//    -- dzielenie całkowitoliczbowe (5.3+)
```

### 1.6 Indeksowanie od 1

```lua
local t = {"a", "b", "c"}
print(t[1])  -- "a"   (NIE "b"!)
print(t[0])  -- nil
```

Tak. Od 1. Można nad tym filozofować, można płakać, można się przyzwyczaić. W KarmazynOS API zaprojektuj świadomie — jeśli mieszasz Lua z C, ustal jedną konwencję na granicy.

### 1.7 String — kilka fajnych rzeczy

```lua
local s = "hello"
print(#s)           -- 5
print(s:upper())    -- "HELLO"  (! metoda na stringu)
print(s:sub(1, 3))  -- "hel"
print(string.format("hex: %x", 255))  -- "hex: ff"

-- Long string (raw, bez escape):
local sql = [[
  SELECT * FROM holons
  WHERE phi > 0.5
]]
```

Wzorce (patterns) Lua to *nie* regex — są podobne, ale uboższe i szybsze. Składnia: `%d`, `%a`, `%s`, `+`, `*`, `-` (lazy), `?`. Dla pełnego regex: zewnętrzna biblioteka (lpeg, rex_pcre).

### 1.8 Conditional / loop

```lua
if x > 0 then
  print("plus")
elseif x < 0 then
  print("minus")
else
  print("zero")
end

for i = 1, 10 do print(i) end          -- numeric for
for i = 10, 1, -1 do print(i) end      -- ze step
for k, v in pairs(t) do ... end        -- generic for
for i, v in ipairs(t) do ... end       -- po tablicy

while cond do ... end
repeat ... until cond                   -- do-while
```

**Nie ma `continue`.** Używa się `goto continue` z etykietą `::continue::` na końcu pętli (od 5.2). Tak, brzydkie.

```lua
for i = 1, 10 do
  if i % 2 == 0 then goto continue end
  print(i)
  ::continue::
end
```

---

## 2. Tabele — serce Lua

To jest moment, w którym Lua przestaje być "kolejnym językiem skryptowym" i staje się czymś charakterystycznym. **Tabela to jedyna złożona struktura danych w Lua** — i jest jednocześnie tablicą, słownikiem, obiektem, namespace'em, modułem, klasą i prototypem.

### 2.1 Konstrukcja

```lua
local t = {}                    -- pusta
local t = {10, 20, 30}          -- "tablica" (klucze 1, 2, 3)
local t = {x = 1, y = 2}        -- "rekord"  (klucze "x", "y")
local t = {                     -- mieszanka
  "first",                       -- t[1]
  "second",                      -- t[2]
  name = "holon",                -- t.name
  [42] = "answer",               -- t[42]
}
```

### 2.2 Dostęp

```lua
t.x          -- syntactic sugar dla t["x"]
t["x"]       -- to samo
t[1]         -- indeks numeryczny
t[fn]        -- klucz może być DOWOLNĄ wartością nie-nil (nawet funkcją)
```

Klucz może być wszystkim oprócz `nil` i `NaN`. Tak, kluczem może być inna tabela — to się przydaje w mapach przez tożsamość referencji.

### 2.3 Iteracja — `pairs` vs `ipairs`

```lua
local t = {10, 20, 30, name = "x"}

for k, v in ipairs(t) do print(k, v) end
-- 1  10
-- 2  20
-- 3  30
-- (zatrzymuje się na pierwszym nil; ignoruje klucze nie-numeryczne)

for k, v in pairs(t) do print(k, v) end
-- 1  10
-- 2  20
-- 3  30
-- name  x
-- (kolejność niezdefiniowana dla części hash)
```

**Pułapka:** `ipairs` zatrzymuje się na pierwszym `nil`. Jeśli masz tabelę `{1, 2, nil, 4}` — `ipairs` wypisze tylko 2 elementy, a `#t` może zwrócić 2 lub 4 (niezdefiniowane). **W Lua nie wkładamy `nil` do tablic.** Jeśli musisz reprezentować "puste miejsce", użyj sentinela albo struktury z osobnym `length`.

### 2.4 Standardowa biblioteka tabel

```lua
table.insert(t, "x")           -- append
table.insert(t, 1, "x")        -- insert na pozycji
table.remove(t)                -- pop z końca
table.remove(t, 1)             -- remove z pozycji
table.concat({"a","b","c"}, ", ")  -- "a, b, c"
table.sort(t)                  -- in-place
table.sort(t, function(a, b) return a.phi > b.phi end)
table.unpack(t)                -- multiple values (5.2+; w 5.1 to po prostu unpack)
```

### 2.5 Tabele to referencje

```lua
local a = {1, 2, 3}
local b = a
b[1] = 99
print(a[1])  -- 99
```

Jak w Pythonie z listami. Kopiowanie głębokie pisze się ręcznie albo bierze z biblioteki.

### 2.6 Praktycznie: tabela jako wszystko

```lua
-- jako rekord
local holon = {phi = 0.7, sig = "abc123", born_at = os.time()}

-- jako enum
local State = {IDLE = 1, ACTIVE = 2, DEAD = 3}
print(State.ACTIVE)

-- jako namespace / moduł
local hss = {}
function hss.spawn(phi) return {phi = phi} end
function hss.kill(h)   h.phi = 0 end

-- jako set (klucz to element, wartość to true)
local seen = {}
seen["abc"] = true
if seen["abc"] then ... end
```

---

## 3. Funkcje — first-class, closures, multiple return

### 3.1 Definicja

```lua
local function add(a, b)
  return a + b
end

-- to samo:
local add = function(a, b) return a + b end

-- Składnia z kropką:
hss.spawn = function(phi) ... end
-- to dokładny ekwiwalent
function hss.spawn(phi) ... end
```

### 3.2 Multiple return values

To jedna z lepszych rzeczy w Lua.

```lua
local function divmod(a, b)
  return a // b, a % b
end

local q, r = divmod(17, 5)   -- q=3, r=2
```

Pułapka: w wyrażeniach złożonych tylko **ostatni** wynik się rozwija.

```lua
local function f() return 1, 2 end
local t = {f(), f()}     -- {1, 1, 2}  -- pierwsze f() obcięte do 1, drugie rozwinięte
local t = {f()}          -- {1, 2}
print(f(), 99)           -- 1   99   -- f() obcięte
print(99, f())           -- 99  1   2 -- f() rozwinięte
```

To jest spójne, ale na początku gryzie.

### 3.3 Varargs

```lua
local function log(level, ...)
  local args = {...}
  local n = select('#', ...)   -- liczba argumentów (! nie #args, bo nil)
  for i = 1, n do
    io.write(tostring(args[i]), " ")
  end
  io.write("\n")
end

log("INFO", "phi=", 0.7, nil, "sig=abc")
```

`select('#', ...)` jest preferowane nad `#{...}` bo poprawnie liczy z nilami w środku.

### 3.4 Closures

```lua
local function counter()
  local n = 0
  return function()
    n = n + 1
    return n
  end
end

local c = counter()
print(c())  -- 1
print(c())  -- 2
print(c())  -- 3
```

Closure trzyma referencję do **upvalue** — zmiennej z otaczającego scope. To podstawa wszystkiego: stanu, modułów, prywatności.

### 3.5 Składnia metody — `:` vs `.`

```lua
local obj = {name = "holon"}

function obj.get_name(self)        -- definiowane z kropką
  return self.name
end

print(obj.get_name(obj))           -- musisz ręcznie podać self
print(obj:get_name())              -- składnia : automatycznie podaje self

-- I odwrotnie przy definicji:
function obj:get_name()            -- : w definicji = ukryty parametr self
  return self.name
end
```

Reguła kciuka: `:` w wywołaniu == `:` w definicji. Mieszanie działa, ale czytaj wtedy uważnie.

---

## 4. Metatable i metametody — magia Lua

To jest miejsce, gdzie Lua naprawdę staje się ciekawa. Każda tabela może mieć **metatable** — drugą tabelę, która definiuje "co robić, gdy ktoś próbuje X" dla pierwszej tabeli.

### 4.1 `__index` — fallback dla brakujących kluczy

```lua
local default = {phi = 0.0, alive = true}
local h = {sig = "abc"}

setmetatable(h, {__index = default})

print(h.sig)    -- "abc"   (jest w h)
print(h.phi)    -- 0.0     (nie ma w h, więc szuka w default)
print(h.alive)  -- true    (j.w.)
```

`__index` może być tabelą **albo funkcją**:

```lua
setmetatable(h, {__index = function(t, key)
  return "default_" .. key
end})

print(h.foo)  -- "default_foo"
```

Tu jest dynamiczna obsługa "wszystkich" kluczy. Bardzo przydatne dla proxy obiektów.

### 4.2 `__newindex` — przechwyć przypisanie

```lua
local readonly = setmetatable({}, {
  __newindex = function(t, k, v)
    error("nie ruszaj kapłanie, tabela poświęcona", 2)
  end
})

readonly.x = 5  -- error!
```

W KarmazynOS bardzo użyteczne do robienia frozen contextów.

### 4.3 Pełna lista metametod

```lua
__add    -- a + b
__sub    -- a - b
__mul    -- a * b
__div    -- a / b
__mod    -- a % b
__pow    -- a ^ b
__unm    -- -a
__concat -- a .. b
__len    -- #a
__eq     -- a == b   (używane tylko gdy oba operandy mają TEN SAM metatable)
__lt     -- a < b
__le     -- a <= b
__index    -- a.x   gdy x nie istnieje w a
__newindex -- a.x = v
__call   -- a(...)  -- tabela wywoływana jak funkcja!
__tostring -- tostring(a)
__metatable -- chroni metatable przed odczytem/zmianą
__gc     -- finalizator (uwaga: tylko dla userdata w 5.1, dla tabel od 5.2)
__mode   -- "k", "v", "kv" -- weak tables
```

### 4.4 OOP idiomatyczne

```lua
-- Klasa Holon
local Holon = {}
Holon.__index = Holon            -- TO jest klucz: metatable wskazuje na Holon

function Holon.new(sig, phi)
  local self = setmetatable({}, Holon)
  self.sig = sig
  self.phi = phi or 0.0
  self.alive = true
  return self
end

function Holon:decay(dt)
  self.phi = self.phi * math.exp(-dt)
  if self.phi < 1e-6 then
    self.alive = false
  end
end

function Holon:__tostring()
  return string.format("Holon<%s, phi=%.3f, %s>",
    self.sig, self.phi, self.alive and "alive" or "dead")
end

-- Użycie:
local h = Holon.new("abc123", 0.9)
h:decay(0.5)
print(h)   -- Holon<abc123, phi=0.546, alive>
```

Co tu się stało:
1. `Holon` jest tabelą i jednocześnie metatable.
2. `Holon.__index = Holon` — gdy w `self` nie ma metody, szukaj w `Holon`.
3. `Holon.new` tworzy instancję i ustawia jej metatable na `Holon`.
4. Metody pisane z `:` mają ukryty `self`.

Dziedziczenie: tworzysz nową klasę i ustawiasz jej `__index` na klasę bazową. Ale w praktyce w embedded use-case (KarmazynOS) — często wystarcza kompozycja zamiast dziedziczenia.

### 4.5 Weak tables — przydatne dla cache

```lua
local cache = setmetatable({}, {__mode = "v"})  -- wartości słabe
cache[key] = some_object
-- Gdy some_object przestanie być referencjonowany skądinąd, GC go zmiecie
-- i cache[key] stanie się nil.
```

Bardzo użyteczne dla LRU-podobnych struktur albo "obserwatorów" które nie powinny trzymać obserwowanego przy życiu.

---

## 5. Obsługa błędów

Lua nie ma try/catch. Ma za to coś prostszego: **`pcall`** (protected call).

### 5.1 `error` i `pcall`

```lua
local function risky()
  error("coś się zepsuło")
end

local ok, err = pcall(risky)
if not ok then
  print("złapano:", err)   -- "złapano: <plik>:linia: coś się zepsuło"
end
```

`pcall(f, ...)` wywołuje `f(...)` w "trybie chronionym". Jeśli `f` rzuca błąd — `pcall` zwraca `false, error_obj` zamiast propagować. Jeśli OK — zwraca `true, ...wszystkie_wyniki_f`.

### 5.2 `xpcall` — z handlerem

```lua
local function handler(err)
  return debug.traceback(err, 2)
end

local ok, err = xpcall(risky, handler)
if not ok then
  print(err)   -- pełen stack trace
end
```

W KarmazynOS `xpcall` z handlerem logującym do dziennika sesji to standard.

### 5.3 `error` — poziomy

```lua
error("msg")        -- wskazuje na linię gdzie został wywołany error()
error("msg", 2)     -- wskazuje na callera (przydatne gdy error() jest w funkcji walidującej)
error("msg", 0)     -- bez info o lokalizacji
```

Możesz też rzucić **dowolnym obiektem**, nie tylko stringiem:

```lua
error({code = 42, msg = "phi out of range"})
-- ...
local ok, err = pcall(...)
if not ok and type(err) == "table" then
  print(err.code, err.msg)
end
```

### 5.4 `assert`

```lua
assert(phi >= 0 and phi <= 1, "phi musi być w [0,1]")
-- Równoważne:
if not (phi >= 0 and phi <= 1) then error("phi musi być w [0,1]") end
```

---

## 6. Korutyny — cooperative multitasking

To jest funkcja, która sama uzasadnia używanie Lua. Korutyny to **symetryczne korutyny** (nie generatory ani async/await — coś bardziej fundamentalnego).

### 6.1 Podstawy

```lua
local co = coroutine.create(function(x)
  print("krok 1", x)
  local y = coroutine.yield(x * 2)
  print("krok 2", y)
  local z = coroutine.yield(y + 1)
  print("krok 3", z)
  return "koniec"
end)

print(coroutine.resume(co, 10))  -- "krok 1   10"  -> true, 20
print(coroutine.resume(co, 99))  -- "krok 2   99"  -> true, 100
print(coroutine.resume(co, 7))   -- "krok 3   7"   -> true, "koniec"
print(coroutine.resume(co))      -- false, "cannot resume dead coroutine"
```

Co się dzieje:
- `create` tworzy korutynę — *nie* uruchamia jej.
- `resume` rusza ją lub wznawia. Argumenty `resume` lecą do `yield` (drugiego i kolejnych), a wartości z `yield` wracają jako kolejne wyniki `resume`.
- Korutyna nie ma własnego wątku OS — to po prostu zachowany stos.

### 6.2 `coroutine.wrap` — wygodniejsze API

```lua
local gen = coroutine.wrap(function()
  for i = 1, 5 do
    coroutine.yield(i * i)
  end
end)

print(gen())  -- 1
print(gen())  -- 4
print(gen())  -- 9
```

`wrap` zwraca funkcję — każde wywołanie to `resume`. Wadą jest brak ochrony przed błędami (propagują się), więc do produkcji często wracamy do `create`/`resume` z `pcall`.

### 6.3 Praktyczne zastosowania w KarmazynOS

- **Pipeline multi-agent:** każdy agent to korutyna, scheduler je rotuje.
- **Cooperative I/O:** korutyna `yield`-uje gdy czeka na deskryptor, scheduler ją wznawia gdy fd ready (model OpenResty / cqueues).
- **Long-running scripts:** każde N instrukcji `yield` daje hostowi szansę przerwać (mechanizm `lua_sethook` z `LUA_MASKCOUNT`).
- **Generatory:** lazy sekwencje danych z dużego źródła.

```lua
-- Przykład: generator wszystkich podziałów liczby (lazy)
local function partitions(n)
  return coroutine.wrap(function()
    local function aux(remaining, max, prefix)
      if remaining == 0 then
        coroutine.yield(prefix)
        return
      end
      for i = math.min(remaining, max), 1, -1 do
        local new_prefix = {}
        for j = 1, #prefix do new_prefix[j] = prefix[j] end
        new_prefix[#new_prefix + 1] = i
        aux(remaining - i, i, new_prefix)
      end
    end
    aux(n, n, {})
  end)
end

for p in partitions(5) do
  print(table.concat(p, "+"))
end
-- 5
-- 4+1
-- 3+2
-- 3+1+1
-- 2+2+1
-- 2+1+1+1
-- 1+1+1+1+1
```

---

## 7. Moduły i `require`

### 7.1 Pisanie modułu

Plik `holon.lua`:

```lua
local M = {}

local function _internal()  -- prywatne, nie eksportowane
  return 42
end

function M.spawn(sig, phi)
  return {sig = sig, phi = phi or 0.0}
end

function M.is_alive(h)
  return h.phi > 1e-6
end

M.VERSION = "0.1.0"

return M
```

### 7.2 Używanie

```lua
local holon = require "holon"

local h = holon.spawn("abc", 0.7)
print(holon.is_alive(h))
print(holon.VERSION)
```

`require` szuka pliku w ścieżkach z `package.path`. Kompiluje plik raz (rezultat `return M` jest cache'owany w `package.loaded`), więc kolejne `require` zwraca to samo. To pozwala mieć stan modułowy bez globalnych.

### 7.3 Wstrzykiwanie modułów (dla embeddingu)

W KarmazynOS często chcesz, by skrypt **nie miał** dostępu do `require`, a zamiast tego dostawał gotowe moduły wstrzyknięte z hosta. Wtedy konstruujesz `_ENV` ręcznie (patrz sekcja o sandboxingu).

---

## 8. C API — sedno embeddingu

To jest sekcja, która dla KarmazynOS jest najważniejsza. Lua jest projektowana tak, że host w C **kontroluje wszystko**: tworzy interpreter, wstrzykuje funkcje, ładuje skrypty, łapie błędy, ogranicza zasoby.

### 8.1 Model: stos

Cały interfejs C ↔ Lua chodzi przez **stos** powiązany z `lua_State *L`. Wszystko co przekazujesz między C a Lua jedzie przez ten stos.

Stos jest indeksowany od **1** (od dołu) i od **-1** (od góry, top). `-1` to top, `-2` to element pod topem itd.

### 8.2 Minimalny embedding

```c
#include <stdio.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

int main(void) {
    lua_State *L = luaL_newstate();   // 1. utwórz interpreter
    luaL_openlibs(L);                  // 2. załaduj standardową bibliotekę

    int rc = luaL_dostring(L,          // 3. wykonaj skrypt
        "print('hello from Lua, '..jit and 'with LuaJIT' or 'plain Lua')");
    if (rc != LUA_OK) {
        fprintf(stderr, "Lua error: %s\n", lua_tostring(L, -1));
        lua_pop(L, 1);
    }

    lua_close(L);                      // 4. sprzątanie
    return 0;
}
```

Kompilacja (po `apt install liblua5.4-dev`):
```bash
gcc -o demo demo.c -llua5.4 -lm -ldl
```

### 8.3 Wywołanie funkcji Lua z C

```c
// Wywołaj Lua: result = compute(0.7, 0.3)
lua_getglobal(L, "compute");      // push funkcji
lua_pushnumber(L, 0.7);           // push arg1
lua_pushnumber(L, 0.3);           // push arg2

if (lua_pcall(L, 2, 1, 0) != LUA_OK) {  // 2 argi, 1 wynik, 0 = bez msgh
    fprintf(stderr, "call failed: %s\n", lua_tostring(L, -1));
    lua_pop(L, 1);
    return -1;
}

double result = lua_tonumber(L, -1);
lua_pop(L, 1);
```

`lua_pcall` jest *protected* — łapie błędy. `lua_call` ich nie łapie i wywala host przy panic. **W KarmazynOS zawsze `lua_pcall`.**

### 8.4 Rejestracja funkcji C dla Lua

```c
// Funkcja w stylu Lua: bierze args ze stosu, kładzie wyniki na stos,
// zwraca liczbę wyników.
static int l_phi_distance(lua_State *L) {
    double a = luaL_checknumber(L, 1);
    double b = luaL_checknumber(L, 2);
    double d = (a - b) * (a - b);   // tutaj prawdziwa metryka
    lua_pushnumber(L, d);
    return 1;  // jeden wynik na stosie
}

// Rejestracja jako global "phi_distance":
lua_pushcfunction(L, l_phi_distance);
lua_setglobal(L, "phi_distance");

// Albo lepiej — jako moduł:
static const luaL_Reg hss_lib[] = {
    {"phi_distance", l_phi_distance},
    {"spawn",        l_spawn},
    {"sign",         l_sign},
    {NULL, NULL}
};

luaL_newlib(L, hss_lib);
lua_setglobal(L, "hss");
// W skrypcie: hss.phi_distance(0.7, 0.3)
```

`luaL_check*` automatycznie rzucają błąd Lua jeśli typ się nie zgadza — to jest właściwa droga walidacji argumentów.

### 8.5 Userdata — opaque pointery

Gdy chcesz, by skrypt trzymał **referencję do struktury C** (np. handle do Φ-space session) bez możliwości jej modyfikacji od środka:

```c
typedef struct {
    char sig[32];
    double phi;
    void *internal;
} hss_session_t;

// Tworzenie nowej sesji z C (zwraca userdata na stosie):
static int l_session_new(lua_State *L) {
    const char *sig = luaL_checkstring(L, 1);
    
    hss_session_t *s = lua_newuserdata(L, sizeof(hss_session_t));
    snprintf(s->sig, sizeof(s->sig), "%s", sig);
    s->phi = 0.0;
    s->internal = NULL;
    
    // Ustaw metatable (zarejestrowany wcześniej):
    luaL_getmetatable(L, "hss.session");
    lua_setmetatable(L, -2);
    
    return 1;  // userdata na topie stosu
}

// Metoda: session:phi()
static int l_session_phi(lua_State *L) {
    hss_session_t *s = luaL_checkudata(L, 1, "hss.session");
    lua_pushnumber(L, s->phi);
    return 1;
}

// Finalizator (wywołany przez GC Lua):
static int l_session_gc(lua_State *L) {
    hss_session_t *s = luaL_checkudata(L, 1, "hss.session");
    if (s->internal) {
        free(s->internal);
        s->internal = NULL;
    }
    return 0;
}

// W init:
luaL_newmetatable(L, "hss.session");

lua_pushstring(L, "__index");
lua_newtable(L);
lua_pushcfunction(L, l_session_phi);
lua_setfield(L, -2, "phi");
// ... więcej metod
lua_settable(L, -3);

lua_pushcfunction(L, l_session_gc);
lua_setfield(L, -2, "__gc");

lua_pop(L, 1);  // pop metatable
```

Z perspektywy skryptu Lua:
```lua
local s = hss.session_new("abc123")
print(s:phi())   -- wywoła l_session_phi
-- Gdy s wyjdzie z scope i GC odpali — wywoła się l_session_gc
```

`luaL_checkudata` weryfikuje, że userdata ma odpowiedni metatable (czyli jest rzeczywiście `hss.session`). Bez tego skrypt mógłby Ci podać dowolny pointer i crashować host.

### 8.6 Ograniczanie zasobów — hooks

```c
static int instruction_count = 0;
static const int MAX_INSTRUCTIONS = 1000000;

static void instruction_hook(lua_State *L, lua_Debug *ar) {
    instruction_count += 100;
    if (instruction_count > MAX_INSTRUCTIONS) {
        luaL_error(L, "instruction quota exhausted");
    }
}

// Po załadowaniu skryptu, przed wykonaniem:
lua_sethook(L, instruction_hook, LUA_MASKCOUNT, 100);
// "co 100 instrukcji wywołaj hook"
```

To jest prosty mechanizm CPU quota. Dla pamięci masz `lua_setallocf` — własny alokator, który możesz przerwać po przekroczeniu limitu.

---

## 9. Sandboxing — jak nie wpuścić demonów

W KarmazynOS, gdzie skrypty są niezaufane (multi-agent, user-supplied), sandboxing jest obowiązkowy. Lua daje do tego naprawdę porządne narzędzia.

### 9.1 Zasada: kontroluj `_ENV`

Od Lua 5.2 każdy chunk ma niejawny upvalue `_ENV` — to jest "globalna tabela" dla tego chunka. Zmieniając ją, zmieniasz co skrypt widzi jako globalne.

```c
// W C: skompiluj kawałek kodu, ale zanim go uruchomisz,
// podmień _ENV na okrojoną tabelę.

if (luaL_loadstring(L, user_code) != LUA_OK) { /* error */ }
// teraz na stosie jest funkcja-chunk

// Zbuduj okrojony _ENV:
lua_newtable(L);                  // env = {}

lua_getglobal(L, "print");        // wpuść print
lua_setfield(L, -2, "print");

lua_getglobal(L, "math");         // wpuść math (cały moduł)
lua_setfield(L, -2, "math");

lua_getglobal(L, "string");
lua_setfield(L, -2, "string");

// Wpuść hss (nasz custom moduł):
lua_getglobal(L, "hss");
lua_setfield(L, -2, "hss");

// Ustaw env jako _ENV chunka (upvalue #1 chunka):
const char *upname = lua_setupvalue(L, -2, 1);
// upname powinno być "_ENV"; jeśli nie — coś się stało nie tak

if (lua_pcall(L, 0, 0, 0) != LUA_OK) { /* error */ }
```

W tej konfiguracji skrypt **nie zobaczy** `os`, `io`, `debug`, `package`, `require`, `dofile`, `loadfile`, `load`, `_G`. Czyli nie otworzy pliku, nie odpali procesu, nie załaduje innego kodu, nie zhakuje hosta przez `debug.getinfo`.

### 9.2 Lista funkcji do **zdecydowanego** odcięcia

```
os.execute, os.remove, os.rename, os.exit, os.getenv, os.tmpname
io.*  (cały moduł — chyba że dostarczysz własny stub)
debug.*  (cały moduł — debug.sethook, debug.setupvalue itd. = ucieczka z piaskownicy)
package.*  (require, package.loadlib)
load, loadfile, dofile, loadstring
```

Te funkcje albo same w sobie są niebezpieczne, albo pozwalają obejść sandbox.

### 9.3 String — ostrożnie

`string.dump` pozwala zserializować funkcję do bytecode'u. `load` (gdyby był dostępny) potrafi załadować bytecode — i fałszywy bytecode może crashować interpreter. **Albo wyłącz `string.dump`, albo wymuś `load(s, name, "t")` (text-only).**

### 9.4 Per-skrypt timeout + memory cap

Połącz okrojone `_ENV` z hookiem instrukcji + custom alokatorem z limitem. Wtedy nawet skrypt złośliwy z `while true do end` ginie po N instrukcjach, a `string.rep("x", 1e9)` ginie na alokatorze.

### 9.5 Konkretnie dla HSS

```c
// Per session:
typedef struct {
    lua_State *L;
    size_t mem_used;
    size_t mem_limit;
    int    instr_used;
    int    instr_limit;
} hss_lua_session_t;

static void *limited_alloc(void *ud, void *ptr, size_t osize, size_t nsize) {
    hss_lua_session_t *s = (hss_lua_session_t *)ud;
    if (nsize == 0) {
        if (ptr) s->mem_used -= osize;
        free(ptr);
        return NULL;
    }
    if (s->mem_used + nsize - (ptr ? osize : 0) > s->mem_limit) {
        return NULL;  // alokator zwraca NULL = Lua rzuca "not enough memory"
    }
    void *new_ptr = realloc(ptr, nsize);
    if (new_ptr) {
        s->mem_used += nsize - (ptr ? osize : 0);
    }
    return new_ptr;
}

// Tworzenie sesji:
hss_lua_session_t *s = calloc(1, sizeof(*s));
s->mem_limit  = 4 * 1024 * 1024;   // 4 MB
s->instr_limit = 1000000;
s->L = lua_newstate(limited_alloc, s);
// ... openlibs (selektywnie!), setup _ENV, sethook ...
```

---

## 10. LuaJIT — kiedy i czy

LuaJIT to alternatywna implementacja Lua 5.1 (z częścią rzeczy z 5.2) z trace-compilerem. Często **3-50x szybsza** od standardowego Lua. Plus daje FFI:

```lua
local ffi = require "ffi"
ffi.cdef[[
    int printf(const char *fmt, ...);
    typedef struct { double x, y; } point_t;
]]

ffi.C.printf("hello from FFI\n")
local p = ffi.new("point_t", 1.0, 2.0)
print(p.x, p.y)
```

FFI pozwala wołać dowolne funkcje C bez pisania bindingów. To genialne i niebezpieczne jednocześnie. **W sandboxowanym kontekście KarmazynOS — wyłącz FFI.** Dla zaufanych skryptów hosta — używaj.

Wady LuaJIT:
- Stoi technologicznie na 5.1 (z dodatkami), nie ma wszystkich rzeczy z 5.3/5.4 (np. integer/float split).
- Mniej aktywny rozwój niż dawniej.
- Większy footprint niż referencyjny Lua.

Decyzja dla KarmazynOS: **referencyjny Lua 5.4** dla skryptów niezaufanych (sandbox + małe state'y), **LuaJIT** dla zaufanych komponentów hosta gdzie liczy się wydajność (np. parser polityk, transformacje Φ-space).

---

## 11. Praktyka: DSL konfiguracyjny dla HSS

Złóżmy to wszystko w coś, co realnie pasuje do KarmazynOS. DSL do definiowania polityk sesji HSS:

```lua
-- /etc/holonos/policies/default.lua

policy "default" {
    description = "Domyślna polityka sesji HSS",
    
    quota {
        cpu_ms       = 500,
        mem_kb       = 4096,
        atoms_max    = 1000,
        epoch_max    = 100,
    },
    
    capabilities {
        "phi.read",
        "phi.write",
        "session.spawn",
        -- "session.kill",     -- zakomentowane = niedozwolone
    },
    
    on_atom_create = function(atom)
        if atom.phi > 0.95 then
            log.warn("nietypowo wysokie phi", atom.sig)
        end
    end,
    
    on_session_end = function(session)
        log.info("sesja zakończona, atomów żywych:", session.alive_count())
    end,
}

policy "techpriest_strict" {
    inherits = "default",
    quota { cpu_ms = 100, mem_kb = 1024 },
    capabilities { "phi.read" },   -- read-only
}
```

Implementacja DSL po stronie Lua (host wstrzykuje funkcje `policy`, `quota`, `capabilities`, `log`):

```lua
-- policy_dsl.lua
local M = {}
local registered = {}

local function quota(t)   return {kind = "quota",        data = t} end
local function capabilities(t) return {kind = "capabilities", data = t} end

local function policy(name)
    return function(spec)
        local p = {
            name = name,
            description = spec.description,
            inherits = spec.inherits,
            quota = nil,
            capabilities = {},
            hooks = {},
        }
        for _, item in ipairs(spec) do
            if type(item) == "table" then
                if item.kind == "quota" then
                    p.quota = item.data
                elseif item.kind == "capabilities" then
                    for _, cap in ipairs(item.data) do
                        p.capabilities[cap] = true
                    end
                end
            end
        end
        for k, v in pairs(spec) do
            if type(v) == "function" and k:match("^on_") then
                p.hooks[k] = v
            end
        end
        registered[name] = p
        return p
    end
end

function M.load(path)
    local env = {
        policy = policy,
        quota = quota,
        capabilities = capabilities,
        log = {info = print, warn = print, error = print},
    }
    local chunk, err = loadfile(path, "t", env)
    if not chunk then return nil, err end
    local ok, e = pcall(chunk)
    if not ok then return nil, e end
    return registered
end

function M.resolve(name)
    local p = registered[name]
    if not p then return nil end
    if p.inherits then
        local parent = M.resolve(p.inherits)
        if parent then
            -- merge: dziecko nadpisuje, ale dziedziczy capabilities
            local merged = {}
            for k, v in pairs(parent) do merged[k] = v end
            for k, v in pairs(p) do
                if v ~= nil then merged[k] = v end
            end
            return merged
        end
    end
    return p
end

return M
```

I host w C ładuje to:

```c
// hss_policy_load(L, "/etc/holonos/policies/default.lua");
// Następnie z C: hss_policy_check_quota(p, ...) odwołuje się do skompilowanej tabeli.
```

To jest prawdziwy use-case. Plik konfiguracyjny **jest skryptem Lua** — i to daje Ci za darmo: warunki, pętle, dziedziczenie, hooki, walidację, komentarze. Coś, czego nigdy nie da Ci YAML czy TOML.

---

## 12. Ścieżka dalszej nauki

Gdy ten kurs przemyślisz na spokojnie, kolejne kroki:

1. **"Programming in Lua"** Roberto Ierusalimschy — autor języka, aktualnie 4. edycja (Lua 5.3). Najlepsza książka. Pierwsza edycja jest free online (na lua.org), nieco zdezaktualizowana ale fundamenty się nie zmieniły.

2. **lua-users wiki** (lua-users.org/wiki) — kopalnia wzorców i tricków.

3. **OpenResty / lua-nginx-module** — jeśli interesuje Cię embedding Lua w wysokowydajnym serwerze, to flagowa implementacja. Pokazuje też świetnie cooperative I/O na korutynach.

4. **Lunatik** (github.com/luainkernel/lunatik) — Lua w kernelu Linuksa. Idealne dla Twojego LSM-style use case'u.

5. **lua-resty-string, lua-resty-jit-uuid, lua-resty-lock** — biblioteki, które warto przejrzeć stylistycznie. Pisanie idiomatycznego Lua to oddzielna umiejętność.

6. **LPeg** (Roberto Ierusalimschy) — Parsing Expression Grammars. Genialny do parserów DSL-i. Jeśli HSS będzie miał własny język polityk poza Lua DSL — LPeg jest narzędziem.

---

## Dodatek: szybka referencja

```lua
-- Tworzenie sesji w stylu KarmazynOS:
local function make_session(sig, phi_init)
    local self = {
        sig         = sig,
        phi         = phi_init or 0.0,
        atoms       = {},
        epoch       = 0,
        born_at     = os.time(),
    }
    
    function self:add_atom(atom)
        atom.epoch = self.epoch
        table.insert(self.atoms, atom)
        return #self.atoms
    end
    
    function self:tick(dt)
        self.epoch = self.epoch + 1
        for i = #self.atoms, 1, -1 do
            local a = self.atoms[i]
            a.phi = a.phi * math.exp(-dt)
            if a.phi < 1e-6 then
                table.remove(self.atoms, i)
            end
        end
    end
    
    function self:alive_count()
        return #self.atoms
    end
    
    return self
end

-- Użycie:
local s = make_session("abc123", 0.9)
s:add_atom({phi = 0.7, sig = "x1"})
s:add_atom({phi = 0.3, sig = "x2"})
s:tick(0.5)
print(s:alive_count())
```

To wszystko bez metatable — closures wystarczają. Wybierz styl, który Ci pasuje (closures vs metatable OOP) i konsekwentnie go trzymaj w kodzie KarmazynOS.

---

*Kurs wersja 1.0, dla KarmazynOS / HSS.  
Następny krok rekomendowany: napisz mały DSL polityki HSS w Lua i osadź go w C-helperze user-space.*
