//! Konsola PID 1: ekran VGA (`/dev/tty1`) i serial (`/dev/ttyS0`) naraz.
//!
//! Shell i goście piszą na zwykłe stdout i czytają zwykłe stdin. Tu stdin i
//! stdout stają się rurami: jeden wątek kopiuje wyjście na każdy terminal,
//! drugi zbiera wejście z tego, na którym ktoś pisze. Echo wpisywanej linii
//! robi terminal, na którym pisano; wynik polecenia widać na wszystkich.
//!
//! `KARMAZYN_CONSOLE=auto` (domyślnie: oba), `vga`, `serial`, `none`
//! (zostaje /dev/console od jądra).

use std::sync::OnceLock;

/// Deskryptory terminali, gdy konsola działa (dla trybu surowego edytora).
static TTYS: OnceLock<Vec<i32>> = OnceLock::new();

/// Terminale konsoli. Pusto = zwykłe fd 0/1 (host albo `none`).
pub fn ttys() -> &'static [i32] {
    TTYS.get().map(Vec::as_slice).unwrap_or(&[])
}

/// Czy wyjście trafia na prawdziwy terminal (kolory, czyszczenie ekranu),
/// także gdy stdout to rura konsoli.
pub fn is_terminal() -> bool {
    use std::io::IsTerminal;
    !ttys().is_empty() || std::io::stdout().is_terminal()
}

/// Ścieżki terminali dla wartości `KARMAZYN_CONSOLE`.
pub fn devices(mode: &str) -> &'static [&'static str] {
    match mode {
        "vga" => &["/dev/tty1"],
        "serial" => &["/dev/ttyS0"],
        "none" => &[],
        _ => &["/dev/tty1", "/dev/ttyS0"],
    }
}

/// Uruchamia konsolę. Zwraca nazwy terminali (do linii startowej) albo opis,
/// czemu zostaje /dev/console.
#[cfg(target_os = "linux")]
pub fn setup() -> Result<Vec<String>, String> {
    use std::ffi::CString;
    use std::thread;

    let mode = std::env::var("KARMAZYN_CONSOLE").unwrap_or_default();
    let mode = mode.trim();
    let wanted = devices(mode);
    if wanted.is_empty() {
        return Err("KARMAZYN_CONSOLE=none".into());
    }
    if let Some(e) = crate::disk::mount_dev() {
        return Err(e);
    }
    let mut fds = Vec::new();
    let mut names = Vec::new();
    for dev in wanted {
        let path = CString::new(*dev).unwrap();
        // SAFETY: ścieżka to żywy CString.
        let fd = unsafe { libc::open(path.as_ptr(), libc::O_RDWR | libc::O_NOCTTY) };
        if fd < 0 {
            continue;
        }
        // SAFETY: fd właśnie otwarty.
        if unsafe { libc::isatty(fd) } != 1 {
            unsafe { libc::close(fd) };
            continue;
        }
        fds.push(fd);
        names.push(dev.trim_start_matches("/dev/").to_string());
    }
    if fds.is_empty() {
        return Err(format!("brak terminali: {}", wanted.join(", ")));
    }

    let (in_r, in_w) = pipe()?;
    let (out_r, out_w) = pipe()?;
    // SAFETY: dup2 na otwarte deskryptory; stare fd 0/1/2 (/dev/console) znikają.
    unsafe {
        libc::dup2(in_r, 0);
        libc::dup2(out_w, 1);
        libc::dup2(out_w, 2);
        libc::close(in_r);
        libc::close(out_w);
    }

    let out_fds = fds.clone();
    thread::spawn(move || copy_out(out_r, &out_fds));
    let in_fds = fds.clone();
    thread::spawn(move || copy_in(&in_fds, in_w));
    let _ = TTYS.set(fds);
    Ok(names)
}

#[cfg(not(target_os = "linux"))]
pub fn setup() -> Result<Vec<String>, String> {
    Err("konsola VGA tylko na Linuksie".into())
}

#[cfg(target_os = "linux")]
fn pipe() -> Result<(i32, i32), String> {
    let mut p = [0i32; 2];
    // SAFETY: tablica na dwa fd.
    if unsafe { libc::pipe(p.as_mut_ptr()) } != 0 {
        return Err(format!("pipe: {}", std::io::Error::last_os_error()));
    }
    Ok((p[0], p[1]))
}

/// Pełny zapis; terminal, który odpada, jest pomijany.
#[cfg(target_os = "linux")]
fn write_all(fd: i32, mut buf: &[u8]) -> bool {
    while !buf.is_empty() {
        // SAFETY: bufor żyje przez wywołanie.
        let n = unsafe { libc::write(fd, buf.as_ptr().cast(), buf.len()) };
        if n < 0 {
            if std::io::Error::last_os_error().kind() == std::io::ErrorKind::Interrupted {
                continue;
            }
            return false;
        }
        buf = &buf[n as usize..];
    }
    true
}

/// stdout shella → każdy terminal.
#[cfg(target_os = "linux")]
fn copy_out(from: i32, to: &[i32]) {
    let mut buf = [0u8; 4096];
    loop {
        // SAFETY: bufor lokalny.
        let n = unsafe { libc::read(from, buf.as_mut_ptr().cast(), buf.len()) };
        if n <= 0 {
            if n < 0
                && std::io::Error::last_os_error().kind() == std::io::ErrorKind::Interrupted
            {
                continue;
            }
            return;
        }
        for fd in to {
            write_all(*fd, &buf[..n as usize]);
        }
    }
}

/// Tryb liniowy (ICANON): terminal sam robi echo i oddaje całą linię.
#[cfg(target_os = "linux")]
fn is_canonical(fd: i32) -> bool {
    // SAFETY: termios wypełnia tcgetattr.
    unsafe {
        let mut t: libc::termios = std::mem::zeroed();
        libc::tcgetattr(fd, &mut t) == 0 && t.c_lflag & libc::ICANON != 0
    }
}

/// Terminal, na którym ktoś pisze → stdin shella.
#[cfg(target_os = "linux")]
fn copy_in(from: &[i32], to: i32) {
    let mut polls: Vec<libc::pollfd> = from
        .iter()
        .map(|fd| libc::pollfd { fd: *fd, events: libc::POLLIN, revents: 0 })
        .collect();
    let mut buf = [0u8; 1024];
    loop {
        // SAFETY: tablica pollfd żyje przez wywołanie.
        let rc = unsafe { libc::poll(polls.as_mut_ptr(), polls.len() as libc::nfds_t, -1) };
        if rc < 0 {
            continue;
        }
        for p in polls.iter_mut() {
            if p.revents & libc::POLLIN != 0 {
                // SAFETY: bufor lokalny.
                let n = unsafe { libc::read(p.fd, buf.as_mut_ptr().cast(), buf.len()) };
                if n > 0 {
                    let line = &buf[..n as usize];
                    if !write_all(to, line) {
                        return;
                    }
                    // linia wpisana tutaj: echo zrobił ten terminal, pozostałe
                    // dostają ją same (w trybie surowym ekran rysuje edytor)
                    if is_canonical(p.fd) {
                        for other in from.iter().filter(|fd| **fd != p.fd) {
                            write_all(*other, line);
                        }
                    }
                }
            }
            if p.revents & (libc::POLLHUP | libc::POLLERR | libc::POLLNVAL) != 0 {
                // terminal odpadł: nie pytaj go więcej
                p.fd = -1;
            }
            p.revents = 0;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn console_modes() {
        assert_eq!(devices(""), &["/dev/tty1", "/dev/ttyS0"]);
        assert_eq!(devices("auto"), &["/dev/tty1", "/dev/ttyS0"]);
        assert_eq!(devices("vga"), &["/dev/tty1"]);
        assert_eq!(devices("serial"), &["/dev/ttyS0"]);
        assert!(devices("none").is_empty());
        assert!(ttys().is_empty());
    }
}
