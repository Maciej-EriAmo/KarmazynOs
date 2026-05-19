"""
karmazyn_browser.py — Tekstowa Przegladarka HTTP KarmazynOS v1.0
================================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Strony internetowe jako atomy phi-space:
  - swiezo pobrana = HOT
  - w cache = stygnie
  - zakładki = babel 'browser_bookmarks'
  - historia = hologram 'browser_history'

Renderowanie HTML → tekst:
  - czysty tekst bez zewnetrznych zaleznoci (tylko stdlib html.parser)
  - linki numerowane [1], [2]... do nawigacji
  - naglowki wyroznianie
  - tabele uproszczone do list

Uzycie w shellu:
  BROWSE <url>            — otworz strone
  BROWSE BACK             — wstecz
  BROWSE FORWARD          — naprzod
  BROWSE LINKS            — pokaz linki
  BROWSE FOLLOW <n>       — podaz za linkiem nr n
  BROWSE RELOAD           — odswierz
  BROWSE FIND <tekst>     — szukaj na stronie
  BROWSE SAVE <babel>     — zapisz strone jako babl
  BROWSE BM               — dodaj do zakladek
  BROWSE BOOKMARKS        — lista zakladek
  BROWSE SOURCE           — pokaz zrodlo HTML
  BROWSE HISTORY          — historia
  BROWSE SCROLL <n>       — przewin o n linii
"""

import html
import os
import re
import textwrap
import time
import urllib.parse
from collections import deque
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple

# karmazyn_net jest opcjonalne — fallback na urllib
try:
    from karmazyn_net import http_get, HttpResponse
    HAS_NET = True
except ImportError:
    HAS_NET = False
    import urllib.request, urllib.error

    @dataclass
    class HttpResponse:
        url: str; status: int; content_type: str
        body: bytes; headers: dict; elapsed_ms: float
        @property
        def text(self):
            for enc in ("utf-8", "utf-8-sig", "latin-1"):
                try: return self.body.decode(enc)
                except: continue
            return self.body.decode("utf-8", errors="replace")
        def ok(self): return 200 <= self.status < 300

    def http_get(url, headers=None, timeout=15.0):
        hdrs = {"User-Agent": "KarmazynBrowser/1.0", **(headers or {})}
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return HttpResponse(url=url, status=r.status,
                    content_type=r.headers.get("Content-Type",""),
                    body=r.read(), headers=dict(r.headers), elapsed_ms=0)
        except Exception as e:
            return HttpResponse(url=url, status=0, content_type="",
                body=str(e).encode(), headers={}, elapsed_ms=0)

BOOKMARKS_LABEL = "browser_bookmarks"
HISTORY_LABEL   = "browser_history"
CACHE_DIR       = ".bubbles/store/browser_cache"
DISPLAY_WIDTH   = 80    # szerokosc renderowania tekstu
PAGE_SIZE       = 40    # linii na "ekran"


# ─── Parser HTML → tekst ──────────────────────────────────────────────────────

@dataclass
class ParsedPage:
    title:    str
    text:     str
    links:    List[Tuple[str, str]]   # [(url, tekst), ...]
    headings: List[str]
    raw_html: str
    url:      str

    def lines(self) -> List[str]:
        return self.text.splitlines()


class _TextExtractor(HTMLParser):
    """Konwertuje HTML na czysty tekst z zachowaniem struktury."""

    SKIP_TAGS = {"script", "style", "noscript", "head",
                 "meta", "link", "svg", "path", "img"}
    BLOCK_TAGS = {"p", "div", "article", "section", "main",
                  "header", "footer", "nav", "aside",
                  "li", "td", "th", "dt", "dd", "br"}
    HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
    PRE_TAGS = {"pre", "code"}

    def __init__(self, base_url: str = "", width: int = DISPLAY_WIDTH):
        super().__init__()
        self.base_url = base_url
        self.width    = width
        self._buf:    List[str] = []
        self._links:  List[Tuple[str, str]] = []
        self._link_url:  str  = ""
        self._link_text: List[str] = []
        self._in_link    = False
        self._in_pre     = False
        self._skip_depth = 0
        self._title      = ""
        self._in_title   = False
        self._headings:  List[str] = []
        self._cur_heading: str = ""
        self._in_heading = False
        self._heading_level = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs_dict = dict(attrs)

        if tag in self.SKIP_TAGS and tag != "head":
            self._skip_depth += 1
            return
        if self._skip_depth > 0:
            return

        if tag == "title":
            self._in_title = True
        elif tag in self.HEADING_TAGS:
            self._in_heading = True
            self._heading_level = int(tag[1])
            self._cur_heading   = ""
            self._buf.append("\n")
        elif tag == "a":
            href = attrs_dict.get("href", "")
            if href:
                self._link_url = _resolve_url(href, self.base_url)
                self._in_link  = True
                self._link_text = []
        elif tag in self.PRE_TAGS:
            self._in_pre = True
        elif tag in self.BLOCK_TAGS:
            if tag == "li":
                self._buf.append("\n  • ")
            else:
                self._buf.append("\n")
        elif tag == "hr":
            self._buf.append("\n" + "─" * self.width + "\n")
        elif tag in ("strong", "b"):
            self._buf.append("**")
        elif tag in ("em", "i"):
            self._buf.append("_")

    def handle_endtag(self, tag):
        tag = tag.lower()

        if self._skip_depth > 0:
            if tag in self.SKIP_TAGS and tag != "head":
                self._skip_depth -= 1
            return

        if tag == "title":
            self._in_title = False
        elif tag in self.HEADING_TAGS:
            if self._cur_heading.strip():
                prefix = "#" * self._heading_level + " "
                line   = prefix + self._cur_heading.strip()
                sep    = "═" * min(len(line), self.width) if self._heading_level == 1 else \
                         "─" * min(len(line), self.width)
                self._buf.append(line + "\n" + sep + "\n")
                self._headings.append(self._cur_heading.strip())
            self._in_heading = False
            self._cur_heading = ""
        elif tag == "a":
            if self._in_link and self._link_url:
                link_text = "".join(self._link_text).strip()
                if link_text:
                    idx = len(self._links) + 1
                    self._links.append((self._link_url, link_text))
                    self._buf.append(f" [{idx}]")
            self._in_link    = False
            self._link_url   = ""
            self._link_text  = []
        elif tag in self.PRE_TAGS:
            self._in_pre = False
        elif tag in self.BLOCK_TAGS:
            self._buf.append("\n")
        elif tag in ("strong", "b"):
            self._buf.append("**")
        elif tag in ("em", "i"):
            self._buf.append("_")

    def handle_data(self, data):
        if self._skip_depth > 0:
            return

        if self._in_title:
            self._title += data
            return

        if self._in_heading:
            self._cur_heading += data
            return

        if self._in_link:
            self._link_text.append(data)

        if self._in_pre:
            self._buf.append(data)
        else:
            # Normalizuj biale znaki
            clean = re.sub(r"\s+", " ", data)
            self._buf.append(clean)

    def handle_entityref(self, name):
        char = html.unescape(f"&{name};")
        self.handle_data(char)

    def handle_charref(self, name):
        char = html.unescape(f"&#{name};")
        self.handle_data(char)

    def result(self, raw_html: str, url: str) -> ParsedPage:
        raw_text = "".join(self._buf)

        # Zawijanie linii (poza blokami <pre>)
        lines_out = []
        for line in raw_text.splitlines():
            if len(line) <= self.width or line.startswith("─") or line.startswith("═"):
                lines_out.append(line)
            else:
                wrapped = textwrap.fill(line, width=self.width,
                                        break_long_words=True,
                                        break_on_hyphens=True)
                lines_out.extend(wrapped.splitlines())

        # Usuniecie nadmiernych pustych linii (max 2 z rzedu)
        clean_lines = []
        blank_count = 0
        for line in lines_out:
            if not line.strip():
                blank_count += 1
                if blank_count <= 2:
                    clean_lines.append("")
            else:
                blank_count = 0
                clean_lines.append(line)

        return ParsedPage(
            title    = self._title.strip() or url,
            text     = "\n".join(clean_lines),
            links    = self._links,
            headings = self._headings,
            raw_html = raw_html,
            url      = url,
        )


def parse_html(html_text: str, url: str = "",
               width: int = DISPLAY_WIDTH) -> ParsedPage:
    """Parsuje HTML i zwraca ParsedPage z tekstem i linkami."""
    parser = _TextExtractor(base_url=url, width=width)
    try:
        parser.feed(html_text)
    except Exception:
        pass
    return parser.result(html_text, url)


def _resolve_url(href: str, base: str) -> str:
    """Rozwiazuje wzgledny URL wzgledem bazy."""
    if not href or href.startswith(("javascript:", "mailto:", "#")):
        return ""
    try:
        return urllib.parse.urljoin(base, href)
    except Exception:
        return href


# ─── Glowna klasa przegladarki ────────────────────────────────────────────────

class KarmazynBrowser:
    """
    Tekstowa przegladarka HTTP.
    Historia nawigacji jako hologram w phi-space.
    Zakładki jako babl 'browser_bookmarks'.
    Cache stron jako atomy (stygna z czasem).
    """

    T_FRESH   = 80.0   # swiezo pobrana strona
    T_CACHED  = 45.0   # z cache, kilka minut
    T_STALE   = 20.0   # stara, > godzina

    def __init__(self, runtime, width: int = DISPLAY_WIDTH):
        self.runtime    = runtime
        self.width      = width
        self._history:  deque = deque(maxlen=50)   # stack URL
        self._forward:  deque = deque(maxlen=50)   # do naprzod
        self._current:  Optional[ParsedPage] = None
        self._scroll:   int  = 0   # aktualna linia scrollu
        self._cache:    Dict[str, Tuple[ParsedPage, float]] = {}  # url→(page,ts)
        self._bookmarks: Dict[str, str] = {}   # url→tytul

        os.makedirs(CACHE_DIR, exist_ok=True)
        self._load_bookmarks()

    # ── Nawigacja ─────────────────────────────────────────────────────────────

    def go(self, url: str, force_reload: bool = False) -> Tuple[bool, str]:
        """
        Otwiera URL. Uzywa cache jesli dostepny i swiezy.
        Zwraca (ok, tresc_do_wyswietlenia).
        """
        # Dodaj protokol jesli brak
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        # Sprawdz cache (swiezy = < 5 minut)
        if not force_reload and url in self._cache:
            page, ts = self._cache[url]
            if time.time() - ts < 300:
                if self._current:
                    self._history.append(self._current.url)
                    self._forward.clear()
                self._current = page
                self._scroll  = 0
                return True, self._render_current()

        # Pobierz strone
        t0   = time.time()
        resp = http_get(url, headers={"User-Agent": "KarmazynBrowser/1.0 (KarmazynOS)"})
        elapsed = time.time() - t0

        if not resp.ok():
            return False, f"HTTP {resp.status}: {url}"

        ct = resp.content_type.lower()
        if "html" not in ct and "text" not in ct:
            return False, (f"Nieobslugiwany typ: {resp.content_type}\n"
                           f"URL: {url}")

        page = parse_html(resp.text, url=url, width=self.width)
        self._cache[url] = (page, time.time())

        # Atom dla tej strony
        label = "www_" + re.sub(r"[^a-z0-9]", "_",
                                url.lower().replace("https://","")
                                          .replace("http://",""))[:20]
        try:
            if self.runtime.matrix.has_atom(label):
                atom = self.runtime.get_atom(label)
                if atom:
                    atom.T     = self.T_FRESH
                    atom.state = "HOT"
            else:
                self.runtime.create_atom(
                    label, page.title[:64], url, self.T_FRESH,
                )
        except Exception:
            pass

        if self._current:
            self._history.append(self._current.url)
            self._forward.clear()

        self._current = page
        self._scroll  = 0
        return True, self._render_current()

    def back(self) -> Tuple[bool, str]:
        if not self._history:
            return False, "Brak historii do cofniecia."
        if self._current:
            self._forward.appendleft(self._current.url)
        url = self._history.pop()
        return self.go(url)

    def forward(self) -> Tuple[bool, str]:
        if not self._forward:
            return False, "Brak stron do przodu."
        url = self._forward.popleft()
        return self.go(url)

    def reload(self) -> Tuple[bool, str]:
        if self._current is None:
            return False, "Brak aktualnej strony."
        url = self._current.url
        if url in self._cache:
            del self._cache[url]
        return self.go(url, force_reload=True)

    def follow_link(self, n: int) -> Tuple[bool, str]:
        """Podaza za linkiem numer n (1-indeksowany)."""
        if self._current is None:
            return False, "Brak aktualnej strony."
        links = self._current.links
        if not links:
            return False, "Strona nie ma linkow."
        if n < 1 or n > len(links):
            return False, f"Link {n} nie istnieje (1-{len(links)})."
        url, _ = links[n - 1]
        if not url:
            return False, f"Link {n} jest pusty lub javascript."
        return self.go(url)

    # ── Wyswietlanie ──────────────────────────────────────────────────────────

    def _render_current(self) -> str:
        """Renderuje aktualnie wyswietlana strone."""
        if self._current is None:
            return "Brak strony. Uzyj: BROWSE <url>"

        p     = self._current
        lines = p.lines()
        total = len(lines)

        # Naglowek przegladarki
        url_short = p.url[:self.width - 10]
        header = [
            "─" * self.width,
            f"  {p.title[:self.width - 4]}",
            f"  {url_short}",
            f"  Linki: {len(p.links)}  |  Linie: {total}",
            "─" * self.width,
        ]

        # Strona tekstu
        page_lines = lines[self._scroll:self._scroll + PAGE_SIZE]
        remaining  = max(0, total - self._scroll - PAGE_SIZE)

        footer_parts = [f"[{self._scroll + 1}-{min(self._scroll + PAGE_SIZE, total)}/{total}]"]
        if remaining > 0:
            footer_parts.append(f"  BROWSE SCROLL 1 aby kontynuowac ({remaining} linii)")
        footer = "─" * self.width + "\n" + "  ".join(footer_parts)

        return "\n".join(header + page_lines + [footer])

    def scroll(self, pages: int = 1) -> str:
        """Przewija o n stron."""
        if self._current is None:
            return "Brak strony."
        total         = len(self._current.lines())
        self._scroll  = max(0, min(
            self._scroll + pages * PAGE_SIZE,
            max(0, total - PAGE_SIZE),
        ))
        return self._render_current()

    def find(self, query: str) -> str:
        """Szuka tekstu na aktualnej stronie."""
        if self._current is None:
            return "Brak strony."
        q     = query.lower()
        lines = self._current.lines()
        hits  = [(i + 1, line) for i, line in enumerate(lines)
                 if q in line.lower()]
        if not hits:
            return f"Nie znaleziono: '{query}'"
        result = [f"Znaleziono '{query}' ({len(hits)} wystapien):"]
        for lineno, line in hits[:15]:
            result.append(f"  [{lineno:4}] {line[:self.width - 10]}")
        if len(hits) > 15:
            result.append(f"  ... i {len(hits)-15} wiecej")
        return "\n".join(result)

    def show_links(self) -> str:
        """Lista linkow aktualnej strony."""
        if self._current is None:
            return "Brak strony."
        links = self._current.links
        if not links:
            return "Strona nie ma linkow."
        lines = [f"Linki ({len(links)}):"]
        for i, (url, text) in enumerate(links, 1):
            url_short  = url[:50] if url else "(pusty)"
            text_short = text[:30]
            lines.append(f"  [{i:3}] {text_short:<30} {url_short}")
        return "\n".join(lines)

    def show_source(self, lines_n: int = 50) -> str:
        """Pokazuje pierwsze n linii zrodla HTML."""
        if self._current is None:
            return "Brak strony."
        src_lines = self._current.raw_html.splitlines()[:lines_n]
        return "\n".join(src_lines)

    # ── Zakladki ──────────────────────────────────────────────────────────────

    def _load_bookmarks(self) -> None:
        path = os.path.join(CACHE_DIR, "bookmarks.json")
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    self._bookmarks = json_load(f)
            except Exception:
                self._bookmarks = {}

    def _save_bookmarks(self) -> None:
        path = os.path.join(CACHE_DIR, "bookmarks.json")
        import json as _json
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(self._bookmarks, f, ensure_ascii=False, indent=2)

    def add_bookmark(self) -> str:
        if self._current is None:
            return "Brak strony do dodania."
        url   = self._current.url
        title = self._current.title
        self._bookmarks[url] = title
        self._save_bookmarks()

        # Atom zakładki
        label = "bm_" + re.sub(r"[^a-z0-9]", "_", url.lower())[:20]
        try:
            if not self.runtime.matrix.has_atom(label):
                self.runtime.create_atom(label, title[:64], url, self.T_CACHED)
        except Exception:
            pass
        return f"Dodano zakładkę: {title}"

    def list_bookmarks(self) -> str:
        if not self._bookmarks:
            return "Brak zakladek. Uzyj: BROWSE BM"
        lines = [f"Zakładki ({len(self._bookmarks)}):"]
        for i, (url, title) in enumerate(self._bookmarks.items(), 1):
            lines.append(f"  [{i:3}] {title[:35]:<35} {url[:45]}")
        return "\n".join(lines)

    def go_bookmark(self, n: int) -> Tuple[bool, str]:
        urls = list(self._bookmarks.keys())
        if n < 1 or n > len(urls):
            return False, f"Zakladka {n} nie istnieje (1-{len(urls)})."
        return self.go(urls[n - 1])

    # ── Historia ──────────────────────────────────────────────────────────────

    def show_history(self) -> str:
        hist = list(self._history)
        if not hist:
            return "Historia pusta."
        lines = [f"Historia ({len(hist)}):"]
        for i, url in enumerate(reversed(hist[-20:]), 1):
            cached = url in self._cache
            mark   = "✓" if cached else " "
            lines.append(f"  [{mark}] {url[:self.width - 8]}")
        return "\n".join(lines)


def json_load(f):
    import json as _json
    return _json.load(f)


# ─── Komenda shella ───────────────────────────────────────────────────────────

def cmd_browse(args, browser: KarmazynBrowser) -> str:
    """
    BROWSE <url>            — otworz strone
    BROWSE BACK             — wstecz
    BROWSE FORWARD / FWD   — naprzod
    BROWSE RELOAD           — odswierz
    BROWSE LINKS            — lista linkow
    BROWSE FOLLOW <n>       — podaz za linkiem nr n
    BROWSE FIND <tekst>     — szukaj na stronie
    BROWSE SCROLL [n]       — przewin o n stron (domyslnie 1)
    BROWSE SOURCE [n]       — pokaz zrodlo (pierwsze n linii)
    BROWSE BM               — dodaj zakładke
    BROWSE BOOKMARKS        — lista zakladek
    BROWSE GOTO <n>         — idz do zakladki nr n
    BROWSE HISTORY          — historia
    BROWSE SAVE <label>     — zapisz strone jako atom
    """
    if not args:
        if browser._current:
            return browser._render_current()
        return "BROWSE <url>  —  np. BROWSE example.com"

    sub = args[0].upper()

    # Bezposredni URL (nie subkomenda)
    if sub.startswith("HTTP") or ("." in args[0] and sub not in (
        "BACK", "FORWARD", "FWD", "RELOAD", "LINKS", "FOLLOW",
        "FIND", "SCROLL", "SOURCE", "BM", "BOOKMARKS", "GOTO",
        "HISTORY", "SAVE",
    )):
        ok, content = browser.go(args[0])
        return content

    if sub == "BACK":
        ok, content = browser.back()
        return content

    if sub in ("FORWARD", "FWD"):
        ok, content = browser.forward()
        return content

    if sub == "RELOAD":
        ok, content = browser.reload()
        return content

    if sub == "LINKS":
        return browser.show_links()

    if sub == "FOLLOW":
        if len(args) < 2:
            return "BROWSE FOLLOW <numer_linku>"
        try:
            n = int(args[1])
        except ValueError:
            return f"Nieprawidlowy numer: {args[1]}"
        ok, content = browser.follow_link(n)
        return content

    if sub == "FIND":
        if len(args) < 2:
            return "BROWSE FIND <tekst>"
        return browser.find(" ".join(args[1:]))

    if sub == "SCROLL":
        n = int(args[1]) if len(args) > 1 else 1
        return browser.scroll(n)

    if sub == "SOURCE":
        n = int(args[1]) if len(args) > 1 else 50
        return browser.show_source(n)

    if sub == "BM":
        return browser.add_bookmark()

    if sub == "BOOKMARKS":
        return browser.list_bookmarks()

    if sub == "GOTO":
        if len(args) < 2:
            return "BROWSE GOTO <numer_zakładki>"
        try:
            n = int(args[1])
        except ValueError:
            return f"Nieprawidlowy numer: {args[1]}"
        ok, content = browser.go_bookmark(n)
        return content

    if sub == "HISTORY":
        return browser.show_history()

    if sub == "SAVE":
        if browser._current is None:
            return "Brak strony do zapisania."
        label = args[1] if len(args) > 1 else (
            "www_" + re.sub(r"[^a-z0-9]", "_",
                            browser._current.url.lower()
                                   .replace("https://","")
                                   .replace("http://",""))[:20]
        )
        try:
            browser.runtime.write(
                label,
                browser._current.title[:64],
                browser._current.url,
                browser.T_CACHED,
            )
            if browser.runtime.get_bubble(label) is None:
                browser.runtime.consolidate(label)
            return f"Zapisano jako atom/babel: {label}"
        except Exception as e:
            return f"Blad zapisu: {e}"

    # Jesli nie pasuje do zadnej subkomendy, traktuj jako URL
    ok, content = browser.go(args[0])
    return content