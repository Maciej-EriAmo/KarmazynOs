#!/usr/bin/env python3
"""Uruchom testy z workspace jako pakiet karmazyn_lua.

Preferuje kanoniczne jadro: C:\\Users\\drwis\\Kernel Karmazyn
(nad site-packages), potem katalog LUA.
"""
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
KERNEL = os.path.normpath(os.path.join(ROOT, "..", "Kernel Karmazyn"))
if not os.path.isdir(KERNEL):
    KERNEL = r"C:\Users\drwis\Kernel Karmazyn"

# 1) Kernel kanoniczny  2) workspace (liby + pakiet)
if os.path.isdir(KERNEL):
    sys.path.insert(0, KERNEL)
sys.path.insert(0, ROOT)

# zarejestruj katalog jako pakiet karmazyn_lua (zanim cokolwiek go importuje)
pkg = types.ModuleType("karmazyn_lua")
pkg.__path__ = [ROOT]
pkg.__file__ = os.path.join(ROOT, "__init__.py")
sys.modules["karmazyn_lua"] = pkg

# doładuj publiczną powierzchnię
from karmazyn_lua.lib import mount, LuaLib, install_env_of, install_tools  # noqa: E402
from karmazyn_lua.values import lua_env_of, compose_phi  # noqa: E402
pkg.mount = mount
pkg.LuaLib = LuaLib
pkg.install_env_of = install_env_of
pkg.install_tools = install_tools
pkg.lua_env_of = lua_env_of
pkg.compose_phi = compose_phi

import karmazyn_kernel  # noqa: E402
print("kernel:", karmazyn_kernel.__file__, "v" + getattr(karmazyn_kernel, "__version__", "?"))

# test_lua jako top-level (importuje karmazyn_lua)
import test_lua  # noqa: E402

if __name__ == "__main__":
    loader = unittest.defaultTestLoader
    suite = loader.loadTestsFromModule(test_lua)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
