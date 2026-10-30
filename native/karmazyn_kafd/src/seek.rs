//! KAFD seekable: `KAFDWriter` / `KAFDReader` (v2.0 table-first, v2.1 footer + KTIX, v1 odczyt).

use crate::json;
use crate::{
    align8, cas_hash, crc32, err, id_hash, peek_thermal_header, Atom, Error, Result, A_RAW,
    ATOM_ENTRY, F_ENCRYPTED, F_FOOTER_TOC, F_PHI_NATIVE, HEADER_SIZE, KAFX_MAGIC, MAGIC,
    MIME_DEFAULT, S_WARM, TICK_INDEX_ENTRY, TICK_INDEX_MAGIC, VERSION, VERSION_V21,
};
use serde_json::{Map, Value};
use std::io::Write;
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Layout {
    /// v2.0: tabela przed payloadem (pełny rewrite).
    TableFirst,
    /// v2.1: payload, potem tabela, ID, META i KTIX w stopce.
    Footer,
}

/// `KAFDWriter`. Kolejność atomów w tabeli: rosnąco po `id_hash`
/// (stabilnie, jak `list.sort`), pula ID w kolejności dodawania.
pub struct Writer {
    atoms: Vec<Atom>,
    meta: Map<String, Value>,
    flags: u16,
    layout: Layout,
    created: Option<(u64, String)>,
}

impl Writer {
    pub fn new(layout: Layout) -> Self {
        Writer {
            atoms: Vec::new(),
            meta: Map::new(),
            flags: F_PHI_NATIVE,
            layout,
            created: None,
        }
    }

    pub fn with_meta(mut self, meta: Map<String, Value>) -> Self {
        self.meta = meta;
        self
    }

    pub fn with_flags(mut self, flags: u16) -> Self {
        self.flags = flags;
        self
    }

    /// Czas w nagłówku (unix) i `_created` w META. Domyślnie teraz (UTC;
    /// Python pisze czas lokalny — na płycie to i tak UTC).
    pub fn with_created(mut self, unix: u64, created: impl Into<String>) -> Self {
        self.created = Some((unix, created.into()));
        self
    }

    pub fn add(&mut self, atom: Atom) -> &mut Self {
        self.atoms.push(atom);
        self
    }

    pub fn len(&self) -> usize {
        self.atoms.len()
    }

    pub fn is_empty(&self) -> bool {
        self.atoms.is_empty()
    }

    pub fn build(&self) -> Vec<u8> {
        let mut out = Vec::new();
        self.write_to(&mut out).expect("zapis do Vec");
        out
    }

    /// `write_stream`: strumieniowo do dowolnego ujścia. Zwraca liczbę bajtów.
    pub fn write_to<W: Write>(&self, sink: &mut W) -> Result<u64> {
        let footer = self.layout == Layout::Footer;
        let (unix, created) = self.created.clone().unwrap_or_else(now);

        // słownik MIME w kolejności pierwszego wystąpienia
        let mut mimes: Vec<&str> = Vec::new();
        let mut id_pool = Vec::new();
        let mut rows: Vec<(Row, &Atom)> = Vec::with_capacity(self.atoms.len());
        for a in &self.atoms {
            let id = a.id.as_bytes();
            let mime_idx = match mimes.iter().position(|m| *m == a.mime) {
                Some(i) => i,
                None => {
                    mimes.push(&a.mime);
                    mimes.len() - 1
                }
            } as u16;
            rows.push((
                Row {
                    id_hash: id_hash(&a.id),
                    id_off: id_pool.len() as u32,
                    id_len: id.len() as u16,
                    mime_idx,
                    data_off: 0,
                    data_size: a.data.len() as u64,
                },
                a,
            ));
            id_pool.extend_from_slice(id);
        }
        rows.sort_by_key(|(r, _)| r.id_hash);
        let mut cur = 0u64;
        for (r, a) in rows.iter_mut() {
            r.data_off = cur;
            cur += align8(a.data.len()) as u64;
        }
        let payload_total = cur;

        let mut meta = self.meta.clone();
        meta.insert("_kafd_v".into(), Value::from(if footer { 21 } else { 2 }));
        let mut md = Map::new();
        for (i, m) in mimes.iter().enumerate() {
            md.insert(i.to_string(), Value::from(*m));
        }
        meta.insert("_mime_dict".into(), Value::Object(md));
        meta.insert("_created".into(), Value::from(created));
        if footer {
            meta.insert("_layout".into(), Value::from("footer"));
        }
        let meta_bytes = json::dumps(&meta);

        let n = rows.len();
        let (table_off, meta_off, payload_off) = if footer {
            let payload_off = HEADER_SIZE as u64;
            let table_off = payload_off + payload_total;
            let id_pool_off = table_off + (n * ATOM_ENTRY) as u64;
            (table_off, id_pool_off + align8(id_pool.len()) as u64, payload_off)
        } else {
            let table_off = HEADER_SIZE as u64;
            let id_pool_off = table_off + (n * ATOM_ENTRY) as u64;
            let meta_off = id_pool_off + align8(id_pool.len()) as u64;
            (table_off, meta_off, meta_off + align8(meta_bytes.len()) as u64)
        };
        let avg_t = if n == 0 {
            0.0
        } else {
            rows.iter().map(|(_, a)| a.t).sum::<f64>() / n as f64
        };
        let version = if footer { VERSION_V21 } else { VERSION };
        let flags = self.flags | if footer { F_FOOTER_TOC } else { 0 };

        let mut hdr = Vec::with_capacity(HEADER_SIZE);
        hdr.extend_from_slice(MAGIC);
        hdr.extend(version.to_be_bytes());
        hdr.extend(flags.to_be_bytes());
        hdr.extend((n as u32).to_be_bytes());
        hdr.extend(unix.to_be_bytes());
        hdr.extend(table_off.to_be_bytes());
        hdr.extend(meta_off.to_be_bytes());
        hdr.extend((meta_bytes.len() as u32).to_be_bytes());
        hdr.extend(payload_off.to_be_bytes());
        hdr.extend(payload_total.to_be_bytes());
        hdr.extend((avg_t as f32).to_be_bytes());
        debug_assert_eq!(hdr.len(), HEADER_SIZE - 4);
        let c = crc32(&hdr);
        hdr.extend(c.to_be_bytes());

        let mut w = Counter { sink, n: 0 };
        w.put(&hdr)?;
        let table = |w: &mut Counter<W>| -> Result<()> {
            for (r, a) in &rows {
                let mut row = Vec::with_capacity(ATOM_ENTRY);
                row.extend(r.id_hash.to_be_bytes());
                row.extend(r.id_off.to_be_bytes());
                row.extend(r.id_len.to_be_bytes());
                row.extend(r.mime_idx.to_be_bytes());
                row.extend(r.data_off.to_be_bytes());
                row.extend(r.data_size.to_be_bytes());
                row.extend((a.t as f32).to_be_bytes());
                row.extend((a.t_max as f32).to_be_bytes());
                row.push(a.state);
                row.push(a.atype);
                row.extend_from_slice(&a.cas);
                row.extend([0, 0]);
                w.put(&row)?;
            }
            Ok(())
        };
        let padded = |w: &mut Counter<W>, b: &[u8]| -> Result<()> {
            w.put(b)?;
            w.put(&[0u8; 8][..align8(b.len()) - b.len()])
        };
        let payload = |w: &mut Counter<W>| -> Result<()> {
            for (_, a) in &rows {
                padded(w, &a.data)?;
            }
            Ok(())
        };
        if footer {
            payload(&mut w)?;
            table(&mut w)?;
            padded(&mut w, &id_pool)?;
            padded(&mut w, &meta_bytes)?;
            let mut ktix = Vec::new();
            let recs: Vec<_> = rows
                .iter()
                .filter_map(|(r, a)| peek_thermal_header(&a.data).map(|h| (h, r)))
                .collect();
            ktix.extend_from_slice(TICK_INDEX_MAGIC);
            ktix.extend(1u16.to_be_bytes());
            ktix.extend((recs.len() as u32).to_be_bytes());
            for (h, r) in recs {
                ktix.extend(h.tick.to_be_bytes());
                ktix.extend(r.data_off.to_be_bytes());
                ktix.extend(r.data_size.to_be_bytes());
                ktix.extend(h.t_min.to_be_bytes());
                ktix.extend(h.t_max.to_be_bytes());
                ktix.push(h.kind);
                ktix.extend([0u8; 7]);
            }
            w.put(&ktix)?;
        } else {
            table(&mut w)?;
            padded(&mut w, &id_pool)?;
            padded(&mut w, &meta_bytes)?;
            payload(&mut w)?;
        }
        Ok(w.n)
    }
}

fn now() -> (u64, String) {
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    (secs, format_utc_minute(secs))
}

/// `%Y-%m-%d %H:%M` w UTC (dni od epoki → data cywilna, Howard Hinnant).
fn format_utc_minute(secs: u64) -> String {
    let days = (secs / 86_400) as i64;
    let rem = secs % 86_400;
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = yoe + era * 400 + i64::from(m <= 2);
    format!("{y:04}-{m:02}-{d:02} {:02}:{:02}", rem / 3600, (rem % 3600) / 60)
}

struct Row {
    id_hash: u64,
    id_off: u32,
    id_len: u16,
    mime_idx: u16,
    data_off: u64,
    data_size: u64,
}

struct Counter<'a, W: Write> {
    sink: &'a mut W,
    n: u64,
}

impl<W: Write> Counter<'_, W> {
    fn put(&mut self, b: &[u8]) -> Result<()> {
        self.sink.write_all(b)?;
        self.n += b.len() as u64;
        Ok(())
    }
}

/// Wpis tabeli atomów po odczycie.
#[derive(Debug, Clone, PartialEq)]
pub struct Entry {
    pub id: String,
    pub id_hash: u64,
    pub data_off: u64,
    pub data_size: u64,
    pub t: f32,
    pub t_max: f32,
    pub state: u8,
    pub atype: u8,
    pub mime_idx: u16,
    pub cas: [u8; 12],
    v1: bool,
}

/// Rekord indeksu KTIX (v2.1).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct TickRecord {
    pub tick: u64,
    pub data_off: u64,
    pub data_size: u64,
    pub t_min: f32,
    pub t_max: f32,
    pub kind: u8,
}

/// `KAFDReader`: v2.0 / v2.1 / v1. CRC nagłówka sprawdzany ściśle,
/// CAS przy `get_atom` (gdy w tabeli nie same zera).
pub struct Reader {
    data: Vec<u8>,
    flags: u16,
    version: u16,
    meta: Map<String, Value>,
    mimes: Vec<(u16, String)>,
    table: Vec<Entry>,
    payload_off: u64,
    ticks: Vec<TickRecord>,
    verify_cas: bool,
}

impl Reader {
    pub fn parse(data: Vec<u8>) -> Result<Self> {
        Reader::parse_with(data, true)
    }

    pub fn from_path(path: impl AsRef<std::path::Path>) -> Result<Self> {
        Reader::parse(std::fs::read(path)?)
    }

    pub fn parse_with(data: Vec<u8>, verify_cas: bool) -> Result<Self> {
        if data.starts_with(KAFX_MAGIC) {
            return err("KAFD: koperta KAFX (AES-GCM) — odszyfrowanie jeszcze nie jest natywne");
        }
        if data.len() < HEADER_SIZE || &data[..4] != MAGIC {
            return err("KAFD: brak magii KAFD");
        }
        let mut r = Reader {
            data,
            flags: 0,
            version: 0,
            meta: Map::new(),
            mimes: Vec::new(),
            table: Vec::new(),
            payload_off: 0,
            ticks: Vec::new(),
            verify_cas,
        };
        r.version = r.be16(4);
        if r.version < 0x0200 {
            r.parse_v1()?;
        } else {
            r.parse_v2()?;
        }
        Ok(r)
    }

    fn be16(&self, o: usize) -> u16 {
        u16::from_be_bytes(self.data[o..o + 2].try_into().unwrap())
    }
    fn be32(&self, o: usize) -> u32 {
        u32::from_be_bytes(self.data[o..o + 4].try_into().unwrap())
    }
    fn be64(&self, o: usize) -> u64 {
        u64::from_be_bytes(self.data[o..o + 8].try_into().unwrap())
    }

    fn slice(&self, off: u64, len: u64) -> Result<&[u8]> {
        let end = off.checked_add(len).filter(|e| *e <= self.data.len() as u64);
        match end {
            Some(e) => Ok(&self.data[off as usize..e as usize]),
            None => err(format!(
                "KAFD v2: offset {off}+{len} poza danymi ({}B)",
                self.data.len()
            )),
        }
    }

    fn parse_v2(&mut self) -> Result<()> {
        let stored = self.be32(60);
        let computed = crc32(&self.data[..60]);
        if stored != 0 && stored != computed {
            return err(format!(
                "KAFD: CRC naglowka niezgodny (stored={stored:#010x} computed={computed:#010x})"
            ));
        }
        self.flags = self.be16(6);
        let n = self.be32(8) as u64;
        let table_off = self.be64(20);
        let meta_off = self.be64(28);
        let meta_size = u64::from(self.be32(36));
        self.payload_off = self.be64(40);

        if let Ok(raw) = self.slice(meta_off, meta_size) {
            if let Some(m) = json::loads(raw) {
                if let Some(Value::Object(md)) = m.get("_mime_dict") {
                    for (k, v) in md {
                        if let (Ok(i), Some(s)) = (k.parse::<u16>(), v.as_str()) {
                            self.mimes.push((i, s.to_string()));
                        }
                    }
                }
                self.meta = m;
            }
        }

        let id_pool_off = table_off + n * ATOM_ENTRY as u64;
        let id_pool = self
            .data
            .get(id_pool_off as usize..(meta_off as usize).min(self.data.len()))
            .unwrap_or(&[])
            .to_vec();
        for i in 0..n {
            let off = (table_off + i * ATOM_ENTRY as u64) as usize;
            let Some(e) = self.data.get(off..off + ATOM_ENTRY) else {
                break;
            };
            let id_off = u32::from_be_bytes(e[8..12].try_into().unwrap()) as usize;
            let id_len = u16::from_be_bytes(e[12..14].try_into().unwrap()) as usize;
            let id = id_pool
                .get(id_off..id_off + id_len)
                .and_then(|b| std::str::from_utf8(b).ok())
                .map(str::to_string)
                .unwrap_or_else(|| format!("atom_{i}"));
            self.table.push(Entry {
                id,
                id_hash: u64::from_be_bytes(e[0..8].try_into().unwrap()),
                mime_idx: u16::from_be_bytes(e[14..16].try_into().unwrap()),
                data_off: u64::from_be_bytes(e[16..24].try_into().unwrap()),
                data_size: u64::from_be_bytes(e[24..32].try_into().unwrap()),
                t: f32::from_be_bytes(e[32..36].try_into().unwrap()),
                t_max: f32::from_be_bytes(e[36..40].try_into().unwrap()),
                state: e[40],
                atype: e[41],
                cas: e[42..54].try_into().unwrap(),
                v1: false,
            });
        }
        if self.flags & F_FOOTER_TOC != 0 {
            self.parse_ticks(meta_off + align8(meta_size as usize) as u64);
        }
        Ok(())
    }

    fn parse_ticks(&mut self, off: u64) {
        let Ok(head) = self.slice(off, 10) else {
            return;
        };
        if &head[..4] != TICK_INDEX_MAGIC {
            return;
        }
        let n = u32::from_be_bytes(head[6..10].try_into().unwrap()) as u64;
        let Ok(raw) = self.slice(off + 10, n * TICK_INDEX_ENTRY as u64) else {
            return;
        };
        let recs = raw
            .chunks_exact(TICK_INDEX_ENTRY)
            .map(|r| TickRecord {
                tick: u64::from_be_bytes(r[0..8].try_into().unwrap()),
                data_off: u64::from_be_bytes(r[8..16].try_into().unwrap()),
                data_size: u64::from_be_bytes(r[16..24].try_into().unwrap()),
                t_min: f32::from_be_bytes(r[24..28].try_into().unwrap()),
                t_max: f32::from_be_bytes(r[28..32].try_into().unwrap()),
                kind: r[32],
            })
            .collect();
        self.ticks = recs;
    }

    /// v1: `KAFD` + rozmiar nagłówka JSON {meta, atoms: {id: {offset, size}}} + payload.
    fn parse_v1(&mut self) -> Result<()> {
        let size = u64::from(self.be32(4));
        let header = self
            .slice(8, size)
            .ok()
            .and_then(json::loads)
            .ok_or_else(|| Error("KAFD v1: zły nagłówek JSON".into()))?;
        let mut meta = match header.get("meta") {
            Some(Value::Object(m)) => m.clone(),
            _ => Map::new(),
        };
        meta.insert("_kafd_v".into(), Value::from(1));
        self.meta = meta;
        self.payload_off = 8 + size;
        if let Some(Value::Object(atoms)) = header.get("atoms") {
            for (id, info) in atoms {
                let num = |k: &str| info.get(k).and_then(Value::as_u64).unwrap_or(0);
                self.table.push(Entry {
                    id: id.clone(),
                    id_hash: id_hash(id),
                    data_off: num("offset"),
                    data_size: num("size"),
                    t: 50.0,
                    t_max: 100.0,
                    state: S_WARM,
                    atype: A_RAW,
                    mime_idx: 0,
                    cas: [0; 12],
                    v1: true,
                });
            }
        }
        Ok(())
    }

    pub fn version(&self) -> u16 {
        self.version
    }

    pub fn flags(&self) -> u16 {
        self.flags
    }

    pub fn is_encrypted_mark(&self) -> bool {
        self.flags & F_ENCRYPTED != 0
    }

    pub fn meta(&self) -> &Map<String, Value> {
        &self.meta
    }

    pub fn entries(&self) -> &[Entry] {
        &self.table
    }

    pub fn atom_ids(&self) -> Vec<&str> {
        self.table.iter().map(|e| e.id.as_str()).collect()
    }

    pub fn tick_index(&self) -> &[TickRecord] {
        &self.ticks
    }

    /// KTIX: klatki, których przedział T zachodzi na [t_min, t_max].
    pub fn ticks_in_t_range(&self, t_min: f32, t_max: f32) -> Vec<TickRecord> {
        self.ticks
            .iter()
            .filter(|r| r.t_max >= t_min && r.t_min <= t_max)
            .copied()
            .collect()
    }

    pub fn mime(&self, idx: u16) -> &str {
        self.mimes
            .iter()
            .find(|(i, _)| *i == idx)
            .map(|(_, m)| m.as_str())
            .unwrap_or(MIME_DEFAULT)
    }

    /// Wyszukiwanie binarne po `id_hash`, z pełnym skanem kolizji.
    pub fn get_entry(&self, id: &str) -> Option<&Entry> {
        let target = id_hash(id);
        if self.table.first().is_some_and(|e| e.v1) {
            return self.table.iter().find(|e| e.id == id);
        }
        let mut i = self.table.partition_point(|e| e.id_hash < target);
        while let Some(e) = self.table.get(i).filter(|e| e.id_hash == target) {
            if e.id == id {
                return Some(e);
            }
            i += 1;
        }
        None
    }

    pub fn data(&self, e: &Entry) -> Result<&[u8]> {
        self.slice(self.payload_off + e.data_off, e.data_size)
    }

    /// `get_atom`: dane + weryfikacja CAS.
    pub fn get_atom(&self, id: &str) -> Result<Option<Atom>> {
        let Some(e) = self.get_entry(id) else {
            return Ok(None);
        };
        let data = self.data(e)?.to_vec();
        if self.verify_cas && e.cas != [0; 12] {
            let got = cas_hash(&data);
            if got != e.cas {
                return err(format!(
                    "KAFD CAS mismatch id={id:?} stored={} computed={}",
                    hex(&e.cas),
                    hex(&got)
                ));
            }
        }
        Ok(Some(Atom {
            id: e.id.clone(),
            data,
            mime: self.mime(e.mime_idx).to_string(),
            t: f64::from(e.t),
            t_max: f64::from(e.t_max),
            state: e.state,
            atype: e.atype,
            cas: e.cas,
        }))
    }

    /// Wszystkie atomy w kolejności tabeli.
    pub fn atoms(&self) -> Result<Vec<Atom>> {
        self.table
            .iter()
            .map(|e| self.get_atom(&e.id).map(|a| a.expect("wpis z tabeli")))
            .collect()
    }
}

impl std::fmt::Debug for Reader {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Reader")
            .field("version", &self.version)
            .field("flags", &self.flags)
            .field("atoms", &self.table.len())
            .field("bytes", &self.data.len())
            .finish()
    }
}

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{A_PHI_ATOM, A_THERMAL, MIME_THERMAL};

    fn thermal(tick: u64, kind: u8, tmin: f32, tmax: f32) -> Vec<u8> {
        let mut d = vec![2u8, kind];
        d.extend(1_700_000_000u64.to_le_bytes());
        d.extend(tick.to_le_bytes());
        d.extend(0u32.to_le_bytes());
        d.extend(tmin.to_le_bytes());
        d.extend(tmax.to_le_bytes());
        d
    }

    fn sample(layout: Layout) -> Vec<u8> {
        let mut meta = Map::new();
        meta.insert("label".into(), Value::from("test"));
        let mut w = Writer::new(layout).with_meta(meta).with_created(1_700_000_000, "2023-11-14 22:13");
        w.add(Atom::new("doc.readme", b"Dokumentacja\n".to_vec(), "text/plain", 45.0, 100.0, A_RAW));
        w.add(Atom::new("img.logo", vec![0x89, b'P', b'N', b'G', 0, 0, 0], "image/png", 72.0, 100.0, A_RAW));
        w.add(Atom::new("shell.init", br#"{"id": "shell.init"}"#.to_vec(), "application/x-phi-atom", 85.0, 100.0, A_PHI_ATOM));
        w.add(Atom::new("tick.417", thermal(417, 0, 40.0, 70.0), MIME_THERMAL, 55.0, 100.0, A_THERMAL));
        w.build()
    }

    #[test]
    fn roundtrip_both_layouts() {
        for layout in [Layout::TableFirst, Layout::Footer] {
            let blob = sample(layout);
            let r = Reader::parse(blob).unwrap();
            assert_eq!(r.version(), if layout == Layout::Footer { VERSION_V21 } else { VERSION });
            assert_eq!(r.atom_ids().len(), 4);
            let a = r.get_atom("img.logo").unwrap().unwrap();
            assert_eq!((a.mime.as_str(), a.t, a.state), ("image/png", 72.0, crate::S_HOT));
            assert_eq!(r.get_atom("doc.readme").unwrap().unwrap().data, b"Dokumentacja\n");
            assert!(r.get_atom("brak").unwrap().is_none());
            assert_eq!(r.meta()["label"], "test");
            // tabela posortowana po id_hash
            let hs: Vec<u64> = r.entries().iter().map(|e| e.id_hash).collect();
            assert!(hs.windows(2).all(|w| w[0] <= w[1]));
        }
    }

    #[test]
    fn footer_has_tick_index() {
        let r = Reader::parse(sample(Layout::Footer)).unwrap();
        assert_eq!(r.tick_index().len(), 1);
        assert_eq!(r.tick_index()[0].tick, 417);
        assert_eq!(r.ticks_in_t_range(60.0, 90.0).len(), 1);
        assert!(r.ticks_in_t_range(71.0, 90.0).is_empty());
        assert!(Reader::parse(sample(Layout::TableFirst)).unwrap().tick_index().is_empty());
    }

    #[test]
    fn corruption_is_an_error() {
        let mut blob = sample(Layout::TableFirst);
        blob[10] ^= 1;
        assert!(Reader::parse(blob).unwrap_err().0.contains("CRC naglowka"));
        let mut blob = sample(Layout::TableFirst);
        let n = blob.len();
        blob[n - 3] ^= 0xff; // ostatni bajt payloadu (thermal albo inny atom)
        let r = Reader::parse(blob).unwrap();
        let bad: Vec<_> = r.entries().iter().filter(|e| r.get_atom(&e.id).is_err()).collect();
        assert_eq!(bad.len(), 1);
        assert!(Reader::parse(b"KAFX....".repeat(10)).unwrap_err().0.contains("KAFX"));
    }

    #[test]
    fn reads_v1() {
        let header = br#"{"meta": {"label": "old"}, "atoms": {"a": {"offset": 0, "size": 3}, "b": {"offset": 3, "size": 2}}}"#;
        let mut blob = b"KAFD".to_vec();
        blob.extend((header.len() as u32).to_be_bytes());
        blob.extend_from_slice(header);
        blob.extend_from_slice(b"abcde");
        blob.resize(blob.len().max(HEADER_SIZE), 0);
        let r = Reader::parse(blob).unwrap();
        assert_eq!(r.get_atom("b").unwrap().unwrap().data, b"de");
        assert_eq!(r.meta()["_kafd_v"], 1);
    }

    #[test]
    fn utc_minute() {
        assert_eq!(format_utc_minute(1_700_000_000), "2023-11-14 22:13");
        assert_eq!(format_utc_minute(0), "1970-01-01 00:00");
    }
}
