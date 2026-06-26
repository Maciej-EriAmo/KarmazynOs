"""
karmazyn_radio.py — Radio Internetowe KarmazynOS v1.1
======================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Stacje radiowe jako atomy phi-space:
  - słuchana stacja = HOT (T wysoka)
  - dawno niesluchana = COLD (stygaca)
  - ulubione = babel 'radio_favorites'
  - historia = ostatnie 20 stacji

Odtwarzanie:
  AudioDaemon (karmazyn_audio.py) — pełne IPC: głośność, pauza, ICY metadata
  Fallback subprocess              — brak IPC gdy brak karmazyn_audio.py

Zmiany v1.1 (poprawki recenzji):
  - _classify_T: COLD >= 10 zamiast >= 1 (TOMB realne)
  - toggle_favorite: usunięto consolidate(None)
  - RADIO ADD: URL może zawierać spacje, " ".join(args[2:])
  - play(): custom URL → SHA1 hash zamiast śmieciowej nazwy
  - Fallback subprocess: watchdog thread zapobiega zombie process
  - stop(): process.wait() POZA lockiem — usunięto potencjalny deadlock
  - cmd_radio STATUS: usunięto nieistniejące radio.player / radio._volume
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# AudioDaemon — właściwy daemon audio z IPC zamiast surowego subprocess
try:
    from karmazyn_audio import AudioDaemon
    HAS_AUDIO_DAEMON = True
except ImportError:
    HAS_AUDIO_DAEMON = False


# ─── Domyślne stacje ─────────────────────────────────────────────────────────

DEFAULT_STATIONS = {
    "polskie_radio_1":   "https://stream.polskieradio.pl/pr1/pr1.sdp.m3u8",
    "polskie_radio_3":   "https://stream.polskieradio.pl/pr3/pr3.sdp.m3u8",
    "tok_fm":            "https://stream.tokfm.pl/Tokfm/Tokfm/mp3/128/internet.mp3",
    "rmf_fm":            "https://rs6-krk2-cyfronet.rmfstream.pl/RMFFM48",
    "radio_357":         "https://radio357.pl/radio357-hd.mp3",
    "jazz_radio":        "http://jazz.streamr.ru:8000/jazz-256",
    "soma_groove_salad": "https://ice2.somafm.com/groovesalad-256-mp3",
    "soma_drone_zone":   "https://ice2.somafm.com/dronezone-256-mp3",
    "bbc_world":         "https://stream.live.vc.bbcmedia.co.uk/bbc_world_service",
    "fip_paris":         "https://icecast.radiofrance.fr/fip-midfi.mp3",
}

STATIONS_FILE   = ".bubbles/store/radio_stations.json"
FAVORITES_LABEL = "radio_favorites"


# ─── Wykrywanie odtwarzacza (fallback gdy brak AudioDaemon) ──────────────────

def _detect_player() -> Optional[str]:
    """Wykrywa dostępny odtwarzacz audio."""
    for p in ("mpv", "mplayer", "ffplay", "cvlc", "vlc"):
        if shutil.which(p):
            return p
    return None


def _build_play_cmd(player: str, url: str, volume: int = 80) -> List[str]:
    """Buduje komendę odtwarzania dla danego playera."""
    if player == "mpv":
        return ["mpv", "--no-video", "--quiet",
                f"--volume={volume}", "--term-status-msg=", url]
    if player == "mplayer":
        return ["mplayer", "-quiet", "-nolirc",
                "-volume", str(volume), url]
    if player == "ffplay":
        return ["ffplay", "-nodisp", "-autoexit",
                "-loglevel", "quiet", url]
    if player in ("cvlc", "vlc"):
        return ["cvlc", "--intf", "dummy", "--quiet", url]
    return [player, url]


# ─── Stacja ───────────────────────────────────────────────────────────────────

@dataclass
class Station:
    name:        str
    url:         str
    favorite:    bool      = False
    play_count:  int       = 0
    last_played: float     = 0.0
    tags:        List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name, "url": self.url,
            "favorite": self.favorite, "play_count": self.play_count,
            "last_played": self.last_played, "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Station":
        return cls(
            name=d["name"], url=d["url"],
            favorite=d.get("favorite", False),
            play_count=d.get("play_count", 0),
            last_played=d.get("last_played", 0.0),
            tags=d.get("tags", []),
        )


# ─── Główna klasa radia ───────────────────────────────────────────────────────

class KarmazynRadio:
    """
    Radio internetowe zintegrowane z phi-space.

    Każda stacja = atom w RUNTIME:
      label  = "radio_<nazwa>"
      S      = nazwa stacji
      E      = URL strumienia
      T      = ciepło: rośnie przy odtwarzaniu, stygnie gdy nieużywana

    Odtwarzanie przez AudioDaemon (IPC) lub fallback subprocess.
    Ulubione = bąbel 'radio_favorites' w RUNTIME.
    """

    T_PLAYING = 95.0   # aktywnie słuchana
    T_RECENT  = 65.0   # słuchana < 1h temu
    T_KNOWN   = 35.0   # słuchana < 24h temu
    T_COLD    = 15.0   # dawno niesluchana

    def __init__(self, runtime):
        self.runtime   = runtime
        self._stations: Dict[str, Station] = {}
        self._current:  Optional[str]  = None
        self._lock      = threading.Lock()

        # Fallback subprocess (gdy brak AudioDaemon)
        self._fallback_proc:   Optional[subprocess.Popen] = None
        self._fallback_thread: Optional[threading.Thread] = None

        # AudioDaemon — pełne IPC jeśli dostępny
        self._audio = AudioDaemon(runtime) if HAS_AUDIO_DAEMON else None

        self._load_stations()
        self._sync_atoms()

    # ── Persystencja ──────────────────────────────────────────────────────────

    def _load_stations(self) -> None:
        os.makedirs(os.path.dirname(STATIONS_FILE), exist_ok=True)
        if os.path.exists(STATIONS_FILE):
            try:
                with open(STATIONS_FILE, encoding="utf-8") as f:
                    for d in json.load(f):
                        s = Station.from_dict(d)
                        self._stations[s.name] = s
            except Exception:
                pass
        for name, url in DEFAULT_STATIONS.items():
            if name not in self._stations:
                self._stations[name] = Station(name=name, url=url)

    def _save_stations(self) -> None:
        os.makedirs(os.path.dirname(STATIONS_FILE), exist_ok=True)
        with open(STATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump([s.to_dict() for s in self._stations.values()],
                      f, indent=2, ensure_ascii=False)

    # ── Temperatura ───────────────────────────────────────────────────────────

    def _station_T(self, station: Station) -> float:
        if station.name == self._current:
            return self.T_PLAYING
        if station.last_played == 0.0:
            return self.T_COLD
        age_h = (time.time() - station.last_played) / 3600.0
        if age_h < 1:
            return self.T_RECENT
        if age_h < 24:
            return self.T_KNOWN
        # Stygnie liniowo poniżej T_KNOWN, ale nie niżej niż T_COLD
        return max(self.T_COLD, self.T_KNOWN - age_h * 0.5)

    @staticmethod
    def _classify_T(T: float) -> str:
        """
        BUG FIX v1.1: próg COLD zmieniony z >= 1 na >= 10.
        Poprzednio TOMB nigdy praktycznie nie wystąpił (T >= 1 = COLD
        obejmowało niemal cały zakres). Teraz TOMB jest realny dla T < 10.
        """
        if T >= 70: return "HOT"
        if T >= 30: return "WARM"
        if T >= 10: return "COLD"
        return "TOMB"

    def _sync_atoms(self) -> None:
        for name, station in self._stations.items():
            label = f"radio_{name}"
            T = self._station_T(station)
            try:
                if self.runtime.matrix.has_atom(label):
                    atom = self.runtime.get_atom(label)
                    if atom:
                        atom.T     = T
                        atom.state = self._classify_T(T)
                else:
                    self.runtime.create_atom(label, station.name, station.url, T)
            except Exception:
                pass

    # ── Odtwarzanie ───────────────────────────────────────────────────────────

    def play(self, name_or_url: str) -> Tuple[bool, str]:
        """
        Odtwarza stację po nazwie lub URL.
        Używa AudioDaemon (IPC) jeśli dostępny, fallback do subprocess.
        """
        if self._audio is None and _detect_player() is None:
            return False, ("Brak odtwarzacza. Zainstaluj:\n"
                           "  Termux: pkg install mpv\n"
                           "  Linux:  apt install mpv")

        # Znajdź stację
        station = self._stations.get(name_or_url)
        if station is None:
            q = name_or_url.lower()
            for n, s in self._stations.items():
                if q in n.lower() or q in s.url.lower():
                    station = s
                    break

        if station is None:
            # BUG FIX v1.1: SHA1 hash zamiast suffix URL.
            # "custom_live", "custom_stream", "custom_128" przestają zaśmiecać
            # listę stacji przy każdym nowym URL.
            url = name_or_url
            sid = hashlib.sha1(url.encode()).hexdigest()[:8]
            name = f"custom_{sid}"
            station = Station(name=name, url=url)
            self._stations[name] = station
        else:
            url  = station.url
            name = station.name

        self.stop(silent=True)

        # Odtwarzanie przez AudioDaemon lub fallback
        if self._audio is not None:
            ok, msg = self._audio.play(url, station_name=name)
            if not ok:
                return False, msg
        else:
            player = _detect_player()
            if player is None:
                return False, "Brak odtwarzacza. pkg install mpv"
            cmd = _build_play_cmd(player, url)
            try:
                # BUG FIX v1.1: zapisz proc PRZED startem watchdoga
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                with self._lock:
                    self._fallback_proc = proc
                self._start_fallback_watchdog()
            except Exception as e:
                return False, f"Błąd: {e}"

        with self._lock:
            self._current = name

        station.play_count  += 1
        station.last_played  = time.time()

        label = f"radio_{name}"
        try:
            if not self.runtime.matrix.has_atom(label):
                self.runtime.create_atom(label, station.name, station.url,
                                         self.T_PLAYING)
            else:
                atom = self.runtime.get_atom(label)
                if atom:
                    atom.T     = self.T_PLAYING
                    atom.state = "HOT"
        except Exception:
            pass

        self._save_stations()
        return True, f"Odtwarzam: {name}"

    def stop(self, silent: bool = False) -> str:
        """
        Zatrzymuje odtwarzanie.
        BUG FIX v1.1: process.wait() POZA lockiem — zapobiega deadlock.
        Wzorzec: pobierz proc z locka, zwolnij lock, czekaj poza lockiem.
        """
        with self._lock:
            prev = self._current
            self._current = None
            # Wyciągnij referencje poza lock — operacje na procesie mogą blokować
            fallback = self._fallback_proc
            self._fallback_proc = None

        # Operacje blokujące POZA lockiem
        if self._audio is not None:
            self._audio.stop()
        elif fallback is not None:
            try:
                fallback.terminate()
                fallback.wait(timeout=2.0)   # wait() bezpieczne — poza lockiem
            except Exception:
                try:
                    fallback.kill()
                except Exception:
                    pass

        if prev:
            label = f"radio_{prev}"
            try:
                atom = self.runtime.get_atom(label)
                if atom:
                    atom.T     = self.T_RECENT
                    atom.state = "WARM"
            except Exception:
                pass

        if silent:
            return ""
        return "Zatrzymano." + (f" (było: {prev})" if prev else "")

    def _start_fallback_watchdog(self) -> None:
        """
        BUG FIX v1.1: watchdog zapobiegający zombie process przy fallback.
        Gdy mpv/mplayer zakończy się sam (np. koniec streamu), czyści referencję
        zamiast zostawiać Popen z poll()!=None wiszący w _fallback_proc.
        """
        if (self._fallback_thread is not None
                and self._fallback_thread.is_alive()):
            return  # already running

        def _watch():
            while True:
                time.sleep(1.0)
                with self._lock:
                    proc = self._fallback_proc
                if proc is None:
                    break
                if proc.poll() is not None:
                    # Proces zakończył się sam
                    with self._lock:
                        if self._fallback_proc is proc:  # nadal ten sam proc
                            self._fallback_proc = None
                            self._current = None
                    break

        self._fallback_thread = threading.Thread(
            target=_watch, daemon=True, name="radio-watchdog")
        self._fallback_thread.start()

    def is_playing(self) -> bool:
        if self._audio is not None:
            return self._audio.is_playing()
        with self._lock:
            proc = self._fallback_proc
        return proc is not None and proc.poll() is None

    def is_paused(self) -> bool:
        if self._audio is not None:
            return self._audio.is_paused()
        return False

    def pause_toggle(self) -> str:
        if self._audio is not None:
            return self._audio.pause_toggle()
        return "Pauza niedostępna w trybie fallback (brak AudioDaemon/IPC)."

    def now_playing(self) -> Optional[str]:
        if not self.is_playing():
            with self._lock:
                self._current = None
            return None
        return self._current

    def now_playing_info(self) -> str:
        name = self.now_playing()
        if name is None:
            return "Nic nie gra."
        lines = [f"Stacja: {name}"]
        s = self._stations.get(name)
        if s:
            lines.append(f"URL:    {s.url}")
            lines.append(f"Grane:  {s.play_count}x")
        if self._audio is not None:
            track = self._audio.now_playing()
            if track and track.title and track.title != name:
                lines.append(f"Utwór:  {track.title}")
            if self._audio._use_ipc and self._audio._ipc:
                vol = self._audio._ipc.get_volume()
                if vol >= 0:
                    lines.append(f"Głośność: {vol}%")
        return "\n".join(lines)

    def set_volume(self, vol: int) -> str:
        if self._audio is not None:
            return self._audio.volume(vol)
        return f"Głośność: {max(0,min(100,vol))}% (aktywna przy następnym RADIO PLAY)"

    # ── Zarządzanie stacjami ──────────────────────────────────────────────────

    def add_station(self, name: str, url: str,
                    tags: List[str] = None) -> str:
        if name in self._stations:
            return f"Stacja '{name}' już istnieje."
        self._stations[name] = Station(name=name, url=url, tags=tags or [])
        try:
            self.runtime.create_atom(f"radio_{name}", name, url, self.T_COLD)
        except Exception:
            pass
        self._save_stations()
        return f"Dodano stację: {name}"

    def remove_station(self, name: str) -> str:
        if name not in self._stations:
            return f"Nie znaleziono stacji: {name}"
        if self._current == name:
            self.stop()
        del self._stations[name]
        try:
            label = f"radio_{name}"
            if self.runtime.matrix.has_atom(label):
                self.runtime.delete_atom(label)
        except Exception:
            pass
        self._save_stations()
        return f"Usunięto stację: {name}"

    def toggle_favorite(self, name: str) -> str:
        """
        BUG FIX v1.1: usunięto consolidate(None).
        Poprzedni kod: consolidate(FAVORITES_LABEL if has_atom(...) else None)
        Gdy has_atom() = False → consolidate(None) → ValueError w runtime.
        Teraz: konsolidujemy label stacji, nie FAVORITES_LABEL (który nie był atomem).
        """
        if name not in self._stations:
            return f"Nie znaleziono stacji: {name}"
        s = self._stations[name]
        s.favorite = not s.favorite
        self._save_stations()

        if s.favorite:
            # Konsoliduj atom stacji do bąbla ulubionych jeśli istnieje
            label = f"radio_{name}"
            try:
                if self.runtime.matrix.has_atom(label):
                    self.runtime.consolidate(label)
            except Exception:
                pass
            return f"Dodano do ulubionych: {name}"
        return f"Usunięto z ulubionych: {name}"

    # ── Listowanie ────────────────────────────────────────────────────────────

    def list_stations(self) -> List[dict]:
        """Lista stacji posortowana wg temperatury — HOT pierwsze."""
        result = []
        for name, s in self._stations.items():
            T = self._station_T(s)
            result.append({
                "name":     name,
                "url":      s.url,
                "T":        T,
                "state":    self._classify_T(T),
                "favorite": s.favorite,
                "playing":  (name == self._current),
                "plays":    s.play_count,
            })
        # BUG FIX v1.1 (zachowany): sort wg T desc, potem nazwa — semantyczny UX
        result.sort(key=lambda x: (-x["T"], x["name"]))
        return result

    def list_favorites(self) -> List[dict]:
        return [s for s in self.list_stations() if s["favorite"]]

    def search(self, query: str) -> List[dict]:
        q = query.lower()
        return [s for s in self.list_stations()
                if q in s["name"].lower() or q in s["url"].lower()]


# ─── Komenda shella ───────────────────────────────────────────────────────────

def cmd_radio(args, radio: KarmazynRadio) -> str:
    """
    RADIO                       — status
    RADIO LS [q]                — lista stacji (opcjonalnie filtruj)
    RADIO PLAY <nazwa|url>      — odtwarzaj
    RADIO STOP                  — zatrzymaj
    RADIO PAUSE                 — pauza/wznów (wymaga AudioDaemon)
    RADIO NOW                   — co gra (z metadanymi ICY)
    RADIO ADD <nazwa> <url...>  — dodaj stację (URL może mieć spacje)
    RADIO RM <nazwa>            — usuń stację
    RADIO FAV <nazwa>           — przełącz ulubioną
    RADIO FAVS                  — lista ulubionych
    RADIO VOL <0-100>           — głośność
    RADIO SEARCH <q>            — szukaj stacji
    """
    if not args:
        # BUG FIX v1.1: usunięto radio.player (nie istnieje) i radio._volume.
        # Status budowany z AudioDaemon jeśli dostępny.
        now    = radio.now_playing()
        lines  = [f"Stacji:  {len(radio._stations)}",
                  f"Teraz:   {now or '(nic nie gra)'}"]
        if radio._audio is not None:
            cap = radio._audio.capabilities()
            lines.insert(0, f"Daemon:  AudioDaemon (IPC={'aktywne' if cap['use_ipc'] else 'niedostępne'})")
            lines.insert(1, f"Player:  {cap['mpv_path'] or 'nie znaleziono'}")
            lines.insert(2, f"Głośność:{cap['volume']}%")
        else:
            player = _detect_player()
            lines.insert(0, f"Player:  {player or 'nie znaleziono'} (tryb fallback)")
        return "\n".join(lines)

    sub = args[0].upper()

    if sub == "LS":
        q        = args[1].lower() if len(args) > 1 else ""
        stations = radio.search(q) if q else radio.list_stations()
        if not stations:
            return f"Brak stacji{f' dla: {q}' if q else ''}."
        lines = []
        for s in stations:
            fav   = " ♥" if s["favorite"] else "  "
            play  = " ▶" if s["playing"]  else "  "
            state = s["state"][0]  # H/W/C/T
            lines.append(
                f"{play}{fav} {s['name']:<25} T={s['T']:4.0f} [{state}]"
                f" [{s['plays']}x] {s['url'][:40]}"
            )
        return "\n".join(lines)

    if sub == "PLAY":
        if len(args) < 2:
            return "RADIO PLAY <nazwa|url>"
        ok, msg = radio.play(" ".join(args[1:]))
        return msg

    if sub == "STOP":
        return radio.stop()

    if sub == "PAUSE":
        return radio.pause_toggle()

    if sub == "NOW":
        return radio.now_playing_info()

    if sub == "ADD":
        if len(args) < 3:
            return "RADIO ADD <nazwa> <url>"
        # BUG FIX v1.1: " ".join(args[2:]) — URL może zawierać spacje
        return radio.add_station(args[1], " ".join(args[2:]))

    if sub == "RM":
        if len(args) < 2:
            return "RADIO RM <nazwa>"
        return radio.remove_station(args[1])

    if sub == "FAV":
        if len(args) < 2:
            return "RADIO FAV <nazwa>"
        return radio.toggle_favorite(args[1])

    if sub == "FAVS":
        favs = radio.list_favorites()
        if not favs:
            return "Brak ulubionych. Użyj: RADIO FAV <nazwa>"
        lines = []
        for s in favs:
            play = " ▶" if s["playing"] else "  "
            lines.append(f"{play} ♥ {s['name']:<25} {s['url'][:45]}")
        return "\n".join(lines)

    if sub == "VOL":
        if len(args) < 2:
            # Pokaż aktualną głośność z AudioDaemon jeśli dostępny
            if radio._audio is not None:
                vol = radio._audio._volume
                return f"Głośność: {vol}%"
            return "RADIO VOL <0-100>"
        try:
            return radio.set_volume(int(args[1]))
        except ValueError:
            return "RADIO VOL <0-100>"

    if sub == "SEARCH":
        if len(args) < 2:
            return "RADIO SEARCH <zapytanie>"
        q       = " ".join(args[1:])
        results = radio.search(q)
        if not results:
            return f"Brak wyników dla: {q}"
        lines = [f"Wyniki dla '{q}':"]
        for s in results:
            lines.append(f"  {s['name']:<25} {s['url'][:50]}")
        return "\n".join(lines)

    # Nieznana subkomenda — wyświetl status
    return cmd_radio([], radio)