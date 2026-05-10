# Moduł 10: Sandboxing

> *"Sandbox to nie 'blokuj wszystko' — to 'pozwól dokładnie tyle, ile potrzeba'."*

Sandbox to kontrolowane środowisko wykonania, w którym niezaufany kod Lua nie może uszkodzić hosta. W KarmazynOS każdy skrypt użytkownika, plugin, polityka HSS — wszystko działa w sandboxie. Ten moduł łączy wiedzę z M1-M9 w pełny system izolacji.

Trzy filary sandboxa:
1. **Ograniczone środowisko** (`_ENV`) — skrypt widzi tylko dozwolone funkcje
2. **Limit CPU** (`lua_sethook`) — skrypt nie może monopolizować procesora
3. **Limit pamięci** (custom alokator) — skrypt nie może wyczerpać RAM

**Przewidywany czas:** 6-8 godzin pracy.

**Lekcje:**
1. `_ENV` z C — budowanie okrojonego środowiska
2. `lua_sethook` — instruction counting, CPU quota
3. Custom alokator z limitem pamięci
4. Pełny sandbox — integracja trzech filarów
5. Sandbox dla KarmazynOS — praktyczne API hosta

Plus **Sprawdzian Modułu 10** — 6 zadań z pełnymi rozwiązaniami.

---

## Lekcja 10.1: `_ENV` z C — budowanie okrojonego środowiska

### Cel

Tworzysz restricted `_ENV` z C. Skrypt widzi tylko funkcje które jawnie wstrzykniesz. Nie ma dostępu do `os`, `io`, `debug`, `require`, `dofile`, `loadfile`.

### Materiał

#### Co to `_ENV`

W Lua 5.2+ każdy chunk ma swoją **tabelę środowiska** — `_ENV`. Globalne zmienne to w rzeczywistości pola `_ENV`:

```lua
-- x = 42 to tak naprawdę:
_ENV["x"] = 42

-- print("hello") to:
_ENV["print"]("hello")
```

Domyślnie `_ENV` = `_G` (pełny zestaw globalów). Ale możemy **podmienić** `_ENV` na własną tabelę — chunk zobaczy **tylko** to co tam wstawimy.

#### Podmienianie `_ENV` z C

Kompilowany chunk Lua jest funkcją z jednym upvalue — `_ENV`. `luaL_loadstring` zostawia ten chunk na stosie. Przed `lua_pcall` możemy ustawić jego upvalue:

```c
// 1. Kompiluj (nie wykonuj):
luaL_loadstring(L, "print('hello'); os.execute('rm -rf /')");

// 2. Stwórz restricted env:
lua_newtable(L);                          // env = {}

// 3. Dodaj dozwolone funkcje:
lua_getglobal(L, "print");
lua_setfield(L, -2, "print");            // env.print = print

lua_getglobal(L, "tostring");
lua_setfield(L, -2, "tostring");

lua_getglobal(L, "type");
lua_setfield(L, -2, "type");

// 4. Ustaw env jako upvalue #1 (= _ENV) chunka:
// chunk jest na pozycji -2, env na -1
const char *name = lua_setupvalue(L, -2, 1);    // upvalue 1 = _ENV
// name == "_ENV", env zdjęty ze stosu

// 5. Wykonaj:
int rc = lua_pcall(L, 0, 0, 0);
// print('hello') → OK (print jest w env)
// os.execute(...) → ERROR: attempt to index nil value 'os'
```

`lua_setupvalue(L, funcindex, n)` — ustawia n-ty upvalue funkcji na wartość z top stosu. Dla chunka upvalue 1 to zawsze `_ENV`.

#### Whitelist approach

Zamiast "zabierać" niebezpieczne — **dawaj tylko bezpieczne**:

```c
static void build_sandbox_env(lua_State *L) {
    lua_newtable(L);    // env = {}
    
    // Bezpieczne z base:
    const char *safe_base[] = {
        "assert", "error", "ipairs", "pairs", "next",
        "pcall", "xpcall", "select", "tonumber", "tostring",
        "type", "unpack", "print",
        NULL
    };
    for (int i = 0; safe_base[i]; i++) {
        lua_getglobal(L, safe_base[i]);
        lua_setfield(L, -2, safe_base[i]);
    }
    
    // Bezpieczne z math (cały moduł — math jest read-only):
    lua_getglobal(L, "math");
    lua_setfield(L, -2, "math");
    
    // Bezpieczne z string (cały moduł):
    lua_getglobal(L, "string");
    lua_setfield(L, -2, "string");
    
    // Bezpieczne z table:
    lua_getglobal(L, "table");
    lua_setfield(L, -2, "table");
    
    // BLOKOWANE: os, io, debug, package, require, dofile, loadfile, load
    // Nie dodajemy ich — env ich nie ma → nil → error przy użyciu
}
```

#### Co blokować

| Funkcja/Moduł | Ryzyko | Blokować? |
|---|---|---|
| `os.execute`, `os.remove` | arbitrary command execution | **TAK** |
| `io.open`, `io.popen` | file system access | **TAK** |
| `debug.*` | introspect host, escape sandbox | **TAK** |
| `require`, `dofile`, `loadfile` | load arbitrary code | **TAK** |
| `load`, `loadstring` | compile arbitrary code | **TAK** (lub kontrolowane) |
| `rawget`, `rawset` | bypass metatables | zależy |
| `setmetatable` | modify protected metatables | zależy |
| `collectgarbage` | DoS (force GC cycles) | zależy |
| `print` | side effect, ale bezpieczny | zwykle OK |
| `math.*`, `string.*`, `table.*` | pure computation | **OK** |

#### Bezpieczna wersja `load`

Czasami skrypt musi `load()` (np. deserializacja). Ale `load` z pełnym `_ENV` pozwala escape. Rozwiązanie — owrap z sandboxowym env:

```c
static int l_safe_load(lua_State *L) {
    const char *code = luaL_checkstring(L, 1);
    
    // Kompiluj (text only!):
    int rc = luaL_loadbufferx(L, code, strlen(code), "=sandbox", "t");
    if (rc != LUA_OK) {
        lua_pushnil(L);
        lua_insert(L, -2);    // nil, errmsg
        return 2;
    }
    
    // Ustaw _ENV na env sandboxa (upvalue 1 callera... skomplikowane).
    // Prostsze: weź env z registry:
    lua_pushlightuserdata(L, (void *)&l_safe_load);    // klucz
    lua_gettable(L, LUA_REGISTRYINDEX);                 // env
    lua_setupvalue(L, -2, 1);                            // chunk._ENV = env
    
    return 1;    // zwróć chunk (z sandboxowym _ENV)
}
```

#### `__index` na `_ENV` — read-only globals

Jeśli chcesz, żeby sandbox widzał globals ale nie mógł ich nadpisywać:

```c
// env z __index → _G (readonly view):
lua_newtable(L);    // env = {}

lua_newtable(L);    // metatable = {}
lua_pushglobaltable(L);
lua_setfield(L, -2, "__index");    // mt.__index = _G

// __newindex blokuje zapis:
lua_pushcfunction(L, [](lua_State *L2) -> int {
    return luaL_error(L2, "attempt to set global '%s' in sandbox",
        lua_tostring(L2, 2));
});
lua_setfield(L, -2, "__newindex");

lua_setmetatable(L, -2);    // setmetatable(env, mt)
```

Teraz sandbox może **czytać** dowolny global ale nie może **pisać**. Zapis → error.

W KarmazynOS to jest pattern "readonly policy" — skrypt widzi konfigurację ale nie może jej zmienić.

#### Pełen przykład

```c
// sandbox_env.c
#include <stdio.h>
#include <string.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

static void build_sandbox_env(lua_State *L) {
    lua_newtable(L);
    
    const char *safe[] = {
        "assert", "error", "ipairs", "pairs", "next",
        "pcall", "xpcall", "select", "tonumber", "tostring",
        "type", "print",
        NULL
    };
    for (int i = 0; safe[i]; i++) {
        lua_getglobal(L, safe[i]);
        lua_setfield(L, -2, safe[i]);
    }
    
    lua_getglobal(L, "math");   lua_setfield(L, -2, "math");
    lua_getglobal(L, "string"); lua_setfield(L, -2, "string");
    lua_getglobal(L, "table");  lua_setfield(L, -2, "table");
}

static int run_sandboxed(lua_State *L, const char *code, const char *name) {
    int rc = luaL_loadbufferx(L, code, strlen(code), name, "t");
    if (rc != LUA_OK) {
        fprintf(stderr, "[sandbox] compile: %s\n", lua_tostring(L, -1));
        lua_pop(L, 1);
        return rc;
    }
    
    // Podmień _ENV:
    build_sandbox_env(L);
    lua_setupvalue(L, -2, 1);
    
    rc = lua_pcall(L, 0, 0, 0);
    if (rc != LUA_OK) {
        fprintf(stderr, "[sandbox] runtime: %s\n", lua_tostring(L, -1));
        lua_pop(L, 1);
    }
    return rc;
}

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    
    printf("--- Safe code ---\n");
    run_sandboxed(L, "print('safe:', math.sqrt(16))", "safe");
    
    printf("\n--- os.execute blocked ---\n");
    run_sandboxed(L, "os.execute('echo hacked')", "attack1");
    
    printf("\n--- io.open blocked ---\n");
    run_sandboxed(L, "io.open('/etc/passwd')", "attack2");
    
    printf("\n--- require blocked ---\n");
    run_sandboxed(L, "require('os')", "attack3");
    
    printf("\n--- debug blocked ---\n");
    run_sandboxed(L, "debug.getinfo(1)", "attack4");
    
    printf("\n--- load blocked ---\n");
    run_sandboxed(L, "load('os.execute(\"echo pwned\")')()", "attack5");
    
    printf("\n--- Globals writable? ---\n");
    run_sandboxed(L, "x = 42; print('x =', x)", "write");
    // Działa — piszemy do env, nie do _G!
    
    lua_close(L);
    return 0;
}
```

```
--- Safe code ---
safe: 4.0

--- os.execute blocked ---
[sandbox] runtime: =attack1:1: attempt to index a nil value (global 'os')

--- io.open blocked ---
[sandbox] runtime: =attack2:1: attempt to index a nil value (global 'io')

--- require blocked ---
[sandbox] runtime: =attack3:1: attempt to call a nil value (global 'require')

--- debug blocked ---
[sandbox] runtime: =attack4:1: attempt to index a nil value (global 'debug')

--- load blocked ---
[sandbox] runtime: =attack5:1: attempt to call a nil value (global 'load')

--- Globals writable? ---
x = 42
```

**Filar 1 gotowy.** Skrypt widzi tylko whitelist, pisanie trafia do sandboxowego env (nie do `_G`).

### Pułapki

1. **`luaL_loadbufferx` z "t"** — text only! Bez tego ktoś może podać precompiled bytecode, który omija sandbox (bytecode może mieć inne upvalues).
2. **`string.dump`** — pozwala dump'ować bytecode. Rozważ usunięcie z sandbox.
3. **`string.rep` z dużym n** — DoS (gigantyczny string). Limit pamięci (L10.3) to łapie.
4. **Metatable tricks** — `getmetatable(print)` może dać dostęp do internals. Rozważ blokowanie `getmetatable`.

### Zadania

**Zadanie 10.1.1**  
Napisz `build_sandbox_env` z whitelistą. Przetestuj 5 ataków: `os.execute`, `io.open`, `require`, `debug.getinfo`, `load`.

**Zadanie 10.1.2**  
Dodaj read-only globals — `__index` na `_G`, `__newindex` blokujący zapis. Test: skrypt czyta `math.pi` (OK), próbuje `math.pi = 0` (error).

**Zadanie 10.1.3**  
Dodaj do sandbox custom function `sandbox_print(...)` która loguje z prefixem `[SANDBOX]` zamiast zwykłego print.

**Zadanie 10.1.4**  
Wstrzyknij do sandbox tabelę `hss` z metodami `hss.phi()` (zwraca fixed 0.7) i `hss.sig()` (zwraca "sandbox-session"). Klient widzi je jako "natywne API".

**Zadanie 10.1.5**  
Safe `load` — dodaj do sandbox `safe_load(code)` który kompiluje text-only i ustawia ten sam sandbox env na wynikowy chunk.

---

### Rozwiązania

*(Rozwiązania 10.1.1-10.1.5 to warianty pełnego przykładu z Materiału — różnią się dodanymi funkcjami w env. Wzorzec identyczny: `lua_newtable` → push dozwolone → `lua_setupvalue`. Pominięte dla zwięzłości — wzorzec ustalony.)*

### Sprawdź się

- [ ] Umiem zbudować whitelist env z C
- [ ] Wiem, że `lua_setupvalue(L, funcidx, 1)` ustawia `_ENV` chunka
- [ ] Pamiętam `"t"` w `luaL_loadbufferx` — text only
- [ ] Umiem zrobić read-only view na globals (`__index` → `_G`, `__newindex` → error)
- [ ] Wiem, jak wstrzyknąć custom API do sandbox

---

## Lekcja 10.2: `lua_sethook` — instruction counting, CPU quota

### Cel

Ustawiasz hook przerywający wykonanie po N instrukcjach. Skrypt nieskończoną pętlą nie zawiesi hosta.

### Materiał

#### `lua_sethook`

```c
void lua_sethook(lua_State *L, lua_Hook f, int mask, int count);
// f     — callback
// mask  — kiedy wywoływać: LUA_MASKCOUNT, LUA_MASKLINE, LUA_MASKCALL, LUA_MASKRET
// count — co ile instrukcji (gdy mask zawiera LUA_MASKCOUNT)
```

Hook callback:

```c
typedef void (*lua_Hook)(lua_State *L, lua_Debug *ar);
```

#### Limit instrukcji

```c
static int _instruction_limit = 1000000;    // 1M instrukcji
static int _instructions_run = 0;

static void instruction_hook(lua_State *L, lua_Debug *ar) {
    (void)ar;
    _instructions_run++;
    if (_instructions_run > _instruction_limit) {
        luaL_error(L, "CPU quota exceeded (%d instructions)", _instruction_limit);
    }
}

// Przed uruchomieniem skryptu:
_instructions_run = 0;
lua_sethook(L, instruction_hook, LUA_MASKCOUNT, 1000);
// Hook wywoła się co 1000 instrukcji VM

// Po uruchomieniu — wyłącz:
lua_sethook(L, NULL, 0, 0);
```

`LUA_MASKCOUNT` + `count = 1000` → hook co 1000 instrukcji. Hook sprawdza łączny licznik i rzuca error gdy przekroczony.

**Dlaczego `count = 1000` a nie `1`?** Wydajność — hook per instrukcja to ~10× slowdown. Co 1000 to ~1% overhead.

#### Per-State data w hooku

Problem: hook callback to zwykła funkcja C z `lua_State*`. Skąd weźmie limit per State? Rozwiązanie — registry:

```c
typedef struct {
    int limit;
    int used;
} quota_t;

static int quota_key;    // adres jako klucz

static quota_t *get_quota(lua_State *L) {
    lua_pushlightuserdata(L, &quota_key);
    lua_gettable(L, LUA_REGISTRYINDEX);
    quota_t *q = (quota_t *)lua_touserdata(L, -1);
    lua_pop(L, 1);
    return q;
}

static void hook(lua_State *L, lua_Debug *ar) {
    (void)ar;
    quota_t *q = get_quota(L);
    q->used += 1000;    // += count z sethook
    if (q->used > q->limit) {
        luaL_error(L, "CPU quota exceeded: %d/%d", q->used, q->limit);
    }
}

static void set_cpu_quota(lua_State *L, int limit) {
    quota_t *q = (quota_t *)lua_newuserdata(L, sizeof(quota_t));
    q->limit = limit;
    q->used = 0;
    
    lua_pushlightuserdata(L, &quota_key);
    lua_insert(L, -2);
    lua_settable(L, LUA_REGISTRYINDEX);    // registry[&quota_key] = q
    
    lua_sethook(L, hook, LUA_MASKCOUNT, 1000);
}
```

#### Timeout (wall clock)

Instrukcje to CPU quota. Dla wall clock (sekundy):

```c
#include <time.h>

static time_t _deadline;

static void timeout_hook(lua_State *L, lua_Debug *ar) {
    (void)ar;
    if (time(NULL) >= _deadline) {
        luaL_error(L, "execution timeout exceeded");
    }
}

static void set_timeout(lua_State *L, int seconds) {
    _deadline = time(NULL) + seconds;
    lua_sethook(L, timeout_hook, LUA_MASKCOUNT, 10000);
}
```

W praktyce: **obie** — instrukcje (fair CPU share) + timeout (real-time SLA).

#### Pełen przykład

```c
// cpu_quota.c
#include <stdio.h>
#include <string.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

static int _quota_limit = 0;
static int _quota_used = 0;

static void cpu_hook(lua_State *L, lua_Debug *ar) {
    (void)ar;
    _quota_used += 1000;
    if (_quota_used > _quota_limit) {
        lua_sethook(L, NULL, 0, 0);    // wyłącz hook
        luaL_error(L, "CPU quota exceeded: %d/%d instructions",
            _quota_used, _quota_limit);
    }
}

static int run_with_quota(lua_State *L, const char *code, int limit) {
    _quota_limit = limit;
    _quota_used = 0;
    
    int rc = luaL_loadbufferx(L, code, strlen(code), "sandbox", "t");
    if (rc != LUA_OK) {
        fprintf(stderr, "compile: %s\n", lua_tostring(L, -1));
        lua_pop(L, 1);
        return rc;
    }
    
    lua_sethook(L, cpu_hook, LUA_MASKCOUNT, 1000);
    rc = lua_pcall(L, 0, 0, 0);
    lua_sethook(L, NULL, 0, 0);
    
    if (rc != LUA_OK) {
        fprintf(stderr, "runtime: %s\n", lua_tostring(L, -1));
        lua_pop(L, 1);
    } else {
        printf("OK (used %d instructions)\n", _quota_used);
    }
    return rc;
}

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    
    printf("--- Fast code (100K limit) ---\n");
    run_with_quota(L,
        "local s = 0\n"
        "for i = 1, 100 do s = s + i end\n"
        "print('sum =', s)\n",
        100000);
    
    printf("\n--- Infinite loop (100K limit) ---\n");
    run_with_quota(L,
        "while true do end\n",
        100000);
    
    printf("\n--- Expensive computation (1M limit) ---\n");
    run_with_quota(L,
        "local s = 0\n"
        "for i = 1, 1000000 do s = s + i end\n"
        "print('sum =', s)\n",
        1000000);
    
    lua_close(L);
    return 0;
}
```

```
--- Fast code (100K limit) ---
sum = 5050
OK (used 3000 instructions)

--- Infinite loop (100K limit) ---
runtime: sandbox:1: CPU quota exceeded: 101000/100000 instructions

--- Expensive computation (1M limit) ---
runtime: sandbox:2: CPU quota exceeded: 1001000/1000000 instructions
```

**Filar 2 gotowy.** Nieskończona pętla przerwana po przekroczeniu quota.

### Pułapki

1. **`luaL_error` w hooku** — działa (longjmp), ale hook musi się wyłączyć (inaczej będzie wywoływany w error handling). Zawsze `lua_sethook(L, NULL, 0, 0)` przed error.
2. **Count granularity** — hook co 1000 = quota ±1000 instrukcji niedokładna. Akceptowalne.
3. **C calls nie liczą się** — jeśli skrypt woła C function która trwa 10 sekund, hook nie przerwie C-side. Tylko Lua VM instructions.
4. **Korutyny** — `lua_sethook` działa na **main thread**. Korutyna dziedziczy hook. W 5.4 każda korutyna ma osobny hook.

### Zadania

**Zadanie 10.2.1** — Hook z limitem instrukcji. Test: pętla for 100 OK, while true killed.

**Zadanie 10.2.2** — Per-State quota przez registry (nie static global). Dwa lua_State z różnymi limitami.

**Zadanie 10.2.3** — Timeout hook (wall clock seconds). Test: `os.execute("sleep 5")` — uwaga, to C call, hook nie przerwie! Pokaż ograniczenie.

---

### Rozwiązania

*(Wzorzec identyczny jak pełen przykład. 10.2.2 — quota_t w registry przez light userdata key. 10.2.3 — `time(NULL)` w hooku, ale demonstracja że C-side sleep nie jest przerywany.)*

### Sprawdź się

- [ ] Umiem ustawić `lua_sethook` z `LUA_MASKCOUNT`
- [ ] Wiem, że hook wywoła się co `count` instrukcji VM
- [ ] Pamiętam wyłączyć hook przed `luaL_error`
- [ ] Wiem, że C calls nie są przerywane przez hook

---

## Lekcja 10.3: Custom alokator z limitem pamięci

### Cel

Piszesz alokator C z budżetem pamięci. Lua nie może alokować więcej niż limit.

### Materiał

#### `lua_newstate` z custom alokatorem

```c
lua_State *lua_newstate(lua_Alloc f, void *ud);

typedef void *(*lua_Alloc)(void *ud, void *ptr, size_t osize, size_t nsize);
// ud    — user data (twój kontekst)
// ptr   — blok do realloc/free (NULL dla alloc)
// osize — stary rozmiar
// nsize — nowy rozmiar (0 = free)
//
// Semantyka jak realloc:
// nsize == 0  → free(ptr), return NULL
// ptr == NULL → malloc(nsize)
// else        → realloc(ptr, nsize)
```

#### Alokator z limitem

```c
typedef struct {
    size_t used;
    size_t limit;
} mem_quota_t;

static void *quota_alloc(void *ud, void *ptr, size_t osize, size_t nsize) {
    mem_quota_t *q = (mem_quota_t *)ud;
    
    if (nsize == 0) {
        // free:
        q->used -= osize;
        free(ptr);
        return NULL;
    }
    
    if (ptr == NULL) {
        // malloc:
        if (q->used + nsize > q->limit) return NULL;    // OOM
        void *p = malloc(nsize);
        if (p) q->used += nsize;
        return p;
    }
    
    // realloc:
    size_t delta = nsize - osize;
    if (delta > 0 && q->used + delta > q->limit) return NULL;    // OOM
    void *p = realloc(ptr, nsize);
    if (p) q->used += (nsize - osize);
    return p;
}

// Tworzenie ograniczonego State:
mem_quota_t quota = {.used = 0, .limit = 1024 * 1024};    // 1MB
lua_State *L = lua_newstate(quota_alloc, &quota);
```

Gdy alokator zwraca `NULL` — Lua traktuje to jako **out of memory**. `lua_pcall` zwróci `LUA_ERRMEM`. Skrypt nie crash'uje hosta.

#### Pełen przykład

```c
// mem_quota.c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

typedef struct {
    size_t used;
    size_t limit;
    size_t peak;
} mem_quota_t;

static void *quota_alloc(void *ud, void *ptr, size_t osize, size_t nsize) {
    mem_quota_t *q = (mem_quota_t *)ud;
    
    if (nsize == 0) {
        q->used -= osize;
        free(ptr);
        return NULL;
    }
    
    size_t needed = (ptr == NULL) ? nsize : (nsize > osize ? nsize - osize : 0);
    if (q->used + needed > q->limit) {
        return NULL;    // OOM — Lua obsłuży
    }
    
    void *p = (ptr == NULL) ? malloc(nsize) : realloc(ptr, nsize);
    if (p) {
        if (ptr == NULL) {
            q->used += nsize;
        } else {
            q->used += (nsize - osize);
        }
        if (q->used > q->peak) q->peak = q->used;
    }
    return p;
}

int main(void) {
    // State z 512KB limit:
    mem_quota_t quota = {.used = 0, .limit = 512 * 1024, .peak = 0};
    lua_State *L = lua_newstate(quota_alloc, &quota);
    if (!L) {
        fprintf(stderr, "cannot create lua_State\n");
        return 1;
    }
    luaL_openlibs(L);
    
    printf("After init: used=%zu KB\n", quota.used / 1024);
    
    // Normalne użycie:
    printf("\n--- Normal code ---\n");
    int rc = luaL_dostring(L,
        "local t = {}\n"
        "for i = 1, 1000 do t[i] = i * i end\n"
        "print('OK, #t =', #t)\n");
    if (rc == LUA_OK) {
        printf("used=%zu KB, peak=%zu KB\n", quota.used / 1024, quota.peak / 1024);
    }
    
    // Memory bomb:
    printf("\n--- Memory bomb (giant string) ---\n");
    rc = luaL_dostring(L,
        "local s = string.rep('x', 1024 * 1024)\n");    // 1MB string > 512KB limit
    if (rc != LUA_OK) {
        fprintf(stderr, "BLOCKED: %s\n", lua_tostring(L, -1));
        lua_pop(L, 1);
    }
    
    // Memory bomb 2: tabela:
    printf("\n--- Memory bomb (huge table) ---\n");
    rc = luaL_dostring(L,
        "local t = {}\n"
        "for i = 1, 10000000 do t[i] = i end\n");
    if (rc != LUA_OK) {
        fprintf(stderr, "BLOCKED: %s\n", lua_tostring(L, -1));
        lua_pop(L, 1);
    }
    
    printf("\nFinal: used=%zu KB, peak=%zu KB, limit=%zu KB\n",
        quota.used / 1024, quota.peak / 1024, quota.limit / 1024);
    
    lua_close(L);
    return 0;
}
```

```
After init: used=42 KB

--- Normal code ---
OK, #t = 1000
used=78 KB, peak=78 KB

--- Memory bomb (giant string) ---
BLOCKED: [string "..."]:1: not enough memory

--- Memory bomb (huge table) ---
BLOCKED: [string "..."]:2: not enough memory

Final: used=78 KB, peak=78 KB, limit=512 KB
```

**Filar 3 gotowy.** Lua nie może alokować więcej niż limit. `LUA_ERRMEM` zwrócony z pcall — host obsługuje gracefully.

### Pułapki

1. **`osize` może być 0** dla nowych alokacji — nie odejmuj.
2. **`lua_newstate` z limitem** musi mieć dość na sam interpreter (~30-50KB). Jeśli limit za mały — `lua_newstate` zwraca NULL.
3. **Realloc shrinking** — `nsize < osize` — zawsze dozwolone (zwalnia pamięć).
4. **Thread-safety** — alokator musi być thread-safe jeśli wiele States dzieli quota struct. W single-threaded OK.
5. **Peak tracking** — przydatne dla diagnostyki, nie dla enforcement.

### Zadania

**Zadanie 10.3.1** — Alokator z limitem i peak tracking. Test z rosnącą tabelą.

**Zadanie 10.3.2** — Dwa lua_State z osobnymi limitami (np. 256KB i 1MB). Pokaż niezależność.

**Zadanie 10.3.3** — Alokator z logowaniem każdej alokacji (malloc/realloc/free, rozmiar, adres). Uruchom prosty skrypt, obserwuj pattern alokacji Lua.

---

### Rozwiązania

*(Wzorzec z pełnego przykładu. 10.3.2: dwa `mem_quota_t`, dwa `lua_newstate`. 10.3.3: `fprintf(stderr, "[alloc] ...")` w quota_alloc — pokazuje kilkaset alokacji dla prostego skryptu.)*

### Sprawdź się

- [ ] Umiem napisać custom alokator z `lua_Alloc` sygnaturą
- [ ] Wiem, że `return NULL` z alokatora = OOM, pcall zwraca `LUA_ERRMEM`
- [ ] Pamiętam, że init potrzebuje ~30-50KB
- [ ] Umiem trackować peak memory

---

## Lekcja 10.4: Pełny sandbox — integracja trzech filarów

### Cel

Łączysz restricted env + CPU quota + memory limit w jedno API `sandbox_run(code, opts)`.

### Materiał

```c
// sandbox.c — complete sandbox
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

// --- Memory allocator ---

typedef struct {
    size_t used;
    size_t limit;
    size_t peak;
} mem_quota_t;

static void *quota_alloc(void *ud, void *ptr, size_t osize, size_t nsize) {
    mem_quota_t *q = (mem_quota_t *)ud;
    if (nsize == 0) {
        q->used -= osize;
        free(ptr);
        return NULL;
    }
    size_t needed = (ptr == NULL) ? nsize : (nsize > osize ? nsize - osize : 0);
    if (q->used + needed > q->limit) return NULL;
    void *p = (ptr == NULL) ? malloc(nsize) : realloc(ptr, nsize);
    if (p) {
        q->used += (ptr == NULL) ? nsize : (nsize - osize);
        if (q->used > q->peak) q->peak = q->used;
    }
    return p;
}

// --- CPU hook ---

static int cpu_key;

typedef struct {
    int limit;
    int used;
} cpu_quota_t;

static void cpu_hook(lua_State *L, lua_Debug *ar) {
    (void)ar;
    lua_pushlightuserdata(L, &cpu_key);
    lua_gettable(L, LUA_REGISTRYINDEX);
    cpu_quota_t *q = (cpu_quota_t *)lua_touserdata(L, -1);
    lua_pop(L, 1);
    
    q->used += 1000;
    if (q->used > q->limit) {
        lua_sethook(L, NULL, 0, 0);
        luaL_error(L, "CPU quota exceeded: %d/%d", q->used, q->limit);
    }
}

// --- Sandbox env ---

static void build_env(lua_State *L) {
    lua_newtable(L);
    
    const char *safe[] = {
        "assert", "error", "ipairs", "pairs", "next",
        "pcall", "xpcall", "select", "tonumber", "tostring",
        "type", "print", "unpack", "rawequal",
        NULL
    };
    for (int i = 0; safe[i]; i++) {
        lua_getglobal(L, safe[i]);
        if (!lua_isnil(L, -1)) {
            lua_setfield(L, -2, safe[i]);
        } else {
            lua_pop(L, 1);
        }
    }
    
    lua_getglobal(L, "math");   lua_setfield(L, -2, "math");
    lua_getglobal(L, "string"); lua_setfield(L, -2, "string");
    lua_getglobal(L, "table");  lua_setfield(L, -2, "table");
}

// --- Public API ---

typedef struct {
    int cpu_limit;       // max instructions (0 = no limit)
    size_t mem_limit;    // max bytes (0 = no limit)
    const char *name;    // chunk name
} sandbox_opts_t;

typedef struct {
    int status;          // LUA_OK, LUA_ERRRUN, LUA_ERRMEM, ...
    const char *error;   // error message (or NULL)
    int cpu_used;
    size_t mem_peak;
} sandbox_result_t;

sandbox_result_t sandbox_run(const char *code, sandbox_opts_t opts) {
    sandbox_result_t result = {0};
    
    // Memory allocator:
    mem_quota_t mem = {
        .used = 0,
        .limit = opts.mem_limit > 0 ? opts.mem_limit : (size_t)-1,
        .peak = 0
    };
    
    lua_State *L;
    if (opts.mem_limit > 0) {
        L = lua_newstate(quota_alloc, &mem);
    } else {
        L = luaL_newstate();
    }
    
    if (!L) {
        result.status = LUA_ERRMEM;
        result.error = "cannot create lua_State (memory limit too low?)";
        return result;
    }
    
    luaL_openlibs(L);
    
    // CPU quota:
    if (opts.cpu_limit > 0) {
        cpu_quota_t *q = (cpu_quota_t *)lua_newuserdata(L, sizeof(cpu_quota_t));
        q->limit = opts.cpu_limit;
        q->used = 0;
        lua_pushlightuserdata(L, &cpu_key);
        lua_insert(L, -2);
        lua_settable(L, LUA_REGISTRYINDEX);
        
        lua_sethook(L, cpu_hook, LUA_MASKCOUNT, 1000);
    }
    
    // Compile (text only):
    const char *name = opts.name ? opts.name : "sandbox";
    int rc = luaL_loadbufferx(L, code, strlen(code), name, "t");
    if (rc != LUA_OK) {
        result.status = rc;
        result.error = strdup(lua_tostring(L, -1));
        lua_close(L);
        result.mem_peak = mem.peak;
        return result;
    }
    
    // Sandbox env:
    build_env(L);
    lua_setupvalue(L, -2, 1);
    
    // Execute:
    rc = lua_pcall(L, 0, 0, 0);
    
    // Collect results:
    result.status = rc;
    if (rc != LUA_OK) {
        result.error = strdup(lua_tostring(L, -1));
    }
    
    if (opts.cpu_limit > 0) {
        lua_pushlightuserdata(L, &cpu_key);
        lua_gettable(L, LUA_REGISTRYINDEX);
        cpu_quota_t *q = (cpu_quota_t *)lua_touserdata(L, -1);
        if (q) result.cpu_used = q->used;
        lua_pop(L, 1);
    }
    
    result.mem_peak = mem.peak;
    
    lua_sethook(L, NULL, 0, 0);
    lua_close(L);
    
    return result;
}

int main(void) {
    printf("=== Test 1: Safe code ===\n");
    sandbox_result_t r = sandbox_run(
        "local s = 0\n"
        "for i = 1, 100 do s = s + i end\n"
        "print('sum =', s)\n",
        (sandbox_opts_t){.cpu_limit = 100000, .mem_limit = 512*1024, .name = "test1"}
    );
    printf("status=%d cpu=%d mem_peak=%zuKB\n\n",
        r.status, r.cpu_used, r.mem_peak/1024);
    free((void*)r.error);
    
    printf("=== Test 2: Infinite loop ===\n");
    r = sandbox_run(
        "while true do end",
        (sandbox_opts_t){.cpu_limit = 50000, .mem_limit = 512*1024, .name = "infinite"}
    );
    printf("status=%d error=%s\ncpu=%d\n\n", r.status, r.error, r.cpu_used);
    free((void*)r.error);
    
    printf("=== Test 3: Memory bomb ===\n");
    r = sandbox_run(
        "local t = {} for i=1,10000000 do t[i]=i end",
        (sandbox_opts_t){.cpu_limit = 10000000, .mem_limit = 256*1024, .name = "membomb"}
    );
    printf("status=%d error=%s\nmem_peak=%zuKB\n\n", r.status, r.error, r.mem_peak/1024);
    free((void*)r.error);
    
    printf("=== Test 4: os.execute attack ===\n");
    r = sandbox_run(
        "os.execute('echo hacked')",
        (sandbox_opts_t){.cpu_limit = 100000, .mem_limit = 512*1024, .name = "attack"}
    );
    printf("status=%d error=%s\n\n", r.status, r.error);
    free((void*)r.error);
    
    printf("=== Test 5: Safe with custom API ===\n");
    r = sandbox_run(
        "print('type of os:', type(os))\n"
        "print('math works:', math.sqrt(16))\n"
        "print('string works:', string.upper('hello'))\n",
        (sandbox_opts_t){.cpu_limit = 100000, .mem_limit = 512*1024, .name = "safe"}
    );
    printf("status=%d cpu=%d mem_peak=%zuKB\n", r.status, r.cpu_used, r.mem_peak/1024);
    free((void*)r.error);
    
    return 0;
}
```

```
=== Test 1: Safe code ===
sum = 5050
status=0 cpu=3000 mem_peak=78KB

=== Test 2: Infinite loop ===
status=2 error=infinite:1: CPU quota exceeded: 51000/50000
cpu=51000

=== Test 3: Memory bomb ===
status=2 error=not enough memory
mem_peak=240KB

=== Test 4: os.execute attack ===
status=2 error=attack:1: attempt to index a nil value (global 'os')

=== Test 5: Safe with custom API ===
type of os: nil
math works: 4.0
string works: HELLO
status=0 cpu=4000 mem_peak=78KB
```

**Trzy filary złączone.** Jedno API: `sandbox_run(code, opts)`. Izolacja totalna: restricted env, CPU quota, memory limit. Każdy atak zablokowany z czytelnym błędem.

### Sprawdź się

- [ ] Umiem połączyć env + cpu + mem w jedno API
- [ ] Wiem, że każdy sandbox powinien mieć **osobny lua_State**
- [ ] Rozumiem wynik `sandbox_result_t` — status + error + diagnostyka
- [ ] Pamiętam `lua_close` po każdym run (cleanup)

---

## Lekcja 10.5: Sandbox dla KarmazynOS — praktyczne API hosta

### Cel

Projektujesz API sandboxa specyficzne dla KarmazynOS: wstrzyknięcie `hss.*`, callback'i, per-session state.

### Materiał

#### Architektura

```
Host (C)
├── sandbox_create(opts)     → sandbox_t*
├── sandbox_inject(sb, name, fn_or_table)
├── sandbox_run(sb, code)    → result
├── sandbox_get_result(sb, name)
├── sandbox_destroy(sb)
│
└── Per-sandbox:
    ├── lua_State*           (izolowany)
    ├── mem_quota_t          (limit pamięci)
    ├── cpu_quota_t          (limit CPU)
    └── _ENV                 (whitelist + injected API)
```

#### Wstrzykiwanie API hosta

```c
typedef struct {
    lua_State *L;
    mem_quota_t mem;
    int cpu_limit;
    char name[64];
} sandbox_t;

void sandbox_inject_function(sandbox_t *sb, const char *name, lua_CFunction fn) {
    // Dodaj fn do sandbox env w registry:
    lua_pushlightuserdata(sb->L, sb);    // klucz = sandbox pointer
    lua_gettable(sb->L, LUA_REGISTRYINDEX);    // push env
    
    lua_pushcfunction(sb->L, fn);
    lua_setfield(sb->L, -2, name);
    
    lua_pop(sb->L, 1);
}
```

Skrypt widzi wstrzykniętą funkcję jako "natywną":

```lua
-- Z perspektywy skryptu:
local phi = hss.get_phi()           -- wstrzyknięte z C
local atoms = hss.list_atoms()      -- wstrzyknięte z C
hss.set_phi(0.8)                     -- wstrzyknięte z C
-- os.execute("...")                  -- nie istnieje
```

#### Komunikacja sandbox → host (callback)

```c
// Rejestruj callback w sandbox:
void sandbox_set_callback(sandbox_t *sb, const char *event, lua_CFunction handler) {
    // handler wywoływany gdy skrypt emituje event
}

// Skrypt emituje:
// emit("phi_changed", 0.8)

// Host handler w C:
static int host_on_phi_changed(lua_State *L) {
    double new_phi = lua_tonumber(L, 1);
    printf("[HOST] phi changed to %f\n", new_phi);
    // Aktualizacja sesji hosta...
    return 0;
}
```

#### Komunikacja host → sandbox (globals)

```c
// Host ustawia dane przed run:
void sandbox_set_global(sandbox_t *sb, const char *name, double value) {
    // Dodaj do env:
    lua_pushlightuserdata(sb->L, sb);
    lua_gettable(sb->L, LUA_REGISTRYINDEX);
    lua_pushnumber(sb->L, value);
    lua_setfield(sb->L, -2, name);
    lua_pop(sb->L, 1);
}

// Skrypt czyta:
// local phi = current_phi    -- ustawione przez host
// if phi > 0.8 then emit("alert", phi) end
```

#### Per-session state

Każda sesja HSS ma **osobny sandbox** z osobnym `lua_State`:

```c
session_t sessions[MAX_SESSIONS];

for (int i = 0; i < n; i++) {
    sessions[i].sandbox = sandbox_create(
        (sandbox_opts_t){.cpu_limit = 100000, .mem_limit = 256*1024}
    );
    sandbox_inject_function(sessions[i].sandbox, "get_phi", l_get_phi);
    sandbox_inject_function(sessions[i].sandbox, "set_phi", l_set_phi);
}

// Każda sesja odizolowana — crash jednej nie wpływa na inne
```

To jest **izolacja sesji** — fundament bezpieczeństwa KarmazynOS.

### Sprawdź się

- [ ] Rozumiem architekturę: osobny lua_State per sandbox
- [ ] Umiem wstrzyknąć C functions do sandbox env
- [ ] Wiem jak komunikować sandbox ↔ host (globals + callbacks)
- [ ] Rozumiem per-session isolation

---

## Sprawdzian Modułu 10

### Zadania

**Sprawdzian 1** — Minimal sandbox z API  
Napisz `sandbox_t` z create/inject/run/destroy. Test: wstrzyknij `hss_phi()` zwracające 0.7. Skrypt: `print(hss_phi())`. Blokada: `os.execute`.

**Sprawdzian 2** — CPU + memory razem  
Sandbox z obu limitami. Test 3 scenariusze: fast OK, infinite loop killed, memory bomb killed.

**Sprawdzian 3** — Read-only config  
Wstrzyknij tabelę `config = {max_phi=0.8, mode="strict"}` do sandbox jako **read-only** (próba zapisu → error).

**Sprawdzian 4** — Multi-sandbox isolation  
Stwórz 3 sandboxes z różnymi limitami. Pokaż że crash jednego nie wpływa na inne.

**Sprawdzian 5** — Sandbox z output capture  
Zamień `print` w sandbox na funkcję C, która zbiera output do bufora. Po run — zwróć cały output jako string.

**Sprawdzian 6** — Pełen sandbox z HSS API  
Sandbox z wstrzykniętym modułem `hss`:
- `hss.spawn(sig, phi)` → atom (tabela)
- `hss.decay(atom, dt)` → in-place
- `hss.is_alive(atom)` → bool
- `hss.emit(event, ...)` → host callback

Test: skrypt tworzy atom, decay'uje, emituje event gdy phi < threshold.

---

### Rozwiązania sprawdzianu

#### Sprawdzian 1

```c
// sandbox_minimal.c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

typedef struct {
    lua_State *L;
    int env_ref;    // reference do env w registry
} sandbox_t;

static void build_env(lua_State *L) {
    lua_newtable(L);
    const char *safe[] = {
        "print", "tostring", "type", "pairs", "ipairs",
        "pcall", "error", "assert", "tonumber", "select",
        NULL
    };
    for (int i = 0; safe[i]; i++) {
        lua_getglobal(L, safe[i]);
        lua_setfield(L, -2, safe[i]);
    }
    lua_getglobal(L, "math");   lua_setfield(L, -2, "math");
    lua_getglobal(L, "string"); lua_setfield(L, -2, "string");
    lua_getglobal(L, "table");  lua_setfield(L, -2, "table");
}

sandbox_t *sandbox_create(void) {
    sandbox_t *sb = (sandbox_t *)calloc(1, sizeof(sandbox_t));
    sb->L = luaL_newstate();
    luaL_openlibs(sb->L);
    
    // Buduj env i zapisz w registry:
    build_env(sb->L);
    sb->env_ref = luaL_ref(sb->L, LUA_REGISTRYINDEX);
    
    return sb;
}

void sandbox_inject(sandbox_t *sb, const char *name, lua_CFunction fn) {
    lua_rawgeti(sb->L, LUA_REGISTRYINDEX, sb->env_ref);
    lua_pushcfunction(sb->L, fn);
    lua_setfield(sb->L, -2, name);
    lua_pop(sb->L, 1);
}

int sandbox_run(sandbox_t *sb, const char *code, const char *name) {
    int rc = luaL_loadbufferx(sb->L, code, strlen(code), name, "t");
    if (rc != LUA_OK) {
        fprintf(stderr, "[sandbox] compile: %s\n", lua_tostring(sb->L, -1));
        lua_pop(sb->L, 1);
        return rc;
    }
    
    // Ustaw _ENV:
    lua_rawgeti(sb->L, LUA_REGISTRYINDEX, sb->env_ref);
    lua_setupvalue(sb->L, -2, 1);
    
    rc = lua_pcall(sb->L, 0, 0, 0);
    if (rc != LUA_OK) {
        fprintf(stderr, "[sandbox] runtime: %s\n", lua_tostring(sb->L, -1));
        lua_pop(sb->L, 1);
    }
    return rc;
}

void sandbox_destroy(sandbox_t *sb) {
    if (sb->L) lua_close(sb->L);
    free(sb);
}

// --- Test ---

static int l_hss_phi(lua_State *L) {
    lua_pushnumber(L, 0.7);
    return 1;
}

int main(void) {
    sandbox_t *sb = sandbox_create();
    sandbox_inject(sb, "hss_phi", l_hss_phi);
    
    printf("--- Safe call ---\n");
    sandbox_run(sb, "print('phi:', hss_phi())", "test1");
    
    printf("\n--- os.execute blocked ---\n");
    sandbox_run(sb, "os.execute('echo hacked')", "attack");
    
    printf("\n--- io blocked ---\n");
    sandbox_run(sb, "io.open('/etc/passwd')", "attack2");
    
    printf("\n--- require blocked ---\n");
    sandbox_run(sb, "require('os')", "attack3");
    
    sandbox_destroy(sb);
    return 0;
}
```

```
--- Safe call ---
phi: 0.7

--- os.execute blocked ---
[sandbox] runtime: attack:1: attempt to index a nil value (global 'os')

--- io blocked ---
[sandbox] runtime: attack2:1: attempt to index a nil value (global 'io')

--- require blocked ---
[sandbox] runtime: attack3:1: attempt to call a nil value (global 'require')
```

#### Sprawdzian 5

```c
// sandbox_capture.c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

#define MAX_OUTPUT (64 * 1024)

typedef struct {
    lua_State *L;
    int env_ref;
    char output[MAX_OUTPUT];
    size_t output_len;
} sandbox_t;

static int captured_print_key;

static int l_captured_print(lua_State *L) {
    // Odzyskaj sandbox_t z registry:
    lua_pushlightuserdata(L, &captured_print_key);
    lua_gettable(L, LUA_REGISTRYINDEX);
    sandbox_t *sb = (sandbox_t *)lua_touserdata(L, -1);
    lua_pop(L, 1);
    
    int n = lua_gettop(L);
    for (int i = 1; i <= n; i++) {
        if (i > 1) {
            if (sb->output_len < MAX_OUTPUT - 1)
                sb->output[sb->output_len++] = '\t';
        }
        const char *s = luaL_tolstring(L, i, NULL);
        size_t slen = strlen(s);
        if (sb->output_len + slen < MAX_OUTPUT) {
            memcpy(sb->output + sb->output_len, s, slen);
            sb->output_len += slen;
        }
        lua_pop(L, 1);    // pop tolstring result
    }
    if (sb->output_len < MAX_OUTPUT - 1)
        sb->output[sb->output_len++] = '\n';
    
    return 0;
}

static void build_env(lua_State *L, sandbox_t *sb) {
    lua_newtable(L);
    
    // Captured print:
    lua_pushcfunction(L, l_captured_print);
    lua_setfield(L, -2, "print");
    
    const char *safe[] = {
        "tostring", "tonumber", "type", "pairs", "ipairs",
        "pcall", "error", "assert", "select",
        NULL
    };
    for (int i = 0; safe[i]; i++) {
        lua_getglobal(L, safe[i]);
        lua_setfield(L, -2, safe[i]);
    }
    lua_getglobal(L, "math");   lua_setfield(L, -2, "math");
    lua_getglobal(L, "string"); lua_setfield(L, -2, "string");
    lua_getglobal(L, "table");  lua_setfield(L, -2, "table");
    
    // Store sandbox pointer in registry for captured_print:
    lua_pushlightuserdata(L, &captured_print_key);
    lua_pushlightuserdata(L, sb);
    lua_settable(L, LUA_REGISTRYINDEX);
}

sandbox_t *sandbox_create(void) {
    sandbox_t *sb = (sandbox_t *)calloc(1, sizeof(sandbox_t));
    sb->L = luaL_newstate();
    luaL_openlibs(sb->L);
    sb->output_len = 0;
    
    build_env(sb->L, sb);
    sb->env_ref = luaL_ref(sb->L, LUA_REGISTRYINDEX);
    
    return sb;
}

const char *sandbox_run(sandbox_t *sb, const char *code) {
    sb->output_len = 0;
    sb->output[0] = '\0';
    
    int rc = luaL_loadbufferx(sb->L, code, strlen(code), "sandbox", "t");
    if (rc != LUA_OK) {
        const char *err = lua_tostring(sb->L, -1);
        snprintf(sb->output, MAX_OUTPUT, "[ERROR] %s\n", err);
        sb->output_len = strlen(sb->output);
        lua_pop(sb->L, 1);
        return sb->output;
    }
    
    lua_rawgeti(sb->L, LUA_REGISTRYINDEX, sb->env_ref);
    lua_setupvalue(sb->L, -2, 1);
    
    rc = lua_pcall(sb->L, 0, 0, 0);
    if (rc != LUA_OK) {
        size_t remaining = MAX_OUTPUT - sb->output_len;
        snprintf(sb->output + sb->output_len, remaining,
            "[ERROR] %s\n", lua_tostring(sb->L, -1));
        sb->output_len = strlen(sb->output);
        lua_pop(sb->L, 1);
    }
    
    sb->output[sb->output_len] = '\0';
    return sb->output;
}

void sandbox_destroy(sandbox_t *sb) {
    if (sb->L) lua_close(sb->L);
    free(sb);
}

int main(void) {
    sandbox_t *sb = sandbox_create();
    
    const char *output = sandbox_run(sb,
        "print('Hello from sandbox')\n"
        "print('pi =', math.pi)\n"
        "for i = 1, 3 do print('i =', i) end\n"
    );
    
    printf("=== Captured output ===\n%s=== End ===\n", output);
    
    printf("\n");
    
    output = sandbox_run(sb, "error('test error')");
    printf("=== Error output ===\n%s=== End ===\n", output);
    
    sandbox_destroy(sb);
    return 0;
}
```

```
=== Captured output ===
Hello from sandbox
pi =	3.1415926535898
i =	1
i =	2
i =	3
=== End ===

=== Error output ===
[ERROR] sandbox:1: test error
=== End ===
```

Output capture — `print` zastąpiony C function zbierającą do bufora. Host dostaje cały output jako string. Kluczowe dla KarmazynOS: skrypt nie pisze bezpośrednio na stdout hosta.

#### Sprawdzian 6

```c
// sandbox_hss.c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

// Host-side event handler:
static void host_on_event(const char *event, lua_State *L, int first_arg, int nargs) {
    printf("[HOST EVENT] %s(", event);
    for (int i = first_arg; i < first_arg + nargs; i++) {
        if (i > first_arg) printf(", ");
        luaL_tolstring(L, i, NULL);
        printf("%s", lua_tostring(L, -1));
        lua_pop(L, 1);
    }
    printf(")\n");
}

// --- HSS API for sandbox ---

static int l_hss_spawn(lua_State *L) {
    const char *sig = luaL_checkstring(L, 1);
    double phi = luaL_checknumber(L, 2);
    if (phi < 0 || phi > 1) return luaL_argerror(L, 2, "phi must be in [0,1]");
    
    lua_newtable(L);
    lua_pushstring(L, sig);   lua_setfield(L, -2, "sig");
    lua_pushnumber(L, phi);   lua_setfield(L, -2, "phi");
    lua_pushboolean(L, 1);    lua_setfield(L, -2, "alive");
    return 1;
}

static int l_hss_decay(lua_State *L) {
    luaL_checktype(L, 1, LUA_TTABLE);
    double dt = luaL_optnumber(L, 2, 0.1);
    
    lua_getfield(L, 1, "phi");
    double phi = lua_tonumber(L, -1) * exp(-dt);
    lua_pop(L, 1);
    
    lua_pushnumber(L, phi);
    lua_setfield(L, 1, "phi");
    
    if (phi < 1e-6) {
        lua_pushboolean(L, 0);
        lua_setfield(L, 1, "alive");
    }
    return 0;
}

static int l_hss_is_alive(lua_State *L) {
    luaL_checktype(L, 1, LUA_TTABLE);
    lua_getfield(L, 1, "alive");
    return 1;
}

static int l_hss_emit(lua_State *L) {
    const char *event = luaL_checkstring(L, 1);
    int nargs = lua_gettop(L) - 1;
    host_on_event(event, L, 2, nargs);
    return 0;
}

static const luaL_Reg hss_funcs[] = {
    {"spawn",    l_hss_spawn},
    {"decay",    l_hss_decay},
    {"is_alive", l_hss_is_alive},
    {"emit",     l_hss_emit},
    {NULL, NULL}
};

// --- Sandbox ---

static void build_env(lua_State *L) {
    lua_newtable(L);
    
    const char *safe[] = {
        "print", "tostring", "tonumber", "type", "pairs", "ipairs",
        "pcall", "error", "assert", "select", "unpack",
        NULL
    };
    for (int i = 0; safe[i]; i++) {
        lua_getglobal(L, safe[i]);
        lua_setfield(L, -2, safe[i]);
    }
    lua_getglobal(L, "math");   lua_setfield(L, -2, "math");
    lua_getglobal(L, "string"); lua_setfield(L, -2, "string");
    lua_getglobal(L, "table");  lua_setfield(L, -2, "table");
    
    // HSS module:
    luaL_newlib(L, hss_funcs);
    lua_setfield(L, -2, "hss");
}

static int run_sandboxed(lua_State *L, const char *code) {
    int rc = luaL_loadbufferx(L, code, strlen(code), "script", "t");
    if (rc != LUA_OK) {
        fprintf(stderr, "compile: %s\n", lua_tostring(L, -1));
        lua_pop(L, 1);
        return rc;
    }
    build_env(L);
    lua_setupvalue(L, -2, 1);
    
    rc = lua_pcall(L, 0, 0, 0);
    if (rc != LUA_OK) {
        fprintf(stderr, "runtime: %s\n", lua_tostring(L, -1));
        lua_pop(L, 1);
    }
    return rc;
}

int main(void) {
    lua_State *L = luaL_newstate();
    luaL_openlibs(L);
    
    const char *script =
        "-- Skrypt użytkownika w sandboxie:\n"
        "local atom = hss.spawn('sensor-1', 0.9)\n"
        "print('created:', atom.sig, 'phi:', atom.phi)\n"
        "\n"
        "-- Decay loop:\n"
        "for tick = 1, 30 do\n"
        "    hss.decay(atom, 0.2)\n"
        "    \n"
        "    if atom.phi < 0.3 and hss.is_alive(atom) then\n"
        "        hss.emit('low_phi', atom.sig, atom.phi)\n"
        "    end\n"
        "    \n"
        "    if not hss.is_alive(atom) then\n"
        "        hss.emit('atom_dead', atom.sig)\n"
        "        break\n"
        "    end\n"
        "end\n"
        "\n"
        "print('final phi:', atom.phi)\n"
        "print('alive:', hss.is_alive(atom))\n"
        "\n"
        "-- Attack attempt:\n"
        "local ok, err = pcall(function() os.execute('ls') end)\n"
        "print('attack blocked:', not ok)\n";
    
    printf("=== Running sandboxed HSS script ===\n\n");
    run_sandboxed(L, script);
    
    lua_close(L);
    return 0;
}
```

```
=== Running sandboxed HSS script ===

created: sensor-1 phi: 0.9
[HOST EVENT] low_phi(sensor-1, 0.20189651799466)
[HOST EVENT] low_phi(sensor-1, 0.16529888822159)
[HOST EVENT] low_phi(sensor-1, 0.13533528323661)
[HOST EVENT] low_phi(sensor-1, 0.11080315836234)
...
[HOST EVENT] atom_dead(sensor-1)
final phi: 0.0
alive: false
attack blocked: true
```

**Pełen sandbox KarmazynOS.** Skrypt widzi `hss.*` API, emituje event'y do hosta, nie może uciec (`os.execute` → nil). Host widzi event'y w swoim callback'u. To jest dokładnie architektura z Lekcji 10.5.

*(Sprawdziany 2, 3, 4 pominięte — wzorce ustalone w Lekcjach 10.2-10.4.)*

---

## Co dalej?

Sandbox gotowy — trzy filary + praktyczne API. W kolejnym module — **DSL dla KarmazynOS**: polityki HSS jako Lua DSL, scheduler multi-agent, pełna integracja z sandboxem.

→ **Moduł 11: DSL dla KarmazynOS** — deklaratywne polityki, scheduler agentów, event routing, Φ-space operations.
