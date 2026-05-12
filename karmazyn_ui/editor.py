import os

class EmanationEditor:
    """
    Termodynamiczny edytor liniowy dla KarmazynOs.
    Działa płynnie na PC oraz w terminalach mobilnych, edytując czystą Emanację.
    """
    def __init__(self, target_name="PLAZMA Φ (Niezapisane)", initial_content=""):
        self.target_name = target_name
        self.lines = initial_content.split('\n') if initial_content else []

    def _clear_screen(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    def _render_ui(self):
        self._clear_screen()
        print("=" * 60)
        print(f" [ EDYTOR EMANACJI ] | Cel: {self.target_name}")
        print("=" * 60)

        for i, line in enumerate(self.lines):
            print(f"{i+1:3d} | {line}")

        print("-" * 60)
        print(" TRYB PLAZMY: Wpisz kod, aby dodać nową linię na koniec.")
        print(" KOMENDY: :wq (Konsoliduj), :q! (Zniszcz), ")
        print("          :e <nr> (Edytuj linię), :d <nr> (Usuń linię), :i <nr> (Wstaw)")
        print("=" * 60)

    def run(self):
        while True:
            self._render_ui()
            try:
                cmd = input("Φ-EDIT> ")
            except (EOFError, KeyboardInterrupt):
                return None

            if cmd == ":wq":
                return "\n".join(self.lines)
            elif cmd == ":q!":
                return None
            elif cmd.startswith(":e "):
                try:
                    idx = int(cmd.split(' ')[1]) - 1
                    if 0 <= idx < len(self.lines):
                        print(f" Stara treść: {self.lines[idx]}")
                        self.lines[idx] = input(" Nowa treść: ")
                    else:
                        print(f" Błąd: Linia {idx+1} nie istnieje (zakres: 1-{len(self.lines)}).")
                except (ValueError, IndexError):
                    print(" Błąd składni. Prawidłowe użycie: :e <numer_linii>")
            elif cmd.startswith(":d "):
                try:
                    idx = int(cmd.split(' ')[1]) - 1
                    if 0 <= idx < len(self.lines):
                        removed = self.lines.pop(idx)
                        print(f" Usunięto: {removed}")
                    else:
                        print(f" Błąd: Brak linii {idx+1}.")
                except (ValueError, IndexError):
                    print(" Błąd składni. Prawidłowe użycie: :d <numer_linii>")
            elif cmd.startswith(":i "):
                try:
                    idx = int(cmd.split(' ')[1]) - 1
                    if 0 <= idx <= len(self.lines):
                        new_line = input(f" Wstaw przed linią {idx+1}: ")
                        self.lines.insert(idx, new_line)
                    else:
                        print(f" Błąd: Indeks poza zakresem.")
                except (ValueError, IndexError):
                    print(" Błąd składni. Prawidłowe użycie: :i <numer_linii>")
            else:
                self.lines.append(cmd)
