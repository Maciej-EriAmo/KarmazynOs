//! KAFD — Karmazyn Atom Flow Datum, implementacja natywna.
//!
//! Zgodna bajt w bajt z `DBase/karmazyn_kafd.py` (specyfikacja: `DBase/docs/KAFD.md`):
//!
//! - **KAFD v2.0** (`Layout::TableFirst`): `[HEADER 64][TABLE N×56][ID_POOL][META][PAYLOAD]`
//! - **KAFD v2.1** (`Layout::Footer`): `[HEADER 64][PAYLOAD][TABLE][ID_POOL][META][KTIX]`
//! - **KAFD v1** — tylko odczyt (stary nagłówek JSON)
//! - **KAFS** — ramki `[type:1][size:4][body][crc32:4]`: strumień (hot-first),
//!   dziennik z checkpointami i odzyskiwaniem ogona, `compact_journal` → v2.1.
//!
//! Wszystkie liczby big-endian. T zapisywane jako f32. `id_hash` = pierwsze 8 B
//! SHA-256 identyfikatora, CAS = pierwsze 12 B SHA-256 danych.
//!
//! Szyfrowanie jak `karmazyn_cipher.py` (moduł [`cipher`]): koperta pliku KAFX
//! i koperta danych atomu w dzienniku KX1, AES-256-GCM z kluczem świata
//! (HKDF-SHA256 z klucza węzła). Stary XOR tylko do odczytu.
//!
//! Moduł [`world`]: świat DBase (`karmazyn_store.py`, bąble jako atomy `__bubble__`);
//! z cechą `substrate` zapis i odczyt natywnego Store.

pub mod cipher;
mod flow;
mod json;
mod seek;
pub mod world;

pub use flow::{
    atomic_replace, compact_journal, sync_dir, Checkpoint, CompactReport, Crypt, FlowReader, FlowWriter,
    Journal, Recovery, FT_ATOM, FT_CHECKPOINT, FT_END, FT_META, KAFS_MAGIC,
};
pub use seek::{Entry, Layout, Reader, TickRecord, Writer};

use sha2::{Digest, Sha256};
use std::fmt;

pub const MAGIC: &[u8; 4] = b"KAFD";
pub const VERSION: u16 = 0x0200;
pub const VERSION_V21: u16 = 0x0201;
pub const HEADER_SIZE: usize = 64;
pub const ATOM_ENTRY: usize = 56;
pub const TICK_INDEX_MAGIC: &[u8; 4] = b"KTIX";
pub const TICK_INDEX_ENTRY: usize = 40;

pub const F_ENCRYPTED: u16 = 0x0001;
pub const F_COMPRESSED: u16 = 0x0002;
pub const F_SIGNED: u16 = 0x0004;
pub const F_STREAMING: u16 = 0x0008;
pub const F_PHI_NATIVE: u16 = 0x0010;
pub const F_FOOTER_TOC: u16 = 0x0020;

pub const S_COLD: u8 = 0;
pub const S_WARM: u8 = 1;
pub const S_HOT: u8 = 2;
pub const S_TOMB: u8 = 3;

pub const A_RAW: u8 = 0;
pub const A_MANIFEST: u8 = 1;
pub const A_STREAM: u8 = 2;
pub const A_PHI_ATOM: u8 = 3;
pub const A_THERMAL: u8 = 4;

pub const MIME_DEFAULT: &str = "application/octet-stream";
pub const MIME_THERMAL: &str = "application/x-karmazyn-thermal-frame";

/// Prefiks zaszyfrowanej koperty pliku (KAFX) i ramki atomu (KX1).
pub const KAFX_MAGIC: &[u8; 4] = b"KAFX";
pub const KX1_MAGIC: &[u8; 4] = b"KX1\x00";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Error(pub String);

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for Error {}

impl From<std::io::Error> for Error {
    fn from(e: std::io::Error) -> Self {
        Error(e.to_string())
    }
}

pub type Result<T> = std::result::Result<T, Error>;

pub(crate) fn err<T>(msg: impl Into<String>) -> Result<T> {
    Err(Error(msg.into()))
}

/// Atom KAFD — jednostka przepływu (tekst, obraz, atom Φ, klatka termiczna…).
#[derive(Debug, Clone, PartialEq)]
pub struct Atom {
    pub id: String,
    pub data: Vec<u8>,
    pub mime: String,
    pub t: f64,
    pub t_max: f64,
    pub state: u8,
    pub atype: u8,
    pub cas: [u8; 12],
}

impl Atom {
    /// Jak `KAFDAtom(id, data, mime, T, T_max, atype)`: stan z T, CAS z danych.
    pub fn new(
        id: impl Into<String>,
        data: Vec<u8>,
        mime: impl Into<String>,
        t: f64,
        t_max: f64,
        atype: u8,
    ) -> Self {
        let cas = cas_hash(&data);
        Atom {
            id: id.into(),
            data,
            mime: mime.into(),
            t,
            t_max,
            state: state_for_t(t),
            atype,
            cas,
        }
    }

    /// Atom surowy z domyślnymi T=50, T_max=100.
    pub fn raw(id: impl Into<String>, data: Vec<u8>, mime: impl Into<String>) -> Self {
        Atom::new(id, data, mime, 50.0, 100.0, A_RAW)
    }

    pub fn size(&self) -> usize {
        self.data.len()
    }
}

/// `_T_to_state`: HOT > 70, WARM > 30, COLD > 2, inaczej TOMB.
pub fn state_for_t(t: f64) -> u8 {
    if t > 70.0 {
        S_HOT
    } else if t > 30.0 {
        S_WARM
    } else if t > 2.0 {
        S_COLD
    } else {
        S_TOMB
    }
}

/// `_id_hash`: pierwsze 8 B SHA-256(id UTF-8), big-endian.
pub fn id_hash(id: &str) -> u64 {
    let h = Sha256::digest(id.as_bytes());
    u64::from_be_bytes(h[..8].try_into().unwrap())
}

/// `_cas_hash`: pierwsze 12 B SHA-256 danych.
pub fn cas_hash(data: &[u8]) -> [u8; 12] {
    let h = Sha256::digest(data);
    h[..12].try_into().unwrap()
}

pub(crate) fn align8(n: usize) -> usize {
    (n + 7) & !7
}

const fn crc_table() -> [u32; 256] {
    let mut t = [0u32; 256];
    let mut i = 0;
    while i < 256 {
        let mut c = i as u32;
        let mut k = 0;
        while k < 8 {
            c = if c & 1 != 0 { 0xEDB8_8320 ^ (c >> 1) } else { c >> 1 };
            k += 1;
        }
        t[i] = c;
        i += 1;
    }
    t
}

static CRC_TABLE: [u32; 256] = crc_table();

/// CRC-32 jak `zlib.crc32` (IEEE, odbity).
pub fn crc32(data: &[u8]) -> u32 {
    let mut c = 0xFFFF_FFFFu32;
    for b in data {
        c = CRC_TABLE[((c ^ u32::from(*b)) & 0xFF) as usize] ^ (c >> 8);
    }
    c ^ 0xFFFF_FFFF
}

/// Koperta `ThermalFrame` v1/v2 (little-endian) bez dekodowania atomów.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ThermalHeader {
    pub version: u8,
    pub kind: u8,
    pub timestamp: u64,
    pub tick: u64,
    pub num_atoms: u32,
    pub t_min: f32,
    pub t_max: f32,
}

/// `peek_thermal_header`: v2 = 30 B (kind, T_min/T_max), v1 = 21 B.
pub fn peek_thermal_header(data: &[u8]) -> Option<ThermalHeader> {
    if data.len() < 21 {
        return None;
    }
    let u64le = |o: usize| u64::from_le_bytes(data[o..o + 8].try_into().unwrap());
    let u32le = |o: usize| u32::from_le_bytes(data[o..o + 4].try_into().unwrap());
    let f32le = |o: usize| f32::from_le_bytes(data[o..o + 4].try_into().unwrap());
    match data[0] {
        1 => Some(ThermalHeader {
            version: 1,
            kind: 0,
            timestamp: u64le(1),
            tick: u64le(9),
            num_atoms: u32le(17),
            t_min: 0.0,
            t_max: 0.0,
        }),
        2 if data.len() >= 30 => Some(ThermalHeader {
            version: 2,
            kind: data[1],
            timestamp: u64le(2),
            tick: u64le(10),
            num_atoms: u32le(18),
            t_min: f32le(22),
            t_max: f32le(26),
        }),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn crc32_matches_zlib() {
        // zlib.crc32(b"123456789") == 0xCBF43926
        assert_eq!(crc32(b"123456789"), 0xCBF4_3926);
        assert_eq!(crc32(b""), 0);
    }

    #[test]
    fn hashes_match_python() {
        // hashlib.sha256(b"abc") = ba7816bf8f01cfea414140de5dae2223...
        assert_eq!(id_hash("abc"), 0xba78_16bf_8f01_cfea);
        assert_eq!(
            cas_hash(b"abc"),
            [0xba, 0x78, 0x16, 0xbf, 0x8f, 0x01, 0xcf, 0xea, 0x41, 0x41, 0x40, 0xde]
        );
    }

    #[test]
    fn states_follow_thresholds() {
        assert_eq!(state_for_t(71.0), S_HOT);
        assert_eq!(state_for_t(70.0), S_WARM);
        assert_eq!(state_for_t(30.0), S_COLD);
        assert_eq!(state_for_t(2.0), S_TOMB);
    }

    #[test]
    fn thermal_header_v2() {
        let mut d = vec![2u8, 1];
        d.extend(7u64.to_le_bytes());
        d.extend(417u64.to_le_bytes());
        d.extend(3u32.to_le_bytes());
        d.extend(40f32.to_le_bytes());
        d.extend(70f32.to_le_bytes());
        let h = peek_thermal_header(&d).unwrap();
        assert_eq!((h.kind, h.tick, h.num_atoms, h.t_min, h.t_max), (1, 417, 3, 40.0, 70.0));
        assert!(peek_thermal_header(&d[..20]).is_none());
    }
}
