#!/usr/bin/env python3
"""Szybki audyt izolacji host/projekt vs filozofia bąbla."""
import os
import sys
import types
import tempfile
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
KERNEL = os.path.normpath(os.path.join(ROOT, "..", "Kernel Karmazyn"))
if not os.path.isdir(KERNEL):
    KERNEL = r"C:\Users\drwis\Kernel Karmazyn"
sys.path[:0] = [KERNEL, ROOT]
pkg = types.ModuleType("karmazyn_lua")
pkg.__path__ = [ROOT]
pkg.__file__ = os.path.join(ROOT, "__init__.py")
sys.modules["karmazyn_lua"] = pkg

from karmazyn_kernel import Store
from karmazyn_lua.session import mount_session, GuestSession
from karmazyn_lua.values import _own_keys

issues = []

ev = mount_session(Store(thermal=True))
keys = set(_own_keys(ev.G))
for ban in ("dofile", "loadfile"):
    if ban in keys:
        issues.append(f"guest ma {ban}")
print("io.open type:", ev.eval_line("return type(io.open)"))
print("os.execute type:", ev.eval_line("return type(os.execute)"))
# wywołanie os.execute — nie powinno dawać shella
out = ev.eval_line("return os.execute('echo pwned')")
print("os.execute call:", out)
if "pwned" in (out or ""):
    issues.append("os.execute wykonało host command?")

td = tempfile.mkdtemp()
try:
    with open(os.path.join(td, "main.lua"), "w", encoding="utf-8") as f:
        f.write("return 1\n")
    ev2 = mount_session(Store(thermal=True), project=td)
    r1 = ev2.eval_line("return require('..')")
    r2 = ev2.eval_line("return require('secret')")
    print("require ..:", r1)
    print("require secret:", r2)
    if not str(r1).startswith("blad"):
        issues.append("require '..' nie jest błędem")
    if not str(r2).startswith("blad"):
        issues.append("require secret poza projektem nie jest błędem")
finally:
    shutil.rmtree(td, ignore_errors=True)

s = GuestSession(project=os.path.join(ROOT, "examples", "hello"))
if s.ev.G not in s.store.roots:
    issues.append("G nie jest korzeniem Store (reach-GC)")
kind, text = s.run()
print("run:", kind, (text or "").splitlines()[-1:])
if kind != "ok":
    issues.append(f"run hello failed: {text}")

# phi/caps na sesji
print("caps:", getattr(s.ev, "caps", None))
print("phi attr:", hasattr(s.ev, "phi"))

# editor overlay nie wstrzykuje do require bez put — OK
from karmazyn_lua.editor_bridge import EditorBridge
br = EditorBridge(project=os.path.join(ROOT, "examples", "hello"))
br.put_buffer("evil.lua", "return 1")
# require evil nie powinno znaleźć bufora (overlay tylko check) — filozofia: host explicit
r = br.eval("return require('evil')")
print("require evil from buffer overlay:", r)
if not str(r).startswith("blad"):
    issues.append(
        "UWAGA: require znalazł evil — niespodziewane (lub plik na dysku)"
    )
else:
    print("  (OK: overlay bufora nie jest ambient require — tylko check)")

if issues:
    print("ISSUES:")
    for i in issues:
        print(" -", i)
    sys.exit(1)
print("AUDIT_SANITY_OK")
