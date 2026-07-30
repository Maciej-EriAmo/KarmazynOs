#!/usr/bin/env python3
"""Uruchom testy z workspace jako pakiet karmazyn_lua.

Discovery jądra: KARMAZYN_KERNEL → monorepo kernel/ → monorepo root → sibling.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from _paths import ensure_kernel_on_path, ensure_lua_package  # noqa: E402

ensure_kernel_on_path(ROOT)
ensure_lua_package(ROOT)

from karmazyn_lua.lib import mount, LuaLib, install_env_of, install_tools  # noqa: E402
from karmazyn_lua.values import lua_env_of, compose_phi  # noqa: E402
import karmazyn_lua as pkg  # noqa: E402

pkg.mount = mount
pkg.LuaLib = LuaLib
pkg.install_env_of = install_env_of
pkg.install_tools = install_tools
pkg.lua_env_of = lua_env_of
pkg.compose_phi = compose_phi

import karmazyn_kernel  # noqa: E402
print("kernel:", karmazyn_kernel.__file__, "v" + getattr(karmazyn_kernel, "__version__", "?"))

import test_lua  # noqa: E402

if __name__ == "__main__":
    loader = unittest.defaultTestLoader
    suite = loader.loadTestsFromModule(test_lua)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
