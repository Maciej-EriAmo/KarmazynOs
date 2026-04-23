#!/usr/bin/env python3
"""
shell.py — Karmazyn Shell (KSH) v1.0.2
=====================================
Interaktywna powłoka dla KarmazynOS v1.0.0.
"""

import sys
import os
import readline
from typing import List

try:
    from karmazyn import KarmazynOS, VERSION as KARM_VERSION
except ImportError:
    print("Błąd: nie znaleziono modułu 'karmazyn.py' w bieżącym katalogu.")
    sys.exit(1)


class KarmazynShell:
    def __init__(self):
        self.k = KarmazynOS()
        self.last_label: str | None = None
        self.history_file = os.path.expanduser("~/.karmazyn_history")
        self._init_readline()

    def _init_readline(self):
        try:
            readline.read_history_file(self.history_file)
        except FileNotFoundError:
            pass
        readline.set_history_length(2000)

    def save_history(self):
        try:
            readline.write_history_file(self.history_file)
        except Exception:
            pass

    def _is_float(self, s: str) -> bool:
        try:
            float(s)
            return True
        except ValueError:
            return False

    def print_help(self, cmd: str | None = None):
        help_text = {
            "write": "write <tekst> – zapisuje nowy atom do Φ",
            "recall": "recall <zapytanie> [k] – wyszukaj w pamięci roboczej i bąblach",
            "consolidate": "consolidate <etykieta> – przenieś atom do pamięci trwałej (bąbel)",
            "reactivate": "reactivate <etykieta> – przywróć bąbel do Φ",
            "revoke": "revoke <etykieta> – unieważnij bąbel (Warp Oblivion)",
            "decay": "decay <etykieta> <rate> – ustaw tempo rozpadu",
            "refresh": "refresh <etykieta> – odśwież bąbel (zresetuj decay)",
            "idea": "idea <temat> <etykieta1> [etykieta2 ...] – utwórz hologram/ideę",
            "ideas": "ideas – lista wszystkich idei",
            "gen": "gen <id_idei> <prompt> [temp] – wygeneruj atom z idei",
            "spawn": "spawn <id_idei> <prompt> [--consolidate] – wygeneruj + opcjonalnie skonsoliduj",
            "rehydrate": "rehydrate <id_idei> – odtwórz przybliżone atomy z idei",
            "stats": "stats – wyświetl statystyki systemu",
            "step": "step [n] – przesuń czas o n epok",
            "gc": "gc – wymuś garbage collection revoked bąbli",
            "run": "run <plik.karm> – uruchom skrypt",
            "exit": "exit / quit – wyjdź z powłoki"
        }

        if cmd and cmd in help_text:
            print(f"{cmd} — {help_text[cmd]}")
        else:
            print("Karmazyn Shell v1.0.2 — dostępne komendy:\n")
            for c in sorted(help_text.keys()):
                desc = help_text[c].split('–')[0].strip() if '–' in help_text[c] else help_text[c]
                print(f"  {c:<12}  {desc}")
            print("\nUżyj 'help <komenda>' po więcej szczegółów.")
            print("Zmienna $LAST zawiera etykietę ostatniego utworzonego elementu.")

    def run_script(self, filename: str):
        if not os.path.exists(filename):
            print(f"Błąd: plik '{filename}' nie istnieje.")
            return

        try:
            with open(filename, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f, 1):
                    line = line.strip()
                    if line and not line.startswith('#'):
                        print(f"ksh> {line}")
                        self.execute(line)
        except Exception as e:
            print(f"Błąd podczas wykonywania skryptu (linia {i}): {e}")

    def execute(self, cmdline: str):
        if not cmdline.strip():
            return

        # Zastąp $LAST
        cmdline = cmdline.replace("$LAST", self.last_label or "")
        parts: List[str] = cmdline.split()
        cmd = parts[0].lower()
        args = parts[1:]

        try:
            if cmd == "write":
                if not args:
                    print("Użycie: write <tekst>")
                    return
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
                for i, r in enumerate(res, 1):
                    line = f"{i}. [{r['layer']}] {r['label'][:35]:35} (score={r['score']:.3f})"
                    if r.get('layer') == 'bubble' and 'liveliness' in r:
                        line += f"  liv={r['liveliness']:.2f}"
                    print(line)

            elif cmd == "consolidate":
                if not args:
                    print("Użycie: consolidate <etykieta>")
                    return
                label = args[0]
                bid = self.k.consolidate(label)
                if bid:
                    self.last_label = bid
                    print(f"[KONSOLIDACJA] '{label}' → {bid}")

            elif cmd == "reactivate":
                if not args:
                    print("Użycie: reactivate <etykieta>")
                    return
                new_label = self.k.reactivate_bubble(args[0])
                if new_label:
                    self.last_label = new_label
                    print(f"[REAKTYWACJA] '{args[0]}' → {new_label}")

            elif cmd == "revoke":
                if not args:
                    print("Użycie: revoke <etykieta>")
                    return
                if self.k.revoke_bubble(args[0]):
                    print(f"[REVOKE] '{args[0]}' → Warp Oblivion")

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
                    print(f"Oznaczono '{args[0]}' do rozpadu (rate={rate})")

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
                    print(f"[IDEA] Utworzono '{hid}' z {len(labels)} bąbli.")
                else:
                    print("Nie udało się utworzyć idei — sprawdź czy podane bąble istnieją.")

            elif cmd == "ideas":
                if not self.k.holograms:
                    print("Brak zapisanych idei.")
                    return
                epoch = self.k.phi.epoch
                for hid, h in self.k.holograms.items():
                    liv = h.liveliness(epoch)
                    print(f"{hid:<40} | {h.topic} | bąble:{len(h.bubble_labels)} | liv:{liv:.3f}")

            elif cmd == "gen":
                if len(args) < 2:
                    print("Użycie: gen <id_idei> <prompt> [temperatura]")
                    return
                hid = args[0]
                temp = 0.3
                if len(args) > 1 and self._is_float(args[-1]):
                    temp = float(args[-1])
                    prompt = " ".join(args[1:-1])
                else:
                    prompt = " ".join(args[1:])
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
                consolidate = "--consolidate" in args
                prompt_parts = [a for a in args[1:] if a != "--consolidate"]
                prompt = " ".join(prompt_parts)
                vec = self.k.generate_from_idea(hid, prompt, temperature=0.4)
                if vec is not None:
                    label = self.k.phi.add_vector(vec, label=f"spawn_{hid}_{self.k.phi.epoch}")
                    self.last_label = label
                    if consolidate:
                        bid = self.k.consolidate(label)
                        print(f"Utworzono i skonsolidowano bąbel: {label}")
                    else:
                        print(f"Utworzono atom Φ: {label}")
                else:
                    print("Nie znaleziono idei.")

            elif cmd == "rehydrate":
                if not args:
                    print("Użycie: rehydrate <id_idei>")
                    return
                labels = self.k.rehydrate_hologram(args[0])
                if labels:
                    shown = ", ".join(labels[:6])
                    more = f" +{len(labels)-6}" if len(labels) > 6 else ""
                    print(f"Odtworzono atomy: {shown}{more}")
                    self.last_label = labels[0]
                else:
                    print("Nie udało się odtworzyć atomów z tej idei.")

            elif cmd == "stats":
                s = self.k.stats()
                print(f"KarmazynOS v{KARM_VERSION}  |  Epoka: {s['epoch']}")
                print(f"Temperatura Φ: {s['temperature']:.2f}  |  T_vacuum: {s['t_vacuum']:.4f}")
                print(f"Atomy Φ: {s['atoms_phi']}  |  Bąble: {s['bubbles']} (rozpadające się: {s['bubbles_decaying']})")
                print(f"Unieważnione: {s['bubbles_revoked']}  |  Idee: {s['holograms']}")
                print(f"Bias bąbli: {s['bubble_bias']:.3f}")

            elif cmd == "step":
                n = int(args[0]) if args and args[0].isdigit() else 1
                self.k.step(n)
                print(f"Wykonano {n} kroków. Aktualna epoka: {self.k.phi.epoch}")

            elif cmd == "gc":
                removed = self.k.cleanup_revoked()
                print(f"[GC] Usunięto {removed} unieważnionych bąbli.")

            elif cmd == "run":
                if not args:
                    print("Użycie: run <plik.karm>")
                    return
                self.run_script(args[0])

            elif cmd in ("exit", "quit"):
                self.save_history()
                print("Do zobaczenia w następnej epoce.")
                sys.exit(0)

            elif cmd == "help":
                self.print_help(args[0] if args else None)

            else:
                print(f"Nieznana komenda: '{cmd}'. Wpisz 'help' aby zobaczyć listę.")

        except Exception as e:
            print(f"Błąd wykonania: {e}")

    def run(self):
        print(f"\nKarmazyn Shell v1.0.2 | KarmazynOS v{KARM_VERSION}")
        print("Wpisz 'help' aby zobaczyć komendy, 'exit' aby wyjść.\n")
        while True:
            try:
                cmdline = input("ksh> ").strip()
                self.execute(cmdline)
            except KeyboardInterrupt:
                print("\nUżyj 'exit' aby opuścić powłokę.")
                continue
            except EOFError:
                print("\nexit")
                break
        self.save_history()


if __name__ == "__main__":
    shell = KarmazynShell()
    shell.run()