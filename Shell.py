#!/usr/bin/env python3
"""
shell.py — Karmazyn Shell (KSH) v1.0
=====================================
Interaktywna powłoka dla KarmazynOS (Thermodynamic Memory Kernel).

Komendy:
  write <tekst>               – zapisz nowy atom Φ
  recall <zapytanie> [k]      – przypomnij z pamięci (Φ + bąble)
  consolidate <etykieta>      – przenieś atom do bąbla (pamięć trwała)
  reactivate <etykieta>       – przywróć bąbel do Φ
  revoke <etykieta>           – unieważnij bąbel (Warp Oblivion)
  decay <etykieta> <rate>     – oznacz bąbel do rozpadu (rate 0.01 = 1%/epoka)
  refresh <etykieta>          – odśwież bąbel (reset decay)

  idea <temat> [lista etykiet] – utwórz hologram (ideę) z podanych bąbli
  ideas                        – lista zapisanych idei (hologramów)
  gen <id_idei> <prompt> [temp] – wygeneruj nowy wektor z idei
  rehydrate <id_idei>         – odtwórz atomy Φ z idei

  stats                       – statystyki systemu
  step [n]                    – przesuń czas o n epok (domyślnie 1)
  gc                          – wymuś czyszczenie revoked bąbli

  agent derive <nazwa> <zadanie> [prismy] – utwórz nowego agenta
  agent read <pid> <etykieta> [--bubble] – odczytaj przez agenta

  run <plik.karm>             – wykonaj skrypt powłoki
  help [komenda]              – pomoc
  exit / quit                 – wyjście

Zmienne środowiskowe:
  $LAST                        – etykieta ostatnio utworzonego atomu/bąbla

Przykład:
  > write "Python jest super"
  > recall "język programowania"
  > consolidate $LAST
  > idea "Python tips" $LAST
  > gen idea_123 "wydajność"
"""

import sys
import os
import readline  # historia i edycja linii (Unix)
from typing import List, Optional

from karmazyn import KarmazynOS, VERSION as KARM_VERSION

# ----------------------------------------------------------------------
# Karmazyn Shell
# ----------------------------------------------------------------------
class KarmazynShell:
    def __init__(self):
        self.k = KarmazynOS()
        self.last_label = None          # zmienna $LAST
        self.history_file = os.path.expanduser("~/.karmazyn_history")
        self._init_readline()

    def _init_readline(self):
        """Inicjalizacja readline z historią."""
        try:
            readline.read_history_file(self.history_file)
        except FileNotFoundError:
            pass
        readline.set_history_length(1000)

    def save_history(self):
        """Zapisuje historię przy wyjściu."""
        try:
            readline.write_history_file(self.history_file)
        except Exception:
            pass

    def print_help(self, cmd: str = None):
        """Wyświetla pomoc ogólną lub dla konkretnej komendy."""
        help_text = {
            "write": "write <tekst> – zapisuje nowy atom w Φ i zwraca etykietę (zapamiętaną w $LAST)",
            "recall": "recall <zapytanie> [k] – wyszukuje w Φ i bąblach, zwraca top k wyników (domyślnie 5)",
            "consolidate": "consolidate <etykieta> – przenosi atom Φ do bąbla (pamięć trwała)",
            "reactivate": "reactivate <etykieta> – przywraca bąbel do pamięci roboczej Φ",
            "revoke": "revoke <etykieta> – unieważnia bąbel (Warp Oblivion), dane stają się bełkotem",
            "decay": "decay <etykieta> <rate> – ustawia tempo rozpadu bąbla (np. 0.01 oznacza 1% na epokę)",
            "refresh": "refresh <etykieta> – resetuje rozpad bąbla, przywraca pełną żywotność",
            "idea": "idea <temat> <etykieta1> [etykieta2 ...] – tworzy hologram (ideę) z podanych bąbli",
            "ideas": "ideas – wyświetla listę wszystkich zapisanych idei (hologramów)",
            "gen": "gen <id_idei> <prompt> [temperatura] – generuje nowy wektor z idei na podstawie promptu",
            "rehydrate": "rehydrate <id_idei> – odtwarza atomy Φ ze wszystkich wektorów w idei",
            "stats": "stats – wyświetla statystyki: liczba atomów, bąbli, idei, temperatura, epoka",
            "step": "step [n] – przesuwa czas o n epok (domyślnie 1), powoduje stygnięcie Φ i rozpad bąbli",
            "gc": "gc – wymusza natychmiastowe usunięcie unieważnionych (revoked) bąbli",
            "agent": "agent derive <nazwa> <zadanie> [prismy] – tworzy agenta\n"
                     "agent read <pid> <etykieta> [--bubble] – odczytuje dane jako agent",
            "run": "run <plik.karm> – wykonuje polecenia z pliku skryptu",
            "exit/quit": "exit – opuszcza powłokę"
        }
        if cmd and cmd in help_text:
            print(help_text[cmd])
        else:
            print("Karmazyn Shell – dostępne komendy:")
            for c in sorted(help_text.keys()):
                print(f"  {c:<12} - {help_text[c].split('–')[0].strip()}")
            print("\nUżyj 'help <komenda>' aby uzyskać szczegóły.")
            print("Zmienna $LAST przechowuje etykietę ostatnio utworzonego elementu.")

    def run_script(self, filename: str):
        """Wykonuje polecenia z pliku .karm."""
        if not os.path.exists(filename):
            print(f"Błąd: plik '{filename}' nie istnieje.")
            return
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                print(f"ksh> {line}")
                self.execute(line)

    def execute(self, cmdline: str):
        """Parsuje i wykonuje pojedynczą komendę."""
        if not cmdline:
            return
        # Podstawienie zmiennej $LAST
        cmdline = cmdline.replace("$LAST", self.last_label or "")
        parts = cmdline.split()
        cmd = parts[0].lower()
        args = parts[1:]

        try:
            if cmd == "write":
                text = " ".join(args)
                label = self.k.write(text)
                self.last_label = label
                print(f"Zapisano: {label}")

            elif cmd == "recall":
                if not args:
                    print("Użycie: recall <zapytanie> [k]")
                    return
                k = 5
                if len(args) > 1 and args[-1].isdigit():
                    k = int(args[-1])
                    query = " ".join(args[:-1])
                else:
                    query = " ".join(args)
                res = self.k.recall(query, k=k)
                for i, r in enumerate(res):
                    print(f"{i+1}. [{r['layer']}] {r['label'][:30]} (score={r['score']:.3f})")

            elif cmd == "consolidate":
                if not args:
                    print("Użycie: consolidate <etykieta>")
                    return
                label = args[0]
                bid = self.k.consolidate(label)
                if bid:
                    self.last_label = label
                    print(f"Bąbel: {bid}")

            elif cmd == "reactivate":
                if not args:
                    print("Użycie: reactivate <etykieta>")
                    return
                new_label = self.k.reactivate_bubble(args[0])
                if new_label:
                    self.last_label = new_label

            elif cmd == "revoke":
                if not args:
                    print("Użycie: revoke <etykieta>")
                    return
                if self.k.revoke_bubble(args[0]):
                    print(f"Bąbel '{args[0]}' unieważniony.")
                else:
                    print("Nie znaleziono bąbla.")

            elif cmd == "decay":
                if len(args) < 2:
                    print("Użycie: decay <etykieta> <rate>")
                    return
                label = args[0]
                try:
                    rate = float(args[1])
                except ValueError:
                    print("Rate musi być liczbą.")
                    return
                if self.k.mark_bubble_for_decay(label, rate):
                    print(f"Oznaczono bąbel '{label}' do rozpadu z tempem {rate}.")
                else:
                    print("Nie znaleziono bąbla.")

            elif cmd == "refresh":
                if not args:
                    print("Użycie: refresh <etykieta>")
                    return
                if self.k.refresh_bubble(args[0]):
                    print(f"Bąbel '{args[0]}' odświeżony.")
                else:
                    print("Nie znaleziono bąbla.")

            elif cmd == "idea":
                if len(args) < 2:
                    print("Użycie: idea <temat> <etykieta1> [etykieta2 ...]")
                    return
                topic = args[0]
                labels = args[1:]
                hid = self.k.archive_bubbles_to_hologram(topic, labels)
                if hid:
                    self.last_label = hid
                    print(f"Idea utworzona: {hid}")

            elif cmd == "ideas":
                if not self.k.holograms:
                    print("Brak zapisanych idei.")
                else:
                    for hid, h in self.k.holograms.items():
                        print(f"{hid} | temat: {h.topic} | bąble: {len(h.bubble_labels)} | epoka: {h.epoch_created}")

            elif cmd == "gen":
                if len(args) < 2:
                    print("Użycie: gen <id_idei> <prompt> [temperatura]")
                    return
                hid = args[0]
                prompt = args[1] if len(args) > 1 else ""
                temp = 0.3
                if len(args) > 2:
                    try:
                        temp = float(args[2])
                    except ValueError:
                        pass
                vecs = self.k.recall_from_hologram(hid, prompt, temperature=temp, k=1)
                if vecs:
                    print(f"Wygenerowano wektor (pierwsze 8): {vecs[0][:8]}")
                else:
                    print("Nie znaleziono idei lub błąd generowania.")

            elif cmd == "rehydrate":
                if not args:
                    print("Użycie: rehydrate <id_idei>")
                    return
                labels = self.k.rehydrate_hologram(args[0])
                if labels:
                    print(f"Odtworzono atomy: {', '.join(labels)}")
                    if labels:
                        self.last_label = labels[0]

            elif cmd == "stats":
                s = self.k.stats()
                print(f"KarmazynOS v{KARM_VERSION}")
                print(f"Epoka: {s['epoch']} | Temperatura Φ: {s['temperature']:.2f} | T_vacuum: {s['t_vacuum']:.4f}")
                print(f"Atomy Φ: {s['atoms_phi']} | Bąble: {s['bubbles']} (w tym rozpadających się: {s['bubbles_decaying']})")
                print(f"Bąble unieważnione: {s['bubbles_revoked']} | Idee (hologramy): {s['holograms']}")
                print(f"Bias bąbli: {s['bubble_bias']:.3f}")

            elif cmd == "step":
                n = 1
                if args:
                    try:
                        n = int(args[0])
                    except ValueError:
                        pass
                self.k.step(n)
                print(f"Wykonano {n} kroków. Epoka: {self.k.phi.epoch}")

            elif cmd == "gc":
                removed = self.k.cleanup_revoked()
                print(f"Usunięto {removed} unieważnionych bąbli.")

            elif cmd == "agent":
                if not args:
                    print("Użycie: agent derive <nazwa> <zadanie> [prismy]")
                    print("       agent read <pid> <etykieta> [--bubble]")
                    return
                sub = args[0].lower()
                if sub == "derive":
                    if len(args) < 3:
                        print("Użycie: agent derive <nazwa> <zadanie> [prismy]")
                        return
                    name = args[1]
                    task = args[2]
                    prisms = args[3:] if len(args) > 3 else ["core"]
                    pid, s = self.k.derive_agent(name, task, prisms)
                    print(f"Agent utworzony: PID={pid}, klucz sesyjny (pierwsze 8): {s[:8]}")

                elif sub == "read":
                    if len(args) < 3:
                        print("Użycie: agent read <pid> <etykieta> [--bubble]")
                        return
                    try:
                        pid = int(args[1])
                    except ValueError:
                        print("PID musi być liczbą.")
                        return
                    label = args[2]
                    from_bubble = "--bubble" in args
                    # Potrzebujemy s_agent – w demo odtwarzamy go z rejestru (uproszczenie)
                    reg = self.k._reg.get(pid)
                    if not reg:
                        print(f"Agent PID={pid} nie istnieje.")
                        return
                    # W prawdziwym systemie s_agent byłby przechowywany; tutaj wywołujemy read_as_agent z s_agent=None,
                    # ale ono wymaga s_agent. Musimy go mieć. Alternatywnie: dodać metodę w KarmazynOS do pobrania s_agent.
                    # Dla uproszczenia zakładamy, że użytkownik nie używa tej komendy lub dodać przechowywanie s_agent.
                    print("Funkcja w budowie – wymaga przechowywania klucza agenta.")
                else:
                    print("Nieznana podkomenda agenta.")

            elif cmd == "run":
                if not args:
                    print("Użycie: run <plik.karm>")
                    return
                self.run_script(args[0])

            elif cmd in ("exit", "quit"):
                self.save_history()
                print("Do zobaczenia.")
                sys.exit(0)

            elif cmd == "help":
                self.print_help(args[0] if args else None)

            else:
                print(f"Nieznana komenda: {cmd}. Wpisz 'help' aby zobaczyć dostępne komendy.")

        except Exception as e:
            print(f"Błąd: {e}")

    def run(self):
        """Główna pętla powłoki."""
        print(f"Karmazyn Shell v1.0 | KarmazynOS v{KARM_VERSION}")
        print("Wpisz 'help' aby zobaczyć dostępne komendy, 'exit' aby wyjść.")
        while True:
            try:
                cmdline = input("ksh> ").strip()
            except KeyboardInterrupt:
                print("\nUżyj 'exit' aby opuścić.")
                continue
            except EOFError:
                print("\nexit")
                break
            self.execute(cmdline)
        self.save_history()


# ----------------------------------------------------------------------
if __name__ == "__main__":
    shell = KarmazynShell()
    shell.run()