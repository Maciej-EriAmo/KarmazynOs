"""
karmazyn_app.py — Warstwa aplikacyjna KarmazynOS v1.0
======================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Niewidzialna warstwa pod aplikacjami. Aplikacje (edytor, zarządca,
odtwarzacz) mówią językiem użytkownika: otwórz / zapisz / lista / usuń.
NIE wiedzą nic o atomach, bąblach, phi-space ani równaniach.

Filozofia (jak Android/macOS): cała maszyneria pod maską.
  Użytkownik: "otwórz notatki", "zapisz", "odtwórz piosenkę"
  Warstwa:    tłumaczy to na atomy/bąble i sama wykrywa typ zawartości

Izomorfizm z LOGO/JS (ten sam kontrakt karmazyn_atom + karmazyn_phi):
  dokument        ≡ PhiBubble (label = nazwa widoczna dla użytkownika)
  bieżąca treść   ≡ atom S="content:<kind>"  (jeden, nadpisywany)
  wersja w historii ≡ atom S="version"  (gorący, stygnie sam = naturalne undo)
  zapis           ≡ create_atom (nowy/aktualizacja) — jak make w LOGO
  usunięcie wersji ≡ phi.tick() stygnie stare → Vacuum Decay

Typ zawartości wykrywany AUTOMATYCZNIE z bajtów (magic bytes).
Użytkownik nigdy nie podaje "czy to tekst czy audio" — system wie sam.

Publiczny interfejs (zero słów atom/bąbel/phi):
    ws = Workspace()
    ws.save("notatki", "treść...")          # tekst
    ws.save("piosenka", mp3_bytes)          # audio (wykryte)
    item = ws.open("notatki")               # → Item
    item.kind        # "text" | "audio" | "image" | "binary"
    item.text        # treść tekstowa (gdy kind=="text")
    item.data        # surowe bajty (gdy binarne)
    ws.list()        # [{"name","kind","size","updated"}, ...]
    ws.delete("notatki")
    ws.versions("notatki")  # historia (gorące=nowe, stygną same)
"""

import base64
import time
from typing import Any, Dict, List, Optional, Union

from karmazyn_atom import Atom, T_HOT, T_WARM, T_INIT
from karmazyn_phi  import PhiSpace, PhiBubble


# ─── Wykrywanie typu zawartości (magic bytes) ────────────────────────────────

def detect_kind(data: Union[bytes, str]) -> str:
    """
    Wykrywa rodzaj zawartości z surowych bajtów.

    Zwraca: "text" | "audio" | "image" | "binary"

    To jedyne miejsce w systemie które decyduje "co to jest".
    Aplikacja nie pyta — woła detect_kind() i dostaje odpowiedź.
    """
    if isinstance(data, str):
        return "text"
    if not data:
        return "text"

    head = data[:16]

    # ── Audio ──
    if head[:3] == b'ID3':                         return "audio"   # MP3 z tagiem
    if head[:2] in (b'\xff\xfb', b'\xff\xf3', b'\xff\xf2', b'\xff\xfa'):
        return "audio"                                              # MP3 frame
    if head[:4] == b'OggS':                        return "audio"   # OGG/Vorbis/Opus
    if head[:4] == b'fLaC':                        return "audio"   # FLAC
    if head[:4] == b'RIFF' and data[8:12] == b'WAVE': return "audio"  # WAV
    if head[:4] == b'\x00\x00\x00\x18ftyp'[:4] and b'M4A' in data[:16]:
        return "audio"                                             # M4A

    # ── Obraz ──
    if head[:8] == b'\x89PNG\r\n\x1a\n':           return "image"   # PNG
    if head[:3] == b'\xff\xd8\xff':                return "image"   # JPEG
    if head[:6] in (b'GIF87a', b'GIF89a'):         return "image"   # GIF
    if head[:2] == b'BM':                          return "image"   # BMP
    if head[:4] == b'RIFF' and data[8:12] == b'WEBP': return "image"  # WEBP
    if head[:4] == b'\x00\x00\x01\x00':            return "image"   # ICO

    # ── Tekst? (próba dekodowania UTF-8) ──
    try:
        data.decode('utf-8')
        return "text"
    except (UnicodeDecodeError, AttributeError):
        return "binary"


# ─── Item — to co użytkownik nazywa "dokumentem" / "plikiem" / "utworem" ──────

class Item:
    """
    Pozycja w workspace — widziana przez użytkownika i aplikację.
    NIE wie że pod spodem to bąbel z atomami.

    Pola:
      name    — nazwa widoczna dla użytkownika
      kind    — "text" | "audio" | "image" | "binary" (wykryty)
      text    — treść tekstowa (gdy kind == "text", inaczej None)
      data    — surowe bajty (gdy binarne, inaczej None)
      size    — rozmiar w bajtach
      updated — timestamp ostatniego zapisu
    """
    __slots__ = ("name", "kind", "text", "data", "size", "updated")

    def __init__(self, name: str, kind: str,
                 text: Optional[str] = None,
                 data: Optional[bytes] = None,
                 size: int = 0, updated: float = 0.0):
        self.name    = name
        self.kind    = kind
        self.text    = text
        self.data    = data
        self.size    = size
        self.updated = updated

    @property
    def is_text(self)  -> bool: return self.kind == "text"
    @property
    def is_audio(self) -> bool: return self.kind == "audio"
    @property
    def is_image(self) -> bool: return self.kind == "image"

    def __repr__(self) -> str:
        return f"<Item {self.name!r} kind={self.kind} size={self.size}B>"


# ─── Workspace — niewidzialna warstwa ────────────────────────────────────────

class Workspace:
    """
    Warstwa-pod-maską. Tłumaczy język użytkownika (open/save/list)
    na operacje phi-space. Aplikacje używają TYLKO tej klasy.

    Konwencja wewnętrzna (nigdy nie wypływa na powierzchnię):
      manifest atomu : id = "doc::<name>"            S="document"
      bieżąca treść  : id = "doc::<name>::content"   S="content:<kind>"
      wersja historii: id = "doc::<name>::v::<ts>"   S="version"

    Tekst trafia do atom.E (str) ORAZ bubble.content (szybki odczyt).
    Bajty (audio/obraz) trafiają do atom.metadata['data'] (dict trzyma bytes).
    """

    _MANIFEST_S = "document"
    _VERSION_S  = "version"
    MAX_VERSIONS_HINT = 12   # tyle wersji trzymamy "gorących"; reszta stygnie

    def __init__(self, phi: Optional[PhiSpace] = None):
        # Współdziel phi z resztą systemu (LOGO/JS/runtime) jeśli podane,
        # inaczej utwórz własną przestrzeń.
        self.phi = phi if phi is not None else PhiSpace()

    # ── Klucze wewnętrzne ─────────────────────────────────────────────────────

    @staticmethod
    def _manifest_id(name: str) -> str:
        return f"doc::{name}"

    @staticmethod
    def _content_id(name: str) -> str:
        return f"doc::{name}::content"

    @staticmethod
    def _version_id(name: str, ts: float) -> str:
        return f"doc::{name}::v::{ts:.6f}"

    # ── Zapis ─────────────────────────────────────────────────────────────────

    def save(self, name: str, content: Union[str, bytes],
             keep_version: bool = True) -> Item:
        """
        Zapisz dokument. Wykrywa typ sam. Tworzy/aktualizuje bąbel.

        keep_version=True → poprzednia treść zostaje jako wersja historii
                            (gorąca, stygnie sama przez phi.tick()).
        """
        kind = detect_kind(content)
        now  = time.time()

        is_text = isinstance(content, str)
        raw     = content.encode("utf-8") if is_text else content
        size    = len(raw)

        bubble = self.phi.create_bubble(name)

        # ── Historia: zachowaj poprzednią treść jako wersję (zanim nadpiszemy) ──
        if keep_version:
            prev = self.phi.peek_atom(self._content_id(name))
            if prev is not None and (prev.E or prev.metadata.get("data")):
                vid = self._version_id(name, now)
                vatom = self.phi.create_atom(
                    vid, S=self._VERSION_S, E=prev.E, T=T_HOT)
                # przenieś dane binarne wersji jeśli były
                if prev.metadata.get("data") is not None:
                    vatom.metadata["data"] = prev.metadata["data"]
                vatom.metadata["kind"]    = prev.metadata.get("kind", "text")
                vatom.metadata["of"]      = name
                vatom.metadata["created"] = now
                bubble.add(vid)

        # ── Manifest (marker dokumentu) ──
        man = self.phi.create_atom(
            self._manifest_id(name), S=self._MANIFEST_S, E=name, T=T_HOT)
        man.metadata.update(kind=kind, updated=now, size=size)
        bubble.add(man.id)

        # ── Bieżąca treść ──
        cid = self._content_id(name)
        if is_text:
            catom = self.phi.create_atom(cid, S=f"content:{kind}",
                                         E=content, T=T_HOT)
            catom.metadata["kind"] = kind
            catom.metadata.pop("data", None)   # wyczyść stare bajty jeśli były
            bubble.content = content           # szybki odczyt tekstu
        else:
            catom = self.phi.create_atom(cid, S=f"content:{kind}",
                                         E="", T=T_HOT)
            catom.metadata["kind"] = kind
            catom.metadata["data"] = raw       # surowe bajty w metadanych
            bubble.content = ""
        bubble.add(cid)

        return Item(name, kind,
                    text=content if is_text else None,
                    data=None if is_text else raw,
                    size=size, updated=now)

    # ── Odczyt ────────────────────────────────────────────────────────────────

    def open(self, name: str) -> Optional[Item]:
        """
        Otwórz dokument. Ogrzewa atomy (dostęp użytkownika).
        Zwraca None jeśli nie istnieje.
        """
        man = self.phi.get_atom(self._manifest_id(name))
        if man is None:
            return None
        catom = self.phi.get_atom(self._content_id(name))
        kind  = man.metadata.get("kind", "text")

        if catom is None:
            return Item(name, kind, text="" if kind == "text" else None,
                        data=None, size=0, updated=man.metadata.get("updated", 0))

        if kind == "text":
            text = catom.E or ""
            return Item(name, kind, text=text, data=None,
                        size=len(text.encode("utf-8")),
                        updated=man.metadata.get("updated", 0))
        else:
            data = catom.metadata.get("data", b"")
            return Item(name, kind, text=None, data=data,
                        size=len(data),
                        updated=man.metadata.get("updated", 0))

    def exists(self, name: str) -> bool:
        return self.phi.has_atom(self._manifest_id(name))

    # ── Lista ─────────────────────────────────────────────────────────────────

    def list(self) -> List[Dict[str, Any]]:
        """
        Lista dokumentów. Nie ogrzewa (peek) — przeglądanie nie powinno
        sztucznie podnosić temperatury.

        Sortowane: najświeższe (updated malejąco).
        """
        out = []
        for atom in self.phi.matrix.atoms():
            if atom.S != self._MANIFEST_S:
                continue
            out.append({
                "name":    atom.E,
                "kind":    atom.metadata.get("kind", "text"),
                "size":    atom.metadata.get("size", 0),
                "updated": atom.metadata.get("updated", 0),
                "state":   atom.state,
            })
        out.sort(key=lambda d: -d.get("updated", 0))
        return out

    def names(self) -> List[str]:
        return [d["name"] for d in self.list()]

    # ── Historia wersji ────────────────────────────────────────────────────────

    def versions(self, name: str) -> List[Dict[str, Any]]:
        """
        Historia wersji dokumentu. Gorące = najnowsze.
        Stygną same przez phi.tick() — naturalne, zanikające undo.
        Sortowane wg T malejąco (najświeższe pierwsze).
        """
        prefix = f"doc::{name}::v::"
        vers = []
        for atom in self.phi.matrix.atoms():
            if atom.S == self._VERSION_S and atom.id.startswith(prefix):
                vers.append({
                    "id":      atom.id,
                    "created": atom.metadata.get("created", 0),
                    "T":       round(atom.T, 1),
                    "state":   atom.state,
                    "kind":    atom.metadata.get("kind", "text"),
                })
        vers.sort(key=lambda v: -v["T"])
        return vers

    def restore_version(self, name: str, version_id: str) -> Optional[Item]:
        """Przywróć wersję jako bieżącą treść (tworzy nową wersję z aktualnej)."""
        vatom = self.phi.get_atom(version_id)
        if vatom is None:
            return None
        kind = vatom.metadata.get("kind", "text")
        if kind == "text":
            return self.save(name, vatom.E)
        else:
            return self.save(name, vatom.metadata.get("data", b""))

    # ── Usuwanie ────────────────────────────────────────────────────────────────

    def delete(self, name: str) -> bool:
        """Usuń dokument i wszystkie jego wersje."""
        if not self.exists(name):
            return False
        # zbierz wszystkie atomy tego dokumentu
        to_del = [self._manifest_id(name), self._content_id(name)]
        prefix = f"doc::{name}::"
        for atom in list(self.phi.matrix.atoms()):
            if atom.id.startswith(prefix):
                to_del.append(atom.id)
        for aid in set(to_del):
            self.phi.delete_atom(aid)
        # usuń bąbel z rejestru jeśli pusty
        b = self.phi.get_bubble(name)
        if b is not None:
            self.phi._bubbles.pop(name, None)
        return True

    def rename(self, old: str, new: str) -> bool:
        """Zmień nazwę dokumentu (zachowuje treść, gubi historię wersji)."""
        item = self.open(old)
        if item is None:
            return False
        self.save(new, item.text if item.is_text else item.data,
                  keep_version=False)
        self.delete(old)
        return True

    # ── Konserwacja ──────────────────────────────────────────────────────────

    def tick(self) -> Dict[str, int]:
        """
        Jeden krok termodynamiczny — stare wersje stygną, martwe znikają.
        Wywoływać okresowo (scheduler systemu albo po każdej operacji).
        """
        return self.phi.tick()

    def stats(self) -> Dict[str, Any]:
        docs = self.list()
        return {
            "documents": len(docs),
            "by_kind":   {k: sum(1 for d in docs if d["kind"] == k)
                          for k in ("text", "audio", "image", "binary")},
            "phi":       self.phi.snapshot(),
        }