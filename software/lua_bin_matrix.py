#!/usr/bin/env python3
"""Macierz statusu lua_bin + automatyczny smoke bezpiecznych narzędzi.

  python software/lua_bin_matrix.py           # tabela + smoke
  python software/lua_bin_matrix.py --md      # wypisz markdown
  python software/lua_bin_matrix.py --smoke   # tylko smoke (exit 1 przy fail)

Status:
  pass  — smoke E2E na host API (io_input wstrzyknięty)
  skip  — interaktywne / pętla / poza surface alpha (nie failuje gate)
  fail  — oczekiwany pass, a run rzucił
"""
from __future__ import annotations

import argparse
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUA_BIN = os.path.join(ROOT, "lua_bin")
SOFTWARE = os.path.join(ROOT, "software")

sys.path[:0] = [ROOT, SOFTWARE, os.path.join(ROOT, "kernel"), os.path.join(ROOT, "LUA")]
os.environ.setdefault("KARMAZYN_LUA", os.path.join(ROOT, "LUA"))
os.environ.setdefault("KARMAZYN_SUBSTRATE", "python")
os.environ.setdefault("KARMAZYN_NOSLEEP", "1")

# name -> (status_default, io_input_factory | None, note)
# io_input_factory: callable(store, host) -> list[str] | None
# None factory = no lines needed

def _io_atom(store, host, *lines):
    return list(lines)


# Katalog ręczny — źródło prawdy dla skip/note; brak w dict = auto „pass” z pustym input
TOOL_SPEC = {
    # no input / self-contained
    "ls": ("pass", lambda s, h: None, "list atoms"),
    "df": ("pass", lambda s, h: None, "stats by layer"),
    "free": ("pass", lambda s, h: None, "store.stats resources"),
    "whoami": ("pass", lambda s, h: None, "node info"),
    "uptime": ("pass", lambda s, h: None, "epoch"),
    "clear": ("pass", lambda s, h: None, "clear_screen"),
    "du": ("pass", lambda s, h: None, "emanation usage"),
    "ps": ("pass", lambda s, h: None, "agents list"),
    "lsh": ("pass", lambda s, h: None, "holograms list"),
    "lsb": ("pass", lambda s, h: None, "bubbles list"),
    # with canned input
    "step": ("pass", lambda s, h: ["2"], "settle n"),
    "man": ("pass", lambda s, h: [""], "empty = list tools"),
    "touch": ("pass", lambda s, h: ["m_touch", "S", "E-touch"], "create atom"),
    "cat": ("pass", lambda s, h: (s.create_atom("m_cat", "S", "body", 0.8) or True) and ["m_cat"], "show atom"),
    "stat": ("pass", lambda s, h: (s.create_atom("m_stat", "S", "body", 0.8) or True) and ["m_stat"], "metadata"),
    "rm": ("pass", lambda s, h: (s.create_atom("m_rm", "S", "x", 0.5) or True) and ["m_rm"], "delete atom"),
    "cp": ("pass", lambda s, h: (s.create_atom("m_cp_src", "S", "c", 0.8) or True) and ["m_cp_src", "m_cp_dst"], "clone"),
    "mv": ("pass", lambda s, h: (s.create_atom("m_mv", "S", "x", 0.5) or True) and ["m_mv", "HOT"], "set_state layer"),
    "grep": ("pass", lambda s, h: (s.create_atom("m_g", "needle", "hay", 0.8) or True) and ["needle"], "search S/E"),
    "find": ("pass", lambda s, h: ["ALL", "0"], "filter layer/T"),
    "ping": ("pass", lambda s, h: (
        s.create_atom("m_p1", "a", "same", 0.8),
        s.create_atom("m_p2", "b", "same", 0.8),
        ["m_p1", "m_p2"],
    )[-1], "similarity"),
    "recall": ("pass", lambda s, h: (s.create_atom("m_rec", "q", "pamiec semantyczna", 0.9) or True) and ["pamiec"], "resonance"),
    "consolidate": ("pass", lambda s, h: (s.create_atom("m_con", "S", "keep", 0.9) or True) and ["m_con"], "to bubble"),
    "kill": ("pass", lambda s, h: (h.spawn_agent("tmp", "t", ["phi"]), ["1"])[-1] if h else ["1"], "delete agent"),
    "idea": ("pass", lambda s, h: (h.create_hologram("h1", "tema"), ["h1", "prompt"])[-1], "vector from hologram"),
    "kedit": ("pass", lambda s, h: (s.create_atom("m_ke", "S", "old", 0.8) or True) and ["m_ke", "4"], "exit only path"),
    # skip
    "top": ("skip", None, "DEPRECATED in automation — infinite loop; manual only"),
    "nano": ("skip", None, "DEPRECATED in automation — interactive editor; manual only"),
}


def _all_tools():
    names = sorted(
        fn[:-4] for fn in os.listdir(LUA_BIN)
        if fn.endswith(".lua") and not fn.startswith(".")
    )
    return names


def _prepare_io(name, store, host):
    spec = TOOL_SPEC.get(name)
    if not spec:
        return "pass", None, "auto (no canned IO — may need input)"
    status, factory, note = spec
    if status == "skip" or factory is None:
        return status, None, note
    try:
        lines = factory(store, host)
        if lines is True:
            lines = None
        if isinstance(lines, tuple):
            # accidental multi-return from create_atom side effects
            lines = list(lines) if lines and isinstance(lines[-1], list) else None
    except Exception as e:
        return "fail", None, f"io setup: {e}"
    return status, lines, note


def run_matrix(do_smoke=True):
    from karmazyn_kernel import Store
    import karmazyn_boot as boot
    from karmazyn_host import run_lua_tool

    results = []
    fails = 0
    for name in _all_tools():
        store = Store(thermal=True)
        ev = boot.mount_evaluator(store, kind="lua", lua_bin=LUA_BIN)
        host = getattr(ev, "host", None)
        if host is not None:
            host._no_sleep = True
        status, lines, note = _prepare_io(name, store, host)
        row = {
            "name": name,
            "status": status,
            "note": note,
            "detail": "",
        }
        if status == "skip" or not do_smoke:
            results.append(row)
            continue
        if lines is not None:
            ev._io_input = list(lines)
        else:
            ev._io_input = []
        try:
            ret = run_lua_tool(ev, name, lua_bin=LUA_BIN)
            text = ev.format_run_result(ret=ret) or ""
            if text.startswith("blad:"):
                row["status"] = "fail"
                row["detail"] = text[:120]
                fails += 1
            else:
                row["status"] = "pass"
                row["detail"] = (text.splitlines()[0] if text else "ok")[:80]
        except Exception as e:
            row["status"] = "fail"
            row["detail"] = f"{type(e).__name__}: {e}"[:120]
            fails += 1
        results.append(row)
    return results, fails


def format_table(results):
    lines = []
    lines.append(f"{'tool':<14} {'status':<6} note")
    lines.append("-" * 72)
    for r in results:
        note = r["note"]
        if r["detail"] and r["status"] == "fail":
            note = r["detail"]
        lines.append(f"{r['name']:<14} {r['status']:<6} {note}")
    n_pass = sum(1 for r in results if r["status"] == "pass")
    n_skip = sum(1 for r in results if r["status"] == "skip")
    n_fail = sum(1 for r in results if r["status"] == "fail")
    lines.append("-" * 72)
    lines.append(f"pass={n_pass}  skip={n_skip}  fail={n_fail}  total={len(results)}")
    return "\n".join(lines)


def format_md(results):
    lines = [
        "# lua_bin status matrix (karmazyn_lua alpha→0.9)",
        "",
        "Generated by `software/lua_bin_matrix.py`.",
        "",
        "| Tool | Status | Note |",
        "|------|--------|------|",
    ]
    for r in results:
        note = (r["detail"] if r["status"] == "fail" and r["detail"] else r["note"]).replace("|", "/")
        lines.append(f"| `{r['name']}` | **{r['status']}** | {note} |")
    n_pass = sum(1 for r in results if r["status"] == "pass")
    n_skip = sum(1 for r in results if r["status"] == "skip")
    n_fail = sum(1 for r in results if r["status"] == "fail")
    lines.append("")
    lines.append(f"**Summary:** pass={n_pass}, skip={n_skip}, fail={n_fail}, total={len(results)}")
    lines.append("")
    lines.append("- **pass** — automated smoke with host API")
    lines.append("- **skip** — interactive / infinite loop; not in release gate smoke")
    lines.append("- **fail** — must fix before counting toward 0.9 coverage")
    return "\n".join(lines) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description="lua_bin status matrix")
    p.add_argument("--md", action="store_true", help="markdown output")
    p.add_argument("--smoke", action="store_true", help="smoke only; exit 1 on fail")
    p.add_argument("--write", metavar="PATH", help="write markdown to path")
    args = p.parse_args(argv)

    results, fails = run_matrix(do_smoke=True)
    if args.md or args.write:
        text = format_md(results)
    else:
        text = format_table(results)
    print(text)
    if args.write:
        path = args.write
        if not os.path.isabs(path):
            path = os.path.join(ROOT, path)
        with open(path, "w", encoding="utf-8") as f:
            f.write(format_md(results) if not args.md else text)
        print(f"\nWrote {path}", file=sys.stderr)
    if args.smoke or fails:
        return 1 if fails else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
