"""karmazyn_host — bindings hosta dla gościa Lua (tabela globalna `karmazyn`).

Sandbox = bąbel: gość woła tylko jawnie wstrzyknięte funkcje.
Host ma Store + (opcjonalnie) kolejkę io_input / stdin.

Surface v1 (karmazyn_lua 0.9.0): lua_bin tools + session agents/holograms.
"""

from __future__ import annotations

import os
import time

# wersja surface hosta (nie mylić z jądrem / z __version__ pakietu Lua)
HOST_API_VERSION = "1.0.0"


# typowe T dla warstw FSM (wystarczająco w progu state_for_T)
_STATE_T = {
    "HOT": 0.95,
    "WARM": 0.45,
    "COLD": 0.05,
    "TOMB": 0.001,
}


class KarmazynHost:
    """Sesja hosta spięta z ewaluatorem Lua."""

    def __init__(self, store, ev, boot_t0=None):
        self.store = store
        self.ev = ev
        self.boot_t0 = boot_t0 if boot_t0 is not None else time.monotonic()
        self._epoch = 0
        self._agents = {}          # pid -> dict (stub)
        self._holograms = {}       # id -> dict (stub)
        self._fs = {}              # (bubble, file_id) -> content
        self._cache = {}           # name -> {E, S, ...}
        self._screen = []          # clear_screen marker for tests

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

    def _atom_proxy(self, atom):
        """Tabela z __index: pola i metody atomu (live)."""
        t = self._tbl()
        store = self.store
        host = self

        def idx(_tbl, key=None, *_):
            if key is None:
                return None
            if key == "id":
                return atom.id
            if key == "S":
                return atom.S
            if key == "E":
                return atom.E
            if key == "state":
                return atom.state
            if key == "age":
                try:
                    return float(atom.age())
                except Exception:
                    return 0.0
            if key == "T_raw":
                return float(atom.T)

            if key == "get_T":
                def get_T(*_a):
                    return float(atom.T)
                return get_T

            if key == "set_E":
                def set_E(new_e=None, *_a):
                    if new_e is not None:
                        atom.E = str(new_e)
                        if hasattr(atom, "touch_write"):
                            atom.touch_write()
                    return True
                return set_E

            if key == "set_state":
                def set_state(layer=None, *_a):
                    if not isinstance(layer, str):
                        return False
                    u = layer.upper()
                    if u not in _STATE_T:
                        return False
                    atom.T = float(_STATE_T[u])
                    if hasattr(atom, "_update_state"):
                        atom._update_state()
                    return True
                return set_state

            if key == "refresh":
                def refresh(*_a):
                    if hasattr(atom, "heat"):
                        atom.heat(0.5)
                    elif hasattr(atom, "touch"):
                        atom.touch(2.0)
                    return True
                return refresh

            if key == "consolidate":
                def consolidate(*_a):
                    return host.consolidate(atom.id)
                return consolidate

            return None

        mt = self._tbl()
        self._set(mt, "__index", idx)
        self.ev._set_metatable(t, mt)
        return t

    # ── API powierzchni ────────────────────────────────────────────────
    def read_line(self, prompt=None, *_):
        p = "" if prompt is None else str(prompt)
        # kolejka hosta (testy / CLI)
        q = getattr(self.ev, "_io_input", None)
        if q:
            line = q.pop(0)
            return line if isinstance(line, str) else str(line)
        try:
            return input(p)
        except EOFError:
            return ""

    def clear_screen(self, *_):
        self._screen.append("clear")
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
        st = state if isinstance(state, str) and state else None
        if isinstance(st, str) and st.upper() == "ALL":
            st = None
        try:
            atoms = self.store.atoms(st)
        except Exception:
            atoms = self.store.atoms()
        return self._arr([self._atom_proxy(a) for a in atoms])

    def get_atom(self, aid=None, *_):
        if not isinstance(aid, str) or not aid:
            return None
        atom = self.store.get_atom(aid)
        if atom is None:
            return None
        return self._atom_proxy(atom)

    def create_atom(self, aid=None, s=None, e=None, t=0.8, *_):
        if not isinstance(aid, str) or not aid:
            return "brak id"
        S = "" if s is None else str(s)
        E = "" if e is None else str(e)
        try:
            T = float(t) if t is not None else 0.8
        except (TypeError, ValueError):
            T = 0.8
        try:
            if self.store.has_atom(aid):
                return f"atom o id {aid!r} już istnieje"
            self.store.create_atom(aid, S, E, T)
            atom = self.store.get_atom(aid)
            return self._atom_proxy(atom) if atom else "błąd create"
        except Exception as ex:
            return str(ex)

    def delete_atom(self, aid=None, *_):
        if not isinstance(aid, str):
            return False
        try:
            return bool(self.store.delete_atom(aid))
        except Exception:
            return False

    def clone_atom(self, src=None, dst=None, *_):
        if not isinstance(src, str) or not isinstance(dst, str):
            return "złe id"
        a = self.store.get_atom(src)
        if a is None:
            return f"brak źródła {src}"
        try:
            if self.store.has_atom(dst):
                self.store.delete_atom(dst)
            self.store.create_atom(dst, a.S, a.E, float(a.T))
            return self._atom_proxy(self.store.get_atom(dst))
        except Exception as ex:
            return str(ex)

    def consolidate(self, aid=None, *_):
        if not isinstance(aid, str):
            return None
        atom = self.store.get_atom(aid)
        if atom is None:
            return None
        label = f"bubble_{aid}"
        try:
            self.store.create_bubble(label, atom_ids=[aid], root=True)
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


def install_karmazyn_host(ev, store=None, boot_t0=None):
    """Zainstaluj global `karmazyn` + `karmazyn.ui` w ewaluatorze.

    Zwraca instancję KarmazynHost (dla testów / boot meta).
    """
    store = store or ev.store
    host = KarmazynHost(store, ev, boot_t0=boot_t0)

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
