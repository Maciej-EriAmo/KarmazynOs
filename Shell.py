#!/usr/bin/env python3
"""
shell.py — Karmazyn Shell (KSH) v1.0
=====================================
Interaktywna powłoka dla KarmazynOS v1.0.0.
Umożliwia operowanie na ideach, generowanie nowych bytów i zarządzanie pamięcią.
"""

import sys
import os
import readline
from typing import Optional
from karmazyn import KarmazynOS, VERSION as KARM_VERSION

class KarmazynShell:
    def __init__(self):
        self.k = KarmazynOS()
        self.last_label = None
        self.history_file = os.path.expanduser("~/.karmazyn_history")
        self._init_readline()

    def _init_readline(self):
        try:
            readline.read_history_file(self.history_file)
        except FileNotFoundError:
            pass
        readline.set_history_length(1000)

    def save_history(self):
        try:
            readline.write_history_file(self.history_file)
        except Exception:
            pass

    def print_help(self, cmd: str = None):
        help_text = {
            "write": "write <tekst> – zapisuje nowy atom Φ, zwraca etykietę ($LAST)",
            "recall": "recall <zapytanie> [k] – przypomnij z Φ i bąbli",
            "consolidate": "consolidate <etykieta> – przenieś atom do bąbla",
            "reactivate": "reactivate <etykieta> – przywróć bąbel do Φ",
            "revoke": "revoke <etykieta> – unieważnij bąbel (Warp Oblivion)",
            "decay": "decay <etykieta> <rate> – ustaw tempo rozpadu bąbla (np. 0.01)",
            "refresh": "refresh <etykieta> – resetuj rozpad bąbla",
            "idea": "idea <temat> <etykieta1> [etykieta2...] – utwórz ideę (hologram)",
            "ideas": "ideas – lista zapisanych idei",
            "gen": "gen <id_idei> <prompt> [temperatura] – wygeneruj wektor i utwórz atom Φ",
            "spawn": "spawn <id_idei> <prompt> [--consolidate] – generuj i opcjonalnie konsoliduj",
            "rehydrate": "rehydrate <id_idei> – odtwórz atomy z idei",
            "stats": "stats – statystyki systemu",
            "step": "step [n] – przesuń czas o n epok",
            "gc": "gc – wymuś czyszczenie revoked bąbli",
            "run": "run <plik.karm> – wykonaj skrypt",
            "exit/quit": "exit – opuść powłokę"
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
        if not os.path.exists(filename):
            print(f"Błąd: plik '{filename}' nie istnieje.")
            return
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    print(f"ksh> {line}")
                    self.execute(line)

    def execute(self, cmdline: str):
        if not cmdline:
            return
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

            elif cmd == "decay":
                if len(args) < 2:
                    print("Użycie: decay <etykieta> <rate>")
                    return
                try:
                    rate = float(args[1])
                except ValueError:
                    print("Rate musi być liczbą.")
                    return
                if self.k.mark_bubble_for_decay(args[0], rate):
                    print(f"Oznaczono bąbel '{args[0]}' do rozpadu z tempem {rate}.")

            elif cmd == "refresh":
                if not args:
                    print("Użycie: refresh <etykieta>")
                    return
                if self.k.refresh_bubble(args[0]):
                    print(f"Bąbel '{args[0]}' odświeżony.")

            elif cmd == "idea":
                if len(args) < 2:
                    print("Użycie: idea <temat> <etykieta1> [etykieta2...]")
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
                prompt = " ".join(args[1:])
                temp = 0.3
                # Sprawdź, czy ostatni token jest liczbą
                if args and args[-1].replace('.', '', 1).isdigit():
                    temp = float(args[-1])
                    prompt = " ".join(args[1:-1])
                vec = self.k.generate_from_idea(hid, prompt, temperature=temp)
                if vec is not None:
                    label = self.k.phi.add_vector(vec, label=f"gen_{hid}_{self.k.phi.epoch}")
                    self.last_label = label
                    print(f"Wygenerowano atom Φ: {label} (temp={temp})")
                else:
                    print("Nie znaleziono idei lub błąd generowania.")

            elif cmd == "spawn":
                if len(args) < 2:
                    print("Użycie: spawn <id_idei> <prompt> [--consolidate]")
                    return
                hid = args[0]
                prompt = " ".join(args[1:])
                consolidate = "--consolidate" in args
                if consolidate:
                    prompt = prompt.replace(" --consolidate", "")
                vec = self.k.generate_from_idea(hid, prompt, temperature=0.4)
                if vec is not None:
                    label = self.k.phi.add_vector(vec, label=f"spawn_{hid}_{self.k.phi.epoch}")
                    if consolidate:
                        self.k.consolidate(label)
                        print(f"Utworzono i skonsolidowano bąbel: {label}")
                    else:
                        print(f"Utworzono atom Φ: {label}")
                    self.last_label = label
                else:
                    print("Nie znaleziono idei.")

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


if __name__ == "__main__":
    shell = KarmazynShell()
    shell.run()