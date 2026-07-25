#!/usr/bin/env python3
"""
karmazyn_boot.py — punkt startowy samodzielnego runtime KarmazynOS (v0.5)
=========================================================================
Maciej Mazur, Warsaw 2026

Po boocie: PROMPT WYKONAWCZY. Domyslny jezyk narzedzi: karmazyn_lua (Lua 5.5).
  - linia kodu              -> warstwa wykonawcza (Lua / fallback mini-Lisp)
  - linia ':...'            -> komenda systemu (OS meta)

Narzedzia w OS: funkcje i moduly Lua (package.preload / require).
  function echo(s) print(s) end
  package.preload.tool = function() return {run=function() return 42 end} end
  require("tool").run()

Start RAPORTUJE uslugi na ekran: [ OK ]/[WARN]/[FAIL] per usluga, z czasem.
Kolor tylko na terminalu (na potoku/do pliku — czyste tagi). Awaria uslugi
jest zgloszona jako [FAIL] i przerywa start czysto, bez surowego traceback.

Zmienne/tabele Lua to atomy w bablu-korzeniu -> zyja pod REACH-GC.

  python3 karmazyn_boot.py          # interaktywny prompt
  python3 karmazyn_boot.py --demo   # skryptowa sesja
  KARMAZYN_GUEST=exec               # wymus mini-Lisp zamiast Lua
  KARMAZYN_LUA=<sciezka>            # katalog pakietu karmazyn_lua

SZEW MONTAZU: boot oczekuje obiektu z `eval_line(str)->str` oraz `.env` (Bubble).

FIX v0.4 (audyt 2026-07):
  - :tick waliduje argument (n >= 1); wczesniej `:tick -5` bylo cichym
    no-op z komunikatem sugerujacym wykonanie.
  - :gc raportuje uczciwie: zmienne-korzeniowe przezywaja vacuum jako
    retained-TOMB (widoczne w `:ls tomb`); dopisane w :help.
  - Wspolbieznosc scheduler <-> REPL: bezpieczenstwo daje `Store.lock`
    (karmazyn_substrate v1.1) + ramki/extra_reach u gosci; boot nie
    musi nic synchronizowac sam.

FIX v0.5: domyslny gosc = karmazyn_lua (jezyk narzedzi w KarmazynOS).
"""

import os
import sys
import threading
import time
import types

from karmazyn_kernel import Store, kernel_info

try:
    import readline
    _HAS_READLINE = True
except Exception:
    _HAS_READLINE = False

# etykieta zamontowanego gosci (lua | exec) — dla :help / raportu startu
_GUEST_KIND = "exec"


# ─────────────────────────────────────────────────────────────────────────────
# Raport startu uslug
# ─────────────────────────────────────────────────────────────────────────────
class BootLog:
    """Log startu na ekran. [ OK ]/[WARN]/[FAIL], kolor tylko gdy stdout to TTY."""

    _COLOR = {"ok": "32", "warn": "33", "fail": "31"}   # zielony/zolty/czerwony

    def __init__(self, stream=None, color=None):
        self.stream = stream or sys.stdout
        self.color = (self.stream.isatty() if color is None else color)
        self.failed = False

    def _tag(self, code):
        label = {"ok": " OK ", "warn": "WARN", "fail": "FAIL"}[code]
        if self.color:
            return f"[\x1b[1;{self._COLOR[code]}m{label}\x1b[0m]"
        return f"[{label}]"

    def _line(self, code, name, detail, ms):
        t = f"  ({ms:.1f} ms)" if ms is not None else ""
        d = f" — {detail}" if detail else ""
        print(f"  {self._tag(code)} {name}{d}{t}", file=self.stream)

    def ok(self, name, detail="", ms=None):
        self._line("ok", name, detail, ms)

    def warn(self, name, detail="", ms=None):
        self._line("warn", name, detail, ms)

    def fail(self, name, detail="", ms=None):
        self.failed = True
        self._line("fail", name, detail, ms)


def _ms(t0):
    return (time.perf_counter() - t0) * 1000.0


# ─────────────────────────────────────────────────────────────────────────────
def _lua_root_candidates():
    """Katalogi, w ktorych moze lezec pakiet karmazyn_lua (pliki lib.py, evaluator.py…)."""
    here = os.path.dirname(os.path.abspath(__file__))
    # software/ -> repo root; root boot -> parent = Users\… sibling LUA
    kernel_root = os.path.dirname(here)
    parent = os.path.dirname(kernel_root)
    env = os.environ.get("KARMAZYN_LUA") or os.environ.get("KARMAZYN_LUA_HOME")
    out = []
    if env:
        out.append(os.path.abspath(env))
    # Prefer in-repo LUA (KarmazynOs/LUA), then sibling C:\Users\…\LUA
    out.extend([
        os.path.join(here, "LUA"),
        os.path.join(kernel_root, "LUA"),
        os.path.join(here, "karmazyn_lua"),
        os.path.join(here, "lua"),
        os.path.join(parent, "LUA"),
        os.path.join(parent, "Karmazyn_lua"),
    ])
    return out


def _ensure_karmazyn_lua():
    """Zarejestruj katalog zrodlowy jako pakiet karmazyn_lua (relative imports)."""
    if "karmazyn_lua" in sys.modules and getattr(sys.modules["karmazyn_lua"], "mount", None):
        return sys.modules["karmazyn_lua"]
    root = None
    for cand in _lua_root_candidates():
        if cand and os.path.isfile(os.path.join(cand, "lib.py")) and os.path.isfile(
            os.path.join(cand, "evaluator.py")
        ):
            root = cand
            break
    if root is None:
        # klasyczny import (site-packages / PYTHONPATH)
        import karmazyn_lua  # noqa: F401
        return sys.modules["karmazyn_lua"]
    pkg = types.ModuleType("karmazyn_lua")
    pkg.__path__ = [root]
    pkg.__file__ = os.path.join(root, "__init__.py")
    sys.modules["karmazyn_lua"] = pkg
    from karmazyn_lua.lib import mount, LuaLib, install_env_of, install_tools  # noqa: E402
    from karmazyn_lua.values import lua_env_of, compose_phi  # noqa: E402
    pkg.mount = mount
    pkg.LuaLib = LuaLib
    pkg.install_env_of = install_env_of
    pkg.install_tools = install_tools
    pkg.lua_env_of = lua_env_of
    pkg.compose_phi = compose_phi
    return pkg


def _tools_dir():
    """Opcjonalny katalog narzedzi *.lua (KARMAZYN_TOOLS lub software/tools)."""
    env = os.environ.get("KARMAZYN_TOOLS")
    if env and os.path.isdir(env):
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.join(here, "tools")
    return cand if os.path.isdir(cand) else None


def mount_evaluator(store):
    """Montuje warstwe wykonawcza na Store.

    Domyslnie karmazyn_lua (jezyk narzedzi). Fallback: karmazyn_exec (mini-Lisp).
    Wymus: KARMAZYN_GUEST=lua|exec
    Kontrakt: eval_line(str)->str, .env = Bubble korzenia (reach-GC).
    """
    global _GUEST_KIND
    prefer = (os.environ.get("KARMAZYN_GUEST") or "lua").strip().lower()
    if prefer in ("exec", "lisp", "scheme", "karmazyn_exec"):
        import karmazyn_exec
        _GUEST_KIND = "exec"
        return karmazyn_exec.Evaluator(store, env_label="repl")
    try:
        kl = _ensure_karmazyn_lua()
        tools = _tools_dir()
        kwargs = {"env_label": "lua"}
        if tools:
            kwargs["tools"] = tools
        ev = kl.mount(store, **kwargs)
        _GUEST_KIND = "lua"
        return ev
    except Exception as e:
        if prefer in ("lua", "karmazyn_lua"):
            # jawnie chcieli Lua — nie ukrywaj awarii
            raise
        import karmazyn_exec
        _GUEST_KIND = "exec"
        # ostrzezenie zostawi boot() w logu przez fail? tu cichy fallback + atrybut
        ev = karmazyn_exec.Evaluator(store, env_label="repl")
        ev._lua_mount_error = e
        return ev


class KarmazynShell:
    """Prompt: kod -> warstwa wykonawcza; ':...' -> komendy systemu."""

    def __init__(self, store, evaluator, verbose_events=False):
        self.store = store
        self.ev = evaluator
        self.env = getattr(evaluator, "env", None) or getattr(evaluator, "G", None)
        if verbose_events:
            store.events.on("vacuum_decay",
                            lambda a: print(f"  [GC] vacuum_decay: {a.id} ({a.E})"))

    def feed(self, line: str) -> str:
        line = line.strip()
        if not line:
            return ""
        if line.startswith(":"):
            return self._meta(line[1:].split())
        return self.ev.eval_line(line)

    def _meta(self, parts):
        if not parts:
            return ""
        cmd, args = parts[0].lower(), parts[1:]
        fn = getattr(self, f"_m_{cmd}", None)
        if fn is None:
            return f"nieznana komenda systemu: :{cmd}  (:help)"
        try:
            return fn(args)
        except (ValueError, IndexError) as e:
            return f"zly argument dla :{cmd}: {e}"
        except Exception as e:
            return f"blad :{cmd}: {type(e).__name__}: {e}"

    def _m_help(self, a):
        if _GUEST_KIND == "lua":
            kod = (
                "KOD (Lua):  x = 10  |  function f(n) return n*n end  |  print(f(5))\n"
                "  tool: package.preload.echo = function() return function(s) print(s) end end\n"
                "        require('echo')('czesc')   |  load('return 1+2')()\n"
            )
        else:
            kod = (
                "KOD (Lisp): (define x 10)  (+ x 5)  (lambda (n) (* n n))  (begin ...)\n"
            )
        return (
            kod
            + "OS : :info | :stats | :tick [n>=1] | :gc | :ls [stan] | :env | :tools\n"
            "     :find <q> | :new <S> <E> | :exit\n"
            "     :gc studzi WSZYSTKO: sieroty gina, korzenie jako retained-TOMB (:ls tomb)"
        )

    def _m_tools(self, a):
        """Lista narzedzi z package.preload (Lua) albo wskazowka dla exec."""
        if _GUEST_KIND != "lua":
            return "gosc exec (mini-Lisp): brak package.preload — :help"
        preload = getattr(self.ev, "_preload", None) or {}
        loaded = getattr(self.ev, "_modules", None) or {}
        if not preload and not loaded:
            return ("(brak narzedzi w package.preload)\n"
                    "  zdefiniuj: package.preload.foo = function() return {run=function() return 1 end} end\n"
                    "  uzyj:      local m = require('foo'); print(m.run())\n"
                    "  albo pliki *.lua w software/tools/ (auto-preload przy starcie)")
        lines = ["package.preload:"]
        for name in sorted(preload.keys()):
            st = " [loaded]" if name in loaded else ""
            lines.append(f"  {name}{st}")
        if loaded:
            extra = [n for n in sorted(loaded.keys()) if n not in preload]
            if extra:
                lines.append("package.loaded (poza preload): " + ", ".join(extra))
        return "\n".join(lines)

    def _m_info(self, a):
        i = kernel_info()
        return (f"KarmazynOS jadro v{i['version']}  D={i['vec_dim']}  "
                f"HRR={'on' if i['hrr_active'] else 'off (zero-dep)'}\n"
                f"prawo: {i['law']}")

    def _m_stats(self, a):
        return str(self.store.stats())

    def _m_tick(self, a):
        # FIX v0.4: walidacja — n musi byc calkowite i >= 1; wczesniej
        # `:tick -5` przechodzilo do settle(-5) = ciche no-op.
        if a:
            try:
                n = int(a[0])
            except ValueError:
                return "uzycie: :tick [n>=1]"
            if n < 1:
                return "uzycie: :tick [n>=1]"
        else:
            n = 1
        before = self.store.stats()
        self.store.settle(n)
        after = self.store.stats()
        d_reaped = after["reaped"] - before["reaped"]
        d_total = before["total"] - after["total"]
        return f"tick x{n}: ubylo {d_total} atomow (zreapowano {d_reaped}); -> {after}"

    def _m_gc(self, a):
        before = self.store.stats()["reaped"]
        for _ in range(1000):
            st = self.store.stats()
            r0 = st["reaped"]
            self.store.tick()
            st2 = self.store.stats()
            # stop: nic nie zreapowano i nie ma atomow zywych termicznie (T ≥ T_TOMB)
            alive = st2.get("alive", st2.get("hot", 0))
            if st2["reaped"] == r0 and alive == 0:
                break
        reaped = self.store.stats()["reaped"] - before
        # FIX v0.4: uczciwy komunikat — vacuum studzi WSZYSTKO; to co przezylo,
        # przezylo przez osiagalnosc (retained-TOMB), nie przez temperature.
        return (f"vacuum: zreapowano {reaped}; zmienne-korzeniowe przetrwaly "
                f"jako retained-TOMB (:ls tomb) -> {self.store.stats()}")

    def _m_ls(self, a):
        state = a[0] if a else None
        atoms = self.store.atoms(state)
        if not atoms:
            return "(brak atomow)" + (f" w stanie {state}" if state else "")
        return "\n".join(f"  {x.id:4}  T={x.T:5.1f} {x.state:4}  S={x.S!r} E={x.E!r}"
                         for x in atoms)

    def _m_env(self, a):
        b = self.env
        if b is None:
            return "(brak env — ewaluator bez korzenia)"
        out = []
        depth = 0
        while b is not None:
            # Lua: klucze s:name w bindings; Lisp: nazwy proste
            keys = list(getattr(b, "bindings", {}).keys())
            # skroc: pokaz uzytkownicze / bez wewnetrznych @
            shown = []
            for k in keys:
                if isinstance(k, str) and k.startswith("@"):
                    continue
                if isinstance(k, str) and k.startswith("s:"):
                    shown.append(k[2:])
                else:
                    shown.append(str(k))
            names = ", ".join(shown) or "(puste)"
            if len(names) > 200:
                names = names[:200] + "…"
            out.append(f"  {'  '*depth}{b.label}: {names}")
            b = b.parent
            depth += 1
        return "\n".join(out)

    def _m_find(self, a):
        if not a:
            return "uzycie: :find <zapytanie>"
        hits = self.store.resonance(" ".join(a), k=5)
        if not hits:
            return "brak rezonansu (HRR/numpy nieaktywne)"
        return "\n".join(f"  {sim:.3f}  {aid}" for sim, aid in hits)

    def _m_new(self, a):
        if not a:
            return "uzycie: :new <S> [E]"
        S = a[0]; E = " ".join(a[1:]) if len(a) > 1 else ""
        atom = self.store.atom_new(S, E)
        return f"sierota {atom.id}  S={S!r} E={E!r} (niezwiazana)"

    def _m_exit(self, a):
        return "__EXIT__"


def _scheduler(store, interval, stop):
    while not stop.wait(interval):
        store.tick()


class BootError(RuntimeError):
    """Start przerwany — usluga krytyczna nie wstala (zgloszona jako [FAIL])."""


def boot(verbose_events=False, log=None):
    """Sekwencja startowa z raportem uslug. Zwraca (store, shell).
    Awaria uslugi krytycznej -> [FAIL] + BootError (czysto, bez surowego traceback)."""
    log = log or BootLog()
    print("=" * 60)
    print("  KarmazynOS — sekwencja startowa")
    print("=" * 60)

    # 1. fasada jadra (musi zaladowac sie samodzielnie)
    t = time.perf_counter()
    try:
        i = kernel_info()
    except Exception as e:
        log.fail("fasada jadra", f"{type(e).__name__}: {e}")
        raise BootError("fasada jadra nie wstala") from e
    log.ok("fasada jadra", f"v{i['version']} D={i['vec_dim']}", _ms(t))
    if i["hrr_active"]:
        log.ok("HRR (wektory)", "aktywne (numpy)")
    else:
        log.warn("HRR (wektory)", "wylaczone — brak numpy (tryb zero-dep)")

    # 2. substrat (Store + reach-GC)
    t = time.perf_counter()
    try:
        store = Store(thermal=True)
    except Exception as e:
        log.fail("substrat (Store)", f"{type(e).__name__}: {e}")
        raise BootError("substrat nie wstal") from e
    log.ok("substrat (Store, reach-GC)", f"prawo: {i['law']}", _ms(t))

    # 3. warstwa wykonawcza (montaz: env_of + korzen) — domyslnie Lua
    t = time.perf_counter()
    try:
        evaluator = mount_evaluator(store)
    except Exception as e:
        log.fail("warstwa wykonawcza", f"{type(e).__name__}: {e}")
        raise BootError("warstwa wykonawcza nie wstala") from e
    env = getattr(evaluator, "env", None) or getattr(evaluator, "G", None)
    wired = (env is not None and env in store.roots)
    guest = _GUEST_KIND
    detail = f"gosc={guest}, korzen={'tak' if wired else 'NIE'}"
    err = getattr(evaluator, "_lua_mount_error", None)
    if err is not None:
        log.warn("warstwa wykonawcza", f"{detail}; Lua niedostepna: {err}", _ms(t))
    else:
        log.ok("warstwa wykonawcza", detail, _ms(t))
    if guest == "lua":
        ntools = len(getattr(evaluator, "_preload", {}) or {})
        if ntools:
            log.ok("narzedzia Lua", f"package.preload x{ntools}")
        else:
            log.ok("narzedzia Lua", "package.preload gotowy (pusto — :tools)")

    # 4. shell
    t = time.perf_counter()
    shell = KarmazynShell(store, evaluator, verbose_events=verbose_events)
    log.ok("shell", "prompt gotowy", _ms(t))

    return store, shell


def _setup_history():
    if not _HAS_READLINE:
        return
    import atexit
    histfile = os.path.expanduser("~/.karmazyn_history")
    try:
        if os.path.exists(histfile):
            readline.read_history_file(histfile)
        atexit.register(readline.write_history_file, histfile)
    except Exception:
        pass


def repl(interval=2.0):
    log = BootLog()
    try:
        store, shell = boot(verbose_events=True, log=log)
    except BootError as e:
        print(f"\n  start przerwany: {e}")
        sys.exit(1)

    # uslugi REPL (osobno, bo zalezne od trybu interaktywnego)
    _setup_history()
    if _HAS_READLINE:
        log.ok("historia (readline)", "~/.karmazyn_history")
    else:
        log.warn("historia", "readline niedostepne — bez historii linii")

    stop = threading.Event()
    threading.Thread(target=_scheduler, args=(store, interval, stop), daemon=True).start()
    log.ok("scheduler termiczny", f"tick co {interval:g}s (tlo, pod Store.lock)")

    print("  " + "-" * 56)
    print("  start zakonczony. Wpisz kod albo ':help'.\n")
    try:
        while True:
            out = shell.feed(input("karmazyn> "))
            if out == "__EXIT__":
                break
            if out:
                print(out)
    except (EOFError, KeyboardInterrupt):
        print()
    finally:
        stop.set()
    print("Zamykanie KarmazynOS.")


def demo():
    store, shell = boot(verbose_events=True)
    print("  " + "-" * 56)
    print("  start zakonczony (tryb demo).\n")
    if _GUEST_KIND == "lua":
        script = [
            ":info",
            ":help",
            "x = 10",
            "y = x + 5",
            "return x + y",
            "function square(n) return n * n end",
            "return square(7)",
            "keep = 123",
            ":new sierota orphan-bez-wiazania",
            ":ls",
            ":tick 200",
            "return keep",
            # narzedzie jako modul w package.preload
            "package.preload.echo = function() local M = {}; function M.run(s) return 'echo:' .. tostring(s) end; return M end",
            "e = require('echo')",
            "return e.run('karmazyn')",
            "function counter() local n = 0; return function() n = n + 1; return n end end",
            "c = counter()",
            "return c()",
            "return c()",
            ":tick 100",
            "return c()",
            ":tools",
            ":env",
            ":stats",
            ":exit",
        ]
    else:
        script = [
            ":info",
            "(define x 10)", "(define y (+ x 5))", "(+ x y)",
            "(if (> y x) (* x y) 0)",
            "(define keep 123)",
            ":new sierota orphan-bez-wiazania",
            ":ls", ":tick 200", ":ls tomb", "keep", "(+ keep x)",
            "(define counter (lambda () (begin (define n 0) (lambda () (begin (set! n (+ n 1)) n)))))",
            "(define c (counter))", "(c)", "(c)", ":tick 100", "(c)",
            ":tick -5",
            ":env", ":stats", ":exit",
        ]
    for line in script:
        print(f"\nkarmazyn> {line}")
        out = shell.feed(line)
        if out == "__EXIT__":
            break
        if out:
            print(out)
    print("\n[demo] gosc=%s; zmienne/tabele zyja pod reach-GC." % _GUEST_KIND)


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    else:
        repl()