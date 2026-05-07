# Moduł 5: Obsługa błędów

> *"Każdy program ma błędy. Tylko te, które je spodziewają się i obsługują, są programami produkcyjnymi."*

W Lua nie ma `try`/`catch`. Jest coś prostszego i mocniejszego: **`pcall`** (protected call). Tym modułem zamykamy fundamentalną wiedzę o samym języku — kolejne (6: Korutyny, 7: Moduły) oparte są o pcall/xpcall jako fundament.

**Przewidywany czas:** 3-4 godziny pracy.

**Lekcje:**
1. `error`, `assert`, poziomy błędów
2. `pcall` i `xpcall` — protected call
3. `debug.traceback`, error objects, error handling patterns
4. Defensive programming i kontrakty

Plus **Sprawdzian Modułu 5** — 6 zadań w tym mini "circuit breaker" pattern i walidator typów dla DSL.

---

## Lekcja 5.1: `error`, `assert`, poziomy błędów

### Cel

Wiesz jak rzucić błąd, jak działają poziomy lokalizacji błędu, znasz `assert` i jego pułapki, rozumiesz różnicę między błędem string-owym a obiektem-błędem.

### Materiał

#### `error(msg)` — podstawa

```lua
local function divide(a, b)
    if b == 0 then
        error("dzielenie przez zero")
    end
    return a / b
end

print(divide(10, 2))    -- 5.0
print(divide(10, 0))    -- BŁĄD: ...divide_demo.lua:3: dzielenie przez zero
                        --        stack traceback:...
```

`error(msg)` przerywa wykonanie i propaguje "do góry" — aż znajdzie `pcall` (Lekcja 5.2) lub dotrze do top-levelu (wtedy interpreter wypisze błąd i zakończy).

Domyślnie Lua dodaje przed komunikatem **lokalizację** (`plik:linia:`). To jest zwykły string z dwukropkami.

#### Poziomy lokalizacji — `error(msg, level)`

```
level 1 = pokaż linię gdzie wywołano error()  (default)
level 2 = pokaż linię gdzie wywołano funkcję wewnątrz której był error()
level 3 = jeszcze poziom wyżej
level 0 = nie dodawaj lokalizacji wcale
```

Klasyczny use case — funkcja walidująca:

```lua
local function check_positive(x, name)
    if x < 0 then
        error(name .. " musi być dodatnie, jest " .. x, 2)
        --                                              ^ poziom 2
    end
end

local function compute(a, b)
    check_positive(a, "a")    -- linia 8
    check_positive(b, "b")    -- linia 9
    return a + b
end

compute(-1, 5)    -- linia 14
```

Co użytkownik zobaczy:
- z `error(msg, 1)`: błąd wskazuje na linię 3 (wewnątrz `check_positive`) — bezużyteczne dla użytkownika
- z `error(msg, 2)`: błąd wskazuje na linię 8 (`check_positive(a, "a")`) — lepiej
- z `error(msg, 3)`: błąd wskazuje na linię 14 (`compute(-1, 5)`) — najlepiej, wskazuje na **prawdziwe miejsce** błędu klienta

Reguła: `error(msg, 2)` w funkcji walidującej, `error(msg, 3)` w funkcji walidującej wywoływanej przez funkcję walidującą.

#### `assert(cond, msg)`

```lua
assert(x > 0, "x musi być dodatnie")
-- Równoważne:
if not (x > 0) then error("x musi być dodatnie") end
```

`assert(cond)`:
- jeśli `cond` jest truthy — zwraca `cond` (! przekazuje dalej, bardzo użyteczne)
- jeśli falsy — rzuca błąd z `msg` (lub generic "assertion failed!")

#### `assert` jako "throw on nil"

```lua
local file = assert(io.open("config.txt", "r"))
-- io.open zwraca file lub nil, errmsg
-- assert sprawdza pierwszą wartość; jeśli nil — używa drugiej jako msg
```

**To jest klasyczny idiom Lua.** Wszystko w bibliotece standardowej, co może zawieść, zwraca `nil, errmsg`. `assert` na tym wzorcu jest ZACZEPEM:
- gdy się powiodło — `assert` przekazuje wynik dalej
- gdy zawiodło — `assert` rzuca błąd z `errmsg`

```lua
-- Bez assert:
local file, err = io.open("config.txt", "r")
if not file then error(err) end
-- ... użyj file

-- Z assert (jeden line):
local file = assert(io.open("config.txt", "r"))
-- ... użyj file
```

#### Pułapka `assert` — argumenty zawsze ewaluują

```lua
assert(check_thing(), "drogie obliczenie: " .. expensive_string())
-- ! 'expensive_string()' WYWOŁA SIĘ ZAWSZE, nawet gdy check_thing zwróci true
```

`assert` to zwykła funkcja — Lua oblicza wszystkie argumenty PRZED wywołaniem. Jeśli message jest droga do skomponowania, użyj jawnego if:

```lua
if not check_thing() then
    error("drogie obliczenie: " .. expensive_string())
end
```

#### Error jako obiekt

`error()` przyjmuje DOWOLNĄ wartość, nie tylko string:

```lua
local function process()
    error({
        code = 42,
        msg = "phi out of range",
        details = {phi = 1.5, max = 1.0}
    })
end

-- Złapie pcall (Lekcja 5.2):
local ok, err = pcall(process)
print(type(err))       -- "table"
print(err.code)        -- 42
print(err.msg)         -- "phi out of range"
```

To bardzo użyteczne dla **strukturalnych błędów** — gdy wywołujący chce różnie reagować na różne typy błędów.

**Pułapka:** gdy podasz tabelę, Lua **nie dodaje** lokalizacji do wiadomości (bo nie ma do czego). Jeśli chcesz mieć stack info — dodaj sam:

```lua
error({
    code = 42,
    msg = "phi out of range",
    where = debug.getinfo(2, "Sl"),    -- info o callerze
})
```

`debug.getinfo` (Lekcja 5.3) daje strukturalne info o stack frame.

#### `error(nil)` — pułapka

```lua
error(nil)    -- ! rzuca błąd z wiadomością "nil"
```

Nie pisz `error(nil)`. Rzuca błąd, ale wiadomość jest niejasna. Zawsze daj coś sensownego.

### Pułapki

1. **`error()` bez `level`** — wskazuje na linię z `error`, nie na callera. Użyj `level=2` w funkcjach walidujących.
2. **`assert(cond, expensive_msg)`** — message ewaluuje się ZAWSZE.
3. **`assert(0)`** zwraca 0 (bo `0` to truthy w Lua!) — `assert` patrzy tylko na falsy/truthy.
4. **`error({...})`** nie ma lokalizacji — dodaj sam jeśli potrzebne.
5. **`assert(false)`** rzuca "assertion failed!" — generic, daj zawsze message.

### Zadania

**Zadanie 5.1.1**  
Napisz funkcję `validate_atom(atom)`, która sprawdza:
- `atom` musi być tabelą
- musi mieć pole `sig` (string, niepusty)
- musi mieć pole `phi` (number w [0, 1])

Każde naruszenie — `error` z opisowym komunikatem i `level=2`.

Test:
```lua
validate_atom({sig = "abc", phi = 0.7})    -- OK, nic nie zwraca
validate_atom({sig = "", phi = 0.5})        -- error: sig nie może być pusty
validate_atom("not table")                  -- error: atom musi być tabelą
```

**Zadanie 5.1.2**  
Napisz funkcję `safe_open(path, mode)` używającą `assert(io.open(...))`. Jeśli pliku nie ma — niech błąd zawiera ścieżkę.

**Zadanie 5.1.3**  
Napisz funkcję `parse_phi(s)`, która z stringa typu `"phi=0.7"` wyciąga liczbę. Jeśli format niepoprawny — rzuć błąd jako **tabelę** z polami `code` (string) i `input` (string).

```lua
parse_phi("phi=0.7")     -- 0.7
parse_phi("foo=0.7")     -- error: {code="invalid_format", input="foo=0.7"}
```

**Zadanie 5.1.4**  
Napisz funkcję `assert_type(value, expected_type, name)`, która rzuca opisowy błąd jeśli `type(value) ~= expected_type`. `name` opisuje co to za zmienna (do komunikatu). Level właściwy.

```lua
local function f(x)
    assert_type(x, "number", "x")
    return x * 2
end
f("abc")    -- error: x musi być number, dostałem string
```

**Zadanie 5.1.5**  
Napisz `chain_check(...)` — funkcję, która przyjmuje listę par `{predicate, message}` i sprawdza je po kolei. Pierwsza która zwróci falsy — error z odpowiednim message. Wszystkie OK — nic.

```lua
chain_check(
    {x ~= nil, "x nie może być nil"},
    {type(x) == "number", "x musi być number"},
    {x > 0, "x musi być dodatnie"},
    {x < 1, "x musi być mniejsze od 1"}
)
```

---

### Rozwiązania

#### Rozwiązanie 5.1.1

```lua
-- validate_atom.lua
local function validate_atom(atom)
    if type(atom) ~= "table" then
        error("atom musi być tabelą, jest " .. type(atom), 2)
    end
    if type(atom.sig) ~= "string" then
        error("atom.sig musi być stringiem, jest " .. type(atom.sig), 2)
    end
    if #atom.sig == 0 then
        error("atom.sig nie może być pusty", 2)
    end
    if type(atom.phi) ~= "number" then
        error("atom.phi musi być number, jest " .. type(atom.phi), 2)
    end
    if atom.phi < 0 or atom.phi > 1 then
        error("atom.phi musi być w [0, 1], jest " .. atom.phi, 2)
    end
end

-- Test (przez pcall, Lekcja 5.2):
local function test(case, name)
    local ok, err = pcall(validate_atom, case)
    print(name .. ":", ok, err)
end

test({sig = "abc", phi = 0.7}, "valid")
-- valid:   true   nil

test({sig = "", phi = 0.5}, "empty sig")
-- empty sig:   false   ...validate_atom.lua:8: atom.sig nie może być pusty

test("not table", "string instead of table")
-- string instead of table:   false   ...:atom musi być tabelą, jest string

test({sig = "x", phi = 1.5}, "phi too high")
-- phi too high:   false   ...:atom.phi musi być w [0, 1], jest 1.5
```

Każdy `error(..., 2)` wskaże na callera `validate_atom(...)`, czyli linię `test(...)` w teście. Bez `level=2` — wskazywałby na linię wewnątrz `validate_atom`, która z perspektywy klienta jest "wewnętrzny detail".

#### Rozwiązanie 5.1.2

```lua
-- safe_open.lua
local function safe_open(path, mode)
    mode = mode or "r"
    local f, err = io.open(path, mode)
    if not f then
        error(string.format("nie mogę otworzyć '%s' (%s): %s", path, mode, err), 2)
    end
    return f
end

-- Wersja krótsza z assert:
local function safe_open_short(path, mode)
    mode = mode or "r"
    return assert(io.open(path, mode), "nie mogę otworzyć: " .. path)
end

-- Test:
local ok, err = pcall(safe_open, "/nonexistent/file.txt")
print(ok, err)
-- false   ...:nie mogę otworzyć '/nonexistent/file.txt' (r): /nonexistent/file.txt: No such file or directory

local ok, err = pcall(safe_open_short, "/nonexistent/file.txt")
print(ok, err)
-- false   ...:nie mogę otworzyć: /nonexistent/file.txt
```

Wersja długa daje pełniejszy message (włącznie z systemowym `errno`-style). Wersja krótka traci szczegóły. Wybór zależy od czy potrzebujesz dokładnego diagnostyki.

#### Rozwiązanie 5.1.3

```lua
-- parse_phi_error.lua
local function parse_phi(s)
    if type(s) ~= "string" then
        error({code = "type_error", input = s, expected = "string"}, 2)
    end
    
    local num_str = s:match("^phi=(%-?%d+%.?%d*)$")
    if not num_str then
        error({code = "invalid_format", input = s, expected = "phi=NUMBER"}, 2)
    end
    
    local num = tonumber(num_str)
    if not num then
        error({code = "not_a_number", input = num_str}, 2)
    end
    
    return num
end

-- Test:
print(parse_phi("phi=0.7"))    -- 0.7
print(parse_phi("phi=-0.3"))   -- -0.3

-- Złe formaty:
local ok, err = pcall(parse_phi, "foo=0.7")
print(ok, type(err), err.code, err.input)
-- false   table   invalid_format   foo=0.7

local ok, err = pcall(parse_phi, "phi=abc")
print(ok, type(err), err.code, err.input)
-- false   table   invalid_format   phi=abc
-- (! nie 'not_a_number' — match już zwrócił nil bo 'abc' nie pasuje do %d)

local ok, err = pcall(parse_phi, 42)
print(ok, type(err), err.code, err.expected)
-- false   table   type_error   string
```

Strukturalne błędy pozwalają wywołującemu na **rozróżnianie typów błędów** bez parsowania stringów:

```lua
local ok, err = pcall(parse_phi, input)
if not ok then
    if err.code == "invalid_format" then
        -- pokaz user-friendly hint
    elseif err.code == "type_error" then
        -- log incident
    end
end
```

Stringy są dla ludzi, tabele są dla maszyn. Oba są legal w `error()`.

#### Rozwiązanie 5.1.4

```lua
-- assert_type.lua
local function assert_type(value, expected_type, name)
    local got = type(value)
    if got ~= expected_type then
        error(string.format(
            "%s musi być %s, dostałem %s",
            name, expected_type, got
        ), 3)   -- ! poziom 3 — caller funkcji która wywołała assert_type
    end
end

local function f(x)
    assert_type(x, "number", "x")
    return x * 2
end

print(f(5))    -- 10

local ok, err = pcall(f, "abc")
print(ok, err)
-- false   ...:f wywołane na linii X: x musi być number, dostałem string

-- Po szczegółach:
-- error(msg, 3):
--   poziom 1 = wewnątrz error -> bez sensu
--   poziom 2 = caller error() = wewnątrz assert_type -> wskaże na 'error(...)' w assert_type
--   poziom 3 = caller assert_type = wewnątrz f (linia "assert_type(x, ...)")
--   poziom 4 = caller f = miejsce gdzie f(x) zostało wywołane
```

Dyskusyjne czy `level=3` czy `level=2`. **Level=2** wskaże na linię `assert_type(x, "number", "x")` w środku `f`. **Level=3** wskaże na `f("abc")` z perspektywy użytkownika `f`.

Reguła: jeśli `assert_type` jest "własną" infrastrukturą biblioteki, użyj level=3 — żeby błąd wskazał na linię klienta. Jeśli `assert_type` jest re-eksportowane jako część API — level=2.

Tu wybrałem level=3 bo to wewnętrzny helper.

#### Rozwiązanie 5.1.5

```lua
-- chain_check.lua
local function chain_check(...)
    local checks = table.pack(...)
    for i = 1, checks.n do
        local check = checks[i]
        local cond = check[1]
        local msg = check[2]
        if not cond then
            error(msg, 3)   -- 3 = caller chain_check
        end
    end
end

-- Test:
local function process(x)
    chain_check(
        {x ~= nil, "x nie może być nil"},
        {type(x) == "number", "x musi być number"},
        {x > 0, "x musi być dodatnie"},
        {x < 100, "x musi być mniejsze od 100"}
    )
    return x * 2
end

print(process(50))    -- 100

local ok, err = pcall(process, nil)
print(err)    -- ...x nie może być nil

local ok, err = pcall(process, "abc")
print(err)    -- ...x musi być number

local ok, err = pcall(process, -5)
print(err)    -- ...x musi być dodatnie

local ok, err = pcall(process, 200)
print(err)    -- ...x musi być mniejsze od 100
```

**Pułapka:** w przykładzie `{x ~= nil, "..."}` — wartości `x ~= nil`, `type(x) == "number"`, itp. są **obliczane wcześniej**, w momencie tworzenia tabeli, przed wywołaniem `chain_check`. To znaczy że dla `x = nil`, `type(x) == "number"` to `false` — to OK, ale `x > 0` to `nil > 0` co rzuca **błąd ARYTMETYCZNY** zanim `chain_check` zacznie sprawdzać.

To jest realne ograniczenie podejścia. Lepiej:

```lua
local function process(x)
    chain_check(
        {function() return x ~= nil end, "x nie może być nil"},
        {function() return type(x) == "number" end, "x musi być number"},
        {function() return x > 0 end, "x musi być dodatnie"},
        {function() return x < 100 end, "x musi być mniejsze od 100"}
    )
    return x * 2
end

local function chain_check(...)
    local checks = table.pack(...)
    for i = 1, checks.n do
        if not checks[i][1]() then
            error(checks[i][2], 3)
        end
    end
end
```

Tu predykaty są funkcjami, ewaluowane lazy w `chain_check`. Każdy następny tylko gdy poprzedni przeszedł.

To jest klasyczny pattern w funkcyjnych językach z lazy evaluation. W Lua trzeba jawnie zawijać w `function()`.

### Sprawdź się

- [ ] Wiem, że `error(msg)` wskazuje na linię gdzie był wywołany
- [ ] Umiem użyć `level=2`/`level=3` żeby wskazać na callera
- [ ] Pamiętam pułapkę `assert(cond, expensive_msg)` — msg ewaluuje zawsze
- [ ] Rozumiem idiom `local f = assert(io.open(...))`
- [ ] Wiem, że `error()` przyjmuje dowolną wartość, nie tylko string
- [ ] Pamiętam, że `0` jest truthy — `assert(0)` przechodzi

---

## Lekcja 5.2: `pcall` i `xpcall` — protected call

### Cel

Łapiesz błędy przez `pcall`. Używasz `xpcall` dla custom error handlerów. Znasz wzorce "albo wynik, albo błąd". Wiesz kiedy NIE używać pcall.

### Materiał

#### `pcall(fn, ...)`

```lua
local function risky()
    error("coś się zepsuło")
end

local ok, err = pcall(risky)
print(ok)    -- false
print(err)   -- ...:coś się zepsuło
```

Sygnatura: `pcall(fn, ...args)`:
- jeśli `fn(args)` przeszło bez błędu — zwraca `true, ...wszystkie_wyniki_fn`
- jeśli rzuciło — zwraca `false, error_msg`

To jest **jedyny sposób** w Lua na "łapanie" błędów. Bez `pcall` — błąd propaguje aż do top-levelu i Lua kończy.

#### Multiple return z pcall

```lua
local function multi()
    return 1, 2, 3
end

local ok, a, b, c = pcall(multi)
print(ok, a, b, c)    -- true   1   2   3

local function fail_or_succeed(should_fail)
    if should_fail then error("bad") end
    return "good", 42
end

local ok, a, b = pcall(fail_or_succeed, false)
print(ok, a, b)    -- true   good   42

local ok, err = pcall(fail_or_succeed, true)
print(ok, err)     -- false   ...:bad
```

Gdy pcall ok = `true, ...wyniki`. Gdy nie ok = `false, errmsg`. Sprawdzasz pierwszy wynik i interpretujesz reszta.

#### Wzorzec idiomatyczny

```lua
local ok, result = pcall(some_function, arg1, arg2)
if ok then
    -- result to wartość zwrócona
    print("OK:", result)
else
    -- result to errmsg
    print("ERR:", result)
end
```

Albo wariant z multiple return:

```lua
local function safe_call(fn, ...)
    local results = table.pack(pcall(fn, ...))
    if results[1] then
        -- usuń pierwszy (true) i zwróć reszta:
        return table.unpack(results, 2, results.n)
    else
        -- pierwszy false, drugi to errmsg:
        return nil, results[2]
    end
end

local r, err = safe_call(function() return 42 end)
print(r, err)    -- 42   nil

local r, err = safe_call(function() error("bad") end)
print(r, err)    -- nil   ...:bad
```

To konwertuje `pcall` styl na "nil + errmsg" styl używany w bibliotekach standardowych.

#### `xpcall(fn, handler, ...)` — custom handler

`xpcall` jest jak `pcall`, ale z dodatkowym **error handlerem** wywoływanym w momencie błędu (przed odwinięciem stack'u):

```lua
local function handler(err)
    print("HANDLER CALLED with:", err)
    return "transformed: " .. tostring(err)
end

local ok, err = xpcall(function() error("oryginalny") end, handler)
-- HANDLER CALLED with: ...:oryginalny
print(ok, err)
-- false   transformed: ...:oryginalny
```

Co to daje:
1. **Handler ma dostęp do "żywego" stack'u** — może zawołać `debug.traceback`. Po zwykłym `pcall` stack jest już rozwinięty, traceback nie ma sensu.
2. **Handler może transformować błąd** — zwracana wartość trafia jako drugi wynik `xpcall`.

Klasyczny use case — pełen traceback w logu:

```lua
local function with_traceback(err)
    return debug.traceback(err, 2)
end

local function deep()
    local function deeper()
        error("z głębi")
    end
    deeper()
end

local ok, err = xpcall(deep, with_traceback)
print(err)
-- ...:z głębi
-- stack traceback:
--     ...: in function 'deeper'
--     ...: in function 'deep'
--     ...: in function <...>
```

Dla `pcall` zobaczyłbyś tylko `...:z głębi` bez stack info. `xpcall` z handlerem wołającym `debug.traceback` daje pełen kontekst.

#### Pułapka — handler nie może rzucać

```lua
local function bad_handler(err)
    error("handler się zepsuł")    -- (! to wpadnie do top-levelu jako "handler error")
end

local ok, err = xpcall(function() error("original") end, bad_handler)
-- nieprzyjemny output, w starszych Lua mogło crashować
```

Handler powinien być **prosty i nieblokujący** — odczytaj info, sformatuj string, zwróć. Nie wykonuj logiki która sama może paść.

#### `pcall` z metodami

```lua
local obj = {x = 5}
function obj:method() error("method failed") end

-- ŹLE:
local ok = pcall(obj.method)    -- BŁĄD ARYTMETYCZNY: self jest nil!

-- DOBRZE 1: jawnie podaj self:
local ok, err = pcall(obj.method, obj)
print(ok, err)    -- false   ...:method failed

-- DOBRZE 2: zawiń w lambda:
local ok, err = pcall(function() return obj:method() end)
print(ok, err)    -- false   ...:method failed
```

`pcall` nie obsługuje składni `:` (bo to nie call, to jego pierwszy argument). Musisz albo podać `obj` jawnie, albo zawinąć w lambda.

#### Kiedy NIE używać pcall

1. **Błędy programisty** (typeerror, off-by-one, undefined variable) — niech crashują głośno. `pcall` ich ukryje, długo nie zauważysz.
2. **Out of memory** — zwykle nie da się sensownie continuować.
3. **W kodzie krytycznym dla bezpieczeństwa** — `pcall` może maskować naruszenia constraint'ów.

`pcall` jest dla **przewidzianych** typów błędów: parse error, IO error, walidacja wejścia. Nie dla bugów.

#### Top-level error handling

W skrypcie głównym możesz owinąć całość w xpcall:

```lua
-- main.lua
local function main()
    -- ... cała logika
    process_data(arg)
end

local ok, err = xpcall(main, debug.traceback)
if not ok then
    io.stderr:write("FATAL: " .. err .. "\n")
    os.exit(1)
end
```

Złapiesz wszystkie nieprzewidziane błędy, wypiszesz na stderr, zakończysz z kodem 1. Standard wzorzec.

### Pułapki

1. **`pcall(obj.method)` bez `self`** — błąd arytmetyczny.
2. **Handler `xpcall` rzucający** — undefined behavior (w starszych Lua) lub wewnętrzny "double error".
3. **Łapanie WSZYSTKIEGO** — może maskować bugi. `pcall` selektywnie.
4. **`pcall` z error-table** — działa, ale message w tabeli nie ma lokalizacji (chyba że dodasz jawnie).

### Zadania

**Zadanie 5.2.1**  
Napisz funkcję `try(fn, fallback)`, która:
- woła `fn()`
- jeśli OK — zwraca wynik
- jeśli error — zwraca `fallback`

```lua
print(try(function() return 42 end, 0))           -- 42
print(try(function() error("bad") end, 0))        -- 0
```

**Zadanie 5.2.2**  
Napisz funkcję `try_until(fn, max_attempts)`, która próbuje `fn()` do `max_attempts` razy. Zwraca pierwszy udany wynik. Po wszystkich nieudanych — zwraca `nil, last_err`.

```lua
local n = 0
local result = try_until(function()
    n = n + 1
    if n < 3 then error("fail") end
    return "success"
end, 5)
print(result, n)    -- "success"   3
```

**Zadanie 5.2.3**  
Napisz `safe(fn)` — wrapper, który zwraca **funkcję** o zachowaniu "albo wynik, albo nil + errmsg". Standardowy "Lua-style" interfejs.

```lua
local divide = function(a, b)
    if b == 0 then error("dzielenie przez zero") end
    return a / b
end

local safe_divide = safe(divide)
print(safe_divide(10, 2))    -- 5.0   nil
print(safe_divide(10, 0))    -- nil   ...:dzielenie przez zero
```

**Zadanie 5.2.4**  
Napisz `with_resource(open_fn, close_fn, body)` — pattern "try-finally" / context manager:
- wywołuje `open_fn()`, dostaje resource
- woła `body(resource)`
- ZAWSZE woła `close_fn(resource)` (nawet jeśli body rzuci błąd)
- propaguje błąd dalej

```lua
local function open() print("opening"); return {id = 42} end
local function close(r) print("closing #" .. r.id) end

with_resource(open, close, function(r)
    print("body using #" .. r.id)
end)
-- opening
-- body using #42
-- closing #42

-- Nawet z błędem:
local ok, err = pcall(with_resource, open, close, function(r)
    error("bad")
end)
-- opening
-- closing #42
-- (błąd propagowany, ok=false, err="...:bad")
```

**Zadanie 5.2.5**  
Napisz `attempt(fn, types_to_catch)` — łapie tylko określone typy błędów (gdy error to tabela z polem `code` w `types_to_catch`). Inne błędy propaguje dalej.

```lua
local function risky()
    error({code = "ParseError", msg = "bad syntax"})
end

local ok, err = attempt(risky, {"ParseError", "IOError"})
print(ok, err.code)    -- false   ParseError

local function critical()
    error({code = "OOM", msg = "out of memory"})
end

-- 'OOM' nie w types_to_catch — propaguje:
local outer_ok = pcall(attempt, critical, {"ParseError"})
print(outer_ok)    -- false (błąd nie złapany)
```

---

### Rozwiązania

#### Rozwiązanie 5.2.1

```lua
-- try.lua
local function try(fn, fallback)
    local ok, result = pcall(fn)
    if ok then return result end
    return fallback
end

print(try(function() return 42 end, 0))           -- 42
print(try(function() error("bad") end, 0))        -- 0
print(try(function() return "ok" end, "default")) -- "ok"

-- Use case: dostęp do ryzykownego pola:
local data = nil
local val = try(function() return data.field.nested end, "missing")
print(val)    -- "missing"
```

Bardzo prosty pattern, ale używany ciągle. W KarmazynOS — gdy przetwarzasz user input i nie chcesz crashować na każdym corner case.

#### Rozwiązanie 5.2.2

```lua
-- try_until.lua
local function try_until(fn, max_attempts)
    local last_err
    for attempt = 1, max_attempts do
        local ok, result = pcall(fn)
        if ok then return result end
        last_err = result
    end
    return nil, last_err
end

-- Test:
local n = 0
local result = try_until(function()
    n = n + 1
    print("attempt " .. n)
    if n < 3 then error("not yet") end
    return "success"
end, 5)
print("result:", result, "after", n, "attempts")
-- attempt 1
-- attempt 2
-- attempt 3
-- result: success after 3 attempts

-- Wszystkie nieudane:
local n = 0
local result, err = try_until(function()
    n = n + 1
    error("always fails")
end, 3)
print(result, err, n)
-- nil   ...:always fails   3
```

Klasyczny retry pattern. W produkcji dodałbyś `delay` między próbami (sleep), backoff exponential, itp. Dla edukacyjnego skryptu — wystarcza.

#### Rozwiązanie 5.2.3

```lua
-- safe.lua
local function safe(fn)
    return function(...)
        local results = table.pack(pcall(fn, ...))
        if results[1] then
            -- ok=true, zwróć wszystkie wyniki bez pierwszego (czyli ok)
            return table.unpack(results, 2, results.n)
        end
        return nil, results[2]
    end
end

-- Test:
local divide = function(a, b)
    if b == 0 then error("dzielenie przez zero") end
    return a / b
end

local safe_divide = safe(divide)

print(safe_divide(10, 2))    -- 5.0
print(safe_divide(10, 0))    -- nil   ...:dzielenie przez zero

-- Działa też dla multiple return:
local divmod = function(a, b)
    if b == 0 then error("zero") end
    return a // b, a % b
end

local safe_divmod = safe(divmod)
print(safe_divmod(17, 5))    -- 3   2
print(safe_divmod(17, 0))    -- nil   ...:zero
```

`safe` konwertuje funkcję error-throwing → "nil + errmsg" styl. Bardzo użyteczne przy integracji z funkcjami które rzucają błędy a chcesz mieć Lua-idiomatyczny zwrot.

#### Rozwiązanie 5.2.4

```lua
-- with_resource.lua
local function with_resource(open_fn, close_fn, body)
    local resource = open_fn()
    local ok, err = pcall(body, resource)
    -- ZAWSZE close (sukces czy błąd):
    close_fn(resource)
    -- Propaguj błąd:
    if not ok then
        error(err, 0)    -- 0 = nie dodawaj lokalizacji (już jest w err)
    end
    -- Brak błędu — return nic (dla simplicity)
end

-- Test:
local function open()
    print("opening")
    return {id = 42}
end
local function close(r)
    print("closing #" .. r.id)
end

print("--- normal ---")
with_resource(open, close, function(r)
    print("body using #" .. r.id)
end)
-- opening
-- body using #42
-- closing #42

print()
print("--- with error ---")
local ok, err = pcall(with_resource, open, close, function(r)
    print("body started")
    error("body failed")
end)
print("ok:", ok, "err:", err)
-- opening
-- body started
-- closing #42       (! wciąż wywołane)
-- ok: false err: ...:body failed
```

`error(err, 0)` — propagujemy oryginalny błąd bez modyfikacji. Level 0 = nie dodawaj lokalizacji (bo `err` już ma swoją z oryginalnego rzutu).

W praktyce to jest pattern jak Pythonowy `with`, Ruby `block`, C# `using`. Niezawodny cleanup. W KarmazynOS przyda się do lock'ów, sesji DB, file handles.

#### Rozwiązanie 5.2.5

```lua
-- attempt.lua
local function attempt(fn, types_to_catch)
    -- Buduj set z typami:
    local catch_set = {}
    for _, t in ipairs(types_to_catch) do
        catch_set[t] = true
    end
    
    local ok, err = pcall(fn)
    if ok then return true, nil end
    
    -- Sprawdź czy złapać:
    if type(err) == "table" and catch_set[err.code] then
        return false, err
    end
    
    -- Nie nasz błąd — propaguj:
    error(err, 0)
end

-- Test:
local function risky_parse()
    error({code = "ParseError", msg = "bad syntax", line = 42})
end

print("--- caught ---")
local ok, err = attempt(risky_parse, {"ParseError", "IOError"})
print(ok, err.code, err.msg, err.line)
-- false   ParseError   bad syntax   42

print("--- not in list — propagated ---")
local function critical()
    error({code = "OOM", msg = "out of memory"})
end

local outer_ok, outer_err = pcall(attempt, critical, {"ParseError"})
print(outer_ok, outer_err.code)
-- false   OOM
-- (error propagated do outer pcall)

print("--- string error — propagated ---")
local function bad()
    error("just a string error")
end

local outer_ok, outer_err = pcall(attempt, bad, {"ParseError"})
print(outer_ok)
-- false  (string nie ma .code, więc nie pasuje do catch_set, propagowane)
```

To jest "selective catch" pattern — łapiesz tylko spodziewane błędy. Klasyczny wzorzec w językach z exceptions: `try { ... } catch (ParseError e) { ... }` — w Lua trzeba zaimplementować ręcznie, ale `attempt` daje czystą abstrakcję.

W KarmazynOS hostującym niezaufane skrypty (Moduł 10) takie selective catch jest niezbędne — łapiesz "ParseError" w skrypcie użytkownika, ale "QuotaExceeded" musi propagować do hosta.

### Sprawdź się

- [ ] Wiem, że `pcall` zwraca `true, ...wyniki` lub `false, errmsg`
- [ ] Znam `xpcall` z custom handlerem
- [ ] Pamiętam, że `pcall(obj.method)` wymaga jawnego `self`
- [ ] Umiem zaimplementować `safe(fn)` konwertujący na "nil + errmsg" styl
- [ ] Wiem, jak zrobić `with_resource` (try-finally pattern)
- [ ] Rozumiem różnicę "łapać selektywnie" vs "łapać wszystko"

---

## Lekcja 5.3: `debug.traceback`, error objects, error handling patterns

### Cel

Generujesz pełne stack tracebacks. Tworzysz custom error classes. Znasz wzorce: error chaining, error wrapping, error categories.

### Materiał

#### `debug.traceback(msg, level)`

```lua
local function inner()
    print(debug.traceback("hello", 1))
end

local function outer()
    inner()
end

outer()
-- hello
-- stack traceback:
--     ...:in function 'inner'
--     ...:in function 'outer'
--     ...:in main chunk
--     ...:in ?
```

`debug.traceback(msg, level)` zwraca string z message i pełnym stack trace. Bardzo użyteczne w `xpcall` handlerze:

```lua
local function trace_handler(err)
    return debug.traceback(tostring(err), 2)
end

local ok, err = xpcall(function()
    error("test")
end, trace_handler)

print(err)
-- ...:test
-- stack traceback:
--     [C]: in ?
--     ...:in function <...>
--     ...:in function 'xpcall'
--     ...:in main chunk
```

Bez `xpcall` z handlerem, `pcall` nie da Ci traceback (stack już rozwinięty zanim dostaniesz err).

#### `debug.getinfo`

```lua
local function inspect()
    local info = debug.getinfo(1, "Sln")
    -- 1 = bieżący frame
    -- "Sln" = source, line, name
    print(info.short_src)    -- nazwa pliku
    print(info.currentline)  -- linia
    print(info.name)         -- nazwa funkcji ("inspect")
end

inspect()
```

Pełne flagi w 2 argument:
- `S` — source (`source`, `short_src`, `linedefined`, `lastlinedefined`)
- `l` — bieżąca linia (`currentline`)
- `n` — nazwa (`name`, `namewhat`)
- `f` — sama funkcja (`func`)
- `t` — czy tail call (`istailcall`)
- `u` — info o parametrach/upvalues

Najczęściej `"Sln"` — source, line, name.

`debug.getinfo(2, "Sl")` — info o callerze (level 2). Użyteczne w `error` handlerach.

#### Custom error class

```lua
local Error = {}
Error.__index = Error

function Error.new(code, msg, details)
    return setmetatable({
        code = code,
        msg = msg,
        details = details or {},
        traceback = debug.traceback(nil, 2),
        timestamp = os.time(),
    }, Error)
end

function Error:__tostring()
    return string.format("[%s] %s", self.code, self.msg)
end

function Error:is(code)
    return self.code == code
end

function Error:to_table()
    return {
        code = self.code,
        msg = self.msg,
        details = self.details,
        timestamp = self.timestamp,
    }
end

-- Helper:
local function raise(code, msg, details)
    error(Error.new(code, msg, details), 2)
end

-- Test:
local function process(input)
    if type(input) ~= "string" then
        raise("type_error", "input musi być stringiem", {got = type(input)})
    end
    if #input == 0 then
        raise("empty_input", "input pusty")
    end
    return input:upper()
end

local ok, err = pcall(process, 42)
print(ok)                       -- false
print(getmetatable(err) == Error)  -- true
print(err)                      -- [type_error] input musi być stringiem
print(err:is("type_error"))     -- true
print(err.details.got)          -- "number"
print(err.traceback)            -- pełen stack
```

Custom Error class daje:
- strukturalne pola (`code`, `details`)
- automatyczny traceback
- czytelny `__tostring`
- metody (`:is(code)`, `:to_table()`)

To jest fundament systemu obsługi błędów dużej aplikacji.

#### Error wrapping (chained errors)

Często chcesz **opakować** błąd w wyższy poziom kontekstu:

```lua
local function load_config(path)
    local f, err = io.open(path)
    if not f then
        error(Error.new("config_load_failed",
            "nie mogę otworzyć configa: " .. path,
            {path = path, cause = err}), 2)
    end
    -- ... parsuj
end

local function init_app()
    local ok, err = pcall(load_config, "/etc/myapp.conf")
    if not ok then
        -- wrap z dodatkowym kontekstem:
        error(Error.new("init_failed",
            "init aplikacji zawiódł",
            {cause = err}), 2)
    end
end

local ok, err = pcall(init_app)
if not ok then
    print(err)              -- [init_failed] init aplikacji zawiódł
    if err.details and err.details.cause then
        print("  cause:", err.details.cause)    -- [config_load_failed] ...
        if err.details.cause.details and err.details.cause.details.cause then
            print("  root:", err.details.cause.details.cause)  -- "...: No such file..."
        end
    end
end
```

To jest "exception chaining" — każda warstwa dodaje swój kontekst. Najwyższa warstwa wie "init zawiódł", środkowa wie "konkretnie z powodu config", najniższa wie "konkretnie plik nie istnieje".

#### Error categories

```lua
local Categories = {
    USER_ERROR = "user_error",      -- zły input
    SYSTEM_ERROR = "system_error",  -- IO, sieć, OS
    LOGIC_ERROR = "logic_error",    -- bug programisty
    QUOTA_ERROR = "quota_error",    -- limity
}

local function should_retry(err)
    if type(err) ~= "table" then return false end
    return err.category == Categories.SYSTEM_ERROR
end

local function should_log_to_user(err)
    if type(err) ~= "table" then return false end
    return err.category == Categories.USER_ERROR
end
```

Kategoryzacja błędów pozwala na **scentralizowaną logikę** — "co robić z błędem typu X" decydujesz raz, używasz wszędzie.

#### Pattern: Result type

W językach jak Rust istnieje `Result<T, E>`. W Lua możesz to zaimplementować:

```lua
local Result = {}
Result.__index = Result

function Result.ok(value)
    return setmetatable({_ok = true, _value = value}, Result)
end

function Result.err(error_value)
    return setmetatable({_ok = false, _error = error_value}, Result)
end

function Result:is_ok() return self._ok end
function Result:is_err() return not self._ok end

function Result:unwrap()
    if not self._ok then
        error("unwrap on Err: " .. tostring(self._error), 2)
    end
    return self._value
end

function Result:unwrap_or(default)
    if self._ok then return self._value end
    return default
end

function Result:map(fn)
    if self._ok then
        return Result.ok(fn(self._value))
    end
    return self
end

function Result:and_then(fn)
    if self._ok then
        return fn(self._value)    -- fn musi zwrócić Result
    end
    return self
end

-- Use case:
local function parse_number(s)
    local n = tonumber(s)
    if n then return Result.ok(n) end
    return Result.err("not a number: " .. s)
end

local function double_if_positive(n)
    if n > 0 then return Result.ok(n * 2) end
    return Result.err("non-positive: " .. n)
end

-- Pipeline:
local result = parse_number("42")
    :and_then(double_if_positive)
    :map(function(x) return x + 1 end)

if result:is_ok() then
    print("Result:", result:unwrap())    -- 85
else
    print("Error:", result:unwrap_or("?"))
end

-- Z błędem:
local result = parse_number("abc")
    :and_then(double_if_positive)
print(result:is_err(), result._error)
-- true   not a number: abc
```

`Result` to alternatywa dla error-throwing — jawne ścieżki "ok" i "err" w typie zwracanym. Bezpieczniejsze (nie da się zignorować błędu), ale bardziej verbose niż `pcall`.

W KarmazynOS bym używał obu: `Result` dla **zewnętrznego API** (klient widzi czysty interface), `pcall` dla **wewnętrznych** ścieżek.

### Pułapki

1. **`debug.traceback` poza `xpcall` handlerem** — można zawołać kiedykolwiek, ale poza handlerem nie pokazuje stacka błędu (bo nie jest go).
2. **Custom Error bez `__tostring`** — `print(err)` da `table: 0x...`. Zawsze definiuj.
3. **Error wrapping z głębokim chaining** — może być nieczytelne. 2-3 warstwy max.
4. **Result + pcall mix** — wybierz jeden pattern dla danego API i trzymaj się.

### Zadania

**Zadanie 5.3.1**  
Napisz `make_error_class(code)` — fabryka klas błędów. Każda zwrócona klasa ma swoje `code`, ale zachowuje się jak Error.

```lua
local ParseError = make_error_class("parse")
local IOError = make_error_class("io")

local err = ParseError.new("bad syntax", {line = 42})
print(err)                  -- [parse] bad syntax
print(err.code)             -- "parse"
print(err.details.line)     -- 42
print(getmetatable(err) == ParseError)    -- true
```

**Zadanie 5.3.2**  
Napisz `wrap_error(err, msg)` — opakowanie istniejącego błędu w nowy z kontekstem. Zachowuje `cause` w details.

```lua
local function inner()
    error({code = "io_err", msg = "file not found"})
end

local function outer()
    local ok, err = pcall(inner)
    if not ok then
        error(wrap_error(err, "init failed"))
    end
end

local ok, err = pcall(outer)
print(err.msg)              -- "init failed"
print(err.details.cause.msg) -- "file not found"
```

**Zadanie 5.3.3**  
Napisz `format_error_chain(err)` — pretty-printer dla chained errors. Wypisuje hierarchię z wcięciami.

Test (dla error z 5.3.2):
```
[init failed]
  caused by: [io_err] file not found
```

**Zadanie 5.3.4**  
Napisz pełen `Result` z dodatkowymi metodami:
- `:or_else(fn)` — gdy err, woła `fn(err)` które zwraca nowy Result
- `:expect(msg)` — jak unwrap, ale custom msg
- `Result.try(fn)` — woła fn przez pcall, zwraca Result.ok lub Result.err

**Zadanie 5.3.5**  
Napisz `try_log(fn, logger)` — woła fn przez xpcall, każdy złapany błąd loguje (przez `logger:log("ERROR", ...)`) z pełnym tracebackiem, ale **propaguje dalej** po zalogowaniu.

```lua
local logger = {log = function(self, level, msg) print(level, msg) end}

local ok, err = pcall(function()
    try_log(function()
        error("bad")
    end, logger)
end)
-- ERROR   ...:bad   stack traceback:...
-- ok=false (przepropagowane)
```

---

### Rozwiązania

#### Rozwiązanie 5.3.1

```lua
-- error_class_factory.lua
local function make_error_class(code)
    local cls = {}
    cls.__index = cls
    cls.code = code
    
    function cls.new(msg, details)
        return setmetatable({
            code = code,
            msg = msg,
            details = details or {},
            traceback = debug.traceback(nil, 2),
            timestamp = os.time(),
        }, cls)
    end
    
    function cls:__tostring()
        return string.format("[%s] %s", self.code, self.msg)
    end
    
    function cls:is(other_code)
        return self.code == other_code
    end
    
    return cls
end

-- Test:
local ParseError = make_error_class("parse")
local IOError = make_error_class("io")
local ValidationError = make_error_class("validation")

local err1 = ParseError.new("bad syntax", {line = 42, col = 5})
local err2 = IOError.new("file not found")

print(err1)                           -- [parse] bad syntax
print(err1.code)                      -- "parse"
print(err1.details.line)              -- 42
print(getmetatable(err1) == ParseError)    -- true
print(getmetatable(err2) == IOError)       -- true
print(getmetatable(err1) == IOError)       -- false (różne klasy)

print(err1:is("parse"))               -- true
print(err1:is("io"))                  -- false

-- Polimorficznie:
local errors = {err1, err2, ValidationError.new("phi out of range")}
for _, e in ipairs(errors) do print(e) end
-- [parse] bad syntax
-- [io] file not found
-- [validation] phi out of range
```

`make_error_class` to fabryka — dla każdego `code` produkujemy oddzielną klasę. Każda dziedziczy ten sam interface, ale identity różne (bo różne metatable).

#### Rozwiązanie 5.3.2

```lua
-- wrap_error.lua
local function wrap_error(cause, msg, code)
    code = code or "wrapped"
    return {
        code = code,
        msg = msg,
        details = {cause = cause},
        timestamp = os.time(),
        traceback = debug.traceback(nil, 2),
    }
end

-- Test:
local function inner()
    error({code = "io_err", msg = "file not found", details = {path = "/etc/cfg"}})
end

local function outer()
    local ok, err = pcall(inner)
    if not ok then
        error(wrap_error(err, "init failed", "init_err"))
    end
end

local ok, err = pcall(outer)
print(err.code)                      -- "init_err"
print(err.msg)                       -- "init failed"
print(err.details.cause.code)        -- "io_err"
print(err.details.cause.msg)         -- "file not found"
print(err.details.cause.details.path)    -- "/etc/cfg"

-- 3 warstwy:
local function deepest()
    error({code = "syscall_failed", msg = "EACCES"})
end
local function deeper()
    local ok, err = pcall(deepest)
    if not ok then error(wrap_error(err, "open file", "open_failed")) end
end
local function deep()
    local ok, err = pcall(deeper)
    if not ok then error(wrap_error(err, "load config", "config_failed")) end
end

local ok, err = pcall(deep)
print(err.msg)                                          -- "load config"
print(err.details.cause.msg)                            -- "open file"
print(err.details.cause.details.cause.msg)              -- "EACCES"
```

`wrap_error` to "exception chaining" w Lua-style. Każda warstwa wie tylko o swoim poziomie, ale można zejść w dół przez `details.cause`.

#### Rozwiązanie 5.3.3

```lua
-- format_error_chain.lua
local function format_error_chain(err, depth)
    depth = depth or 0
    local indent = string.rep("  ", depth)
    local lines = {}
    
    -- Bieżący błąd:
    if type(err) == "table" then
        local code = err.code or "unknown"
        local msg = err.msg or tostring(err)
        if depth == 0 then
            lines[#lines + 1] = string.format("[%s] %s", code, msg)
        else
            lines[#lines + 1] = string.format("%scaused by: [%s] %s", indent, code, msg)
        end
        
        -- Recurse do cause:
        if err.details and err.details.cause then
            lines[#lines + 1] = format_error_chain(err.details.cause, depth + 1)
        end
    else
        -- String albo coś innego:
        if depth == 0 then
            lines[#lines + 1] = tostring(err)
        else
            lines[#lines + 1] = string.format("%scaused by: %s", indent, tostring(err))
        end
    end
    
    return table.concat(lines, "\n")
end

-- Test:
local function inner()
    error({code = "io_err", msg = "file not found"})
end

local function wrap_error(cause, msg, code)
    return {code = code or "wrapped", msg = msg, details = {cause = cause}}
end

local function outer()
    local ok, err = pcall(inner)
    if not ok then
        error(wrap_error(err, "init failed", "init_err"))
    end
end

local function top_level()
    local ok, err = pcall(outer)
    if not ok then
        error(wrap_error(err, "system startup failed", "startup_err"))
    end
end

local ok, err = pcall(top_level)
print(format_error_chain(err))
-- [startup_err] system startup failed
--   caused by: [init_err] init failed
--     caused by: [io_err] file not found
```

Rekurencyjne formatowanie. Każde `caused by:` z większym wcięciem. Top-level bez prefixu (najwyższe). Przyjazne dla logów.

#### Rozwiązanie 5.3.4

```lua
-- result_full.lua
local Result = {}
Result.__index = Result

function Result.ok(value)
    return setmetatable({_ok = true, _value = value}, Result)
end

function Result.err(error_value)
    return setmetatable({_ok = false, _error = error_value}, Result)
end

function Result.try(fn, ...)
    local results = table.pack(pcall(fn, ...))
    if results[1] then
        return Result.ok(table.unpack(results, 2, results.n))
    end
    return Result.err(results[2])
end

function Result:is_ok() return self._ok end
function Result:is_err() return not self._ok end

function Result:unwrap()
    if not self._ok then
        error("unwrap on Err: " .. tostring(self._error), 2)
    end
    return self._value
end

function Result:unwrap_or(default)
    if self._ok then return self._value end
    return default
end

function Result:expect(msg)
    if not self._ok then
        error(msg .. ": " .. tostring(self._error), 2)
    end
    return self._value
end

function Result:map(fn)
    if self._ok then
        return Result.ok(fn(self._value))
    end
    return self
end

function Result:and_then(fn)
    if self._ok then
        return fn(self._value)
    end
    return self
end

function Result:or_else(fn)
    if not self._ok then
        return fn(self._error)
    end
    return self
end

function Result:__tostring()
    if self._ok then
        return "Ok(" .. tostring(self._value) .. ")"
    end
    return "Err(" .. tostring(self._error) .. ")"
end

-- Test:
local function parse(s)
    local n = tonumber(s)
    if n then return Result.ok(n) end
    return Result.err("parse_failed: " .. s)
end

local function safe_divide(a, b)
    if b == 0 then return Result.err("div_by_zero") end
    return Result.ok(a / b)
end

-- Happy path:
local r = parse("42"):and_then(function(n) return safe_divide(n, 2) end)
print(r)                    -- Ok(21.0)
print(r:unwrap())           -- 21.0

-- Error short-circuit:
local r = parse("abc"):and_then(function(n) return safe_divide(n, 2) end)
print(r)                    -- Err(parse_failed: abc)
print(r:unwrap_or(0))       -- 0

-- Recovery z or_else:
local r = parse("abc"):or_else(function(_) return Result.ok(99) end)
print(r:unwrap())           -- 99

-- Result.try z error-throwing fn:
local r = Result.try(function() error("bad") end)
print(r)                    -- Err(...:bad)

local r = Result.try(function() return 1, 2, 3 end)
print(r)                    -- Ok(1)  (! tylko pierwszy z multiple)

-- Expect:
local r = Result.err("nope")
local ok, err = pcall(function() r:expect("operacja musiała się udać") end)
print(err)                  -- ...:operacja musiała się udać: nope
```

`Result.try` to most między error-throwing a Result-style. `or_else` daje "fallback po error". `and_then` daje composition. To jest pełna alternatywa dla `pcall`.

#### Rozwiązanie 5.3.5

```lua
-- try_log.lua
local function try_log(fn, logger)
    local function handler(err)
        local trace = debug.traceback(tostring(err), 2)
        logger:log("ERROR", trace)
        return err   -- przekazujemy dalej, xpcall zwróci nieudane
    end
    
    local results = table.pack(xpcall(fn, handler))
    if results[1] then
        return table.unpack(results, 2, results.n)
    end
    -- Po zalogowaniu — propaguj:
    error(results[2], 0)
end

-- Test:
local logger = {
    log = function(self, level, msg)
        print("[" .. level .. "] " .. msg)
    end
}

print("--- success ---")
local r = try_log(function() return "ok" end, logger)
print("returned:", r)
-- returned: ok

print()
print("--- error logged + propagated ---")
local ok, err = pcall(function()
    try_log(function()
        error("something bad")
    end, logger)
end)
print("ok:", ok, "propagated:", err)
-- [ERROR] ...:something bad
-- stack traceback:
--     ...
-- ok: false propagated: ...:something bad

print()
print("--- structured error ---")
local ok, err = pcall(function()
    try_log(function()
        error({code = "VALIDATION", msg = "phi out of range"})
    end, logger)
end)
print("propagated code:", err.code)
-- [ERROR] table: 0x...   stack traceback:...
-- propagated code: VALIDATION
```

`try_log` daje "log + rethrow" — błąd jest logowany, ale wciąż propaguje. Klasyczny pattern dla observability w aplikacji wielowarstwowej. Każda warstwa loguje swoje, najwyższa decyduje co zrobić z błędem.

W KarmazynOS dla sandboxowanych skryptów: każde wywołanie skryptu owijasz w `try_log` z dziennikiem sesji — niezależnie czy host obsłuży błąd, dziennik ma pełną historię.

### Sprawdź się

- [ ] Umiem użyć `debug.traceback` w `xpcall` handlerze
- [ ] Wiem co daje `debug.getinfo` i jakie flagi są przydatne
- [ ] Umiem napisać Custom Error class
- [ ] Znam pattern error chaining (wrap z cause)
- [ ] Wiem co to Result type i kiedy go używać zamiast pcall
- [ ] Umiem zrobić "log + rethrow" przez xpcall

---

## Lekcja 5.4: Defensive programming i kontrakty

### Cel

Stosujesz preconditions i postconditions. Walidujesz argumenty na granicy modułu. Znasz kompromis: zbyt mało defensive = bugi, zbyt dużo = noise.

### Materiał

#### Defensive programming — zasada

"Funkcja powinna sprawdzać swoje założenia na wejściu i wyjściu". W praktyce — walidujesz argumenty na granicy modułu, ufasz wewnątrz.

```lua
-- Kanoniczny kształt:
function module.public_function(arg)
    -- 1. Walidacja preconditions
    assert(type(arg) == "table", "arg musi być tabelą")
    assert(arg.sig ~= nil, "arg.sig wymagane")
    
    -- 2. Logika
    local result = _internal_logic(arg)
    
    -- 3. Walidacja postconditions (opcjonalnie)
    assert(result ~= nil, "_internal_logic zwróciło nil")
    
    return result
end

-- Wewnętrzne — bez walidacji (zaufanie):
function _internal_logic(arg)
    return process(arg.sig)
end
```

#### Type checking helpers

```lua
local check = {}

function check.is_string(v, name)
    if type(v) ~= "string" then
        error(string.format("%s musi być stringiem, jest %s", name or "value", type(v)), 3)
    end
    return v
end

function check.is_number(v, name)
    if type(v) ~= "number" then
        error(string.format("%s musi być number, jest %s", name or "value", type(v)), 3)
    end
    return v
end

function check.is_table(v, name)
    if type(v) ~= "table" then
        error(string.format("%s musi być tabelą, jest %s", name or "value", type(v)), 3)
    end
    return v
end

function check.in_range(v, lo, hi, name)
    check.is_number(v, name)
    if v < lo or v > hi then
        error(string.format("%s musi być w [%s, %s], jest %s",
            name or "value", lo, hi, v), 3)
    end
    return v
end

function check.non_empty_string(v, name)
    check.is_string(v, name)
    if #v == 0 then
        error(string.format("%s nie może być pusty", name or "value"), 3)
    end
    return v
end

-- Use case:
local function open_session(sig, phi)
    check.non_empty_string(sig, "sig")
    check.in_range(phi, 0, 1, "phi")
    
    return {sig = sig, phi = phi, atoms = {}}
end

print(open_session("abc", 0.7).sig)    -- "abc"

local ok, err = pcall(open_session, "", 0.7)
print(err)    -- ...:sig nie może być pusty

local ok, err = pcall(open_session, "abc", 1.5)
print(err)    -- ...:phi musi być w [0, 1], jest 1.5
```

Dlaczego `level=3`:
- level 1 = wewnątrz `error()` (nie pomocne)
- level 2 = wewnątrz `check.in_range` (linia z `error(...)`)
- level 3 = wewnątrz `open_session` (linia z `check.in_range(...)`)
- level 4 = caller `open_session` (kod klienta)

Level 3 wskazuje na linię w `open_session` — lepsze niż level 2 (pokazuje konkretną walidację która zawiodła).

Niektóre style preferują level=4 (kod klienta). Zależy od kontekstu — czy klient zna kod biblioteki.

#### Function contracts

Bardziej formalne — specyfikujesz pre i post-conditions jako część definicji:

```lua
local function contract(spec, fn)
    return function(...)
        -- Preconditions:
        if spec.pre then
            for i, check_fn in ipairs(spec.pre) do
                if not check_fn(...) then
                    error("precondition " .. i .. " failed", 2)
                end
            end
        end
        
        -- Wywołanie:
        local result = fn(...)
        
        -- Postconditions:
        if spec.post then
            for i, check_fn in ipairs(spec.post) do
                if not check_fn(result, ...) then
                    error("postcondition " .. i .. " failed", 2)
                end
            end
        end
        
        return result
    end
end

-- Use:
local sqrt = contract({
    pre = {
        function(x) return type(x) == "number" end,
        function(x) return x >= 0 end,
    },
    post = {
        function(result, x) return result >= 0 end,
        function(result, x) return math.abs(result * result - x) < 1e-9 end,
    }
}, math.sqrt)

print(sqrt(16))    -- 4.0

local ok, err = pcall(sqrt, -1)
print(err)         -- ...:precondition 2 failed
```

To wzbogacenie nad zwykłymi assertami — kontrakt jest deklaratywny, łatwy do audytu.

W produkcyjnym kodzie często wyłącza się postconditions (kosztowne sprawdzanie) w trybie release, zostaje preconditions.

#### Validation DSL

Bardziej Lua-friendly podejście:

```lua
local function validator(rules)
    return function(value)
        for _, rule in ipairs(rules) do
            local ok, err = rule(value)
            if not ok then
                return false, err
            end
        end
        return true
    end
end

-- Pojedyncze reguły:
local function rule_type(t) return function(v)
    if type(v) ~= t then
        return false, string.format("expected %s, got %s", t, type(v))
    end
    return true
end end

local function rule_range(lo, hi) return function(v)
    if type(v) ~= "number" then return false, "not a number" end
    if v < lo or v > hi then
        return false, string.format("out of range [%s, %s]: %s", lo, hi, v)
    end
    return true
end end

local function rule_match(pattern) return function(v)
    if type(v) ~= "string" then return false, "not a string" end
    if not v:match(pattern) then
        return false, "doesn't match: " .. pattern
    end
    return true
end end

-- Złożenie:
local validate_phi = validator({
    rule_type("number"),
    rule_range(0, 1),
})

local validate_sig = validator({
    rule_type("string"),
    rule_match("^%w+$"),
})

print(validate_phi(0.7))     -- true
print(validate_phi(1.5))     -- false   "out of range [0, 1]: 1.5"
print(validate_phi("x"))     -- false   "expected number, got string"
print(validate_sig("abc"))   -- true
print(validate_sig(""))      -- false   "doesn't match: ^%w+$"
```

Komponowalne reguły. Każda zwraca `true` lub `false, err`. Validator iteruje, pierwszy fail = zwróć ten err.

To jest **DSL dla walidacji** — schematy stają się czytelne, łatwo dodać nowe reguły, łatwo wielokrotnie używać.

#### Kompromis: kiedy walidować

**Waliduj na granicy:**
- API publiczne modułu
- Granica trust boundary (host ↔ skrypt sandboxowany)
- Wejście użytkownika (CLI, web, plik konfig)

**NIE waliduj wewnątrz:**
- Funkcje pomocnicze prywatne modułu
- Metody klasy wywołujące się nawzajem
- Hot paths gdzie wydajność krytyczna

W KarmazynOS kanoniczny przykład: API hosta dla skryptów Lua **całe** waliduje (bo skrypt może być niezaufany). Wewnętrzne funkcje hosta — minimalnie.

#### `assert` vs `error` — wybór

| Sytuacja | Wybór |
|---|---|
| Sprawdzenie założenia "to nigdy nie powinno się stać" | `assert` |
| Walidacja user input | `error` z opisem |
| Wynik IO który może być nil | `assert(io.open(...))` |
| Wykrycie błędu programisty (NULL pointer-like) | `assert` |
| Strukturalny błąd biznesowy | `error({code, msg})` |

`assert` jest dla niezmienników kodu. `error` z explicit msg jest dla obsługi business logic.

### Pułapki

1. **Over-validation** — każda funkcja waliduje wszystkie argumenty. Slowdown + noise.
2. **Under-validation** — public API ufa wszystkim. Bugi propagują głęboko, trace bezużyteczny.
3. **`assert` w pętli krytycznej** — koszt znaczący przy mln iteracji. W release builds można `assert = function() end`.
4. **Postconditions kosztowne** — sprawdzaj selektywnie.

### Zadania

**Zadanie 5.4.1**  
Napisz moduł `check` (jak w Materiale) z funkcjami `is_string`, `is_number`, `is_table`, `in_range`, `non_empty_string`. Każda zwraca wartość gdy OK (chain'owalne), rzuca błąd przy fail.

**Zadanie 5.4.2**  
Napisz `enforce_schema(value, schema)` gdzie schema to tabela jak:
```lua
{
    sig = {type = "string", non_empty = true},
    phi = {type = "number", min = 0, max = 1},
    epoch = {type = "number", optional = true, min = 0},
}
```

Dla wejścia value (tabela) — waliduje każde pole. Brakujące pole non-optional = błąd. Dodatkowe pola w value = błąd. Wszystkie błędy razem (nie pierwszy).

**Zadanie 5.4.3**  
Napisz `assert_invariant(obj, invariant_fn)` — sprawdza warunek na obiekcie, drukuje error z `__tostring(obj)` w razie naruszenia.

```lua
local stack = {data = {1, 2, 3}, size = 3}
assert_invariant(stack, function(s) return s.size == #s.data end)
-- OK

stack.size = 99
assert_invariant(stack, function(s) return s.size == #s.data end)
-- error: invariant violated: ...
```

**Zadanie 5.4.4**  
Napisz dekorator `with_contract(pre, post)` analogiczny do `contract` w Materiale, ale przyjmujący **funkcje** zwracające `true/false, errmsg` (nie samo `true/false`). Lepszy diagnostic.

**Zadanie 5.4.5**  
Napisz `validator_chain(...rules)` dające validation DSL z Materiału. Plus dwie nowe reguły: `rule_one_of(values)`, `rule_table_with(key_rules)` (rekurencyjna walidacja zagnieżdżonych tabel).

---

### Rozwiązania

#### Rozwiązanie 5.4.1

```lua
-- check.lua
local check = {}

function check.is_string(v, name)
    if type(v) ~= "string" then
        error(string.format("%s musi być stringiem, jest %s", name or "value", type(v)), 3)
    end
    return v
end

function check.is_number(v, name)
    if type(v) ~= "number" then
        error(string.format("%s musi być number, jest %s", name or "value", type(v)), 3)
    end
    return v
end

function check.is_table(v, name)
    if type(v) ~= "table" then
        error(string.format("%s musi być tabelą, jest %s", name or "value", type(v)), 3)
    end
    return v
end

function check.is_function(v, name)
    if type(v) ~= "function" then
        error(string.format("%s musi być funkcją, jest %s", name or "value", type(v)), 3)
    end
    return v
end

function check.in_range(v, lo, hi, name)
    check.is_number(v, name)
    if v < lo or v > hi then
        error(string.format("%s musi być w [%s, %s], jest %s",
            name or "value", lo, hi, v), 3)
    end
    return v
end

function check.non_empty_string(v, name)
    check.is_string(v, name)
    if #v == 0 then
        error(string.format("%s nie może być pusty", name or "value"), 3)
    end
    return v
end

function check.matches(v, pattern, name)
    check.is_string(v, name)
    if not v:match(pattern) then
        error(string.format("%s nie pasuje do '%s', jest '%s'",
            name or "value", pattern, v), 3)
    end
    return v
end

function check.has_field(t, field, name)
    check.is_table(t, name)
    if t[field] == nil then
        error(string.format("%s wymaga pola '%s'", name or "table", field), 3)
    end
    return t
end

-- Test:
local function open_session(sig, phi)
    check.non_empty_string(sig, "sig")
    check.in_range(phi, 0, 1, "phi")
    return {sig = sig, phi = phi}
end

print(open_session("abc", 0.7).sig)    -- "abc"

local ok, err = pcall(open_session, "", 0.7)
print(err)    -- ...:sig nie może być pusty

local ok, err = pcall(open_session, "abc", 1.5)
print(err)    -- ...:phi musi być w [0, 1], jest 1.5

-- Chaining (każda zwraca v):
local function process(name, age)
    local n = check.non_empty_string(name, "name"):upper()
    check.in_range(age, 0, 120, "age")
    return n .. " (" .. age .. ")"
end

print(process("anna", 30))    -- "ANNA (30)"
```

`check.*` zwraca wartość — pozwala na chain'owanie `:upper()` od razu po check'u. Klasyczny "fluent validator".

#### Rozwiązanie 5.4.2

```lua
-- enforce_schema.lua
local function enforce_schema(value, schema)
    if type(value) ~= "table" then
        return false, {"value musi być tabelą, jest " .. type(value)}
    end
    
    local errors = {}
    
    -- Sprawdź każde pole schemy:
    for field, spec in pairs(schema) do
        local v = value[field]
        
        if v == nil then
            if not spec.optional then
                errors[#errors + 1] = string.format("brak wymaganego pola: %s", field)
            end
        else
            -- Type:
            if spec.type and type(v) ~= spec.type then
                errors[#errors + 1] = string.format(
                    "pole %s: oczekiwano %s, jest %s", field, spec.type, type(v))
            else
                -- Min/max (dla number):
                if spec.min ~= nil and type(v) == "number" and v < spec.min then
                    errors[#errors + 1] = string.format(
                        "pole %s: %s < %s", field, v, spec.min)
                end
                if spec.max ~= nil and type(v) == "number" and v > spec.max then
                    errors[#errors + 1] = string.format(
                        "pole %s: %s > %s", field, v, spec.max)
                end
                
                -- non_empty (dla string):
                if spec.non_empty and type(v) == "string" and #v == 0 then
                    errors[#errors + 1] = string.format(
                        "pole %s: nie może być puste", field)
                end
                
                -- pattern (dla string):
                if spec.pattern and type(v) == "string" and not v:match(spec.pattern) then
                    errors[#errors + 1] = string.format(
                        "pole %s: nie pasuje do '%s'", field, spec.pattern)
                end
            end
        end
    end
    
    -- Sprawdź extra pola:
    for field in pairs(value) do
        if schema[field] == nil then
            errors[#errors + 1] = string.format("nieoczekiwane pole: %s", field)
        end
    end
    
    if #errors > 0 then
        return false, errors
    end
    return true
end

-- Test:
local schema = {
    sig = {type = "string", non_empty = true},
    phi = {type = "number", min = 0, max = 1},
    epoch = {type = "number", optional = true, min = 0},
}

-- OK:
local ok, errs = enforce_schema({sig = "abc", phi = 0.7}, schema)
print(ok, errs)    -- true   nil

-- OK z optional:
local ok, errs = enforce_schema({sig = "abc", phi = 0.7, epoch = 42}, schema)
print(ok, errs)    -- true   nil

-- Wiele błędów naraz:
local ok, errs = enforce_schema({sig = "", phi = 1.5, extra = "x"}, schema)
print(ok)
for _, e in ipairs(errs) do print("  -", e) end
-- false
--   - pole sig: nie może być puste
--   - pole phi: 1.5 > 1
--   - nieoczekiwane pole: extra

-- Brakujące pole:
local ok, errs = enforce_schema({sig = "abc"}, schema)
for _, e in ipairs(errs) do print("  -", e) end
--   - brak wymaganego pola: phi
```

Strategia "zbieraj wszystkie błędy" zamiast "pierwszy błąd kończy". Lepiej dla user feedback (widzisz wszystko od razu), gorzej dla wydajności (zawsze pełne sprawdzenie).

#### Rozwiązanie 5.4.3

```lua
-- assert_invariant.lua
local function assert_invariant(obj, invariant_fn, msg)
    msg = msg or "invariant violated"
    if not invariant_fn(obj) then
        error(string.format("%s on object: %s", msg, tostring(obj)), 2)
    end
end

-- Test:
local Stack = {}
Stack.__index = Stack
function Stack.__tostring(s)
    return "Stack(size=" .. s.size .. ", data_len=" .. #s.data .. ")"
end

local s = setmetatable({data = {1, 2, 3}, size = 3}, Stack)

local invariant = function(s) return s.size == #s.data end

assert_invariant(s, invariant, "stack size mismatch")
print("OK: invariant holds")

-- Naruszenie:
s.size = 99
local ok, err = pcall(assert_invariant, s, invariant, "stack size mismatch")
print(err)
-- ...:stack size mismatch on object: Stack(size=99, data_len=3)
```

`tostring(obj)` używa `__tostring` jeśli zdefiniowane, inaczej wraca `table: 0x...`. Stąd ważność `__tostring` w klasach (Lekcja 4.2/4.3).

W praktyce — invarianty wywołujesz po publicznych metodach klasy. To jest "self-test" obiektu. Wykrywa korupcję stanu w developmentcie.

#### Rozwiązanie 5.4.4

```lua
-- with_contract.lua
local function with_contract(pre, post)
    return function(fn)
        return function(...)
            -- Preconditions:
            if pre then
                for i, check_fn in ipairs(pre) do
                    local ok, err = check_fn(...)
                    if not ok then
                        error(string.format("precondition %d: %s", i, err or "failed"), 2)
                    end
                end
            end
            
            local result = fn(...)
            
            -- Postconditions:
            if post then
                for i, check_fn in ipairs(post) do
                    local ok, err = check_fn(result, ...)
                    if not ok then
                        error(string.format("postcondition %d: %s", i, err or "failed"), 2)
                    end
                end
            end
            
            return result
        end
    end
end

-- Helpers do tworzenia checków:
local function is_number(x)
    if type(x) ~= "number" then return false, "not a number: " .. type(x) end
    return true
end

local function is_non_negative(x)
    if x < 0 then return false, "negative: " .. x end
    return true
end

-- Use:
local sqrt = with_contract(
    {is_number, is_non_negative},
    {
        function(result) return result >= 0, "result negative" end,
        function(result, x)
            if math.abs(result * result - x) > 1e-9 then
                return false, "result^2 != x"
            end
            return true
        end,
    }
)(math.sqrt)

print(sqrt(16))    -- 4.0
print(sqrt(2))     -- 1.4142...

local ok, err = pcall(sqrt, -1)
print(err)
-- ...:precondition 2: negative: -1

local ok, err = pcall(sqrt, "abc")
print(err)
-- ...:precondition 1: not a number: string
```

Zmienione od `contract` w Materiale: każdy check zwraca `(bool, msg)` zamiast samego boola. Gdy fail — komunikat trafia do error message. Lepsze diagnostic.

#### Rozwiązanie 5.4.5

```lua
-- validator_chain.lua

local function validator_chain(...)
    local rules = table.pack(...)
    return function(value)
        for i = 1, rules.n do
            local ok, err = rules[i](value)
            if not ok then return false, err end
        end
        return true
    end
end

-- Reguły:
local function rule_type(t)
    return function(v)
        if type(v) ~= t then
            return false, string.format("expected %s, got %s", t, type(v))
        end
        return true
    end
end

local function rule_range(lo, hi)
    return function(v)
        if type(v) ~= "number" then return false, "not a number" end
        if v < lo or v > hi then
            return false, string.format("out of range [%s, %s]: %s", lo, hi, v)
        end
        return true
    end
end

local function rule_one_of(values)
    local set = {}
    for _, v in ipairs(values) do set[v] = true end
    return function(v)
        if not set[v] then
            return false, string.format("not in allowed values: %s (got %s)",
                table.concat(values, ", "), tostring(v))
        end
        return true
    end
end

local function rule_table_with(key_rules)
    return function(v)
        if type(v) ~= "table" then return false, "not a table" end
        for key, rule in pairs(key_rules) do
            local ok, err = rule(v[key])
            if not ok then
                return false, string.format("field '%s': %s", key, err)
            end
        end
        return true
    end
end

local function rule_match(pattern)
    return function(v)
        if type(v) ~= "string" then return false, "not a string" end
        if not v:match(pattern) then
            return false, "doesn't match: " .. pattern
        end
        return true
    end
end

local function rule_non_empty()
    return function(v)
        if type(v) == "string" and #v == 0 then return false, "empty string" end
        if type(v) == "table" and next(v) == nil then return false, "empty table" end
        return true
    end
end

-- Test:
local validate_phi = validator_chain(
    rule_type("number"),
    rule_range(0, 1)
)
print(validate_phi(0.7))      -- true
print(validate_phi(1.5))      -- false   "out of range [0, 1]: 1.5"
print(validate_phi("abc"))    -- false   "expected number, got string"

local validate_level = validator_chain(
    rule_type("string"),
    rule_one_of({"DEBUG", "INFO", "WARN", "ERROR"})
)
print(validate_level("INFO"))    -- true
print(validate_level("FAT"))     -- false   "not in allowed values: ..."

-- Zagnieżdżone:
local validate_atom = validator_chain(
    rule_table_with({
        sig = validator_chain(rule_type("string"), rule_non_empty(), rule_match("^%w+$")),
        phi = validator_chain(rule_type("number"), rule_range(0, 1)),
    })
)

print(validate_atom({sig = "abc", phi = 0.7}))    -- true
print(validate_atom({sig = "", phi = 0.5}))        -- false   "field 'sig': empty string"
print(validate_atom({sig = "abc", phi = 2}))       -- false   "field 'phi': out of range..."
print(validate_atom({sig = "abc"}))                 -- false   "field 'phi': not a number"
```

Komponowalne, rekurencyjne, czytelne. To jest **mini-DSL** dla walidacji — można rozbudowywać o nowe reguły bez zmiany infrastructure.

W KarmazynOS taki validator idealnie pasuje do walidacji konfiguracji polityk HSS — schema + rule_table_with(rule_table_with(...)) potrafi zwalidować dowolnie złożone struktury.

### Sprawdź się

- [ ] Wiem, gdzie walidować (granica trust) i gdzie nie (wewnętrzne pomocnicze)
- [ ] Umiem napisać moduł `check` z type-checkers
- [ ] Umiem zaimplementować schema validation
- [ ] Umiem napisać assert_invariant z `__tostring`
- [ ] Znam pattern function contracts (pre/post)
- [ ] Wiem co to validator chain i kiedy go używać

---

## Sprawdzian Modułu 5

Sześć zadań — moduł krótszy niż poprzednie. Po nich masz pełną wiedzę o obsłudze błędów w Lua.

### Zadania

**Sprawdzian 1** — Custom error hierarchy  
Hierarchia error class:
- `BaseError` (root)
- `UserError` (z BaseError) — błąd po stronie usera
- `SystemError` (z BaseError) — błąd systemu
- `IOError` (z SystemError)
- `ValidationError` (z UserError)

Każda klasa: `code`, `msg`, `details`, `traceback`. Funkcja `is_kind_of(err, class)` sprawdzająca czy `err` jest instancją (lub pochodną) `class`. Funkcja `format(err)` wypisująca z indent dla chain.

**Sprawdzian 2** — Retry z backoff  
Napisz `retry(fn, options)` gdzie options to `{max_attempts, backoff_ms_fn(attempt), filter}`. `filter(err)` zwraca true jeśli błąd jest "retryable". Default — wszystkie. Symulujemy backoff przez print (bez sleep).

```lua
local r = retry(some_fn, {
    max_attempts = 5,
    backoff_ms_fn = function(n) return n * 100 end,
    filter = function(err) return err.code == "transient" end,
})
```

**Sprawdzian 3** — Circuit breaker  
Klasa `CircuitBreaker.new(threshold, timeout)`:
- `:call(fn, ...)` — wywołuje fn; po `threshold` consecutive errors, "trip" — kolejne calle zwracają `nil, "circuit open"` przez `timeout` sekund. Po timeout — half-open, single attempt.
- Stany: closed (normalne), open (blocked), half-open (testowe).

**Sprawdzian 4** — Try-with-cleanup  
Napisz `try_finally(try_fn, finally_fn)`. Zarówno przy sukcesie jak i błędzie wywołuje `finally_fn`. Błąd propagowany. `finally_fn` ma swój pcall (jego błędy logowane ale nie maskują głównego).

**Sprawdzian 5** — Validator generator dla DSL  
Napisz "schema builder DSL":
```lua
local schema = Schema()
    :string("sig"):non_empty()
    :number("phi"):range(0, 1)
    :number("epoch"):optional():min(0)
    :build()

local ok, errs = schema:validate({sig = "abc", phi = 0.7})
```

`Schema()` zwraca builder. `:string(name)`, `:number(name)` zaczynają definiować pole. Modyfikatory: `:non_empty()`, `:range()`, `:min()`, `:max()`, `:pattern()`, `:optional()`. `:build()` zwraca finalny validator.

**Sprawdzian 6** — Error context decorator  
Napisz `with_error_context(context_msg, fn)` — wrapper, który łapie błędy z fn i wraps je w nowy błąd z `context_msg` jako outer message, oryginał jako cause.

```lua
local function load_plugin(name)
    return with_error_context("loading plugin " .. name, function()
        local f = assert(io.open("plugins/" .. name .. ".lua"))
        -- ...
    end)
end

local ok, err = pcall(load_plugin, "test")
-- err.msg = "loading plugin test"
-- err.details.cause = oryginalny błąd
```

---

### Rozwiązania sprawdzianu

#### Sprawdzian 1

```lua
-- error_hierarchy.lua

-- Bazowa
local BaseError = {}
BaseError.__index = BaseError

function BaseError.new(code, msg, details)
    return setmetatable({
        code = code,
        msg = msg,
        details = details or {},
        traceback = debug.traceback(nil, 3),
        timestamp = os.time(),
    }, BaseError)
end

function BaseError:__tostring()
    return string.format("[%s] %s", self.code, self.msg)
end

-- Helper do tworzenia subclass
local function subclass(parent, code_default)
    local cls = setmetatable({}, {__index = parent})
    cls.__index = cls
    cls.__tostring = parent.__tostring
    
    function cls.new(msg, details)
        local self = parent.new(code_default, msg, details)
        return setmetatable(self, cls)
    end
    
    return cls
end

local UserError = subclass(BaseError, "user_error")
local SystemError = subclass(BaseError, "system_error")
local IOError = subclass(SystemError, "io_error")
local ValidationError = subclass(UserError, "validation_error")

-- Test instance check
local function is_kind_of(err, class)
    if type(err) ~= "table" then return false end
    local mt = getmetatable(err)
    while mt do
        if mt == class then return true end
        local meta_mt = getmetatable(mt)
        if not meta_mt then return false end
        mt = meta_mt.__index
    end
    return false
end

-- Format z chain:
local function format(err, depth)
    depth = depth or 0
    local indent = string.rep("  ", depth)
    local lines = {}
    
    if type(err) == "table" and err.code then
        if depth == 0 then
            lines[#lines + 1] = tostring(err)
        else
            lines[#lines + 1] = indent .. "caused by: " .. tostring(err)
        end
        if err.details and err.details.cause then
            lines[#lines + 1] = format(err.details.cause, depth + 1)
        end
    else
        lines[#lines + 1] = indent .. tostring(err)
    end
    
    return table.concat(lines, "\n")
end

-- Test:
local ve = ValidationError.new("phi out of range", {phi = 1.5})
print(ve)                                       -- [validation_error] phi out of range
print(is_kind_of(ve, ValidationError))          -- true
print(is_kind_of(ve, UserError))                -- true (parent)
print(is_kind_of(ve, BaseError))                -- true (root)
print(is_kind_of(ve, IOError))                  -- false
print(is_kind_of(ve, SystemError))              -- false

local ie = IOError.new("file not found", {path = "/etc/cfg"})
print(is_kind_of(ie, IOError))                  -- true
print(is_kind_of(ie, SystemError))              -- true
print(is_kind_of(ie, UserError))                -- false

-- Format chain:
local outer = BaseError.new("startup_failed", "system startup failed",
    {cause = BaseError.new("config_failed", "config load failed",
        {cause = IOError.new("file not found")})})

print(format(outer))
-- [startup_failed] system startup failed
--   caused by: [config_failed] config load failed
--     caused by: [io_error] file not found
```

`subclass` to fabryka — każde wywołanie tworzy nową klasę dziedziczącą z parent. Klasy współdzielą `__tostring` ale każda ma własny `code`.

#### Sprawdzian 2

```lua
-- retry.lua
local function retry(fn, options)
    options = options or {}
    local max_attempts = options.max_attempts or 3
    local backoff_ms_fn = options.backoff_ms_fn or function(_) return 0 end
    local filter = options.filter or function(_) return true end
    
    local last_err
    for attempt = 1, max_attempts do
        local ok, result = pcall(fn)
        if ok then
            return result, attempt
        end
        last_err = result
        
        -- Czy retry-uje?
        if not filter(result) then
            return nil, last_err, attempt
        end
        
        if attempt < max_attempts then
            local delay = backoff_ms_fn(attempt)
            print(string.format("[retry] attempt %d failed, waiting %dms", attempt, delay))
            -- W produkcji: socket.sleep(delay/1000)
        end
    end
    
    return nil, last_err, max_attempts
end

-- Test 1: succeeds after 2 attempts
print("--- transient errors ---")
local n = 0
local result, err_or_attempt, attempts = retry(function()
    n = n + 1
    if n < 3 then error({code = "transient", msg = "temp error"}) end
    return "success"
end, {
    max_attempts = 5,
    backoff_ms_fn = function(a) return a * 100 end,
})
print("result:", result, "attempts:", err_or_attempt)
-- [retry] attempt 1 failed, waiting 100ms
-- [retry] attempt 2 failed, waiting 200ms
-- result: success attempts: 3

print()
print("--- non-retryable error ---")
local n = 0
local result, err = retry(function()
    n = n + 1
    error({code = "fatal", msg = "permanent"})
end, {
    max_attempts = 5,
    filter = function(err)
        return type(err) == "table" and err.code == "transient"
    end,
})
print("result:", result, "err.code:", err.code, "n:", n)
-- result: nil   err.code: fatal   n: 1
-- (! tylko 1 attempt, bo filter zwrócił false)

print()
print("--- exhausted attempts ---")
local result, err, attempts = retry(function()
    error({code = "transient", msg = "always fails"})
end, {max_attempts = 3, backoff_ms_fn = function(_) return 50 end})
print("result:", result, "attempts:", attempts)
-- [retry] attempt 1 failed, waiting 50ms
-- [retry] attempt 2 failed, waiting 50ms
-- result: nil   attempts: 3
```

`filter` daje selektywność — niektóre błędy są permanent (no retry), inne transient (retry). `backoff_ms_fn` pozwala dowolny backoff strategy: liniowy (`n * 100`), exponential (`2^n * 100`), constant (`500`).

#### Sprawdzian 3

```lua
-- circuit_breaker.lua
local CircuitBreaker = {}
CircuitBreaker.__index = CircuitBreaker

function CircuitBreaker.new(threshold, timeout)
    return setmetatable({
        threshold = threshold,
        timeout = timeout,
        state = "closed",      -- closed | open | half-open
        failures = 0,
        last_failure_time = 0,
    }, CircuitBreaker)
end

function CircuitBreaker:_now()
    return os.time()
end

function CircuitBreaker:_should_attempt()
    if self.state == "closed" then return true end
    if self.state == "open" then
        if self:_now() - self.last_failure_time >= self.timeout then
            self.state = "half-open"
            return true
        end
        return false
    end
    -- half-open
    return true
end

function CircuitBreaker:_record_success()
    self.state = "closed"
    self.failures = 0
end

function CircuitBreaker:_record_failure()
    self.failures = self.failures + 1
    self.last_failure_time = self:_now()
    if self.state == "half-open" or self.failures >= self.threshold then
        self.state = "open"
    end
end

function CircuitBreaker:call(fn, ...)
    if not self:_should_attempt() then
        return nil, "circuit open"
    end
    
    local ok, result = pcall(fn, ...)
    if ok then
        self:_record_success()
        return result
    end
    self:_record_failure()
    return nil, result
end

function CircuitBreaker:get_state()
    return self.state, self.failures
end

-- Test:
local cb = CircuitBreaker.new(3, 5)    -- threshold=3, timeout=5s

local fail_count = 0
local function flaky()
    fail_count = fail_count + 1
    error("fail #" .. fail_count)
end

print("--- 3 failures - circuit opens ---")
for i = 1, 3 do
    local r, err = cb:call(flaky)
    print(i, "result:", r, "err:", err, "state:", cb:get_state())
end
-- 1 result: nil err: ...:fail #1 state: closed
-- 2 result: nil err: ...:fail #2 state: closed
-- 3 result: nil err: ...:fail #3 state: open

print()
print("--- 4th call - circuit blocked ---")
local r, err = cb:call(flaky)
print("result:", r, "err:", err)
-- result: nil err: circuit open

print()
print("--- after timeout (simulated) — half-open ---")
cb.last_failure_time = cb.last_failure_time - 10   -- "5s minęło"
local n = 0
local r, err = cb:call(function()
    n = n + 1
    return "recovered"
end)
print("result:", r, "state:", cb:get_state())
-- result: recovered state: closed (success in half-open → reset)

print()
print("--- half-open + fail = back to open ---")
cb.failures = 3
cb.state = "open"
cb.last_failure_time = cb:_now() - 10   -- timeout minął
local r, err = cb:call(function() error("still failing") end)
print("result:", r, "err:", err, "state:", cb:get_state())
-- result: nil err: ...:still failing state: open
```

3 stany: closed (normal), open (blocked), half-open (próba recovery). Klasyczny pattern dla integracji z usługami zewnętrznymi (HTTP API, DB) — gdy usługa pada, nie zalewasz jej dalszymi żądaniami, czekasz aż "przyjdzie do siebie".

#### Sprawdzian 4

```lua
-- try_finally.lua
local function try_finally(try_fn, finally_fn)
    local results = table.pack(pcall(try_fn))
    
    -- Wywołaj finally w pcall (żeby jego błędy nie maskowały głównego):
    local finally_ok, finally_err = pcall(finally_fn)
    if not finally_ok then
        io.stderr:write("[try_finally] finally raised: " .. tostring(finally_err) .. "\n")
    end
    
    -- Zwróć/propaguj wyniki try:
    if results[1] then
        return table.unpack(results, 2, results.n)
    end
    error(results[2], 0)
end

-- Test:
print("--- success: finally called ---")
local result = try_finally(
    function()
        print("doing work")
        return "result"
    end,
    function()
        print("cleanup")
    end
)
print("got:", result)
-- doing work
-- cleanup
-- got: result

print()
print("--- error: finally still called, error propagated ---")
local ok, err = pcall(try_finally,
    function()
        print("doing work")
        error("bad")
    end,
    function()
        print("cleanup")
    end
)
print("ok:", ok, "err:", err)
-- doing work
-- cleanup
-- ok: false err: ...:bad

print()
print("--- finally raises, but original error propagates ---")
local ok, err = pcall(try_finally,
    function()
        error("main error")
    end,
    function()
        error("finally error")
    end
)
print("ok:", ok, "err:", err)
-- [try_finally] finally raised: ...:finally error  (na stderr)
-- ok: false err: ...:main error
-- (! oryginalny error wygrywa, finally tylko logged)
```

`finally_fn` w osobnym pcall — gwarantuje że jego ewentualny błąd nie zamaskuje głównego. To jest semantyka Pythona/Java/C# `try-finally`.

#### Sprawdzian 5

```lua
-- schema_dsl.lua
local Schema = {}
Schema.__index = Schema

function Schema.new()
    return setmetatable({
        fields = {},          -- {name = {type, rules, optional}}
        current_field = nil,  -- nazwa pola w trakcie definiowania
    }, Schema)
end

local function ensure_current(self)
    if self.current_field == nil then
        error("no field being defined", 3)
    end
    return self.fields[self.current_field]
end

function Schema:string(name)
    self.fields[name] = {type = "string", rules = {}, optional = false}
    self.current_field = name
    return self
end

function Schema:number(name)
    self.fields[name] = {type = "number", rules = {}, optional = false}
    self.current_field = name
    return self
end

function Schema:boolean(name)
    self.fields[name] = {type = "boolean", rules = {}, optional = false}
    self.current_field = name
    return self
end

function Schema:optional()
    ensure_current(self).optional = true
    return self
end

function Schema:non_empty()
    table.insert(ensure_current(self).rules, function(v, name)
        if type(v) == "string" and #v == 0 then
            return false, name .. " cannot be empty string"
        end
        if type(v) == "table" and next(v) == nil then
            return false, name .. " cannot be empty table"
        end
        return true
    end)
    return self
end

function Schema:range(lo, hi)
    table.insert(ensure_current(self).rules, function(v, name)
        if v < lo or v > hi then
            return false, string.format("%s must be in [%s, %s], got %s", name, lo, hi, v)
        end
        return true
    end)
    return self
end

function Schema:min(m)
    table.insert(ensure_current(self).rules, function(v, name)
        if v < m then return false, name .. " must be >= " .. m end
        return true
    end)
    return self
end

function Schema:max(m)
    table.insert(ensure_current(self).rules, function(v, name)
        if v > m then return false, name .. " must be <= " .. m end
        return true
    end)
    return self
end

function Schema:pattern(p)
    table.insert(ensure_current(self).rules, function(v, name)
        if not v:match(p) then
            return false, name .. " doesn't match pattern: " .. p
        end
        return true
    end)
    return self
end

function Schema:build()
    -- Snapshot fields:
    local fields_snapshot = {}
    for k, v in pairs(self.fields) do fields_snapshot[k] = v end
    
    return {
        validate = function(_, value)
            if type(value) ~= "table" then
                return false, {"value must be a table"}
            end
            
            local errors = {}
            
            -- Check defined fields:
            for name, spec in pairs(fields_snapshot) do
                local v = value[name]
                if v == nil then
                    if not spec.optional then
                        errors[#errors + 1] = "missing required field: " .. name
                    end
                else
                    if type(v) ~= spec.type then
                        errors[#errors + 1] = string.format(
                            "field %s: expected %s, got %s", name, spec.type, type(v))
                    else
                        for _, rule in ipairs(spec.rules) do
                            local ok, err = rule(v, name)
                            if not ok then errors[#errors + 1] = err end
                        end
                    end
                end
            end
            
            -- Check extras:
            for name in pairs(value) do
                if fields_snapshot[name] == nil then
                    errors[#errors + 1] = "unexpected field: " .. name
                end
            end
            
            if #errors > 0 then return false, errors end
            return true
        end
    }
end

-- Test:
local schema = Schema.new()
    :string("sig"):non_empty():pattern("^%w+$")
    :number("phi"):range(0, 1)
    :number("epoch"):optional():min(0)
    :boolean("alive")
    :build()

local ok, errs = schema:validate({sig = "abc", phi = 0.7, alive = true})
print(ok)    -- true

local ok, errs = schema:validate({sig = "abc", phi = 0.7, epoch = 42, alive = true})
print(ok)    -- true (optional with value)

local ok, errs = schema:validate({sig = "", phi = 1.5})
print(ok)
for _, e in ipairs(errs) do print("  -", e) end
-- false
--   - sig cannot be empty string
--   - field phi: ... must be in [0, 1], got 1.5
--   - missing required field: alive

local ok, errs = schema:validate({sig = "abc", phi = 0.7, alive = true, extra = "x"})
print(ok)
for _, e in ipairs(errs) do print("  -", e) end
-- false
--   - unexpected field: extra
```

Method chaining + state machine. `current_field` zapamiętuje "ostatnio dodane pole" — modyfikatory (`:non_empty()`, `:range()`) operują na nim. `:build()` zamyka definiowanie i daje immutable validator.

To jest ogromny krok ku **DSL** dla KarmazynOS. W Module 11 zobaczysz podobny pattern dla polityk HSS.

#### Sprawdzian 6

```lua
-- with_error_context.lua
local function with_error_context(context_msg, fn)
    local ok, result = pcall(fn)
    if ok then return result end
    
    -- Wrap błąd w nowy z context_msg:
    local wrapped = {
        code = "context",
        msg = context_msg,
        details = {cause = result},
        traceback = debug.traceback(nil, 2),
        timestamp = os.time(),
    }
    error(wrapped, 0)
end

-- Test:
local function load_plugin(name)
    return with_error_context("loading plugin " .. name, function()
        local f, err = io.open("plugins/" .. name .. ".lua")
        if not f then
            error({code = "io", msg = err})
        end
        f:close()
        return "loaded"
    end)
end

-- Sukces (jeśli plik istnieje):
-- print(load_plugin("test"))    -- "loaded"

-- Z błędem (plik nie istnieje):
local ok, err = pcall(load_plugin, "nonexistent")
print("ok:", ok)
print("msg:", err.msg)                          -- "loading plugin nonexistent"
print("cause.code:", err.details.cause.code)    -- "io"
print("cause.msg:", err.details.cause.msg)      -- "plugins/nonexistent.lua: No such file..."
-- ok: false
-- msg: loading plugin nonexistent
-- cause.code: io
-- cause.msg: plugins/nonexistent.lua: No such file or directory

-- Wieloperformowe wrapping:
local function init_app()
    return with_error_context("app initialization", function()
        return load_plugin("main")
    end)
end

local ok, err = pcall(init_app)
local function format_chain(e, depth)
    depth = depth or 0
    local indent = string.rep("  ", depth)
    if type(e) == "table" and e.msg then
        local prefix = depth == 0 and "" or "caused by: "
        local s = indent .. prefix .. e.msg
        if e.details and e.details.cause then
            s = s .. "\n" .. format_chain(e.details.cause, depth + 1)
        end
        return s
    end
    return indent .. tostring(e)
end

print()
print(format_chain(err))
-- app initialization
--   caused by: loading plugin main
--     caused by: plugins/main.lua: No such file or directory
```

`with_error_context` to "exception annotation" — dodaje warstwę kontekstu bez zmiany behaviour. Każda warstwa wie tylko o swoim "co próbowała zrobić". Bottom warstwa zna szczegóły. Format chain pokazuje całą historię.

Dla developmentu zwykle preferujesz pełen traceback. Dla production logów — czasami sam chain (bez stack), gdzie błąd "się zdarzył" jest mniej ważne niż "co próbowano zrobić".

---

## Co dalej?

Po tym module masz pełną wiedzę o tym jak Lua "myśli o błędach". W kolejnym wracamy do warstwy języka — korutyny. Sandbox HSS w Module 10 będzie korzystać masywnie z `pcall`/`xpcall` + custom Error classes opracowanych tutaj.

→ **Moduł 6: Korutyny** — symetryczne korutyny, generatory, scheduler, producent-konsument, lazy iteratory na sterydach.
