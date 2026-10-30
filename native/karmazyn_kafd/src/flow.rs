//! KAFS: ramkowy przepływ atomów (`KAFDFlowWriter` / `KAFDFlowReader`),
//! dziennik `KAFDJournal` i `compact_journal`.
//!
//! Ramka: `[type:1][size:4 = len(body)+4][body][crc32(body):4]`, big-endian.
//! Nagłówek strumienia: `KAFS` + wersja 0x0200 + flagi.

use crate::json;
use crate::seek::{Layout, Writer};
use crate::{
    crc32, err, peek_thermal_header, Atom, Error, Result, F_PHI_NATIVE,
    F_STREAMING, KX1_MAGIC, VERSION,
};
use serde_json::{Map, Value};
use std::fs::{self, File, OpenOptions};
use std::io::{ErrorKind, Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};

pub const KAFS_MAGIC: &[u8; 4] = b"KAFS";
pub const FT_ATOM: u8 = 0x01;
pub const FT_META: u8 = 0x02;
pub const FT_CHECKPOINT: u8 = 0x03;
pub const FT_END: u8 = 0xFF;

fn write_frame<W: Write>(sink: &mut W, kind: u8, body: &[u8]) -> Result<u64> {
    let mut head = [0u8; 5];
    head[0] = kind;
    head[1..].copy_from_slice(&((body.len() + 4) as u32).to_be_bytes());
    sink.write_all(&head)?;
    sink.write_all(body)?;
    sink.write_all(&crc32(body).to_be_bytes())?;
    Ok(5 + body.len() as u64 + 4)
}

fn stream_header(flags: u16) -> [u8; 8] {
    let mut h = [0u8; 8];
    h[..4].copy_from_slice(KAFS_MAGIC);
    h[4..6].copy_from_slice(&VERSION.to_be_bytes());
    h[6..].copy_from_slice(&flags.to_be_bytes());
    h
}

fn meta_body(meta: &Map<String, Value>) -> Vec<u8> {
    let m = json::dumps(meta);
    let mut body = (m.len() as u32).to_be_bytes().to_vec();
    body.extend(m);
    body
}

/// `_encode_atom_frame_body`.
pub(crate) fn encode_atom(a: &Atom) -> Vec<u8> {
    let id = a.id.as_bytes();
    let mime = a.mime.as_bytes();
    let mut b = Vec::with_capacity(id.len() + mime.len() + 22 + a.data.len());
    b.extend((id.len() as u16).to_be_bytes());
    b.extend_from_slice(id);
    b.extend((mime.len() as u16).to_be_bytes());
    b.extend_from_slice(mime);
    b.extend((a.t as f32).to_be_bytes());
    b.extend((a.t_max as f32).to_be_bytes());
    b.push(a.state);
    b.push(a.atype);
    b.extend((a.data.len() as u64).to_be_bytes());
    b.extend_from_slice(&a.data);
    b
}

/// `_parse_atom_frame_body`. Stan z ramki, CAS liczony od nowa (jak w Pythonie).
pub(crate) fn decode_atom(b: &[u8]) -> Option<Atom> {
    let mut o = 0usize;
    let mut take = |n: usize| -> Option<&[u8]> {
        let s = b.get(o..o + n)?;
        o += n;
        Some(s)
    };
    let id_len = u16::from_be_bytes(take(2)?.try_into().ok()?) as usize;
    let id = std::str::from_utf8(take(id_len)?).ok()?.to_string();
    let ml = u16::from_be_bytes(take(2)?.try_into().ok()?) as usize;
    let mime = std::str::from_utf8(take(ml)?).ok()?.to_string();
    let t = f32::from_be_bytes(take(4)?.try_into().ok()?);
    let t_max = f32::from_be_bytes(take(4)?.try_into().ok()?);
    let sa = take(2)?;
    let (state, atype) = (sa[0], sa[1]);
    let len = u64::from_be_bytes(take(8)?.try_into().ok()?) as usize;
    // Python bierze body[off:off+len] — krótsze dane też przechodzą
    let start = o;
    let data = b[start..(start + len).min(b.len())].to_vec();
    let mut a = Atom::new(id, data, mime, f64::from(t), f64::from(t_max), atype);
    a.state = state;
    Some(a)
}

fn checkpoint_body(tick: u64, n_frames: u64, t_min: f32, t_max: f32, kind: u8, causality: &str) -> Vec<u8> {
    let c = causality.as_bytes();
    let mut b = Vec::with_capacity(29 + c.len());
    b.extend(tick.to_be_bytes());
    b.extend(n_frames.to_be_bytes());
    b.extend(t_min.to_be_bytes());
    b.extend(t_max.to_be_bytes());
    b.push(kind);
    b.extend((c.len() as u32).to_be_bytes());
    b.extend_from_slice(c);
    b
}

/// Checkpoint dziennika (`_decode_checkpoint_body`).
#[derive(Debug, Clone, PartialEq)]
pub struct Checkpoint {
    pub tick: u64,
    pub n_frames: u64,
    pub t_min: f32,
    pub t_max: f32,
    pub kind: u8,
    pub causality: String,
}

fn decode_checkpoint(b: &[u8]) -> Option<Checkpoint> {
    if b.len() < 25 {
        return None;
    }
    let clen = b
        .get(25..29)
        .map(|x| u32::from_be_bytes(x.try_into().unwrap()) as usize)
        .unwrap_or(0);
    let c = b.get(29..(29 + clen).min(b.len())).unwrap_or(&[]);
    Some(Checkpoint {
        tick: u64::from_be_bytes(b[0..8].try_into().unwrap()),
        n_frames: u64::from_be_bytes(b[8..16].try_into().unwrap()),
        t_min: f32::from_be_bytes(b[16..20].try_into().unwrap()),
        t_max: f32::from_be_bytes(b[20..24].try_into().unwrap()),
        kind: b[24],
        causality: String::from_utf8_lossy(c).into_owned(),
    })
}

fn refuse_kx1(a: &Atom) -> Result<()> {
    if a.data.starts_with(KX1_MAGIC) {
        return err(format!(
            "KAFS: atom {:?} zaszyfrowany (KX1) — odszyfrowanie jeszcze nie jest natywne",
            a.id
        ));
    }
    Ok(())
}

/// `KAFDFlowWriter`: META, atomy malejąco po T (stabilnie), END.
#[derive(Default)]
pub struct FlowWriter {
    meta: Map<String, Value>,
    atoms: Vec<Atom>,
}

impl FlowWriter {
    pub fn new(meta: Map<String, Value>) -> Self {
        FlowWriter { meta, atoms: Vec::new() }
    }

    pub fn add(&mut self, a: Atom) -> &mut Self {
        self.atoms.push(a);
        self
    }

    pub fn write_to<W: Write>(&self, sink: &mut W) -> Result<u64> {
        sink.write_all(&stream_header(F_PHI_NATIVE))?;
        let mut w = 8;
        if !self.meta.is_empty() {
            w += write_frame(sink, FT_META, &meta_body(&self.meta))?;
        }
        let mut order: Vec<&Atom> = self.atoms.iter().collect();
        // sorted(key=-T): stabilny, malejąco
        order.sort_by(|a, b| b.t.partial_cmp(&a.t).unwrap_or(std::cmp::Ordering::Equal));
        let mut total = 0u64;
        for a in &order {
            w += write_frame(sink, FT_ATOM, &encode_atom(a))?;
            total += a.data.len() as u64;
        }
        let mut end = (order.len() as u32).to_be_bytes().to_vec();
        end.extend(total.to_be_bytes());
        w += write_frame(sink, FT_END, &end)?;
        Ok(w)
    }

    pub fn build(&self) -> Vec<u8> {
        let mut v = Vec::new();
        self.write_to(&mut v).expect("zapis do Vec");
        v
    }
}

/// `KAFDFlowReader` nad dowolnym `Read`.
pub struct FlowReader<R: Read> {
    src: R,
    flags: u16,
    sorted_by_t: bool,
    meta: Map<String, Value>,
    pub last_checkpoint: Option<Checkpoint>,
}

impl<R: Read> FlowReader<R> {
    /// `sorted_by_t`: strumień hot-first (próg `min_t` kończy). Dziennik
    /// z flagą F_STREAMING przełącza to sam w `read_header`.
    pub fn new(src: R, sorted_by_t: bool) -> Self {
        FlowReader { src, flags: 0, sorted_by_t, meta: Map::new(), last_checkpoint: None }
    }

    pub fn read_header(&mut self) -> Result<(u16, u16)> {
        let mut h = [0u8; 8];
        self.src.read_exact(&mut h).map_err(|e| Error(format!("KAFS: nagłówek: {e}")))?;
        if &h[..4] != KAFS_MAGIC {
            return err(format!("KAFS: zly magic {:?}", &h[..4]));
        }
        let version = u16::from_be_bytes([h[4], h[5]]);
        self.flags = u16::from_be_bytes([h[6], h[7]]);
        if self.flags & F_STREAMING != 0 {
            self.sorted_by_t = false;
        }
        Ok((version, self.flags))
    }

    pub fn flags(&self) -> u16 {
        self.flags
    }

    pub fn meta(&self) -> &Map<String, Value> {
        &self.meta
    }

    /// Następna ramka `(typ, body)`. `None` na EOF (także urwanym).
    pub fn next_frame(&mut self, verify_crc: bool) -> Result<Option<(u8, Vec<u8>)>> {
        let mut head = [0u8; 5];
        match self.src.read_exact(&mut head) {
            Ok(()) => {}
            Err(e) if e.kind() == ErrorKind::UnexpectedEof => return Ok(None),
            Err(e) => return Err(e.into()),
        }
        let size = u32::from_be_bytes(head[1..5].try_into().unwrap()) as usize;
        let mut payload = vec![0u8; size];
        match self.src.read_exact(&mut payload) {
            Ok(()) => {}
            Err(e) if e.kind() == ErrorKind::UnexpectedEof => return Ok(None),
            Err(e) => return Err(e.into()),
        }
        if size < 4 {
            return Ok(None);
        }
        let crc = u32::from_be_bytes(payload[size - 4..].try_into().unwrap());
        payload.truncate(size - 4);
        if verify_crc && crc != crc32(&payload) {
            return err(format!(
                "KAFS CRC: stored={crc:#010x} computed={:#010x}",
                crc32(&payload)
            ));
        }
        Ok(Some((head[0], payload)))
    }

    /// `iter_atoms(min_T)`: META i CHECKPOINT zapamiętane, END kończy.
    pub fn atoms(&mut self, min_t: f64) -> Result<Vec<Atom>> {
        let mut out = Vec::new();
        while let Some((kind, body)) = self.next_frame(true)? {
            match kind {
                FT_META => {
                    let n = body
                        .get(..4)
                        .map(|b| u32::from_be_bytes(b.try_into().unwrap()) as usize)
                        .unwrap_or(0);
                    if let Some(m) = body.get(4..4 + n).and_then(json::loads) {
                        self.meta = m;
                    }
                }
                FT_END => break,
                FT_CHECKPOINT => self.last_checkpoint = decode_checkpoint(&body),
                FT_ATOM => {
                    let Some(a) = decode_atom(&body) else { continue };
                    if a.t >= min_t {
                        out.push(a);
                    } else if min_t > 0.0 && self.sorted_by_t {
                        break;
                    }
                }
                _ => {}
            }
        }
        Ok(out)
    }
}

/// Wynik `recover`.
#[derive(Debug, Clone, PartialEq)]
pub struct Recovery {
    pub truncated: bool,
    pub reason: &'static str,
    pub frames: u64,
    pub empty: bool,
    pub last_good: u64,
    pub file_size: u64,
    pub last_checkpoint: Option<Checkpoint>,
    pub last_tick: u64,
}

/// `KAFDJournal`: append-only KAFS z flagą F_STREAMING, checkpointy,
/// obcięcie urwanej ramki przy otwarciu. Zapis jawny (bez KX1).
pub struct Journal {
    path: PathBuf,
    file: Option<File>,
    fsync: bool,
    pub n_frames: u64,
    pub last_tick: u64,
    pub last_checkpoint: Option<Checkpoint>,
    pub recovered: Recovery,
}

impl Journal {
    pub fn open(path: impl AsRef<Path>, fsync: bool, meta: &Map<String, Value>) -> Result<Self> {
        let path = path.as_ref().to_path_buf();
        if let Some(d) = path.parent().filter(|d| !d.as_os_str().is_empty()) {
            fs::create_dir_all(d)?;
        }
        let existing = fs::metadata(&path).map(|m| m.len() >= 8).unwrap_or(false);
        let (file, recovered) = if existing {
            let rec = recover(&path)?;
            let mut f = OpenOptions::new().read(true).write(true).open(&path)?;
            f.seek(SeekFrom::End(0))?;
            (f, rec)
        } else {
            let mut f = OpenOptions::new()
                .read(true)
                .write(true)
                .create(true)
                .truncate(true)
                .open(&path)?;
            f.write_all(&stream_header(F_PHI_NATIVE | F_STREAMING))?;
            if !meta.is_empty() {
                write_frame(&mut f, FT_META, &meta_body(meta))?;
            }
            f.flush()?;
            if fsync {
                f.sync_all()?;
            }
            (
                f,
                Recovery {
                    truncated: false,
                    reason: "",
                    frames: 0,
                    empty: true,
                    last_good: 0,
                    file_size: 0,
                    last_checkpoint: None,
                    last_tick: 0,
                },
            )
        };
        let ck = recovered.last_checkpoint.clone();
        Ok(Journal {
            path,
            file: Some(file),
            fsync,
            n_frames: recovered.frames,
            last_tick: if recovered.last_tick != 0 {
                recovered.last_tick
            } else {
                ck.as_ref().map(|c| c.tick).unwrap_or(0)
            },
            last_checkpoint: ck,
            recovered,
        })
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    fn sync(&mut self) -> Result<()> {
        if let Some(f) = self.file.as_mut() {
            f.flush()?;
            if self.fsync {
                f.sync_all()?;
            }
        }
        Ok(())
    }

    fn file(&mut self) -> Result<&mut File> {
        self.file.as_mut().ok_or_else(|| Error("KAFDJournal zamknięty".into()))
    }

    pub fn append_atom(&mut self, a: &Atom) -> Result<u64> {
        let n = write_frame(self.file()?, FT_ATOM, &encode_atom(a))?;
        self.n_frames += 1;
        if let Some(h) = peek_thermal_header(&a.data) {
            self.last_tick = h.tick;
        }
        self.sync()?;
        Ok(n)
    }

    pub fn checkpoint(&mut self, tick: u64, causality: &str, t_min: f32, t_max: f32, kind: u8) -> Result<u64> {
        let body = checkpoint_body(tick, self.n_frames, t_min, t_max, kind, causality);
        let n = write_frame(self.file()?, FT_CHECKPOINT, &body)?;
        self.last_checkpoint = decode_checkpoint(&body);
        self.last_tick = tick;
        self.sync()?;
        Ok(n)
    }

    /// Atomy od początku pliku (osobny uchwyt).
    pub fn atoms(&self, min_t: f64) -> Result<Vec<Atom>> {
        let mut r = FlowReader::new(std::io::BufReader::new(File::open(&self.path)?), false);
        r.read_header()?;
        let atoms = r.atoms(min_t)?;
        for a in &atoms {
            refuse_kx1(a)?;
        }
        Ok(atoms)
    }

    pub fn close(&mut self, write_end: bool) -> Result<()> {
        if self.file.is_none() {
            return Ok(());
        }
        if write_end {
            let mut end = (self.n_frames as u32).to_be_bytes().to_vec();
            end.extend(0u64.to_be_bytes());
            write_frame(self.file()?, FT_END, &end)?;
            self.sync()?;
        }
        self.file = None;
        Ok(())
    }
}

/// `recover`: skan ramek, obcięcie po ostatnim dobrym CRC.
pub fn recover(path: &Path) -> Result<Recovery> {
    let size = fs::metadata(path).map(|m| m.len()).unwrap_or(0);
    let mut rec = Recovery {
        truncated: false,
        reason: "",
        frames: 0,
        empty: size == 0,
        last_good: 0,
        file_size: size,
        last_checkpoint: None,
        last_tick: 0,
    };
    if size == 0 {
        return Ok(rec);
    }
    let mut f = OpenOptions::new().read(true).write(true).open(path)?;
    let mut all = Vec::with_capacity(size as usize);
    f.read_to_end(&mut all)?;
    if all.len() < 8 || &all[..4] != KAFS_MAGIC {
        return err("KAFS journal: zły nagłówek");
    }
    let mut pos = 8usize;
    let cut = |reason: &'static str, rec: &mut Recovery, at: usize| {
        rec.truncated = true;
        rec.reason = reason;
        rec.last_good = at as u64;
    };
    rec.last_good = 8;
    loop {
        if pos == all.len() {
            break;
        }
        if all.len() - pos < 5 {
            cut("short_header", &mut rec, pos);
            break;
        }
        let kind = all[pos];
        let fsize = u32::from_be_bytes(all[pos + 1..pos + 5].try_into().unwrap()) as usize;
        let start = pos + 5;
        if all.len() - start < fsize {
            cut("short_payload", &mut rec, pos);
            break;
        }
        if fsize < 4 {
            cut("bad_size", &mut rec, pos);
            break;
        }
        let body = &all[start..start + fsize - 4];
        let crc = u32::from_be_bytes(all[start + fsize - 4..start + fsize].try_into().unwrap());
        if crc != crc32(body) {
            cut("crc", &mut rec, pos);
            break;
        }
        pos = start + fsize;
        rec.last_good = pos as u64;
        match kind {
            FT_ATOM => {
                rec.frames += 1;
                if let Some(h) = decode_atom(body).and_then(|a| peek_thermal_header(&a.data)) {
                    rec.last_tick = h.tick;
                }
            }
            FT_CHECKPOINT => rec.last_checkpoint = decode_checkpoint(body),
            FT_END => break,
            _ => {}
        }
    }
    if rec.truncated {
        f.set_len(rec.last_good)?;
        f.sync_all()?;
    }
    Ok(rec)
}

/// Wynik `compact_journal`.
#[derive(Debug, Clone, PartialEq)]
pub struct CompactReport {
    pub atoms: usize,
    pub bytes: usize,
    pub empty: bool,
    pub recovered_frames: u64,
}

/// `compact_journal`: dziennik KAFS → KAFD (domyślnie v2.1 footer), zapis
/// tmp + fsync + rename, opcjonalnie wyzerowanie dziennika. Bez koperty KAFX.
pub fn compact_journal(
    journal: &Path,
    kafd: &Path,
    layout: Layout,
    reset_journal: bool,
    meta: Option<Map<String, Value>>,
) -> Result<CompactReport> {
    let size = fs::metadata(journal).map(|m| m.len()).unwrap_or(0);
    if size < 8 {
        return Ok(CompactReport { atoms: 0, bytes: 0, empty: true, recovered_frames: 0 });
    }
    let mut j = Journal::open(journal, false, &Map::new())?;
    let recovered_frames = j.n_frames;
    let atoms = j.atoms(0.0)?;
    j.close(false)?;

    let meta = meta.unwrap_or_else(|| {
        let mut m = Map::new();
        m.insert("source".into(), Value::from("kafs-journal"));
        m.insert("frames".into(), Value::from(atoms.len()));
        m
    });
    let mut w = Writer::new(layout).with_meta(meta);
    for a in &atoms {
        w.add(a.clone());
    }
    let blob = w.build();
    atomic_replace(kafd, &blob)?;

    if reset_journal {
        let mut f = File::create(journal)?;
        f.write_all(&stream_header(F_PHI_NATIVE | F_STREAMING))?;
        f.sync_all()?;
    }
    Ok(CompactReport { atoms: atoms.len(), bytes: blob.len(), empty: false, recovered_frames })
}

/// Zapis tmp + fsync + rename w tym samym katalogu.
pub fn atomic_replace(path: &Path, data: &[u8]) -> Result<()> {
    let dir = path.parent().filter(|d| !d.as_os_str().is_empty()).unwrap_or(Path::new("."));
    fs::create_dir_all(dir)?;
    let name = path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
    let tmp = dir.join(format!(".kafd_{name}.{}.part", std::process::id()));
    {
        let mut f = File::create(&tmp)?;
        f.write_all(data)?;
        f.sync_all()?;
    }
    fs::rename(&tmp, path).map_err(|e| {
        let _ = fs::remove_file(&tmp);
        Error::from(e)
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{Reader, A_RAW, A_THERMAL, MIME_THERMAL};

    fn tmp(name: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("kafd_test_{}_{name}", std::process::id()));
        let _ = fs::remove_dir_all(&d);
        fs::create_dir_all(&d).unwrap();
        d
    }

    fn thermal(tick: u64) -> Vec<u8> {
        let mut d = vec![2u8, 0];
        d.extend(0u64.to_le_bytes());
        d.extend(tick.to_le_bytes());
        d.extend(0u32.to_le_bytes());
        d.extend(10f32.to_le_bytes());
        d.extend(90f32.to_le_bytes());
        d
    }

    #[test]
    fn flow_hot_first_and_threshold() {
        let mut meta = Map::new();
        meta.insert("k".into(), Value::from("v"));
        let mut w = FlowWriter::new(meta);
        w.add(Atom::new("cold", b"c".to_vec(), "text/plain", 20.0, 100.0, A_RAW));
        w.add(Atom::new("hot", b"h".to_vec(), "text/plain", 90.0, 100.0, A_RAW));
        w.add(Atom::new("warm", b"w".to_vec(), "text/plain", 50.0, 100.0, A_RAW));
        let blob = w.build();
        let mut r = FlowReader::new(&blob[..], true);
        r.read_header().unwrap();
        let ids: Vec<_> = r.atoms(0.0).unwrap().into_iter().map(|a| a.id).collect();
        assert_eq!(ids, ["hot", "warm", "cold"]);
        assert_eq!(r.meta()["k"], "v");
        let mut r = FlowReader::new(&blob[..], true);
        r.read_header().unwrap();
        assert_eq!(r.atoms(40.0).unwrap().len(), 2);
        // uszkodzona ramka → błąd CRC
        let mut bad = blob.clone();
        let i = bad.windows(1).position(|x| x == b"h").unwrap();
        bad[i] = b'x';
        let mut r = FlowReader::new(&bad[..], true);
        r.read_header().unwrap();
        assert!(r.atoms(0.0).unwrap_err().0.contains("CRC"));
    }

    #[test]
    fn journal_recover_and_compact() {
        let d = tmp("journal");
        let jp = d.join("world.kafs");
        let mut meta = Map::new();
        meta.insert("world".into(), Value::from("w"));
        let mut j = Journal::open(&jp, true, &meta).unwrap();
        for t in 1..=3 {
            j.append_atom(&Atom::new(format!("tick.{t}"), thermal(t), MIME_THERMAL, 50.0, 100.0, A_THERMAL)).unwrap();
        }
        j.checkpoint(3, "seal", 10.0, 90.0, 0).unwrap();
        j.close(false).unwrap();
        // urwana ramka na końcu
        let mut f = OpenOptions::new().append(true).open(&jp).unwrap();
        f.write_all(&[FT_ATOM, 0, 0, 0, 99, 1, 2, 3]).unwrap();
        drop(f);
        let j = Journal::open(&jp, false, &Map::new()).unwrap();
        assert!(j.recovered.truncated);
        assert_eq!(j.recovered.reason, "short_payload");
        assert_eq!((j.n_frames, j.last_tick), (3, 3));
        assert_eq!(j.last_checkpoint.as_ref().unwrap().causality, "seal");
        drop(j);

        let kp = d.join("world.kafd");
        let rep = compact_journal(&jp, &kp, Layout::Footer, true, None).unwrap();
        assert_eq!(rep.atoms, 3);
        let r = Reader::from_path(&kp).unwrap();
        assert_eq!(r.tick_index().len(), 3);
        assert_eq!(r.meta()["source"], "kafs-journal");
        assert_eq!(fs::metadata(&jp).unwrap().len(), 8);
        let _ = fs::remove_dir_all(&d);
    }

    #[test]
    fn kx1_atoms_are_refused() {
        let d = tmp("kx1");
        let jp = d.join("e.kafs");
        let mut j = Journal::open(&jp, false, &Map::new()).unwrap();
        let mut data = KX1_MAGIC.to_vec();
        data.extend([0u8; 40]);
        j.append_atom(&Atom::raw("x", data, "application/octet-stream")).unwrap();
        assert!(j.atoms(0.0).unwrap_err().0.contains("KX1"));
        let _ = fs::remove_dir_all(&d);
    }
}
