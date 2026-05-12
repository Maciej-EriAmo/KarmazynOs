# Moduł 0: Zanim zaczniesz — od zera do Lua

> *"Nie musisz wiedzieć jak działa silnik, żeby prowadzić pociąg. Ale żeby zaprojektować semafor, musisz znać sygnalizację."*

Ten moduł jest dla Ciebie jeśli **nigdy nie programowałeś** albo robiłeś to dawno i chcesz odświeżyć podstawy. Nie zakładam żadnej wiedzy — tłumaczę od zera. Po tym module będziesz gotowy na Moduł 1.

Jeśli umiesz już pisać pętle i funkcje w jakimkolwiek języku — **pomiń ten moduł**, przejdź od razu do M01.

**Przewidywany czas:** 3-4 godziny pracy.

**Lekcje:**
1. Czym jest program — i czym jest Lua
2. Instalacja i REPL — Twój pierwszy kod
3. Zmienne i typy — pudełka z etykietami
4. Podejmowanie decyzji — `if` i `while`
5. Funkcje — nazywanie kawałków kodu

Plus **Sprawdzian Modułu 0** — 6 prostych zadań z rozwiązaniami.

---

## Lekcja 0.1: Czym jest program — i czym jest Lua

### Cel

Rozumiesz czym jest program, czym jest interpreter, dlaczego uczymy się Lua.

### Materiał

#### Program to przepis

Wyobraź sobie przepis kulinarny:

```
1. Weź 3 jajka
2. Rozbij do miski
3. Dodaj szczyptę soli
4. Mieszaj 30 sekund
5. Wylej na patelnię
```

Program komputerowy działa tak samo — to lista instrukcji wykonywanych **po kolei**, od góry do dołu. Komputer robi dokładnie to co napiszesz — nic więcej, nic mniej.

#### Lua to język dla ludzi

Komputery rozumieją tylko jedynki i zera. Języki programowania to **tłumacze** — piszesz po angielsku (mniej więcej), tłumacz zamienia na jedynki i zera.

```lua
print("Witaj, świecie!")
```

To jest kompletny program w Lua. Jedna linia. Robi jedną rzecz: wypisuje tekst na ekran.

#### Dlaczego Lua?

- **Prosta** — mniej reguł niż inne języki. Łatwiej zacząć.
- **Lekka** — cały interpreter to plik ~300KB. Działa wszędzie — na telefonie, na komputerze, na serwerze.
- **Embeddowalna** — można ją wbudować w inne programy. W KarmazynOS Lua to "język którym mówisz do systemu".

#### Interpreter

Lua to język **interpretowany**. To znaczy: nie musisz "kompilować" (długo przekształcać) programu przed uruchomieniem. Piszesz kod → uruchamiasz → widzisz wynik. Natychmiastowa informacja zwrotna.

**Interpreter** to program który czyta Twój kod linia po linii i wykonuje go. Jak tłumacz na żywo — czyta zdanie, tłumaczy, mówi.

### Sprawdź się

- [ ] Program to lista instrukcji wykonywanych po kolei
- [ ] Lua to język programowania — przetłumacza między Tobą a komputerem
- [ ] Interpreter czyta i wykonuje kod na bieżąco (bez kompilacji)

---

## Lekcja 0.2: Instalacja i REPL — Twój pierwszy kod

### Cel

Instalujesz Lua, uruchamiasz REPL, piszesz i uruchamiasz pierwszy program.

### Materiał

#### Instalacja

**Linux (Ubuntu/Debian):**
```bash
sudo apt install lua5.4
```

**Linux (Arch):**
```bash
sudo pacman -S lua
```

**Android (Termux):**
```bash
pkg install lua54
```

**Windows:** pobierz z luabinaries.sourceforge.net, rozpakuj, dodaj do PATH.

**Sprawdzenie:**
```bash
lua5.4 -v
# Lua 5.4.7  Copyright (C) 1994-2024 Lua.org, PUC-Rio
```

Jeśli widzisz wersję — Lua działa. Jeśli "command not found" — spróbuj `lua` zamiast `lua5.4`.

#### REPL — rozmowa z Lua

Wpisz `lua5.4` (lub `lua`) w terminalu:

```
$ lua5.4
Lua 5.4.7  Copyright (C) 1994-2024 Lua.org, PUC-Rio
>
```

To jest **REPL** (Read-Eval-Print Loop) — Lua czeka na Twój kod. Wpisz cokolwiek, naciśnij Enter, Lua odpowie.

```
> print("Witaj, świecie!")
Witaj, świecie!

> 2 + 2
4

> 10 * 3
30
```

Wyjście z REPL-a: wpisz `os.exit()` albo naciśnij Ctrl+D.

#### Pierwszy plik

Otwórz dowolny edytor tekstu (nano, vim, notepad, VS Code). Stwórz plik `hello.lua`:

```lua
-- To jest komentarz. Lua go ignoruje.
-- Komentarze zaczynają się od dwóch myślników: --

print("Witaj, świecie!")
print("To jest mój pierwszy program w Lua.")
print("2 + 2 =", 2 + 2)
```

Uruchom:
```bash
lua5.4 hello.lua
```

Output:
```
Witaj, świecie!
To jest mój pierwszy program w Lua.
2 + 2 = 4
```

**Brawo — właśnie uruchomiłeś swój pierwszy program!**

#### Komentarze

```lua
-- To jest komentarz jednoliniowy. Lua go ignoruje.

--[[
    To jest komentarz
    wieloliniowy.
    Może mieć
    wiele linii.
]]
```

Komentarze są dla Ciebie i dla ludzi czytających Twój kod. Komputer je pomija. Pisz je — przyszłe "Ty" podziękuje.

### Pułapki

1. **Wielkość liter ma znaczenie** — `print` działa, `Print` nie. `PRINT` nie.
2. **Cudzysłowy** — `"tekst"` albo `'tekst'` — oba OK. Ale nie mieszaj: `"tekst'` nie działa.
3. **Pliku nie trzeba "kompilować"** — od razu `lua5.4 plik.lua`.

### Zadania

**Zadanie 0.2.1**  
W REPL-u oblicz:
- 100 + 200
- 15 * 7
- 144 / 12
- 2 ^ 10 (potęga)

**Zadanie 0.2.2**  
Stwórz plik `obliczenia.lua` który wypisze:
```
5 + 3 = 8
10 - 4 = 6
7 * 8 = 56
```

**Zadanie 0.2.3**  
Stwórz plik `wizytowka.lua` który wypisze Twoje imię, miasto i ulubiony kolor — każde w osobnej linii.

---

### Rozwiązania

#### Rozwiązanie 0.2.1

```
> 100 + 200
300
> 15 * 7
105
> 144 / 12
12.0
> 2 ^ 10
1024.0
```

Zauważ: dzielenie (`/`) i potęga (`^`) dają liczbę z kropką (`12.0`, `1024.0`). To "liczba zmiennoprzecinkowa" (float). Nie przejmuj się na razie — w M01 wyjaśniamy różnicę.

#### Rozwiązanie 0.2.2

```lua
-- obliczenia.lua
print("5 + 3 =", 5 + 3)
print("10 - 4 =", 10 - 4)
print("7 * 8 =", 7 * 8)
```

#### Rozwiązanie 0.2.3

```lua
-- wizytowka.lua
print("Imię: Anna")
print("Miasto: Warszawa")
print("Ulubiony kolor: niebieski")
```

### Sprawdź się

- [ ] Umiem uruchomić `lua5.4` w terminalu
- [ ] Umiem wpisać wyrażenie w REPL i zobaczyć wynik
- [ ] Umiem stworzyć plik `.lua` i uruchomić go
- [ ] Wiem, że `--` to komentarz

---

## Lekcja 0.3: Zmienne i typy — pudełka z etykietami

### Cel

Rozumiesz zmienne, przypisujesz wartości, znasz podstawowe typy (number, string, boolean, nil).

### Materiał

#### Zmienne — pudełka z etykietami

Zmienna to **nazwane pudełko** w którym trzymasz wartość. Dajesz pudełku nazwę, wkładasz coś:

```lua
imie = "Anna"
wiek = 30
wzrost = 1.75
```

Teraz `imie` to pudełko z napisem "Anna", `wiek` to pudełko z liczbą 30.

```lua
print(imie)      -- Anna
print(wiek)      -- 30
print(wzrost)    -- 1.75
```

Możesz zmienić zawartość pudełka:

```lua
wiek = 30
print(wiek)    -- 30

wiek = 31      -- urodziny!
print(wiek)    -- 31
```

Stara wartość (30) znika. Nowa (31) zajmuje jej miejsce.

#### `local` — dobre praktyki

W Lua zmienne powinny zaczynać się od słowa `local`:

```lua
local imie = "Anna"
local wiek = 30
```

`local` znaczy "ta zmienna istnieje tylko tutaj". Na razie różnica nie jest widoczna, ale w dłuższych programach jest kluczowa. **Zawsze pisz `local`** — to dobry nawyk.

#### Typy — co może być w pudełku

Lua ma kilka **typów** wartości:

**Number** (liczba):
```lua
local x = 42        -- integer (całkowita)
local y = 3.14      -- float (zmiennoprzecinkowa)
local z = -7        -- ujemna
```

**String** (tekst):
```lua
local imie = "Anna"
local miasto = 'Warszawa'   -- cudzysłów pojedynczy też OK
local dluzszy = "Witaj, świecie!"
```

**Boolean** (prawda/fałsz):
```lua
local jest_cieplo = true
local pada_deszcz = false
```

Tylko dwie wartości: `true` (prawda) i `false` (fałsz). Użyteczne do decyzji — "czy coś jest?" → tak lub nie.

**Nil** (nic):
```lua
local nic = nil    -- "brak wartości"
print(nic)         -- nil
```

`nil` to specjalna wartość znacząca "nic tu nie ma". Jeśli odczytasz zmienną której nie stworzyłeś — dostaniesz `nil`.

```lua
print(nieistniejaca_zmienna)    -- nil
```

#### Sprawdzanie typu

```lua
print(type(42))          -- number
print(type("Anna"))      -- string
print(type(true))        -- boolean
print(type(nil))         -- nil
```

`type(x)` mówi Ci co jest w pudełku. Przydatne gdy nie pamiętasz.

#### Łączenie stringów (konkatenacja)

Dwa stringi łączysz operatorem `..` (dwie kropki):

```lua
local imie = "Anna"
local nazwisko = "Kowalska"
local pelne = imie .. " " .. nazwisko
print(pelne)    -- Anna Kowalska
```

`..` to "sklej razem". `imie .. " " .. nazwisko` → `"Anna" .. " " .. "Kowalska"` → `"Anna Kowalska"`.

#### Konwersja

```lua
local x = "42"           -- to jest STRING, nie number
local y = tonumber(x)    -- teraz y to NUMBER 42
print(y + 1)             -- 43

local z = 100
local s = tostring(z)    -- teraz s to STRING "100"
print("wynik: " .. s)    -- wynik: 100
```

`tonumber(x)` — zamień string na liczbę. `tostring(x)` — zamień cokolwiek na string.

### Pułapki

1. **Lua rozróżnia wielkie i małe litery** — `Imie`, `imie`, `IMIE` to trzy różne zmienne.
2. **Nazwy zmiennych** nie mogą zaczynać się od cyfry: `1zmienna` → błąd. `zmienna1` → OK.
3. **`..` to konkatenacja** (łączenie stringów), nie dodawanie. `"2" .. "3"` to `"23"`, nie `5`.
4. **`nil` nie jest zerem** — `nil` to "brak", `0` to liczba zero. Różne rzeczy.

### Zadania

**Zadanie 0.3.1**  
Stwórz zmienne `imie`, `wiek`, `miasto` ze swoimi danymi. Wypisz je w jednej linii: `"Jestem Anna, mam 30 lat, mieszkam w Warszawie"` (z konkatenacją `..`).

**Zadanie 0.3.2**  
Stwórz dwie zmienne liczbowe `a = 15` i `b = 4`. Wypisz:
- sumę
- różnicę
- iloczyn
- iloraz
- resztę z dzielenia (operator `%`)

**Zadanie 0.3.3**  
Sprawdź typy: `type(42)`, `type("hello")`, `type(true)`, `type(nil)`, `type(print)`.

**Zadanie 0.3.4**  
Zamień string `"3.14"` na liczbę, dodaj 1, wypisz wynik.

**Zadanie 0.3.5**  
Co wypisze ten kod? Odpowiedz ZANIM uruchomisz:
```lua
local x = 10
local y = x
x = 20
print(x, y)
```

---

### Rozwiązania

#### Rozwiązanie 0.3.1

```lua
local imie = "Anna"
local wiek = 30
local miasto = "Warszawa"

print("Jestem " .. imie .. ", mam " .. tostring(wiek) .. " lat, mieszkam w " .. miasto)
-- Jestem Anna, mam 30 lat, mieszkam w Warszawie
```

`tostring(wiek)` — bo `wiek` to number, a `..` oczekuje stringów. W Lua akurat `..` automatycznie konwertuje liczby, więc `tostring` tu nie jest konieczny, ale to dobry nawyk.

#### Rozwiązanie 0.3.2

```lua
local a = 15
local b = 4

print("suma:", a + b)        -- 19
print("różnica:", a - b)     -- 11
print("iloczyn:", a * b)     -- 60
print("iloraz:", a / b)      -- 3.75
print("reszta:", a % b)      -- 3
```

`%` to **modulo** — reszta z dzielenia. 15 ÷ 4 = 3 reszta 3.

#### Rozwiązanie 0.3.3

```lua
print(type(42))         -- number
print(type("hello"))    -- string
print(type(true))       -- boolean
print(type(nil))        -- nil
print(type(print))      -- function
```

`print` to **funkcja** — wbudowana w Lua. Funkcje to też wartości. O tym w L0.5.

#### Rozwiązanie 0.3.4

```lua
local s = "3.14"
local n = tonumber(s)
print(n + 1)    -- 4.14
```

#### Rozwiązanie 0.3.5

```
20   10
```

`y = x` **kopiuje** wartość (10) do `y`. Potem zmiana `x = 20` nie wpływa na `y` — `y` wciąż ma swoją kopię (10). Pudełka są niezależne.

### Sprawdź się

- [ ] Wiem, że zmienna to "pudełko z etykietą"
- [ ] Znam typy: number, string, boolean, nil
- [ ] Umiem łączyć stringi przez `..`
- [ ] Wiem, że `local` to dobra praktyka
- [ ] Umiem użyć `type()` do sprawdzenia typu

---

## Lekcja 0.4: Podejmowanie decyzji — `if` i `while`

### Cel

Program reaguje na warunki — robi różne rzeczy zależnie od danych. Powtarza czynności w pętli.

### Materiał

#### `if` — jeśli... to...

```lua
local temperatura = 35

if temperatura > 30 then
    print("Jest gorąco!")
end
```

Czytaj: "**Jeśli** temperatura jest większa niż 30, **to** wypisz 'Jest gorąco!'". Jeśli warunek jest fałszywy — `print` się nie wykona.

#### `if`/`else` — jeśli... to... w przeciwnym razie...

```lua
local wiek = 16

if wiek >= 18 then
    print("Jesteś pełnoletni.")
else
    print("Jesteś niepełnoletni.")
end
```

Jedno z dwóch się wykona — nigdy oba.

#### `if`/`elseif`/`else` — wiele warunków

```lua
local nota = 85

if nota >= 90 then
    print("Celująco!")
elseif nota >= 75 then
    print("Bardzo dobrze!")
elseif nota >= 60 then
    print("Dobrze.")
else
    print("Popracuj jeszcze.")
end
-- Bardzo dobrze!
```

Lua sprawdza warunki **od góry**. Pierwszy prawdziwy wygrywa. Reszta pomijana.

#### Operatory porównania

```lua
x == y     -- równe (DWIE równości!)
x ~= y     -- różne (NIE równe)
x > y      -- większe
x < y      -- mniejsze
x >= y     -- większe lub równe
x <= y     -- mniejsze lub równe
```

**Pułapka:** `=` to przypisanie (`x = 5`). `==` to porównanie (`x == 5`). Dwie różne rzeczy!

#### `and`, `or`, `not` — łączenie warunków

```lua
local wiek = 25
local ma_prawo_jazdy = true

if wiek >= 18 and ma_prawo_jazdy then
    print("Może prowadzić samochód.")
end

local jest_weekend = false
local jest_swieto = true

if jest_weekend or jest_swieto then
    print("Wolny dzień!")
end

if not jest_weekend then
    print("Dzień roboczy.")
end
```

- `and` — oba muszą być prawdziwe
- `or` — przynajmniej jedno
- `not` — odwraca (prawda → fałsz, fałsz → prawda)

#### `while` — powtarzaj dopóki

```lua
local i = 1
while i <= 5 do
    print("Powtórzenie nr " .. i)
    i = i + 1
end
```

```
Powtórzenie nr 1
Powtórzenie nr 2
Powtórzenie nr 3
Powtórzenie nr 4
Powtórzenie nr 5
```

`while warunek do ... end` — wykonuj blok dopóki warunek jest prawdziwy. **Pamiętaj o `i = i + 1`** — bez tego pętla nigdy się nie skończy (nieskończona pętla!).

#### `for` — powtórz N razy

```lua
for i = 1, 5 do
    print("Krok " .. i)
end
```

```
Krok 1
Krok 2
Krok 3
Krok 4
Krok 5
```

`for zmienna = start, stop do ... end` — prostsze niż `while` gdy wiesz ile razy.

Z krokiem:
```lua
for i = 0, 20, 5 do
    print(i)
end
-- 0  5  10  15  20
```

`for i = 0, 20, 5` → od 0 do 20, co 5.

#### `break` — przerwij pętlę

```lua
for i = 1, 100 do
    if i * i > 50 then
        print("Pierwsza liczba której kwadrat > 50: " .. i)
        break    -- wyskocz z pętli
    end
end
-- Pierwsza liczba której kwadrat > 50: 8
```

### Pułapki

1. **`=` vs `==`** — przypisanie vs porównanie. Najczęstszy błąd początkujących.
2. **Brak `i = i + 1` w `while`** — nieskończona pętla. Ctrl+C żeby przerwać.
3. **`end`** — każdy `if`, `while`, `for` musi mieć swoje `end`.
4. **W Lua `0` to prawda!** — `if 0 then print("tak") end` wypisze "tak". Tylko `false` i `nil` to fałsz.

### Zadania

**Zadanie 0.4.1**  
Napisz program który pyta o temperaturę (wpisz na sztywno jako zmienną) i wypisuje:
- < 0: "Mróz!"
- 0-15: "Chłodno."
- 16-25: "Przyjemnie."
- > 25: "Ciepło!"

**Zadanie 0.4.2**  
Pętla `for` — wypisz liczby od 1 do 10 i ich kwadraty: `"1^2 = 1"`, `"2^2 = 4"`, ...

**Zadanie 0.4.3**  
Suma liczb od 1 do 100 (użyj pętli `for` i zmiennej `suma`). Wypisz wynik (powinno być 5050).

**Zadanie 0.4.4**  
FizzBuzz — dla liczb 1-20:
- podzielne przez 3: wypisz "Fizz"
- podzielne przez 5: wypisz "Buzz"
- podzielne przez 3 i 5: wypisz "FizzBuzz"
- inne: wypisz liczbę

**Zadanie 0.4.5**  
Znajdź największą liczbę w zbiorze `{7, 23, 4, 42, 15, 8}` (bez tabeli — użyj zmiennych i `if`).

---

### Rozwiązania

#### Rozwiązanie 0.4.1

```lua
local temp = 22

if temp < 0 then
    print("Mróz!")
elseif temp <= 15 then
    print("Chłodno.")
elseif temp <= 25 then
    print("Przyjemnie.")
else
    print("Ciepło!")
end
-- Przyjemnie.
```

Zmień `temp` na różne wartości i uruchom ponownie — zobaczysz różne wyniki.

#### Rozwiązanie 0.4.2

```lua
for i = 1, 10 do
    print(i .. "^2 = " .. i * i)
end
-- 1^2 = 1
-- 2^2 = 4
-- ...
-- 10^2 = 100
```

#### Rozwiązanie 0.4.3

```lua
local suma = 0
for i = 1, 100 do
    suma = suma + i
end
print("Suma 1..100 = " .. suma)
-- Suma 1..100 = 5050
```

Wzorzec "akumulator" — zaczynamy od 0, w każdym kroku dodajemy.

#### Rozwiązanie 0.4.4

```lua
for i = 1, 20 do
    if i % 3 == 0 and i % 5 == 0 then
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

```
1
2
Fizz
4
Buzz
Fizz
7
8
Fizz
Buzz
11
Fizz
13
14
FizzBuzz
16
17
Fizz
19
Buzz
```

**FizzBuzz** to klasyczne zadanie na rozmowach rekrutacyjnych. Jeśli je rozwiązałeś — gratulacje, jesteś programistą!

Ważne: `i % 3 == 0 and i % 5 == 0` musi być PIERWSZA. Gdyby `i % 3 == 0` była pierwsza, złapałaby "15" jako "Fizz" zanim dotrzemy do "FizzBuzz".

#### Rozwiązanie 0.4.5

```lua
local max = 7    -- zaczynamy od pierwszej

if 23 > max then max = 23 end
if 4  > max then max = 4  end
if 42 > max then max = 42 end
if 15 > max then max = 15 end
if 8  > max then max = 8  end

print("Największa: " .. max)
-- Największa: 42
```

Wzorzec "trzymaj najlepszego kandydata" — zaczynasz od pierwszego, każdy następny porównujesz. W M01 poznasz tabele i pętlę — wtedy to będzie 3 linijki zamiast 6.

### Sprawdź się

- [ ] Umiem napisać `if`/`elseif`/`else`
- [ ] Pamiętam, że `=` to przypisanie, `==` to porównanie
- [ ] Umiem napisać pętlę `for` i `while`
- [ ] Wiem, że `break` przerywa pętlę
- [ ] Pamiętam, że w Lua `0` to prawda (tylko `false` i `nil` to fałsz)

---

## Lekcja 0.5: Funkcje — nazywanie kawałków kodu

### Cel

Definiujesz funkcje, wywołujesz je z argumentami, odbijerasz wyniki. Rozumiesz "dlaczego funkcje".

### Materiał

#### Po co funkcje?

Bez funkcji:

```lua
-- Oblicz pole prostokąta 3x5:
print("Pole: " .. 3 * 5)

-- Oblicz pole prostokąta 7x2:
print("Pole: " .. 7 * 2)

-- Oblicz pole prostokąta 10x4:
print("Pole: " .. 10 * 4)
```

Z funkcją:

```lua
local function pole_prostokata(a, b)
    return a * b
end

print("Pole: " .. pole_prostokata(3, 5))     -- 15
print("Pole: " .. pole_prostokata(7, 2))     -- 14
print("Pole: " .. pole_prostokata(10, 4))    -- 40
```

Funkcja to **nazwany kawałek kodu**, który możesz wielokrotnie wywoływać z różnymi danymi. Piszesz raz, używasz wielokrotnie.

#### Anatomia funkcji

```lua
local function nazwa(parametr1, parametr2)
    -- ciało funkcji — co robi
    return wynik    -- co zwraca
end
```

- **`local function nazwa`** — definiujesz funkcję o danej nazwie
- **`(parametr1, parametr2)`** — dane wejściowe (mogą być 0, 1, 2, ... parametrów)
- **`return wynik`** — wartość którą funkcja "oddaje" na zewnątrz
- **`end`** — koniec definicji

#### Wywołanie

```lua
local function powitaj(imie)
    print("Cześć, " .. imie .. "!")
end

powitaj("Anna")      -- Cześć, Anna!
powitaj("Maciej")    -- Cześć, Maciej!
powitaj("Lua")       -- Cześć, Lua!
```

#### Funkcja z `return`

```lua
local function kwadrat(x)
    return x * x
end

local wynik = kwadrat(7)
print(wynik)    -- 49

-- Można też bezpośrednio:
print(kwadrat(3))    -- 9
print(kwadrat(12))   -- 144
```

`return` "oddaje" wartość. Wywołujący może ją złapać do zmiennej lub użyć od razu.

#### Funkcja bez `return`

```lua
local function podzielnik()
    print("====================")
end

podzielnik()
print("Sekcja 1")
podzielnik()
print("Sekcja 2")
podzielnik()
```

```
====================
Sekcja 1
====================
Sekcja 2
====================
```

Nie każda funkcja musi coś zwracać. Niektóre robią "efekt uboczny" (np. drukują).

#### Wiele parametrów

```lua
local function bmi(waga_kg, wzrost_m)
    return waga_kg / (wzrost_m * wzrost_m)
end

print(string.format("BMI: %.1f", bmi(75, 1.80)))    -- BMI: 23.1
print(string.format("BMI: %.1f", bmi(90, 1.75)))    -- BMI: 29.4
```

`string.format("%.1f", x)` — formatuje liczbę z jednym miejscem po przecinku. Poznasz to dokładniej w M01.

#### Funkcja wywołująca funkcję

```lua
local function kwadrat(x)
    return x * x
end

local function suma_kwadratow(a, b)
    return kwadrat(a) + kwadrat(b)
end

print(suma_kwadratow(3, 4))    -- 9 + 16 = 25
```

Funkcje mogą wywoływać inne funkcje. To jest **składanie** — budowanie złożonych operacji z prostych.

#### Wbudowane funkcje

Lua ma wiele gotowych funkcji — już ich używałeś:

```lua
print("hello")        -- wypisuje
type(42)              -- zwraca "number"
tonumber("3.14")      -- zamienia string na liczbę
tostring(42)          -- zamienia liczbę na string
math.sqrt(16)         -- pierwiastek → 4
math.abs(-5)          -- wartość bezwzględna → 5
string.upper("abc")   -- na wielkie → "ABC"
string.lower("ABC")   -- na małe → "abc"
#"hello"              -- długość stringa → 5
```

### Pułapki

1. **Definicja vs wywołanie** — `function f() ... end` to definicja. `f()` to wywołanie. Sama definicja nic nie robi — musisz wywołać.
2. **`return` kończy funkcję** — kod po `return` nigdy się nie wykona.
3. **Brak `return`** — funkcja zwraca `nil`.
4. **Kolejność** — funkcja musi być zdefiniowana PRZED użyciem (w pliku powyżej wywołania).

### Zadania

**Zadanie 0.5.1**  
Napisz `obwod_prostokata(a, b)` — zwraca obwód. Test z kilkoma wartościami.

**Zadanie 0.5.2**  
Napisz `jest_parzysta(n)` — zwraca `true` jeśli n jest parzyste, `false` jeśli nieparzyste. Test:
```lua
print(jest_parzysta(4))    -- true
print(jest_parzysta(7))    -- false
```

**Zadanie 0.5.3**  
Napisz `max2(a, b)` — zwraca większą z dwóch liczb. Napisz `max3(a, b, c)` — największą z trzech (użyj `max2`!).

**Zadanie 0.5.4**  
Napisz `factorial(n)` — silnia (n! = 1 * 2 * 3 * ... * n). Użyj pętli `for`.

```lua
print(factorial(5))    -- 120
print(factorial(10))   -- 3628800
```

**Zadanie 0.5.5**  
Napisz `powtorz(tekst, n)` — zwraca string złożony z `tekst` powtórzonego `n` razy.

```lua
print(powtorz("ha", 3))    -- hahaha
print(powtorz("la ", 4))   -- la la la la 
```

---

### Rozwiązania

#### Rozwiązanie 0.5.1

```lua
local function obwod_prostokata(a, b)
    return 2 * (a + b)
end

print(obwod_prostokata(3, 5))     -- 16
print(obwod_prostokata(10, 4))    -- 28
print(obwod_prostokata(1, 1))     -- 4 (kwadrat)
```

#### Rozwiązanie 0.5.2

```lua
local function jest_parzysta(n)
    return n % 2 == 0
end

print(jest_parzysta(4))    -- true
print(jest_parzysta(7))    -- false
print(jest_parzysta(0))    -- true (zero jest parzyste)
print(jest_parzysta(-3))   -- false
```

`n % 2` daje resztę z dzielenia przez 2. Parzyste → reszta 0. Nieparzyste → reszta 1.

#### Rozwiązanie 0.5.3

```lua
local function max2(a, b)
    if a >= b then
        return a
    else
        return b
    end
end

local function max3(a, b, c)
    return max2(max2(a, b), c)
end

print(max2(3, 7))         -- 7
print(max2(10, 2))        -- 10
print(max3(3, 7, 5))      -- 7
print(max3(1, 2, 3))      -- 3
print(max3(100, 50, 75))  -- 100
```

`max3` wywołuje `max2` dwukrotnie — najpierw porównuje `a` z `b`, potem zwycięzcę z `c`. To jest **kompozycja** — budowanie złożonego z prostego.

#### Rozwiązanie 0.5.4

```lua
local function factorial(n)
    local wynik = 1
    for i = 2, n do
        wynik = wynik * i
    end
    return wynik
end

print(factorial(1))     -- 1
print(factorial(5))     -- 120  (1*2*3*4*5)
print(factorial(10))    -- 3628800
print(factorial(0))     -- 1  (konwencja: 0! = 1, pętla nie wykonuje się)
```

Wzorzec "akumulator z mnożeniem" — zamiast dodawania (suma) mnożymy.

#### Rozwiązanie 0.5.5

```lua
local function powtorz(tekst, n)
    local wynik = ""
    for i = 1, n do
        wynik = wynik .. tekst
    end
    return wynik
end

print(powtorz("ha", 3))      -- hahaha
print(powtorz("la ", 4))     -- la la la la 
print(powtorz("*", 10))      -- **********
```

W Lua istnieje wbudowana `string.rep("ha", 3)` która robi to samo. Ale ćwiczenie uczy jak budować wynik w pętli.

### Sprawdź się

- [ ] Umiem zdefiniować funkcję z `local function`
- [ ] Wiem, że `return` oddaje wartość na zewnątrz
- [ ] Umiem wywoływać funkcję z argumentami
- [ ] Umiem składać funkcje (jedna wywołuje drugą)
- [ ] Wiem, że Lua ma wbudowane funkcje (`print`, `type`, `math.sqrt`)

---

## Sprawdzian Modułu 0

Sześć zadań sprawdzających że jesteś gotowy na M01.

### Zadania

**Sprawdzian 1** — Kalkulator BMI  
Napisz program z funkcją `oblicz_bmi(waga_kg, wzrost_cm)` (uwaga: wzrost w centymetrach, nie metrach!). Wypisz BMI z jednym miejscem po przecinku i kategorię (niedowaga < 18.5, norma 18.5-25, nadwaga 25-30, otyłość > 30).

**Sprawdzian 2** — Tabliczka mnożenia  
Wypisz tabliczkę mnożenia 1-10 w formacie:
```
1 x 1 = 1
1 x 2 = 2
...
10 x 10 = 100
```
Użyj zagnieżdżonych pętli `for` (pętla w pętli).

**Sprawdzian 3** — Ciąg Fibonacciego  
Napisz `fibonacci(n)` — zwraca n-tą liczbę Fibonacciego (1, 1, 2, 3, 5, 8, 13, ...). Wypisz pierwsze 15 liczb.

**Sprawdzian 4** — Prosty szyfr  
Napisz `szyfruj(tekst)` — przesuwa każdą literę o 1 w alfabecie (a→b, b→c, z→a). Użyj `string.byte` i `string.char`. Napisz też `deszyfruj(tekst)`.

**Sprawdzian 5** — Statystyki  
Dane: `87, 92, 45, 78, 100, 63, 71, 88, 55, 96`. Oblicz (bez tabeli — zmienne i pętla):
- minimum
- maksimum
- średnią

**Sprawdzian 6** — Mini gra "zgadnij liczbę"  
Program losuje liczbę 1-100 (`math.random(1, 100)`). Gracz "zgaduje" (na sztywno wpisz kilka prób). Program mówi "za mało", "za dużo" lub "trafione!". Użyj pętli i `if`.

---

### Rozwiązania sprawdzianu

#### Sprawdzian 1

```lua
local function oblicz_bmi(waga_kg, wzrost_cm)
    local wzrost_m = wzrost_cm / 100
    return waga_kg / (wzrost_m * wzrost_m)
end

local function kategoria_bmi(bmi)
    if bmi < 18.5 then
        return "niedowaga"
    elseif bmi < 25 then
        return "norma"
    elseif bmi < 30 then
        return "nadwaga"
    else
        return "otyłość"
    end
end

-- Test:
local osoby = {
    {imie = "Anna", waga = 55, wzrost = 165},
    {imie = "Jan",  waga = 90, wzrost = 180},
    {imie = "Ewa",  waga = 45, wzrost = 170},
    {imie = "Piotr", waga = 105, wzrost = 175},
}

-- (tablice uczysz się w M01, ale tu pokażę wynik)
-- Wersja bez tabeli:

local bmi1 = oblicz_bmi(55, 165)
print(string.format("Anna: BMI = %.1f (%s)", bmi1, kategoria_bmi(bmi1)))

local bmi2 = oblicz_bmi(90, 180)
print(string.format("Jan: BMI = %.1f (%s)", bmi2, kategoria_bmi(bmi2)))

local bmi3 = oblicz_bmi(45, 170)
print(string.format("Ewa: BMI = %.1f (%s)", bmi3, kategoria_bmi(bmi3)))

local bmi4 = oblicz_bmi(105, 175)
print(string.format("Piotr: BMI = %.1f (%s)", bmi4, kategoria_bmi(bmi4)))
```

```
Anna: BMI = 20.2 (norma)
Jan: BMI = 27.8 (nadwaga)
Ewa: BMI = 15.6 (niedowaga)
Piotr: BMI = 34.3 (otyłość)
```

#### Sprawdzian 2

```lua
for i = 1, 10 do
    for j = 1, 10 do
        print(string.format("%2d x %2d = %3d", i, j, i * j))
    end
end
```

```
 1 x  1 =   1
 1 x  2 =   2
...
10 x 10 = 100
```

Pętla w pętli — "dla każdego `i`, przejdź przez wszystkie `j`". To daje 10 × 10 = 100 linii.

#### Sprawdzian 3

```lua
local function fibonacci(n)
    if n <= 2 then return 1 end
    local a, b = 1, 1
    for i = 3, n do
        a, b = b, a + b
    end
    return b
end

for i = 1, 15 do
    io.write(fibonacci(i) .. " ")
end
print()
-- 1 1 2 3 5 8 13 21 34 55 89 144 233 377 610
```

`a, b = b, a + b` — jednoczesne przypisanie. Lua oblicza prawą stronę ZANIM przypisze. Bez tego potrzebowałbyś zmiennej tymczasowej.

#### Sprawdzian 4

```lua
local function szyfruj(tekst)
    local wynik = ""
    for i = 1, #tekst do
        local bajt = string.byte(tekst, i)
        -- Małe litery a-z (97-122):
        if bajt >= 97 and bajt <= 122 then
            bajt = 97 + (bajt - 97 + 1) % 26
        -- Wielkie litery A-Z (65-90):
        elseif bajt >= 65 and bajt <= 90 then
            bajt = 65 + (bajt - 65 + 1) % 26
        end
        -- Inne znaki (spacja, cyfry) — bez zmian
        wynik = wynik .. string.char(bajt)
    end
    return wynik
end

local function deszyfruj(tekst)
    local wynik = ""
    for i = 1, #tekst do
        local bajt = string.byte(tekst, i)
        if bajt >= 97 and bajt <= 122 then
            bajt = 97 + (bajt - 97 - 1 + 26) % 26
        elseif bajt >= 65 and bajt <= 90 then
            bajt = 65 + (bajt - 65 - 1 + 26) % 26
        end
        wynik = wynik .. string.char(bajt)
    end
    return wynik
end

local original = "Hello World! Lua jest super."
local encrypted = szyfruj(original)
local decrypted = deszyfruj(encrypted)

print("Oryginał:    " .. original)
print("Zaszyfrowany:" .. encrypted)
print("Odszyfrowany:" .. decrypted)
print("Poprawnie?   " .. tostring(original == decrypted))
```

```
Oryginał:    Hello World! Lua jest super.
Zaszyfrowany:Ifmmp Xpsme! Mvb kftu tvqfs.
Odszyfrowany:Hello World! Lua jest super.
Poprawnie?   true
```

To jest **szyfr Cezara** z przesunięciem 1. `string.byte("a")` = 97. `string.char(98)` = "b". `% 26` zapewnia zawijanie (z → a).

#### Sprawdzian 5

```lua
local dane = {87, 92, 45, 78, 100, 63, 71, 88, 55, 96}

-- Wersja bez tabeli (jak w wymaganiach):
local min = 87
local max = 87
local suma = 87
local n = 1

local function sprawdz(v)
    if v < min then min = v end
    if v > max then max = v end
    suma = suma + v
    n = n + 1
end

sprawdz(92)
sprawdz(45)
sprawdz(78)
sprawdz(100)
sprawdz(63)
sprawdz(71)
sprawdz(88)
sprawdz(55)
sprawdz(96)

print("Minimum: " .. min)
print("Maksimum: " .. max)
print("Średnia: " .. string.format("%.1f", suma / n))
```

```
Minimum: 45
Maksimum: 100
Średnia: 77.5
```

W M01 z tablicami to będzie 5 linii zamiast 15. Ale wzorzec "trzymaj min/max/sumę i aktualizuj" jest uniwersalny.

#### Sprawdzian 6

```lua
math.randomseed(os.time())
local sekret = math.random(1, 100)

-- Symulacja prób (w prawdziwej grze czytałbyś z klawiatury):
local proby = {50, 75, 60, 65, 63, 64}

print("Zgadnij liczbę 1-100!")
print("(Sekret: " .. sekret .. " — normalnie byłby ukryty)")
print()

local zgadl = false
for _, proba in ipairs(proby) do
    print("Próba: " .. proba)
    if proba == sekret then
        print("  >>> TRAFIONE! <<<")
        zgadl = true
        break
    elseif proba < sekret then
        print("  Za mało!")
    else
        print("  Za dużo!")
    end
end

if not zgadl then
    print("Nie trafiłeś. Sekret to " .. sekret)
end
```

```
Zgadnij liczbę 1-100!
(Sekret: 64 — normalnie byłby ukryty)

Próba: 50
  Za mało!
Próba: 75
  Za dużo!
Próba: 60
  Za mało!
Próba: 65
  Za dużo!
Próba: 63
  Za mało!
Próba: 64
  >>> TRAFIONE! <<<
```

Strategia "binary search" — za mało/za dużo → zawęż zakres o połowę. W 7 próbach zgadniesz każdą liczbę 1-100 (bo 2^7 = 128 > 100).

`math.randomseed(os.time())` — inicjalizuje generator losowy od czasu. Bez tego `math.random` daje te same "losowe" liczby co uruchomienie.

---

## Co dalej?

Jeśli rozwiązałeś Sprawdzian Modułu 0 — jesteś gotowy na **Moduł 1: Fundamenty**. Tam spotkasz tabele (M2), funkcje zaawansowane (M3), i resztę Lua — ale fundamenty z M0 dają Ci grunt pod nogami.

→ **Moduł 1: Fundamenty** — typy Lua w pełni, truthy/falsy, stringi i patterns, pętla `for ... in`, scope zmiennych.
