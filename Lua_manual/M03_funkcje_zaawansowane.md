# Moduł 3: Funkcje zaawansowane

> *"Funkcje są pierwszą klasą obywateli — i tym co odróżnia kod profesjonalny od skryptów."*

W Module 1 poznałeś podstawy funkcji. Tutaj zagłębimy się w to, co czyni Lua **językiem funkcyjnym z domieszką OOP**: multiple return values z dokładnymi regułami rozwijania, varargs, closures jako narzędzie enkapsulacji, partial application i memoizacja.

**Przewidywany czas:** 5-7 godzin pracy.

**Lekcje:**
1. Multiple return values — reguły rozwijania
2. Varargs (`...`) i `select`
3. Closures głębiej — upvalues, prywatny stan, pułapki
4. Funkcje wyższego rzędu — partial, compose, curry
5. Memoizacja, dekoratory, profilowanie

Plus **Sprawdzian Modułu 3** — 7 zadań integrujących całość, w tym pełen "lazy iterator" i mini-system observer pattern.

---

## Lekcja 3.1: Multiple return values — reguły rozwijania

### Cel

Rozumiesz dokładnie, kiedy funkcja zwracająca wiele wartości jest "rozwijana", a kiedy "obcinana". Znasz idiom otaczania nawiasami i wiesz, kiedy go używać.

### Materiał

#### Podstawa — przypomnienie

```lua
local function divmod(a, b)
    return a // b, a % b
end

local q, r = divmod(17, 5)
print(q, r)    -- 3   2
```

Funkcja może zwrócić dowolną liczbę wartości. Po stronie wywołania:
- za mało zmiennych — nadmiarowe wyniki **odrzucone**
- za dużo zmiennych — brakujące = `nil`

```lua
local q = divmod(17, 5)         -- 3   (r odrzucone)
local q, r, x = divmod(17, 5)   -- 3   2   nil
```

#### Reguła "ostatniego miejsca"

To jest kluczowa reguła. **Funkcja zwracająca wiele wartości jest ROZWIJANA tylko gdy jest na ostatnim miejscu w wyrażeniu. Inaczej — OBCINANA do jednej wartości.**

```lua
local function f() return 1, 2, 3 end

-- Rozwijanie (ostatnia pozycja):
print(f())                  -- 1   2   3
local t = {f()}             -- {1, 2, 3}
local a, b, c = f()         -- 1, 2, 3
return f()                  -- (zwraca trzy wartości)

-- Obcinanie (NIE na ostatniej pozycji):
print(f(), 99)              -- 1   99       (! tylko pierwszy z f)
print(99, f(), 99)          -- 99  1   99   (! tylko pierwszy z f)
local t = {f(), 99}         -- {1, 99}
local a, b = f(), 0         -- 1, 0  (b dostaje 0, nie 2!)
local x = f() + 10          -- 11    (1 + 10)
```

#### Otaczanie nawiasami — explicit obcinanie

`(expr)` ZAWSZE obcina do jednej wartości:

```lua
local function f() return 1, 2, 3 end

print((f()))           -- 1            (! tylko jedna wartość)
print((f()), 99)       -- 1   99
local t = {(f())}      -- {1}          (! tylko 1)
local a, b = (f())     -- 1, nil
```

Idiom `return (gsub(...))` z Modułu 1 — `gsub` zwraca dwie wartości (string i count), nawiasy obcinają do pierwszej.

#### Przykłady które łapią

```lua
local function f() return 1, 2 end

-- Test 1: konkatenacja
print(f() .. "X")       -- "1X"   (! .. wymaga 1 wartości po lewej)

-- Test 2: w środku tabeli
local t = {f(), f(), f()}
-- t[1] = 1   (pierwsze f obcięte)
-- t[2] = 1   (drugie f obcięte)
-- t[3] = 1   (trzecie f rozwinięte... ale tylko 1 jest jako 1, 2 jako t[4])
-- t = {1, 1, 1, 2}      -- ! czytaj poniżej
```

Stop. Sprawdźmy:

```lua
local function f() return 1, 2 end
local t = {f(), f(), f()}
for i, v in ipairs(t) do print(i, v) end
-- 1   1
-- 2   1
-- 3   1
-- 4   2
```

Tak — **trzecie** wywołanie (na ostatniej pozycji konstruktora) rozwija się, więc dostajemy 4 elementy. To jest jedna z najczęstszych pułapek początkujących.

#### `(...)`  vs `...` w wywołaniu

```lua
local function f() return 1, 2, 3 end

local function g(a, b, c) return a, b, c end

print(g(f()))           -- 1   2   3   (rozwinięte — ostatnia pozycja w call)
print(g(f(), 99))       -- 1   99  nil (obcięte — nie ostatnia)
print(g((f())))         -- 1   nil nil (jawnie obcięte nawiasami)
```

#### Pula wzorców

**Sprawdzanie błędu z pcall** (Moduł 5, zapowiedź):

```lua
local ok, err = pcall(some_function)
if not ok then
    print("Błąd:", err)
end
```

`pcall` zwraca `true, ...wyniki` lub `false, errmsg`. Wzorzec multiple return jest tu fundamentalny.

**Idiom "wynik albo nil, msg":**

```lua
local function open_session(sig)
    if not validate(sig) then
        return nil, "nieprawidłowy sig"
    end
    return create_session(sig)
end

local s, err = open_session("abc")
if not s then
    print("Błąd:", err)
end
```

To samo robi `io.open`, `tonumber`, `string.find`. Kanoniczny Lua-style.

**Swap przez multiple assignment:**

```lua
a, b = b, a              -- swap, bez tymczasowej
```

Lua oblicza WSZYSTKIE prawe strony **przed** przypisaniami. Więc nie ma kolizji.

```lua
-- Cyklicznie:
local a, b, c = 1, 2, 3
a, b, c = b, c, a
print(a, b, c)    -- 2   3   1
```

#### `select` — narzędzie do pracy z multiple values

```lua
print(select(2, "a", "b", "c", "d"))    -- "b"  "c"  "d"   (od pozycji 2)
print(select(3, "a", "b", "c", "d"))    -- "c"  "d"
print(select("#", "a", "b", "c"))       -- 3                (liczba argumentów)
```

`select(n, ...)` zwraca wartości od n-tej. `select("#", ...)` zwraca liczbę argumentów.

Wkrótce w Lekcji 3.2 zobaczysz dlaczego to niezbędne dla varargs.

### Pułapki

1. **Funkcja w środku wyrażenia/listy** = obcięta do 1 wartości.
2. **`{f(), g()}`** — `f` obcięta, `g` rozwinięta (ostatnia pozycja).
3. **`local a, b = f(), 0`** — `b` dostaje 0, nie drugi wynik `f`!
4. **Nawiasy `(f())`** — JAWNE obcięcie.
5. **`a, b = b, a`** działa bez tymczasowej, bo prawe strony są oblicane przed przypisaniami.

### Zadania

**Zadanie 3.1.1**  
Co wypisze każda z linii? Najpierw odpowiedz w głowie, potem uruchom.

```lua
local function f() return 10, 20, 30 end

print(f())              -- ?
print(f(), 99)          -- ?
print(99, f())          -- ?
print((f()))            -- ?
local a, b = f()        -- a, b = ?
local a, b = f(), 0     -- a, b = ?
local t = {f()}         -- t = ?
local t = {f(), 0}      -- t = ?
local t = {0, f()}      -- t = ?
```

**Zadanie 3.1.2**  
Napisz funkcję `min_max(t)` zwracającą najmniejszą i największą wartość z tabeli (multiple return). Dla pustej tabeli — `nil, nil`.

**Zadanie 3.1.3**  
Napisz funkcję `swap_pairs(t)`, która **in-place** zamienia parami sąsiednie elementy: `{1,2,3,4,5}` → `{2,1,4,3,5}`. Dla nieparzystej długości ostatni element zostaje. Zwróć liczbę dokonanych swapów.

**Zadanie 3.1.4**  
Napisz funkcję `partition(t, predicate)` zwracającą **dwie tabele** (przez multiple return): pierwsza z elementami spełniającymi predykat, druga z resztą. Kolejność zachowana.  
Test:
```lua
local even, odd = partition({1,2,3,4,5,6}, function(x) return x % 2 == 0 end)
-- even = {2, 4, 6}
-- odd  = {1, 3, 5}
```

**Zadanie 3.1.5**  
Napisz funkcję `parse_phi_string(s)`, która z wejścia typu `"phi=0.7,sig=abc,epoch=42"` zwraca **trzy wartości** (multiple return): `phi` jako number, `sig` jako string, `epoch` jako number. Jeśli format niepoprawny — `nil, "msg"`.

---

### Rozwiązania

#### Rozwiązanie 3.1.1

```lua
local function f() return 10, 20, 30 end

print(f())              -- 10  20  30        (rozwinięte na ostatniej pozycji)
print(f(), 99)          -- 10  99            (f obcięte, bo NIE ostatnie)
print(99, f())          -- 99  10  20  30    (f rozwinięte, ostatnie)
print((f()))            -- 10                (jawnie obcięte nawiasami)
local a, b = f()        -- a=10, b=20        (rozwinięte; c byłoby 30 gdyby było)
local a, b = f(), 0     -- a=10, b=0         (! f obcięte, b dostaje 0)
local t = {f()}         -- t = {10, 20, 30}
local t = {f(), 0}      -- t = {10, 0}       (f obcięte, 0 jako t[2])
local t = {0, f()}      -- t = {0, 10, 20, 30}  (f rozwinięte na ostatniej)
```

To jest **konieczna do opanowania** wiedza. Pierwsze przejście tego zestawu jest myląca; po przejrzeniu wyników i zrozumieniu reguły "ostatniego miejsca" — staje się oczywista.

#### Rozwiązanie 3.1.2

```lua
-- min_max.lua
local function min_max(t)
    if #t == 0 then return nil, nil end
    local mn, mx = t[1], t[1]
    for i = 2, #t do
        if t[i] < mn then mn = t[i] end
        if t[i] > mx then mx = t[i] end
    end
    return mn, mx
end

print(min_max({3, 1, 4, 1, 5, 9, 2, 6}))    -- 1   9
print(min_max({-5}))                         -- -5  -5
print(min_max({}))                           -- nil  nil
```

Inicjacja `mn, mx = t[1], t[1]`, pętla od 2. Multiple return naturalnie pasuje — dwie wartości, dwa miejsca w `return`.

Wersja jednoplinerkowa korzystając z `math.min`/`math.max` z `table.unpack`:

```lua
local function min_max_v2(t)
    if #t == 0 then return nil, nil end
    return math.min(table.unpack(t)), math.max(table.unpack(t))
end
```

Ładne, ale dwie iteracje (`math.min` widzi wszystkie elementy, `math.max` też). Plus `table.unpack` ma limit (~250 wartości na większości implementacji). Dla małych tabel OK, dla dużych — pierwsza wersja.

#### Rozwiązanie 3.1.3

```lua
-- swap_pairs.lua
local function swap_pairs(t)
    local count = 0
    local i = 1
    while i + 1 <= #t do
        t[i], t[i+1] = t[i+1], t[i]
        count = count + 1
        i = i + 2
    end
    return count
end

local t = {1, 2, 3, 4, 5}
local n = swap_pairs(t)
for _, v in ipairs(t) do io.write(v, " ") end
print()
print("swapów:", n)
-- 2 1 4 3 5
-- swapów: 2

local t2 = {"a", "b", "c", "d"}
swap_pairs(t2)
for _, v in ipairs(t2) do io.write(v, " ") end
print()
-- b a d c
```

`t[i], t[i+1] = t[i+1], t[i]` — swap przez multiple assignment. Bez tymczasowej zmiennej.

#### Rozwiązanie 3.1.4

```lua
-- partition.lua
local function partition(t, predicate)
    local yes = {}
    local no = {}
    for _, v in ipairs(t) do
        if predicate(v) then
            yes[#yes + 1] = v
        else
            no[#no + 1] = v
        end
    end
    return yes, no
end

local even, odd = partition({1, 2, 3, 4, 5, 6, 7, 8},
    function(x) return x % 2 == 0 end)

io.write("even: "); for _, v in ipairs(even) do io.write(v, " ") end; print()
io.write("odd:  "); for _, v in ipairs(odd)  do io.write(v, " ") end; print()
-- even: 2 4 6 8
-- odd:  1 3 5 7

local strings, others = partition({"a", 1, "b", 2, "c"},
    function(x) return type(x) == "string" end)
print("strings:", #strings, "others:", #others)
-- strings: 3   others: 2
```

Dwie tabele zwrócone jako multiple return — naturalnie destrukturuje się na dwie zmienne.

#### Rozwiązanie 3.1.5

```lua
-- parse_phi_string.lua
local function parse_phi_string(s)
    local phi_str = s:match("phi=([%-%d%.]+)")
    local sig = s:match("sig=([%w]+)")
    local epoch_str = s:match("epoch=(%d+)")
    
    if not phi_str then return nil, "brak phi" end
    if not sig then return nil, "brak sig" end
    if not epoch_str then return nil, "brak epoch" end
    
    local phi = tonumber(phi_str)
    local epoch = tonumber(epoch_str)
    
    if not phi then return nil, "phi nie jest liczbą" end
    if not epoch then return nil, "epoch nie jest liczbą" end
    
    return phi, sig, epoch
end

local phi, sig, epoch = parse_phi_string("phi=0.7,sig=abc,epoch=42")
print(phi, sig, epoch)    -- 0.7   abc   42

local phi, sig, epoch = parse_phi_string("sig=xyz,epoch=10,phi=-0.3")
print(phi, sig, epoch)    -- -0.3   xyz   10

local r, err = parse_phi_string("phi=0.7,epoch=42")
print(r, err)              -- nil   brak sig
```

Obsługa "wynik albo nil/err" + multiple return składają się idiomatycznie. Wywołujący widzi:

```lua
local phi, sig, epoch = parse_phi_string(s)
if not phi then
    print("błąd:", sig)   -- ! gdy błąd, drugi wynik to errmsg
    return
end
-- ... użyj phi, sig, epoch
```

Konwencja: gdy pierwszy wynik to `nil`, drugi to message. Dla użytkownika to "albo wszystkie OK, albo nil + msg".

### Sprawdź się

- [ ] Pamiętam regułę "ostatniego miejsca" dla rozwijania
- [ ] Wiem, że `{f(), 0}` ma 2 elementy, a `{0, f()}` może mieć więcej
- [ ] Umiem jawnie obciąć wyniki przez `(f())`
- [ ] Pamiętam, że `local a, b = f(), 0` daje `b = 0`, nie drugi wynik
- [ ] Znam idiom `return wynik` lub `return nil, msg`
- [ ] Wiem, jak działa `select(n, ...)` i `select("#", ...)`

---

## Lekcja 3.2: Varargs (`...`) i `select`

### Cel

Definiujesz funkcje z dowolną liczbą argumentów, bezpiecznie przekazujesz `...`, znasz pułapkę z nilami w varargs i wiesz, kiedy używać `select`.

### Materiał

#### Składnia

```lua
local function log(level, ...)
    print(level, ...)
end

log("INFO", "phi=", 0.7, "sig=", "abc")
-- INFO   phi=   0.7   sig=   abc
```

`...` w deklaracji funkcji — "zbierz pozostałe argumenty". `...` w ciele — rozwiń je.

#### Dostęp do varargs — opcje

```lua
local function show(...)
    -- Opcja 1: bezpośrednie rozwijanie
    print(...)
    
    -- Opcja 2: pakowanie w tabelę
    local args = {...}
    for i, v in ipairs(args) do
        print(i, v)
    end
    
    -- Opcja 3: select dla liczby argumentów
    local n = select("#", ...)
    print("liczba argumentów:", n)
    
    -- Opcja 4: select(n, ...) — od n-tego
    print("od 2-go:", select(2, ...))
end

show("a", "b", "c")
-- a   b   c
-- 1   a
-- 2   b
-- 3   c
-- liczba argumentów:    3
-- od 2-go:    b   c
```

#### Pułapka z nilami

`{...}` to konstruktor tabeli. Jeśli w varargs są nile w środku — zachowanie jest niezdefiniowane (Lekcja 2.1):

```lua
local function f(...)
    local args = {...}
    print("#args =", #args)
    for i = 1, #args do print(i, args[i]) end
end

f(1, 2, nil, 4)
-- #args = 4 lub 2 — niezdefiniowane!
```

**Bezpieczne podejście:** używaj `select("#", ...)`:

```lua
local function f_safe(...)
    local n = select("#", ...)
    print("n =", n)                    -- ZAWSZE 4
    for i = 1, n do
        print(i, (select(i, ...)))     -- nawiasy! select(i, ...) zwraca wszystko od i
    end
end

f_safe(1, 2, nil, 4)
-- n = 4
-- 1   1
-- 2   2
-- 3   nil
-- 4   4
```

Drobna pułapka w `(select(i, ...))` — `select(i, ...)` zwraca wszystkie argumenty od i-tego (multiple return!). Bez nawiasów `print(i, select(i, ...))` wypisałoby resztę. Nawiasy obcinają do pierwszego.

#### Lua 5.2+: `table.pack`

```lua
local function f(...)
    local t = table.pack(...)
    print("n =", t.n)              -- ! pole n z liczbą argumentów
    for i = 1, t.n do
        print(i, t[i])
    end
end

f(1, 2, nil, 4)
-- n = 4
-- 1   1
-- 2   2
-- 3   nil
-- 4   4
```

`table.pack(...)` zwraca tabelę `{1=arg1, 2=arg2, ..., n=count}`. Pole `n` przechowuje liczbę argumentów (włącznie z nilami).

To jest preferowany sposób w nowoczesnym Lua (5.2+). Przed `table.pack` używaj `select("#", ...)`.

#### `table.unpack` — rozwijanie tabeli

Odwrotność `pack`:

```lua
local args = {10, 20, 30}
print(table.unpack(args))    -- 10   20   30

local function add(a, b, c) return a + b + c end
print(add(table.unpack(args)))    -- 60
```

`table.unpack(t)` zwraca multiple values — zachowuje się jak rozwinięte argumenty. Ale **działa tylko dla sekwencji** — nile w środku zatrzymują rozwijanie.

Dla bezpiecznego unpack z polem `n`:

```lua
print(table.unpack(args, 1, args.n))   -- z jawnymi granicami
```

`table.unpack(t, i, j)` rozwija od `i` do `j`. Z `n` pakowanym przez `table.pack`, obejmiesz wszystko (włącznie z nilami).

#### Forwarding varargs

Częsty wzorzec — funkcja "wrapper" przekazuje wszystkie argumenty dalej:

```lua
local function timed(fn, ...)
    local t0 = os.clock()
    local result = fn(...)
    local elapsed = os.clock() - t0
    print(string.format("Czas: %.6fs", elapsed))
    return result
end

local r = timed(string.find, "hello world", "world")
print(r)   -- 7
```

`fn(...)` przekazuje wszystkie varargs do `fn`. Działa idealnie dopóki nie ma nilów w środku — wtedy rozważ pakowanie do tabeli.

#### Multiple return values z varargs

```lua
local function many() return 1, 2, 3 end

local function f(...)
    print("liczba args:", select("#", ...))
    print("args:", ...)
end

f(many())
-- liczba args:  3
-- args:  1   2   3

f(many(), 99)
-- liczba args:  2
-- args:  1   99
-- (! many obcięte bo nie ostatnie)
```

Reguła "ostatniego miejsca" stosuje się do varargs tak samo.

### Pułapki

1. **`{...}` z nilami** w środku = niezdefiniowane.
2. **`select("#", ...)` lub `table.pack`** dla bezpiecznego liczenia.
3. **`select(i, ...)` zwraca multiple values** — nawiasy żeby obciąć.
4. **Forwarding `fn(...)`** działa idealnie dla bezniloych argumentów.
5. **`table.unpack`** zatrzymuje się na nilu — używaj z jawnymi granicami.

### Zadania

**Zadanie 3.2.1**  
Napisz funkcję `printf(fmt, ...)`, która działa jak `print(string.format(fmt, ...))`.  
Test: `printf("Phi=%.2f, sig=%s", 0.7, "abc")`.

**Zadanie 3.2.2**  
Napisz funkcję `sum_all(...)` przyjmującą dowolną liczbę argumentów liczbowych i zwracającą ich sumę.  
Test: `sum_all(1, 2, 3, 4, 5)` = 15. `sum_all()` = 0.

**Zadanie 3.2.3**  
Napisz funkcję `count_truthy(...)` zwracającą liczbę argumentów, które są truthy (różne od `nil` i `false`). Musi obsługiwać nile w środku.  
Test: `count_truthy(1, nil, "a", false, 0)` = 3 (1, "a", 0 są truthy; nil i false — nie).

**Zadanie 3.2.4**  
Napisz funkcję `concat_strs(sep, ...)`, która łączy wszystkie argumenty z separatorem, **bezpiecznie** obsługując nile (pomija je).  
Test: `concat_strs(", ", "a", nil, "b", nil, "c")` = `"a, b, c"`.

**Zadanie 3.2.5**  
Napisz funkcję `wrap_logger(prefix)`, która zwraca **funkcję** logującą z tym prefixem.  
Test:
```lua
local err = wrap_logger("[ERROR] ")
local info = wrap_logger("[INFO] ")
err("nie udało się otworzyć pliku")    -- [ERROR] nie udało się otworzyć pliku
info("session opened, sig=%s", "abc")  -- [INFO] session opened, sig=abc
```

Logger akceptuje fmt + varargs.

---

### Rozwiązania

#### Rozwiązanie 3.2.1

```lua
-- printf.lua
local function printf(fmt, ...)
    print(string.format(fmt, ...))
end

printf("Phi=%.2f, sig=%s", 0.7, "abc")
-- Phi=0.70, sig=abc

printf("hex: %x, dec: %d, str: %q", 255, 42, "hello")
-- hex: ff, dec: 42, str: "hello"

printf("bez argumentów")
-- bez argumentów
```

Dwie linie. `string.format` przyjmuje varargs, więc `string.format(fmt, ...)` przekazuje je idealnie.

#### Rozwiązanie 3.2.2

```lua
-- sum_all.lua
local function sum_all(...)
    local s = 0
    local n = select("#", ...)
    for i = 1, n do
        local v = select(i, ...)
        s = s + v
    end
    return s
end

print(sum_all(1, 2, 3, 4, 5))    -- 15
print(sum_all())                  -- 0
print(sum_all(0.1, 0.2, 0.3))    -- 0.6 (z drobnym fp drift)
print(sum_all(-1, 1))            -- 0
```

**Pułapka subtelna:** `select(i, ...)` zwraca **wszystkie** wartości od i-tej. W kontekście `s = s + select(i, ...)` Lua bierze pierwszy zwrot (bo `+` to operator binarny — jeden lewy, jeden prawy). Działa, ale niezbyt jasne. Czystsze:

```lua
local function sum_all_v2(...)
    local s = 0
    for i = 1, select("#", ...) do
        s = s + (select(i, ...))    -- nawiasy: jawnie pierwszą wartość
    end
    return s
end
```

Wersja przez `table.pack`:

```lua
local function sum_all_v3(...)
    local args = table.pack(...)
    local s = 0
    for i = 1, args.n do
        s = s + args[i]
    end
    return s
end
```

Ostatnia wersja jest najczystsza i najszybsza dla wielu argumentów (jedno `pack`, potem dostęp przez indeks). `select(i, ...)` w pętli to O(n²) — każde `select` musi przejść argumenty.

#### Rozwiązanie 3.2.3

```lua
-- count_truthy.lua
local function count_truthy(...)
    local count = 0
    local n = select("#", ...)
    for i = 1, n do
        local v = select(i, ...)
        if v then count = count + 1 end
    end
    return count
end

print(count_truthy(1, nil, "a", false, 0))    -- 3
print(count_truthy())                          -- 0
print(count_truthy(nil, nil, nil))             -- 0
print(count_truthy(true, true, true))          -- 3
print(count_truthy(0, "", {}))                 -- 3 (! 0, "" i {} są truthy w Lua)
```

`select("#", ...)` daje pełną liczbę argumentów (z nilami w środku). To jest jedyny niezawodny sposób — `{...}` mogłoby zatrzymać się na pierwszym nilu.

#### Rozwiązanie 3.2.4

```lua
-- concat_strs.lua
local function concat_strs(sep, ...)
    local n = select("#", ...)
    local parts = {}
    for i = 1, n do
        local v = select(i, ...)
        if v ~= nil then
            parts[#parts + 1] = tostring(v)
        end
    end
    return table.concat(parts, sep)
end

print(concat_strs(", ", "a", nil, "b", nil, "c"))    -- "a, b, c"
print(concat_strs(" - ", 1, 2, 3))                   -- "1 - 2 - 3"
print(concat_strs("|", nil, nil, nil))               -- ""
print(concat_strs(",", "single"))                    -- "single"
```

Strategia: zbierz nie-nile do tabeli, użyj `table.concat`. **NIE** używaj konkatenacji w pętli — O(n²) (Lekcja 2.4).

`tostring(v)` zabezpiecza przed liczbami i innymi typami nie-stringowymi.

#### Rozwiązanie 3.2.5

```lua
-- wrap_logger.lua
local function wrap_logger(prefix)
    return function(fmt, ...)
        if select("#", ...) == 0 then
            print(prefix .. fmt)
        else
            print(prefix .. string.format(fmt, ...))
        end
    end
end

local err = wrap_logger("[ERROR] ")
local info = wrap_logger("[INFO]  ")
local debug = wrap_logger("[DEBUG] ")

err("nie udało się otworzyć pliku")
info("session opened, sig=%s", "abc")
debug("phi=%.4f, epoch=%d", 0.7234, 42)
err("kod błędu %d, msg: %q", 500, "Internal Error")
-- [ERROR] nie udało się otworzyć pliku
-- [INFO]  session opened, sig=abc
-- [DEBUG] phi=0.7234, epoch=42
-- [ERROR] kod błędu 500, msg: "Internal Error"
```

Dwie obserwacje:

1. **To closure** — zwracana funkcja "pamięta" `prefix` z otaczającego scope. (Lekcja 3.3.)
2. **Sprawdzenie `select("#", ...) == 0`** — jeśli nie ma argumentów do format, wyświetlamy `fmt` jako gołe `print`. Bez tego sprawdzenia, `string.format("foo")` (bez argumentów) zadziała OK, ale `string.format("100% taken")` rzuciłby błąd (próbuje sformatować `% t` jako specyfikator).

W praktyce log zawierający `%` w wiadomości statycznej jest realny:

```lua
err("CPU 100% utilized")    -- bez sprawdzenia: błąd!
```

Wersja "always format" wymagałaby od użytkownika podwojenia `%%`. Nasza wersja jest tolerancyjna.

### Sprawdź się

- [ ] Wiem, kiedy `{...}` może mieć błędną długość
- [ ] Umiem używać `select("#", ...)` i `table.pack`
- [ ] Pamiętam pułapkę `select(i, ...)` zwracającego multiple values
- [ ] Umiem napisać forwarding `fn(...)`
- [ ] Wiem, czemu `table.unpack` zatrzymuje się na nilu
- [ ] Umiem napisać logger jako closure z prefixem

---

## Lekcja 3.3: Closures głębiej — upvalues, prywatny stan, pułapki

### Cel

Rozumiesz mechanizm closures od strony implementacji (upvalues), umiesz tworzyć enkapsulowany stan, znasz typowe błędy (shared upvalues, modyfikacja w iteratorach) i wiesz, kiedy closure jest lepsza od tabeli.

### Materiał

#### Czym jest closure

Closure to funkcja, która "zapamiętuje" zmienne lokalne ze swojego scope tworzenia. Te zmienne nazywamy **upvalues**.

```lua
local function counter()
    local n = 0
    return function()
        n = n + 1
        return n
    end
end

local c = counter()
print(c())   -- 1
print(c())   -- 2
print(c())   -- 3
```

Anonimowa funkcja "łapie" `n`. Każde wywołanie `counter()` tworzy nową `n` i nową funkcję — niezależną:

```lua
local a = counter()
local b = counter()
print(a())   -- 1
print(a())   -- 2
print(b())   -- 1   (niezależna)
print(a())   -- 3
```

#### Upvalues vs zmienne lokalne

Zmienna lokalna (`local x = 5` w bieżącej funkcji) — żyje w bieżącej ramce. Upvalue — odwołanie do zmiennej **z otaczającej** funkcji.

Z perspektywy implementacji: gdy zmienna lokalna jest "łapana" przez closure, Lua tworzy z niej "upvalue" — komórkę pamięci żyjącą tak długo, jak najdłużej żyjąca funkcja, która ją łapie.

```lua
local function make_pair()
    local x = 0
    
    local get = function() return x end
    local set = function(v) x = v end
    
    return get, set
end

local g, s = make_pair()
print(g())   -- 0
s(42)
print(g())   -- 42
```

**Klucz:** `get` i `set` **dzielą** to samo `x`. To jest ten sam upvalue. Modyfikacja przez `set` widoczna w `get`.

To jest fundament enkapsulacji w Lua. Możesz mieć "obiekt" bez tabeli — sama para closures.

#### Closures w pętli — pułapka

```lua
local fns = {}
for i = 1, 3 do
    fns[i] = function() return i end
end

print(fns[1]())   -- ?
print(fns[2]())   -- ?
print(fns[3]())   -- ?
```

Wynik:
```
1
2
3
```

Lua **tworzy nową** zmienną `i` na każdej iteracji `for`. Każda closure łapie *swoją* `i`. To **dobra wiadomość** — Lua zachowuje się intuicyjnie.

**Inaczej niż JavaScript** (przed `let`):

```javascript
// JS:
var fns = []
for (var i = 1; i <= 3; i++) fns.push(() => i)
fns[0]()  // 4 (! wszystkie dzielą tę samą i)
```

W Lua zmienna `i` w `for i = 1, 3` jest fresh-per-iteration. To samo dla `for k, v in pairs(...)`.

**ALE** — uważaj na `while`/`repeat` z lokalną przed pętlą:

```lua
local fns = {}
local i = 0
while i < 3 do
    i = i + 1
    fns[i] = function() return i end
end

for j = 1, 3 do print(fns[j]()) end
-- 3
-- 3
-- 3
-- (! wszystkie dzielą tę samą zewnętrzną i)
```

Tu wszystkie closures łapią **tę samą** `i` (zadeklarowaną przed pętlą). Po zakończeniu pętli `i == 3`, więc każda zwraca 3.

Naprawa:

```lua
local fns = {}
local i = 0
while i < 3 do
    i = i + 1
    local captured_i = i           -- nowa lokalna na iterację
    fns[i] = function() return captured_i end
end
```

To jest klasyczna pułapka, którą musisz znać. **Reguła kciuka:** w `while` lub `repeat` z closure łapiącą zmienną pętli — zrób kopię do nowej `local`.

#### Closure vs tabela jako "obiekt"

Możesz zaimplementować "stack" na dwa sposoby:

```lua
-- Wersja 1: tabela (Moduł 2)
local function make_stack_table()
    local self = {data = {}, size = 0}
    function self:push(v)
        self.size = self.size + 1
        self.data[self.size] = v
    end
    function self:pop()
        if self.size == 0 then return nil end
        local v = self.data[self.size]
        self.data[self.size] = nil
        self.size = self.size - 1
        return v
    end
    return self
end

-- Wersja 2: closure
local function make_stack_closure()
    local data = {}
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
    }
end
```

**Różnice:**

| Aspekt | Tabela | Closure |
|---|---|---|
| Składnia wywołania | `s:push(v)` | `s.push(v)` |
| Dostęp do stanu | `s.size`, `s.data` (publiczne) | Niedostępne z zewnątrz (prywatne) |
| Pamięć | 1 tabela + 2 funkcje | 2 funkcje + upvalues |
| Wydajność | Marginalnie szybsza (lookup w tabeli) | Marginalnie wolniejsza (upvalue access) |
| Dziedziczenie | Łatwe (Moduł 4) | Trudne |
| Introspekcja | `for k, v in pairs(s)` | Brak |

**Reguła kciuka:**
- **Tabela** + metatable (Moduł 4) — gdy potrzebujesz OOP, dziedziczenia, introspekcji.
- **Closure** — gdy potrzebujesz prawdziwej prywatności (np. tokeny bezpieczeństwa, wewnętrzny stan którego nie wolno zepsuć z zewnątrz).

#### Counter z reset

Pełen przykład z kilkoma metodami:

```lua
local function make_counter(initial)
    local n = initial or 0
    
    return {
        inc = function() n = n + 1; return n end,
        dec = function() n = n - 1; return n end,
        get = function() return n end,
        reset = function() n = initial or 0 end,
        set = function(v) n = v end,
    }
end

local c = make_counter(10)
print(c.get())     -- 10
print(c.inc())     -- 11
print(c.inc())     -- 12
print(c.dec())     -- 11
c.reset()
print(c.get())     -- 10
c.set(100)
print(c.inc())     -- 101
```

`n` jest naprawdę prywatne. Z zewnątrz nie ma sposobu, by je odczytać poza `c.get()` ani zmodyfikować poza `c.set(...)` itp. To jest enkapsulacja.

#### Counter z dziedzicznym scope (currying-like)

```lua
local function make_adder(by)
    return function(x) return x + by end
end

local add5 = make_adder(5)
local add10 = make_adder(10)

print(add5(3))    -- 8
print(add10(3))   -- 13

-- Funkcja generująca specjalizowaną wersję funkcji:
local function logger_for(level)
    return function(msg)
        print("[" .. level .. "] " .. os.date("%H:%M:%S") .. " " .. msg)
    end
end

local err = logger_for("ERROR")
local info = logger_for("INFO")
err("disk full")
info("user logged in")
```

To **partial application** — częściowe związanie argumentów. Prosta forma currying. Szczegóły w Lekcji 3.4.

### Pułapki

1. **Closure w `while`/`repeat`** — kopia do `local` na iterację.
2. **Closure trzyma upvalue PRZY ŻYCIU** — nawet po zakończeniu funkcji która ją utworzyła. Ważne dla GC: closure przeciwstawia się usunięciu danych, do których odwołuje się przez upvalue. Pamięć szczelna.
3. **Wszystkie funkcje wewnętrzne dzielą upvalues** — modyfikacja w jednej widoczna w drugiej.
4. **Closure capture jest BY REFERENCE**, nie by value. Gdyby Lua kopiowała wartość, `set`/`get` byłyby bezużyteczne.

### Zadania

**Zadanie 3.3.1**  
Napisz funkcję `make_id_generator(prefix)`, która zwraca funkcję generującą unikalne identyfikatory `prefix-1`, `prefix-2`, itd.  
Test:
```lua
local sess_id = make_id_generator("sess")
local atom_id = make_id_generator("atom")
print(sess_id())    -- "sess-1"
print(atom_id())    -- "atom-1"
print(sess_id())    -- "sess-2"
```

**Zadanie 3.3.2**  
Napisz funkcję `make_throttled(fn, max_calls)`, która zwraca funkcję wywołującą `fn` tylko `max_calls` razy. Po przekroczeniu limitu zwraca `nil, "limit exceeded"`.  
Test:
```lua
local f = make_throttled(function(x) return x * 2 end, 3)
print(f(5))    -- 10
print(f(5))    -- 10
print(f(5))    -- 10
print(f(5))    -- nil   "limit exceeded"
```

**Zadanie 3.3.3**  
Napisz funkcję `make_observable(initial)`, która tworzy "wartość obserwowalną" z metodami:
- `get()` — zwraca aktualną wartość
- `set(v)` — ustawia nową wartość (powiadamia obserwatorów)
- `subscribe(fn)` — dodaje obserwatora (`fn(new_value, old_value)`); zwraca funkcję unsubscribe

Test:
```lua
local phi = make_observable(0.5)
local unsub = phi.subscribe(function(new, old)
    print("phi zmienione: " .. old .. " -> " .. new)
end)
phi.set(0.7)    -- "phi zmienione: 0.5 -> 0.7"
phi.set(0.9)    -- "phi zmienione: 0.7 -> 0.9"
unsub()
phi.set(1.0)    -- (cisza)
```

**Zadanie 3.3.4**  
Pułapka closures w pętli. Co wypisze ten kod? Najpierw odpowiedz, potem uruchom:

```lua
local fns = {}
local i = 0
while i < 3 do
    i = i + 1
    fns[i] = function() return i end
end
for j = 1, 3 do print(fns[j]()) end
```

Następnie zmodyfikuj go, by każda funkcja zwracała własną wartość (1, 2, 3).

**Zadanie 3.3.5**  
Napisz `make_lazy(fn)`, która zwraca funkcję obliczającą `fn()` **tylko raz** przy pierwszym wywołaniu, a kolejne wywołania zwracają zacachowany wynik. (To jest "lazy evaluation" / "memoize-once".)  
Test:
```lua
local count = 0
local lazy = make_lazy(function()
    count = count + 1
    return "obliczony wynik"
end)
print(count)       -- 0  (jeszcze nie wywołane)
print(lazy())      -- "obliczony wynik"
print(count)       -- 1
print(lazy())      -- "obliczony wynik"
print(count)       -- 1  (drugie wywołanie nie wywołało fn)
```

---

### Rozwiązania

#### Rozwiązanie 3.3.1

```lua
-- make_id_generator.lua
local function make_id_generator(prefix)
    local n = 0
    return function()
        n = n + 1
        return prefix .. "-" .. n
    end
end

local sess_id = make_id_generator("sess")
local atom_id = make_id_generator("atom")

print(sess_id())   -- sess-1
print(atom_id())   -- atom-1
print(sess_id())   -- sess-2
print(sess_id())   -- sess-3
print(atom_id())   -- atom-2
```

Każde wywołanie `make_id_generator` tworzy własne `n`. Closure-encapsulation jest kompletna: nie ma sposobu, by skoczyć licznikowi z 5 do 100 z zewnątrz (oprócz wywołań). Dla systemu jak HSS to ważne — żeby identyfikatory były niezawodnie unikalne.

#### Rozwiązanie 3.3.2

```lua
-- make_throttled.lua
local function make_throttled(fn, max_calls)
    local count = 0
    return function(...)
        if count >= max_calls then
            return nil, "limit exceeded"
        end
        count = count + 1
        return fn(...)
    end
end

local f = make_throttled(function(x) return x * 2 end, 3)
print(f(5))    -- 10
print(f(5))    -- 10
print(f(5))    -- 10
print(f(5))    -- nil   limit exceeded
print(f(99))   -- nil   limit exceeded
```

`fn(...)` przekazuje varargs — działa dla funkcji o dowolnej arności. `nil, "..."` to standardowy idiom błędu.

W praktyce taki throttle przyda się np. do limitowania wywołań API w sandboxowanych skryptach KarmazynOS — każda sesja dostaje throttled wrapper.

#### Rozwiązanie 3.3.3

```lua
-- make_observable.lua
local function make_observable(initial)
    local value = initial
    local observers = {}
    local next_id = 0
    
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
            next_id = next_id + 1
            local id = next_id
            observers[id] = fn
            -- Zwracamy funkcję unsubscribe:
            return function()
                observers[id] = nil
            end
        end,
    }
end

local phi = make_observable(0.5)

local unsub1 = phi.subscribe(function(new, old)
    print("Obs1: " .. old .. " -> " .. new)
end)

local unsub2 = phi.subscribe(function(new, old)
    if new > 0.8 then
        print("Obs2: alarm! phi=" .. new)
    end
end)

phi.set(0.7)    -- Obs1: 0.5 -> 0.7
phi.set(0.9)    -- Obs1: 0.7 -> 0.9
                -- Obs2: alarm! phi=0.9

unsub1()
phi.set(1.0)    -- Obs2: alarm! phi=1.0  (Obs1 odpisany)

unsub2()
phi.set(0.3)    -- (cisza)
```

To jest pełny **observer pattern** w 20 liniach. Closures dają nam:
- `value` — prywatny stan
- `observers` — prywatna mapa (klient nie może jej skorumpować)
- `next_id` — generator ID dla safe unsubscribe
- `unsub` — closure trzymająca `id`, która usuwa obserwatora gdy wywołana

Używamy `pairs(observers)` zamiast `ipairs` — bo gdy ktoś robi unsubscribe w środku iteracji, sekwencja może się rozpaść. (Modyfikacja tabeli w `pairs` ustawiając klucz na nil jest legalna.)

W produkcyjnym KarmazynOS taki wzorzec jest jeden z fundamentów — `phi` jako observable, hook-i sesji jako subskrybenci, każda zmiana propaguje.

#### Rozwiązanie 3.3.4

Co wypisuje kod **przed** modyfikacją:

```
3
3
3
```

Wszystkie closures dzielą TĘ SAMĄ zewnętrzną `i`. Po zakończeniu pętli `i == 3`. Każde wywołanie czyta to `i` z upvalue — wszystkie widzą 3.

Modyfikacja:

```lua
local fns = {}
local i = 0
while i < 3 do
    i = i + 1
    local captured_i = i           -- nowa LOKALNA na każdą iterację
    fns[i] = function() return captured_i end
end

for j = 1, 3 do print(fns[j]()) end
-- 1
-- 2
-- 3
```

`local captured_i = i` w środku pętli tworzy nową zmienną na każdej iteracji — każda closure dostaje własny upvalue.

Alternatywnie — IIFE (immediately invoked function expression):

```lua
fns[i] = (function(snapshot) return function() return snapshot end end)(i)
```

Ale to mniej czytelne. Wersja z `local captured_i` jest lepsza.

**Notabene:** `for i = 1, n do` (numeric for) **nie ma** tego problemu — Lua tworzy fresh `i` na każdej iteracji. Tylko `while`/`repeat` z lokalną przed pętlą stwarzają pułapkę.

#### Rozwiązanie 3.3.5

```lua
-- make_lazy.lua
local function make_lazy(fn)
    local computed = false
    local result
    
    return function()
        if not computed then
            result = fn()
            computed = true
        end
        return result
    end
end

local count = 0
local lazy = make_lazy(function()
    count = count + 1
    return "obliczony wynik"
end)

print("count przed:", count)        -- 0
print(lazy())                       -- "obliczony wynik"
print("count po 1:", count)         -- 1
print(lazy())                       -- "obliczony wynik"
print("count po 2:", count)         -- 1
print(lazy())                       -- "obliczony wynik"
print("count po 3:", count)         -- 1
```

**Pułapka:** `if not result then` byłoby błędem — gdyby `fn()` zwracała `nil` lub `false`, każde wywołanie liczyłoby od nowa. Dlatego osobna flaga `computed`.

Wersja dla wielu wartości return:

```lua
local function make_lazy_multi(fn)
    local computed = false
    local results
    
    return function()
        if not computed then
            results = table.pack(fn())
            computed = true
        end
        return table.unpack(results, 1, results.n)
    end
end

local lazy_pair = make_lazy_multi(function() return 1, 2, 3 end)
print(lazy_pair())   -- 1   2   3
```

`table.pack` z polem `n`, `table.unpack(t, 1, t.n)` dla rozwijania z nilami. Idiomatyczne.

### Sprawdź się

- [ ] Wiem, co to upvalue
- [ ] Pamiętam, że `numeric for` daje fresh zmienną per iteration
- [ ] Pamiętam, że `while`/`repeat` z lokalną przed pętlą — pułapka closure
- [ ] Umiem zaimplementować observer pattern przez closures
- [ ] Wiem, że closure trzyma upvalue przy życiu (kontra GC)
- [ ] Umiem napisać `make_lazy` z osobną flagą `computed`

---

## Lekcja 3.4: Funkcje wyższego rzędu — partial, compose, curry

### Cel

Tworzysz i używasz funkcji wyższego rzędu (HOF). Znasz wzorce: partial application, compose, curry, pipe. Umiesz wyrazić dany obliczeniowy łańcuch funkcyjnie.

### Materiał

#### Co to HOF

**Higher-order function** — funkcja, która:
- przyjmuje funkcję jako argument, **albo**
- zwraca funkcję jako wynik.

Lua to potrafi w pełni. `map`, `filter`, `reduce` (Lekcja 2.5) to przykłady.

#### `reduce` / `fold`

Standardowy HOF do "zwijania" listy do jednej wartości:

```lua
local function reduce(t, fn, init)
    local acc = init
    for _, v in ipairs(t) do
        acc = fn(acc, v)
    end
    return acc
end

print(reduce({1, 2, 3, 4, 5}, function(a, b) return a + b end, 0))   -- 15
print(reduce({1, 2, 3, 4, 5}, function(a, b) return a * b end, 1))   -- 120
print(reduce({"a", "b", "c"}, function(a, b) return a .. b end, "")) -- "abc"

-- Maksimum:
print(reduce({3, 7, 1, 9, 4}, function(a, b) return a > b and a or b end, -math.huge))
-- 9
```

`reduce(table, fn(acc, v), init)`. `fn` bierze akumulator i kolejny element, zwraca nowy akumulator. Klasyk programowania funkcyjnego.

#### Partial application

"Zafiksuj kilka argumentów funkcji, otrzymaj funkcję o mniejszej arności":

```lua
local function partial(fn, ...)
    local fixed_args = table.pack(...)
    return function(...)
        local new_args = table.pack(...)
        local all = {}
        for i = 1, fixed_args.n do all[i] = fixed_args[i] end
        for i = 1, new_args.n do all[fixed_args.n + i] = new_args[i] end
        return fn(table.unpack(all, 1, fixed_args.n + new_args.n))
    end
end

local function add(a, b, c) return a + b + c end

local add_5 = partial(add, 5)
print(add_5(2, 3))           -- 10  (5 + 2 + 3)

local add_5_10 = partial(add, 5, 10)
print(add_5_10(7))           -- 22

-- Może przekształcić bibliotekę w "punkt-free":
local prefix = partial(string.format, "[%s] %s")
print(prefix("INFO", "session opened"))     -- "[INFO] session opened"
print(prefix("ERROR", "disk full"))         -- "[ERROR] disk full"
```

Praktyczny przykład — preset funkcji logger z przykładu wcześniej.

#### `compose` — łączenie funkcji

`compose(f, g)(x) = f(g(x))`:

```lua
local function compose(f, g)
    return function(...) return f(g(...)) end
end

local function plus_one(x) return x + 1 end
local function times_two(x) return x * 2 end

local f = compose(plus_one, times_two)
print(f(3))   -- (3*2) + 1 = 7

-- Łączenie wielu:
local function compose_many(...)
    local fns = table.pack(...)
    return function(x)
        for i = fns.n, 1, -1 do   -- od ostatniej do pierwszej (mathematical order)
            x = fns[i](x)
        end
        return x
    end
end

local pipeline = compose_many(plus_one, times_two, function(x) return x - 3 end)
-- equivalent: x -> (x-3) -> (x-3)*2 -> ((x-3)*2)+1
print(pipeline(10))   -- ((10-3)*2)+1 = 15
```

#### `pipe` — alternatywa do compose

`pipe` to compose w odwrotnej kolejności — czyta się "od lewej do prawej":

```lua
local function pipe(...)
    local fns = table.pack(...)
    return function(x)
        for i = 1, fns.n do
            x = fns[i](x)
        end
        return x
    end
end

local pipeline = pipe(
    function(x) return x - 3 end,
    times_two,
    plus_one
)
-- equivalent: x -> x-3 -> (x-3)*2 -> ((x-3)*2)+1
print(pipeline(10))   -- 15
```

Mniej "matematyczne", bardziej "data-flow". W praktyce inżynierskiej `pipe` częściej naturalne — to jak Unixowy `|`.

#### Currying

Curry transformuje funkcję `f(a, b, c)` w `f(a)(b)(c)`:

```lua
local function curry2(fn)
    return function(a)
        return function(b)
            return fn(a, b)
        end
    end
end

local function add(a, b) return a + b end
local cadd = curry2(add)

print(cadd(5)(3))    -- 8

local add5 = cadd(5)
print(add5(10))      -- 15
print(add5(20))      -- 25
```

Currying jest **podzbiorem** partial application — zawsze fixujesz po jednym argumencie, generując funkcje jednoargumentowe.

W praktyce Lua: `partial` jest częściej użyteczny. Currying ma swoje miejsce w czysto-funkcyjnych pipelach.

#### Filter, map, reduce — łańcuch

```lua
local function filter(t, predicate)
    local r = {}
    for _, v in ipairs(t) do
        if predicate(v) then r[#r + 1] = v end
    end
    return r
end

local function map(t, fn)
    local r = {}
    for i, v in ipairs(t) do r[i] = fn(v) end
    return r
end

-- Łańcuch:
local nums = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10}

local result = reduce(
    map(
        filter(nums, function(x) return x % 2 == 0 end),    -- {2, 4, 6, 8, 10}
        function(x) return x * x end                         -- {4, 16, 36, 64, 100}
    ),
    function(a, b) return a + b end,
    0
)
print(result)    -- 220

-- Więcej czytelnie z pipe:
local function compute(nums)
    return pipe(
        function(t) return filter(t, function(x) return x % 2 == 0 end) end,
        function(t) return map(t, function(x) return x * x end) end,
        function(t) return reduce(t, function(a, b) return a + b end, 0) end
    )(nums)
end

print(compute(nums))   -- 220
```

Lua nie ma "method chaining" jak `nums |> filter(...) |> map(...) |> reduce(...)` natywnie. Można dodać metatable + `__concat` jako trick (egzotyczne), albo używać `pipe` jak wyżej.

### Pułapki

1. **`compose` vs `pipe`** — mathematical (compose, prawo do lewej) vs procedural (pipe, lewo do prawej).
2. **Partial z varargs** — wymaga obsługi `table.pack`/`table.unpack`.
3. **Łańcuch `filter`/`map`/`reduce`** alokuje pośrednie tabele. Dla małych OK, dla dużych — fold-fusion lub iteratory (Moduł 6).

### Zadania

**Zadanie 3.4.1**  
Napisz funkcję `apply_n(fn, n, x)`, która stosuje `fn` `n` razy: `apply_n(fn, 3, x) = fn(fn(fn(x)))`.  
Test: `apply_n(function(x) return x*2 end, 5, 1)` = 32.

**Zadanie 3.4.2**  
Napisz funkcję `negate(predicate)`, która zwraca predykat odwrotny.  
Test:
```lua
local is_even = function(x) return x % 2 == 0 end
local is_odd = negate(is_even)
print(is_odd(3))    -- true
print(is_odd(4))    -- false
```

**Zadanie 3.4.3**  
Napisz funkcję `all(t, predicate)` zwracającą `true` jeśli **każdy** element spełnia predykat. Bonus: `any(t, predicate)` zwracający `true` gdy **przynajmniej jeden** spełnia. Pusta tabela: `all` zwraca `true`, `any` zwraca `false`.  
Test:
```lua
all({1,2,3,4}, function(x) return x > 0 end)    -- true
all({1,-2,3}, function(x) return x > 0 end)     -- false
any({1,2,3}, function(x) return x > 2 end)      -- true
any({1,2,3}, function(x) return x > 10 end)     -- false
```

**Zadanie 3.4.4**  
Napisz `pipe_table(t, ...)`, który przyjmuje tabelę i sekwencję funkcji-transformatorów. Każda funkcja bierze tabelę, zwraca tabelę. Bezpośrednia ścieżka data-flow.  
Test:
```lua
local result = pipe_table({1,2,3,4,5,6},
    function(t) return filter(t, function(x) return x > 2 end) end,
    function(t) return map(t, function(x) return x * 10 end) end
)
-- result = {30, 40, 50, 60}
```

**Zadanie 3.4.5**  
Napisz `compose_n(...)` — wariant compose dla wielu funkcji, który **zachowuje multiple return values** wewnątrz łańcucha.  
Test:
```lua
local function divmod(x) return x // 2, x % 2 end
local function pair_str(a, b) return "q=" .. a .. ", r=" .. b end

local f = compose_n(pair_str, divmod)
print(f(7))    -- "q=3, r=1"
```

(Tu `divmod` zwraca dwie wartości, które są następnie podawane do `pair_str`.)

---

### Rozwiązania

#### Rozwiązanie 3.4.1

```lua
-- apply_n.lua
local function apply_n(fn, n, x)
    for _ = 1, n do
        x = fn(x)
    end
    return x
end

print(apply_n(function(x) return x * 2 end, 5, 1))    -- 32  (1->2->4->8->16->32)
print(apply_n(function(x) return x + 1 end, 100, 0))  -- 100
print(apply_n(function(x) return x*x end, 4, 2))      -- 65536  (2->4->16->256->65536)
print(apply_n(function(x) return x end, 1000000, 42)) -- 42  (identity, dowolnie razy)
```

Naturalna iteracja. Można też rekurencyjnie:

```lua
local function apply_n_rec(fn, n, x)
    if n == 0 then return x end
    return apply_n_rec(fn, n - 1, fn(x))
end
```

Uwaga: rekurencja w Lua **NIE** jest tail-call-optimized w trybie który zachowuje stack trace dla `pcall`. Dla `n = 1000000` rekurencja może się sypnąć (stack overflow). **Dla iteracji wybieraj iteracyjną wersję.**

#### Rozwiązanie 3.4.2

```lua
-- negate.lua
local function negate(predicate)
    return function(...) return not predicate(...) end
end

local is_even = function(x) return x % 2 == 0 end
local is_odd = negate(is_even)

print(is_even(3))    -- false
print(is_odd(3))     -- true
print(is_even(4))    -- true
print(is_odd(4))     -- false

local is_positive = function(x) return x > 0 end
local is_non_positive = negate(is_positive)
print(is_non_positive(0))    -- true
print(is_non_positive(-5))   -- true
print(is_non_positive(5))    -- false
```

`...` w obie strony — funkcja może być wieloargumentowa.

#### Rozwiązanie 3.4.3

```lua
-- all_any.lua
local function all(t, predicate)
    for _, v in ipairs(t) do
        if not predicate(v) then return false end
    end
    return true
end

local function any(t, predicate)
    for _, v in ipairs(t) do
        if predicate(v) then return true end
    end
    return false
end

print(all({1,2,3,4}, function(x) return x > 0 end))     -- true
print(all({1,-2,3}, function(x) return x > 0 end))      -- false
print(all({}, function(x) return false end))            -- true   (pusta -> trivially all)
print(any({1,2,3}, function(x) return x > 2 end))       -- true
print(any({1,2,3}, function(x) return x > 10 end))      -- false
print(any({}, function(x) return true end))             -- false  (pusta -> trivially none)

-- Praktyczny test:
local atoms = {{phi=0.7}, {phi=0.4}, {phi=0.9}}
print(all(atoms, function(a) return a.phi >= 0 end))    -- true
print(any(atoms, function(a) return a.phi > 0.8 end))   -- true
```

Krótkie spinanie (short-circuit): obie funkcje wracają od razu po znalezieniu kontrprzykładu / dowodu. Pełne O(n) tylko w pesymistycznym przypadku.

Pusta tabela: `all` zwraca `true` ("vacuous truth" — nie ma żadnego elementu, który NIE spełnia, więc wszystkie spełniają). `any` zwraca `false` — nic nie ma więc nic nie spełnia.

#### Rozwiązanie 3.4.4

```lua
-- pipe_table.lua
local function pipe_table(t, ...)
    local fns = table.pack(...)
    local current = t
    for i = 1, fns.n do
        current = fns[i](current)
    end
    return current
end

-- Pomocnicze (z Lekcji 2.5):
local function filter(t, predicate)
    local r = {}
    for _, v in ipairs(t) do
        if predicate(v) then r[#r + 1] = v end
    end
    return r
end

local function map(t, fn)
    local r = {}
    for i, v in ipairs(t) do r[i] = fn(v) end
    return r
end

local result = pipe_table({1,2,3,4,5,6},
    function(t) return filter(t, function(x) return x > 2 end) end,
    function(t) return map(t, function(x) return x * 10 end) end
)

for _, v in ipairs(result) do io.write(v, " ") end
print()
-- 30 40 50 60
```

Lokalne wrappery `function(t) return filter(t, predicate) end` są nieco verbose. W praktyce możesz zdefiniować currified wersje:

```lua
local function filter_by(predicate)
    return function(t) return filter(t, predicate) end
end

local function map_by(fn)
    return function(t) return map(t, fn) end
end

-- Pipeline staje się czytelny:
local result = pipe_table({1,2,3,4,5,6},
    filter_by(function(x) return x > 2 end),
    map_by(function(x) return x * 10 end)
)
```

To jest **functional style** — czyste pipeline'y bez verbose lambd. Wymaga jednak większego ekosystemu helpersów.

#### Rozwiązanie 3.4.5

```lua
-- compose_n.lua
local function compose_n(...)
    local fns = table.pack(...)
    return function(...)
        local args = table.pack(...)
        -- Iteruj od OSTATNIEJ funkcji (najgłębsza w composition)
        for i = fns.n, 1, -1 do
            args = table.pack(fns[i](table.unpack(args, 1, args.n)))
        end
        return table.unpack(args, 1, args.n)
    end
end

-- Test:
local function divmod(x) return x // 2, x % 2 end
local function pair_str(a, b) return "q=" .. a .. ", r=" .. b end

local f = compose_n(pair_str, divmod)
print(f(7))    -- "q=3, r=1"
print(f(20))   -- "q=10, r=0"
print(f(13))   -- "q=6, r=1"

-- Trzy funkcje:
local function increment(x) return x + 1 end
local g = compose_n(pair_str, divmod, increment)
print(g(7))    -- (7+1)//2=4, (7+1)%2=0  -> "q=4, r=0"
```

Klucz: `args = table.pack(fn(table.unpack(args)))`. Każda funkcja może zwrócić multiple values, pakujemy w tabelę, w następnej iteracji rozwijamy.

To rozwiązanie jest cięższe niż prosty `compose` z Lekcji 1.5 — bo musimy zachować multiple values przez wiele kroków. W typowym kodzie funkcyjnym Lua compose dla single-return wystarcza w 95% przypadków. Wersja multi-return jest dla zaawansowanych.

### Sprawdź się

- [ ] Wiem, co to higher-order function
- [ ] Umiem zaimplementować `reduce`
- [ ] Znam różnicę `compose` vs `pipe`
- [ ] Umiem zaimplementować `partial`, `negate`, `all`/`any`
- [ ] Wiem, dlaczego rekurencja w Lua nie jest tail-call dla każdego przypadku
- [ ] Znam wzorzec `filter_by`/`map_by` dla czystych pipeline'ów

---

## Lekcja 3.5: Memoizacja, dekoratory, profilowanie

### Cel

Implementujesz memoizację funkcji deterministycznych, piszesz dekoratory (logging, timing, retry), znasz proste techniki profilowania kodu Lua.

### Materiał

#### Memoizacja — co to

Cache wyników funkcji deterministycznej: jeśli widzieliśmy już to wejście, zwróć zacachowany wynik bez ponownego obliczania. Przyspieszenie dla funkcji kosztownych obliczeniowo o powtarzalnych wejściach.

#### Memoizacja jednoargumentowa

```lua
local function memoize(fn)
    local cache = {}
    return function(x)
        if cache[x] == nil then
            cache[x] = fn(x)
        end
        return cache[x]
    end
end

-- Klasyk: Fibonacci rekurencyjny (eksponencjalny bez memo)
local function fib(n)
    if n < 2 then return n end
    return fib(n - 1) + fib(n - 2)
end

-- Memoizowany:
local fib_memo
fib_memo = memoize(function(n)
    if n < 2 then return n end
    return fib_memo(n - 1) + fib_memo(n - 2)
end)

print(fib_memo(30))    -- 832040  (szybko)
-- print(fib(40))       -- ~1 sekunda
print(fib_memo(50))    -- 12586269025  (natychmiast)
```

**Uwaga subtelna:** w `fib_memo` rekurencja musi wołać **memoizowaną** wersję, nie oryginalną. Stąd forward declaration `local fib_memo` przed przypisaniem. Bez tego rekursywne wywołania nie korzystałyby z cache'u.

#### Pułapka: nil w cache

```lua
if cache[x] == nil then ... end
```

Działa, dopóki `fn(x)` nie zwraca `nil`. Jeśli zwraca, każde wywołanie liczy od nowa. Bezpieczniejsze:

```lua
local function memoize_safe(fn)
    local cache = {}
    local NIL_SENTINEL = {}
    return function(x)
        local cached = cache[x]
        if cached == NIL_SENTINEL then return nil end
        if cached == nil then
            local result = fn(x)
            cache[x] = (result == nil) and NIL_SENTINEL or result
            return result
        end
        return cached
    end
end
```

Sentinela jako "marker dla nila".

#### Memoizacja wieloargumentowa

```lua
local function memoize_n(fn)
    local cache = {}
    return function(...)
        local args = table.pack(...)
        -- Zbudować klucz z argumentów:
        local key = ""
        for i = 1, args.n do
            key = key .. tostring(args[i]) .. "|"
        end
        if cache[key] == nil then
            cache[key] = fn(...)
        end
        return cache[key]
    end
end

local function expensive(a, b)
    print("liczę dla", a, b)
    return a * b + math.sin(a)
end

local em = memoize_n(expensive)
print(em(1, 2))    -- liczę dla 1   2 / wynik
print(em(1, 2))    -- (cache, bez "liczę")
print(em(2, 1))    -- liczę dla 2   1 (nowe!)
print(em(1, 2))    -- cache
```

Strategia: zbuduj klucz przez konkatenację `tostring` argumentów. Działa dla number/string/boolean. Dla tabel — `tostring(t)` daje adres pamięci, więc cache by-identity (ten sam obiekt, ten sam cache hit).

Wersja z zagnieżdżonym cache (drzewo) jest szybsza dla wielu argumentów, ale skomplikowana — pierwsza wystarcza dla większości.

#### Dekoratory

Dekorator to HOF który "owija" inną funkcję dodając zachowanie.

**Logger:**

```lua
local function logged(fn, name)
    return function(...)
        print(string.format("[CALL] %s(%s)", name, table.concat({...}, ", ")))
        local result = fn(...)
        print(string.format("[RET]  %s -> %s", name, tostring(result)))
        return result
    end
end

local function add(a, b) return a + b end
local add_logged = logged(add, "add")

print(add_logged(3, 4))
-- [CALL] add(3, 4)
-- [RET]  add -> 7
-- 7
```

(Subtelność: `table.concat({...}, ", ")` nie obsłuży nilów ani różnych typów. W praktyce użyj `string.format` z osobnymi `tostring`.)

**Timer:**

```lua
local function timed(fn, name)
    return function(...)
        local t0 = os.clock()
        local result = table.pack(fn(...))
        local elapsed = os.clock() - t0
        print(string.format("%s: %.6fs", name or "(anon)", elapsed))
        return table.unpack(result, 1, result.n)
    end
end

local function compute(n)
    local s = 0
    for i = 1, n do s = s + math.sqrt(i) end
    return s
end

local timed_compute = timed(compute, "compute")
print(timed_compute(1000000))
-- compute: 0.018127s
-- 6.6666664583353e+08
```

**Retry:**

```lua
local function with_retry(fn, max_attempts, delay_seconds)
    return function(...)
        local last_err
        for attempt = 1, max_attempts do
            local ok, result = pcall(fn, ...)
            if ok then return result end
            last_err = result
            print(string.format("attempt %d failed: %s", attempt, tostring(result)))
            -- Symulujemy delay (w prawdziwym systemie: os.execute("sleep ..."))
        end
        return nil, last_err
    end
end
```

(Pełne `pcall`/`xpcall` — Moduł 5.)

#### Łączenie dekoratorów

```lua
local fn = compute
fn = timed(fn, "compute")
fn = logged(fn, "compute")
-- Teraz fn loguje argumenty + zwraca timing
```

Albo w jednym łańcuchu:

```lua
local function decorate(fn, ...)
    local decorators = table.pack(...)
    local result = fn
    for i = 1, decorators.n do
        result = decorators[i](result)
    end
    return result
end
```

#### Profilowanie ręczne

```lua
local function profile_calls(fn)
    local count = 0
    local total_time = 0
    
    local wrapped = function(...)
        count = count + 1
        local t0 = os.clock()
        local result = table.pack(fn(...))
        total_time = total_time + (os.clock() - t0)
        return table.unpack(result, 1, result.n)
    end
    
    local stats = function()
        return {
            calls = count,
            total = total_time,
            avg = count > 0 and total_time / count or 0,
        }
    end
    
    return wrapped, stats
end

local f, stats = profile_calls(function(n)
    local s = 0
    for i = 1, n do s = s + i end
    return s
end)

for _ = 1, 1000 do f(10000) end

local s = stats()
print(string.format("calls=%d total=%.3fs avg=%.6fs",
    s.calls, s.total, s.avg))
-- calls=1000 total=0.0XXs avg=0.0000XXs
```

To jest **simple profiler** — owijasz funkcję wrapperem, mierzysz, pytasz o statystyki. Dla zaawansowanego profilowania Lua ma bibliotekę `LuaProfiler` lub `lua-debug` — ale prosty wrapper wystarcza w 90% przypadków.

#### `os.clock` vs `os.time`

- `os.clock()` — zwraca CPU time procesu w sekundach (float). Idealne do mikropomiarów.
- `os.time()` — wallclock time w sekundach (integer). Dobry do dat, zły do mikropomiarów (rozdzielczość 1s).

Dla mikropomiarów: `os.clock()`. Dla "kiedy się wydarzyło": `os.time()`.

### Pułapki

1. **Memoizacja musi wołać memoizowaną wersję** w rekursji — forward declaration.
2. **Cache z `nil` jako wynikiem** — sentinel pattern.
3. **Memoizacja dla funkcji niedeterministycznych** — wynik może być błędny.
4. **Cache rośnie nieograniczone** — w długo działającym programie potrzebny LRU.
5. **`os.clock` ma ograniczoną rozdzielczość** — mierzony fragment musi być sensownie długi (~1ms+) lub uśredniaj wiele wywołań.

### Zadania

**Zadanie 3.5.1**  
Napisz `count_calls(fn)`, który zwraca: nową funkcję + funkcję `count()` zwracającą liczbę wywołań tej funkcji. Multiple return.  
Test:
```lua
local f, count = count_calls(function(x) return x*2 end)
f(5); f(10); f(20)
print(count())    -- 3
```

**Zadanie 3.5.2**  
Napisz memoizację z **limitowanym cache** (LRU-like — gdy przekroczy `max_size`, usuń najstarszy wpis). Wersja prosta: zlicz tylko hits, gdy size > max — wyczyść cache całkowicie.  
Test pokaż że cache się czyści po 5 wpisach.

**Zadanie 3.5.3**  
Napisz dekorator `validate(fn, type_specs)`, który sprawdza typy argumentów. `type_specs` to tabela typów. Jeśli typ nie pasuje — `error` z opisowym komunikatem.  
Test:
```lua
local f = validate(function(a, b) return a + b end, {"number", "number"})
print(f(3, 4))         -- 7
print(f(3, "abc"))     -- error: argument 2: oczekiwano number, dostałem string
```

**Zadanie 3.5.4**  
Napisz `make_rate_limiter(rate_per_sec)` — dekorator zezwalający na wywołanie max `rate_per_sec` razy na sekundę. Po przekroczeniu zwraca `nil, "rate limited"`.  
Hint: trzymaj listę timestampów wywołań, czyść starsze niż 1 sekunda.

**Zadanie 3.5.5**  
Napisz funkcję `fibonacci_dp(n)` używającą memoizacji, ale **bez** rekursji — jako iteracyjny dynamic programming. Limit: `n <= 100`. Sprawdź `fib(70)` (potrzeba 64-bit integer — Lua 5.3+).

---

### Rozwiązania

#### Rozwiązanie 3.5.1

```lua
-- count_calls.lua
local function count_calls(fn)
    local count = 0
    local wrapped = function(...)
        count = count + 1
        return fn(...)
    end
    local get_count = function() return count end
    return wrapped, get_count
end

local f, count = count_calls(function(x) return x * 2 end)

print(f(5))         -- 10
print(f(10))        -- 20
print(f(20))        -- 40
print(count())      -- 3

f(99); f(99)
print(count())      -- 5
```

Closure dzieli `count` między `wrapped` i `get_count`. Standardowy enkapsulowany licznik.

#### Rozwiązanie 3.5.2

```lua
-- memoize_lru.lua
local function memoize_lru(fn, max_size)
    local cache = {}
    local size = 0
    return function(x)
        if cache[x] ~= nil then return cache[x] end
        
        if size >= max_size then
            -- Naprawdę proste wyczyszczenie:
            cache = {}
            size = 0
        end
        
        local result = fn(x)
        cache[x] = result
        size = size + 1
        return result
    end
end

local count_compute = 0
local slow_square = function(x)
    count_compute = count_compute + 1
    return x * x
end

local memo = memoize_lru(slow_square, 5)

memo(1); memo(2); memo(3); memo(4); memo(5)
print(count_compute)   -- 5  (wszystkie nowe)

memo(1); memo(2)
print(count_compute)   -- 5  (cache hit)

memo(6)                -- size było 5, czyszczenie, potem dodaj 6
print(count_compute)   -- 6

memo(1)                -- już nie w cache po reset, recompute
print(count_compute)   -- 7
```

Pełny LRU z dwukierunkową listą jest bardziej skomplikowany — zostawiam to jako "challenge task". Wersja "wyczyść po przekroczeniu" jest prosta i wystarcza w wielu zastosowaniach (np. cache dla deterministicznych obliczeń, gdzie gorszy MVP > brak cache'u).

#### Rozwiązanie 3.5.3

```lua
-- validate.lua
local function validate(fn, type_specs)
    return function(...)
        local args = table.pack(...)
        for i = 1, #type_specs do
            local expected = type_specs[i]
            local got = type(args[i])
            if got ~= expected then
                error(string.format(
                    "argument %d: oczekiwano %s, dostałem %s",
                    i, expected, got
                ), 2)   -- '2' = poziom = wskaż na callera, nie na validate
            end
        end
        return fn(...)
    end
end

local f = validate(function(a, b) return a + b end, {"number", "number"})

print(f(3, 4))    -- 7

-- Uruchom ten z pcall, żeby zobaczyć błąd:
local ok, err = pcall(f, 3, "abc")
print(ok, err)
-- false   ...: argument 2: oczekiwano number, dostałem string
```

`error(msg, level)` z poziomem 2 — wskazuje błąd na linię, gdzie wywołano `f(...)`, nie wewnątrz `validate`. Lepszy stack trace dla użytkownika.

`pcall(f, 3, "abc")` to sposób na "przechwycenie" błędu — szczegóły w Module 5.

#### Rozwiązanie 3.5.4

```lua
-- make_rate_limiter.lua
local function make_rate_limiter(rate_per_sec)
    local timestamps = {}    -- queue (head/tail) timestampów
    local head = 1
    local tail = 0
    
    return function(...)
        local now = os.time()
        
        -- Wyczyść timestampy starsze niż 1 sekunda:
        while head <= tail and timestamps[head] < now do
            timestamps[head] = nil
            head = head + 1
        end
        
        -- Sprawdź limit:
        local active = tail - head + 1
        if active >= rate_per_sec then
            return nil, "rate limited"
        end
        
        -- Zarejestruj wywołanie:
        tail = tail + 1
        timestamps[tail] = now
        
        return ...   -- bez fn, bo to nie wrapper, a "limit checker"
    end
end

-- Wersja z fn:
local function rate_limited(fn, rate_per_sec)
    local check = make_rate_limiter(rate_per_sec)
    return function(...)
        local ok = check()
        if not ok then return nil, "rate limited" end
        return fn(...)
    end
end

-- Test:
local function expensive() return "ok" end
local f = rate_limited(expensive, 3)

for i = 1, 5 do
    local r, err = f()
    print(i, r, err)
end
-- 1   ok   nil
-- 2   ok   nil
-- 3   ok   nil
-- 4   nil  rate limited
-- 5   nil  rate limited

-- Po sekundzie limit się zresetuje, ale w teście synchronicznym tego nie zobaczymy.
```

`os.time()` ma rozdzielczość 1 sekundy. Dla **podsekundowego** rate-limitera potrzebujesz biblioteki z lepszym timerem (`luasocket.gettime()`, `os.clock()` jest CPU time, nie wallclock).

W KarmazynOS sandboxie (HSS) podobny mechanizm jest podstawą `quota.cpu_ms` / "max calls per second" per session.

#### Rozwiązanie 3.5.5

```lua
-- fibonacci_dp.lua
local function fibonacci_dp(n)
    if n < 0 then return nil, "ujemny indeks" end
    if n < 2 then return n end
    
    local memo = {[0] = 0, [1] = 1}
    for i = 2, n do
        memo[i] = memo[i-1] + memo[i-2]
    end
    return memo[n]
end

print(fibonacci_dp(0))    -- 0
print(fibonacci_dp(1))    -- 1
print(fibonacci_dp(10))   -- 55
print(fibonacci_dp(70))   -- 190392490709135

-- Sprawdź typ:
print(math.type(fibonacci_dp(70)))    -- "integer" (Lua 5.3+)

-- Limit dla 64-bit signed int:
print(fibonacci_dp(92))   -- 7540113804746346429  (mieści się)
print(fibonacci_dp(93))   -- 12200160415121876738 (! wraps around / overflows)
```

`fib(93)` wynosi ~1.2e19 — to przekracza 64-bit signed integer (max ~9.2e18). W Lua 5.3+ integer wrap-around jest dobrze zdefiniowany — dla większych wartości potrzebujesz `bigint` library lub przejście na float (z utratą precyzji).

Wersja **memory-efficient** — bez tablicy:

```lua
local function fib_dp_compact(n)
    if n < 2 then return n end
    local a, b = 0, 1
    for _ = 2, n do
        a, b = b, a + b
    end
    return b
end
```

Ta wersja jest tym samym co w sprawdzianie M1 — iteracyjny Fibonacci. Pamięć O(1) zamiast O(n). Memoizacja przydatna była w przykładzie "rekursywny fib z cache" — tam unikamy rozgałęzień.

### Sprawdź się

- [ ] Umiem zaimplementować memoizację jednoargumentową
- [ ] Wiem, że memoizowana rekursja musi wołać memoizowaną wersję
- [ ] Pamiętam pułapkę z nilem jako wynikiem (sentinel)
- [ ] Umiem napisać dekorator `timed`, `logged`, `validate`
- [ ] Wiem, kiedy `os.clock` vs `os.time`
- [ ] Umiem zaimplementować prosty rate limiter

---

## Sprawdzian Modułu 3

Siedem zadań. Łącząc multiple return, varargs, closures i HOF — będziesz pisać prawdziwy "funcjonalny Lua".

### Zadania

**Sprawdzian 1** — `range`  
Napisz funkcję `range(start, stop, step)` zwracającą tabelę-listę liczb. `step` opcjonalny (domyślnie 1). `start` opcjonalny (domyślnie 1) gdy podany tylko jeden argument — wtedy `range(n)` = `{1, 2, ..., n}`.  
Test:
```lua
range(5)            -- {1, 2, 3, 4, 5}
range(2, 6)         -- {2, 3, 4, 5, 6}
range(1, 10, 2)     -- {1, 3, 5, 7, 9}
range(10, 1, -1)    -- {10, 9, ..., 1}
```

**Sprawdzian 2** — `each` z early termination  
Napisz funkcję `each(t, fn)` iterującą po tabeli i wywołującą `fn(value, index)` dla każdego elementu. Jeśli `fn` zwróci `false` — zatrzymaj iterację. Zwraca liczbę iteracji wykonanych.  
Test:
```lua
local n = each({10, 20, 30, 40, 50}, function(v, i)
    print(i, v)
    if v >= 30 then return false end
end)
print("zakończono po", n, "iteracjach")
-- 1   10
-- 2   20
-- 3   30
-- zakończono po 3 iteracjach
```

**Sprawdzian 3** — `min_by` / `max_by`  
Napisz funkcje `min_by(t, key_fn)` i `max_by(t, key_fn)` zwracające element z najmniejszym/największym kluczem wyciągniętym przez `key_fn`. Wraz z indeksem (multiple return).  
Test:
```lua
local atoms = {
    {sig = "a", phi = 0.4},
    {sig = "b", phi = 0.7},
    {sig = "c", phi = 0.2},
}
local atom, idx = max_by(atoms, function(a) return a.phi end)
print(atom.sig, atom.phi, idx)    -- "b"   0.7   2
```

**Sprawdzian 4** — `chain` jako iterator  
Napisz funkcję `chain(...)`, która z wielu tabel-list zwraca jedną iterację (jak `for v in chain({1,2}, {3,4}, {5}) do`).

Hint: zwraca generator-funkcję plus stan, jak w `pairs`/`ipairs`. Patrz format generic for.

Lub prościej: zwraca pojedynczą funkcję iteratora przez closure. Wtedy:
```lua
for v in chain({1, 2}, {3, 4}, {5}) do
    io.write(v, " ")
end
print()
-- 1 2 3 4 5
```

**Sprawdzian 5** — `memoize` z TTL  
Napisz `memoize_ttl(fn, ttl_seconds)`. Cache wpisu wygasa po `ttl_seconds`. Po wygaśnięciu — recompute.

Test (symulowany — bo nie chcemy `sleep`):
```lua
-- Ustaw ttl=2
-- Wywołaj raz, sprawdź count
-- (czekaj 3 sekundy w prawdziwym teście)
-- Wywołaj znowu, sprawdź count rośnie
```

**Sprawdzian 6** — Pipeline DSL  
Napisz "DSL pipeline" — funkcję `Pipeline(value)` zwracającą tabelę z metodami `:filter(p)`, `:map(f)`, `:reduce(f, init)`, `:get()`. Każda metoda zwraca tę samą strukturę (poza `:get()` które zwraca wynik). Method chaining.

Test:
```lua
local result = Pipeline({1,2,3,4,5,6,7,8,9,10})
    :filter(function(x) return x % 2 == 0 end)
    :map(function(x) return x * x end)
    :reduce(function(a, b) return a + b end, 0)
    :get()
print(result)    -- 220 (4+16+36+64+100)
```

(Tu wracamy do tabel z metodami — Sprawdzian z M2 użyłeś `Stack.push(s, v)`. Tutaj musisz użyć `s:method()` — pomyśl jak.)

**Sprawdzian 7** — Lazy iterator (generator)  
Napisz funkcję `lazy_range(start, stop, step)`, która zwraca **generator** — funkcję, którą można wywołać i dostać następną wartość. `nil` oznacza koniec.

Następnie napisz `lazy_filter(gen, predicate)` i `lazy_map(gen, fn)` — funkcje przekształcające jeden generator w drugi. **Bez** alokacji pośredniej tabeli.

Test:
```lua
local g = lazy_range(1, 1000000)        -- nie alokuje miliona elementów!
local g2 = lazy_filter(g, function(x) return x % 7 == 0 end)
local g3 = lazy_map(g2, function(x) return x * x end)

-- Pobierz pierwsze 5 wartości:
for _ = 1, 5 do
    print(g3())
end
-- 49 (7^2)
-- 196 (14^2)
-- 441 (21^2)
-- 784 (28^2)
-- 1225 (35^2)
```

To jest klasyczny **stream/iterator pipeline**. W Module 6 (korutyny) zobaczysz jeszcze ładniejszą wersję.

---

### Rozwiązania sprawdzianu

#### Sprawdzian 1

```lua
-- range.lua
local function range(a, b, step)
    local start, stop
    if b == nil then
        start, stop = 1, a
    else
        start, stop = a, b
    end
    step = step or 1
    
    if step == 0 then return nil, "step nie może być 0" end
    
    local result = {}
    if step > 0 then
        for i = start, stop, step do
            result[#result + 1] = i
        end
    else
        for i = start, stop, step do
            result[#result + 1] = i
        end
    end
    return result
end

local function show(t)
    if t == nil then print("nil"); return end
    for _, v in ipairs(t) do io.write(v, " ") end
    print()
end

show(range(5))             -- 1 2 3 4 5
show(range(2, 6))          -- 2 3 4 5 6
show(range(1, 10, 2))      -- 1 3 5 7 9
show(range(10, 1, -1))     -- 10 9 8 7 6 5 4 3 2 1
show(range(0, 0))          -- 0
show(range(5, 1))          -- (puste, bo step=1, start>stop)
```

Sprytna obsługa "1 lub 2 argumenty" przez sprawdzanie `b == nil`. Pętla `for` w Lua sama nie wykonuje iteracji gdy step jest dodatni a start > stop (lub ujemny i start < stop) — więc nie potrzebujemy specjalnej obsługi.

#### Sprawdzian 2

```lua
-- each.lua
local function each(t, fn)
    for i, v in ipairs(t) do
        if fn(v, i) == false then
            return i   -- liczba iteracji = indeks ostatniej wykonanej
        end
    end
    return #t
end

local n = each({10, 20, 30, 40, 50}, function(v, i)
    print(i, v)
    if v >= 30 then return false end
end)
print("zakończono po", n, "iteracjach")
-- 1   10
-- 2   20
-- 3   30
-- zakończono po 3 iteracjach

-- Bez early termination:
local n = each({1, 2, 3}, function(v, i) print(v) end)
print(n)
-- 1
-- 2
-- 3
-- 3
```

`fn(v, i) == false` — testujemy **dokładnie** `false`, nie `not`. Bo gdyby `fn` zwracała `nil` (większość funkcji bez explicit return), wszystkie iteracje wyglądałyby jak `early termination`. Tylko jawne `return false` zatrzymuje.

#### Sprawdzian 3

```lua
-- min_max_by.lua
local function min_by(t, key_fn)
    if #t == 0 then return nil, nil end
    local best = t[1]
    local best_idx = 1
    local best_key = key_fn(t[1])
    for i = 2, #t do
        local k = key_fn(t[i])
        if k < best_key then
            best, best_idx, best_key = t[i], i, k
        end
    end
    return best, best_idx
end

local function max_by(t, key_fn)
    if #t == 0 then return nil, nil end
    local best = t[1]
    local best_idx = 1
    local best_key = key_fn(t[1])
    for i = 2, #t do
        local k = key_fn(t[i])
        if k > best_key then
            best, best_idx, best_key = t[i], i, k
        end
    end
    return best, best_idx
end

local atoms = {
    {sig = "a", phi = 0.4},
    {sig = "b", phi = 0.7},
    {sig = "c", phi = 0.2},
    {sig = "d", phi = 0.5},
}

local atom, idx = max_by(atoms, function(a) return a.phi end)
print(atom.sig, atom.phi, idx)    -- "b"   0.7   2

local atom, idx = min_by(atoms, function(a) return a.phi end)
print(atom.sig, atom.phi, idx)    -- "c"   0.2   3
```

Cache `best_key` — wywołujemy `key_fn` raz na element, nie raz na porównanie. To istotne dla kosztownych key_fn.

Wspólna logika `min_by`/`max_by` — można scaliować przez `compare` predicate, ale przy 2 funkcjach duplikacja jest OK (czytelność wygrywa).

#### Sprawdzian 4

```lua
-- chain.lua
local function chain(...)
    local tables = table.pack(...)
    local table_idx = 1
    local elem_idx = 0
    
    return function()
        while table_idx <= tables.n do
            elem_idx = elem_idx + 1
            local current = tables[table_idx]
            if elem_idx <= #current then
                return current[elem_idx]
            end
            -- przeskocz do następnej tabeli:
            table_idx = table_idx + 1
            elem_idx = 0
        end
        return nil   -- koniec
    end
end

for v in chain({1, 2}, {3, 4}, {5}) do
    io.write(v, " ")
end
print()
-- 1 2 3 4 5

-- Z różnymi typami:
for v in chain({"a", "b"}, {1, 2, 3}, {"x"}) do
    io.write(tostring(v), " ")
end
print()
-- a b 1 2 3 x

-- Pusta:
for v in chain() do io.write(v, " ") end
print()
-- (nic)

-- Z pustymi tabelami:
for v in chain({}, {1}, {}, {2, 3}, {}) do io.write(v, " ") end
print()
-- 1 2 3
```

Closure trzyma `table_idx`, `elem_idx` jako stan. Pętla `while` w środku — bo gdy skończymy aktualną tabelę, musimy przeskoczyć ewentualne puste tabele (stąd loop, nie tylko `if`).

`for v in iter do` — generic for wymaga iteratora w stylu `iter() -> next_value` (lub `iter() -> nil` na końcu). Nasza funkcja to spełnia.

#### Sprawdzian 5

```lua
-- memoize_ttl.lua
local function memoize_ttl(fn, ttl_seconds)
    local cache = {}
    local timestamps = {}
    
    return function(x)
        local now = os.time()
        if cache[x] ~= nil and timestamps[x] + ttl_seconds > now then
            return cache[x]
        end
        local result = fn(x)
        cache[x] = result
        timestamps[x] = now
        return result
    end
end

local count = 0
local memo = memoize_ttl(function(x)
    count = count + 1
    return x * 2
end, 2)   -- TTL = 2 sekundy

print(memo(5))      -- 10, count=1
print(memo(5))      -- 10, count=1 (cache)
print(memo(7))      -- 14, count=2 (nowy klucz)
print(memo(5))      -- 10, count=2 (cache)
print(count)        -- 2

-- W realnym kodzie testowałbyś:
-- os.execute("sleep 3")
-- print(memo(5))      -- count rośnie do 3 (TTL minął)

-- Symulujemy: nadpisz timestamp manualnie do testu
-- (nieczyste, ale pokazuje)
print("--- symulacja upływu czasu ---")
-- Niestety nie da się "manualnie cofnąć timestampu" bez modyfikacji impl.
-- W praktyce użyj `sleep` lub mock'uj os.time.
```

Wersja "z mockowalnym timer":

```lua
local function memoize_ttl_v2(fn, ttl, time_fn)
    time_fn = time_fn or os.time
    local cache = {}
    local timestamps = {}
    
    return function(x)
        local now = time_fn()
        if cache[x] ~= nil and timestamps[x] + ttl > now then
            return cache[x]
        end
        local result = fn(x)
        cache[x] = result
        timestamps[x] = now
        return result
    end
end

-- Test z fake-timer:
local fake_now = 0
local time_fn = function() return fake_now end

local count = 0
local memo = memoize_ttl_v2(function(x) count = count + 1; return x*2 end, 2, time_fn)

memo(5)              -- count=1
memo(5)              -- count=1 (cache)
fake_now = 3         -- "minęły 3 sekundy"
memo(5)              -- count=2 (TTL minął, recompute)
print(count)         -- 2
```

Wstrzyknięcie `time_fn` jako argument to klasyczna technika dla testowalności — pozwala kontrolować czas w testach bez prawdziwego `sleep`.

#### Sprawdzian 6

```lua
-- pipeline_dsl.lua
local Pipeline = {}
Pipeline.__index = Pipeline   -- ! to jest "spojler" Modułu 4 — metatable

function Pipeline.new(value)
    local self = setmetatable({}, Pipeline)
    self.value = value
    return self
end

function Pipeline:filter(predicate)
    local new_value = {}
    for _, v in ipairs(self.value) do
        if predicate(v) then new_value[#new_value + 1] = v end
    end
    self.value = new_value
    return self
end

function Pipeline:map(fn)
    local new_value = {}
    for i, v in ipairs(self.value) do
        new_value[i] = fn(v)
    end
    self.value = new_value
    return self
end

function Pipeline:reduce(fn, init)
    local acc = init
    for _, v in ipairs(self.value) do
        acc = fn(acc, v)
    end
    self.value = acc
    return self
end

function Pipeline:get()
    return self.value
end

-- Wywołanie konstruktora jak funkcji
setmetatable(Pipeline, {__call = function(_, value) return Pipeline.new(value) end})

local result = Pipeline({1, 2, 3, 4, 5, 6, 7, 8, 9, 10})
    :filter(function(x) return x % 2 == 0 end)
    :map(function(x) return x * x end)
    :reduce(function(a, b) return a + b end, 0)
    :get()

print(result)    -- 220
```

Tu **wyprzedzamy Moduł 4** — `setmetatable(self, Pipeline)` z `Pipeline.__index = Pipeline` daje `s:method()` notation. Jeśli to dla Ciebie niejasne — wróć do tego po Module 4. Zostawiłem to w sprawdzianie M3, bo:

1. Method chaining wymaga zwracania `self` z każdej metody (kluczowy idiom).
2. Spojler na `setmetatable` przyda się do następnego modułu.
3. Pełne zrozumienie OOP-a w Lua wymaga zobaczenia obu — closure-based (ten moduł) i metatable-based (M4).

Każda metoda **mutuje** `self.value` zamiast tworzyć nowy obiekt. Mniej "funkcyjne" w sensie immutable, ale wydajne (mniej alokacji).

Czystsza, immutable wersja byłaby:

```lua
function Pipeline:map(fn)
    local new_value = {}
    for i, v in ipairs(self.value) do new_value[i] = fn(v) end
    return Pipeline.new(new_value)   -- nowy obiekt
end
```

#### Sprawdzian 7

```lua
-- lazy_iterators.lua
local function lazy_range(start, stop, step)
    step = step or 1
    local current = start - step
    return function()
        current = current + step
        if (step > 0 and current > stop) or (step < 0 and current < stop) then
            return nil
        end
        return current
    end
end

local function lazy_filter(gen, predicate)
    return function()
        while true do
            local v = gen()
            if v == nil then return nil end
            if predicate(v) then return v end
        end
    end
end

local function lazy_map(gen, fn)
    return function()
        local v = gen()
        if v == nil then return nil end
        return fn(v)
    end
end

-- Pomocnicza: lazy_take(gen, n) — bierze pierwsze n
local function lazy_take(gen, n)
    local taken = 0
    return function()
        if taken >= n then return nil end
        taken = taken + 1
        return gen()
    end
end

-- Test:
local g = lazy_range(1, 1000000)
local g2 = lazy_filter(g, function(x) return x % 7 == 0 end)
local g3 = lazy_map(g2, function(x) return x * x end)
local g4 = lazy_take(g3, 5)

while true do
    local v = g4()
    if v == nil then break end
    print(v)
end
-- 49
-- 196
-- 441
-- 784
-- 1225

-- Test z `for in`:
print("--- for in ---")
for v in lazy_take(lazy_map(
    lazy_filter(lazy_range(1, 100),
        function(x) return x % 7 == 0 end),
    function(x) return x * x end
), 5) do
    io.write(v, " ")
end
print()
-- 49 196 441 784 1225
```

**Klucz:** żaden z generatorów nie alokuje pełnej listy. `lazy_range(1, 1000000)` to closure trzymająca `current`. `lazy_filter` to closure zawijająca poprzedni generator. Łańcuch działa **strumieniowo** — wartość przepływa przez wszystkie etapy bez pośrednich tabel.

Memory: O(1) zamiast O(n). Dla `n = 10^9` — to różnica między działa-i-OOM.

Korutyny (Moduł 6) dadzą **jeszcze ładniejszą** notację dla tego — możesz pisać generator jak normalną funkcję z `coroutine.yield(x)` zamiast ręcznych closures z `current`.

---

## Co dalej?

Funkcje są w pełni opanowane. Mamy fundament wszystkiego — w kolejnych modułach zobaczysz jak to wszystko składa się w bardziej zaawansowane konstrukcje.

→ **Moduł 4: Metatable i OOP** — dziedziczenie, operatory, prototypowy OOP, weak tables, `__index` jako funkcja.
