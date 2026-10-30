//! Trwałość shella: świat DBase (KAFD w kopercie KAFX) jako plik na ext4.
//!
//! Na płycie (PID 1): dysk `KARMAZYN_DISK` (domyślnie `/dev/vda`) montowany
//! jako ext4 pod `/data`. Pusty dysk (same zera na początku) dostaje ext2
//! z [`crate::ext2`]; dysk z nieznanymi danymi czeka na jawne `disk format`.
//! `CYNOBER_DATA_HOME` = `/data/cynober` (klucz węzła `master.key`), świat
//! w `worlds/<KARMAZYN_WORLD_NAME albo karmazyn>.kafd` — jak `cynober_worlds`.
//!
//! Na hoście: `KARMAZYN_WORLD=<plik.kafd>` wskazuje świat wprost.
//!
//! Gdy istniejącego świata nie da się wczytać (zły klucz, uszkodzenie),
//! zapis zostaje wstrzymany, żeby go nie nadpisać pustym Store.

use karmazyn_kafd::world::{load_store, save_store};
use karmazyn_kafd::Crypt;
use karmazyn_substrate::Store;
use std::cell::Cell;
use std::path::{Path, PathBuf};

pub const DEFAULT_DEVICE: &str = "/dev/vda";
pub const DATA_MOUNT: &str = "/data";
pub const DEFAULT_WORLD: &str = "karmazyn";

/// Świat na dysku.
pub struct Storage {
    pub world: PathBuf,
    pub device: Option<String>,
    crypt: Crypt,
    writable: Cell<bool>,
    saves: Cell<u64>,
}

impl Storage {
    pub fn new(world: PathBuf, device: Option<String>) -> Self {
        Storage {
            world,
            device,
            crypt: Crypt::default(),
            writable: Cell::new(true),
            saves: Cell::new(0),
        }
    }

    /// Wczytuje świat, gdy plik istnieje. `Ok(None)` = świata jeszcze nie ma.
    /// Błąd blokuje zapis.
    pub fn load(&self, store: &Store) -> Result<Option<(usize, usize)>, String> {
        if !self.world.exists() {
            return Ok(None);
        }
        match load_store(store, &self.world, &self.crypt) {
            Ok(n) => Ok(Some(n)),
            Err(e) => {
                self.writable.set(false);
                Err(format!("{}: {e} — zapis wstrzymany", self.world.display()))
            }
        }
    }

    pub fn save(&self, store: &Store) -> Result<usize, String> {
        if !self.writable.get() {
            return Err(format!(
                "{}: świata nie dało się wczytać, zapis wstrzymany (nie nadpisuję)",
                self.world.display()
            ));
        }
        let n = save_store(store, &self.world, &self.crypt).map_err(|e| e.to_string())?;
        self.saves.set(self.saves.get() + 1);
        Ok(n)
    }

    pub fn writable(&self) -> bool {
        self.writable.get()
    }

    pub fn saves(&self) -> u64 {
        self.saves.get()
    }
}

/// Ścieżka świata w `data_home` (jak `cynober_paths.worlds_home()`).
pub fn world_in_data_home() -> PathBuf {
    let name = std::env::var("KARMAZYN_WORLD_NAME")
        .ok()
        .map(|v| v.trim().to_string())
        .filter(|v| !v.is_empty())
        .unwrap_or_else(|| DEFAULT_WORLD.into());
    karmazyn_kafd::cipher::data_home()
        .join("worlds")
        .join(format!("{name}.kafd"))
}

/// Czy początek urządzenia (do 1 MiB) to same zera — tylko taki dysk
/// formatujemy bez pytania.
pub fn is_blank(device: &Path) -> std::io::Result<bool> {
    use std::io::Read;
    let mut f = std::fs::File::open(device)?;
    let mut buf = vec![0u8; 1 << 20];
    let mut n = 0;
    while n < buf.len() {
        match f.read(&mut buf[n..])? {
            0 => break,
            k => n += k,
        }
    }
    Ok(buf[..n].iter().all(|b| *b == 0))
}

/// Zakłada ext2 na całym urządzeniu (albo pliku obrazu).
pub fn format(device: &Path) -> Result<crate::ext2::Layout, String> {
    use std::io::{Seek, SeekFrom};
    let mut f = std::fs::OpenOptions::new()
        .read(true)
        .write(true)
        .open(device)
        .map_err(|e| format!("{}: {e}", device.display()))?;
    let size = f.seek(SeekFrom::End(0)).map_err(|e| e.to_string())?;
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as u32)
        .unwrap_or(0);
    let mut uuid = [0u8; 16];
    getrandom::getrandom(&mut uuid).map_err(|e| e.to_string())?;
    let layout = crate::ext2::format(&mut f, size, now, uuid).map_err(|e| e.to_string())?;
    f.sync_all().map_err(|e| e.to_string())?;
    Ok(layout)
}

/// devtmpfs na `/dev`, raz na proces (konsola i dysk wołają to oba).
/// `Some` = opis błędu.
#[cfg(target_os = "linux")]
pub fn mount_dev() -> Option<String> {
    use std::ffi::CString;
    use std::sync::OnceLock;
    static DONE: OnceLock<Option<String>> = OnceLock::new();
    DONE.get_or_init(|| {
        let _ = std::fs::create_dir_all("/dev");
        let src = CString::new("devtmpfs").unwrap();
        let dst = CString::new("/dev").unwrap();
        // SAFETY: wskaźniki na żywe CString; data = NULL.
        let rc = unsafe {
            libc::mount(src.as_ptr(), dst.as_ptr(), src.as_ptr(), 0, std::ptr::null())
        };
        if rc == 0 {
            return None;
        }
        let e = std::io::Error::last_os_error();
        (e.raw_os_error() != Some(libc::EBUSY)).then(|| format!("mount /dev: {e}"))
    })
    .clone()
}

/// PID 1 na Linuksie: `/dev` (devtmpfs) i moduły z `/lib/modules` w kolejności
/// nazw (prefiks `NN-` ustala zależności), potem czeka chwilę na urządzenie.
/// Zwraca opis kroków, które się nie udały.
#[cfg(target_os = "linux")]
pub fn prepare(device: &Path) -> Vec<String> {
    use std::ffi::CString;
    use std::time::{Duration, Instant};

    let mut warn = Vec::new();
    if let Some(e) = mount_dev() {
        warn.push(e);
    }

    if let Ok(dir) = std::fs::read_dir("/lib/modules") {
        let mut mods: Vec<PathBuf> = dir
            .filter_map(|e| e.ok().map(|e| e.path()))
            .filter(|p| p.extension().is_some_and(|x| x == "ko"))
            .collect();
        mods.sort();
        for m in mods {
            let Ok(image) = std::fs::read(&m) else {
                warn.push(format!("read {}", m.display()));
                continue;
            };
            let params = CString::new("").unwrap();
            // SAFETY: obraz modułu żyje do końca wywołania.
            let rc = unsafe {
                libc::syscall(
                    libc::SYS_init_module,
                    image.as_ptr(),
                    image.len() as libc::c_ulong,
                    params.as_ptr(),
                )
            };
            if rc != 0 {
                let e = std::io::Error::last_os_error();
                if e.raw_os_error() != Some(libc::EEXIST) {
                    warn.push(format!("insmod {}: {e}", m.display()));
                }
            }
        }
    }

    let end = Instant::now() + Duration::from_secs(3);
    while !device.exists() && Instant::now() < end {
        std::thread::sleep(Duration::from_millis(50));
    }
    warn
}

#[cfg(not(target_os = "linux"))]
pub fn prepare(_device: &Path) -> Vec<String> {
    Vec::new()
}

/// `mount -t ext4 device target`.
#[cfg(target_os = "linux")]
pub fn mount_ext4(device: &Path, target: &Path) -> Result<(), String> {
    use std::ffi::CString;
    use std::os::unix::ffi::OsStrExt;
    std::fs::create_dir_all(target).map_err(|e| format!("{}: {e}", target.display()))?;
    let src = CString::new(device.as_os_str().as_bytes()).map_err(|e| e.to_string())?;
    let dst = CString::new(target.as_os_str().as_bytes()).map_err(|e| e.to_string())?;
    let fs = CString::new("ext4").unwrap();
    // ext2 bez księgowania: zapisy i metadane od razu na dysk (MS_SYNCHRONOUS),
    // bez aktualizacji czasu odczytu (MS_NOATIME)
    let flags = libc::MS_SYNCHRONOUS | libc::MS_NOATIME;
    // SAFETY: wskaźniki na żywe CString; data = NULL.
    let rc = unsafe { libc::mount(src.as_ptr(), dst.as_ptr(), fs.as_ptr(), flags, std::ptr::null()) };
    if rc == 0 {
        Ok(())
    } else {
        Err(format!("mount {}: {}", device.display(), std::io::Error::last_os_error()))
    }
}

#[cfg(not(target_os = "linux"))]
pub fn mount_ext4(_device: &Path, _target: &Path) -> Result<(), String> {
    Err("mount ext4 tylko na Linuksie (płyta)".into())
}

/// PID 1: dysk → ext4 pod `/data` → świat w `data_home`. Zwraca magazyn
/// (gdy dysk jest gotowy) i opis do linii startowej.
pub fn attach_device(device: &str, allow_format: bool) -> (Option<Storage>, Result<String, String>) {
    let dev = Path::new(device);
    let warn = prepare(dev);
    if !dev.exists() {
        let extra = if warn.is_empty() { String::new() } else { format!(" ({})", warn.join("; ")) };
        return (None, Err(format!("{device}: brak urządzenia{extra}")));
    }
    let target = Path::new(DATA_MOUNT);
    let mut note = String::new();
    if mount_ext4(dev, target).is_err() {
        let blank = is_blank(dev).unwrap_or(false);
        if !blank && !allow_format {
            return (
                None,
                Err(format!("{device}: nie ext4 i nie pusty — `disk format` wyczyści go i założy ext2")),
            );
        }
        if let Err(e) = format(dev) {
            return (None, Err(format!("{device}: format: {e}")));
        }
        if let Err(e) = mount_ext4(dev, target) {
            return (None, Err(e));
        }
        note = ", sformatowano".into();
    }
    if std::env::var_os("CYNOBER_DATA_HOME").is_none() {
        std::env::set_var("CYNOBER_DATA_HOME", target.join("cynober"));
    }
    let storage = Storage::new(world_in_data_home(), Some(device.to_string()));
    (Some(storage), Ok(format!("{device} ext4 → {DATA_MOUNT}{note}")))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn storage_roundtrip_and_refuses_unreadable_world() {
        let dir = std::env::temp_dir().join(format!("shell_world_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("swiat.kafd");
        let mut st = Storage::new(path.clone(), None);
        st.crypt = Crypt::with_master(&[5u8; 32]);
        let s = Store::new(true);
        assert_eq!(st.load(&s).unwrap(), None);
        let a = s.atom_new("var", "x", 60.0);
        let b = s.bubble_new("r", None);
        s.set_root(b);
        s.bind(b, "x", a).unwrap();
        st.save(&s).unwrap();

        let t = Store::new(true);
        assert_eq!(st.load(&t).unwrap(), Some((1, 1)));
        assert_eq!(t.lookup(b, "x"), Some(a));

        // zły klucz: odczyt zawodzi, zapis wstrzymany, plik nietknięty
        let before = std::fs::read(&path).unwrap();
        let mut bad = Storage::new(path.clone(), None);
        bad.crypt = Crypt::with_master(&[6u8; 32]);
        assert!(bad.load(&Store::new(true)).is_err());
        assert!(!bad.writable());
        assert!(bad.save(&Store::new(true)).is_err());
        assert_eq!(std::fs::read(&path).unwrap(), before);
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn blank_detection_and_format_file() {
        let dir = std::env::temp_dir().join(format!("shell_blank_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let img = dir.join("disk.img");
        std::fs::File::create(&img).unwrap().set_len(8 << 20).unwrap();
        assert!(is_blank(&img).unwrap());
        format(&img).unwrap();
        assert!(!is_blank(&img).unwrap());
        let head = std::fs::read(&img).unwrap();
        assert!(crate::ext2::has_ext_superblock(&head[..2048]));
        let _ = std::fs::remove_dir_all(&dir);
    }
}
