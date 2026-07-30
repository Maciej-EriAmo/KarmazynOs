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
    from karmazyn_backend import (
        open_store,
        native_available,
        substrate_backend,
        apply_cli_substrate_flags,
        backend_info,
    )
except Exception:  # pragma: no cover
    open_store = None
    native_available = lambda: False
    substrate_backend = lambda explicit=None: "python"
    apply_cli_substrate_flags = lambda argv=None: None
    backend_info = lambda: {"backend": "python", "native_available": False}

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
    # Prefer katalog z warstwą projektu (project.py), potem in-repo, sibling.
    # Dzięki temu dev w C:\Users\…\LUA nie gubi się za starym mirror w monorepo.
    candidates = [
        os.path.join(here, "LUA"),
        os.path.join(kernel_root, "LUA"),
        os.path.join(here, "karmazyn_lua"),
        os.path.join(here, "lua"),
        os.path.join(parent, "LUA"),
        os.path.join(parent, "Karmazyn_lua"),
    ]
    # Najpierw te, które mają project.py (MVP host→bąbel), potem reszta
    with_proj = [c for c in candidates if c and os.path.isfile(os.path.join(c, "project.py"))]
    without = [c for c in candidates if c and c not in with_proj]
    out.extend(with_proj + without)
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
    # katalog pakietu na sys.path — bloki lib (karmazyn_lua_math, …) importują się po nazwie
    if root not in sys.path:
        sys.path.insert(0, root)
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
    # opcjonalnie: warstwa projektu (host → bąbel)
    try:
        from karmazyn_lua.session import (  # noqa: E402
            mount_session, run_entry, check_project, reload_module, set_project,
        )
        from karmazyn_lua.project import (  # noqa: E402
            ProjectSpec, attach_lua_bin, put_memory_module,
        )
        pkg.mount_session = mount_session
        pkg.run_entry = run_entry
        pkg.check_project = check_project
        pkg.reload_module = reload_module
        pkg.set_project = set_project
        pkg.ProjectSpec = ProjectSpec
        pkg.attach_lua_bin = attach_lua_bin
        pkg.put_memory_module = put_memory_module
    except Exception:
        pass
    return pkg


def _tools_dir():
    """Opcjonalny katalog narzedzi *.lua (KARMAZYN_TOOLS lub software/tools)."""
    env = os.environ.get("KARMAZYN_TOOLS")
    if env and os.path.isdir(env):
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.join(here, "tools")
    return cand if os.path.isdir(cand) else None


def _project_from_env():
    """KARMAZYN_PROJECT → ścieżka root lub None."""
    p = os.environ.get("KARMAZYN_PROJECT")
    if p and os.path.isdir(p):
        return os.path.abspath(p)
    return None


def _normalize_guest(kind):
    """Znormalizuj etykiete gosci: lua | exec. None/'' = z env / domyslnie lua."""
    if kind is None or kind == "":
        kind = os.environ.get("KARMAZYN_GUEST") or "lua"
    k = str(kind).strip().lower()
    if k in ("exec", "lisp", "scheme", "karmazyn_exec", "mini-lisp", "minilisp"):
        return "exec"
    if k in ("lua", "karmazyn_lua"):
        return "lua"
    raise ValueError(f"nieznany gosc: {kind!r}  (lua|exec)")


def _lua_bin_dir():
    """KARMAZYN_LUA_BIN lub monorepo lua_bin/."""
    env = os.environ.get("KARMAZYN_LUA_BIN")
    if env and os.path.isdir(env):
        return os.path.abspath(env)
    here = os.path.dirname(os.path.abspath(__file__))
    kernel_root = os.path.dirname(here)
    for cand in (
        os.path.join(kernel_root, "lua_bin"),
        os.path.join(here, "lua_bin"),
    ):
        if os.path.isdir(cand):
            return cand
    return None


def mount_evaluator(store, kind=None, project=None, tools=None, caps=None,
                    lua_bin=None):
    """Montuje warstwe wykonawcza na Store.

    Domyslnie karmazyn_lua. Alternatywa: karmazyn_exec (mini-Lisp).
    Wymus: kind= | KARMAZYN_GUEST=lua|exec | CLI --lua / --lisp
    project: root projektu (searcher hosta) | KARMAZYN_PROJECT | None
    lua_bin: katalog narzędzi OS (preload) | KARMAZYN_LUA_BIN | monorepo lua_bin
    Kontrakt: eval_line(str)->str, .env = Bubble korzenia (reach-GC).
    Haki reach: register_env_of / register_extra_reach (name='guest').
    """
    global _GUEST_KIND
    prefer = _normalize_guest(kind)
    if prefer == "exec":
        import karmazyn_exec
        _GUEST_KIND = "exec"
        return karmazyn_exec.Evaluator(store, env_label="repl")
    try:
        kl = _ensure_karmazyn_lua()
        tools = tools if tools is not None else _tools_dir()
        if project is None:
            project = _project_from_env()
        if lua_bin is None:
            lua_bin = _lua_bin_dir()
        kwargs = {"env_label": "lua"}
        if tools:
            kwargs["tools"] = tools
        if project:
            kwargs["project"] = project
        if caps:
            kwargs["caps"] = caps
        # mount z project= gdy lib to obsługuje; fallback: mount + set_project
        try:
            ev = kl.mount(store, **kwargs)
        except TypeError:
            kwargs.pop("project", None)
            ev = kl.mount(store, **kwargs)
            if project and getattr(kl, "set_project", None):
                kl.set_project(ev, project)
        # lua_bin: preload + module root (host; gość bez FS)
        if lua_bin and getattr(kl, "attach_lua_bin", None):
            try:
                kl.attach_lua_bin(ev, lua_bin)
            except Exception:
                # nie zabijaj bootu jeśli stary skrypt w bin
                from karmazyn_lua.project import attach_lua_bin
                try:
                    attach_lua_bin(ev, lua_bin)
                except Exception:
                    pass
        elif lua_bin:
            try:
                from karmazyn_lua.project import attach_lua_bin
                attach_lua_bin(ev, lua_bin)
            except Exception:
                pass
        # host API: global `karmazyn` (bindings Store → Lua)
        try:
            from karmazyn_host import install_karmazyn_host
            install_karmazyn_host(ev, store=store)
            ev._lua_bin = lua_bin
        except Exception as hex_:
            ev._host_install_error = hex_
        _GUEST_KIND = "lua"
        return ev
    except Exception as e:
        # prefer=lua (domyslnie lub wymuszone): nie ukrywaj awarii montazu
        if prefer == "lua":
            raise
        import karmazyn_exec
        _GUEST_KIND = "exec"
        ev = karmazyn_exec.Evaluator(store, env_label="repl")
        ev._lua_mount_error = e
        return ev


class KarmazynShell:
    """Prompt: kod -> warstwa wykonawcza; ':...' -> komendy systemu."""

    def __init__(self, store, evaluator, verbose_events=False, project=None):
        self.store = store
        self.ev = evaluator
        self.env = getattr(evaluator, "env", None) or getattr(evaluator, "G", None)
        # root projektu hosta (mapa → bąbel); None = tylko preload/tools
        self.project_root = project or _project_from_env()
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
            "     :project [path] | :run [file] | :reload [mod] | :check\n"
            "     :tool <name>   — skrypt z lua_bin/<name>.lua (host API karmazyn.*)\n"
            "     :guest [lua|exec] | :find <q> | :new <S> <E> | :exit\n"
            "     :gc studzi WSZYSTKO: sieroty gina, korzenie jako retained-TOMB (:ls tomb)\n"
            "     projekt = mapa host→bąbel; sandbox=bąbel; host montuje karmazyn.*"
        )

    def _m_guest(self, a):
        """Pokaz / przelacz gościa: :guest | :guest lua | :guest exec|lisp."""
        global _GUEST_KIND
        if not a:
            hooks = {}
            if hasattr(self.store, "hook_names"):
                hooks = self.store.hook_names()
            return (
                f"gosc={_GUEST_KIND}  haki={hooks}\n"
                "  :guest lua   — karmazyn_lua\n"
                "  :guest exec  — mini-Lisp (karmazyn_exec)\n"
                "  start: --lua | --lisp  albo  KARMAZYN_GUEST=lua|exec"
            )
        try:
            want = _normalize_guest(a[0])
        except ValueError as e:
            return str(e)
        if want == _GUEST_KIND:
            return f"gosc={_GUEST_KIND} (bez zmian)"
        old_env = self.env
        try:
            ev = mount_evaluator(
                self.store, kind=want, project=self.project_root,
            )
        except Exception as e:
            return f"nie udalo sie zamontowac {want}: {type(e).__name__}: {e}"
        if old_env is not None and old_env is not (
            getattr(ev, "env", None) or getattr(ev, "G", None)
        ):
            try:
                self.store.unset_root(old_env)
            except Exception:
                pass
        self.ev = ev
        self.env = getattr(ev, "env", None) or getattr(ev, "G", None)
        return f"gosc={_GUEST_KIND}  (przelaczono; nowy korzen env)"

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
                    "  albo pliki *.lua w software/tools/ (auto-preload przy starcie)\n"
                    "  albo :project <dir> + require z plików projektu")
        lines = ["package.preload:"]
        for name in sorted(preload.keys()):
            st = " [loaded]" if name in loaded else ""
            lines.append(f"  {name}{st}")
        if loaded:
            extra = [n for n in sorted(loaded.keys()) if n not in preload]
            if extra:
                lines.append("package.loaded (poza preload): " + ", ".join(extra))
        return "\n".join(lines)

    def _m_project(self, a):
        """Pokaż / ustaw root projektu (host mapa → bąbel searcher)."""
        if _GUEST_KIND != "lua":
            return "gosc exec: :project tylko dla Lua"
        if not a:
            spec = getattr(self.ev, "project", None)
            if spec is not None:
                return f"project={spec.root}"
            if self.project_root:
                return f"project={self.project_root} (env; nie podpięty do searchera?)"
            return ("project=(brak)\n"
                    "  :project <katalog>  — require z plików pod rootem\n"
                    "  start: --project PATH  lub  KARMAZYN_PROJECT=PATH")
        root = os.path.abspath(a[0])
        if not os.path.isdir(root):
            return f"brak katalogu: {root}"
        try:
            kl = _ensure_karmazyn_lua()
            set_project = getattr(kl, "set_project", None)
            if set_project is None:
                from karmazyn_lua.session import set_project as set_project  # noqa
            set_project(self.ev, root)
        except Exception as e:
            return f"nie udalo sie podpiac projektu: {type(e).__name__}: {e}"
        self.project_root = root
        os.environ["KARMAZYN_PROJECT"] = root
        return f"project={root}  (searcher aktywny; :run / require \"mod\")"

    def _m_run(self, a):
        """Uruchom main.lua projektu lub wskazany plik (host czyta FS)."""
        if _GUEST_KIND != "lua":
            return "gosc exec: :run tylko dla Lua"
        entry = a[0] if a else None
        try:
            kl = _ensure_karmazyn_lua()
            run_entry = getattr(kl, "run_entry", None)
            if run_entry is None:
                from karmazyn_lua.session import run_entry  # noqa
            # jeśli brak projektu a podano plik — jednorazowy run_file
            if entry is None and getattr(self.ev, "project", None) is None:
                if self.project_root:
                    self._m_project([self.project_root])
                else:
                    return "uzycie: :run [plik]  (najpierw :project <dir> lub main.lua)"
            kind, text = run_entry(self.ev, entry=entry)
            return text if text else f"(run {kind})"
        except Exception as e:
            return f"blad :run: {type(e).__name__}: {e}"

    def _m_reload(self, a):
        """Wyczyść cache require; opcjonalnie przeładuj moduł z dysku projektu."""
        if _GUEST_KIND != "lua":
            return "gosc exec: :reload tylko dla Lua"
        name = a[0] if a else None
        try:
            kl = _ensure_karmazyn_lua()
            reload_module = getattr(kl, "reload_module", None)
            if reload_module is None:
                from karmazyn_lua.session import reload_module  # noqa
            return reload_module(self.ev, name)
        except Exception as e:
            return f"blad :reload: {type(e).__name__}: {e}"

    def _m_check(self, a):
        """Parse wszystkich *.lua w projekcie (bez wykonania)."""
        if _GUEST_KIND != "lua":
            return "gosc exec: :check tylko dla Lua"
        if a:
            # jednorazowo podłącz katalog
            r = self._m_project([a[0]])
            if r.startswith("brak") or r.startswith("nie"):
                return r
        if getattr(self.ev, "project", None) is None:
            return "uzycie: :check [katalog]  (wymaga projektu)"
        try:
            kl = _ensure_karmazyn_lua()
            check_project = getattr(kl, "check_project", None)
            if check_project is None:
                from karmazyn_lua.session import check_project  # noqa
            errs = check_project(self.ev)
        except Exception as e:
            return f"blad :check: {type(e).__name__}: {e}"
        if not errs:
            return "check: OK"
        return "check FAIL:\n" + "\n".join(errs)

    def _m_tool(self, a):
        """Uruchom skrypt narzędzia z lua_bin (host API karmazyn.*)."""
        if _GUEST_KIND != "lua":
            return "gosc exec: :tool tylko dla Lua"
        if not a:
            # lista narzędzi
            root = getattr(self.ev, "_lua_bin", None) or _lua_bin_dir()
            if not root or not os.path.isdir(root):
                return "uzycie: :tool <name>  (brak lua_bin)"
            names = sorted(
                fn[:-4] for fn in os.listdir(root)
                if fn.endswith(".lua") and not fn.startswith(".")
            )
            if not names:
                return f"(pusto w {root})"
            return "lua_bin:\n  " + "\n  ".join(names) + "\n  uzycie: :tool ls"
        name = a[0]
        try:
            from karmazyn_host import run_lua_tool
            ret = run_lua_tool(
                self.ev, name,
                lua_bin=getattr(self.ev, "_lua_bin", None) or _lua_bin_dir(),
            )
            return self.ev.format_run_result(ret=ret)
        except FileNotFoundError as e:
            return str(e)
        except Exception as e:
            from karmazyn_lua.values import LuaError
            if isinstance(e, LuaError):
                return self.ev.format_run_result(err=e)
            return f"blad :tool: {type(e).__name__}: {e}"

    def _m_info(self, a):
        i = kernel_info()
        sub = i.get("substrate") or {}
        be = sub.get("backend") or type(self.store).__name__
        return (f"KarmazynOS jadro v{i['version']}  D={i['vec_dim']}  "
                f"HRR={'on' if i['hrr_active'] else 'off (zero-dep)'}\n"
                f"substrat: {be}  store={type(self.store).__name__}\n"
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


def boot(verbose_events=False, log=None, project=None):
    """Sekwencja startowa z raportem uslug. Zwraca (store, shell).
    Awaria uslugi krytycznej -> [FAIL] + BootError (czysto, bez surowego traceback).
    project: root projektu Lua (host→bąbel) lub None / KARMAZYN_PROJECT."""
    log = log or BootLog()
    if project is None:
        project = _project_from_env()
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

    # 2. substrat (Store + reach-GC) — native Rust domyślnie; Python = referencja
    t = time.perf_counter()
    try:
        if open_store is not None:
            store = open_store(thermal=True)
            backend = substrate_backend()
            if backend == "both":
                backend = "python"
        else:
            store = Store(thermal=True)
            backend = "python"
    except Exception as e:
        # native fail → twardy fallback na pure-Python reference Store
        want_native = False
        try:
            want_native = substrate_backend() == "native"
        except Exception:
            want_native = False
        if open_store is not None and want_native:
            try:
                log.warn("substrat native", f"{type(e).__name__}: {e} → fallback python")
                os.environ["KARMAZYN_SUBSTRATE"] = "python"
                store = open_store(thermal=True)
                backend = "python"
            except Exception as e2:
                log.fail("substrat (Store)", f"{type(e2).__name__}: {e2}")
                raise BootError("substrat nie wstal") from e2
        else:
            log.fail("substrat (Store)", f"{type(e).__name__}: {e}")
            raise BootError("substrat nie wstal") from e
    sub_detail = f"backend={backend}, prawo: {i['law']}"
    if backend == "native":
        try:
            from karmazyn_backend import backend_info as _bi
            bi = _bi() or {}
            ver = bi.get("native_version") or "?"
            bridge = bi.get("native_bridge") or getattr(store, "native_backend", "?")
            sub_detail = f"backend=native/{bridge} ({ver}), prawo: {i['law']}"
        except Exception:
            bridge = getattr(store, "native_backend", "?")
            sub_detail = f"backend=native/{bridge}, prawo: {i['law']}"
    else:
        sub_detail = f"backend=python (reference), prawo: {i['law']}"
    log.ok("substrat (Store, reach-GC)", sub_detail, _ms(t))

    # 3. warstwa wykonawcza (montaz: env_of + korzen) — domyslnie Lua
    t = time.perf_counter()
    try:
        evaluator = mount_evaluator(store, project=project)
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
        spec = getattr(evaluator, "project", None)
        if spec is not None:
            log.ok("projekt Lua", spec.root)
        elif project:
            log.warn("projekt Lua", f"ustawiono {project}, ale searcher nieaktywny")
        if getattr(evaluator, "host", None) is not None:
            log.ok("host API", "global karmazyn.* (Store bindings)")
        elif getattr(evaluator, "_host_install_error", None):
            log.warn("host API", str(evaluator._host_install_error))
        lb = getattr(evaluator, "_lua_bin", None)
        if lb:
            log.ok("lua_bin", lb)

    # 4. shell
    t = time.perf_counter()
    shell = KarmazynShell(
        store, evaluator, verbose_events=verbose_events, project=project,
    )
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


def _apply_cli_guest_flags(argv):
    """--lua / --lisp|--exec  oraz  --guest NAME  -> KARMAZYN_GUEST."""
    if "--lua" in argv:
        os.environ["KARMAZYN_GUEST"] = "lua"
    if "--lisp" in argv or "--exec" in argv:
        os.environ["KARMAZYN_GUEST"] = "exec"
    if "--guest" in argv:
        i = argv.index("--guest")
        if i + 1 < len(argv):
            os.environ["KARMAZYN_GUEST"] = argv[i + 1]


def _apply_cli_project_flags(argv):
    """--project PATH → KARMAZYN_PROJECT (host mapa plików → bąbel)."""
    if "--project" in argv:
        i = argv.index("--project")
        if i + 1 < len(argv):
            os.environ["KARMAZYN_PROJECT"] = os.path.abspath(argv[i + 1])


if __name__ == "__main__":
    _apply_cli_guest_flags(sys.argv)
    _apply_cli_project_flags(sys.argv)
    if "--demo" in sys.argv:
        demo()
    else:
        repl()