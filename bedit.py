#!/usr/bin/env python3
"""
KarmazynOS Bubble Editor (bedit) v3.1.0

Zmiany v3.1.0:
  HSSDaemon usuniety z KarmazynIntegration.__init__.
  HSS jest usluga mikrojadra (runtime.hss), nie edytora plikow.
  shell.py wstrzykuje: BUBBLES.hss_daemon = RUNTIME.hss
"""

import cmd
import os
import time
import json
import hashlib
import uuid
from typing import Dict, List, Optional, Any
from pathlib import Path

MAX_ATOMS_PER_BUBBLE = 200
REFRESH_STRENGTH     = 0.15
DEFAULT_PRISM        = "CORE"

KARMAZYN_LOADED = False
BUBBLEFS_LOADED = False
SOUL_LOADED     = False

try:
    from karmazyn import KarmazynOS
    KARMAZYN_LOADED = True
except ImportError as e:
    print(f"karmazyn.py - {e} - tryb standalone")

try:
    from bubblefs import (export as bubblefs_export,
                          import_ as bubblefs_import,
                          inspect as bubblefs_inspect)
    BUBBLEFS_LOADED = True
except ImportError as e:
    print(f"bubblefs.py - {e}")

try:
    import soul_store
    SOUL_LOADED = True
except ImportError as e:
    print(f"soul_store.py - {e}")

# HSS_LOADED celowo usuniete - HSSDaemon inicjowany w runtime.py,
# wstrzykiwany do KarmazynIntegration.hss_daemon przez shell.py.


class KarmazynIntegration:
    def __init__(self, workspace: str = ".bubbles"):
        self.workspace = Path(workspace)
        self.workspace.mkdir(exist_ok=True)

        self.kernel             = None
        self.bubblefs_available = BUBBLEFS_LOADED
        self.soul_available     = SOUL_LOADED

        # HSS wstrzykiwany z zewnatrz przez shell.py po inicjalizacji runtime:
        #   BUBBLES.hss_daemon = RUNTIME.hss
        self.hss_daemon = None

        if KARMAZYN_LOADED:
            try:
                self.kernel = KarmazynOS()
                print("Jadro KarmazynOS zaladowane")
            except Exception as e:
                print(f"Blad inicjalizacji KarmazynOS: {e}")

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
        return {'id': atom_id, 'content': content, 'energy': energy,
                'metadata': metadata, 'S': S, 'E': E}

    def create_bubble(self, name: str, bubble_type: str = "document") -> str:
        bubble_id = f"bubble_{int(time.time())}_{hashlib.md5(name.encode()).hexdigest()[:8]}"
        bubble_data = {
            'bubble': {
                'id': bubble_id, 'name': name, 'created_at': time.time(),
                'manifest': {
                    'version': '3.1.0', 'type': bubble_type,
                    'prism_default': DEFAULT_PRISM, 'tags': [],
                    'description': '',
                    'media_stats': {'image': 0, 'audio': 0, 'document': 0},
                },
            },
            'atoms': [],
        }
        self._local_bubbles[bubble_id] = bubble_data
        if self.kernel and (self.bubblefs_available or self.soul_available):
            self.save_all(silent=True)
        return bubble_id

    def add_atom_to_bubble(self, bubble_id: str, content: str,
                           S: str = "", E: str = "",
                           atom_id: str = None) -> Optional[str]:
        atoms = self.get_active_atoms(bubble_id)
        if len(atoms) >= MAX_ATOMS_PER_BUBBLE:
            print(f"Limit atomow osiagniety ({MAX_ATOMS_PER_BUBBLE})")
            return None
        if not atom_id:
            atom_id = str(uuid.uuid4())[:12]
        if self.kernel:
            try:
                final_id = self.kernel.write(content) if not atom_id else atom_id
                if bubble_id in self._local_bubbles:
                    self._local_bubbles[bubble_id]['atoms'].append({
                        'id': final_id, 'content': content,
                        'S': S or "TEXT", 'E': E or content[:100],
                        'type': 'text', 'energy': 1.0,
                        'created_at': time.time(),
                        'metadata': {'tags': [], 'links': []},
                    })
                if self.kernel and (self.bubblefs_available or self.soul_available):
                    self.save_all(silent=True)
                return final_id
            except Exception as e:
                print(f"Blad dodawania atomu przez kernel: {e}")
                return None
        else:
            if bubble_id in self._local_bubbles:
                self._local_bubbles[bubble_id]['atoms'].append({
                    'id': atom_id, 'content': content,
                    'S': S or "TEXT", 'E': E or content[:100],
                    'type': 'text', 'energy': 1.0,
                    'created_at': time.time(),
                    'metadata': {'tags': [], 'links': []},
                })
        if self.kernel and (self.bubblefs_available or self.soul_available):
            self.save_all(silent=True)
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
                return ' | '.join(
                    f"[E:{a.get('energy',0):.2f}] {a['content'][:80]}" for a in atoms)
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
                'id': bid, 'name': data['bubble']['name'],
                'label': data['bubble'].get('label', data['bubble']['name']),
                'active_atoms': len(data.get('atoms', [])),
                'created_at': data['bubble']['created_at'],
                'type': data['bubble']['manifest']['type'],
                'media_stats': data['bubble']['manifest'].get('media_stats', {}),
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

    def save(self, silent: bool = False):
        if self.kernel:
            if self.kernel.save(str(self.workspace / "soul_data")):
                if not silent:
                    print("Zapisano przez KarmazynOS (.soul)")
                return
        for bid, data in self._local_bubbles.items():
            name = data['bubble']['name'].replace(' ', '_')
            filepath = self.workspace / f"{name}.bubble"
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        if not silent:
            print("Zapisano bable do plikow .bubble")

    def load(self, silent: bool = False):
        if self.kernel:
            if self.kernel.load(str(self.workspace / "soul_data")):
                if not silent:
                    print("Wczytano przez KarmazynOS (.soul)")
                return
        self._local_bubbles.clear()
        self._load_local_bubbles()
        if not silent:
            print("Wczytano bable z plikow .bubble")

    def save_all(self, silent: bool = False):
        self.save(silent=silent)

    def export_bubblefs(self, path: str, shared_secret: Optional[bytes] = None):
        if not self.bubblefs_available or not self.kernel:
            print("BubbleFS niedostepny")
            return
        try:
            manifest = bubblefs_export(self.kernel, path, shared_secret)
            print(f"Eksport BubbleFS: {manifest['n_bubbles']} babli")
        except Exception as e:
            print(f"Blad eksportu BubbleFS: {e}")

    def import_bubblefs(self, path: str, shared_secret: Optional[bytes] = None,
                        merge: bool = False):
        if not self.bubblefs_available or not self.kernel:
            print("BubbleFS niedostepny")
            return
        try:
            result = bubblefs_import(self.kernel, path, shared_secret, merge)
            print(f"Import BubbleFS: {result['imported_bubbles']} babli")
        except Exception as e:
            print(f"Blad importu BubbleFS: {e}")

    def find_bubble_by_name(self, name: str) -> Optional[str]:
        for b in self.list_bubbles():
            if b['name'].lower() == name.lower():
                return b['id']
        return None

    def add_text(self, bubble_id: str, text: str) -> Optional[str]:
        return self.add_atom_to_bubble(bubble_id, text)

    def assemble(self, bubble_id: str, prism: str = "CORE") -> str:
        return self.get_bubble_content(bubble_id, prism)

    def add_file(self, bubble_id: str, filepath: str) -> Optional[str]:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            return self.add_atom_to_bubble(bubble_id, content)
        except Exception as e:
            print(f"Blad add_file: {e}")
            return None

    def add_directory(self, bubble_id: str, dirpath: str,
                      recursive: bool = False) -> List[str]:
        added_ids = []
        path = Path(dirpath)
        pattern = "**/*" if recursive else "*"
        for fp in path.glob(pattern):
            if fp.is_file():
                aid = self.add_file(bubble_id, str(fp))
                if aid:
                    added_ids.append(aid)
        return added_ids

    def import_to_bubble(self, bubble_id: str, atom_id: str,
                         runtime, target_name: Optional[str] = None):
        bubble = self.get_bubble(bubble_id)
        if not bubble:
            self.create_bubble(bubble_id, f"Grupa Wynikowa: {bubble_id}")
            bubble = self.get_bubble(bubble_id)
        atom = runtime.get_atom(atom_id)
        if atom:
            from core.phi_math import PhiPhysics
            atom_S = getattr(atom, 'S', None)
            atom_phi = PhiPhysics.normalize_to_phi_space(
                atom_S if isinstance(atom_S, str) else ''
            )
            bubble_name = (bubble.get('name', '') if isinstance(bubble, dict)
                           else getattr(bubble, 'name', ''))
            bubble_phi = PhiPhysics.normalize_to_phi_space(bubble_name)
            if not PhiPhysics.predict_vector_convergence(atom_phi, bubble_phi):
                print("diverged")
                runtime.delete_atom(atom_id)
                return None
            final_id = target_name if target_name else atom.id
            res = self.add_atom_to_bubble(
                bubble_id, getattr(atom, 'E', ''),
                S=getattr(atom, 'S', ''), E=getattr(atom, 'E', ''),
                atom_id=final_id,
            )
            if self.kernel and (self.bubblefs_available or self.soul_available):
                self.save_all(silent=True)
            return res
        return None

    def snapshot_runtime(self, bubble_id: str, atoms: List) -> int:
        count = 0
        for atom in atoms:
            if hasattr(atom, 'id'):
                S = getattr(atom, 'S', 'TEXT')
                E = getattr(atom, 'E', '')
                content = E if E else S
                if self.add_atom_to_bubble(bubble_id, content,
                                           S=S, E=E, atom_id=atom.id):
                    count += 1
        return count

    def get_media_gallery(self, bubble_id: str) -> str:
        atoms = self.get_active_atoms(bubble_id)
        if not atoms:
            return "(brak mediow)"
        lines = []
        for a in atoms:
            typ = "tekst"
            if a['content'].startswith(("http://", "https://")):
                typ = "link"
            elif a['content'].endswith(('.png', '.jpg', '.gif')):
                typ = "obraz"
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
    'CORE': {'name': 'Rdzen',      'desc': 'Pelna tresc',  'icon': 'O'},
    'IN':   {'name': 'Wewnetrzny', 'desc': 'Introspekcja', 'icon': 'I'},
    'OUT':  {'name': 'Zewnetrzny', 'desc': 'Sygnatury',    'icon': 'X'},
}


class BubbleEditor(cmd.Cmd):
    intro  = "KARMAZYN BUBBLE EDITOR v3.1.0\n"
    prompt = '[karmazyn] -> '

    def __init__(self):
        super().__init__()
        self.integration          = KarmazynIntegration()
        self.current_bubble_id:   Optional[str] = None
        self.current_bubble_name: Optional[str] = None
        self.current_prism        = DEFAULT_PRISM

        bubbles = self.integration.list_bubbles()
        print(f"{len(bubbles)} babli w przestrzeni")
        if self.integration.kernel:
            print("Jadro: KarmazynOS")
        if self.integration.bubblefs_available:
            print("BubbleFS dostepny")
        if self.integration.soul_available:
            print("Soul Store dostepny")
        if self.integration.hss_daemon:
            print("HSS Daemon dostepny (wstrzykniety z runtime)")
        print()

    def do_export_bubblefs(self, arg):
        args   = arg.split()
        if not args:
            print("export_bubblefs <sciezka> [secret]")
            return
        secret = args[1].encode() if len(args) > 1 else None
        self.integration.export_bubblefs(args[0], secret)

    def do_import_bubblefs(self, arg):
        args   = arg.split()
        if not args:
            print("import_bubblefs <sciezka> [secret] [merge]")
            return
        secret = args[1].encode() if len(args) > 1 else None
        merge  = args[2].lower() == 'true' if len(args) > 2 else False
        self.integration.import_bubblefs(args[0], secret, merge)

    def do_soul_save(self, arg):
        self.integration.save(silent=False)

    def do_soul_load(self, arg):
        self.integration.load(silent=False)


if __name__ == '__main__':
    BubbleEditor().cmdloop()