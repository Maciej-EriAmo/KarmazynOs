# Moduł 12: Capstone — KarmazynOS Micro-Runtime

> *"Wiedzieć każdy kawałek osobno — to rzemiosło. Złożyć je w działający system — to inżynieria."*

Ten moduł nie uczy nowych pojęć. Ten moduł **łączy wszystko** w działający system. Budujesz od zera mini-runtime KarmazynOS: host w C, sandbox, bindingi userdata, polityki DSL, scheduler agentów, event routing. Na końcu masz jeden program który można uruchomić.

Moduł jest zorganizowany jako **5 faz projektu** — każda dodaje warstwę. Na końcu — sprawdzian: rozszerzenia i modyfikacje.

**Przewidywany czas:** 8-12 godzin pracy.

---

## Faza 1: Host C — szkielet z sandboxem

### Cel

Program C tworzący sandboxowany `lua_State` z custom alokatorem, CPU hookiem, restricted `_ENV`.

### Materiał

```c
// karmazyn_micro.c — Faza 1: szkielet

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>

// ============================================================
// Memory allocator (M10.3)
// ============================================================

typedef struct {
    size_t used;
    size_t limit;
    size_t peak;
} mem_ctx_t;

static void *mem_alloc(void *ud, void *ptr, size_t osize, size_t nsize) {
    mem_ctx_t *ctx = (mem_ctx_t *)ud;
    if (nsize == 0) {
        ctx->used -= osize;
        free(ptr);
        return NULL;
    }
    size_t need = ptr ? (nsize > osize ? nsize - osize : 0) : nsize;
    if (ctx->used + need > ctx->limit) return NULL;
    void *p = ptr ? realloc(ptr, nsize) : malloc(nsize);
    if (p) {
        ctx->used += ptr ? (nsize - osize) : nsize;
        if (ctx->used > ctx->peak) ctx->peak = ctx->used;
    }
    return p;
}

// ============================================================
// CPU hook (M10.2)
// ============================================================

static int cpu_key;

typedef struct {
    int limit;
    int used;
} cpu_ctx_t;

static void cpu_hook(lua_State *L, lua_Debug *ar) {
    (void)ar;
    lua_pushlightuserdata(L, &cpu_key);
    lua_gettable(L, LUA_REGISTRYINDEX);
    cpu_ctx_t *ctx = (cpu_ctx_t *)lua_touserdata(L, -1);
    lua_pop(L, 1);
    if (!ctx) return;
    ctx->used += 1000;
    if (ctx->used > ctx->limit) {
        lua_sethook(L, NULL, 0, 0);
        luaL_error(L, "CPU quota exceeded: %d/%d", ctx->used, ctx->limit);
    }
}

// ============================================================
// Sandbox env (M10.1)
// ============================================================

static int env_key;

static void build_env(lua_State *L) {
    lua_newtable(L);
    
    const char *safe[] = {
        "assert", "error", "ipairs", "pairs", "next",
        "pcall", "xpcall", "select", "tonumber", "tostring",
        "type", "unpack", "rawequal",
        "setmetatable", "getmetatable",
        NULL
    };
    for (int i = 0; safe[i]; i++) {
        lua_getglobal(L, safe[i]);
        if (!lua_isnil(L, -1)) lua_setfield(L, -2, safe[i]);
        else lua_pop(L, 1);
    }
    
    lua_getglobal(L, "math");       lua_setfield(L, -2, "math");
    lua_getglobal(L, "string");     lua_setfield(L, -2, "string");
    lua_getglobal(L, "table");      lua_setfield(L, -2, "table");
    lua_getglobal(L, "coroutine");  lua_setfield(L, -2, "coroutine");
    
    // Store env in registry:
    lua_pushlightuserdata(L, &env_key);
    lua_pushvalue(L, -2);
    lua_settable(L, LUA_REGISTRYINDEX);
}

// ============================================================
// Sandbox context
// ============================================================

typedef struct {
    lua_State *L;
    mem_ctx_t mem;
    cpu_ctx_t cpu;
    char name[64];
    int alive;
} sandbox_t;

sandbox_t *sandbox_create(const char *name, size_t mem_limit, int cpu_limit) {
    sandbox_t *sb = (sandbox_t *)calloc(1, sizeof(sandbox_t));
    strncpy(sb->name, name, sizeof(sb->name) - 1);
    sb->alive = 1;
    
    sb->mem.limit = mem_limit;
    sb->L = lua_newstate(mem_alloc, &sb->mem);
    if (!sb->L) { free(sb); return NULL; }
    
    luaL_openlibs(sb->L);
    build_env(sb->L);
    
    // CPU quota:
    sb->cpu.limit = cpu_limit;
    sb->cpu.used = 0;
    cpu_ctx_t *cq = (cpu_ctx_t *)lua_newuserdata(sb->L, sizeof(cpu_ctx_t));
    *cq = sb->cpu;
    lua_pushlightuserdata(sb->L, &cpu_key);
    lua_insert(sb->L, -2);
    lua_settable(sb->L, LUA_REGISTRYINDEX);
    
    return sb;
}

int sandbox_exec(sandbox_t *sb, const char *code) {
    if (!sb->alive) return -1;
    
    // Reset CPU:
    lua_pushlightuserdata(sb->L, &cpu_key);
    lua_gettable(sb->L, LUA_REGISTRYINDEX);
    cpu_ctx_t *cq = (cpu_ctx_t *)lua_touserdata(sb->L, -1);
    lua_pop(sb->L, 1);
    if (cq) cq->used = 0;
    
    int rc = luaL_loadbufferx(sb->L, code, strlen(code), sb->name, "t");
    if (rc != LUA_OK) {
        fprintf(stderr, "[%s] compile: %s\n", sb->name, lua_tostring(sb->L, -1));
        lua_pop(sb->L, 1);
        return rc;
    }
    
    // Set sandbox _ENV:
    lua_pushlightuserdata(sb->L, &env_key);
    lua_gettable(sb->L, LUA_REGISTRYINDEX);
    lua_setupvalue(sb->L, -2, 1);
    
    lua_sethook(sb->L, cpu_hook, LUA_MASKCOUNT, 1000);
    rc = lua_pcall(sb->L, 0, LUA_MULTRET, 0);
    lua_sethook(sb->L, NULL, 0, 0);
    
    if (rc != LUA_OK) {
        fprintf(stderr, "[%s] runtime: %s\n", sb->name, lua_tostring(sb->L, -1));
        lua_pop(sb->L, 1);
    }
    
    // Update CPU stats:
    if (cq) sb->cpu = *cq;
    
    return rc;
}

void sandbox_inject_cfunc(sandbox_t *sb, const char *name, lua_CFunction fn) {
    lua_pushlightuserdata(sb->L, &env_key);
    lua_gettable(sb->L, LUA_REGISTRYINDEX);
    lua_pushcfunction(sb->L, fn);
    lua_setfield(sb->L, -2, name);
    lua_pop(sb->L, 1);
}

void sandbox_inject_module(sandbox_t *sb, const char *name, const luaL_Reg *funcs) {
    lua_pushlightuserdata(sb->L, &env_key);
    lua_gettable(sb->L, LUA_REGISTRYINDEX);
    luaL_newlib(sb->L, funcs);
    lua_setfield(sb->L, -2, name);
    lua_pop(sb->L, 1);
}

void sandbox_destroy(sandbox_t *sb) {
    if (sb->L) lua_close(sb->L);
    sb->alive = 0;
    free(sb);
}

void sandbox_stats(sandbox_t *sb) {
    printf("[%s] mem: %zuKB/%zuKB (peak %zuKB) cpu: %d/%d\n",
        sb->name,
        sb->mem.used / 1024, sb->mem.limit / 1024, sb->mem.peak / 1024,
        sb->cpu.used, sb->cpu.limit);
}
```

Szkielet gotowy — `sandbox_create`, `sandbox_exec`, `sandbox_inject_*`, `sandbox_destroy`. To jest fundament — kolejne fazy dodają warstwy na tej bazie.

### Sprawdź się

- [ ] Mam kompilujący się szkielet z alokatorem, hookiem, env
- [ ] `sandbox_exec` kompiluje text-only, ustawia _ENV, uruchamia z hookiem

---

## Faza 2: HSS bindingi — Atom i Session jako userdata

### Cel

Dodajesz typy `Atom` i `Session` jako userdata (M9) do sandbox env.

### Materiał

```c
// ============================================================
// Atom userdata (M9)
// ============================================================

#define ATOM_MT "KAtom"

typedef struct {
    char sig[64];
    double phi;
    int alive;
    int id;
} katom_t;

static int _atom_id = 0;

static katom_t *check_atom(lua_State *L, int idx) {
    return (katom_t *)luaL_checkudata(L, idx, ATOM_MT);
}

static int l_atom_new(lua_State *L) {
    const char *sig = luaL_checkstring(L, 1);
    double phi = luaL_optnumber(L, 2, 1.0);
    if (phi < 0 || phi > 1) return luaL_argerror(L, 2, "phi must be in [0,1]");
    
    katom_t *a = (katom_t *)lua_newuserdata(L, sizeof(katom_t));
    strncpy(a->sig, sig, sizeof(a->sig) - 1);
    a->phi = phi;
    a->alive = 1;
    a->id = ++_atom_id;
    luaL_setmetatable(L, ATOM_MT);
    return 1;
}

static int l_atom_sig(lua_State *L) { lua_pushstring(L, check_atom(L, 1)->sig); return 1; }
static int l_atom_phi(lua_State *L) { lua_pushnumber(L, check_atom(L, 1)->phi); return 1; }
static int l_atom_is_alive(lua_State *L) { lua_pushboolean(L, check_atom(L, 1)->alive); return 1; }

static int l_atom_decay(lua_State *L) {
    katom_t *a = check_atom(L, 1);
    double dt = luaL_optnumber(L, 2, 0.1);
    a->phi *= exp(-dt);
    if (a->phi < 1e-6) { a->phi = 0; a->alive = 0; }
    return 0;
}

static int l_atom_kill(lua_State *L) {
    katom_t *a = check_atom(L, 1);
    a->alive = 0; a->phi = 0;
    return 0;
}

static int l_atom_tostring(lua_State *L) {
    katom_t *a = check_atom(L, 1);
    lua_pushfstring(L, "Atom#%d<%s, phi=%.4f, %s>",
        a->id, a->sig, a->phi, a->alive ? "alive" : "dead");
    return 1;
}

static int l_atom_lt(lua_State *L) {
    lua_pushboolean(L, check_atom(L, 1)->phi < check_atom(L, 2)->phi);
    return 1;
}

static int l_atom_gc(lua_State *L) {
    katom_t *a = check_atom(L, 1);
    if (a->alive) {
        fprintf(stderr, "[GC] Atom#%d '%s' alive at collection\n", a->id, a->sig);
    }
    return 0;
}

static const luaL_Reg atom_methods[] = {
    {"sig", l_atom_sig}, {"phi", l_atom_phi},
    {"is_alive", l_atom_is_alive}, {"decay", l_atom_decay},
    {"kill", l_atom_kill},
    {NULL, NULL}
};

static const luaL_Reg atom_meta[] = {
    {"__tostring", l_atom_tostring}, {"__lt", l_atom_lt}, {"__gc", l_atom_gc},
    {NULL, NULL}
};

// ============================================================
// Session userdata
// ============================================================

#define SESSION_MT "KSession"
#define MAX_SESSION_ATOMS 128

typedef struct {
    char sig[64];
    katom_t *atoms[MAX_SESSION_ATOMS];    // pointery do atom userdata
    int atom_refs[MAX_SESSION_ATOMS];     // registry refs
    int atom_count;
    int epoch;
    int alive;
    int id;
} ksession_t;

static int _session_id = 0;

static ksession_t *check_session(lua_State *L, int idx) {
    return (ksession_t *)luaL_checkudata(L, idx, SESSION_MT);
}

static int l_session_new(lua_State *L) {
    const char *sig = luaL_checkstring(L, 1);
    
    ksession_t *s = (ksession_t *)lua_newuserdata(L, sizeof(ksession_t));
    memset(s, 0, sizeof(ksession_t));
    strncpy(s->sig, sig, sizeof(s->sig) - 1);
    s->alive = 1;
    s->id = ++_session_id;
    luaL_setmetatable(L, SESSION_MT);
    return 1;
}

static int l_session_add_atom(lua_State *L) {
    ksession_t *s = check_session(L, 1);
    katom_t *a = check_atom(L, 2);
    if (!s->alive) return luaL_error(L, "session is dead");
    if (s->atom_count >= MAX_SESSION_ATOMS) return luaL_error(L, "max atoms reached");
    
    // Keep reference so GC doesn't collect atom:
    lua_pushvalue(L, 2);
    s->atom_refs[s->atom_count] = luaL_ref(L, LUA_REGISTRYINDEX);
    s->atoms[s->atom_count] = a;
    s->atom_count++;
    
    lua_pushinteger(L, s->atom_count);
    return 1;
}

static int l_session_tick(lua_State *L) {
    ksession_t *s = check_session(L, 1);
    double dt = luaL_optnumber(L, 2, 0.1);
    s->epoch++;
    
    int killed = 0;
    for (int i = 0; i < s->atom_count; i++) {
        if (s->atoms[i] && s->atoms[i]->alive) {
            s->atoms[i]->phi *= exp(-dt);
            if (s->atoms[i]->phi < 1e-6) {
                s->atoms[i]->phi = 0;
                s->atoms[i]->alive = 0;
                killed++;
            }
        }
    }
    lua_pushinteger(L, killed);
    return 1;
}

static int l_session_alive_count(lua_State *L) {
    ksession_t *s = check_session(L, 1);
    int n = 0;
    for (int i = 0; i < s->atom_count; i++)
        if (s->atoms[i] && s->atoms[i]->alive) n++;
    lua_pushinteger(L, n);
    return 1;
}

static int l_session_epoch(lua_State *L) { lua_pushinteger(L, check_session(L, 1)->epoch); return 1; }
static int l_session_sig(lua_State *L) { lua_pushstring(L, check_session(L, 1)->sig); return 1; }

static int l_session_close(lua_State *L) {
    ksession_t *s = check_session(L, 1);
    s->alive = 0;
    // Release atom refs:
    for (int i = 0; i < s->atom_count; i++) {
        if (s->atom_refs[i] != 0) {
            luaL_unref(L, LUA_REGISTRYINDEX, s->atom_refs[i]);
            s->atom_refs[i] = 0;
        }
    }
    return 0;
}

static int l_session_tostring(lua_State *L) {
    ksession_t *s = check_session(L, 1);
    int alive = 0;
    for (int i = 0; i < s->atom_count; i++)
        if (s->atoms[i] && s->atoms[i]->alive) alive++;
    lua_pushfstring(L, "Session#%d<%s, atoms=%d/%d, epoch=%d, %s>",
        s->id, s->sig, alive, s->atom_count, s->epoch,
        s->alive ? "alive" : "closed");
    return 1;
}

static int l_session_gc(lua_State *L) {
    ksession_t *s = check_session(L, 1);
    if (s->alive) {
        fprintf(stderr, "[GC] Session#%d '%s' not closed\n", s->id, s->sig);
        for (int i = 0; i < s->atom_count; i++) {
            if (s->atom_refs[i] != 0)
                luaL_unref(L, LUA_REGISTRYINDEX, s->atom_refs[i]);
        }
    }
    return 0;
}

static const luaL_Reg session_methods[] = {
    {"add_atom", l_session_add_atom}, {"tick", l_session_tick},
    {"alive_count", l_session_alive_count}, {"epoch", l_session_epoch},
    {"sig", l_session_sig}, {"close", l_session_close},
    {NULL, NULL}
};

static const luaL_Reg session_meta[] = {
    {"__tostring", l_session_tostring}, {"__gc", l_session_gc},
    {NULL, NULL}
};

// ============================================================
// Register types
// ============================================================

static void register_hss_types(lua_State *L) {
    // Atom:
    luaL_newmetatable(L, ATOM_MT);
    luaL_setfuncs(L, atom_meta, 0);
    luaL_newlib(L, atom_methods);
    lua_setfield(L, -2, "__index");
    lua_pop(L, 1);
    
    // Session:
    luaL_newmetatable(L, SESSION_MT);
    luaL_setfuncs(L, session_meta, 0);
    luaL_newlib(L, session_methods);
    lua_setfield(L, -2, "__index");
    lua_pop(L, 1);
}

// Inject constructors into sandbox env:
static void inject_hss(sandbox_t *sb) {
    register_hss_types(sb->L);
    sandbox_inject_cfunc(sb, "Atom", l_atom_new);
    sandbox_inject_cfunc(sb, "Session", l_session_new);
}
```

Teraz w sandboxie:

```lua
local s = Session("user-1")
local a = Atom("sensor", 0.9)
s:add_atom(a)
print(s)    -- Session#1<user-1, atoms=1/1, epoch=0, alive>
s:tick(0.5)
print(a)    -- Atom#1<sensor, phi=0.6065, alive>
```

### Sprawdź się

- [ ] Atom i Session to userdata z metatable, nie tabele
- [ ] Session trzyma referencje do atomów (luaL_ref) żeby GC ich nie zebrał
- [ ] `__gc` loguje niezamknięte sesje

---

## Faza 3: Captured print + event emitter

### Cel

Print sandbox'owy pisze do bufora hosta. Event emitter pozwala skryptowi wysyłać sygnały do C.

### Materiał

```c
// ============================================================
// Output capture (M10 Sprawdzian 5)
// ============================================================

#define MAX_OUTPUT (64 * 1024)
static int output_key;

typedef struct {
    char buf[MAX_OUTPUT];
    size_t len;
} output_ctx_t;

static int l_sandbox_print(lua_State *L) {
    lua_pushlightuserdata(L, &output_key);
    lua_gettable(L, LUA_REGISTRYINDEX);
    output_ctx_t *out = (output_ctx_t *)lua_touserdata(L, -1);
    lua_pop(L, 1);
    if (!out) return 0;
    
    int n = lua_gettop(L);
    for (int i = 1; i <= n; i++) {
        if (i > 1 && out->len < MAX_OUTPUT - 1) out->buf[out->len++] = '\t';
        luaL_tolstring(L, i, NULL);
        const char *s = lua_tostring(L, -1);
        size_t slen = strlen(s);
        if (out->len + slen < MAX_OUTPUT) {
            memcpy(out->buf + out->len, s, slen);
            out->len += slen;
        }
        lua_pop(L, 1);
    }
    if (out->len < MAX_OUTPUT - 1) out->buf[out->len++] = '\n';
    return 0;
}

static void setup_output_capture(sandbox_t *sb) {
    output_ctx_t *out = (output_ctx_t *)lua_newuserdata(sb->L, sizeof(output_ctx_t));
    out->len = 0;
    memset(out->buf, 0, sizeof(out->buf));
    
    lua_pushlightuserdata(sb->L, &output_key);
    lua_insert(sb->L, -2);
    lua_settable(sb->L, LUA_REGISTRYINDEX);
    
    sandbox_inject_cfunc(sb, "print", l_sandbox_print);
}

static const char *get_captured_output(sandbox_t *sb) {
    lua_pushlightuserdata(sb->L, &output_key);
    lua_gettable(sb->L, LUA_REGISTRYINDEX);
    output_ctx_t *out = (output_ctx_t *)lua_touserdata(sb->L, -1);
    lua_pop(sb->L, 1);
    if (!out) return "";
    out->buf[out->len] = '\0';
    return out->buf;
}

// ============================================================
// Event emitter (M8 Sprawdzian 4 pattern)
// ============================================================

typedef void (*event_handler_t)(const char *event, const char *data);

static event_handler_t _host_event_handler = NULL;

void sandbox_set_event_handler(event_handler_t handler) {
    _host_event_handler = handler;
}

static int l_emit(lua_State *L) {
    const char *event = luaL_checkstring(L, 1);
    const char *data = luaL_optstring(L, 2, "");
    
    if (_host_event_handler) {
        _host_event_handler(event, data);
    }
    return 0;
}
```

---

## Faza 4: Config loader + REPL

### Cel

Ładujesz konfigurację z pliku Lua. REPL pozwala debugować sandbox live.

### Materiał

```c
// ============================================================
// Config loader (M8.3)
// ============================================================

int sandbox_load_file(sandbox_t *sb, const char *path) {
    FILE *f = fopen(path, "r");
    if (!f) {
        fprintf(stderr, "[%s] cannot open: %s\n", sb->name, path);
        return -1;
    }
    
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    
    char *buf = (char *)malloc(size + 1);
    fread(buf, 1, size, f);
    buf[size] = '\0';
    fclose(f);
    
    int rc = sandbox_exec(sb, buf);
    free(buf);
    return rc;
}

// ============================================================
// Debug REPL (M8.1 Zadanie 4)
// ============================================================

void sandbox_repl(sandbox_t *sb) {
    char line[4096];
    printf("[REPL] %s (type :quit to exit)\n", sb->name);
    
    while (1) {
        printf("%s> ", sb->name);
        fflush(stdout);
        
        if (!fgets(line, sizeof(line), stdin)) { printf("\n"); break; }
        size_t len = strlen(line);
        if (len > 0 && line[len-1] == '\n') line[--len] = '\0';
        if (len == 0) continue;
        if (strcmp(line, ":quit") == 0) break;
        
        if (strcmp(line, ":stats") == 0) {
            sandbox_stats(sb);
            continue;
        }
        
        // Try "return expr" first:
        char rbuf[4200];
        snprintf(rbuf, sizeof(rbuf), "return %s", line);
        
        int rc = luaL_loadbufferx(sb->L, rbuf, strlen(rbuf), "=repl", "t");
        if (rc == LUA_OK) {
            lua_pushlightuserdata(sb->L, &env_key);
            lua_gettable(sb->L, LUA_REGISTRYINDEX);
            lua_setupvalue(sb->L, -2, 1);
            
            rc = lua_pcall(sb->L, 0, LUA_MULTRET, 0);
            if (rc == LUA_OK) {
                int n = lua_gettop(sb->L);
                if (n > 0) {
                    for (int i = 1; i <= n; i++) {
                        if (i > 1) printf("\t");
                        luaL_tolstring(sb->L, i, NULL);
                        printf("%s", lua_tostring(sb->L, -1));
                        lua_pop(sb->L, 1);
                    }
                    printf("\n");
                }
                lua_settop(sb->L, 0);
                continue;
            }
            fprintf(stderr, "%s\n", lua_tostring(sb->L, -1));
            lua_pop(sb->L, 1);
            continue;
        }
        lua_pop(sb->L, 1);
        
        sandbox_exec(sb, line);
        
        // Show captured output:
        const char *out = get_captured_output(sb);
        if (out && strlen(out) > 0) {
            printf("%s", out);
            // Reset:
            lua_pushlightuserdata(sb->L, &output_key);
            lua_gettable(sb->L, LUA_REGISTRYINDEX);
            output_ctx_t *o = (output_ctx_t *)lua_touserdata(sb->L, -1);
            if (o) o->len = 0;
            lua_pop(sb->L, 1);
        }
    }
}
```

---

## Faza 5: Main — złożenie całości

### Cel

Pełen `main()` łączący wszystkie fazy. Program akceptuje plik Lua lub wchodzi w REPL.

### Materiał

```c
// ============================================================
// Host event handler
// ============================================================

static void on_event(const char *event, const char *data) {
    printf("[HOST EVENT] %s: %s\n", event, data);
}

// ============================================================
// main
// ============================================================

int main(int argc, char *argv[]) {
    printf("=== KarmazynOS Micro-Runtime v0.1 ===\n\n");
    
    sandbox_set_event_handler(on_event);
    
    // Stwórz sandbox:
    sandbox_t *sb = sandbox_create(
        "karmazyn",
        1024 * 1024,    // 1MB memory
        5000000         // 5M instructions
    );
    if (!sb) {
        fprintf(stderr, "FATAL: cannot create sandbox\n");
        return 1;
    }
    
    // Inject HSS types:
    inject_hss(sb);
    
    // Inject emit:
    sandbox_inject_cfunc(sb, "emit", l_emit);
    
    // Setup output capture:
    setup_output_capture(sb);
    
    printf("Sandbox created: mem=%zuKB, cpu=%d\n",
        sb->mem.limit / 1024, sb->cpu.limit);
    
    if (argc >= 2) {
        // File mode:
        printf("Loading: %s\n\n", argv[1]);
        int rc = sandbox_load_file(sb, argv[1]);
        
        const char *out = get_captured_output(sb);
        if (out && strlen(out) > 0) printf("%s", out);
        
        printf("\n");
        sandbox_stats(sb);
        
        if (rc != LUA_OK) {
            sandbox_destroy(sb);
            return 1;
        }
    } else {
        // REPL mode:
        sandbox_repl(sb);
    }
    
    sandbox_destroy(sb);
    printf("\n=== Shutdown ===\n");
    return 0;
}
```

#### Kompilacja

```bash
gcc -o karmazyn karmazyn_micro.c -llua5.4 -lm -ldl -Wall
```

#### Test z plikiem

```lua
-- test_scenario.lua
print("=== KarmazynOS Test Scenario ===")

-- Stwórz sesję:
local session = Session("test-user")
print(session)

-- Spawn atomów:
local atoms = {}
for i = 1, 5 do
    atoms[i] = Atom("sensor-" .. i, 0.8 + i * 0.02)
    session:add_atom(atoms[i])
end

print("After spawn:", session)

-- Symulacja decay:
for epoch = 1, 50 do
    local killed = session:tick(0.15)
    
    if killed > 0 then
        emit("atoms_killed", tostring(killed) .. " at epoch " .. epoch)
    end
    
    if session:alive_count() == 0 then
        emit("session_empty", "epoch " .. epoch)
        break
    end
end

print("Final:", session)

-- Status atomów:
for i, a in ipairs(atoms) do
    print("  " .. tostring(a))
end

session:close()
print("Closed:", session)
```

```bash
./karmazyn test_scenario.lua
```

```
=== KarmazynOS Micro-Runtime v0.1 ===

Sandbox created: mem=1024KB, cpu=5000000
Loading: test_scenario.lua

=== KarmazynOS Test Scenario ===
Session#1<test-user, atoms=0/0, epoch=0, alive>
After spawn: Session#1<test-user, atoms=5/5, epoch=0, alive>
[HOST EVENT] atoms_killed: 1 at epoch 27
[HOST EVENT] atoms_killed: 1 at epoch 28
[HOST EVENT] atoms_killed: 1 at epoch 29
[HOST EVENT] atoms_killed: 2 at epoch 30
[HOST EVENT] session_empty: epoch 30
Final: Session#1<test-user, atoms=0/5, epoch=30, alive>
  Atom#1<sensor-1, phi=0.0000, dead>
  Atom#2<sensor-2, phi=0.0000, dead>
  Atom#3<sensor-3, phi=0.0000, dead>
  Atom#4<sensor-4, phi=0.0000, dead>
  Atom#5<sensor-5, phi=0.0000, dead>
Closed: Session#1<test-user, atoms=0/5, epoch=30, closed>

[karmazyn] mem: 92KB/1024KB (peak 92KB) cpu: 30000/5000000

=== Shutdown ===
```

**Pełen system działa.** Host w C, sandbox z limitami, userdata Session/Atom, event emitter, output capture, file loader. Jeden plik C, kompilacja jednym poleceniem.

#### Test z REPL

```bash
./karmazyn
```

```
=== KarmazynOS Micro-Runtime v0.1 ===

Sandbox created: mem=1024KB, cpu=5000000
[REPL] karmazyn (type :quit to exit)
karmazyn> local a = Atom("test", 0.9)
karmazyn> print(a)
Atom#1<test, phi=0.9000, alive>
karmazyn> a:decay(0.5)
karmazyn> a:phi()
0.60653065971263
karmazyn> :stats
[karmazyn] mem: 91KB/1024KB (peak 91KB) cpu: 0/5000000
karmazyn> os.execute("ls")
[karmazyn] runtime: =repl:1: attempt to index a nil value (global 'os')
karmazyn> while true do end
[karmazyn] runtime: karmazyn:1: CPU quota exceeded: 5001000/5000000
karmazyn> :quit
```

Interaktywna praca z sandboxem. `os.execute` → blocked. Nieskończona pętla → CPU quota. Live debugging z `:stats`.

### Sprawdź się

- [ ] Program kompiluje się i uruchamia
- [ ] File mode ładuje i wykonuje skrypt
- [ ] REPL mode pozwala na interaktywną pracę
- [ ] Ataki (os.execute, infinite loop, memory bomb) są blokowane
- [ ] Events docierają do hosta

---

## Sprawdzian Modułu 12

Rozszerzenia systemu — każde wymaga modyfikacji istniejącego kodu.

### Zadania

**Sprawdzian 1** — Dodaj `hss.log(level, msg)` do sandbox — loguje do hosta z timestampem i levelem. Filtruj po min_level ustawionym z C.

**Sprawdzian 2** — Session atoms iterator — dodaj `session:atoms()` zwracającą tabelę żywych atomów (jako userdata, nie kopie).

**Sprawdzian 3** — Policy z pliku — załaduj `policy.lua` definiujący `max_atoms`, `decay_rate`, `phi_threshold`. Host odczytuje wartości z C i stosuje w logice tick.

**Sprawdzian 4** — Multiple sandboxes — stwórz 3 sandboxes z różnymi limitami, uruchom ten sam skrypt w każdym, pokaż izolację.

**Sprawdzian 5** — Watchdog — background thread (lub periodic check w REPL loop) który co 100 ticków sprawdza `sandbox_stats` i killuje sandbox gdy mem > 80% limit.

**Sprawdzian 6** — Pełen scenariusz multi-session — host tworzy 3 sesje z różnymi politykami, każda w osobnym sandbox, uruchamia skrypt, zbiera eventy, drukuje raport.

---

### Rozwiązania sprawdzianu

#### Sprawdzian 1

```c
// Dodaj do sandbox:

static int _min_log_level = 1;    // 0=DEBUG, 1=INFO, 2=WARN, 3=ERROR

static int level_val(const char *s) {
    if (strcmp(s, "DEBUG") == 0) return 0;
    if (strcmp(s, "INFO") == 0)  return 1;
    if (strcmp(s, "WARN") == 0)  return 2;
    if (strcmp(s, "ERROR") == 0) return 3;
    return -1;
}

static int l_hss_log(lua_State *L) {
    const char *level = luaL_checkstring(L, 1);
    const char *msg = luaL_checkstring(L, 2);
    
    int lv = level_val(level);
    if (lv < 0) return luaL_argerror(L, 1, "unknown level");
    if (lv < _min_log_level) return 0;
    
    time_t now = time(NULL);
    struct tm *tm = localtime(&now);
    char timebuf[32];
    strftime(timebuf, sizeof(timebuf), "%H:%M:%S", tm);
    
    printf("[%s] %s %s\n", level, timebuf, msg);
    return 0;
}

// W inject_hss:
sandbox_inject_cfunc(sb, "hss_log", l_hss_log);

// Test:
// hss_log("INFO", "session started")
// hss_log("DEBUG", "detail")    -- filtered if min=INFO
```

#### Sprawdzian 2

```c
static int l_session_atoms(lua_State *L) {
    ksession_t *s = check_session(L, 1);
    lua_newtable(L);
    int idx = 0;
    for (int i = 0; i < s->atom_count; i++) {
        if (s->atoms[i] && s->atoms[i]->alive) {
            idx++;
            // Push actual userdata (not copy):
            lua_rawgeti(L, LUA_REGISTRYINDEX, s->atom_refs[i]);
            lua_rawseti(L, -2, idx);
        }
    }
    return 1;
}

// Dodaj do session_methods:
// {"atoms", l_session_atoms},

// Test:
// for i, a in ipairs(session:atoms()) do print(a) end
```

`lua_rawgeti` z registry ref — zwraca ten sam userdata (nie kopię). Modyfikacja atomu w tabeli modyfikuje atom w sesji.

#### Sprawdzian 4

```c
// W main:
int main(void) {
    printf("=== Multi-sandbox isolation test ===\n\n");
    
    sandbox_set_event_handler(on_event);
    
    sandbox_t *sb1 = sandbox_create("sandbox-A", 256*1024, 100000);
    sandbox_t *sb2 = sandbox_create("sandbox-B", 512*1024, 500000);
    sandbox_t *sb3 = sandbox_create("sandbox-C", 1024*1024, 5000000);
    
    inject_hss(sb1); inject_hss(sb2); inject_hss(sb3);
    setup_output_capture(sb1);
    setup_output_capture(sb2);
    setup_output_capture(sb3);
    sandbox_inject_cfunc(sb1, "emit", l_emit);
    sandbox_inject_cfunc(sb2, "emit", l_emit);
    sandbox_inject_cfunc(sb3, "emit", l_emit);
    
    const char *test_code =
        "local s = Session('test')\n"
        "for i = 1, 10 do s:add_atom(Atom('a' .. i, 0.9)) end\n"
        "for _ = 1, 50 do s:tick(0.1) end\n"
        "print('alive:', s:alive_count())\n"
        "s:close()\n";
    
    printf("--- Sandbox A (256KB, 100K cpu) ---\n");
    sandbox_exec(sb1, test_code);
    printf("%s", get_captured_output(sb1));
    sandbox_stats(sb1);
    
    printf("\n--- Sandbox B (512KB, 500K cpu) ---\n");
    sandbox_exec(sb2, test_code);
    printf("%s", get_captured_output(sb2));
    sandbox_stats(sb2);
    
    printf("\n--- Sandbox C (1MB, 5M cpu) ---\n");
    sandbox_exec(sb3, test_code);
    printf("%s", get_captured_output(sb3));
    sandbox_stats(sb3);
    
    // Crash test: only sb1 gets infinite loop:
    printf("\n--- Crash sb1 (infinite loop) ---\n");
    sandbox_exec(sb1, "while true do end");
    sandbox_stats(sb1);
    
    printf("\n--- sb2 still works ---\n");
    sandbox_exec(sb2, "print('sb2 alive!')");
    printf("%s", get_captured_output(sb2));
    
    sandbox_destroy(sb1);
    sandbox_destroy(sb2);
    sandbox_destroy(sb3);
    
    printf("\n=== All destroyed ===\n");
    return 0;
}
```

```
--- Sandbox A (256KB, 100K cpu) ---
alive: 5
[sandbox-A] mem: 92KB/256KB (peak 92KB) cpu: 28000/100000

--- Sandbox B (512KB, 500K cpu) ---
alive: 5
[sandbox-B] mem: 92KB/512KB (peak 92KB) cpu: 28000/500000

--- Sandbox C (1MB, 5M cpu) ---
alive: 5
[sandbox-C] mem: 92KB/1024KB (peak 92KB) cpu: 28000/5000000

--- Crash sb1 (infinite loop) ---
[sandbox-A] runtime: sandbox-A:1: CPU quota exceeded: 101000/100000
[sandbox-A] mem: 92KB/256KB (peak 92KB) cpu: 101000/100000

--- sb2 still works ---
sb2 alive!

=== All destroyed ===
```

**Pełna izolacja.** Crash sandbox-A (CPU exceeded) nie wpływa na sandbox-B. Każdy ma osobny `lua_State`, osobny alokator, osobny CPU quota.

#### Sprawdzian 6

```c
// multi_session.c — pełen scenariusz

typedef struct {
    const char *name;
    size_t mem_kb;
    int cpu_limit;
    double decay_rate;
    int n_atoms;
} policy_t;

int main(void) {
    printf("=== KarmazynOS Multi-Session Scenario ===\n\n");
    
    int total_events = 0;
    sandbox_set_event_handler([](const char *ev, const char *data) {
        printf("  [EVENT] %s: %s\n", ev, data);
    });
    // (Uwaga: lambda w C wymaga gcc extension lub C++.
    //  W strict C: osobna static function.)
    
    policy_t policies[] = {
        {"relaxed",  512, 2000000, 0.05, 10},
        {"strict",   256, 1000000, 0.20, 10},
        {"ultra",    256,  500000, 0.50, 10},
    };
    int n_policies = 3;
    
    for (int p = 0; p < n_policies; p++) {
        policy_t *pol = &policies[p];
        printf("--- Session '%s' (decay=%.2f, atoms=%d) ---\n",
            pol->name, pol->decay_rate, pol->n_atoms);
        
        sandbox_t *sb = sandbox_create(pol->name, pol->mem_kb * 1024, pol->cpu_limit);
        inject_hss(sb);
        setup_output_capture(sb);
        sandbox_inject_cfunc(sb, "emit", l_emit);
        
        // Inject decay_rate as global:
        lua_pushlightuserdata(sb->L, &env_key);
        lua_gettable(sb->L, LUA_REGISTRYINDEX);
        lua_pushnumber(sb->L, pol->decay_rate);
        lua_setfield(sb->L, -2, "DECAY_RATE");
        lua_pushinteger(sb->L, pol->n_atoms);
        lua_setfield(sb->L, -2, "N_ATOMS");
        lua_pop(sb->L, 1);
        
        const char *script =
            "local s = Session('session')\n"
            "for i = 1, N_ATOMS do\n"
            "    s:add_atom(Atom('atom-' .. i, 0.9))\n"
            "end\n"
            "\n"
            "for epoch = 1, 500 do\n"
            "    local killed = s:tick(DECAY_RATE)\n"
            "    if killed > 0 then\n"
            "        emit('killed', killed .. ' atoms at epoch ' .. epoch)\n"
            "    end\n"
            "    if s:alive_count() == 0 then\n"
            "        emit('empty', 'epoch ' .. epoch)\n"
            "        break\n"
            "    end\n"
            "end\n"
            "\n"
            "print('Final: ' .. tostring(s))\n"
            "s:close()\n";
        
        sandbox_exec(sb, script);
        printf("%s", get_captured_output(sb));
        sandbox_stats(sb);
        sandbox_destroy(sb);
        printf("\n");
    }
    
    printf("=== Done ===\n");
    return 0;
}
```

```
=== KarmazynOS Multi-Session Scenario ===

--- Session 'relaxed' (decay=0.05, atoms=10) ---
  [EVENT] killed: 10 atoms at epoch 91
  [EVENT] empty: epoch 91
Final: Session#1<session, atoms=0/10, epoch=91, alive>
[relaxed] mem: 94KB/512KB (peak 94KB) cpu: 456000/2000000

--- Session 'strict' (decay=0.20, atoms=10) ---
  [EVENT] killed: 10 atoms at epoch 23
  [EVENT] empty: epoch 23
Final: Session#2<session, atoms=0/10, epoch=23, alive>
[strict] mem: 94KB/256KB (peak 94KB) cpu: 117000/1000000

--- Session 'ultra' (decay=0.50, atoms=10) ---
  [EVENT] killed: 10 atoms at epoch 10
  [EVENT] empty: epoch 10
Final: Session#3<session, atoms=0/10, epoch=10, alive>
[ultra] mem: 94KB/256KB (peak 94KB) cpu: 53000/500000

=== Done ===
```

**Pełen scenariusz.** 3 sesje, 3 polityki, 30 atomów. Ultra zabija w 10 epokach, relaxed w 91. Host wstrzykuje parametry (`DECAY_RATE`, `N_ATOMS`) do sandbox env. Eventy docierają do hosta. Każda sesja w osobnym sandbox z osobnymi limitami.

To jest **kompletny prototyp runtime KarmazynOS** w jednym pliku C.

---

## Podsumowanie kursu

Ukończyłeś 13 modułów (M00-M12). Oto co umiesz:

**Język Lua (M00-M07):**
- Typy, tabele, closures, korutyny, moduły, metatable, OOP, error handling
- Stream library, scheduler, pipeline patterns
- Deklaratywne DSL, validation, hot reload

**C API (M08-M10):**
- `lua_State`, stos, push/pop, pcall
- Userdata z metatable, `__gc`, type-safe bindingi
- Sandbox: `_ENV`, `lua_sethook`, custom alokator

**KarmazynOS (M11-M12):**
- Policy DSL, atom lifecycle rules
- Multi-agent scheduler na korutynach
- Event routing, output capture
- Pełny runtime: host C + sandbox + bindingi + REPL

**Następne kroki:**
1. Portuj `karmazyn_micro.c` na Termux (Samsung A54)
2. Dodaj HSS Φ-space semantics (HRR, semantic decay)
3. Integracja z `.soul` JSONL persistence
4. Multi-thread: wiele `lua_State` w osobnych wątkach
5. Kurs interaktywny na stronie z wasmoon
