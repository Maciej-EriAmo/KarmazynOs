//! Trwały dysk shella: snapshot KSUB na surowym urządzeniu blokowym.
//!
//! Bez systemu plików. Urządzenie dzieli się na dwa sloty (A i B). Każdy zaczyna
//! się nagłówkiem, po nim leżą bajty snapshotu:
//!
//! ```text
//! 0   8  magic  "KDISK01\0"
//! 8   8  gen    numer zapisu (rośnie)
//! 16  8  len    długość snapshotu
//! 24  8  sum    FNV-1a 64 (gen, len, dane)
//! ```
//!
//! `sync` pisze do starszego slotu: najpierw dane, fsync, potem nagłówek, fsync.
//! Zerwany zapis zostawia poprzedni slot nietknięty. Odczyt bierze ważny slot
//! z najwyższym `gen`.

use std::fs::{File, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};

const MAGIC: &[u8; 8] = b"KDISK01\0";
const HDR: u64 = 32;
const ALIGN: u64 = 4096;
pub const DEFAULT_DEVICE: &str = "/dev/vda";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Slot {
    pub gen: u64,
    pub len: u64,
}

pub struct Disk {
    path: PathBuf,
}

fn fnv1a(gen: u64, len: u64, data: &[u8]) -> u64 {
    let mut h: u64 = 0xcbf2_9ce4_8422_2325;
    for b in gen.to_le_bytes().iter().chain(len.to_le_bytes().iter()).chain(data) {
        h ^= u64::from(*b);
        h = h.wrapping_mul(0x0000_0100_0000_01b3);
    }
    h
}

fn u64_at(b: &[u8], at: usize) -> u64 {
    let mut a = [0u8; 8];
    a.copy_from_slice(&b[at..at + 8]);
    u64::from_le_bytes(a)
}

impl Disk {
    pub fn new(path: impl Into<PathBuf>) -> Self {
        Disk { path: path.into() }
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    fn open(&self, write: bool) -> Result<File, String> {
        OpenOptions::new()
            .read(true)
            .write(write)
            .open(&self.path)
            .map_err(|e| format!("{}: {e}", self.path.display()))
    }

    /// Rozmiar urządzenia (dla pliku blokowego seek na koniec daje pojemność).
    pub fn size(&self) -> Result<u64, String> {
        let mut f = self.open(false)?;
        f.seek(SeekFrom::End(0)).map_err(|e| e.to_string())
    }

    fn slot_size(&self) -> Result<u64, String> {
        let size = self.size()?;
        let slot = (size / 2) / ALIGN * ALIGN;
        if slot <= HDR {
            return Err(format!("{}: za mały ({size} B)", self.path.display()));
        }
        Ok(slot)
    }

    /// Nagłówek i dane slotu `i`, gdy suma się zgadza.
    fn read_slot(&self, f: &mut File, i: u64, slot: u64) -> Option<(Slot, Vec<u8>)> {
        let mut h = [0u8; HDR as usize];
        f.seek(SeekFrom::Start(i * slot)).ok()?;
        f.read_exact(&mut h).ok()?;
        if &h[0..8] != MAGIC {
            return None;
        }
        let gen = u64_at(&h, 8);
        let len = u64_at(&h, 16);
        let sum = u64_at(&h, 24);
        if len > slot - HDR {
            return None;
        }
        let mut data = vec![0u8; len as usize];
        f.read_exact(&mut data).ok()?;
        (fnv1a(gen, len, &data) == sum).then_some((Slot { gen, len }, data))
    }

    /// Stan obu slotów (A, B). `None` = pusty albo uszkodzony.
    pub fn slots(&self) -> Result<[Option<Slot>; 2], String> {
        let slot = self.slot_size()?;
        let mut f = self.open(false)?;
        Ok([
            self.read_slot(&mut f, 0, slot).map(|s| s.0),
            self.read_slot(&mut f, 1, slot).map(|s| s.0),
        ])
    }

    /// Najnowszy ważny snapshot.
    pub fn read_latest(&self) -> Result<Option<(Slot, Vec<u8>)>, String> {
        let slot = self.slot_size()?;
        let mut f = self.open(false)?;
        let a = self.read_slot(&mut f, 0, slot);
        let b = self.read_slot(&mut f, 1, slot);
        Ok(match (a, b) {
            (Some(a), Some(b)) => Some(if b.0.gen > a.0.gen { b } else { a }),
            (a, b) => a.or(b),
        })
    }

    /// Zapis do starszego slotu. Zwraca nowy `gen`.
    pub fn write_next(&self, data: &[u8]) -> Result<Slot, String> {
        let slot = self.slot_size()?;
        let len = data.len() as u64;
        if len > slot - HDR {
            return Err(format!("snapshot {len} B > slot {} B", slot - HDR));
        }
        let [a, b] = self.slots()?;
        let (i, gen) = match (a, b) {
            (Some(a), Some(b)) if a.gen <= b.gen => (0, b.gen + 1),
            (Some(a), Some(_)) => (1, a.gen + 1),
            (Some(a), None) => (1, a.gen + 1),
            (None, Some(b)) => (0, b.gen + 1),
            (None, None) => (0, 1),
        };
        let mut f = self.open(true)?;
        let io = |e: std::io::Error| e.to_string();
        f.seek(SeekFrom::Start(i * slot + HDR)).map_err(io)?;
        f.write_all(data).map_err(io)?;
        f.sync_all().map_err(io)?;
        let mut h = [0u8; HDR as usize];
        h[0..8].copy_from_slice(MAGIC);
        h[8..16].copy_from_slice(&gen.to_le_bytes());
        h[16..24].copy_from_slice(&len.to_le_bytes());
        h[24..32].copy_from_slice(&fnv1a(gen, len, data).to_le_bytes());
        f.seek(SeekFrom::Start(i * slot)).map_err(io)?;
        f.write_all(&h).map_err(io)?;
        f.sync_all().map_err(io)?;
        Ok(Slot { gen, len })
    }
}

/// PID 1 na Linuksie: `/dev` (devtmpfs) i moduły z `/lib/modules`, potem
/// czeka chwilę na urządzenie. Zwraca opis kroków, które się nie udały.
#[cfg(target_os = "linux")]
pub fn prepare(device: &Path) -> Vec<String> {
    use std::ffi::CString;
    use std::time::{Duration, Instant};

    let mut warn = Vec::new();
    let _ = std::fs::create_dir_all("/dev");
    let src = CString::new("devtmpfs").unwrap();
    let dst = CString::new("/dev").unwrap();
    // SAFETY: wskaźniki na żywe CString; data = NULL.
    let rc = unsafe {
        libc::mount(src.as_ptr(), dst.as_ptr(), src.as_ptr(), 0, std::ptr::null())
    };
    if rc != 0 {
        let e = std::io::Error::last_os_error();
        if e.raw_os_error() != Some(libc::EBUSY) {
            warn.push(format!("mount /dev: {e}"));
        }
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

#[cfg(test)]
mod tests {
    use super::*;

    fn blank(name: &str, size: u64) -> Disk {
        let p = std::env::temp_dir().join(format!("kdisk_{name}_{}.raw", std::process::id()));
        let f = File::create(&p).unwrap();
        f.set_len(size).unwrap();
        Disk::new(p)
    }

    #[test]
    fn empty_disk_has_nothing() {
        let d = blank("empty", 64 * 1024);
        assert_eq!(d.read_latest().unwrap(), None);
        assert_eq!(d.slots().unwrap(), [None, None]);
        let _ = std::fs::remove_file(d.path());
    }

    #[test]
    fn writes_alternate_and_latest_wins() {
        let d = blank("alt", 64 * 1024);
        assert_eq!(d.write_next(b"one").unwrap().gen, 1);
        assert_eq!(d.write_next(b"two").unwrap().gen, 2);
        assert_eq!(d.write_next(b"three").unwrap().gen, 3);
        let [a, b] = d.slots().unwrap();
        assert_eq!(a.unwrap().gen, 3);
        assert_eq!(b.unwrap().gen, 2);
        let (s, data) = d.read_latest().unwrap().unwrap();
        assert_eq!((s.gen, data.as_slice()), (3, &b"three"[..]));
        let _ = std::fs::remove_file(d.path());
    }

    #[test]
    fn torn_slot_falls_back_to_previous() {
        let d = blank("torn", 64 * 1024);
        d.write_next(b"good").unwrap();
        d.write_next(b"newer").unwrap();
        // psuje dane slotu B (gen 2): suma się nie zgadza
        let mut f = OpenOptions::new().write(true).open(d.path()).unwrap();
        f.seek(SeekFrom::Start(32 * 1024 + HDR)).unwrap();
        f.write_all(b"X").unwrap();
        drop(f);
        let (s, data) = d.read_latest().unwrap().unwrap();
        assert_eq!((s.gen, data.as_slice()), (1, &b"good"[..]));
        // następny zapis nadpisuje uszkodzony slot, nie dobry
        assert_eq!(d.write_next(b"again").unwrap().gen, 2);
        assert_eq!(d.slots().unwrap()[0].unwrap().gen, 1);
        let _ = std::fs::remove_file(d.path());
    }

    #[test]
    fn too_big_is_refused() {
        let d = blank("big", 16 * 1024);
        assert!(d.write_next(&vec![0u8; 9000]).is_err());
        let _ = std::fs::remove_file(d.path());
    }
}
