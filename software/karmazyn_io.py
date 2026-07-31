# -*- coding: utf-8 -*-
"""karmazyn_io — Stage 1 bootstrap: I/O × matryca termiczna.

Gentoo Stage 1 mindset:
  • tylko to, co musi działać na KAŻDYM substracie (python + native)
  • brak cichej degradacji: attach_thermal albo rzuca, albo daje żywą matrycę
  • logiczne nazwy (io:console) ≠ id Store (str | int) — tabela name→aid
  • sterowniki poza jądrem; heat tylko z uwagi/interakcji (anti self-heat)

Env:
  KARMAZYN_IO=stdio|queue|null   (domyślnie: stdio)
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

# Progi T — tylko przez fasadę jadra (enterprise: nie importuj wnetrza karmazyn_atom)
try:
    from karmazyn_kernel import T_INIT, T_WARM, T_HOT, T_MAX, T_TOMB  # type: ignore
except Exception:  # pragma: no cover
    try:
        import karmazyn_kernel as _kk  # type: ignore
        T_INIT = float(getattr(_kk, "T_INIT", 50.0))
        T_WARM = float(getattr(_kk, "T_WARM", 30.0))
        T_HOT = float(getattr(_kk, "T_HOT", 70.0))
        T_MAX = float(getattr(_kk, "T_MAX", 100.0))
        T_TOMB = float(getattr(_kk, "T_TOMB", 2.0))
    except Exception:
        T_INIT, T_WARM, T_HOT, T_MAX, T_TOMB = 50.0, 30.0, 70.0, 100.0, 2.0

# ── kwoty ciepła (Stage 1: stałe, clamp do T_MAX po stronie atomu) ───────────
HEAT_INPUT = 12.0
HEAT_HIT = 6.0
HEAT_VISIBLE = 4.0
HEAT_FOCUS = 8.0

# logiczne nazwy powierzchni (nie id substratu)
NAME_CONSOLE = "io:console"
NAME_DISPLAY = "io:display"
NAME_KEYBOARD = "io:keyboard"
BUBBLE_IO = "io:surface"

# aliasy wsteczne (stare testy / docs)
AID_CONSOLE = NAME_CONSOLE
AID_DISPLAY = NAME_DISPLAY
AID_KEYBOARD = NAME_KEYBOARD

AtomId = Union[str, int]


class ThermalMountError(RuntimeError):
    """Stage 1: matryca I/O nie wstała — boot ma FAIL, nie WARN."""


# ═══════════════════════════════════════════════════════════════════════════
# IoPort
# ═══════════════════════════════════════════════════════════════════════════

class IoPort:
    name = "base"

    def write(self, text: str) -> None:
        raise NotImplementedError

    def write_err(self, text: str) -> None:
        self.write(text)

    def read_line(self, prompt: str = "") -> str:
        raise NotImplementedError

    def try_read(self) -> Optional[str]:
        return None

    def push_input(self, line: str) -> None:
        pass

    def is_tty(self) -> bool:
        return False

    def clear(self) -> None:
        pass


class StdioIo(IoPort):
    name = "stdio"

    def write(self, text: str) -> None:
        sys.stdout.write(text)
        sys.stdout.flush()

    def write_err(self, text: str) -> None:
        sys.stderr.write(text)
        sys.stderr.flush()

    def read_line(self, prompt: str = "") -> str:
        try:
            return input(prompt)
        except EOFError:
            return ""

    def is_tty(self) -> bool:
        try:
            return bool(sys.stdout.isatty())
        except Exception:
            return False

    def clear(self) -> None:
        if self.is_tty():
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()


class QueueIo(IoPort):
    name = "queue"

    def __init__(self, lines: Optional[Sequence[str]] = None, sink: Optional[List[str]] = None):
        self._in: List[str] = list(lines or [])
        self._out: List[str] = sink if sink is not None else []

    def write(self, text: str) -> None:
        self._out.append(text)

    def write_err(self, text: str) -> None:
        self._out.append(text)

    def read_line(self, prompt: str = "") -> str:
        if prompt:
            self._out.append(prompt)
        if not self._in:
            return ""
        return self._in.pop(0)

    def try_read(self) -> Optional[str]:
        if not self._in:
            return None
        return self._in.pop(0)

    def push_input(self, line: str) -> None:
        self._in.append(str(line))

    def clear(self) -> None:
        self._out.append("<clear>")


class NullIo(IoPort):
    name = "null"

    def write(self, text: str) -> None:
        pass

    def read_line(self, prompt: str = "") -> str:
        return ""


def resolve_io(kind: Optional[str] = None, **kwargs: Any) -> IoPort:
    raw = (kind or os.environ.get("KARMAZYN_IO") or "stdio").strip().lower()
    if raw in ("queue", "q", "test"):
        return QueueIo(kwargs.get("lines"), kwargs.get("sink"))
    if raw in ("null", "none", "headless"):
        return NullIo()
    if raw in ("sdl", "sdl2", "pygame", "studio"):
        try:
            from karmazyn_io_sdl import SdlIo  # type: ignore
            return SdlIo()  # type: ignore[return-value]
        except Exception:
            return StdioIo()  # fallback Stage1 — studio i tak podmieni port
    return StdioIo()


# ═══════════════════════════════════════════════════════════════════════════
# ThermalSurface — Stage 1 (name table + real Store ids)
# ═══════════════════════════════════════════════════════════════════════════

class ThermalSurface:
    """Powierzchnia I/O × Store.

    name_to_aid: logiczna nazwa → rzeczywiste id atomu w Store
      Python Store: często ten sam string (create_atom z jawnym id)
      NativeStore:  int z atom_new; nazwa tylko w tej tabeli + metadata
    """

    def __init__(self, store: Any, io: Optional[IoPort] = None):
        self.store = store
        self.io = io or resolve_io()
        self.focus_name: str = NAME_CONSOLE
        self.name_to_aid: Dict[str, AtomId] = {}
        self._bubble = None
        self._ensure_matrix()

    # ── montaż (Stage 1: twardy sukces albo wyjątek) ────────────────────

    def _ensure_matrix(self) -> None:
        specs = (
            (NAME_CONSOLE, "io", "console"),
            (NAME_KEYBOARD, "io", "keyboard"),
            (NAME_DISPLAY, "io", "display"),
        )
        for name, S, E in specs:
            aid = self._ensure_named_atom(name, S, E, T_INIT)
            self.name_to_aid[name] = aid

        aids = [self.name_to_aid[n] for n in (NAME_CONSOLE, NAME_KEYBOARD, NAME_DISPLAY)]
        if not self._root_io_bubble(aids):
            raise ThermalMountError(
                "nie udało się ukorzenić bąbla I/O (create_bubble/set_root) — "
                "Stage 1 wymaga żywego korzenia GC"
            )

        # weryfikacja: każde imię resolvuje się do żywego atomu
        for name, aid in self.name_to_aid.items():
            if self._atom_by_aid(aid) is None:
                raise ThermalMountError(
                    f"atom powierzchni {name!r} (aid={aid!r}) nieżywy po montażu"
                )

    def _ensure_named_atom(self, name: str, S: str, E: str, T: float) -> AtomId:
        """Utwórz lub odzyskaj atom; zwróć REALNE id Store (str lub int)."""
        st = self.store

        # 1) Python-style: jawne string id = name
        if self._store_has(name):
            return name

        # 2) create_atom(name, ...) — Python zachowa id; Native zignoruje i da int
        if hasattr(st, "create_atom"):
            try:
                ret = st.create_atom(name, S, E, float(T))
                # Native: ret = int id; Python: ret = name (str) lub id
                if ret is not None and self._store_has(ret):
                    atom = self._atom_by_aid(ret)
                    if atom is not None:
                        self._tag_logical_name(atom, name)
                    return ret  # type: ignore[return-value]
            except ValueError:
                # już istnieje pod tym id (python)
                if self._store_has(name):
                    return name
            except Exception:
                pass

        # 3) atom_new — uniwersalne (native + python)
        if not hasattr(st, "atom_new"):
            raise ThermalMountError(f"Store nie ma atom_new/create_atom — nie dam atomu {name}")
        atom = st.atom_new(S, E, T=float(T))
        aid = getattr(atom, "id", None)
        if aid is None:
            raise ThermalMountError(f"atom_new nie zwrócił id dla {name}")
        self._tag_logical_name(atom, name)
        return aid

    def _tag_logical_name(self, atom: Any, name: str) -> None:
        try:
            md = getattr(atom, "metadata", None)
            if md is not None and hasattr(md, "__setitem__"):
                md["io_name"] = name
                md["_requested_id"] = name
        except Exception:
            pass

    def _store_has(self, aid: AtomId) -> bool:
        st = self.store
        try:
            if hasattr(st, "has_atom"):
                return bool(st.has_atom(aid))
        except (TypeError, ValueError):
            return False
        try:
            return st.get_atom(aid) is not None
        except Exception:
            return False

    def _atom_by_aid(self, aid: AtomId):
        try:
            return self.store.get_atom(aid)
        except Exception:
            return None

    def _atom_by_name(self, name: str):
        aid = self.name_to_aid.get(name)
        if aid is None:
            return None
        return self._atom_by_aid(aid)

    def _root_io_bubble(self, aids: List[AtomId]) -> bool:
        st = self.store
        try:
            if hasattr(st, "create_bubble"):
                st.create_bubble(BUBBLE_IO, atom_ids=list(aids), root=True)
                # potwierdź: bąbel w roots albo get_bubble
                if hasattr(st, "get_bubble"):
                    b = st.get_bubble(BUBBLE_IO)
                    if b is None:
                        return False
                    self._bubble = b
                    if hasattr(st, "roots") and b not in getattr(st, "roots", []):
                        # create_bubble miało root=True — dociśnij
                        if hasattr(st, "set_root"):
                            st.set_root(b)
                return True
            # minimalna ścieżka
            b = st.bubble_new(BUBBLE_IO)
            for aid in aids:
                a = self._atom_by_aid(aid)
                if a is None:
                    continue
                key = str(getattr(a, "E", None) or aid)
                b.bind(key, a)
            st.set_root(b)
            self._bubble = b
            return True
        except Exception:
            return False

    def _heat_aid(self, aid: AtomId, amount: float) -> bool:
        a = self._atom_by_aid(aid)
        if a is None:
            return False
        try:
            if amount and hasattr(a, "heat"):
                a.heat(float(amount))
            elif hasattr(self.store, "heat"):
                self.store.heat(a)
            elif hasattr(a, "touch"):
                a.touch(max(0.1, float(amount) / 10.0) if amount else 1.0)
            return True
        except Exception:
            return False

    def _heat_name(self, name: str, amount: float) -> bool:
        aid = self.name_to_aid.get(name)
        if aid is None:
            return False
        return self._heat_aid(aid, amount)

    def resolve(self, name_or_aid: Union[str, int]) -> Optional[AtomId]:
        """Nazwa logiczna lub surowe id → aid w Store."""
        if name_or_aid in self.name_to_aid:
            return self.name_to_aid[name_or_aid]  # type: ignore[index]
        if self._store_has(name_or_aid):  # type: ignore[arg-type]
            return name_or_aid  # type: ignore[return-value]
        return None

    # ── API adapterów ───────────────────────────────────────────────────

    def heat_input(self, amount: float = HEAT_INPUT, name: Optional[str] = None) -> None:
        self._heat_name(NAME_KEYBOARD, amount)
        self._heat_name(name or self.focus_name, amount)

    def heat_hit(self, name_or_aid: Optional[Union[str, int]] = None,
                 amount: float = HEAT_HIT) -> None:
        target = name_or_aid if name_or_aid is not None else self.focus_name
        if isinstance(target, str) and target in self.name_to_aid:
            self._heat_name(target, amount)
            return
        aid = self.resolve(target) if not isinstance(target, int) else target
        if aid is None and isinstance(target, str):
            # treść użytkownika: page:link itd. — id = string na python, lub int
            if self._store_has(target):
                aid = target
        if aid is not None:
            self._heat_aid(aid, amount)

    def note_visible(self, names_or_aids: Optional[Iterable[Union[str, int]]] = None,
                     amount: float = HEAT_VISIBLE) -> int:
        """Ciepło z jawnej widoczności — NIE z pełnego skanu matrycy.

        Stage 1: domyślnie tylko io:display. Lista musi być świadoma.
        """
        n = 0
        if names_or_aids is None:
            items: List[Union[str, int]] = [NAME_DISPLAY]
        else:
            items = list(names_or_aids)
        for item in items:
            if isinstance(item, str) and item in self.name_to_aid:
                if self._heat_name(item, amount):
                    n += 1
            else:
                aid = self.resolve(item) if isinstance(item, str) else item
                if aid is None and isinstance(item, str) and self._store_has(item):
                    aid = item
                if aid is not None and self._heat_aid(aid, amount):
                    n += 1
        return n

    def set_focus(self, name: str, amount: float = HEAT_FOCUS) -> None:
        if name not in self.name_to_aid and not self._store_has(name):
            # pozwól na fokus na atomie treści po id string
            pass
        self.focus_name = name
        self.heat_hit(name, amount=amount)

    def project_hot(self, min_T: float = T_WARM, limit: int = 64,
                    mark_visible: bool = False) -> List[Dict[str, Any]]:
        """DisplayList-lite. mark_visible=False domyślnie (Stage 1 anti thrash)."""
        st = self.store
        atoms = []
        try:
            atoms = list(st.atoms()) if hasattr(st, "atoms") else []
        except Exception:
            atoms = []
        # reverse map aid→name for display
        aid_to_name = {v: k for k, v in self.name_to_aid.items()}
        out: List[Dict[str, Any]] = []
        for a in atoms:
            try:
                T = float(getattr(a, "T", 0.0))
            except Exception:
                continue
            if T < min_T:
                continue
            aid = getattr(a, "id", "")
            logical = aid_to_name.get(aid, "")
            out.append({
                "id": aid,
                "name": logical or str(aid),
                "T": round(T, 2),
                "state": getattr(a, "state", None) or (
                    "HOT" if T >= T_HOT else "WARM" if T >= T_WARM else "COLD"
                ),
                "S": getattr(a, "S", "") or "",
                "E": (getattr(a, "E", "") or "")[:200],
            })
        out.sort(key=lambda r: r["T"], reverse=True)
        out = out[: max(1, int(limit))]
        if mark_visible and out:
            # Stage 1: grzej TYLKO surface display + jawne io:*, nie cały skan
            only = [NAME_DISPLAY]
            for r in out:
                if r.get("name") in (NAME_CONSOLE, NAME_KEYBOARD, NAME_DISPLAY):
                    only.append(r["name"])
            self.note_visible(only, amount=HEAT_VISIBLE)
        return out

    def hot_content(self, min_T: float = T_WARM, limit: int = 12
                    ) -> List[Tuple[float, str, str]]:
        return [
            (r["T"], r["S"], r["E"])
            for r in self.project_hot(min_T, limit, mark_visible=False)
        ]

    def read_line(self, prompt: str = "") -> str:
        line = self.io.read_line(prompt)
        if not isinstance(line, str):
            line = str(line)
        # Stage 1: puste / EOF nie grzeje
        if line.strip():
            self.heat_input()
        return line

    def write(self, text: str, *, visible: bool = True) -> None:
        self.io.write(text)
        # Stage 1: write NIE grzeje matrycy (unik self-heat logami boota)
        # widoczność = jawne note_visible / DisplayAdapter.frame
        if visible:
            pass

    def write_err(self, text: str) -> None:
        self.io.write_err(text)

    def clear(self) -> None:
        self.io.clear()

    def stats(self) -> Dict[str, Any]:
        def _t(name: str):
            a = self._atom_by_name(name)
            return None if a is None else float(getattr(a, "T", 0.0))

        return {
            "io": getattr(self.io, "name", type(self.io).__name__),
            "focus": self.focus_name,
            "name_to_aid": {k: v for k, v in self.name_to_aid.items()},
            "T_console": _t(NAME_CONSOLE),
            "T_keyboard": _t(NAME_KEYBOARD),
            "T_display": _t(NAME_DISPLAY),
            "stage": 1,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Adaptery (poza jądrem)
# ═══════════════════════════════════════════════════════════════════════════

class KeyboardAdapter:
    def __init__(self, surface: ThermalSurface):
        self.surface = surface

    def on_line(self, line: str) -> str:
        line = str(line)
        if line.strip():
            self.surface.heat_input()
        if hasattr(self.surface.io, "push_input"):
            self.surface.io.push_input(line)
        return line

    def on_key(self, keysym: str, char: str = "") -> None:
        self.surface._heat_name(NAME_KEYBOARD, HEAT_HIT * 0.5)


class DisplayAdapter:
    """Projekcja: frame() blituje project_hot; widoczność = tylko surface display."""

    def __init__(self, surface: ThermalSurface):
        self.surface = surface

    def frame(self, min_T: float = T_WARM, limit: int = 64) -> List[Dict[str, Any]]:
        recs = self.surface.project_hot(min_T=min_T, limit=limit, mark_visible=False)
        # jedna porcja ciepła na surface display (nie na cały skan)
        self.surface.note_visible([NAME_DISPLAY], amount=HEAT_VISIBLE)
        return recs

    def blit_text(self, records: Optional[List[Dict[str, Any]]] = None) -> str:
        recs = records if records is not None else self.frame()
        lines = [
            f"  {r['T']:5.1f} {r['state']:4} {r.get('name', r['id'])}:{r['E'][:40]}"
            for r in recs
        ]
        text = "\n".join(lines) + ("\n" if lines else "")
        if text:
            self.surface.io.write(text)
        return text


def attach_thermal(store: Any, io: Optional[IoPort] = None) -> ThermalSurface:
    """Stage 1: zwraca żywą matrycę albo rzuca ThermalMountError."""
    return ThermalSurface(store, io=io or resolve_io())
