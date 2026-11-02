//! Konsola PID 1: ekran VGA (`/dev/tty1`) i serial (`/dev/ttyS0`) naraz.
//!
//! Shell i goście piszą na zwykłe stdout i czytają zwykłe stdin. Tu stdin i
//! stdout stają się rurami: jeden wątek kopiuje wyjście na każdy terminal,
//! drugi zbiera wejście z tego, na którym ktoś pisze. Echo wpisywanej linii
//! robi terminal, na którym pisano; wynik polecenia widać na wszystkich.
//!
//! `KARMAZYN_CONSOLE=auto` (domyślnie: oba), `vga`, `serial`, `none`
//! (zostaje /dev/console od jądra).
//!
//! Na ekran VGA idzie font PSF2 z tabelą Unicode (`KARMAZYN_FONT`, domyślnie
//! pierwszy `*.psfu` w `/font`; `none` zostawia font karty). Wbudowany font
//! karty to CP437: bez niego jądro pokazuje „e” zamiast „ę”.

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
#[cfg_attr(not(target_os = "linux"), allow(dead_code))]
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
        let mut name = dev.trim_start_matches("/dev/").to_string();
        if *dev == "/dev/tty1" {
            match load_font(fd) {
                Some(Ok(font)) => name = format!("{name} ({font})"),
                Some(Err(e)) => name = format!("{name} (font: {e})"),
                None => {}
            }
        }
        names.push(name);
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

/// Font PSF2 gotowy dla `KDFONTOP`: glify po 32 B (wiersze 8 px, dopełnione
/// zerami do 32 wierszy, jak oczekuje jądro) i pary (Unicode, numer glifu).
#[derive(Debug, PartialEq)]
pub struct Psf {
    pub width: u32,
    pub height: u32,
    pub count: u32,
    pub glyphs: Vec<u8>,
    pub unimap: Vec<(u16, u16)>,
}

const PSF2_MAGIC: [u8; 4] = [0x72, 0xb5, 0x4a, 0x86];

/// PSF2 z tabelą Unicode (flaga 1). Sekwencje po 0xFE (znaki złożone) pomija.
#[cfg_attr(not(target_os = "linux"), allow(dead_code))]
pub fn parse_psf2(b: &[u8]) -> Result<Psf, String> {
    let u32_at = |o: usize| -> Result<u32, String> {
        b.get(o..o + 4)
            .map(|x| u32::from_le_bytes(x.try_into().unwrap()))
            .ok_or_else(|| "krótki nagłówek PSF2".to_string())
    };
    if b.get(..4) != Some(&PSF2_MAGIC[..]) {
        return Err("to nie PSF2".into());
    }
    let header = u32_at(8)? as usize;
    let flags = u32_at(12)?;
    let count = u32_at(16)?;
    let size = u32_at(20)? as usize;
    let height = u32_at(24)?;
    let width = u32_at(28)?;
    if width != 8 || height == 0 || height > 32 || size != height as usize || count == 0 || count > 512 {
        return Err(format!("PSF2 {width}x{height}: obsługiwane 8 px, do 32 wierszy"));
    }
    let end = header + count as usize * size;
    let raw = b.get(header..end).ok_or("PSF2 urwany")?;
    let mut glyphs = vec![0u8; count as usize * 32];
    for (g, rows) in raw.chunks(size).enumerate() {
        glyphs[g * 32..g * 32 + size].copy_from_slice(rows);
    }
    let mut unimap = Vec::new();
    if flags & 1 != 0 {
        let mut table = &b[end..];
        for g in 0..count as u16 {
            let stop = table.iter().position(|&x| x == 0xFF).ok_or("tabela Unicode urwana")?;
            let single = table[..stop].split(|&x| x == 0xFE).next().unwrap_or(&[]);
            for ch in String::from_utf8_lossy(single).chars() {
                if let Ok(u) = u16::try_from(ch as u32) {
                    unimap.push((u, g));
                }
            }
            table = &table[stop + 1..];
        }
    }
    Ok(Psf { width, height, count, glyphs, unimap })
}

/// Plik fontu: `KARMAZYN_FONT` albo pierwszy `*.psfu` w `/font`. `None` =
/// nie ma czego ładować (zostaje font karty).
#[cfg(target_os = "linux")]
fn font_path() -> Option<std::path::PathBuf> {
    match std::env::var("KARMAZYN_FONT") {
        Ok(v) if v.trim() == "none" => None,
        Ok(v) if !v.trim().is_empty() => Some(v.trim().into()),
        _ => {
            let mut all: Vec<_> = std::fs::read_dir("/font")
                .ok()?
                .filter_map(|e| e.ok().map(|e| e.path()))
                .filter(|p| p.extension().is_some_and(|x| x == "psfu"))
                .collect();
            all.sort();
            all.into_iter().next()
        }
    }
}

/// Glify (`KDFONTOP`) i mapa Unicode (`PIO_UNIMAPCLR` + `PIO_UNIMAP`) na
/// terminal `fd`, jak `setfont`. Zwraca nazwę fontu.
#[cfg(target_os = "linux")]
fn load_font(fd: i32) -> Option<Result<String, String>> {
    let path = font_path()?;
    let name = path
        .file_stem()
        .map(|s| s.to_string_lossy().into_owned())
        .unwrap_or_default();
    Some(std::fs::read(&path).map_err(|e| e.to_string()).and_then(|b| {
        let mut psf = parse_psf2(&b)?;
        set_font(fd, &mut psf)?;
        Ok(name)
    }))
}

#[cfg(target_os = "linux")]
fn set_font(fd: i32, psf: &mut Psf) -> Result<(), String> {
    const KDFONTOP: u32 = 0x4B72;
    const KD_FONT_OP_SET: u32 = 0;
    const PIO_UNIMAPCLR: u32 = 0x4B68;
    const PIO_UNIMAP: u32 = 0x4B67;
    #[repr(C)]
    struct ConsoleFontOp {
        op: u32,
        flags: u32,
        width: u32,
        height: u32,
        charcount: u32,
        data: *mut u8,
    }
    #[repr(C)]
    struct UnimapInit {
        hashsize: u16,
        hashstep: u16,
        hashlevel: u16,
    }
    #[repr(C)]
    struct Unipair {
        unicode: u16,
        fontpos: u16,
    }
    #[repr(C)]
    struct UnimapDesc {
        count: u16,
        entries: *mut Unipair,
    }
    let os = || std::io::Error::last_os_error().to_string();
    let mut op = ConsoleFontOp {
        op: KD_FONT_OP_SET,
        flags: 0,
        width: psf.width,
        height: psf.height,
        charcount: psf.count,
        data: psf.glyphs.as_mut_ptr(),
    };
    // SAFETY: struktura i bufor glifów żyją do końca wywołania.
    if unsafe { libc::ioctl(fd, KDFONTOP as _, &mut op) } != 0 {
        return Err(format!("KDFONTOP: {}", os()));
    }
    if psf.unimap.is_empty() {
        return Ok(());
    }
    let mut init = UnimapInit { hashsize: 0, hashstep: 0, hashlevel: 0 };
    // SAFETY: jak wyżej.
    if unsafe { libc::ioctl(fd, PIO_UNIMAPCLR as _, &mut init) } != 0 {
        return Err(format!("PIO_UNIMAPCLR: {}", os()));
    }
    let mut pairs: Vec<Unipair> = psf
        .unimap
        .iter()
        .map(|&(unicode, fontpos)| Unipair { unicode, fontpos })
        .collect();
    let mut desc = UnimapDesc { count: pairs.len() as u16, entries: pairs.as_mut_ptr() };
    // SAFETY: jak wyżej.
    if unsafe { libc::ioctl(fd, PIO_UNIMAP as _, &mut desc) } != 0 {
        return Err(format!("PIO_UNIMAP: {}", os()));
    }
    Ok(())
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
    fn psf2_glyphs_padded_and_unicode_pairs() {
        // 2 glify 8x16; glif 0: "a" i "ą", glif 1: "—" oraz sekwencja po 0xFE
        let mut b = vec![0x72, 0xb5, 0x4a, 0x86];
        for v in [0u32, 32, 1, 2, 16, 16, 8] {
            b.extend(v.to_le_bytes());
        }
        b.extend([0x11u8; 16]);
        b.extend([0x22u8; 16]);
        b.extend("aą".as_bytes());
        b.push(0xFF);
        b.extend("—".as_bytes());
        b.push(0xFE);
        b.extend("e\u{301}".as_bytes());
        b.push(0xFF);
        let psf = parse_psf2(&b).unwrap();
        assert_eq!((psf.width, psf.height, psf.count), (8, 16, 2));
        assert_eq!(psf.glyphs.len(), 64);
        assert_eq!(&psf.glyphs[..16], &[0x11; 16]);
        assert_eq!(&psf.glyphs[16..32], &[0; 16]);
        assert_eq!(&psf.glyphs[32..48], &[0x22; 16]);
        assert_eq!(psf.unimap, vec![(0x61, 0), (0x105, 0), (0x2014, 1)]);
        assert!(parse_psf2(b"\x36\x04\x02\x10").is_err());
        b[28] = 9;
        assert!(parse_psf2(&b).is_err());
    }

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
