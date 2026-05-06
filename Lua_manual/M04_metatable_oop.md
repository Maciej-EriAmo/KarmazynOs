# Moduł 4: Metatable i OOP

> *"Lua nie ma klas. Lua ma metatable, a klasy to tylko jeden ze sposobów ich użycia."*

Metatable to mechanizm, który pozwala tabeli **kontrolować jak działają na niej operatory i podstawowe operacje**. To Lua's wersja "magicznych metod" Pythona (`__init__`, `__add__`) lub "operator overloading" w C++. Z metatable budujemy: klasy, dziedziczenie, immutable struct, lazy ewaluację, proxy, defaultdict, modyfikowalne fallback'i.

To jest najobszerniejszy moduł części I — 6 lekcji zamiast standardowych 5.

**Przewidywany czas:** 7-9 godzin pracy.

**Lekcje:**
1. `__index` i `__newindex` — fallback i przechwycenie
2. Operatory: `__add`, `__eq`, `__lt`, `__concat`, `__len`, `__tostring`
3. OOP prototypowy — klasy, instancje, metody
4. Dziedziczenie i polimorfizm
5. `__call`, `__metatable`, `__pairs` i pozostałe
6. Weak tables, `__gc`, finalizatory

Plus **Sprawdzian Modułu 4** — 8 zadań (zamiast 7, bo materiał szerszy), w tym pełna klasa `Vector` z arytmetyką, `defaultdict`, `Observable` z metatable, immutable record, mixin pattern.

---

## Lekcja 4.1: `__index` i `__newindex` — fallback i przechwycenie

### Cel

Rozumiesz, jak Lua wyszukuje pola w tabeli i jak `__index` modyfikuje to wyszukiwanie. Umiesz przechwytywać przypisania przez `__newindex`. Znasz różnicę między tabelą-fallbackiem a funkcją-fallbackiem.

### Materiał

#### Co to metatable

Każda tabela może mieć **drugą tabelę** zwaną *metatable*, która definiuje "jak Lua zachowuje się przy operacjach na tej tabeli".

```lua
local t = {}
local mt = {}

setmetatable(t, mt)         -- ustaw mt jako metatable dla t
print(getmetatable(t))      -- zwraca mt
```

`mt` to zwykła tabela, ale gdy umieścimy w niej klucze o specjalnych nazwach (zaczynających się od `__`) — Lua będzie ich używać przy operacjach na `t`.

#### `__index` — fallback przy odczycie

Gdy próbujemy odczytać `t[k]`, a `t` **nie ma** klucza `k`, Lua sprawdza `metatable.__index`:
- jeśli to **tabela** — szuka `k` w niej
- jeśli to **funkcja** — woła `__index(t, k)` i bierze wynik

```lua
local defaults = {phi = 0.0, alive = true, epoch = 0}

local atom = {sig = "abc"}
setmetatable(atom, {__index = defaults})

print(atom.sig)        -- "abc"   (jest w atom)
print(atom.phi)        -- 0.0     (NIE ma w atom -> szuka w defaults)
print(atom.alive)      -- true    (j.w.)
print(atom.unknown)    -- nil     (nie ma ani w atom, ani w defaults)
```

**Zauważ:** Lua **nie modyfikuje** `atom`. Nie robi `atom.phi = 0.0` po tym jak je znajdzie w `defaults`. Następne odczytanie `atom.phi` znów schodzi do `defaults`. To jest **tylko fallback**.

#### `__index` jako funkcja

```lua
local proxy = {}
setmetatable(proxy, {
    __index = function(t, k)
        return "klucz '" .. tostring(k) .. "' obliczony dynamicznie"
    end
})

print(proxy.foo)     -- "klucz 'foo' obliczony dynamicznie"
print(proxy.bar)     -- "klucz 'bar' obliczony dynamicznie"
print(proxy[42])     -- "klucz '42' obliczony dynamicznie"
```

Funkcja `__index(t, k)` dostaje tabelę i klucz, zwraca wartość. Ten wzorzec jest podstawą **defaultdict** (jak w Pythonie), **lazy fields**, **proxy objects**.

#### `defaultdict` w Lua

```lua
local function defaultdict(factory)
    return setmetatable({}, {
        __index = function(t, k)
            local v = factory()
            t[k] = v             -- ! zapisuje do TABELI, więc kolejne odczyty są bezpośrednie
            return v
        end
    })
end

local groups = defaultdict(function() return {} end)
table.insert(groups.infra, "Anna")
table.insert(groups.infra, "Ola")
table.insert(groups.research, "Jan")

for k, v in pairs(groups) do
    print(k, table.concat(v, ", "))
end
-- infra      Anna, Ola
-- research   Jan
```

To jest dokładnie to, co obiecałem w Module 2 (Sprawdzian 5 — pivot table). Z `defaultdict` `pivot` staje się banalny:

```lua
local function pivot(events)
    local result = defaultdict(function() return defaultdict(function() return 0 end) end)
    for _, e in ipairs(events) do
        result[e.level][e.source] = result[e.level][e.source] + e.count
    end
    return result
end
```

Bez explicit `if result[level] == nil`. Eleganckie.

#### `__newindex` — przechwycenie przypisania

Gdy próbujemy `t[k] = v`, a `t` **nie ma** klucza `k`, Lua sprawdza `metatable.__newindex`:
- jeśli **tabela** — wpisuje tam (! NIE w `t`)
- jeśli **funkcja** — woła `__newindex(t, k, v)`
- jeśli **brak** — wpisuje normalnie do `t`

```lua
-- Read-only table:
local function readonly(t)
    return setmetatable({}, {
        __index = t,
        __newindex = function(_, k, v)
            error("próba modyfikacji read-only: " .. tostring(k), 2)
        end
    })
end

local config = readonly({version = "1.0", debug = true})
print(config.version)       -- "1.0"
config.debug = false        -- BŁĄD: próba modyfikacji read-only: debug
```

Tworzymy pustą tabelę proxy, której `__index` wskazuje na "prawdziwą" tabelę (odczyty fallback'ują), a `__newindex` rzuca błąd przy każdej próbie zapisu.

**Pułapka:** `__newindex` działa **tylko gdy klucz nie istnieje** w `t`. Dlatego proxy musi być **pustą tabelą** — wtedy KAŻDA próba zapisu trafia do `__newindex`.

```lua
-- TO NIE działa jak readonly:
local t = {x = 1}
setmetatable(t, {__newindex = function() error("read-only") end})
t.x = 99       -- nie wywoła __newindex! Klucz x JEST w t.
print(t.x)     -- 99
t.y = 2        -- TERAZ __newindex (klucza 'y' nie ma)
```

#### `rawget` i `rawset`

Czasami chcesz **ominąć** metatable — odczytać/zapisać "bez magii":

```lua
local t = setmetatable({}, {__index = function() return "magic" end})

print(t.x)            -- "magic"  (przez __index)
print(rawget(t, "x")) -- nil      (bezpośrednio z tabeli)

rawset(t, "x", 42)    -- ustaw bez wywoływania __newindex
print(rawget(t, "x")) -- 42
print(t.x)            -- 42  (teraz JEST w t, więc __index się nie odpala)
```

`rawget`/`rawset` to "escape hatch" gdy musisz zignorować metatable. Używaj rzadko, świadomie.

### Pułapki

1. **`__index` to tylko fallback** — nie modyfikuje tabeli. Zapis do `atom.phi = 0.5` tworzy klucz w `atom`, a nie w `defaults`.
2. **`__newindex` działa tylko gdy klucz NIE istnieje.** Read-only przez `__newindex` wymaga pustej tabeli proxy.
3. **`rawget`/`rawset`** omijają metatable — nie używaj rutynowo.
4. **Nieskończona rekursja** w `__index = function`: jeśli funkcja sięga do `t.something`, a `something` też nie istnieje w `t` i wraca do `__index` — cykl. Używaj `rawget(t, k)` w `__index` jeśli sięgasz do tej samej tabeli.

### Zadania

**Zadanie 4.1.1**  
Napisz funkcję `with_defaults(t, defaults)`, która zwraca tabelę zachowującą się jak `t`, ale z fallback do `defaults` dla brakujących kluczy. Modyfikacje muszą iść do oryginalnego `t` (nie do `defaults`).

Test:
```lua
local atom = {sig = "abc"}
local defaults = {phi = 0.0, alive = true}
local a = with_defaults(atom, defaults)
print(a.sig)     -- "abc"
print(a.phi)     -- 0.0
a.phi = 0.7
print(a.phi)     -- 0.7
print(atom.phi)  -- 0.7  (zapis poszedł do oryginalnego atom)
print(defaults.phi)  -- 0.0  (nietknięte)
```

**Zadanie 4.1.2**  
Napisz funkcję `track_access(t)`, która zwraca proxy zliczające ile razy każdy klucz został odczytany. Plus metoda `get_stats()`.

Test:
```lua
local t, stats = track_access({a = 1, b = 2, c = 3})
print(t.a, t.a, t.b, t.unknown)
local s = stats()
-- s = {a = 2, b = 1, unknown = 1}  (c nieczytane)
```

**Zadanie 4.1.3**  
Napisz `make_lazy_loader(loaders)` gdzie `loaders` to tabela `{key = function() return value end}`. Wartości są obliczane przy pierwszym dostępie do klucza i cachowane.

Test:
```lua
local count = 0
local lazy = make_lazy_loader({
    config = function() count = count + 1; return {x = 1} end,
    settings = function() return {y = 2} end,
})
print(count)            -- 0
print(lazy.config.x)    -- 1
print(count)            -- 1
print(lazy.config.x)    -- 1 (cache)
print(count)            -- 1
```

**Zadanie 4.1.4**  
Napisz `freeze(t)` — zwraca głęboko-immutable wersję `t`. Każda próba modyfikacji (na dowolnym poziomie zagnieżdżenia) rzuca błąd.

Test:
```lua
local config = freeze({version = "1.0", nested = {x = 1}})
print(config.version)         -- "1.0"
print(config.nested.x)        -- 1
config.version = "2.0"        -- ERROR
config.nested.x = 999         -- ERROR (! nawet zagnieżdżony)
```

**Zadanie 4.1.5**  
Napisz `with_logger(t, name)` — proxy logujące każde odczytanie i zapisanie z prefixem `name`.

Test:
```lua
local t = with_logger({}, "config")
t.x = 5         -- "[config] SET x = 5"
print(t.x)      -- "[config] GET x" / 5
t.y = nil       -- "[config] SET y = nil"  (! też logowane)
```

---

### Rozwiązania

#### Rozwiązanie 4.1.1

```lua
-- with_defaults.lua
local function with_defaults(t, defaults)
    return setmetatable(t, {__index = defaults})
end

local atom = {sig = "abc"}
local defaults = {phi = 0.0, alive = true}
local a = with_defaults(atom, defaults)

print(a.sig)            -- "abc"
print(a.phi)            -- 0.0      (z defaults)
print(a.alive)          -- true     (z defaults)

a.phi = 0.7
print(a.phi)            -- 0.7      (teraz bezpośrednio w atom)
print(atom.phi)         -- 0.7      (zapis poszedł do atom!)
print(defaults.phi)     -- 0.0      (nietknięte)

-- Zauważ: a == atom (to ta sama tabela, tylko z metatable)
print(a == atom)        -- true
```

Subtelnie: `setmetatable(t, ...)` modyfikuje `t` w miejscu i zwraca tę samą tabelę. Więc `a` to ta sama referencja co `atom`. To zwykle dokładnie czego chcemy.

Gdyby chcieć **nową** tabelę z fallbackiem:

```lua
local function with_defaults_new(t, defaults)
    local copy = {}
    for k, v in pairs(t) do copy[k] = v end
    return setmetatable(copy, {__index = defaults})
end
```

#### Rozwiązanie 4.1.2

```lua
-- track_access.lua
local function track_access(t)
    local stats = {}
    local proxy = setmetatable({}, {
        __index = function(_, k)
            stats[k] = (stats[k] or 0) + 1
            return t[k]
        end,
        __newindex = function(_, k, v)
            t[k] = v
        end
    })
    
    local get_stats = function()
        local copy = {}
        for k, v in pairs(stats) do copy[k] = v end
        return copy
    end
    
    return proxy, get_stats
end

local t, stats = track_access({a = 1, b = 2, c = 3})

print(t.a, t.a, t.b, t.unknown)
-- 1   1   2   nil

local s = stats()
print(s.a, s.b, s.c, s.unknown)
-- 2   1   nil   1
```

Proxy to pusta tabela — wszystkie odczyty trafiają do `__index`, wszystkie zapisy do `__newindex`. Statystyki w closure (prywatne, niedostępne z proxy).

`get_stats` zwraca **kopię** — gdyby zwracał `stats` bezpośrednio, klient mógłby zmienić wartości i skorumpować liczenie.

#### Rozwiązanie 4.1.3

```lua
-- make_lazy_loader.lua
local function make_lazy_loader(loaders)
    local cache = {}
    return setmetatable({}, {
        __index = function(_, k)
            if cache[k] == nil then
                local loader = loaders[k]
                if loader == nil then return nil end
                cache[k] = loader()
            end
            return cache[k]
        end
    })
end

local count = 0
local lazy = make_lazy_loader({
    config = function()
        count = count + 1
        return {x = 1, name = "config-loaded"}
    end,
    settings = function()
        count = count + 1
        return {y = 2}
    end,
})

print("count przed:", count)        -- 0
print(lazy.config.name)             -- "config-loaded"
print("count po config:", count)    -- 1
print(lazy.config.x)                -- 1 (cache hit, no recompute)
print("count po cache:", count)     -- 1
print(lazy.settings.y)              -- 2
print("count po settings:", count)  -- 2
print(lazy.unknown)                 -- nil (no loader)
```

To jest pattern dla "drogich rzeczy do załadowania" — np. kompilacja regex, parsowanie JSON, ładowanie pliku konfiguracji. Wartości są tworzone tylko gdy ktoś faktycznie ich potrzebuje.

W KarmazynOS taki loader idealnie pasuje do **lazy loading polityk HSS** — masz katalog z plikami `.lua` per polityka, ładujesz je tylko gdy sesja danego typu się otworzy.

#### Rozwiązanie 4.1.4

```lua
-- freeze.lua
local function freeze(t)
    -- Najpierw rekurencyjnie zamroź zagnieżdżone tabele:
    local frozen = {}
    for k, v in pairs(t) do
        if type(v) == "table" then
            frozen[k] = freeze(v)
        else
            frozen[k] = v
        end
    end
    
    -- Pusty proxy z fallbackiem do frozen:
    return setmetatable({}, {
        __index = frozen,
        __newindex = function(_, k, _)
            error("próba modyfikacji frozen table: " .. tostring(k), 2)
        end,
        __metatable = "frozen"   -- chroni metatable (Lekcja 4.5)
    })
end

local config = freeze({
    version = "1.0",
    nested = {
        x = 1,
        deep = {y = 2}
    }
})

print(config.version)            -- "1.0"
print(config.nested.x)           -- 1
print(config.nested.deep.y)      -- 2

-- Te muszą rzucić błąd:
local ok, err = pcall(function() config.version = "2.0" end)
print(ok, err)       -- false / "...próba modyfikacji frozen table: version"

local ok, err = pcall(function() config.nested.x = 999 end)
print(ok, err)       -- false / "...próba modyfikacji frozen table: x"
```

Klucz: **rekurencja** — przed zamrożeniem korzenia musimy zamrozić każde zagnieżdżenie. Bez tego `config.nested.x = 999` zadziałałoby (`config.nested` to zwykła tabela bez `__newindex`).

`__metatable = "frozen"` — sprawia, że `getmetatable(config)` zwraca string `"frozen"` zamiast prawdziwego metatable, i `setmetatable(config, ...)` rzuca błąd. To zabezpieczenie przed ucieczką (Lekcja 4.5).

#### Rozwiązanie 4.1.5

```lua
-- with_logger.lua
local function with_logger(t, name)
    return setmetatable({}, {
        __index = function(_, k)
            local v = t[k]
            print(string.format("[%s] GET %s = %s", name, tostring(k), tostring(v)))
            return v
        end,
        __newindex = function(_, k, v)
            print(string.format("[%s] SET %s = %s", name, tostring(k), tostring(v)))
            t[k] = v
        end
    })
end

local config = with_logger({}, "config")

config.version = "1.0"
-- [config] SET version = 1.0

config.debug = true
-- [config] SET debug = true

print(config.version)
-- [config] GET version = 1.0
-- 1.0

local x = config.unknown
-- [config] GET unknown = nil

config.y = nil
-- [config] SET y = nil
```

Pomocne do debugowania: gdy nie wiesz "co dotyka tej tabeli" — owiń ją w logger, zobacz w logach.

W KarmazynOS taki logger może być włączany flagą — w trybie debug wszystkie sesje HSS dostają proxy z log do dziennika.

### Sprawdź się

- [ ] Wiem, co to metatable i `__index`
- [ ] Pamiętam, że `__index` jest fallbackiem (nie modyfikuje tabeli)
- [ ] Umiem napisać `__index` jako funkcję
- [ ] Wiem, kiedy uruchamia się `__newindex` (klucz nie istnieje w t)
- [ ] Umiem zaimplementować `defaultdict` z `__index = function`
- [ ] Znam `rawget`/`rawset` jako escape hatch

---

## Lekcja 4.2: Operatory — `__add`, `__eq`, `__lt`, `__concat`, `__len`, `__tostring`

### Cel

Definiujesz, jak tabele zachowują się pod operatorami arytmetycznymi i porównywania. Umiesz overloadować `==`, `<`, `..`, `#`, `tostring`, `+`, `-`, `*`, `/` i pozostałe.

### Materiał

#### Pełna lista metametod operatorów

```
Arytmetyczne:
__add       a + b
__sub       a - b
__mul       a * b
__div       a / b
__mod       a % b
__pow       a ^ b
__unm       -a       (unary minus)
__idiv      a // b   (5.3+, integer division)

Bitowe (5.3+):
__band      a & b
__bor       a | b
__bxor      a ~ b    (XOR)
__bnot      ~a       (NOT)
__shl       a << b
__shr       a >> b

Łączenie:
__concat    a .. b

Długość:
__len       #a

Porównania:
__eq        a == b   (oba operandy MUSZĄ mieć ten sam metatable!)
__lt        a < b
__le        a <= b   (5.4: jeśli brak, używa not __lt(b, a))

Reprezentacja:
__tostring  tostring(a)

Wywołanie:
__call      a(...)   (Lekcja 4.5)
```

#### `__add` — przykład

```lua
local Vec = {}
Vec.__index = Vec

function Vec.new(x, y)
    return setmetatable({x = x, y = y}, Vec)
end

function Vec.__add(a, b)
    return Vec.new(a.x + b.x, a.y + b.y)
end

function Vec.__tostring(v)
    return "(" .. v.x .. ", " .. v.y .. ")"
end

local v1 = Vec.new(1, 2)
local v2 = Vec.new(3, 4)
local v3 = v1 + v2
print(v3)    -- (4, 6)
```

`a + b` dla tabel z metatable — Lua wywołuje `metatable.__add(a, b)`. Operator `..` na `print(v3)` wywołuje `__tostring`. Cały OOP-style "polimorfizm operatorów" wynika z tego.

#### `__eq` — pułapka

```lua
local A = setmetatable({x = 1}, {
    __eq = function(a, b) return a.x == b.x end
})
local B = setmetatable({x = 1}, {
    __eq = function(a, b) return a.x == b.x end
})

print(A == B)    -- false! (! różne metatable)
```

W Lua **`__eq` jest wywoływane tylko jeśli oba operandy mają TEN SAM metatable** (oddzielnie definiują, ale same tabele wskazują na ten sam mt).

Naprawa: jeden wspólny metatable:

```lua
local mt = {__eq = function(a, b) return a.x == b.x end}
local A = setmetatable({x = 1}, mt)
local B = setmetatable({x = 1}, mt)
print(A == B)    -- true
```

W praktyce klasy (Lekcja 4.3) używają jednej "tabeli klasy" jako wspólnego metatable wszystkich instancji — więc wewnątrz klasy `__eq` działa naturalnie.

**Lua 5.3+ poluzowała tę regułę** — `__eq` działa też gdy oba mają `__eq` (niekoniecznie ten sam metatable). Ale kanonicznie: jeden metatable.

#### `__lt` i `__le`

```lua
local Phi = {}
Phi.__index = Phi
Phi.__lt = function(a, b) return a.value < b.value end
Phi.__le = function(a, b) return a.value <= b.value end
Phi.__tostring = function(p) return "phi=" .. p.value end

function Phi.new(v) return setmetatable({value = v}, Phi) end

local p1 = Phi.new(0.3)
local p2 = Phi.new(0.7)

print(p1 < p2)     -- true
print(p1 <= p2)    -- true
print(p2 > p1)     -- true (! Lua tłumaczy a > b jako b < a)
print(p2 >= p1)    -- true (analogicznie)
```

`>` i `>=` nie mają osobnych metametod — Lua sama tłumaczy `a > b` jako `b < a`.

Lua 5.4 pozwala pominąć `__le` — używa wtedy `not __lt(b, a)`. W 5.1-5.3 musisz zdefiniować oba.

#### `__concat` — operator `..`

```lua
local Hour = {}
Hour.__index = Hour
Hour.__concat = function(a, b)
    if type(a) == "string" then return a .. tostring(b) end
    if type(b) == "string" then return tostring(a) .. b end
    return tostring(a) .. tostring(b)
end
Hour.__tostring = function(h) return string.format("%02d:%02d", h.h, h.m) end

function Hour.new(h, m) return setmetatable({h = h, m = m}, Hour) end

local t = Hour.new(14, 30)
print("Czas: " .. t)         -- "Czas: 14:30"
print(t .. " odjazd")        -- "14:30 odjazd"
```

`..` jest często wywoływany z lewym lub prawym argumentem stringowym. Robust `__concat` obsługuje wszystkie kombinacje.

**Bez `__concat`:** `print("Czas: " .. t)` rzuciłby błąd `"attempt to concatenate a table value"`. To częsta pułapka — chcesz wypisać debugowo strukturę i Lua mówi nie. Zdefiniuj `__concat` lub `__tostring` (i konwertuj jawnie przez `tostring`).

#### `__len` — operator `#`

```lua
local Stack = {}
Stack.__index = Stack
Stack.__len = function(s) return s.size end

function Stack.new()
    return setmetatable({data = {}, size = 0}, Stack)
end
function Stack.push(s, v) s.size = s.size + 1; s.data[s.size] = v end

local s = Stack.new()
Stack.push(s, "a"); Stack.push(s, "b"); Stack.push(s, "c")
print(#s)    -- 3   (! NIE liczy elementów tabeli, używa __len)
```

`__len` jest przydatne gdy "wielkość" obiektu nie odpowiada `#data`. Np. dla LRU cache `__len` może zwracać `size`, a `data` ma osobne struktury.

#### `__tostring` — kanoniczne

Każda klasa, która ma być debugowalna, **powinna mieć** `__tostring`. To convention:

```lua
function Atom.__tostring(a)
    return string.format("Atom<sig=%s, phi=%.3f, alive=%s>",
        a.sig, a.phi, tostring(a.alive))
end
```

Wtedy `print(atom)` daje czytelny output, nie `table: 0x55a3b8c7d180`.

#### Operatory niemetatable'owalne

**Nie ma metametody dla:**
- `not` (logiczne — wynik zawsze boolean)
- `and` / `or` (zwracają jeden z operandów, nie wynik specjalny)
- `=` (przypisanie nie jest operatorem w Lua)

To znaczy: nie możesz "overloadować" `if t then`. Sprawdzenie truthiness tabeli to zawsze `true` (bo tabela istnieje, nie jest `nil` ani `false`).

### Pułapki

1. **`__eq` wymaga wspólnego metatable** (lub przynajmniej obu z `__eq` w 5.3+).
2. **Brak `__tostring`** = `print(t)` daje "table: 0x...". Zawsze definiuj.
3. **`__concat` z mieszanymi typami** — sprawdź który operand jest stringiem.
4. **`__len` nie liczy elementów** — zwraca cokolwiek funkcja zwróci. Ale w "normalnych" tabelach zostaje domyślne zachowanie sekwencji.
5. **Komutatywność** — `__add` jest wywoływane raz, ale `a + b` może mieć `b` jako tabelę a `a` jako liczbę. Lua wywoła wtedy `b.__add(a, b)` (! a jako liczba!). Twój `__add` musi to obsłużyć.

### Zadania

**Zadanie 4.2.1** — Wektor 2D  
Napisz klasę `Vec2` z arytmetyką: `+`, `-`, `*` (scalar mnożenie), `==`, `__tostring`.

```lua
local v1 = Vec2.new(1, 2)
local v2 = Vec2.new(3, 4)
print(v1 + v2)         -- (4, 6)
print(v2 - v1)         -- (2, 2)
print(v1 * 3)          -- (3, 6)
print(3 * v1)          -- (3, 6)  (! też działa)
print(v1 == Vec2.new(1, 2))    -- true
print(v1 == v2)        -- false
```

**Zadanie 4.2.2** — Liczba zespolona  
Napisz `Complex` z `+`, `-`, `*`, `__eq`, `__tostring`.

`Complex.new(re, im)` tworzy `re + im*i`.  
`Complex.new(2, 3) * Complex.new(1, 4)` = `(2*1 - 3*4) + (2*4 + 3*1)i` = `-10 + 11i`.

**Zadanie 4.2.3** — Zbiór z porównaniami  
Napisz `Set` (z M2 Sprawdzian 1) ze wzbogaconymi operatorami:
- `+` — suma zbiorów
- `*` — przecięcie
- `-` — różnica
- `==` — równość
- `<` — czy lewy jest **podzbiorem właściwym** prawego
- `<=` — czy lewy jest podzbiorem
- `__tostring`

Test:
```lua
local A = Set.new("a", "b", "c")
local B = Set.new("b", "c", "d")
print(A + B)      -- {a, b, c, d}
print(A * B)      -- {b, c}
print(A - B)      -- {a}
print(A == Set.new("c", "b", "a"))    -- true
print(Set.new("a") < A)               -- true (właściwy podzbiór)
print(Set.new("a") <= A)              -- true
print(A < A)                          -- false (! nie WŁAŚCIWY)
print(A <= A)                         -- true
```

**Zadanie 4.2.4** — `__concat` z formatowaniem  
Napisz klasę `Path` reprezentującą ścieżkę plikową. `__concat` łączy segmenty ze slashami. `__tostring` zwraca pełną ścieżkę.

```lua
local p = Path.new("/etc/holonos")
local q = p .. "policies" .. "default.lua"
print(q)    -- "/etc/holonos/policies/default.lua"
```

**Zadanie 4.2.5** — Liczby z jednostkami  
Napisz `Quantity` reprezentujący liczbę z jednostką. `+`/`-` działają tylko dla zgodnych jednostek; inaczej rzucają błąd. `*` przez liczbę zwraca nową `Quantity`.

```lua
local a = Quantity.new(5, "kg")
local b = Quantity.new(3, "kg")
local c = Quantity.new(2, "m")
print(a + b)     -- 8 kg
print(a * 2)     -- 10 kg
local ok, err = pcall(function() return a + c end)
print(ok, err)   -- false   "incompatible units: kg vs m"
```

---

### Rozwiązania

#### Rozwiązanie 4.2.1

```lua
-- vec2.lua
local Vec2 = {}
Vec2.__index = Vec2

function Vec2.new(x, y)
    return setmetatable({x = x, y = y}, Vec2)
end

function Vec2.__add(a, b)
    return Vec2.new(a.x + b.x, a.y + b.y)
end

function Vec2.__sub(a, b)
    return Vec2.new(a.x - b.x, a.y - b.y)
end

function Vec2.__mul(a, b)
    -- Komutatywność: scalar * vec lub vec * scalar
    if type(a) == "number" then
        return Vec2.new(b.x * a, b.y * a)
    end
    if type(b) == "number" then
        return Vec2.new(a.x * b, a.y * b)
    end
    -- vec * vec — dot product (skalar):
    return a.x * b.x + a.y * b.y
end

function Vec2.__eq(a, b)
    return a.x == b.x and a.y == b.y
end

function Vec2.__tostring(v)
    return string.format("(%g, %g)", v.x, v.y)
end

-- Test:
local v1 = Vec2.new(1, 2)
local v2 = Vec2.new(3, 4)

print(v1 + v2)             -- (4, 6)
print(v2 - v1)             -- (2, 2)
print(v1 * 3)              -- (3, 6)
print(3 * v1)              -- (3, 6)
print(v1 * v2)             -- 11 (dot: 1*3 + 2*4)
print(v1 == Vec2.new(1, 2))    -- true
print(v1 == v2)            -- false
```

`__mul` z sprawdzeniem typu — to jest klasyczna technika dla operatorów komutatywnych z mieszanymi typami. Bez tego `3 * v1` wywołałby `(3).__mul(3, v1)` — ale liczby nie mają metatable, więc Lua sięga do prawego operandu (`v1`'s `__mul`) i wywołuje go z `a = 3, b = v1`. Trzeba sprawdzić co jest czym.

`%g` w `string.format` — wyświetla liczbę bez końcowych zer (1.5, nie 1.500000).

#### Rozwiązanie 4.2.2

```lua
-- complex.lua
local Complex = {}
Complex.__index = Complex

function Complex.new(re, im)
    return setmetatable({re = re, im = im or 0}, Complex)
end

function Complex.__add(a, b)
    if type(a) == "number" then a = Complex.new(a, 0) end
    if type(b) == "number" then b = Complex.new(b, 0) end
    return Complex.new(a.re + b.re, a.im + b.im)
end

function Complex.__sub(a, b)
    if type(a) == "number" then a = Complex.new(a, 0) end
    if type(b) == "number" then b = Complex.new(b, 0) end
    return Complex.new(a.re - b.re, a.im - b.im)
end

function Complex.__mul(a, b)
    if type(a) == "number" then a = Complex.new(a, 0) end
    if type(b) == "number" then b = Complex.new(b, 0) end
    return Complex.new(
        a.re * b.re - a.im * b.im,
        a.re * b.im + a.im * b.re
    )
end

function Complex.__eq(a, b)
    return a.re == b.re and a.im == b.im
end

function Complex.__tostring(c)
    if c.im == 0 then return tostring(c.re) end
    if c.re == 0 then return c.im .. "i" end
    if c.im < 0 then return string.format("%g - %gi", c.re, -c.im) end
    return string.format("%g + %gi", c.re, c.im)
end

-- Test:
local a = Complex.new(2, 3)
local b = Complex.new(1, 4)

print(a + b)        -- 3 + 7i
print(a - b)        -- 1 - 1i
print(a * b)        -- -10 + 11i
print(a == Complex.new(2, 3))    -- true
print(2 + Complex.new(0, 1))     -- 2 + 1i

-- Tożsamość: i * i = -1
local i = Complex.new(0, 1)
print(i * i)        -- -1
```

Promocja `number → Complex` na początku każdej operacji — pozwala na `2 + complex`. Klasyczna technika "mixed arithmetic".

#### Rozwiązanie 4.2.3

```lua
-- set_with_ops.lua
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

function Set:contains(v)
    return self._data[v] == true
end

function Set:size()
    return self._size
end

function Set.__add(a, b)
    local r = Set.new()
    for k in pairs(a._data) do r._data[k] = true; r._size = r._size + 1 end
    for k in pairs(b._data) do
        if not r._data[k] then r._data[k] = true; r._size = r._size + 1 end
    end
    return r
end

function Set.__mul(a, b)
    local r = Set.new()
    for k in pairs(a._data) do
        if b._data[k] then r._data[k] = true; r._size = r._size + 1 end
    end
    return r
end

function Set.__sub(a, b)
    local r = Set.new()
    for k in pairs(a._data) do
        if not b._data[k] then r._data[k] = true; r._size = r._size + 1 end
    end
    return r
end

function Set.__eq(a, b)
    if a._size ~= b._size then return false end
    for k in pairs(a._data) do
        if not b._data[k] then return false end
    end
    return true
end

function Set.__le(a, b)
    -- a podzbiór b (każdy element a jest w b)
    for k in pairs(a._data) do
        if not b._data[k] then return false end
    end
    return true
end

function Set.__lt(a, b)
    -- a właściwy podzbiór b: a podzbiór b ORAZ a ≠ b
    return Set.__le(a, b) and not Set.__eq(a, b)
end

function Set.__tostring(s)
    local list = {}
    for k in pairs(s._data) do list[#list + 1] = tostring(k) end
    table.sort(list)
    return "{" .. table.concat(list, ", ") .. "}"
end

-- Test:
local A = Set.new("a", "b", "c")
local B = Set.new("b", "c", "d")
local C = Set.new("a")

print("A     =", A)         -- {a, b, c}
print("B     =", B)         -- {b, c, d}
print("A + B =", A + B)     -- {a, b, c, d}
print("A * B =", A * B)     -- {b, c}
print("A - B =", A - B)     -- {a}
print("A == Set.new('c','b','a'):", A == Set.new("c", "b", "a"))    -- true
print("C < A =", C < A)     -- true (właściwy podzbiór)
print("C <= A =", C <= A)   -- true
print("A < A =", A < A)     -- false
print("A <= A =", A <= A)   -- true
print("A < B =", A < B)     -- false (a nie jest w b)
```

Ten zbiór dziedziczy z M2 Sprawdzian, ale teraz ma "operator-style" interfejs. To samo zachowanie, ale dla klienta o niebo czytelniejsze: `A + B` zamiast `Set.union(A, B)`.

#### Rozwiązanie 4.2.4

```lua
-- path.lua
local Path = {}
Path.__index = Path

function Path.new(s)
    -- Normalizacja: usuń trailing slash, ale zachowaj root "/"
    if s ~= "/" and s:sub(-1) == "/" then
        s = s:sub(1, -2)
    end
    return setmetatable({path = s}, Path)
end

function Path.__concat(a, b)
    local left, right
    if type(a) == "string" then left = a
    else left = a.path end
    if type(b) == "string" then right = b
    else right = b.path end
    
    -- Łączenie:
    if left:sub(-1) == "/" then
        return Path.new(left .. right)
    end
    return Path.new(left .. "/" .. right)
end

function Path.__tostring(p)
    return p.path
end

function Path:basename()
    return self.path:match("([^/]+)$")
end

function Path:dirname()
    return self.path:match("(.+)/[^/]+$") or "/"
end

-- Test:
local p = Path.new("/etc/holonos")
local q = p .. "policies" .. "default.lua"
print(q)               -- /etc/holonos/policies/default.lua

print(q:basename())    -- default.lua
print(q:dirname())     -- /etc/holonos/policies

-- Z trailing slashem:
local p2 = Path.new("/etc/holonos/")
local q2 = p2 .. "atoms"
print(q2)              -- /etc/holonos/atoms
```

Bonus: dodałem metody `:basename()` i `:dirname()` — bo skoro mamy Path, niech robi coś użytecznego. To jest typowy "value-class enrichment" — klasa wokół jednego pola `path` z bogatym interfejsem.

#### Rozwiązanie 4.2.5

```lua
-- quantity.lua
local Quantity = {}
Quantity.__index = Quantity

function Quantity.new(value, unit)
    return setmetatable({value = value, unit = unit}, Quantity)
end

function Quantity.__add(a, b)
    if a.unit ~= b.unit then
        error("incompatible units: " .. a.unit .. " vs " .. b.unit, 2)
    end
    return Quantity.new(a.value + b.value, a.unit)
end

function Quantity.__sub(a, b)
    if a.unit ~= b.unit then
        error("incompatible units: " .. a.unit .. " vs " .. b.unit, 2)
    end
    return Quantity.new(a.value - b.value, a.unit)
end

function Quantity.__mul(a, b)
    if type(a) == "number" then
        return Quantity.new(a * b.value, b.unit)
    end
    if type(b) == "number" then
        return Quantity.new(a.value * b, a.unit)
    end
    error("Quantity * Quantity nie jest zaimplementowane (wymagałoby algebry jednostek)", 2)
end

function Quantity.__eq(a, b)
    return a.value == b.value and a.unit == b.unit
end

function Quantity.__tostring(q)
    return q.value .. " " .. q.unit
end

-- Test:
local a = Quantity.new(5, "kg")
local b = Quantity.new(3, "kg")
local c = Quantity.new(2, "m")

print(a + b)     -- 8 kg
print(a - b)     -- 2 kg
print(a * 2)     -- 10 kg
print(3 * a)     -- 15 kg
print(a == Quantity.new(5, "kg"))    -- true
print(a == b)    -- false

local ok, err = pcall(function() return a + c end)
print(ok, err)   -- false   "...incompatible units: kg vs m"
```

**Niezauważalna pułapka:** dodawanie kg + g powinno zadziałać po konwersji. Tutaj są równe stringi, więc to "syntactic equality of units". Pełna obsługa wymagałaby tabeli konwersji. To jest celowo prosta wersja — pokazuje pomysł, w prawdziwym kodzie użyjesz biblioteki jak `lua-units` albo zaimplementujesz strict-units jako warstwę na typach.

### Sprawdź się

- [ ] Wiem, jak overloadować `+`, `-`, `*`, `/`
- [ ] Pamiętam, że `__eq` wymaga (zwykle) wspólnego metatable
- [ ] Wiem, że `>` jest tłumaczone na `b < a`
- [ ] Umiem obsłużyć komutatywność operatora (`scalar * vec` vs `vec * scalar`)
- [ ] Każda moja klasa ma `__tostring`
- [ ] Wiem, że `__concat` musi obsłużyć string + table i odwrotnie

---

## Lekcja 4.3: OOP prototypowy — klasy, instancje, metody

### Cel

Tworzysz klasy w idiomatycznym Lua: tabela klasy + metatable z `__index = klasa` + konstruktor. Rozumiesz jak działa `s:method()` i czemu to jest klucz do OOP.

### Materiał

#### Wzorzec klasy w Lua

W Lua nie ma słowa kluczowego `class`. **Klasa to tabela**, której metatable jest ustawiony tak, aby instancje "dziedziczyły" jej metody.

```lua
-- Tabela klasy + metatable
local Holon = {}
Holon.__index = Holon

-- Konstruktor
function Holon.new(sig, phi)
    local self = setmetatable({}, Holon)
    self.sig = sig
    self.phi = phi or 0.0
    self.alive = true
    return self
end

-- Metoda (z self)
function Holon:get_phi()
    return self.phi
end

function Holon:set_phi(v)
    self.phi = v
end

function Holon:kill()
    self.alive = false
    self.phi = 0
end

function Holon:__tostring()
    return string.format("Holon<%s, phi=%.3f, %s>",
        self.sig, self.phi, self.alive and "alive" or "dead")
end

-- Użycie:
local h = Holon.new("abc123", 0.7)
print(h:get_phi())     -- 0.7
h:set_phi(0.9)
print(h:get_phi())     -- 0.9
print(h)               -- Holon<abc123, phi=0.900, alive>
h:kill()
print(h)               -- Holon<abc123, phi=0.000, dead>
```

#### Co tu się stało — krok po kroku

1. **`Holon = {}`** — pusta tabela "klasy".
2. **`Holon.__index = Holon`** — kluczowy trik. Mówi: gdy ktoś szuka klucza w instancji i nie znajdzie, niech szuka w `Holon`.
3. **`Holon.new(sig, phi)`** — konstruktor:
   - Tworzy nową tabelę `self = {}`.
   - Ustawia `Holon` jako metatable: `setmetatable({}, Holon)`.
   - Wypełnia pola.
   - Zwraca.
4. **`function Holon:get_phi()`** — to skrót dla `function Holon.get_phi(self)`. Składnia `:` wstawia ukryty parametr `self`.
5. **`h:get_phi()`** — skrót dla `h.get_phi(h)`. Składnia `:` przekazuje `h` jako pierwszy argument.

Mechanika: gdy piszesz `h:get_phi()`, Lua szuka klucza `get_phi` w `h`. Nie znajduje. Sprawdza metatable `h` (czyli `Holon`). Znajduje `Holon.__index` — ono jest tabelą (samym `Holon`). Szuka `get_phi` w `Holon`. Znajduje. Wywołuje z `h` jako `self`.

#### Składnia `:` vs `.`

```lua
-- Definicja:
function Holon:method(a, b) ... end       -- ukryty self
function Holon.method(self, a, b) ... end -- to samo, jawnie

-- Wywołanie:
obj:method(a, b)        -- ukryty self
obj.method(obj, a, b)   -- to samo, jawnie
```

**Reguła kciuka:**
- Definiujesz metodę z `:` → wywołujesz z `:`.
- Funkcja, która nie potrzebuje `self` (np. konstruktor `Holon.new`) — definiujesz z `.`.

Konstruktor to **funkcja klasy**, nie metoda instancji — stąd `Holon.new(...)` z `.`, nie `:new`.

#### Sprawdzanie typu instancji

```lua
local function is_holon(x)
    return type(x) == "table" and getmetatable(x) == Holon
end

print(is_holon(h))          -- true
print(is_holon({}))          -- false
print(is_holon("string"))    -- false
```

`getmetatable` zwraca metatable lub `nil`. Porównanie z `Holon` to test "czy jest tej klasy".

#### Pełniejsza klasa — `Session`

```lua
local Session = {}
Session.__index = Session

function Session.new(sig)
    return setmetatable({
        sig = sig,
        atoms = {},
        epoch = 0,
        born_at = os.time(),
        alive = true,
    }, Session)
end

function Session:add_atom(atom)
    if not self.alive then
        return nil, "session is dead"
    end
    self.atoms[#self.atoms + 1] = atom
    return #self.atoms
end

function Session:remove_atom(idx)
    if idx < 1 or idx > #self.atoms then
        return nil, "invalid index"
    end
    return table.remove(self.atoms, idx)
end

function Session:tick(dt)
    self.epoch = self.epoch + 1
    -- Decay phi atomów:
    for i = #self.atoms, 1, -1 do
        local a = self.atoms[i]
        a.phi = a.phi * math.exp(-dt)
        if a.phi < 1e-6 then
            table.remove(self.atoms, i)
        end
    end
end

function Session:atom_count()
    return #self.atoms
end

function Session:close()
    self.alive = false
    self.atoms = {}
end

function Session:age()
    return os.time() - self.born_at
end

function Session:__tostring()
    return string.format("Session<%s, atoms=%d, epoch=%d, age=%ds>",
        self.sig, #self.atoms, self.epoch, self:age())
end

-- Użycie:
local s = Session.new("abc123")
s:add_atom({sig = "atom1", phi = 0.7})
s:add_atom({sig = "atom2", phi = 0.4})
s:add_atom({sig = "atom3", phi = 0.05})

print(s)                  -- Session<abc123, atoms=3, epoch=0, age=0s>
s:tick(0.5)
print(s:atom_count())     -- 2 (atom3 wymarł)
print(s)
```

#### Prywatne pola — konwencje

Lua nie ma prywatnych pól. Konwencja: nazwy z prefiksem `_` to "prywatne, nie ruszaj":

```lua
function Session.new(sig)
    return setmetatable({
        sig = sig,
        _atoms = {},        -- ! prywatne
        _epoch = 0,
        _alive = true,
    }, Session)
end
```

Klient **może** technicznie sięgnąć do `s._atoms`, ale **nie powinien**. To gentleman's agreement.

Dla **prawdziwie** prywatnych pól — closures (Moduł 3, make_stack) lub weak tables (Lekcja 4.6, "perfect privacy").

### Pułapki

1. **`Holon.__index = Holon`** — bez tego metody instancji nie działają.
2. **Konstruktor z `.` nie `:`** — nie ma jeszcze `self`.
3. **Metody z `:`, funkcje pomocnicze z `.`** — kontekstowo.
4. **Modyfikacja klasy modyfikuje wszystkie instancje** (które jej dziedziczą):

```lua
function Holon:new_method() print("nowa") end
h:new_method()    -- działa, mimo że h było stworzone wcześniej
```

To **dynamiczność** — Lua pozwala dodać metody do klasy w runtime. Pythonopodobne, użyteczne dla hot-reload, niebezpieczne dla pomyłek.

### Zadania

**Zadanie 4.3.1** — Counter  
Napisz klasę `Counter` z metodami `:inc()`, `:dec()`, `:get()`, `:reset()`. Konstruktor `Counter.new(initial)` (default 0).

```lua
local c = Counter.new(10)
c:inc(); c:inc(); c:dec()
print(c:get())    -- 11
c:reset()
print(c:get())    -- 10
```

**Zadanie 4.3.2** — Stack jako klasa  
Przepisz Stack z M2 (Sprawdzian 1) jako pełną klasę z `:push()`, `:pop()`, `:peek()`, `:size()`, `:empty()`, `:__tostring()`, `:__len()`. Składnia `s:push(v)` zamiast `Stack.push(s, v)`.

**Zadanie 4.3.3** — Atom z walidacją  
Napisz `Atom.new(sig, phi)`, który **waliduje** argumenty:
- `sig` musi być stringiem niepustym (rzuć error)
- `phi` musi być w przedziale [0, 1] (rzuć error)

Następnie metody `:get_phi()`, `:set_phi(v)` (też walidacja!), `:fade(rate)` (mnoży phi przez `rate`), `:__tostring()`.

**Zadanie 4.3.4** — Range jako klasa  
Napisz `Range.new(start, stop, step)` — klasa reprezentująca zakres liczb. Metody: `:contains(n)` (czy n jest w zakresie), `:to_list()` (zwraca listę), `:length()`. Plus `__tostring`.

```lua
local r = Range.new(1, 10, 2)    -- 1, 3, 5, 7, 9
print(r:length())         -- 5
print(r:contains(5))      -- true
print(r:contains(6))      -- false
print(r)                  -- "Range(1..10 step 2)"
local list = r:to_list()
-- list = {1, 3, 5, 7, 9}
```

**Zadanie 4.3.5** — Bank account  
Napisz `Account.new(owner, initial_balance)`. Metody:
- `:deposit(amount)` — dodaje, walidacja amount > 0
- `:withdraw(amount)` — odejmuje; jeśli za mało, zwraca `nil, "insufficient funds"`
- `:balance()` — zwraca saldo
- `:transfer(other, amount)` — przelew na inne konto; atomic (albo cały, albo nic)
- `:__tostring()`

```lua
local a = Account.new("Anna", 100)
local b = Account.new("Bartek", 50)
a:deposit(50)            -- 150
a:withdraw(20)           -- 130
print(a:balance())       -- 130

local ok, err = a:transfer(b, 200)
print(ok, err)           -- nil   "insufficient funds"

a:transfer(b, 50)
print(a:balance(), b:balance())   -- 80   100
```

---

### Rozwiązania

#### Rozwiązanie 4.3.1

```lua
-- counter.lua
local Counter = {}
Counter.__index = Counter

function Counter.new(initial)
    return setmetatable({
        value = initial or 0,
        initial = initial or 0,
    }, Counter)
end

function Counter:inc()
    self.value = self.value + 1
end

function Counter:dec()
    self.value = self.value - 1
end

function Counter:get()
    return self.value
end

function Counter:reset()
    self.value = self.initial
end

function Counter:__tostring()
    return "Counter<" .. self.value .. ">"
end

-- Test:
local c = Counter.new(10)
c:inc(); c:inc(); c:dec()
print(c:get())    -- 11
c:reset()
print(c:get())    -- 10

local c2 = Counter.new()
c2:inc(); c2:inc()
print(c2)         -- Counter<2>
```

`initial` zapisany w polu — bo `:reset()` musi wiedzieć "do czego wracać". Bez tego reset by działał zawsze do 0.

#### Rozwiązanie 4.3.2

```lua
-- stack_class.lua
local Stack = {}
Stack.__index = Stack

function Stack.new()
    return setmetatable({_data = {}, _size = 0}, Stack)
end

function Stack:push(v)
    self._size = self._size + 1
    self._data[self._size] = v
end

function Stack:pop()
    if self._size == 0 then return nil end
    local v = self._data[self._size]
    self._data[self._size] = nil
    self._size = self._size - 1
    return v
end

function Stack:peek()
    return self._data[self._size]
end

function Stack:size()
    return self._size
end

function Stack:empty()
    return self._size == 0
end

function Stack:__len()
    return self._size
end

function Stack:__tostring()
    local parts = {}
    for i = 1, self._size do
        parts[i] = tostring(self._data[i])
    end
    return "Stack[" .. table.concat(parts, ", ") .. "]"
end

-- Test:
local s = Stack.new()
s:push("a"); s:push("b"); s:push("c")
print(s)             -- Stack[a, b, c]
print(#s)            -- 3 (! __len)
print(s:peek())      -- "c"
print(s:pop())       -- "c"
print(s)             -- Stack[a, b]
print(s:size())      -- 2
print(s:empty())     -- false

while not s:empty() do
    s:pop()
end
print(s:empty())     -- true
```

Z tabeli klasy `Stack` używamy go zarówno jako "namespace dla metod" jak i jako "metatable instancji". Klucz `__index = Stack` zamyka pętlę.

#### Rozwiązanie 4.3.3

```lua
-- atom_validated.lua
local Atom = {}
Atom.__index = Atom

local function validate_sig(sig)
    if type(sig) ~= "string" then
        error("sig must be string, got " .. type(sig), 3)
    end
    if #sig == 0 then
        error("sig cannot be empty", 3)
    end
end

local function validate_phi(phi)
    if type(phi) ~= "number" then
        error("phi must be number, got " .. type(phi), 3)
    end
    if phi < 0 or phi > 1 then
        error("phi must be in [0, 1], got " .. phi, 3)
    end
end

function Atom.new(sig, phi)
    validate_sig(sig)
    validate_phi(phi)
    return setmetatable({sig = sig, phi = phi}, Atom)
end

function Atom:get_phi()
    return self.phi
end

function Atom:set_phi(v)
    validate_phi(v)
    self.phi = v
end

function Atom:fade(rate)
    if type(rate) ~= "number" or rate < 0 or rate > 1 then
        error("rate must be in [0, 1]", 2)
    end
    self.phi = self.phi * rate
end

function Atom:__tostring()
    return string.format("Atom<%s, phi=%.4f>", self.sig, self.phi)
end

-- Test:
local a = Atom.new("abc", 0.7)
print(a)             -- Atom<abc, phi=0.7000>

a:set_phi(0.9)
print(a)             -- Atom<abc, phi=0.9000>

a:fade(0.5)
print(a)             -- Atom<abc, phi=0.4500>

-- Walidacja:
local ok, err = pcall(Atom.new, "", 0.5)
print(ok, err)       -- false   "...sig cannot be empty"

local ok, err = pcall(Atom.new, "x", 1.5)
print(ok, err)       -- false   "...phi must be in [0, 1], got 1.5"

local ok, err = pcall(function() a:set_phi(-0.1) end)
print(ok, err)       -- false   "...phi must be in [0, 1], got -0.1"
```

`error(msg, 3)` — poziom 3 wskazuje **callera konstruktora** (3 = "ten kto wywołał walidator", "ten kto wywołał `Atom.new`", "ten kto wywołał stronę użytkownika"). Dla użytkownika błąd wskazuje na `Atom.new("", 0.5)` zamiast wewnętrzne `validate_sig`.

#### Rozwiązanie 4.3.4

```lua
-- range_class.lua
local Range = {}
Range.__index = Range

function Range.new(start, stop, step)
    step = step or 1
    if step == 0 then error("step cannot be 0", 2) end
    return setmetatable({
        start = start,
        stop = stop,
        step = step,
    }, Range)
end

function Range:contains(n)
    if self.step > 0 then
        if n < self.start or n > self.stop then return false end
    else
        if n > self.start or n < self.stop then return false end
    end
    -- Sprawdź czy wpada w siatkę step:
    return (n - self.start) % self.step == 0
end

function Range:length()
    if self.step > 0 then
        if self.start > self.stop then return 0 end
        return (self.stop - self.start) // self.step + 1
    else
        if self.start < self.stop then return 0 end
        return (self.start - self.stop) // (-self.step) + 1
    end
end

function Range:to_list()
    local list = {}
    for i = self.start, self.stop, self.step do
        list[#list + 1] = i
    end
    return list
end

function Range:__tostring()
    if self.step == 1 then
        return string.format("Range(%d..%d)", self.start, self.stop)
    end
    return string.format("Range(%d..%d step %d)", self.start, self.stop, self.step)
end

-- Test:
local r = Range.new(1, 10, 2)
print(r)                 -- Range(1..10 step 2)
print(r:length())        -- 5
print(r:contains(5))     -- true
print(r:contains(6))     -- false (6 nie wpada w siatkę 1, 3, 5, 7, 9)
print(r:contains(11))    -- false (poza zakresem)

for _, v in ipairs(r:to_list()) do io.write(v, " ") end
print()
-- 1 3 5 7 9

local r2 = Range.new(10, 1, -1)
print(r2:length())       -- 10
print(r2:contains(5))    -- true

local r3 = Range.new(1, 5)   -- step domyślnie 1
print(r3)                -- Range(1..5)
print(r3:length())       -- 5
```

`:contains(n)` z dwoma sprawdzeniami: zakres + dopasowanie do siatki. `:length()` z dzieleniem całkowitoliczbowym.

#### Rozwiązanie 4.3.5

```lua
-- account.lua
local Account = {}
Account.__index = Account

function Account.new(owner, initial_balance)
    initial_balance = initial_balance or 0
    if type(owner) ~= "string" or #owner == 0 then
        error("owner must be non-empty string", 2)
    end
    if type(initial_balance) ~= "number" or initial_balance < 0 then
        error("initial_balance must be non-negative number", 2)
    end
    return setmetatable({
        owner = owner,
        _balance = initial_balance,
    }, Account)
end

function Account:deposit(amount)
    if type(amount) ~= "number" or amount <= 0 then
        return nil, "amount must be positive number"
    end
    self._balance = self._balance + amount
    return self._balance
end

function Account:withdraw(amount)
    if type(amount) ~= "number" or amount <= 0 then
        return nil, "amount must be positive number"
    end
    if self._balance < amount then
        return nil, "insufficient funds"
    end
    self._balance = self._balance - amount
    return self._balance
end

function Account:balance()
    return self._balance
end

function Account:transfer(other, amount)
    -- Atomic: sprawdź sufficiency PRZED jakąkolwiek modyfikacją
    if type(amount) ~= "number" or amount <= 0 then
        return nil, "amount must be positive"
    end
    if self._balance < amount then
        return nil, "insufficient funds"
    end
    -- Teraz oba kroki:
    self._balance = self._balance - amount
    other._balance = other._balance + amount
    return amount
end

function Account:__tostring()
    return string.format("Account<%s: %.2f>", self.owner, self._balance)
end

-- Test:
local a = Account.new("Anna", 100)
local b = Account.new("Bartek", 50)
print(a)                    -- Account<Anna: 100.00>

a:deposit(50)
print(a:balance())          -- 150

a:withdraw(20)
print(a:balance())          -- 130

local ok, err = a:withdraw(-5)
print(ok, err)              -- nil   "amount must be positive number"

local ok, err = a:transfer(b, 200)
print(ok, err)              -- nil   "insufficient funds"
print(a:balance(), b:balance())   -- 130   50  (! niezmienione, atomic)

local ok, err = a:transfer(b, 30)
print(ok, err)              -- 30   nil
print(a, b)                 -- Account<Anna: 100.00>   Account<Bartek: 80.00>
```

**Atomicity:** sprawdzamy wszystko przed jakimkolwiek `=`. Po sprawdzeniu — modyfikacje są deterministyczne (nie ma punktu, w którym jedna konta zmieniono a drugiego nie). To prosty case, ale pokazuje pattern.

**W concurrent code** (np. korutyny w Module 6) ten "atomic" wcale nie jest atomic — między `self._balance -= amount` a `other._balance += amount` może yieldować. Wtedy potrzebujesz lock'a. Tu zakładamy single-threaded (typowe dla Lua).

### Sprawdź się

- [ ] Umiem napisać szablon klasy: tabela + `__index` + konstruktor
- [ ] Wiem, że `:method()` przekazuje ukryte `self`
- [ ] Pamiętam, że konstruktor to `Class.new`, nie `Class:new`
- [ ] Każda moja klasa ma `__tostring`
- [ ] Wiem, jak walidować argumenty z dobrą ścieżką błędu (`error(msg, level)`)
- [ ] Rozumiem co znaczy "atomic" w prostej operacji jak transfer

---

## Lekcja 4.4: Dziedziczenie i polimorfizm

### Cel

Implementujesz dziedziczenie klas, znasz `super` pattern, wiesz, jak przesłaniać i rozszerzać metody, rozumiesz polimorfizm w Lua.

### Materiał

#### Dziedziczenie — podstawa

Tworzymy klasę pochodną przez ustawienie `__index` jej **klasy** na klasę bazową:

```lua
-- Klasa bazowa
local Animal = {}
Animal.__index = Animal

function Animal.new(name, sound)
    return setmetatable({name = name, sound = sound}, Animal)
end

function Animal:speak()
    return self.name .. " mówi: " .. self.sound
end

function Animal:describe()
    return "Animal: " .. self.name
end

-- Klasa pochodna
local Dog = setmetatable({}, {__index = Animal})    -- ! dziedziczenie
Dog.__index = Dog

function Dog.new(name)
    local self = Animal.new(name, "Hau!")           -- wywołaj konstruktor bazowej
    return setmetatable(self, Dog)                  -- ale ustaw Dog jako mt
end

function Dog:fetch()
    return self.name .. " przynosi piłkę"
end

-- Test:
local rex = Dog.new("Rex")
print(rex:speak())     -- "Rex mówi: Hau!"   (z Animal)
print(rex:describe())  -- "Animal: Rex"      (z Animal)
print(rex:fetch())     -- "Rex przynosi piłkę"  (z Dog)
```

Co się dzieje przy `rex:speak()`:
1. Lua szuka `speak` w `rex`. Brak.
2. Sprawdza metatable `rex` → `Dog`.
3. `Dog.__index = Dog`, więc szuka w `Dog`. Brak.
4. Sprawdza metatable `Dog` → `{__index = Animal}`.
5. Szuka w `Animal`. Znajduje. Wywołuje.

**Łańcuch dziedziczenia** chodzi przez kolejne `__index`-y.

#### Przesłanianie metod (override)

```lua
function Dog:describe()
    return "Dog: " .. self.name .. " (głośny)"
end

print(rex:describe())   -- "Dog: Rex (głośny)"
```

Od teraz `rex:describe()` znajduje metodę w `Dog`, nie w `Animal`. To override.

#### Wywołanie metody bazowej — `super`

W Lua nie ma słowa kluczowego `super`. Konwencja:

```lua
function Dog:describe()
    local base = Animal.describe(self)
    return base .. " (i przynosi piłkę)"
end

print(rex:describe())   -- "Animal: Rex (i przynosi piłkę)"
```

Wywołujesz `BaseClass.method(self, ...)` z jawnym `self`. To jest "super call" w Lua.

#### Pełen przykład — `Session` i `PrivilegedSession`

```lua
-- Klasa bazowa
local Session = {}
Session.__index = Session

function Session.new(sig)
    return setmetatable({
        sig = sig,
        atoms = {},
        epoch = 0,
        capabilities = {"phi.read"},
    }, Session)
end

function Session:add_atom(atom)
    self.atoms[#self.atoms + 1] = atom
    return #self.atoms
end

function Session:has_capability(cap)
    for _, c in ipairs(self.capabilities) do
        if c == cap then return true end
    end
    return false
end

function Session:__tostring()
    return string.format("Session<%s, atoms=%d>", self.sig, #self.atoms)
end

-- Klasa pochodna z dodatkowymi capabilities
local PrivilegedSession = setmetatable({}, {__index = Session})
PrivilegedSession.__index = PrivilegedSession

function PrivilegedSession.new(sig)
    local self = Session.new(sig)
    self.capabilities = {"phi.read", "phi.write", "session.spawn", "session.kill"}
    return setmetatable(self, PrivilegedSession)
end

function PrivilegedSession:spawn_child(child_sig)
    if not self:has_capability("session.spawn") then
        return nil, "no spawn capability"
    end
    return PrivilegedSession.new(child_sig)
end

-- Override z super-call
function PrivilegedSession:__tostring()
    local base = Session.__tostring(self)
    return base .. " [PRIV]"
end

-- Test:
local s = Session.new("user-001")
print(s:has_capability("phi.read"))      -- true
print(s:has_capability("phi.write"))     -- false
print(s)                                 -- Session<user-001, atoms=0>

local p = PrivilegedSession.new("admin-001")
print(p:has_capability("phi.read"))      -- true (z bazy)
print(p:has_capability("phi.write"))     -- true (override capabilities)

local child = p:spawn_child("child-001")
print(child)                              -- Session<child-001, atoms=0> [PRIV]
print(getmetatable(child) == PrivilegedSession)    -- true (jest privileged)
```

#### Polimorfizm

Polimorfizm = "wywołuję metodę X na obiekcie, nie wiedząc jakiej klasy jest". W Lua to działa naturalnie:

```lua
local function describe_all(things)
    for _, t in ipairs(things) do
        print(tostring(t))   -- każdy ma swoje __tostring
    end
end

describe_all({
    Session.new("a"),
    PrivilegedSession.new("b"),
    Session.new("c"),
})
-- Session<a, atoms=0>
-- Session<b, atoms=0> [PRIV]
-- Session<c, atoms=0>
```

Każdy obiekt sam wie, jak się przedstawić — `tostring()` woła ich własne `__tostring`.

#### Sprawdzanie typu w hierarchii

```lua
local function instance_of(obj, class)
    local mt = getmetatable(obj)
    while mt do
        if mt == class then return true end
        local meta_mt = getmetatable(mt)
        if not meta_mt then return false end
        mt = meta_mt.__index
    end
    return false
end

print(instance_of(p, PrivilegedSession))   -- true
print(instance_of(p, Session))             -- true (! przez dziedziczenie)
print(instance_of(s, PrivilegedSession))   -- false
print(instance_of(s, Session))             -- true
```

Iteruje przez łańcuch `__index`. Dla `p`: jego mt to `PrivilegedSession`, `PrivilegedSession`-mt to `{__index = Session}`, więc znajduje `Session` jako "ancestor".

#### Multiple inheritance — bonus

Lua pozwala na to przez `__index` jako funkcję:

```lua
local function make_class(...)
    local parents = {...}
    local class = {}
    setmetatable(class, {__index = function(t, k)
        for _, parent in ipairs(parents) do
            local v = parent[k]
            if v then return v end
        end
    end})
    class.__index = class
    return class
end

local Mixin1 = {hello = function(self) return "hello from mixin1" end}
local Mixin2 = {greet = function(self) return "greet from mixin2" end}

local Combined = make_class(Mixin1, Mixin2)
function Combined.new() return setmetatable({}, Combined) end

local c = Combined.new()
print(c:hello())    -- "hello from mixin1"
print(c:greet())    -- "greet from mixin2"
```

Multiple inheritance w Lua jest **rzadko stosowane** — większość projektów używa kompozycji. Pokazałem tylko żebyś wiedział że istnieje.

### Pułapki

1. **Łańcuch `__index`** — zbyt głęboka hierarchia spowalnia lookup. Każde wywołanie metody to przejście przez łańcuch.
2. **Konstruktor pochodnej** musi wywołać konstruktor bazowej jawnie (`Animal.new(name, sound)`).
3. **Override z super-call** — `Animal.method(self, ...)`, NIE `self:Animal.method(...)`.
4. **Multiple inheritance** komplikuje znacząco — diamond problem. Unikaj.
5. **Modyfikacja klasy w runtime** wpływa na wszystkie instancje przez łańcuch.

### Zadania

**Zadanie 4.4.1** — `Vehicle` → `Car` → `ElectricCar`  
Klasa `Vehicle` z `:start()`, `:describe()`. `Car` dziedziczy, dodaje `:honk()`. `ElectricCar` dziedziczy z `Car`, override `:start()` z dodatkowym komunikatem. Test instance_of.

**Zadanie 4.4.2** — `Shape` z polimorfizmem  
Klasa `Shape` z metodą `:area()` (rzuca error "abstract"). Pochodne: `Circle`, `Rectangle`, `Triangle` — każda implementuje `:area()`. Funkcja `total_area(shapes)` sumuje pola wszystkich.

**Zadanie 4.4.3** — Zegar i AlarmClock  
`Clock` z polami `h, m, s`, metodą `:tick()` (zwiększa o 1 sekundę). `AlarmClock` dziedziczy, dodaje pole `alarm` i override `:tick()` — gdy czas zgadza się z alarm, drukuje "DZWONI!".

**Zadanie 4.4.4** — Mixin pattern  
Napisz funkcję `add_mixin(class, mixin)`, która kopiuje wszystkie funkcje z `mixin` do `class`. Następnie zademonstruj: klasa `Atom` + mixin `Loggable` (dodaje `:log(msg)` z prefixem self.sig).

**Zadanie 4.4.5** — Hierarchia `Logger`  
Bazowa `Logger` z `:log(level, msg)`. Pochodne: `ConsoleLogger` (drukuje na stdout), `FileLogger` (zapisuje do tabeli `entries` w obiekcie), `FilteringLogger` (wrapper innego loggera + min_level — pomija niższe).

`FilteringLogger` przyjmuje wewnętrzny logger w konstruktorze (kompozycja, nie dziedziczenie). Wykorzystaj polimorfizm.

---

### Rozwiązania

#### Rozwiązanie 4.4.1

```lua
-- vehicle_hierarchy.lua
local Vehicle = {}
Vehicle.__index = Vehicle

function Vehicle.new(name)
    return setmetatable({name = name, started = false}, Vehicle)
end

function Vehicle:start()
    self.started = true
    return self.name .. " started"
end

function Vehicle:describe()
    return "Vehicle: " .. self.name
end

-- Car
local Car = setmetatable({}, {__index = Vehicle})
Car.__index = Car

function Car.new(name, brand)
    local self = Vehicle.new(name)
    self.brand = brand
    return setmetatable(self, Car)
end

function Car:honk()
    return self.name .. " HONK!"
end

function Car:describe()
    return "Car: " .. self.brand .. " " .. self.name
end

-- ElectricCar
local ElectricCar = setmetatable({}, {__index = Car})
ElectricCar.__index = ElectricCar

function ElectricCar.new(name, brand, battery_kwh)
    local self = Car.new(name, brand)
    self.battery_kwh = battery_kwh
    return setmetatable(self, ElectricCar)
end

function ElectricCar:start()
    local base = Vehicle.start(self)   -- super call
    return base .. " [silently, battery " .. self.battery_kwh .. "kWh]"
end

-- Helpers
local function instance_of(obj, class)
    local mt = getmetatable(obj)
    while mt do
        if mt == class then return true end
        local meta_mt = getmetatable(mt)
        if not meta_mt then return false end
        mt = meta_mt.__index
    end
    return false
end

-- Test:
local v = Vehicle.new("BasicV")
local c = Car.new("Civic", "Honda")
local e = ElectricCar.new("Model3", "Tesla", 75)

print(v:start())         -- BasicV started
print(c:start())         -- Civic started
print(e:start())         -- Model3 started [silently, battery 75kWh]

print(c:honk())          -- Civic HONK!
print(e:honk())          -- Model3 HONK!  (z Car)

print(v:describe())      -- Vehicle: BasicV
print(c:describe())      -- Car: Honda Civic  (override)
print(e:describe())      -- Car: Tesla Model3 (z Car, nie override w Electric)

-- Hierarchia:
print(instance_of(e, ElectricCar))   -- true
print(instance_of(e, Car))           -- true
print(instance_of(e, Vehicle))       -- true
print(instance_of(c, ElectricCar))   -- false
print(instance_of(v, Car))           -- false
```

`ElectricCar:start()` woła `Vehicle.start(self)` — pomija `Car` w łańcuchu (bo `Car` nie ma override). Możesz też wołać `Car.start(self)` jeśli chcesz "kolejny w łańcuchu". Wybór zależy od semantyki.

#### Rozwiązanie 4.4.2

```lua
-- shapes.lua
local Shape = {}
Shape.__index = Shape

function Shape.new()
    return setmetatable({}, Shape)
end

function Shape:area()
    error("abstract method: Shape:area must be overridden", 2)
end

function Shape:describe()
    return string.format("%s with area=%.4f", self.name, self:area())
end

-- Circle
local Circle = setmetatable({}, {__index = Shape})
Circle.__index = Circle

function Circle.new(radius)
    local self = setmetatable({name = "Circle", radius = radius}, Circle)
    return self
end

function Circle:area()
    return math.pi * self.radius * self.radius
end

-- Rectangle
local Rectangle = setmetatable({}, {__index = Shape})
Rectangle.__index = Rectangle

function Rectangle.new(w, h)
    return setmetatable({name = "Rectangle", w = w, h = h}, Rectangle)
end

function Rectangle:area()
    return self.w * self.h
end

-- Triangle (Heron's formula)
local Triangle = setmetatable({}, {__index = Shape})
Triangle.__index = Triangle

function Triangle.new(a, b, c)
    return setmetatable({name = "Triangle", a = a, b = b, c = c}, Triangle)
end

function Triangle:area()
    local s = (self.a + self.b + self.c) / 2
    return math.sqrt(s * (s - self.a) * (s - self.b) * (s - self.c))
end

-- Polymorphic function
local function total_area(shapes)
    local total = 0
    for _, s in ipairs(shapes) do
        total = total + s:area()
    end
    return total
end

-- Test:
local shapes = {
    Circle.new(5),
    Rectangle.new(3, 4),
    Triangle.new(3, 4, 5),
}

for _, s in ipairs(shapes) do
    print(s:describe())
end
-- Circle with area=78.5398
-- Rectangle with area=12.0000
-- Triangle with area=6.0000

print(string.format("Total: %.4f", total_area(shapes)))
-- Total: 96.5398

-- Próba wywołania abstrakcyjnej:
local s = Shape.new()
local ok, err = pcall(function() return s:area() end)
print(ok, err)
-- false   "...abstract method: Shape:area must be overridden"
```

`Shape:area()` rzuca error — to "abstract" w Lua-style. Każdy konkretny kształt musi override'ować. `total_area` to czysty polimorfizm: nie wie, jakie kształty dostaje, ale każdy odpowiada na `:area()`.

#### Rozwiązanie 4.4.3

```lua
-- clocks.lua
local Clock = {}
Clock.__index = Clock

function Clock.new(h, m, s)
    return setmetatable({h = h or 0, m = m or 0, s = s or 0}, Clock)
end

function Clock:tick()
    self.s = self.s + 1
    if self.s >= 60 then
        self.s = 0
        self.m = self.m + 1
        if self.m >= 60 then
            self.m = 0
            self.h = (self.h + 1) % 24
        end
    end
end

function Clock:__tostring()
    return string.format("%02d:%02d:%02d", self.h, self.m, self.s)
end

function Clock:equals_time(h, m, s)
    return self.h == h and self.m == m and self.s == s
end

-- AlarmClock
local AlarmClock = setmetatable({}, {__index = Clock})
AlarmClock.__index = AlarmClock

function AlarmClock.new(h, m, s, alarm)
    local self = Clock.new(h, m, s)
    self.alarm = alarm   -- {h, m, s} or nil
    return setmetatable(self, AlarmClock)
end

function AlarmClock:tick()
    Clock.tick(self)   -- super call
    if self.alarm and self:equals_time(self.alarm.h, self.alarm.m, self.alarm.s) then
        print("[" .. tostring(self) .. "] DZWONI!")
    end
end

function AlarmClock:set_alarm(h, m, s)
    self.alarm = {h = h, m = m, s = s}
end

-- Test:
local c = Clock.new(23, 59, 58)
print(c)         -- 23:59:58
c:tick(); print(c)   -- 23:59:59
c:tick(); print(c)   -- 00:00:00 (zawinięcie)
c:tick(); print(c)   -- 00:00:01

print()
print("--- AlarmClock ---")

local a = AlarmClock.new(7, 29, 58, {h=7, m=30, s=0})
for _ = 1, 5 do
    a:tick()
    print(a)
end
-- 07:29:59
-- [07:30:00] DZWONI!
-- 07:30:00
-- 07:30:01
-- 07:30:02
-- 07:30:03
```

`AlarmClock:tick()` używa super-call `Clock.tick(self)` żeby wykonać "normalny tick", a potem dodaje sprawdzenie alarmu. To czysty pattern "extend by override + super".

#### Rozwiązanie 4.4.4

```lua
-- mixin.lua
local function add_mixin(class, mixin)
    for k, v in pairs(mixin) do
        if type(v) == "function" then
            class[k] = v
        end
    end
end

-- Mixin: Loggable
local Loggable = {}

function Loggable:log(msg)
    print(string.format("[%s] %s", self.sig or "?", msg))
end

function Loggable:warn(msg)
    print(string.format("[%s] WARN: %s", self.sig or "?", msg))
end

-- Mixin: Serializable
local Serializable = {}

function Serializable:to_table()
    local t = {}
    for k, v in pairs(self) do
        if type(v) ~= "function" then
            t[k] = v
        end
    end
    return t
end

-- Klasa Atom z mixin-ami
local Atom = {}
Atom.__index = Atom

function Atom.new(sig, phi)
    return setmetatable({sig = sig, phi = phi}, Atom)
end

function Atom:get_phi()
    return self.phi
end

add_mixin(Atom, Loggable)
add_mixin(Atom, Serializable)

-- Test:
local a = Atom.new("abc", 0.7)
print(a:get_phi())    -- 0.7
a:log("created")      -- [abc] created
a:warn("phi low")     -- [abc] WARN: phi low

local t = a:to_table()
for k, v in pairs(t) do
    print(k, v)
end
-- sig   abc
-- phi   0.7
```

Mixin pattern dodaje funkcjonalność do klasy bez dziedziczenia. Klasa może mieć wiele mixin-ów (multiple inheritance "lite"). `add_mixin` kopiuje funkcje — niektóre warianty kopiują też pola, ale to ryzykowne (kolizje).

#### Rozwiązanie 4.4.5

```lua
-- logger_hierarchy.lua

-- Bazowa
local Logger = {}
Logger.__index = Logger

function Logger.new()
    return setmetatable({}, Logger)
end

function Logger:log(level, msg)
    error("abstract: Logger:log must be overridden", 2)
end

-- ConsoleLogger
local ConsoleLogger = setmetatable({}, {__index = Logger})
ConsoleLogger.__index = ConsoleLogger

function ConsoleLogger.new()
    return setmetatable({}, ConsoleLogger)
end

function ConsoleLogger:log(level, msg)
    print(string.format("[%s] %s", level, msg))
end

-- FileLogger (in-memory dla uproszczenia)
local FileLogger = setmetatable({}, {__index = Logger})
FileLogger.__index = FileLogger

function FileLogger.new()
    return setmetatable({entries = {}}, FileLogger)
end

function FileLogger:log(level, msg)
    self.entries[#self.entries + 1] = {
        level = level,
        msg = msg,
        time = os.time(),
    }
end

function FileLogger:get_entries()
    return self.entries
end

-- FilteringLogger (kompozycja!)
local FilteringLogger = setmetatable({}, {__index = Logger})
FilteringLogger.__index = FilteringLogger

local LEVELS = {DEBUG = 1, INFO = 2, WARN = 3, ERROR = 4, FATAL = 5}

function FilteringLogger.new(inner, min_level)
    return setmetatable({
        inner = inner,
        min_level = LEVELS[min_level] or 1,
    }, FilteringLogger)
end

function FilteringLogger:log(level, msg)
    local lvl_num = LEVELS[level] or 0
    if lvl_num >= self.min_level then
        self.inner:log(level, msg)
    end
end

-- Test:
print("--- ConsoleLogger ---")
local console = ConsoleLogger.new()
console:log("INFO", "session opened")
console:log("DEBUG", "phi=0.7")
console:log("ERROR", "disk full")

print()
print("--- FileLogger ---")
local file = FileLogger.new()
file:log("INFO", "started")
file:log("DEBUG", "checkpoint 1")
file:log("WARN", "low disk")

for i, e in ipairs(file:get_entries()) do
    print(i, e.level, e.msg)
end

print()
print("--- FilteringLogger (WARN+) ---")
local filtered = FilteringLogger.new(console, "WARN")
filtered:log("DEBUG", "skip this")    -- (cisza)
filtered:log("INFO", "skip this too") -- (cisza)
filtered:log("WARN", "show this")     -- "[WARN] show this"
filtered:log("ERROR", "and this")     -- "[ERROR] and this"

print()
print("--- FilteringLogger wokół FileLogger ---")
local filtered_file = FilteringLogger.new(FileLogger.new(), "WARN")
filtered_file:log("INFO", "ignored")
filtered_file:log("WARN", "kept")
filtered_file:log("ERROR", "kept too")
print("entries:", #filtered_file.inner.entries)   -- 2
```

`FilteringLogger` jest **wrapper-em** (nie dziedziczy z konkretnego loggera). To **kompozycja** — preferowana zwykle nad dziedziczeniem. Polimorfizm: `inner` może być dowolnym Logger-em.

To jest klasyczny **decorator pattern**.

### Sprawdź się

- [ ] Umiem napisać klasę pochodną przez `setmetatable(Pochodna, {__index = Bazowa})`
- [ ] Pamiętam wzorzec `Pochodna.new` wywołujący `Bazowa.new` plus `setmetatable(self, Pochodna)`
- [ ] Wiem, jak zrobić super-call: `Bazowa.method(self, ...)`
- [ ] Umiem napisać `instance_of` przechodzący łańcuch dziedziczenia
- [ ] Znam pattern mixin (kopiowanie funkcji)
- [ ] Wiem, kiedy preferować kompozycję nad dziedziczeniem

---

## Lekcja 4.5: `__call`, `__metatable`, `__pairs` i pozostałe

### Cel

Znasz mniej oczywiste metametody: `__call` (tabela jak funkcja), `__metatable` (ochrona), `__pairs` (kontrola iteracji), `__index` z dziedziczeniem statycznych pól.

### Materiał

#### `__call` — tabela jak funkcja

```lua
local Counter = {}
Counter.__index = Counter

function Counter.new()
    return setmetatable({n = 0}, Counter)
end

function Counter:__call(...)
    self.n = self.n + 1
    return self.n, ...
end

local c = Counter.new()
print(c())       -- 1
print(c())       -- 2
print(c("x", "y"))   -- 3   x   y
```

Każda tabela z `__call` może być wywołana jak funkcja. Pierwszy argument to sama tabela (jak `self`).

#### Konstruktor jako `__call` na klasie

Częsty pattern: chcesz pisać `Holon(sig, phi)` zamiast `Holon.new(sig, phi)`:

```lua
local Holon = {}
Holon.__index = Holon

function Holon:get_phi() return self.phi end

setmetatable(Holon, {
    __call = function(_, sig, phi)
        return setmetatable({sig = sig, phi = phi or 0.0}, Holon)
    end
})

local h = Holon("abc", 0.7)    -- jak konstruktor!
print(h:get_phi())              -- 0.7
```

Tu `Holon` ma własne metatable (osobne od `Holon` jako `__index` instancji). Trochę confusing — dwa metatable w grze:
- Metatable instancji: `Holon` (z `__index = Holon`).
- Metatable klasy: anonimowa `{__call = ...}`.

To ten sam pattern co `Pipeline()` ze sprawdzianu M3.

#### `__metatable` — ochrona

```lua
local t = setmetatable({}, {
    __metatable = "this is private"
})

print(getmetatable(t))    -- "this is private"   (zwraca pole __metatable, nie prawdziwy mt)

-- Próba zmiany:
local ok, err = pcall(function() setmetatable(t, {}) end)
print(ok, err)
-- false   "...cannot change a protected metatable"
```

Gdy metatable ma pole `__metatable`:
- `getmetatable(t)` zwraca **wartość pola** `__metatable` (zwykle string identyfikujący), a nie prawdziwy mt.
- `setmetatable(t, ...)` **rzuca błąd**.

To zabezpieczenie przed manipulacją metatable z zewnątrz. W KarmazynOS / sandboxach — kluczowe. Bez tego sandbox mógłby zmienić `__index` na wskaźnik do swojego kodu i obejść ograniczenia.

```lua
-- Frozen z lepszą ochroną:
local function freeze_protected(t)
    return setmetatable({}, {
        __index = t,
        __newindex = function() error("frozen", 2) end,
        __metatable = "frozen"   -- (! ochrona)
    })
end
```

#### `__pairs` (5.2+)

Kontrola jak działa `pairs(t)` na danym obiekcie:

```lua
local CountingTable = {}
CountingTable.__index = CountingTable

function CountingTable.new()
    return setmetatable({_data = {a = 1, b = 2, c = 3}}, CountingTable)
end

function CountingTable:__pairs()
    return next, self._data, nil
end

local ct = CountingTable.new()

for k, v in pairs(ct) do
    print(k, v)
end
-- a   1
-- b   2
-- c   3
```

`__pairs` zwraca trzy wartości: iterator, obiekt nad którym iterujemy, początkowy stan. Standardowy `pairs` zwraca `next, t, nil` — my robimy to samo, ale wskazując `_data`.

To używamy gdy "publiczna" tabela ma metadane wewnętrzne, które chcemy ukryć podczas iteracji.

**Uwaga:** Lua 5.4 nieformalnie deprecuje `__pairs` i zaleca pisać własną funkcję iteratora. Ale `__pairs` wciąż działa.

#### `__ipairs` (5.2 only)

Istniała w 5.2, **usunięta** w 5.3. Nie używamy.

#### Łańcuch metatable (deep `__index`)

```lua
local Granny = {gen = "G"}
Granny.__index = Granny

local Mom = setmetatable({gen = "M"}, {__index = Granny})
Mom.__index = Mom

local Daughter = setmetatable({}, {__index = Mom})
Daughter.__index = Daughter

local d = setmetatable({}, Daughter)

print(d.gen)    -- "M"  (z Mom — Daughter nie ma)
```

Lookup chodzi: `d` → `Daughter` (przez `__index`) → `Mom` (przez `Daughter`'s metatable's `__index`) → znajduje `gen = "M"`.

Idzie głębiej dopiero gdy nie znajdzie. To jest **prototypowy OOP** — łańcuch prototypów, jak w JavaScript.

#### Statyczne pola klasy

```lua
local Atom = {}
Atom.__index = Atom

Atom.MAX_PHI = 1.0      -- "stała klasy"
Atom.count = 0          -- counter klasy

function Atom.new(sig, phi)
    Atom.count = Atom.count + 1
    return setmetatable({sig = sig, phi = phi or 0.0}, Atom)
end

function Atom:is_max()
    return self.phi >= Atom.MAX_PHI
end

local a = Atom.new("a", 0.5)
local b = Atom.new("b", 1.0)
print(Atom.count)      -- 2
print(a:is_max())      -- false
print(b:is_max())      -- true
```

`Atom.MAX_PHI` i `Atom.count` to "static fields" — należą do klasy, nie instancji. Dostępne przez `Atom.MAX_PHI` (z dowolnego miejsca) i przez `self:metoda()` która woła `Atom.MAX_PHI`.

**Pułapka:** `a.MAX_PHI` też zwróci 1.0 (przez `__index` fallback do `Atom`)! To może być chcianie lub niechcianie. Jeśli niechciane — keep as `Atom.MAX_PHI` always.

### Pułapki

1. **`__call`** może uczynić tabelę "callable" — confusing dla czytelnika kodu, używaj świadomie.
2. **`__metatable`** raz ustawiony — nie da się zdjąć (poza `rawset` na metatable, który wymaga dostępu do mt).
3. **`__pairs`** w 5.4 deprecated stylu — preferuj jawny iterator.
4. **Statyczne pola dostępne przez instancję** — może być cechą lub bugiem.

### Zadania

**Zadanie 4.5.1** — Function-like object  
Napisz `make_accumulator(initial)` zwracający tabelę-callable. Każde wywołanie z liczbą — dodaje. Bez argumentu — zwraca aktualną sumę.

```lua
local acc = make_accumulator(10)
acc(5)    -- 15
acc(3)    -- 18
acc(-2)   -- 16
print(acc())   -- 16
```

**Zadanie 4.5.2** — Class with __call konstruktor  
Przepisz `Vec2` (z Lekcji 4.2) tak, by można było pisać `Vec2(1, 2)` zamiast `Vec2.new(1, 2)`.

**Zadanie 4.5.3** — Sealed object  
Napisz `seal(t)` — tabela której nie da się modyfikować ANI metatable której nie da się zmienić.

```lua
local s = seal({x = 1, y = 2})
print(s.x)        -- 1
local ok = pcall(function() s.x = 99 end)
print(ok)          -- false
local ok = pcall(function() setmetatable(s, {}) end)
print(ok)          -- false
```

**Zadanie 4.5.4** — Singleton  
Napisz `Singleton(class)` — funkcję, która z klasy robi singleton (każde wywołanie konstruktora zwraca ten sam obiekt).

```lua
local Logger = {}
Logger.__index = Logger
function Logger:log(msg) print("[LOG]", msg) end

Singleton(Logger)

local l1 = Logger()
local l2 = Logger()
print(l1 == l2)    -- true
l1:log("hello")
```

**Zadanie 4.5.5** — Read-only iteration  
Napisz `read_only_iter(t)` — proxy, po którym można iterować przez `pairs` (zwraca pary), ale nie można modyfikować ani dodać klucza.

---

### Rozwiązania

#### Rozwiązanie 4.5.1

```lua
-- accumulator.lua
local function make_accumulator(initial)
    return setmetatable({sum = initial or 0}, {
        __call = function(self, x)
            if x ~= nil then
                self.sum = self.sum + x
            end
            return self.sum
        end
    })
end

local acc = make_accumulator(10)
print(acc(5))     -- 15
print(acc(3))     -- 18
print(acc(-2))    -- 16
print(acc())      -- 16  (bez argumentu — sama suma)
print(acc.sum)    -- 16  (też bezpośrednio)
```

`__call` z opcjonalnym argumentem — sprawdzamy `x ~= nil`. Bez argumentu wynik to "tylko bieżąca suma".

#### Rozwiązanie 4.5.2

```lua
-- vec2_callable.lua
local Vec2 = {}
Vec2.__index = Vec2

function Vec2:__add(other)
    return Vec2(self.x + other.x, self.y + other.y)   -- używa nowego konstruktora
end

function Vec2:__tostring()
    return string.format("(%g, %g)", self.x, self.y)
end

setmetatable(Vec2, {
    __call = function(_, x, y)
        return setmetatable({x = x, y = y}, Vec2)
    end
})

-- Test:
local v1 = Vec2(1, 2)
local v2 = Vec2(3, 4)
print(v1)         -- (1, 2)
print(v1 + v2)    -- (4, 6)
print(getmetatable(v1) == Vec2)   -- true
```

Klasy w JavaScript też tak są: `new Vec2(1, 2)` (lub w nowszym JS bez `new` + `__call`-like).

#### Rozwiązanie 4.5.3

```lua
-- seal.lua
local function seal(t)
    local proxy = setmetatable({}, {
        __index = t,
        __newindex = function(_, k, _)
            error("sealed table: cannot set " .. tostring(k), 2)
        end,
        __metatable = "sealed",   -- chroni metatable
        __pairs = function() return pairs(t) end,
    })
    return proxy
end

local s = seal({x = 1, y = 2})

print(s.x)    -- 1
print(s.y)    -- 2

local ok, err = pcall(function() s.x = 99 end)
print(ok, err)    -- false   "...sealed table: cannot set x"

local ok, err = pcall(function() s.z = 3 end)
print(ok, err)    -- false   "...sealed table: cannot set z"

local ok, err = pcall(function() setmetatable(s, {}) end)
print(ok, err)    -- false   "...cannot change a protected metatable"

print(getmetatable(s))   -- "sealed"

-- Iteracja działa:
for k, v in pairs(s) do
    print(k, v)
end
-- x   1
-- y   2
```

Kombinacja `__newindex` + `__metatable` daje pełną ochronę. `__pairs` przekazuje iterację do oryginalnej tabeli.

#### Rozwiązanie 4.5.4

```lua
-- singleton.lua
local function Singleton(class)
    local instance = nil
    setmetatable(class, {
        __call = function(cls, ...)
            if instance == nil then
                if cls.new then
                    instance = cls.new(...)
                else
                    instance = setmetatable({}, cls)
                end
            end
            return instance
        end
    })
end

-- Test:
local Logger = {}
Logger.__index = Logger

function Logger:log(msg)
    print("[LOG]", msg)
end

Singleton(Logger)

local l1 = Logger()
local l2 = Logger()
print(l1 == l2)    -- true

l1:log("hello")
l2:log("world")
-- [LOG]   hello
-- [LOG]   world
```

`Singleton` modyfikuje metatable klasy, dodając `__call`. `instance` jest closure-cached — pierwsze wywołanie tworzy, kolejne zwracają to samo.

Pułapki: jeśli klasa miała już metatable (np. dla dziedziczenia), `Singleton` ją nadpisuje. Solidniejsza wersja by sprawdziła `getmetatable(class)` i merge-owała.

#### Rozwiązanie 4.5.5

```lua
-- read_only_iter.lua
local function read_only_iter(t)
    return setmetatable({}, {
        __index = t,
        __newindex = function(_, k, _)
            error("read-only: cannot set " .. tostring(k), 2)
        end,
        __pairs = function() return pairs(t) end,
        __len = function() return #t end,
        __metatable = "read-only",
    })
end

-- Test:
local original = {a = 1, b = 2, c = 3}
local ro = read_only_iter(original)

-- Czytanie i iteracja:
print(ro.a)              -- 1
for k, v in pairs(ro) do
    print(k, v)
end
-- a   1
-- b   2
-- c   3

-- Próba modyfikacji:
local ok = pcall(function() ro.a = 99 end)
print(ok)    -- false

-- Oryginał wciąż mutowalny:
original.a = 100
print(ro.a)   -- 100  (! widzi zmiany w oryginale)

-- Sekwencja:
local seq = read_only_iter({"x", "y", "z"})
print(#seq)              -- 3
for i, v in ipairs(seq) do print(i, v) end
-- 1   x
-- 2   y
-- 3   z
```

To jest "view" na tabelę — jak `MappingProxyType` w Pythonie. Klient może czytać i iterować, ale nie modyfikować. Zmiany w oryginale są widoczne (jeśli to pożądane lub nie — zależy od use-case).

### Sprawdź się

- [ ] Umiem zrobić tabelę-callable przez `__call`
- [ ] Umiem zrobić "konstruktor jak funkcję" przez metatable klasy z `__call`
- [ ] Wiem, że `__metatable` chroni przed manipulacją
- [ ] Znam `__pairs` (i wiem, że w 5.4 preferujemy jawne iteratory)
- [ ] Umiem stworzyć read-only proxy

---

## Lekcja 4.6: Weak tables, `__gc`, finalizatory

### Cel

Rozumiesz co to słabe referencje i kiedy ich używać. Implementujesz cache LRU. Znasz finalizatory `__gc` i ich pułapki.

### Materiał

#### Garbage Collector — przypomnienie

Lua ma **incremental mark-and-sweep GC**. Zbiera obiekty (tabele, funkcje, korutyny, userdata, stringi), do których nie ma już żadnych "silnych referencji".

```lua
local t = {data = "wielka tablica"}
t = nil    -- usuwamy ostatnią referencję
collectgarbage()    -- wymuszamy GC
-- pamięć po t zwolniona
```

W normalnym kodzie nie trzeba `collectgarbage()` — uruchamia się automatycznie.

#### Weak references

**Słaba referencja** to taka, której GC ignoruje przy decydowaniu czy usunąć obiekt. Jeśli obiekt ma tylko słabe referencje — GC go usuwa.

W Lua to robimy przez `__mode` na metatable tabeli:

```lua
local cache = setmetatable({}, {__mode = "v"})
-- "v" = wartości słabe
-- "k" = klucze słabe
-- "kv" = oba słabe
```

#### Słabe wartości — typowy przypadek

Cache, który nie powinien przeciwstawiać się GC:

```lua
local cache = setmetatable({}, {__mode = "v"})

local function load_image(path)
    if cache[path] then return cache[path] end
    local img = {data = "duża zawartość obrazu"}    -- droga operacja
    cache[path] = img
    return img
end

local img = load_image("logo.png")
-- cache["logo.png"] istnieje, img wskazuje na obraz

img = nil    -- usuwamy lokalną referencję
collectgarbage()
-- cache["logo.png"] może (ale nie musi) być teraz nil
-- bo była tylko słaba referencja w cache
print(cache["logo.png"])    -- nil (po GC)
```

To jest cache "best effort" — jeśli pamięć potrzebna, GC zwalnia. Idealne dla: cache obrazów, cache parsowania, scratch buffers.

#### Słabe klucze

```lua
local listeners = setmetatable({}, {__mode = "k"})
listeners[some_object] = "callback dla tego obiektu"

some_object = nil
collectgarbage()
-- listeners nie trzyma some_object przy życiu — wpis znika
```

Use case: chcesz przypisać metadane do obiektu, ale gdy obiekt umiera — metadane też. Np. mapa "obiekt → callback" gdzie nie chcesz wycieku gdy obiekt znika.

#### Pełna implementacja LRU lite

```lua
local function make_cache(loader)
    local cache = setmetatable({}, {__mode = "v"})
    return function(key)
        local v = cache[key]
        if v ~= nil then return v end
        v = loader(key)
        cache[key] = v
        return v
    end
end

local count_loads = 0
local image_loader = make_cache(function(path)
    count_loads = count_loads + 1
    return {data = "image " .. path, loaded_at = os.time()}
end)

local img1 = image_loader("a.png")
local img2 = image_loader("b.png")
print(count_loads)         -- 2

local img3 = image_loader("a.png")    -- cache hit (img1 wciąż żyje)
print(count_loads)         -- 2

img1, img3 = nil, nil
collectgarbage()
local img4 = image_loader("a.png")    -- już nie w cache (GC wyczyścił)
print(count_loads)         -- 3
```

Cache automatycznie się "kurczy" pod presją pamięci. Bez jawnego LRU.

#### `__gc` — finalizator

Funkcja wywoływana **przed** zniszczeniem obiektu przez GC:

```lua
local t = setmetatable({name = "test"}, {
    __gc = function(self)
        print("GC: niszczę " .. self.name)
    end
})

t = nil
collectgarbage()
-- GC: niszczę test
```

Use case:
- Zamknięcie pliku gdy obiekt go opisujący umiera.
- Zwolnienie zasobu C (handle, lock).
- Logowanie cleanup-u.

#### Pułapki `__gc`

1. **Dla TABEL `__gc` jest wywoływane TYLKO gdy metatable istniała w momencie ustawiania tabeli na metatable.** Czyli:

```lua
local t = {}
setmetatable(t, {__gc = function() print("gc!") end})
t = nil
collectgarbage()
-- (cisza! gc nie odpaliło)

-- Naprawa: ustaw metatable razem z tabelą:
local t = setmetatable({}, {__gc = function() print("gc!") end})
t = nil
collectgarbage()
-- gc!
```

To dziwactwo kompatybilności — Lua 5.1 nie miało `__gc` dla tabel, więc 5.2+ dodała ostrożnie. Dla **userdata** (Moduł 9) `__gc` zawsze działa.

2. **`__gc` może uruchomić się w niedeterministycznym momencie.** Cykle silnych referencji + GC = obiekt może długo żyć.

3. **Jeśli `__gc` rzuci błąd — Lua traktuje to specjalnie** (loguje, ale nie propagują). Wewnątrz `__gc` używaj `pcall`.

4. **Resurrection** — jeśli `__gc` wpisze `self` gdzieś (do globalnej), obiekt "zmartwychwstaje". Potem `__gc` nie zostanie wywołane drugi raz.

#### `collectgarbage` — kontrola

```lua
collectgarbage()                   -- pełen cykl GC
collectgarbage("count")            -- zwraca: KB w użyciu, bytes additional
collectgarbage("stop")             -- wstrzymaj GC
collectgarbage("restart")          -- wznów
collectgarbage("step", n)          -- mały krok GC
collectgarbage("setpause", 200)    -- ustaw pauzę (% — kiedy znów uruchomić)
collectgarbage("setstepmul", 200)  -- ustaw mnożnik krokiu
```

W KarmazynOS dla sandboxowanych skryptów: ustawiasz `setpause` i `setstepmul` agresywnie (więcej GC = mniej pamięci, ale więcej CPU). Można też tunnelować — uruchamiać GC po każdym `pcall`-u skryptu.

#### `collectgarbage("count")` — pomiar

```lua
print(string.format("Pamięć: %.2f KB", collectgarbage("count")))
```

Use case: profilowanie pamięci. Przed operacją zmierz, po operacji zmierz, różnica = ile zaalokowała.

### Pułapki

1. **`__mode` musi być na metatable**, nie na tabeli.
2. **Słabe wartości muszą być GC-able** — primitives (number, boolean, string) **nie są** wywalane (są internowane lub wartościowe). Tylko tabele, funkcje, threads, userdata.
3. **`__gc` na tabeli** — ustaw metatable JEDNOCZEŚNIE z tabelą.
4. **Order finalizacji niezdefiniowany** — nie pisz `__gc` zależnego od kolejności.
5. **Cykle z weak references** — mogą "wypaść" niespodziewanie. Testuj.

### Zadania

**Zadanie 4.6.1** — Resource z auto-close  
Napisz "Resource" — obiekt z metodą `:close()` i finalizatorem, który wywołuje close jeśli ktoś o tym zapomniał. Każdy zasób ma unikalny ID. Przy close oraz GC drukuj komunikaty.

```lua
local r1 = Resource.new("plik1")
local r2 = Resource.new("plik2")
r1:close()                  -- "closing plik1"
r2 = nil; collectgarbage()  -- "auto-closing plik2"
```

**Zadanie 4.6.2** — Weak observers  
Zmodyfikuj observer pattern z M3 (Lekcja 3.3.3) tak, by obserwatorzy byli słabymi referencjami — gdy obserwator umiera, automatycznie zostaje odpisany.

**Zadanie 4.6.3** — Memory profiler dla funkcji  
Napisz `measure_memory(fn, ...)` — wywołuje fn, zwraca `(result, kb_allocated)`. Przed pomiarem `collectgarbage()`.

**Zadanie 4.6.4** — Cache z TTL i weak  
Połącz: cache, w którym wpisy są **i** weak (mogą zniknąć pod GC) **i** ttl-ograniczone (po N sekund eksperują).

**Zadanie 4.6.5** — Object registry  
Napisz `Registry.new()` — rejestr obiektów po nazwie, ale słaby (jeśli obiekt znika z innych miejsc, znika z rejestru). Metody: `register(name, obj)`, `get(name)`, `count()`.

---

### Rozwiązania

#### Rozwiązanie 4.6.1

```lua
-- resource.lua
local Resource = {}
Resource.__index = Resource

local _next_id = 0

function Resource.new(name)
    _next_id = _next_id + 1
    local self = setmetatable({
        id = _next_id,
        name = name,
        closed = false,
    }, Resource)
    print(string.format("opened %s (#%d)", self.name, self.id))
    return self
end

function Resource:close()
    if self.closed then return end
    self.closed = true
    print(string.format("closing %s (#%d)", self.name, self.id))
end

-- Finalizator
function Resource:__gc()
    if not self.closed then
        print(string.format("auto-closing %s (#%d)", self.name, self.id))
        self:close()
    end
end

-- Test:
print("--- Test 1: explicit close ---")
local r1 = Resource.new("plik1")
r1:close()
r1 = nil; collectgarbage()
-- opened plik1 (#1)
-- closing plik1 (#1)

print()
print("--- Test 2: auto-close via GC ---")
local r2 = Resource.new("plik2")
r2 = nil; collectgarbage()
-- opened plik2 (#2)
-- auto-closing plik2 (#2)
-- closing plik2 (#2)
```

`__gc` wywołane automatycznie. `self.closed` flag zapobiega podwójnemu zamknięciu.

To jest pattern "best practice" — jawne `close()` preferowane, ale fallback na finalizator zabezpiecza przed wyciekami.

#### Rozwiązanie 4.6.2

```lua
-- weak_observable.lua
local function make_observable_weak(initial)
    local value = initial
    -- Obserwatorzy są w słabej tabeli — automatycznie znikają gdy zostaną GC
    local observers = setmetatable({}, {__mode = "v"})
    
    return {
        get = function() return value end,
        
        set = function(new_value)
            local old_value = value
            value = new_value
            for _, obs in pairs(observers) do
                obs(new_value, old_value)
            end
        end,
        
        subscribe = function(fn)
            -- fn musi być przechowywany jako zmienna w wywołującym kodzie,
            -- inaczej zostanie GC'd po wyjściu z funkcji subscribe.
            observers[fn] = fn
            return function()
                observers[fn] = nil
            end
        end,
    }
end

-- Test:
local phi = make_observable_weak(0.5)

local fn1 = function(new, old) print("obs1:", old, "->", new) end
local fn2 = function(new, old) print("obs2:", old, "->", new) end

phi.subscribe(fn1)
phi.subscribe(fn2)

phi.set(0.7)
-- obs1:  0.5  ->  0.7
-- obs2:  0.5  ->  0.7

fn1 = nil; collectgarbage()
phi.set(0.9)
-- obs2:  0.7  ->  0.9
-- (obs1 nie wywołane, bo fn1 GC'd)
```

**Pułapka:** w tym kodzie `fn1` musi być trzymane w wywołującym kodzie, inaczej GC sprzątnie. To może być nieintuicyjne — w klasycznym observer pattern tworzysz funkcję `function(new, old) ... end` w `subscribe` i nie trzymasz referencji.

**Rozwiązanie alternatywne:** `subscribe(fn)` może zwracać "handle" które klient musi trzymać. Wtedy GC handle = unsubscribe automatyczne.

```lua
-- Wersja z handle:
subscribe = function(fn)
    local handle = {fn = fn}
    observers[handle] = handle    -- klucz silny, wartość = handle (silna)
    -- Ale handle też GC-able przez słabe wartości:
    -- ...
    return handle    -- klient trzyma handle
end
```

Konkretna implementacja zależy od desired semantics. Pokazałem prostą wersję żeby zilustrować zasadę weak references.

#### Rozwiązanie 4.6.3

```lua
-- measure_memory.lua
local function measure_memory(fn, ...)
    collectgarbage()           -- wyczyść grunt
    collectgarbage("stop")     -- wstrzymaj na czas pomiaru (! żeby nie czyścił między)
    
    local before = collectgarbage("count")
    local result = table.pack(fn(...))
    local after = collectgarbage("count")
    
    collectgarbage("restart")
    
    return after - before, table.unpack(result, 1, result.n)
end

-- Test:
local kb, result = measure_memory(function()
    local t = {}
    for i = 1, 10000 do
        t[i] = "string number " .. i
    end
    return #t
end)
print(string.format("Allocated: %.2f KB", kb))
print("Result:", result)
-- Allocated: ~XXX KB
-- Result: 10000

-- Funkcja "lekka":
local kb2 = measure_memory(function() return 1 + 2 end)
print(string.format("Light: %.2f KB", kb2))
-- Light: ~0 KB
```

`collectgarbage("count")` zwraca KB pamięci heap'u. Różnica `after - before` to przybliżona alokacja. Pamiętaj że to **netto** — jeśli funkcja alokuje i potem zwalnia, pomiar może wyjść 0.

`stop`/`restart` zapobiega GC w trakcie pomiaru — bez tego mogłoby zwolnić w środku i pomiar by się rozjechał.

#### Rozwiązanie 4.6.4

```lua
-- weak_ttl_cache.lua
local function make_cache_weak_ttl(loader, ttl_seconds)
    local data = setmetatable({}, {__mode = "v"})    -- weak values
    local timestamps = {}                              -- ttl tracking (silna)
    
    return function(key)
        local now = os.time()
        local cached = data[key]
        local ts = timestamps[key]
        
        if cached ~= nil and ts and (ts + ttl_seconds > now) then
            return cached
        end
        
        -- Either weak GC zabrał, albo TTL wygasł
        local v = loader(key)
        data[key] = v
        timestamps[key] = now
        return v
    end
end

local count_loads = 0
local cache = make_cache_weak_ttl(function(key)
    count_loads = count_loads + 1
    return {key = key, computed_at = os.time()}
end, 60)    -- TTL = 60 sekund

local a = cache("foo")
print(count_loads)    -- 1
local a2 = cache("foo")
print(count_loads)    -- 1 (cache hit)

a, a2 = nil, nil
collectgarbage()
local a3 = cache("foo")
print(count_loads)    -- 2 (recomputed po GC)
```

Dwie warstwy ochrony: weak (GC może zwolnić), TTL (po czasie wymusza odświeżenie). Used case: kosztowne obliczenie którego wynik chcesz cache'ować, ale nie chcesz ani trzymać miliona wpisów, ani serwować zacofanych odpowiedzi.

Tabela `timestamps` jest silna — bo timestamp to liczba (zawsze internowana w Lua, weak nie zadziała na liczbach). I tak: gdy weak `data[key]` wypadnie, `timestamps[key]` zostanie. To "memory leak" timestampów. Dla długo działającej aplikacji można dodać sweep co N wywołań.

#### Rozwiązanie 4.6.5

```lua
-- registry.lua
local Registry = {}
Registry.__index = Registry

function Registry.new()
    return setmetatable({
        _by_name = setmetatable({}, {__mode = "v"}),    -- weak values
    }, Registry)
end

function Registry:register(name, obj)
    self._by_name[name] = obj
end

function Registry:get(name)
    return self._by_name[name]
end

function Registry:count()
    local n = 0
    for _ in pairs(self._by_name) do n = n + 1 end
    return n
end

function Registry:names()
    local list = {}
    for name in pairs(self._by_name) do list[#list + 1] = name end
    table.sort(list)
    return list
end

-- Test:
local reg = Registry.new()

local s1 = {sig = "session-1"}
local s2 = {sig = "session-2"}
local s3 = {sig = "session-3"}

reg:register("user-1", s1)
reg:register("user-2", s2)
reg:register("user-3", s3)

print(reg:count())                -- 3
print(reg:get("user-1").sig)      -- "session-1"

-- Usuwamy referencje:
s1, s2 = nil, nil
collectgarbage()

print(reg:count())                -- 1 (s1, s2 GC'd, znikły z rejestru)
print(reg:get("user-1"))          -- nil (s1 zniknął)
print(reg:get("user-3").sig)      -- "session-3" (s3 wciąż żyje)

-- Lista pozostałych:
for _, name in ipairs(reg:names()) do
    print(name)
end
-- user-3
```

Rejestr "best effort" — gdy obiekt umiera w innym miejscu, wpis automatycznie znika. Idealne dla:
- Active sessions registry (auto-expire gdy sesja zamknięta).
- Plugin registry (gdy plugin wyładowany — znika z rejestru).
- Connection pool (martwe połączenia samoczynnie się usuwają).

W KarmazynOS to jest **dokładnie** wzorzec, którego potrzebujesz dla mapowania `sig → session` — bo gdy sesja zostaje zamknięta i żaden hook jej nie trzyma, znika z rejestru bez ręcznego cleanup-u.

### Sprawdź się

- [ ] Wiem, co to weak reference i `__mode = "v"`/`"k"`/`"kv"`
- [ ] Umiem napisać LRU-lite cache na słabych wartościach
- [ ] Wiem, że primitives (number, string) nie są GC-able w słabych tabelach
- [ ] Pamiętam pułapkę `__gc` na tabeli (musi być ustawione razem z setmetatable)
- [ ] Umiem napisać Resource z auto-close przez `__gc`
- [ ] Znam `collectgarbage("count")` do pomiaru pamięci

---

## Sprawdzian Modułu 4

Osiem zadań — bo metatable to obszerny temat, a chcę pokryć każdy aspekt. To jest najdłuższy sprawdzian części I kursu, ale po jego rozwiązaniu masz absolutne ugruntowanie OOP-a w Lua.

### Zadania

**Sprawdzian 1** — `Vector` z pełną arytmetyką  
Napisz klasę `Vector` (n-wymiarową) z:
- konstruktorem `Vector(x1, x2, ..., xn)` (przez `__call`)
- `__add`, `__sub`, `__mul` (skalar lub dot product), `__unm`
- `__eq`, `__tostring`
- `:length()`, `:normalize()`, `:dim()`
- statyczne `Vector.zero(n)`, `Vector.dot(a, b)`

```lua
local v1 = Vector(1, 2, 3)
local v2 = Vector(4, 5, 6)
print(v1 + v2)       -- (5, 7, 9)
print(v1 * v2)       -- 32  (dot product)
print(v1 * 2)        -- (2, 4, 6)
print(v1:length())   -- ~3.7416
print(v1 == Vector(1, 2, 3))    -- true
print(Vector.zero(4))    -- (0, 0, 0, 0)
```

**Sprawdzian 2** — Pełen `defaultdict`  
Klasa `DefaultDict.new(factory)`. Powinna:
- `:get(k)` — zwraca lub tworzy
- `:set(k, v)` — zwykły zapis
- `:keys()`, `:values()`, `:pairs()` — iteratory
- działać z `pairs(d)` — `__pairs`
- `__index` zwraca i tworzy
- `__newindex` przepuszcza
- `__tostring`

```lua
local d = DefaultDict.new(function() return {} end)
table.insert(d.infra, "Anna")
table.insert(d.infra, "Ola")
table.insert(d.research, "Jan")
for k, v in pairs(d) do
    print(k, table.concat(v, ", "))
end
```

**Sprawdzian 3** — `Observable` z metatable  
Przepisz `Observable` z M3 (Lekcja 3.3.3) jako pełną klasę z metatable. Method chaining: `obs:on(event, fn):on(event2, fn2)`.

Plus — `on(event, fn)` z events string-owymi: `obs:on("change", fn)`. Wiele callbacków dla jednego eventu.

**Sprawdzian 4** — Immutable Record  
`Record.new(fields)` — tworzy "rekord" z polami fields, immutable. Operacje "modyfikujące" zwracają **nowy** rekord. `__eq` po wartości pól. `__tostring` tabelarycznie.

```lua
local p1 = Record.new({x = 1, y = 2, name = "a"})
local p2 = p1:with({y = 99})
print(p1.y, p2.y)     -- 2   99
print(p1 == Record.new({x = 1, y = 2, name = "a"}))    -- true
local ok = pcall(function() p1.x = 5 end)
print(ok)              -- false
```

**Sprawdzian 5** — Mixin: Comparable + Hashable  
Napisz mixin `Comparable` dodający `:lt(other)` (rzuca abstract — implementacja w klasie) i automatycznie wywodzące `__lt`, `__le`, `__eq`, `:gt()`, `:ge()`, `:eq()`. Plus mixin `Hashable` z `:hash()` (abstrakcyjny). Następnie klasa `Atom` używająca obu (porządkowanie po phi, hash po sig).

**Sprawdzian 6** — `LazyList` (lazy infinite list)  
Klasa `LazyList` reprezentująca **leniwie obliczaną** listę. Konstruktor: `LazyList.from(generator_fn)` — gdzie `generator_fn(n)` daje n-ty element. Lista jest "nieskończona". Metody:
- `:get(i)` — i-ty element (cachowany!)
- `:take(n)` — zwraca tabelę pierwszych n
- `:map(fn)` — zwraca nowy LazyList
- `:filter(predicate)` — zwraca nowy LazyList (uwaga: filter może wymagać generowania więcej elementów żeby znaleźć N pasujących)

```lua
local nats = LazyList.from(function(i) return i end)
print(nats:get(5))    -- 5
print(nats:get(1000000))    -- 1000000  (działa, leniwie)

local squares = nats:map(function(x) return x * x end)
local p = squares:take(5)
-- p = {1, 4, 9, 16, 25}

local odd_squares = nats:filter(function(x) return x % 2 == 1 end):map(function(x) return x * x end)
print(odd_squares:get(3))    -- 25  (1, 3, 5 -> 1, 9, 25)
```

**Sprawdzian 7** — Registry z observers  
Połącz Registry z M4.6.5 i Observable z Sprawdzianu 3. `SessionRegistry`:
- `:register(sig, session)`, `:unregister(sig)`, `:get(sig)`
- weak storage — sesje GC-d znikają samoczynnie
- emituje eventy `"register"`, `"unregister"`, `"vanish"` (gdy sesja zniknęła przez GC)
- `:on(event, fn)` jak w Observable

(Hint dla "vanish": nie sposób tego doskonale wykryć w Lua bez okresowego skanu. Alternatywa: `:gc_check()` metoda którą wywołuje hook periodyczny.)

**Sprawdzian 8** — Hierarchia DSL  
Klasa `Policy` (DSL polityki HSS):
- pola: `name`, `description`, `quotas` (tabela), `capabilities` (set), `hooks` (tabela funkcji)
- metody: `:set_quota(name, value)`, `:add_capability(cap)`, `:on(hook_name, fn)`
- klasa pochodna `StrictPolicy(name)` z domyślnymi quota = `{cpu_ms = 100, mem_kb = 1024}` i pustymi capabilities (wszystko trzeba jawnie dodać)
- `:check_capability(cap)`, `:get_quota(name)`
- `__tostring` wypisuje policy w czytelnym formacie

```lua
local default = Policy.new("default")
default:set_quota("cpu_ms", 500)
default:add_capability("phi.read")

local strict = StrictPolicy.new("admin-strict")
strict:add_capability("phi.read")
print(strict:get_quota("cpu_ms"))    -- 100  (z bazy StrictPolicy)
print(strict:check_capability("phi.read"))    -- true
print(strict:check_capability("phi.write"))   -- false
print(strict)
```

---

### Rozwiązania sprawdzianu

#### Sprawdzian 1

```lua
-- vector.lua
local Vector = {}
Vector.__index = Vector

local function check_same_dim(a, b)
    if #a ~= #b then
        error("vectors of different dimensions: " .. #a .. " vs " .. #b, 3)
    end
end

function Vector:dim()
    return #self
end

function Vector:length()
    local sum = 0
    for i = 1, #self do
        sum = sum + self[i] * self[i]
    end
    return math.sqrt(sum)
end

function Vector:normalize()
    local len = self:length()
    if len == 0 then error("cannot normalize zero vector", 2) end
    local result = {}
    for i = 1, #self do
        result[i] = self[i] / len
    end
    return Vector(table.unpack(result))   -- (! poniżej __call dla konstruktora)
end

function Vector.__add(a, b)
    check_same_dim(a, b)
    local result = {}
    for i = 1, #a do result[i] = a[i] + b[i] end
    return Vector(table.unpack(result))
end

function Vector.__sub(a, b)
    check_same_dim(a, b)
    local result = {}
    for i = 1, #a do result[i] = a[i] - b[i] end
    return Vector(table.unpack(result))
end

function Vector.__unm(a)
    local result = {}
    for i = 1, #a do result[i] = -a[i] end
    return Vector(table.unpack(result))
end

function Vector.__mul(a, b)
    if type(a) == "number" then
        local result = {}
        for i = 1, #b do result[i] = b[i] * a end
        return Vector(table.unpack(result))
    end
    if type(b) == "number" then
        local result = {}
        for i = 1, #a do result[i] = a[i] * b end
        return Vector(table.unpack(result))
    end
    -- vec * vec = dot product
    return Vector.dot(a, b)
end

function Vector.__eq(a, b)
    if #a ~= #b then return false end
    for i = 1, #a do
        if a[i] ~= b[i] then return false end
    end
    return true
end

function Vector.__tostring(v)
    local parts = {}
    for i = 1, #v do parts[i] = tostring(v[i]) end
    return "(" .. table.concat(parts, ", ") .. ")"
end

function Vector.dot(a, b)
    check_same_dim(a, b)
    local sum = 0
    for i = 1, #a do sum = sum + a[i] * b[i] end
    return sum
end

function Vector.zero(n)
    local result = {}
    for i = 1, n do result[i] = 0 end
    return Vector(table.unpack(result))
end

-- __call dla konstruktora:
setmetatable(Vector, {
    __call = function(_, ...)
        local self = setmetatable({...}, Vector)
        return self
    end
})

-- Test:
local v1 = Vector(1, 2, 3)
local v2 = Vector(4, 5, 6)

print(v1)             -- (1, 2, 3)
print(v1 + v2)        -- (5, 7, 9)
print(v2 - v1)        -- (3, 3, 3)
print(-v1)            -- (-1, -2, -3)
print(v1 * 2)         -- (2, 4, 6)
print(3 * v1)         -- (3, 6, 9)
print(v1 * v2)        -- 32   (dot)
print(Vector.dot(v1, v2))   -- 32
print(string.format("%.4f", v1:length()))   -- 3.7417
print(v1:dim())       -- 3

print(v1 == Vector(1, 2, 3))    -- true
print(v1 == v2)                  -- false

print(Vector.zero(4))    -- (0, 0, 0, 0)

print(v1:normalize())    -- (0.2673..., 0.5345..., 0.8018...)
```

Robocie się postarał. Zarówno arytmetyka, jak i statyczne metody, wspólny `__call` dla konstruktora. `check_same_dim` jako lokalna helper z `error(level=3)` żeby błąd wskazywał na faktyczne `v1 + v2` w kodzie klienta.

#### Sprawdzian 2

```lua
-- defaultdict.lua
local DefaultDict = {}
DefaultDict.__index = function(t, k)
    -- Najpierw sprawdź czy to metoda klasy (a nie wartość-klucz):
    local class_method = rawget(DefaultDict, k)
    if class_method then return class_method end
    
    -- Sprawdź dane:
    local raw = rawget(t, "_data")
    if raw == nil then return nil end
    if raw[k] == nil then
        raw[k] = t._factory()
    end
    return raw[k]
end

DefaultDict.__newindex = function(t, k, v)
    rawget(t, "_data")[k] = v
end

DefaultDict.__pairs = function(t)
    return pairs(rawget(t, "_data"))
end

DefaultDict.__tostring = function(t)
    local parts = {}
    for k, v in pairs(rawget(t, "_data")) do
        parts[#parts + 1] = tostring(k) .. "=" .. tostring(v)
    end
    return "DefaultDict{" .. table.concat(parts, ", ") .. "}"
end

function DefaultDict.new(factory)
    return setmetatable({
        _factory = factory,
        _data = {},
    }, DefaultDict)
end

function DefaultDict:get(k)
    return self[k]
end

function DefaultDict:set(k, v)
    self[k] = v
end

function DefaultDict:keys()
    local list = {}
    for k in pairs(self._data) do list[#list + 1] = k end
    return list
end

function DefaultDict:values()
    local list = {}
    for _, v in pairs(self._data) do list[#list + 1] = v end
    return list
end

-- Test:
local d = DefaultDict.new(function() return {} end)
table.insert(d.infra, "Anna")
table.insert(d.infra, "Ola")
table.insert(d.research, "Jan")

for k, v in pairs(d) do
    print(k, table.concat(v, ", "))
end
-- infra      Anna, Ola
-- research   Jan

-- Pivot:
local counters = DefaultDict.new(function() return 0 end)
counters.x = counters.x + 1
counters.x = counters.x + 1
counters.y = counters.y + 1
print(counters.x, counters.y)   -- 2   1
```

**Trudność:** `__index` musi rozróżnić "lookup metody klasy" od "lookup danych". Stąd `rawget(DefaultDict, k)` najpierw — gdy klucz to metoda (`get`, `set`, `keys`...) zwracamy ją; inaczej traktujemy jako klucz danych.

To jest typowy konflikt "metody na obiekcie vs. dane". W idiomatycznym Lua często używamy `:get()`/`:set()` zamiast `t.x`/`t.x = v` żeby uniknąć tego problemu. Tutaj zrobiłem oba dla showcase.

#### Sprawdzian 3

```lua
-- observable_class.lua
local Observable = {}
Observable.__index = Observable

function Observable.new(initial)
    return setmetatable({
        _value = initial,
        _listeners = {},   -- {event_name = {fn1, fn2, ...}}
    }, Observable)
end

function Observable:get()
    return self._value
end

function Observable:set(new_value)
    local old_value = self._value
    self._value = new_value
    self:emit("change", new_value, old_value)
end

function Observable:on(event, fn)
    if self._listeners[event] == nil then
        self._listeners[event] = {}
    end
    self._listeners[event][#self._listeners[event] + 1] = fn
    return self    -- chaining
end

function Observable:off(event, fn)
    local list = self._listeners[event]
    if not list then return self end
    for i, f in ipairs(list) do
        if f == fn then
            table.remove(list, i)
            break
        end
    end
    return self
end

function Observable:emit(event, ...)
    local list = self._listeners[event]
    if not list then return end
    for _, fn in ipairs(list) do
        fn(...)
    end
end

function Observable:__tostring()
    return string.format("Observable<%s>", tostring(self._value))
end

-- Test:
local phi = Observable.new(0.5)

phi:on("change", function(new, old)
    print("Change observer 1:", old, "->", new)
end):on("change", function(new, old)
    if new > 0.8 then print("HIGH PHI ALARM:", new) end
end):on("custom", function(...)
    print("Custom:", ...)
end)

phi:set(0.7)
-- Change observer 1: 0.5  ->  0.7

phi:set(0.9)
-- Change observer 1: 0.7  ->  0.9
-- HIGH PHI ALARM: 0.9

phi:emit("custom", "arg1", "arg2")
-- Custom:  arg1   arg2

print(phi)   -- Observable<0.9>
```

Method chaining przez `return self`. Każdy event może mieć wiele listenerów. `emit` wywołuje każdego z varargs. To prawdziwy event emitter w 50 liniach.

#### Sprawdzian 4

```lua
-- record.lua
local Record = {}
Record.__index = Record

function Record.new(fields)
    -- Walidacja
    if type(fields) ~= "table" then
        error("Record.new requires table", 2)
    end
    
    -- Stworzenie immutable kopii
    local data = {}
    for k, v in pairs(fields) do data[k] = v end
    
    return setmetatable({_data = data}, Record)
end

Record.__index = function(t, k)
    -- Najpierw sprawdź metody:
    local m = rawget(Record, k)
    if m then return m end
    -- Potem dane:
    return rawget(t, "_data")[k]
end

Record.__newindex = function()
    error("Record is immutable", 2)
end

Record.__eq = function(a, b)
    local ad, bd = a._data, b._data
    -- Zlicz klucze:
    local na, nb = 0, 0
    for k, v in pairs(ad) do
        if bd[k] ~= v then return false end
        na = na + 1
    end
    for _ in pairs(bd) do nb = nb + 1 end
    return na == nb
end

Record.__tostring = function(t)
    local data = t._data
    local keys = {}
    for k in pairs(data) do keys[#keys + 1] = tostring(k) end
    table.sort(keys)
    local parts = {}
    for _, k in ipairs(keys) do
        parts[#parts + 1] = k .. "=" .. tostring(data[k])
    end
    return "Record{" .. table.concat(parts, ", ") .. "}"
end

function Record:with(updates)
    local new_data = {}
    for k, v in pairs(self._data) do new_data[k] = v end
    for k, v in pairs(updates) do new_data[k] = v end
    return Record.new(new_data)
end

function Record:to_table()
    local copy = {}
    for k, v in pairs(self._data) do copy[k] = v end
    return copy
end

-- Test:
local p1 = Record.new({x = 1, y = 2, name = "a"})
print(p1)             -- Record{name=a, x=1, y=2}
print(p1.x)           -- 1
print(p1.name)        -- "a"

local p2 = p1:with({y = 99, z = 100})
print(p1.y, p2.y, p2.z)    -- 2   99   100  (! p1 nietknięte)
print(p1)             -- Record{name=a, x=1, y=2}    (oryginalny)
print(p2)             -- Record{name=a, x=1, y=99, z=100}

print(p1 == Record.new({x = 1, y = 2, name = "a"}))    -- true
print(p1 == Record.new({x = 1, y = 2, name = "b"}))    -- false
print(p1 == p2)       -- false

local ok, err = pcall(function() p1.x = 5 end)
print(ok, err)
-- false   "...Record is immutable"
```

`:with(updates)` to wzorzec **immutable update** z funkcyjnych języków (Haskell `record { field = value }`). Zamiast modyfikować istniejący — tworzy nowy z nadpisaniami. Bezpieczne, łatwe do debugowania, nadaje się do undo/redo.

#### Sprawdzian 5

```lua
-- mixins.lua

-- Comparable mixin
local Comparable = {}

function Comparable:lt(other)
    error("abstract method: implement :lt(other)", 2)
end

function Comparable:le(other)
    return not other:lt(self)
end

function Comparable:eq(other)
    return not self:lt(other) and not other:lt(self)
end

function Comparable:gt(other)
    return other:lt(self)
end

function Comparable:ge(other)
    return not self:lt(other)
end

-- Hashable mixin
local Hashable = {}

function Hashable:hash()
    error("abstract method: implement :hash()", 2)
end

-- Helper do wprowadzania mixinów
local function add_mixin(class, mixin)
    for k, v in pairs(mixin) do
        if class[k] == nil then    -- nie nadpisuj jeśli już zdefiniowane
            class[k] = v
        end
    end
end

local function setup_comparable_meta(class)
    class.__lt = function(a, b) return a:lt(b) end
    class.__le = function(a, b) return a:le(b) end
    class.__eq = function(a, b) return a:eq(b) end
end

-- Klasa Atom używająca obu mixinów
local Atom = {}
Atom.__index = Atom

function Atom.new(sig, phi)
    return setmetatable({sig = sig, phi = phi}, Atom)
end

-- Implementacja abstrakcyjnych
function Atom:lt(other) return self.phi < other.phi end
function Atom:hash() return self.sig end

function Atom:__tostring()
    return string.format("Atom<%s, phi=%.3f>", self.sig, self.phi)
end

add_mixin(Atom, Comparable)
add_mixin(Atom, Hashable)
setup_comparable_meta(Atom)

-- Test:
local a = Atom.new("a", 0.5)
local b = Atom.new("b", 0.7)
local c = Atom.new("c", 0.5)

print(a:lt(b))    -- true   (a.phi < b.phi)
print(a:gt(b))    -- false
print(a:eq(b))    -- false
print(a:eq(c))    -- true   (oba phi=0.5)
print(a:le(c))    -- true
print(a:ge(c))    -- true

print(a < b)      -- true   (operator)
print(a == c)     -- true
print(b > a)      -- true

print(a:hash())   -- "a"
print(b:hash())   -- "b"

-- Sortowanie przez Comparable:
local atoms = {b, c, a, Atom.new("d", 0.9)}
table.sort(atoms, function(x, y) return x:lt(y) end)
for _, atom in ipairs(atoms) do print(atom) end
-- Atom<a, phi=0.500>
-- Atom<c, phi=0.500>
-- Atom<b, phi=0.700>
-- Atom<d, phi=0.900>
```

Pattern: **mixin definiuje funkcje pochodne** (jak `:le()`, `:gt()`) zakładając abstrakcyjną metodę (`:lt()`). Klasa konkretna implementuje `:lt()`. Dostaje resztę za darmo. Plus `setup_comparable_meta` tworzy operatory `<`, `<=`, `==`.

W praktyce mixiny + abstract methods + helpers są **dokładnie** tym, czego brakuje "czystemu" Lua i czemu warto je sobie napisać raz w ekosystemie projektu.

#### Sprawdzian 6

```lua
-- lazy_list.lua
local LazyList = {}
LazyList.__index = LazyList

function LazyList.new(generator)
    return setmetatable({
        _gen = generator,
        _cache = {},
    }, LazyList)
end

function LazyList.from(generator)
    return LazyList.new(generator)
end

function LazyList:get(i)
    if self._cache[i] ~= nil then return self._cache[i] end
    local v = self._gen(i)
    self._cache[i] = v
    return v
end

function LazyList:take(n)
    local result = {}
    for i = 1, n do
        result[i] = self:get(i)
    end
    return result
end

function LazyList:map(fn)
    local self_ref = self
    return LazyList.new(function(i)
        return fn(self_ref:get(i))
    end)
end

function LazyList:filter(predicate)
    -- Filter wymaga generowania *aż znajdziemy* n-ty element pasujący
    local self_ref = self
    -- Filter cache: mapuje "indeks po filtrze" -> "indeks oryginalny"
    local index_cache = {}
    
    return LazyList.new(function(i)
        if index_cache[i] then
            return self_ref:get(index_cache[i])
        end
        -- Idź dalej, znajdując pasujące
        local source_idx = index_cache[i - 1] or 0
        local found = i - 1   -- ile już znaleźliśmy
        while found < i do
            source_idx = source_idx + 1
            local v = self_ref:get(source_idx)
            if predicate(v) then
                found = found + 1
                index_cache[found] = source_idx
            end
        end
        return self_ref:get(index_cache[i])
    end)
end

-- Test:
local nats = LazyList.from(function(i) return i end)
print(nats:get(5))         -- 5
print(nats:get(1000000))   -- 1000000  (działa!)

local squares = nats:map(function(x) return x * x end)
local p = squares:take(5)
for _, v in ipairs(p) do io.write(v, " ") end
print()
-- 1 4 9 16 25

local odd_squares = nats:filter(function(x) return x % 2 == 1 end)
                        :map(function(x) return x * x end)
print(odd_squares:get(1))    -- 1   (1^2)
print(odd_squares:get(2))    -- 9   (3^2)
print(odd_squares:get(3))    -- 25  (5^2)
print(odd_squares:take(5))   -- ... (table)
local r = odd_squares:take(5)
for _, v in ipairs(r) do io.write(v, " ") end
print()
-- 1 9 25 49 81

-- Fibonacci jako lazy:
local function fib(i)
    if i <= 2 then return 1 end
    return fib(i-1) + fib(i-2)   -- bez memo to byłby exponential time
end
-- ALE przez LazyList cache, drugie wywołanie fib jest O(1)

local fibs = LazyList.from(fib)
print(fibs:get(10))    -- 55
print(fibs:get(15))    -- 610
```

`filter` jest najtrudniejszy — bo "i-ty element po filtrze" to "i-ty element oryginału który pasuje", co wymaga skanowania od początku (lub cache'owania mapy filtered_idx → original_idx).

Wersja `LazyList` w Module 6 (korutyny) będzie **znacznie** ładniejsza — bo korutyna to naturalny generator z `yield`.

#### Sprawdzian 7

```lua
-- session_registry.lua
-- (Łączy Sprawdzian 3 i M4.6.5)

local SessionRegistry = {}
SessionRegistry.__index = SessionRegistry

function SessionRegistry.new()
    return setmetatable({
        _by_sig = setmetatable({}, {__mode = "v"}),   -- weak values
        _last_seen = {},                                -- silne, dla tracking
        _listeners = {},
    }, SessionRegistry)
end

function SessionRegistry:on(event, fn)
    if not self._listeners[event] then
        self._listeners[event] = {}
    end
    table.insert(self._listeners[event], fn)
    return self
end

function SessionRegistry:emit(event, ...)
    local list = self._listeners[event]
    if not list then return end
    for _, fn in ipairs(list) do fn(...) end
end

function SessionRegistry:register(sig, session)
    self._by_sig[sig] = session
    self._last_seen[sig] = true
    self:emit("register", sig, session)
end

function SessionRegistry:unregister(sig)
    local session = self._by_sig[sig]
    self._by_sig[sig] = nil
    self._last_seen[sig] = nil
    self:emit("unregister", sig, session)
end

function SessionRegistry:get(sig)
    return self._by_sig[sig]
end

-- Periodic sweep — wywołać manualnie (np. z timera w hosting'u)
function SessionRegistry:gc_check()
    collectgarbage()    -- wymuś
    for sig in pairs(self._last_seen) do
        if self._by_sig[sig] == nil then
            -- Sesja zniknęła przez GC
            self._last_seen[sig] = nil
            self:emit("vanish", sig)
        end
    end
end

-- Test:
local reg = SessionRegistry.new()

reg:on("register", function(sig, sess)
    print("REGISTER:", sig)
end):on("unregister", function(sig)
    print("UNREGISTER:", sig)
end):on("vanish", function(sig)
    print("VANISH:", sig)
end)

local s1 = {sig = "user-1", phi = 0.7}
local s2 = {sig = "user-2", phi = 0.4}
local s3 = {sig = "user-3", phi = 0.9}

reg:register("user-1", s1)
reg:register("user-2", s2)
reg:register("user-3", s3)
-- REGISTER: user-1
-- REGISTER: user-2
-- REGISTER: user-3

reg:unregister("user-2")
-- UNREGISTER: user-2

print(reg:get("user-1").phi)    -- 0.7
print(reg:get("user-2"))        -- nil

s1, s3 = nil, nil
reg:gc_check()
-- VANISH: user-1
-- VANISH: user-3
```

`gc_check` to "manualne sprawdzenie weak references które wypadły". W KarmazynOS taką metodę można podpiąć do timer'a hosta (np. co sekundę).

Alternatywą byłoby `__gc` na sesjach z reverse-pointer do registry, ale to skomplikowane.

#### Sprawdzian 8

```lua
-- policy_dsl.lua

-- Bazowa Policy
local Policy = {}
Policy.__index = Policy

function Policy.new(name)
    return setmetatable({
        name = name,
        description = "",
        quotas = {},
        capabilities = {},   -- set: {cap = true}
        hooks = {},
    }, Policy)
end

function Policy:set_quota(name, value)
    self.quotas[name] = value
    return self
end

function Policy:get_quota(name)
    return self.quotas[name]
end

function Policy:add_capability(cap)
    self.capabilities[cap] = true
    return self
end

function Policy:check_capability(cap)
    return self.capabilities[cap] == true
end

function Policy:on(hook_name, fn)
    self.hooks[hook_name] = fn
    return self
end

function Policy:set_description(desc)
    self.description = desc
    return self
end

function Policy:__tostring()
    local lines = {"Policy: " .. self.name}
    if self.description ~= "" then
        lines[#lines + 1] = "  description: " .. self.description
    end
    
    -- Quotas
    local q_keys = {}
    for k in pairs(self.quotas) do q_keys[#q_keys + 1] = k end
    table.sort(q_keys)
    if #q_keys > 0 then
        lines[#lines + 1] = "  quotas:"
        for _, k in ipairs(q_keys) do
            lines[#lines + 1] = "    " .. k .. " = " .. tostring(self.quotas[k])
        end
    end
    
    -- Capabilities
    local c_keys = {}
    for k in pairs(self.capabilities) do c_keys[#c_keys + 1] = k end
    table.sort(c_keys)
    if #c_keys > 0 then
        lines[#lines + 1] = "  capabilities: " .. table.concat(c_keys, ", ")
    end
    
    -- Hooks
    local h_keys = {}
    for k in pairs(self.hooks) do h_keys[#h_keys + 1] = k end
    table.sort(h_keys)
    if #h_keys > 0 then
        lines[#lines + 1] = "  hooks: " .. table.concat(h_keys, ", ")
    end
    
    return table.concat(lines, "\n")
end

-- StrictPolicy
local StrictPolicy = setmetatable({}, {__index = Policy})
StrictPolicy.__index = StrictPolicy

function StrictPolicy.new(name)
    local self = Policy.new(name)
    -- Domyślne strict quotas:
    self.quotas.cpu_ms = 100
    self.quotas.mem_kb = 1024
    self.quotas.atoms_max = 100
    -- Capabilities domyślnie puste — wszystko trzeba dodać jawnie
    return setmetatable(self, StrictPolicy)
end

function StrictPolicy:__tostring()
    local base = Policy.__tostring(self)
    return base .. "\n  [STRICT]"
end

-- Test:
print("--- Default policy ---")
local default = Policy.new("default")
default:set_description("Domyślna polityka sesji")
default:set_quota("cpu_ms", 500)
default:set_quota("mem_kb", 4096)
default:add_capability("phi.read")
default:add_capability("phi.write")
default:on("on_atom_create", function(atom)
    print("created atom:", atom.sig)
end)
print(default)
print()

print("--- Strict policy ---")
local strict = StrictPolicy.new("admin-strict")
strict:set_description("Strict admin policy")
strict:add_capability("phi.read")    -- musi być dodane jawnie
print(strict:get_quota("cpu_ms"))    -- 100  (z bazy StrictPolicy)
print(strict:get_quota("mem_kb"))    -- 1024
print(strict:check_capability("phi.read"))    -- true
print(strict:check_capability("phi.write"))   -- false
print(strict)
```

```
--- Default policy ---
Policy: default
  description: Domyślna polityka sesji
  quotas:
    cpu_ms = 500
    mem_kb = 4096
  capabilities: phi.read, phi.write
  hooks: on_atom_create

--- Strict policy ---
100
1024
true
false
Policy: admin-strict
  description: Strict admin policy
  quotas:
    atoms_max = 100
    cpu_ms = 100
    mem_kb = 1024
  capabilities: phi.read
  [STRICT]
```

To jest realny szkielet DSL polityki HSS. Method chaining (`:set_quota():add_capability():on()`) sprawia, że jeden blok kodu konfiguruje całą polityke. W Module 11 (DSL dla KarmazynOS) rozwiniemy to do pełnej składni typu `policy "name" { ... }`.

---

## Co dalej?

Wielki rozdział zakończony. Po tym module masz w głowie wszystko, co potrzebne do pisania zaawansowanego OOP-a w Lua: klasy, dziedziczenie, operatory, weak tables, immutable patterns, mixins.

Kolejne moduły są mniejsze — każdy domyka jeden temat.

→ **Moduł 5: Obsługa błędów** — `pcall`, `xpcall`, `error`, wzorce defensive, debug traceback.
