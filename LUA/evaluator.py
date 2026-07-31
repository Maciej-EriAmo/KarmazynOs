"""karmazyn_lua.evaluator — montaż na Store; tabela=bąbel; metametody."""

import math

from .values import (
    Store, Bubble, LuaError, LuaFunction, LuaThread, _Return, _Break, _Goto,
    _META_KEY, _TBC_KEY, _keyname, _truthy, _type, _fmt_num, _tostring, _tonumber,
    _arith_num, _to_int, _wrap64, _idiv, _bitshift,
    _BIT_OPS, _ARITH_MM, _is_real_num, _is_concatable, _is_num_or_numstr,
    _bitable, _raw_arith, _NOVAL, _LOOP_GUARD,
    _own_aid, _own_atom, _own_has, _own_keys, _own_unbind, _array_len, lua_env_of,
)
from .lexer import tokenize
from .parser import Parser


# =====================================================================
#  EVALUATOR — montaż na Store, tabela=bąbel, osiągalność przez env_of
# =====================================================================
class Evaluator:
    def __init__(self, store, env_label="lua", root_bubble=None, phi=None):
        """
        store        — karmazyn_kernel.Store (substrat)
        root_bubble  — opcjonalny bąbel sesji Karmin (staje się G + set_root);
                       gdy None: nowy bubble_new(env_label)
        phi          — token zdolności sesji (φ = φ1·φ2 lub bytes/wektor);
                       brak ambient authority — tylko etykieta na ewaluatorze
        """
        self.store = store
        self.phi = phi
        if root_bubble is not None:
            if getattr(root_bubble, "store", None) is not store:
                raise LuaError("root_bubble należy do innego Store")
            self.G = root_bubble
        else:
            self.G = store.bubble_new(env_label)     # globalny zakres = korzeń
        store.set_root(self.G)
        # HAK OSIĄGALNOŚCI (kontrakt substratu): rejestr register_* (name="guest").
        # Ta sama name = zamiana bez stackowania przy remount / :guest.
        # Nie przypisujemy store._env_of / store._extra_reach ręcznie.
        self._out = []
        self._va_stack = [[]]                    # varargi ramek; dno = chunk główny
        # metatabele typów (Lua: string library → mt z __index=string → s:sub())
        self._type_mt = {}                       # typename -> Bubble
        self._modules = {}                       # package.loaded (nazwa -> wartość)
        self._preload = {}                       # package.preload (nazwa -> loader fn)
        self._memory_modules = {}                # host overlay: nazwa -> źródło (edytor)
        self._coro = None                        # bieżąca korutyna (LuaThread|None)
        self._YIELD = object()                   # wartownik builtin yield
        # Lua 5.5 global mode: open (*) vs strict (po pierwszej deklaracji global)
        self._global_open = True
        self._declared_globals = set()
        # budżet sesji (instrukcje / wywołania); None = bez limitu
        self.budget = None
        self._budget_used = 0
        # finalizery __gc i tabele ze słabymi referencjami
        self._finalizers = []                    # lista Bubble oznaczonych do __gc
        self._weak_tables = []                   # tabele z __mode
        self._io_input = []                      # wirtualne linie io.read
        self._active_envs = []                   # stos bąbli wywołań (extra_reach GC)
        # ramki: dict {name, what, fn, scope, source} — najstarsza→0, najnowsza→-1
        self._call_stack = []
        self._cur_line = None                    # linia bieżącej instrukcji (parser "@")
        self._cur_chunk = None                   # nazwa chunka (compile/run)
        self._register_reach_hooks()
        self._install_builtins()

    def _register_reach_hooks(self):
        """Zarejestruj env_of + extra_reach ramek jako guest (bez stackowania)."""
        store = self.store

        def _guest_env_of(v):
            return lua_env_of(v)

        def _guest_extra_reach():
            # Bubble.bindings trzyma publiczne sid (np. "a12"). Substrat w
            # register_extra_reach robi int(getattr(x,"id",x)) — string sid
            # wywala ValueError i rama ginie z reach → locale chunka po
            # collectgarbage stają się "undeclared global". Zwracamy core aid.
            ids = []
            resolve = getattr(store, "_aid", None)
            get_atom = getattr(store, "get_atom", None)
            for env in self._active_envs:
                try:
                    for raw in list(env.bindings.values()):
                        core = None
                        if resolve is not None:
                            try:
                                core = resolve(raw)
                            except Exception:
                                core = None
                        if core is None and get_atom is not None:
                            atom = get_atom(raw)
                            if atom is not None:
                                core = getattr(atom, "_aid", None)
                        if core is None:
                            try:
                                core = int(getattr(raw, "id", raw))
                            except Exception:
                                continue
                        ids.append(int(core))
                except Exception:
                    pass
            return ids

        if hasattr(store, "register_env_of"):
            store.register_env_of(_guest_env_of, name="guest")
        else:
            # stary substrat bez rejestru — ostatni gość wygrywa
            store._env_of = _guest_env_of
        if hasattr(store, "register_extra_reach"):
            store.register_extra_reach(_guest_extra_reach, name="guest")
        else:
            store._extra_reach = _guest_extra_reach

    # ── wbudowane (biała lista; żadnej ambient authority) ──
    def _install_builtins(self):
        def b_print(*args):
            self._out.append("\t".join(self._tostring_mm(a) for a in args))
            return None

        # --- iteratory: zwykłe funkcje biblioteczne na protokole (f, s, ctrl) ---
        def b_next(t, k=None, *_):
            # stateless next: zwraca (klucz, wartość) PO kluczu k, lub nil na końcu.
            if not isinstance(t, Bubble):
                raise LuaError("'next' wymaga tabeli")
            keynames = _own_keys(t, skip={_META_KEY, _TBC_KEY})  # własne pola, pod lock
            if k is None:
                idx = 0
            else:
                try:
                    idx = keynames.index(_keyname(k)) + 1
                except ValueError:
                    raise LuaError("nieprawidłowy klucz do 'next'")
            if idx >= len(keynames):
                return [None]                             # wyczerpane
            atom = _own_atom(t, keynames[idx])
            return [atom.metadata["k"], atom.metadata["v"]]

        def b_pairs(t, *_):
            if not isinstance(t, Bubble):
                raise LuaError("'pairs' wymaga tabeli")
            return [b_next, t, None]                       # (iterator, stan, ctrl)

        def b_inext(t, i=0, *_):
            # iterator całkowity: 1,2,3,... aż do pierwszego nil
            i = (i or 0) + 1
            atom = _own_atom(t, _keyname(i)) if isinstance(t, Bubble) else None
            if atom is None:
                return [None]
            return [i, atom.metadata["v"]]

        def b_ipairs(t, *_):
            if not isinstance(t, Bubble):
                raise LuaError("'ipairs' wymaga tabeli")
            return [b_inext, t, 0]

        # --- metatabele ---
        def b_setmetatable(t, mt=None, *_):
            if not isinstance(t, Bubble):
                raise LuaError("'setmetatable' wymaga tabeli")
            if not (mt is None or isinstance(mt, Bubble)):
                raise LuaError("metatabela musi być tabelą albo nil")
            self._set_metatable(t, mt)
            # __gc: oznacz do finalizacji (gdy tabela stanie się nieosiągalna)
            if mt is not None and self._raw_field(mt, "__gc") is not None:
                if t not in self._finalizers:
                    self._finalizers.append(t)
            # __mode: słabe referencje
            if mt is not None:
                mode = self._raw_field(mt, "__mode")
                if isinstance(mode, str) and mode in ("k", "v", "kv"):
                    if t not in self._weak_tables:
                        self._weak_tables.append(t)
            return t

        def b_getmetatable(t, *_):
            if not isinstance(t, Bubble):
                return None
            return self._get_metatable(t)

        def b_rawget(t, k=None, *_):                        # odczyt BEZ __index
            if not isinstance(t, Bubble):
                raise LuaError("'rawget' wymaga tabeli")
            atom = _own_atom(t, self._env_key(t, k))
            return atom.metadata["v"] if atom is not None else None

        def b_rawset(t, k=None, v=None, *_):                # zapis BEZ __newindex
            if not isinstance(t, Bubble):
                raise LuaError("'rawset' wymaga tabeli")
            kn = self._env_key(t, k)
            existing = _own_aid(t, kn)
            if v is None:
                if existing is not None:
                    _own_unbind(t, kn)
            elif existing is not None:
                self.store.get_atom(existing).metadata["v"] = v
            else:
                atom = self.store.atom_new("field", kn, value=v)
                atom.metadata["k"] = k
                t.bind(kn, atom)
            return t

        # ── obsługa błędów (poziom języka, nie biblioteka) ──
        def b_error(msg=None, level=1, *_):
            # string → lua_value = msg (pcall widzi czysty msg);
            # traceback ma lokalizację chunk:line + stack
            if isinstance(msg, str) or msg is None:
                m = "error" if msg is None else msg
                try:
                    lv = 1 if level is None else int(level)
                except (TypeError, ValueError):
                    lv = 1
                head = self._error_head(m)
                tb = self._format_traceback(head, lv)
                raise LuaError(m, value=m, traceback=tb)
            raise LuaError(_tostring(msg), value=msg)

        def b_assert(*args):
            if not args or not _truthy(args[0]):
                if len(args) > 1:
                    m = args[1]
                    if isinstance(m, str):
                        tb = self._format_traceback(self._error_head(m), 1)
                        raise LuaError(m, value=m, traceback=tb)
                    raise LuaError(_tostring(m), value=m)
                m = "assertion failed!"
                raise LuaError(m, value=m, traceback=self._format_traceback(self._error_head(m), 1))
            return list(args)                            # sukces: zwraca WSZYSTKIE argumenty

        def b_pcall(f=None, *args):
            try:
                return [True] + self._call(f, list(args))
            except LuaError as e:
                return [False, e.lua_value]
            except RecursionError:
                return [False, "za głęboka rekurencja"]
            except Exception as ex:                      # nigdy nie wywal hosta
                return [False, f"błąd wewnętrzny: {ex}"]

        def b_xpcall(f=None, handler=None, *args):
            try:
                return [True] + self._call(f, list(args))
            except LuaError as e:
                # handler dostaje obiekt błędu; może wołać debug.traceback
                hr = self._call(handler, [e.lua_value])
                return [False] + (hr if hr else [None])
            except RecursionError:
                hr = self._call(handler, ["za głęboka rekurencja"])
                return [False] + (hr if hr else [None])
            except Exception as ex:
                hr = self._call(handler, [f"błąd wewnętrzny: {ex}"])
                return [False] + (hr if hr else [None])

        def b_traceback(a=None, b=None, c=None, *_):
            # debug.traceback([thread,] [message [, level]])
            msg, level = a, b
            if isinstance(a, LuaThread):
                msg, level = b, c
            try:
                lv = 1 if level is None else int(level)
            except (TypeError, ValueError):
                lv = 1
            return self._format_traceback(msg, lv)

        def b_select(n=None, *rest):
            if n == "#":
                return len(rest)
            if isinstance(n, (int, float)) and not isinstance(n, bool):
                i = int(n)
                if i < 0:
                    i = len(rest) + i + 1                 # ujemny: od końca
                if i < 1:
                    raise LuaError("select: indeks poza zakresem")
                return list(rest[i - 1:])                 # od i-tego argumentu dalej
            raise LuaError("select: oczekiwano liczby lub '#'")

        def b_rawequal(a=None, b=None, *_):
            return self._eq(a, b)                         # równość bez metametod

        def b_rawlen(v=None, *_):
            if isinstance(v, str):
                return len(v)
            if isinstance(v, Bubble):
                return _array_len(v)
            raise LuaError("rawlen: oczekiwano tabeli lub stringa")

        builtins = {
            "print": b_print,
            "type": lambda v=None, *_: _type(v),
            "tostring": lambda v=None, *_: self._tostring_mm(v),
            "tonumber": lambda v=None, *_: _tonumber(v),
            "next": b_next,
            "pairs": b_pairs,
            "ipairs": b_ipairs,
            "setmetatable": b_setmetatable,
            "getmetatable": b_getmetatable,
            "rawget": b_rawget,
            "rawset": b_rawset,
            "rawequal": b_rawequal,
            "rawlen": b_rawlen,
            "error": b_error,
            "assert": b_assert,
            "pcall": b_pcall,
            "xpcall": b_xpcall,
            "select": b_select,
        }

        # ── load (tylko tekst; zero FS) ──
        def b_load(chunk=None, chunkname=None, mode=None, env=None, *_):
            # mode: nil/"t"/"bt" OK; samo "b" → błąd (brak bytecode)
            if mode is not None and isinstance(mode, str):
                if "b" in mode and "t" not in mode:
                    return [None, "attempt to load a binary chunk (not supported)"]
            if not isinstance(chunk, str):
                return [None, "chunk must be a string"]
            cname = chunkname if isinstance(chunkname, str) and chunkname else "=(load)"
            try:
                toks = tokenize(chunk)
                block = Parser(toks).parse_chunk()
            except LuaError as e:
                return [None, f"{cname}: {_tostring(e.lua_value)}"]
            except Exception as ex:
                return [None, f"{cname}: {ex}"]
            env_tbl = env if isinstance(env, Bubble) else self.G
            wrap = self.store.bubble_new("load", parent=None)
            ea = self.store.atom_new("var", "_ENV", value=env_tbl)
            wrap.bind("_ENV", ea)
            fn = LuaFunction(["..."], block, wrap, name=cname)
            return fn

        def b_loadstring(chunk=None, chunkname=None, *_):
            return b_load(chunk, chunkname, "t", None)

        # ── require / package.searchers ──
        # Domyślnie: preload w pamięci (zero path gościa). Host może dodać
        # searchers[2] = project (czyta pliki pod rootem projektu — nie ambient FS).
        def b_searcher_preload(modname=None, *_):
            if not isinstance(modname, str):
                return None
            loader = self._preload.get(modname)
            if loader is not None:
                return [loader, modname]                 # loader + extra (jak Lua)
            return "\n\tno field package.preload['" + modname + "']"

        def b_require(modname=None, *_):
            if not isinstance(modname, str):
                raise LuaError("require: oczekiwano nazwy modułu (string)")
            if modname in self._modules:
                return self._modules[modname]
            errs = []
            # package.searchers: sekwencja 1..n
            searchers = self._package_searchers
            i = 1
            while True:
                searcher = self._table_get(searchers, i)
                if searcher is None:
                    break
                res = self._call(searcher, [modname])
                if not res:
                    i += 1
                    continue
                first = res[0]
                if isinstance(first, str):
                    errs.append(first)
                elif first is not None and (
                    isinstance(first, LuaFunction) or callable(first)
                ):
                    loader = first
                    extra = res[1:]
                    self._modules[modname] = True       # anty-cykl
                    r = self._call(loader, [modname] + list(extra))
                    mod = r[0] if r else None
                    if mod is None:
                        mod = True
                    self._modules[modname] = mod
                    return mod
                i += 1
            msg = "module '" + modname + "' not found:"
            if errs:
                msg += "".join(errs)
            else:
                msg += "\n\tno searchers"
            raise LuaError(msg)

        builtins["load"] = b_load
        builtins["loadstring"] = b_loadstring
        builtins["require"] = b_require

        # ── coroutine ──
        def b_create(f=None, *_):
            if not (isinstance(f, LuaFunction) or callable(f)):
                raise LuaError("coroutine.create: oczekiwano funkcji")
            return LuaThread(f)

        def b_status(co=None, *_):
            if not isinstance(co, LuaThread):
                raise LuaError("coroutine.status: oczekiwano thread")
            if getattr(co, "closed", False):
                return "dead"
            if co is self._coro and co.status == "running":
                return "running"
            return co.status

        def b_running(*_):
            if self._coro is None:
                return [None, False]                     # main thread
            return [self._coro, True]

        def b_isyieldable(*_):
            return self._coro is not None

        def b_close(co=None, *_):
            if not isinstance(co, LuaThread):
                raise LuaError("coroutine.close: oczekiwano thread")
            if co is self._coro:
                raise LuaError("cannot close a running coroutine")
            if getattr(co, "closed", False) or co.status == "dead":
                co.closed = True
                co.status = "dead"
                return [True]
            co.closed = True
            co.status = "dead"
            co.gen = None
            return [True]

        def b_yield(*args):
            # obsłużone w _call_gen przez wartownik; tu tylko błąd sync
            raise LuaError("attempt to yield from outside a coroutine")

        def b_resume(co=None, *args):
            if not isinstance(co, LuaThread):
                return [False, "coroutine expected"]
            if getattr(co, "closed", False) or co.status == "dead":
                return [False, "cannot resume dead coroutine"]
            if co.status == "running":
                return [False, "cannot resume running coroutine"]
            prev = self._coro
            self._coro = co
            co.status = "running"
            try:
                if co.gen is None:
                    co.gen = self._call_gen(co.fn, list(args))
                    try:
                        y = next(co.gen)
                        co.status = "suspended"
                        return [True] + (y if isinstance(y, list) else [y])
                    except StopIteration as e:
                        co.status = "dead"
                        r = e.value
                        if r is None:
                            r = []
                        elif not isinstance(r, list):
                            r = [r]
                        return [True] + r
                else:
                    try:
                        y = co.gen.send(list(args))
                        co.status = "suspended"
                        return [True] + (y if isinstance(y, list) else [y])
                    except StopIteration as e:
                        co.status = "dead"
                        r = e.value
                        if r is None:
                            r = []
                        elif not isinstance(r, list):
                            r = [r]
                        return [True] + r
            except LuaError as e:
                co.status = "dead"
                return [False, e.lua_value]
            except Exception as ex:
                co.status = "dead"
                return [False, str(ex)]
            finally:
                self._coro = prev

        def b_wrap(f=None, *_):
            if not (isinstance(f, LuaFunction) or callable(f)):
                raise LuaError("coroutine.wrap: oczekiwano funkcji")
            co = LuaThread(f)

            def wrapper(*args):
                res = b_resume(co, *args)
                if not res[0]:
                    raise LuaError(res[1] if len(res) > 1 else "coroutine error")
                return res[1:] if len(res) > 1 else []
            return wrapper

        co_tbl = self.store.bubble_new("table")
        for n, fn in (
            ("create", b_create), ("resume", b_resume), ("yield", b_yield),
            ("status", b_status), ("wrap", b_wrap), ("running", b_running),
            ("isyieldable", b_isyieldable), ("close", b_close),
        ):
            a = self.store.atom_new("builtin", "co." + n, value=fn)
            # bind via table field helpers after G exists — use raw bind
            ka = self.store.atom_new("field", "s:" + n, value=fn)
            ka.metadata["k"] = n
            co_tbl.bind("s:" + n, ka)
        # yield as special for _call_gen: store on self
        self._yield_fn = b_yield

        for name, fn in builtins.items():
            atom = self.store.atom_new("builtin", name, value=fn)
            self.G.bind(name, atom)
        # package: loaded, preload, searchers (bez path/cpath/FS)
        pkg = self.store.bubble_new("table")
        loaded = self.store.bubble_new("table")
        preload = self.store.bubble_new("table")
        searchers = self.store.bubble_new("table")
        self._package_searchers = searchers

        def b_preload_index(t, k, *_):
            if isinstance(k, str) and k in self._preload:
                return self._preload[k]
            return None
        def b_preload_newindex(t, k, v, *_):
            if isinstance(k, str):
                if v is None:
                    self._preload.pop(k, None)
                else:
                    self._preload[k] = v
            return None
        def b_loaded_index(t, k, *_):
            if isinstance(k, str) and k in self._modules:
                return self._modules[k]
            return None
        def b_loaded_newindex(t, k, v, *_):
            if isinstance(k, str):
                if v is None:
                    self._modules.pop(k, None)
                else:
                    self._modules[k] = v
            return None
        pmt = self.store.bubble_new("table")
        lmt = self.store.bubble_new("table")
        for mt, idx, nidx in (
            (pmt, b_preload_index, b_preload_newindex),
            (lmt, b_loaded_index, b_loaded_newindex),
        ):
            ia = self.store.atom_new("field", "s:__index", value=idx)
            ia.metadata["k"] = "__index"
            mt.bind("s:__index", ia)
            na = self.store.atom_new("field", "s:__newindex", value=nidx)
            na.metadata["k"] = "__newindex"
            mt.bind("s:__newindex", na)
        self._set_metatable(preload, pmt)
        self._set_metatable(loaded, lmt)
        # searchers[1] = preload
        sa = self.store.atom_new("field", "i:1", value=b_searcher_preload)
        sa.metadata["k"] = 1
        searchers.bind("i:1", sa)
        for n, v in (
            ("loaded", loaded), ("preload", preload), ("searchers", searchers),
        ):
            a = self.store.atom_new("field", "s:" + n, value=v)
            a.metadata["k"] = n
            pkg.bind("s:" + n, a)
        pa = self.store.atom_new("lib", "package", value=pkg)
        self.G.bind("package", pa)
        # debug.* — subset read/mutate locale Lua; zero Store/host escape
        def b_getinfo(level_or_fn=None, what=None, *_):
            return self._debug_getinfo(level_or_fn, what)

        def b_getlocal(level=None, index=None, *_):
            return self._debug_getlocal(level, index)

        def b_setlocal(level=None, index=None, value=None, *_):
            return self._debug_setlocal(level, index, value)

        def b_getupvalue(fn=None, index=None, *_):
            return self._debug_getupvalue(fn, index)

        def b_setupvalue(fn=None, index=None, value=None, *_):
            return self._debug_setupvalue(fn, index, value)

        dbg = self.store.bubble_new("table")
        for n, fn in (
            ("traceback", b_traceback),
            ("getinfo", b_getinfo),
            ("getlocal", b_getlocal),
            ("setlocal", b_setlocal),
            ("getupvalue", b_getupvalue),
            ("setupvalue", b_setupvalue),
        ):
            ka = self.store.atom_new("field", "s:" + n, value=fn)
            ka.metadata["k"] = n
            dbg.bind("s:" + n, ka)
        da = self.store.atom_new("lib", "debug", value=dbg)
        self.G.bind("debug", da)
        # coroutine table
        ca = self.store.atom_new("lib", "coroutine", value=co_tbl)
        self.G.bind("coroutine", ca)
        # _G = tabela globali (G); _VERSION — etykieta zgodności (podzbiór 5.5)
        g_atom = self.store.atom_new("lib", "_G", value=self.G)
        self.G.bind("_G", g_atom)
        ver_atom = self.store.atom_new("lib", "_VERSION", value="Lua 5.5")
        self.G.bind("_VERSION", ver_atom)
        # _ENV = G (chunk default); local _ENV = t zmienia wolne nazwy w zakresie
        env_atom = self.store.atom_new("lib", "_ENV", value=self.G)
        self.G.bind("_ENV", env_atom)
        # predeklaruj wbudowane jako legalne globalne (tryb strict)
        from .values import _own_keys as _ok
        for n in _ok(self.G):
            if not n.startswith("@"):
                self._declared_globals.add(n)

        # ── wirtualne io (kanał sesji, zero FS) ──
        def b_io_write(*args):
            self._out.append("".join(_tostring(a) for a in args))
            return None

        def b_io_read(fmt=None, *_):
            # czyta z kolejki _io_input (wstrzykniętej przez host/mount)
            if self._io_input:
                return self._io_input.pop(0)
            return None

        def b_io_flush(*_):
            return None

        io_tbl = self.store.bubble_new("table")
        for n, fn in (("write", b_io_write), ("read", b_io_read), ("flush", b_io_flush)):
            a = self.store.atom_new("field", "s:" + n, value=fn)
            a.metadata["k"] = n
            io_tbl.bind("s:" + n, a)
        # stdout/stderr/stdin jako tabele-uchwyty z write/read
        for handle_name, writeable in (("stdout", True), ("stderr", True), ("stdin", False)):
            h = self.store.bubble_new("table")
            if writeable:
                a = self.store.atom_new("field", "s:write", value=b_io_write)
                a.metadata["k"] = "write"
                h.bind("s:write", a)
            else:
                a = self.store.atom_new("field", "s:read", value=b_io_read)
                a.metadata["k"] = "read"
                h.bind("s:read", a)
            ha = self.store.atom_new("field", "s:" + handle_name, value=h)
            ha.metadata["k"] = handle_name
            io_tbl.bind("s:" + handle_name, ha)
        ia = self.store.atom_new("lib", "io", value=io_tbl)
        self.G.bind("io", ia)
        self._declared_globals.add("io")

        # collectgarbage — mapowanie na gc_step / settle substratu (nie omija T×reach)
        def b_collectgarbage(opt=None, arg=None, *_):
            if opt is None or opt == "collect":
                self.gc_step()
                return 0
            if opt == "count":
                # KB-ish: atomy osiągalne z G + live envs (nie cały heap silnika aN)
                return self._guest_live_atom_count() / 1024.0
            if opt == "isrunning":
                return True
            if opt == "step":
                # jeden krok settle + weak/__gc (arg ignorowany lub liczba ticków)
                try:
                    n = 1 if arg is None else max(1, int(arg))
                except (TypeError, ValueError):
                    n = 1
                try:
                    self.store.settle(n)
                except Exception:
                    pass
                self.gc_step()
                return True
            if opt == "stop" or opt == "restart" or opt == "setpause" or opt == "setstepmul":
                # no-op kompatybilny — GC steruje substrat
                return 0
            return 0
        cga = self.store.atom_new("builtin", "collectgarbage", value=b_collectgarbage)
        self.G.bind("collectgarbage", cga)
        self._declared_globals.add("collectgarbage")

    def _guest_live_atom_count(self):
        """Liczba atomów w grafie gościa (G + active envs + domknięcia) — metryka count."""
        seen_bub = set()
        aids = set()
        stack = [self.G]
        for env in self._active_envs:
            if isinstance(env, Bubble):
                stack.append(env)
        while stack:
            b = stack.pop()
            bid = id(b)
            if bid in seen_bub:
                continue
            seen_bub.add(bid)
            for kn in _own_keys(b):
                atom = _own_atom(b, kn)
                if atom is None:
                    continue
                aids.add(getattr(atom, "id", id(atom)))
                v = atom.metadata.get("v")
                if isinstance(v, Bubble):
                    stack.append(v)
                elif isinstance(v, LuaFunction) and isinstance(getattr(v, "env", None), Bubble):
                    stack.append(v.env)
        return float(len(aids))

    def gc_step(self):
        """Krok GC gościa: słabe tabele + finalizery __gc + settle substratu.

        1) wyczyść wpisy weak (klucz/wartość-tabela nieosiągalna z G + live envs)
        2) settle store (reach-GC atomów)
        3) wywołaj __gc dla finalizerów, których tabela zginęła z reach
        """
        # reach z korzeni
        try:
            self.store.settle(1)
        except Exception:
            pass
        # weak clear
        still_weak = []
        for tb in self._weak_tables:
            if not isinstance(tb, Bubble):
                continue
            mt = self._get_metatable(tb)
            mode = self._raw_field(mt, "__mode") if mt else None
            if not isinstance(mode, str):
                continue
            weak_k = "k" in mode
            weak_v = "v" in mode
            keys = _own_keys(tb, skip={_META_KEY, _TBC_KEY})
            for kn in keys:
                atom = _own_atom(tb, kn)
                if atom is None:
                    continue
                k = atom.metadata.get("k")
                v = atom.metadata.get("v")
                drop = False
                if weak_k and isinstance(k, Bubble) and not self._bubble_reachable(k):
                    drop = True
                if weak_v and isinstance(v, Bubble) and not self._bubble_reachable(v):
                    drop = True
                if drop:
                    _own_unbind(tb, kn)
            still_weak.append(tb)
        self._weak_tables = still_weak
        # finalizers — błędy nie giną w ciszy (zbierane; po pętli raport)
        remain = []
        gc_errors = []
        for tb in self._finalizers:
            if self._bubble_reachable(tb):
                remain.append(tb)
                continue
            mt = self._get_metatable(tb)
            if mt is None:
                continue
            gc = self._raw_field(mt, "__gc")
            if gc is not None:
                try:
                    self._call(gc, [tb])
                except LuaError as e:
                    gc_errors.append(e)
                except Exception as ex:
                    gc_errors.append(LuaError(f"__gc: {ex}"))
        self._finalizers = remain
        try:
            self.store.settle(50)
        except Exception:
            pass
        if gc_errors:
            # nie zrywaj sesji w środku vacuum — ostatni błąd do hosta / kolejnego pcall
            self._last_gc_error = gc_errors[-1]
            # widoczne w stdout sesji (diagnostyka)
            for e in gc_errors:
                self._out.append("[__gc error] " + _tostring(e.lua_value))

    def _bubble_reachable(self, tb):
        """Czy bąbel osiągalny z G, store.roots oraz live call/block envs."""
        if tb is None or not isinstance(tb, Bubble):
            return False
        if tb is self.G:
            return True
        roots = list(getattr(self.store, "roots", None) or [])
        stack = [self.G]
        for r in roots:
            if isinstance(r, Bubble):
                stack.append(r)
        for env in self._active_envs:
            if isinstance(env, Bubble):
                stack.append(env)
        seen = set()
        while stack:
            b = stack.pop()
            bid = id(b)
            if bid in seen:
                continue
            seen.add(bid)
            if b is tb:
                return True
            for kn in _own_keys(b):
                atom = _own_atom(b, kn)
                if atom is None:
                    continue
                v = atom.metadata.get("v")
                if isinstance(v, Bubble):
                    stack.append(v)
                elif isinstance(v, LuaFunction) and isinstance(getattr(v, "env", None), Bubble):
                    stack.append(v.env)
        return False

    # ── kontrakt boota/shell: env == G (korzeń sesji) ──
    @property
    def env(self):
        """Alias do G — KarmazynShell i :env oczekują evaluator.env (Bubble)."""
        return self.G

    def register_preload(self, name, source, chunkname=None):
        """Zarejestruj narzędzie/moduł w package.preload[name].

        source: str (chunk Lua zwracający moduł) albo callable (loader hosta).
        Po rejestracji: require(name) ładuje raz i cache'uje w package.loaded.
        """
        if not isinstance(name, str) or not name:
            raise LuaError("register_preload: oczekiwano niepustej nazwy")
        if callable(source) and not isinstance(source, str):
            self._preload[name] = source
            return name
        if not isinstance(source, str):
            raise LuaError("register_preload: source = string chunk lub callable")
        cname = chunkname if isinstance(chunkname, str) and chunkname else f"@{name}"
        try:
            toks = tokenize(source)
            block = Parser(toks).parse_chunk()
        except LuaError:
            raise
        except Exception as ex:
            raise LuaError(f"{cname}: {ex}")
        wrap = self.store.bubble_new("preload", parent=None)
        ea = self.store.atom_new("var", "_ENV", value=self.G)
        wrap.bind("_ENV", ea)
        body = LuaFunction(["..."], block, wrap, name=cname)

        def loader(modname=None, *_):
            r = self._call(body, [modname] if modname is not None else [])
            if not r:
                return True
            return r[0] if r[0] is not None else True

        self._preload[name] = loader
        # wyczyszczony cache — ponowny require załaduje nową wersję
        self._modules.pop(name, None)
        return name

    # ── publiczne: chunk z hosta (pliki / project searcher) ──
    def compile_chunk(self, source, chunkname="=(chunk)", env=None):
        """Skompiluj tekstowy chunk do LuaFunction. Rzuca LuaError przy błędzie parse.

        env: tabela _ENV dla chunka (domyślnie G). Host / searcher projektowy —
        nie dają gościowi dostępu do FS; źródło dostarcza host.
        Format błędu: chunkname:line:col: message (gdy parser podał linię).
        """
        if not isinstance(source, str):
            raise LuaError("compile_chunk: oczekiwano stringa")
        cname = chunkname if isinstance(chunkname, str) and chunkname else "=(chunk)"
        try:
            toks = tokenize(source)
            block = Parser(toks).parse_chunk()
        except LuaError as e:
            msg = _tostring(e.lua_value)
            # już sformatowane jako name:… albo line:col:…
            if msg.startswith(cname):
                raise
            # line:col: message → @chunk:line:col: message
            raise LuaError(f"{cname}:{msg}", value=f"{cname}:{msg}") from e
        except Exception as ex:
            raise LuaError(f"{cname}: {ex}") from ex
        env_tbl = env if isinstance(env, Bubble) else self.G
        wrap = self.store.bubble_new("chunk", parent=None)
        ea = self.store.atom_new("var", "_ENV", value=env_tbl)
        wrap.bind("_ENV", ea)
        return LuaFunction(["..."], block, wrap, name=cname)

    def run_source(self, source, chunkname="=(chunk)", args=None, env=None,
                   as_module=False, clear_out=None):
        """Uruchom chunk (host wpuszcza źródło). Zwraca listę wartości return.

        as_module=True: jak plik require — pierwsza wartość albo True gdy brak return.
        print() ląduje w self._out. Błędy → LuaError (host decyduje o formatowaniu).
        clear_out: domyślnie True dla entrypointu, False dla as_module (require).
        """
        if clear_out is None:
            clear_out = not as_module
        if clear_out:
            self._out = []
        prev_chunk = self._cur_chunk
        self._cur_chunk = chunkname if isinstance(chunkname, str) else prev_chunk
        try:
            fn = self.compile_chunk(source, chunkname=chunkname, env=env)
            ret = self._call(fn, list(args) if args is not None else [])
            if as_module:
                if not ret:
                    return True
                return ret[0] if ret[0] is not None else True
            return ret
        except LuaError as e:
            # pcall/xpcall: czysty lua_value; nieprzechwycony: zachowaj traceback
            # (z chunk:line w nagłówku). Nie nadpisuj value prefiksem lokalizacji.
            if getattr(e, "traceback", None):
                raise
            msg = _tostring(e.lua_value)
            prefix = self._loc_prefix()
            if prefix and isinstance(msg, str) and prefix not in msg[: max(8, len(prefix) + 4)]:
                if not (isinstance(chunkname, str) and msg.startswith(chunkname)):
                    head = prefix + msg
                    raise LuaError(
                        msg,
                        value=e.lua_value,
                        traceback=self._format_traceback(head, 1),
                    ) from e
            raise
        finally:
            self._cur_chunk = prev_chunk

    def run_file(self, path, chunkname=None, args=None, as_module=False, clear_out=None):
        """Host: odczytaj plik z dysku i run_source. Gość nigdy nie woła tego sam."""
        import os
        if not isinstance(path, str) or not path:
            raise LuaError("run_file: oczekiwano ścieżki")
        try:
            with open(path, encoding="utf-8") as f:
                src = f.read()
        except OSError as e:
            raise LuaError(f"run_file: nie można odczytać {path!r}: {e}") from e
        cname = chunkname
        if not cname:
            cname = "@" + os.path.basename(path)
        return self.run_source(
            src, chunkname=cname, args=args, as_module=as_module, clear_out=clear_out,
        )

    def format_run_result(self, ret=None, err=None):
        """Złóż wynik jak eval_line: stdout (_out) + return values / błąd."""
        if err is not None:
            if isinstance(err, LuaError):
                if getattr(err, "traceback", None):
                    return "blad: " + err.traceback
                return "blad: " + _tostring(err.lua_value)
            return f"blad: {type(err).__name__}: {err}"
        parts = []
        if self._out:
            parts.append("\n".join(self._out))
        if ret:
            parts.append("\t".join(_tostring(v) for v in ret))
        return "\n".join(p for p in parts if p)

    # ── publiczne: jedna linia/chunk -> string ──
    def eval_line(self, line):
        """Jedna linia REPL: izolowany scope (jak chunk), _ENV=G — nie brudzi G localami.

        P0-2: wcześniej locale lądowały na G i wyciekały między liniami.
        """
        self._out = []
        # scope jak compile_chunk: parent=None, wolne nazwy → _ENV (=G)
        scope = self.store.bubble_new("stdin", parent=None)
        ea = self.store.atom_new("var", "_ENV", value=self.G)
        scope.bind("_ENV", ea)
        stdin_fr = {
            "name": "stdin", "what": "main", "fn": None,
            "scope": scope, "source": "=stdin", "currentline": None,
        }
        self._call_stack.append(stdin_fr)
        self._push_live_env(scope)
        display = _NOVAL
        try:
            toks = tokenize(line)
            block = Parser(toks).parse_chunk()
            i = 0
            jumps = 0
            while i < len(block):
                stmt = block[i]
                try:
                    val = self._exec_stmt(stmt, scope)
                    i += 1
                except _Goto as g:
                    # etykieta na poziomie chunka? (jak _exec_block)
                    for j, s in enumerate(block):
                        _ln, core = self._stmt_core(s)
                        if core[0] == "label" and core[1] == g.name:
                            i = j + 1
                            break
                    else:
                        raise
                    jumps += 1
                    if jumps > _LOOP_GUARD:
                        raise LuaError("goto: przekroczono limit skoków")
                    continue
                # tylko gołe wyrażenie pokazuje wartość (nawet nil); reszta = pusto
                _ln, core = self._stmt_core(stmt)
                display = val if core[0] == "exprstat" else _NOVAL
        except _Return as r:
            return "\t".join(_tostring(v) for v in r.value) if r.value else ""
        except _Break:
            return "blad: 'break' poza pętlą"
        except _Goto as g:
            return f"blad: goto: nie znaleziono etykiety '{g.name}'"
        except LuaError as e:
            # nieprzechwycony błąd: pokaż traceback jeśli jest
            if getattr(e, "traceback", None):
                return "blad: " + e.traceback
            msg = _tostring(e.lua_value)
            prefix = self._loc_prefix()
            if prefix and isinstance(msg, str) and not msg.startswith(prefix.rstrip(": ")):
                if not (msg.startswith("@") or (len(msg) > 2 and msg[0].isdigit())):
                    msg = prefix + msg
            return "blad: " + msg
        except RecursionError:
            return "blad: za głęboka rekurencja"
        except Exception as e:                       # nigdy nie leci w hosta
            return f"blad: {type(e).__name__}: {e}"
        finally:
            self._pop_live_env(scope)
            if self._call_stack and self._call_stack[-1] is stdin_fr:
                self._call_stack.pop()
        if self._out:
            return "\n".join(self._out)
        if display is _NOVAL:
            return ""
        return _tostring(display)

    # ── to-be-closed + zakres ─────────────────────────────────────────
    def _tbc_list(self, env):
        atom = _own_atom(env, _TBC_KEY)
        if atom is None:
            lst = []
            a = self.store.atom_new("tbc", _TBC_KEY, value=lst)
            env.bind(_TBC_KEY, a)
            return lst
        return atom.metadata["v"]

    def _close_env(self, env):
        """Wywołaj __close na zmiennych <close> (odwrotna kolejność)."""
        atom = _own_atom(env, _TBC_KEY)
        if atom is None:
            return
        lst = list(atom.metadata.get("v") or [])
        atom.metadata["v"] = []
        for va in reversed(lst):
            v = va.metadata.get("v")
            if v is None or v is False:
                continue
            if not isinstance(v, Bubble):
                raise LuaError("zmienna <close> musi mieć __close (tabela)")
            mm = self._metamethod(v, "__close")
            if mm is None:
                raise LuaError("zmienna <close> bez metametody __close")
            try:
                self._call(mm, [v])
            except LuaError:
                raise
            except Exception as ex:
                raise LuaError(f"__close: {ex}")

    @staticmethod
    def _stmt_core(stmt):
        """Zdejmij ("@", line, stmt) → (line|None, real_stmt)."""
        if isinstance(stmt, tuple) and stmt and stmt[0] == "@":
            return stmt[1], stmt[2]
        return None, stmt

    def _loc_prefix(self):
        """Prefiks lokalizacji do komunikatu błędu runtime."""
        parts = []
        if self._cur_chunk:
            parts.append(str(self._cur_chunk))
        if self._cur_line is not None:
            parts.append(str(self._cur_line))
        if not parts:
            return ""
        return ":".join(parts) + ": "

    def _error_head(self, msg):
        """Pierwsza linia błędu: opcjonalnie chunk:line: message (dla tracebacku)."""
        prefix = self._loc_prefix()
        m = msg if isinstance(msg, str) else _tostring(msg)
        if prefix and prefix not in m[: max(8, len(prefix) + 4)]:
            return prefix + m
        return m

    def _touch_frame_line(self, line):
        """Aktualizuj linię na szczycie stacka (debug + traceback)."""
        if line is None:
            return
        self._cur_line = line
        if self._call_stack and isinstance(self._call_stack[-1], dict):
            self._call_stack[-1]["currentline"] = line

    def _push_live_env(self, env):
        """Zarejestruj bąbel zakresu w extra_reach (call + bloki do/for/if/…)."""
        if env is not None:
            self._active_envs.append(env)

    def _pop_live_env(self, env):
        if self._active_envs and self._active_envs[-1] is env:
            self._active_envs.pop()

    def _block_env(self, parent, label):
        """Nowy bąbel bloku + extra_reach na czas życia bloku (caller: try/finally pop)."""
        inner = self.store.bubble_new(label, parent=parent)
        self._push_live_env(inner)
        return inner

    def _exec_block(self, block, env):
        last = None
        i = 0
        guard = 0
        try:
            while i < len(block):
                stmt = block[i]
                try:
                    last = self._exec_stmt(stmt, env)
                    i += 1
                except _Goto as g:
                    # skocz do ::etykiety:: w TYM bloku; brak -> propaguj (close)
                    for j, s in enumerate(block):
                        _ln, core = self._stmt_core(s)
                        if core[0] == "label" and core[1] == g.name:
                            i = j + 1
                            break
                    else:
                        self._close_env(env)
                        raise
                    guard += 1
                    if guard > _LOOP_GUARD:
                        raise LuaError("goto: przekroczono limit skoków")
                except (_Return, _Break):
                    self._close_env(env)
                    raise
            self._close_env(env)
            return last
        except (_Return, _Break, _Goto):
            raise

    def _get_env_table(self, env):
        """Wartość _ENV widoczna w env (domyślnie G)."""
        atom = env.lookup("_ENV")
        if atom is not None:
            v = atom.metadata["v"]
            if isinstance(v, Bubble):
                return v
        return self.G

    def _check_global_name(self, name, writing=False):
        """Lua 5.5: w trybie strict wolne nazwy muszą być zadeklarowane global."""
        if self._global_open:
            return
        if name in self._declared_globals:
            return
        # wbudowane / liby zainstalowane przy starcie — zawsze legalne
        if _own_has(self.G, name):
            self._declared_globals.add(name)
            return
        raise LuaError(f"undeclared global '{name}'")

    def _budget_tick(self, n=1):
        if self.budget is None:
            return
        self._budget_used += n
        if self._budget_used > self.budget:
            raise LuaError(f"session budget exceeded ({self.budget})")

    def _exec_stmt(self, stmt, env):
        self._budget_tick(1)
        line, stmt = self._stmt_core(stmt)
        if line is not None:
            self._touch_frame_line(line)
        tag = stmt[0]
        if tag == "local":
            # AST: ("local", names, inits, attrs) — attrs opcjonalne (wstecz: 3-el.)
            names, inits = stmt[1], stmt[2]
            attrs = stmt[3] if len(stmt) > 3 else [None] * len(names)
            vals = self._eval_list(inits, env)
            for i, name in enumerate(names):
                v = vals[i] if i < len(vals) else None
                atom = self.store.atom_new("var", name, value=v)
                attr = attrs[i] if i < len(attrs) else None
                if attr == "const":
                    atom.metadata["const"] = True
                if attr == "close":
                    atom.metadata["const"] = True        # close ⇒ read-only
                    atom.metadata["close"] = True
                    if v is not None and v is not False:
                        if not isinstance(v, Bubble):
                            raise LuaError("wartość <close> musi być tabelą z __close")
                        if self._metamethod(v, "__close") is None:
                            raise LuaError("wartość <close> bez __close")
                    self._tbc_list(env).append(atom)
                env.bind(name, atom)
            return None
        if tag == "global":
            # deklaracja global → tryb strict (void implicit global *)
            self._global_open = False
            names, inits = stmt[1], stmt[2]
            attrs = stmt[3] if len(stmt) > 3 else [None] * len(names)
            et = self._get_env_table(env)
            vals = self._eval_list(inits, env) if inits else []
            for i, name in enumerate(names):
                self._declared_globals.add(name)
                if inits:
                    v = vals[i] if i < len(vals) else None
                    if self._table_get(et, name) is not None:
                        raise LuaError(f"global '{name}' już zdefiniowane")
                    self._table_set(et, name, v)
                if i < len(attrs) and attrs[i] == "const":
                    kn = self._env_key(et, name)
                    aid = _own_aid(et, kn)
                    if aid is not None:
                        self.store.get_atom(aid).metadata["const"] = True
            return None
        if tag == "global_star":
            # global * — z powrotem tryb otwarty (jak preambuła chunka)
            self._global_open = True
            return None
        if tag == "localfunc":
            # 'local function f' — wiąż NAJPIERW (by rekurencja widziała siebie)
            _, name, params, body = stmt
            atom = self.store.atom_new("var", name, value=None)
            env.bind(name, atom)
            atom.metadata["v"] = LuaFunction(params, body, env, name)
            return None
        if tag == "return":
            raise _Return(self._eval_list(stmt[1], env))
        if tag == "break":
            raise _Break()
        if tag == "assign":
            _, targets, exprs = stmt
            vals = self._eval_list(exprs, env)
            # GORLIWA ewaluacja celów: obj/key indeksów PRZED jakąkolwiek mutacją,
            # inaczej 'j, u[j] = 2, 10' policzyłoby u[j] już po zmianie j.
            resolved = []
            for tgt in targets:
                if tgt[0] == "name":
                    resolved.append(tgt)
                elif tgt[0] == "index":
                    obj = self._eval(tgt[1], env)
                    key = self._eval(tgt[2], env)
                    if not isinstance(obj, Bubble):
                        raise LuaError(f"próba indeksowania {_type(obj)} (przypisanie)")
                    resolved.append(("rindex", obj, key))   # cel już rozwiązany
                else:
                    raise LuaError("nieprawidłowy cel przypisania")
            for i, tgt in enumerate(resolved):
                v = vals[i] if i < len(vals) else None    # brak = nil
                self._assign_one(tgt, v, env)
            return None
        if tag == "exprstat":
            return self._eval(stmt[1], env)
        if tag == "do":
            inner = self._block_env(env, "do")
            try:
                return self._exec_block(stmt[1], inner)
            finally:
                self._pop_live_env(inner)
        if tag == "if":
            _, branches, els = stmt
            for cond, blk in branches:
                if _truthy(self._eval(cond, env)):
                    inner = self._block_env(env, "if")
                    try:
                        return self._exec_block(blk, inner)
                    finally:
                        self._pop_live_env(inner)
            if els is not None:
                inner = self._block_env(env, "else")
                try:
                    return self._exec_block(els, inner)
                finally:
                    self._pop_live_env(inner)
            return None
        if tag == "while":
            _, cond, blk = stmt
            guard = 0
            while _truthy(self._eval(cond, env)):
                inner = self._block_env(env, "while")
                try:
                    self._exec_block(blk, inner)
                except _Break:
                    break
                finally:
                    self._pop_live_env(inner)
                guard += 1
                if guard > _LOOP_GUARD:
                    raise LuaError("pętla while przekroczyła limit iteracji")
            return None
        if tag == "repeat":
            # repeat blk until cond — cond widzi LOKALNE bloku (ten sam bąbel)
            _, blk, cond = stmt
            guard = 0
            while True:
                inner = self._block_env(env, "repeat")
                try:
                    self._exec_block(blk, inner)
                    if _truthy(self._eval(cond, inner)):
                        break
                except _Break:
                    break
                finally:
                    self._pop_live_env(inner)
                guard += 1
                if guard > _LOOP_GUARD:
                    raise LuaError("pętla repeat przekroczyła limit iteracji")
            return None
        if tag == "goto":
            raise _Goto(stmt[1])
        if tag == "label":
            return None                                  # etykieta sama nic nie robi
        if tag == "fornum":
            _, name, e0, e1, e2, blk = stmt
            start = _arith_num(self._eval(e0, env), "for")
            limit = _arith_num(self._eval(e1, env), "for")
            step = _arith_num(self._eval(e2, env), "for") if e2 is not None else 1
            if step == 0:
                raise LuaError("krok 'for' = 0")
            # liczba iteracji (włącznie po granicy) — policz dokładnie, odrzuć runaway
            if step > 0:
                est = (math.floor((limit - start) / step) + 1) if start <= limit else 0
            else:
                est = (math.floor((start - limit) / (-step)) + 1) if start >= limit else 0
            if est > _LOOP_GUARD:
                raise LuaError("pętla for: za dużo iteracji (limit hosta)")
            i = start
            guard = 0
            while (step > 0 and i <= limit) or (step < 0 and i >= limit):
                inner = self._block_env(env, "for")
                atom = self.store.atom_new("var", name, value=i)
                inner.bind(name, atom)
                try:
                    self._exec_block(blk, inner)
                except _Break:
                    break
                finally:
                    self._pop_live_env(inner)
                i += step
                guard += 1
                if guard > _LOOP_GUARD:
                    raise LuaError("pętla for przekroczyła limit iteracji")
            return None
        if tag == "forin":
            # for namelist in explist do block end
            # 4. wartość explist = to-be-closed (Lua 5.4+)
            _, names, exprs, blk = stmt
            vals = self._eval_list(exprs, env)
            f = vals[0] if len(vals) > 0 else None
            s = vals[1] if len(vals) > 1 else None
            ctrl = vals[2] if len(vals) > 2 else None
            closer = vals[3] if len(vals) > 3 else None
            guard = 0
            try:
                while True:
                    results = self._call(f, [s, ctrl])
                    first = results[0] if results else None
                    if first is None:
                        break
                    ctrl = first
                    inner = self._block_env(env, "forin")
                    for idx, nm in enumerate(names):
                        v = results[idx] if idx < len(results) else None
                        atom = self.store.atom_new("var", nm, value=v)
                        inner.bind(nm, atom)
                    try:
                        self._exec_block(blk, inner)
                    except _Break:
                        break
                    finally:
                        self._pop_live_env(inner)
                    guard += 1
                    if guard > _LOOP_GUARD:
                        raise LuaError("pętla for-in przekroczyła limit iteracji")
            finally:
                self._close_value(closer)
            return None
        raise LuaError(f"nieznana instrukcja: {tag}")

    def _close_value(self, v):
        """Zamknij wartość to-be-closed (iterator / <close>)."""
        if v is None or v is False:
            return
        if not isinstance(v, Bubble):
            return
        mm = self._metamethod(v, "__close")
        if mm is not None:
            try:
                self._call(mm, [v])
            except LuaError:
                pass

    # ── przypisanie / odczyt nazw: local vs _ENV (Lua 5.2+) ──
    def _assign_one(self, target, val, env):
        if target[0] == "name":
            name = target[1]
            atom = env.lookup(name)
            if atom is not None:
                if atom.metadata.get("const"):
                    raise LuaError(f"próba przypisania do stałej '{name}'")
                atom.metadata["v"] = val             # mutacja w miejscu (stałe id)
            else:
                # wolna nazwa → _ENV[name] (strict global check)
                self._check_global_name(name, writing=True)
                et = self._get_env_table(env)
                self._table_set(et, name, val)
            return
        if target[0] == "rindex":
            # cel indeksowy już rozwiązany (obj, key) PRZED mutacją — patrz 'assign'
            self._table_set(target[1], target[2], val)
            return
        raise LuaError("zły cel przypisania")

    # ── metatabele: przechowywane jako wiązanie '@meta' WEWNĄTRZ bąbla-tabeli ──
    # (reach-GC widzi je za darmo; '_keyname' nigdy nie produkuje '@'-prefiksu,
    #  więc nie kolidują z kluczami użytkownika i są pomijane w iteracji)
    def _get_metatable(self, tb):
        atom = _own_atom(tb, _META_KEY)
        return atom.metadata["v"] if atom is not None else None

    def _set_metatable(self, tb, mt):
        if mt is None:
            if _own_has(tb, _META_KEY):
                _own_unbind(tb, _META_KEY)
            return
        existing = _own_aid(tb, _META_KEY)
        if existing is not None:
            self.store.get_atom(existing).metadata["v"] = mt
        else:
            atom = self.store.atom_new("meta", _META_KEY, value=mt)
            tb.bind(_META_KEY, atom)

    def _raw_field(self, tb, name):
        """Surowy odczyt pola po nazwie-stringu, BEZ metametod (do czytania metatabeli)."""
        atom = _own_atom(tb, _keyname(name))
        return atom.metadata["v"] if atom is not None else None

    def _env_key(self, tb, key):
        """Klucz wiązania: globalne G używa gołych nazw (print, _VERSION);
        zwykłe tabele — _keyname (s:/i:/…). Dzięki temu _G.x == global x."""
        if tb is self.G and isinstance(key, str):
            return key
        return _keyname(key)

    def _table_set(self, tb, key, val):
        kn = self._env_key(tb, key)
        existing = _own_aid(tb, kn)
        if existing is not None:
            # klucz ISTNIEJE -> surowe nadpisanie/usunięcie; __newindex NIE odpala
            if val is None:
                _own_unbind(tb, kn)                  # pole=nil usuwa klucz (Lua)
            else:
                self.store.get_atom(existing).metadata["v"] = val
            return
        # klucz NIEOBECNY -> spróbuj __newindex z metatabeli
        mt = self._get_metatable(tb)
        if mt is not None:
            ni = self._raw_field(mt, "__newindex")
            if isinstance(ni, Bubble):
                self._table_set(ni, key, val)        # przekieruj zapis do tabeli
                return
            if isinstance(ni, LuaFunction) or callable(ni):
                self._call(ni, [tb, key, val])       # handler decyduje
                return
        if val is None:
            return                                   # brak __newindex i nil = no-op
        atom = self.store.atom_new("field", kn, value=val)
        atom.metadata["k"] = key                     # oryginalny klucz Lua (dla pairs)
        tb.bind(kn, atom)

    def _table_get(self, tb, key, _depth=0):
        # własne pole (bez parent chain — tabele Lua ≠ scope leksykalny)
        atom = _own_atom(tb, self._env_key(tb, key))
        if atom is not None:
            # heat jak lookup (odczyt grzeje) — spójne z Bubble.lookup substratu
            if getattr(self.store, "thermal", False) and hasattr(self.store, "heat"):
                self.store.heat(atom)
            return atom.metadata["v"]
        # klucz NIEOBECNY -> spróbuj __index z metatabeli
        mt = self._get_metatable(tb)
        if mt is not None:
            idx = self._raw_field(mt, "__index")
            if isinstance(idx, Bubble):
                if _depth > 100:
                    raise LuaError("łańcuch __index za głęboki (cykl?)")
                return self._table_get(idx, key, _depth + 1)   # łańcuch prototypów
            if isinstance(idx, LuaFunction) or callable(idx):
                res = self._call(idx, [tb, key])
                return res[0] if res else None
        return None

    # ── wielowartościowość: lista wyrażeń, gdzie OSTATNIE wyrażenie rozwija się ──
    # (wywołanie na końcu listy oddaje wszystkie wartości; w środku — tylko 1)
    def _invoke(self, e, env):
        """Pełna lista wartości z 'call' albo 'methodcall' (obj liczone RAZ)."""
        if e[0] == "call":
            fn = self._eval(e[1], env)
            args = self._eval_list(e[2], env)
            return self._call(fn, args)
        # methodcall: obj:m(args) == obj.m(obj, args), ale obj liczone dokładnie raz
        obj = self._eval(e[1], env)
        method = e[2]
        args = self._eval_list(e[3], env)
        if isinstance(obj, Bubble):
            fn = self._table_get(obj, method)        # metoda przez __index, jeśli trzeba
            return self._call(fn, [obj] + args)      # self na początku
        # metatabela typu (np. string: s:sub(i) → string.sub(s, i))
        mt = self._type_mt.get(_type(obj))
        if mt is not None:
            idx = self._raw_field(mt, "__index")
            if isinstance(idx, Bubble):
                fn = self._table_get(idx, method)
                return self._call(fn, [obj] + args)
            if isinstance(idx, LuaFunction) or callable(idx):
                res = self._call(idx, [obj, method])
                fn = res[0] if res else None
                return self._call(fn, [obj] + args)
        raise LuaError(f"próba wywołania metody '{method}' na {_type(obj)}")

    def _eval_multi(self, e, env):
        """Wyrażenie w kontekście wielowartościowym -> lista wartości."""
        if e[0] in ("call", "methodcall"):
            return self._invoke(e, env)              # pełna lista
        if e[0] == "vararg":
            return list(self._va_stack[-1])          # '...' -> wszystkie varargi ramki
        return [self._eval(e, env)]                   # pozostałe: dokładnie 1

    def _eval_list(self, exprs, env):
        """Lista wyrażeń (return/args/RHS/konstruktor): ostatnie rozwija się."""
        if not exprs:
            return []
        vals = [self._eval(e, env) for e in exprs[:-1]]   # wszystkie poza ostatnim: 1
        vals.extend(self._eval_multi(exprs[-1], env))     # ostatnie: rozwija
        return vals

    # ── wywołanie: domknięcie Lua albo builtin Pythona ──
    def _as_retlist(self, v):
        if v is None:
            return []
        return v if isinstance(v, list) else [v]

    def _sync_drive(self, gen):
        """Uruchom generator wywołania; yield = błąd (poza korutyną)."""
        try:
            y = next(gen)
            gen.close()
            raise LuaError("attempt to yield from outside a coroutine")
        except StopIteration as e:
            return self._as_retlist(e.value)

    def _frame_label(self, fn):
        if isinstance(fn, LuaFunction):
            return fn.name or "function"
        if callable(fn):
            return getattr(fn, "__name__", None) or "builtin"
        return "?"

    def _make_frame(self, fn, scope=None):
        """Rekord ramki na _call_stack (traceback + debug.*)."""
        name = self._frame_label(fn)
        if isinstance(fn, LuaFunction):
            what = "main" if (fn.name or "").startswith("@") or (fn.name or "").startswith("=") else "Lua"
            source = fn.name if isinstance(fn.name, str) else "=(lua)"
        elif callable(fn):
            what = "C"
            source = "=[C]"
        else:
            what = "C"
            source = "=[C]"
        return {
            "name": name,
            "what": what,
            "fn": fn,
            "scope": scope,
            "source": source,
            "currentline": self._cur_line,
        }

    def _frame_name(self, fr):
        if isinstance(fr, dict):
            return fr.get("name") or "?"
        return str(fr) if fr is not None else "?"

    def _format_traceback(self, msg=None, level=1):
        """Uproszczony stack traceback (nazwy funkcji / chunków)."""
        try:
            lv = max(1, int(level))
        except (TypeError, ValueError):
            lv = 1
        lines = []
        if msg is not None and msg is not False:
            lines.append(_tostring(msg) if not isinstance(msg, str) else msg)
        lines.append("stack traceback:")
        stack = list(reversed(self._call_stack))
        skip = lv - 1
        shown = stack[skip:] if skip < len(stack) else []
        if not shown:
            lines.append("\t[C]: in ?")
        else:
            for fr in shown:
                nm = self._frame_name(fr)
                if isinstance(fr, dict) and fr.get("what") == "C":
                    lines.append(f"\t[C]: in {nm}")
                else:
                    src = fr.get("source") if isinstance(fr, dict) else None
                    ln = fr.get("currentline") if isinstance(fr, dict) else None
                    if src and ln is not None:
                        lines.append(f"\t{src}:{ln}: in {nm}")
                    elif src:
                        lines.append(f"\t{src}: in {nm}")
                    else:
                        lines.append(f"\t{nm}")
        return "\n".join(lines)

    # ── debug.* (subset; bez escape do Store / host path) ──
    def _debug_resolve_level(self, level):
        """Lua: level 0 = getinfo, 1 = caller… → indeks w _call_stack."""
        try:
            lv = int(level)
        except (TypeError, ValueError):
            raise LuaError("debug: zły level")
        # stack[-1] = bieżąca (zwykle C getinfo/getlocal)
        idx = len(self._call_stack) - 1 - lv
        if idx < 0 or idx >= len(self._call_stack):
            return None
        return self._call_stack[idx]

    def _debug_info_table(self, fields):
        t = self.store.bubble_new("table")
        for k, v in fields.items():
            if v is None and k not in ("func",):
                continue
            atom = self.store.atom_new("field", "s:" + k, value=v)
            atom.metadata["k"] = k
            t.bind("s:" + k, atom)
        return t

    def _short_src(self, source):
        if not isinstance(source, str) or not source:
            return "[C]"
        # nie ujawniaj absolutnych ścieżek hosta — tylko chunkname
        s = source
        if s.startswith("@"):
            s = s[1:]
        if len(s) > 60:
            s = "..." + s[-57:]
        return s

    def _debug_getinfo(self, level_or_fn=None, what=None, *_):
        what = what if isinstance(what, str) and what else "flnStu"
        fr = None
        fn = None
        if isinstance(level_or_fn, LuaFunction) or callable(level_or_fn):
            fn = level_or_fn
            fr = {
                "name": self._frame_label(fn),
                "what": "Lua" if isinstance(fn, LuaFunction) else "C",
                "fn": fn,
                "scope": None,
                "source": fn.name if isinstance(fn, LuaFunction) else "=[C]",
                "currentline": None,
            }
        else:
            fr = self._debug_resolve_level(1 if level_or_fn is None else level_or_fn)
            if fr is None:
                return None
            if not isinstance(fr, dict):
                fr = {"name": str(fr), "what": "Lua", "fn": None, "scope": None,
                      "source": "?", "currentline": None}
            fn = fr.get("fn")

        fields = {}
        if "n" in what:
            fields["name"] = fr.get("name")
            fields["namewhat"] = "global" if fr.get("what") == "main" else "local"
        if "S" in what:
            src = fr.get("source") or "=[C]"
            fields["source"] = src if isinstance(src, str) else "=[C]"
            fields["short_src"] = self._short_src(fields["source"])
            fields["what"] = fr.get("what") or "Lua"
            fields["linedefined"] = -1
            fields["lastlinedefined"] = -1
        if "l" in what:
            cl = fr.get("currentline")
            if cl is None:
                cl = self._cur_line
            fields["currentline"] = int(cl) if cl is not None else -1
        if "u" in what:
            nups = 0
            if isinstance(fn, LuaFunction) and isinstance(fn.env, Bubble):
                nups = len([k for k in _own_keys(fn.env) if not str(k).startswith("@")])
            fields["nups"] = nups
            fields["nparams"] = (
                len([p for p in fn.params if p != "..."])
                if isinstance(fn, LuaFunction) else 0
            )
            fields["isvararg"] = (
                isinstance(fn, LuaFunction) and "..." in fn.params
            )
        if "f" in what:
            fields["func"] = fn
        if "t" in what:
            fields["istailcall"] = False
        return self._debug_info_table(fields)

    def _scope_locals(self, scope):
        """Lista (name, atom) locale ramki (własne wiązania, bez @meta/@tbc)."""
        if scope is None or not isinstance(scope, Bubble):
            return []
        out = []
        for kn in _own_keys(scope, skip={_META_KEY, _TBC_KEY}):
            atom = _own_atom(scope, kn)
            if atom is None:
                continue
            # param/var: nazwa = kn (bez prefiksu s: — locale to surowe nazwy)
            name = kn
            if name.startswith("s:"):
                name = name[2:]
            if name.startswith("@"):
                continue
            out.append((name, atom))
        return out

    def _debug_getlocal(self, level=None, index=None, *_):
        fr = self._debug_resolve_level(1 if level is None else level)
        if fr is None or not isinstance(fr, dict):
            return []
        try:
            idx = int(index)
        except (TypeError, ValueError):
            raise LuaError("debug.getlocal: zły indeks")
        locs = self._scope_locals(fr.get("scope"))
        if idx < 1 or idx > len(locs):
            return []
        name, atom = locs[idx - 1]
        return [name, atom.metadata.get("v")]

    def _debug_setlocal(self, level=None, index=None, value=None, *_):
        fr = self._debug_resolve_level(1 if level is None else level)
        if fr is None or not isinstance(fr, dict):
            return None
        try:
            idx = int(index)
        except (TypeError, ValueError):
            raise LuaError("debug.setlocal: zły indeks")
        locs = self._scope_locals(fr.get("scope"))
        if idx < 1 or idx > len(locs):
            return None
        name, atom = locs[idx - 1]
        if atom.metadata.get("const"):
            raise LuaError(f"próba przypisania do stałej '{name}'")
        atom.metadata["v"] = value
        return name

    def _upvalue_list(self, fn):
        """Upvalues domknięcia ≈ własne wiązania fn.env (model bąbla, nie sloty PUC).

        Pomijamy _ENV (zawsze obecne na wrapie chunka) — mniej mylące niż „pierwszy
        upvalue = _ENV”.
        """
        if not isinstance(fn, LuaFunction) or not isinstance(fn.env, Bubble):
            return []
        return [(n, a) for n, a in self._scope_locals(fn.env) if n != "_ENV"]

    def _debug_getupvalue(self, fn=None, index=None, *_):
        if not isinstance(fn, LuaFunction):
            return []
        try:
            idx = int(index)
        except (TypeError, ValueError):
            raise LuaError("debug.getupvalue: zły indeks")
        ups = self._upvalue_list(fn)
        if idx < 1 or idx > len(ups):
            return []
        name, atom = ups[idx - 1]
        return [name, atom.metadata.get("v")]

    def _debug_setupvalue(self, fn=None, index=None, value=None, *_):
        if not isinstance(fn, LuaFunction):
            return None
        try:
            idx = int(index)
        except (TypeError, ValueError):
            raise LuaError("debug.setupvalue: zły indeks")
        ups = self._upvalue_list(fn)
        if idx < 1 or idx > len(ups):
            return None
        name, atom = ups[idx - 1]
        if atom.metadata.get("const"):
            raise LuaError(f"próba przypisania do stałej '{name}'")
        atom.metadata["v"] = value
        return name

    def _call(self, fn, args):
        return self._sync_drive(self._call_gen(fn, list(args)))

    def _call_gen(self, fn, args):
        """Generatorowa ścieżka wywołania — yield = coroutine.yield."""
        # coroutine.yield
        if fn is getattr(self, "_yield_fn", None):
            if self._coro is None:
                raise LuaError("attempt to yield from outside a coroutine")
            sent = yield list(args)
            return self._as_retlist(sent)

        if isinstance(fn, LuaFunction):
            scope = self.store.bubble_new("call", parent=fn.env)
            self._push_live_env(scope)
            frame = self._make_frame(fn, scope=scope)
            self._call_stack.append(frame)
            named = [p for p in fn.params if p != "..."]
            for i, p in enumerate(named):
                v = args[i] if i < len(args) else None
                atom = self.store.atom_new("param", p, value=v)
                scope.bind(p, atom)
            is_va = "..." in fn.params
            if is_va:
                self._va_stack.append(list(args[len(named):]))
            try:
                yield from self._exec_block_gen(fn.body, scope)
            except _Return as r:
                return r.value
            except _Break:
                raise LuaError("'break' nie może opuścić funkcji")
            except _Goto as g:
                raise LuaError(f"goto: nie znaleziono etykiety '{g.name}'")
            finally:
                if is_va:
                    self._va_stack.pop()
                self._pop_live_env(scope)
                if self._call_stack and self._call_stack[-1] is frame:
                    self._call_stack.pop()
            return []
        if callable(fn):
            # pcall/xpcall i inne: synchroniczne (yield przez C-boundary → błąd w _sync_drive)
            frame = self._make_frame(fn, scope=None)
            self._call_stack.append(frame)
            try:
                r = fn(*args)
                return r if isinstance(r, list) else [r]
            finally:
                if self._call_stack and self._call_stack[-1] is frame:
                    self._call_stack.pop()
        if isinstance(fn, Bubble):
            mm = self._metamethod(fn, "__call")
            if mm is not None:
                return (yield from self._call_gen(mm, [fn] + list(args)))
        raise LuaError(f"próba wywołania {_type(fn)}")

    def _exec_block_gen(self, block, env):
        """Jak _exec_block, ale propaguje yield z wywołań."""
        last = None
        i = 0
        guard = 0
        try:
            while i < len(block):
                stmt = block[i]
                try:
                    last = yield from self._exec_stmt_gen(stmt, env)
                    i += 1
                except _Goto as g:
                    for j, s in enumerate(block):
                        _ln, core = self._stmt_core(s)
                        if core[0] == "label" and core[1] == g.name:
                            i = j + 1
                            break
                    else:
                        self._close_env(env)
                        raise
                    guard += 1
                    if guard > _LOOP_GUARD:
                        raise LuaError("goto: przekroczono limit skoków")
                except (_Return, _Break):
                    self._close_env(env)
                    raise
            self._close_env(env)
            return last
        except (_Return, _Break, _Goto):
            raise

    def _exec_stmt_gen(self, stmt, env):
        """Wersja generatorowa: większość instrukcji = sync; call-path przez gen."""
        line, stmt = self._stmt_core(stmt)
        if line is not None:
            self._touch_frame_line(line)
        tag = stmt[0]
        # instrukcje z potencjalnym yield w wyrażeniach / ciele
        if tag in ("local", "global", "global_star", "localfunc", "return", "break",
                   "assign", "exprstat", "do", "if", "while", "repeat", "goto", "label",
                   "fornum", "forin"):
            # użyj ścieżki sync, ale _call jest _sync_drive — yield w for/while
            # złamie się przez "outside coroutine". Dlatego _call w trakcie coro
            # musi iść gen. Ustawiamy flagę i nadpisujemy chwilowo? 
            # Prościej: reimplementuj call-heavy tags z yield from.
            pass
        if tag == "exprstat":
            return (yield from self._eval_gen(stmt[1], env))
        if tag == "return":
            raise _Return((yield from self._eval_list_gen(stmt[1], env)))
        if tag == "assign":
            _, targets, exprs = stmt
            vals = yield from self._eval_list_gen(exprs, env)
            resolved = []
            for tgt in targets:
                if tgt[0] == "name":
                    resolved.append(tgt)
                elif tgt[0] == "index":
                    obj = yield from self._eval_gen(tgt[1], env)
                    key = yield from self._eval_gen(tgt[2], env)
                    if not isinstance(obj, Bubble):
                        raise LuaError(f"próba indeksowania {_type(obj)} (przypisanie)")
                    resolved.append(("rindex", obj, key))
                else:
                    raise LuaError("nieprawidłowy cel przypisania")
            for i, tgt in enumerate(resolved):
                v = vals[i] if i < len(vals) else None
                self._assign_one(tgt, v, env)
            return None
        if tag == "local":
            names, inits = stmt[1], stmt[2]
            attrs = stmt[3] if len(stmt) > 3 else [None] * len(names)
            vals = yield from self._eval_list_gen(inits, env)
            for i, name in enumerate(names):
                v = vals[i] if i < len(vals) else None
                atom = self.store.atom_new("var", name, value=v)
                attr = attrs[i] if i < len(attrs) else None
                if attr == "const":
                    atom.metadata["const"] = True
                if attr == "close":
                    atom.metadata["const"] = True
                    atom.metadata["close"] = True
                    if v is not None and v is not False:
                        if not isinstance(v, Bubble) or self._metamethod(v, "__close") is None:
                            raise LuaError("wartość <close> bez __close")
                    self._tbc_list(env).append(atom)
                env.bind(name, atom)
            return None
        if tag == "do":
            inner = self._block_env(env, "do")
            try:
                return (yield from self._exec_block_gen(stmt[1], inner))
            finally:
                self._pop_live_env(inner)
        if tag == "if":
            _, branches, els = stmt
            for cond, blk in branches:
                if _truthy((yield from self._eval_gen(cond, env))):
                    inner = self._block_env(env, "if")
                    try:
                        return (yield from self._exec_block_gen(blk, inner))
                    finally:
                        self._pop_live_env(inner)
            if els is not None:
                inner = self._block_env(env, "else")
                try:
                    return (yield from self._exec_block_gen(els, inner))
                finally:
                    self._pop_live_env(inner)
            return None
        if tag == "while":
            _, cond, blk = stmt
            guard = 0
            while _truthy((yield from self._eval_gen(cond, env))):
                inner = self._block_env(env, "while")
                try:
                    yield from self._exec_block_gen(blk, inner)
                except _Break:
                    break
                finally:
                    self._pop_live_env(inner)
                guard += 1
                if guard > _LOOP_GUARD:
                    raise LuaError("pętla while przekroczyła limit iteracji")
            return None
        if tag == "repeat":
            _, blk, cond = stmt
            guard = 0
            while True:
                inner = self._block_env(env, "repeat")
                try:
                    yield from self._exec_block_gen(blk, inner)
                    if _truthy((yield from self._eval_gen(cond, inner))):
                        break
                except _Break:
                    break
                finally:
                    self._pop_live_env(inner)
                guard += 1
                if guard > _LOOP_GUARD:
                    raise LuaError("pętla repeat przekroczyła limit iteracji")
            return None
        if tag == "fornum":
            _, name, e0, e1, e2, blk = stmt
            start = _arith_num((yield from self._eval_gen(e0, env)), "for")
            limit = _arith_num((yield from self._eval_gen(e1, env)), "for")
            step = _arith_num((yield from self._eval_gen(e2, env)), "for") if e2 is not None else 1
            if step == 0:
                raise LuaError("krok 'for' = 0")
            i = start
            guard = 0
            while (step > 0 and i <= limit) or (step < 0 and i >= limit):
                inner = self._block_env(env, "for")
                atom = self.store.atom_new("var", name, value=i)
                inner.bind(name, atom)
                try:
                    yield from self._exec_block_gen(blk, inner)
                except _Break:
                    break
                finally:
                    self._pop_live_env(inner)
                i += step
                guard += 1
                if guard > _LOOP_GUARD:
                    raise LuaError("pętla for przekroczyła limit iteracji")
            return None
        if tag == "forin":
            _, names, exprs, blk = stmt
            vals = yield from self._eval_list_gen(exprs, env)
            f = vals[0] if len(vals) > 0 else None
            s = vals[1] if len(vals) > 1 else None
            ctrl = vals[2] if len(vals) > 2 else None
            closer = vals[3] if len(vals) > 3 else None
            guard = 0
            try:
                while True:
                    results = yield from self._call_gen(f, [s, ctrl])
                    first = results[0] if results else None
                    if first is None:
                        break
                    ctrl = first
                    inner = self._block_env(env, "forin")
                    for idx, nm in enumerate(names):
                        v = results[idx] if idx < len(results) else None
                        atom = self.store.atom_new("var", nm, value=v)
                        inner.bind(nm, atom)
                    try:
                        yield from self._exec_block_gen(blk, inner)
                    except _Break:
                        break
                    finally:
                        self._pop_live_env(inner)
                    guard += 1
                    if guard > _LOOP_GUARD:
                        raise LuaError("pętla for-in przekroczyła limit iteracji")
            finally:
                self._close_value(closer)
            return None
        # fallback: sync (break/goto/label/global/localfunc)
        return self._exec_stmt(stmt, env)

    def _eval_gen(self, e, env):
        tag = e[0]
        if tag in ("num", "str", "nil", "true", "false", "vararg"):
            return self._eval(e, env)
        if tag == "name":
            return self._eval(e, env)
        if tag == "paren":
            return (yield from self._eval_gen(e[1], env))
        if tag == "index":
            obj = yield from self._eval_gen(e[1], env)
            key = yield from self._eval_gen(e[2], env)
            if not isinstance(obj, Bubble):
                raise LuaError(f"próba indeksowania {_type(obj)}")
            return self._table_get(obj, key)
        if tag == "call" or tag == "methodcall":
            vals = yield from self._invoke_gen(e, env)
            return vals[0] if vals else None
        if tag == "function":
            return LuaFunction(e[1], e[2], env, name="anonim")
        if tag == "table":
            return (yield from self._build_table_gen(e[1], env))
        if tag == "unop":
            return self._unop(e[1], (yield from self._eval_gen(e[2], env)))
        if tag == "binop":
            # and/or short-circuit
            if e[1] == "and":
                l = yield from self._eval_gen(e[2], env)
                return (yield from self._eval_gen(e[3], env)) if _truthy(l) else l
            if e[1] == "or":
                l = yield from self._eval_gen(e[2], env)
                return l if _truthy(l) else (yield from self._eval_gen(e[3], env))
            return self._binop(e[1], e[2], e[3], env)  # may call metamethods via _call sync
        return self._eval(e, env)

    def _eval_list_gen(self, exprs, env):
        if not exprs:
            return []
        vals = []
        for e in exprs[:-1]:
            vals.append((yield from self._eval_gen(e, env)))
        last = exprs[-1]
        if last[0] in ("call", "methodcall"):
            vals.extend((yield from self._invoke_gen(last, env)))
        elif last[0] == "vararg":
            vals.extend(list(self._va_stack[-1]))
        else:
            vals.append((yield from self._eval_gen(last, env)))
        return vals

    def _invoke_gen(self, e, env):
        if e[0] == "call":
            fn = yield from self._eval_gen(e[1], env)
            args = yield from self._eval_list_gen(e[2], env)
            return (yield from self._call_gen(fn, args))
        obj = yield from self._eval_gen(e[1], env)
        method = e[2]
        args = yield from self._eval_list_gen(e[3], env)
        if isinstance(obj, Bubble):
            fn = self._table_get(obj, method)
            return (yield from self._call_gen(fn, [obj] + args))
        mt = self._type_mt.get(_type(obj))
        if mt is not None:
            idx = self._raw_field(mt, "__index")
            if isinstance(idx, Bubble):
                fn = self._table_get(idx, method)
                return (yield from self._call_gen(fn, [obj] + args))
        raise LuaError(f"próba wywołania metody '{method}' na {_type(obj)}")

    def _build_table_gen(self, fields, env):
        tb = self.store.bubble_new("table")
        auto = 1
        n = len(fields)
        for idx, (keyexpr, valexpr) in enumerate(fields):
            if keyexpr is None:
                if idx == n - 1:
                    for v in (yield from self._eval_multi_gen(valexpr, env)):
                        self._table_set(tb, auto, v)
                        auto += 1
                else:
                    self._table_set(tb, auto, (yield from self._eval_gen(valexpr, env)))
                    auto += 1
            else:
                key = yield from self._eval_gen(keyexpr, env)
                self._table_set(tb, key, (yield from self._eval_gen(valexpr, env)))
        return tb

    def _eval_multi_gen(self, e, env):
        if e[0] in ("call", "methodcall"):
            return (yield from self._invoke_gen(e, env))
        if e[0] == "vararg":
            return list(self._va_stack[-1])
        return [(yield from self._eval_gen(e, env))]

    # ── ewaluacja wyrażeń ──
    def _eval(self, e, env):
        tag = e[0]
        if tag == "num":
            return e[1]
        if tag == "str":
            return e[1]
        if tag == "nil":
            return None
        if tag == "true":
            return True
        if tag == "false":
            return False
        if tag == "name":
            name = e[1]
            atom = env.lookup(name)
            if atom is not None:
                return atom.metadata["v"]
            # wolna nazwa → _ENV[name] (strict: musi być zadeklarowana)
            self._check_global_name(name, writing=False)
            return self._table_get(self._get_env_table(env), name)
        if tag == "paren":
            return self._eval(e[1], env)                 # nawiasy: zawsze 1 wartość
        if tag == "vararg":
            va = self._va_stack[-1]
            return va[0] if va else None                 # kontekst 1-wart.: pierwszy
        if tag == "index":
            obj = self._eval(e[1], env)
            key = self._eval(e[2], env)
            if not isinstance(obj, Bubble):
                raise LuaError(f"próba indeksowania {_type(obj)}")
            return self._table_get(obj, key)
        if tag == "call" or tag == "methodcall":
            vals = self._invoke(e, env)
            return vals[0] if vals else None             # kontekst 1-wartościowy: dostrojenie
        if tag == "function":
            # literał funkcji: domknięcie przechwytuje BIEŻĄCE środowisko
            return LuaFunction(e[1], e[2], env, name="anonim")
        if tag == "table":
            return self._build_table(e[1], env)
        if tag == "unop":
            return self._unop(e[1], self._eval(e[2], env))
        if tag == "binop":
            return self._binop(e[1], e[2], e[3], env)
        raise LuaError(f"nieznane wyrażenie: {tag}")

    def _build_table(self, fields, env):
        tb = self.store.bubble_new("table")
        auto = 1
        n = len(fields)
        for idx, (keyexpr, valexpr) in enumerate(fields):
            if keyexpr is None:
                if idx == n - 1:                          # ostatnie pozycyjne: rozwija wiele wartości
                    for v in self._eval_multi(valexpr, env):
                        self._table_set(tb, auto, v)
                        auto += 1
                else:
                    self._table_set(tb, auto, self._eval(valexpr, env))
                    auto += 1
            else:
                key = self._eval(keyexpr, env)
                self._table_set(tb, key, self._eval(valexpr, env))
        return tb

    def _unop(self, op, v):
        if op == "-":
            if _is_num_or_numstr(v):
                return -_arith_num(v, "-")
            mm = self._metamethod(v, "__unm")
            if mm is not None:
                res = self._call(mm, [v, v])           # Lua: operand przekazany dwukrotnie
                return res[0] if res else None
            raise LuaError(f"próba arytmetyki (-) na {_type(v)}")
        if op == "not":
            return not _truthy(v)
        if op == "~":                                  # bitowy NOT (64-bit) lub __bnot
            if _bitable(v):
                return _wrap64(~_to_int(v))
            mm = self._metamethod(v, "__bnot")
            if mm is not None:
                res = self._call(mm, [v, v])
                return res[0] if res else None
            raise LuaError(f"operacja bitowa na {_type(v)}")
        if op == "#":
            if isinstance(v, str):
                # WYBÓR: stringi to sekwencje punktów kodowych (Unicode), nie bajtów.
                # Spójne z lekserem (nazwy spoza ASCII dozwolone). Świadoma rozbieżność
                # z Lua (tam # = długość w bajtach). #"żółw" = 4, nie 8.
                return len(v)
            if isinstance(v, Bubble):
                mm = self._metamethod(v, "__len")
                if mm is not None:
                    res = self._call(mm, [v])
                    return res[0] if res else None
                return _array_len(v)
            raise LuaError(f"próba użycia długości na {_type(v)}")
        raise LuaError(f"nieznany operator unarny: {op}")

    def _binop(self, op, le, re, env):
        # and/or — zwarciowe
        if op == "and":
            l = self._eval(le, env)
            return self._eval(re, env) if _truthy(l) else l
        if op == "or":
            l = self._eval(le, env)
            return l if _truthy(l) else self._eval(re, env)
        l = self._eval(le, env)
        r = self._eval(re, env)
        if op == "..":
            if _is_concatable(l) and _is_concatable(r):
                return _tostring(l) + _tostring(r)
            handled, res = self._try_binop_mm("__concat", l, r)
            if handled:
                return res
            bad = l if not _is_concatable(l) else r
            raise LuaError(f"próba konkatenacji {_type(bad)}")
        if op == "==":
            return self._eq_mm(l, r)
        if op == "~=":
            return not self._eq_mm(l, r)
        if op in ("<", ">", "<=", ">="):
            return self._cmp_mm(op, l, r)
        # arytmetyka + bitowe: jeden tor (surowe -> metametoda -> błąd)
        event = _ARITH_MM.get(op)
        if event is not None:
            raw = self._raw_numeric(op, l, r)
            if raw is not _NOVAL:
                return raw
            handled, res = self._try_binop_mm(event, l, r)
            if handled:
                return res
            bad = l if not self._numeric_ok(op, l) else r
            kind = "operacji bitowej" if op in _BIT_OPS else "arytmetyki"
            raise LuaError(f"próba {kind} ({op}) na {_type(bad)}")
        raise LuaError(f"nieznany operator: {op}")

    # ── metametody: pomocnicy ──
    def _metamethod(self, v, name):
        """Metametoda 'name' wartości v (tylko tabele); None jeśli brak."""
        if isinstance(v, Bubble):
            mt = self._get_metatable(v)
            if mt is not None:
                return self._raw_field(mt, name)
        return None

    def _try_binop_mm(self, event, l, r):
        """Szuka metametody na l, potem r; (True, wynik) albo (False, None)."""
        mm = self._metamethod(l, event)
        if mm is None:
            mm = self._metamethod(r, event)
        if mm is None:
            return (False, None)
        res = self._call(mm, [l, r])
        return (True, res[0] if res else None)

    def _numeric_ok(self, op, v):
        return _bitable(v) if op in _BIT_OPS else _is_num_or_numstr(v)

    def _raw_numeric(self, op, l, r):
        """Surowy wynik operacji numerycznej albo _NOVAL gdy operandy się nie nadają."""
        if op in _BIT_OPS:
            if _bitable(l) and _bitable(r):
                if op == "&":
                    return _wrap64(_to_int(l) & _to_int(r))
                if op == "|":
                    return _wrap64(_to_int(l) | _to_int(r))
                if op == "~":
                    return _wrap64(_to_int(l) ^ _to_int(r))
                if op == "<<":
                    return _bitshift(l, r, True)
                if op == ">>":
                    return _bitshift(l, r, False)
            return _NOVAL
        if _is_num_or_numstr(l) and _is_num_or_numstr(r):
            return _raw_arith(op, _arith_num(l, op), _arith_num(r, op))
        return _NOVAL

    def _eq_mm(self, l, r):
        if self._eq(l, r):
            return True
        # __eq tylko gdy OBA to tabele i nie są prymitywnie równe (semantyka Lua)
        if isinstance(l, Bubble) and isinstance(r, Bubble):
            mm = self._metamethod(l, "__eq") or self._metamethod(r, "__eq")
            if mm is not None:
                res = self._call(mm, [l, r])
                return _truthy(res[0] if res else None)
        return False

    def _cmp_mm(self, op, l, r):
        rawable = (_is_real_num(l) and _is_real_num(r)) or (isinstance(l, str) and isinstance(r, str))
        if rawable:
            return self._cmp(op, l, r)
        # a<b -> __lt(a,b); a>b -> __lt(b,a); a<=b -> __le(a,b); a>=b -> __le(b,a)
        if op == "<":
            return self._order_mm("__lt", l, r)
        if op == ">":
            return self._order_mm("__lt", r, l)
        if op == "<=":
            return self._order_mm("__le", l, r)
        return self._order_mm("__le", r, l)

    def _order_mm(self, event, l, r):
        mm = self._metamethod(l, event) or self._metamethod(r, event)
        if mm is not None:
            res = self._call(mm, [l, r])
            return _truthy(res[0] if res else None)
        raise LuaError(f"próba porównania {_type(l)} z {_type(r)}")

    def _tostring_mm(self, v):
        """tostring honorujący __tostring (i __name dla etykiety typu)."""
        if isinstance(v, Bubble):
            mm = self._metamethod(v, "__tostring")
            if mm is not None:
                res = self._call(mm, [v])
                out = res[0] if res else None
                if not isinstance(out, str):
                    raise LuaError("__tostring musi zwrócić string")
                return out
            name = self._metamethod(v, "__name")
            if isinstance(name, str):
                return f"{name}: 0x{id(v) & 0xffffffff:08x}"
        return _tostring(v)

    def _eq(self, l, r):
        if isinstance(l, bool) or isinstance(r, bool):
            return l is r
        if isinstance(l, Bubble) or isinstance(r, Bubble):
            return l is r                             # tabele po tożsamości
        if isinstance(l, (int, float)) and isinstance(r, (int, float)):
            return l == r
        if type(l) is type(r):
            return l == r
        return False

    def _cmp(self, op, l, r):
        num = isinstance(l, (int, float)) and not isinstance(l, bool) \
            and isinstance(r, (int, float)) and not isinstance(r, bool)
        if not (num or (isinstance(l, str) and isinstance(r, str))):
            raise LuaError(f"próba porównania {_type(l)} z {_type(r)}")
        if op == "<":
            return l < r
        if op == ">":
            return l > r
        if op == "<=":
            return l <= r
        return l >= r
