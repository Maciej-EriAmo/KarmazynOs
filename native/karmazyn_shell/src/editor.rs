//! `edit <etykieta>`: pełnoekranowy edytor z kursorem dla źródła bąbla.
//!
//! Logika (bufor, kursor, klawisze, rysowanie) nie dotyka terminala, więc
//! testy działają na każdym hoście. Tryb surowy terminala i pętla odczytu są
//! tylko na Linuksie (płyta, serial albo konsola).
//!
//! Klawisze: strzałki, Home/End, PgUp/PgDn, Backspace, Delete, Enter, Tab
//! (4 spacje), ^S zapis, ^Q wyjście (przy zmianach drugi raz), ^K usuń linię,
//! ^L odśwież cały ekran (np. po komunikatach jądra na serialu).

// Na hoście bez Linuksa działa tylko logika (testy); pętla terminala jest wyłączona.
#![cfg_attr(not(target_os = "linux"), allow(dead_code))]

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Key {
    Char(char),
    Enter,
    Backspace,
    Delete,
    Tab,
    Left,
    Right,
    Up,
    Down,
    Home,
    End,
    PageUp,
    PageDown,
    Save,
    Quit,
    KillLine,
    Redraw,
    Ignore,
}

/// Bajty z terminala → klawisze. Niedokończony znak UTF-8 albo sekwencja ESC
/// na końcu porcji zostaje w `pending` do następnego odczytu. Samotny ESC
/// na końcu porcji jest pomijany.
pub fn parse_keys(chunk: &[u8], pending: &mut Vec<u8>) -> Vec<Key> {
    pending.extend_from_slice(chunk);
    let buf = std::mem::take(pending);
    let mut keys = Vec::new();
    let mut i = 0;
    while i < buf.len() {
        let b = buf[i];
        match b {
            0x1b => {
                let rest = &buf[i + 1..];
                if rest.is_empty() {
                    i += 1;
                    continue;
                }
                if rest[0] != b'[' && rest[0] != b'O' {
                    keys.push(Key::Ignore);
                    i += 1;
                    continue;
                }
                // ESC [ <cyfry> <litera albo ~>
                let mut j = 1;
                while j < rest.len() && (rest[j].is_ascii_digit() || rest[j] == b';') {
                    j += 1;
                }
                if j >= rest.len() {
                    // sekwencja przecięta między odczytami
                    pending.extend_from_slice(&buf[i..]);
                    return keys;
                }
                let params = std::str::from_utf8(&rest[1..j]).unwrap_or("");
                let key = match (rest[j], params) {
                    (b'A', _) => Key::Up,
                    (b'B', _) => Key::Down,
                    (b'C', _) => Key::Right,
                    (b'D', _) => Key::Left,
                    (b'H', _) => Key::Home,
                    (b'F', _) => Key::End,
                    (b'~', "1") | (b'~', "7") => Key::Home,
                    (b'~', "4") | (b'~', "8") => Key::End,
                    (b'~', "3") => Key::Delete,
                    (b'~', "5") => Key::PageUp,
                    (b'~', "6") => Key::PageDown,
                    _ => Key::Ignore,
                };
                keys.push(key);
                i += 1 + j + 1;
            }
            b'\r' | b'\n' => {
                keys.push(Key::Enter);
                // \r\n z terminala to jeden Enter
                if b == b'\r' && buf.get(i + 1) == Some(&b'\n') {
                    i += 1;
                }
                i += 1;
            }
            0x7f | 0x08 => {
                keys.push(Key::Backspace);
                i += 1;
            }
            b'\t' => {
                keys.push(Key::Tab);
                i += 1;
            }
            0x13 => {
                keys.push(Key::Save);
                i += 1;
            }
            0x11 => {
                keys.push(Key::Quit);
                i += 1;
            }
            0x0c => {
                keys.push(Key::Redraw);
                i += 1;
            }
            0x0b => {
                keys.push(Key::KillLine);
                i += 1;
            }
            0x00..=0x1f => {
                keys.push(Key::Ignore);
                i += 1;
            }
            _ => {
                let len = match b {
                    0xc0..=0xdf => 2,
                    0xe0..=0xef => 3,
                    0xf0..=0xf7 => 4,
                    _ => 1,
                };
                if i + len > buf.len() {
                    pending.extend_from_slice(&buf[i..]);
                    return keys;
                }
                match std::str::from_utf8(&buf[i..i + len]) {
                    Ok(s) => keys.extend(s.chars().map(Key::Char)),
                    Err(_) => keys.push(Key::Ignore),
                }
                i += len;
            }
        }
    }
    keys
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Action {
    None,
    Save,
    Quit,
}

pub struct Editor {
    lines: Vec<Vec<char>>,
    cy: usize,
    cx: usize,
    top: usize,
    left: usize,
    rows: usize,
    cols: usize,
    title: String,
    dirty: bool,
    quit_armed: bool,
    message: String,
    /// Ostatnio narysowane wiersze ekranu; None = nieznany, rysuj.
    drawn: Vec<Option<String>>,
}

impl Editor {
    pub fn new(title: &str, text: &str, rows: usize, cols: usize) -> Self {
        let mut lines: Vec<Vec<char>> = text
            .replace('\r', "")
            .split('\n')
            .map(|l| l.chars().collect())
            .collect();
        // końcowy \n nie robi pustej linii; pusty plik to jedna pusta linia
        if lines.len() > 1 && lines.last().is_some_and(|l| l.is_empty()) {
            lines.pop();
        }
        Editor {
            lines,
            cy: 0,
            cx: 0,
            top: 0,
            left: 0,
            rows: rows.max(3),
            cols: cols.max(10),
            title: title.to_string(),
            dirty: false,
            quit_armed: false,
            message: "^S zapisz  ^Q wyjdź  ^K usuń linię  ^L odśwież".into(),
            drawn: Vec::new(),
        }
    }

    pub fn text(&self) -> String {
        let mut out: Vec<String> = self.lines.iter().map(|l| l.iter().collect()).collect();
        while out.len() > 1 && out.last().is_some_and(|l| l.is_empty()) {
            out.pop();
        }
        out.join("\n")
    }

    #[cfg(test)]
    pub fn cursor(&self) -> (usize, usize) {
        (self.cy, self.cx)
    }

    #[cfg(test)]
    pub fn is_dirty(&self) -> bool {
        self.dirty
    }

    /// Po zapisie: czysty bufor i komunikat w pasku.
    pub fn saved(&mut self, message: &str) {
        self.dirty = false;
        self.message = message.to_string();
    }

    pub fn set_message(&mut self, message: &str) {
        self.message = message.to_string();
    }

    fn text_rows(&self) -> usize {
        self.rows - 2
    }

    fn clamp_cx(&mut self) {
        self.cx = self.cx.min(self.lines[self.cy].len());
    }

    fn edited(&mut self) {
        self.dirty = true;
    }

    pub fn handle(&mut self, key: Key) -> Action {
        if key != Key::Quit {
            self.quit_armed = false;
        }
        match key {
            Key::Char(c) => {
                self.lines[self.cy].insert(self.cx, c);
                self.cx += 1;
                self.edited();
            }
            Key::Tab => {
                for _ in 0..4 {
                    self.lines[self.cy].insert(self.cx, ' ');
                    self.cx += 1;
                }
                self.edited();
            }
            Key::Enter => {
                let rest = self.lines[self.cy].split_off(self.cx);
                self.lines.insert(self.cy + 1, rest);
                self.cy += 1;
                self.cx = 0;
                self.edited();
            }
            Key::Backspace => {
                if self.cx > 0 {
                    self.cx -= 1;
                    self.lines[self.cy].remove(self.cx);
                    self.edited();
                } else if self.cy > 0 {
                    let line = self.lines.remove(self.cy);
                    self.cy -= 1;
                    self.cx = self.lines[self.cy].len();
                    self.lines[self.cy].extend(line);
                    self.edited();
                }
            }
            Key::Delete => {
                if self.cx < self.lines[self.cy].len() {
                    self.lines[self.cy].remove(self.cx);
                    self.edited();
                } else if self.cy + 1 < self.lines.len() {
                    let next = self.lines.remove(self.cy + 1);
                    self.lines[self.cy].extend(next);
                    self.edited();
                }
            }
            Key::KillLine => {
                if self.lines.len() > 1 {
                    self.lines.remove(self.cy);
                    if self.cy >= self.lines.len() {
                        self.cy = self.lines.len() - 1;
                    }
                } else {
                    self.lines[0].clear();
                }
                self.clamp_cx();
                self.edited();
            }
            Key::Left => {
                if self.cx > 0 {
                    self.cx -= 1;
                } else if self.cy > 0 {
                    self.cy -= 1;
                    self.cx = self.lines[self.cy].len();
                }
            }
            Key::Right => {
                if self.cx < self.lines[self.cy].len() {
                    self.cx += 1;
                } else if self.cy + 1 < self.lines.len() {
                    self.cy += 1;
                    self.cx = 0;
                }
            }
            Key::Up => {
                if self.cy > 0 {
                    self.cy -= 1;
                    self.clamp_cx();
                }
            }
            Key::Down => {
                if self.cy + 1 < self.lines.len() {
                    self.cy += 1;
                    self.clamp_cx();
                }
            }
            Key::Home => self.cx = 0,
            Key::End => self.cx = self.lines[self.cy].len(),
            Key::PageUp => {
                self.cy = self.cy.saturating_sub(self.text_rows());
                self.clamp_cx();
            }
            Key::PageDown => {
                self.cy = (self.cy + self.text_rows()).min(self.lines.len() - 1);
                self.clamp_cx();
            }
            Key::Save => return Action::Save,
            Key::Quit => {
                if !self.dirty || self.quit_armed {
                    return Action::Quit;
                }
                self.quit_armed = true;
                self.message = "Niezapisane zmiany. ^Q jeszcze raz = wyjdź bez zapisu, ^S = zapisz".into();
            }
            Key::Redraw => self.invalidate(),
            Key::Ignore => {}
        }
        Action::None
    }

    fn scroll(&mut self) {
        let h = self.text_rows();
        if self.cy < self.top {
            self.top = self.cy;
        } else if self.cy >= self.top + h {
            self.top = self.cy + 1 - h;
        }
        if self.cx < self.left {
            self.left = self.cx;
        } else if self.cx >= self.left + self.cols {
            self.left = self.cx + 1 - self.cols;
        }
    }

    /// Wiersze ekranu tak, jak mają wyglądać: tekst, pasek stanu, komunikat.
    fn screen_rows(&self) -> Vec<String> {
        let mut rows = Vec::with_capacity(self.rows);
        for r in 0..self.text_rows() {
            let row = match self.lines.get(self.top + r) {
                Some(line) => line.iter().skip(self.left).take(self.cols).collect(),
                None => "~".to_string(),
            };
            rows.push(row);
        }
        let status = format!(
            " {}{}  L{}:{}  ({} linii)",
            self.title,
            if self.dirty { " [+]" } else { "" },
            self.cy + 1,
            self.cx + 1,
            self.lines.len()
        );
        let status: String = status.chars().take(self.cols).collect();
        let pad = self.cols.saturating_sub(status.chars().count());
        rows.push(format!("\x1b[7m{status}{}\x1b[0m", " ".repeat(pad)));
        rows.push(self.message.chars().take(self.cols).collect());
        rows
    }

    /// Sekwencje ANSI tylko dla wierszy, które zmieniły się od poprzedniego
    /// rysunku (po serialu 115200 cały ekran 80×24 to do ~2 KB, linia z paskiem
    /// stanu ~150 B).
    /// Pierwszy rysunek i `invalidate` rysują wszystko.
    pub fn render(&mut self) -> String {
        self.scroll();
        let rows = self.screen_rows();
        if self.drawn.len() != rows.len() {
            self.drawn = vec![None; rows.len()];
        }
        let mut out = String::from("\x1b[?25l");
        for (r, row) in rows.into_iter().enumerate() {
            if self.drawn[r].as_deref() == Some(row.as_str()) {
                continue;
            }
            out.push_str(&format!("\x1b[{};1H{row}\x1b[K", r + 1));
            self.drawn[r] = Some(row);
        }
        out.push_str(&format!(
            "\x1b[{};{}H\x1b[?25h",
            self.cy - self.top + 1,
            self.cx - self.left + 1
        ));
        out
    }

    /// Następny `render` rysuje cały ekran (np. po wyczyszczeniu terminala).
    pub fn invalidate(&mut self) {
        self.drawn.clear();
    }
}

/// Wynik zapisu podany przez wywołującego: komunikat do paska albo błąd.
pub type SaveFn<'a> = dyn FnMut(&str) -> Result<String, String> + 'a;

#[cfg(target_os = "linux")]
mod term {
    use std::io::{self, Read, Write};

    /// Terminale do przełączenia: konsola PID 1 (ekran i serial) albo fd 0.
    fn fds() -> Vec<i32> {
        let t = crate::console::ttys();
        if t.is_empty() {
            vec![0]
        } else {
            t.to_vec()
        }
    }

    pub struct Raw {
        saved: Vec<(i32, libc::termios)>,
    }

    impl Raw {
        pub fn enter() -> io::Result<Self> {
            let mut saved = Vec::new();
            for fd in fds() {
                // SAFETY: termios wypełnia tcgetattr; fd to terminal konsoli.
                unsafe {
                    let mut t: libc::termios = std::mem::zeroed();
                    if libc::tcgetattr(fd, &mut t) != 0 {
                        continue;
                    }
                    let old = t;
                    libc::cfmakeraw(&mut t);
                    // cfmakeraw zdejmuje OPOST; bez niego nowa linia nie wraca do kolumny 1
                    t.c_oflag |= libc::OPOST | libc::ONLCR;
                    t.c_cc[libc::VMIN] = 1;
                    t.c_cc[libc::VTIME] = 0;
                    if libc::tcsetattr(fd, libc::TCSANOW, &t) == 0 {
                        saved.push((fd, old));
                    }
                }
            }
            if saved.is_empty() {
                return Err(io::Error::other("brak terminala do trybu surowego"));
            }
            print!("\x1b[?1049h");
            let _ = io::stdout().flush();
            Ok(Raw { saved })
        }
    }

    impl Drop for Raw {
        fn drop(&mut self) {
            print!("\x1b[?1049l");
            let _ = io::stdout().flush();
            for (fd, t) in &self.saved {
                // SAFETY: przywraca ustawienia odczytane w enter().
                unsafe {
                    libc::tcsetattr(*fd, libc::TCSANOW, t);
                }
            }
        }
    }

    /// (wiersze, kolumny): najmniejszy z terminali konsoli, żeby ekran mieścił
    /// się wszędzie. Serial zwykle zwraca 0×0 → LINES/COLUMNS albo 24×80.
    pub fn size() -> (usize, usize) {
        let env = |k: &str, d: usize| {
            std::env::var(k).ok().and_then(|v| v.parse().ok()).unwrap_or(d)
        };
        let mut best = (env("LINES", 24), env("COLUMNS", 80));
        let mut fds = crate::console::ttys().to_vec();
        if fds.is_empty() {
            fds.push(1);
        }
        for fd in fds {
            // SAFETY: winsize wypełnia ioctl.
            let mut ws: libc::winsize = unsafe { std::mem::zeroed() };
            let ok = unsafe { libc::ioctl(fd, libc::TIOCGWINSZ, &mut ws) } == 0;
            if ok && ws.ws_row > 0 && ws.ws_col > 0 {
                best.0 = best.0.min(ws.ws_row as usize);
                best.1 = best.1.min(ws.ws_col as usize);
            }
        }
        best
    }

    /// Kolejna porcja bajtów. Czyta przez std::io::stdin, więc najpierw
    /// dostaje to, co shell już zbuforował.
    pub fn read_chunk(buf: &mut [u8]) -> io::Result<usize> {
        io::stdin().lock().read(buf)
    }
}

/// Pętla edytora na terminalu. `save` dostaje cały tekst.
#[cfg(target_os = "linux")]
pub fn run(title: &str, text: &str, save: &mut SaveFn) -> Result<(), String> {
    use std::io::Write;
    let _raw = term::Raw::enter().map_err(|e| format!("edit: terminal: {e}"))?;
    let (rows, cols) = term::size();
    let mut ed = Editor::new(title, text, rows, cols);
    let mut out = std::io::stdout();
    let mut pending = Vec::new();
    let mut buf = [0u8; 256];
    let _ = write!(out, "\x1b[2J{}", ed.render());
    let _ = out.flush();
    loop {
        let n = term::read_chunk(&mut buf).map_err(|e| e.to_string())?;
        if n == 0 {
            return Ok(());
        }
        for key in parse_keys(&buf[..n], &mut pending) {
            match ed.handle(key) {
                Action::None => {}
                Action::Save => match save(&ed.text()) {
                    Ok(msg) => ed.saved(&msg),
                    Err(e) => ed.set_message(&e),
                },
                Action::Quit => return Ok(()),
            }
        }
        let _ = write!(out, "{}", ed.render());
        let _ = out.flush();
    }
}

#[cfg(not(target_os = "linux"))]
pub fn run(_title: &str, _text: &str, _save: &mut SaveFn) -> Result<(), String> {
    Err("edit: edytor z kursorem działa na Linuksie (płyta); tu użyj tool nano".into())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn feed(ed: &mut Editor, bytes: &[u8]) -> Vec<Action> {
        let mut pending = Vec::new();
        parse_keys(bytes, &mut pending)
            .into_iter()
            .map(|k| ed.handle(k))
            .collect()
    }

    #[test]
    fn parses_arrows_utf8_and_controls() {
        let mut p = Vec::new();
        let keys = parse_keys(b"a\x1b[A\x1b[3~\x1bOH\r\n\x7f\x13\x11", &mut p);
        assert_eq!(
            keys,
            vec![
                Key::Char('a'),
                Key::Up,
                Key::Delete,
                Key::Home,
                Key::Enter,
                Key::Backspace,
                Key::Save,
                Key::Quit
            ]
        );
        // ą = C4 85, przecięte między odczytami; tak samo ESC [
        assert_eq!(parse_keys(b"\xc4", &mut p), vec![]);
        assert_eq!(parse_keys(b"\x85\x1b[", &mut p), vec![Key::Char('ą')]);
        assert_eq!(parse_keys(b"B", &mut p), vec![Key::Down]);
        assert!(p.is_empty());
    }

    #[test]
    fn edits_with_cursor() {
        let mut ed = Editor::new("bin/x", "return 1\n", 10, 40);
        assert_eq!(ed.text(), "return 1");
        // koniec linii, Backspace, wpisz 2, Enter z podziałem w środku
        feed(&mut ed, b"\x1b[F\x7f2");
        assert_eq!(ed.text(), "return 2");
        feed(&mut ed, b"\x1b[H\x1b[C\x1b[C\x1b[C\x1b[C\x1b[C\x1b[C\r");
        assert_eq!(ed.text(), "return\n 2");
        assert_eq!(ed.cursor(), (1, 0));
        // Backspace na początku linii skleja z poprzednią
        feed(&mut ed, b"\x7f");
        assert_eq!(ed.text(), "return 2");
        assert_eq!(ed.cursor(), (0, 6));
        // nowa linia nad: Home, Enter, w górę, wpisz
        feed(&mut ed, b"\x1b[H\r\x1b[Alocal a = ...");
        assert_eq!(ed.text(), "local a = ...\nreturn 2");
        // Delete na końcu linii skleja z następną, ^K usuwa linię
        feed(&mut ed, b"\x1b[F\x1b[3~");
        assert_eq!(ed.text(), "local a = ...return 2");
        feed(&mut ed, b"\x0b");
        assert_eq!(ed.text(), "");
        assert!(ed.is_dirty());
    }

    #[test]
    fn quit_asks_twice_when_dirty() {
        let mut ed = Editor::new("lib/m", "", 10, 40);
        assert_eq!(feed(&mut ed, b"\x11"), vec![Action::Quit]);
        let mut ed = Editor::new("lib/m", "", 10, 40);
        feed(&mut ed, b"x");
        assert_eq!(feed(&mut ed, b"\x11"), vec![Action::None]);
        assert_eq!(feed(&mut ed, b"\x11"), vec![Action::Quit]);
        // inny klawisz rozbraja drugie ^Q
        feed(&mut ed, b"\x11y\x11");
        assert!(ed.is_dirty());
        assert_eq!(feed(&mut ed, b"\x13"), vec![Action::Save]);
        ed.saved("ok");
        assert_eq!(feed(&mut ed, b"\x11"), vec![Action::Quit]);
    }

    #[test]
    fn render_scrolls_to_cursor() {
        let text: Vec<String> = (1..=30).map(|n| format!("linia {n}")).collect();
        let mut ed = Editor::new("bin/d", &text.join("\n"), 6, 40);
        let first = ed.render();
        assert!(first.contains("linia 1\x1b[K"), "{first}");
        assert!(first.contains("bin/d  L1:1  (30 linii)"), "{first}");
        feed(&mut ed, b"\x1b[6~\x1b[6~");
        let after = ed.render();
        assert_eq!(ed.cursor(), (8, 0));
        assert!(after.contains("linia 9\x1b[K"), "{after}");
        assert!(!after.contains("linia 1\x1b[K"), "{after}");
        // kursor na ekranie: 4 wiersze tekstu, linia 9 na dole → wiersz 4
        assert!(after.ends_with("\x1b[4;1H\x1b[?25h"), "{after}");
    }

    #[test]
    fn render_sends_only_changed_rows() {
        let text: Vec<String> = (1..=30).map(|n| format!("linia numer {n}")).collect();
        let mut ed = Editor::new("bin/d", &text.join("\n"), 24, 80);
        let full = ed.render();
        assert!(full.len() > 600, "pierwszy rysunek: {}", full.len());

        // bez zmian: żaden wiersz, tylko kursor
        let idle = ed.render();
        assert_eq!(idle, "\x1b[?25l\x1b[1;1H\x1b[?25h");

        // znak w linii 1: linia 1 i pasek stanu (wiersz 23), komunikat bez zmian
        feed(&mut ed, b"X");
        let typed = ed.render();
        assert!(typed.contains("\x1b[1;1HXlinia numer 1\x1b[K"), "{typed}");
        assert!(typed.contains("\x1b[23;1H"), "{typed}");
        assert!(!typed.contains("\x1b[2;1H"), "{typed}");
        assert!(!typed.contains("\x1b[24;1H"), "{typed}");
        assert!(typed.len() < 200, "po znaku: {} B", typed.len());

        // sama strzałka: tylko pasek stanu (pozycja kursora)
        feed(&mut ed, b"\x1b[B");
        let moved = ed.render();
        assert!(!moved.contains("linia"), "{moved}");
        assert!(moved.contains("L2:2"), "{moved}");

        // ^L: znowu cały ekran
        assert_eq!(feed(&mut ed, b"\x0c"), vec![Action::None]);
        assert!(ed.render().len() > 600);
    }
}
