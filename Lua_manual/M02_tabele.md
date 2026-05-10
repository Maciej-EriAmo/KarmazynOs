# Moduł 2: Tabele

> *"Lua nie ma struktur danych. Lua ma jedną strukturę danych. To wystarcza."*

W Lua **tabela** to jedyna złożona struktura danych. Jest jednocześnie tablicą, słownikiem, rekordem, namespace'em, klasą, kolejką i grafem. Po tym module tabele będą dla Ciebie tak naturalne jak listy w Pythonie czy obiekty w JavaScript.

**Przewidywany czas:** 5-7 godzin pracy.

**Lekcje:**
1. Tabele jako tablice (sekwencje)
2. Tabele jako rekordy
3. Tabele mieszane i zagnieżdżone — referencje
4. Iteracja i biblioteka `table.*`
5. Wzorce: set, stack, queue, multiset, namespace

Plus **Sprawdzian Modułu 2** — 7 zadań integrujących całość, wśród nich path resolver i operacje na zbiorach.

---

## Lekcja 2.1: Tabele jako tablice

### Cel

Tworzysz tabele indeksowane liczbowo, dodajesz/usuwasz elementy, iterujesz po nich, znasz pułapki "sekwencji" w Lua.

### Materiał

#### Tworzenie

```lua
local pusta = {}
local liczby = {10, 20, 30}             -- klucze 1, 2, 3
local mieszanka = {true, "abc", 3.14}   -- różne typy są OK
```

Konstruktor `{...}` tworzy tabelę. Kolejne wartości dostają klucze 1, 2, 3, ... Pierwszy element ma indeks **1**, nie 0. To jest pierwsza rzecz, którą trzeba sobie wbić.

#### Dostęp i modyfikacja

```lua
local t = {10, 20, 30}

print(t[1])    -- 10
print(t[2])    -- 20
print(t[0])    -- nil   (! nie istnieje)
print(t[4])    -- nil   (! też nie)

t[1] = 99
print(t[1])    -- 99

t[4] = 40      -- rozszerzenie tabeli
print(t[4])    -- 40
```

#### Operator `#` — długość

Dla "poprawnej sekwencji" — `#t` zwraca liczbę elementów:

```lua
local t = {10, 20, 30}
print(#t)    -- 3
```

**Pułapka:** `#t` jest niezdefiniowane dla tabel z **dziurami** (nilami w środku):

```lua
local t = {1, 2, nil, 4}
print(#t)    -- może być 2 albo 4 — undefined!
```

Reguła zdrowego rozsądku: **nie wkładaj `nil` do tablic**. Jeśli musisz reprezentować "puste miejsce", użyj sentinela (np. `false` lub specjalnego stringa) albo trzymaj długość w osobnym polu.

#### Dodawanie elementów

```lua
local t = {}

-- Najczystszy idiom dopisywania:
t[#t + 1] = "pierwszy"
t[#t + 1] = "drugi"
t[#t + 1] = "trzeci"

-- Lub funkcja standardowa:
table.insert(t, "czwarty")           -- na koniec
table.insert(t, 1, "ZERO")           -- na pozycję 1, reszta przesuwa się w prawo

print(t[1], t[2], t[5])  -- "ZERO"  "pierwszy"  "czwarty"
```

**Wydajność:**
- `t[#t + 1] = v` — O(1)
- `table.insert(t, v)` (na koniec) — O(1)
- `table.insert(t, 1, v)` (z przesunięciem) — O(n)

Dla wstawiania na koniec preferuj `t[#t+1] = v` lub `table.insert(t, v)` — kwestia stylu. Dla wstawiania w środku — pamiętaj o koszcie.

#### Usuwanie elementów

```lua
local t = {"a", "b", "c", "d"}

table.remove(t)        -- usuwa ostatni; zwraca usunięty: "d"
table.remove(t, 1)     -- usuwa pierwszy; przesuwa resztę: "a"

-- Po tych operacjach: t = {"b", "c"}

-- Można też ręcznie, ale uważaj:
t[#t] = nil            -- usuwa ostatni — OK
t[1] = nil             -- ! TWORZY DZIURĘ! sekwencja zepsuta
```

**Reguła:** nigdy nie ustawiaj na `nil` elementu z **środka** sekwencji, jeśli chcesz zachować ją jako sekwencję. Zamiast tego — `table.remove(t, i)`.

#### Iteracja: `ipairs`

```lua
local t = {"alfa", "beta", "gamma"}

for i, v in ipairs(t) do
    print(i, v)
end
-- 1   alfa
-- 2   beta
-- 3   gamma
```

`ipairs` iteruje od 1 dopóki nie napotka `nil`. Idealne dla sekwencji.

```lua
local t = {1, 2, nil, 4}
for i, v in ipairs(t) do print(i, v) end
-- 1   1
-- 2   2
-- (zatrzymuje się na nil; nigdy nie dochodzi do indeksu 4)
```

Iteracja "ręczna" przez indeksy:

```lua
for i = 1, #t do
    print(i, t[i])
end
```

To samo co `ipairs`, ale bardziej elastyczne (np. iteracja wsteczna, ze step).

### Pułapki

1. **Indeksowanie od 1.** `t[0]` to dziwne miejsce, nie pierwszy element.
2. **`#t` na tabeli z dziurami** — niezdefiniowane.
3. **Nie wkładaj nila do sekwencji.** Łamie `#`, `ipairs`, `table.concat`.
4. **`table.insert(t, 1, v)`** to O(n) — przesuwa wszystkie elementy.
5. **`t[1] = nil` ze środka** tworzy dziurę — używaj `table.remove`.

### Zadania

**Zadanie 2.1.1**  
Stwórz tabelę z liczbami 1 do 10. Wypisz ją od końca.

**Zadanie 2.1.2**  
Napisz funkcję `sum(t)` — suma wszystkich elementów tabeli liczbowej.

**Zadanie 2.1.3**  
Napisz funkcję `contains(t, v)` zwracającą `true`/`false` w zależności od tego, czy `v` jest w `t`. Działa dla dowolnego typu wartości.

**Zadanie 2.1.4**  
Napisz funkcję `max_index(t)` zwracającą indeks **pierwszego maksymalnego** elementu. Dla pustej tabeli — `nil`.  
Test: `max_index({3, 7, 2, 7, 1})` = 2 (pierwszy 7).

**Zadanie 2.1.5**  
Napisz funkcję `remove_value(t, v)` usuwającą **wszystkie** wystąpienia wartości `v` z tabeli `t`, zachowując sekwencję (bez dziur). In-place. Zwraca liczbę usuniętych elementów.  
Test:
```lua
local t = {1, 2, 3, 2, 4, 2}
local n = remove_value(t, 2)
-- t == {1, 3, 4}, n == 3
```

---

### Rozwiązania

#### Rozwiązanie 2.1.1

```lua
-- backwards.lua
local t = {}
for i = 1, 10 do
    t[i] = i
end

-- Wersja 1: pętla wsteczna
for i = #t, 1, -1 do
    io.write(t[i], " ")
end
print()
-- 10 9 8 7 6 5 4 3 2 1
```

Pętla `for i = #t, 1, -1` — od końca, krok -1.

#### Rozwiązanie 2.1.2

```lua
-- sum.lua
local function sum(t)
    local s = 0
    for i = 1, #t do
        s = s + t[i]
    end
    return s
end

print(sum({1, 2, 3, 4, 5}))    -- 15
print(sum({}))                 -- 0
print(sum({-1, 1}))            -- 0
print(sum({0.5, 0.5, 0.5}))    -- 1.5
```

Wersja z `ipairs` jest też idiomatyczna:

```lua
local function sum(t)
    local s = 0
    for _, v in ipairs(t) do
        s = s + v
    end
    return s
end
```

`for i = 1, #t` jest minimalnie szybsza (jedno wywołanie `#` na początek), ale różnica jest mikroskopijna. Wybieraj `ipairs` dla czytelności.

#### Rozwiązanie 2.1.3

```lua
-- contains.lua
local function contains(t, v)
    for i = 1, #t do
        if t[i] == v then
            return true
        end
    end
    return false
end

print(contains({1, 2, 3}, 2))           -- true
print(contains({1, 2, 3}, 4))           -- false
print(contains({"a", "b"}, "b"))        -- true
print(contains({}, 1))                  -- false
print(contains({nil, 1}, 1))            -- false! (! ipairs/# zatrzymuje się na nil[1])
```

Ostatni przypadek pokazuje pułapkę: tabela `{nil, 1}` ma `#t == 0` (lub niezdefiniowane). Dlatego pętla nie iteruje. Jeśli musisz obsłużyć tabele z nilami — użyj `pairs` (Lekcja 2.2):

```lua
local function contains_safe(t, v)
    for _, x in pairs(t) do
        if x == v then return true end
    end
    return false
end
```

Ale wtedy kolejność iteracji jest niezdefiniowana.

#### Rozwiązanie 2.1.4

```lua
-- max_index.lua
local function max_index(t)
    if #t == 0 then return nil end
    local idx = 1
    for i = 2, #t do
        if t[i] > t[idx] then
            idx = i
        end
    end
    return idx
end

print(max_index({3, 7, 2, 7, 1}))    -- 2
print(max_index({5}))                -- 1
print(max_index({}))                 -- nil
print(max_index({-3, -1, -10}))      -- 2
```

Strzeżenie inicjacji: `idx = 1`, pętla od 2. Klasyczne. Używamy `>` (nie `>=`) żeby zwracać indeks **pierwszego** maksimum.

#### Rozwiązanie 2.1.5

```lua
-- remove_value.lua
local function remove_value(t, v)
    local write_idx = 1
    local removed = 0
    for read_idx = 1, #t do
        if t[read_idx] == v then
            removed = removed + 1
        else
            t[write_idx] = t[read_idx]
            write_idx = write_idx + 1
        end
    end
    -- Wyczyść końcówkę:
    for i = write_idx, #t do
        t[i] = nil
    end
    return removed
end

local t = {1, 2, 3, 2, 4, 2}
print(remove_value(t, 2))    -- 3

for i, v in ipairs(t) do
    io.write(v, " ")
end
print()
-- 1 3 4
```

Użyłem **two-pointer technique**: `read_idx` skanuje tabelę, `write_idx` wskazuje gdzie zapisać następny element nie-do-usunięcia. Po przejściu — czyścimy końcówkę.

To jest O(n). Naiwne podejście "dla każdego usuwanego elementu zrób `table.remove`" byłoby O(n²) bo każdy `table.remove(t, i)` przesuwa resztę.

### Sprawdź się

- [ ] Pamiętam, że indeksy zaczynają się od 1
- [ ] Wiem, czemu nie wkładać nila do sekwencji
- [ ] Umiem dodawać do końca przez `t[#t+1] = v` lub `table.insert`
- [ ] Wiem, że `table.insert(t, 1, v)` jest O(n)
- [ ] Umiem iterować przez `for i = 1, #t` i `ipairs`
- [ ] Znam two-pointer technique do filtrowania in-place

---

## Lekcja 2.2: Tabele jako rekordy

### Cel

Używasz tabel z dowolnymi kluczami (stringami, liczbami, innymi tabelami), znasz różnicę składni `t.x` vs `t["x"]`, iterujesz przez `pairs`.

### Materiał

#### Konstrukcja z nazwanymi polami

```lua
local atom = {phi = 0.7, sig = "abc123", alive = true}

print(atom.phi)        -- 0.7
print(atom.sig)        -- "abc123"
print(atom.alive)      -- true
```

`{phi = 0.7}` to skrót dla `{["phi"] = 0.7}` — klucze stringowe.

#### Składnia `t.x` vs `t["x"]`

Te dwie linie są **identyczne**:

```lua
atom.phi
atom["phi"]
```

Ale `.` działa **tylko dla identyfikatorów** (litery, cyfry, podkreślniki — nie zaczyna się od cyfry, nie jest słowem kluczowym).

```lua
local t = {}

t.x = 1                -- OK
t["x"] = 1             -- OK, to samo

t["1abc"] = 2          -- OK
t.1abc                 -- BŁĄD składni: nie zaczyna się od cyfry

t["with space"] = 3    -- OK
t.with space           -- BŁĄD składni

t["if"] = 4            -- OK
t.if                   -- BŁĄD: 'if' to słowo kluczowe!
```

Reguła: dla "ładnych" kluczy używaj `.`, dla wszystkich innych — `[]`.

#### Inne typy kluczy

Klucz może być **dowolnego typu** poza `nil` i `NaN`:

```lua
local t = {}

t[1] = "liczba całkowita jako klucz"
t[1.5] = "float jako klucz"
t["abc"] = "string"
t[true] = "boolean"
t[print] = "funkcja"

local key_table = {}
t[key_table] = "inna tabela jako klucz"
print(t[key_table])    -- "inna tabela jako klucz"
```

**Pułapka:** `t[1]` i `t[1.0]` to **ten sam klucz** (Lua normalizuje całkowite floaty do integerów). Ale `t[1]` i `t["1"]` to **różne klucze** (number vs string).

```lua
local t = {}
t[1] = "a"
t[1.0] = "b"
print(t[1])           -- "b"  (! nadpisane)
print(t[1.0])         -- "b"
print(t["1"])         -- nil (! inny klucz)
```

#### Konstruktor mieszany

```lua
local t = {
    "first",                    -- t[1] = "first"
    "second",                   -- t[2] = "second"
    name = "holon",             -- t.name = "holon"
    [42] = "answer",            -- t[42] = "answer"
    [true] = "yes",             -- t[true] = "yes"
}
```

Składnia `[expr] = value` pozwala na klucze obliczone (lub typu innego niż string-identyfikator).

#### Iteracja: `pairs`

```lua
local atom = {phi = 0.7, sig = "abc", alive = true}

for k, v in pairs(atom) do
    print(k, v)
end
-- phi    0.7
-- sig    abc
-- alive  true
-- (kolejność niezdefiniowana!)
```

`pairs` iteruje przez **wszystkie** klucze tabeli. Kolejność jest nieokreślona. Jeśli potrzebujesz konkretnej kolejności — sortuj klucze (Lekcja 2.4).

#### Usuwanie klucza

```lua
local t = {x = 1, y = 2, z = 3}

t.y = nil    -- usuwa klucz "y"

for k, v in pairs(t) do
    print(k, v)
end
-- x   1
-- z   3
```

Ustawienie wartości na `nil` usuwa klucz całkowicie. Po tym `t.y` zwróci `nil` jak każdy nieistniejący klucz.

#### Zliczanie kluczy w tabeli

`#t` **nie** liczy kluczy nie-numerycznych:

```lua
local t = {x = 1, y = 2, z = 3}
print(#t)    -- 0  (! żaden klucz nie jest sekwencyjny)
```

Aby policzyć wszystkie klucze:

```lua
local function count_keys(t)
    local n = 0
    for _ in pairs(t) do
        n = n + 1
    end
    return n
end

print(count_keys({x = 1, y = 2, z = 3}))    -- 3
print(count_keys({"a", "b", "c"}))           -- 3
print(count_keys({"a", x = 1}))              -- 2
```

### Pułapki

1. **`t.if` to błąd** — słowa kluczowe wymagają `t["if"]`.
2. **Klucze 1 i 1.0 to ten sam klucz** (Lua 5.3+).
3. **Klucze "1" i 1 to różne klucze** (string vs number).
4. **`pairs` nie gwarantuje kolejności.**
5. **`#t` nie zlicza kluczy hash** — używaj własnej `count_keys`.
6. **Modyfikacja tabeli podczas `pairs`** — można ustawiać istniejące klucze na nil, ale dodawanie nowych jest niezdefiniowane.

### Zadania

**Zadanie 2.2.1**  
Napisz funkcję `keys(t)` zwracającą tabelę-listę wszystkich kluczy `t` (w jakiejkolwiek kolejności).  
Test: dla `{a=1, b=2, c=3}` zwróci np. `{"b", "a", "c"}`.

**Zadanie 2.2.2**  
Napisz funkcję `values(t)` zwracającą tabelę-listę wszystkich wartości `t`.

**Zadanie 2.2.3**  
Napisz funkcję `char_count(s)`, która dla stringa `s` zwraca tabelę-rekord, gdzie kluczem jest znak, wartością — liczba wystąpień.  
Test: `char_count("hello")` = `{h=1, e=1, l=2, o=1}`.

**Zadanie 2.2.4**  
Napisz funkcję `invert(t)`, która zamienia klucze i wartości:  
`{a = "x", b = "y"}` → `{x = "a", y = "b"}`.  
Co się stanie, jeśli dwie wartości są takie same? Pomyśl i napisz wersję, która **wykrywa kolizję** i zwraca `nil, "kolizja: <wartość>"`.

**Zadanie 2.2.5**  
Napisz funkcję `merge(a, b)` zwracającą **nową** tabelę będącą połączeniem `a` i `b`. Jeśli klucz jest w obu — wartość z `b` ma priorytet.  
Test:
```lua
local x = {a = 1, b = 2, c = 3}
local y = {b = 99, d = 4}
local m = merge(x, y)
-- m == {a=1, b=99, c=3, d=4}
-- x i y pozostają bez zmian!
```

---

### Rozwiązania

#### Rozwiązanie 2.2.1

```lua
-- keys.lua
local function keys(t)
    local result = {}
    for k in pairs(t) do
        result[#result + 1] = k
    end
    return result
end

local k = keys({a = 1, b = 2, c = 3})
for _, v in ipairs(k) do
    io.write(v, " ")
end
print()
-- np. "b a c " — kolejność niezdefiniowana
```

`for k in pairs(t)` — bierzemy tylko klucze, ignorujemy wartości (nie potrzebujemy `_` dla drugiego).

#### Rozwiązanie 2.2.2

```lua
-- values.lua
local function values(t)
    local result = {}
    for _, v in pairs(t) do
        result[#result + 1] = v
    end
    return result
end

local v = values({a = 1, b = 2, c = 3})
for _, x in ipairs(v) do
    io.write(x, " ")
end
print()
-- np. "2 1 3 "
```

Symetryczne. `_` dla nieinteresującego klucza.

#### Rozwiązanie 2.2.3

```lua
-- char_count.lua
local function char_count(s)
    local result = {}
    for i = 1, #s do
        local c = s:sub(i, i)
        result[c] = (result[c] or 0) + 1
    end
    return result
end

local cc = char_count("hello world")
-- Wypiszmy uporządkowanie:
local keys_sorted = {}
for k in pairs(cc) do
    keys_sorted[#keys_sorted + 1] = k
end
table.sort(keys_sorted)

for _, k in ipairs(keys_sorted) do
    print("'" .. k .. "': " .. cc[k])
end
-- ' ': 1
-- 'd': 1
-- 'e': 1
-- 'h': 1
-- 'l': 3
-- 'o': 2
-- 'r': 1
-- 'w': 1
```

**Idiom:** `result[c] = (result[c] or 0) + 1` — jeśli `result[c]` jeszcze nie istnieje (jest `nil`), bierzemy 0. Następnie inkrementujemy. Jedna linia, bez `if`.

To jest **counter** / **multiset** idiom — pojawi się jeszcze wielokrotnie.

#### Rozwiązanie 2.2.4

```lua
-- invert.lua
local function invert(t)
    local result = {}
    for k, v in pairs(t) do
        if result[v] ~= nil then
            return nil, "kolizja: " .. tostring(v)
        end
        result[v] = k
    end
    return result
end

local r = invert({a = "x", b = "y", c = "z"})
for k, v in pairs(r) do
    print(k, v)
end
-- x   a
-- y   b
-- z   c

local r2, err = invert({a = "x", b = "x"})
print(r2, err)
-- nil   kolizja: x
```

**Wersja prostsza** (która ignoruje kolizje — drugi nadpisuje pierwszy):

```lua
local function invert_naive(t)
    local result = {}
    for k, v in pairs(t) do
        result[v] = k
    end
    return result
end
```

Ale wykrycie kolizji jest często ważne — bo "co znaczy odwrócić mapping `{a="x", b="x"}`" jest niejednoznaczne. Wersja z błędem jest bezpieczniejsza.

#### Rozwiązanie 2.2.5

```lua
-- merge.lua
local function merge(a, b)
    local result = {}
    for k, v in pairs(a) do
        result[k] = v
    end
    for k, v in pairs(b) do
        result[k] = v   -- nadpisuje jeśli istnieje w a
    end
    return result
end

local x = {a = 1, b = 2, c = 3}
local y = {b = 99, d = 4}
local m = merge(x, y)

local sorted_keys = {}
for k in pairs(m) do sorted_keys[#sorted_keys + 1] = k end
table.sort(sorted_keys)

for _, k in ipairs(sorted_keys) do
    print(k, m[k])
end
-- a   1
-- b   99
-- c   3
-- d   4

-- Sprawdzenie że oryginały nietknięte:
print("x.b =", x.b)    -- 2
print("y.a =", y.a)    -- nil
```

Strategia: kopiujemy `a` do `result`, potem nadpisujemy z `b`. Operacje są **na osobnej tabeli** — `a` i `b` zostają nietknięte.

To jest **shallow** merge — wartości to referencje. Jeśli `a.x` jest tabelą, to `result.x` wskazuje na **tę samą** tabelę. Modyfikacja `result.x.cos` zmienia także `a.x.cos`. Dla głębokiego merge'u — Moduł 4 (po metatable).

### Sprawdź się

- [ ] Wiem, czemu `t.if` jest błędem składni
- [ ] Pamiętam, że `t[1] == t[1.0]`, ale `t[1] ≠ t["1"]`
- [ ] Umiem iterować rekord przez `pairs`
- [ ] Wiem, że kolejność `pairs` jest niezdefiniowana
- [ ] Znam idiom `result[k] = (result[k] or 0) + 1` (counter)
- [ ] Wiem, jak policzyć wszystkie klucze tabeli (nie `#`)

---

## Lekcja 2.3: Tabele mieszane i zagnieżdżone — referencje

### Cel

Rozumiesz, że tabele to **referencje**, nie kopie. Umiesz pracować ze strukturami zagnieżdżonymi. Wiesz, jak porównać dwie tabele po wartości i jak je sklonować (płytko i głęboko).

### Materiał

#### Tabele mieszane

Tabela może mieć jednocześnie sekwencję i hash:

```lua
local session = {
    "first_event",              -- [1]
    "second_event",             -- [2]
    "third_event",              -- [3]
    sig = "abc123",
    phi = 0.7,
    epoch = 42,
}

-- Sekwencja działa normalnie:
for i, e in ipairs(session) do print(i, e) end
-- 1   first_event
-- 2   second_event
-- 3   third_event

-- Hash przez pairs:
for k, v in pairs(session) do print(k, v) end
-- (wypisuje wszystko, w nieokreślonej kolejności)
```

To bywa wygodne (np. event log z metadanymi), ale częściej cleaniejsze jest rozdzielenie:

```lua
local session = {
    sig = "abc123",
    phi = 0.7,
    epoch = 42,
    events = {"first_event", "second_event", "third_event"},
}

-- Teraz events jest osobnym polem:
for i, e in ipairs(session.events) do print(i, e) end
```

#### Zagnieżdżone tabele

```lua
local hss = {
    name = "default-policy",
    quota = {
        cpu_ms = 500,
        mem_kb = 4096,
    },
    capabilities = {
        "phi.read",
        "phi.write",
    },
    sessions = {
        {sig = "abc", phi = 0.7},
        {sig = "def", phi = 0.4},
    },
}

print(hss.quota.cpu_ms)               -- 500
print(hss.capabilities[1])            -- "phi.read"
print(hss.sessions[1].sig)            -- "abc"
print(hss.sessions[2].phi)            -- 0.4
```

To jest typowa konfiguracja systemu jak HSS. Lua zagnieżdżenia wyglądają jak JSON, ale są bardziej elastyczne (klucze dowolnych typów, brak cudzysłowów na kluczach).

#### Tabele to **referencje**

Najważniejsza rzecz w tej lekcji.

```lua
local a = {1, 2, 3}
local b = a               -- b jest TĄ SAMĄ tabelą, nie kopią!

b[1] = 99
print(a[1])               -- 99   (! a też się zmieniło)

print(a == b)             -- true (same identity)
```

Lua przekazuje tabele **przez referencję** (jak Python listy, jak obiekty w JS). To znaczy:
- przypisanie `b = a` — kopiuje *referencję*, nie zawartość
- przekazanie `f(t)` — funkcja widzi tę samą tabelę, modyfikacje wpływają na oryginał
- powrót `return t` — wraca referencja

#### Porównanie tabel — `==`

Operator `==` na tabelach porównuje **identity** (czy to ten sam obiekt), **nie zawartość**:

```lua
print({1, 2, 3} == {1, 2, 3})    -- false! (różne tabele, mimo tej samej zawartości)

local a = {1, 2, 3}
local b = a
print(a == b)                     -- true (ta sama tabela)
```

Aby porównać po wartości — pisze się ręcznie (lub używa metatable `__eq`, Moduł 4).

#### Shallow copy — kopia płytka

```lua
local function shallow_copy(t)
    local result = {}
    for k, v in pairs(t) do
        result[k] = v
    end
    return result
end

local a = {1, 2, 3}
local b = shallow_copy(a)
b[1] = 99
print(a[1], b[1])    -- 1   99   (różne tabele)
```

**Pułapka shallow copy:** jeśli wartości są tabelami, obie kopie wskazują na **te same** podtabele:

```lua
local original = {
    name = "x",
    nested = {value = 10},
}

local copy = shallow_copy(original)
copy.name = "y"
copy.nested.value = 999

print(original.name)            -- "x"   (nie zmieniło się — string skopiowany)
print(original.nested.value)    -- 999   (! zmieniło się — to ta sama podtabela)
```

#### Deep copy — kopia głęboka

```lua
local function deep_copy(t)
    if type(t) ~= "table" then
        return t   -- liczby, stringi, booleany kopiują się "naturalnie"
    end
    local result = {}
    for k, v in pairs(t) do
        result[k] = deep_copy(v)   -- rekurencyjnie
    end
    return result
end

local original = {
    name = "x",
    nested = {value = 10},
}

local copy = deep_copy(original)
copy.nested.value = 999
print(original.nested.value)    -- 10  (nietknięte!)
```

**Pułapki deep copy:**
- **Cykle:** jeśli `t.self = t`, naiwna implementacja wpadnie w nieskończoną rekursję. Rozwiązanie — tabela "już skopiowane" (zadanie 2.3.5).
- **Klucze tabelowe:** też powinny być deep-copy'owane (rzadko praktyczne).
- **Metatable:** standardowy deep copy ich nie kopiuje. Trzeba dodać `setmetatable(result, getmetatable(t))`.
- **Funkcje, userdata, threads:** nie da się ich skopiować — kopiujemy referencję.

### Pułapki

1. **Tabele to referencje.** Przypisanie nie kopiuje.
2. **`{1, 2} == {1, 2}` to `false`** — porównanie po identity.
3. **Shallow copy nie kopiuje podtabel.**
4. **Deep copy musi obsłużyć cykle.**
5. **Mieszane tabele** są legalne, ale często myli — preferuj separację.

### Zadania

**Zadanie 2.3.1**  
Reprezentacja punktu jako `{x = ?, y = ?}`. Napisz funkcję `distance(a, b)` zwracającą odległość euklidesową między dwoma punktami.

**Zadanie 2.3.2**  
Lista atomów, każdy o postaci `{sig = ?, phi = ?}`. Napisz funkcję `average_phi(atoms)` zwracającą średnią `phi` wszystkich atomów. Jeśli lista pusta — zwróć 0.

**Zadanie 2.3.3**  
Napisz funkcję `equal(a, b)` porównującą dwie tabele **po wartości**, rekurencyjnie. Działa dla zagnieżdżonych struktur. Klucze to liczby/stringi (bez tabelowych kluczy).  
Test:
```lua
equal({1, 2, 3}, {1, 2, 3})                          -- true
equal({a = {1, 2}}, {a = {1, 2}})                    -- true
equal({1, 2, 3}, {1, 2})                             -- false
equal({a = 1, b = 2}, {a = 1})                       -- false
equal({a = 1, b = 2}, {a = 1, b = 2, c = 3})         -- false
```

**Zadanie 2.3.4**  
Napisz funkcję `flatten(t)` która z tabeli zagnieżdżonych tabel-list zwraca jedną listę.  
Test: `flatten({{1,2}, {3, {4,5}}, {6}})` = `{1, 2, 3, 4, 5, 6}`.

**Zadanie 2.3.5**  
Napisz funkcję `deep_copy_safe(t)` która obsługuje cykle (używa pomocniczej tabeli z już skopiowanymi referencjami).  
Test:
```lua
local t = {a = 1}
t.self = t                      -- cykl!
local copy = deep_copy_safe(t)
print(copy.a)                   -- 1
print(copy.self == copy)        -- true (cykl zachowany, ale na nowej tabeli)
print(copy.self == t)           -- false (to nie jest oryginalny t)
```

---

### Rozwiązania

#### Rozwiązanie 2.3.1

```lua
-- distance.lua
local function distance(a, b)
    local dx = a.x - b.x
    local dy = a.y - b.y
    return math.sqrt(dx * dx + dy * dy)
end

print(distance({x = 0, y = 0}, {x = 3, y = 4}))    -- 5.0
print(distance({x = 1, y = 1}, {x = 1, y = 1}))    -- 0.0
print(distance({x = -1, y = 0}, {x = 1, y = 0}))   -- 2.0
```

`dx * dx` zamiast `dx^2` — `^` daje float zawsze, mnożenie zachowuje typ (integer × integer = integer w 5.3+, choć potem `sqrt` i tak da float).

#### Rozwiązanie 2.3.2

```lua
-- average_phi.lua
local function average_phi(atoms)
    if #atoms == 0 then return 0 end
    local sum = 0
    for _, atom in ipairs(atoms) do
        sum = sum + atom.phi
    end
    return sum / #atoms
end

local atoms = {
    {sig = "a", phi = 0.7},
    {sig = "b", phi = 0.4},
    {sig = "c", phi = 0.9},
}
print(average_phi(atoms))    -- 0.66666666666667
print(average_phi({}))       -- 0
```

#### Rozwiązanie 2.3.3

```lua
-- equal.lua
local function equal(a, b)
    if type(a) ~= type(b) then return false end
    if type(a) ~= "table" then
        return a == b
    end
    -- Obie tabele — porównujemy zawartość rekurencyjnie
    
    -- Sprawdzamy: każdy klucz z a istnieje w b z tą samą wartością
    for k, v in pairs(a) do
        if not equal(v, b[k]) then return false end
    end
    -- I odwrotnie: każdy klucz z b istnieje w a (żeby wykryć extra klucze w b)
    for k in pairs(b) do
        if a[k] == nil then return false end
    end
    return true
end

print(equal({1, 2, 3}, {1, 2, 3}))                            -- true
print(equal({a = {1, 2}}, {a = {1, 2}}))                      -- true
print(equal({1, 2, 3}, {1, 2}))                               -- false
print(equal({a = 1, b = 2}, {a = 1}))                         -- false
print(equal({a = 1, b = 2}, {a = 1, b = 2, c = 3}))           -- false
print(equal({{1, 2}, {3, 4}}, {{1, 2}, {3, 4}}))              -- true
print(equal({{1, 2}, {3, 4}}, {{1, 2}, {3, 5}}))              -- false
print(equal(1, 1))                                            -- true
print(equal("a", "a"))                                        -- true
```

Dwa pełne sprawdzenia są konieczne. Pierwsza pętla (`a -> b`) sprawdza, że każdy klucz z `a` ma dopasowanie w `b`. Druga (`b -> a`) sprawdza, że `b` nie ma **dodatkowych** kluczy. Bez drugiej pętli `equal({a=1}, {a=1, b=2})` zwróciłoby `true`.

#### Rozwiązanie 2.3.4

```lua
-- flatten.lua
local function flatten(t)
    local result = {}
    local function helper(sub)
        for _, v in ipairs(sub) do
            if type(v) == "table" then
                helper(v)
            else
                result[#result + 1] = v
            end
        end
    end
    helper(t)
    return result
end

local r = flatten({{1, 2}, {3, {4, 5}}, {6}})
for _, v in ipairs(r) do io.write(v, " ") end
print()
-- 1 2 3 4 5 6

local r2 = flatten({1, {2, {3, {4, {5}}}}})
for _, v in ipairs(r2) do io.write(v, " ") end
print()
-- 1 2 3 4 5
```

Pomocnicza funkcja `helper` ma dostęp do `result` przez closure. Rekurencyjnie schodzi do każdej zagnieżdżonej tabeli. Korzystamy z `ipairs` — zakładamy, że "tabela-lista" znaczy sekwencja.

#### Rozwiązanie 2.3.5

```lua
-- deep_copy_safe.lua
local function deep_copy_safe(t)
    local seen = {}    -- mapa: oryginalna_tabela -> kopia
    
    local function helper(x)
        if type(x) ~= "table" then return x end
        if seen[x] then return seen[x] end    -- już kopiowaliśmy — zwróć kopię
        
        local copy = {}
        seen[x] = copy   -- zaznacz PRZED rekursją (! żeby cykl został wykryty)
        
        for k, v in pairs(x) do
            copy[helper(k)] = helper(v)   -- klucze też deep-copy
        end
        return copy
    end
    
    return helper(t)
end

-- Test cyklu:
local t = {a = 1}
t.self = t
local copy = deep_copy_safe(t)

print(copy.a)                  -- 1
print(copy.self == copy)       -- true (struktura cyklu zachowana)
print(copy.self == t)          -- false (nowa tabela)
print(copy ~= t)               -- true

-- Test struktury bez cyklu:
local original = {x = 1, nested = {y = 2, deep = {z = 3}}}
local c = deep_copy_safe(original)
c.nested.deep.z = 999
print(original.nested.deep.z)  -- 3 (nietknięte)
```

Klucz: `seen[x] = copy` ustawiane **przed** wejściem w pętlę. Gdy w trakcie pętli natkniemy się na `x` (cykl), `seen[x]` już istnieje — zwracamy kopię zamiast wpadać w nieskończoną rekursję.

Notabene: tabela `seen` używa **tabel jako kluczy** — tu wykorzystujemy fakt, że Lua to umie (Lekcja 2.2). Klucze są porównywane po identity, więc `seen[x]` znajduje dokładnie tę tabelę.

### Sprawdź się

- [ ] Wiem, że tabele to referencje
- [ ] Pamiętam, że `{} == {}` to `false`
- [ ] Umiem napisać shallow_copy i wiem, czemu nie wystarcza
- [ ] Znam algorytm deep_copy z obsługą cykli
- [ ] Wiem, że klucze tabeli mogą być same tabelami
- [ ] Umiem porównać dwie tabele po wartości

---

## Lekcja 2.4: Iteracja i biblioteka `table.*`

### Cel

Znasz pełen zestaw narzędzi do iteracji (pairs, ipairs, next) i biblioteki standardowej `table` (concat, sort, unpack, move).

### Materiał

#### `pairs` vs `ipairs` — przypomnienie + szczegół

```lua
local t = {10, 20, 30, name = "x"}

for k, v in ipairs(t) do print(k, v) end
-- 1   10
-- 2   20
-- 3   30
-- (nie wypisuje 'name' — ipairs idzie tylko po sekwencji)

for k, v in pairs(t) do print(k, v) end
-- 1     10
-- 2     20
-- 3     30
-- name  x
-- (kolejność niezdefiniowana, ale wszystko jest)
```

#### `next(t, k)` — niskopoziomowy iterator

`pairs` to wrapper na `next`. Bezpośrednio:

```lua
local t = {a = 1, b = 2, c = 3}

local k, v = next(t)             -- pierwszy klucz/wartość (kolejność undefined)
print(k, v)                      -- np. "b   2"

k, v = next(t, k)                -- następny po k
print(k, v)                      -- np. "a   1"

k, v = next(t, k)
print(k, v)                      -- np. "c   3"

k = next(t, k)
print(k)                         -- nil (koniec)
```

`next(t, nil)` lub `next(t)` zwraca pierwszą parę. `next(t, k)` zwraca parę po `k`. Gdy nie ma więcej — zwraca `nil`.

**Praktyczny use case:** sprawdzenie, czy tabela jest pusta:

```lua
local function is_empty(t)
    return next(t) == nil
end

print(is_empty({}))           -- true
print(is_empty({1}))          -- false
print(is_empty({a = 1}))      -- false
```

`#t == 0` nie wystarczy — `{a = 1}` ma `#t == 0`, ale nie jest puste.

#### `table.concat`

```lua
local t = {"alfa", "beta", "gamma"}
print(table.concat(t))            -- "alfabetagamma"
print(table.concat(t, ", "))      -- "alfa, beta, gamma"
print(table.concat(t, " | "))     -- "alfa | beta | gamma"

-- Z zakresem:
print(table.concat(t, ", ", 2, 3))  -- "beta, gamma"
print(table.concat(t, ", ", 1, 2))  -- "alfa, beta"
```

**Wymóg:** wszystkie elementy muszą być stringami albo liczbami. `table.concat({1, 2, "a"}, "-")` = `"1-2-a"`. Ale `table.concat({1, true})` rzuca błąd.

**Wydajność:** `table.concat` jest **dużo** szybsze niż `s = s .. v` w pętli. Idiom budowania długiego stringu:

```lua
-- ŹLE — O(n²):
local s = ""
for i = 1, 10000 do
    s = s .. tostring(i)
end

-- DOBRZE — O(n):
local parts = {}
for i = 1, 10000 do
    parts[#parts + 1] = tostring(i)
end
local s = table.concat(parts)
```

#### `table.sort`

```lua
local t = {3, 1, 4, 1, 5, 9, 2, 6, 5}
table.sort(t)
-- t to teraz {1, 1, 2, 3, 4, 5, 5, 6, 9}

-- Z komparatorem:
local atoms = {
    {sig = "a", phi = 0.4},
    {sig = "b", phi = 0.7},
    {sig = "c", phi = 0.2},
}

table.sort(atoms, function(a, b) return a.phi > b.phi end)
-- malejąco po phi:
-- {sig = "b", phi = 0.7}
-- {sig = "a", phi = 0.4}
-- {sig = "c", phi = 0.2}
```

**Modyfikuje in-place** i nic nie zwraca. Komparator: funkcja `(a, b) -> bool` zwracająca `true` gdy `a` ma być przed `b`.

**Pułapka:** komparator musi być **strictly less than** — nie dopuszczalne `<=`. Jeśli zwracasz `<=`, dwa równe elementy "obie idą przed sobą" i sort zaczyna głupieć (a przy złośliwym wejściu może wpaść w nieskończoną pętlę).

#### `table.unpack` — z tabeli na multiple values

```lua
local t = {10, 20, 30}
print(table.unpack(t))           -- 10   20   30

-- Wywołanie funkcji z argumentami z tabeli:
local function add3(a, b, c) return a + b + c end
print(add3(table.unpack(t)))     -- 60
```

W Lua 5.1: `unpack(t)` (bez `table.`). W 5.2+ — `table.unpack(t)`. **Działa tylko dla sekwencji.** Hash zostanie pominięty. Z zakresem:

```lua
print(table.unpack({1,2,3,4,5}, 2, 4))    -- 2   3   4
```

#### `table.move` (5.3+)

Kopiowanie zakresu z jednej tabeli do drugiej:

```lua
local src = {10, 20, 30, 40, 50}
local dst = {}

table.move(src, 1, 5, 1, dst)
-- src[1..5] -> dst[1..5]
print(dst[1], dst[2], dst[5])    -- 10   20   50
```

Sygnatura: `table.move(a1, f, e, t [, a2])`:
- `a1` — źródło
- `f` — pierwszy indeks źródła (od)
- `e` — ostatni indeks źródła (do, inclusive)
- `t` — pierwszy indeks docelowy
- `a2` — tabela docelowa (jeśli pominięte — `a1`, czyli przesunięcie wewnątrz)

Use case — przesunięcie wewnątrz tabeli:

```lua
local t = {1, 2, 3, 4, 5}
table.move(t, 2, 5, 1)         -- przesuń [2..5] na pozycję 1
-- t == {2, 3, 4, 5, 5}        (! ostatni element niezmieniony, bo nie był nadpisany)
```

### Pułapki

1. **`pairs` nie gwarantuje kolejności** — sortuj klucze jeśli musisz.
2. **`next(t)` to test pustości** — nie `#t == 0`.
3. **`table.concat` wymaga string/number values.**
4. **Konkatenacja w pętli** — używaj `table.concat`, nie `..`.
5. **`table.sort` jest in-place** i nic nie zwraca.
6. **Komparator musi być strict <**, nie `<=`.

### Zadania

**Zadanie 2.4.1**  
Napisz funkcję `sorted_keys(t)`, która zwraca tabelę kluczy `t` posortowaną alfabetycznie. Następnie wykorzystaj ją do iteracji po `t` w stałej kolejności.

**Zadanie 2.4.2**  
Napisz funkcję `top_n(atoms, n)`, która zwraca **nową** tabelę zawierającą `n` atomów o największym `phi`. Oryginalna tabela `atoms` ma być **nietknięta**.

**Zadanie 2.4.3**  
Napisz funkcję `join(t, sep, prefix, suffix)`, która łączy elementy tabeli (jak `table.concat`), ale otacza całość prefixem i sufiksem. Domyślny sep = `", "`, prefix/suffix opcjonalne.  
Test: `join({1,2,3}, "-", "[", "]")` = `"[1-2-3]"`.

**Zadanie 2.4.4**  
Napisz funkcję `reverse(t)`, która odwraca tabelę-listę **in-place**. Bez tworzenia nowej tabeli.  
Test:
```lua
local t = {1, 2, 3, 4, 5}
reverse(t)
-- t == {5, 4, 3, 2, 1}
```

**Zadanie 2.4.5**  
Napisz funkcję `slice(t, i, j)`, która zwraca **nową** tabelę będącą wycinkiem `t[i..j]` (inclusive, oba). Domyślnie `i = 1`, `j = #t`. Ujemne indeksy liczone od końca (jak w Pythonie / Lua string).  
Test:
```lua
slice({10, 20, 30, 40, 50}, 2, 4)     -- {20, 30, 40}
slice({10, 20, 30}, 2)                -- {20, 30}
slice({10, 20, 30, 40}, -2)           -- {30, 40}
slice({10, 20, 30, 40}, 1, -2)        -- {10, 20, 30}
```

---

### Rozwiązania

#### Rozwiązanie 2.4.1

```lua
-- sorted_keys.lua
local function sorted_keys(t)
    local keys = {}
    for k in pairs(t) do
        keys[#keys + 1] = k
    end
    table.sort(keys)
    return keys
end

local config = {
    cpu_ms = 500,
    mem_kb = 4096,
    atoms_max = 1000,
    epoch_max = 100,
}

for _, k in ipairs(sorted_keys(config)) do
    print(k, config[k])
end
-- atoms_max  1000
-- cpu_ms     500
-- epoch_max  100
-- mem_kb     4096
```

To jest **kanoniczny idiom** wypisywania konfiguracji w deterministycznej kolejności. Bardzo użyteczny w log message'ach (gdzie chcesz, by ten sam stan dawał ten sam wydruk).

#### Rozwiązanie 2.4.2

```lua
-- top_n.lua
local function top_n(atoms, n)
    -- Kopia płytka tabeli (bo sort jest in-place):
    local copy = {}
    for i, a in ipairs(atoms) do
        copy[i] = a
    end
    
    table.sort(copy, function(a, b) return a.phi > b.phi end)
    
    -- Wytnij top n:
    local result = {}
    for i = 1, math.min(n, #copy) do
        result[i] = copy[i]
    end
    return result
end

local atoms = {
    {sig = "a", phi = 0.4},
    {sig = "b", phi = 0.9},
    {sig = "c", phi = 0.2},
    {sig = "d", phi = 0.7},
    {sig = "e", phi = 0.1},
}

local top = top_n(atoms, 3)
for _, a in ipairs(top) do
    print(a.sig, a.phi)
end
-- b   0.9
-- d   0.7
-- a   0.4

-- Sprawdzenie że oryginał nietknięty:
print("Original [1].sig =", atoms[1].sig)    -- "a"
```

`math.min(n, #copy)` zabezpiecza przed prośbą o więcej elementów niż jest. Bez tego — błąd albo nil w wyniku.

**Uwaga:** to jest shallow copy — `copy[i]` to ciągle ten sam atom co `atoms[i]`. Jeśli ktoś zmodyfikuje `top[1].phi`, zmieni też oryginał. Dla pełnej izolacji potrzebny by był deep copy (Lekcja 2.3).

#### Rozwiązanie 2.4.3

```lua
-- join.lua
local function join(t, sep, prefix, suffix)
    sep = sep or ", "
    prefix = prefix or ""
    suffix = suffix or ""
    return prefix .. table.concat(t, sep) .. suffix
end

print(join({1, 2, 3}))                      -- "1, 2, 3"
print(join({1, 2, 3}, "-"))                 -- "1-2-3"
print(join({1, 2, 3}, "-", "[", "]"))       -- "[1-2-3]"
print(join({"alfa", "beta"}, " | ", "<<", ">>"))   -- "<<alfa | beta>>"
print(join({}, "-", "[", "]"))              -- "[]"
```

Idiom `x = x or default` — domyślne wartości dla opcjonalnych argumentów.

#### Rozwiązanie 2.4.4

```lua
-- reverse.lua
local function reverse(t)
    local i, j = 1, #t
    while i < j do
        t[i], t[j] = t[j], t[i]
        i = i + 1
        j = j - 1
    end
end

local t = {1, 2, 3, 4, 5}
reverse(t)
for _, v in ipairs(t) do io.write(v, " ") end
print()
-- 5 4 3 2 1

local t2 = {"a", "b", "c", "d"}
reverse(t2)
for _, v in ipairs(t2) do io.write(v, " ") end
print()
-- d c b a
```

Two-pointer technique — `i` od początku, `j` od końca, swap, do spotkania w środku. `t[i], t[j] = t[j], t[i]` — multiple assignment dla swapu.

#### Rozwiązanie 2.4.5

```lua
-- slice.lua
local function slice(t, i, j)
    local n = #t
    i = i or 1
    j = j or n
    
    -- Ujemne indeksy:
    if i < 0 then i = n + i + 1 end
    if j < 0 then j = n + j + 1 end
    
    -- Clamp do legalnego zakresu:
    if i < 1 then i = 1 end
    if j > n then j = n end
    
    local result = {}
    for k = i, j do
        result[#result + 1] = t[k]
    end
    return result
end

local function show(t)
    for _, v in ipairs(t) do io.write(v, " ") end
    print()
end

show(slice({10, 20, 30, 40, 50}, 2, 4))    -- 20 30 40
show(slice({10, 20, 30}, 2))               -- 20 30
show(slice({10, 20, 30, 40}, -2))          -- 30 40
show(slice({10, 20, 30, 40}, 1, -2))       -- 10 20 30
show(slice({10, 20, 30, 40}))              -- 10 20 30 40
show(slice({10, 20, 30}, 5))               -- (puste)
```

Konwersja ujemnego indeksu: `n + i + 1`. Dla `n = 4, i = -2`: `4 + (-2) + 1 = 3` — prawidłowo (trzeci element od końca).

Implementacja Lua 5.3+ mogłaby używać `table.move`:

```lua
local function slice_move(t, i, j)
    -- (...uzupełnij i, j jak wyżej...)
    local result = {}
    table.move(t, i, j, 1, result)
    return result
end
```

Bardziej idiomatyczne i potencjalnie szybsze (C-implementation pod spodem).

### Sprawdź się

- [ ] Umiem testować pustość tabeli przez `next(t) == nil`
- [ ] Wiem, że konkatenacja w pętli to O(n²) — używam `table.concat`
- [ ] Pamiętam, że `table.sort` jest in-place
- [ ] Komparator dla `table.sort` musi być `strict <`
- [ ] Znam idiom sortowania kluczy do deterministycznej iteracji
- [ ] Wiem, jak skopiować zakres tabeli przez `table.move`

---

## Lekcja 2.5: Wzorce — set, stack, queue, multiset, namespace

### Cel

Znasz kanoniczne wzorce użycia tabel: jako zbiór, stos, kolejka, licznik, namespace. Te wzorce są fundamentem każdego większego programu w Lua.

### Materiał

#### Tabela jako **set** (zbiór)

```lua
local set = {}

-- Dodawanie:
set["abc"] = true
set["def"] = true

-- Sprawdzanie:
if set["abc"] then print("jest") end
if not set["xyz"] then print("nie ma") end

-- Usuwanie:
set["abc"] = nil
```

Konwencja: wartością jest `true` (lub cokolwiek truthy — np. liczba). Lookup to `O(1)`.

```lua
-- Inicjalizacja z listy:
local function set_from_list(list)
    local s = {}
    for _, v in ipairs(list) do
        s[v] = true
    end
    return s
end

local cap = set_from_list({"phi.read", "phi.write", "session.spawn"})
print(cap["phi.read"])       -- true
print(cap["phi.delete"])     -- nil
```

#### Tabela jako **stack** (LIFO)

```lua
local stack = {}

-- Push:
stack[#stack + 1] = "a"
stack[#stack + 1] = "b"
stack[#stack + 1] = "c"

-- Peek (bez usuwania):
local top = stack[#stack]    -- "c"

-- Pop:
local popped = stack[#stack]
stack[#stack] = nil           -- "c" usunięte
```

Albo z `table.insert`/`table.remove`:

```lua
table.insert(stack, "d")     -- push
local x = table.remove(stack)  -- pop (z końca)
```

`table.remove(t)` (bez indeksu) usuwa i zwraca ostatni — idealne dla stosu.

#### Tabela jako **queue** (FIFO) — naiwna

```lua
local queue = {}

-- Enqueue:
queue[#queue + 1] = "a"
queue[#queue + 1] = "b"
queue[#queue + 1] = "c"

-- Dequeue:
local first = table.remove(queue, 1)    -- "a"
-- ALE: O(n) bo przesuwa resztę!
```

`table.remove(queue, 1)` przesuwa wszystkie elementy w lewo. Dla małych kolejek OK, dla dużych — kosztowne.

#### Tabela jako **queue** — efektywna (head/tail)

Profesjonalna implementacja z dwoma wskaźnikami:

```lua
local queue = {head = 1, tail = 0}

local function enqueue(q, v)
    q.tail = q.tail + 1
    q[q.tail] = v
end

local function dequeue(q)
    if q.head > q.tail then return nil end   -- pusta
    local v = q[q.head]
    q[q.head] = nil
    q.head = q.head + 1
    return v
end

local function queue_size(q)
    return q.tail - q.head + 1
end

enqueue(queue, "a")
enqueue(queue, "b")
enqueue(queue, "c")
print(dequeue(queue))      -- "a"
print(dequeue(queue))      -- "b"
print(queue_size(queue))   -- 1
```

`head` rośnie przy dequeue, `tail` rośnie przy enqueue. Operacje są O(1). Tabela rośnie monotonicznie (nie ma "shrinkowania"), ale puste sloty (`q[k] = nil`) są zwalniane przez GC.

#### Tabela jako **counter / multiset**

```lua
local count = {}

local function inc(t, k)
    t[k] = (t[k] or 0) + 1
end

inc(count, "phi.read")
inc(count, "phi.read")
inc(count, "phi.write")

print(count["phi.read"])     -- 2
print(count["phi.write"])    -- 1
print(count["phi.delete"])   -- nil
```

Jednoplinerek `t[k] = (t[k] or 0) + 1` to chyba najczęstszy idiom w Lua. Pojawia się w word counting, hit counting, statystykach, profilowaniu.

#### Tabela jako **namespace / moduł**

```lua
-- hss_utils.lua (jako moduł — szczegóły Moduł 7)
local M = {}

function M.spawn_atom(sig, phi)
    return {sig = sig, phi = phi or 0.0, alive = true}
end

function M.kill(atom)
    atom.alive = false
    atom.phi = 0
end

function M.is_high_phi(atom, threshold)
    threshold = threshold or 0.5
    return atom.phi > threshold
end

return M
```

Użycie:

```lua
local hss = require("hss_utils")
local a = hss.spawn_atom("abc", 0.7)
print(hss.is_high_phi(a))    -- true
```

Ten wzorzec — tabela `M`, dodawanie funkcji, `return M` — jest fundamentem modułów w Lua.

#### Filter, map — funkcyjne

Lua nie ma natywnego `filter`/`map`, ale łatwo napisać:

```lua
local function filter(t, predicate)
    local result = {}
    for _, v in ipairs(t) do
        if predicate(v) then
            result[#result + 1] = v
        end
    end
    return result
end

local function map(t, fn)
    local result = {}
    for i, v in ipairs(t) do
        result[i] = fn(v)
    end
    return result
end

local nums = {1, 2, 3, 4, 5, 6}
local evens = filter(nums, function(n) return n % 2 == 0 end)
-- {2, 4, 6}

local doubled = map(nums, function(n) return n * 2 end)
-- {2, 4, 6, 8, 10, 12}
```

W praktyce te funkcje warto wpisać do swojego "stdlib" (np. `local fn = require("fn_utils")`).

### Pułapki

1. **Naiwna kolejka jest O(n)** dla dequeue. Dla dużych kolejek — head/tail.
2. **Set z `set[k] = true`** — usuwasz przez `set[k] = nil`, nie `false`. (`false` to wciąż klucz!)

```lua
local s = {}
s["x"] = true
s["x"] = false       -- klucz "x" wciąż w tabeli!
print(next(s))       -- "x"   false  — wciąż widoczny
s["x"] = nil         -- usunięty
print(next(s))       -- nil  (pusty)
```

3. **Multiset bez fallback** — `count[k] + 1` gdy `count[k]` to nil rzuca błąd. Zawsze `(count[k] or 0) + 1`.

### Zadania

**Zadanie 2.5.1** — Implementacja set jako moduł  
Napisz moduł (tabelę) `Set` z funkcjami:
- `Set.new()` — pusty zbiór
- `Set.add(s, v)` — dodaje
- `Set.remove(s, v)` — usuwa
- `Set.contains(s, v)` — czy zawiera
- `Set.size(s)` — liczba elementów
- `Set.to_list(s)` — lista wartości

Test:
```lua
local s = Set.new()
Set.add(s, "a"); Set.add(s, "b"); Set.add(s, "a")
print(Set.size(s))          -- 2
print(Set.contains(s, "a")) -- true
Set.remove(s, "a")
print(Set.size(s))          -- 1
```

**Zadanie 2.5.2** — Stack jako closure  
Napisz funkcję `make_stack()` zwracającą obiekt-stos jako tabelę zawierającą metody `push`, `pop`, `peek`, `size`, `empty`. Wewnątrz używa **prywatnej** tabeli (przez closure), nie pola w obiekcie.  
Test:
```lua
local s = make_stack()
s.push(1); s.push(2); s.push(3)
print(s.peek())     -- 3
print(s.pop())      -- 3
print(s.size())     -- 2
```

**Zadanie 2.5.3** — Word count  
Napisz funkcję `word_count(text)`, która zwraca tabelę z liczbą wystąpień każdego słowa (case-insensitive). Słowo = ciąg znaków alfanumerycznych.  
Test:
```lua
local wc = word_count("ala ma kota a kot ma alę")
-- wc = {ala=1, alę=1, ma=2, kota=1, a=1, kot=1}
```

**Zadanie 2.5.4** — Group by  
Napisz funkcję `group_by(list, key_fn)`, która grupuje elementy listy po wartości zwracanej przez `key_fn(element)`. Wynik to tabela: klucz → lista elementów.  
Test:
```lua
local people = {
    {name = "Anna", dept = "infra"},
    {name = "Jan",  dept = "research"},
    {name = "Ola",  dept = "infra"},
}
local by_dept = group_by(people, function(p) return p.dept end)
-- by_dept.infra = {<Anna>, <Ola>}
-- by_dept.research = {<Jan>}
```

**Zadanie 2.5.5** — Filter, map z indeksami  
Napisz funkcje `imap(t, fn)` i `ifilter(t, predicate)`, które działają jak `map`/`filter`, ale przekazują też **indeks** do funkcji: `fn(value, index)`.  
Test:
```lua
imap({"a", "b", "c"}, function(v, i) return i .. ":" .. v end)
-- {"1:a", "2:b", "3:c"}
ifilter({10, 20, 30, 40}, function(v, i) return i % 2 == 0 end)
-- {20, 40}
```

---

### Rozwiązania

#### Rozwiązanie 2.5.1

```lua
-- set.lua
local Set = {}

function Set.new()
    return {_data = {}, _size = 0}
end

function Set.add(s, v)
    if s._data[v] == nil then
        s._data[v] = true
        s._size = s._size + 1
    end
end

function Set.remove(s, v)
    if s._data[v] ~= nil then
        s._data[v] = nil
        s._size = s._size - 1
    end
end

function Set.contains(s, v)
    return s._data[v] ~= nil
end

function Set.size(s)
    return s._size
end

function Set.to_list(s)
    local list = {}
    for k in pairs(s._data) do
        list[#list + 1] = k
    end
    return list
end

-- Test:
local s = Set.new()
Set.add(s, "a"); Set.add(s, "b"); Set.add(s, "a")
print(Set.size(s))           -- 2
print(Set.contains(s, "a"))  -- true
Set.remove(s, "a")
print(Set.size(s))           -- 1
print(Set.contains(s, "b"))  -- true

local list = Set.to_list(s)
for _, v in ipairs(list) do print(v) end
-- "b"
```

Pole `_size` cache'uje rozmiar — bez niego `Set.size` musiałby iterować przez `_data` co iteracja. Konwencja: pola zaczynające się od `_` to "prywatne, nie ruszaj" (Lua tego nie wymusza, to gentlemen's agreement).

W Module 4 zobaczysz jak zrobić `s:size()` zamiast `Set.size(s)` — to czyściej, ale wymaga metatable.

#### Rozwiązanie 2.5.2

```lua
-- make_stack.lua
local function make_stack()
    local data = {}    -- prywatne, schowane w closure
    local size = 0
    
    return {
        push = function(v)
            size = size + 1
            data[size] = v
        end,
        
        pop = function()
            if size == 0 then return nil end
            local v = data[size]
            data[size] = nil
            size = size - 1
            return v
        end,
        
        peek = function()
            return data[size]
        end,
        
        size = function()
            return size
        end,
        
        empty = function()
            return size == 0
        end,
    }
end

-- Test:
local s = make_stack()
s.push(1); s.push(2); s.push(3)
print(s.peek())     -- 3
print(s.pop())      -- 3
print(s.size())     -- 2
print(s.empty())    -- false

while not s.empty() do
    print(s.pop())
end
-- 2
-- 1
```

To jest **closure-based encapsulation**. `data` i `size` są zmiennymi lokalnymi w `make_stack`, ale każda zwrócona funkcja "pamięta" do nich referencję (closure). Z zewnątrz nie ma żadnego sposobu, by je odczytać/zmodyfikować — są naprawdę prywatne.

To jest jedna z mocnych stron Lua. W Module 3 i 4 zobaczysz wariacje.

**Pułapka:** dwa wywołania `make_stack()` tworzą **niezależne** instancje (każda ze swoim `data`):

```lua
local a = make_stack()
local b = make_stack()
a.push(1)
print(b.size())    -- 0
```

Closures są per-call.

#### Rozwiązanie 2.5.3

```lua
-- word_count.lua
local function word_count(text)
    local result = {}
    for word in text:lower():gmatch("[%w]+") do
        result[word] = (result[word] or 0) + 1
    end
    return result
end

local wc = word_count("Ala ma kota, a kot ma Alę")

-- Wypisz w kolejności alfabetycznej:
local keys = {}
for k in pairs(wc) do keys[#keys + 1] = k end
table.sort(keys)
for _, k in ipairs(keys) do
    print(k, wc[k])
end
-- a    1
-- ala  1
-- alę  1
-- kot  1
-- kota 1
-- ma   2
```

Łańcuch: `text:lower()` → string lower-case → `:gmatch("[%w]+")` → iterator po słowach. `[%w]+` to "jeden lub więcej znaków alfanumerycznych".

**Uwaga:** `%w` w Lua patterns dla UTF-8 stringów polskich może nie działać idealnie (bo "ą", "ę" itp. mogą nie być traktowane jako alfanumeryczne — zależy od locale). W moim teście "alę" zadziałało, ale w innych systemach może nie. Dla pełnej obsługi UTF-8 — biblioteka `utf8` (5.3+) lub `lua-utf8` (zewnętrzna).

#### Rozwiązanie 2.5.4

```lua
-- group_by.lua
local function group_by(list, key_fn)
    local result = {}
    for _, item in ipairs(list) do
        local key = key_fn(item)
        if result[key] == nil then
            result[key] = {}
        end
        result[key][#result[key] + 1] = item
    end
    return result
end

local people = {
    {name = "Anna", dept = "infra"},
    {name = "Jan",  dept = "research"},
    {name = "Ola",  dept = "infra"},
    {name = "Piotr", dept = "research"},
    {name = "Bartek", dept = "infra"},
}

local by_dept = group_by(people, function(p) return p.dept end)

-- Wypisz:
local depts = {}
for k in pairs(by_dept) do depts[#depts + 1] = k end
table.sort(depts)

for _, d in ipairs(depts) do
    print("=== " .. d .. " ===")
    for _, p in ipairs(by_dept[d]) do
        print("  " .. p.name)
    end
end
-- === infra ===
--   Anna
--   Ola
--   Bartek
-- === research ===
--   Jan
--   Piotr
```

Idiom inicjowania pod-tabeli: `if result[key] == nil then result[key] = {} end`. Lua nie ma `defaultdict` jak Python, ale można to napisać przez metatable (Moduł 4):

```lua
-- Spojler — Moduł 4:
local function defaultdict(factory)
    return setmetatable({}, {__index = function(t, k)
        local v = factory()
        t[k] = v
        return v
    end})
end

local function group_by_v2(list, key_fn)
    local result = defaultdict(function() return {} end)
    for _, item in ipairs(list) do
        local g = result[key_fn(item)]
        g[#g + 1] = item
    end
    return result
end
```

Ale to zostawiamy na Moduł 4.

#### Rozwiązanie 2.5.5

```lua
-- imap_ifilter.lua
local function imap(t, fn)
    local result = {}
    for i, v in ipairs(t) do
        result[i] = fn(v, i)
    end
    return result
end

local function ifilter(t, predicate)
    local result = {}
    for i, v in ipairs(t) do
        if predicate(v, i) then
            result[#result + 1] = v
        end
    end
    return result
end

-- Testy:
local r1 = imap({"a", "b", "c"}, function(v, i) return i .. ":" .. v end)
for _, x in ipairs(r1) do io.write(x, " ") end
print()
-- 1:a 2:b 3:c

local r2 = ifilter({10, 20, 30, 40}, function(v, i) return i % 2 == 0 end)
for _, x in ipairs(r2) do io.write(x, " ") end
print()
-- 20 40

local r3 = ifilter({10, 20, 30, 40, 50}, function(v) return v > 25 end)
for _, x in ipairs(r3) do io.write(x, " ") end
print()
-- 30 40 50
```

`fn(v, i)` przekazuje wartość i indeks. Gdy `fn` jest jednoargumentowe — i tak działa, bo Lua nie sprawdza arity (Lekcja 1.5).

Wersja "fluent" / chainable wymagałaby metatable — Moduł 4.

### Sprawdź się

- [ ] Umiem zaimplementować set, stack, queue (head/tail) i counter
- [ ] Pamiętam, że `set[k] = false` NIE usuwa klucza
- [ ] Wiem, że `t[k] = (t[k] or 0) + 1` to idiom counter
- [ ] Umiem napisać closure-based stack (prywatny stan)
- [ ] Umiem napisać `group_by`
- [ ] Wiem, jak będzie wyglądał defaultdict z metatable (Moduł 4)

---

## Sprawdzian Modułu 2

Siedem zadań. Razem składają się na fundament — gdy je rozwiążesz, masz wszystko, czego potrzeba do zaawansowanego użycia tabel.

### Zadania

**Sprawdzian 1** — Stack jako moduł  
Napisz moduł `Stack` (zwracaną tabelę) z funkcjami `Stack.new`, `Stack.push`, `Stack.pop`, `Stack.peek`, `Stack.size`, `Stack.empty`. **Bez closures** — implementacja przez pole w tabeli reprezentującej stos.

**Sprawdzian 2** — Efektywna kolejka  
Napisz moduł `Queue` z `new`, `enqueue`, `dequeue`, `peek`, `size`, `empty`. Implementacja head/tail (O(1) na operację).

**Sprawdzian 3** — Operacje na zbiorach  
Napisz funkcje `set_union(a, b)`, `set_intersection(a, b)`, `set_difference(a, b)` (a − b), `set_symmetric_diff(a, b)` (xor). Zbiór reprezentowany jako `{[v] = true, ...}`. Wszystkie zwracają **nowy** zbiór.

**Sprawdzian 4** — Top N słów  
Napisz funkcję `top_words(text, n)` zwracającą `n` najczęstszych słów w tekście, posortowaną malejąco po liczności. Zwraca listę par `{word, count}`.

**Sprawdzian 5** — Pivot table  
Mając listę zdarzeń `{level, source, count}`, napisz funkcję `pivot(events)` zwracającą strukturę:  
`result[level][source]` = suma `count` wszystkich zdarzeń o tym `level` i `source`.  
Test:
```lua
local events = {
    {level = "INFO",  source = "scheduler", count = 5},
    {level = "WARN",  source = "lsm",       count = 3},
    {level = "INFO",  source = "scheduler", count = 2},
    {level = "INFO",  source = "lsm",       count = 1},
}
local p = pivot(events)
-- p.INFO.scheduler = 7
-- p.INFO.lsm = 1
-- p.WARN.lsm = 3
```

**Sprawdzian 6** — Deep equal z cyklami  
Napisz funkcję `deep_equal(a, b)`, która porównuje dwie zagnieżdżone tabele po wartości i obsługuje cykle (gdy `a.self = a` i `b.self = b`, zwraca `true`).

Hint: trzymaj tabelę "już porównane pary" — dla pary `(a, b)` która wraca w rekursji, traktuj jako równą (założenie, że nie znaleziono dotąd różnicy = wciąż mogą być równe).

**Sprawdzian 7** — Path getter  
Napisz funkcję `get_path(t, path)`, która z tabeli `t` wyciąga wartość pod ścieżką typu `"a.b[3].c"`. Wspiera:
- klucze stringowe oddzielone kropką
- indeksy numeryczne w nawiasach kwadratowych

Zwraca wartość lub `nil` jeśli ścieżka nieprawidłowa.

Test:
```lua
local data = {
    sessions = {
        {sig = "abc", atoms = {{phi = 0.7}, {phi = 0.4}}},
        {sig = "def", atoms = {}},
    },
    meta = {version = "1.0"},
}

get_path(data, "meta.version")              -- "1.0"
get_path(data, "sessions[1].sig")           -- "abc"
get_path(data, "sessions[1].atoms[2].phi")  -- 0.4
get_path(data, "sessions[3].sig")           -- nil
get_path(data, "nonsense.path")             -- nil
```

---

### Rozwiązania sprawdzianu

#### Sprawdzian 1

```lua
-- stack_module.lua
local Stack = {}

function Stack.new()
    return {data = {}, size = 0}
end

function Stack.push(s, v)
    s.size = s.size + 1
    s.data[s.size] = v
end

function Stack.pop(s)
    if s.size == 0 then return nil end
    local v = s.data[s.size]
    s.data[s.size] = nil
    s.size = s.size - 1
    return v
end

function Stack.peek(s)
    return s.data[s.size]
end

function Stack.size_(s)
    return s.size
end

function Stack.empty(s)
    return s.size == 0
end

-- Test:
local s = Stack.new()
Stack.push(s, "a")
Stack.push(s, "b")
Stack.push(s, "c")
print(Stack.peek(s))   -- "c"
print(Stack.size_(s))  -- 3
print(Stack.pop(s))    -- "c"
print(Stack.size_(s))  -- 2
print(Stack.empty(s))  -- false

while not Stack.empty(s) do
    print(Stack.pop(s))
end
-- "b"
-- "a"
```

Uwaga: nazwałem funkcję `Stack.size_` (z podkreślnikiem), bo `Stack.size` weszłoby w konflikt z polem `s.size`. To pokazuje pułapkę nazewnictwa, gdy pomieszamy "metody modułu" z "polami obiektu". W Module 4 zobaczysz jak to czysto rozwiązać metatable'em (`s:size()` zamiast `Stack.size(s)`).

#### Sprawdzian 2

```lua
-- queue_module.lua
local Queue = {}

function Queue.new()
    return {head = 1, tail = 0}
end

function Queue.enqueue(q, v)
    q.tail = q.tail + 1
    q[q.tail] = v
end

function Queue.dequeue(q)
    if q.head > q.tail then return nil end
    local v = q[q.head]
    q[q.head] = nil
    q.head = q.head + 1
    return v
end

function Queue.peek(q)
    if q.head > q.tail then return nil end
    return q[q.head]
end

function Queue.size(q)
    return q.tail - q.head + 1
end

function Queue.empty(q)
    return q.head > q.tail
end

-- Test:
local q = Queue.new()
Queue.enqueue(q, "first")
Queue.enqueue(q, "second")
Queue.enqueue(q, "third")

print(Queue.peek(q))     -- "first"
print(Queue.size(q))     -- 3

print(Queue.dequeue(q))  -- "first"
print(Queue.dequeue(q))  -- "second"
print(Queue.size(q))     -- 1

Queue.enqueue(q, "fourth")
print(Queue.dequeue(q))  -- "third"
print(Queue.dequeue(q))  -- "fourth"
print(Queue.empty(q))    -- true
print(Queue.dequeue(q))  -- nil (pusta)
```

`head` i `tail` rosną monotonicznie — po wielu enqueue/dequeue mogą być duże liczby. To OK, Lua integery to 64-bit. Dla bardzo długo działającego procesu można by zaimplementować "shrink" co N operacji, ale to optymalizacja.

#### Sprawdzian 3

```lua
-- set_ops.lua
local function set_union(a, b)
    local result = {}
    for k in pairs(a) do result[k] = true end
    for k in pairs(b) do result[k] = true end
    return result
end

local function set_intersection(a, b)
    local result = {}
    for k in pairs(a) do
        if b[k] then result[k] = true end
    end
    return result
end

local function set_difference(a, b)
    local result = {}
    for k in pairs(a) do
        if not b[k] then result[k] = true end
    end
    return result
end

local function set_symmetric_diff(a, b)
    local result = {}
    for k in pairs(a) do
        if not b[k] then result[k] = true end
    end
    for k in pairs(b) do
        if not a[k] then result[k] = true end
    end
    return result
end

-- Helper do wypisywania:
local function show(name, s)
    local list = {}
    for k in pairs(s) do list[#list + 1] = k end
    table.sort(list)
    print(name .. ": {" .. table.concat(list, ", ") .. "}")
end

local A = {a = true, b = true, c = true}
local B = {b = true, c = true, d = true, e = true}

show("A", A)
show("B", B)
show("A ∪ B", set_union(A, B))
show("A ∩ B", set_intersection(A, B))
show("A − B", set_difference(A, B))
show("B − A", set_difference(B, A))
show("A △ B", set_symmetric_diff(A, B))
```

```
A: {a, b, c}
B: {b, c, d, e}
A ∪ B: {a, b, c, d, e}
A ∩ B: {b, c}
A − B: {a}
B − A: {d, e}
A △ B: {a, d, e}
```

Symmetric difference można też zaimplementować jako `union(diff(a, b), diff(b, a))`, ale wersja z dwiema pętlami jest jaśniejsza i równie szybka.

#### Sprawdzian 4

```lua
-- top_words.lua
local function top_words(text, n)
    -- Liczenie:
    local count = {}
    for word in text:lower():gmatch("[%w]+") do
        count[word] = (count[word] or 0) + 1
    end
    
    -- Spłaszczenie do listy par:
    local pairs_list = {}
    for w, c in pairs(count) do
        pairs_list[#pairs_list + 1] = {word = w, count = c}
    end
    
    -- Sortowanie malejąco po count, przy równych — alfabetycznie po word:
    table.sort(pairs_list, function(a, b)
        if a.count ~= b.count then
            return a.count > b.count
        end
        return a.word < b.word
    end)
    
    -- Top n:
    local result = {}
    for i = 1, math.min(n, #pairs_list) do
        result[i] = {pairs_list[i].word, pairs_list[i].count}
    end
    return result
end

local text = [[
    Phi space session opened. Phi value high.
    New atom in space. Atom signature recorded.
    Session phi value updated. Phi rises.
]]

local top = top_words(text, 5)
for _, p in ipairs(top) do
    print(p[1], p[2])
end
-- phi      4
-- atom     2
-- session  2
-- space    2
-- value    2
```

Komparator z dwukluczowym sortowaniem: najpierw count malejąco, przy równych count — alfabetycznie. To jest deterministyczne sortowanie (stable-like behavior), dzięki czemu `top_words` daje powtarzalne wyniki.

#### Sprawdzian 5

```lua
-- pivot.lua
local function pivot(events)
    local result = {}
    for _, e in ipairs(events) do
        if result[e.level] == nil then
            result[e.level] = {}
        end
        result[e.level][e.source] = (result[e.level][e.source] or 0) + e.count
    end
    return result
end

local events = {
    {level = "INFO",  source = "scheduler", count = 5},
    {level = "WARN",  source = "lsm",       count = 3},
    {level = "INFO",  source = "scheduler", count = 2},
    {level = "INFO",  source = "lsm",       count = 1},
    {level = "ERROR", source = "scheduler", count = 2},
}

local p = pivot(events)

-- Wypisz uporządkowanie:
local levels = {}
for l in pairs(p) do levels[#levels + 1] = l end
table.sort(levels)

for _, l in ipairs(levels) do
    print(l .. ":")
    local sources = {}
    for s in pairs(p[l]) do sources[#sources + 1] = s end
    table.sort(sources)
    for _, s in ipairs(sources) do
        print("  " .. s .. " = " .. p[l][s])
    end
end
-- ERROR:
--   scheduler = 2
-- INFO:
--   lsm = 1
--   scheduler = 7
-- WARN:
--   lsm = 3
```

Dwa zagnieżdżone idiomy: inicjowanie pod-tabeli (`if result[level] == nil then result[level] = {} end`) plus counter (`(result[level][source] or 0) + count`).

#### Sprawdzian 6

```lua
-- deep_equal.lua
local function deep_equal(a, b)
    -- Pomocnicza funkcja z tabelą "już sprawdzone pary"
    local function helper(x, y, seen)
        if type(x) ~= type(y) then return false end
        if type(x) ~= "table" then
            return x == y
        end
        
        -- Zarejestruj parę przed rekursją (! żeby cykle terminowały)
        if seen[x] and seen[x][y] then
            return true   -- już sprawdzane lub w trakcie sprawdzania = traktuj jako równe
        end
        if not seen[x] then seen[x] = {} end
        seen[x][y] = true
        
        -- Klucze x w y
        for k, v in pairs(x) do
            if not helper(v, y[k], seen) then return false end
        end
        -- Dodatkowe klucze w y
        for k in pairs(y) do
            if x[k] == nil then return false end
        end
        return true
    end
    
    return helper(a, b, {})
end

-- Bez cykli:
print(deep_equal({1, 2, 3}, {1, 2, 3}))                              -- true
print(deep_equal({a = {b = 1}}, {a = {b = 1}}))                      -- true
print(deep_equal({a = {b = 1}}, {a = {b = 2}}))                      -- false

-- Z cyklami:
local x = {n = 1}
x.self = x
local y = {n = 1}
y.self = y
print(deep_equal(x, y))                                              -- true

-- Cykl z różną zawartością:
local p = {n = 1}
p.self = p
local q = {n = 2}
q.self = q
print(deep_equal(p, q))                                              -- false (n=1 vs n=2)

-- Cykl z różnym kształtem:
local r = {n = 1}
r.self = r
local s = {n = 1, extra = "x"}
s.self = s
print(deep_equal(r, s))                                              -- false (extra w s)
```

Trick: `seen[x][y] = true` **przed** rekursją. Gdy w środku rekursji wrócimy do pary `(x, y)`, zwróćmy `true` — to assumption-based reasoning ("zakładamy że są równe; jeśli znajdziemy różnicę gdzie indziej, zwrócimy false). Standardowy algorytm dla równości grafów.

`seen` jest tabelą mapującą `x -> {y -> true, y2 -> true, ...}`. Każde `x` ma własny set partnerów `y`.

#### Sprawdzian 7

```lua
-- get_path.lua
local function get_path(t, path)
    local current = t
    
    -- Iterujemy po segmentach: ".key" lub "[index]"
    -- Wzorzec dopasowuje albo "%w+" (klucz) albo "[%d+]" (indeks)
    
    -- Najpierw znormalizujmy ścieżkę: zamieńmy [N] na .N
    -- Najprostsza implementacja: parsuj segment po segmencie
    
    local pos = 1
    while pos <= #path do
        local key
        local first_char = path:sub(pos, pos)
        
        if first_char == "[" then
            -- Indeks numeryczny
            local end_pos = path:find("]", pos)
            if not end_pos then return nil end
            local idx_str = path:sub(pos + 1, end_pos - 1)
            local idx = tonumber(idx_str)
            if not idx then return nil end
            key = idx
            pos = end_pos + 1
        else
            -- Klucz stringowy
            if first_char == "." then pos = pos + 1 end
            local end_pos = path:find("[%.%[]", pos)
            if not end_pos then end_pos = #path + 1 end
            key = path:sub(pos, end_pos - 1)
            pos = end_pos
        end
        
        if type(current) ~= "table" then return nil end
        current = current[key]
        if current == nil then return nil end
    end
    
    return current
end

-- Test:
local data = {
    sessions = {
        {sig = "abc", atoms = {{phi = 0.7}, {phi = 0.4}}},
        {sig = "def", atoms = {}},
    },
    meta = {version = "1.0"},
}

print(get_path(data, "meta.version"))              -- "1.0"
print(get_path(data, "sessions[1].sig"))           -- "abc"
print(get_path(data, "sessions[1].atoms[2].phi"))  -- 0.4
print(get_path(data, "sessions[2].sig"))           -- "def"
print(get_path(data, "sessions[3].sig"))           -- nil
print(get_path(data, "nonsense.path"))             -- nil
print(get_path(data, "sessions[1].atoms[10].phi")) -- nil
```

Parser stanowy: kursor `pos` skanuje string. Jeśli widzi `[` — czyta indeks numeryczny do `]`. Inaczej — czyta stringowy klucz do następnej kropki lub `[`.

Funkcja `path:find("[%.%[]", pos)` szuka pierwszej `.` lub `[` od pozycji `pos` (klasa `[%.%[]` zawiera dosłowną kropkę i nawias kwadratowy). Gdy nie znajdzie — wracamy `nil`, traktujemy to jako "do końca stringu".

Każde `current = current[key]` może zwrócić `nil` (klucz nie istnieje). Sprawdzamy i wracamy `nil` z funkcji.

**Edge cases:**
- `get_path(t, "")` zwróci `t` (pętla nie wejdzie).
- `get_path(t, ".x")` jest tolerowana (skip kropki).
- Niepoprawny indeks (`"[abc]"`) — `tonumber` zwraca nil → `nil` z funkcji.

---

## Co dalej?

Świetnie. Tabele są opanowane. Następny moduł zagłębia się w funkcje — multiple return values, varargs, closures (już je widziałeś, teraz dokładnie), funkcje wyższego rzędu, partial application, currying.

→ **Moduł 3: Funkcje zaawansowane**
