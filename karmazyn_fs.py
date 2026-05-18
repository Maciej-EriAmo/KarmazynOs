"""
KarmazynOS — Semantyczny System Plików
Warstwowa nawigacja, wsparcie dla bąbli, przestrzeni użytkowników i wyników rozproszonych.
"""
from typing import Optional
from runtime import SanctuaryRuntime, SystemState
from karmazyn_ui import gfx


class KarmazynFS:
    def __init__(self, runtime: SanctuaryRuntime, bubbles_runtime=None):
        self.rt = runtime
        self.bubbles = bubbles_runtime      # Referencja do systemu bąbli
        self.cwd = "HOT"                    # "HOT", "WARM", "COLD" LUB id bąbla
        self.current_prism: Optional[str] = None
        self.current_emanation: Optional[str] = None

        # Bąbel konfiguracyjny - działa jak lokalny routing / .profile
        self.config_bubble: Optional[str] = None

    def set_config_bubble(self, bubble_id: str):
        """Ustawia bąbel pełniący rolę tablicy routingu dla węzła/użytkownika."""
        self.config_bubble = bubble_id

    def resolve_alias(self, name: str) -> str:
        """Rozwiązuje logiczne aliasy (np. 'wyniki') na fizyczne ID bąbli rozproszonych."""
        if not self.config_bubble or not self.bubbles:
            return name

        config = self.bubbles.get_bubble(self.config_bubble)
        if not config:
            return name

        # Szukamy atomu definiującego alias wewnątrz bąbla konfiguracyjnego.
        # Konwencja: S = "ALIAS", id = <nazwa_aliasu>, E = <docelowy_id>
        atoms = self.bubbles.get_active_atoms(self.config_bubble)
        for a in atoms:
            s_val  = a.get('S')  if isinstance(a, dict) else a.S
            e_val  = a.get('E')  if isinstance(a, dict) else a.E
            id_val = a.get('id') if isinstance(a, dict) else a.id

            if s_val == "ALIAS" and id_val == name:
                return e_val
        return name

    # ─── Nawigacja ─────────────────────────
    def ls(self, path: str = None) -> str:
        target = path or self.cwd
        target = self.resolve_alias(target)

        atoms = []
        if target in ("HOT", "WARM", "COLD", "TOMB"):
            # BUG FIX: SanctuaryRuntime.list_atoms() nie ma parametru 'prism'.
            # Sygnatura: list_atoms(layer, emanation, visible_only).
            atoms = self.rt.list_atoms(
                layer=target,
                emanation=self.current_emanation
            )
        elif self.bubbles and self.bubbles.get_bubble(target):
            # Traktujemy bąbel jako wirtualny katalog (zgrupowane wyniki)
            atoms = self.bubbles.get_active_atoms(target)
        else:
            return f"Nieznana ścieżka / warstwa: {target}"

        if not atoms:
            return "Brak widocznych atomów."

        rows = []
        for a in atoms:
            # Ujednolicenie dostępu dla Atom vs słownik (z JSONa bąbli)
            id_val    = a.get('id', '?')    if isinstance(a, dict) else a.id
            s_val     = a.get('S', '?')     if isinstance(a, dict) else a.S
            e_val     = a.get('E', '?')     if isinstance(a, dict) else a.E
            t_val     = a.get('T', 0)       if isinstance(a, dict) else a.T
            t_max_val = a.get('T_max', 100) if isinstance(a, dict) else getattr(a, 'T_max', 100)
            state_val = a.get('state', 'BUBBLE') if isinstance(a, dict) else a.state

            color = "phi_signal" if t_val > 50 else "phi_decay"
            bar = gfx.progress_bar(t_val, t_max_val, fg=color)
            rows.append([id_val, s_val, e_val, bar, f"{t_val:.1f}°", state_val])

        return gfx.table(["ID", "S", "E", "Żar", "T", "Stan"], rows)

    def cd(self, target: str) -> str:
        if target.startswith("@"):
            self.current_emanation = target[1:]
            return f"Filtr Emanacji: '{target[1:]}'"

        resolved_target = self.resolve_alias(target)

        if resolved_target in ("HOT", "WARM", "COLD", "TOMB"):
            self.cwd = resolved_target
            self.current_emanation = None
            return f"Warstwa: {resolved_target}"

        if self.bubbles and self.bubbles.get_bubble(resolved_target):
            self.cwd = resolved_target
            self.current_emanation = None
            return f"Eksploracja Bąbla (Przestrzeń Wyników): {target} -> {resolved_target}"

        return f"Nieznany cel podróży: {target}"

    def pwd(self) -> str:
        if self.cwd in ("HOT", "WARM", "COLD", "TOMB"):
            count = self.rt.count_atoms(self.cwd)
        elif self.bubbles and self.bubbles.get_bubble(self.cwd):
            count = len(self.bubbles.get_active_atoms(self.cwd))
        else:
            count = 0
        return f"{self.cwd} ({count} elementów)"

    # ─── Operacje CRUD ─────────────────────
    def touch(self, id: str, S: str = None, E: str = "Tekst", T: float = 80) -> str:
        if self.rt.has_atom(id):
            return f"Atom {id} już istnieje."

        self.rt.create_atom(id, S or f"USER-{id}", E, T)

        if self.cwd not in ("HOT", "WARM", "COLD", "TOMB") and self.bubbles:
            return f"Stworzono Atom {id} (Rozważ dodanie go z shella do bąbla {self.cwd})."

        return f"Stworzono Atom {id} w macierzy bazowej."

    def rm(self, id: str) -> str:
        try:
            self.rt.delete_atom(id)
            return f"Atom {id} przeniesiony do TOMB."
        except ValueError as e:
            return str(e)

    def cp(self, src: str, dst: str) -> str:
        try:
            self.rt.clone_atom(src, dst)
            return f"Skopiowano {src} → {dst}."
        except ValueError as e:
            return str(e)

    def mv(self, id: str, new_layer: str) -> str:
        target = self.resolve_alias(new_layer)

        if target in ("HOT", "WARM", "COLD"):
            try:
                self.rt.update_atom(id, state=target)
                return f"Atom {id} przeniesiony do {target}."
            except ValueError as e:
                return str(e)

        elif self.bubbles and self.bubbles.get_bubble(target):
            return (f"Atom {id} wytypowany do eksportu do Grupy Wynikowej '{new_layer}' ({target}). "
                    f"Wymagane użycie IMPORT / CONSOLIDATE.")

        return "Nieprawidłowy cel (warstwa lub bąbel-sink nie istnieje)."

    def setE(self, id: str, new_E: str) -> str:
        try:
            self.rt.update_atom(id, E=new_E)
            return f"Emanacja {id} zmieniona na '{new_E}'."
        except ValueError as e:
            return str(e)

    def find(self, query: str) -> str:
        results = []

        # 1. Przeszukiwanie macierzy operacyjnej
        for a in self.rt.list_atoms():
            if query in a.S or query in a.E:
                results.append(f"[Φ] {a.id}: S={a.S} E={a.E}")

        # 2. Przeszukiwanie wnętrza obecnego bąbla roboczego (jeśli cwd to bąbel)
        if self.cwd not in ("HOT", "WARM", "COLD", "TOMB") and self.bubbles:
            atoms = self.bubbles.get_active_atoms(self.cwd)
            for a in atoms:
                s_val  = a.get('S', '') if isinstance(a, dict) else a.S
                e_val  = a.get('E', '') if isinstance(a, dict) else a.E
                id_val = a.get('id', '') if isinstance(a, dict) else a.id
                if query in s_val or query in e_val:
                    results.append(f"[🫧 {self.cwd}] {id_val}: S={s_val} E={e_val}")

        return "\n".join(results) if results else "Nic nie znaleziono."