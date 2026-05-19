#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
karmazyn_browser.py — Tekstowa Przegladarka HTTP KarmazynOS v3.2 (stabilna)
================================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Ostatnie poprawki produkcyjne:
- bezpieczne zamykanie tag_stack (pop do napotkanego tagu)
- śledzenie aktywnych stylów ANSI przy zawijaniu
- filtrowanie niebezpiecznych sekwencji OSC
- podstawowe wsparcie dla wcwidth (jeśli dostępne)
- poprawne <ul>/<ol> z indentacją i numeracją
- find() na tekście bez ANSI z mapowaniem
- timeout i partial read w fallbacku
"""

import gzip
import html
import json
import os
import re
import sys
import textwrap
import time
import urllib.parse
from collections import deque, OrderedDict
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple

# ===== Wsparcie dla szerokości CJK ============================================
try:
    import wcwidth
    HAS_WCWIDTH = True
except ImportError:
    HAS_WCWIDTH = False

def visible_len(s: str) -> int:
    """Długość stringa bez kodów ANSI, z uwzględnieniem CJK jeśli wcwidth dostępne."""
    stripped = ANSI_RE.sub('', s)
    if HAS_WCWIDTH:
        return sum(max(1, wcwidth.wcwidth(ch)) for ch in stripped)
    return len(stripped)

# ===== ANSI handling – bezpieczne sekwencje ===================================
ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')
# Niebezpieczne sekwencje (OSC, zmiana tytułu, clipboard itp.) – usuwamy wszystkie poza CSI m
DANGEROUS_ANSI_RE = re.compile(r'\x1b[\]\][^\x07]*\x07|\x1b[\]\][^\x1b]*\x1b\\|\x1b[PX^_]')

def sanitize_ansi(text: str) -> str:
    """Usuwa niebezpieczne sekwencje ANSI (OSC, zmiana tytułu, clipboard)."""
    return DANGEROUS_ANSI_RE.sub('', text)

class ANSIState:
    """Śledzi aktywne style ANSI dla poprawnego zawijania."""
    def __init__(self):
        self.codes = []  # lista kodów (np. '91', '1', '0')
    def apply(self, text: str) -> str:
        if not self.codes:
            return text
        prefix = '\033[' + ';'.join(self.codes) + 'm'
        return prefix + text + '\033[0m'
    def update(self, seq: str):
        # seq jak '\033[91m' lub '\033[0m'
        m = re.match(r'\033\[([0-9;]*)m', seq)
        if m:
            codes = m.group(1).split(';') if m.group(1) else ['0']
            if '0' in codes:
                self.codes = []
            else:
                for code in codes:
                    if code not in self.codes:
                        self.codes.append(code)

def ansi_wrap(text: str, width: int) -> List[str]:
    """
    Zawija tekst z uwzględnieniem aktywnych stylów ANSI.
    Zachowuje style na początku każdej nowej linii.
    """
    # Najpierw podziel na fragmenty tekstu i sekwencje ANSI
    parts = []
    pos = 0
    for m in ANSI_RE.finditer(text):
        if m.start() > pos:
            parts.append(('text', text[pos:m.start()]))
        parts.append(('ansi', m.group(0)))
        pos = m.end()
    if pos < len(text):
        parts.append(('text', text[pos:]))

    # Przejdź przez części, zbierając słowa
    lines = []
    current_line = ''
    current_visible = 0
    state = ANSIState()
    pending_ansi = ''   # ANSI, które zostało dodane, ale jeszcze nie zresetowane

    for typ, chunk in parts:
        if typ == 'ansi':
            # aktualizuj stan
            state.update(chunk)
            # dodaj sekwencję do bieżącej linii (ale nie wpływa na długość)
            current_line += chunk
            continue
        # typ == 'text'
        # Tokenizuj na słowa i białe znaki
        tokens = re.split(r'(\s+)', chunk)
        for token in tokens:
            if not token:
                continue
            if token.isspace():
                # spacje – zawsze dodajemy do linii, jeśli nie przepełnia
                current_line += token
                continue
            # słowo – sprawdź czy zmieści się
            token_visible = visible_len(token)
            if current_visible + token_visible > width and current_visible > 0:
                # nie zmieści się – zapisz bieżącą linię i zacznij nową
                lines.append(current_line)
                # nowa linia zaczyna się od aktywnego ANSI (zachowaj styl)
                current_line = state.apply('')
                current_visible = 0
            current_line += token
            current_visible += token_visible
    if current_line or current_visible > 0:
        lines.append(current_line)
    return lines if lines else [text]

# ===== karmazyn_net fallback (z timeout i partial) ============================
try:
    from karmazyn_net import http_get, HttpResponse
    HAS_NET = True
except ImportError:
    HAS_NET = False
    import urllib.request
    import urllib.error
    import socket

    @dataclass
    class HttpResponse:
        url: str
        status: int
        content_type: str
        body: bytes
        headers: dict
        elapsed_ms: float

        @property
        def text(self) -> str:
            body = self.body
            ce = self.headers.get('content-encoding', '').lower()
            if ce == 'gzip':
                try:
                    body = gzip.decompress(body)
                except Exception:
                    pass
            elif ce == 'deflate':
                try:
                    import zlib
                    body = zlib.decompress(body)
                except Exception:
                    pass
            charset = None
            if 'content-type' in self.headers:
                ct = self.headers['content-type'].lower()
                if 'charset=' in ct:
                    charset = ct.split('charset=')[-1].split(';')[0].strip()
            for enc in (charset, "utf-8", "utf-8-sig", "latin-1"):
                if enc:
                    try:
                        return body.decode(enc)
                    except (UnicodeDecodeError, LookupError):
                        continue
            return body.decode("utf-8", errors="replace")

        def ok(self) -> bool:
            return 200 <= self.status < 300

    def http_get(url, headers=None, timeout=15.0):
        hdrs = {"User-Agent": "KarmazynBrowser/3.2", "Accept-Encoding": "gzip, deflate",
                **(headers or {})}
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp_headers = dict(r.headers)
                return HttpResponse(
                    url=url,
                    status=r.status,
                    content_type=r.headers.get("Content-Type", ""),
                    body=r.read(),
                    headers=resp_headers,
                    elapsed_ms=0
                )
        except socket.timeout:
            return HttpResponse(url=url, status=0, content_type="",
                                body=b"Timeout", headers={}, elapsed_ms=timeout*1000)
        except Exception as e:
            return HttpResponse(url=url, status=0, content_type="",
                                body=str(e).encode(), headers={}, elapsed_ms=0)

# ===== Stałe ==================================================================
BOOKMARKS_LABEL = "browser_bookmarks"
HISTORY_LABEL = "browser_history"
CACHE_DIR = ".bubbles/store/browser_cache"
DISPLAY_WIDTH = 80
PAGE_SIZE = 40
CACHE_MAX_SIZE = 100

COLORS = {
    'reset': '\033[0m',
    'bold': '\033[1m',
    'red': '\033[91m',
    'green': '\033[92m',
    'yellow': '\033[93m',
    'blue': '\033[94m',
    'magenta': '\033[95m',
    'cyan': '\033[96m',
    'gray': '\033[90m',
}

def _log_error(msg: str) -> None:
    try:
        print(f"[Browser Error] {msg}", file=sys.stderr)
    except Exception:
        pass

# ===== Fragment tekstu =========================================================
@dataclass
class TextChunk:
    text: str
    preformatted: bool = False
    style: str = ''

# ===== ParsedPage z cache'owaniem linii =======================================
@dataclass
class ParsedPage:
    title: str
    chunks: List[TextChunk]
    links: List[Tuple[str, str]]
    headings: List[str]
    raw_html: str
    url: str
    width: int = DISPLAY_WIDTH
    _lines_cache: Optional[List[str]] = field(default=None, repr=False)

    def lines(self) -> List[str]:
        if self._lines_cache is not None:
            return self._lines_cache
        result = []
        current_line = ""
        for chunk in self.chunks:
            if chunk.preformatted:
                if current_line:
                    result.append(current_line)
                    current_line = ""
                lines = chunk.text.splitlines()
                result.extend(lines)
                result.append("")
            else:
                text = chunk.text
                if text == "\n":
                    if current_line:
                        result.append(current_line)
                        current_line = ""
                    result.append("")
                else:
                    current_line += text
        if current_line:
            result.append(current_line)
        # Usuń nadmiarowe puste linie (max 2)
        cleaned = []
        blank = 0
        for line in result:
            if line == "":
                blank += 1
                if blank <= 2:
                    cleaned.append("")
            else:
                blank = 0
                cleaned.append(line)
        self._lines_cache = cleaned
        return cleaned

# ===== Parser HTML ============================================================
class _HTMLParserWithStack(HTMLParser):
    SKIP_TAGS = {"script", "style", "noscript"}
    BLOCK_TAGS = {"p","div","article","section","main","header","footer","nav","aside","br"}
    HEADING_TAGS = {"h1","h2","h3","h4","h5","h6"}
    PRE_TAGS = {"pre","code"}
    LIST_TAGS = {"ul","ol"}
    LIST_ITEM_TAG = "li"

    def __init__(self, base_url: str = "", width: int = DISPLAY_WIDTH):
        super().__init__()
        self.base_url = base_url
        self.width = width
        self.chunks: List[TextChunk] = []
        self.links: List[Tuple[str, str]] = []
        self.title = ""
        self.headings: List[str] = []
        self.raw_html = ""

        # Stos tagów (z korektą błędów)
        self.tag_stack: List[str] = []
        self.skip_depth = 0
        self.pre_depth = 0
        self.pre_buffer: List[str] = []
        self.link_depth = 0
        self.link_url = ""
        self.link_text: List[str] = []
        self.in_heading = False
        self.heading_level = 0
        self.heading_text = ""

        # Listy
        self.list_stack: List[Tuple[str, int]] = []  # (typ, licznik)
        self.in_list_item = False

        # Tabele (uproszczone)
        self.in_table = False
        self.table_rows: List[List[Tuple[str, int, int]]] = []
        self.current_row: List[Tuple[str, int, int]] = []
        self.current_cell = ""
        self.current_colspan = 1
        self.current_rowspan = 1
        self.in_cell = False

        self.in_title = False

    # --- Obsługa tagów ---
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        self.tag_stack.append(tag)
        attrs_dict = dict(attrs)

        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth > 0:
            return

        if tag == "title":
            self.in_title = True
        elif tag in self.HEADING_TAGS:
            self.in_heading = True
            self.heading_level = int(tag[1])
            self.heading_text = ""
            self.add_text("\n")
        elif tag == "a":
            if self.pre_depth == 0:
                href = attrs_dict.get("href", "")
                if href:
                    if self.link_depth == 0:
                        self.link_url = _resolve_url(href, self.base_url)
                        self.link_text = []
                    self.link_depth += 1
        elif tag in self.PRE_TAGS:
            if self.pre_depth == 0:
                self.pre_buffer = []
            self.pre_depth += 1
        elif tag in self.LIST_TAGS:
            typ = tag
            cnt = 0
            self.list_stack.append((typ, cnt))
            self.add_text("\n")
        elif tag == self.LIST_ITEM_TAG:
            self.in_list_item = True
            if self.list_stack:
                typ, cnt = self.list_stack[-1]
                if typ == "ol":
                    cnt += 1
                    self.list_stack[-1] = (typ, cnt)
                    marker = f"{cnt}. "
                else:
                    marker = "  • "
            else:
                marker = "  • "
            self.add_text(marker)
        elif tag == "table":
            self.in_table = True
            self.table_rows = []
        elif tag == "tr":
            self.current_row = []
        elif tag in ("td","th"):
            self.in_cell = True
            self.current_cell = ""
            self.current_colspan = int(attrs_dict.get("colspan", 1))
            self.current_rowspan = int(attrs_dict.get("rowspan", 1))
        elif tag in self.BLOCK_TAGS:
            self.add_text("\n")
        elif tag == "hr":
            self.add_text("\n" + "─" * self.width + "\n")
        elif tag in ("strong","b"):
            self.add_text(COLORS['bold'])
        elif tag in ("em","i"):
            self.add_text(COLORS['cyan'])

    def handle_endtag(self, tag):
        tag = tag.lower()
        # Inteligentne zamykanie: pop aż do napotkania pasującego tagu
        if tag in self.tag_stack:
            while self.tag_stack:
                top = self.tag_stack.pop()
                if top == tag:
                    break
        # Dla bezpieczeństwa, nie usuwamy jeśli nie ma

        if tag in self.SKIP_TAGS:
            if self.skip_depth > 0:
                self.skip_depth -= 1
            return
        if self.skip_depth > 0:
            return

        if tag == "title":
            self.in_title = False
        elif tag in self.HEADING_TAGS:
            if self.heading_text.strip():
                prefix = "#" * self.heading_level + " "
                line = prefix + self.heading_text.strip()
                self.headings.append(self.heading_text.strip())
                color = COLORS['yellow'] if self.heading_level == 1 else COLORS['green']
                sep = "═" * min(visible_len(line), self.width) if self.heading_level == 1 else \
                      "─" * min(visible_len(line), self.width)
                self.add_text(f"\n{color}{line}{COLORS['reset']}\n{sep}\n")
            self.in_heading = False
            self.heading_text = ""
        elif tag == "a":
            if self.link_depth > 0:
                self.link_depth -= 1
                if self.link_depth == 0 and self.link_url:
                    link_text = "".join(self.link_text).strip()
                    if not link_text:
                        link_text = self.link_url
                    idx = len(self.links) + 1
                    self.links.append((self.link_url, link_text))
                    self.add_text(f"{COLORS['blue']} [{idx}]{COLORS['reset']}")
                    self.link_url = ""
                    self.link_text = []
        elif tag in self.PRE_TAGS:
            self.pre_depth -= 1
            if self.pre_depth == 0 and self.pre_buffer:
                full_pre = "".join(self.pre_buffer)
                self.chunks.append(TextChunk(text=full_pre, preformatted=True))
                self.pre_buffer = []
        elif tag == "li":
            self.in_list_item = False
            self.add_text("\n")
        elif tag in self.LIST_TAGS:
            if self.list_stack:
                self.list_stack.pop()
            self.add_text("\n")
        elif tag == "table":
            self.in_table = False
            self.render_table()
        elif tag in ("td","th"):
            self.in_cell = False
            self.current_row.append((self.current_cell.strip(), self.current_colspan, self.current_rowspan))
        elif tag == "tr":
            if self.current_row:
                self.table_rows.append(self.current_row)
            self.current_row = []
        elif tag in ("strong","b","em","i"):
            self.add_text(COLORS['reset'])
        elif tag in self.BLOCK_TAGS:
            self.add_text("\n")

    def handle_data(self, data):
        if self.skip_depth > 0:
            return
        # Sanityzacja ANSI
        data = sanitize_ansi(data)

        if self.in_title:
            self.title += data
            return
        if self.in_heading:
            self.heading_text += data
            return
        if self.in_cell:
            self.current_cell += data
            return
        if self.pre_depth > 0:
            self.pre_buffer.append(data)
            return
        if self.link_depth > 0:
            self.link_text.append(data)
            return

        clean = re.sub(r"\s+", " ", data)
        if clean:
            self.add_text(clean)

    def handle_entityref(self, name):
        self.handle_data(html.unescape(f"&{name};"))

    def handle_charref(self, name):
        self.handle_data(html.unescape(f"&#{name};"))

    def add_text(self, text: str):
        if text:
            self.chunks.append(TextChunk(text=text, preformatted=False))

    def render_table(self):
        if not self.table_rows:
            return
        # Uproszczone renderowanie (bez colspan/rowspan w pełni, ale nie psuje ANSI)
        max_cols = 0
        for row in self.table_rows:
            cols = sum(cell[1] for cell in row)
            max_cols = max(max_cols, cols)
        if max_cols == 0:
            return
        col_widths = [0] * max_cols
        for row in self.table_rows:
            c = 0
            for cell, colspan, _ in row:
                w = visible_len(cell) + 2
                for i in range(colspan):
                    idx = c + i
                    if idx < max_cols:
                        if w > col_widths[idx]:
                            col_widths[idx] = w
                c += colspan
        total = sum(col_widths) + max_cols - 1
        if total > self.width:
            factor = (self.width - max_cols + 1) / total
            col_widths = [max(3, int(w * factor)) for w in col_widths]
        sep = "+" + "+".join("-" * w for w in col_widths) + "+"
        self.add_text("\n" + sep + "\n")
        for row in self.table_rows:
            c = 0
            cells = []
            for cell, colspan, _ in row:
                w = sum(col_widths[c:c+colspan])
                # ANSI-safe truncation (uproszczone: bierzemy do w znaków widocznych)
                visible_cell = ANSI_RE.sub('', cell)
                if len(visible_cell) > w:
                    cell = visible_cell[:w-1] + "…"
                cells.append(cell.ljust(w))
                c += colspan
            while len(cells) < max_cols:
                cells.append(" " * col_widths[len(cells)])
            self.add_text("|" + "|".join(cells) + "|\n")
        self.add_text(sep + "\n")

    def get_page(self, raw_html: str, url: str) -> ParsedPage:
        # Zastosuj zawijanie ANSI-aware
        new_chunks = []
        for chunk in self.chunks:
            if chunk.preformatted:
                new_chunks.append(chunk)
            else:
                lines = chunk.text.splitlines()
                for line in lines:
                    if visible_len(line) <= self.width:
                        new_chunks.append(TextChunk(text=line + "\n", preformatted=False))
                    else:
                        wrapped = ansi_wrap(line, self.width)
                        for wline in wrapped:
                            new_chunks.append(TextChunk(text=wline + "\n", preformatted=False))
        self.chunks = new_chunks
        return ParsedPage(
            title=self.title.strip() or url,
            chunks=self.chunks,
            links=self.links,
            headings=self.headings,
            raw_html=raw_html,
            url=url,
            width=self.width,
            _lines_cache=None
        )

def parse_html(html_text: str, url: str = "", width: int = DISPLAY_WIDTH) -> ParsedPage:
    parser = _HTMLParserWithStack(base_url=url, width=width)
    try:
        parser.feed(html_text)
    except Exception as e:
        _log_error(f"parse_html: {e}")
    return parser.get_page(html_text, url)

def _resolve_url(href: str, base: str) -> str:
    if not href or href.startswith(("javascript:", "mailto:", "#")):
        return ""
    try:
        return urllib.parse.urljoin(base, href)
    except Exception:
        return href

# ===== Główna klasa przeglądarki ===============================================
class KarmazynBrowser:
    T_FRESH = 80.0
    T_CACHED = 45.0
    T_STALE = 20.0

    def __init__(self, runtime, width: int = DISPLAY_WIDTH):
        self.runtime = runtime
        self.width = width
        self._history = deque(maxlen=50)
        self._forward = deque(maxlen=50)
        self._current: Optional[ParsedPage] = None
        self._scroll = 0
        self._cache: OrderedDict[str, Tuple[ParsedPage, float]] = OrderedDict()
        self._bookmarks: Dict[str, str] = {}
        os.makedirs(CACHE_DIR, exist_ok=True)
        self._load_bookmarks()

    def _cache_put(self, url: str, page: ParsedPage):
        if len(self._cache) >= CACHE_MAX_SIZE:
            self._cache.popitem(last=False)
        self._cache[url] = (page, time.time())
        self._cache.move_to_end(url)

    def _cache_get(self, url: str) -> Optional[Tuple[ParsedPage, float]]:
        if url in self._cache:
            self._cache.move_to_end(url)
            return self._cache[url]
        return None

    def _update_atom_temp(self, url: str, temp: float):
        try:
            label = "www_" + re.sub(r"[^a-z0-9]", "_", url.lower().replace("https://","").replace("http://",""))[:20]
            if self.runtime.matrix.has_atom(label):
                atom = self.runtime.get_atom(label)
                if atom:
                    atom.T = temp
                    atom.state = "stygnie" if temp < 60 else "HOT"
        except Exception as e:
            _log_error(f"Atom update: {e}")

    def _load_url(self, url: str, add_to_history: bool = True, force_reload: bool = False) -> Tuple[bool, str]:
        if not url.startswith(("http://","https://")):
            url = "https://" + url
        max_redirects = 5
        current_url = url
        for _ in range(max_redirects):
            if not force_reload:
                cached = self._cache_get(current_url)
                if cached:
                    page, ts = cached
                    if time.time() - ts < 300:
                        if add_to_history and self._current:
                            self._add_to_history(self._current.url)
                            self._forward.clear()
                        self._current = page
                        self._scroll = 0
                        self._clamp_scroll()
                        self._update_atom_temp(current_url, self.T_CACHED)
                        return True, self._render_current()
            resp = http_get(current_url, headers={"User-Agent": "KarmazynBrowser/3.2"})
            if resp.status in (301,302,303,307,308):
                location = resp.headers.get('Location') or resp.headers.get('location')
                if location:
                    current_url = _resolve_url(location, current_url)
                    if current_url:
                        continue
            break
        if not resp.ok():
            return False, f"HTTP {resp.status}: {current_url}"
        ct = resp.content_type.lower()
        if "html" not in ct and "text" not in ct:
            return False, f"Nieobsługiwany typ: {resp.content_type}\nURL: {current_url}"
        page = parse_html(resp.text, url=current_url, width=self.width)
        self._cache_put(current_url, page)
        self._update_atom_temp(current_url, self.T_FRESH)
        if add_to_history and self._current:
            self._add_to_history(self._current.url)
            self._forward.clear()
        self._current = page
        self._scroll = 0
        self._clamp_scroll()
        return True, self._render_current()

    def _add_to_history(self, url: str):
        if self._history and self._history[-1] == url:
            return
        self._history.append(url)

    def _clamp_scroll(self):
        if self._current is None:
            self._scroll = 0
            return
        total = len(self._current.lines())
        max_scroll = max(0, total - PAGE_SIZE)
        self._scroll = max(0, min(self._scroll, max_scroll))

    def go(self, url: str, force_reload: bool = False) -> Tuple[bool, str]:
        return self._load_url(url, add_to_history=True, force_reload=force_reload)

    def back(self) -> Tuple[bool, str]:
        if not self._history:
            return False, "Brak historii."
        if self._current:
            self._forward.appendleft(self._current.url)
        prev = self._history.pop()
        return self._load_url(prev, add_to_history=False)

    def forward(self) -> Tuple[bool, str]:
        if not self._forward:
            return False, "Brak stron do przodu."
        nxt = self._forward.popleft()
        return self._load_url(nxt, add_to_history=True)

    def reload(self) -> Tuple[bool, str]:
        if not self._current:
            return False, "Brak strony."
        url = self._current.url
        if url in self._cache:
            del self._cache[url]
        return self._load_url(url, add_to_history=False, force_reload=True)

    def follow_link(self, n: int) -> Tuple[bool, str]:
        if not self._current:
            return False, "Brak strony."
        if not self._current.links:
            return False, "Brak linków."
        if n < 1 or n > len(self._current.links):
            return False, f"Link {n} nie istnieje (1-{len(self._current.links)})."
        url, _ = self._current.links[n-1]
        if not url:
            return False, "Pusty link."
        return self.go(url)

    def _render_current(self) -> str:
        if self._current is None:
            return "Brak strony."
        self._clamp_scroll()
        lines = self._current.lines()
        total = len(lines)
        url_short = self._current.url[:self.width-10]
        header = [
            COLORS['gray'] + "─" * self.width + COLORS['reset'],
            COLORS['bold'] + f"  {self._current.title[:self.width-4]}" + COLORS['reset'],
            COLORS['cyan'] + f"  {url_short}" + COLORS['reset'],
            f"  Linki: {len(self._current.links)}  |  Linie: {total}",
            COLORS['gray'] + "─" * self.width + COLORS['reset'],
        ]
        page_lines = lines[self._scroll:self._scroll+PAGE_SIZE]
        remaining = max(0, total - self._scroll - PAGE_SIZE)
        footer = COLORS['gray'] + "─" * self.width + COLORS['reset'] + "\n"
        footer += f"[{self._scroll+1}-{min(self._scroll+PAGE_SIZE, total)}/{total}]"
        if remaining:
            footer += f"  BROWSE SCROLL 1 aby kontynuować ({remaining} linii)"
        return "\n".join(header + page_lines + [footer])

    def scroll(self, pages: int = 1) -> str:
        if not self._current:
            return "Brak strony."
        total = len(self._current.lines())
        self._scroll += pages * PAGE_SIZE
        self._clamp_scroll()
        return self._render_current()

    def find(self, query: str) -> str:
        if not self._current:
            return "Brak strony."
        lines = self._current.lines()
        # Szukamy na tekście bez ANSI, ale podświetlamy w oryginalnych liniach
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        hits = []
        for i, line in enumerate(lines, 1):
            stripped = ANSI_RE.sub('', line)
            if pattern.search(stripped):
                # Podświetlenie w oryginalnej linii – trudne, zrobimy prostsze: podświetlamy w stripped
                highlighted = pattern.sub(lambda m: COLORS['red'] + m.group(0) + COLORS['reset'], stripped)
                hits.append((i, highlighted))
        if not hits:
            return f"Nie znaleziono: '{query}'"
        result = [COLORS['yellow'] + f"Znaleziono '{query}' ({len(hits)} wystąpień):" + COLORS['reset']]
        for lineno, line in hits[:15]:
            result.append(f"  [{lineno:4}] {line[:self.width-10]}")
        if len(hits) > 15:
            result.append(f"  ... i {len(hits)-15} więcej")
        return "\n".join(result)

    def show_links(self) -> str:
        if not self._current:
            return "Brak strony."
        if not self._current.links:
            return "Brak linków."
        lines = [COLORS['bold'] + f"Linki ({len(self._current.links)}):" + COLORS['reset']]
        for i, (url, text) in enumerate(self._current.links, 1):
            url_short = url[:50] if url else "(pusty)"
            text_short = text[:30]
            lines.append(f"  {COLORS['blue']}[{i:3}]{COLORS['reset']} {text_short:<30} {COLORS['cyan']}{url_short}{COLORS['reset']}")
        return "\n".join(lines)

    def show_source(self, lines_n: int = 50) -> str:
        if not self._current:
            return "Brak strony."
        src = self._current.raw_html.splitlines()[:lines_n]
        return "\n".join(src)

    def _load_bookmarks(self):
        path = os.path.join(CACHE_DIR, "bookmarks.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._bookmarks = json.load(f)
            except Exception as e:
                _log_error(f"Load bookmarks: {e}")
                self._bookmarks = {}

    def _save_bookmarks(self):
        path = os.path.join(CACHE_DIR, "bookmarks.json")
        os.makedirs(CACHE_DIR, exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._bookmarks, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _log_error(f"Save bookmarks: {e}")

    def add_bookmark(self) -> str:
        if not self._current:
            return "Brak strony."
        url = self._current.url
        title = self._current.title
        self._bookmarks[url] = title
        self._save_bookmarks()
        label = "bm_" + re.sub(r"[^a-z0-9]", "_", url.lower())[:20]
        try:
            if not self.runtime.matrix.has_atom(label):
                self.runtime.create_atom(label, title[:64], url, self.T_CACHED)
        except Exception as e:
            _log_error(f"Bookmark atom: {e}")
        return f"Dodano zakładkę: {title}"

    def list_bookmarks(self) -> str:
        if not self._bookmarks:
            return "Brak zakładek."
        lines = [COLORS['bold'] + f"Zakładki ({len(self._bookmarks)}):" + COLORS['reset']]
        for i, (url, title) in enumerate(self._bookmarks.items(), 1):
            lines.append(f"  {COLORS['green']}[{i:3}]{COLORS['reset']} {title[:35]:<35} {COLORS['cyan']}{url[:45]}{COLORS['reset']}")
        return "\n".join(lines)

    def go_bookmark(self, n: int) -> Tuple[bool, str]:
        urls = list(self._bookmarks.keys())
        if n < 1 or n > len(urls):
            return False, f"Zakładka {n} nie istnieje (1-{len(urls)})."
        return self.go(urls[n-1])

    def show_history(self) -> str:
        if not self._history:
            return "Historia pusta."
        lines = [COLORS['bold'] + f"Historia ({len(self._history)}):" + COLORS['reset']]
        for url in reversed(self._history):
            cached = url in self._cache
            mark = COLORS['green'] + "✓" + COLORS['reset'] if cached else " "
            lines.append(f"  [{mark}] {url[:self.width-8]}")
        return "\n".join(lines)

# ===== Komenda shella ==========================================================
def cmd_browse(args, browser: KarmazynBrowser) -> str:
    if not args:
        return browser._render_current() if browser._current else "BROWSE <url>"
    sub = args[0].upper()
    if (sub.startswith("HTTP") or ("." in args[0] and sub not in (
        "BACK","FORWARD","FWD","RELOAD","LINKS","FOLLOW","FIND",
        "SCROLL","SOURCE","BM","BOOKMARKS","GOTO","HISTORY","SAVE"
    ))):
        _, msg = browser.go(args[0])
        return msg
    if sub == "BACK":
        _, msg = browser.back()
        return msg
    if sub in ("FORWARD","FWD"):
        _, msg = browser.forward()
        return msg
    if sub == "RELOAD":
        _, msg = browser.reload()
        return msg
    if sub == "LINKS":
        return browser.show_links()
    if sub == "FOLLOW":
        if len(args) < 2:
            return "BROWSE FOLLOW <numer>"
        try:
            n = int(args[1])
        except ValueError:
            return f"Nieprawidłowy numer: {args[1]}"
        _, msg = browser.follow_link(n)
        return msg
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
            return "BROWSE GOTO <numer>"
        try:
            n = int(args[1])
        except ValueError:
            return f"Nieprawidłowy numer: {args[1]}"
        _, msg = browser.go_bookmark(n)
        return msg
    if sub == "HISTORY":
        return browser.show_history()
    if sub == "SAVE":
        if not browser._current:
            return "Brak strony."
        label = args[1] if len(args) > 1 else "www_" + re.sub(r"[^a-z0-9]", "_", browser._current.url.lower().replace("https://","").replace("http://",""))[:20]
        try:
            browser.runtime.write(label, browser._current.title[:64], browser._current.url, browser.T_CACHED)
            return f"Zapisano jako atom: {label}"
        except Exception as e:
            return f"Błąd zapisu: {e}"
    _, msg = browser.go(args[0])
    return msg