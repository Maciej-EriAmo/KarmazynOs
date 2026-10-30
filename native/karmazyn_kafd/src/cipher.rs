//! KAFX / KX1 — AES-256-GCM, klucz per świat. Zgodne z `DBase/karmazyn_cipher.py`.
//!
//! ```text
//! KAFX:  "KAFX" | ver=1 | kdf=1 | flags u16=0 | wlen u16 | świat | nonce 12 | AES-GCM(KAFD)
//!        AAD = "KAFX" | ver | kdf | świat
//! KX1:   "KX1\0" | nonce 12 | AES-GCM(atom.data),  AAD = id atomu (UTF-8)
//! klucz świata = HKDF-SHA256(master, salt="karmazyn-kafx-v1", info="world:<nazwa>")
//! ```
//!
//! Master: `CYNOBER_MASTER_KEY` / `KARMAZYN_MASTER_KEY` (64 hex, 32 znaki ASCII
//! albo dowolny napis → SHA-256), plik `CYNOBER_MASTER_KEY_FILE` /
//! `KARMAZYN_MASTER_KEY_FILE`, albo `{data_home}/master.key` (tworzony przy
//! pierwszym zapisie). Stary XOR ze stałym seedem — tylko odczyt.

use crate::{err, Error, Result, KAFX_MAGIC, KX1_MAGIC, MAGIC};
use aes_gcm::aead::{Aead, KeyInit, Payload};
use aes_gcm::{Aes256Gcm, Nonce};
use hkdf::Hkdf;
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};

pub const KAFX_VERSION: u8 = 1;
pub const KAFX_KDF_HKDF: u8 = 1;
pub const NONCE_LEN: usize = 12;
pub const KEY_LEN: usize = 32;
pub const HKDF_SALT: &[u8] = b"karmazyn-kafx-v1";
const PHI_XOR_SEED: &[u8] = b"KARMAZYN_PHI_ROOT_SPACE_V1_SEED";
const KAFS_MAGIC: &[u8; 4] = b"KAFS";

/// `KARMAZYN_KAFD_PLAIN=1|true|yes|on` — zapis bez koperty (debug).
pub fn plain_requested() -> bool {
    std::env::var("KARMAZYN_KAFD_PLAIN")
        .map(|v| matches!(v.trim().to_lowercase().as_str(), "1" | "true" | "yes" | "on"))
        .unwrap_or(false)
}

/// Nazwa świata z nazwy pliku (rdzeń bez rozszerzenia), inaczej `_default`.
pub fn infer_world_from_path(path: &Path) -> String {
    path.file_stem()
        .map(|s| s.to_string_lossy().into_owned())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| "_default".into())
}

fn parse_key_material(raw: &str) -> Vec<u8> {
    let s = raw.trim();
    if s.len() == 64 {
        if let Some(b) = from_hex(s) {
            return b;
        }
    }
    if s.chars().count() == 32 && s.is_ascii() {
        return s.as_bytes().to_vec();
    }
    Sha256::digest(s.as_bytes()).to_vec()
}

fn from_hex(s: &str) -> Option<Vec<u8>> {
    (0..s.len())
        .step_by(2)
        .map(|i| s.get(i..i + 2).and_then(|h| u8::from_str_radix(h, 16).ok()))
        .collect()
}

fn env_nonempty(keys: &[&str]) -> Option<String> {
    keys.iter()
        .filter_map(|k| std::env::var(k).ok())
        .map(|v| v.trim().to_string())
        .find(|v| !v.is_empty())
}

/// Jak `cynober_paths.data_home()`.
pub fn data_home() -> PathBuf {
    if let Some(d) = env_nonempty(&["CYNOBER_DATA_HOME"]) {
        return PathBuf::from(d);
    }
    if let Some(local) = env_nonempty(&["LOCALAPPDATA"]) {
        return PathBuf::from(local).join("Cynober");
    }
    let home = env_nonempty(&["HOME", "USERPROFILE"]).unwrap_or_else(|| "/".into());
    PathBuf::from(home).join(".local").join("share").join("cynober")
}

fn master_key_path() -> PathBuf {
    match env_nonempty(&["CYNOBER_MASTER_KEY_FILE", "KARMAZYN_MASTER_KEY_FILE"]) {
        Some(p) => PathBuf::from(p),
        None => data_home().join("master.key"),
    }
}

/// `resolve_master_key`: zmienna środowiska, plik, albo nowy losowy klucz w pliku.
pub fn resolve_master_key(create: bool) -> Result<Vec<u8>> {
    if let Some(raw) = env_nonempty(&["CYNOBER_MASTER_KEY", "KARMAZYN_MASTER_KEY"]) {
        return Ok(parse_key_material(&raw));
    }
    let path = master_key_path();
    if path.is_file() {
        let data = std::fs::read(&path)?;
        return Ok(if data.len() >= KEY_LEN {
            data[..KEY_LEN].to_vec()
        } else {
            Sha256::digest(&data).to_vec()
        });
    }
    if !create {
        return err(format!("brak master key ({})", path.display()));
    }
    if let Some(d) = path.parent() {
        std::fs::create_dir_all(d)?;
    }
    let mut key = vec![0u8; KEY_LEN];
    getrandom::getrandom(&mut key).map_err(|e| Error(format!("losowość: {e}")))?;
    std::fs::write(&path, &key)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600));
    }
    Ok(key)
}

/// Klucz główny podany jawnie albo z `resolve_master_key(create=true)`.
fn master_or_default(master: Option<&[u8]>) -> Result<Vec<u8>> {
    match master {
        Some(m) => Ok(m.to_vec()),
        None => resolve_master_key(true),
    }
}

/// `derive_world_key`: HKDF-SHA256(master, salt, "world:" + nazwa).
pub fn derive_world_key(world: &str, master: Option<&[u8]>) -> Result<[u8; KEY_LEN]> {
    let master = master_or_default(master)?;
    let name = if world.is_empty() { "_default" } else { world };
    let mut info = b"world:".to_vec();
    info.extend_from_slice(name.as_bytes());
    let mut okm = [0u8; KEY_LEN];
    Hkdf::<Sha256>::new(Some(HKDF_SALT), &master)
        .expand(&info, &mut okm)
        .map_err(|_| Error("HKDF: zła długość".into()))?;
    Ok(okm)
}

fn random_nonce() -> Result<[u8; NONCE_LEN]> {
    let mut n = [0u8; NONCE_LEN];
    getrandom::getrandom(&mut n).map_err(|e| Error(format!("losowość: {e}")))?;
    Ok(n)
}

fn seal(key: &[u8; KEY_LEN], nonce: &[u8; NONCE_LEN], plain: &[u8], aad: &[u8]) -> Result<Vec<u8>> {
    Aes256Gcm::new(key.into())
        .encrypt(Nonce::from_slice(nonce), Payload { msg: plain, aad })
        .map_err(|_| Error("AES-GCM: szyfrowanie".into()))
}

fn open(key: &[u8; KEY_LEN], nonce: &[u8], ct: &[u8], aad: &[u8]) -> Result<Vec<u8>> {
    Aes256Gcm::new(key.into())
        .decrypt(Nonce::from_slice(nonce), Payload { msg: ct, aad })
        .map_err(|_| Error("KAFX: zły klucz, zły świat albo uszkodzony plik".into()))
}

fn kafx_aad(world: &[u8]) -> Vec<u8> {
    let mut aad = KAFX_MAGIC.to_vec();
    aad.extend([KAFX_VERSION, KAFX_KDF_HKDF]);
    aad.extend_from_slice(world);
    aad
}

/// `wrap_kafx`: koperta całego bloba (świat jawnie w nagłówku).
pub fn wrap_kafx(plain: &[u8], world: &str, master: Option<&[u8]>) -> Result<Vec<u8>> {
    wrap_kafx_with_nonce(plain, world, master, &random_nonce()?)
}

/// Jak `wrap_kafx`, z podanym nonce (testy zgodności). Nonce nie może się
/// powtórzyć dla tego samego klucza — w produkcji tylko `wrap_kafx`.
#[doc(hidden)]
pub fn wrap_kafx_with_nonce(
    plain: &[u8],
    world: &str,
    master: Option<&[u8]>,
    nonce: &[u8; NONCE_LEN],
) -> Result<Vec<u8>> {
    let world = if world.is_empty() { "_default" } else { world };
    let w = world.as_bytes();
    if w.len() > 65535 {
        return err("nazwa świata za długa");
    }
    let key = derive_world_key(world, master)?;
    let ct = seal(&key, nonce, plain, &kafx_aad(w))?;
    let mut out = Vec::with_capacity(10 + w.len() + NONCE_LEN + ct.len());
    out.extend_from_slice(KAFX_MAGIC);
    out.extend([KAFX_VERSION, KAFX_KDF_HKDF]);
    out.extend(0u16.to_be_bytes());
    out.extend((w.len() as u16).to_be_bytes());
    out.extend_from_slice(w);
    out.extend_from_slice(nonce);
    out.extend(ct);
    Ok(out)
}

/// `unwrap_kafx`. `world`: gdy podany, musi się zgadzać ze światem w pliku.
pub fn unwrap_kafx(blob: &[u8], world: Option<&str>, master: Option<&[u8]>) -> Result<Vec<u8>> {
    if blob.len() < 10 + NONCE_LEN || !blob.starts_with(KAFX_MAGIC) {
        return err("to nie jest koperta KAFX");
    }
    let (ver, kdf) = (blob[4], blob[5]);
    if ver != KAFX_VERSION {
        return err(format!("KAFX: nieznana wersja {ver}"));
    }
    if kdf != KAFX_KDF_HKDF {
        return err(format!("KAFX: nieznany KDF {kdf}"));
    }
    let wlen = u16::from_be_bytes([blob[8], blob[9]]) as usize;
    let off = 10 + wlen;
    if blob.len() < off + NONCE_LEN + 16 {
        return err("KAFX: za krótki blob");
    }
    let wbytes = &blob[10..off];
    let stored = String::from_utf8_lossy(wbytes).into_owned();
    if let Some(w) = world.filter(|w| !w.is_empty()) {
        if w != stored {
            return err(format!("KAFX: świat w pliku {stored:?} ≠ żądany {w:?}"));
        }
    }
    let key = derive_world_key(&stored, master)?;
    open(&key, &blob[off..off + NONCE_LEN], &blob[off + NONCE_LEN..], &kafx_aad(wbytes))
}

/// `wrap_payload` (KX1): koperta danych atomu, AAD = id atomu.
pub fn wrap_payload(plain: &[u8], world: &str, aad: &[u8], master: Option<&[u8]>) -> Result<Vec<u8>> {
    wrap_payload_with_nonce(plain, world, aad, master, &random_nonce()?)
}

#[doc(hidden)]
pub fn wrap_payload_with_nonce(
    plain: &[u8],
    world: &str,
    aad: &[u8],
    master: Option<&[u8]>,
    nonce: &[u8; NONCE_LEN],
) -> Result<Vec<u8>> {
    let key = derive_world_key(world, master)?;
    let mut out = KX1_MAGIC.to_vec();
    out.extend_from_slice(nonce);
    out.extend(seal(&key, nonce, plain, aad)?);
    Ok(out)
}

pub fn unwrap_payload(blob: &[u8], world: &str, aad: &[u8], master: Option<&[u8]>) -> Result<Vec<u8>> {
    if !blob.starts_with(KX1_MAGIC) || blob.len() < 4 + NONCE_LEN + 16 {
        return err("to nie jest koperta KX1");
    }
    let key = derive_world_key(world, master)?;
    open(&key, &blob[4..4 + NONCE_LEN], &blob[4 + NONCE_LEN..], aad)
}

pub fn is_kafx(data: &[u8]) -> bool {
    data.starts_with(KAFX_MAGIC)
}

pub fn is_kx1(data: &[u8]) -> bool {
    data.starts_with(KX1_MAGIC)
}

/// Historyczny XOR (SHA-256-CTR ze stałym seedem) — tylko odczyt starych plików.
pub fn legacy_phi_xor(data: &[u8]) -> Vec<u8> {
    let key_hash = Sha256::digest(PHI_XOR_SEED);
    let mut out = Vec::with_capacity(data.len());
    for (counter, block) in data.chunks(32).enumerate() {
        let mut h = Sha256::new();
        h.update(key_hash);
        h.update((counter as u64).to_be_bytes());
        let stream = h.finalize();
        out.extend(block.iter().zip(stream.iter()).map(|(b, s)| b ^ s));
    }
    out
}

/// Tryb odczytu przechowanego bloba.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Stored {
    Kafx,
    Plain,
    XorLegacy,
}

/// `open_stored_bytes`: KAFX → odszyfruj; KAFD/KAFS → bez zmian; stary XOR.
pub fn open_stored_bytes(data: &[u8], world: Option<&str>, master: Option<&[u8]>) -> Result<(Vec<u8>, Stored)> {
    if is_kafx(data) {
        return Ok((unwrap_kafx(data, world, master)?, Stored::Kafx));
    }
    if data.starts_with(MAGIC) || data.starts_with(KAFS_MAGIC) {
        return Ok((data.to_vec(), Stored::Plain));
    }
    let xor = legacy_phi_xor(data);
    if xor.starts_with(MAGIC) || xor.starts_with(KAFS_MAGIC) {
        return Ok((xor, Stored::XorLegacy));
    }
    err("nierozpoznany blob (ani KAFX, ani KAFD/KAFS, ani stary XOR)")
}

/// `encrypt_for_path`: `encrypt=None` → szyfruj, chyba że KARMAZYN_KAFD_PLAIN.
pub fn encrypt_for_path(
    plain: Vec<u8>,
    path: &Path,
    world: Option<&str>,
    master: Option<&[u8]>,
    encrypt: Option<bool>,
) -> Result<Vec<u8>> {
    if !encrypt.unwrap_or_else(|| !plain_requested()) {
        return Ok(plain);
    }
    let w = world.map(str::to_string).unwrap_or_else(|| infer_world_from_path(path));
    wrap_kafx(&plain, &w, master)
}

#[cfg(test)]
mod tests {
    use super::*;

    const M: &[u8] = &[7u8; 32];

    #[test]
    fn hkdf_rfc5869_case1() {
        // RFC 5869 A.1 (SHA-256), pierwsze 32 B OKM
        let ikm = [0x0bu8; 22];
        let salt: Vec<u8> = (0u8..=0x0c).collect();
        let info: Vec<u8> = (0xf0u8..=0xf9).collect();
        let mut okm = [0u8; 32];
        Hkdf::<Sha256>::new(Some(&salt), &ikm).expand(&info, &mut okm).unwrap();
        assert_eq!(
            okm[..8],
            [0x3c, 0xb2, 0x5f, 0x25, 0xfa, 0xac, 0xd5, 0x7a]
        );
    }

    #[test]
    fn kafx_roundtrip_and_world_check() {
        let blob = wrap_kafx(b"KAFD....", "lore", Some(M)).unwrap();
        assert!(is_kafx(&blob));
        assert_eq!(unwrap_kafx(&blob, None, Some(M)).unwrap(), b"KAFD....");
        assert_eq!(unwrap_kafx(&blob, Some("lore"), Some(M)).unwrap(), b"KAFD....");
        assert!(unwrap_kafx(&blob, Some("inny"), Some(M)).unwrap_err().0.contains("świat"));
        assert!(unwrap_kafx(&blob, None, Some(&[8u8; 32])).unwrap_err().0.contains("zły klucz"));
        let mut bad = blob.clone();
        let n = bad.len();
        bad[n - 1] ^= 1;
        assert!(unwrap_kafx(&bad, None, Some(M)).is_err());
    }

    #[test]
    fn kx1_binds_atom_id() {
        let b = wrap_payload(b"dane", "w", b"atom.1", Some(M)).unwrap();
        assert!(is_kx1(&b));
        assert_eq!(unwrap_payload(&b, "w", b"atom.1", Some(M)).unwrap(), b"dane");
        assert!(unwrap_payload(&b, "w", b"atom.2", Some(M)).is_err());
        assert!(unwrap_payload(&b, "x", b"atom.1", Some(M)).is_err());
    }

    #[test]
    fn key_material_and_xor() {
        assert_eq!(parse_key_material(&"ab".repeat(32)), vec![0xab; 32]);
        assert_eq!(parse_key_material("0123456789abcdef0123456789ABCDEF!"), Sha256::digest(b"0123456789abcdef0123456789ABCDEF!").to_vec());
        assert_eq!(parse_key_material("x".repeat(32).as_str()), vec![b'x'; 32]);
        let x = legacy_phi_xor(b"KAFD stary plik ktory ma wiecej niz 32 bajty");
        assert_eq!(legacy_phi_xor(&x), b"KAFD stary plik ktory ma wiecej niz 32 bajty");
        let (plain, mode) = open_stored_bytes(&x, None, Some(M)).unwrap();
        assert_eq!((plain.starts_with(b"KAFD"), mode), (true, Stored::XorLegacy));
        assert_eq!(infer_world_from_path(Path::new("dir/lore.kafd")), "lore");
    }
}
