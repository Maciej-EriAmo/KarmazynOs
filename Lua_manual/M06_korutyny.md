# Moduł 6: Korutyny

> *"Korutyna to funkcja, która wie, że nie jest jedyna."*

Korutyny to mechanizm Lua, który wygląda jak wątki, ale jest **nie-preemptive** (cooperative) i **single-threaded** — tylko jedna naraz wykonuje kod. Zamiast wątków OS — to "zachowane stosy wykonania", które można wstrzymać i wznowić.

Brzmi prosto, jest potężne. Korutyny dają Ci za darmo: generatory, lazy iteratory, prosty scheduler multi-tasking, producer/consumer pipelines, async I/O (gdy zintegrujesz z event loop), state machines — wszystko bez dodatkowych bibliotek.

W KarmazynOS będą **fundamentem** schedulera multi-agent pipeline (Moduł 11) — każdy agent to korutyna, scheduler je rotuje, każda może yieldować na limicie CPU/pamięci.

**Przewidywany czas:** 5-7 godzin pracy.

**Lekcje:**
1. Podstawy — `create`, `resume`, `yield`, stany
2. `coroutine.wrap`, generic for, generatory
3. Producer/consumer i pipelines
4. Scheduler — round-robin, priority
5. Lazy iteratory na korutynach (vs closures z M3)

Plus **Sprawdzian Modułu 6** — 6 zadań, w tym pełny scheduler z timeoutami i state machine na korutynach.

---

## Lekcja 6.1: Podstawy — `create`, `resume`, `yield`, stany

### Cel

Tworzysz korutyny, wstrzymujesz je przez `yield` i wznawiasz przez `resume`. Rozumiesz dwukierunkowy przepływ argumentów. Znasz stany korutyny: suspended, running, normal, dead.

### Materiał

#### Co to korutyna

Korutyna to **funkcja, która może się zatrzymać i być wznowiona**. Zachowuje swój kontekst (zmienne lokalne, pozycję w kodzie) między wstrzymaniami.

Porównanie z funkcjami:
- **Funkcja:** wywołujesz, ona wykonuje od początku do końca, zwraca wynik. Każde wywołanie to świeży start.
- **Korutyna:** tworzysz raz, potem "wznawiasz" wielokrotnie. Pamięta gdzie skończyła ostatnio.

Porównanie z wątkami:
- **Wątek:** preemptive (system może wstrzymać w dowolnym momencie), wiele naraz, kosztuje pamięć.
- **Korutyna:** cooperative (sama decyduje kiedy yieldować), tylko jedna aktywna naraz, tania (~kilka KB).

#### `coroutine.create`

```lua
local co = coroutine.create(function(x)
    print("start, x=", x)
    coroutine.yield(x * 2)
    print("po pierwszym yield")
    coroutine.yield(x * 3)
    print("po drugim yield")
    return x * 4
end)

print(type(co))                  -- "thread"
print(coroutine.status(co))      -- "suspended"  (utworzona, nie startowała)
```

`create` przyjmuje funkcję, zwraca **korutynę** (typu `thread`). NIE uruchamia kodu — kod startuje przy pierwszym `resume`.

#### `coroutine.resume`

```lua
local co = coroutine.create(function(x)
    print("krok 1, x=", x)
    local y = coroutine.yield(x * 2)        -- pauzuj, wartością zwrotną resume jest x*2
    print("krok 2, y=", y)                  -- y to argument NASTĘPNEGO resume
    local z = coroutine.yield(y + 1)
    print("krok 3, z=", z)
    return "koniec"
end)

print(coroutine.resume(co, 10))   -- "krok 1, x=10"  -> true, 20
print(coroutine.resume(co, 99))   -- "krok 2, y=99"  -> true, 100
print(coroutine.resume(co, 7))    -- "krok 3, z=7"   -> true, "koniec"
print(coroutine.resume(co))       -- false, "cannot resume dead coroutine"
```

**Mechanika:**
1. Pierwsze `resume(co, 10)` — przekazuje `10` jako pierwszy argument funkcji. `x = 10`.
2. Funkcja drukuje "krok 1" i `yield(x * 2)` = `yield(20)`. **20 wraca do `resume`.** Funkcja jest wstrzymana.
3. `resume` zwraca `true, 20`.
4. Drugie `resume(co, 99)` — wznawia korutynę. **99 staje się wynikiem `yield(20)`.** `y = 99`.
5. Funkcja drukuje "krok 2" i `yield(y + 1)` = `yield(100)`. 100 wraca do `resume`.
6. ... i tak dalej.

#### Dwukierunkowy przepływ — wizualizacja

```
host                                korutyna
----                                --------
resume(co, 10)  --[args]-->         start: x=10
                                    print "krok 1"
            <--[yield val]--        yield(x*2)  -- czyli yield(20)
got 20                              [pauza]
resume(co, 99)  --[args]-->         y = 99 (z resume)
                                    print "krok 2"
            <--[yield val]--        yield(y+1)
got 100                             [pauza]
resume(co, 7)   --[args]-->         z = 7
                                    print "krok 3"
            <--[return val]--       return "koniec"
got "koniec"                        [DEAD]
resume(co)
got false, "cannot resume dead..."
```

`resume` → `yield`: argumenty `resume` (oprócz pierwszego, co) → wynik `yield`.  
`yield` → `resume`: argumenty `yield` → wynik `resume` (po `true`).  
Końcowy `return` z funkcji → ostatni wynik `resume`.

#### Stany korutyny

```lua
print(coroutine.status(co))   -- jeden z:
-- "suspended"  — utworzona lub po yield
-- "running"    — aktualnie wykonująca (! zwykle widzisz tylko z wewnątrz)
-- "normal"     — wywołała inną korutynę i czeka na nią
-- "dead"       — zakończona (przez return albo error)
```

```lua
local co = coroutine.create(function()
    print("inside, status:", coroutine.status(coroutine.running()))
    -- "running"
end)

print("przed resume:", coroutine.status(co))   -- "suspended"
coroutine.resume(co)
-- inside, status: running
print("po resume:", coroutine.status(co))      -- "dead"
```

`coroutine.running()` zwraca bieżącą korutynę (lub nil w main thread).

#### Errors w korutynie

```lua
local co = coroutine.create(function()
    error("coś się zepsuło")
end)

local ok, err = coroutine.resume(co)
print(ok, err)
-- false   ...:coś się zepsuło

print(coroutine.status(co))    -- "dead"
```

`resume` jest jak `pcall` — łapie błędy. Zwraca `false, errmsg` zamiast propagować.

To znaczy: błąd w korutynie **nie** wywala hosta. Korutyna umiera, host dostaje `false` jako pierwszy wynik.

To jest jeden z powodów, dla których korutyny w sandboxie HSS są bezpieczne — niezaufany skrypt nie może crashować hosta nawet rzucając błędy.

#### `coroutine.yield` w funkcji wewnętrznej

```lua
local function helper()
    print("helper start")
    coroutine.yield("z helpera")
    print("helper end")
end

local co = coroutine.create(function()
    helper()
    coroutine.yield("z main")
end)

print(coroutine.resume(co))    -- "helper start"  -> true, "z helpera"
print(coroutine.resume(co))    -- "helper end"  -> true, "z main"
print(coroutine.resume(co))    -- true (koniec, nic nie zwraca)
```

`yield` wstrzymuje **całą korutynę**, niezależnie od głębokości stack'u. To kluczowe — korutyna może yieldować z dowolnego miejsca w wywoływanych funkcjach.

#### Pułapka: `yield` w pcall (5.1)

W Lua 5.1 nie można `yield` przez `pcall`. W 5.2+ można. Ponieważ kurs używa 5.4 — działa, ale warto wiedzieć dla kompatybilności wstecznej.

```lua
local co = coroutine.create(function()
    pcall(function()
        coroutine.yield("z wewnątrz pcall")
    end)
    print("po pcall")
end)

print(coroutine.resume(co))    -- true   "z wewnątrz pcall"  (5.2+)
                                -- w 5.1: błąd "attempt to yield across C-call boundary"
print(coroutine.resume(co))    -- "po pcall"
```

#### Kiedy korutyna kończy?

Trzy sposoby:
1. **Funkcja zwróci** (`return`) — końcowa wartość trafia do `resume`.
2. **Funkcja rzuci błąd** — `resume` zwraca `false, errmsg`.
3. **`yield` na poziomie głównym** korutyny po zakończeniu — niemożliwe (ostatni `yield` jest przed return).

Po zakończeniu — `status` to `"dead"`. Kolejne `resume` zwraca `false, "cannot resume dead coroutine"`.

### Pułapki

1. **`coroutine.create` NIE uruchamia** — pierwszy `resume` startuje.
2. **Pierwsze argumenty `resume` lecą do funkcji**, kolejne — do `yield`.
3. **Pierwszy wynik `resume` to status** (true/false), reszta to wartości yield/return.
4. **Błąd w korutynie nie wywala hosta** — `resume` zwraca `false`.
5. **`yield` z głównej (main) korutyny** — błąd "attempt to yield from outside a coroutine".

### Zadania

**Zadanie 6.1.1**  
Napisz korutynę, która drukuje liczby 1-5 z yield między nimi. Wzbudź ją resume'ami w pętli for. Zlicz ile razy musiałeś wywołać resume.

**Zadanie 6.1.2**  
Korutyna `fibonacci_co()` yielduje kolejne liczby Fibonacciego: 0, 1, 1, 2, 3, 5, ... Pokaż pierwsze 10.

**Zadanie 6.1.3**  
Napisz funkcję `safe_resume(co, ...)` jako wrapper na `coroutine.resume`, który:
- jeśli `resume` zwraca `false, err` → zwraca `nil, err`
- jeśli `resume` zwraca `true, ...wyniki` → zwraca `...wyniki`
- jeśli korutyna mortwa → zwraca `nil, "dead"`

```lua
local r, err = safe_resume(co)
if r == nil then print("error:", err) end
```

**Zadanie 6.1.4**  
Korutyna "echo" — yielduje argumenty resume w kolejności. Pierwszy resume z `"a"` → yielduje `"a"`. Drugi z `"b"` → yielduje `"b"`. Itd. Zwraca `"end"` po N yieldach.

**Zadanie 6.1.5**  
Pułapka — co wypisze ten kod?
```lua
local co = coroutine.create(function(a, b, c)
    print("got:", a, b, c)
    local x, y, z = coroutine.yield(1, 2, 3)
    print("after yield:", x, y, z)
end)

print(coroutine.resume(co, 10, 20, 30))
print(coroutine.resume(co, "a", "b", "c"))
```

Najpierw odpowiedz, potem uruchom.

---

### Rozwiązania

#### Rozwiązanie 6.1.1

```lua
-- five_yields.lua
local co = coroutine.create(function()
    for i = 1, 5 do
        print("krok", i)
        coroutine.yield(i)
    end
end)

local resume_count = 0
while coroutine.status(co) ~= "dead" do
    coroutine.resume(co)
    resume_count = resume_count + 1
end

print("liczba resume:", resume_count)
-- krok 1
-- krok 2
-- krok 3
-- krok 4
-- krok 5
-- liczba resume: 6
```

**Niespodzianka — 6, nie 5.** Po piątym yield korutyna jest nadal "suspended" (czeka na resume żeby skończyć). Szóste resume — kończy funkcję, status zmienia się na "dead", pętla wychodzi.

To częsty błąd off-by-one. Bezpieczniej:

```lua
while coroutine.status(co) ~= "dead" do
    local ok, val = coroutine.resume(co)
    if val ~= nil then
        print("yield:", val)
    end
end
```

`val == nil` po skończeniu (gdy funkcja `return` bez wartości) — nie drukujemy.

#### Rozwiązanie 6.1.2

```lua
-- fibonacci_co.lua
local fib_co = coroutine.create(function()
    local a, b = 0, 1
    while true do
        coroutine.yield(a)
        a, b = b, a + b
    end
end)

for _ = 1, 10 do
    local _, v = coroutine.resume(fib_co)
    io.write(v, " ")
end
print()
-- 0 1 1 2 3 5 8 13 21 34
```

**Korutyna "infinite"** — `while true` z `yield` w środku. Nie kończy się, ale dopóki host nie woła resume — nic się nie wykonuje. To dokładnie pattern generatora.

`local _, v = coroutine.resume(fib_co)` — pomijamy `true`, bierzemy wartość yield.

#### Rozwiązanie 6.1.3

```lua
-- safe_resume.lua
local function safe_resume(co, ...)
    if coroutine.status(co) == "dead" then
        return nil, "dead"
    end
    local results = table.pack(coroutine.resume(co, ...))
    if results[1] then
        return table.unpack(results, 2, results.n)
    end
    return nil, results[2]
end

-- Test:
local co = coroutine.create(function()
    coroutine.yield(42)
    error("bad")
end)

print(safe_resume(co))    -- 42
print(safe_resume(co))    -- nil   ...:bad
print(safe_resume(co))    -- nil   "dead"
```

Wzorzec analogiczny do `safe(fn)` z M5.2.3 — konwertuje pcall-style (`true/false, ...`) na "wynik albo nil + errmsg".

W praktyce zawsze opakowuję `coroutine.resume` w taki helper — zewnętrzny kod nie powinien znać detali "true jako pierwszy wynik".

#### Rozwiązanie 6.1.4

```lua
-- echo_co.lua
local function make_echo(n)
    return coroutine.create(function(first)
        local val = first
        for _ = 1, n - 1 do
            val = coroutine.yield(val)
        end
        coroutine.yield(val)
        return "end"
    end)
end

-- Test:
local co = make_echo(3)
print(coroutine.resume(co, "a"))    -- true   "a"
print(coroutine.resume(co, "b"))    -- true   "b"
print(coroutine.resume(co, "c"))    -- true   "c"
print(coroutine.resume(co))         -- true   "end"
```

Pierwszy argument idzie do funkcji (`first`), kolejne resume → arg do yield → przypisany do `val`, zwracany przez następny yield.

To rozwiązanie też pokazuje, że `coroutine.yield` może odbierać wartość z `resume` — to "two-way" channel.

#### Rozwiązanie 6.1.5

```
got:  10  20  30
true   1   2   3
after yield:  a   b   c
true
```

Przepływ:
1. `resume(co, 10, 20, 30)` — `10, 20, 30` lecą do funkcji jako `a, b, c`. Funkcja drukuje, `yield(1, 2, 3)`. `1, 2, 3` wracają do resume. **Resume zwraca `true, 1, 2, 3`**.
2. `resume(co, "a", "b", "c")` — `"a", "b", "c"` to argumenty zwrócone z `yield`. Czyli `x, y, z = "a", "b", "c"`. Funkcja drukuje, kończy się (return bez wartości). **Resume zwraca `true`** (tylko status, brak return val).

To dobry test rozumienia dwukierunkowego przepływu argumentów. Jeśli odpowiedziałeś poprawnie — opanowałeś podstawy.

### Sprawdź się

- [ ] Pamiętam, że `create` nie startuje korutyny — pierwszy `resume` startuje
- [ ] Wiem, że pierwsze `resume(co, args)` przekazuje args do funkcji, kolejne — do `yield`
- [ ] Rozumiem dwukierunkowy przepływ: yield(x) → resume zwraca x; resume(y) → yield zwraca y
- [ ] Znam stany: suspended, running, normal, dead
- [ ] Wiem, że `resume` nie wywala host na error
- [ ] Pamiętam pułapkę off-by-one: po ostatnim yield jeszcze jeden resume potrzebny by skończyć

---

## Lekcja 6.2: `coroutine.wrap`, generic for, generatory

### Cel

Używasz `coroutine.wrap` jako lżejszego API. Tworzysz iteratory z korutynami i używasz w `for ... in`. Znasz różnicę i kompromisy.

### Materiał

#### `coroutine.wrap(fn)` — wygodniejsze API

`wrap` zwraca **funkcję**, która przy każdym wywołaniu robi `resume`:

```lua
local gen = coroutine.wrap(function()
    for i = 1, 5 do
        coroutine.yield(i * i)
    end
end)

print(gen())   -- 1
print(gen())   -- 4
print(gen())   -- 9
print(gen())   -- 16
print(gen())   -- 25
print(gen())   -- nil (po zakończeniu)
```

**Zalety wrap:**
- Krótsza składnia (`gen()` zamiast `coroutine.resume(co)`).
- Argumenty wrap-a przekazywane do funkcji, kolejne argumenty do `yield`.
- Wyniki yield wracają jako wynik wywołania.

**Wady wrap:**
- Nie ma odpowiednika `coroutine.status` na wrap-ie.
- Błędy **propagują** zamiast być łapane (wracają `false, err` jak w resume) — `wrap` rzuca błąd jako exception.

```lua
local gen = coroutine.wrap(function()
    coroutine.yield(1)
    error("zła rzecz")
end)

print(gen())    -- 1
print(gen())    -- ! BŁĄD: ...:zła rzecz   (rzuca exception)
```

To znaczy: wrap dla "trusted" generatorów. Resume + safe_resume dla "untrusted" gdzie chcesz łapać błędy.

#### Generic for z korutyną

`for var in iterator do` jest "syntactic sugar" dla:

```lua
local iter = expr
while true do
    local val = iter()
    if val == nil then break end
    -- użyj val
end
```

To znaczy — funkcja zwracana przez `coroutine.wrap` to **gotowy iterator** dla `for`:

```lua
for v in coroutine.wrap(function()
    for i = 1, 5 do
        coroutine.yield(i * i)
    end
end) do
    io.write(v, " ")
end
print()
-- 1 4 9 16 25
```

**To jest jedna z najbardziej eleganckich rzeczy w Lua.** W jednym wyrażeniu masz: definicja generatora + iteracja po nim.

#### Permutacje — klasyczny przykład

```lua
local function permutations(t)
    return coroutine.wrap(function()
        local function permute(arr, k)
            if k == #arr then
                coroutine.yield(arr)
                return
            end
            for i = k, #arr do
                arr[k], arr[i] = arr[i], arr[k]
                permute(arr, k + 1)
                arr[k], arr[i] = arr[i], arr[k]   -- backtrack
            end
        end
        local copy = {}
        for i, v in ipairs(t) do copy[i] = v end
        permute(copy, 1)
    end)
end

for p in permutations({"a", "b", "c"}) do
    print(table.concat(p, ""))
end
-- abc
-- acb
-- bac
-- bca
-- cba
-- cab
```

Klasyczny rekurencyjny algorytm + `yield` zamiast "zbieraj do listy". Generator daje **leniwy** wynik — nawet permutacje 10! = 3.6M elementów można iterować bez alokacji listy.

**Pułapka:** ta wersja `yield(arr)` daje TĘ SAMĄ tabelę za każdym razem (po backtrack zmieniona). Klient, który przechowa wynik:

```lua
local saved = {}
for p in permutations({"a", "b", "c"}) do
    saved[#saved + 1] = p   -- ! wszystkie wpisy wskazują na ten sam arr
end
-- saved zawiera 6 razy ostatnią permutację
```

Trzeba `coroutine.yield({...arr})` (kopia) lub klient sam kopiuje. Świadomy projekt API.

#### Pierwsze N elementów leniwego generatora

```lua
local function take(gen, n)
    local result = {}
    for i = 1, n do
        local v = gen()
        if v == nil then break end
        result[i] = v
    end
    return result
end

-- Nieskończony generator naturalsów:
local nats = coroutine.wrap(function()
    local i = 1
    while true do
        coroutine.yield(i)
        i = i + 1
    end
end)

local first10 = take(nats, 10)
print(table.concat(first10, " "))
-- 1 2 3 4 5 6 7 8 9 10

-- Można dalej brać — nats zachowuje stan:
local next5 = take(nats, 5)
print(table.concat(next5, " "))
-- 11 12 13 14 15
```

**Generator zachowuje stan między wywołaniami.** Nieskończona sekwencja jest naturalna — nie ma problemu z alokacją.

#### Iterator z parametrami stanu

Generic for w Lua wspiera bardziej ogólny pattern:

```lua
for var_1, var_2, ..., var_n in iterator, state, control do ... end
```

Iterator dostaje `(state, control)` i zwraca `(new_control, ...)`. Gdy zwróci nil — koniec.

`coroutine.wrap` upraszcza to do "iterator bez state/control" — closure trzyma stan.

```lua
-- Z korutyną (proste):
for k, v in coroutine.wrap(function()
    coroutine.yield("a", 1)
    coroutine.yield("b", 2)
    coroutine.yield("c", 3)
end) do
    print(k, v)
end
-- a   1
-- b   2
-- c   3
```

Wielowartościowy yield → wielowartościowa zmienna w `for`.

#### `coroutine.wrap` vs "zwykły" closure

Możesz pisać iteratory bez korutyn — przez closure (M3.5):

```lua
local function range_iter(start, stop)
    local i = start - 1
    return function()
        i = i + 1
        if i > stop then return nil end
        return i
    end
end

for v in range_iter(1, 5) do
    io.write(v, " ")
end
print()
-- 1 2 3 4 5
```

To **closure-iterator**. Działa, ale wymaga ręcznego trzymania stanu (`i`). Dla skomplikowanych algorytmów (np. drzewa, generatory rekurencyjne) — koszmar.

Wersja korutynowa:

```lua
local function range_iter_co(start, stop)
    return coroutine.wrap(function()
        for i = start, stop do
            coroutine.yield(i)
        end
    end)
end
```

**Mniejsza, prostsza, bardziej czytelna.** Korutyna sama trzyma stan w swoim "zachowanym stosie".

#### Kiedy korutyna, kiedy closure

| Sytuacja | Wybór |
|---|---|
| Prosty iterator (range, lista) | closure |
| Rekurencyjny generator (drzewa, kombinatoryka) | korutyna |
| Bardzo wiele iteracji (mln+), wydajność krytyczna | closure (mniej overhead per step) |
| State machine z wieloma scenariuszami | korutyna |
| Stop/resume na requesty zewnętrzne | korutyna (yield) |

Korutyna ma overhead per resume (~kilka mikrosekund). Dla iteratora po milionach elementów — closure jest szybsza. Dla skomplikowanej logiki gdzie czytelność > microoptimalizacja — korutyna wygrywa.

### Pułapki

1. **`wrap` rzuca błędy** zamiast łapać. Dla untrusted code — `create + resume + safe_resume`.
2. **`yield` na ostatnim miejscu** w pętli — funkcja musi się skończyć, by `wrap` zwróciła nil.
3. **Przekazywanie referencji przez yield** — odbiorca może modyfikować. Świadomie kopiuj jeśli potrzeba.
4. **Korutyna w pętli** — overhead per yield. Dla mln iteracji rozważ alternatywy.

### Zadania

**Zadanie 6.2.1**  
Napisz `range_co(a, b, step)` — generator zakresu jako korutyna. Następnie iteruj w `for`. Wszystkie wartości default jak w M3 Sprawdzian 1.

**Zadanie 6.2.2**  
Napisz generator `tree_traverse(root)` w trybie pre-order, gdzie tree to:
```lua
{value = 1, children = {
    {value = 2, children = {}},
    {value = 3, children = {
        {value = 4, children = {}},
    }},
}}
```

Yielduje wartości w kolejności pre-order. Test:
```lua
for v in tree_traverse(tree) do io.write(v, " ") end
-- 1 2 3 4
```

**Zadanie 6.2.3**  
Napisz `lazy_filter(gen, predicate)` — bierze generator, zwraca generator yielding tylko elementy spełniające predykat. Implementacja jako korutyna.

```lua
local nats = coroutine.wrap(function()
    local i = 1; while true do coroutine.yield(i); i = i + 1 end
end)

local odds = lazy_filter(nats, function(x) return x % 2 == 1 end)
for _ = 1, 5 do io.write(odds(), " ") end
-- 1 3 5 7 9
```

**Zadanie 6.2.4**  
Napisz `gen_powerset(t)` — generator wszystkich podzbiorów tabeli `t`. Yielduje tabele.  
Test:
```lua
for s in gen_powerset({"a", "b", "c"}) do
    print(table.concat(s, ","))
end
-- (pusty)
-- a
-- b
-- a,b
-- c
-- a,c
-- b,c
-- a,b,c
```

(Kolejność może się różnić — ważne że są wszystkie 2^n = 8 podzbiorów.)

**Zadanie 6.2.5**  
Napisz `gen_pairs(...)` — generator wszystkich par (a, b) gdzie a, b są elementami z różnych input tabel. Wyższa kolejność: dla każdego a iterujemy wszystkie b.

```lua
for a, b in gen_pairs({"x", "y"}, {1, 2, 3}) do
    print(a, b)
end
-- x   1
-- x   2
-- x   3
-- y   1
-- y   2
-- y   3
```

---

### Rozwiązania

#### Rozwiązanie 6.2.1

```lua
-- range_co.lua
local function range_co(a, b, step)
    local start, stop
    if b == nil then
        start, stop = 1, a
    else
        start, stop = a, b
    end
    step = step or 1
    
    return coroutine.wrap(function()
        if step > 0 then
            for i = start, stop, step do
                coroutine.yield(i)
            end
        elseif step < 0 then
            for i = start, stop, step do
                coroutine.yield(i)
            end
        end
        -- step == 0 — niech będzie błąd
    end)
end

-- Test:
io.write("range_co(5): ")
for v in range_co(5) do io.write(v, " ") end
print()
-- 1 2 3 4 5

io.write("range_co(2, 6): ")
for v in range_co(2, 6) do io.write(v, " ") end
print()
-- 2 3 4 5 6

io.write("range_co(1, 10, 2): ")
for v in range_co(1, 10, 2) do io.write(v, " ") end
print()
-- 1 3 5 7 9

io.write("range_co(10, 1, -1): ")
for v in range_co(10, 1, -1) do io.write(v, " ") end
print()
-- 10 9 8 7 6 5 4 3 2 1
```

Porównaj z M3 Sprawdzian 1 (closure-based) — kod krótszy, prostszy. Korutyna sama trzyma stan iteracji.

#### Rozwiązanie 6.2.2

```lua
-- tree_traverse.lua
local function tree_traverse(root)
    return coroutine.wrap(function()
        local function visit(node)
            coroutine.yield(node.value)
            for _, child in ipairs(node.children) do
                visit(child)    -- rekurencja — yield z głębi działa!
            end
        end
        visit(root)
    end)
end

-- Test:
local tree = {value = 1, children = {
    {value = 2, children = {}},
    {value = 3, children = {
        {value = 4, children = {}},
        {value = 5, children = {}},
    }},
    {value = 6, children = {}},
}}

io.write("pre-order: ")
for v in tree_traverse(tree) do io.write(v, " ") end
print()
-- pre-order: 1 2 3 4 5 6

-- Tree z 100 elementów:
local big_tree = {value = "root", children = {}}
for i = 1, 100 do
    table.insert(big_tree.children, {value = i, children = {}})
end
local count = 0
for v in tree_traverse(big_tree) do count = count + 1 end
print("count:", count)    -- 101
```

**To jest dokładnie miejsce, gdzie korutyna błyszczy.** Rekurencyjny traverse z `yield` w środku — niemożliwy do napisania zwięźle z closure. Closure musiałaby symulować stack ręcznie. Korutyna pisze się jak normalny kod.

W KarmazynOS — przy iteracji po HSS Φ-space (drzewo sesji → atomy → bubbles), korutyny dają najczystszą abstrakcję.

#### Rozwiązanie 6.2.3

```lua
-- lazy_filter.lua
local function lazy_filter(gen, predicate)
    return coroutine.wrap(function()
        while true do
            local v = gen()
            if v == nil then return end
            if predicate(v) then
                coroutine.yield(v)
            end
        end
    end)
end

-- Test:
local nats = coroutine.wrap(function()
    local i = 1
    while true do
        coroutine.yield(i)
        i = i + 1
    end
end)

local odds = lazy_filter(nats, function(x) return x % 2 == 1 end)
for _ = 1, 5 do io.write(odds(), " ") end
print()
-- 1 3 5 7 9

-- Łańcuch: filter -> map -> take
local function lazy_map(gen, fn)
    return coroutine.wrap(function()
        while true do
            local v = gen()
            if v == nil then return end
            coroutine.yield(fn(v))
        end
    end)
end

local nats2 = coroutine.wrap(function()
    local i = 1
    while true do coroutine.yield(i); i = i + 1 end
end)

local odd_squares = lazy_map(
    lazy_filter(nats2, function(x) return x % 2 == 1 end),
    function(x) return x * x end
)

for _ = 1, 5 do io.write(odd_squares(), " ") end
print()
-- 1 9 25 49 81
```

Porównaj z M3 Sprawdzian 7 (`lazy_filter`/`lazy_map` jako closures). Korutynowa wersja **znacznie czytelniejsza**. Closure musiała być stanowa, korutyna jest "naturalnie pisana" jak imperatywny kod.

#### Rozwiązanie 6.2.4

```lua
-- gen_powerset.lua
local function gen_powerset(t)
    return coroutine.wrap(function()
        local n = #t
        -- 2^n podzbiorów: każdy bit reprezentuje "czy wybrać element i"
        for mask = 0, (1 << n) - 1 do
            local subset = {}
            for i = 1, n do
                if (mask & (1 << (i - 1))) ~= 0 then
                    subset[#subset + 1] = t[i]
                end
            end
            coroutine.yield(subset)
        end
    end)
end

-- Test:
for s in gen_powerset({"a", "b", "c"}) do
    print("{" .. table.concat(s, ", ") .. "}")
end
-- {}
-- {a}
-- {b}
-- {a, b}
-- {c}
-- {a, c}
-- {b, c}
-- {a, b, c}

-- Większy zbiór:
local count = 0
for _ in gen_powerset({1, 2, 3, 4, 5}) do count = count + 1 end
print("powerset of 5 elements:", count, "= 2^5 =", 1 << 5)
-- powerset of 5 elements: 32   = 2^5 = 32
```

Bitowa kombinatoryka — dla każdej liczby 0..2^n-1 traktujemy bity jako "wybrane/niewybrane". Bardzo zwięzłe dla n ≤ 30 (bo 2^31 to limit integer dla mask).

Yieldujemy **świeże** tabele za każdym razem — klient może bezpiecznie zachować je.

#### Rozwiązanie 6.2.5

```lua
-- gen_pairs.lua
local function gen_pairs(a, b)
    return coroutine.wrap(function()
        for _, x in ipairs(a) do
            for _, y in ipairs(b) do
                coroutine.yield(x, y)
            end
        end
    end)
end

-- Test:
for a, b in gen_pairs({"x", "y"}, {1, 2, 3}) do
    print(a, b)
end
-- x   1
-- x   2
-- x   3
-- y   1
-- y   2
-- y   3

-- Cartesian product wielu tabel:
local function gen_product(...)
    local tabs = table.pack(...)
    return coroutine.wrap(function()
        local function rec(idx, acc)
            if idx > tabs.n then
                coroutine.yield(table.unpack(acc, 1, tabs.n))
                return
            end
            for _, v in ipairs(tabs[idx]) do
                acc[idx] = v
                rec(idx + 1, acc)
            end
        end
        rec(1, {})
    end)
end

print("--- product 3 tabel ---")
for x, y, z in gen_product({1, 2}, {"a", "b"}, {true, false}) do
    print(x, y, z)
end
-- 1   a   true
-- 1   a   false
-- 1   b   true
-- 1   b   false
-- 2   a   true
-- 2   a   false
-- 2   b   true
-- 2   b   false
```

`yield(x, y)` z dwoma wartościami → `for a, b in ...` z dwoma zmiennymi. Multiple values flow through.

`gen_product` to bonus — Cartesian product n tabel. Rekurencyjny `rec` schodzi po indeksach, w deepest level yielduje pełną krotkę. Klasyk kombinatoryczny.

### Sprawdź się

- [ ] Wiem, co zwraca `coroutine.wrap` (funkcję) i jak ją wywoływać
- [ ] Pamiętam, że `wrap` propaguje błędy (nie łapie jak resume)
- [ ] Umiem użyć generatora w `for v in gen do`
- [ ] Wiem, że yield(x, y) → for a, b in gen do z multiple values
- [ ] Rozumiem czemu rekurencyjny generator jest trywialny w korutynach
- [ ] Znam kompromis closure (mały overhead) vs korutyna (czytelność)

---

## Lekcja 6.3: Producer/consumer i pipelines

### Cel

Implementujesz wzorzec producer/consumer. Budujesz pipeline'y leniwie ewaluowane. Rozumiesz jak korutyny zastępują thread-pools w prostych przypadkach.

### Materiał

#### Producer/consumer — klasyczny pattern

```lua
-- Producer: generuje dane
local function make_producer()
    return coroutine.wrap(function()
        for i = 1, 10 do
            print("producer: produkuję " .. i)
            coroutine.yield(i)
        end
        print("producer: koniec")
    end)
end

-- Consumer: konsumuje dane
local function consumer(producer)
    while true do
        local v = producer()
        if v == nil then break end
        print("consumer: konsumuję " .. v)
    end
end

consumer(make_producer())
-- producer: produkuję 1
-- consumer: konsumuję 1
-- producer: produkuję 2
-- consumer: konsumuję 2
-- ...
```

**Kluczowa obserwacja:** producer i consumer wymieniają dane na żądanie. Producer **nie** generuje wszystkiego naraz — generuje 1 element gdy consumer zapyta. Brak buforu, brak pamięci na pełną listę.

#### Pipeline z filtrem

```lua
local function generate(n)
    return coroutine.wrap(function()
        for i = 1, n do
            coroutine.yield(i)
        end
    end)
end

local function filter_p(gen, predicate)
    return coroutine.wrap(function()
        while true do
            local v = gen()
            if v == nil then return end
            if predicate(v) then
                coroutine.yield(v)
            end
        end
    end)
end

local function map_p(gen, fn)
    return coroutine.wrap(function()
        while true do
            local v = gen()
            if v == nil then return end
            coroutine.yield(fn(v))
        end
    end)
end

local function consume(gen, fn)
    while true do
        local v = gen()
        if v == nil then break end
        fn(v)
    end
end

-- Pipeline: 1..100 -> filter even -> map x*x -> consume print
consume(
    map_p(
        filter_p(generate(100), function(x) return x % 2 == 0 end),
        function(x) return x * x end
    ),
    function(x) print(x) end
)
-- 4
-- 16
-- 36
-- ...
-- 9604
-- 10000
```

**Każdy krok pipeline'u to korutyna.** Dane "płyną" przez pipeline element po elemencie — nigdy nie ma w pamięci pełnej listy.

To jest **shell-style processing** w Lua. `cat input | grep ... | awk ... | head -10`. Każdy `|` to korutyna.

#### Buffer między producer a consumer

Czasami chcesz, żeby producer mógł "iść do przodu" gdy consumer jest wolny:

```lua
local function buffered(gen, buffer_size)
    local buffer = {}
    return coroutine.wrap(function()
        -- Wypełnij bufor
        for _ = 1, buffer_size do
            local v = gen()
            if v == nil then break end
            buffer[#buffer + 1] = v
        end
        
        while #buffer > 0 do
            -- Wypuść jeden, dolej jeden
            local out = table.remove(buffer, 1)
            local new = gen()
            if new ~= nil then
                buffer[#buffer + 1] = new
            end
            coroutine.yield(out)
        end
    end)
end
```

To jest **prefetch buffer** — wewnętrznie producer wyprzedza consumer'a o `buffer_size` elementów. Użyteczne gdy producer ma duży overhead per element.

#### Pull vs push semantyka

Dwa style:

**Pull:** consumer pyta "daj kolejny" → producer dostarcza. Lazy. Dominujący w Lua.

```lua
local v = gen()    -- consumer pulls
```

**Push:** producer "wysyła" → consumer reaguje. Reactive style.

```lua
producer:on("data", function(v) ... end)    -- push
```

W Lua mamy pull przez korutyny natywnie. Push wymaga callback'ów (M3.3 observer).

Konwersja jednego na drugi:

```lua
-- Pull -> Push
local function push_from_pull(gen, callback)
    while true do
        local v = gen()
        if v == nil then break end
        callback(v)
    end
end

-- Push -> Pull (z buforem - wymaga lock'ów lub thread w prawdziwym async)
-- W single-threaded Lua po prostu zbieramy do listy:
local function pull_from_push(register_fn)
    local items = {}
    register_fn(function(v) items[#items + 1] = v end)
    -- ...wszystko trzeba z góry; nie ma "leniwego" pull bez async
    return ipairs(items)
end
```

W KarmazynOS dla event-stream-ów zwykle pull (korutyny). Push tylko gdy masz prawdziwy async (np. integracja z LSocket).

#### Yield z wieloma wartościami — ustrukturyzowane wiadomości

```lua
local function event_stream()
    return coroutine.wrap(function()
        coroutine.yield("INFO", "session started", {sig = "abc"})
        coroutine.yield("WARN", "high phi", {phi = 0.95})
        coroutine.yield("ERROR", "atom rejected", {reason = "quota"})
    end)
end

for level, msg, ctx in event_stream() do
    print(string.format("[%s] %s (%s)", level, msg, ctx.sig or ctx.phi or ctx.reason))
end
-- [INFO] session started (abc)
-- [WARN] high phi (0.95)
-- [ERROR] atom rejected (quota)
```

`yield(level, msg, ctx)` → `for a, b, c in ...` z trzema zmiennymi. Naturalne dla strumieni eventów.

#### Stop/abort korutyny

Korutyna nie ma "killable" API. Sposoby na "anulowanie":

1. **Po prostu nie wzbudzać.** Jeśli host nie woła resume, korutyna nie wykonuje. Eventually GC ją sprzątnie (gdy nie ma referencji).

2. **Przekazać "stop signal" przez yield → resume.**

```lua
local function cancellable_gen()
    return coroutine.wrap(function()
        local i = 0
        while true do
            i = i + 1
            local cmd = coroutine.yield(i)
            if cmd == "stop" then return end
        end
    end)
end

local g = cancellable_gen()
print(g())          -- 1   (default arg do yield = nil)
print(g())          -- 2
print(g("stop"))    -- nil (korutyna kończy)
```

3. **Time/quota check w środku korutyny** (samokontrola).

W M11 (DSL HSS) zobaczysz wzorzec "quota tick" — host periodycznie zatwierdza/odrzuca dalsze działanie skryptu.

### Pułapki

1. **Brak buforu** — pipeline jest tak szybki jak najwolniejszy element.
2. **Korutyna trzyma referencje** do swoich upvalues — pamięć rośnie z głębokością stack'u.
3. **`yield(nil)` jest zwykle złe** — bo `nil` w iterators to sygnał końca.
4. **Pipeline z error w środku** — propaguje przez wrap-a (jeśli wrap), zatrzymuje całość. Dla robustnego — używaj resume + safe_resume.

### Zadania

**Zadanie 6.3.1**  
Napisz `lines_co(filename)` — generator linii pliku (jako korutyna). Zamknij plik gdy plik się skończy lub korutyna zostanie GC.

```lua
for line in lines_co("data.txt") do
    print(line)
end
```

**Zadanie 6.3.2**  
Napisz `take_co(gen, n)` — generator pierwszych `n` elementów. Implementacja jako korutyna (nie jak w M3 closure).

**Zadanie 6.3.3**  
Napisz `chain_co(...)` — łączy wiele generatorów w jeden, yieldując kolejno wszystkie z każdego.

```lua
local g1 = range_co(1, 3)
local g2 = range_co(10, 12)
for v in chain_co(g1, g2) do io.write(v, " ") end
-- 1 2 3 10 11 12
```

**Zadanie 6.3.4**  
Pipeline word-counting:
- `words_co(filename)` — generator słów w pliku (lowercase)
- `count_words(gen)` — konsument zwracający tabelę `{word = count}`

Połącz: czytaj plik leniwie, zlicz słowa, wypisz top 10.

**Zadanie 6.3.5**  
Napisz `zip_co(a, b)` — generator par z dwóch generatorów. Kończy gdy którykolwiek się skończy.

```lua
for x, y in zip_co(range_co(1, 5), range_co(10, 15)) do
    print(x, y)
end
-- 1   10
-- 2   11
-- 3   12
-- 4   13
-- 5   14
-- (range 10-15 ma 6 elementów ale a tylko 5 → kończy na 5)
```

---

### Rozwiązania

#### Rozwiązanie 6.3.1

```lua
-- lines_co.lua
local function lines_co(filename)
    return coroutine.wrap(function()
        local f = assert(io.open(filename, "r"))
        -- Setmetatable dla GC cleanup:
        local handle = setmetatable({f = f}, {
            __gc = function(self)
                if self.f then self.f:close() end
            end
        })
        for line in f:lines() do
            coroutine.yield(line)
        end
        f:close()
        handle.f = nil
    end)
end

-- Test:
-- (zakładamy że istnieje data.txt)
local function create_test_file()
    local f = io.open("/tmp/lua_test.txt", "w")
    f:write("first line\nsecond line\nthird line\n")
    f:close()
end
create_test_file()

for line in lines_co("/tmp/lua_test.txt") do
    print("line:", line)
end
-- line: first line
-- line: second line
-- line: third line

-- Cleanup test file:
os.remove("/tmp/lua_test.txt")
```

`f:lines()` to wbudowany iterator po liniach pliku. Owijamy go w korutynę. `setmetatable` z `__gc` jako insurance — gdy korutyna zostanie GC przed zakończeniem (klient wziął tylko parę linii i przestał iterować), `__gc` zamknie file handle.

W praktyce `io.lines(filename)` jest sufficient i ma swój cleanup. Korutyna to wzorcowy przykład — pokazuje jak owinąć resource z cleanup.

#### Rozwiązanie 6.3.2

```lua
-- take_co.lua
local function take_co(gen, n)
    return coroutine.wrap(function()
        for _ = 1, n do
            local v = gen()
            if v == nil then return end
            coroutine.yield(v)
        end
    end)
end

-- Test:
local nats = coroutine.wrap(function()
    local i = 1; while true do coroutine.yield(i); i = i + 1 end
end)

for v in take_co(nats, 5) do io.write(v, " ") end
print()
-- 1 2 3 4 5

-- Po take, nats wciąż żyje:
print("next from nats:", nats())   -- 6

-- Take więcej niż jest:
local short = coroutine.wrap(function()
    coroutine.yield(1); coroutine.yield(2); coroutine.yield(3)
end)
for v in take_co(short, 10) do io.write(v, " ") end
print()
-- 1 2 3
```

Banalnie prosta wersja korutynowa — closure z M3 wymagała stanowego counter-a. Tutaj `for _ = 1, n` w środku korutyny wystarcza.

#### Rozwiązanie 6.3.3

```lua
-- chain_co.lua
local function chain_co(...)
    local gens = table.pack(...)
    return coroutine.wrap(function()
        for i = 1, gens.n do
            local g = gens[i]
            while true do
                local v = g()
                if v == nil then break end
                coroutine.yield(v)
            end
        end
    end)
end

-- Test:
local function range_co(a, b)
    return coroutine.wrap(function()
        for i = a, b do coroutine.yield(i) end
    end)
end

for v in chain_co(range_co(1, 3), range_co(10, 12), range_co(100, 101)) do
    io.write(v, " ")
end
print()
-- 1 2 3 10 11 12 100 101

-- Z różnymi typami:
local letters = coroutine.wrap(function()
    coroutine.yield("a"); coroutine.yield("b")
end)
local nums = coroutine.wrap(function()
    coroutine.yield(1); coroutine.yield(2); coroutine.yield(3)
end)

for v in chain_co(letters, nums) do
    print(v, type(v))
end
-- a   string
-- b   string
-- 1   number
-- 2   number
-- 3   number
```

Porównaj z M3 Sprawdzian 4 (closure-based chain) — kod krótszy, naturalny "for + yield" zamiast ręcznego state-tracking.

#### Rozwiązanie 6.3.4

```lua
-- word_count_pipeline.lua

local function create_test_file()
    local f = io.open("/tmp/lua_words.txt", "w")
    f:write("Phi space session opened. Phi value high.\n")
    f:write("New atom in space. Atom signature recorded.\n")
    f:write("Session phi value updated. Phi rises.\n")
    f:close()
end
create_test_file()

local function words_co(filename)
    return coroutine.wrap(function()
        local f = assert(io.open(filename, "r"))
        for line in f:lines() do
            for word in line:lower():gmatch("[%w]+") do
                coroutine.yield(word)
            end
        end
        f:close()
    end)
end

local function count_words(gen)
    local counts = {}
    while true do
        local w = gen()
        if w == nil then break end
        counts[w] = (counts[w] or 0) + 1
    end
    return counts
end

local function top_n(counts, n)
    local pairs_list = {}
    for w, c in pairs(counts) do
        pairs_list[#pairs_list + 1] = {word = w, count = c}
    end
    table.sort(pairs_list, function(a, b)
        if a.count ~= b.count then return a.count > b.count end
        return a.word < b.word
    end)
    local result = {}
    for i = 1, math.min(n, #pairs_list) do
        result[i] = pairs_list[i]
    end
    return result
end

-- Pipeline:
local counts = count_words(words_co("/tmp/lua_words.txt"))
local top = top_n(counts, 10)

for i, p in ipairs(top) do
    print(string.format("%2d. %-15s %d", i, p.word, p.count))
end

os.remove("/tmp/lua_words.txt")
-- 1. phi             4
-- 2. atom            2
-- 3. session         2
-- 4. space           2
-- 5. value           2
-- 6. high            1
-- 7. in              1
-- 8. new             1
-- 9. opened          1
-- 10. recorded        1
```

**Pipeline jest streamowy** — czyta plik linię po linii, każdą linię tnie na słowa, każde słowo doliczane do counts. Dla 1GB pliku tekstowego — pamięć stała (size mapy słów + buffer linii). Dla naiwnej wersji "wczytaj cały plik, split, count" — 1GB w pamięci.

#### Rozwiązanie 6.3.5

```lua
-- zip_co.lua
local function zip_co(a, b)
    return coroutine.wrap(function()
        while true do
            local va = a()
            local vb = b()
            if va == nil or vb == nil then return end
            coroutine.yield(va, vb)
        end
    end)
end

-- Test:
local function range_co(a, b)
    return coroutine.wrap(function()
        for i = a, b do coroutine.yield(i) end
    end)
end

print("--- równe długości ---")
for x, y in zip_co(range_co(1, 5), range_co(10, 14)) do
    print(x, y)
end
-- 1   10
-- 2   11
-- 3   12
-- 4   13
-- 5   14

print("--- różne długości — kończy na krótszym ---")
for x, y in zip_co(range_co(1, 5), range_co(10, 15)) do
    print(x, y)
end
-- 1   10
-- 2   11
-- 3   12
-- 4   13
-- 5   14
-- (a kończy na 5, b miałby 15 ale i tak kończymy)

-- Z różnymi typami:
local letters = coroutine.wrap(function()
    for c in ("abcde"):gmatch(".") do coroutine.yield(c) end
end)

for i, c in zip_co(range_co(1, 100), letters) do
    print(i, c)
end
-- 1   a
-- 2   b
-- 3   c
-- 4   d
-- 5   e
```

`zip_co` — klasyczna abstrakcja z funkcyjnych języków. Krótszy = kończy.

W KarmazynOS (M11) przyda się gdy iterujesz po dwóch równoległych strumieniach (np. `epochs` × `atoms`).

### Sprawdź się

- [ ] Rozumiem semantykę pull (consumer pyta) vs push (producer wysyła)
- [ ] Umiem zbudować pipeline `gen → filter → map → consume`
- [ ] Wiem, że pipeline streamuje element-po-elemencie (mała pamięć)
- [ ] Umiem pisać generatory yieldujące multiple values
- [ ] Pamiętam, że korutynę "anulujesz" po prostu przestając ją wzbudzać
- [ ] Wiem, jak owinąć resource z cleanup (`__gc` lub jawne close)

---

## Lekcja 6.4: Scheduler — round-robin, priority

### Cel

Implementujesz prosty scheduler wielu korutyn. Round-robin, priority, limit czasu CPU per task. To bezpośredni krok ku pipeline multi-agent w KarmazynOS.

### Materiał

#### Wątki w Lua — czego nie ma

Lua **nie ma** thread'ów OS w bibliotece standardowej. Korutyny to single-threaded — w danym momencie wykonuje się tylko jedna. Ale możesz mieć **wiele korutyn na zmianę** — to jest cooperative multitasking.

Wymaga to **schedulera** — kodu który decyduje "którą korutynę wzbudzić następnie".

#### Najprostszy scheduler — round-robin

```lua
local function make_scheduler()
    local tasks = {}    -- lista korutyn
    
    local sched = {}
    
    function sched.add(fn)
        local co = coroutine.create(fn)
        tasks[#tasks + 1] = co
    end
    
    function sched.run()
        while #tasks > 0 do
            -- Iteruj po wszystkich, każdą pchnij raz:
            for i = #tasks, 1, -1 do
                local co = tasks[i]
                local ok, err = coroutine.resume(co)
                if coroutine.status(co) == "dead" then
                    table.remove(tasks, i)
                end
            end
        end
    end
    
    return sched
end

-- Test:
local sched = make_scheduler()

sched.add(function()
    for i = 1, 3 do
        print("A", i)
        coroutine.yield()
    end
end)

sched.add(function()
    for i = 1, 4 do
        print("B", i)
        coroutine.yield()
    end
end)

sched.add(function()
    for i = 1, 2 do
        print("C", i)
        coroutine.yield()
    end
end)

sched.run()
-- A   1
-- B   1
-- C   1
-- A   2
-- B   2
-- C   2
-- A   3
-- B   3
-- B   4
```

**Round-robin:** każda korutyna dostaje jeden "tick" na rundę. Gdy umiera — usuwana. Pętla kończy gdy wszystkie martwe.

To jest kompletny, działający scheduler w 30 liniach.

#### Cooperative — task musi `yield`

```lua
sched.add(function()
    while true do
        print("nieskończona pętla")    -- ! brak yield
        -- BEZ yield korutyna nigdy nie pozwoli innym działać!
    end
end)
```

Cooperative znaczy: jeśli task nie zawoła `yield`, **monopolizuje CPU**. Inne tasks nigdy nie ruszą. Scheduler nie może go wstrzymać siłą (to NIE preemptive).

To jest fundamentalna cecha cooperative multitasking. W KarmazynOS musisz mieć wszystko:
1. Wymóg by user code wołał `yield` periodycznie.
2. Mechanizm "force yield" przez Lua hooks (Moduł 8 — C API).
3. Quota monitoring (count instrukcji od ostatniego yield → kill).

#### Sleep/wakeup — task czeka na zewnętrzne event

```lua
local function make_scheduler_v2()
    local ready = {}        -- gotowe do uruchomienia
    local sleeping = {}     -- czekające na deadline
    
    local sched = {}
    
    function sched.add(fn)
        ready[#ready + 1] = coroutine.create(fn)
    end
    
    function sched.sleep(seconds)
        local deadline = os.time() + seconds
        coroutine.yield("sleep", deadline)
    end
    
    function sched.run()
        while #ready > 0 or #sleeping > 0 do
            -- Sprawdź sleeping — przebudź gotowe:
            local now = os.time()
            for i = #sleeping, 1, -1 do
                if sleeping[i].deadline <= now then
                    ready[#ready + 1] = sleeping[i].co
                    table.remove(sleeping, i)
                end
            end
            
            if #ready == 0 then
                -- Wszystkie śpią — czekaj (w prawdziwym świecie sleep until next deadline)
                -- Tu uproszczenie:
                if #sleeping > 0 then
                    -- skok w przyszłość — symulacja
                    -- W produkcji: znaleźć min deadline, sleep do niego
                end
                -- Dla testu — po prostu break gdy wszystko śpi w nieskończoność
                if #sleeping == 0 then break end
            end
            
            -- Iteruj po ready:
            for i = #ready, 1, -1 do
                local co = ready[i]
                table.remove(ready, i)
                
                local ok, cmd, arg = coroutine.resume(co)
                
                if coroutine.status(co) == "dead" then
                    -- task skończony
                elseif cmd == "sleep" then
                    sleeping[#sleeping + 1] = {co = co, deadline = arg}
                else
                    -- normalny yield — wraca na koniec ready
                    ready[1] = co    -- na początek (najmniej fair) lub na koniec (FIFO)
                    -- Lepsze: table.insert(ready, 1, co) ale to O(n) - dla dużych liczb użyj queue
                end
            end
        end
    end
    
    return sched
end
```

To wzorzec **event loop** — popularny w async I/O (Node.js, asyncio Pythona). Korutyna może `sleep(N)` — zostaje przeniesiona na "sleeping queue", scheduler wraca do niej gdy minie czas.

#### Priority scheduler

```lua
local function make_priority_scheduler()
    local tasks = {}    -- {co, priority}
    
    local sched = {}
    
    function sched.add(fn, priority)
        tasks[#tasks + 1] = {co = coroutine.create(fn), priority = priority or 0}
    end
    
    function sched.run()
        while #tasks > 0 do
            -- Sortuj po priority (malejąco):
            table.sort(tasks, function(a, b) return a.priority > b.priority end)
            
            -- Wykonaj jeden krok task'u o najwyższym priority:
            local top = tasks[1]
            local ok, err = coroutine.resume(top.co)
            if coroutine.status(top.co) == "dead" then
                table.remove(tasks, 1)
            end
        end
    end
    
    return sched
end

-- Test:
local sched = make_priority_scheduler()

sched.add(function()
    for i = 1, 3 do
        print("LOW", i)
        coroutine.yield()
    end
end, 1)

sched.add(function()
    for i = 1, 3 do
        print("HIGH", i)
        coroutine.yield()
    end
end, 10)

sched.add(function()
    for i = 1, 3 do
        print("MED", i)
        coroutine.yield()
    end
end, 5)

sched.run()
-- HIGH   1
-- HIGH   2
-- HIGH   3
-- MED    1
-- MED    2
-- MED    3
-- LOW    1
-- LOW    2
-- LOW    3
```

**Strict priority** — wyższy priority działa do końca, potem niższy. To może być **starvation** — niski priority może nigdy nie ruszyć jeśli wysokie nieskończenie generują pracę.

Lepsze: **weighted round-robin** — priority decyduje "ile ticków per rundę".

#### Quota — limit CPU per task

```lua
local function make_quota_scheduler()
    local tasks = {}   -- {co, quota_remaining, quota_total}
    
    local sched = {}
    
    function sched.add(fn, quota)
        tasks[#tasks + 1] = {
            co = coroutine.create(fn),
            quota_remaining = quota or 10,
            quota_total = quota or 10,
        }
    end
    
    function sched.run()
        while #tasks > 0 do
            for i = #tasks, 1, -1 do
                local task = tasks[i]
                
                -- Pchnij task aż wyczerpie quota lub yieldnie:
                while task.quota_remaining > 0 do
                    local ok, err = coroutine.resume(task.co)
                    task.quota_remaining = task.quota_remaining - 1
                    
                    if coroutine.status(task.co) == "dead" then
                        table.remove(tasks, i)
                        break
                    end
                end
                
                -- Reset quota:
                task.quota_remaining = task.quota_total
            end
        end
    end
    
    return sched
end
```

To jest "ile resume na rundę". W realnym schedulerze: ile **instrukcji Lua** może wykonać przed force-yield (przez `lua_sethook` z C, Moduł 8).

#### Inter-task communication przez yield/resume

Tasks mogą "rozmawiać" przez wartości yield/resume:

```lua
-- Task wysyła wiadomości przez yield:
local function producer_task(channel)
    for i = 1, 5 do
        coroutine.yield("msg", i)    -- "send" via yield
    end
    coroutine.yield("done")
end

-- Scheduler przekazuje wiadomości:
-- (uproszczone — w pełnym schedulerze trzymasz channels jako tabela {name -> queue})
```

W praktyce dla KarmazynOS pipeline multi-agent — channel-based messaging. M11 pokażę pełną implementację.

### Pułapki

1. **Cooperative** — task bez yield blokuje wszystko. Wymóg dyscypliny.
2. **Sleeping queue z dużą liczbą deadline'ów** — szukanie min deadline = sortowanie. Min-heap dla O(log n).
3. **Priority + starvation** — strict priority może wyłączać niskie. Aging (priority rośnie z czasem) to klasyk.
4. **Resource leaks** — gdy task umiera/jest killed, jego resources (file handles, sockets) muszą być sprzątnięte. `with_resource` z M5.

### Zadania

**Zadanie 6.4.1**  
Zaimplementuj basic round-robin scheduler. Dodaj 3 tasks, każdy yieldujący 5 razy z różnymi nazwami. Pokaż interleaving.

**Zadanie 6.4.2**  
Rozszerz scheduler z 6.4.1 o `sched.spawn(fn)` wywoływane **z wewnątrz** korutyny — dynamicznie dodaje nowy task. Hint: spawn to specjalny yield ze schedulerem reagującym.

```lua
sched.add(function()
    print("main task")
    sched.spawn(function() print("dynamicznie dodany") end)
    coroutine.yield()
    print("main koniec")
end)
```

**Zadanie 6.4.3**  
Scheduler z `wait_for(value)` — task czeka aż inny task yieldnie tę wartość. Hint: trzymaj mapę `value → list of waiting tasks`.

**Zadanie 6.4.4**  
Quota-based scheduler: każdy task ma `max_resumes`. Po przekroczeniu — task killed (przerywany), scheduler emituje event "quota_exceeded".

**Zadanie 6.4.5**  
Priorytety z weighted round-robin: priority N = N ticków na rundę. Pokaż interleaving 3 tasks z priority 1, 2, 4.

---

### Rozwiązania

#### Rozwiązanie 6.4.1

```lua
-- basic_round_robin.lua
local function make_scheduler()
    local tasks = {}
    
    local sched = {}
    
    function sched.add(fn)
        tasks[#tasks + 1] = coroutine.create(fn)
    end
    
    function sched.run()
        while #tasks > 0 do
            for i = #tasks, 1, -1 do
                local co = tasks[i]
                local ok, err = coroutine.resume(co)
                if not ok then
                    print("[sched] task error:", err)
                end
                if coroutine.status(co) == "dead" then
                    table.remove(tasks, i)
                end
            end
        end
    end
    
    return sched
end

-- Test:
local sched = make_scheduler()

local function make_task(name, n)
    return function()
        for i = 1, n do
            print(name .. ": step " .. i)
            coroutine.yield()
        end
    end
end

sched.add(make_task("A", 5))
sched.add(make_task("B", 3))
sched.add(make_task("C", 4))

sched.run()
-- (Iterujemy od końca, więc kolejność C, B, A)
-- C: step 1
-- B: step 1
-- A: step 1
-- C: step 2
-- B: step 2
-- A: step 2
-- C: step 3
-- B: step 3
-- A: step 3
-- C: step 4
-- A: step 4
-- A: step 5
```

`for i = #tasks, 1, -1` — od końca, żeby `table.remove(i)` nie zepsuło iteracji. Klasyczny pattern dla "filter while iterating".

#### Rozwiązanie 6.4.2

```lua
-- spawn_scheduler.lua
local function make_scheduler()
    local tasks = {}
    local sched = {}
    
    function sched.add(fn)
        tasks[#tasks + 1] = coroutine.create(fn)
    end
    
    -- spawn: woła yield ze specjalnym command
    function sched.spawn(fn)
        coroutine.yield("spawn", fn)
    end
    
    function sched.run()
        while #tasks > 0 do
            local i = #tasks
            while i >= 1 do
                local co = tasks[i]
                local ok, cmd, arg = coroutine.resume(co)
                
                if not ok then
                    print("[sched] error:", cmd)
                end
                
                if cmd == "spawn" then
                    -- Dodaj nowy task na koniec:
                    tasks[#tasks + 1] = coroutine.create(arg)
                    -- zostaje tutaj — oryginal task wciąż tam
                end
                
                if coroutine.status(co) == "dead" then
                    table.remove(tasks, i)
                end
                i = i - 1
            end
        end
    end
    
    return sched
end

-- Test:
local sched = make_scheduler()

sched.add(function()
    print("main: krok 1")
    coroutine.yield()
    
    print("main: spawning child A")
    sched.spawn(function()
        for i = 1, 3 do
            print("childA: " .. i)
            coroutine.yield()
        end
    end)
    
    print("main: krok 2")
    coroutine.yield()
    
    print("main: spawning child B")
    sched.spawn(function()
        for i = 1, 2 do
            print("childB: " .. i)
            coroutine.yield()
        end
    end)
    
    print("main: koniec")
end)

sched.run()
-- main: krok 1
-- main: spawning child A
-- main: krok 2
-- childA: 1
-- main: spawning child B
-- main: koniec
-- childA: 2
-- childB: 1
-- childA: 3
-- childB: 2
```

`sched.spawn` wywołane z task'u **yieldnie ze specjalnym command** ("spawn"). Scheduler interpretuje yield-arg i dodaje nowy task. Eleganckie API.

W M11 (DSL HSS) ten pattern (yield + cmd) będzie podstawowy: `wait("event")`, `send(channel, msg)`, `kill(task_id)`, `set_phi(value)` — wszystko jako commands przekazywane przez yield.

#### Rozwiązanie 6.4.3

```lua
-- wait_scheduler.lua
local function make_scheduler()
    local ready = {}
    local waiting = {}    -- {value -> list of {co, ...}}
    
    local sched = {}
    
    function sched.add(fn)
        ready[#ready + 1] = coroutine.create(fn)
    end
    
    function sched.wait_for(value)
        coroutine.yield("wait", value)
    end
    
    function sched.notify(value, ...)
        coroutine.yield("notify", value, ...)
    end
    
    function sched.run()
        while #ready > 0 do
            local i = #ready
            while i >= 1 do
                local co = ready[i]
                local ok, cmd, arg, extra = coroutine.resume(co)
                
                if cmd == "wait" then
                    if not waiting[arg] then waiting[arg] = {} end
                    table.insert(waiting[arg], co)
                    table.remove(ready, i)
                elseif cmd == "notify" then
                    -- Przebudź wszystkich czekających na 'arg':
                    if waiting[arg] then
                        for _, wco in ipairs(waiting[arg]) do
                            ready[#ready + 1] = wco
                        end
                        waiting[arg] = nil
                    end
                end
                
                if coroutine.status(co) == "dead" then
                    -- już usunięty z ready jeśli wait, lub usuwamy teraz:
                    if cmd ~= "wait" then
                        table.remove(ready, i)
                    end
                end
                i = i - 1
            end
        end
    end
    
    return sched
end

-- Test:
local sched = make_scheduler()

sched.add(function()
    print("Task A: czekam na 'event_x'")
    sched.wait_for("event_x")
    print("Task A: odebrałem event_x, kontynuuję")
end)

sched.add(function()
    print("Task B: pracuję")
    coroutine.yield()
    print("Task B: wysyłam event_x")
    sched.notify("event_x")
    coroutine.yield()
    print("Task B: koniec")
end)

sched.add(function()
    print("Task C: czekam na 'event_x' (równolegle z A)")
    sched.wait_for("event_x")
    print("Task C: też odebrałem event_x")
end)

sched.run()
-- Task A: czekam na 'event_x'
-- Task B: pracuję
-- Task C: czekam na 'event_x' (równolegle z A)
-- Task B: wysyłam event_x
-- Task B: koniec
-- Task C: też odebrałem event_x
-- Task A: odebrałem event_x, kontynuuję
```

Klasyczny mechanizm **condition variable** / **event signaling**. Wielu czekających → wszystkich budzimy. To podstawowy primitive synchronizacji.

W KarmazynOS HSS — atom czeka na "phi crossed threshold", inny atom emituje event gdy phi się zmienia. Naturalnie pasuje.

#### Rozwiązanie 6.4.4

```lua
-- quota_scheduler.lua
local function make_scheduler()
    local tasks = {}    -- {co, resumes_used, max_resumes}
    local listeners = {}    -- event -> list of fn
    
    local sched = {}
    
    function sched.add(fn, max_resumes)
        tasks[#tasks + 1] = {
            co = coroutine.create(fn),
            resumes_used = 0,
            max_resumes = max_resumes or math.huge,
        }
    end
    
    function sched.on(event, fn)
        if not listeners[event] then listeners[event] = {} end
        table.insert(listeners[event], fn)
    end
    
    local function emit(event, ...)
        if listeners[event] then
            for _, fn in ipairs(listeners[event]) do fn(...) end
        end
    end
    
    function sched.run()
        while #tasks > 0 do
            for i = #tasks, 1, -1 do
                local task = tasks[i]
                
                -- Quota check:
                if task.resumes_used >= task.max_resumes then
                    emit("quota_exceeded", i, task.resumes_used)
                    table.remove(tasks, i)
                else
                    local ok, err = coroutine.resume(task.co)
                    task.resumes_used = task.resumes_used + 1
                    
                    if not ok then
                        emit("error", i, err)
                        table.remove(tasks, i)
                    elseif coroutine.status(task.co) == "dead" then
                        emit("complete", i, task.resumes_used)
                        table.remove(tasks, i)
                    end
                end
            end
        end
    end
    
    return sched
end

-- Test:
local sched = make_scheduler()

sched.on("quota_exceeded", function(idx, used)
    print(string.format("[QUOTA] task #%d killed after %d resumes", idx, used))
end)
sched.on("complete", function(idx, used)
    print(string.format("[OK] task #%d done in %d resumes", idx, used))
end)
sched.on("error", function(idx, err)
    print(string.format("[ERR] task #%d: %s", idx, err))
end)

-- Task który skończy w czasie:
sched.add(function()
    for i = 1, 3 do
        print("good_task: " .. i)
        coroutine.yield()
    end
end, 10)

-- Task który przekracza quota:
sched.add(function()
    local i = 0
    while true do
        i = i + 1
        print("infinite_task: " .. i)
        coroutine.yield()
    end
end, 5)

sched.run()
-- (interleaving)
-- [QUOTA] task #X killed after 5 resumes
-- [OK] task #Y done in 4 resumes
```

Quota = max_resumes. Po przekroczeniu — task usuwany, event emitowany. To uproszczenie — w praktyce quota powinna być w **instrukcjach** (przez Lua hooks z C), nie w resume-ach. Resume to grube ticki.

#### Rozwiązanie 6.4.5

```lua
-- weighted_scheduler.lua
local function make_scheduler()
    local tasks = {}    -- {co, weight, ticks_remaining}
    
    local sched = {}
    
    function sched.add(fn, weight)
        tasks[#tasks + 1] = {
            co = coroutine.create(fn),
            weight = weight or 1,
            ticks_remaining = weight or 1,
        }
    end
    
    function sched.run()
        while #tasks > 0 do
            local i = #tasks
            while i >= 1 do
                local task = tasks[i]
                
                -- Pchnij task tyle razy ile weight:
                while task.ticks_remaining > 0 do
                    local ok = coroutine.resume(task.co)
                    task.ticks_remaining = task.ticks_remaining - 1
                    if coroutine.status(task.co) == "dead" then
                        table.remove(tasks, i)
                        break
                    end
                end
                
                if coroutine.status(task.co) ~= "dead" then
                    -- Reset:
                    task.ticks_remaining = task.weight
                end
                
                i = i - 1
            end
        end
    end
    
    return sched
end

-- Test:
local sched = make_scheduler()

sched.add(function()
    for i = 1, 6 do
        print("LOW (w=1):  " .. i)
        coroutine.yield()
    end
end, 1)

sched.add(function()
    for i = 1, 8 do
        print("MED (w=2):  " .. i)
        coroutine.yield()
    end
end, 2)

sched.add(function()
    for i = 1, 12 do
        print("HIGH (w=4): " .. i)
        coroutine.yield()
    end
end, 4)

sched.run()
-- HIGH (w=4): 1
-- HIGH (w=4): 2
-- HIGH (w=4): 3
-- HIGH (w=4): 4
-- MED (w=2):  1
-- MED (w=2):  2
-- LOW (w=1):  1
-- HIGH (w=4): 5
-- HIGH (w=4): 6
-- HIGH (w=4): 7
-- HIGH (w=4): 8
-- MED (w=2):  3
-- MED (w=2):  4
-- LOW (w=1):  2
-- ...
```

Weighted round-robin: HIGH dostaje 4 ticki na rundę, MED 2, LOW 1. **Brak starvation** — każdy task dostaje przynajmniej 1 tick na rundę. Praktyczne dla "fair share" allocation.

W KarmazynOS — sesje VIP mogą mieć większy weight, ale zwykli użytkownicy też dostają ticki.

### Sprawdź się

- [ ] Umiem napisać round-robin scheduler dla wielu korutyn
- [ ] Wiem, czemu cooperative wymaga `yield` — task bez yield monopolizuje
- [ ] Umiem zrobić scheduler z `wait_for/notify` (event signaling)
- [ ] Pamiętam, że spawn to "yield + cmd"
- [ ] Wiem, jak weighted round-robin daje fair priority bez starvation
- [ ] Rozumiem różnicę resumes vs instrukcje jako quota unit

---

## Lekcja 6.5: Lazy iteratory na korutynach (vs closures z M3)

### Cel

Implementujesz pełen "lazy stream" library na korutynach. Porównujesz z closure-based approach z M3. Wybierasz właściwe narzędzie dla problemu.

### Materiał

#### Lazy stream library — porównanie

**Closure-based** (M3 Sprawdzian 7):

```lua
local function lazy_range(a, b, step)
    step = step or 1
    local current = a - step
    return function()
        current = current + step
        if current > b then return nil end
        return current
    end
end

local function lazy_map(gen, fn)
    return function()
        local v = gen()
        if v == nil then return nil end
        return fn(v)
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
```

**Korutyna-based:**

```lua
local function lazy_range(a, b, step)
    return coroutine.wrap(function()
        for i = a, b, step or 1 do
            coroutine.yield(i)
        end
    end)
end

local function lazy_map(gen, fn)
    return coroutine.wrap(function()
        for v in gen do
            coroutine.yield(fn(v))
        end
    end)
end

local function lazy_filter(gen, predicate)
    return coroutine.wrap(function()
        for v in gen do
            if predicate(v) then
                coroutine.yield(v)
            end
        end
    end)
end
```

**Korutyny krótsze, czytelne. Closures szybsze, mniej alokacji.**

#### Pełna lazy stream library

```lua
local Stream = {}
Stream.__index = Stream

local function _stream(gen)
    return setmetatable({_gen = gen}, Stream)
end

function Stream.from_table(t)
    return _stream(coroutine.wrap(function()
        for _, v in ipairs(t) do coroutine.yield(v) end
    end))
end

function Stream.from_range(a, b, step)
    return _stream(coroutine.wrap(function()
        for i = a, b, step or 1 do coroutine.yield(i) end
    end))
end

function Stream.iterate(initial, step_fn)
    return _stream(coroutine.wrap(function()
        local x = initial
        while true do
            coroutine.yield(x)
            x = step_fn(x)
        end
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

function Stream:take(n)
    local prev = self._gen
    return _stream(coroutine.wrap(function()
        for _ = 1, n do
            local v = prev()
            if v == nil then return end
            coroutine.yield(v)
        end
    end))
end

function Stream:drop(n)
    local prev = self._gen
    return _stream(coroutine.wrap(function()
        for _ = 1, n do
            if prev() == nil then return end
        end
        while true do
            local v = prev()
            if v == nil then return end
            coroutine.yield(v)
        end
    end))
end

function Stream:take_while(predicate)
    local prev = self._gen
    return _stream(coroutine.wrap(function()
        while true do
            local v = prev()
            if v == nil or not predicate(v) then return end
            coroutine.yield(v)
        end
    end))
end

-- Terminal operations (zwracają wartość, nie Stream):

function Stream:to_table()
    local result = {}
    while true do
        local v = self._gen()
        if v == nil then break end
        result[#result + 1] = v
    end
    return result
end

function Stream:reduce(fn, initial)
    local acc = initial
    while true do
        local v = self._gen()
        if v == nil then break end
        acc = fn(acc, v)
    end
    return acc
end

function Stream:count()
    local n = 0
    while self._gen() ~= nil do n = n + 1 end
    return n
end

function Stream:first()
    return self._gen()
end

function Stream:each(fn)
    while true do
        local v = self._gen()
        if v == nil then break end
        fn(v)
    end
end

-- Test:
local result = Stream.from_range(1, 1000)
    :filter(function(x) return x % 3 == 0 end)
    :map(function(x) return x * x end)
    :take(5)
    :to_table()

for _, v in ipairs(result) do io.write(v, " ") end
print()
-- 9 36 81 144 225  (3^2, 6^2, 9^2, 12^2, 15^2)

-- Nieskończone: pierwsze 10 liczb pierwszych
local function is_prime(n)
    if n < 2 then return false end
    for i = 2, math.floor(math.sqrt(n)) do
        if n % i == 0 then return false end
    end
    return true
end

local primes = Stream.iterate(2, function(x) return x + 1 end)
    :filter(is_prime)
    :take(10)
    :to_table()

for _, p in ipairs(primes) do io.write(p, " ") end
print()
-- 2 3 5 7 11 13 17 19 23 29

-- Reduce:
local sum_squares = Stream.from_range(1, 10)
    :map(function(x) return x * x end)
    :reduce(function(a, b) return a + b end, 0)
print(sum_squares)    -- 385

-- Take while:
local under_100 = Stream.iterate(1, function(x) return x * 2 end)
    :take_while(function(x) return x < 100 end)
    :to_table()
for _, v in ipairs(under_100) do io.write(v, " ") end
print()
-- 1 2 4 8 16 32 64
```

To jest **kompletny stream library** w ~100 liniach kodu. Method chaining, leniwość, nieskończone strumienie. Korzysta z OOP (metatable z M4) + korutyny.

#### Wydajność — benchmark

```lua
local function benchmark(name, fn)
    local t0 = os.clock()
    fn()
    local elapsed = os.clock() - t0
    print(string.format("%-30s: %.4fs", name, elapsed))
end

-- Closures version (M3 Sprawdzian 7):
local function lazy_range_c(a, b)
    local current = a - 1
    return function()
        current = current + 1
        if current > b then return nil end
        return current
    end
end
local function lazy_filter_c(gen, p)
    return function()
        while true do
            local v = gen()
            if v == nil then return nil end
            if p(v) then return v end
        end
    end
end
local function lazy_map_c(gen, fn)
    return function()
        local v = gen()
        if v == nil then return nil end
        return fn(v)
    end
end

benchmark("closure 1M elements", function()
    local g = lazy_map_c(
        lazy_filter_c(lazy_range_c(1, 1000000),
            function(x) return x % 2 == 0 end),
        function(x) return x * x end)
    while g() do end
end)

benchmark("coroutine 1M elements", function()
    local s = Stream.from_range(1, 1000000)
        :filter(function(x) return x % 2 == 0 end)
        :map(function(x) return x * x end)
    while s._gen() do end
end)
```

Typowy wynik (zależy od maszyny):

```
closure 1M elements           : 0.42s
coroutine 1M elements         : 1.85s
```

Korutyny ~4× wolniejsze. Cena za czytelność.

**Reguła:** dla **mln+ iteracji w hot path** — closures. Dla **kilku tysięcy** lub **na żądanie użytkownika** (interaktywne) — korutyny (czystszy kod).

#### Generic for vs explicit gen()

```lua
-- Closure i korutyna oba implementują iterator-protocol.
-- Generic for działa dla obu:

for v in lazy_range_c(1, 5) do io.write(v, " ") end
-- 1 2 3 4 5

for v in coroutine.wrap(function()
    for i = 1, 5 do coroutine.yield(i) end
end) do io.write(v, " ") end
-- 1 2 3 4 5
```

Stream library mogłoby implementować `__call` lub `:iter()` zwracające gen-funkcję żeby działało w `for`:

```lua
function Stream:iter()
    return self._gen
end

for v in Stream.from_range(1, 5):iter() do io.write(v, " ") end
-- 1 2 3 4 5

-- Albo przez __call:
setmetatable(Stream, {
    __call = function(self) return self._gen() end
})
for v in Stream.from_range(1, 5) do io.write(v, " ") end
```

Drugie subtelnie: `for v in stream do` wywołuje `stream(v)` które przez `__call` woła `_gen()`. Działa.

### Pułapki

1. **Nieskończony generator + `to_table`** = OOM. Zawsze `take(N)` przed terminal operation.
2. **Stream może być iterowany tylko raz** — po wyczerpaniu, `_gen()` zwraca nil. Klient świadomie.
3. **Korutyny + GC** — gdy stream nie iterowany do końca, korutyna pozostaje "zawieszona" do GC. Drobny pamięciowy footprint.
4. **Method chaining + side effects** — operacje są lazy! Side effects (`each`, `print`) wykonują się dopiero przy terminal.

### Zadania

**Zadanie 6.5.1**  
Dodaj do Stream metody `:zip(other_stream)` i `:enumerate()` (yield (index, value)).

**Zadanie 6.5.2**  
Napisz `Stream.unfold(initial, fn)` gdzie `fn(state)` zwraca `value, new_state` lub `nil` (koniec). Klasyczna higher-order operacja z funkcyjnych języków.

```lua
-- Fibonacci przez unfold:
local fibs = Stream.unfold({0, 1}, function(state)
    return state[1], {state[2], state[1] + state[2]}
end):take(10):to_table()
-- {0, 1, 1, 2, 3, 5, 8, 13, 21, 34}
```

**Zadanie 6.5.3**  
Dodaj `:partition(predicate)` zwracające **dwa** strumienie. Hint: jeden generator nie może być iterowany przez dwie strony — buforujesz.

**Zadanie 6.5.4**  
Napisz `Stream.zip_with(a, b, fn)` — łączy dwa streams parami przez `fn(a_val, b_val)`. Krótszy = kończy.

**Zadanie 6.5.5**  
Napisz `Stream.cycle(t)` — nieskończony strumień powtarzający elementy tabeli `t` w nieskończoność.

```lua
local repeats = Stream.cycle({1, 2, 3}):take(7):to_table()
-- {1, 2, 3, 1, 2, 3, 1}
```

---

### Rozwiązania

#### Rozwiązanie 6.5.1

```lua
-- (kontynuacja Stream library)

function Stream:zip(other)
    local a_gen = self._gen
    local b_gen = other._gen
    return _stream(coroutine.wrap(function()
        while true do
            local av = a_gen()
            local bv = b_gen()
            if av == nil or bv == nil then return end
            coroutine.yield({av, bv})    -- yield jako pair-tabela
        end
    end))
end

function Stream:enumerate()
    local prev = self._gen
    return _stream(coroutine.wrap(function()
        local i = 0
        while true do
            local v = prev()
            if v == nil then return end
            i = i + 1
            coroutine.yield({i, v})
        end
    end))
end

-- Test:
local s1 = Stream.from_range(1, 5)
local s2 = Stream.from_table({"a", "b", "c", "d", "e"})

local zipped = s1:zip(s2):to_table()
for _, p in ipairs(zipped) do
    print(p[1], p[2])
end
-- 1   a
-- 2   b
-- 3   c
-- 4   d
-- 5   e

-- Enumerate:
for _, p in ipairs(Stream.from_table({"x", "y", "z"}):enumerate():to_table()) do
    print(p[1], p[2])
end
-- 1   x
-- 2   y
-- 3   z
```

`zip` yielduje **tabele dwuelementowe** (bo `yield(av, bv)` byłoby wielowartościowe — to też legalne, ale `to_table` musiałoby specjalnie obsłużyć). Tabele jest prostsze.

Lepszy projekt API: zwracać multiple values z `:iter()`:

```lua
function Stream:iter()
    return self._gen
end

-- yield(av, bv) zamiast yield({av, bv}):
function Stream:zip(other)
    -- ...
    coroutine.yield(av, bv)
    -- ...
end

-- Use:
for a, b in Stream.from_range(1,5):zip(Stream.from_table({"a","b","c","d","e"})):iter() do
    print(a, b)
end
```

Wybór: tabele (jednorodne API) vs multiple values (bardziej idiomatyczne dla Lua). Zależy od reszty API.

#### Rozwiązanie 6.5.2

```lua
function Stream.unfold(initial, fn)
    return _stream(coroutine.wrap(function()
        local state = initial
        while true do
            local value, new_state = fn(state)
            if value == nil then return end
            coroutine.yield(value)
            state = new_state
        end
    end))
end

-- Test: Fibonacci
local fibs = Stream.unfold({0, 1}, function(state)
    return state[1], {state[2], state[1] + state[2]}
end):take(10):to_table()

for _, v in ipairs(fibs) do io.write(v, " ") end
print()
-- 0 1 1 2 3 5 8 13 21 34

-- Test: countdown
local countdown = Stream.unfold(10, function(n)
    if n < 0 then return nil end
    return n, n - 1
end):to_table()

for _, v in ipairs(countdown) do io.write(v, " ") end
print()
-- 10 9 8 7 6 5 4 3 2 1 0

-- Test: powers of 2
local powers = Stream.unfold(1, function(n)
    return n, n * 2
end):take(8):to_table()

for _, v in ipairs(powers) do io.write(v, " ") end
print()
-- 1 2 4 8 16 32 64 128
```

`unfold` to "build a list from a seed". Generalizacja `iterate` — możesz mieć złożony state (tabelę, tuple).

W matematyce / Haskell `unfoldr` to dual `foldr` — folder konsumuje, unfolder produkuje. Bardzo użyteczne dla rekurencyjnych sekwencji.

#### Rozwiązanie 6.5.3

```lua
function Stream:partition(predicate)
    -- Buforujemy bo nie da się iterować dwóch dróg z jednego gen-a
    local pos = {}
    local neg = {}
    
    while true do
        local v = self._gen()
        if v == nil then break end
        if predicate(v) then
            pos[#pos + 1] = v
        else
            neg[#neg + 1] = v
        end
    end
    
    return Stream.from_table(pos), Stream.from_table(neg)
end

-- Test:
local pos, neg = Stream.from_range(1, 10):partition(function(x) return x % 2 == 0 end)

print("evens:", table.concat(pos:to_table(), " "))
print("odds:", table.concat(neg:to_table(), " "))
-- evens: 2 4 6 8 10
-- odds:  1 3 5 7 9
```

**Important:** `partition` to **terminal-ish** operacja — konsumuje cały stream. Dla nieskończonych streams nie działa. To unikalna własność wśród naszych operacji — zwraca multiple streams ale wymaga buforowania.

Alternatywa **lazy partition** byłaby implementowana z 2 osobnymi generatorami które dzielą jeden source — wymaga lock-step koordynacji, znacznie bardziej skomplikowane. Poza scope kursu.

#### Rozwiązanie 6.5.4

```lua
function Stream.zip_with(a, b, fn)
    local a_gen = a._gen
    local b_gen = b._gen
    return _stream(coroutine.wrap(function()
        while true do
            local av = a_gen()
            local bv = b_gen()
            if av == nil or bv == nil then return end
            coroutine.yield(fn(av, bv))
        end
    end))
end

-- Test:
-- Suma par:
local sums = Stream.zip_with(
    Stream.from_range(1, 5),
    Stream.from_range(10, 14),
    function(a, b) return a + b end
):to_table()

for _, v in ipairs(sums) do io.write(v, " ") end
print()
-- 11 13 15 17 19

-- Iloczyn:
local products = Stream.zip_with(
    Stream.from_range(1, 4),
    Stream.from_table({10, 20, 30, 40, 50}),    -- dłuższy
    function(a, b) return a * b end
):to_table()

for _, v in ipairs(products) do io.write(v, " ") end
print()
-- 10 40 90 160  (krótszy [1..4] limit)

-- Łączenie stringów:
local joined = Stream.zip_with(
    Stream.from_table({"a", "b", "c"}),
    Stream.from_table({"X", "Y", "Z"}),
    function(s1, s2) return s1 .. s2 end
):to_table()

for _, v in ipairs(joined) do io.write(v, " ") end
print()
-- aX bY cZ
```

`zip_with` to `zip` + `map` w jednym kroku. Bardziej idiomatyczne dla wielu use case'ów niż osobne `zip` + `map(unpacka)`.

#### Rozwiązanie 6.5.5

```lua
function Stream.cycle(t)
    if #t == 0 then
        error("cannot cycle empty table", 2)
    end
    return _stream(coroutine.wrap(function()
        while true do
            for _, v in ipairs(t) do
                coroutine.yield(v)
            end
        end
    end))
end

-- Test:
local repeats = Stream.cycle({1, 2, 3}):take(7):to_table()
for _, v in ipairs(repeats) do io.write(v, " ") end
print()
-- 1 2 3 1 2 3 1

-- Stringi:
local greeting = Stream.cycle({"Hi", "Hello", "Cześć"}):take(8):to_table()
for _, s in ipairs(greeting) do io.write(s, " ") end
print()
-- Hi Hello Cześć Hi Hello Cześć Hi Hello

-- Połączone z innymi operacjami:
local sum = Stream.cycle({1, 2, 3, 4})
    :take(20)
    :reduce(function(a, b) return a + b end, 0)
print("sum of cycle{1,2,3,4} take 20:", sum)
-- 1+2+3+4 = 10 per cycle, 20 elements = 5 cycles = 50
-- sum of cycle{1,2,3,4} take 20: 50
```

`cycle` to nieskończony powtarzacz. Bez `take` nigdy nie kończy. To dobrze pokazuje "leniwość" — nigdy nie alokujemy nieskończonej tabeli, tylko produkujemy elementy na żądanie.

Use case: round-robin assignment, repeating patterns, test data generation.

### Sprawdź się

- [ ] Umiem zbudować pełny Stream library na korutynach (~100 linii)
- [ ] Wiem, że terminal operations konsumują stream
- [ ] Pamiętam, że stream działa tylko raz (po terminal — pusty)
- [ ] Znam `unfold` jako generalizację iterate
- [ ] Wiem, że `partition` wymaga buforowania (nie lazy)
- [ ] Rozumiem trade-off: korutyny = czytelność, closures = wydajność

---

## Sprawdzian Modułu 6

Sześć zadań — każde to integracja kilku tematów. Po nich masz fundament dla schedulera w M11.

### Zadania

**Sprawdzian 1** — State machine na korutynie  
Zaimplementuj state machine "Atom lifecycle" na korutynie:
- stany: `created`, `active`, `decaying`, `dead`
- transition rules: created → active, active → decaying (po phi < 0.5), decaying → dead (po phi < 0.01)
- API: `:tick(dt)` (zewnętrzny push), `:state()`, `:on_state_change(fn)`

```lua
local atom = Atom.new("abc", 1.0)
atom:on_state_change(function(old, new)
    print(old .. " -> " .. new)
end)

for _ = 1, 100 do
    atom:tick(0.05)
    if atom:state() == "dead" then break end
end
```

**Sprawdzian 2** — Producer/consumer z bounded buffer  
Implementuj `make_channel(capacity)` z metodami `:send(value)` i `:receive()`. Send blokuje (yield) gdy bufor pełny, receive blokuje gdy pusty. Plus scheduler na korutynach.

```lua
local ch = make_channel(3)
local sched = Scheduler.new()

sched:add(function()
    for i = 1, 5 do
        ch:send(i)
        print("sent " .. i)
    end
end)

sched:add(function()
    for _ = 1, 5 do
        local v = ch:receive()
        print("got " .. v)
    end
end)

sched:run()
```

**Sprawdzian 3** — Pełny scheduler z timeoutami  
Scheduler z metodami:
- `:add(fn)` — basic
- `:sleep(seconds)` — task-side (waits)
- `:timeout(seconds, fn)` — uruchom fn przez max N sekund, potem kill
- `:run()`

Testuj symulując czas przez fake timer.

**Sprawdzian 4** — Pipeline DSL (method chaining)  
Wzbogać Stream library z M6.5 o operacje:
- `:flat_map(fn)` — fn zwraca iterowalną kolekcję, spłaszcz
- `:distinct()` — zachowaj tylko unikalne elementy (set tracking)
- `:group_by(key_fn)` — zwraca tabelę `{key → tabela elementów}`
- `:windowed(n)` — yielduje "okna" n kolejnych elementów

**Sprawdzian 5** — Fork-join na korutynach  
Implementuj `parallel(fn_list, scheduler)` — odpala wszystkie funkcje jako tasks, czeka aż wszystkie skończą, zwraca tabelę wyników w kolejności.

```lua
local results = parallel({
    function() coroutine.yield(); return "a" end,
    function() coroutine.yield(); coroutine.yield(); return "b" end,
    function() return "c" end,
}, sched)
-- results = {"a", "b", "c"}
```

**Sprawdzian 6** — Generator algorytmów grafowych  
Reprezentacja grafu jako `{node = {neighbor1, neighbor2, ...}}`. Zaimplementuj jako korutyny:
- `bfs(graph, start)` — yielduje nodes w BFS order
- `dfs(graph, start)` — yielduje nodes w DFS order
- `paths(graph, start, target)` — yielduje wszystkie ścieżki od start do target

```lua
local g = {
    A = {"B", "C"},
    B = {"D"},
    C = {"D", "E"},
    D = {"F"},
    E = {"F"},
    F = {},
}

for node in bfs(g, "A") do io.write(node, " ") end
-- A B C D E F

for path in paths(g, "A", "F") do
    print(table.concat(path, " -> "))
end
-- A -> B -> D -> F
-- A -> C -> D -> F
-- A -> C -> E -> F
```

---

### Rozwiązania sprawdzianu

#### Sprawdzian 1

```lua
-- atom_state_machine.lua
local Atom = {}
Atom.__index = Atom

function Atom.new(sig, initial_phi)
    local self = setmetatable({
        sig = sig,
        phi = initial_phi,
        _state = "created",
        _listeners = {},
    }, Atom)
    
    -- Korutyna jako state machine:
    self._co = coroutine.wrap(function()
        -- "created" -> "active" przy pierwszym tick:
        self:_set_state("active")
        coroutine.yield()
        
        -- "active" while phi >= 0.5:
        while self.phi >= 0.5 do
            coroutine.yield()
        end
        self:_set_state("decaying")
        
        -- "decaying" while phi >= 0.01:
        while self.phi >= 0.01 do
            coroutine.yield()
        end
        self:_set_state("dead")
    end)
    
    return self
end

function Atom:_set_state(new_state)
    local old = self._state
    self._state = new_state
    for _, fn in ipairs(self._listeners) do
        fn(old, new_state)
    end
end

function Atom:state()
    return self._state
end

function Atom:on_state_change(fn)
    self._listeners[#self._listeners + 1] = fn
end

function Atom:tick(dt)
    if self._state == "dead" then return end
    self.phi = self.phi * math.exp(-dt)
    self._co()
end

-- Test:
local atom = Atom.new("abc", 1.0)

atom:on_state_change(function(old, new)
    print(string.format("transition: %s -> %s (phi=%.4f)", old, new, atom.phi))
end)

print("initial state:", atom:state(), "phi:", atom.phi)

for i = 1, 100 do
    atom:tick(0.05)
    if atom:state() == "dead" then
        print("died at iteration", i)
        break
    end
end
```

```
initial state: created phi: 1.0
transition: created -> active (phi=0.9512)
transition: active -> decaying (phi=0.4966)
transition: decaying -> dead (phi=0.0095)
died at iteration 92
```

State machine jako korutyna jest bardzo eleganckie — kolejne stany to kolejne `while` loops. Bez korutyny musiałbyś trzymać `_current_state` i robić if-else w każdym tick.

#### Sprawdzian 2

```lua
-- bounded_channel.lua
local Channel = {}
Channel.__index = Channel

function Channel.new(capacity)
    return setmetatable({
        _buffer = {},
        _capacity = capacity,
        _senders_waiting = {},
        _receivers_waiting = {},
    }, Channel)
end

function Channel:send(value)
    -- Jeśli są czekający odbiorcy — przekaż bezpośrednio:
    if #self._receivers_waiting > 0 then
        local receiver = table.remove(self._receivers_waiting, 1)
        receiver._value = value
        coroutine.yield("wake", receiver._co)
        return
    end
    
    -- Jeśli bufor pełny — czekaj:
    if #self._buffer >= self._capacity then
        local me = {co = coroutine.running(), value = value}
        self._senders_waiting[#self._senders_waiting + 1] = me
        coroutine.yield("sleep")
        -- po wakeup — wartość już w buforze:
        return
    end
    
    self._buffer[#self._buffer + 1] = value
end

function Channel:receive()
    -- Jeśli bufor ma coś:
    if #self._buffer > 0 then
        local v = table.remove(self._buffer, 1)
        -- Obudź senderów jeśli czekali:
        if #self._senders_waiting > 0 then
            local sender = table.remove(self._senders_waiting, 1)
            self._buffer[#self._buffer + 1] = sender.value
            coroutine.yield("wake", sender.co)
        end
        return v
    end
    
    -- Pusty bufor — czekaj:
    local me = {_co = coroutine.running()}
    self._receivers_waiting[#self._receivers_waiting + 1] = me
    coroutine.yield("sleep")
    return me._value
end

-- Scheduler z support dla wake/sleep:
local Scheduler = {}
Scheduler.__index = Scheduler

function Scheduler.new()
    return setmetatable({
        _ready = {},
        _sleeping = {},
    }, Scheduler)
end

function Scheduler:add(fn)
    self._ready[#self._ready + 1] = coroutine.create(fn)
end

function Scheduler:run()
    while #self._ready > 0 or next(self._sleeping) do
        if #self._ready == 0 then
            -- Wszyscy śpią — deadlock detect:
            error("deadlock: all tasks sleeping")
        end
        
        local co = table.remove(self._ready, 1)
        local ok, cmd, target = coroutine.resume(co)
        
        if not ok then
            print("[error]", cmd)
        elseif cmd == "sleep" then
            self._sleeping[co] = true
        elseif cmd == "wake" then
            -- Obudź target:
            self._sleeping[target] = nil
            self._ready[#self._ready + 1] = target
            -- I powtarzaj sender — wraca do ready:
            if coroutine.status(co) == "suspended" then
                self._ready[#self._ready + 1] = co
            end
        else
            -- Normal yield — wraca do ready:
            if coroutine.status(co) == "suspended" then
                self._ready[#self._ready + 1] = co
            end
        end
    end
end

-- Test:
local ch = Channel.new(3)
local sched = Scheduler.new()

sched:add(function()
    for i = 1, 5 do
        print("sender: trying to send " .. i)
        ch:send(i)
        print("sender: sent " .. i)
    end
end)

sched:add(function()
    for _ = 1, 5 do
        local v = ch:receive()
        print("receiver: got " .. v)
        coroutine.yield()
    end
end)

sched:run()
```

```
sender: trying to send 1
sender: sent 1
sender: trying to send 2
sender: sent 2
sender: trying to send 3
sender: sent 3
sender: trying to send 4
receiver: got 1
sender: sent 4
sender: trying to send 5
receiver: got 2
sender: sent 5
receiver: got 3
receiver: got 4
receiver: got 5
```

Bounded channel z buffering + signaling. Sender blocks gdy bufor pełny, wakes up gdy receiver pulluje. Receiver blocks gdy pusty, wakes up gdy sender pushuje. Klasyczny synchronizacja primitive.

To jest **prawdziwy "Go channel"** w Lua. W KarmazynOS pipeline multi-agent można na tym zbudować — każdy agent to task, channels to inter-agent messaging.

#### Sprawdzian 3

```lua
-- timeout_scheduler.lua
local Scheduler = {}
Scheduler.__index = Scheduler

function Scheduler.new()
    return setmetatable({
        _ready = {},
        _sleeping = {},      -- {co = wake_time}
        _timeouts = {},      -- {co = deadline}
        _now = 0,
    }, Scheduler)
end

function Scheduler:add(fn)
    self._ready[#self._ready + 1] = coroutine.create(fn)
end

function Scheduler:timeout(seconds, fn)
    local co = coroutine.create(fn)
    self._ready[#self._ready + 1] = co
    self._timeouts[co] = self._now + seconds
end

function Scheduler:sleep(seconds)
    coroutine.yield("sleep", seconds)
end

function Scheduler:advance(dt)
    self._now = self._now + dt
end

function Scheduler:run_step()
    -- Przebudź sleepers:
    for co, wake in pairs(self._sleeping) do
        if self._now >= wake then
            self._sleeping[co] = nil
            self._ready[#self._ready + 1] = co
        end
    end
    
    -- Killuj timeouts:
    for co, deadline in pairs(self._timeouts) do
        if self._now >= deadline then
            self._timeouts[co] = nil
            self._sleeping[co] = nil
            -- Usuń z ready:
            for i = #self._ready, 1, -1 do
                if self._ready[i] == co then
                    table.remove(self._ready, i)
                end
            end
            print("[timeout] task killed at " .. self._now)
        end
    end
    
    -- Wykonaj jeden krok każdego ready:
    local current_ready = {}
    for _, co in ipairs(self._ready) do current_ready[#current_ready + 1] = co end
    self._ready = {}
    
    for _, co in ipairs(current_ready) do
        local ok, cmd, arg = coroutine.resume(co)
        if cmd == "sleep" then
            self._sleeping[co] = self._now + arg
        elseif coroutine.status(co) == "suspended" then
            self._ready[#self._ready + 1] = co
        else
            -- dead — clean up:
            self._timeouts[co] = nil
        end
    end
end

function Scheduler:run(total_time, dt)
    dt = dt or 0.1
    while self._now < total_time do
        self:run_step()
        self:advance(dt)
        if #self._ready == 0 and not next(self._sleeping) and not next(self._timeouts) then
            break
        end
    end
end

-- Test:
local sched = Scheduler.new()

sched:add(function()
    print("[T1] start at " .. sched._now)
    sched:sleep(2)
    print("[T1] after sleep at " .. sched._now)
end)

sched:timeout(3, function()
    print("[T2] start at " .. sched._now)
    while true do
        sched:sleep(1)
        print("[T2] still alive at " .. sched._now)
    end
end)

sched:add(function()
    print("[T3] short task")
end)

sched:run(10, 0.5)
```

```
[T1] start at 0
[T2] start at 0
[T3] short task
[T2] still alive at 1.0
[T1] after sleep at 2.0
[T2] still alive at 2.0
[timeout] task killed at 3.0
```

Kompletny scheduler z sleep i timeout. `_now` to fake timer — w produkcji byłoby `os.time()` lub real timer z C.

#### Sprawdzian 4

```lua
-- (kontynuacja Stream library)

function Stream:flat_map(fn)
    local prev = self._gen
    return _stream(coroutine.wrap(function()
        while true do
            local v = prev()
            if v == nil then return end
            local sub = fn(v)
            -- sub może być Stream lub tabela:
            if type(sub) == "table" and getmetatable(sub) == Stream then
                while true do
                    local sv = sub._gen()
                    if sv == nil then break end
                    coroutine.yield(sv)
                end
            elseif type(sub) == "table" then
                for _, sv in ipairs(sub) do
                    coroutine.yield(sv)
                end
            end
        end
    end))
end

function Stream:distinct()
    local prev = self._gen
    return _stream(coroutine.wrap(function()
        local seen = {}
        while true do
            local v = prev()
            if v == nil then return end
            if not seen[v] then
                seen[v] = true
                coroutine.yield(v)
            end
        end
    end))
end

function Stream:group_by(key_fn)
    -- Terminal — konsumuje stream
    local groups = {}
    while true do
        local v = self._gen()
        if v == nil then break end
        local k = key_fn(v)
        if not groups[k] then groups[k] = {} end
        groups[k][#groups[k] + 1] = v
    end
    return groups
end

function Stream:windowed(n)
    local prev = self._gen
    return _stream(coroutine.wrap(function()
        local window = {}
        while true do
            local v = prev()
            if v == nil then return end
            window[#window + 1] = v
            if #window > n then table.remove(window, 1) end
            if #window == n then
                local copy = {}
                for i, w in ipairs(window) do copy[i] = w end
                coroutine.yield(copy)
            end
        end
    end))
end

-- Test:
print("--- flat_map ---")
local result = Stream.from_table({1, 2, 3})
    :flat_map(function(x) return Stream.from_range(1, x) end)
    :to_table()
for _, v in ipairs(result) do io.write(v, " ") end
print()
-- 1 1 2 1 2 3

print("--- distinct ---")
local result = Stream.from_table({1, 2, 2, 3, 1, 4, 3, 5})
    :distinct()
    :to_table()
for _, v in ipairs(result) do io.write(v, " ") end
print()
-- 1 2 3 4 5

print("--- group_by ---")
local groups = Stream.from_range(1, 10)
    :group_by(function(x) return x % 3 end)
for k, vs in pairs(groups) do
    print(k, table.concat(vs, ","))
end
-- 0   3,6,9
-- 1   1,4,7,10
-- 2   2,5,8

print("--- windowed ---")
local windows = Stream.from_range(1, 6):windowed(3):to_table()
for _, w in ipairs(windows) do
    print("[" .. table.concat(w, ", ") .. "]")
end
-- [1, 2, 3]
-- [2, 3, 4]
-- [3, 4, 5]
-- [4, 5, 6]
```

`flat_map` — popularne dla "expand every element", np. dla każdego user → wszystkie ich orders. `distinct` — set dedup. `windowed` — sliding window dla time-series analysis.

#### Sprawdzian 5

```lua
-- parallel.lua
local function parallel(fn_list, sched)
    local results = {}
    local completed = 0
    local total = #fn_list
    
    -- Wrapper: każdy task zapisuje wynik do results[i]:
    for i, fn in ipairs(fn_list) do
        sched:add(function()
            results[i] = fn()
            completed = completed + 1
        end)
    end
    
    -- Wait until all done:
    while completed < total do
        coroutine.yield()
    end
    
    return results
end

-- Helper: prosty scheduler
local function make_simple_scheduler()
    local tasks = {}
    return {
        add = function(self, fn)
            tasks[#tasks + 1] = coroutine.create(fn)
        end,
        run = function(self)
            while #tasks > 0 do
                for i = #tasks, 1, -1 do
                    coroutine.resume(tasks[i])
                    if coroutine.status(tasks[i]) == "dead" then
                        table.remove(tasks, i)
                    end
                end
            end
        end,
    }
end

-- Test:
local sched = make_simple_scheduler()

local main_results
sched:add(function()
    main_results = parallel({
        function() coroutine.yield(); return "a" end,
        function() coroutine.yield(); coroutine.yield(); return "b" end,
        function() return "c" end,
    }, sched)
end)

sched:run()

print(table.concat(main_results, ", "))
-- a, b, c
```

`parallel` to fork-join: spawn N tasks, each writes to results[i], main waits until all done. Klasyczny pattern z paralelnych systemów (OpenMP, async/await).

W single-threaded Lua — pseudo-parallel (interleaved). W Module 11 — możesz mieć true parallel przez wiele lua_State (ale to wymaga C-side koordynacji).

#### Sprawdzian 6

```lua
-- graph_algos.lua
local function bfs(graph, start)
    return coroutine.wrap(function()
        local visited = {[start] = true}
        local queue = {start}
        while #queue > 0 do
            local node = table.remove(queue, 1)
            coroutine.yield(node)
            for _, neighbor in ipairs(graph[node] or {}) do
                if not visited[neighbor] then
                    visited[neighbor] = true
                    queue[#queue + 1] = neighbor
                end
            end
        end
    end)
end

local function dfs(graph, start)
    return coroutine.wrap(function()
        local visited = {}
        local function visit(node)
            if visited[node] then return end
            visited[node] = true
            coroutine.yield(node)
            for _, neighbor in ipairs(graph[node] or {}) do
                visit(neighbor)
            end
        end
        visit(start)
    end)
end

local function paths(graph, start, target)
    return coroutine.wrap(function()
        local function find(node, current_path, visited)
            current_path[#current_path + 1] = node
            visited[node] = true
            
            if node == target then
                -- Yield kopię ścieżki:
                local copy = {}
                for i, n in ipairs(current_path) do copy[i] = n end
                coroutine.yield(copy)
            else
                for _, neighbor in ipairs(graph[node] or {}) do
                    if not visited[neighbor] then
                        find(neighbor, current_path, visited)
                    end
                end
            end
            
            -- backtrack:
            current_path[#current_path] = nil
            visited[node] = nil
        end
        find(start, {}, {})
    end)
end

-- Test:
local g = {
    A = {"B", "C"},
    B = {"D"},
    C = {"D", "E"},
    D = {"F"},
    E = {"F"},
    F = {},
}

print("--- BFS ---")
for node in bfs(g, "A") do io.write(node, " ") end
print()
-- A B C D E F

print("--- DFS ---")
for node in dfs(g, "A") do io.write(node, " ") end
print()
-- A B D F C E

print("--- All paths A → F ---")
for path in paths(g, "A", "F") do
    print(table.concat(path, " -> "))
end
-- A -> B -> D -> F
-- A -> C -> D -> F
-- A -> C -> E -> F
```

Graph algorithms jako korutyny — kanoniczny przypadek "rekurencyjny generator". DFS to kilka linii. Paths przez backtracking — `yield` w środku rekurencji, klient dostaje wszystkie rozwiązania leniwie.

Dla 1M nodes graph + paths: można zatrzymać po N pierwszych paths bez generowania reszty. Wielka zaleta lazy approach.

---

## Co dalej?

Korutyny opanowane. W kolejnym module — moduły, `require`, organizacja kodu. To zamknięcie Części I (język).

→ **Moduł 7: Moduły** — `require`, `package.path`, prywatny stan modułu, design API, hot reload.
