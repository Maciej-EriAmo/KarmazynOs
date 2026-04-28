#!/usr/bin/env python3
"""
KarmazynOS Bubble Editor (bedit) v3.0.0
Zintegrowany z jądrem KarmazynOS.
Korzysta z: karmazyn.py, bubblefs.py, soul_store.py, hss_demo.py
Uruchom: python bedit.py
"""

import cmd
import os
import sys
import time
import json
import hashlib
import uuid
from typing import Dict, List, Optional, Set, Any
from pathlib import Path
from datetime import datetime

# ============================================================
# IMPORTY Z KARMAZYNOS
# ============================================================

try:
    # Jądro termodynamiczne
    from karmazyn import (
        ThermodynamicKernel, 
        Atom, 
        Prism, 
        Hologram,
        VACUUM_ENERGY,
        DECAY_RATE
    )
    KARMAZYN_LOADED = True
except ImportError:
    print("⚠️ karmazyn.py nie znaleziony - używam trybu standalone")
    KARMAZYN_LOADED = False

try:
    # BubbleFS - natywny system bąbli
    from bubblefs import BubbleFS, Bubble as NativeBubble
    BUBBLEFS_LOADED = True
except ImportError:
    print("⚠️ bubblefs.py nie znaleziony - używam własnej implementacji")
    BUBBLEFS_LOADED = False

try:
    # Soul Store - persystencja
    from soul_store import SoulStore
    SOUL_LOADED = True
except ImportError:
    print("⚠️ soul_store.py nie znaleziony")
    SOUL_LOADED = False

try:
    # HSS - Holographic Session Spaces
    from hss_demo import HSSDaemon, SessionSpace
    HSS_LOADED = True
except ImportError:
    print("⚠️ hss_demo.py nie znaleziony")
    HSS_LOADED = False

# ============================================================
# KONFIGURACJA (zgodna z KarmazynOS)
# ============================================================

if KARMAZYN_LOADED:
    # Użyj stałych z jądra
    VACUUM = VACUUM_ENERGY
    LAMBDA = DECAY_RATE
else:
    VACUUM = 0.05
    LAMBDA = 0.02

DECAY_THRESHOLD = 0.1
MAX_ATOMS_PER_BUBBLE = 200
REFRESH_STRENGTH = 0.15
DEFAULT_PRISM = "CORE"

# ============================================================
# INTEGRACJA Z KARMAZYNOS
# ============================================================

class KarmazynIntegration:
    """
    Warstwa integracyjna między BubbleEditor a KarmazynOS.
    Jeśli komponenty KarmazynOS są dostępne, używa ich.
    Jeśli nie - używa własnych implementacji.
    """
    
    def __init__(self, workspace: str = ".bubbles"):
        self.workspace = Path(workspace)
        self.workspace.mkdir(exist_ok=True)
        
        # Inicjalizuj komponenty KarmazynOS
        self.kernel = None
        self.bubblefs = None
        self.soul_store = None
        self.hss_daemon = None
        self.session = None
        
        if KARMAZYN_LOADED:
            self.kernel = ThermodynamicKernel()
            print("🧠 Jądro termodynamiczne załadowane")
        
        if BUBBLEFS_LOADED:
            self.bubblefs = BubbleFS(str(self.workspace))
            print("🫧 BubbleFS załadowany")
        
        if SOUL_LOADED:
            self.soul_store = SoulStore(str(self.workspace / "souls"))
            print("💾 Soul Store załadowany")
        
        if HSS_LOADED:
            self.hss_daemon = HSSDaemon()
            self.session = self.hss_daemon.create_session("bedit_session")
            print("🔐 HSS Session załadowana")
        
        # Lokalne bąble (jeśli BubbleFS nie działa)
        self._local_bubbles: Dict[str, Any] = {}
        self._load_local_bubbles()
    
    def _load_local_bubbles(self):
        """Ładuje bąble z plików .bubble (fallback)"""
        for fp in self.workspace.glob("*.bubble"):
            try:
                with open(fp, 'r') as f:
                    data = json.load(f)
                self._local_bubbles[data['bubble']['id']] = data
            except:
                pass
    
    def create_bubble(self, name: str, bubble_type: str = "document") -> str:
        """Tworzy nowy bąbel używając natywnego BubbleFS lub fallbacku"""
        if self.bubblefs:
            bubble = self.bubblefs.create_bubble(name, bubble_type)
            return bubble.id
        else:
            # Fallback: własna implementacja
            bubble_id = f"bubble_{int(time.time())}_{hashlib.md5(name.encode()).hexdigest()[:8]}"
            bubble_data = {
                'bubble': {
                    'id': bubble_id,
                    'name': name,
                    'created_at': time.time(),
                    'manifest': {
                        'version': '3.0.0',
                        'type': bubble_type,
                        'prism_default': DEFAULT_PRISM,
                        'tags': [],
                        'description': ''
                    }
                },
                'atoms': []
            }
            self._local_bubbles[bubble_id] = bubble_data
            return bubble_id
    
    def add_atom_to_bubble(self, bubble_id: str, content: str) -> Optional[str]:
        """Dodaje atom do bąbla używając jądra termodynamicznego"""
        atom_id = str(uuid.uuid4())[:12]
        
        if self.kernel:
            # Użyj natywnego atomu KarmazynOS
            atom = self.kernel.create_atom(
                embedding=content[:64],
                semantic={"content": content, "type": "text"},
                energy=1.0
            )
            atom_id = atom.id
            
            if self.bubblefs:
                self.bubblefs.add_atom_to_bubble(bubble_id, atom)
            else:
                # Fallback
                if bubble_id in self._local_bubbles:
                    self._local_bubbles[bubble_id]['atoms'].append({
                        'id': atom_id,
                        'content': content,
                        'type': 'text',
                        'energy': 1.0,
                        'created_at': time.time(),
                        'metadata': {'tags': [], 'links': []}
                    })
        else:
            # Fallback: prosty atom
            if bubble_id in self._local_bubbles:
                self._local_bubbles[bubble_id]['atoms'].append({
                    'id': atom_id,
                    'content': content,
                    'type': 'text',
                    'energy': 1.0,
                    'created_at': time.time(),
                    'metadata': {'tags': [], 'links': []}
                })
        
        return atom_id
    
    def get_bubble_content(self, bubble_id: str, prism: str = "CORE") -> str:
        """Pobiera zawartość bąbla przez pryzmat"""
        if self.bubblefs:
            bubble = self.bubblefs.get_bubble(bubble_id)
            if bubble:
                return bubble.assemble_content(prism)
        else:
            if bubble_id in self._local_bubbles:
                atoms = self._local_bubbles[bubble_id].get('atoms', [])
                if prism == "CORE":
                    return '\n'.join(a['content'] for a in atoms)
                elif prism == "IN":
                    return ' | '.join(
                        f"[E:{a.get('energy', 0):.2f}] {a['content'][:80]}"
                        for a in atoms
                    )
                elif prism == "OUT":
                    return ' | '.join(f"[atom:{a['id']}]" for a in atoms)
        return ""
    
    def get_active_atoms(self, bubble_id: str) -> List[Dict]:
        """Zwraca aktywne atomy z bąbla"""
        if self.bubblefs:
            bubble = self.bubblefs.get_bubble(bubble_id)
            if bubble:
                return [
                    {
                        'id': a.id,
                        'content': a.content,
                        'energy': a.get_stability(),
                        'metadata': a.metadata
                    }
                    for a in bubble.get_active_atoms()
                ]
        else:
            if bubble_id in self._local_bubbles:
                return self._local_bubbles[bubble_id].get('atoms', [])
        return []
    
    def refresh_bubble(self, bubble_id: str) -> int:
        """Odświeża energię atomów w bąblu"""
        count = 0
        if self.bubblefs:
            bubble = self.bubblefs.get_bubble(bubble_id)
            if bubble:
                for atom in bubble.get_active_atoms():
                    atom.refresh()
                    count += 1
        else:
            if bubble_id in self._local_bubbles:
                for atom in self._local_bubbles[bubble_id].get('atoms', []):
                    atom['energy'] = min(1.0, atom.get('energy', 0) + REFRESH_STRENGTH)
                    count += 1
        return count
    
    def list_bubbles(self) -> List[Dict]:
        """Lista wszystkich bąbli"""
        bubbles = []
        if self.bubblefs:
            for b in self.bubblefs.list_bubbles():
                bubbles.append({
                    'id': b.id,
                    'name': b.name,
                    'active_atoms': len(b.get_active_atoms()),
                    'created_at': b.created_at
                })
        else:
            for bid, data in self._local_bubbles.items():
                bubbles.append({
                    'id': bid,
                    'name': data['bubble']['name'],
                    'active_atoms': len(data.get('atoms', [])),
                    'created_at': data['bubble']['created_at']
                })
        return sorted(bubbles, key=lambda x: x['created_at'], reverse=True)
    
    def search(self, query: str) -> List[Dict]:
        """Wyszukuje w bąblach"""
        q = query.lower()
        results = []
        for bubble in self.list_bubbles():
            content = self.get_bubble_content(bubble['id'], "CORE")
            if q in bubble['name'].lower() or q in content.lower():
                results.append(bubble)
        return results
    
    def save(self):
        """Zapisuje wszystkie zmiany"""
        if self.bubblefs:
            self.bubblefs.save_all()
        else:
            for bid, data in self._local_bubbles.items():
                name = data['bubble']['name'].replace(' ', '_')
                filepath = self.workspace / f"{name}.bubble"
                with open(filepath, 'w') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
        
        if self.soul_store:
            self.soul_store.save_all()
        
        if self.hss_daemon and self.session:
            self.hss_daemon.close_session(self.session.id)

# ============================================================
# PRYZMATY (zgodne z karmazyn.py)
# ============================================================

PRISMS = {
    'CORE': {'name': 'Rdzeń', 'desc': 'Pełna treść', 'icon': '🔮'},
    'IN':   {'name': 'Wewnętrzny', 'desc': 'Introspekcja', 'icon': '🔍'},
    'OUT':  {'name': 'Zewnętrzny', 'desc': 'Sygnatury', 'icon': '🌫️'}
}

# ============================================================
# GŁÓWNY EDYTOR
# ============================================================

class BubbleEditor(cmd.Cmd):
    """
    KarmazynOS Bubble Editor v3.0.0
    Zintegrowany edytor bąbli pracujący na jądrze termodynamicznym.
    """
    
    intro = """
╔══════════════════════════════════════════════════════════════╗
║     KARMAZYNOS BUBBLE EDITOR v3.0.0                         ║
║     Zintegrowany z jądrem termodynamicznym                  ║
║     "System nie przechowuje — system utrzymuje przy życiu"  ║
╚══════════════════════════════════════════════════════════════╝
"""
    prompt = '\033[96m[karmazyn]\033[0m → '
    
    def __init__(self):
        super().__init__()
        self.integration = KarmazynIntegration()
        self.current_bubble_id: Optional[str] = None
        self.current_bubble_name: Optional[str] = None
        self.current_prism = DEFAULT_PRISM
        
        bubbles = self.integration.list_bubbles()
        print(f"✨ {len(bubbles)} bąbli w przestrzeni")
        if self.integration.kernel:
            print(f"🧠 Jądro: KarmazynOS Thermodynamic Kernel")
        if self.integration.bubblefs:
            print(f"🫧 Storage: BubbleFS")
        if self.integration.hss_daemon:
            print(f"🔐 Sesja: HSS v2.6.0")
        print()
    
    def _read_multiline_input(self, prompt_prefix: str) -> Optional[List[str]]:
        """Czyta wieloliniowy input"""
        print(f"\n📝 {prompt_prefix}")
        print("   ↵ Pusta linia = nowa linia")
        print("   '..' = KONIEC | '!cancel' = ANULUJ\n")
        
        lines = []
        num = 1
        
        while True:
            try:
                raw_line = input(f"  {num:03d} │ ")
            except KeyboardInterrupt:
                print("\n⚠️ Anulowano (Ctrl+C)")
                return None
            except EOFError:
                print("\n⚠️ Anulowano (EOF)")
                return None
            
            stripped = raw_line.strip()
            
            if stripped == '..':
                if not lines:
                    print("❌ Nie można zapisać pustego tekstu")
                    continue
                return lines
            
            if stripped.lower() in ('!cancel', '!quit', '!q'):
                print("❌ Anulowano")
                return None
            
            lines.append(raw_line)
            num += 1
    
    def do_create(self, arg):
        """Stwórz nowy bąbel: create <nazwa>"""
        if not arg:
            print("❌ create <nazwa>")
            return
        
        bubble_id = self.integration.create_bubble(arg)
        self.current_bubble_id = bubble_id
        self.current_bubble_name = arg
        
        print(f"🫧 Stworzono bąbel: {arg}")
        print(f"   ID: {bubble_id}")
        print(f"   Użyj 'write' by dodać atomy")
    
    def do_open(self, arg):
        """Otwórz bąbel: open <nazwa>"""
        if not arg:
            print("❌ open <nazwa>")
            return
        
        for b in self.integration.list_bubbles():
            if arg.lower() in b['name'].lower():
                self.current_bubble_id = b['id']
                self.current_bubble_name = b['name']
                print(f"📂 Otwarto: {b['name']}")
                self.do_view('')
                return
        
        print(f"❌ Nie znaleziono: {arg}")
    
    def do_write(self, arg):
        """Dodaj tekst do bąbla (wieloliniowy)"""
        if not self.current_bubble_id:
            print("❌ Najpierw otwórz lub stwórz bąbel")
            return
        
        lines = self._read_multiline_input(
            f"Piszesz w: {self.current_bubble_name}"
        )
        
        if lines is None:
            return
        
        content = '\n'.join(lines)
        atom_id = self.integration.add_atom_to_bubble(
            self.current_bubble_id, 
            content
        )
        
        if atom_id:
            print(f"\n✅ Dodano atom {atom_id}")
            print(f"   {len(lines)} linii, {len(content)} znaków")
        else:
            print("❌ Błąd dodawania atomu")
    
    def do_append(self, arg):
        """Szybko dodaj linię: append <tekst>"""
        if not self.current_bubble_id:
            print("❌ Najpierw otwórz bąbel")
            return
        if not arg:
            print("❌ append <tekst>")
            return
        
        atom_id = self.integration.add_atom_to_bubble(
            self.current_bubble_id,
            arg
        )
        print(f"✅ Dodano: \"{arg[:60]}{'...' if len(arg)>60 else ''}\"")
    
    def do_view(self, arg):
        """Zobacz zawartość: view [CORE|IN|OUT]"""
        if not self.current_bubble_id:
            print("❌ Brak otwartego bąbla")
            return
        
        prism = arg.upper() if arg and arg.upper() in PRISMS else self.current_prism
        content = self.integration.get_bubble_content(
            self.current_bubble_id, 
            prism
        )
        atoms = self.integration.get_active_atoms(self.current_bubble_id)
        
        # Oblicz energię
        if atoms:
            energies = [a['energy'] for a in atoms]
            avg_energy = sum(energies) / len(energies)
            bar_len = 20
            filled = int(bar_len * min(1.0, avg_energy))
            bar = '█' * filled + '░' * (bar_len - filled)
            energy_str = f"[{bar}] {avg_energy:.2f}"
        else:
            energy_str = "(pusty)"
        
        print(f"\n{'='*50}")
        print(f"🫧 {self.current_bubble_name} | {len(atoms)} atomów")
        print(f"   Pryzmat: {prism} | Energia: {energy_str}")
        print(f"{'='*50}")
        
        if content:
            print(content)
        else:
            print("(pusty bąbel - użyj 'write' lub 'append')")
        
        print(f"{'='*50}\n")
    
    def do_prism(self, arg):
        """Zmień pryzmat: prism <CORE|IN|OUT>"""
        if arg.upper() in PRISMS:
            self.current_prism = arg.upper()
            print(f"🔮 Pryzmat: {arg.upper()}")
            if self.current_bubble_id:
                self.do_view('')
        else:
            print(f"Dostępne: {', '.join(PRISMS.keys())}")
    
    def do_list(self, arg):
        """Lista wszystkich bąbli"""
        bubbles = self.integration.list_bubbles()
        print(f"\n🫧 BĄBLE W PRZESTRZENI ({len(bubbles)}):")
        print('-' * 50)
        for b in bubbles:
            marker = '→' if self.current_bubble_id == b['id'] else ' '
            print(f"{marker} {b['name']:30s} | atomów: {b['active_atoms']}")
        print('-' * 50 + '\n')
    
    def do_refresh(self, arg):
        """Odśwież energię atomów"""
        if not self.current_bubble_id:
            print("❌ Brak otwartego bąbla")
            return
        
        count = self.integration.refresh_bubble(self.current_bubble_id)
        print(f"⚡ Odświeżono {count} atomów")
    
    def do_search(self, arg):
        """Szukaj: search <słowo>"""
        if not arg:
            print("❌ search <słowo>")
            return
        
        results = self.integration.search(arg)
        if results:
            print(f"\n🔍 Znaleziono {len(results)} bąbli:")
            for b in results:
                print(f"   🫧 {b['name']} ({b['active_atoms']} atomów)")
        else:
            print(f"🔍 Brak wyników dla: {arg}")
    
    def do_info(self, arg):
        """Szczegóły bąbla"""
        if not self.current_bubble_id:
            print("❌ Brak otwartego bąbla")
            return
        
        atoms = self.integration.get_active_atoms(self.current_bubble_id)
        print(f"\n{'='*50}")
        print(f"🫧 {self.current_bubble_name}")
        print(f"ID: {self.current_bubble_id}")
        print(f"Atomy: {len(atoms)}")
        
        if atoms:
            print(f"\n📊 ATOMY:")
            print('-' * 40)
            for i, atom in enumerate(atoms, 1):
                energy = atom['energy']
                bar = '█' * int(15 * energy) + '░' * (15 - int(15 * energy))
                preview = atom['content'][:50].replace('\n', '↵')
                print(f"\n{i}. [{atom['id']}] [{bar}] {energy:.2f}")
                print(f"   {preview}...")
        
        print(f"\n{'='*50}")
    
    def do_save(self, arg):
        """Zapisz ręcznie"""
        self.integration.save()
        print("💾 Wszystkie bąble zapisane")
    
    def do_quit(self, arg):
        """Wyjdź"""
        self.integration.save()
        bubbles = self.integration.list_bubbles()
        print(f"\n👋 Przestrzeń zamknięta ({len(bubbles)} bąbli)")
        if self.integration.kernel:
            print("🧠 Jądro termodynamiczne zatrzymane")
        print()
        return True
    
    def do_exit(self, arg):
        return self.do_quit(arg)
    
    def do_help(self, arg):
        """Pomoc"""
        print("""
╔══════════════════════════════════════════════════════════╗
║     KARMAZYNOS BUBBLE EDITOR - KOMENDY                   ║
╠══════════════════════════════════════════════════════════╣
║                                                        ║
║  📝 create <nazwa>  - stwórz nowy bąbel                ║
║  📂 open <nazwa>    - otwórz bąbel                     ║
║  ✍️  write          - dodaj tekst (wieloliniowy)       ║
║  📎 append <tekst>  - szybka linia                     ║
║  👁️  view [CORE|IN|OUT] - zobacz zawartość           ║
║  🔍 search <słowo>  - szukaj                           ║
║  📋 list            - lista bąbli                      ║
║  ℹ️  info           - szczegóły                        ║
║  ⚡ refresh         - odśwież energię                   ║
║  💾 save            - zapisz                            ║
║  🚪 quit            - wyjdź                             ║
║                                                        ║
║  Zasada: Bąbel = TRWAŁY, Atomy = NIETRWAŁE             ║
║  Atomy rozpadają się przy energii < 0.10               ║
║  Użyj 'refresh' by podtrzymać życie atomów             ║
╚══════════════════════════════════════════════════════════╝
""")


def main():
    """Uruchom edytor"""
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  KarmazynOS Bubble Editor v3.0.0                        ║")
    print("║  Zintegrowany z jądrem termodynamicznym                ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()
    
    editor = BubbleEditor()
    
    try:
        editor.cmdloop()
    except KeyboardInterrupt:
        print("\n\n⚠️ Zamykanie...")
        editor.integration.save()
        print("👋 Przestrzeń zamknięta\n")
    except Exception as e:
        print(f"\n❌ Błąd: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
# Brakująca metoda
def _save_all_patch(self):
    import json
    for bid, data in self._local_bubbles.items():
        name = data['bubble']['name'].replace(' ', '_')
        filepath = self.workspace / f"{name}.bubble"
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

KarmazynIntegration.save_all = _save_all_patch
