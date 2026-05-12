#!/usr/bin/env python3
"""
KarmazynOS Bubble Editor (bedit) v3.0.2
Zintegrowany z jądrem KarmazynOS oraz opcjonalnymi modułami bubblefs i soul_store.
"""

import cmd
import os
import sys
import time
import json
import hashlib
import uuid
from typing import Dict, List, Optional, Any
from pathlib import Path

MAX_ATOMS_PER_BUBBLE = 200
REFRESH_STRENGTH = 0.15
DEFAULT_PRISM = "CORE"

# Próba importu modułów opcjonalnych
KARMAZYN_LOADED = False
BUBBLEFS_LOADED = False
SOUL_LOADED = False
HSS_LOADED = False

try:
    from karmazyn import KarmazynOS
    KARMAZYN_LOADED = True
except ImportError as e:
    print(f"⚠️ karmazyn.py – {e} – używam trybu standalone")

try:
    from bubblefs import export as bubblefs_export, import_ as bubblefs_import, inspect as bubblefs_inspect
    BUBBLEFS_LOADED = True
except ImportError as e:
    print(f"⚠️ bubblefs.py – {e} – eksport/import niedostępny")

try:
    import soul_store
    SOUL_LOADED = True
except ImportError as e:
    print(f"⚠️ soul_store.py – {e} – zapis/odczyt .soul niedostępny")

try:
    from hss_demo import HSSDaemon
    HSS_LOADED = True
except ImportError as e:
    print(f"⚠️ hss_demo.py – {e}")


class KarmazynIntegration:
    def __init__(self, workspace: str = ".bubbles"):
        self.workspace = Path(workspace)
        self.workspace.mkdir(exist_ok=True)

        self.kernel = None
        self.bubblefs_available = BUBBLEFS_LOADED
        self.soul_available = SOUL_LOADED
        self.hss_daemon = None
        self.session = None

        if KARMAZYN_LOADED:
            try:
                self.kernel = KarmazynOS()
                print("🧠 Jądro KarmazynOS załadowane")
            except Exception as e:
                print(f"⚠️ Błąd inicjalizacji KarmazynOS: {e}")

        if HSS_LOADED:
            try:
                self.hss_daemon = HSSDaemon()
                if hasattr(self.hss_daemon, 'create_session'):
                    self.session = self.hss_daemon.create_session("bedit_session")
                    print("🔐 HSS Session załadowana")
                else:
                    print("🔐 HSS Daemon dostępny (bez sesji)")
            except Exception as e:
                print(f"⚠️ Błąd HSS: {e}")

        self._local_bubbles: Dict[str, Any] = {}
        self._load_local_bubbles()

    def _load_local_bubbles(self):
        for fp in self.workspace.glob("*.bubble"):
            try:
                with open(fp, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._local_bubbles[data['bubble']['id']] = data
            except Exception:
                pass

    @staticmethod
    def _normalize_atom(atom_obj) -> Dict:
        if hasattr(atom_obj, 'get_stability'):
            energy = float(atom_obj.get_stability())
            content = getattr(atom_obj, 'content', '')
            atom_id = getattr(atom_obj, 'id', '')
            metadata = getattr(atom_obj, 'metadata', {})
            S = getattr(atom_obj, 'S', '')
            E = getattr(atom_obj, 'E', '')
        elif hasattr(atom_obj, 'energy'):
            energy = float(atom_obj.energy)
            content = getattr(atom_obj, 'content', '')
            atom_id = getattr(atom_obj, 'id', '')
            metadata = getattr(atom_obj, 'metadata', {})
            S = getattr(atom_obj, 'S', '')
            E = getattr(atom_obj, 'E', '')
        else:
            energy = float(atom_obj.get('energy', 0.0))
            content = atom_obj.get('content', '')
            atom_id = atom_obj.get('id', '')
            metadata = atom_obj.get('metadata', {})
            S = atom_obj.get('S', '')
            E = atom_obj.get('E', '')
        return {
            'id': atom_id,
            'content': content,
            'energy': energy,
            'metadata': metadata,
            'S': S,
            'E': E
        }

    def create_bubble(self, name: str, bubble_type: str = "document") -> str:
        # Jeśli mamy kernel, możemy użyć jego mechanizmu bąbli (jeśli istnieje)
        if self.kernel and hasattr(self.kernel, 'bubbles'):
            # Użyjemy natywnego bubble store z KarmazynOS
            # Uwaga: to uproszczenie – w pełnej implementacji trzeba by utworzyć bąbel w kernelu
            pass
        # Fallback: własny słownik
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
                    'description': '',
                    'media_stats': {'image': 0, 'audio': 0, 'document': 0}
                }
            },
            'atoms': []
        }
        self._local_bubbles[bubble_id] = bubble_data
        # Save explicitly if we are fully loaded in a kernel context with persistence
        if self.kernel and (self.bubblefs_available or self.soul_available):
            self.save_all()
        return bubble_id

    def add_atom_to_bubble(self, bubble_id: str, content: str, S: str = "", E: str = "", atom_id: str = None) -> Optional[str]:
        atoms = self.get_active_atoms(bubble_id)
        if len(atoms) >= MAX_ATOMS_PER_BUBBLE:
            print(f"❌ Limit atomów osiągnięty ({MAX_ATOMS_PER_BUBBLE})")
            return None

        if not atom_id:
            atom_id = str(uuid.uuid4())[:12]

        if self.kernel:
            try:
                # Użyjemy write() z jądra – zwraca label atomu
                # Uwaga: kernel.write() tworzy nowy atom w matrycy i generuje ID.
                # Aby zachować spójność nazw narzędzi (np. KEDIT), używamy podanego ID jeśli możliwe.
                final_id = self.kernel.write(content) if not atom_id else atom_id

                # Jeśli kernel ma własne bąble, trzeba dodać atom do bąbla – tutaj upraszczamy
                if bubble_id in self._local_bubbles:
                    self._local_bubbles[bubble_id]['atoms'].append({
                        'id': final_id,
                        'content': content,
                        'S': S or "TEXT",
                        'E': E or content[:100],
                        'type': 'text',
                        'energy': 1.0,
                        'created_at': time.time(),
                        'metadata': {'tags': [], 'links': []}
                    })
                if self.kernel and (self.bubblefs_available or self.soul_available):
                    self.save_all()
                return final_id
            except Exception as e:
                print(f"⚠️ Błąd dodawania atomu przez kernel: {e}")
                return None
        else:
            if bubble_id in self._local_bubbles:
                self._local_bubbles[bubble_id]['atoms'].append({
                    'id': atom_id,
                    'content': content,
                    'S': S or "TEXT",
                    'E': E or content[:100],
                    'type': 'text',
                    'energy': 1.0,
                    'created_at': time.time(),
                    'metadata': {'tags': [], 'links': []}
                })
        if self.kernel and (self.bubblefs_available or self.soul_available):
            self.save_all()
        return atom_id

    def get_active_atoms(self, bubble_id: str) -> List[Dict]:
        atoms = []
        if bubble_id in self._local_bubbles:
            for a in self._local_bubbles[bubble_id].get('atoms', []):
                atoms.append(self._normalize_atom(a))
        return atoms

    def get_bubble(self, bubble_id: str) -> Optional[Any]:
        return self._local_bubbles.get(bubble_id)

    def get_bubble_content(self, bubble_id: str, prism: str = "CORE") -> str:
        if bubble_id in self._local_bubbles:
            atoms = self._local_bubbles[bubble_id].get('atoms', [])
            if prism == "CORE":
                return '\n'.join(a['content'] for a in atoms)
            elif prism == "IN":
                return ' | '.join(f"[E:{a.get('energy', 0):.2f}] {a['content'][:80]}" for a in atoms)
            elif prism == "OUT":
                return ' | '.join(f"[atom:{a['id']}]" for a in atoms)
        return ""

    def refresh_bubble(self, bubble_id: str) -> int:
        count = 0
        if bubble_id in self._local_bubbles:
            for atom in self._local_bubbles[bubble_id].get('atoms', []):
                atom['energy'] = min(1.0, atom.get('energy', 0) + REFRESH_STRENGTH)
                count += 1
        return count

    def list_bubbles(self) -> List[Dict]:
        bubbles = []
        for bid, data in self._local_bubbles.items():
            bubbles.append({
                'id': bid,
                'name': data['bubble']['name'],
                'label': data['bubble'].get('label', data['bubble']['name']),
                'active_atoms': len(data.get('atoms', [])),
                'created_at': data['bubble']['created_at'],
                'type': data['bubble']['manifest']['type'],
                'media_stats': data['bubble']['manifest'].get('media_stats', {})
            })
        return sorted(bubbles, key=lambda x: x['created_at'], reverse=True)

    def search(self, query: str) -> List[Dict]:
        q = query.lower()
        results = []
        for bubble in self.list_bubbles():
            content = self.get_bubble_content(bubble['id'], "CORE")
            if q in bubble['name'].lower() or q in content.lower():
                results.append(bubble)
        return results

    def save(self):
        """Zapisuje stan używając jądra (soul_store) lub domyślnego JSON."""
        if self.kernel:
            if self.kernel.save(str(self.workspace / "soul_data")):
                print("💾 Zapisano przez KarmazynOS (.soul)")
                return

        # Fallback: zapis do plików .bubble
        for bid, data in self._local_bubbles.items():
            name = data['bubble']['name'].replace(' ', '_')
            filepath = self.workspace / f"{name}.bubble"
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        print("💾 Zapisano bąble do plików .bubble")

    def load(self):
        """Wczytuje stan przez jądro (soul_store) lub z plików .bubble."""
        if self.kernel:
            if self.kernel.load(str(self.workspace / "soul_data")):
                print("📂 Wczytano przez KarmazynOS (.soul)")
                return

        # Fallback: wczytaj z plików .bubble
        self._local_bubbles.clear()
        self._load_local_bubbles()
        print("📂 Wczytano bąble z plików .bubble")

    def save_all(self):
        """Alias dla save()."""
        self.save()

    def export_bubblefs(self, path: str, shared_secret: Optional[bytes] = None):
        """Eksportuje stan jądra do formatu BubbleFS."""
        if not self.bubblefs_available or not self.kernel:
            print("❌ BubbleFS niedostępny (brak modułu lub jądra)")
            return
        try:
            manifest = bubblefs_export(self.kernel, path, shared_secret)
            print(f"✅ Eksport BubbleFS zakończony: {manifest['n_bubbles']} bąbli")
        except Exception as e:
            print(f"❌ Błąd eksportu BubbleFS: {e}")

    def import_bubblefs(self, path: str, shared_secret: Optional[bytes] = None, merge: bool = False):
        """Importuje stan z formatu BubbleFS."""
        if not self.bubblefs_available or not self.kernel:
            print("❌ BubbleFS niedostępny (brak modułu lub jądra)")
            return
        try:
            result = bubblefs_import(self.kernel, path, shared_secret, merge)
            print(f"✅ Import BubbleFS zakończony: {result['imported_bubbles']} bąbli")
        except Exception as e:
            print(f"❌ Błąd importu BubbleFS: {e}")

    # --- Metody dla kompatybilności z bubble_commands ---
    def find_bubble_by_name(self, name: str) -> Optional[str]:
        for b in self.list_bubbles():
            if b['name'].lower() == name.lower():
                return b['id']
        return None

    def add_text(self, bubble_id: str, text: str) -> Optional[str]:
        return self.add_atom_to_bubble(bubble_id, text)

    def assemble(self, bubble_id: str, prism: str = "CORE") -> str:
        """Alias dla get_bubble_content dla kompatybilności."""
        return self.get_bubble_content(bubble_id, prism)

    def add_file(self, bubble_id: str, filepath: str) -> Optional[str]:
        """Wczytuje plik i dodaje jego treść do bąbla."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            return self.add_atom_to_bubble(bubble_id, content)
        except Exception as e:
            print(f"⚠️ Błąd add_file: {e}")
            return None

    def add_directory(self, bubble_id: str, dirpath: str, recursive: bool = False) -> List[str]:
        """Dodaje wszystkie pliki z katalogu do bąbla."""
        added_ids = []
        path = Path(dirpath)
        pattern = "**/*" if recursive else "*"
        for fp in path.glob(pattern):
            if fp.is_file():
                aid = self.add_file(bubble_id, str(fp))
                if aid:
                    added_ids.append(aid)
        return added_ids

    def import_to_bubble(self, bubble_id: str, atom_id: str, runtime, target_name: Optional[str] = None):
        """Importuje atom z runtime do bąbla, zachowując metadane S i E oraz ID."""
        bubble = self.get_bubble(bubble_id)
        if not bubble:
            # Jeśli bąbel wynikowy nie istnieje, tworzymy go w locie
            self.create_bubble(bubble_id, f"Grupa Wynikowa: {bubble_id}")

        atom = runtime.get_atom(atom_id)
        if atom:
            final_id = target_name if target_name else atom.id
            # Zachowujemy ID atomu (istotne dla narzędzi BIN) oraz metadane S i E
            res = self.add_atom_to_bubble(bubble_id, atom.E, S=atom.S, E=atom.E, atom_id=final_id)
            if self.kernel and (self.bubblefs_available or self.soul_available):
                self.save_all()
            return res
        return None

    def snapshot_runtime(self, bubble_id: str, atoms: List) -> int:
        """Przenosi wszystkie atomy z listy do bąbla."""
        count = 0
        for atom in atoms:
            # Używamy import_to_bubble zamiast ręcznego dodawania, aby zachować ID i metadane
            # Przekazujemy self.kernel jako runtime jeśli istnieje, w przeciwnym razie mockujemy minimalnie
            # W praktyce w shellu RUNTIME jest dostępny.
            if hasattr(atom, 'id'):
                # Tworzymy tymczasowy wrapper jeśli atom nie ma metody get_atom (ale atoms[] w runtime to obiekty Atom)
                # import_to_bubble potrzebuje obiektu z metodą get_atom(id).
                # Wygodniej będzie wywołać bezpośrednio add_atom_to_bubble
                S = getattr(atom, 'S', 'TEXT')
                E = getattr(atom, 'E', '')
                content = E if E else S
                if self.add_atom_to_bubble(bubble_id, content, S=S, E=E, atom_id=atom.id):
                    count += 1
        return count

    def get_media_gallery(self, bubble_id: str) -> str:
        atoms = self.get_active_atoms(bubble_id)
        if not atoms:
            return "(brak mediów)"
        lines = []
        for a in atoms:
            typ = "📄 tekst"
            if a['content'].startswith(("http://", "https://")):
                typ = "🔗 link"
            elif a['content'].endswith(('.png','.jpg','.gif')):
                typ = "🖼 obraz"
            lines.append(f"  {typ} [{a['energy']:.2f}] {a['content'][:50]}")
        return "\n".join(lines)

    def export_files(self, bubble_id: str, output_dir: str) -> List[str]:
        os.makedirs(output_dir, exist_ok=True)
        atoms = self.get_active_atoms(bubble_id)
        files = []
        for a in atoms:
            fpath = os.path.join(output_dir, f"{a['id']}.txt")
            try:
                with open(fpath, 'w', encoding='utf-8') as f:
                    f.write(a['content'])
                files.append(fpath)
            except Exception:
                pass
        return files


PRISMS = {
    'CORE': {'name': 'Rdzeń', 'desc': 'Pełna treść', 'icon': '🔮'},
    'IN':   {'name': 'Wewnętrzny', 'desc': 'Introspekcja', 'icon': '🔍'},
    'OUT':  {'name': 'Zewnętrzny', 'desc': 'Sygnatury', 'icon': '🌫️'}
}


class BubbleEditor(cmd.Cmd):
    intro = """
╔══════════════════════════════════════════════════════════════╗
║     KARMAZYNOS BUBBLE EDITOR v3.0.2                         ║
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
            print(f"🧠 Jądro: KarmazynOS")
        if self.integration.bubblefs_available:
            print(f"📦 BubbleFS dostępny")
        if self.integration.soul_available:
            print(f"💾 Soul Store dostępny")
        if self.integration.hss_daemon:
            print(f"🔐 HSS Daemon dostępny")
        print()

    # ... (reszta metod edytora bez zmian – do_create, do_write, itd.) ...
    # Ze względu na długość, pomijam je – możesz pozostawić oryginalne metody.
    # Ważne, że nowe metody integracji (save, load, export_bubblefs, import_bubblefs)
    # są dostępne przez self.integration.

    def do_export_bubblefs(self, arg):
        """Eksportuje cały stan do katalogu BubbleFS: export_bubblefs <ścieżka> [secret]"""
        args = arg.split()
        if not args:
            print("❌ export_bubblefs <ścieżka> [shared_secret]")
            return
        path = args[0]
        secret = args[1].encode() if len(args) > 1 else None
        self.integration.export_bubblefs(path, secret)

    def do_import_bubblefs(self, arg):
        """Importuje stan z katalogu BubbleFS: import_bubblefs <ścieżka> [secret] [merge]"""
        args = arg.split()
        if not args:
            print("❌ import_bubblefs <ścieżka> [shared_secret] [merge]")
            return
        path = args[0]
        secret = args[1].encode() if len(args) > 1 else None
        merge = args[2].lower() == 'true' if len(args) > 2 else False
        self.integration.import_bubblefs(path, secret, merge)

    def do_soul_save(self, arg):
        """Zapisuje stan przez soul_store (nadpisuje domyślny zapis)"""
        self.integration.save()

    def do_soul_load(self, arg):
        """Wczytuje stan przez soul_store"""
        self.integration.load()


# Uruchomienie
if __name__ == '__main__':
    BubbleEditor().cmdloop()