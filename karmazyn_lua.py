#!/usr/bin/env python3
"""
karmazyn_lua.py — Moduł integrujący LuaJIT z KarmazynOS v1.0
Zapewnia bezpieczne środowisko (piaskownicę) do wykonywania skryptów Lua
operujących bezpośrednio na atomach i pętli termodynamicznej.
Skrypty są ładowane i wykonywane natywnie z wnętrza Bąbli.
"""

import threading
from typing import Optional, Any

try:
    from lupa import LuaRuntime
except ImportError:
    print("⚠️ Brak biblioteki lupa. Zainstaluj ją: pip install lupa")
    LuaRuntime = None

from runtime import SanctuaryRuntime
from karmazyn_ui import gfx

class LuaSandbox:
    """Izolowane środowisko dla skryptów Lua."""
    @staticmethod
    def apply(lua: LuaRuntime):
        # Usuwamy dostęp do niebezpiecznych modułów i funkcji systemowych
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
    """
    Most między Pythonem (KarmazynOS) a środowiskiem Lua.
    Zarządza stanem Lupy i zapewnia bezpieczne metody dla skryptów.
    """
    def __init__(self, runtime: SanctuaryRuntime):
        self.rt = runtime
        self.lua = LuaRuntime(unpack_returned_tuples=True) if LuaRuntime else None
        # Używamy RLock (Reentrant Lock), aby uniknąć deadloku
        self.lock = threading.RLock()
        
        if self.lua:
            LuaSandbox.apply(self.lua)
            self._setup_globals()

    def _setup_globals(self):
        """Inicjalizuje globalne API dostępne dla skryptów Lua."""
        g = self.lua.globals()
        
        # Tworzymy główną tablicę 'karmazyn'
        self.lua.execute("karmazyn = { ui = {} }")
        karm = g.karmazyn
        
        # Rejestracja funkcji API KarmazynOS
        karm.create_atom = self._lua_create_atom
        karm.get_temperature = self._lua_get_temperature
        karm.get_state = self._lua_get_state
        karm.step = self._lua_step
        karm.on = self._lua_on_event

        # Funkcje API jądra i systemu
        karm.list_atoms = self._lua_list_atoms
        karm.get_atom = self._lua_get_atom
        karm.delete_atom = self._lua_delete_atom
        karm.stabilize_atom = self._lua_stabilize_atom
        karm.recall = self._lua_recall
        karm.read_line = self._lua_read_line
        karm.consolidate = self._lua_consolidate
        karm.refresh_bubble = self._lua_refresh_bubble
        karm.revoke_bubble = self._lua_revoke_bubble
        karm.archive_to_hologram = self._lua_archive_to_hologram
        karm.generate_from_idea = self._lua_generate_from_idea
        karm.clone_atom = self._lua_clone_atom
        karm.get_resources = self._lua_get_resources
        karm.get_epoch = self._lua_get_epoch
        karm.list_agents = self._lua_list_agents
        karm.route_output = self._lua_route_output

        # UI API
        def lua_draw_frame(title, lines, style="phi_core"):
            # Lupa przekazuje tabele Lua jako obiekty, które mogą nie być listami Pythona
            python_lines = list(lines.values()) if hasattr(lines, 'values') else list(lines)
            return gfx.draw_frame(title, python_lines, style)

        karm.ui.draw_frame = lua_draw_frame
        karm.ui.progress_bar = gfx.progress_bar
        karm.ui.status_dot = gfx.status_dot

    # =================================================================
    # MAPOWANIE API (Python -> Lua)
    # =================================================================

    def _lua_create_atom(self, id_str: str, S: str, E: str, T: float):
        """Tworzy atom; Lua wysyła T w skali 0..1, system używa 0..100."""
        with self.lock:
            try:
                atom = self.rt.create_atom(id_str, S, E, T * 100.0)
                return self._wrap_atom(atom)
            except Exception as e:
                return f"Błąd tworzenia atomu: {str(e)}"

    def _wrap_atom(self, atom):
        """Tworzy wirtualną tabelę Lua z metodami hermetyzującymi logikę atomu."""
        atom_table = self.lua.eval("{}")
        atom_table.id = atom.id
        atom_table.S = atom.S
        atom_table.E = atom.E
        atom_table.state = atom.state
        
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

    def _lua_get_temperature(self):
        """Zwraca średnią temperaturę układu w skali 0..1."""
        with self.lock:
            atoms = self.rt.list_atoms()
            if not atoms:
                return self.rt.phi.t_vacuum()
            return sum(a.T for a in atoms) / len(atoms) / 100.0

    def _lua_get_state(self, atom_id: str):
        with self.lock:
            atom = self.rt.get_atom(atom_id)
            return atom.state if atom else "TOMB"

    def _lua_step(self, n: int = 1):
        with self.lock:
            self.rt.step(n)

    def _lua_on_event(self, event_name: str, lua_func):
        """Rejestruje funkcję Lua jako asynchroniczny callback zdarzeń z EventBus."""
        def wrapper(atom):
            with self.lock:
                try:
                    wrapped_atom = self._wrap_atom(atom)
                    lua_func(wrapped_atom)
                except Exception as e:
                    print(f"  [Lua Event Error] Błąd wykonania zdarzenia '{event_name}': {e}")
        
        with self.lock:
            self.rt.events.on(event_name, wrapper)

    def _lua_list_atoms(self, layer: str = None):
        with self.lock:
            atoms = self.rt.list_atoms(layer=layer)
            return self.lua.table(*[self._wrap_atom(a) for a in atoms])

    def _lua_get_atom(self, atom_id: str):
        with self.lock:
            atom = self.rt.get_atom(atom_id)
            if atom:
                return self._wrap_atom(atom)
            return None

    def _lua_delete_atom(self, atom_id: str):
        with self.lock:
            try:
                self.rt.delete_atom(atom_id)
                return True
            except Exception:
                return False

    def _lua_stabilize_atom(self, atom_id: str):
        with self.lock:
            try:
                self.rt.stabilize_atom(atom_id)
                return True
            except Exception:
                return False

    def _lua_recall(self, query: str, k: int = 5):
        with self.lock:
            results = self.rt.recall(query, k=k)
            # Wyniki z SanctuaryRuntime.recall to lista słowników
            return self.lua.table(*results)

    def _lua_read_line(self, prompt: str = ""):
        return input(prompt)

    def _lua_consolidate(self, label: str):
        with self.lock:
            try:
                return self.rt.consolidate(label)
            except Exception as e:
                return f"Błąd konsolidacji: {str(e)}"

    def _lua_archive_to_hologram(self, topic: str, atom_ids, remove_originals: bool = False):
        with self.lock:
            try:
                # Lupa przekazuje tabele Lua jako obiekty, które mogą nie być listami Pythona
                python_ids = list(atom_ids.values()) if hasattr(atom_ids, 'values') else list(atom_ids)
                return self.rt.archive_to_hologram(topic, python_ids, remove_originals=remove_originals)
            except Exception as e:
                return f"Błąd tworzenia hologramu: {str(e)}"

    def _lua_generate_from_idea(self, hologram_id: str, prompt: str, temperature: float = 0.3):
        with self.lock:
            try:
                vec = self.rt.generate_from_idea(hologram_id, prompt, temperature=temperature)
                if vec is not None:
                    return self.lua.table(*vec.tolist())
                return None
            except Exception as e:
                return f"Błąd generowania: {str(e)}"

    def _lua_refresh_bubble(self, label: str):
        with self.lock:
            return self.rt.refresh_bubble(label)

    def _lua_revoke_bubble(self, label: str):
        with self.lock:
            return self.rt.revoke_bubble(label)

    def _lua_clone_atom(self, src_id: str, dst_id: str):
        with self.lock:
            try:
                atom = self.rt.clone_atom(src_id, dst_id)
                return self._wrap_atom(atom)
            except Exception as e:
                return f"Błąd klonowania: {str(e)}"

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

    def _lua_route_output(self, atom_id: str, target_alias: str):
        """Przesyła atom do bąbla wynikowego na podstawie aliasu z konfiguracji."""
        with self.lock:
            # Importy lokalne, aby uniknąć cykli przy inicjalizacji
            from shell import FS, BUBBLES

            target_id = FS.resolve_alias(target_alias)
            if BUBBLES.get_bubble(target_id):
                # Logika importu atomu do bąbla
                BUBBLES.import_to_bubble(target_id, atom_id, self.rt)
                return f"✅ Wynik {atom_id} przesłany do {target_alias} ({target_id})"
            return f"❌ Nie znaleziono celu dla aliasu: {target_alias}"

    # =================================================================
    # WYKONYWANIE KODU
    # =================================================================

    def run_script(self, script_content: str) -> Any:
        """Kompiluje i wykonuje podany ciąg znaków jako kod Lua."""
        if not self.lua:
            return "Błąd: Środowisko LuaJIT (lupa) nie jest dostępne."
        with self.lock:
            try:
                return self.lua.execute(script_content)
            except Exception as e:
                return f"  [Lua Error] {str(e)}"

    def run_file(self, filepath: str) -> Any:
        """Wczytuje plik i wykonuje go jako kod Lua."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            return self.run_script(content)
        except Exception as e:
            return f"Błąd odczytu pliku: {str(e)}"

    def run_bubble(self, bubble_label: str) -> Any:
        """
        Pobiera zawartość wskazanego Bąbla z SanctuaryRuntime
        i wykonuje go jako kod Lua w bezpiecznej piaskownicy.
        """
        with self.lock:
            bubble = self.rt.get_bubble(bubble_label)
            if not bubble:
                return f"Błąd: Bąbel '{bubble_label}' nie istnieje."
            
            # W runtime.py (v1.3) zawartość to po prostu bubble.content
            return self.run_script(bubble.content)


# =================================================================
# MODUŁ TESTOWY 
# =================================================================
if __name__ == "__main__":
    rt = SanctuaryRuntime()
    executor = LuaExecutor(rt)
    
    # 1. Definiujemy kod skryptu jako czysty tekst. 
    # S (sygnatura) to komentarz Lua, by po konsolidacji kod był poprawny.
    lua_code = """
        print(">> LUA: Jestem skryptem wykonującym się bezpośrednio z Bąbla!")
        local a = karmazyn.create_atom("agent_1", "Proces", "Aktywny", 0.95)
        print(">> LUA: Powołałem do życia atom:", a.id, "z energią", a.get_T())
    """
    
    # 2. Rejestrujemy kod w KarmazynOs jako gorący Atom (zapis do macierzy)
    rt.write(name="skrypt_rdzenny", S="-- definicja skryptu", E=lua_code, T=100.0)
    
    # 3. Konsolidujemy ten Atom do trwałego Bąbla
    rt.consolidate("skrypt_rdzenny")
    
    # 4. Wykonujemy kod odwołując się wyłącznie do Bąbla!
    print("--- Start egzekucji z Bąbla ---")
    wynik = executor.run_bubble("skrypt_rdzenny")
    if isinstance(wynik, str) and wynik.startswith("Błąd"):
        print(wynik)
    print("--- Koniec egzekucji ---")