#!/usr/bin/env python3
"""
shell.py — KarmazynOS Shell (ksh) v1.3.0
=========================================
Zmiany v1.3.0:
  [nowe] /phi_id         – wyświetl Φ-ID bieżącego węzła
  [nowe] /crimson_nodes  – lista znanych węzłów z rejestru TOFU
  [nowe] /help           – zaktualizowana lista komend
"""

import sys
import os
import readline  # opcjonalne: historia poleceń

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from karmazyn import KarmazynOS
from crimson_network import CrimsonNetwork

VERSION = "1.3.0"


class KarmazynShell:
    def __init__(self):
        print(f"  ╔══════════════════════════════════════╗")
        print(f"  ║    KarmazynOS Shell (ksh) v{VERSION}    ║")
        print(f"  ╚══════════════════════════════════════╝")
        self.karmazyn = KarmazynOS()
        self.network: CrimsonNetwork | None = None
        self.running = True
        self._load_or_init()

    def _load_or_init(self):
        if os.path.isdir("./karmazyn_data"):
            ans = input("Wykryto zapisany stan. Wczytać? [T/n]: ").strip().lower()
            if ans != 'n':
                self.karmazyn.load("./karmazyn_data")
                return
        # Nowa sesja – inicjalizuj bąbel tożsamości
        print("Tworzenie nowej sesji Φ...")
        self.karmazyn._init_p2s_bubble()

    # ========================================================================
    #  KOMENDY PODSTAWOWE
    # ========================================================================

    def do_help(self, arg):
        """Wyświetla dostępne komendy."""
        print("""
  ┌─────────────── PODSTAWOWE ───────────────────────────────┐
  │ /write <tekst>         Zapisz atom do Φ                  │
  │ /recall <zapytanie>    Przypomnij atomy i bąble          │
  │ /consolidate <label>   Konsoliduj atom w bąbel           │
  │ /read_bubble <label>   Odczytaj bąbel                    │
  │ /reactivate <label>    Reaktywuj bąbel do Φ              │
  │ /step [n]              Wykonaj n kroków termodynamicznych │
  │ /stats                 Pokaż statystyki systemu          │
  │ /save                  Zapisz stan                       │
  │ /load                  Wczytaj stan                      │
  │ /evaluate <kontekst>   Oceń spójność kontekstu           │
  ├─────────────── TOŻSAMOŚĆ ────────────────────────────────┤
  │ /phi_id                Pokaż Φ-ID tego węzła             │
  ├─────────────── KARMAZYNOWY KOMUNIKATOR ──────────────────┤
  │ /crimson_listen <port> Nasłuchuj na połączenie           │
  │ /crimson_connect <h> <p> Połącz z węzłem                │
  │ /crimson_msg <tekst>   Wyślij wiadomość                  │
  │ /crimson_nodes         Lista znanych węzłów              │
  │ /crimson_close         Zamknij kanał                     │
  ├──────────────────────────────────────────────────────────┤
  │ /quit                  Wyjdź                             │
  └──────────────────────────────────────────────────────────┘
""")

    def do_write(self, arg):
        if not arg.strip():
            print("Użycie: /write <tekst>")
            return
        label = self.karmazyn.write(arg.strip())
        print(f"  [Φ] Zapisano atom: {label}")

    def do_recall(self, arg):
        if not arg.strip():
            print("Użycie: /recall <zapytanie>")
            return
        results = self.karmazyn.recall(arg.strip())
        if not results:
            print("  Brak wyników.")
            return
        for i, r in enumerate(results):
            print(f"  [{i+1}] {r['label'][:40]:40s} {r['layer']:6s} "
                  f"T={r.get('T', float('inf')):.2f} sim={r['sim']:.3f} "
                  f"score={r['score']:.3f}")

    def do_consolidate(self, arg):
        if not arg.strip():
            print("Użycie: /consolidate <label>")
            return
        bid = self.karmazyn.consolidate(arg.strip())
        if bid:
            print(f"  [bąbel] {bid}")

    def do_read_bubble(self, arg):
        if not arg.strip():
            print("Użycie: /read_bubble <label>")
            return
        content = self.karmazyn.read_bubble(arg.strip())
        if content:
            print(f"  [bąbel] {content[:200]}")
        else:
            print("  Nie znaleziono bąbla.")

    def do_reactivate(self, arg):
        if not arg.strip():
            print("Użycie: /reactivate <label>")
            return
        new_label = self.karmazyn.reactivate_bubble(arg.strip())
        if new_label:
            print(f"  [Φ] Reaktywowano jako: {new_label}")

    def do_step(self, arg):
        n = int(arg.strip() or "1")
        stats = self.karmazyn.step(n)
        print(f"  [krok] epoka={stats['epoch']} atomy={stats['atoms']} "
              f"T={stats['temperature']:.2f} bąble={stats['bubbles']}")

    def do_stats(self, arg):
        s = self.karmazyn.stats()
        print(f"  KarmazynOS v{s['version']}")
        print(f"  Φ-ID:         {s['phi_id']}")
        print(f"  Epoka:        {s['epoch']}")
        print(f"  Atomy Φ:      {s['atoms']}")
        print(f"  Temperatura:  {s['temperature']:.3f}")
        print(f"  T_vacuum:     {s['t_vacuum']:.4f} bit")
        print(f"  Bąble:        {s['bubbles']} (zanikające: {s['bubbles_decaying']}, "
              f"odwołane: {s['bubbles_revoked']})")
        print(f"  Hologramy:    {s['holograms']}")
        print(f"  Bubble bias:  {s['bubble_bias']:.3f}")

    def do_save(self, arg):
        self.karmazyn.save()

    def do_load(self, arg):
        self.karmazyn.load()

    def do_evaluate(self, arg):
        if not arg.strip():
            print("Użycie: /evaluate <kontekst>")
            return
        allow, score, reason = self.karmazyn.evaluate(arg.strip())
        status = "✓ SPÓJNY" if allow else "✗ NIESPÓJNY"
        print(f"  [{status}] {reason}")

    # ========================================================================
    #  KOMENDY TOŻSAMOŚCI
    # ========================================================================

    def do_phi_id(self, arg):
        """Wyświetla Φ-ID bieżącego węzła."""
        phi_id = self.karmazyn.get_phi_id()
        phi2_hex = self.karmazyn.phi.phi2_bytes().hex()
        print(f"  Φ-ID:      {phi_id}")
        print(f"  phi2_hex:  {phi2_hex[:32]}…")
        b = self.karmazyn.bubbles.get_by_label(self.karmazyn._P2S_BUBBLE_LABEL)
        if b:
            print(f"  Bąbel:     {b.id} (immortal={b.immortal})")

    # ========================================================================
    #  KOMENDY KARMAZYNOWEGO KOMUNIKATORA
    # ========================================================================

    def _ensure_network(self, port=9000):
        """Inicjalizuje CrimsonNetwork, jeśli jeszcze nie istnieje."""
        if not self.network:
            self.network = CrimsonNetwork(self.karmazyn, port)
            self.network.receive_callback = lambda msg: print(f"\n<Φ> {msg}")

    def do_crimson_listen(self, arg):
        port = int(arg.strip() or "9000")
        self._ensure_network(port)
        self.network.start_server()
        print(f"  [*] Nasłuchiwanie na porcie {port}")

    def do_crimson_connect(self, arg):
        parts = arg.strip().split()
        if not parts:
            print("Użycie: /crimson_connect <host> <port>")
            return
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 9001
        self._ensure_network(port)
        self.network.connect(host, port)

    def do_crimson_msg(self, arg):
        if not arg.strip():
            print("Użycie: /crimson_msg <tekst>")
            return
        if not self.network:
            print("  [!] Brak połączenia. Użyj /crimson_listen i /crimson_connect.")
            return
        self.network.send(arg.strip())

    def do_crimson_nodes(self, arg):
        """Wyświetla listę znanych węzłów z rejestru TOFU."""
        if not self.network:
            self._ensure_network()
        nodes = self.network.registry.list_nodes()
        if not nodes:
            print("  Brak znanych węzłów.")
            return
        print(f"  {'Φ-ID':34s} {'Nazwa':20s} {'Adres':22s} {'Ostatni kontakt'}")
        print(f"  {'-'*34} {'-'*20} {'-'*22} {'-'*19}")
        for n in nodes:
            print(f"  {n['phi_id']:34s} {n.get('name','?'):20s} "
                  f"{n.get('address','?'):22s} {n.get('last_seen','?')}")

    def do_crimson_close(self, arg):
        if self.network:
            self.network.close()
        else:
            print("  [!] Brak aktywnego połączenia.")

    def do_quit(self, arg):
        print("  [*] Zamykanie KarmazynOS...")
        self.karmazyn.save()
        self.running = False

    # ========================================================================
    #  PĘTLA GŁÓWNA
    # ========================================================================

    def run(self):
        while self.running:
            try:
                cmd = input("ksh> ").strip()
                if not cmd:
                    continue
                if cmd.startswith("/"):
                    parts = cmd[1:].split(maxsplit=1)
                    cmd_name = parts[0].lower()
                    cmd_arg = parts[1] if len(parts) > 1 else ""
                    method_name = f"do_{cmd_name}"
                    if hasattr(self, method_name):
                        getattr(self, method_name)(cmd_arg)
                    else:
                        print(f"  [!] Nieznana komenda: /{cmd_name}. Wpisz /help.")
                else:
                    # Jeśli nie zaczyna się od "/", traktuj jako /write
                    self.do_write(cmd)
            except KeyboardInterrupt:
                print("\n  [*] Przerwanie. Wpisz /quit, aby wyjść.")
            except Exception as e:
                print(f"  [!] Błąd: {e}")


if __name__ == "__main__":
    shell = KarmazynShell()
    shell.run()
