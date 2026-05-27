"""
karmazyn_bubble_sync.py — Bridge synchronizacji bąbli v1.0
============================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

PROBLEM ARCHITEKTONICZNY:
  System ma DWA niezależne modele bąbli które nie wiedzą o sobie:

  1. RUNTIME._bubbles (RAM) — używany przez:
     - bubble_commands.py (BUBBLE NEW, BUBBLE LS, BUBBLE STATUS)
     - runtime.py / SanctuaryRuntime (consolidate, get_bubble)
     - karmazyn_core.py (Bubble z PhiSpace, Hologram, Psi)

  2. BubbleVFS (dysk .kafd) — używany przez:
     - karmazyn_vfs.py (save/load zaszyfrowane KAFD)
     - karmazyn_fm.py (File Manager tryb BBL)
     - karmazyn_shell_cmds.py (MKB, RMB, LSB, BIMPORT)
     - NooEdit.py (edytor bąbli)

  Efekt:
     BUBBLE NEW foo  → tworzy w RAM → niewidoczne w FM
     MKB foo         → tworzy na dysku → niewidoczne w BUBBLE LS
     BUBBLE SAVE     → zapisuje do .soul JSONL
     BubbleVFS.save  → zapisuje do .kafd (inny format!)

ROZWIĄZANIE:
  BubbleSync — bridge który:
  1. Przy tworzeniu bąbla → tworzy w OBU systemach
  2. Przy listowaniu → merge z OBU źródeł
  3. Przy zapisie treści → synchronizuje OBA kierunki
  4. Przy usuwaniu → usuwa z OBU systemów

UŻYCIE W shell.py:
  from karmazyn_bubble_sync import BubbleSync
  SYNC = BubbleSync(RUNTIME, BUBBLES)
  # Zamiast bezpośredniego RUNTIME._bubbles lub BUBBLES
  # użyj SYNC.create(), SYNC.list_all(), SYNC.delete()

REJESTRACJA KOMEND:
  SYNC.register_commands(reg)
  # Nadpisuje BUBBLE LS, MKB, RMB aby działały z oboma systemami
"""

import time
from typing import Any, Dict, List, Optional


class BubbleSync:
    """
    Bridge synchronizujący dwa modele bąbli w KarmazynOS.

    Nie zastępuje żadnego z systemów — łączy je.
    RUNTIME._bubbles pozostaje canonical dla phi-space.
    BubbleVFS pozostaje canonical dla persistencji.
    BubbleSync zapewnia że oba widzą to samo.
    """

    def __init__(self, runtime: Any, vfs: Any):
        """
        runtime — PhiSpace lub SanctuaryRuntime (z _bubbles dict)
        vfs     — BubbleVFS (z list_bubbles, create_bubble, etc.)
        """
        self.runtime = runtime
        self.vfs     = vfs
        self._synced_labels: set = set()

    # ── Tworzenie ─────────────────────────────────────────────────────────────

    def create(self, label: str, mode: str = "workspace",
               content: str = "") -> dict:
        """
        Tworzy bąbel w OBU systemach jednocześnie.

        Zwraca dict z informacjami o stworzonym bąblu.
        """
        results = {"label": label, "ram": False, "vfs": False, "errors": []}

        # 1. RAM: RUNTIME._bubbles (lub PhiSpace._bubbles)
        try:
            bubbles_dict = self._get_runtime_bubbles()
            if bubbles_dict is not None and label not in bubbles_dict:
                # Użyj API runtime jeśli dostępne
                if hasattr(self.runtime, 'consolidate'):
                    # Stwórz atom anchor i skonsoliduj do bąbla
                    if not self.runtime.has_atom(label):
                        self._create_atom_compat(label, content or "bubble_init")
                    self.runtime.consolidate(label)
                    results["ram"] = True
                elif hasattr(self.runtime, 'create_bubble'):
                    self.runtime.create_bubble(label)
                    results["ram"] = True
            elif bubbles_dict is not None and label in bubbles_dict:
                results["ram"] = True  # już istnieje
        except Exception as e:
            results["errors"].append(f"RAM: {e}")

        # 2. VFS: BubbleVFS (dysk .kafd)
        try:
            if self.vfs is not None:
                self.vfs.create_bubble(label)
                if content:
                    ct = "py" if label.endswith(".py") else "txt"
                    self.vfs.save(label, content, ct)
                results["vfs"] = True
        except Exception as e:
            results["errors"].append(f"VFS: {e}")

        # 3. Atom phi-space reprezentujący bąbel
        try:
            atom_id = f"bubble.{label}"
            if hasattr(self.runtime, 'has_atom') and not self.runtime.has_atom(atom_id):
                self._create_atom_compat(atom_id, label, S="bubble", T=60.0)
        except Exception:
            pass

        self._synced_labels.add(label)
        return results

    # ── Listowanie ────────────────────────────────────────────────────────────

    def list_all(self) -> List[dict]:
        """
        Merge bąbli z OBU źródeł.
        Zwraca listę dict z polami: label, id, source, active_atoms, T, state
        """
        seen = {}  # label → dict

        # 1. Z RAM (RUNTIME._bubbles)
        try:
            bubbles_dict = self._get_runtime_bubbles()
            if bubbles_dict:
                for label, bubble in bubbles_dict.items():
                    entry = {
                        "label": label,
                        "id": label,
                        "source": "ram",
                        "active_atoms": 0,
                        "T": 0.0,
                        "state": "WARM",
                    }
                    # Spróbuj wyciągnąć dodatkowe info z różnych typów bąbli
                    if hasattr(bubble, 'psi'):
                        entry["psi"] = round(getattr(bubble, 'psi', 0), 4)
                        entry["theta"] = round(getattr(bubble, 'theta', 0), 4)
                    if hasattr(bubble, 'content'):
                        entry["has_content"] = bool(bubble.content)
                    if hasattr(bubble, 'T'):
                        entry["T"] = round(float(bubble.T), 1)
                    if hasattr(bubble, 'state'):
                        entry["state"] = str(bubble.state)
                    # PhiBubble ma len()
                    if hasattr(bubble, '__len__'):
                        entry["active_atoms"] = len(bubble)

                    seen[label] = entry
        except Exception:
            pass

        # 2. Z VFS (BubbleVFS na dysku)
        try:
            if self.vfs is not None:
                vfs_list = self.vfs.list_bubbles()
                for b in vfs_list:
                    label = b.get("label", b.get("id", "?"))
                    if label in seen:
                        # Merge: dodaj info z VFS do istniejącego rekordu
                        seen[label]["source"] = "ram+vfs"
                        seen[label]["size_bytes"] = b.get("size_bytes", 0)
                        # Jeśli VFS ma więcej atomów, użyj tej wartości
                        vfs_atoms = b.get("active_atoms", 0)
                        if vfs_atoms > seen[label]["active_atoms"]:
                            seen[label]["active_atoms"] = vfs_atoms
                    else:
                        # Bąbel tylko w VFS (nie w RAM)
                        seen[label] = {
                            "label": label,
                            "id": b.get("id", label),
                            "source": "vfs",
                            "active_atoms": b.get("active_atoms", 0),
                            "size_bytes": b.get("size_bytes", 0),
                            "T": 0.0,
                            "state": "COLD",  # na dysku = zimny
                        }
        except Exception:
            pass

        return sorted(seen.values(), key=lambda x: x.get("label", ""))

    # ── Usuwanie ──────────────────────────────────────────────────────────────

    def delete(self, label: str) -> dict:
        """Usuwa bąbel z OBU systemów."""
        results = {"label": label, "ram": False, "vfs": False, "errors": []}

        # 1. RAM
        try:
            bubbles_dict = self._get_runtime_bubbles()
            if bubbles_dict and label in bubbles_dict:
                del bubbles_dict[label]
                results["ram"] = True
        except Exception as e:
            results["errors"].append(f"RAM: {e}")

        # 2. VFS
        try:
            if self.vfs is not None:
                self.vfs.delete_bubble(label)
                results["vfs"] = True
        except Exception as e:
            results["errors"].append(f"VFS: {e}")

        # 3. Atom phi-space
        try:
            atom_id = f"bubble.{label}"
            if hasattr(self.runtime, 'has_atom') and self.runtime.has_atom(atom_id):
                if hasattr(self.runtime, 'delete_atom'):
                    self.runtime.delete_atom(atom_id)
                elif hasattr(self.runtime, 'matrix'):
                    self.runtime.matrix.delete(atom_id)
        except Exception:
            pass

        self._synced_labels.discard(label)
        return results

    # ── Synchronizacja ────────────────────────────────────────────────────────

    def sync_ram_to_vfs(self) -> int:
        """
        Synchronizuje bąble z RAM do VFS.
        Dla bąbli które istnieją w RAM ale nie w VFS — tworzy na dysku.
        Zwraca liczbę zsynchronizowanych bąbli.
        """
        count = 0
        try:
            bubbles_dict = self._get_runtime_bubbles()
            if not bubbles_dict or not self.vfs:
                return 0

            # Pobierz listę VFS labels
            vfs_labels = set()
            try:
                for b in self.vfs.list_bubbles():
                    vfs_labels.add(b.get("label", b.get("id", "")))
            except Exception:
                pass

            for label, bubble in bubbles_dict.items():
                if label not in vfs_labels:
                    try:
                        content = ""
                        if hasattr(bubble, 'content'):
                            content = str(bubble.content)
                        self.vfs.create_bubble(label)
                        if content:
                            self.vfs.save(label, content, "txt")
                        count += 1
                    except Exception:
                        pass
        except Exception:
            pass
        return count

    def sync_vfs_to_ram(self) -> int:
        """
        Synchronizuje bąble z VFS do RAM.
        Dla bąbli które istnieją na dysku ale nie w RAM — ładuje do pamięci.
        Zwraca liczbę zsynchronizowanych bąbli.
        """
        count = 0
        try:
            bubbles_dict = self._get_runtime_bubbles()
            if bubbles_dict is None or not self.vfs:
                return 0

            vfs_list = self.vfs.list_bubbles()
            for b in vfs_list:
                label = b.get("label", b.get("id", ""))
                if label and label not in bubbles_dict:
                    try:
                        # Załaduj treść z VFS
                        content = self.vfs.load(label, "txt") or ""
                        # Stwórz bąbel w RAM
                        if hasattr(self.runtime, 'create_bubble'):
                            self.runtime.create_bubble(label)
                        elif hasattr(self.runtime, 'consolidate'):
                            if not self.runtime.has_atom(label):
                                self._create_atom_compat(label, content[:64] or "vfs_sync")
                            self.runtime.consolidate(label)
                        count += 1
                    except Exception:
                        pass
        except Exception:
            pass
        return count

    def full_sync(self) -> dict:
        """Dwukierunkowa synchronizacja."""
        ram_to_vfs = self.sync_ram_to_vfs()
        vfs_to_ram = self.sync_vfs_to_ram()
        return {
            "ram_to_vfs": ram_to_vfs,
            "vfs_to_ram": vfs_to_ram,
            "total_synced": ram_to_vfs + vfs_to_ram,
        }

    # ── Status ────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        """Diagnostyka rozbieżności między RAM i VFS."""
        ram_labels = set()
        vfs_labels = set()

        try:
            bubbles_dict = self._get_runtime_bubbles()
            if bubbles_dict:
                ram_labels = set(bubbles_dict.keys())
        except Exception:
            pass

        try:
            if self.vfs:
                for b in self.vfs.list_bubbles():
                    vfs_labels.add(b.get("label", b.get("id", "")))
        except Exception:
            pass

        only_ram = ram_labels - vfs_labels
        only_vfs = vfs_labels - ram_labels
        both     = ram_labels & vfs_labels

        return {
            "ram_count":  len(ram_labels),
            "vfs_count":  len(vfs_labels),
            "synced":     len(both),
            "only_ram":   sorted(only_ram),
            "only_vfs":   sorted(only_vfs),
            "desync":     len(only_ram) + len(only_vfs),
        }

    # ── Rejestracja komend ────────────────────────────────────────────────────

    def register_commands(self, reg_fn) -> None:
        """
        Rejestruje komendy synchronizacji w shellu.

        BSYNC STATUS  — diagnostyka rozbieżności RAM ↔ VFS
        BSYNC FULL    — dwukierunkowa synchronizacja
        BSYNC RAM2VFS — RAM → VFS
        BSYNC VFS2RAM — VFS → RAM
        """
        def cmd_bsync(args):
            if not args:
                s = self.status()
                lines = [
                    f"  RAM:     {s['ram_count']} bąbli",
                    f"  VFS:     {s['vfs_count']} bąbli",
                    f"  Synced:  {s['synced']}",
                    f"  Desync:  {s['desync']}",
                ]
                if s['only_ram']:
                    lines.append(f"  Tylko RAM: {', '.join(s['only_ram'][:10])}")
                if s['only_vfs']:
                    lines.append(f"  Tylko VFS: {', '.join(s['only_vfs'][:10])}")
                return "\n".join(lines)

            sub = args[0].upper()
            if sub == "STATUS":
                return cmd_bsync([])
            elif sub == "FULL":
                r = self.full_sync()
                return (f"Sync: RAM→VFS={r['ram_to_vfs']} "
                        f"VFS→RAM={r['vfs_to_ram']} "
                        f"total={r['total_synced']}")
            elif sub == "RAM2VFS":
                n = self.sync_ram_to_vfs()
                return f"RAM → VFS: {n} bąbli zsynchronizowanych"
            elif sub == "VFS2RAM":
                n = self.sync_vfs_to_ram()
                return f"VFS → RAM: {n} bąbli zsynchronizowanych"
            return "BSYNC [STATUS|FULL|RAM2VFS|VFS2RAM]"

        reg_fn("BSYNC", cmd_bsync,
               "Synchronizacja bąbli RAM ↔ VFS", category="bubbles")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_runtime_bubbles(self) -> Optional[dict]:
        """Pobierz dict bąbli z runtime (kompatybilne z różnymi runtime'ami)."""
        if hasattr(self.runtime, '_bubbles'):
            return self.runtime._bubbles
        return None

    def _create_atom_compat(self, atom_id: str, content: str = "",
                             S: str = "", T: float = 50.0):
        """Tworzy atom kompatybilnie z różnymi runtime'ami."""
        if hasattr(self.runtime, 'create_atom'):
            try:
                return self.runtime.create_atom(atom_id, S=S or atom_id, E=content, T=T)
            except TypeError:
                try:
                    return self.runtime.create_atom(atom_id, S or atom_id, content, T)
                except Exception:
                    pass
        if hasattr(self.runtime, 'write'):
            try:
                import inspect
                sig = inspect.signature(self.runtime.write)
                if len(sig.parameters) >= 4:
                    return self.runtime.write(atom_id, S or atom_id, content, T)
                else:
                    return self.runtime.write(content or atom_id)
            except Exception:
                pass
        return None
