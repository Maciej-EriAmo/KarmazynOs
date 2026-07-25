"""
karmazyn_substrate_native.py — Python facade over Rust C ABI (optional).

Loads native/karmazyn_substrate target release/debug DLL when present.
If missing: ImportError — caller falls back to pure-Python substrate.

Seam: same law as karmazyn_substrate.Store (reach-GC), ids are int atom/bubble
handles (u32), language values are opaque tokens (id(obj) by default).
"""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import (
    CFUNCTYPE,
    POINTER,
    Structure,
    byref,
    c_char_p,
    c_double,
    c_int,
    c_int64,
    c_uint32,
    c_uint64,
    c_void_p,
)
from typing import Any, Callable, Dict, List, Optional


def _candidate_libs():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.join(here, "karmazyn_substrate", "target")
    names = []
    if sys.platform == "win32":
        names = ["karmazyn_substrate.dll"]
    elif sys.platform == "darwin":
        names = ["libkarmazyn_substrate.dylib"]
    else:
        names = ["libkarmazyn_substrate.so"]
    for profile in ("release", "debug"):
        for n in names:
            yield os.path.join(root, profile, n)
    # also cwd / PATH
    for n in names:
        yield n


def _load_lib():
    last = None
    for path in _candidate_libs():
        if not os.path.isfile(path) and not os.path.isabs(path):
            # bare name — try CDLL search path
            try:
                return ctypes.CDLL(path)
            except OSError as e:
                last = e
                continue
        if os.path.isfile(path):
            try:
                return ctypes.CDLL(path)
            except OSError as e:
                last = e
    raise ImportError(
        "native karmazyn_substrate DLL not found — build with: "
        "cargo build --release -p karmazyn_substrate  "
        f"(last error: {last})"
    )


class _KSubStats(Structure):
    _fields_ = [
        ("total", c_uint64),
        ("hot", c_uint64),
        ("warm", c_uint64),
        ("cold", c_uint64),
        ("tomb", c_uint64),
        ("alive", c_uint64),
        ("dead", c_uint64),
        ("reaped", c_uint64),
        ("retained_tomb", c_uint64),
        ("bubbles", c_uint64),
    ]


_lib = None


def _lib_get():
    global _lib
    if _lib is None:
        lib = _load_lib()
        lib.ksub_version.restype = c_char_p
        lib.ksub_store_new.argtypes = [c_int]
        lib.ksub_store_new.restype = c_uint64
        lib.ksub_store_free.argtypes = [c_uint64]
        lib.ksub_atom_new.argtypes = [c_uint64, c_char_p, c_char_p, c_double]
        lib.ksub_atom_new.restype = c_uint32
        lib.ksub_atom_set_value.argtypes = [c_uint64, c_uint32, c_uint64]
        lib.ksub_atom_set_value.restype = c_int
        lib.ksub_has_atom.argtypes = [c_uint64, c_uint32]
        lib.ksub_has_atom.restype = c_int
        lib.ksub_delete_atom.argtypes = [c_uint64, c_uint32]
        lib.ksub_delete_atom.restype = c_int
        lib.ksub_heat.argtypes = [c_uint64, c_uint32]
        lib.ksub_heat.restype = c_int
        lib.ksub_atom_t.argtypes = [c_uint64, c_uint32]
        lib.ksub_atom_t.restype = c_double
        lib.ksub_atom_is_dead.argtypes = [c_uint64, c_uint32]
        lib.ksub_atom_is_dead.restype = c_int
        lib.ksub_bubble_new.argtypes = [c_uint64, c_char_p, c_int64]
        lib.ksub_bubble_new.restype = c_uint32
        lib.ksub_bind.argtypes = [c_uint64, c_uint32, c_char_p, c_uint32]
        lib.ksub_bind.restype = c_int
        lib.ksub_lookup.argtypes = [c_uint64, c_uint32, c_char_p]
        lib.ksub_lookup.restype = c_int64
        lib.ksub_set_root.argtypes = [c_uint64, c_uint32]
        lib.ksub_unset_root.argtypes = [c_uint64, c_uint32]
        lib.ksub_tick.argtypes = [c_uint64]
        lib.ksub_settle.argtypes = [c_uint64, c_uint32]
        lib.ksub_stats.argtypes = [c_uint64, POINTER(_KSubStats)]
        lib.ksub_stats.restype = c_int
        lib.ksub_register_env_of.argtypes = [c_uint64, c_void_p, c_void_p]
        lib.ksub_register_env_of.restype = c_int
        lib.ksub_register_extra_reach.argtypes = [c_uint64, c_void_p, c_void_p]
        lib.ksub_register_extra_reach.restype = c_int
        _lib = lib
    return _lib


# C callbacks keep alive on store instance
_EnvOfC = CFUNCTYPE(c_uint32, c_uint64, c_void_p)
_ExtraC = CFUNCTYPE(c_uint32, POINTER(c_uint32), c_uint32, c_void_p)


def native_available() -> bool:
    try:
        _lib_get()
        return True
    except ImportError:
        return False


def native_version() -> str:
    v = _lib_get().ksub_version()
    return v.decode("utf-8", errors="replace") if v else ""


class NativeAtom:
    """Lightweight view of a native atom (id + store)."""

    __slots__ = ("id", "_store", "S", "E")

    def __init__(self, store: "NativeStore", aid: int, s: str = "", e: str = ""):
        self.id = int(aid)
        self._store = store
        self.S = s
        self.E = e

    @property
    def T(self) -> float:
        return float(self._store._lib.ksub_atom_t(self._store._h, self.id))

    def is_dead(self) -> bool:
        return self._store._lib.ksub_atom_is_dead(self._store._h, self.id) == 1

    def __repr__(self):
        return f"<NativeAtom a{self.id} T={self.T:.1f}>"


class NativeBubble:
    __slots__ = ("id", "_store", "label", "parent")

    def __init__(self, store: "NativeStore", bid: int, label: str = "", parent=None):
        self.id = int(bid)
        self._store = store
        self.label = label
        self.parent = parent

    def bind(self, name: str, atom: NativeAtom):
        ok = self._store._lib.ksub_bind(
            self._store._h, self.id, name.encode("utf-8"), int(atom.id)
        )
        if not ok:
            raise ValueError(f"bind failed: {name!r} -> {atom.id}")

    def lookup(self, name: str) -> Optional[NativeAtom]:
        aid = self._store._lib.ksub_lookup(
            self._store._h, self.id, name.encode("utf-8")
        )
        if aid < 0:
            return None
        return NativeAtom(self._store, int(aid))


class NativeStore:
    """Subset of Python Store API backed by Rust substrate (law + hooks)."""

    def __init__(self, thermal: bool = True, env_of=None, extra_reach=None, **_kw):
        self._lib = _lib_get()
        self._h = self._lib.ksub_store_new(1 if thermal else 0)
        if not self._h:
            raise RuntimeError("ksub_store_new failed")
        self.thermal = thermal
        self._atoms: Dict[int, NativeAtom] = {}
        self._pin: Dict[int, Any] = {}
        self._env_py: Optional[Callable] = None
        self._extra_py: Optional[Callable] = None
        self._c_env = None
        self._c_extra = None
        self._extra_held: List[int] = []
        # minimal lock stand-in (Python guests expect store.lock)
        import threading
        self.lock = threading.RLock()
        if env_of is not None:
            self.register_env_of(env_of, name="init")
        if extra_reach is not None:
            self.register_extra_reach(extra_reach, name="init")

    def close(self):
        if getattr(self, "_h", 0):
            self._lib.ksub_store_free(self._h)
            self._h = 0

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _aid(self, aid) -> int:
        return int(getattr(aid, "id", aid))

    def atom_new(self, S: str, E: str = "", T: float = 50.0, value=None) -> NativeAtom:
        t = float(T)
        if t != t:  # NaN
            t = 50.0
        aid = self._lib.ksub_atom_new(
            self._h, str(S).encode("utf-8"), str(E).encode("utf-8"), t
        )
        if aid == 0xFFFFFFFF:
            raise RuntimeError("atom_new failed")
        atom = NativeAtom(self, aid, S, E)
        self._atoms[aid] = atom
        if value is not None:
            token = id(value) & 0xFFFFFFFFFFFFFFFF
            self._lib.ksub_atom_set_value(self._h, aid, token)
            self._pin[token] = value
            # also allow value_token = bubble id when value is bubble-like
            bid = getattr(value, "id", None)
            if isinstance(value, NativeBubble):
                self._lib.ksub_atom_set_value(self._h, aid, int(value.id))
        return atom

    def has_atom(self, aid) -> bool:
        return bool(self._lib.ksub_has_atom(self._h, self._aid(aid)))

    def heat(self, atom):
        self._lib.ksub_heat(self._h, self._aid(atom))

    def delete_atom(self, aid) -> bool:
        return bool(self._lib.ksub_delete_atom(self._h, self._aid(aid)))

    def bubble_new(self, label: str = "", parent: Optional[NativeBubble] = None) -> NativeBubble:
        p = -1 if parent is None else int(parent.id)
        bid = self._lib.ksub_bubble_new(self._h, label.encode("utf-8"), p)
        if bid == 0xFFFFFFFF:
            raise RuntimeError("bubble_new failed")
        return NativeBubble(self, bid, label, parent)

    def set_root(self, b: NativeBubble):
        self._lib.ksub_set_root(self._h, int(b.id))

    def unset_root(self, b: NativeBubble):
        self._lib.ksub_unset_root(self._h, int(b.id))

    def tick(self):
        self._lib.ksub_tick(self._h)

    def settle(self, n: int):
        self._lib.ksub_settle(self._h, int(n))

    def stats(self) -> dict:
        st = _KSubStats()
        if not self._lib.ksub_stats(self._h, byref(st)):
            raise RuntimeError("stats failed")
        return {
            "total": int(st.total),
            "HOT": int(st.hot),
            "WARM": int(st.warm),
            "COLD": int(st.cold),
            "TOMB": int(st.tomb),
            "alive": int(st.alive),
            "dead": int(st.dead),
            "hot": int(st.alive),
            "cold": int(st.dead),
            "reaped": int(st.reaped),
            "retained_tomb": int(st.retained_tomb),
            "archived": int(st.retained_tomb),
            "bubbles": int(st.bubbles),
        }

    def register_env_of(self, fn: Callable[[Any], Any], *, name: str = "guest"):
        """Hak env_of: fn(value) -> Bubble|None. value z pin map (id(obj)).

        Dodatkowo: jeśli value_token jest małym int (bubble id), zwraca ten bąbel.
        """
        self._env_py = fn
        store = self

        def _cb(token, _userdata):
            # direct bubble-id token (set for NativeBubble payloads)
            if token < 0x100000 and store._env_py is None:
                return c_uint32(token).value
            obj = store._pin.get(token)
            if obj is None and token < 0x100000:
                # treat token as bubble id
                return int(token)
            if obj is None:
                return 0
            try:
                env = store._env_py(obj) if store._env_py else None
            except Exception:
                return 0
            if env is None:
                return 0
            bid = getattr(env, "id", None)
            return int(bid) if bid is not None else 0

        self._c_env = _EnvOfC(_cb)
        self._lib.ksub_register_env_of(self._h, self._c_env, None)
        return self

    def unregister_env_of(self, name: str = "guest"):
        self._env_py = None
        self._lib.ksub_register_env_of(self._h, None, None)
        return self

    def register_extra_reach(self, fn: Callable[[], Any], *, name: str = "guest"):
        """fn() -> iterable atom ids (int or objects with .id)."""
        self._extra_py = fn
        store = self

        def _cb(out, max_out, _userdata):
            try:
                raw = store._extra_py() if store._extra_py else ()
            except Exception:
                return 0
            n = 0
            for x in raw or ():
                if n >= max_out:
                    break
                aid = int(getattr(x, "id", x))
                out[n] = aid
                n += 1
            return n

        self._c_extra = _ExtraC(_cb)
        self._lib.ksub_register_extra_reach(self._h, self._c_extra, None)
        return self

    def unregister_extra_reach(self, name: str = "guest"):
        self._extra_py = None
        self._lib.ksub_register_extra_reach(self._h, None, None)
        return self

    def hook_names(self):
        names_e = []
        names_x = []
        if self._env_py is not None:
            names_e.append("guest")
        if self._extra_py is not None:
            names_x.append("guest")
        return {"env_of": names_e, "extra_reach": names_x}


def smoke() -> str:
    """Quick native law check: orphan dies, root retains."""
    s = NativeStore(thermal=True)
    try:
        orphan = s.atom_new("var", "orphan")
        s.settle(80)
        assert not s.has_atom(orphan.id), "orphan should be reaped"
        root = s.bubble_new("root")
        s.set_root(root)
        keep = s.atom_new("var", "keep")
        root.bind("keep", keep)
        s.settle(80)
        assert s.has_atom(keep.id), "rooted atom must survive"
        assert keep.is_dead(), "should be cold/tomb"
        st = s.stats()
        assert st["retained_tomb"] >= 1
        return f"OK native {native_version()!r} stats={st}"
    finally:
        s.close()


if __name__ == "__main__":
    if not native_available():
        print("native DLL missing — build: cd native/karmazyn_substrate && cargo build --release")
        sys.exit(1)
    print(smoke())
