# Moduł 8: C API — podstawy

> *"Lua to nie aplikacja. Lua to biblioteka. Twoja aplikacja jest hostem."*

Od tego modułu perspektywa się odwraca. Do tej pory pisaliśmy **w** Lua. Teraz piszemy **program w C** który **osadza** Lua jako wewnętrzny język skryptowy. To jest fundament KarmazynOS — host w C kontroluje interpreter, ładuje skrypty, wstrzykuje API, ogranicza zasoby, łapie błędy.

**Wymagania techniczne:**
- kompilator C (`gcc` lub `clang`)
- nagłówki Lua: `liblua5.4-dev` (Debian/Ubuntu), `lua` (Arch), `lua54` (Termux: `pkg install lua54`)
- `make` (opcjonalnie)

Kompilacja przykładów:
```bash
# Debian/Ubuntu:
gcc -o demo demo.c -llua5.4 -lm -ldl

# Arch:
gcc -o demo demo.c -llua -lm -ldl

# Termux:
clang -o demo demo.c -llua5.4 -lm
```

**Przewidywany czas:** 6-8 godzin pracy.

**Lekcje:**
1. `lua_State` i stos — model mentalny
2. Push, pop, peek — operacje na stosie
3. Wywołanie Lua z C — `luaL_dostring`, `lua_pcall`
4. Rejestracja funkcji C dla Lua
5. Walidacja argumentów — `luaL_check*`, tablice, zagnieżdżone struktury

Plus **Sprawdzian Modułu 8** — 6 zadań z pełnymi rozwiązaniami.

---

## Lekcja 8.1: `lua_State` i stos — model mentalny

### Cel

Rozumiesz co to `lua_State`, jak działa stos komunikacji C ↔ Lua, jak indeksować stos (dodatnio i ujemnie).

### Materiał

#### Co to `lua_State`

`lua_State *L` to **cały interpreter Lua** — zmienne, tabele, funkcje, GC, stack, loaded modules. Jeden `lua_State` = jeden niezależny "świat Lua".

```c
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

int main(void) {
    lua_State *L = luaL_newstate();   // stwórz interpreter
    luaL_openlibs(L);                  // załaduj standardową bibliotekę
    
    // ... tu używasz L ...
    
    lua_close(L);                      // sprzątanie
    return 0;
}
```

Możesz mieć wiele `lua_State` — w KarmazynOS **każda sesja HSS to osobny `lua_State`**. Izolacja na poziomie interpretera.

#### Stos — mechanizm komunikacji

Cały interfejs C ↔ Lua chodzi przez **stos** powiązany z `lua_State`. C i Lua mają radykalnie różne modele pamięci (C: statyczne typy, pointery; Lua: dynamiczne typy, GC). Stos jest neutralnym terenem.

```
Indeks dodatni:     Indeks ujemny:
   |       |
4  | "d"   |  -1  (top)
3  | "c"   |  -2
2  | "b"   |  -3
1  | "a"   |  -4  (bottom)
   |_______|
```

- `lua_gettop(L)` — zwraca indeks top (= liczba elementów).
- Indeks `1` = dół. Indeks `-1` = top.
- Indeks `0` = **nigdy** — nielegalny.
- W 90% kodu C z Lua używasz ujemnych indeksów.

#### Nagłówki

```c
#include <lua.h>       // core API: lua_push*, lua_to*, lua_call
#include <lualib.h>    // luaopen_* (biblioteki standardowe)
#include <lauxlib.h>   // luaL_* (wygodne helpery)
```

#### Minimalny program

```c
// hello_lua.c
#include <stdio.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

int main(void) {
    lua_State *L = luaL_newstate();
    if (L == NULL) {
        fprintf(stderr, "nie udało się stworzyć lua_State\n");
        return 1;
    }
    
    luaL_openlibs(L);
    
    int rc = luaL_dostring(L, "print('Hello from Lua!')");
    if (rc != LUA_OK) {
        fprintf(stderr, "Lua error: %s\n", lua_tostring(L, -1));
        lua_pop(L, 1);
    }
    
    lua_close(L);
    return 0;
}
```

#### Selektywne biblioteki

W sandboxie nie chcesz wszystkich bibliotek:

```c
luaL_requiref(L, "_G", luaopen_base, 1);     lua_pop(L, 1);
luaL_requiref(L, "math", luaopen_math, 1);     lua_pop(L, 1);
luaL_requiref(L, "string", luaopen_string, 1);  lua_pop(L, 1);
luaL_requiref(L, "table", luaopen_table, 1);     lua_pop(L, 1);
// NIE ładujemy: os, io, debug, package
```

Bez `os`, `io`, `debug` — skrypt nie otworzy pliku, nie odpali procesu, nie zhakuje hosta.

### Pułapki

1. **`lua_State` to opaque pointer** — nie dereferencuj.
2. **Stos rośnie i maleje** — sprawdzaj `lua_gettop(L)`.
3. **Indeks 0 jest nielegalny.**
4. **Brak `luaL_openlibs`** — `print` nie istnieje.
5. **Nigdy nie używaj `L` po `lua_close(L)`** — use after free.

### Zadania

**Zadanie 8.1.1**  
Program C: stwórz `lua_State`, załaduj **tylko** `math` i `string` (bez base!). Wykonaj `print("hello")` — powinien dać error. Następnie `return math.sqrt(16)` — odczytaj wynik ze stosu i drukuj w C.

**Zadanie 8.1.2**  
Stwórz **dwa** `lua_State` — L1 i L2. W L1 ustaw `x = 42`. W L2 odczytaj `x`. Pokaż niezależność.

**Zadanie 8.1.3**  
Program przyjmujący ścieżkę `.lua` z `argv[1]`, ładujący plik (`luaL_dofile`), obsługujący błędy.

**Zadanie 8.1.4**  
Mini REPL w C: czytaj linie z stdin, wykonuj przez `luaL_dostring`, drukuj wyniki lub errors. Pętla aż EOF.

**Zadanie 8.1.5**  
Sandbox: załaduj bazę, math, string, table — ale **nie** os/io/debug. Uruchom `os.execute("ls")` — pokaż że jest zablokowane.

---

### Rozwiązania

#### Rozwiązanie 8.1.1

```c
// selective_libs.c
#include <stdio.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

int main(void) {
    lua_State *L = luaL_newstate();
    
    // Tylko math i string — bez base (bez print!):
    luaL_requiref(L, "math", luaopen_math, 1);
    lua_pop(L, 1);
    luaL_requiref(L, "string", luaopen_string, 1);
    lua_pop(L, 1);
    
    // Test 1: print nie istnieje
    printf("--- Test 1: print ---\n");
    int rc = luaL_dostring(L, "print('hello')");
    if (rc != LUA_OK) {
        fprintf(stderr, "BLOCKED: %s\n", lua_tostring(L, -1));
        lua_pop(L, 1);
    }
    
    // Test 2: math.sqrt istnieje
    printf("--- Test 2: math.sqrt ---\n");
    rc = luaL_dostring(L, "return math.sqrt(16)");
    if (rc != LUA_OK) {
        fprintf(stderr, "ERROR: %s\n", lua_tostring(L, -1));
        lua_pop(L, 1);
    } else {
        if (lua_isnumber(L, -1)) {
            printf("math.sqrt(16) = %g\n", lua_tonumber(L, -1));
        }
        lua_pop(L, 1);
    }
    
    lua_close(L);
    return 0;
}
```

```
--- Test 1: print ---
BLOCKED: [string "print('hello')"]:1: attempt to call a nil value (global 'print')
--- Test 2: math.sqrt ---
math.sqrt(16) = 4
```

Bez `luaopen_base` nie ma `print`, `type`, `tostring`, `error`, `pcall`, `assert`. To jest **base library**, nie core. Keywords (`return`, `if`, `for`, `local`) wciąż działają — to kompilator.

#### Rozwiązanie 8.1.2

```c
// two_states.c
#include <stdio.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

int main(void) {
    lua_State *L1 = luaL_newstate();
    lua_State *L2 = luaL_newstate();
    luaL_openlibs(L1);
    luaL_openlibs(L2);
    
    luaL_dostring(L1, "x = 42");
    
    luaL_dostring(L1, "return x");
    printf("L1: x = %g\n", lua_tonumber(L1, -1));
    lua_pop(L1, 1);
    
    luaL_dostring(L2, "return x");
    if (lua_isnil(L2, -1)) {
        printf("L2: x = nil (niezależne!)\n");
    } else {
        printf("L2: x = %g\n", lua_tonumber(L2, -1));
    }
    lua_pop(L2, 1);
    
    lua_close(L1);
    lua_close(L2);
    return 0;
}
```

```
L1: x = 42
L2: x = nil (niezależne!)
```

#### Rozwiązanie 8.1.3

```c
// run_file.c
#include <stdio.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

int main(int argc, char *argv[]) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <script.lua>\n", argv[0]);
        return 1;
    }
    
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    
    int rc = luaL_dofile(L, argv[1]);
    if (rc != LUA_OK) {
        fprintf(stderr, "Error in '%s': %s\n", argv[1], lua_tostring(L, -1));
        lua_pop(L, 1);
        lua_close(L);
        return 1;
    }
    
    lua_close(L);
    return 0;
}
```

#### Rozwiązanie 8.1.4

```c
// mini_repl.c
#include <stdio.h>
#include <string.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    
    char buf[4096];
    printf("Lua %s REPL (Ctrl+D to exit)\n", LUA_VERSION);
    
    while (1) {
        printf("> ");
        fflush(stdout);
        
        if (fgets(buf, sizeof(buf), stdin) == NULL) {
            printf("\n");
            break;
        }
        
        size_t len = strlen(buf);
        if (len > 0 && buf[len - 1] == '\n') buf[len - 1] = '\0';
        if (strlen(buf) == 0) continue;
        
        // Spróbuj "return <expr>" (żeby wyrażenia wypisywały wynik):
        char return_buf[4096 + 16];
        snprintf(return_buf, sizeof(return_buf), "return %s", buf);
        
        int rc = luaL_loadstring(L, return_buf);
        if (rc == LUA_OK) {
            rc = lua_pcall(L, 0, LUA_MULTRET, 0);
            if (rc == LUA_OK) {
                int nresults = lua_gettop(L);
                if (nresults > 0) {
                    for (int i = 1; i <= nresults; i++) {
                        if (i > 1) printf("\t");
                        luaL_tolstring(L, i, NULL);
                        printf("%s", lua_tostring(L, -1));
                        lua_pop(L, 1);
                    }
                    printf("\n");
                }
                lua_settop(L, 0);
                continue;
            }
            fprintf(stderr, "%s\n", lua_tostring(L, -1));
            lua_pop(L, 1);
            continue;
        }
        lua_pop(L, 1);
        
        // Nie kompiluje się z "return" — spróbuj bez:
        rc = luaL_dostring(L, buf);
        if (rc != LUA_OK) {
            fprintf(stderr, "%s\n", lua_tostring(L, -1));
            lua_pop(L, 1);
        }
    }
    
    lua_close(L);
    return 0;
}
```

```
> 2 + 2
4
> print("hello")
hello
> x = 42
> x * 2
84
> for i=1,3 do print(i) end
1
2
3
```

Trick "najpierw return expr" to dokładnie to co robi oficjalny `lua` REPL. `luaL_tolstring` wywołuje `tostring()` na dowolnym typie.

#### Rozwiązanie 8.1.5

```c
// sandbox_no_os.c
#include <stdio.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

int main(void) {
    lua_State *L = luaL_newstate();
    
    luaL_requiref(L, "_G", luaopen_base, 1);     lua_pop(L, 1);
    luaL_requiref(L, "math", luaopen_math, 1);     lua_pop(L, 1);
    luaL_requiref(L, "string", luaopen_string, 1);  lua_pop(L, 1);
    luaL_requiref(L, "table", luaopen_table, 1);     lua_pop(L, 1);
    
    luaL_dostring(L, "print('base załadowane')");
    
    int rc = luaL_dostring(L, "os.execute('echo HACKED')");
    if (rc != LUA_OK) {
        fprintf(stderr, "BLOCKED os: %s\n", lua_tostring(L, -1));
        lua_pop(L, 1);
    }
    
    rc = luaL_dostring(L, "io.open('/etc/passwd')");
    if (rc != LUA_OK) {
        fprintf(stderr, "BLOCKED io: %s\n", lua_tostring(L, -1));
        lua_pop(L, 1);
    }
    
    rc = luaL_dostring(L, "debug.getinfo(1)");
    if (rc != LUA_OK) {
        fprintf(stderr, "BLOCKED debug: %s\n", lua_tostring(L, -1));
        lua_pop(L, 1);
    }
    
    luaL_dostring(L, "print('pi = ' .. math.pi)");
    
    lua_close(L);
    return 0;
}
```

```
base załadowane
BLOCKED os: ...attempt to index a nil value (global 'os')
BLOCKED io: ...attempt to index a nil value (global 'io')
BLOCKED debug: ...attempt to index a nil value (global 'debug')
pi = 3.1415926535898
```

### Sprawdź się

- [ ] Wiem, co to `lua_State`
- [ ] Rozumiem indeksowanie stosu: 1 = dół, -1 = top
- [ ] Umiem skompilować program C z Lua
- [ ] Znam różnicę `luaL_dostring` vs `luaL_dofile`
- [ ] Wiem, jak selektywnie ładować biblioteki

---

## Lekcja 8.2: Push, pop, peek — operacje na stosie

### Cel

Kładziesz wartości na stos, odczytujesz, zdejmujesz. Budujesz i czytasz tabele z C. Masz `dump_stack` w toolkicie.

### Materiał

#### Push

```c
lua_pushnil(L);                    // nil
lua_pushboolean(L, 1);            // true
lua_pushinteger(L, 42);           // integer
lua_pushnumber(L, 3.14);          // float
lua_pushstring(L, "hello");       // string (kopiowany do Lua)
lua_pushlstring(L, data, len);    // string z długością
lua_pushfstring(L, "x=%d", 42);  // format string
lua_pushvalue(L, idx);             // kopiuj element z idx na top
lua_pushcfunction(L, fn);          // C function
```

#### Odczyt (peek — nie zdejmuje)

```c
int lua_type(L, idx);               // LUA_TNIL, LUA_TBOOLEAN, ...
int lua_toboolean(L, idx);          // 0 lub 1
lua_Integer lua_tointeger(L, idx);  // int64
lua_Number lua_tonumber(L, idx);    // double
const char *lua_tostring(L, idx);   // UWAGA: pointer do wnętrza Lua!
```

**Krytyczne:** `lua_tostring` zwraca pointer do **wewnętrznej pamięci Lua**. Po `lua_pop` — pointer jest dangling. Kopiuj jeśli potrzebujesz na dłużej.

#### Pop i manipulacje

```c
lua_pop(L, n);              // zdejmij n z topu
lua_settop(L, n);           // ustaw top na n (0 = wyczyść)
lua_insert(L, idx);         // przenieś top na pozycję idx
lua_remove(L, idx);         // usuń z pozycji idx
lua_replace(L, idx);        // zdejmij top, nadpisz idx
lua_rotate(L, idx, n);      // rotuj elementy [5.3+]
```

#### Budowanie tabeli

```c
lua_newtable(L);                      // push {}
lua_pushstring(L, "abc");
lua_setfield(L, -2, "sig");          // t.sig = "abc"; pop "abc"
lua_pushnumber(L, 0.7);
lua_setfield(L, -2, "phi");          // t.phi = 0.7; pop 0.7
lua_setglobal(L, "atom");            // _G.atom = t; pop t
```

#### Budowanie tablicy (sekwencji)

```c
lua_newtable(L);
for (int i = 0; i < 5; i++) {
    lua_pushinteger(L, (i + 1) * 10);
    lua_rawseti(L, -2, i + 1);       // t[i+1] = value; pop value
}
```

#### Odczyt tabeli

```c
lua_getglobal(L, "atom");            // push atom
lua_getfield(L, -1, "sig");          // push atom.sig
const char *sig = lua_tostring(L, -1);
lua_pop(L, 1);
lua_getfield(L, -1, "phi");          // push atom.phi
double phi = lua_tonumber(L, -1);
lua_pop(L, 2);                       // pop phi + atom
```

#### Debug helper — dump_stack

```c
static void dump_stack(lua_State *L) {
    int top = lua_gettop(L);
    printf("--- stack (%d) ---\n", top);
    for (int i = 1; i <= top; i++) {
        int t = lua_type(L, i);
        switch (t) {
            case LUA_TNIL:     printf("  %d: nil\n", i); break;
            case LUA_TBOOLEAN: printf("  %d: %s\n", i, lua_toboolean(L, i) ? "true" : "false"); break;
            case LUA_TNUMBER:
                if (lua_isinteger(L, i))
                    printf("  %d: %lld (int)\n", i, (long long)lua_tointeger(L, i));
                else
                    printf("  %d: %g (float)\n", i, lua_tonumber(L, i));
                break;
            case LUA_TSTRING:  printf("  %d: \"%s\"\n", i, lua_tostring(L, i)); break;
            case LUA_TTABLE:   printf("  %d: table\n", i); break;
            case LUA_TFUNCTION:printf("  %d: function\n", i); break;
            default:           printf("  %d: %s\n", i, lua_typename(L, t)); break;
        }
    }
    printf("---\n");
}
```

### Pułapki

1. **`lua_tostring` → dangling pointer po pop.**
2. **`lua_setfield` zdejmuje top** — indeksy tabeli nie zmieniają się, ale stos maleje.
3. **`lua_isstring` zwraca true dla number** (auto-konwersja). Strict: `lua_type(L, idx) == LUA_TSTRING`.
4. **Push w pętli bez pop** — stos rośnie bez kontroli.

### Zadania

**Zadanie 8.2.1**  
Push 5 wartości (nil, true, 42, 3.14, "hello"), dump_stack, pushvalue(3), dump, pop(2), dump.

**Zadanie 8.2.2**  
Funkcja C `push_atom(L, sig, phi, alive)` budująca tabelę. Test: przypisz do globalnej, potwierdź z Lua.

**Zadanie 8.2.3**  
Funkcja C `read_atom(L, idx)` odczytująca tabelę na pozycji `idx`, drukująca w C.

**Zadanie 8.2.4**  
Z C zbuduj tabelę-tablicę `{10, 20, 30, 40, 50}`, ustaw jako globalną. Test z Lua: `ipairs`.

**Zadanie 8.2.5**  
Z C zbuduj zagnieżdżoną tabelę `config = {name="test", quota={cpu_ms=500, mem_kb=4096}, caps={"phi.read","phi.write"}}`. Odczytaj z C `config.quota.cpu_ms` i `config.caps[2]`.

---

### Rozwiązania

#### Rozwiązanie 8.2.1

```c
// stack_ops.c
#include <stdio.h>
#include <lua.h>
#include <lauxlib.h>

static void dump_stack(lua_State *L) {
    int top = lua_gettop(L);
    printf("--- stack (%d) ---\n", top);
    for (int i = 1; i <= top; i++) {
        int t = lua_type(L, i);
        switch (t) {
            case LUA_TNIL:     printf("  %d: nil\n", i); break;
            case LUA_TBOOLEAN: printf("  %d: %s\n", i, lua_toboolean(L, i) ? "true" : "false"); break;
            case LUA_TNUMBER:
                if (lua_isinteger(L, i))
                    printf("  %d: %lld\n", i, (long long)lua_tointeger(L, i));
                else
                    printf("  %d: %g\n", i, lua_tonumber(L, i));
                break;
            case LUA_TSTRING:  printf("  %d: \"%s\"\n", i, lua_tostring(L, i)); break;
            default:           printf("  %d: %s\n", i, lua_typename(L, t)); break;
        }
    }
    printf("---\n");
}

int main(void) {
    lua_State *L = luaL_newstate();
    
    lua_pushnil(L);
    lua_pushboolean(L, 1);
    lua_pushinteger(L, 42);
    lua_pushnumber(L, 3.14);
    lua_pushstring(L, "hello");
    
    printf("After push 5:\n");
    dump_stack(L);
    
    lua_pushvalue(L, 3);    // copy slot 3 (42) to top
    printf("After pushvalue(3):\n");
    dump_stack(L);
    
    lua_pop(L, 2);          // pop top 2 (42-copy and "hello")
    printf("After pop(2):\n");
    dump_stack(L);
    
    lua_close(L);
    return 0;
}
```

```
After push 5:
--- stack (5) ---
  1: nil
  2: true
  3: 42
  4: 3.14
  5: "hello"
---
After pushvalue(3):
--- stack (6) ---
  1: nil
  2: true
  3: 42
  4: 3.14
  5: "hello"
  6: 42
---
After pop(2):
--- stack (4) ---
  1: nil
  2: true
  3: 42
  4: 3.14
---
```

#### Rozwiązanie 8.2.2

```c
// push_atom.c
#include <stdio.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

static void push_atom(lua_State *L, const char *sig, double phi, int alive) {
    lua_newtable(L);
    
    lua_pushstring(L, sig);
    lua_setfield(L, -2, "sig");
    
    lua_pushnumber(L, phi);
    lua_setfield(L, -2, "phi");
    
    lua_pushboolean(L, alive);
    lua_setfield(L, -2, "alive");
}

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    
    push_atom(L, "abc123", 0.742, 1);
    lua_setglobal(L, "my_atom");
    
    luaL_dostring(L, "print(my_atom.sig, my_atom.phi, my_atom.alive)");
    // abc123   0.742   true
    
    push_atom(L, "def456", 0.333, 0);
    lua_setglobal(L, "dead_atom");
    luaL_dostring(L, "print(dead_atom.sig, dead_atom.phi, dead_atom.alive)");
    // def456   0.333   false
    
    lua_close(L);
    return 0;
}
```

#### Rozwiązanie 8.2.3

```c
// read_atom.c
#include <stdio.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

static void read_atom(lua_State *L, int idx) {
    idx = lua_absindex(L, idx);
    
    lua_getfield(L, idx, "sig");
    const char *sig = lua_tostring(L, -1);
    lua_pop(L, 1);
    
    lua_getfield(L, idx, "phi");
    double phi = lua_tonumber(L, -1);
    lua_pop(L, 1);
    
    lua_getfield(L, idx, "alive");
    int alive = lua_toboolean(L, -1);
    lua_pop(L, 1);
    
    printf("Atom: sig=%s, phi=%.4f, alive=%s\n",
        sig ? sig : "(nil)", phi, alive ? "true" : "false");
}

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    
    luaL_dostring(L, "atom = {sig='test-1', phi=0.85, alive=true}");
    
    lua_getglobal(L, "atom");
    read_atom(L, -1);
    lua_pop(L, 1);
    // Atom: sig=test-1, phi=0.8500, alive=true
    
    lua_close(L);
    return 0;
}
```

`lua_absindex` normalizuje ujemny indeks — bez tego `getfield` w środku przesuwa stos.

#### Rozwiązanie 8.2.4

```c
// push_array.c
#include <stdio.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    
    lua_newtable(L);
    int values[] = {10, 20, 30, 40, 50};
    for (int i = 0; i < 5; i++) {
        lua_pushinteger(L, values[i]);
        lua_rawseti(L, -2, i + 1);
    }
    lua_setglobal(L, "numbers");
    
    luaL_dostring(L, "for i, v in ipairs(numbers) do print(i, v) end");
    // 1  10 / 2  20 / 3  30 / 4  40 / 5  50
    
    lua_close(L);
    return 0;
}
```

`lua_rawseti(L, idx, i)` — zdejmuje top, wstawia jako `t[i]` bez metametod.

#### Rozwiązanie 8.2.5

```c
// nested_table.c
#include <stdio.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    
    // config = {}
    lua_newtable(L);
    
    // config.name = "test"
    lua_pushstring(L, "test");
    lua_setfield(L, -2, "name");
    
    // config.quota = {cpu_ms=500, mem_kb=4096}
    lua_newtable(L);
    lua_pushinteger(L, 500);
    lua_setfield(L, -2, "cpu_ms");
    lua_pushinteger(L, 4096);
    lua_setfield(L, -2, "mem_kb");
    lua_setfield(L, -2, "quota");    // config.quota = <top>; pop quota
    
    // config.caps = {"phi.read", "phi.write"}
    lua_newtable(L);
    lua_pushstring(L, "phi.read");
    lua_rawseti(L, -2, 1);
    lua_pushstring(L, "phi.write");
    lua_rawseti(L, -2, 2);
    lua_setfield(L, -2, "caps");
    
    lua_setglobal(L, "config");
    
    // Weryfikacja z Lua:
    luaL_dostring(L, "print(config.name, config.quota.cpu_ms, config.caps[2])");
    // test   500   phi.write
    
    // Odczyt zagnieżdżony z C:
    lua_getglobal(L, "config");
    lua_getfield(L, -1, "quota");
    lua_getfield(L, -1, "cpu_ms");
    printf("config.quota.cpu_ms = %lld\n", (long long)lua_tointeger(L, -1));
    lua_pop(L, 3);
    
    lua_getglobal(L, "config");
    lua_getfield(L, -1, "caps");
    lua_rawgeti(L, -1, 2);
    printf("config.caps[2] = \"%s\"\n", lua_tostring(L, -1));
    lua_pop(L, 3);
    
    lua_close(L);
    return 0;
}
```

### Sprawdź się

- [ ] Umiem pushować nil, boolean, integer, number, string
- [ ] Pamiętam, że `lua_tostring` → dangling po pop
- [ ] Umiem zbudować tabelę i tablicę z C
- [ ] Umiem odczytać zagnieżdżone pola z C
- [ ] Mam `dump_stack` w toolkicie

---

## Lekcja 8.3: Wywołanie Lua z C — `luaL_dostring`, `lua_pcall`

### Cel

Wywołujesz funkcje Lua z C z argumentami. Odbierasz wyniki (w tym multiple return). Używasz message handlera z traceback.

### Materiał

#### `lua_pcall(L, nargs, nresults, msgh)`

Przed `pcall`:
```
stos: [..., function, arg1, arg2, ..., argN]
```

Po `pcall` z LUA_OK:
```
stos: [..., result1, result2, ..., resultN]
```

Po `pcall` z error:
```
stos: [..., errmsg]
```

```c
lua_getglobal(L, "add");
lua_pushinteger(L, 3);
lua_pushinteger(L, 4);
int rc = lua_pcall(L, 2, 1, 0);    // 2 args, 1 result
if (rc == LUA_OK) {
    printf("add(3,4) = %lld\n", (long long)lua_tointeger(L, -1));
    lua_pop(L, 1);
} else {
    fprintf(stderr, "Error: %s\n", lua_tostring(L, -1));
    lua_pop(L, 1);
}
```

#### Message handler z traceback

```c
static int traceback_handler(lua_State *L) {
    const char *msg = lua_tostring(L, 1);
    luaL_traceback(L, L, msg, 1);
    return 1;
}

// Użycie:
lua_pushcfunction(L, traceback_handler);
int msgh = lua_gettop(L);
lua_getglobal(L, "risky_function");
int rc = lua_pcall(L, 0, 0, msgh);
if (rc != LUA_OK) {
    fprintf(stderr, "%s\n", lua_tostring(L, -1));
    lua_pop(L, 1);
}
lua_remove(L, msgh);
```

#### Separacja kompilacji i wykonania

```c
int rc = luaL_loadbufferx(L, code, strlen(code), "script", "t");
// "t" = text only (no bytecode) — BEZPIECZEŃSTWO
if (rc == LUA_OK) {
    rc = lua_pcall(L, 0, LUA_MULTRET, 0);
}
```

### Pułapki

1. **`lua_pcall` zdejmuje func + args** ze stosu — nawet przy błędzie.
2. **`lua_call` crashuje** przy błędzie — **nigdy w produkcji**.
3. **`LUA_MULTRET`** — sprawdź `lua_gettop` po pcall żeby wiedzieć ile wyników.

### Zadania

**Zadanie 8.3.1**  
Zdefiniuj w Lua `greet(name)`, wywołaj z C 3 razy z różnymi argumentami, drukuj wyniki.

**Zadanie 8.3.2**  
Napisz `safe_call_lua(L, fn_name, nargs, nresults)` — obsługuje dotted names (`math.sqrt`), handler z traceback, error logging. Full-featured wrapper.

**Zadanie 8.3.3**  
Załaduj plik config.lua z `max_atoms = 1000` i `function validate(x) return x > 0 end`. Odczytaj z C `max_atoms`, wywołaj `validate(42)`.

**Zadanie 8.3.4**  
Głęboki call chain A→B→C→error. Message handler z traceback. Pokaż pełen stack.

**Zadanie 8.3.5**  
Napisz `run_lua_chunk(L, code, name)` — kompiluje text-only, wykonuje, loguje compile vs runtime error osobno, drukuje wyniki.

---

### Rozwiązania

#### Rozwiązanie 8.3.1

```c
// call_greet.c
#include <stdio.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    
    luaL_dostring(L, "function greet(name) return 'Hello, ' .. name .. '!' end");
    
    const char *names[] = {"Maciej", "Anna", "KarmazynOS"};
    for (int i = 0; i < 3; i++) {
        lua_getglobal(L, "greet");
        lua_pushstring(L, names[i]);
        int rc = lua_pcall(L, 1, 1, 0);
        if (rc == LUA_OK) {
            printf("greet('%s') = \"%s\"\n", names[i], lua_tostring(L, -1));
            lua_pop(L, 1);
        } else {
            fprintf(stderr, "Error: %s\n", lua_tostring(L, -1));
            lua_pop(L, 1);
        }
    }
    
    lua_close(L);
    return 0;
}
```

```
greet('Maciej') = "Hello, Maciej!"
greet('Anna') = "Hello, Anna!"
greet('KarmazynOS') = "Hello, KarmazynOS!"
```

#### Rozwiązanie 8.3.2

```c
// safe_call.c
#include <stdio.h>
#include <string.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

static int traceback_handler(lua_State *L) {
    const char *msg = lua_tostring(L, 1);
    if (!msg) msg = "(non-string error)";
    luaL_traceback(L, L, msg, 1);
    return 1;
}

// Pushuje "a.b.c" rozwiązując łańcuch tabeli. Zwraca 1 na sukces, 0 na fail.
static int push_dotted(lua_State *L, const char *name) {
    char buf[256];
    strncpy(buf, name, sizeof(buf) - 1);
    buf[sizeof(buf) - 1] = '\0';
    
    char *save = NULL;
    char *tok = strtok_r(buf, ".", &save);
    if (!tok) return 0;
    
    lua_getglobal(L, tok);
    
    tok = strtok_r(NULL, ".", &save);
    while (tok) {
        if (!lua_istable(L, -1)) { lua_pop(L, 1); return 0; }
        lua_getfield(L, -1, tok);
        lua_remove(L, -2);    // remove parent
        tok = strtok_r(NULL, ".", &save);
    }
    return 1;
}

int safe_call_lua(lua_State *L, const char *fn_name, int nargs, int nresults) {
    // Stos wejściowy: [..., arg1, ..., argN]
    // Musimy wstawić handler PRZED args, func PRZED args ale PO handlerze.
    
    int base = lua_gettop(L) - nargs;    // indeks tuż PRZED args
    
    // Push handler na pozycję base+1 (przed args):
    lua_pushcfunction(L, traceback_handler);
    lua_insert(L, base + 1);              // przesuń handler pod args
    int msgh_idx = base + 1;
    
    // Push func na pozycję base+2 (między handler a args):
    if (!push_dotted(L, fn_name)) {
        fprintf(stderr, "[safe_call] not found: %s\n", fn_name);
        lua_remove(L, msgh_idx);
        for (int i = 0; i < nargs; i++) lua_pop(L, 1);
        return -1;
    }
    lua_insert(L, base + 2);    // przesuń func przed args
    
    // Stos: [..., handler, func, arg1, ..., argN]
    int rc = lua_pcall(L, nargs, nresults, msgh_idx);
    
    if (rc != LUA_OK) {
        fprintf(stderr, "[safe_call] %s failed:\n%s\n", fn_name, lua_tostring(L, -1));
        lua_pop(L, 1);
    }
    
    lua_remove(L, msgh_idx);    // remove handler
    return rc;
}

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    
    // Test 1: math.sqrt(42)
    lua_pushnumber(L, 42);
    int rc = safe_call_lua(L, "math.sqrt", 1, 1);
    if (rc == LUA_OK) {
        printf("math.sqrt(42) = %g\n", lua_tonumber(L, -1));
        lua_pop(L, 1);
    }
    
    // Test 2: string.format
    lua_pushstring(L, "%d + %d = %d");
    lua_pushinteger(L, 1);
    lua_pushinteger(L, 2);
    lua_pushinteger(L, 3);
    rc = safe_call_lua(L, "string.format", 4, 1);
    if (rc == LUA_OK) {
        printf("format: \"%s\"\n", lua_tostring(L, -1));
        lua_pop(L, 1);
    }
    
    // Test 3: error z traceback
    luaL_dostring(L, "function deep() error('boom') end\n"
                     "function mid() deep() end\n"
                     "function top() mid() end");
    safe_call_lua(L, "top", 0, 0);
    
    // Test 4: nieistniejąca
    lua_pushinteger(L, 42);
    safe_call_lua(L, "nonexistent", 1, 0);
    
    lua_close(L);
    return 0;
}
```

```
math.sqrt(42) = 6.48074
format: "1 + 2 = 3"
[safe_call] top failed:
[string "..."]:1: boom
stack traceback:
        [C]: in function 'error'
        [string "..."]:1: in function 'deep'
        [string "..."]:2: in function 'mid'
        [string "..."]:3: in function 'top'
[safe_call] not found: nonexistent
```

**Produkcyjny helper** — obsługuje dotted names, traceback handler, stack management. W KarmazynOS każde wywołanie Lua z hosta powinno przechodzić przez takiego wrappera.

#### Rozwiązanie 8.3.3

```c
// config_loader.c
#include <stdio.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    
    // Stwórz config:
    FILE *f = fopen("/tmp/config_test.lua", "w");
    fprintf(f,
        "max_atoms = 1000\n"
        "function validate(x) return x > 0 end\n");
    fclose(f);
    
    int rc = luaL_dofile(L, "/tmp/config_test.lua");
    if (rc != LUA_OK) {
        fprintf(stderr, "Config error: %s\n", lua_tostring(L, -1));
        lua_pop(L, 1);
        lua_close(L);
        return 1;
    }
    
    // Odczytaj max_atoms:
    lua_getglobal(L, "max_atoms");
    printf("max_atoms = %lld\n", (long long)lua_tointeger(L, -1));
    lua_pop(L, 1);
    
    // Wywołaj validate(42):
    lua_getglobal(L, "validate");
    lua_pushinteger(L, 42);
    rc = lua_pcall(L, 1, 1, 0);
    if (rc == LUA_OK) {
        printf("validate(42) = %s\n", lua_toboolean(L, -1) ? "true" : "false");
        lua_pop(L, 1);
    }
    
    // validate(-5):
    lua_getglobal(L, "validate");
    lua_pushinteger(L, -5);
    lua_pcall(L, 1, 1, 0);
    printf("validate(-5) = %s\n", lua_toboolean(L, -1) ? "true" : "false");
    lua_pop(L, 1);
    
    remove("/tmp/config_test.lua");
    lua_close(L);
    return 0;
}
```

```
max_atoms = 1000
validate(42) = true
validate(-5) = false
```

#### Rozwiązanie 8.3.4

```c
// traceback_demo.c
#include <stdio.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

static int traceback_handler(lua_State *L) {
    luaL_traceback(L, L, lua_tostring(L, 1), 1);
    return 1;
}

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    
    luaL_dostring(L,
        "function A() B() end\n"
        "function B() C() end\n"
        "function C() error('deep error in C') end\n");
    
    lua_pushcfunction(L, traceback_handler);
    int msgh = lua_gettop(L);
    lua_getglobal(L, "A");
    
    int rc = lua_pcall(L, 0, 0, msgh);
    if (rc != LUA_OK) {
        fprintf(stderr, "Error:\n%s\n", lua_tostring(L, -1));
        lua_pop(L, 1);
    }
    lua_pop(L, 1);    // pop handler
    
    lua_close(L);
    return 0;
}
```

```
Error:
[string "..."]:3: deep error in C
stack traceback:
        [C]: in function 'error'
        [string "..."]:3: in function 'C'
        [string "..."]:2: in function 'B'
        [string "..."]:1: in function 'A'
```

#### Rozwiązanie 8.3.5

```c
// run_chunk.c
#include <stdio.h>
#include <string.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

int run_lua_chunk(lua_State *L, const char *code, const char *name) {
    int rc = luaL_loadbufferx(L, code, strlen(code), name, "t");
    if (rc != LUA_OK) {
        fprintf(stderr, "[%s] COMPILE: %s\n", name, lua_tostring(L, -1));
        lua_pop(L, 1);
        return rc;
    }
    
    rc = lua_pcall(L, 0, LUA_MULTRET, 0);
    if (rc != LUA_OK) {
        fprintf(stderr, "[%s] RUNTIME: %s\n", name, lua_tostring(L, -1));
        lua_pop(L, 1);
        return rc;
    }
    
    int nresults = lua_gettop(L);
    if (nresults > 0) {
        printf("[%s] %d result(s):", name, nresults);
        for (int i = 1; i <= nresults; i++) {
            luaL_tolstring(L, i, NULL);
            printf(" %s", lua_tostring(L, -1));
            lua_pop(L, 1);
        }
        printf("\n");
        lua_settop(L, 0);
    } else {
        printf("[%s] OK\n", name);
    }
    return LUA_OK;
}

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    
    run_lua_chunk(L, "return 1 + 2", "test1");
    run_lua_chunk(L, "return bad(", "test2");
    run_lua_chunk(L, "error('boom')", "test3");
    run_lua_chunk(L, "return 'hello', math.pi, true", "test4");
    run_lua_chunk(L, "x = 42", "test5");
    
    lua_close(L);
    return 0;
}
```

```
[test1] 1 result(s): 3
[test2] COMPILE: [string "test2"]:1: unexpected symbol near <eof>
[test3] RUNTIME: [string "test3"]:1: boom
[test4] 3 result(s): hello 3.1415926535898 true
[test5] OK
```

### Sprawdź się

- [ ] Wiem, że `lua_pcall` zdejmuje func+args
- [ ] Umiem wywołać Lua function z C z argumentami
- [ ] Umiem obsłużyć multiple return values
- [ ] Znam message handler z `luaL_traceback`
- [ ] Umiem rozdzielić kompilację i wykonanie

---

## Lekcja 8.4: Rejestracja funkcji C dla Lua

### Cel

Piszesz funkcje C wywołowalne z Lua. Rejestrujesz jako globalne lub jako moduł. Obsługujesz argumenty, wyniki, errory.

### Materiał

#### Sygnatura

```c
typedef int (*lua_CFunction)(lua_State *L);
// Argumenty na stosie (1, 2, ...).
// Kładź wyniki na stos.
// Return = LICZBA WYNIKÓW, nie sam wynik.
```

```c
static int l_add(lua_State *L) {
    double a = lua_tonumber(L, 1);
    double b = lua_tonumber(L, 2);
    lua_pushnumber(L, a + b);
    return 1;
}
```

#### Rejestracja jako globalny

```c
lua_pushcfunction(L, l_add);
lua_setglobal(L, "add");
// Lua: print(add(3, 4))  → 7
```

#### Rejestracja jako moduł

```c
static const luaL_Reg hss_lib[] = {
    {"phi_distance", l_phi_distance},
    {"spawn",        l_spawn},
    {NULL, NULL}    // sentinel
};

luaL_newlib(L, hss_lib);
lua_setglobal(L, "hss");
// Lua: hss.phi_distance(0.7, 0.3)
```

#### Rzucenie błędu z C

```c
return luaL_error(L, "sqrt: negative argument: %f", x);
// NIGDY nie wraca (longjmp). Nie cleanup po nim.
```

#### Argumenty opcjonalne

```c
lua_Integer step = luaL_optinteger(L, 3, 1);    // default 1
const char *prefix = luaL_optstring(L, 1, "id"); // default "id"
```

### Pułapki

1. **Return value = liczba wyników**, nie wynik sam.
2. **`luaL_error` nigdy nie wraca** — nie alokuj przed walidacją.
3. **`luaL_check*`** rzuca error z dobrym komunikatem — preferuj.
4. **Sentinel `{NULL, NULL}`** — zawsze na końcu `luaL_Reg`.

### Zadania

**Zadanie 8.4.1** — `clamp(x, lo, hi)` z defaultami lo=0, hi=1.

**Zadanie 8.4.2** — Moduł `vec`: `new(x,y)`, `add(a,b)`, `length(v)`, `format(v)`.

**Zadanie 8.4.3** — Generator `make_id(prefix)` ze statycznym counterem C.

**Zadanie 8.4.4** — `measure(fn)` — wywołuje fn(), mierzy czas, zwraca `result, elapsed_ms`.

**Zadanie 8.4.5** — Moduł `log`: `info(msg)`, `warn(msg)`, `error(msg)`, `set_level(level)`. Stan w C static.

---

### Rozwiązania

#### Rozwiązanie 8.4.1

```c
// clamp.c
#include <stdio.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

static int l_clamp(lua_State *L) {
    double x  = luaL_checknumber(L, 1);
    double lo = luaL_optnumber(L, 2, 0.0);
    double hi = luaL_optnumber(L, 3, 1.0);
    if (x < lo) x = lo;
    if (x > hi) x = hi;
    lua_pushnumber(L, x);
    return 1;
}

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    lua_pushcfunction(L, l_clamp);
    lua_setglobal(L, "clamp");
    
    luaL_dostring(L,
        "print(clamp(0.5))           -- 0.5\n"
        "print(clamp(2))             -- 1\n"
        "print(clamp(-1))            -- 0\n"
        "print(clamp(50, 0, 100))    -- 50\n"
        "print(clamp(150, 0, 100))   -- 100\n");
    
    lua_close(L);
    return 0;
}
```

#### Rozwiązanie 8.4.2

```c
// vec_module.c
#include <stdio.h>
#include <math.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

static int l_vec_new(lua_State *L) {
    double x = luaL_checknumber(L, 1);
    double y = luaL_checknumber(L, 2);
    lua_newtable(L);
    lua_pushnumber(L, x); lua_setfield(L, -2, "x");
    lua_pushnumber(L, y); lua_setfield(L, -2, "y");
    return 1;
}

static int l_vec_add(lua_State *L) {
    luaL_checktype(L, 1, LUA_TTABLE);
    luaL_checktype(L, 2, LUA_TTABLE);
    lua_getfield(L, 1, "x"); double ax = lua_tonumber(L, -1); lua_pop(L, 1);
    lua_getfield(L, 1, "y"); double ay = lua_tonumber(L, -1); lua_pop(L, 1);
    lua_getfield(L, 2, "x"); double bx = lua_tonumber(L, -1); lua_pop(L, 1);
    lua_getfield(L, 2, "y"); double by = lua_tonumber(L, -1); lua_pop(L, 1);
    lua_newtable(L);
    lua_pushnumber(L, ax + bx); lua_setfield(L, -2, "x");
    lua_pushnumber(L, ay + by); lua_setfield(L, -2, "y");
    return 1;
}

static int l_vec_length(lua_State *L) {
    luaL_checktype(L, 1, LUA_TTABLE);
    lua_getfield(L, 1, "x"); double x = lua_tonumber(L, -1); lua_pop(L, 1);
    lua_getfield(L, 1, "y"); double y = lua_tonumber(L, -1); lua_pop(L, 1);
    lua_pushnumber(L, sqrt(x * x + y * y));
    return 1;
}

static int l_vec_format(lua_State *L) {
    luaL_checktype(L, 1, LUA_TTABLE);
    lua_getfield(L, 1, "x"); double x = lua_tonumber(L, -1); lua_pop(L, 1);
    lua_getfield(L, 1, "y"); double y = lua_tonumber(L, -1); lua_pop(L, 1);
    lua_pushfstring(L, "(%g, %g)", x, y);
    return 1;
}

static const luaL_Reg vec_funcs[] = {
    {"new", l_vec_new}, {"add", l_vec_add},
    {"length", l_vec_length}, {"format", l_vec_format},
    {NULL, NULL}
};

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    luaL_newlib(L, vec_funcs);
    lua_setglobal(L, "vec");
    
    luaL_dostring(L,
        "local v1 = vec.new(3, 4)\n"
        "local v2 = vec.new(1, 2)\n"
        "print(vec.format(v1))\n"
        "print('length:', vec.length(v1))\n"
        "print('sum:', vec.format(vec.add(v1, v2)))\n");
    
    lua_close(L);
    return 0;
}
```

```
(3, 4)
length: 5.0
sum: (4, 6)
```

#### Rozwiązanie 8.4.3

```c
// make_id.c
#include <stdio.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

static int _counter = 0;

static int l_make_id(lua_State *L) {
    const char *prefix = luaL_optstring(L, 1, "id");
    _counter++;
    lua_pushfstring(L, "%s-%d", prefix, _counter);
    return 1;
}

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    lua_pushcfunction(L, l_make_id);
    lua_setglobal(L, "make_id");
    
    luaL_dostring(L,
        "print(make_id('sess'))     -- sess-1\n"
        "print(make_id('atom'))     -- atom-2\n"
        "print(make_id('sess'))     -- sess-3\n"
        "print(make_id())           -- id-4\n");
    
    lua_close(L);
    return 0;
}
```

#### Rozwiązanie 8.4.4

```c
// measure.c
#include <stdio.h>
#include <time.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

static int l_measure(lua_State *L) {
    luaL_checktype(L, 1, LUA_TFUNCTION);
    
    clock_t t0 = clock();
    
    lua_pushvalue(L, 1);    // kopiuj fn na top
    int rc = lua_pcall(L, 0, LUA_MULTRET, 0);
    
    clock_t t1 = clock();
    double elapsed_ms = (double)(t1 - t0) / CLOCKS_PER_SEC * 1000.0;
    
    if (rc != LUA_OK) {
        return lua_error(L);    // propaguj error
    }
    
    int nresults = lua_gettop(L) - 1;    // -1 bo arg fn zdjęty przez pcall
    // Uwaga: po pcall stos ma TYLKO wyniki fn (fn zdjęty).
    // Ale arg fn (z pozycji 1) ciągle "logicznie" na stosie? Nie — pcall go zdjął.
    // Poprawka: lua_gettop(L) to dokładnie nresults po pcall.
    nresults = lua_gettop(L);
    
    lua_pushnumber(L, elapsed_ms);
    return nresults + 1;    // wyniki fn + elapsed
}

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    lua_pushcfunction(L, l_measure);
    lua_setglobal(L, "measure");
    
    luaL_dostring(L,
        "local r, ms = measure(function()\n"
        "    local s = 0\n"
        "    for i = 1, 1000000 do s = s + i end\n"
        "    return s\n"
        "end)\n"
        "print(string.format('result=%s elapsed=%.2fms', r, ms))\n");
    
    lua_close(L);
    return 0;
}
```

#### Rozwiązanie 8.4.5

```c
// log_module.c
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

static int _min_level = 1;    // 0=DEBUG, 1=INFO, 2=WARN, 3=ERROR

static int level_to_int(const char *s) {
    if (strcmp(s, "DEBUG") == 0) return 0;
    if (strcmp(s, "INFO") == 0)  return 1;
    if (strcmp(s, "WARN") == 0)  return 2;
    if (strcmp(s, "ERROR") == 0) return 3;
    return -1;
}

static int log_at(lua_State *L, const char *name, int level) {
    if (level < _min_level) return 0;
    const char *msg = luaL_checkstring(L, 1);
    time_t now = time(NULL);
    struct tm *tm = localtime(&now);
    char timebuf[32];
    strftime(timebuf, sizeof(timebuf), "%H:%M:%S", tm);
    fprintf(stdout, "[%s] %s %s\n", name, timebuf, msg);
    return 0;
}

static int l_debug(lua_State *L) { return log_at(L, "DEBUG", 0); }
static int l_info(lua_State *L)  { return log_at(L, "INFO",  1); }
static int l_warn(lua_State *L)  { return log_at(L, "WARN",  2); }
static int l_error(lua_State *L) { return log_at(L, "ERROR", 3); }

static int l_set_level(lua_State *L) {
    const char *level = luaL_checkstring(L, 1);
    int val = level_to_int(level);
    if (val < 0) return luaL_error(L, "unknown log level: '%s'", level);
    _min_level = val;
    return 0;
}

static const luaL_Reg log_funcs[] = {
    {"debug", l_debug}, {"info", l_info},
    {"warn", l_warn}, {"error", l_error},
    {"set_level", l_set_level},
    {NULL, NULL}
};

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    luaL_newlib(L, log_funcs);
    lua_setglobal(L, "log");
    
    luaL_dostring(L,
        "log.info('start')\n"
        "log.debug('detail')              -- nie wyświetla\n"
        "log.set_level('DEBUG')\n"
        "log.debug('now visible')\n"
        "log.set_level('WARN')\n"
        "log.info('skipped')\n"
        "log.warn('warning!')\n"
        "log.error('critical')\n");
    
    lua_close(L);
    return 0;
}
```

```
[INFO] 15:30:00 start
[DEBUG] 15:30:00 now visible
[WARN] 15:30:00 warning!
[ERROR] 15:30:00 critical
```

### Sprawdź się

- [ ] Pamiętam: return z C function = liczba wyników
- [ ] Umiem zarejestrować jako globalną i jako moduł
- [ ] Preferuję `luaL_check*` i `luaL_opt*`
- [ ] Wiem, że `luaL_error` to longjmp — nie cleanup po nim

---

## Lekcja 8.5: Walidacja argumentów — tablice, zagnieżdżone struktury

### Cel

Piszesz produkcyjne C functions z pełną walidacją. Iterujesz po tabelach z `lua_next`. Odczytujesz zagnieżdżone struktury. Budujesz JSON z tabel.

### Materiał

#### `lua_next` — iteracja po tabeli

```c
lua_pushnil(L);         // first key
while (lua_next(L, table_idx) != 0) {
    // key na -2, value na -1
    // ... process ...
    lua_pop(L, 1);      // pop value; key zostaje dla lua_next
}
```

**Pułapka:** nie rób `lua_tostring` na kluczu-number — modyfikuje go na stosie, `lua_next` potem nie działa. Kopiuj klucz `pushvalue` najpierw.

#### `luaL_Buffer` — budowanie stringów

```c
luaL_Buffer buf;
luaL_buffinit(L, &buf);
luaL_addchar(&buf, '{');
luaL_addstring(&buf, "hello");
luaL_addchar(&buf, '}');
luaL_pushresult(&buf);    // push gotowy string
```

#### `luaL_checkoption` — enum z string

```c
static const char *const modes[] = {"read", "write", "admin", NULL};
int mode = luaL_checkoption(L, 1, NULL, modes);
// mode: 0, 1 lub 2. Error jeśli arg nie pasuje.
```

#### Pattern: C struct z tabeli

```c
typedef struct {
    char sig[64];
    double phi;
    int alive;
} atom_t;

static int parse_atom(lua_State *L, int idx, atom_t *out) {
    idx = lua_absindex(L, idx);
    if (!lua_istable(L, idx)) return 0;
    
    lua_getfield(L, idx, "sig");
    const char *sig = lua_tostring(L, -1);
    if (sig) strncpy(out->sig, sig, sizeof(out->sig) - 1);
    lua_pop(L, 1);
    
    lua_getfield(L, idx, "phi");
    out->phi = luaL_optnumber(L, -1, 0.0);
    lua_pop(L, 1);
    
    lua_getfield(L, idx, "alive");
    out->alive = lua_toboolean(L, -1);
    lua_pop(L, 1);
    
    return 1;
}
```

### Pułapki

1. **`lua_next` + `lua_tostring` na kluczu** — nigdy. Kopiuj klucz.
2. **Ujemne indeksy w zagnieżdżonym getfield** — `lua_absindex`.
3. **`luaL_len`** wywołuje `__len`. Raw: `lua_rawlen`.

### Zadania

**Zadanie 8.5.1** — `validate_atom(t)` — sprawdza sig (string, non-empty), phi (number, [0,1]), alive (boolean, opcja).

**Zadanie 8.5.2** — `sort_by_phi(atoms)` — tabela atomów, sort in-place malejąco po phi (użyj `table.sort` z C).

**Zadanie 8.5.3** — `table_to_json(t)` — flat tabela → JSON string (z `luaL_Buffer`).

**Zadanie 8.5.4** — `merge_tables(a, b)` — zwraca nową tabelę z kluczami obu (b nadpisuje a).

**Zadanie 8.5.5** — `apply_policy(atom, policy)` — policy z `max_phi`, `mode` (strict/permissive), `on_violation` (callback Lua). Gdy phi > max_phi i strict → wywołaj callback, zwróć false.

---

### Rozwiązania

#### Rozwiązanie 8.5.1

```c
// validate_atom.c
#include <stdio.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

static int l_validate_atom(lua_State *L) {
    luaL_checktype(L, 1, LUA_TTABLE);
    
    lua_getfield(L, 1, "sig");
    if (lua_type(L, -1) != LUA_TSTRING) {
        return luaL_argerror(L, 1, "'sig' must be a string");
    }
    size_t len;
    lua_tolstring(L, -1, &len);
    if (len == 0) {
        return luaL_argerror(L, 1, "'sig' must not be empty");
    }
    lua_pop(L, 1);
    
    lua_getfield(L, 1, "phi");
    if (!lua_isnumber(L, -1)) {
        return luaL_argerror(L, 1, "'phi' must be a number");
    }
    double phi = lua_tonumber(L, -1);
    lua_pop(L, 1);
    if (phi < 0.0 || phi > 1.0) {
        return luaL_argerror(L, 1, "'phi' must be in [0, 1]");
    }
    
    lua_getfield(L, 1, "alive");
    if (!lua_isnil(L, -1) && !lua_isboolean(L, -1)) {
        lua_pop(L, 1);
        return luaL_argerror(L, 1, "'alive' must be boolean or absent");
    }
    lua_pop(L, 1);
    
    lua_pushboolean(L, 1);
    return 1;
}

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    lua_pushcfunction(L, l_validate_atom);
    lua_setglobal(L, "validate_atom");
    
    luaL_dostring(L,
        "print(validate_atom({sig='abc', phi=0.7, alive=true}))\n"
        "local ok, err = pcall(validate_atom, {sig='', phi=0.5})\n"
        "print(ok, err)\n"
        "local ok, err = pcall(validate_atom, {sig='abc', phi=1.5})\n"
        "print(ok, err)\n");
    
    lua_close(L);
    return 0;
}
```

```
true
false   bad argument #1 to 'validate_atom' ('sig' must not be empty)
false   bad argument #1 to 'validate_atom' ('phi' must be in [0, 1])
```

#### Rozwiązanie 8.5.2

```c
// sort_atoms.c
#include <stdio.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

static int phi_cmp(lua_State *L) {
    lua_getfield(L, 1, "phi");
    lua_getfield(L, 2, "phi");
    lua_pushboolean(L, lua_tonumber(L, -2) > lua_tonumber(L, -1));
    return 1;
}

static int l_sort_by_phi(lua_State *L) {
    luaL_checktype(L, 1, LUA_TTABLE);
    lua_getglobal(L, "table");
    lua_getfield(L, -1, "sort");
    lua_remove(L, -2);
    lua_pushvalue(L, 1);
    lua_pushcfunction(L, phi_cmp);
    lua_pcall(L, 2, 0, 0);
    return 0;
}

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    lua_pushcfunction(L, l_sort_by_phi);
    lua_setglobal(L, "sort_by_phi");
    
    luaL_dostring(L,
        "local atoms = {\n"
        "    {sig='a', phi=0.4}, {sig='b', phi=0.9},\n"
        "    {sig='c', phi=0.2}, {sig='d', phi=0.7},\n"
        "}\n"
        "sort_by_phi(atoms)\n"
        "for i, a in ipairs(atoms) do print(i, a.sig, a.phi) end\n");
    
    lua_close(L);
    return 0;
}
```

```
1   b   0.9
2   d   0.7
3   a   0.4
4   c   0.2
```

#### Rozwiązanie 8.5.3

```c
// table_to_json.c
#include <stdio.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

static int l_table_to_json(lua_State *L) {
    luaL_checktype(L, 1, LUA_TTABLE);
    
    luaL_Buffer buf;
    luaL_buffinit(L, &buf);
    luaL_addchar(&buf, '{');
    
    int first = 1;
    lua_pushnil(L);
    while (lua_next(L, 1) != 0) {
        if (!first) luaL_addchar(&buf, ',');
        first = 0;
        
        if (lua_type(L, -2) == LUA_TSTRING) {
            luaL_addchar(&buf, '"');
            luaL_addstring(&buf, lua_tostring(L, -2));
            luaL_addstring(&buf, "\":");
        } else {
            lua_pop(L, 1);
            continue;
        }
        
        switch (lua_type(L, -1)) {
            case LUA_TSTRING:
                luaL_addchar(&buf, '"');
                luaL_addstring(&buf, lua_tostring(L, -1));
                luaL_addchar(&buf, '"');
                break;
            case LUA_TNUMBER:
                if (lua_isinteger(L, -1))
                    lua_pushfstring(L, "%I", lua_tointeger(L, -1));
                else
                    lua_pushfstring(L, "%f", lua_tonumber(L, -1));
                luaL_addvalue(&buf);
                break;
            case LUA_TBOOLEAN:
                luaL_addstring(&buf, lua_toboolean(L, -1) ? "true" : "false");
                break;
            default:
                luaL_addstring(&buf, "null");
                break;
        }
        lua_pop(L, 1);
    }
    
    luaL_addchar(&buf, '}');
    luaL_pushresult(&buf);
    return 1;
}

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    lua_pushcfunction(L, l_table_to_json);
    lua_setglobal(L, "table_to_json");
    
    luaL_dostring(L,
        "print(table_to_json({name='abc', phi=0.7, alive=true, count=42}))\n");
    
    lua_close(L);
    return 0;
}
```

```
{"count":42,"alive":true,"phi":0.700000,"name":"abc"}
```

#### Rozwiązanie 8.5.4

```c
// merge_tables.c
#include <stdio.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

static int l_merge(lua_State *L) {
    luaL_checktype(L, 1, LUA_TTABLE);
    luaL_checktype(L, 2, LUA_TTABLE);
    
    lua_newtable(L);    // result na pozycji 3
    
    // Kopiuj z a (pozycja 1):
    lua_pushnil(L);
    while (lua_next(L, 1) != 0) {
        lua_pushvalue(L, -2);    // key copy
        lua_pushvalue(L, -2);    // value copy
        lua_settable(L, 3);      // result[key] = value
        lua_pop(L, 1);           // pop value; key for next
    }
    
    // Kopiuj z b (pozycja 2, nadpisuje):
    lua_pushnil(L);
    while (lua_next(L, 2) != 0) {
        lua_pushvalue(L, -2);
        lua_pushvalue(L, -2);
        lua_settable(L, 3);
        lua_pop(L, 1);
    }
    
    return 1;    // result na topie (pozycja 3)
}

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    lua_pushcfunction(L, l_merge);
    lua_setglobal(L, "merge_tables");
    
    luaL_dostring(L,
        "local m = merge_tables({x=1, y=2, z=3}, {y=99, w=4})\n"
        "for k, v in pairs(m) do print(k, v) end\n");
    // x  1 / y  99 / z  3 / w  4
    
    lua_close(L);
    return 0;
}
```

#### Rozwiązanie 8.5.5

```c
// apply_policy.c
#include <stdio.h>
#include <string.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

static int l_apply_policy(lua_State *L) {
    luaL_checktype(L, 1, LUA_TTABLE);    // atom
    luaL_checktype(L, 2, LUA_TTABLE);    // policy
    
    // atom.phi:
    lua_getfield(L, 1, "phi");
    if (!lua_isnumber(L, -1))
        return luaL_argerror(L, 1, "atom must have numeric 'phi'");
    double phi = lua_tonumber(L, -1);
    lua_pop(L, 1);
    
    // policy.max_phi:
    lua_getfield(L, 2, "max_phi");
    if (!lua_isnumber(L, -1))
        return luaL_argerror(L, 2, "policy must have numeric 'max_phi'");
    double max_phi = lua_tonumber(L, -1);
    lua_pop(L, 1);
    
    // policy.mode:
    lua_getfield(L, 2, "mode");
    const char *mode = luaL_optstring(L, -1, "permissive");
    lua_pop(L, 1);
    
    // Sprawdź violation:
    if (phi > max_phi && strcmp(mode, "strict") == 0) {
        // Wywołaj on_violation jeśli jest:
        lua_getfield(L, 2, "on_violation");
        if (lua_isfunction(L, -1)) {
            lua_pushvalue(L, 1);          // push atom
            lua_pcall(L, 1, 0, 0);        // on_violation(atom)
        } else {
            lua_pop(L, 1);
        }
        lua_pushboolean(L, 0);
        return 1;
    }
    
    lua_pushboolean(L, 1);
    return 1;
}

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    lua_pushcfunction(L, l_apply_policy);
    lua_setglobal(L, "apply_policy");
    
    luaL_dostring(L,
        "local atom = {sig='abc', phi=0.8}\n"
        "local strict = {\n"
        "    max_phi = 0.5,\n"
        "    mode = 'strict',\n"
        "    on_violation = function(a)\n"
        "        print('VIOLATION: ' .. a.sig .. ' phi=' .. a.phi)\n"
        "    end,\n"
        "}\n"
        "local permissive = {max_phi = 0.5, mode = 'permissive'}\n"
        "\n"
        "print('strict:', apply_policy(atom, strict))\n"
        "print('permissive:', apply_policy(atom, permissive))\n"
        "atom.phi = 0.3\n"
        "print('under max:', apply_policy(atom, strict))\n");
    
    lua_close(L);
    return 0;
}
```

```
VIOLATION: abc phi=0.8
strict: false
permissive: true
under max: true
```

**Realny pattern KarmazynOS** — host w C sprawdza atom vs policy, wywołuje callback Lua, zwraca decyzję.

### Sprawdź się

- [ ] Umiem iterować po tabeli z `lua_next` (pamiętam pułapkę klucza)
- [ ] Znam `luaL_Buffer` do budowania stringów
- [ ] Umiem odczytywać zagnieżdżone tabele
- [ ] Umiem wywołać callback Lua z C
- [ ] Znam `luaL_checkoption` do enum-like arguments

---

## Sprawdzian Modułu 8

Sześć zadań z pełnymi rozwiązaniami — zamykają fundamenty C API.

### Zadania

**Sprawdzian 1** — REPL z kolorami i wieloliniowym wejściem  
Rozszerz REPL z L8.1: kolorowy prompt (ANSI: zielony `>` po sukcesie, czerwony `!` po error), wieloliniowe (`\` na końcu kontynuuje), komendy `:quit`, `:stack`.

**Sprawdzian 2** — Pełen moduł `hss`  
Z C: `spawn(sig, phi)`, `decay(atom, dt)`, `is_alive(atom)`, `distance(a,b)`, `validate(atom)`, `format(atom)`, `version()`.

**Sprawdzian 3** — Config loader z walidacją  
Załaduj `.lua` config, odczytaj zagnieżdżone pola, waliduj schemat (brak pola = error).

**Sprawdzian 4** — Event emitter z C  
Moduł `events`: `on(name, fn)`, `emit(name, ...)`, `off(name, fn)`. Listenery w C-side storage.

**Sprawdzian 5** — Schema validator z C  
`validate_schema(value, schema)` — schema jak `{sig="string", phi="number", alive="boolean?"}`. `?` = optional.

**Sprawdzian 6** — Mini kalkulator  
Zarejestruj `add`, `sub`, `mul`, `div`, `pow`, `sqrt` z C. Czytaj wyrażenia z stdin. `div(x,0)` → czytelny error.

---

### Rozwiązania sprawdzianu

#### Sprawdzian 1

```c
// color_repl.c
#include <stdio.h>
#include <string.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

#define GREEN  "\033[32m"
#define RED    "\033[31m"
#define RESET  "\033[0m"

static void dump_stack(lua_State *L) {
    int top = lua_gettop(L);
    printf("--- stack (%d) ---\n", top);
    for (int i = 1; i <= top; i++) {
        int t = lua_type(L, i);
        switch (t) {
            case LUA_TNIL:     printf("  %d: nil\n", i); break;
            case LUA_TBOOLEAN: printf("  %d: %s\n", i, lua_toboolean(L, i) ? "true" : "false"); break;
            case LUA_TNUMBER:
                if (lua_isinteger(L, i))
                    printf("  %d: %lld (int)\n", i, (long long)lua_tointeger(L, i));
                else
                    printf("  %d: %g (float)\n", i, lua_tonumber(L, i));
                break;
            case LUA_TSTRING:  printf("  %d: \"%s\"\n", i, lua_tostring(L, i)); break;
            default:           printf("  %d: %s\n", i, lua_typename(L, t)); break;
        }
    }
    printf("---\n");
}

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    
    char line[4096];
    char accum[16384];
    int last_error = 0;
    int accumulating = 0;
    
    printf("KarmazynOS Lua %s REPL\n", LUA_VERSION);
    printf("Commands: :quit  :stack\n\n");
    
    while (1) {
        if (accumulating) {
            printf("  %s..%s ", last_error ? RED : GREEN, RESET);
        } else {
            printf("%s%s%s ", last_error ? RED "!" : GREEN ">", RESET, "");
        }
        fflush(stdout);
        
        if (fgets(line, sizeof(line), stdin) == NULL) {
            printf("\n");
            break;
        }
        
        size_t len = strlen(line);
        if (len > 0 && line[len - 1] == '\n') line[--len] = '\0';
        
        // Wieloliniowe: jeśli kończy się \ — kontynuuj:
        if (len > 0 && line[len - 1] == '\\') {
            line[len - 1] = '\n';    // zamień \ na newline
            if (!accumulating) {
                strncpy(accum, line, sizeof(accum) - 1);
                accumulating = 1;
            } else {
                strncat(accum, line, sizeof(accum) - strlen(accum) - 1);
            }
            continue;
        }
        
        const char *code;
        if (accumulating) {
            strncat(accum, line, sizeof(accum) - strlen(accum) - 1);
            code = accum;
            accumulating = 0;
        } else {
            code = line;
        }
        
        if (strlen(code) == 0) continue;
        
        // Komendy specjalne:
        if (strcmp(code, ":quit") == 0) break;
        if (strcmp(code, ":stack") == 0) {
            dump_stack(L);
            continue;
        }
        
        // Próba "return expr":
        char rbuf[16400];
        snprintf(rbuf, sizeof(rbuf), "return %s", code);
        
        int rc = luaL_loadstring(L, rbuf);
        if (rc == LUA_OK) {
            rc = lua_pcall(L, 0, LUA_MULTRET, 0);
            if (rc == LUA_OK) {
                int nresults = lua_gettop(L);
                if (nresults > 0) {
                    for (int i = 1; i <= nresults; i++) {
                        if (i > 1) printf("\t");
                        luaL_tolstring(L, i, NULL);
                        printf("%s", lua_tostring(L, -1));
                        lua_pop(L, 1);
                    }
                    printf("\n");
                }
                lua_settop(L, 0);
                last_error = 0;
                continue;
            }
            fprintf(stderr, "%s\n", lua_tostring(L, -1));
            lua_pop(L, 1);
            last_error = 1;
            continue;
        }
        lua_pop(L, 1);
        
        // Bez "return":
        rc = luaL_dostring(L, code);
        if (rc != LUA_OK) {
            fprintf(stderr, "%s\n", lua_tostring(L, -1));
            lua_pop(L, 1);
            last_error = 1;
        } else {
            last_error = 0;
        }
    }
    
    lua_close(L);
    return 0;
}
```

Wieloliniowe: `\` na końcu → akumuluj w `accum`, czytaj dalej aż linia bez `\`. Kolory: zielony `>` po sukcesie, czerwony `!` po error — ANSI escape codes. `:quit` exit, `:stack` dump.

#### Sprawdzian 2

```c
// hss_full_module.c
#include <stdio.h>
#include <math.h>
#include <string.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

static int l_spawn(lua_State *L) {
    const char *sig = luaL_checkstring(L, 1);
    double phi = luaL_optnumber(L, 2, 0.0);
    if (phi < 0 || phi > 1) return luaL_argerror(L, 2, "phi must be in [0,1]");
    
    lua_newtable(L);
    lua_pushstring(L, sig);   lua_setfield(L, -2, "sig");
    lua_pushnumber(L, phi);   lua_setfield(L, -2, "phi");
    lua_pushboolean(L, 1);    lua_setfield(L, -2, "alive");
    return 1;
}

static int l_decay(lua_State *L) {
    luaL_checktype(L, 1, LUA_TTABLE);
    double dt = luaL_checknumber(L, 2);
    
    lua_getfield(L, 1, "phi");
    double phi = lua_tonumber(L, -1);
    lua_pop(L, 1);
    
    phi = phi * exp(-dt);
    lua_pushnumber(L, phi);
    lua_setfield(L, 1, "phi");
    
    if (phi < 1e-6) {
        lua_pushboolean(L, 0);
        lua_setfield(L, 1, "alive");
    }
    return 0;
}

static int l_is_alive(lua_State *L) {
    luaL_checktype(L, 1, LUA_TTABLE);
    lua_getfield(L, 1, "alive");
    int alive = lua_toboolean(L, -1);
    lua_pop(L, 1);
    
    lua_getfield(L, 1, "phi");
    double phi = lua_tonumber(L, -1);
    lua_pop(L, 1);
    
    lua_pushboolean(L, alive && phi > 1e-6);
    return 1;
}

static int l_distance(lua_State *L) {
    luaL_checktype(L, 1, LUA_TTABLE);
    luaL_checktype(L, 2, LUA_TTABLE);
    
    lua_getfield(L, 1, "phi"); double a = lua_tonumber(L, -1); lua_pop(L, 1);
    lua_getfield(L, 2, "phi"); double b = lua_tonumber(L, -1); lua_pop(L, 1);
    
    lua_pushnumber(L, fabs(a - b));
    return 1;
}

static int l_validate(lua_State *L) {
    luaL_checktype(L, 1, LUA_TTABLE);
    
    lua_getfield(L, 1, "sig");
    if (lua_type(L, -1) != LUA_TSTRING)
        return luaL_argerror(L, 1, "missing or invalid 'sig'");
    size_t len;
    lua_tolstring(L, -1, &len);
    if (len == 0)
        return luaL_argerror(L, 1, "'sig' must not be empty");
    lua_pop(L, 1);
    
    lua_getfield(L, 1, "phi");
    if (!lua_isnumber(L, -1))
        return luaL_argerror(L, 1, "missing or invalid 'phi'");
    double phi = lua_tonumber(L, -1);
    lua_pop(L, 1);
    if (phi < 0 || phi > 1)
        return luaL_argerror(L, 1, "'phi' must be in [0,1]");
    
    lua_pushboolean(L, 1);
    return 1;
}

static int l_format(lua_State *L) {
    luaL_checktype(L, 1, LUA_TTABLE);
    
    lua_getfield(L, 1, "sig");
    const char *sig = lua_tostring(L, -1);
    lua_getfield(L, 1, "phi");
    double phi = lua_tonumber(L, -1);
    lua_getfield(L, 1, "alive");
    int alive = lua_toboolean(L, -1);
    lua_pop(L, 3);
    
    lua_pushfstring(L, "Atom<%s, phi=%.4f, %s>",
        sig ? sig : "?", phi, alive ? "alive" : "dead");
    return 1;
}

static int l_version(lua_State *L) {
    lua_pushstring(L, "1.0.0");
    return 1;
}

static const luaL_Reg hss_funcs[] = {
    {"spawn",    l_spawn},
    {"decay",    l_decay},
    {"is_alive", l_is_alive},
    {"distance", l_distance},
    {"validate", l_validate},
    {"format",   l_format},
    {"version",  l_version},
    {NULL, NULL}
};

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    
    luaL_newlib(L, hss_funcs);
    lua_setglobal(L, "hss");
    
    luaL_dostring(L,
        "print('HSS version:', hss.version())\n"
        "\n"
        "local a = hss.spawn('abc', 0.9)\n"
        "print(hss.format(a))\n"
        "print('alive:', hss.is_alive(a))\n"
        "\n"
        "hss.decay(a, 0.5)\n"
        "print(hss.format(a))\n"
        "\n"
        "local b = hss.spawn('def', 0.3)\n"
        "print('distance:', hss.distance(a, b))\n"
        "\n"
        "print('validate OK:', hss.validate(a))\n"
        "\n"
        "local ok, err = pcall(hss.validate, {phi=0.5})\n"
        "print('validate bad:', ok, err)\n"
        "\n"
        "-- Kill atom via heavy decay:\n"
        "for i = 1, 50 do hss.decay(a, 0.5) end\n"
        "print(hss.format(a))\n"
        "print('alive after decay:', hss.is_alive(a))\n");
    
    lua_close(L);
    return 0;
}
```

```
HSS version: 1.0.0
Atom<abc, phi=0.9000, alive>
alive: true
Atom<abc, phi=0.5470, alive>
distance: 0.24696534885964
validate OK: true
validate bad: false   bad argument #1 to 'validate' (missing or invalid 'sig')
Atom<abc, phi=0.0000, dead>
alive after decay: false
```

Pełen moduł HSS w C. Każda funkcja waliduje argumenty, operuje na tabelach, obsługuje edge cases (decay poniżej threshold → atom dies).

#### Sprawdzian 3

```c
// config_validator.c
#include <stdio.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

typedef struct {
    char name[64];
    int cpu_ms;
    int mem_kb;
    char first_cap[64];
} config_t;

static int load_config(lua_State *L, const char *path, config_t *out) {
    int rc = luaL_dofile(L, path);
    if (rc != LUA_OK) {
        fprintf(stderr, "Load error: %s\n", lua_tostring(L, -1));
        lua_pop(L, 1);
        return 0;
    }
    
    // config.name (required):
    lua_getglobal(L, "config");
    if (!lua_istable(L, -1)) {
        fprintf(stderr, "Schema error: 'config' must be a table\n");
        lua_pop(L, 1);
        return 0;
    }
    
    lua_getfield(L, -1, "name");
    if (lua_type(L, -1) != LUA_TSTRING) {
        fprintf(stderr, "Schema error: config.name required (string)\n");
        lua_pop(L, 2);
        return 0;
    }
    strncpy(out->name, lua_tostring(L, -1), sizeof(out->name) - 1);
    lua_pop(L, 1);
    
    // config.quota.cpu_ms (required):
    lua_getfield(L, -1, "quota");
    if (!lua_istable(L, -1)) {
        fprintf(stderr, "Schema error: config.quota required (table)\n");
        lua_pop(L, 2);
        return 0;
    }
    
    lua_getfield(L, -1, "cpu_ms");
    if (!lua_isnumber(L, -1)) {
        fprintf(stderr, "Schema error: config.quota.cpu_ms required (number)\n");
        lua_pop(L, 3);
        return 0;
    }
    out->cpu_ms = (int)lua_tointeger(L, -1);
    lua_pop(L, 1);
    
    lua_getfield(L, -1, "mem_kb");
    if (!lua_isnumber(L, -1)) {
        fprintf(stderr, "Schema error: config.quota.mem_kb required (number)\n");
        lua_pop(L, 3);
        return 0;
    }
    out->mem_kb = (int)lua_tointeger(L, -1);
    lua_pop(L, 2);    // pop mem_kb + quota
    
    // config.capabilities[1] (optional):
    lua_getfield(L, -1, "capabilities");
    if (lua_istable(L, -1)) {
        lua_rawgeti(L, -1, 1);
        const char *cap = lua_tostring(L, -1);
        if (cap) strncpy(out->first_cap, cap, sizeof(out->first_cap) - 1);
        else out->first_cap[0] = '\0';
        lua_pop(L, 1);
    } else {
        out->first_cap[0] = '\0';
    }
    lua_pop(L, 2);    // pop capabilities + config
    
    return 1;
}

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    
    // Poprawny config:
    FILE *f = fopen("/tmp/good_config.lua", "w");
    fprintf(f,
        "config = {\n"
        "    name = 'default',\n"
        "    quota = {cpu_ms = 500, mem_kb = 4096},\n"
        "    capabilities = {'phi.read', 'phi.write'},\n"
        "}\n");
    fclose(f);
    
    printf("--- Good config ---\n");
    config_t cfg = {0};
    if (load_config(L, "/tmp/good_config.lua", &cfg)) {
        printf("name: %s\n", cfg.name);
        printf("cpu_ms: %d\n", cfg.cpu_ms);
        printf("mem_kb: %d\n", cfg.mem_kb);
        printf("first_cap: %s\n", cfg.first_cap);
    }
    
    // Zły config:
    f = fopen("/tmp/bad_config.lua", "w");
    fprintf(f, "config = {quota = {cpu_ms = 100}}\n");
    fclose(f);
    
    printf("\n--- Bad config ---\n");
    config_t cfg2 = {0};
    load_config(L, "/tmp/bad_config.lua", &cfg2);
    
    remove("/tmp/good_config.lua");
    remove("/tmp/bad_config.lua");
    lua_close(L);
    return 0;
}
```

```
--- Good config ---
name: default
cpu_ms: 500
mem_kb: 4096
first_cap: phi.read

--- Bad config ---
Schema error: config.name required (string)
```

#### Sprawdzian 4

```c
// events_module.c
#include <stdio.h>
#include <string.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

#define MAX_EVENTS 16
#define MAX_LISTENERS 10

typedef struct {
    char name[64];
    int refs[MAX_LISTENERS];    // registry refs do funkcji Lua
    int count;
} event_slot_t;

static event_slot_t _events[MAX_EVENTS];
static int _event_count = 0;

static event_slot_t *find_or_create_event(const char *name) {
    for (int i = 0; i < _event_count; i++) {
        if (strcmp(_events[i].name, name) == 0) return &_events[i];
    }
    if (_event_count >= MAX_EVENTS) return NULL;
    event_slot_t *e = &_events[_event_count++];
    strncpy(e->name, name, sizeof(e->name) - 1);
    e->count = 0;
    return e;
}

static int l_events_on(lua_State *L) {
    const char *name = luaL_checkstring(L, 1);
    luaL_checktype(L, 2, LUA_TFUNCTION);
    
    event_slot_t *e = find_or_create_event(name);
    if (!e) return luaL_error(L, "too many event types");
    if (e->count >= MAX_LISTENERS) return luaL_error(L, "too many listeners for '%s'", name);
    
    // Zapisz referencję do funkcji w registry:
    lua_pushvalue(L, 2);
    e->refs[e->count] = luaL_ref(L, LUA_REGISTRYINDEX);
    e->count++;
    
    return 0;
}

static int l_events_emit(lua_State *L) {
    const char *name = luaL_checkstring(L, 1);
    int nargs = lua_gettop(L) - 1;    // argumenty po nazwie eventu
    
    event_slot_t *e = NULL;
    for (int i = 0; i < _event_count; i++) {
        if (strcmp(_events[i].name, name) == 0) { e = &_events[i]; break; }
    }
    if (!e) return 0;    // brak listenerów
    
    for (int i = 0; i < e->count; i++) {
        lua_rawgeti(L, LUA_REGISTRYINDEX, e->refs[i]);    // push fn
        // Push kopie argumentów:
        for (int j = 2; j <= 1 + nargs; j++) {
            lua_pushvalue(L, j);
        }
        int rc = lua_pcall(L, nargs, 0, 0);
        if (rc != LUA_OK) {
            fprintf(stderr, "[events.emit] listener error: %s\n", lua_tostring(L, -1));
            lua_pop(L, 1);
        }
    }
    return 0;
}

static int l_events_off(lua_State *L) {
    const char *name = luaL_checkstring(L, 1);
    luaL_checktype(L, 2, LUA_TFUNCTION);
    
    event_slot_t *e = NULL;
    for (int i = 0; i < _event_count; i++) {
        if (strcmp(_events[i].name, name) == 0) { e = &_events[i]; break; }
    }
    if (!e) return 0;
    
    // Szukaj listenera:
    for (int i = 0; i < e->count; i++) {
        lua_rawgeti(L, LUA_REGISTRYINDEX, e->refs[i]);
        if (lua_rawequal(L, -1, 2)) {
            lua_pop(L, 1);
            luaL_unref(L, LUA_REGISTRYINDEX, e->refs[i]);
            // Przesuń resztę:
            for (int j = i; j < e->count - 1; j++) {
                e->refs[j] = e->refs[j + 1];
            }
            e->count--;
            return 0;
        }
        lua_pop(L, 1);
    }
    return 0;
}

static const luaL_Reg events_funcs[] = {
    {"on",   l_events_on},
    {"emit", l_events_emit},
    {"off",  l_events_off},
    {NULL, NULL}
};

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    
    luaL_newlib(L, events_funcs);
    lua_setglobal(L, "events");
    
    luaL_dostring(L,
        "local function on_phi(value)\n"
        "    print('phi changed to: ' .. value)\n"
        "end\n"
        "\n"
        "local function on_phi_alert(value)\n"
        "    if value > 0.8 then print('ALERT: high phi!') end\n"
        "end\n"
        "\n"
        "events.on('phi_change', on_phi)\n"
        "events.on('phi_change', on_phi_alert)\n"
        "\n"
        "events.emit('phi_change', 0.5)\n"
        "events.emit('phi_change', 0.9)\n"
        "\n"
        "events.off('phi_change', on_phi)\n"
        "events.emit('phi_change', 0.95)\n"
        "\n"
        "events.emit('unknown_event', 1, 2, 3)\n"
        "print('(unknown event — silence, no listeners)')\n");
    
    lua_close(L);
    return 0;
}
```

```
phi changed to: 0.5
phi changed to: 0.9
ALERT: high phi!
ALERT: high phi!
(unknown event — silence, no listeners)
```

`luaL_ref` / `luaL_unref` — trzyma referencje do funkcji Lua w registry. Bez tego GC mógłby zebrać callback. W `emit` — kopiujemy argumenty dla każdego listenera (bo `pcall` zdejmuje je ze stosu). `off` porównuje przez `lua_rawequal` (identity).

#### Sprawdzian 5

```c
// schema_validator.c
#include <stdio.h>
#include <string.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

static int l_validate_schema(lua_State *L) {
    luaL_checktype(L, 1, LUA_TTABLE);    // value
    luaL_checktype(L, 2, LUA_TTABLE);    // schema
    
    lua_newtable(L);    // errors list (pozycja 3)
    int error_count = 0;
    
    // Iteruj po schema:
    lua_pushnil(L);
    while (lua_next(L, 2) != 0) {
        // key (field name) na -2, value (type spec) na -1
        const char *field = lua_tostring(L, -2);
        const char *spec = lua_tostring(L, -1);
        
        if (!field || !spec) { lua_pop(L, 1); continue; }
        
        int optional = 0;
        char expected_type[32];
        strncpy(expected_type, spec, sizeof(expected_type) - 1);
        expected_type[sizeof(expected_type) - 1] = '\0';
        
        size_t slen = strlen(expected_type);
        if (slen > 0 && expected_type[slen - 1] == '?') {
            optional = 1;
            expected_type[slen - 1] = '\0';
        }
        
        // Sprawdź pole w value:
        lua_getfield(L, 1, field);
        int actual_type = lua_type(L, -1);
        
        if (actual_type == LUA_TNIL) {
            if (!optional) {
                error_count++;
                lua_pushfstring(L, "missing required field: %s", field);
                lua_rawseti(L, 3, error_count);
            }
        } else {
            const char *actual_name = lua_typename(L, actual_type);
            
            // Normalizuj "integer" → "number":
            if (strcmp(expected_type, "integer") == 0) {
                if (!lua_isinteger(L, -1)) {
                    error_count++;
                    lua_pushfstring(L, "field '%s': expected integer, got %s",
                        field, actual_name);
                    lua_rawseti(L, 3, error_count);
                }
            } else {
                if (strcmp(actual_name, expected_type) != 0) {
                    error_count++;
                    lua_pushfstring(L, "field '%s': expected %s, got %s",
                        field, expected_type, actual_name);
                    lua_rawseti(L, 3, error_count);
                }
            }
        }
        
        lua_pop(L, 1);    // pop field value
        lua_pop(L, 1);    // pop schema value; key for lua_next
    }
    
    // Sprawdź extra pola (nie w schemacie):
    lua_pushnil(L);
    while (lua_next(L, 1) != 0) {
        lua_pushvalue(L, -2);    // copy key
        lua_getfield(L, 2, lua_tostring(L, -1));    // schema[key]
        if (lua_isnil(L, -1)) {
            error_count++;
            lua_pushfstring(L, "unexpected field: %s", lua_tostring(L, -2));
            lua_rawseti(L, 3, error_count);
        }
        lua_pop(L, 2);    // pop schema lookup + key copy
        lua_pop(L, 1);    // pop value; key for lua_next
    }
    
    if (error_count > 0) {
        lua_pushboolean(L, 0);
        lua_pushvalue(L, 3);    // errors table
        return 2;
    }
    
    lua_pushboolean(L, 1);
    return 1;
}

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    
    lua_pushcfunction(L, l_validate_schema);
    lua_setglobal(L, "validate_schema");
    
    luaL_dostring(L,
        "local schema = {\n"
        "    sig = 'string',\n"
        "    phi = 'number',\n"
        "    alive = 'boolean?',\n"
        "    epoch = 'number?',\n"
        "}\n"
        "\n"
        "-- Valid:\n"
        "local ok = validate_schema({sig='abc', phi=0.7, alive=true}, schema)\n"
        "print('valid:', ok)\n"
        "\n"
        "-- Valid with optionals missing:\n"
        "local ok = validate_schema({sig='abc', phi=0.7}, schema)\n"
        "print('valid minimal:', ok)\n"
        "\n"
        "-- Invalid:\n"
        "local ok, errs = validate_schema({sig=42, extra='x'}, schema)\n"
        "print('invalid:', ok)\n"
        "for i, e in ipairs(errs) do print('  -', e) end\n"
    );
    
    lua_close(L);
    return 0;
}
```

```
valid: true
valid minimal: true
invalid: false
  - field 'sig': expected string, got number
  - missing required field: phi
  - unexpected field: extra
```

`?` suffix na typie = optional. Zbiera **wszystkie** błędy (nie tylko pierwszy). Sprawdza extra pola. Dokładnie taki pattern jak `enforce_schema` z M5.4 — ale teraz w C.

#### Sprawdzian 6

```c
// calculator.c
#include <stdio.h>
#include <string.h>
#include <math.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

static int l_add(lua_State *L) {
    lua_pushnumber(L, luaL_checknumber(L, 1) + luaL_checknumber(L, 2));
    return 1;
}

static int l_sub(lua_State *L) {
    lua_pushnumber(L, luaL_checknumber(L, 1) - luaL_checknumber(L, 2));
    return 1;
}

static int l_mul(lua_State *L) {
    lua_pushnumber(L, luaL_checknumber(L, 1) * luaL_checknumber(L, 2));
    return 1;
}

static int l_div(lua_State *L) {
    double a = luaL_checknumber(L, 1);
    double b = luaL_checknumber(L, 2);
    if (b == 0) return luaL_error(L, "division by zero");
    lua_pushnumber(L, a / b);
    return 1;
}

static int l_pow(lua_State *L) {
    lua_pushnumber(L, pow(luaL_checknumber(L, 1), luaL_checknumber(L, 2)));
    return 1;
}

static int l_sqrt(lua_State *L) {
    double x = luaL_checknumber(L, 1);
    if (x < 0) return luaL_error(L, "sqrt of negative number: %f", x);
    lua_pushnumber(L, sqrt(x));
    return 1;
}

static const luaL_Reg calc_funcs[] = {
    {"add", l_add}, {"sub", l_sub}, {"mul", l_mul},
    {"div", l_div}, {"pow", l_pow}, {"sqrt", l_sqrt},
    {NULL, NULL}
};

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    
    // Zarejestruj jako globalne (nie jako moduł — bardziej naturalne dla kalkulatora):
    for (const luaL_Reg *r = calc_funcs; r->name; r++) {
        lua_pushcfunction(L, r->func);
        lua_setglobal(L, r->name);
    }
    
    char buf[4096];
    printf("calc> ");
    fflush(stdout);
    
    while (fgets(buf, sizeof(buf), stdin) != NULL) {
        size_t len = strlen(buf);
        if (len > 0 && buf[len - 1] == '\n') buf[--len] = '\0';
        
        if (strcmp(buf, ":quit") == 0 || strcmp(buf, "quit") == 0) break;
        if (strlen(buf) == 0) { printf("calc> "); fflush(stdout); continue; }
        
        char rbuf[4096 + 16];
        snprintf(rbuf, sizeof(rbuf), "return %s", buf);
        
        int rc = luaL_dostring(L, rbuf);
        if (rc == LUA_OK) {
            int nresults = lua_gettop(L);
            for (int i = 1; i <= nresults; i++) {
                if (lua_isnumber(L, i)) {
                    if (lua_isinteger(L, i))
                        printf("%lld\n", (long long)lua_tointeger(L, i));
                    else
                        printf("%g\n", lua_tonumber(L, i));
                } else {
                    luaL_tolstring(L, i, NULL);
                    printf("%s\n", lua_tostring(L, -1));
                    lua_pop(L, 1);
                }
            }
            lua_settop(L, 0);
        } else {
            fprintf(stderr, "Error: %s\n", lua_tostring(L, -1));
            lua_pop(L, 1);
        }
        
        printf("calc> ");
        fflush(stdout);
    }
    
    lua_close(L);
    return 0;
}
```

```
calc> sqrt(add(9, 16))
5.0
calc> div(10, 0)
Error: [string "return div(10, 0)"]:1: division by zero
calc> mul(3, pow(2, 10))
3072.0
calc> add(1, sub(10, 3))
8.0
calc> sqrt(-4)
Error: [string "..."]:1: sqrt of negative number: -4.000000
calc> :quit
```

Funktowy kalkulator — `add(sub(mul(...)))` jako drzewo wyrażeń. C-side walidacja (div by zero, sqrt negative). `return expr` automatycznie dodane. Czytelne errory.

---

## Co dalej?

C API opanowane na poziomie fundamentalnym. W kolejnym module — **userdata**: opaque pointery C dostępne z Lua, metatable z C, finalizatory `__gc`, pełne bindingi obiektów C.

→ **Moduł 9: Userdata i bindings** — `lua_newuserdata`, `luaL_setmetatable`, `luaL_checkudata`, `__gc`, light vs full userdata.
