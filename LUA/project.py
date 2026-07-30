"""karmazyn_lua.project — hostowa mapa projektu → bąbel (bez ambient FS w gościu).

Zasada: sandbox = bąbel. Host czyta pliki pod rootem projektu i wpuszcza źródła
przez package.searchers. Gość nie dostaje dofile/loadfile ani package.path OS.

Kolejność package.searchers:
  [1] preload (tools / package.preload)
  [2] memory  (bufory edytora / put_memory_module)
  [3] project (pliki pod rootem projektu)
"""

from __future__ import annotations

import os

from .values import LuaError


def _norm_real(path: str) -> str:
    return os.path.normcase(os.path.realpath(path))


def _is_under(root_real: str, cand_real: str) -> bool:
    """True gdy cand leży w root (lub jest rootem). Windows: normcase."""
    if cand_real == root_real:
        return True
    prefix = root_real
    if not prefix.endswith(os.sep):
        prefix = prefix + os.sep
    return cand_real.startswith(prefix)


class ProjectSpec:
    """Opis projektu hosta: root + katalogi modułów + polityka."""

    def __init__(self, root, module_roots=None, main=None, tools=None,
                 caps=None, phi=None, budget=None, strict=True,
                 extra_roots=None):
        if not root or not isinstance(root, str):
            raise LuaError("ProjectSpec: root musi być ścieżką")
        root_abs = os.path.abspath(root)
        if not os.path.isdir(root_abs):
            raise LuaError(f"ProjectSpec: brak katalogu projektu {root_abs!r}")
        self.root = root_abs
        self.root_real = _norm_real(root_abs)
        if module_roots is None:
            candidates = [root_abs,
                          os.path.join(root_abs, "lib"),
                          os.path.join(root_abs, "src")]
            module_roots = [p for p in candidates if os.path.isdir(p)]
            if root_abs not in module_roots:
                module_roots.insert(0, root_abs)
        extra = list(extra_roots or [])
        self.module_roots = [os.path.abspath(p) for p in list(module_roots) + extra
                             if os.path.isdir(os.path.abspath(p))]
        # dedupe zachowując kolejność
        seen = set()
        uniq = []
        for p in self.module_roots:
            r = _norm_real(p)
            if r not in seen:
                seen.add(r)
                uniq.append(p)
        self.module_roots = uniq
        self.module_roots_real = [_norm_real(p) for p in self.module_roots]
        self.main = main
        self.tools = tools
        self.caps = caps
        self.phi = phi
        self.budget = budget
        self.strict = bool(strict)

    @classmethod
    def from_root(cls, root, **kwargs):
        return cls(root, **kwargs)

    def path_allowed(self, abspath: str) -> bool:
        """Czy host może uruchomić ten plik przy strict=True."""
        try:
            pr = _norm_real(abspath)
        except OSError:
            return False
        if _is_under(self.root_real, pr):
            return True
        return any(_is_under(r, pr) for r in self.module_roots_real)

    def rel_chunkname(self, abspath: str) -> str:
        """Chunkname @względny do root (stabilny w błędach)."""
        try:
            rel = os.path.relpath(abspath, self.root)
        except ValueError:
            rel = os.path.basename(abspath)
        rel = rel.replace("\\", "/")
        return "@" + rel

    def _candidates_for(self, modname: str):
        """Ścieżki kandydujące dla require 'a.b' (kolejność jak Lua path)."""
        if not isinstance(modname, str) or not modname or modname.endswith("."):
            return []
        parts = modname.replace("\\", "/").split(".")
        if any(p in ("", "..") or os.sep in p or "/" in p for p in parts):
            return []
        if any(p == "." for p in parts):
            return []
        rel_base = os.path.join(*parts)
        out = []
        for mroot in self.module_roots:
            out.append(os.path.join(mroot, rel_base + ".lua"))
            out.append(os.path.join(mroot, rel_base, "init.lua"))
        return out

    def resolve(self, modname: str):
        """Znajdź moduł. Zwraca (abspath, source, chunkname) albo None."""
        for cand in self._candidates_for(modname):
            if not os.path.isfile(cand):
                continue
            try:
                cand_real = _norm_real(cand)
            except OSError:
                continue
            if not any(_is_under(r, cand_real) for r in self.module_roots_real):
                continue
            try:
                with open(cand, encoding="utf-8") as f:
                    source = f.read()
            except OSError:
                continue
            # chunkname: względem project root jeśli pod nim, inaczej basename
            if _is_under(self.root_real, cand_real):
                cname = self.rel_chunkname(cand)
            else:
                cname = "@" + os.path.basename(cand)
            return cand, source, cname
        return None

    def resolve_path_display(self, modname: str):
        hit = self.resolve(modname)
        return hit[0] if hit else None

    def find_main(self, entry=None):
        """Wyznacz plik startowy: entry | self.main | main.lua w root."""
        if entry:
            p = entry
            if not os.path.isabs(p):
                p = os.path.join(self.root, p)
            p = os.path.abspath(p)
            if os.path.isdir(p):
                p = os.path.join(p, "main.lua")
            if not os.path.isfile(p):
                raise LuaError(f"brak pliku startowego: {p!r}")
            return p
        if self.main:
            return self.find_main(self.main)
        main = os.path.join(self.root, "main.lua")
        if os.path.isfile(main):
            return main
        raise LuaError(f"brak main.lua w projekcie {self.root!r}")

    def iter_lua_files(self):
        """Wszystkie *.lua pod root (do check)."""
        for dirpath, _dirnames, filenames in os.walk(self.root):
            base = os.path.basename(dirpath)
            if base.startswith(".") or base == "__pycache__":
                continue
            for fn in filenames:
                if fn.endswith(".lua"):
                    yield os.path.join(dirpath, fn)


def _bind_searcher(ev, index, fn):
    searchers = getattr(ev, "_package_searchers", None)
    if searchers is None:
        raise LuaError("brak package.searchers na ewaluatorze")
    key = f"i:{index}"
    sa = ev.store.atom_new("field", key, value=fn)
    sa.metadata["k"] = index
    searchers.bind(key, sa)
    return searchers


def install_memory_searcher(ev):
    """Searcher[2]: package z host _memory_modules (bufory edytora).

    Gość nie pisze do _memory_modules — tylko host (EditorBridge / put_memory).
    """
    mem = getattr(ev, "_memory_modules", None)
    if mem is None:
        ev._memory_modules = {}
        mem = ev._memory_modules

    def b_searcher_memory(modname=None, *_):
        if not isinstance(modname, str):
            return None
        source = mem.get(modname)
        if source is None:
            return "\n\tno field memory['" + modname + "']"
        cname = "@memory:" + modname

        def loader(name=None, *_a):
            # świeże źródło przy każdym ładowaniu (po clear cache)
            src = mem.get(modname if name is None else name, source)
            return ev.run_source(src, chunkname=cname, as_module=True)

        return [loader, modname]

    _bind_searcher(ev, 2, b_searcher_memory)
    return ev


def install_project_searcher(ev, spec: ProjectSpec):
    """Searcher[3]: pliki pod rootem projektu (po memory)."""
    if spec is None:
        return ev

    def b_searcher_project(modname=None, *_):
        if not isinstance(modname, str):
            return None
        hit = spec.resolve(modname)
        if hit is None:
            return "\n\tno file under project for '" + modname + "'"
        _path, source, cname = hit

        def loader(name=None, *_a):
            # ponowne resolve przy reload — świeży odczyt z dysku
            again = spec.resolve(modname if name is None else name)
            if again is None:
                return ev.run_source(source, chunkname=cname, as_module=True)
            _p2, src2, cn2 = again
            return ev.run_source(src2, chunkname=cn2, as_module=True)

        return [loader, modname]

    # upewnij się, że memory searcher też jest (puste mapy OK)
    install_memory_searcher(ev)
    _bind_searcher(ev, 3, b_searcher_project)
    ev.project = spec
    return ev


def put_memory_module(ev, name, source):
    """Host: wstrzyknij / zaktualizuj moduł w pamięci (edytor). Czyści package.loaded[name]."""
    if not isinstance(name, str) or not name:
        raise LuaError("put_memory_module: nazwa")
    if not isinstance(source, str):
        raise LuaError("put_memory_module: source = string")
    if getattr(ev, "_memory_modules", None) is None:
        ev._memory_modules = {}
    install_memory_searcher(ev)
    ev._memory_modules[name] = source
    modules = getattr(ev, "_modules", None)
    if modules is not None:
        modules.pop(name, None)
    return name


def clear_memory_module(ev, name=None):
    """Host: usuń bufor(y) pamięci."""
    mem = getattr(ev, "_memory_modules", None)
    if not mem:
        return
    if name is None:
        mem.clear()
    else:
        mem.pop(name, None)
        mods = getattr(ev, "_modules", None)
        if mods is not None:
            mods.pop(name, None)


def attach_lua_bin(ev, lua_bin_dir, as_tools=True, as_module_root=None):
    """Zamontuj katalog lua_bin: tools (preload) + opcjonalnie module root.

    as_module_root:
      None  — True tylko gdy ev.project już istnieje (nie nadpisuj :project)
      True  — dodaj do module_roots projektu; bez projektu tylko preload
      False — wyłącznie package.preload (tools)

    Nie tworzy mini-ProjectSpec z root=lua_bin (to myliło :project / :run).
    """
    from .lib import install_tools

    if not lua_bin_dir or not os.path.isdir(lua_bin_dir):
        raise LuaError(f"attach_lua_bin: brak katalogu {lua_bin_dir!r}")
    path = os.path.abspath(lua_bin_dir)
    if as_tools:
        install_tools(ev, path)
    if as_module_root is None:
        as_module_root = getattr(ev, "project", None) is not None
    if as_module_root:
        spec = getattr(ev, "project", None)
        if spec is not None:
            if path not in spec.module_roots:
                spec.module_roots.append(path)
                spec.module_roots_real.append(_norm_real(path))
            install_project_searcher(ev, spec)
        # bez projektu: tylko preload — ev.project zostaje None
    ev._lua_bin = path
    return ev
