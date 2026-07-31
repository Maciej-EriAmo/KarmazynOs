"""karmazyn_host — bindings hosta dla gościa Lua (tabela globalna `karmazyn`).

Sandbox = bąbel: gość woła tylko jawnie wstrzyknięte funkcje.
Host ma Store + (opcjonalnie) kolejkę io_input / stdin.

Surface 1.1 (karmazyn_lua 1.1.0): lua_bin tools + session agents/holograms + T-scale 1.1.
Zamrożony kontrakt hosta na serii 1.x — breaking dopiero w 2.0.
"""

from __future__ import annotations

import os
import re
import time

# surface host = 1.1.0 (seria 1.x z pakietem gościa 1.1.0)
HOST_API_VERSION = "1.1.0"

# atom_new (silnik / heap Lua) dostaje publiczne id a0,a1,… — to NIE jest surface create_atom (Φ).
# Kernel ma dwie powierzchnie (engine_native vs AtomStore); host listuje tylko AtomStore.
_ENGINE_SID_RE = re.compile(r"^a\d+$")


def _kernel_T():
    """Progi T z jądra 1.1+ — skala substratu 0..T_MAX (domyślnie 100). Bez przeliczeń 0..1."""
    try:
        import karmazyn_kernel as kk
        return {
            "HOT": float(getattr(kk, "T_HOT", 70.0)),
            "WARM": float(getattr(kk, "T_WARM", 30.0)),
            "INIT": float(getattr(kk, "T_INIT", 50.0)),
            "TOMB": float(getattr(kk, "T_TOMB", 2.0)),
            "MAX": float(getattr(kk, "T_MAX", 100.0)),
            "COLD": float(getattr(kk, "T_TOMB", 2.0)) + 3.0,
        }
    except Exception:
        return {"HOT": 70.0, "WARM": 30.0, "INIT": 50.0, "TOMB": 2.0, "MAX": 100.0, "COLD": 5.0}


def _abs_T(t, default=None):
    """T bezwzględne na skali jądra. None → T_INIT. Bez mapowania 0..1 (to maskowało błędy tools)."""
    kt = _kernel_T()
    if default is None:
        default = kt["INIT"]
    if t is None:
        return float(default)
    try:
        T = float(t)
    except (TypeError, ValueError):
        return float(default)
    tmax = kt["MAX"]
    if T < 0.0:
        T = 0.0
    if T > tmax:
        T = tmax
    return T


def _state_T_map():
    kt = _kernel_T()
    return {
        "HOT": kt["HOT"],
        "WARM": kt["WARM"],
        "COLD": kt["COLD"],
        "TOMB": max(0.001, kt["TOMB"] * 0.5),
    }


def _is_engine_sid(aid) -> bool:
    return isinstance(aid, str) and bool(_ENGINE_SID_RE.match(aid))


class KarmazynHost:
    """Sesja hosta spięta z ewaluatorem Lua."""

    def __init__(self, store, ev, boot_t0=None, io=None, thermal=None):
        self.store = store
        self.ev = ev
        self.boot_t0 = boot_t0 if boot_t0 is not None else time.monotonic()
        # I/O × matryca termiczna (Luneta: adapter poza jądrem)
        self.io = io
        self.thermal = thermal
        self._epoch = 0
        self._agents = {}          # pid -> dict (stub)
        self._holograms = {}       # id -> dict (stub)
        self._fs = {}              # (bubble, file_id) -> content
        self._cache = {}           # name -> {E, S, ...}
        self._screen = []          # clear_screen marker for tests
        # surface Φ: logiczne id (string) z create_atom/clone — nie heap Lua aN
        self._phi_ids = set()
        # Product native (u32): logiczna nazwa → realne id Store (int)
        # Python Store: zwykle 1:1 string; alias i tak nieszkodliwy
        self._id_alias = {}
        # jeden proxy na id — bez ponownej alokacji bąbli przy każdym list_atoms
        self._proxy_by_id = {}

    def _resolve_aid(self, aid):
        """Logical id (Lua/tools) → id Store (str | int)."""
        if aid is None:
            return None
        if aid in self._id_alias:
            return self._id_alias[aid]
        if isinstance(aid, str) and aid in self._id_alias:
            return self._id_alias[aid]
        return aid

    def _register_alias(self, logical, real) -> None:
        if logical is None or real is None:
            return
        key = str(logical)
        if not key or _is_engine_sid(key):
            return
        self._id_alias[key] = real
        self._phi_ids.add(key)

    def _store_has(self, aid) -> bool:
        real = self._resolve_aid(aid)
        try:
            return bool(self.store.has_atom(real))
        except (TypeError, ValueError):
            return False

    def _store_get(self, aid):
        real = self._resolve_aid(aid)
        try:
            return self.store.get_atom(real)
        except (TypeError, ValueError):
            return None

    # ── pomocnicze: tabele Lua ─────────────────────────────────────────
    def _tbl(self):
        return self.store.bubble_new("table")

    def _set(self, tbl, key, value):
        self.ev._table_set(tbl, key, value)

    def _arr(self, items):
        t = self._tbl()
        for i, v in enumerate(items, 1):
            self._set(t, i, v)
        return t

    def _atom_proxy(self, atom, logical_id=None):
        """Tabela z __index: pola i metody atomu (live po id).

        Cache per id: ponowne list_atoms/get_atom NIE alokuje nowych bąbli/atomów
        w Store (wcześniej każdy list = nowe proxy = eksplozja heapu silnika).

        logical_id: publiczne id z Lua/tools (string); real id w Store może być u32.
        """
        real = getattr(atom, "id", None)
        if real is None:
            return None
        # klucze cache: preferuj logiczne string id (surface Φ)
        pub = logical_id if isinstance(logical_id, str) and logical_id else real
        cache_key = pub if isinstance(pub, str) else str(real)
        cached = self._proxy_by_id.get(cache_key)
        if cached is not None:
            return cached

        store = self.store
        host = self

        def _live():
            try:
                return store.get_atom(real)
            except (TypeError, ValueError):
                return None

        def idx(_tbl, key=None, *_):
            if key is None:
                return None
            a = _live()
            if a is None:
                return None
            if key == "id":
                # tools/Lua widzą logiczne id gdy znamy alias
                return pub if isinstance(pub, str) else real
            if key == "S":
                return a.S
            if key == "E":
                return a.E
            if key == "state":
                return a.state
            if key == "age":
                try:
                    return float(a.age())
                except Exception:
                    return 0.0
            if key == "T_raw":
                return float(a.T)

            if key == "store_id":
                return real
            if key == "get_T":
                def get_T(*_a):
                    cur = _live()
                    return float(cur.T) if cur is not None else 0.0
                return get_T

            if key == "get_T_frac":
                def get_T_frac(*_a):
                    cur = _live()
                    if cur is None:
                        return 0.0
                    tmax = _kernel_T()["MAX"] or 100.0
                    return max(0.0, min(1.0, float(cur.T) / float(tmax)))
                return get_T_frac

            if key == "set_E":
                def set_E(new_e=None, *_a):
                    cur = _live()
                    if cur is None:
                        return False
                    if new_e is not None:
                        cur.E = str(new_e)
                        if hasattr(cur, "touch_write"):
                            cur.touch_write()
                    return True
                return set_E

            if key == "set_state":
                def set_state(layer=None, *_a):
                    cur = _live()
                    if cur is None or not isinstance(layer, str):
                        return False
                    u = layer.upper()
                    sm = _state_T_map()
                    if u not in sm:
                        return False
                    cur.T = float(sm[u])
                    if hasattr(cur, "_update_state"):
                        cur._update_state()
                    return True
                return set_state

            if key == "refresh":
                def refresh(*_a):
                    cur = _live()
                    if cur is None:
                        return False
                    try:
                        store.heat(cur)
                        return True
                    except TypeError:
                        pass
                    except Exception:
                        pass
                    if hasattr(cur, "heat"):
                        try:
                            cur.heat()
                            return True
                        except TypeError:
                            try:
                                cur.heat(10.0)
                                return True
                            except Exception:
                                pass
                    if hasattr(cur, "touch"):
                        cur.touch(2.0)
                        return True
                    return False
                return refresh

            if key == "consolidate":
                def consolidate(*_a):
                    # preferuj logiczne id (surface)
                    lid = pub if isinstance(pub, str) else str(real)
                    return host.consolidate(lid)
                return consolidate

            return None

        t = self._tbl()
        mt = self._tbl()
        self._set(mt, "__index", idx)
        self.ev._set_metatable(t, mt)
        self._proxy_by_id[cache_key] = t
        return t

    def _track_phi(self, aid: str) -> None:
        if isinstance(aid, str) and aid and not _is_engine_sid(aid):
            self._phi_ids.add(aid)

    def _untrack_phi(self, aid: str) -> None:
        key = str(aid) if aid is not None else ""
        self._phi_ids.discard(key)
        self._id_alias.pop(key, None)
        self._proxy_by_id.pop(key, None)

    def _reconcile_phi_ids(self) -> list:
        """Zwróć żywe atomy surface Φ.

        Źródła:
          1) rejestr hosta (create/clone przez karmazyn.*)
          2) store.create_atom — Python: string id; native: u32 + metadata _requested_id
        Nigdy nie listujemy heapu Lua (atom_new → a0,a1,…).
        """
        live = []
        seen = set()
        try:
            for a in self.store.atoms():
                rid = getattr(a, "id", None)
                md = getattr(a, "metadata", None) or {}
                req = None
                try:
                    req = md.get("_requested_id") if hasattr(md, "get") else None
                except Exception:
                    req = None
                if req is not None and str(req) and not _is_engine_sid(str(req)):
                    self._register_alias(str(req), rid)
                elif isinstance(rid, str) and not _is_engine_sid(rid):
                    self._phi_ids.add(rid)
        except Exception:
            pass
        for aid in list(self._phi_ids):
            a = self._store_get(aid)
            if a is None:
                self._untrack_phi(aid)
                continue
            key = str(aid)
            if key in seen:
                continue
            seen.add(key)
            live.append(a)
        return live

    # ── API powierzchni ────────────────────────────────────────────────
    def read_line(self, prompt=None, *_):
        p = "" if prompt is None else str(prompt)
        # 1) kolejka testowa na ewaluatorze (lua_bin smoke) — kompatybilność
        q = getattr(self.ev, "_io_input", None)
        if q:
            line = q.pop(0)
            if self.thermal is not None:
                self.thermal.heat_input()
            return line if isinstance(line, str) else str(line)
        # 2) matryca termiczna + IoPort (kanon Product)
        if self.thermal is not None:
            return self.thermal.read_line(p)
        if self.io is not None:
            line = self.io.read_line(p)
            return line if isinstance(line, str) else str(line)
        try:
            return input(p)
        except EOFError:
            return ""

    def clear_screen(self, *_):
        self._screen.append("clear")
        if self.thermal is not None:
            self.thermal.clear()
            return None
        if self.io is not None:
            self.io.clear()
            return None
        # ANSI (no-op na nie-TTY)
        try:
            import sys
            if sys.stdout.isatty():
                sys.stdout.write("\033[2J\033[H")
                sys.stdout.flush()
        except Exception:
            pass
        return None

    def sleep(self, sec=1, *_):
        # w testach / CI: KARMAZYN_NOSLEEP=1
        if os.environ.get("KARMAZYN_NOSLEEP") in ("1", "true", "yes"):
            return None
        if getattr(self, "_no_sleep", False):
            return None
        try:
            time.sleep(float(sec))
        except Exception:
            pass
        return None

    def get_epoch(self, *_):
        return int(self._epoch)

    def step(self, n=1, *_):
        try:
            n = int(n)
        except (TypeError, ValueError):
            n = 1
        n = max(1, n)
        self.store.settle(n)
        self._epoch += n
        return n

    def get_temperature(self, *_):
        st = self.store.stats()
        # „temperatura systemu” ≈ udział żywych
        total = max(1, st.get("total", 0))
        alive = st.get("alive", st.get("hot", 0))
        return float(alive) / float(total)

    def get_resources(self, *_):
        st = self.store.stats()
        t = self._tbl()
        for k, v in st.items():
            if isinstance(v, (int, float)):
                self._set(t, str(k), int(v) if isinstance(v, float) and v == int(v) else v)
        return t

    def list_atoms(self, state=None, *_):
        """Lista atomów surface Φ (create_atom), nie heapu Lua.

        state: HOT|WARM|COLD|TOMB albo ALL (debug: cały store.atoms, łącznie z aN).
        """
        st = state if isinstance(state, str) and state else None
        if isinstance(st, str) and st.upper() == "ALL":
            try:
                atoms = list(self.store.atoms())
            except Exception:
                atoms = []
            return self._arr([p for a in atoms if (p := self._atom_proxy(a)) is not None])

        want = st.upper() if isinstance(st, str) else None
        out = []
        for a in self._reconcile_phi_ids():
            if want and str(getattr(a, "state", "")).upper() != want:
                continue
            p = self._atom_proxy(a)
            if p is not None:
                out.append(p)
        return self._arr(out)

    def get_atom(self, aid=None, *_):
        if not isinstance(aid, str) or not aid:
            return None
        atom = self._store_get(aid)
        if atom is None:
            self._untrack_phi(aid)
            return None
        if not _is_engine_sid(aid):
            self._track_phi(aid)
        return self._atom_proxy(atom, logical_id=aid)

    def create_atom(self, aid=None, s=None, e=None, t=None, *_):
        if not isinstance(aid, str) or not aid:
            return "brak id"
        if _is_engine_sid(aid):
            return f"id {aid!r} zarezerwowane dla silnika (atom_new); użyj innej nazwy"
        S = "" if s is None else str(s)
        E = "" if e is None else str(e)
        T = _abs_T(t)
        try:
            if self._store_has(aid):
                return f"atom o id {aid!r} już istnieje"
            ret = self.store.create_atom(aid, S, E, T)
            # native: ret = u32; python: ret = string id
            real = ret if ret is not None else aid
            self._register_alias(aid, real)
            atom = self._store_get(aid)
            if atom is None:
                return "błąd create"
            return self._atom_proxy(atom, logical_id=aid)
        except Exception as ex:
            return str(ex)

    def delete_atom(self, aid=None, *_):
        if not isinstance(aid, str):
            return False
        try:
            real = self._resolve_aid(aid)
            ok = bool(self.store.delete_atom(real))
            self._untrack_phi(aid)
            return ok
        except Exception:
            self._untrack_phi(aid)
            return False

    def clone_atom(self, src=None, dst=None, *_):
        if not isinstance(src, str) or not isinstance(dst, str):
            return "złe id"
        if _is_engine_sid(dst):
            return f"id {dst!r} zarezerwowane dla silnika"
        a = self._store_get(src)
        if a is None:
            return f"brak źródła {src}"
        try:
            if self._store_has(dst):
                self.delete_atom(dst)
            ret = self.store.create_atom(dst, a.S, a.E, float(a.T))
            real = ret if ret is not None else dst
            self._register_alias(dst, real)
            atom = self._store_get(dst)
            return self._atom_proxy(atom, logical_id=dst) if atom else "błąd clone"
        except Exception as ex:
            return str(ex)

    def consolidate(self, aid=None, *_):
        if not isinstance(aid, str):
            return None
        atom = self._store_get(aid)
        if atom is None:
            return None
        label = f"bubble_{aid}"
        real = self._resolve_aid(aid)
        try:
            self.store.create_bubble(label, atom_ids=[real], root=True)
            return label
        except Exception:
            try:
                b = self.store.bubble_new(label)
                self.store.set_root(b)
                self.store.import_to_bubble(label, aid)
                return label
            except Exception:
                return None

    def recall(self, query=None, k=5, *_):
        q = "" if query is None else str(query)
        try:
            kk = int(k) if k is not None else 5
        except (TypeError, ValueError):
            kk = 5
        hits = []
        try:
            hits = self.store.resonance(q, k=kk) or []
        except Exception:
            hits = []
        # fallback: substring na E/S
        if not hits:
            for a in self.store.atoms():
                if q and (q in (a.E or "") or q in (a.S or "") or q in (a.id or "")):
                    hits.append((0.5, a.id))
                if len(hits) >= kk:
                    break
        rows = []
        for sim, aid in hits:
            row = self._tbl()
            sim_f = float(sim)
            self._set(row, "score", sim_f)
            self._set(row, "sim", sim_f)
            self._set(row, "id", aid)
            atom = self.store.get_atom(aid)
            e = atom.E if atom else ""
            s = atom.S if atom else ""
            self._set(row, "E", e)
            self._set(row, "S", s)
            # pola pod lua_bin/recall.lua
            self._set(row, "label", aid if not e else (aid + ":" + str(e)[:24]))
            self._set(row, "layer", "phi")
            rows.append(row)
        return self._arr(rows)

    def get_similarity(self, id1=None, id2=None, *_):
        if not isinstance(id1, str) or not isinstance(id2, str):
            return 0.0
        a = self.store.get_atom(id1)
        b = self.store.get_atom(id2)
        if a is None or b is None:
            return 0.0
        # HRR jeśli jest
        try:
            hits = self.store.resonance(a.E or a.S or a.id, k=50)
            for sim, aid in hits or []:
                if aid == id2:
                    return float(sim)
        except Exception:
            pass
        # proste podobieństwo tekstowe
        sa, sb = (a.E or a.S or ""), (b.E or b.S or "")
        if not sa or not sb:
            return 0.0
        if sa == sb:
            return 1.0
        return 0.2 if (sa in sb or sb in sa) else 0.0

    def list_bubbles(self, *_):
        rows = []
        try:
            bubbles = list(self.store.bubbles)
        except Exception:
            bubbles = []
        seen = set()
        skip = {
            "lua", "table", "call", "chunk", "preload", "load",
            "lib", "var", "field", "builtin", "param",
        }
        for b in bubbles:
            lab = getattr(b, "label", None) or ""
            if not lab or lab in seen:
                continue
            if lab in skip or lab.startswith("i:") or lab.startswith("s:"):
                continue
            seen.add(lab)
            content_parts = []
            n = 0
            try:
                binds = getattr(b, "bindings", {}) or {}
                n = len(binds)
                for name, atom in list(binds.items())[:5]:
                    if hasattr(atom, "E") and atom.E:
                        content_parts.append(str(atom.E)[:20])
                    else:
                        content_parts.append(str(name)[:20])
            except Exception:
                pass
            row = self._tbl()
            self._set(row, "id", lab)
            self._set(row, "label", lab)
            self._set(row, "n", n)
            self._set(row, "content", ", ".join(content_parts) if content_parts else "(pusto)")
            rows.append(row)
        return self._arr(rows)

    def list_holograms(self, *_):
        rows = []
        for hid, h in self._holograms.items():
            row = self._tbl()
            self._set(row, "id", hid)
            self._set(row, "label", h.get("label", hid))
            self._set(row, "topic", h.get("topic", h.get("label", hid)))
            labels = h.get("atom_labels") or h.get("atoms") or []
            self._set(row, "atom_labels", self._arr([str(x) for x in labels]))
            self._set(row, "epoch_created", int(h.get("epoch_created", 0)))
            rows.append(row)
        return self._arr(rows)

    def create_hologram(self, hid=None, topic=None, atom_ids=None, *_):
        """Utwórz hologram (ideę) w sesji hosta — bez pełnego PCA/HRR engine."""
        if not isinstance(hid, str) or not hid:
            hid = f"idea_{len(self._holograms) + 1}"
        topic = topic if isinstance(topic, str) else (topic or hid)
        labels = []
        if isinstance(atom_ids, (list, tuple)):
            labels = [str(x) for x in atom_ids]
        elif atom_ids is not None:
            # tablica Lua 1..n
            try:
                i = 1
                while i <= 64:
                    v = self.ev._table_get(atom_ids, i)
                    if v is None:
                        break
                    labels.append(str(v))
                    i += 1
            except Exception:
                pass
        self._holograms[hid] = {
            "label": hid,
            "topic": str(topic),
            "atom_labels": labels,
            "epoch_created": int(self._epoch),
            "prompt_seed": str(topic),
        }
        return hid

    def list_agents(self, *_):
        rows = []
        for pid, ag in sorted(self._agents.items()):
            row = self._tbl()
            self._set(row, "pid", int(pid))
            self._set(row, "name", ag.get("name", str(pid)))
            self._set(row, "task", ag.get("task", ag.get("status", "idle")))
            self._set(row, "status", ag.get("status", "idle"))
            prisms = ag.get("prisms") or []
            self._set(row, "prisms", self._arr([str(p) for p in prisms]))
            rows.append(row)
        return self._arr(rows)

    def spawn_agent(self, name=None, task=None, prisms=None, *_):
        """Utwórz agenta w rejestrze sesji (pid auto)."""
        pid = 1
        while pid in self._agents:
            pid += 1
        plist = []
        if isinstance(prisms, (list, tuple)):
            plist = [str(x) for x in prisms]
        elif prisms is not None:
            try:
                i = 1
                while i <= 32:
                    v = self.ev._table_get(prisms, i)
                    if v is None:
                        break
                    plist.append(str(v))
                    i += 1
            except Exception:
                pass
        if not plist:
            plist = ["phi"]
        self._agents[pid] = {
            "name": str(name or f"agent_{pid}"),
            "task": str(task or "idle"),
            "status": "running",
            "prisms": plist,
        }
        return pid

    def delete_agent(self, pid=None, *_):
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            return False
        if pid in self._agents:
            del self._agents[pid]
            return True
        return False

    def generate_from_idea(self, hid=None, prompt=None, temp=0.3, *_):
        """Syntetyczny wektor z hologramu (deterministyczny placeholder + szum z promptu)."""
        if not isinstance(hid, str) or hid not in self._holograms:
            return None
        h = self._holograms[hid]
        try:
            t = float(temp) if temp is not None else 0.3
        except (TypeError, ValueError):
            t = 0.3
        prompt = "" if prompt is None else str(prompt)
        seed = abs(hash((hid, h.get("topic", ""), prompt))) % (10 ** 9)
        dim = 16
        vec = []
        x = float(seed % 997) / 997.0
        for i in range(dim):
            x = (x * 1.6180339887 + 0.1 * t + 0.01 * i) % 1.0
            # mieszaj z literami promptu
            if prompt:
                x = (x + ord(prompt[i % len(prompt)]) / 255.0 * t) % 1.0
            vec.append(round(x * 2.0 - 1.0, 6))
        return self._arr(vec)

    # ── fs / cache (minimalne, w pamięci sesji) ────────────────────────
    def _fs_read(self, bubble=None, file_id=None, *_):
        key = (str(bubble or ""), str(file_id or ""))
        return self._fs.get(key)

    def _fs_write(self, bubble=None, file_id=None, _kind=None, content=None, *_):
        key = (str(bubble or ""), str(file_id or ""))
        self._fs[key] = "" if content is None else str(content)
        return True

    def _cache_read(self, name=None, *_):
        rec = self._cache.get(str(name or ""))
        if not rec:
            return None
        t = self._tbl()
        self._set(t, "E", rec.get("E", ""))
        self._set(t, "S", rec.get("S", ""))
        return t

    def _cache_write(self, name=None, s=None, content=None, _t=None, *_):
        self._cache[str(name or "")] = {
            "S": "" if s is None else str(s),
            "E": "" if content is None else str(content),
        }
        return True

    # ── UI tekstowe ────────────────────────────────────────────────────
    def progress_bar(self, value=0, maximum=100, width=20, _style=None, *_):
        try:
            v = float(value)
            m = float(maximum) if maximum else 100.0
            w = max(1, int(width))
        except (TypeError, ValueError):
            return "[?]"
        frac = 0.0 if m <= 0 else max(0.0, min(1.0, v / m))
        filled = int(round(frac * w))
        return "[" + ("#" * filled) + ("-" * (w - filled)) + "]"

    def draw_frame(self, title=None, lines=None, _style=None, *_):
        title = "" if title is None else str(title)
        # lines: tablica Lua lub lista Python
        out_lines = []
        if lines is None:
            pass
        elif isinstance(lines, list):
            out_lines = [str(x) for x in lines]
        else:
            # Bubble array 1..n
            try:
                i = 1
                while i <= 500:
                    v = self.ev._table_get(lines, i)
                    if v is None:
                        break
                    out_lines.append(str(v))
                    i += 1
            except Exception:
                out_lines = [str(lines)]
        width = max(len(title) + 4, 20, max((len(x) for x in out_lines), default=20))
        bar = "+" + ("-" * (width + 2)) + "+"
        mid = f"| {title.center(width)} |"
        body = [f"| {ln.ljust(width)} |" for ln in out_lines]
        return "\n".join([bar, mid, bar] + body + [bar])


def install_karmazyn_host(ev, store=None, boot_t0=None, io=None, thermal=None):
    """Zainstaluj global `karmazyn` + `karmazyn.ui` w ewaluatorze.

    Zwraca instancję KarmazynHost (dla testów / boot meta).
    io / thermal: opcjonalny IoPort + ThermalSurface (matryca I/O × Store).
    """
    store = store or ev.store
    # dziedzicz z ewaluatora, jeśli boot już podpiął surface
    if io is None:
        io = getattr(ev, "io", None)
    if thermal is None:
        thermal = getattr(ev, "thermal", None)
    host = KarmazynHost(store, ev, boot_t0=boot_t0, io=io, thermal=thermal)

    def bind_fn(tbl, name, fn):
        host._set(tbl, name, fn)

    k = host._tbl()
    for name, fn in (
        ("read_line", host.read_line),
        ("clear_screen", host.clear_screen),
        ("sleep", host.sleep),
        ("get_epoch", host.get_epoch),
        ("step", host.step),
        ("get_temperature", host.get_temperature),
        ("get_resources", host.get_resources),
        ("list_atoms", host.list_atoms),
        ("get_atom", host.get_atom),
        ("create_atom", host.create_atom),
        ("delete_atom", host.delete_atom),
        ("clone_atom", host.clone_atom),
        ("consolidate", host.consolidate),
        ("recall", host.recall),
        ("get_similarity", host.get_similarity),
        ("list_bubbles", host.list_bubbles),
        ("list_holograms", host.list_holograms),
        ("create_hologram", host.create_hologram),
        ("list_agents", host.list_agents),
        ("spawn_agent", host.spawn_agent),
        ("delete_agent", host.delete_agent),
        ("generate_from_idea", host.generate_from_idea),
    ):
        bind_fn(k, name, fn)

    # fs / cache jako podtabele
    fs = host._tbl()
    bind_fn(fs, "read", host._fs_read)
    bind_fn(fs, "write", host._fs_write)
    host._set(k, "fs", fs)

    cache = host._tbl()
    bind_fn(cache, "read", host._cache_read)
    bind_fn(cache, "write", host._cache_write)
    host._set(k, "cache", cache)

    ui = host._tbl()
    bind_fn(ui, "progress_bar", host.progress_bar)
    bind_fn(ui, "draw_frame", host.draw_frame)
    host._set(k, "ui", ui)

    # etykieta wersji surface (string w tabeli karmazyn)
    host._set(k, "_VERSION", HOST_API_VERSION)

    # progi termiczne jądra (skala substratu) — do wizualizacji w Lua
    kt = _kernel_T()
    host._set(k, "T_MAX", kt["MAX"])
    host._set(k, "T_HOT", kt["HOT"])
    host._set(k, "T_WARM", kt["WARM"])
    host._set(k, "T_INIT", kt["INIT"])
    host._set(k, "T_TOMB", kt["TOMB"])

    # global
    atom = store.atom_new("lib", "karmazyn", value=k)
    ev.G.bind("karmazyn", atom)
    if hasattr(ev, "_declared_globals"):
        ev._declared_globals.add("karmazyn")

    ev.host = host
    return host


def run_lua_tool(ev, name, lua_bin=None, args=None):
    """Uruchom skrypt z lua_bin/<name>.lua w bieżącej sesji (host czyta plik)."""
    if not name or not isinstance(name, str):
        raise ValueError("run_lua_tool: nazwa")
    name = name[:-4] if name.endswith(".lua") else name
    roots = []
    if lua_bin:
        roots.append(lua_bin)
    env = os.environ.get("KARMAZYN_LUA_BIN")
    if env:
        roots.append(env)
    # monorepo defaults
    here = os.path.dirname(os.path.abspath(__file__))
    roots.append(os.path.join(os.path.dirname(here), "lua_bin"))
    path = None
    for r in roots:
        if not r:
            continue
        cand = os.path.join(r, name + ".lua")
        if os.path.isfile(cand):
            path = cand
            break
    if path is None:
        raise FileNotFoundError(f"brak narzędzia {name!r} w lua_bin")
    return ev.run_file(path, chunkname="@" + name + ".lua", args=args or [])
