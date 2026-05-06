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
        self.lua.execute("karmazyn = {}")
        karm = g.karmazyn
        
        # Rejestracja funkcji API KarmazynOS
        karm.create_atom = self._lua_create_atom
        karm.get_temperature = self._lua_get_temperature
        karm.get_state = self._lua_get_state
        karm.step = self._lua_step
        karm.on = self._lua_on_event

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
        
        def get_T():
            return atom.T / 100.0
            
        def set_T(value):
            with self.lock:
                atom.T = max(0.0, min(100.0, value * 100.0))
                
        def refresh():
            with self.lock:
                self.rt.stabilize_atom(atom.id)
                
        def corrupt(amount):
            with self.lock:
                self.rt.corrupt_atom(atom.id, amount * 100.0)
                
        atom_table.get_T = get_T
        atom_table.set_T = set_T
        atom_table.refresh = refresh
        atom_table.corrupt = corrupt
        
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