"""karmazyn_lua.cli — host CLI: run / check / path (sandbox = bąbel).

  python -m karmazyn_lua run path/to/main.lua
  python -m karmazyn_lua run path/to/project/
  python -m karmazyn_lua check path/to/project/
  python -m karmazyn_lua path modname --project path/to/project/
"""

from __future__ import annotations

import argparse
import os
import sys

from ._paths import ensure_kernel_on_path, ensure_lua_package, lua_root


def _ensure_package():
    """Umożliw import karmazyn_lua + jądra (przenośne discovery)."""
    root = lua_root()
    ensure_kernel_on_path(root)
    ensure_lua_package(root)
    return root


def _add_common(sp):
    sp.add_argument("--project", "-p", default=None,
                    help="root projektu (module searcher)")
    sp.add_argument("--tools", default=None,
                    help="katalog tools/*.lua → package.preload")
    sp.add_argument("--lua-bin", default=None, dest="lua_bin",
                    help="katalog lua_bin (preload + module root)")
    sp.add_argument("--caps", default=None,
                    help="profil caps: default|strict|compute|full")
    sp.add_argument("--budget", type=int, default=None, help="limit instrukcji")
    sp.add_argument("--strict-project", action="store_true", default=None,
                    dest="strict_project",
                    help="odmów run poza rootem projektu (domyślnie włączone przy -p)")
    sp.add_argument("--no-strict-project", action="store_false", dest="strict_project",
                    help="pozwól run_file poza rootem projektu")


def _build_parser():
    p = argparse.ArgumentParser(
        prog="karmazyn_lua",
        description="Karmazyn Lua — host CLI (projekt → bąbel, bez ambient FS w gościu)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("run", help="uruchom plik lub projekt (main.lua)")
    _add_common(pr)
    pr.add_argument("path", help="plik .lua lub katalog projektu")

    pc = sub.add_parser("check", help="parse wszystkich *.lua w projekcie")
    _add_common(pc)
    pc.add_argument("path", nargs="?", default=".", help="root projektu")

    pp = sub.add_parser("path", help="pokaż co resolve znajdzie dla require")
    _add_common(pp)
    pp.add_argument("modname", help="nazwa modułu (np. lib.util)")
    pp.add_argument("path", nargs="?", default=None,
                    help="root projektu (lub użyj --project)")

    pl = sub.add_parser("repl", help="REPL z projektem (host; :reload / :run / :check)")
    _add_common(pl)
    pl.add_argument("path", nargs="?", default=None, help="root projektu")

    return p


def _project_root_from_args(args, path_arg=None):
    if getattr(args, "project", None):
        return os.path.abspath(args.project)
    if path_arg:
        p = os.path.abspath(path_arg)
        if os.path.isdir(p):
            return p
        if os.path.isfile(p):
            return os.path.dirname(p)
    return os.path.abspath(".")


def cmd_run(args):
    from karmazyn_kernel import Store
    from karmazyn_lua.session import mount_session, run_entry
    from karmazyn_lua.project import ProjectSpec

    path = os.path.abspath(args.path)
    if os.path.isdir(path):
        root = args.project or path
        entry = None
    else:
        root = args.project or os.path.dirname(path)
        entry = path
    root = os.path.abspath(root)
    strict = args.strict_project
    try:
        spec = ProjectSpec.from_root(
            root,
            tools=args.tools,
            caps=args.caps,
            budget=args.budget,
            strict=True if strict is None else bool(strict),
        )
    except Exception as e:
        print(f"blad: {e}", file=sys.stderr)
        return 3
    store = Store(thermal=True)
    ev = mount_session(
        store, project=spec, tools=args.tools,
        caps=args.caps, budget=args.budget,
        lua_bin=args.lua_bin,
        strict=spec.strict,
    )
    kind, text = run_entry(ev, entry=entry, strict_project=spec.strict)
    if text:
        print(text)
    if kind == "ok":
        return 0
    if kind == "parse":
        return 2
    return 1


def cmd_check(args):
    from karmazyn_lua.project import ProjectSpec
    from karmazyn_lua.session import check_project

    root = _project_root_from_args(args, args.path)
    try:
        spec = ProjectSpec.from_root(root)
    except Exception as e:
        print(f"blad: {e}", file=sys.stderr)
        return 3
    errors = check_project(spec)
    if not errors:
        n = sum(1 for _ in spec.iter_lua_files())
        print(f"OK — {n} plik(ów) sparsowanych w {spec.root}")
        return 0
    for e in errors:
        print(e, file=sys.stderr)
    print(f"FAIL — {len(errors)} błąd(ów)", file=sys.stderr)
    return 2


def cmd_path(args):
    from karmazyn_lua.project import ProjectSpec

    root = args.project or args.path or "."
    root = os.path.abspath(root)
    try:
        spec = ProjectSpec.from_root(root)
    except Exception as e:
        print(f"blad: {e}", file=sys.stderr)
        return 3
    hit = spec.resolve(args.modname)
    if hit is None:
        print(f"nie znaleziono: {args.modname!r} w {spec.root}")
        print("szukano:")
        for c in spec._candidates_for(args.modname):
            print(f"  {c}")
        return 1
    path, _src, cname = hit
    print(path)
    print(f"chunkname: {cname}")
    return 0


def cmd_repl(args):
    """Minimalny REPL hosta z tym samym API co boot (:run/:reload/:check)."""
    from karmazyn_lua.session import GuestSession, reload_module, run_entry, check_project

    root = args.project or args.path
    if root:
        root = os.path.abspath(root)
        if not os.path.isdir(root):
            print(f"blad: brak katalogu {root}", file=sys.stderr)
            return 3
    try:
        sess = GuestSession(
            project=root,
            tools=args.tools,
            caps=args.caps,
            budget=args.budget,
            lua_bin=getattr(args, "lua_bin", None),
            strict=args.strict_project,
        )
    except Exception as e:
        print(f"blad montazu: {e}", file=sys.stderr)
        return 3
    print("karmazyn_lua REPL  (sandbox=bąbel; host czyta pliki)")
    if root:
        print(f"project={root}")
    print("linie Lua | :run [file] | :reload [mod] | :check | :project | :quit")
    while True:
        try:
            line = input("lua> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in (":quit", ":exit", ":q"):
            break
        if line.startswith(":"):
            parts = line[1:].split()
            cmd = parts[0].lower() if parts else ""
            a = parts[1:]
            if cmd == "run":
                kind, text = run_entry(sess.ev, entry=a[0] if a else None)
                if text:
                    print(text)
                continue
            if cmd == "reload":
                print(reload_module(sess.ev, a[0] if a else None))
                continue
            if cmd == "check":
                errs = check_project(sess.ev)
                print("check: OK" if not errs else "check FAIL:\n" + "\n".join(errs))
                continue
            if cmd == "project":
                if not a:
                    p = sess.project
                    print(f"project={p.root if p else '(brak)'}")
                else:
                    try:
                        sess.set_project(a[0])
                        print(f"project={sess.project.root}")
                    except Exception as e:
                        print(f"blad: {e}")
                continue
            print(f"nieznana: :{cmd}")
            continue
        out = sess.eval(line)
        if out:
            print(out)
    return 0


def main(argv=None):
    _ensure_package()
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "check":
        return cmd_check(args)
    if args.cmd == "path":
        return cmd_path(args)
    if args.cmd == "repl":
        return cmd_repl(args)
    parser.print_help()
    return 3


if __name__ == "__main__":
    sys.exit(main())
