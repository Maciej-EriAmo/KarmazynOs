"""karmazyn_lua.session — montaż sesji z projektem (host API).

Jeden kontrakt dla CLI, bootu i przyszłego edytora:
  mount_session(store, project=...) → Evaluator
  run_main(ev) / run_entry(ev, path)
"""

from __future__ import annotations

import os

from karmazyn_kernel import Store

from .lib import mount
from .project import (
    ProjectSpec, install_project_searcher, install_memory_searcher,
    put_memory_module, clear_memory_module, attach_lua_bin,
)
from .values import LuaError


def open_project(root, **kwargs) -> ProjectSpec:
    """Utwórz ProjectSpec z katalogu (walidacja root)."""
    return ProjectSpec.from_root(root, **kwargs)


def mount_session(store=None, project=None, root=None, tools=None,
                  caps=None, phi=None, budget=None, io_input=None,
                  root_bubble=None, lua_bin=None, strict=None,
                  **mount_kwargs):
    """Zamontuj ewaluator; opcjonalnie z projektem (searcher) i tools.

    project: ProjectSpec | str (ścieżka root) | None
    root: alias na project path gdy project is None
    lua_bin: katalog narzędzi OS (preload + module root)
    strict: gdy True, run_entry tylko w obrębie projektu
    """
    if store is None:
        store = Store(thermal=True)
    spec = project
    if spec is None and root is not None:
        spec = ProjectSpec.from_root(root)
    if isinstance(spec, str):
        kw = {}
        if strict is not None:
            kw["strict"] = strict
        spec = ProjectSpec.from_root(spec, **kw)
    if isinstance(spec, ProjectSpec) and strict is not None:
        spec.strict = bool(strict)
    if isinstance(spec, ProjectSpec):
        if tools is None and spec.tools is not None:
            tools = spec.tools
        if caps is None and spec.caps is not None:
            caps = spec.caps
        if phi is None and spec.phi is not None:
            phi = spec.phi
        if budget is None and spec.budget is not None:
            budget = spec.budget
    # nie przekazuj project= do mount jeśli i tak install_project_searcher
    mount_kwargs.pop("project", None)
    ev = mount(
        store,
        tools=tools,
        caps=caps,
        phi=phi,
        budget=budget,
        io_input=io_input,
        root_bubble=root_bubble,
        **mount_kwargs,
    )
    install_memory_searcher(ev)
    if isinstance(spec, ProjectSpec):
        install_project_searcher(ev, spec)
    if lua_bin:
        attach_lua_bin(ev, lua_bin)
    return ev


def run_entry(ev, entry=None, args=None, strict_project=None):
    """Uruchom plik startowy sesji. Zwraca (exit_kind, text).

    exit_kind: 'ok' | 'parse' | 'runtime'
    text: sformatowane wyjście / błąd
    strict_project: None → bierz z ProjectSpec.strict (domyślnie True)
    """
    spec = getattr(ev, "project", None)
    try:
        if entry is None and spec is not None:
            path = spec.find_main()
        elif entry is None:
            raise LuaError("run_entry: brak entry i brak projektu")
        else:
            path = entry
            if not os.path.isabs(path) and spec is not None:
                cand = os.path.join(spec.root, path)
                if os.path.isfile(cand) or os.path.isdir(cand):
                    path = cand
            if os.path.isdir(path):
                path = os.path.join(path, "main.lua")
            path = os.path.abspath(path)
        if strict_project is None:
            strict_project = bool(getattr(spec, "strict", False)) if spec else False
        if strict_project and spec is not None and not spec.path_allowed(path):
            raise LuaError(
                f"strict-project: plik poza projektem: {path!r} "
                f"(root={spec.root!r})"
            )
        cname = None
        if spec is not None:
            try:
                cname = spec.rel_chunkname(path) if spec.path_allowed(path) else (
                    "@" + os.path.basename(path)
                )
            except Exception:
                cname = "@" + os.path.basename(path)
        else:
            cname = "@" + os.path.basename(path)
        ret = ev.run_file(path, chunkname=cname, args=args, as_module=False)
        return "ok", ev.format_run_result(ret=ret)
    except LuaError as e:
        msg = ev.format_run_result(err=e)
        s = str(e)
        kind = "runtime"
        if any(x in s for x in (
            "oczekiwano", "nieoczekiwany", "nieznany znak", "niezamknięty",
            "nadmiarowy", "zła liczba", "token",
        )):
            kind = "parse"
        # line:col w komunikacie też wskazuje parse
        if ": " in s:
            head = s.split(":", 2)
            if len(head) >= 2 and head[0].lstrip("@").replace("\\", "/").split("/")[-1]:
                # @file:1:2: msg or 1:2: msg
                pass
        return kind, msg
    except OSError as e:
        return "runtime", f"blad: {e}"
    except Exception as e:
        return "runtime", f"blad: {type(e).__name__}: {e}"


def check_project(ev_or_spec):
    """Sparsuj wszystkie *.lua w projekcie (bez wykonania). Zwraca listę błędów."""
    from .lexer import tokenize
    from .parser import Parser

    if isinstance(ev_or_spec, ProjectSpec):
        spec = ev_or_spec
    else:
        spec = getattr(ev_or_spec, "project", None)
    if spec is None:
        return ["check: brak projektu na sesji"]
    errors = []
    for path in sorted(spec.iter_lua_files()):
        cname = spec.rel_chunkname(path)
        try:
            with open(path, encoding="utf-8") as f:
                src = f.read()
            Parser(tokenize(src)).parse_chunk()
        except Exception as ex:
            errors.append(f"{cname}: {ex}")
    return errors


def reload_module(ev, name=None):
    """Wyczyść cache require i (opcjonalnie) załaduj ponownie z dysku projektu.

    name=None → wyczyść całe package.loaded (moduły).
    Zwraca komunikat tekstowy dla hosta/REPL.
    """
    modules = getattr(ev, "_modules", None)
    if modules is None:
        return "reload: brak package.loaded (nie-Lua?)"
    if name is None:
        n = len(modules)
        modules.clear()
        return f"reload: wyczyszczono package.loaded ({n} wpisów)"
    if not isinstance(name, str) or not name:
        raise LuaError("reload: oczekiwano nazwy modułu")
    modules.pop(name, None)
    # preload loader zostaje; project searcher czyta plik na nowo przy require
    try:
        mod = ev.eval_line(f"return require({name!r})")
        if isinstance(mod, str) and mod.startswith("blad"):
            return f"reload {name!r}: {mod}"
        return f"reload {name!r}: ok"
    except Exception as e:
        return f"reload {name!r}: {type(e).__name__}: {e}"


def check_buffer(name, text, chunkname=None):
    """Sparsuj bufor edytora (bez FS, bez wykonania). Zwraca None | komunikat błędu."""
    from .lexer import tokenize
    from .parser import Parser

    cname = chunkname or ("@" + (name or "buffer"))
    if not isinstance(text, str):
        return f"{cname}: oczekiwano stringa"
    try:
        Parser(tokenize(text)).parse_chunk()
    except Exception as ex:
        return f"{cname}: {ex}"
    return None


def set_project(ev, root_or_spec):
    """Podłącz / zmień projekt na żywym ewaluatorze (searcher). Zwraca ProjectSpec."""
    if isinstance(root_or_spec, ProjectSpec):
        spec = root_or_spec
    else:
        spec = ProjectSpec.from_root(root_or_spec)
    install_project_searcher(ev, spec)
    return spec


class GuestSession:
    """Stabilne API hosta (CLI / boot / edytor) nad jednym bąblem-sesją.

    Sandbox = bąbel: gość nie ma FS; host woła check/run/reload.
    """

    def __init__(self, store=None, project=None, tools=None, caps=None,
                 phi=None, budget=None, lua_bin=None, strict=None, **kwargs):
        self.store = store if store is not None else Store(thermal=True)
        self.ev = mount_session(
            self.store,
            project=project,
            tools=tools,
            caps=caps,
            phi=phi,
            budget=budget,
            lua_bin=lua_bin,
            strict=strict,
            **kwargs,
        )

    @property
    def project(self):
        return getattr(self.ev, "project", None)

    def eval(self, line: str) -> str:
        return self.ev.eval_line(line)

    def run(self, entry=None, strict_project=None):
        return run_entry(self.ev, entry=entry, strict_project=strict_project)

    def check(self):
        return check_project(self.ev)

    def check_buffer(self, name, text, chunkname=None):
        return check_buffer(name, text, chunkname=chunkname)

    def put_module(self, name, source):
        """Wstrzyknij moduł do memory searcher (widoczny w require)."""
        return put_memory_module(self.ev, name, source)

    def reload(self, name=None):
        return reload_module(self.ev, name)

    def set_project(self, root):
        return set_project(self.ev, root)

    def attach_lua_bin(self, path):
        return attach_lua_bin(self.ev, path)

    def diagnostics(self):
        """Lista diagnostyk parse projektu (pusta = OK)."""
        return self.check()
