"""karmazyn_lua.lib — kotwica bibliotek (LuaLib) + mount.

Kontrakt gościa KarmazynOS:
  - import jądra tylko przez values → karmazyn_kernel
  - biblioteki-bloki: register(lib), zero ambient authority
  - piaskownica Karmin = bąbel (root_bubble) + φ + polityka caps
"""

from .values import (
    LuaError, _tostring, _tonumber, _type, Bubble,
    _keyname, _own_atom, _array_len, lua_env_of, compose_phi,
)
from .evaluator import Evaluator


# =====================================================================
#  POLITYKA φ — które biblioteki wolno załadować w sesji Karmin
# =====================================================================
# Nazwy modułów-bloków. "basic" jest zawsze w ewaluatorze (builtins).
_ALL_LIBS = (
    "karmazyn_lua_math",
    "karmazyn_lua_table",
    "karmazyn_lua_string",
    "karmazyn_lua_os",
    "karmazyn_lua_utf8",
)

# profile: zbiór dozwolonych *krótkich* nazw → mapowanie na moduły
_LIB_ALIAS = {
    "math": "karmazyn_lua_math",
    "table": "karmazyn_lua_table",
    "string": "karmazyn_lua_string",
    "os": "karmazyn_lua_os",
    "utf8": "karmazyn_lua_utf8",
}

_PHI_PROFILES = {
    # pełny gość skryptowy (domyślnie) — io wirtualne jest w rdzeniu (builtins)
    "default": frozenset({"math", "table", "string", "os", "utf8"}),
    # twarda piaskownica: bez os
    "strict": frozenset({"math", "table", "string", "utf8"}),
    # tylko obliczenia
    "compute": frozenset({"math", "table"}),
    # wszystko z listy
    "full": frozenset({"math", "table", "string", "os", "utf8"}),
}


def resolve_caps(phi=None, caps=None):
    """Wyznacz zbiór krótkich nazw lib dozwolonych w sesji.

    caps: None | str (profil) | iterable[str] | obiekt z .caps
    phi:  jeśli ma atrybut .caps lub .profile — użyte gdy caps is None
    """
    if caps is None and phi is not None:
        caps = getattr(phi, "caps", None) or getattr(phi, "profile", None)
    if caps is None:
        return set(_PHI_PROFILES["default"])
    if isinstance(caps, str):
        if caps in _PHI_PROFILES:
            return set(_PHI_PROFILES[caps])
        # pojedyncza nazwa lib
        return {caps}
    if isinstance(caps, (set, frozenset, list, tuple)):
        return set(caps)
    raise LuaError(f"nieprawidłowe caps: {caps!r}")


# =====================================================================
#  KONTRAKT GOŚCIA: mount(store) -> obiekt z eval_line
# =====================================================================
class LuaLib:
    """Kotwica bibliotek — wąski, stabilny interfejs do rejestrowania
    modułów-bloków. Biblioteka definiuje register(lib) i używa WYŁĄCZNIE metod
    'lib', bez sięgania do wnętrza interpretera ani do jądra."""

    def __init__(self, ev):
        self._ev = ev
        self.Error = LuaError

    def table(self):
        return self._ev.store.bubble_new("table")

    def set(self, tbl, name, value):
        self._ev._table_set(tbl, name, value)

    def globalize(self, name, value):
        atom = self._ev.store.atom_new("lib", name, value=value)
        self._ev.G.bind(name, atom)

    def call(self, fn, args):
        return self._ev._call(fn, list(args))

    def get(self, tbl, key):
        return self._ev._table_get(tbl, key)

    def rawget(self, tbl, key):
        atom = _own_atom(tbl, _keyname(key))
        return atom.metadata["v"] if atom is not None else None

    def arraylen(self, tbl):
        return _array_len(tbl)

    def set_type_metatable(self, typename, mt):
        self._ev._type_mt[typename] = mt

    @staticmethod
    def tostring(v):
        return _tostring(v)

    @staticmethod
    def tonumber(v):
        return _tonumber(v)

    @staticmethod
    def typename(v):
        return _type(v)

    @staticmethod
    def is_table(v):
        return isinstance(v, Bubble)


def _libs_for_caps(allowed):
    """allowed: zbiór krótkich nazw → lista zaimportowanych modułów."""
    mods = []
    for short in allowed:
        modname = _LIB_ALIAS.get(short, short)
        try:
            mods.append(__import__(modname))
        except ImportError:
            pass
    return mods


def _default_libs():
    return _libs_for_caps(_PHI_PROFILES["default"])


def install_env_of(store):
    prev = getattr(store, "_env_of", None)

    def _env_of(v):
        r = lua_env_of(v)
        if r is not None:
            return r
        if prev is not None and prev is not _env_of:
            try:
                return prev(v)
            except Exception:
                return None
        return None

    store._env_of = _env_of
    return store


def mount(store, libs=None, root_bubble=None, env_label="lua",
          phi=None, phi1=None, phi2=None, caps=None,
          budget=None, io_input=None, tools=None, project=None):
    """Zamontuj interpreter Lua na substracie.

    store        — karmazyn_kernel.Store
    libs         — lista modułów z register(lib); None = wg caps/φ
    root_bubble  — bąbel sesji Karmin; None = nowy bubble
    phi / phi1,phi2 — token φ (φ = φ1·φ2)
    caps         — polityka lib: 'default'|'strict'|'compute'|'full'
    budget       — max. „instrukcji” (_exec_stmt ticks); None = bez limitu
    io_input     — lista stringów do io.read() (kolejka FIFO)
    tools        — dict{nazwa: źródło str|callable} lub ścieżka katalogu *.lua
                   → package.preload (narzędzia OS: require "nazwa")
    project      — ProjectSpec | ścieżka root | None
                   → package.searchers[2] (host czyta pliki pod rootem)

    Zwraca Evaluator (ev.phi, ev.caps, ev.budget; ev.env == ev.G).
    """
    if phi1 is not None or phi2 is not None:
        phi = compose_phi(phi1 if phi1 is not None else phi, phi2)
    allowed = resolve_caps(phi, caps)
    install_env_of(store)
    ev = Evaluator(
        store,
        env_label=env_label,
        root_bubble=root_bubble,
        phi=phi,
    )
    ev.caps = frozenset(allowed)
    if budget is not None:
        ev.budget = int(budget)
        ev._budget_used = 0
    if io_input:
        ev._io_input = list(io_input)
    reg = LuaLib(ev)
    if libs is not None:
        load = libs
    else:
        load = _libs_for_caps(allowed)
    for lib in load:
        lib.register(reg)
    # liby też zadeklarowane w strict
    for n in ("math", "table", "string", "os", "utf8", "package", "coroutine", "io"):
        if _own_has_safe(ev, n):
            ev._declared_globals.add(n)
    if tools is not None:
        install_tools(ev, tools)
    if project is not None:
        from .project import ProjectSpec, install_project_searcher
        spec = project if not isinstance(project, str) else ProjectSpec.from_root(project)
        install_project_searcher(ev, spec)
    return ev


def install_tools(ev, tools):
    """Zainstaluj narzędzia w package.preload ewaluatora.

    tools:
      - dict {name: source_str | callable}
      - ścieżka do katalogu: każdy plik *.lua → preload[basename]
    """
    import os
    if isinstance(tools, str):
        root = tools
        if not os.path.isdir(root):
            raise LuaError(f"install_tools: brak katalogu {root!r}")
        for fn in sorted(os.listdir(root)):
            if not fn.endswith(".lua"):
                continue
            name = fn[:-4]
            path = os.path.join(root, fn)
            with open(path, encoding="utf-8") as f:
                src = f.read()
            ev.register_preload(name, src, chunkname=f"@{path}")
        return ev
    if isinstance(tools, dict):
        for name, src in tools.items():
            ev.register_preload(str(name), src)
        return ev
    raise LuaError(f"install_tools: oczekiwano dict lub ścieżki, dostano {type(tools).__name__}")


def _own_has_safe(ev, name):
    try:
        from .values import _own_has
        return _own_has(ev.G, name)
    except Exception:
        return name in getattr(ev.G, "bindings", {})
