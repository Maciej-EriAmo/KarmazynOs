# Moduł 1: Fundamenty Lua

> *"Każdy techpriest zaczyna od jednego — od poznania mowy maszyn."*

W tym module poznasz Lua na poziomie wystarczającym, aby pisać proste programy: deklarować zmienne, używać typów podstawowych, sterować przepływem, definiować funkcje. To fundament — kolejne moduły zakładają, że ten materiał masz w pamięci mięśniowej.

**Przewidywany czas:** 4-6 godzin pracy.

**Lekcje:**
1. Środowisko, REPL, pierwszy skrypt
2. Typy i zmienne
3. Stringi i podstawowe operacje
4. Sterowanie przepływem
5. Funkcje — podstawy

Plus **Sprawdzian Modułu 1** — 7 zadań integrujących całość.

---

## Lekcja 1.1: Środowisko, REPL, pierwszy skrypt

### Cel

Po tej lekcji potrafisz: zainstalować Lua 5.4, uruchomić REPL, napisać i uruchomić skrypt z pliku, odczytać argumenty wiersza poleceń.

### Materiał

**Lua 5.4** to obecny stabilny release referencyjnej implementacji. To z nim pracujemy w tym kursie.

#### Instalacja

**Debian / Ubuntu:**
```bash
sudo apt install lua5.4 liblua5.4-dev
```

**Arch Linux (Twój Chromebook):**
```bash
sudo pacman -S lua
```

**Termux (Galaxy A54):**
```bash
pkg install lua54
# Dla Modułu 8+:
pkg install clang make
```

**macOS:**
```bash
brew install lua
```

**Sprawdzenie:**
```bash
$ lua5.4 -v
Lua 5.4.6  Copyright (C) 1994-2023 Lua.org, PUC-Rio
```

(Numer minor może być inny — `5.4.x` cokolwiek to OK.)

#### REPL — interaktywna konsola

```bash
$ lua5.4
Lua 5.4.6  Copyright (C) 1994-2023 Lua.org, PUC-Rio
> print("hello")
hello
> 2 + 2
4
> = 2 ^ 10        -- znak '=' to skrót: "wypisz wartość"
1024.0
> -- komentarz, ignorowany
> 
```

Wyjście z REPL: `Ctrl+D` (Unix) lub `os.exit()`.

#### Pierwszy skrypt

Plik `hello.lua`:

```lua
-- hello.lua
local name = "Maciej"
print("Witaj, " .. name)
print("Lua wersja: " .. _VERSION)
```

Uruchomienie:

```bash
$ lua5.4 hello.lua
Witaj, Maciej
Lua wersja: Lua 5.4
```

Lua nie wymaga `#include`, `import`, deklaracji typów, kompilacji. Plik `.lua` to po prostu tekst, który interpreter wykonuje od góry do dołu.

#### Argumenty wiersza poleceń

W każdym skrypcie dostępna jest globalna tabela `arg`:

```lua
-- args_demo.lua
print("Skrypt: " .. arg[0])
print("Liczba argumentów: " .. #arg)
for i = 1, #arg do
    print("  arg[" .. i .. "] = " .. arg[i])
end
```

```bash
$ lua5.4 args_demo.lua hello world 42
Skrypt: args_demo.lua
Liczba argumentów: 3
  arg[1] = hello
  arg[2] = world
  arg[3] = 42
```

`arg[0]` to nazwa skryptu. `arg[1]` i dalej to argumenty. `#arg` to liczba argumentów (bez `arg[0]`). Wszystkie argumenty są stringami — nawet jeśli wyglądają jak liczby. Konwersję pokażę w Lekcji 1.2.

#### Komentarze

```lua
-- jednoliniowy
print("a")  -- może być na końcu linii

--[[
   blok wieloliniowy
   ze swobodą
]]

--[==[ blok z poziomem 2 — przydatne gdy w środku jest ]] ]==]
```

### Pułapki

**Wersje Lua są niekompatybilne.** Skrypt napisany pod 5.1 niekoniecznie działa na 5.4 (i odwrotnie). Najczęstsze różnice:
- 5.1: `unpack(t)`, 5.2+: `table.unpack(t)`
- 5.1 nie ma `goto`/`continue`
- 5.1 nie ma osobnego `integer` (od 5.3)
- 5.1: `setfenv`, 5.2+: `_ENV`

**Komenda `lua` może wskazywać na różne wersje.** Na Debianie często `lua` to dowiązanie alternatywy — może wskazywać na `lua5.1` lub `lua5.4`. **Zawsze pisz `lua5.4` jawnie** w skryptach init i Makefile'ach.

**`print` to nie wszystko.** `print` dodaje newline i tab między argumentami. Do produkcyjnego wypisywania używaj `io.write`:

```lua
print("a", "b")     -- "a\tb\n"
io.write("a", "b")  -- "ab"  (bez separatora i bez newline)
```

### Zadania

**Zadanie 1.1.1**  
Uruchom REPL i sprawdź ile wynosi `2^53`, `2^53 + 1`, oraz `2^63`. Czy widzisz coś dziwnego? Spróbuj wytłumaczyć (nie szukaj, pomyśl — to klasyczny problem reprezentacji liczb).

**Zadanie 1.1.2**  
Napisz skrypt `info.lua`, który wypisze:
- bieżącą datę i czas (użyj `os.date()`)
- nazwę systemu operacyjnego (zmienna `package.config:sub(1,1)` — `\` na Windows, `/` na Unix; możesz też `os.getenv("OS")` lub `os.getenv("HOME")`)
- wersję Lua (`_VERSION`)
- ile mamy uruchomionego procesora — odczytaj `os.clock()` na początku i na końcu skryptu

**Zadanie 1.1.3**  
Napisz skrypt `sum_args.lua`, który zsumuje wszystkie liczby podane jako argumenty i wypisze wynik. Argumenty są stringami — musisz je skonwertować. Hint do konwersji: jest funkcja `tonumber(s)`.

**Zadanie 1.1.4**  
Napisz skrypt `greet.lua`, który przyjmuje jeden argument (imię) i wypisuje powitanie. Jeśli argument nie został podany — wypisz komunikat błędu na `stderr` (`io.stderr:write(...)`) i zakończ z kodem 1 (`os.exit(1)`).

---

### Rozwiązania

#### Rozwiązanie 1.1.1

```
> = 2^53
9.007199254741e+15
> = 2^53 + 1
9.007199254741e+15
> = 2^53 == 2^53 + 1
true
> = 2^63
9.2233720368548e+18
```

**Dlaczego dziwnie?** `^` w Lua zawsze zwraca `float` (typ `number` z reprezentacją IEEE 754 double). Double ma 52-bitową mantysę plus jeden bit ukryty = 53 bity precyzji. `2^53` jest dokładnie reprezentowalne. `2^53 + 1` już nie — pierwsza liczba "po" `2^53`, którą double potrafi reprezentować, to `2^53 + 2`. Stąd `2^53 == 2^53 + 1` jest `true`.

Aby uzyskać dokładny integer, w Lua 5.3+ używaj operatorów integer (`//`, `<<`) lub literałów heksadecymalnych:

```lua
> = 1 << 53
9007199254740992          -- integer, dokładny
> = (1 << 53) + 1
9007199254740993          -- też dokładny
> = math.type(1 << 53)
"integer"
> = math.type(2^53)
"float"
```

#### Rozwiązanie 1.1.2

```lua
-- info.lua
local t_start = os.clock()

print("Data:        " .. os.date())
print("_VERSION:    " .. _VERSION)
print("Sep:         " .. package.config:sub(1, 1))
print("HOME:        " .. (os.getenv("HOME") or "(nieustawione)"))

-- Symulujemy obciążenie:
local s = 0
for i = 1, 1000000 do s = s + i end

local t_end = os.clock()
print("CPU czas:    " .. (t_end - t_start) .. "s")
print("Suma 1..10^6: " .. s)
```

```
$ lua5.4 info.lua
Data:        Mon May  4 14:32:01 2026
_VERSION:    Lua 5.4
Sep:         /
HOME:        /home/maciej
CPU czas:    0.018127s
Suma 1..10^6: 500000500000
```

Komentarz: `os.getenv("HOME") or "(nieustawione)"` to klasyczny idiom default value — jeśli `os.getenv` zwróci `nil`, weź drugą wartość. Wrócimy do tego w Lekcji 1.4.

#### Rozwiązanie 1.1.3

```lua
-- sum_args.lua
local sum = 0
for i = 1, #arg do
    local n = tonumber(arg[i])
    if n == nil then
        io.stderr:write("Argument '" .. arg[i] .. "' nie jest liczbą\n")
        os.exit(1)
    end
    sum = sum + n
end
print("Suma: " .. sum)
```

```
$ lua5.4 sum_args.lua 1 2 3 4 5
Suma: 15

$ lua5.4 sum_args.lua 1 2 trzy
Argument 'trzy' nie jest liczbą
$ echo $?
1
```

`tonumber(s)` zwraca `nil` gdy konwersja zawiedzie — typowy idiom Lua dla "może się nie udać": funkcja zwraca albo wynik, albo nil.

#### Rozwiązanie 1.1.4

```lua
-- greet.lua
if #arg == 0 then
    io.stderr:write("Użycie: lua5.4 greet.lua <imie>\n")
    os.exit(1)
end

local name = arg[1]
print("Witaj, " .. name .. "!")
```

```
$ lua5.4 greet.lua Maciej
Witaj, Maciej!

$ lua5.4 greet.lua
Użycie: lua5.4 greet.lua <imie>
$ echo $?
1
```

`io.stderr:write` używa składni metody (`:`) — zapis stosowany dla obiektów file. Dokładniej w Lekcji 1.5 i Module 3.

### Sprawdź się

- [ ] Umiem zainstalować Lua 5.4 na moim systemie
- [ ] Umiem uruchomić REPL i wykonać proste obliczenia
- [ ] Umiem zapisać skrypt do pliku i go uruchomić
- [ ] Wiem jak odczytać argumenty wiersza poleceń (`arg`)
- [ ] Wiem jak wypisać na `stderr` i zakończyć skrypt z kodem błędu
- [ ] Rozumiem dlaczego `2^53 == 2^53 + 1` w Lua

---

## Lekcja 1.2: Typy i zmienne

### Cel

Po tej lekcji znasz wszystkie typy podstawowe Lua, rozumiesz różnicę `local` vs globalne, wiesz co znaczy "truthy/falsy" w Lua i potrafisz konwertować między typami.

### Materiał

#### Osiem typów Lua

```lua
print(type(nil))       -- "nil"
print(type(true))      -- "boolean"
print(type(42))        -- "number"
print(type("abc"))     -- "string"
print(type({}))        -- "table"
print(type(print))     -- "function"
print(type(coroutine.create(function() end)))  -- "thread"
-- "userdata" — pojawia się tylko gdy host C wstawi opaque pointer
```

To **wszystkie** typy. Nie ma osobnego `integer`/`float` (to są podtypy `number`), nie ma `array`/`dict` (to są tabele), nie ma `class` (to są tabele z metatable — Moduł 4).

#### `nil`

`nil` to "brak wartości". Domyślna wartość niezdefiniowanej zmiennej. Jedyna wartość typu `nil`.

```lua
local x       -- x to nil
print(x)      -- nil
print(type(x))  -- "nil"

local t = {}
print(t.foo)  -- nil  (klucz nie istnieje = wartość nil)

-- Usuwanie z tabeli:
t.foo = "abc"
t.foo = nil   -- klucz znika
```

#### `boolean`

Tylko dwie wartości: `true` i `false`.

**KRYTYCZNE: w Lua tylko `nil` i `false` są fałszywe.** Wszystko inne — w tym `0`, `""`, `{}` — jest prawdziwe.

```lua
if 0 then print("0 jest true!") end          -- WYPISZE
if "" then print("'' jest true!") end        -- WYPISZE
if {} then print("{} jest true!") end        -- WYPISZE
if nil then print("nigdy") end               -- nie wypisze
if false then print("nigdy") end             -- nie wypisze
```

Pułapka po Pythonie/C/JS: tam `0` jest falsy. W Lua **nie**. Ta różnica wywołała tysiące bugów u programistów przesiadających się z innych języków. Wbij sobie w pamięć: **0 i pusty string są w Lua truthy**.

#### `number`

Domyślnie 64-bit. Od Lua 5.3 jest podział wewnętrzny na `integer` (64-bit signed) i `float` (double IEEE 754). `math.type(x)` mówi który podtyp.

```lua
print(math.type(42))      -- "integer"
print(math.type(42.0))    -- "float"
print(math.type(2^10))    -- "float"  (^ zawsze daje float!)
print(math.type(1024))    -- "integer"
print(math.type(1024 // 1))  -- "integer"  (// to integer division)
```

Operacje:

```lua
-- arytmetyczne
+ - * /        -- standard; / zawsze daje float
//             -- floor division
%              -- modulo
^              -- potęgowanie (zawsze float)

-- bitowe (5.3+, tylko na integer)
& | ~ ~  << >>   -- AND, OR, XOR-binarne, NOT-unarne, lshift, rshift

-- relacyjne
== ~= < <= > >=  -- ~= to nierówność, NIE !=

-- logiczne
and or not       -- nie &&, ||, !
```

**Pułapka 5.3+: `1` i `1.0` to formalnie `==` ale `math.type` różny.**

```lua
print(1 == 1.0)            -- true
print(math.type(1))        -- "integer"
print(math.type(1.0))      -- "float"
print(1 // 1)              -- 1     (integer)
print(1 // 1.0)            -- 1.0   (float — bo jeden z operandów float)
```

#### `string`

Niezmienne, internowane, indeksowane od 1. Operacje:

```lua
local s = "hello"
print(#s)            -- 5  (długość w bajtach!)
print(s:upper())     -- "HELLO"
print(s .. " world") -- "hello world"
print(s == "hello")  -- true (porównanie po wartości)
```

Szczegóły w Lekcji 1.3.

#### `table`, `function`, `thread`, `userdata`

- `table` — szczegóły Moduł 2
- `function` — Lekcja 1.5 i Moduł 3
- `thread` — Moduł 6 (korutyny, *nie* OS thread)
- `userdata` — Moduł 9 (opaque pointer z C)

#### `local` vs globalne — KRYTYCZNE

```lua
x = 10           -- GLOBALNE (zła praktyka)
local y = 20     -- lokalne (dobra praktyka)
```

Globalne zmienne lądują w "tabeli środowiska" (`_ENV`, default `_G`). To znaczy:
- są **widoczne ze wszystkich miejsc** — gigantyczna powierzchnia kolizji nazw
- są **wolniejsze** od lokalnych (lookup w tabeli vs adres na rejestrze)
- **łamią sandboxing** — to przez globalne hostujący skrypt może być atakowany

**Reguła: w 99% przypadków pisz `local`.** Wyjątki to świadome dzielenie stanu między pliki — i tam też lepiej używaj jawnego modułu (Moduł 7).

Zakres `local`:

```lua
local x = 1
do
    local x = 2  -- shadows zewnętrzny x w tym bloku
    print(x)     -- 2
end
print(x)         -- 1
```

#### Konwersje

```lua
-- string -> number:
tonumber("42")       -- 42
tonumber("3.14")     -- 3.14
tonumber("abc")      -- nil
tonumber("0x1F")     -- 31
tonumber("ff", 16)   -- 255  (z bazą)

-- number -> string:
tostring(42)         -- "42"
tostring(3.14)       -- "3.14"

-- automatyczna konwersja w konkatenacji:
print(42 .. "")      -- "42"  (number -> string)
print("3" + 4)       -- 7     (string -> number, gdy wygląda jak liczba)
print("3" + "4")     -- 7
print("abc" + 1)     -- BŁĄD: "attempt to perform arithmetic on a string value"
```

**Pułapka:** automatyczna konwersja działa, ale jest źródłem bugów. W produkcji konwertuj jawnie.

### Pułapki

1. **`0` i `""` są truthy.**
2. **Domyślnie globalne** — zawsze `local`.
3. **`#string`** to długość w **bajtach**, nie znakach. Dla UTF-8 użyj `utf8.len`.
4. **`==` na liczbach mieszanych** (integer/float) — daje `true` dla `1 == 1.0`, ale `math.type` różny.
5. **`nil` w arytmetyce** = błąd. `1 + nil` rzuca exception.
6. **Niezdefiniowana zmienna globalna** zwraca `nil` bez ostrzeżenia. To jest podstawowe źródło literówek.

### Zadania

**Zadanie 1.2.1**  
W REPL spróbuj:
- `print(0 and "a" or "b")`
- `print(nil and "a" or "b")`
- `print(false and "a" or "b")`
- `print(1 and "a" or "b")`

Wyjaśnij każdy wynik. To jest klasyczny idiom Lua "ternary".

**Zadanie 1.2.2**  
Napisz skrypt `types_check.lua`, który dla każdej z wartości `nil`, `true`, `false`, `0`, `""`, `{}`, `1.5`, `"abc"`, `print` wypisze:
- typ (`type()`)
- czy wartość jest truthy (sprawdź przez `if`)

Format wyjścia: `<wartość>: type=<typ>, truthy=<true/false>`

**Zadanie 1.2.3**  
Napisz funkcję `safe_div(a, b)` (jako lokalną), która:
- jeśli `b == 0` — zwraca `nil` i string `"dzielenie przez zero"`
- jeśli `a` lub `b` nie są liczbami — zwraca `nil` i string `"argumenty muszą być liczbami"`
- inaczej zwraca wynik dzielenia

Następnie wywołaj ją kilka razy z różnymi argumentami i wypisz wyniki.

Hint: użyj `type(x) ~= "number"` do walidacji.

**Zadanie 1.2.4**  
Demonstracja `local`: napisz skrypt, w którym jest globalna zmienna `g_count = 0` i lokalna `local l_count = 0`. W bloku `do ... end` zwiększ obie. Po bloku wypisz obie. Wyjaśnij wynik.

---

### Rozwiązania

#### Rozwiązanie 1.2.1

```
> print(0 and "a" or "b")        -- "a"
> print(nil and "a" or "b")      -- "b"
> print(false and "a" or "b")    -- "b"
> print(1 and "a" or "b")        -- "a"
```

**Wyjaśnienie:** Operatory `and`/`or` w Lua zwracają **wartość**, nie boolean.

- `x and y` — jeśli `x` jest falsy (`nil`/`false`), zwraca `x`; inaczej zwraca `y`.
- `x or y` — jeśli `x` jest truthy, zwraca `x`; inaczej zwraca `y`.

Krok po kroku dla `0 and "a" or "b"`:
1. `0 and "a"` — `0` jest **truthy** (krytyczne!), więc zwraca `"a"`.
2. `"a" or "b"` — `"a"` jest truthy, zwraca `"a"`.

Dla `nil and "a" or "b"`:
1. `nil and "a"` — `nil` falsy, zwraca `nil`.
2. `nil or "b"` — `nil` falsy, zwraca `"b"`.

To jest idiom **ternary w Lua**: `cond and a or b` ≈ `cond ? a : b`. **Działa pod warunkiem, że `a` nie jest falsy** — bo wtedy "ternary" pójdzie do `b` mimo że warunek był spełniony. Dlatego ten idiom ma znane pułapki:

```lua
-- Bug:
local x = (i > 0) and false or "ujemne"
-- gdy i > 0 jest true, "and false" zwraca false, "or 'ujemne'" zwraca "ujemne"
-- czyli zawsze dostajemy "ujemne" — nigdy false!
```

W kodzie produkcyjnym preferuj jawny `if/else` gdy `a` może być falsy.

#### Rozwiązanie 1.2.2

```lua
-- types_check.lua
local values = {nil, true, false, 0, "", {}, 1.5, "abc", print}
local labels = {"nil", "true", "false", "0", '""', "{}", "1.5", '"abc"', "print"}
-- Uwaga: tabela nie zachowuje nila w środku gdy ipairs.
-- Robimy to inaczej — przez pary:

local pairs_to_check = {
    {label = "nil",   v = nil},
    {label = "true",  v = true},
    {label = "false", v = false},
    {label = "0",     v = 0},
    {label = '""',    v = ""},
    {label = "{}",    v = {}},
    {label = "1.5",   v = 1.5},
    {label = '"abc"', v = "abc"},
    {label = "print", v = print},
}

for _, item in ipairs(pairs_to_check) do
    local truthy = item.v and true or false
    local t = type(item.v)
    print(string.format("%-8s type=%-10s truthy=%s", item.label, t, tostring(truthy)))
end
```

```
nil      type=nil        truthy=false
true     type=boolean    truthy=true
false    type=boolean    truthy=false
0        type=number     truthy=true
""       type=string     truthy=true
{}       type=table      truthy=true
1.5      type=number     truthy=true
"abc"    type=string     truthy=true
print    type=function   truthy=true
```

Komentarz: pierwsza próba `local values = {nil, true, ...}` ma bug — `nil` w środku tabeli sprawia że `ipairs` może się zatrzymać wcześniej niż chcemy (Lua nie definiuje co robi z nilem w środku tablicy). Dlatego pakujemy każdą wartość w tabelę pomocniczą `{label, v}`. Tabele i ich pułapki — Moduł 2.

`item.v and true or false` to idiom konwersji "cokolwiek na boolean".

#### Rozwiązanie 1.2.3

```lua
-- safe_div.lua
local function safe_div(a, b)
    if type(a) ~= "number" or type(b) ~= "number" then
        return nil, "argumenty muszą być liczbami"
    end
    if b == 0 then
        return nil, "dzielenie przez zero"
    end
    return a / b
end

local function show(a, b)
    local result, err = safe_div(a, b)
    if result then
        print(a .. " / " .. b .. " = " .. result)
    else
        print(a .. " / " .. tostring(b) .. " = BŁĄD: " .. err)
    end
end

show(10, 2)
show(10, 0)
show(10, "abc")
show("a", 5)
show(7, 3)
```

```
10 / 2 = 5.0
10 / 0 = BŁĄD: dzielenie przez zero
10 / abc = BŁĄD: argumenty muszą być liczbami
a / 5 = BŁĄD: argumenty muszą być liczbami
7 / 3 = 2.3333333333333
```

**To jest jeden z najważniejszych idiomów w Lua:** funkcja zwraca albo wynik, albo `nil` plus komunikat błędu. Wywołujący sprawdza czy pierwszy wynik jest truthy. Tak działa `io.open`, `tonumber`, `string.find` i większość biblioteki standardowej.

#### Rozwiązanie 1.2.4

```lua
-- local_vs_global.lua
g_count = 0          -- globalna (uwaga: zła praktyka, ale pokazujemy działanie)
local l_count = 0    -- lokalna do całego pliku

print("Przed do-end: g_count=" .. g_count .. ", l_count=" .. l_count)

do
    g_count = g_count + 1   -- modyfikuje globalną
    l_count = l_count + 1   -- modyfikuje lokalną z zewnętrznego scope
    
    local l_count = 99      -- nowa lokalna, shadows zewnętrzną w tym bloku
    print("W do-end:    g_count=" .. g_count .. ", l_count=" .. l_count)
end

print("Po do-end:   g_count=" .. g_count .. ", l_count=" .. l_count)
```

```
Przed do-end: g_count=0, l_count=0
W do-end:    g_count=1, l_count=99
Po do-end:   g_count=1, l_count=1
```

**Kluczowe obserwacje:**
1. `g_count` modyfikujemy "do góry" (jest globalna, wszędzie widoczna).
2. `l_count = l_count + 1` **bez `local`** — modyfikuje lokalną z zewnętrznego scope (Lua szuka najbliższego widocznego `l_count`, znajduje tę z zewnątrz).
3. `local l_count = 99` **z `local`** — tworzy nową, lokalną do bloku `do ... end`, *cieniuje* (shadowuje) zewnętrzną.
4. Po wyjściu z bloku — wewnętrzna lokalna znika, widać znowu zewnętrzną z wartością 1.

To jest standardowy mechanizm scopu leksykalnego (jak Python, Rust, C++).

### Sprawdź się

- [ ] Umiem wymienić wszystkie 8 typów Lua
- [ ] Wiem dlaczego `0 and "a"` daje `"a"`, nie `false`
- [ ] Pamiętam, że tylko `nil` i `false` są falsy
- [ ] Wiem czemu domyślnie pisać `local`
- [ ] Umiem skonwertować string na number i odwrotnie
- [ ] Znam idiom "zwróć wynik albo nil, errmsg"

---

## Lekcja 1.3: Stringi i podstawowe operacje

### Cel

Poznajesz literały stringów, funkcje biblioteki `string`, formatowanie, podstawy patternów Lua (i czym różnią się od regex).

### Materiał

#### Literały

```lua
local a = "podwójne"
local b = 'pojedyncze'  -- równoważne
local c = "z escape: \n nowa linia, \t tab, \\ backslash, \" cudzysłów"
local d = [[
   long string
   bez escape
   z zachowaniem białych znaków
]]
local e = [==[
   jeśli wewnątrz jest ]] albo [[, użyj poziomu z =====
]==]
```

#### Konkatenacja i długość

```lua
local s = "hello" .. " " .. "world"
print(s)     -- "hello world"
print(#s)    -- 11   (długość w BAJTACH, nie znakach!)

-- UTF-8:
local pl = "żółć"
print(#pl)              -- 8  (8 bajtów)
print(utf8.len(pl))     -- 4  (4 znaki Unicode)
```

#### `string.format`

Działa jak `printf` w C:

```lua
print(string.format("Phi: %.3f, sig: %s, epoch: %d", 0.7, "abc", 42))
-- "Phi: 0.700, sig: abc, epoch: 42"

print(string.format("hex: %08x", 255))   -- "hex: 000000ff"
print(string.format("%5d %5d", 1, 100))  -- "    1   100"
print(string.format("%-10s|", "abc"))    -- "abc       |"
print(string.format("%q", 'he said "hi"'))  -- '"he said \"hi\""'  (cudzysłowy escape'owane)
```

Specyfikatory: `%d` (integer), `%f` (float), `%.Nf` (float z precyzją), `%s` (string), `%x` (hex), `%q` (quoted string), `%%` (znak `%`).

#### Składnia `:` na stringach

Każdy string ma "metody" przez metatable string. Te dwie linie są równoważne:

```lua
print(string.upper("hello"))   -- "HELLO"
print(("hello"):upper())       -- "HELLO"  -- składnia metody
```

Wszystkie funkcje z `string.*` można wołać tak: `s:func(args)` zamiast `string.func(s, args)`.

#### Najczęstsze funkcje

```lua
local s = "Hello, World!"

-- Wielkość liter:
s:upper()                  -- "HELLO, WORLD!"
s:lower()                  -- "hello, world!"

-- Substring (1-indexed, oba końce inclusive):
s:sub(1, 5)               -- "Hello"
s:sub(8)                  -- "World!"  (od 8 do końca)
s:sub(-6)                 -- "World!"  (ujemny indeks = od końca)
s:sub(-6, -2)             -- "World"

-- Powtarzanie:
("ab"):rep(3)             -- "ababab"
("ab"):rep(3, "-")        -- "ab-ab-ab"  (5.3+, separator)

-- Reverse:
s:reverse()               -- "!dlroW ,olleH"

-- Bajty <-> znaki:
string.byte("A")          -- 65
string.char(65, 66, 67)   -- "ABC"

-- Trimowanie (nie ma natywnej!):
local function trim(s) return s:match("^%s*(.-)%s*$") end
print(trim("  hello  "))  -- "hello"
```

#### Patterns vs regex

Lua **nie ma regex** w bibliotece standardowej. Ma własny mechanizm — **wzorce Lua** (Lua patterns) — uboższy i prostszy niż regex, ale szybki.

Klasy znaków:
```
%a  litera
%A  nie-litera
%d  cyfra
%D  nie-cyfra
%s  whitespace
%S  nie-whitespace
%w  alfanumeryczny
%W  nie-alfanumeryczny
%p  znak interpunkcyjny
.   dowolny znak (jak w regex)
```

Kwantyfikatory:
```
+   1 lub więcej
*   0 lub więcej
-   0 lub więcej, ale lazy (najkrótsze dopasowanie!)
?   0 lub 1
```

**Brak `{n,m}`, `|`, lookahead, backreferences. Bardzo proste, bardzo szybkie.**

Kotwice:
```
^   początek
$   koniec
```

Grupowanie (capture):
```
(...) — przechwyć grupę
```

Funkcje:

```lua
-- string.find(s, pattern) -> start_pos, end_pos, captures...
local s = "Phi: 0.745"
print(s:find("Phi"))                      -- 1   3
print(s:find("(%d+%.%d+)"))               -- 6   10  "0.745"

-- string.match(s, pattern) -> capture (or whole match if no captures)
print(s:match("Phi: (.+)"))               -- "0.745"
print(s:match("(%d+)%.(%d+)"))            -- "0"    "745"

-- string.gmatch(s, pattern) -> iterator
for word in ("ala ma kota"):gmatch("%S+") do
    print(word)
end
-- "ala", "ma", "kota"

-- string.gsub(s, pattern, replacement) -> new_s, count
print(("ala ma kota"):gsub("a", "A"))     -- "AlA mA kotA"   4
print(("phi=0.7"):gsub("(%w+)=(%S+)", "%2=%1"))  -- "0.7=phi"   1
-- (%1, %2 w replacement = backreference do capture)

-- gsub z funkcją:
local result = ("h e l l o"):gsub("%a", function(c) return c:upper() end)
print(result)                             -- "H E L L O"
```

#### Pułapki patternów

1. **`%` zamiast `\` jako escape.** `%.` to dosłowna kropka (nie regex `\.`).
2. **Brak alternatywy `|`.** Trzeba kilka wzorców albo set `[abc]`.
3. **`-` to lazy quantifier**, nie zakres! Zakres pisze się `[a-z]`.
4. **Magiczne znaki**: `( ) . % + - * ? [ ] ^ $`. Aby dopasować dosłownie, escape przez `%`.

```lua
print(("3.14"):find("."))       -- 1, 1   (! kropka pasuje do każdego znaku)
print(("3.14"):find("%."))      -- 2, 2   (escape — pasuje do dosłownej kropki)
```

### Pułapki

1. `#string` w bajtach — nie używaj do UTF-8 length.
2. Stringi są **immutable** — `s = s .. "x"` tworzy nowy string. W pętli to O(n²)! Używaj `table.concat` (Moduł 2).
3. Patterny Lua nie są regex. Nie próbuj wkleić wzorca z PHP/Pythona.
4. `find` zwraca pozycje, `match` zwraca capture'y. Nie pomyl.

### Zadania

**Zadanie 1.3.1**  
Napisz funkcję `format_phi(p)`, która zwraca string `"phi=X.XXX"` (3 miejsca po przecinku) dla liczby `p`. Test: `format_phi(0.7)` = `"phi=0.700"`, `format_phi(0.74521)` = `"phi=0.745"`.

**Zadanie 1.3.2**  
Napisz funkcję `parse_phi(s)`, która z stringa typu `"phi=0.745"` wyciąga liczbę `0.745` jako `number`. Jeśli format niepoprawny — zwróć `nil, "zły format"`.

**Zadanie 1.3.3**  
Napisz funkcję `count_words(s)`, która zlicza słowa w stringu (słowo = ciąg znaków alfanumerycznych). Test: `count_words("ala ma 3 koty i 2 psy")` = 7.

**Zadanie 1.3.4**  
Napisz funkcję `slugify(s)`, która zamienia tytuł na "slug": wszystko lowercase, spacje zamienione na `-`, niealfabetyczne znaki usunięte. Test: `slugify("Hello, World!")` = `"hello-world"`.

Hint: użyj `gsub` dwa razy, raz dla nie-słownych znaków, raz dla spacji.

**Zadanie 1.3.5**  
Napisz funkcję `mask_pii(s)`, która zamienia w stringu wszystkie ciągi 4+ cyfr na `****`. Test: `mask_pii("PESEL 12345678901, tel 600100200")` = `"PESEL ****, tel ****"`.

---

### Rozwiązania

#### Rozwiązanie 1.3.1

```lua
-- format_phi.lua
local function format_phi(p)
    return string.format("phi=%.3f", p)
end

print(format_phi(0.7))      -- phi=0.700
print(format_phi(0.74521))  -- phi=0.745
print(format_phi(1.0))      -- phi=1.000
```

#### Rozwiązanie 1.3.2

```lua
-- parse_phi.lua
local function parse_phi(s)
    local num = s:match("^phi=(%-?%d+%.?%d*)$")
    if not num then
        return nil, "zły format"
    end
    return tonumber(num)
end

print(parse_phi("phi=0.745"))    -- 0.745
print(parse_phi("phi=1"))        -- 1.0
print(parse_phi("phi=-0.3"))     -- -0.3
print(parse_phi("foo=bar"))      -- nil   "zły format"
print(parse_phi("phi=abc"))      -- nil   "zły format"
```

Wzorzec `^phi=(%-?%d+%.?%d*)$`:
- `^` — początek stringu
- `phi=` — dosłownie
- `(...)` — capture
- `%-?` — opcjonalny minus (escape, bo `-` jest magiczne)
- `%d+` — jedna lub więcej cyfr
- `%.?` — opcjonalna kropka (escape!)
- `%d*` — zero lub więcej cyfr po kropce
- `$` — koniec stringu

Dlaczego `not num` zamiast `num == nil`: gdy `match` nie znajdzie, zwraca `nil`. `not nil` = `true`. Idiomatyczne.

#### Rozwiązanie 1.3.3

```lua
-- count_words.lua
local function count_words(s)
    local count = 0
    for _ in s:gmatch("%w+") do
        count = count + 1
    end
    return count
end

print(count_words("ala ma 3 koty i 2 psy"))     -- 7
print(count_words(""))                          -- 0
print(count_words("   "))                       -- 0
print(count_words("jedno"))                     -- 1
print(count_words("a, b, c"))                   -- 3
```

`for _ in iter() do ... end` — zignoruj wartość iteracji, liczy się sama iteracja. `_` to konwencja "nieinteresująca zmienna".

#### Rozwiązanie 1.3.4

```lua
-- slugify.lua
local function slugify(s)
    s = s:lower()
    s = s:gsub("[^%w%s]", "")     -- usuń wszystko poza alfanumerycznym i spacją
    s = s:gsub("%s+", "-")        -- jedna lub więcej spacji -> jeden myślnik
    s = s:gsub("^%-+", ""):gsub("%-+$", "")  -- trim myślników na końcach
    return s
end

print(slugify("Hello, World!"))                 -- "hello-world"
print(slugify("  Wiele   spacji  "))            -- "wiele-spacji"
print(slugify("HollyScriptSanctum 1.0!"))       -- "hollyscriptsanctum-10"
print(slugify("---test---"))                    -- "test"
```

`[^%w%s]` to klasa znaków: `^` (NIE) `%w` (alfanumeryczne) `%s` (whitespace) — czyli "wszystko poza alfanumerycznym i whitespace". `gsub` zwraca dwa wyniki (string i count); my bierzemy tylko pierwszy.

#### Rozwiązanie 1.3.5

```lua
-- mask_pii.lua
local function mask_pii(s)
    return (s:gsub("%d%d%d%d+", "****"))
end

print(mask_pii("PESEL 12345678901, tel 600100200"))
-- "PESEL ****, tel ****"
print(mask_pii("Roczna data: 2026, kod 1234"))
-- "Roczna data: ****, kod ****"
print(mask_pii("Małe liczby: 12, 99, 100"))
-- "Małe liczby: 12, 99, 100"  (mniej niż 4 cyfry — bez zmian)
```

Wzorzec `%d%d%d%d+` znaczy "cyfra, cyfra, cyfra, jedna lub więcej cyfr" = co najmniej 4 cyfry pod rząd.

Otaczające nawiasy `return (s:gsub(...))` — bo `gsub` zwraca dwie wartości, a nawiasy obcinają do pierwszej. To jest częsty idiom: `(f())` = "weź tylko pierwszy wynik".

### Sprawdź się

- [ ] Umiem napisać literał long-string (`[[...]]`)
- [ ] Wiem co znaczy `%d`, `%s`, `%w`, `%a`, `%p`
- [ ] Pamiętam, że `%.` to dosłowna kropka, a `.` to dowolny znak
- [ ] Wiem czemu `#string` to liczba bajtów
- [ ] Znam różnicę między `find` i `match`
- [ ] Wiem jak otoczyć wywołanie nawiasami żeby wziąć tylko pierwszy wynik

---

## Lekcja 1.4: Sterowanie przepływem

### Cel

Znasz wszystkie konstrukcje sterujące: `if`/`elseif`/`else`, `while`, `repeat`/`until`, numeric `for`, `break`, `goto`. Rozumiesz idiomy z `and`/`or`.

### Materiał

#### `if`/`elseif`/`else`

```lua
if phi > 0.9 then
    print("bardzo wysokie")
elseif phi > 0.5 then
    print("wysokie")
elseif phi > 0.1 then
    print("średnie")
else
    print("niskie")
end
```

`then` jest obowiązkowe (nie ma składni `if cond: ...` jak w Pythonie). Brak nawiasów wokół warunku (jak w Pythonie/Ruby, w odróżnieniu od C/Java).

Pamiętaj: tylko `nil` i `false` są fałszywe. Sprawdzanie typu:

```lua
if x then ... end           -- prawda dla wszystkiego poza nil/false
if x ~= nil then ... end    -- jawnie tylko nie-nil (false jest OK)
if type(x) == "number" then ... end  -- konkretny typ
```

#### `while`

```lua
local i = 1
while i <= 10 do
    print(i)
    i = i + 1
end
```

Klasycznie. Sprawdza warunek na początku.

#### `repeat`/`until`

```lua
local n = 0
repeat
    n = n + 1
    print(n)
until n >= 5
```

Sprawdza warunek **na końcu** (jak `do-while` w C). **Pułapka:** zmienne lokalne zadeklarowane w bloku `repeat ... until` są **widoczne w warunku** `until`:

```lua
repeat
    local line = io.read()
until line == "quit"   -- 'line' tutaj widoczne!
```

To jedyna konstrukcja, w której scope rozszerza się poza końcowy `end`. Specyficznie po to, by można było użyć w warunku zmiennej z bloku.

#### Numeric `for`

```lua
for i = 1, 10 do print(i) end          -- 1, 2, ..., 10
for i = 1, 10, 2 do print(i) end       -- 1, 3, 5, 7, 9
for i = 10, 1, -1 do print(i) end      -- 10, 9, ..., 1
for i = 1, 0 do print(i) end           -- nigdy (start > stop, step domyślnie 1)
```

Składnia: `for i = start, stop, step do ... end`. `step` opcjonalny (domyślnie 1). Pętla idzie **inkluzywnie** do `stop`.

Zmienna pętli (`i`) jest lokalna do pętli — nie widać jej po `end`.

#### Generic `for` (zapowiedź)

```lua
for k, v in pairs(t) do print(k, v) end       -- po wszystkich kluczach
for i, v in ipairs(t) do print(i, v) end      -- po sekwencji
```

Szczegóły w Module 2 (tabele).

#### `break`

```lua
for i = 1, 100 do
    if i * i > 50 then break end
    print(i)
end
-- 1, 2, 3, 4, 5, 6, 7
```

Wychodzi z najbliższej pętli.

#### Brak `continue` — `goto continue`

Lua **nie ma** `continue`. Idiom z `goto` (5.2+):

```lua
for i = 1, 10 do
    if i % 2 == 0 then goto next_iter end
    print(i)
    ::next_iter::
end
-- 1, 3, 5, 7, 9
```

`::label::` — definicja etykiety. `goto label` — skok. Etykieta `::next_iter::` na końcu pętli emuluje `continue`.

W produkcyjnym Lua czasem widać alternatywę przez `if`:

```lua
for i = 1, 10 do
    if i % 2 ~= 0 then
        print(i)
    end
end
```

Stylistycznie cleaniejsze gdy "pomijanie" to większość przypadków.

#### Idiomy z `and`/`or`

**Default value:**

```lua
local function greet(name)
    name = name or "Anonim"
    print("Cześć " .. name)
end

greet("Maciej")    -- "Cześć Maciej"
greet()            -- "Cześć Anonim"
```

`name = name or "Anonim"` — jeśli `name` jest `nil`/`false`, wstaw default.

**Validation guard:**

```lua
local x = some_func()
x = type(x) == "number" and x or 0   -- konwersja na 0 jeśli nie liczba
-- ALE: nie działa gdy default też może być falsy! Patrz Lekcja 1.2 zad. 1.
```

**Short-circuit dla bezpieczeństwa:**

```lua
if t and t.atoms and t.atoms[1] then
    process(t.atoms[1])
end
-- Bezpieczne: jeśli t == nil, nie próbuje t.atoms
```

### Pułapki

1. **Brak nawiasów wokół warunku** — to nie błąd, to składnia Lua.
2. **`repeat-until` ma rozszerzony scope** w warunku.
3. **`for i = 1, n do`** — `n` jest **inkluzywne**.
4. **Zmienne pętli** są lokalne, nie próbuj ich modyfikować w sposób oczekujący że pętla "to złapie" — Lua iteruje po wartościach początkowych, nie po zmiennej.
5. **Brak `continue`** — używaj `goto` lub przekształć logikę.

### Zadania

**Zadanie 1.4.1** — FizzBuzz  
Napisz skrypt, który wypisuje liczby od 1 do 100, ale:
- dla wielokrotności 3 wypisuje `"Fizz"`
- dla wielokrotności 5 wypisuje `"Buzz"`
- dla wielokrotności obu — `"FizzBuzz"`

**Zadanie 1.4.2** — Suma cyfr  
Napisz funkcję `sum_digits(n)`, która liczy sumę cyfr liczby naturalnej. Test: `sum_digits(12345)` = 15.

Hint: w pętli `n = n // 10`, suma += `n % 10`.

**Zadanie 1.4.3** — Liczby pierwsze  
Napisz funkcję `primes(n)`, która zwraca liczbę liczb pierwszych mniejszych lub równych `n`. (Sam zwrot tabeli liczb zostawiamy na Moduł 2; tu tylko liczba.)

Test: `primes(10)` = 4 (czyli 2, 3, 5, 7), `primes(100)` = 25.

**Zadanie 1.4.4** — Default value  
Napisz funkcję `clamp(x, lo, hi)`, która ogranicza `x` do przedziału `[lo, hi]`. `lo` ma domyślnie 0, `hi` ma domyślnie 1.

Test: `clamp(0.5)` = 0.5, `clamp(2)` = 1, `clamp(-1)` = 0, `clamp(50, 0, 100)` = 50.

**Zadanie 1.4.5** — Pierwsza liczba spełniająca warunek  
Napisz funkcję `first_match(start, predicate)`, która zaczynając od `start` zwraca pierwszą liczbę dla której `predicate(n)` jest prawdą.

Test: `first_match(1, function(n) return n*n > 1000 end)` = 32.

---

### Rozwiązania

#### Rozwiązanie 1.4.1

```lua
-- fizzbuzz.lua
for i = 1, 100 do
    if i % 15 == 0 then
        print("FizzBuzz")
    elseif i % 3 == 0 then
        print("Fizz")
    elseif i % 5 == 0 then
        print("Buzz")
    else
        print(i)
    end
end
```

Klasyczne. **Sprawdzaj `% 15` PIERWSZE** — bo każda wielokrotność 15 jest też wielokrotnością 3 i 5, więc gdyby `% 3` było pierwsze, nigdy nie dotarłbyś do FizzBuzz.

#### Rozwiązanie 1.4.2

```lua
-- sum_digits.lua
local function sum_digits(n)
    if n < 0 then n = -n end
    local sum = 0
    while n > 0 do
        sum = sum + (n % 10)
        n = n // 10
    end
    return sum
end

print(sum_digits(12345))     -- 15
print(sum_digits(0))         -- 0
print(sum_digits(99))        -- 18
print(sum_digits(-42))       -- 6
print(sum_digits(1000000))   -- 1
```

`//` to integer division (5.3+). Na Lua 5.1/5.2 musiałbyś `math.floor(n/10)`.

#### Rozwiązanie 1.4.3

```lua
-- primes.lua
local function is_prime(n)
    if n < 2 then return false end
    if n < 4 then return true end       -- 2, 3
    if n % 2 == 0 then return false end -- parzyste > 2
    local i = 3
    while i * i <= n do
        if n % i == 0 then return false end
        i = i + 2
    end
    return true
end

local function primes(n)
    local count = 0
    for i = 2, n do
        if is_prime(i) then
            count = count + 1
        end
    end
    return count
end

print(primes(10))     -- 4
print(primes(100))    -- 25
print(primes(1000))   -- 168
```

`is_prime` ma 3 optymalizacje:
1. Liczby < 2 nie są pierwsze.
2. 2 i 3 są pierwsze (specjalny przypadek).
3. Sprawdzamy tylko nieparzyste dzielniki, do `√n` (warunek `i*i <= n` jest tańszy niż `math.sqrt(n)` i nie wprowadza floatów).

#### Rozwiązanie 1.4.4

```lua
-- clamp.lua
local function clamp(x, lo, hi)
    lo = lo or 0
    hi = hi or 1
    if x < lo then return lo end
    if x > hi then return hi end
    return x
end

print(clamp(0.5))            -- 0.5
print(clamp(2))              -- 1
print(clamp(-1))             -- 0
print(clamp(50, 0, 100))     -- 50
print(clamp(150, 0, 100))    -- 100
print(clamp(-5, -10, 10))    -- -5
```

`lo = lo or 0` to klasyczny idiom default value. Działa **tylko** gdy default nie może być falsy (0 jest truthy w Lua, więc OK; ale gdyby ktoś chciał default `false` — trzeba inaczej).

Bezpieczniejsza forma dla wszystkich przypadków:

```lua
if lo == nil then lo = 0 end
if hi == nil then hi = 1 end
```

Dla naszego use case'u (liczbowy clamp) — `or` wystarcza.

#### Rozwiązanie 1.4.5

```lua
-- first_match.lua
local function first_match(start, predicate)
    local n = start
    while not predicate(n) do
        n = n + 1
    end
    return n
end

print(first_match(1, function(n) return n*n > 1000 end))    -- 32
print(first_match(1, function(n) return n % 7 == 0 end))    -- 7
print(first_match(100, function(n) return n % 17 == 0 end)) -- 102
```

To pierwszy raz, gdy widzisz **funkcję jako argument**. Lua traktuje funkcje jako first-class values (jak zmienne). Szczegóły w Lekcji 1.5 i Module 3.

`function(n) return ... end` to **anonimowa** funkcja (lambda). Można ją przypisać do zmiennej albo przekazać bezpośrednio.

### Sprawdź się

- [ ] Umiem napisać `if/elseif/else`
- [ ] Wiem czemu sprawdzam `% 15` przed `% 3` w FizzBuzz
- [ ] Pamiętam, że `repeat-until` ma rozszerzony scope w warunku
- [ ] Umiem napisać `goto continue` idiom
- [ ] Znam idiom `name = name or "default"`
- [ ] Wiem jak przekazać funkcję jako argument

---

## Lekcja 1.5: Funkcje — podstawy

### Cel

Definiujesz funkcje (lokalne i jako wartości), rozumiesz mismatch parametrów, używasz rekursji, znasz różnicę między function statement i function expression.

### Materiał

#### Definicja funkcji

```lua
-- Function statement (najczęstsza forma):
local function add(a, b)
    return a + b
end

-- Function expression (równoważne):
local add = function(a, b)
    return a + b
end

-- Te dwie formy są semantycznie podobne, ale NIE identyczne:
-- function statement pozwala na rekursję, expression NIE pozwala
-- (chyba że osobno zadeklarujesz local).
```

Różnica między tymi dwoma:

```lua
-- Działa (function statement):
local function fact(n)
    if n <= 1 then return 1 end
    return n * fact(n - 1)   -- 'fact' widoczne wewnątrz
end

-- NIE działa (function expression):
local fact = function(n)
    if n <= 1 then return 1 end
    return n * fact(n - 1)   -- ! 'fact' NIE jest jeszcze przypisane
end                          -- gdy ciało funkcji się definiuje
-- (przy wywołaniu fact(5) -> "attempt to call a nil value")

-- Aby działało, dwie linie:
local fact
fact = function(n)
    if n <= 1 then return 1 end
    return n * fact(n - 1)
end
```

To jest niuans, który łapie wielu początkujących. **Reguła kciuka: dla rekurencyjnych funkcji używaj `local function`.**

#### Mismatch parametrów

Lua **nigdy** nie rzuca błędu z powodu mismatch liczby argumentów:

```lua
local function f(a, b, c)
    print(a, b, c)
end

f(1)            -- 1   nil   nil
f(1, 2)         -- 1   2     nil
f(1, 2, 3, 4)   -- 1   2     3       (4 odrzucone!)
```

Brakujące parametry są `nil`. Nadmiarowe — odrzucone. **To znaczy, że nie istnieje "funkcja n-argumentowa" w sensie sygnatury — każda funkcja przyjmuje dowolnie wiele argumentów.**

Dla varargs (`...`) — Moduł 3.

#### Multiple return

```lua
local function divmod(a, b)
    return a // b, a % b
end

local q, r = divmod(17, 5)
print(q, r)    -- 3   2

-- Tylko pierwszy wynik (gdy mniej zmiennych):
local q = divmod(17, 5)
print(q)       -- 3   (r zignorowane)

-- Brakujące = nil:
local q, r, x = divmod(17, 5)
print(q, r, x)  -- 3   2   nil
```

Szczegóły rozwijania wielu wyników — Moduł 3.

#### Funkcja jako wartość

```lua
-- Funkcja w zmiennej:
local f = print
f("hello")    -- "hello"

-- Funkcja jako argument:
local function apply(fn, x)
    return fn(x)
end
print(apply(math.sqrt, 16))   -- 4.0

-- Funkcja zwracająca funkcję:
local function multiplier(n)
    return function(x) return x * n end
end

local triple = multiplier(3)
print(triple(7))    -- 21
```

To ostatnie to **closure** — funkcja, która "zapamiętała" wartość spoza siebie (`n` zewnętrzne). Pełne omówienie w Module 3.

#### Wczesny return

```lua
local function classify(n)
    if n < 0 then return "ujemne" end
    if n == 0 then return "zero" end
    if n < 10 then return "małe" end
    return "duże"
end

print(classify(-5))    -- "ujemne"
print(classify(0))     -- "zero"
print(classify(7))     -- "małe"
print(classify(100))   -- "duże"
```

Idiom guard clauses jest typowy. Lua nie ma problemu z wieloma `return`.

**Pułapka:** `return` musi być **ostatnim statementem w bloku**:

```lua
local function f()
    return 1
    print("nigdy")   -- BŁĄD składni: "<eof> expected near 'print'"
end
```

Aby obejść (rzadko potrzebne):

```lua
local function f()
    do return 1 end
    print("dotrzemy?")   -- nie, ale parser przechodzi
end
```

#### Wzajemna rekursja — forward declaration

```lua
-- BŁĄD:
local function is_even(n)
    if n == 0 then return true end
    return is_odd(n - 1)         -- is_odd jeszcze nie istnieje!
end

local function is_odd(n)
    if n == 0 then return false end
    return is_even(n - 1)
end
```

Naprawa:

```lua
-- Forward declaration:
local is_even, is_odd

is_even = function(n)
    if n == 0 then return true end
    return is_odd(n - 1)
end

is_odd = function(n)
    if n == 0 then return false end
    return is_even(n - 1)
end

print(is_even(4))    -- true
print(is_odd(7))     -- true
```

### Pułapki

1. **`function f()` bez `local`** — globalna! Zawsze `local function`.
2. **Function expression vs statement** — różnica przy rekursji.
3. **`return` musi być ostatnim w bloku.**
4. **Mismatch argumentów** nie rzuca błędu — łatwo nie zauważyć literówki.
5. **Wzajemna rekursja** wymaga forward declaration.

### Zadania

**Zadanie 1.5.1**  
Napisz dwie wersje silni:
- `factorial_rec(n)` — rekurencyjna
- `factorial_iter(n)` — iteracyjna (pętla)

Porównaj wynik dla `n = 0, 1, 5, 10, 20`. Zwróć uwagę na typ wyniku (integer/float?).

**Zadanie 1.5.2**  
Napisz funkcję `power(base, exp)` która liczy `base^exp` **bez** używania operatora `^`. Dla integer exp >= 0. Test: `power(2, 10)` = 1024.

**Zadanie 1.5.3**  
Napisz funkcję `compose(f, g)` zwracającą nową funkcję `h(x) = f(g(x))`. Test:

```lua
local plus_one = function(x) return x + 1 end
local times_two = function(x) return x * 2 end
local f = compose(plus_one, times_two)
print(f(3))    -- 7    (3*2 + 1)
```

**Zadanie 1.5.4**  
Napisz funkcję `gcd(a, b)` (największy wspólny dzielnik) algorytmem Euklidesa. Iteracyjna. Test: `gcd(12, 18)` = 6, `gcd(100, 75)` = 25.

**Zadanie 1.5.5**  
Napisz funkcję `is_palindrome(s)` zwracającą czy string jest palindromem. Działa dla ASCII. Test: `is_palindrome("kajak")` = true, `is_palindrome("Anna")` = false (case sensitive — `A` != `a`).

---

### Rozwiązania

#### Rozwiązanie 1.5.1

```lua
-- factorial.lua
local function factorial_rec(n)
    if n <= 1 then return 1 end
    return n * factorial_rec(n - 1)
end

local function factorial_iter(n)
    local result = 1
    for i = 2, n do
        result = result * i
    end
    return result
end

for _, n in ipairs({0, 1, 5, 10, 20}) do
    local r = factorial_rec(n)
    local i = factorial_iter(n)
    print(string.format("%2d!  rec=%-25d iter=%-25d type=%s",
        n, r, i, math.type(r)))
end
```

```
 0!  rec=1                         iter=1                         type=integer
 1!  rec=1                         iter=1                         type=integer
 5!  rec=120                       iter=120                       type=integer
10!  rec=3628800                   iter=3628800                   type=integer
20!  rec=2432902008176640000       iter=2432902008176640000       type=integer
```

20! to ~2.4e18, mieści się w 64-bit signed integer. 21! już nie — przepełnienie. W Lua 5.4 integer ma well-defined wrap-around (zmierza w stronę ujemnych). Aby wykryć — Moduł 5 (error handling).

#### Rozwiązanie 1.5.2

```lua
-- power.lua
local function power(base, exp)
    if exp < 0 then return nil, "ujemny wykładnik" end
    local result = 1
    for _ = 1, exp do
        result = result * base
    end
    return result
end

print(power(2, 10))   -- 1024
print(power(3, 5))    -- 243
print(power(5, 0))    -- 1
print(power(2, -1))   -- nil   "ujemny wykładnik"
```

`for _ = 1, exp` — ignorujemy zmienną pętli, używamy `_` (konwencja).

Wersja bardziej "matematyczna" — szybkie potęgowanie:

```lua
local function power_fast(base, exp)
    if exp < 0 then return nil, "ujemny wykładnik" end
    local result = 1
    while exp > 0 do
        if exp % 2 == 1 then result = result * base end
        base = base * base
        exp = exp // 2
    end
    return result
end
```

O(log exp) zamiast O(exp). Klasyczny algorytm "exponentiation by squaring".

#### Rozwiązanie 1.5.3

```lua
-- compose.lua
local function compose(f, g)
    return function(x) return f(g(x)) end
end

local plus_one = function(x) return x + 1 end
local times_two = function(x) return x * 2 end

local f = compose(plus_one, times_two)
print(f(3))    -- 7

local g = compose(times_two, plus_one)
print(g(3))    -- 8

-- Łańcuch:
local h = compose(plus_one, compose(times_two, plus_one))
print(h(3))    -- ((3+1)*2)+1 = 9
```

To jest **closure**: zwracana funkcja "pamięta" `f` i `g` z otaczającego scope. Moduł 3 omawia closures w detalach.

#### Rozwiązanie 1.5.4

```lua
-- gcd.lua
local function gcd(a, b)
    if a < 0 then a = -a end
    if b < 0 then b = -b end
    while b ~= 0 do
        a, b = b, a % b
    end
    return a
end

print(gcd(12, 18))     -- 6
print(gcd(100, 75))    -- 25
print(gcd(7, 13))      -- 1
print(gcd(0, 5))       -- 5
print(gcd(-12, 18))    -- 6
```

`a, b = b, a % b` — **multiple assignment**. Prawe strony obliczane są **przed** przypisaniem, więc nie potrzeba `temp`. To bardzo idiomatyczne dla Lua i jeden z atutów języka.

#### Rozwiązanie 1.5.5

```lua
-- palindrome.lua
local function is_palindrome(s)
    local n = #s
    for i = 1, n // 2 do
        if s:sub(i, i) ~= s:sub(n - i + 1, n - i + 1) then
            return false
        end
    end
    return true
end

print(is_palindrome("kajak"))    -- true
print(is_palindrome("Anna"))     -- false
print(is_palindrome("anna"))     -- true
print(is_palindrome(""))         -- true (pusty jest palindromem)
print(is_palindrome("a"))        -- true
print(is_palindrome("ab"))       -- false
```

Iterujemy do połowy stringu. Dla każdego znaku sprawdzamy lustrzane dopasowanie. `s:sub(i, i)` zwraca pojedynczy znak na pozycji `i`.

Wersja alternatywna z `reverse`:

```lua
local function is_palindrome(s)
    return s == s:reverse()
end
```

Krótsza, ale tworzy nowy string (kosztowniejsza dla długich). Pierwsza wersja jest O(n/2), druga O(n) plus alokacja.

### Sprawdź się

- [ ] Wiem czemu używać `local function` zamiast `local f = function`
- [ ] Pamiętam, że Lua nie sprawdza liczby argumentów
- [ ] Umiem zwrócić wiele wartości
- [ ] Umiem przekazać funkcję jako argument
- [ ] Wiem co to closure (intuicyjnie — szczegóły w Module 3)
- [ ] Umiem napisać wzajemnie rekurencyjne funkcje przez forward declaration

---

## Sprawdzian Modułu 1

Siedem zadań integrujących całość. Spróbuj rozwiązać wszystkie zanim spojrzysz na rozwiązania. To jest twoja "egzamin" — gdy je rozwiążesz, masz fundamenty Lua.

### Zadania

**Sprawdzian 1**  
Napisz skrypt `temp_convert.lua` — konwerter temperatur. Przyjmuje argumenty: `<wartość> <z> <na>`, gdzie `z` i `na` to `C`, `F` lub `K`. Konwertuje i wypisuje wynik z dokładnością do 2 miejsc po przecinku. W razie błędu — komunikat na stderr i exit 1.

Przykłady:
```
$ lua5.4 temp_convert.lua 100 C F
212.00
$ lua5.4 temp_convert.lua 0 C K
273.15
$ lua5.4 temp_convert.lua 32 X Y
Nieznana skala: X
```

**Sprawdzian 2**  
Napisz funkcję `validate_password(s)` zwracającą `true, "OK"` jeśli hasło spełnia wszystkie z poniższych:
- co najmniej 8 znaków
- ma przynajmniej jedną wielką literę (A-Z)
- ma przynajmniej jedną małą literę (a-z)
- ma przynajmniej jedną cyfrę
- ma przynajmniej jeden znak specjalny (cokolwiek poza alfanumerycznym)

W przeciwnym razie zwraca `false, "<powód>"`.

**Sprawdzian 3**  
Napisz funkcję `count_chars(s, ch)` zwracającą liczbę wystąpień znaku `ch` w stringu `s`. Test: `count_chars("Mississippi", "s")` = 4.

Zrób dwie wersje:
- z pętlą po znakach (`s:sub(i, i)`)
- z `gsub` (skorzystaj z drugiego wyniku — count!)

**Sprawdzian 4**  
Napisz funkcję `fibonacci(n)` zwracającą n-tą liczbę Fibonacciego (`F(0)=0, F(1)=1, F(n)=F(n-1)+F(n-2)`). Iteracyjna (NIE rekurencyjna — chcemy O(n) bez stack overflow).

Test: `fibonacci(10)` = 55, `fibonacci(40)` = 102334155, `fibonacci(0)` = 0.

**Sprawdzian 5**  
Napisz funkcję `pyramid(n)`, która wypisuje piramidę gwiazdek o wysokości `n`, wyśrodkowaną. Dla `n = 4`:

```
   *
  ***
 *****
*******
```

(każda linia ma `2*i - 1` gwiazdek, z `n - i` spacjami przed.)

**Sprawdzian 6**  
Napisz `sum_average.lua` — czyta liczby z `arg`, liczy ich sumę i średnią, wypisuje obie z dokładnością do 3 miejsc. Jeśli `arg` jest puste, błąd na stderr.

Test:
```
$ lua5.4 sum_average.lua 1 2 3 4 5
sum=15.000  avg=3.000  count=5
```

**Sprawdzian 7**  
Mini menu konsolowe `menu.lua`. Wczytuje od użytkownika polecenie (`io.read()`) w pętli, dopóki nie wpisze `"quit"`. Polecenia:
- `add <liczba>` — dodaje do akumulatora
- `mul <liczba>` — mnoży akumulator
- `show` — wypisuje akumulator
- `reset` — zeruje akumulator (ustawia na 0)
- `quit` — kończy

Akumulator startuje od 0. Polecenia parseuj przez `string.match`. Niepoprawne polecenia — wypisz `"???"`.

Sesja przykładowa:
```
> add 5
> add 3
> show
8
> mul 2
> show
16
> reset
> show
0
> nonsense
???
> quit
```

---

### Rozwiązania sprawdzianu

#### Sprawdzian 1

```lua
-- temp_convert.lua
local function fail(msg)
    io.stderr:write(msg .. "\n")
    os.exit(1)
end

if #arg ~= 3 then
    fail("Użycie: lua5.4 temp_convert.lua <wartość> <z> <na>")
end

local value = tonumber(arg[1])
if value == nil then
    fail("Nieprawidłowa liczba: " .. arg[1])
end

local from = arg[2]
local to = arg[3]

-- Najpierw konwertujemy do Kelvin (uniwersalny pośrednik):
local kelvin
if from == "C" then
    kelvin = value + 273.15
elseif from == "F" then
    kelvin = (value - 32) * 5 / 9 + 273.15
elseif from == "K" then
    kelvin = value
else
    fail("Nieznana skala: " .. from)
end

-- Z Kelvina do docelowej:
local result
if to == "C" then
    result = kelvin - 273.15
elseif to == "F" then
    result = (kelvin - 273.15) * 9 / 5 + 32
elseif to == "K" then
    result = kelvin
else
    fail("Nieznana skala: " .. to)
end

print(string.format("%.2f", result))
```

Strategia: zawsze konwertujemy przez Kelvin. Dzięki temu zamiast 9 par (3×3) konwersji, mamy 6 (3 z + 3 do).

#### Sprawdzian 2

```lua
-- validate_password.lua
local function validate_password(s)
    if type(s) ~= "string" then
        return false, "hasło musi być stringiem"
    end
    if #s < 8 then
        return false, "za krótkie (min 8 znaków)"
    end
    if not s:find("%u") then
        return false, "brak wielkiej litery"
    end
    if not s:find("%l") then
        return false, "brak małej litery"
    end
    if not s:find("%d") then
        return false, "brak cyfry"
    end
    if not s:find("[^%w]") then
        return false, "brak znaku specjalnego"
    end
    return true, "OK"
end

local function test(p)
    local ok, msg = validate_password(p)
    print(string.format("%-20s -> %s (%s)",
        '"' .. p .. '"', tostring(ok), msg))
end

test("abc")
test("abcdefgh")
test("Abcdefgh")
test("Abcdefg1")
test("Abcdefg1!")
test("Strong!Password123")
```

```
"abc"                -> false (za krótkie (min 8 znaków))
"abcdefgh"           -> false (brak wielkiej litery)
"Abcdefgh"           -> false (brak cyfry)
"Abcdefg1"           -> false (brak znaku specjalnego)
"Abcdefg1!"          -> true (OK)
"Strong!Password123" -> true (OK)
```

`%u` = wielka litera, `%l` = mała, `%d` = cyfra, `%w` = alfanumeryczny, `[^%w]` = nie alfanumeryczny.

`s:find(pattern)` zwraca `nil` gdy nie znajdzie, więc `not s:find(pattern)` = "nie ma".

#### Sprawdzian 3

```lua
-- count_chars.lua

-- Wersja 1: pętla
local function count_chars_loop(s, ch)
    local count = 0
    for i = 1, #s do
        if s:sub(i, i) == ch then
            count = count + 1
        end
    end
    return count
end

-- Wersja 2: gsub
local function count_chars_gsub(s, ch)
    -- Escape ch w razie gdyby był magicznym znakiem patternu:
    local pattern = ch:gsub("[%(%)%.%%%+%-%*%?%[%]%^%$]", "%%%0")
    local _, count = s:gsub(pattern, "")
    return count
end

print(count_chars_loop("Mississippi", "s"))     -- 4
print(count_chars_gsub("Mississippi", "s"))     -- 4
print(count_chars_loop("a.b.c.d", "."))         -- 3
print(count_chars_gsub("a.b.c.d", "."))         -- 3 (bo zescapowane!)
print(count_chars_gsub("a.b.c.d", "a"))         -- 1
```

W wersji `gsub` musimy zescapować `ch`, bo gdyby ktoś przekazał `"."` lub `"+"`, byłoby to interpretowane jako pattern. `"%%%0"` to escape wzorca: `%%` to dosłowny `%`, `%0` to całe dopasowanie. Czyli wynikiem jest `%X` dla każdego magicznego `X`.

Wersja bez escape'owania (działa dla większości):

```lua
local function count_chars_gsub_simple(s, ch)
    local _, count = s:gsub(ch, "")
    return count
end
```

Działa dla `"s"`, `"a"` itd. Nie zadziała dla `"."`, `"%"`, `"^"` itd.

#### Sprawdzian 4

```lua
-- fibonacci.lua
local function fibonacci(n)
    if n < 0 then return nil, "ujemny indeks" end
    if n < 2 then return n end
    
    local a, b = 0, 1
    for _ = 2, n do
        a, b = b, a + b
    end
    return b
end

print(fibonacci(0))    -- 0
print(fibonacci(1))    -- 1
print(fibonacci(2))    -- 1
print(fibonacci(10))   -- 55
print(fibonacci(40))   -- 102334155
print(fibonacci(60))   -- 1548008755920
print(fibonacci(-1))   -- nil   "ujemny indeks"
```

Multiple assignment `a, b = b, a + b` to fundament. Robi to samo co:

```lua
local tmp = b
b = a + b
a = tmp
```

— ale czyściej i bez zmiennej pomocniczej.

Dlaczego nie rekurencyjna: `fibonacci(40)` rekurencyjnie to ~10⁹ wywołań (każde rozgałęzienie 2× — drzewo eksponencjalne). Iteracyjna — 40 iteracji.

#### Sprawdzian 5

```lua
-- pyramid.lua
local function pyramid(n)
    for i = 1, n do
        local spaces = string.rep(" ", n - i)
        local stars = string.rep("*", 2 * i - 1)
        print(spaces .. stars)
    end
end

pyramid(4)
print("---")
pyramid(7)
```

```
   *
  ***
 *****
*******
---
      *
     ***
    *****
   *******
  *********
 ***********
*************
```

`string.rep(s, n)` powtarza string `n` razy — wbudowane, czytelne.

#### Sprawdzian 6

```lua
-- sum_average.lua
if #arg == 0 then
    io.stderr:write("Brak argumentów\n")
    os.exit(1)
end

local sum = 0
local count = 0
for i = 1, #arg do
    local n = tonumber(arg[i])
    if n == nil then
        io.stderr:write("Nieprawidłowa liczba: " .. arg[i] .. "\n")
        os.exit(1)
    end
    sum = sum + n
    count = count + 1
end

local avg = sum / count
print(string.format("sum=%.3f  avg=%.3f  count=%d", sum, avg, count))
```

```
$ lua5.4 sum_average.lua 1 2 3 4 5
sum=15.000  avg=3.000  count=5

$ lua5.4 sum_average.lua 10 20 30
sum=60.000  avg=20.000  count=3

$ lua5.4 sum_average.lua
Brak argumentów
```

Walidacja w pętli — gdy spotkamy nie-liczbę, exit 1.

#### Sprawdzian 7

```lua
-- menu.lua
local acc = 0

print("Mini menu — wpisz 'quit' aby wyjść")

while true do
    io.write("> ")
    io.flush()
    local line = io.read()
    if line == nil then break end   -- EOF (Ctrl+D)
    
    if line == "quit" then
        break
    elseif line == "show" then
        print(acc)
    elseif line == "reset" then
        acc = 0
    else
        local op, val_str = line:match("^(%a+)%s+(%-?%d+%.?%d*)$")
        if op == "add" then
            acc = acc + tonumber(val_str)
        elseif op == "mul" then
            acc = acc * tonumber(val_str)
        else
            print("???")
        end
    end
end
```

```
> add 5
> add 3
> show
8
> mul 2
> show
16
> reset
> show
0
> nonsense
???
> quit
```

Wzorzec `^(%a+)%s+(%-?%d+%.?%d*)$`:
- `^` — początek
- `(%a+)` — capture #1: jedna lub więcej liter (operacja)
- `%s+` — jeden lub więcej whitespace
- `(%-?%d+%.?%d*)` — capture #2: opcjonalny minus, cyfry, opcjonalna kropka, opcjonalne cyfry
- `$` — koniec

Gdy `match` nie znajdzie — zwraca `nil`. Wtedy `op == "add"` jest `nil == "add"` = `false`, `op == "mul"` to samo, więc trafiamy do `else` z `"???"`.

Edge case: `io.read() == nil` to EOF (Ctrl+D). Dobrze obsłużyć — inaczej skrypt wpadłby w pętlę nieskończoną.

---

## Co dalej?

Gratulacje — masz fundamenty Lua. W kolejnym module poznasz **tabele** — jedyną złożoną strukturę danych w Lua, która jest jednocześnie tablicą, słownikiem, obiektem, namespace'em i klasą.

→ **Moduł 2: Tabele**
