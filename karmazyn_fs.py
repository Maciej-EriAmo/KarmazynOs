"""
KarmazynOS — Semantyczny System Plików
Warstwowa nawigacja i transformacje stanów, wszystko delegowane do runtime.
"""
from typing import Optional
from runtime import SanctuaryRuntime, SystemState
from karmazyn_ui import gfx

class KarmazynFS:
    def __init__(self, runtime: SanctuaryRuntime):
        self.rt = runtime
        self.cwd = "HOT"                # bieżąca warstwa
        self.current_prism: Optional[str] = None
        self.current_emanation: Optional[str] = None  # filtr z CD @

    # ─── Nawigacja ─────────────────────────
    def ls(self, layer: str = None) -> str:
        layer = layer or self.cwd
        atoms = self.rt.list_atoms(
            layer=layer,
            prism=self.current_prism,
            emanation=self.current_emanation
        )
        if not atoms:
            return "Brak widocznych atomów."
        rows = []
        for a in atoms:
            bar = gfx.progress_bar(a.T, a.T_max, fg=SystemState.color_for(a))
            rows.append([a.id, a.S, a.E, bar, f"{a.T:.1f}°", a.state])
        return gfx.table(["ID", "S", "E", "Żar", "T", "Stan"], rows)

    def cd(self, target: str) -> str:
        if target.startswith("@"):
            self.current_emanation = target[1:]
            return f"Filtr Emanacji: '{target[1:]}'"
        if target in ("HOT", "WARM", "COLD", "TOMB"):
            self.cwd = target
            self.current_emanation = None  # reset filtra przy zmianie warstwy
            return f"Warstwa: {target}"
        return f"Nieznana warstwa: {target}"

    def pwd(self) -> str:
        count = self.rt.count_atoms(self.cwd)
        return f"{self.cwd} ({count} atomów)"

    # ─── Operacje CRUD ─────────────────────
    def touch(self, id: str, S: str = None, E: str = "Tekst", T: float = 80) -> str:
        if self.rt.has_atom(id):
            return f"Atom {id} już istnieje."
        self.rt.create_atom(id, S or f"USER-{id}", E, T)
        return f"Stworzono Atom {id}."

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
        if new_layer not in ("HOT", "WARM", "COLD"):
            return "Nieprawidłowa warstwa."
        try:
            self.rt.update_atom(id, state=new_layer)
            return f"Atom {id} przeniesiony do {new_layer}."
        except ValueError as e:
            return str(e)

    def setE(self, id: str, new_E: str) -> str:
        try:
            self.rt.update_atom(id, E=new_E)
            return f"Emanacja {id} zmieniona na '{new_E}'."
        except ValueError as e:
            return str(e)

    def find(self, query: str) -> str:
        results = []
        for a in self.rt.list_atoms():
            if query in a.S or query in a.E:
                results.append(f"{a.id}: S={a.S} E={a.E}")
        return "\n".join(results) if results else "Nic nie znaleziono."