#!/usr/bin/env python3
"""ksub_client — Python as a *client* of the Rust substrate (C ABI).

Not the boot. Not a second Store. Not golden Python kernel.
Same idea as native/c_smoke/ksub_client.c.

  python native/ksub_client.py
"""
from __future__ import annotations

import ctypes
import os
import sys
from ctypes import c_char_p, c_double, c_int, c_int64, c_uint32, c_uint64


def _dll_candidates() -> list[str]:
    here = os.path.dirname(os.path.abspath(__file__))
    rel = os.path.join(here, "karmazyn_substrate", "target", "release")
    names = (
        "karmazyn_substrate.dll",
        "libkarmazyn_substrate.so",
        "libkarmazyn_substrate.dylib",
    )
    out = []
    for n in names:
        out.append(os.path.join(rel, n))
    prefix = os.path.join(os.path.dirname(here), "dist", "prefix", "lib")
    for n in names:
        out.append(os.path.join(prefix, n))
    return out


def load_lib():
    last = None
    for path in _dll_candidates():
        if not os.path.isfile(path):
            continue
        try:
            lib = ctypes.CDLL(path)
            break
        except OSError as e:
            last = e
    else:
        raise SystemExit(
            "brak karmazyn_substrate DLL — zbuduj: "
            "cargo build --release --manifest-path native/karmazyn_substrate/Cargo.toml"
            f" ({last})"
        )
    lib.ksub_version.restype = c_char_p
    lib.ksub_store_new.argtypes = [c_int]
    lib.ksub_store_new.restype = c_uint64
    lib.ksub_store_free.argtypes = [c_uint64]
    lib.ksub_atom_new.argtypes = [c_uint64, c_char_p, c_char_p, c_double]
    lib.ksub_atom_new.restype = c_uint32
    lib.ksub_atom_set_value.argtypes = [c_uint64, c_uint32, c_uint64]
    lib.ksub_atom_set_value.restype = c_int
    lib.ksub_atom_value.argtypes = [c_uint64, c_uint32]
    lib.ksub_atom_value.restype = c_uint64
    lib.ksub_has_atom.argtypes = [c_uint64, c_uint32]
    lib.ksub_has_atom.restype = c_int
    lib.ksub_bubble_new.argtypes = [c_uint64, c_char_p, c_int64]
    lib.ksub_bubble_new.restype = c_uint32
    lib.ksub_bind.argtypes = [c_uint64, c_uint32, c_char_p, c_uint32]
    lib.ksub_bind.restype = c_int
    lib.ksub_lookup.argtypes = [c_uint64, c_uint32, c_char_p]
    lib.ksub_lookup.restype = c_int64
    lib.ksub_set_root.argtypes = [c_uint64, c_uint32]
    lib.ksub_tick.argtypes = [c_uint64]
    return lib


class KSub:
    """Thin handle. Python does not implement T×reach."""

    def __init__(self, thermal: bool = True):
        self._lib = load_lib()
        self._h = self._lib.ksub_store_new(1 if thermal else 0)
        if not self._h:
            raise RuntimeError("ksub_store_new failed")

    def version(self) -> str:
        raw = self._lib.ksub_version()
        return raw.decode("utf-8", "replace") if raw else ""

    def atom_new(self, s: str, e: str, t: float = 50.0) -> int:
        return int(self._lib.ksub_atom_new(self._h, s.encode(), e.encode(), float(t)))

    def set_value(self, aid: int, token: int) -> bool:
        return bool(self._lib.ksub_atom_set_value(self._h, aid, token))

    def value(self, aid: int) -> int:
        return int(self._lib.ksub_atom_value(self._h, aid))

    def has(self, aid: int) -> bool:
        return bool(self._lib.ksub_has_atom(self._h, aid))

    def bubble_new(self, label: str = "py") -> int:
        return int(self._lib.ksub_bubble_new(self._h, label.encode(), -1))

    def set_root(self, bid: int) -> None:
        self._lib.ksub_set_root(self._h, bid)

    def bind(self, bid: int, name: str, aid: int) -> bool:
        return bool(self._lib.ksub_bind(self._h, bid, name.encode(), aid))

    def lookup(self, bid: int, name: str) -> int:
        return int(self._lib.ksub_lookup(self._h, bid, name.encode()))

    def tick(self) -> None:
        self._lib.ksub_tick(self._h)

    def close(self) -> None:
        if getattr(self, "_h", 0):
            self._lib.ksub_store_free(self._h)
            self._h = 0

    def __enter__(self) -> "KSub":
        return self

    def __exit__(self, *a) -> None:
        self.close()


def main() -> int:
    with KSub() as s:
        print("ksub_client (Python → C ABI, not boot)")
        print("  version:", s.version())
        a = s.atom_new("var", "x", 80.0)
        assert s.set_value(a, 42)
        assert s.value(a) == 42
        b = s.bubble_new("cli")
        s.set_root(b)
        assert s.bind(b, "x", a)
        assert s.lookup(b, "x") == a
        s.tick()
        assert s.has(a)
        print("  atom", a, "value", s.value(a), "lookup ok")
        print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
