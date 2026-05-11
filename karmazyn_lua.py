#!/usr/bin/env python3
"""
karmazyn_lua.py — Moduł integrujący LuaJIT z KarmazynOS v1.1
"""

import sys
import threading
from typing import Optional, Any

try:
    from lupa import LuaRuntime
except ImportError:
    print("⚠️ Brak biblioteki lupa. Zainstaluj: pip install lupa")
    LuaRuntime = None

from runtime import SanctuaryRuntime
from karmazyn_ui import gfx


class LuaSandbox:
    @staticmethod
    def apply(lua: LuaRuntime):
        lua.execute("""
            os.execute = nil
            os.remove = nil
            os.rename = nil
            os.exit = nil
            io.popen = nil
            io.open = nil
            io.lines = nil
            require = nil
            package = nil
        """)


class LuaExecutor:
    def __init__(self, runtime: SanctuaryRuntime):
        self.rt = runtime
        self.lua = LuaRuntime(unpack_returned_tuples=True) if LuaRuntime else None
        self.lock = threading.RLock()
        self.alias_resolver = None
        self.bubble_importer = None

        if self.lua:
            LuaSandbox.apply(self.lua)
            self._setup_globals()

    def bind_system_services(self, resolver_func, importer_func):
        self.alias_resolver = resolver_func
        self.bubble_importer = importer_func

    def _setup_globals(self):
        g = self.lua.globals()
        self.lua.execute("karmazyn = { ui = {} }")
        karm = g.karmazyn

        # === API podstawowe ===
        karm.create_atom = self._lua_create_atom
        karm.get_temperature = self._lua_get_temperature
        karm.get_state = self._lua_get_state
        karm.step = self._lua_step
        karm.on = self._lua_on_event
        karm.list_atoms = self._lua_list_atoms
        karm.get_atom = self._lua_get_atom
        karm.delete_atom = self._lua_delete_atom
        karm.stabilize_atom = self._lua_stabilize_atom
        karm.recall = self._lua_recall
        karm.consolidate = self._lua_consolidate
        karm.refresh_bubble = self._lua_refresh_bubble
        karm.revoke_bubble = self._lua_revoke_bubble
        karm.archive_to_hologram = self._lua_archive_to_hologram
        karm.generate_from_idea = self._lua_generate_from_idea
        karm.clone_atom = self._lua_clone_atom
        karm.get_similarity = self._lua_get_similarity
        karm.get_resources = self._lua_get_resources
        karm.get_epoch = self._lua_get_epoch
        karm.list_agents = self._lua_list_agents
        karm.route_output = self._lua_route_output
        karm.delete_agent = self._lua_delete_agent
        karm.list_holograms = self._lua_list_holograms
        karm.list_bubbles = self._lua_list_bubbles
        karm.get_tvac = self._lua_get_tvac
        karm.clear_screen = self._lua_clear_screen
        import time
        karm.sleep = time.sleep

        # === read_line (działa interaktywnie) ===
        def lua_read_line(prompt=""):
            return input(prompt)
        karm.read_line = lua_read_line

        # === UI ===
        def lua_draw_frame(title, lines, style="phi_core"):
            python_lines = list(lines.values()) if hasattr(lines, 'values') else list(lines)
            return gfx.draw_frame(title, python_lines, style)

        karm.ui.draw_frame = lua_draw_frame
        karm.ui.progress_bar = gfx.progress_bar
        karm.ui.status_dot = gfx.status_dot

    # ---------- metody pomocnicze (wrapowanie atomów) ----------
    def _wrap_atom(self, atom):
        atom_table = self.lua.eval("{}")
        atom_table.id = atom.id
        atom_table.S = atom.S
        atom_table.E = atom.E
        atom_table.state = atom.state
        atom_table.age = atom.age

        def get_T():
            return atom.T / 100.0
        def set_T(value):
            with self.lock:
                atom.T = max(0.0, min(100.0, value * 100.0))
        def set_E(value):
            with self.lock:
                atom.E = str(value)
                self.rt.phi.register(atom.id, f"{atom.S} {atom.E}")
        def refresh():
            with self.lock:
                self.rt.stabilize_atom(atom.id)
        def corrupt(amount):
            with self.lock:
                self.rt.corrupt_atom(atom.id, amount * 100.0)
        def consolidate():
            with self.lock:
                return self.rt.consolidate(atom.id)
        def set_state(new_layer):
            with self.lock:
                try:
                    self.rt.update_atom(atom.id, state=new_layer)
                    return True
                except Exception:
                    return False

        atom_table.get_T = get_T
        atom_table.set_T = set_T
        atom_table.set_E = set_E
        atom_table.refresh = refresh
        atom_table.corrupt = corrupt
        atom_table.consolidate = consolidate
        atom_table.set_state = set_state
        return atom_table

    # ---------- implementacje API ----------
    def _lua_create_atom(self, id_str, S, E, T):
        with self.lock:
            try:
                atom = self.rt.create_atom(id_str, S, E, T * 100.0)
                return self._wrap_atom(atom)
            except Exception as e:
                return f"Błąd tworzenia atomu: {e}"

    def _lua_get_temperature(self):
        with self.lock:
            atoms = self.rt.list_atoms()
            if not atoms:
                return 0.05
            return sum(a.T for a in atoms) / len(atoms) / 100.0

    def _lua_get_state(self, atom_id):
        with self.lock:
            atom = self.rt.get_atom(atom_id)
            return atom.state if atom else "TOMB"

    def _lua_step(self, n=1):
        with self.lock:
            self.rt.step(n)

    def _lua_on_event(self, event_name, lua_func):
        def wrapper(atom):
            with self.lock:
                try:
                    lua_func(self._wrap_atom(atom))
                except Exception as e:
                    print(f"[Lua Event Error] {event_name}: {e}")
        with self.lock:
            self.rt.events.on(event_name, wrapper)

    def _lua_list_atoms(self, layer=None):
        with self.lock:
            atoms = self.rt.list_atoms(layer=layer)
            return self.lua.table(*[self._wrap_atom(a) for a in atoms])

    def _lua_get_atom(self, atom_id):
        with self.lock:
            atom = self.rt.get_atom(atom_id)
            return self._wrap_atom(atom) if atom else None

    def _lua_delete_atom(self, atom_id):
        with self.lock:
            try:
                self.rt.delete_atom(atom_id)
                return True
            except Exception:
                return False

    def _lua_stabilize_atom(self, atom_id):
        with self.lock:
            try:
                self.rt.stabilize_atom(atom_id)
                return True
            except Exception:
                return False

    def _lua_recall(self, query, k=5):
        with self.lock:
            results = self.rt.recall(query, k=k)
            return self.lua.table(*results)

    def _lua_consolidate(self, label):
        with self.lock:
            try:
                return self.rt.consolidate(label)
            except Exception as e:
                return f"Błąd konsolidacji: {e}"

    def _lua_refresh_bubble(self, label):
        with self.lock:
            return self.rt.refresh_bubble(label)

    def _lua_revoke_bubble(self, label):
        with self.lock:
            return self.rt.revoke_bubble(label)

    def _lua_archive_to_hologram(self, topic, atom_ids, remove_originals=False):
        with self.lock:
            try:
                ids = list(atom_ids.values()) if hasattr(atom_ids, 'values') else list(atom_ids)
                return self.rt.archive_to_hologram(topic, ids, remove_originals=remove_originals)
            except Exception as e:
                return f"Błąd tworzenia hologramu: {e}"

    def _lua_generate_from_idea(self, hid, prompt, temperature=0.3):
        with self.lock:
            try:
                vec = self.rt.generate_from_idea(hid, prompt, temperature)
                return self.lua.table(*vec.tolist()) if vec is not None else None
            except Exception as e:
                return f"Błąd generowania: {e}"

    def _lua_clone_atom(self, src, dst):
        with self.lock:
            try:
                atom = self.rt.clone_atom(src, dst)
                return self._wrap_atom(atom)
            except Exception as e:
                return f"Błąd klonowania: {e}"

    def _lua_get_similarity(self, id1, id2):
        with self.lock:
            try:
                import numpy as np
                a1 = self.rt.get_atom(id1)
                a2 = self.rt.get_atom(id2)
                if not a1 or not a2:
                    return None
                v1 = self.rt.phi.get(id1) or a1._vec
                v2 = self.rt.phi.get(id2) or a2._vec
                return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-9))
            except Exception:
                return None

    def _lua_get_resources(self):
        with self.lock:
            t = self.lua.table()
            for k, v in self.rt.resources.items():
                t[k] = v
            return t

    def _lua_get_epoch(self):
        with self.lock:
            return self.rt.phi.epoch

    def _lua_list_agents(self):
        with self.lock:
            agents = []
            for pid, agent in self.rt._agents.items():
                agents.append({
                    "pid": pid,
                    "name": agent.name,
                    "task": agent.task,
                    "prisms": self.lua.table(*agent.prisms)
                })
            return self.lua.table(*agents)

    def _lua_route_output(self, atom_id, target_alias):
        with self.lock:
            if not self.alias_resolver or not self.bubble_importer:
                return "Błąd: Brak usług routingu."
            target_id = self.alias_resolver(target_alias)
            if not target_id:
                return f"Nieznany alias: {target_alias}"
            self.bubble_importer(target_id, atom_id, self.rt)
            return f"✅ Wynik {atom_id} → {target_alias}"

    def _lua_delete_agent(self, pid):
        with self.lock:
            if pid in self.rt._agents:
                del self.rt._agents[pid]
                return True
            return False

    def _lua_list_holograms(self):
        with self.lock:
            holos = []
            for hid, h in self.rt._holograms.items():
                holos.append({
                    "id": hid,
                    "topic": h.topic,
                    "epoch_created": h.epoch_created,
                    "atom_labels": self.lua.table(*h.atom_labels)
                })
            return self.lua.table(*holos)

    def _lua_list_bubbles(self):
        with self.lock:
            bubbles = []
            for label, b in self.rt._bubbles.items():
                bubbles.append({
                    "label": label,
                    "id": f"bubble_{label}",
                    "content": b.content
                })
            return self.lua.table(*bubbles)

    def _lua_get_tvac(self):
        with self.lock:
            return self.rt.phi.t_vacuum()

    def _lua_clear_screen(self):
        print("\033[H\033[J", end="")

    # ---------- wykonanie ----------
    def run_script(self, script_content: str, args: list = None) -> Any:
        if not self.lua:
            return "Błąd: LuaJIT niedostępny."
        with self.lock:
            try:
                if args:
                    self.lua.globals().arg = self.lua.table(*args)
                else:
                    self.lua.globals().arg = self.lua.table()
                return self.lua.execute(script_content)
            except Exception as e:
                return f"[Lua Error] {e}"

    def run_file(self, filepath: str, args: list = None) -> Any:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            return self.run_script(content, args=args)
        except Exception as e:
            return f"Błąd odczytu pliku: {e}"

    def run_bubble(self, bubble_label: str) -> Any:
        with self.lock:
            bubble = self.rt.get_bubble(bubble_label)
            if not bubble:
                return f"Błąd: Bąbel '{bubble_label}' nie istnieje."
            return self.run_script(bubble.content)


if __name__ == "__main__":
    rt = SanctuaryRuntime()
    ex = LuaExecutor(rt)
    lua_code = """
        print(">> LUA: Jestem skryptem wykonującym się bezpośrednio z Bąbla!")
        local a = karmazyn.create_atom("agent_1", "Proces", "Aktywny", 0.95)
        print(">> LUA: Powołałem do życia atom:", a.id, "z energią", a.get_T())
    """
    rt.write(name="skrypt_rdzenny", S="-- definicja skryptu", E=lua_code, T=100.0)
    rt.consolidate("skrypt_rdzenny")
    print("--- Start egzekucji z Bąbla ---")
    wynik = ex.run_bubble("skrypt_rdzenny")
    if isinstance(wynik, str) and wynik.startswith("Błąd"):
        print(wynik)
    print("--- Koniec egzekucji ---")
