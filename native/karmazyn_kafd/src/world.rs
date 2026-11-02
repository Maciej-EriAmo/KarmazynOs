//! Świat DBase na dysku (`karmazyn_store.py`, format `karmazyn_store_v1.4_kafx`):
//! KAFD v2.0 z `vfs_pack`, każdy atom pod publicznym id, treść
//! `[u32 len][JSON {"S","E","T","meta"}][dane]`. Bąble to atomy
//! `S="__bubble__"`, `E=etykieta`, `meta.v = {"label", "bindings": {nazwa: id}}`
//! (jak `karmazyn_media.sync_bubble_record`). Całość w kopercie KAFX.
//!
//! Natywny Store (cecha `substrate`) dopisuje w `meta.v` pola, których Python
//! nie zna i pomija: `bid`, `parent` (id atomu-bąbla rodzica), `root`.
//! Publiczne id atomów: `a{n}` (jak `NativeStore._alloc_sid`), bąbli: `b{n}`.

use crate::json;
use crate::seek::{Layout, Reader, Writer};
use crate::{err, Atom, Error, Result, A_MANIFEST, A_RAW, F_ENCRYPTED, F_PHI_NATIVE};
use serde_json::{Map, Value};
use std::path::Path;

pub const STORE_META: &str = "karmazyn_store_v1.4_kafx";
pub const BUBBLE_S: &str = "__bubble__";

/// Dokumenty świata: (publiczne id, bajty `encode_doc` albo surowe).
pub type Docs = Vec<(String, Vec<u8>)>;

/// `_encode_atom`: `>I` długość nagłówka JSON, nagłówek, dane.
pub fn encode_doc(s: &str, e: &str, t: f64, meta: Map<String, Value>, data: &[u8]) -> Vec<u8> {
    let mut head = Map::new();
    head.insert("S".into(), Value::from(s));
    head.insert("E".into(), Value::from(e));
    head.insert("T".into(), Value::from(t));
    head.insert("meta".into(), Value::Object(meta));
    let h = json::dumps(&head);
    let mut out = (h.len() as u32).to_be_bytes().to_vec();
    out.extend(h);
    out.extend_from_slice(data);
    out
}

/// Atom dokumentu po `_decode_atom`.
#[derive(Debug, Clone, PartialEq)]
pub struct Doc {
    pub id: String,
    pub s: String,
    pub e: String,
    pub t: f64,
    pub meta: Map<String, Value>,
    pub data: Vec<u8>,
}

/// `_decode_atom`. `None` dla bloba, który nie jest dokumentem.
pub fn decode_doc(id: &str, blob: &[u8]) -> Option<Doc> {
    let n = u32::from_be_bytes(blob.get(..4)?.try_into().ok()?) as usize;
    let head = json::loads(blob.get(4..4 + n)?)?;
    let text = |k: &str| match head.get(k) {
        Some(Value::String(s)) => s.clone(),
        Some(Value::Null) | None => String::new(),
        Some(v) => v.to_string(),
    };
    Some(Doc {
        id: id.to_string(),
        s: text("S"),
        e: text("E"),
        t: head.get("T").and_then(Value::as_f64).unwrap_or(50.0),
        meta: match head.get("meta") {
            Some(Value::Object(m)) => m.clone(),
            _ => Map::new(),
        },
        data: blob[4 + n..].to_vec(),
    })
}

/// `_is_manifest`: JSON-obiekt z kluczem `_manifest_v`.
pub fn is_manifest(data: &[u8]) -> bool {
    std::str::from_utf8(data)
        .ok()
        .and_then(|s| json::loads(s.trim().as_bytes()))
        .is_some_and(|m| m.contains_key("_manifest_v"))
}

/// `_detect_mime`: sygnatury, manifest, rozszerzenie id (jak `os.path.splitext`).
pub fn detect_mime(data: &[u8], id: &str) -> &'static str {
    if data.len() >= 8 {
        if data.starts_with(b"\xff\xd8\xff") {
            return "image/jpeg";
        }
        if data.starts_with(b"\x89PNG\r\n\x1a\n") {
            return "image/png";
        }
        if data.starts_with(b"GIF87a") || data.starts_with(b"GIF89a") {
            return "image/gif";
        }
        if data.starts_with(b"RIFF") && &data[8..data.len().min(12)] == b"WAVE" {
            return "audio/wav";
        }
        if data.starts_with(b"ID3") || data.starts_with(b"\xff\xfb") {
            return "audio/mpeg";
        }
        if data.starts_with(b"fLaC") {
            return "audio/flac";
        }
        if data.starts_with(b"OggS") {
            return "audio/ogg";
        }
        if data.starts_with(b"\x00\x00\x00\x18") || data.starts_with(b"\x00\x00\x00\x1c") {
            return "video/mp4";
        }
        if data.starts_with(b"KAFD") {
            return "application/x-kafd";
        }
    }
    if is_manifest(data) {
        return "application/x-phi-manifest";
    }
    match extension(id).to_lowercase().as_str() {
        ".jpg" => "image/jpeg",
        ".png" => "image/png",
        ".mp3" => "audio/mpeg",
        ".mp4" => "video/mp4",
        ".wav" => "audio/wav",
        ".txt" => "text/plain",
        ".json" => "application/json",
        ".py" => "text/x-python",
        _ => crate::MIME_DEFAULT,
    }
}

/// `os.path.splitext(id)[1]`: od ostatniej kropki w ostatnim członie,
/// kropki wiodące członu się nie liczą.
fn extension(id: &str) -> &str {
    let base = id.rsplit(['/', '\\']).next().unwrap_or(id);
    let lead = base.len() - base.trim_start_matches('.').len();
    match base[lead..].rfind('.') {
        Some(i) => &base[lead + i..],
        None => "",
    }
}

/// `vfs_pack`: KAFD v2.0 table-first; atom manifestu dostaje A_MANIFEST i T
/// z JSON, reszta A_RAW i T=50. Kolejność jak w słowniku Pythona.
pub fn vfs_pack(
    atoms: &[(String, Vec<u8>)],
    meta: Map<String, Value>,
    flags: u16,
    created: Option<(u64, &str)>,
) -> Vec<u8> {
    let mut w = Writer::new(Layout::TableFirst).with_meta(meta).with_flags(flags);
    if let Some((unix, c)) = created {
        w = w.with_created(unix, c);
    }
    for (id, data) in atoms {
        let manifest = is_manifest(data);
        let t = if manifest {
            std::str::from_utf8(data)
                .ok()
                .and_then(|s| json::loads(s.trim().as_bytes()))
                .and_then(|m| m.get("T").and_then(Value::as_f64))
                .unwrap_or(50.0)
        } else {
            50.0
        };
        let atype = if manifest { A_MANIFEST } else { A_RAW };
        w.add(Atom::new(id.clone(), data.clone(), detect_mime(data, id), t, 100.0, atype));
    }
    w.build()
}

/// `vfs_unpack`: (id, dane) w kolejności tabeli + META.
pub fn vfs_unpack(r: &Reader) -> Result<(Docs, Map<String, Value>)> {
    let mut out = Vec::new();
    for e in r.entries() {
        let a = r.get_atom(&e.id)?.ok_or_else(|| Error(format!("brak {}", e.id)))?;
        out.push((a.id, a.data));
    }
    Ok((out, r.meta().clone()))
}

/// Zawartość świata po odczycie: dokumenty i bąble w kolejności pliku.
#[derive(Debug, Clone, Default)]
pub struct World {
    pub meta: Map<String, Value>,
    pub docs: Vec<Doc>,
}

impl World {
    /// Odczyt pliku świata: KAFX / KAFD / stary XOR.
    pub fn read(path: &std::path::Path, world: Option<&str>, master: Option<&[u8]>) -> Result<World> {
        let r = Reader::from_path_with(path, world, master)?;
        let (atoms, meta) = vfs_unpack(&r)?;
        let docs = atoms
            .iter()
            .filter_map(|(id, b)| decode_doc(id, b))
            .collect();
        Ok(World { meta, docs })
    }

    pub fn bubbles(&self) -> impl Iterator<Item = &Doc> {
        self.docs.iter().filter(|d| d.s == BUBBLE_S)
    }

    pub fn atoms(&self) -> impl Iterator<Item = &Doc> {
        self.docs.iter().filter(|d| d.s != BUBBLE_S)
    }
}

/// Zapis świata: META `{"format", "saved", "count"}` (+ `extra`), flagi
/// F_PHI_NATIVE (+ F_ENCRYPTED), koperta KAFX gdy `encrypt` (świat = `world`
/// albo nazwa pliku), zapis tmp + fsync + rename.
pub fn write_world(
    path: &std::path::Path,
    docs: &[(String, Vec<u8>)],
    extra: Map<String, Value>,
    crypt: &crate::Crypt,
    saved: f64,
) -> Result<usize> {
    let mut meta = Map::new();
    meta.insert("format".into(), Value::from(STORE_META));
    meta.insert("saved".into(), Value::from(saved));
    meta.insert("count".into(), Value::from(docs.len()));
    for (k, v) in extra {
        meta.insert(k, v);
    }
    let encrypt = crypt.encrypt.unwrap_or_else(|| !crate::cipher::plain_requested());
    let flags = F_PHI_NATIVE | if encrypt { F_ENCRYPTED } else { 0 };
    let blob = vfs_pack(docs, meta, flags, None);
    let blob = crate::cipher::encrypt_for_path(
        blob,
        path,
        crypt.world.as_deref(),
        crypt.master.as_deref(),
        Some(encrypt),
    )?;
    crate::atomic_replace(path, &blob)?;
    // nowy katalog worlds/ też musi być na dysku
    if let Some(parent) = path.parent().and_then(Path::parent) {
        crate::sync_dir(parent);
    }
    Ok(docs.len())
}

#[cfg(feature = "substrate")]
pub use store::{
    journal_path, load_store, save_store, snapshot_from_world, world_from_snapshot, LoadReport, SaveReport,
    WorldLog, COMPACT_MIN, NATIVE_FRAME,
};

#[cfg(feature = "substrate")]
mod store {
    use super::*;
    use karmazyn_substrate::{AtomSnap, BindSnap, BubbleSnap, Store, StoreSnapshot};
    use std::collections::HashMap;

    fn atom_sid(aid: u32) -> String {
        format!("a{aid}")
    }

    fn bubble_sid(bid: u32) -> String {
        format!("b{bid}")
    }

    fn num_after(prefix: char, sid: &str) -> Option<u32> {
        sid.strip_prefix(prefix).and_then(|n| n.parse().ok())
    }

    /// Store → dokumenty świata (atomy `a{n}`, bąble `b{n}` jako `__bubble__`).
    pub fn world_from_snapshot(snap: &StoreSnapshot) -> (Docs, Map<String, Value>) {
        let mut docs = Vec::with_capacity(snap.atoms.len() + snap.bubbles.len());
        for a in &snap.atoms {
            let mut meta = Map::new();
            if a.value_token != 0 {
                meta.insert("token".into(), Value::from(a.value_token));
            }
            meta.insert("tick".into(), Value::from(snap.ticks));
            let data = a.payload.clone().unwrap_or_default();
            docs.push((atom_sid(a.id), encode_doc(&a.s, &a.e, a.t, meta, &data)));
        }
        for b in &snap.bubbles {
            let mut binds = Map::new();
            for bind in snap.binds.iter().filter(|x| x.bid == b.id) {
                binds.insert(bind.name.clone(), Value::from(atom_sid(bind.aid)));
            }
            let mut v = Map::new();
            v.insert("label".into(), Value::from(b.label.clone()));
            v.insert("bindings".into(), Value::Object(binds));
            v.insert("bid".into(), Value::from(b.id));
            v.insert(
                "parent".into(),
                b.parent.map(|p| Value::from(bubble_sid(p))).unwrap_or(Value::Null),
            );
            v.insert("root".into(), Value::from(snap.roots.contains(&b.id)));
            let mut meta = Map::new();
            meta.insert("v".into(), Value::Object(v));
            docs.push((bubble_sid(b.id), encode_doc(BUBBLE_S, &b.label, 50.0, meta, b"")));
        }
        let mut native = Map::new();
        native.insert("thermal".into(), Value::from(snap.thermal));
        native.insert("decay".into(), Value::from(snap.decay));
        native.insert("reaped".into(), Value::from(snap.reaped));
        native.insert("next_atom".into(), Value::from(snap.next_atom));
        native.insert("next_bubble".into(), Value::from(snap.next_bubble));
        native.insert("ticks".into(), Value::from(snap.ticks));
        let mut extra = Map::new();
        extra.insert("native".into(), Value::Object(native));
        (docs, extra)
    }

    /// Świat → snapshot Store. Atomy `a{n}` zachowują numer; inne id (świat
    /// z Pythona: `cell_…`) dostają kolejne wolne numery. Bąbel bez `bid`
    /// (zapis Pythona) dostaje nowy numer i jest korzeniem, jak w `restore_bubbles`.
    pub fn snapshot_from_world(w: &World) -> StoreSnapshot {
        built_from_world(w).0
    }

    /// Snapshot ze świata i stemple ticków atomów, które je mają.
    fn built_from_world(w: &World) -> (StoreSnapshot, Vec<(u32, u64)>) {
        let native = match w.meta.get("native") {
            Some(Value::Object(m)) => m.clone(),
            _ => Map::new(),
        };
        let nget = |k: &str| native.get(k).and_then(Value::as_u64);
        let mut sid_to_aid: HashMap<String, u32> = HashMap::new();
        let mut next_atom = nget("next_atom").unwrap_or(0) as u32;
        for d in w.atoms() {
            if let Some(n) = num_after('a', &d.id) {
                next_atom = next_atom.max(n + 1);
            }
        }
        let mut atoms = Vec::new();
        let mut stamps = Vec::new();
        for d in w.atoms() {
            let aid = match num_after('a', &d.id) {
                Some(n) => n,
                None => {
                    let n = next_atom;
                    next_atom += 1;
                    n
                }
            };
            sid_to_aid.insert(d.id.clone(), aid);
            if let Some(stamp) = d.meta.get("tick").and_then(Value::as_u64) {
                stamps.push((aid, stamp));
            }
            atoms.push(AtomSnap {
                id: aid,
                s: d.s.clone(),
                e: d.e.clone(),
                t: d.t,
                value_token: d.meta.get("token").and_then(Value::as_u64).unwrap_or(0),
                payload: (!d.data.is_empty()).then(|| d.data.clone()),
            });
        }

        let mut next_bubble = (nget("next_bubble").unwrap_or(1) as u32).max(1);
        let mut recs = Vec::new();
        for d in w.bubbles() {
            let v = match d.meta.get("v") {
                Some(Value::Object(v)) => v.clone(),
                _ => Map::new(),
            };
            let bid = v
                .get("bid")
                .and_then(Value::as_u64)
                .map(|b| b as u32)
                .or_else(|| num_after('b', &d.id));
            if let Some(b) = bid {
                next_bubble = next_bubble.max(b + 1);
            }
            recs.push((d, v, bid));
        }
        let mut sid_to_bid: HashMap<String, u32> = HashMap::new();
        let mut bubbles = Vec::new();
        let mut binds = Vec::new();
        let mut roots = Vec::new();
        let mut parents = Vec::new();
        for (d, v, bid_in) in recs {
            let has_bid = bid_in.is_some();
            let bid = bid_in.unwrap_or_else(|| {
                let b = next_bubble;
                next_bubble += 1;
                b
            });
            sid_to_bid.insert(d.id.clone(), bid);
            let label = v
                .get("label")
                .and_then(Value::as_str)
                .map(str::to_string)
                .unwrap_or_else(|| if d.e.is_empty() { d.id.clone() } else { d.e.clone() });
            // kanon: meta.v.bindings; starsze światy: meta.bindings
            let bmap = match (v.get("bindings"), d.meta.get("bindings")) {
                (Some(Value::Object(b)), _) => b.clone(),
                (_, Some(Value::Object(b))) => b.clone(),
                _ => Map::new(),
            };
            for (name, target) in &bmap {
                let Some(t) = target.as_str() else { continue };
                if let Some(aid) = sid_to_aid.get(t) {
                    binds.push(BindSnap { bid, name: name.clone(), aid: *aid });
                }
            }
            let explicit = v.get("root").and_then(Value::as_bool);
            let is_root = match explicit {
                Some(flag) => flag,
                None => karmazyn_substrate::Store::legacy_python_bubble_is_root(has_bid),
            };
            if is_root {
                roots.push(bid);
            }
            parents.push((bid, v.get("parent").and_then(Value::as_str).map(str::to_string)));
            bubbles.push(BubbleSnap { id: bid, label, parent: None });
        }
        for (bid, parent) in parents {
            let p = parent.and_then(|s| sid_to_bid.get(&s).copied());
            if let Some(b) = bubbles.iter_mut().find(|b| b.id == bid) {
                b.parent = p;
            }
        }
        let snap = StoreSnapshot {
            thermal: native.get("thermal").and_then(Value::as_bool).unwrap_or(true),
            decay: native
                .get("decay")
                .and_then(Value::as_f64)
                .unwrap_or(karmazyn_substrate::DECAY_DEFAULT),
            reaped: nget("reaped").unwrap_or(0),
            next_atom,
            next_bubble,
            ticks: nget("ticks").unwrap_or(0),
            atoms,
            bubbles,
            binds,
            roots,
        };
        (snap, stamps)
    }

    fn install_world(store: &Store, w: &World) -> (usize, usize) {
        let (snap, stamps) = built_from_world(w);
        let counts = (snap.atoms.len(), snap.bubbles.len());
        let now = snap.ticks;
        store.import_snapshot(&snap);
        store.decay_to_tick(now, &stamps);
        counts
    }

    /// Store → plik świata (KAFX przy szyfrowaniu). Zwraca liczbę dokumentów.
    pub fn save_store(store: &Store, path: &std::path::Path, crypt: &crate::Crypt) -> Result<usize> {
        let (docs, extra) = world_from_snapshot(&store.export_snapshot());
        let saved = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs_f64())
            .unwrap_or(0.0);
        write_world(path, &docs, extra, crypt, saved)
    }

    /// Plik świata → Store (zastępuje zawartość). Zwraca (atomy, bąble).
    pub fn load_store(store: &Store, path: &std::path::Path, crypt: &crate::Crypt) -> Result<(usize, usize)> {
        let w = World::read(path, crypt.world.as_deref(), crypt.master.as_deref())?;
        if w.meta.get("format").and_then(Value::as_str) != Some(STORE_META) {
            return err(format!("{}: to nie jest świat {STORE_META}", path.display()));
        }
        let counts = install_world(store, &w);
        Ok(counts)
    }

    /// Id ramki z licznikami `native` (następne id, `reaped`) w dzienniku.
    pub const NATIVE_FRAME: &str = "@native";
    /// Dziennik nie mniejszy niż tyle bajtów, zanim próg wymusi compact.
    pub const COMPACT_MIN: u64 = 256 * 1024;

    /// Wynik `WorldLog::load`.
    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub struct LoadReport {
        pub atoms: usize,
        pub bubbles: usize,
        /// Ramki dziennika odtworzone na migawce.
        pub replayed: u64,
        /// Ogon dziennika obcięty (urwana ramka po twardym wyłączeniu).
        pub truncated: bool,
    }

    /// Wynik `WorldLog::save`.
    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub struct SaveReport {
        /// Ramki dopisane do dziennika (0 przy compact i bez zmian).
        pub frames: usize,
        /// Pełny zapis migawki i wyzerowany dziennik.
        pub compacted: bool,
        /// Dokumenty świata po zapisie.
        pub docs: usize,
    }

    /// Klucz treści dokumentu bez T: zmienia się, gdy zmienia się to, co
    /// autosync uważa za treść. Samo stygnięcie nie przepisuje dokumentu.
    fn doc_keys(snap: &StoreSnapshot) -> HashMap<String, u64> {
        use std::hash::{Hash, Hasher};
        let mut keys = HashMap::with_capacity(snap.atoms.len() + snap.bubbles.len());
        for a in &snap.atoms {
            let mut h = std::collections::hash_map::DefaultHasher::new();
            (&a.s, &a.e, a.value_token, &a.payload).hash(&mut h);
            keys.insert(atom_sid(a.id), h.finish());
        }
        for b in &snap.bubbles {
            let mut h = std::collections::hash_map::DefaultHasher::new();
            let mut binds: Vec<_> = snap
                .binds
                .iter()
                .filter(|x| x.bid == b.id)
                .map(|x| (&x.name, x.aid))
                .collect();
            binds.sort();
            (&b.label, b.parent, binds, snap.roots.contains(&b.id)).hash(&mut h);
            keys.insert(bubble_sid(b.id), h.finish());
        }
        keys
    }

    /// Dziennik obok migawki: `swiat.kafd` → `swiat.kafs`.
    pub fn journal_path(kafd: &Path) -> std::path::PathBuf {
        kafd.with_extension("kafs")
    }

    /// Świat z dziennikiem zmian. Migawka `<nazwa>.kafd` to pełny zapis jak
    /// `save_store` (czytelny dla Pythona); `<nazwa>.kafs` to dziennik KAFS
    /// z dokumentami, które zmieniły się od migawki, w KX1 tym samym kluczem
    /// świata. Pusta ramka = dokument usunięty; ramka `@native` = liczniki.
    /// Odczyt: migawka, potem ramki po kolei. Compact: pełny zapis migawki,
    /// potem pusty dziennik — przerwany w środku zostawia stan do odtworzenia.
    pub struct WorldLog {
        kafd: std::path::PathBuf,
        kafs: std::path::PathBuf,
        crypt: crate::Crypt,
        /// Klucze treści tego, co jest na dysku (migawka + dziennik).
        keys: HashMap<String, u64>,
        native: Map<String, Value>,
        journal: Option<crate::Journal>,
        /// Następny zapis musi być pełny (nowy świat, świat z obcymi id).
        full: bool,
    }

    impl WorldLog {
        pub fn new(kafd: &Path, crypt: &crate::Crypt) -> Self {
            let mut crypt = crypt.clone();
            if crypt.world.is_none() {
                crypt.world = Some(crate::cipher::infer_world_from_path(kafd));
            }
            WorldLog {
                kafd: kafd.to_path_buf(),
                kafs: journal_path(kafd),
                crypt,
                keys: HashMap::new(),
                native: Map::new(),
                journal: None,
                full: true,
            }
        }

        pub fn kafd(&self) -> &Path {
            &self.kafd
        }

        pub fn kafs(&self) -> &Path {
            &self.kafs
        }

        /// Bajty dziennika na dysku (0 = brak albo sam nagłówek).
        pub fn journal_bytes(&self) -> u64 {
            std::fs::metadata(&self.kafs).map(|m| m.len()).unwrap_or(0)
        }

        fn open_journal(&mut self) -> Result<&mut crate::Journal> {
            if self.journal.is_none() {
                let mut meta = Map::new();
                meta.insert("format".into(), Value::from(format!("{STORE_META}-journal")));
                let j = crate::Journal::open_with(&self.kafs, false, &meta, &self.crypt)?;
                self.journal = Some(j);
            }
            Ok(self.journal.as_mut().expect("dziennik otwarty"))
        }

        /// Migawka + dziennik → Store. `Ok(None)` = świata jeszcze nie ma
        /// (osierocony dziennik bez migawki zostanie wyzerowany przy zapisie).
        pub fn load(&mut self, store: &Store) -> Result<Option<LoadReport>> {
            if !self.kafd.exists() {
                self.full = true;
                return Ok(None);
            }
            let mut w = World::read(&self.kafd, self.crypt.world.as_deref(), self.crypt.master.as_deref())?;
            if w.meta.get("format").and_then(Value::as_str) != Some(STORE_META) {
                return err(format!("{}: to nie jest świat {STORE_META}", self.kafd.display()));
            }
            let (mut replayed, mut truncated) = (0, false);
            if self.journal_bytes() > 8 {
                let j = self.open_journal()?;
                truncated = j.recovered.truncated;
                for a in j.atoms(0.0)? {
                    replayed += 1;
                    if a.id == NATIVE_FRAME {
                        if let Some(n) = json::loads(&a.data) {
                            w.meta.insert("native".into(), Value::Object(n));
                        }
                    } else if a.data.is_empty() {
                        w.docs.retain(|d| d.id != a.id);
                    } else if let Some(doc) = decode_doc(&a.id, &a.data) {
                        match w.docs.iter_mut().find(|d| d.id == a.id) {
                            Some(slot) => *slot = doc,
                            None => w.docs.push(doc),
                        }
                    }
                }
            }
            let (atoms, bubbles) = install_world(store, &w);
            let report = LoadReport {
                atoms,
                bubbles,
                replayed,
                truncated,
            };
            // to, co jest na dysku, w id natywnego Store
            let back = store.export_snapshot();
            let (_, extra) = world_from_snapshot(&back);
            self.native = match extra.get("native") {
                Some(Value::Object(m)) => m.clone(),
                _ => Map::new(),
            };
            self.keys = doc_keys(&back);
            // świat z obcymi id (zapis Pythona): dziennik nie może dopisywać
            // `a{n}` obok `cell_…`, więc pierwszy zapis jest pełny
            let on_disk: std::collections::HashSet<&str> = w.docs.iter().map(|d| d.id.as_str()).collect();
            self.full = on_disk.len() != self.keys.len()
                || self.keys.keys().any(|k| !on_disk.contains(k.as_str()));
            Ok(Some(report))
        }

        /// Zapis: tylko zmienione dokumenty do dziennika (bez T, bez fsync na
        /// ramkę, jeden commit). Pełny zapis, gdy świata nie ma, gdy go
        /// trzeba (obce id) albo gdy dziennik przerósł migawkę.
        pub fn save(&mut self, store: &Store) -> Result<SaveReport> {
            if self.full {
                return self.compact(store);
            }
            let snap = store.export_snapshot();
            let (docs, extra) = world_from_snapshot(&snap);
            let keys = doc_keys(&snap);
            let native = match extra.get("native") {
                Some(Value::Object(m)) => m.clone(),
                _ => Map::new(),
            };
            let mut frames: Vec<crate::Atom> = Vec::new();
            for (id, data) in &docs {
                if self.keys.get(id) != keys.get(id) {
                    frames.push(crate::Atom::new(id.clone(), data.clone(), crate::MIME_DEFAULT, 50.0, 100.0, crate::A_RAW));
                }
            }
            let mut gone: Vec<&String> = self.keys.keys().filter(|id| !keys.contains_key(*id)).collect();
            gone.sort();
            for id in gone {
                frames.push(crate::Atom::new(id.clone(), Vec::new(), crate::MIME_DEFAULT, 50.0, 100.0, crate::A_RAW));
            }
            if native != self.native {
                frames.push(crate::Atom::new(
                    NATIVE_FRAME,
                    json::dumps(&native),
                    "application/json",
                    50.0,
                    100.0,
                    crate::A_RAW,
                ));
            }
            if !frames.is_empty() {
                let j = self.open_journal()?;
                for a in &frames {
                    j.append_atom(a)?;
                }
                j.commit()?;
            }
            self.keys = keys;
            self.native = native;
            let world_bytes = std::fs::metadata(&self.kafd).map(|m| m.len()).unwrap_or(0);
            if self.journal_bytes() >= world_bytes.max(COMPACT_MIN) {
                return self.compact(store);
            }
            Ok(SaveReport { frames: frames.len(), compacted: false, docs: docs.len() })
        }

        /// Pełny zapis migawki (jak `save_store`, z T), potem pusty dziennik.
        pub fn compact(&mut self, store: &Store) -> Result<SaveReport> {
            let snap = store.export_snapshot();
            let (docs, extra) = world_from_snapshot(&snap);
            let saved = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_secs_f64())
                .unwrap_or(0.0);
            let n = write_world(&self.kafd, &docs, extra.clone(), &self.crypt, saved)?;
            if let Some(mut j) = self.journal.take() {
                j.close(false)?;
            }
            if self.kafs.exists() {
                crate::reset_journal(&self.kafs)?;
            }
            self.keys = doc_keys(&snap);
            self.native = match extra.get("native") {
                Some(Value::Object(m)) => m.clone(),
                _ => Map::new(),
            };
            self.full = false;
            Ok(SaveReport { frames: 0, compacted: true, docs: n })
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn doc_roundtrip_and_mime() {
        let mut m = Map::new();
        m.insert("token".into(), Value::from(7));
        let b = encode_doc("document", "tekst", 55.0, m, b"\x00bin");
        let d = decode_doc("a1", &b).unwrap();
        assert_eq!((d.s.as_str(), d.e.as_str(), d.t, d.data.as_slice()), ("document", "tekst", 55.0, &b"\x00bin"[..]));
        assert_eq!(d.meta["token"], 7);
        assert_eq!(extension("a.b/c.TXT"), ".TXT");
        assert_eq!(extension(".bashrc"), "");
        assert_eq!(extension("plik"), "");
        assert_eq!(detect_mime(b"abc", "x.txt"), "text/plain");
        assert_eq!(detect_mime(br#"{"_manifest_v": 2, "T": 80}"#, "m"), "application/x-phi-manifest");
        assert!(decode_doc("x", b"\x00\x00\x00\x09nie-json").is_none());
    }

    #[cfg(feature = "substrate")]
    #[test]
    fn store_roundtrip_keeps_ids_parents_roots() {
        use karmazyn_substrate::Store;
        let s = Store::new(true);
        let a = s.atom_new("var", "x", 80.0);
        let b = s.atom_new("plik", "kod", 50.0);
        s.atom_set_guest(b, 3, Some(b"return 1".to_vec()));
        let root = s.bubble_new("fs", None);
        s.set_root(root);
        let child = s.bubble_new("bin", Some(root));
        s.bind(child, "hej", b).unwrap();
        s.bind(root, "x", a).unwrap();
        let free = s.bubble_new("luzem", None);

        let dir = std::env::temp_dir().join(format!("kafd_world_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let path = dir.join("swiat.kafd");
        let crypt = crate::Crypt::with_master(&[3u8; 32]);
        save_store(&s, &path, &crypt).unwrap();
        assert!(crate::cipher::is_kafx(&std::fs::read(&path).unwrap()));

        let t = Store::new(true);
        let (na, nb) = load_store(&t, &path, &crypt).unwrap();
        assert_eq!((na, nb), (2, 3));
        assert_eq!(t.atom_se(a).unwrap(), ("var".to_string(), "x".to_string()));
        assert_eq!(t.atom_payload(b).as_deref(), Some(&b"return 1"[..]));
        assert_eq!(t.atom_value_token(b), Some(3));
        assert_eq!(t.lookup(child, "hej"), Some(b));
        assert_eq!(t.bubble_parent(child), Some(Some(root)));
        assert!(t.is_root(root) && !t.is_root(free));
        assert_eq!(t.bubble_label(free).as_deref(), Some("luzem"));
        // nowy atom nie koliduje z wczytanymi
        assert!(t.atom_new("nowy", "", 50.0) > b);
        assert!(load_store(&t, &path, &crate::Crypt::with_master(&[4u8; 32])).is_err());
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[cfg(feature = "substrate")]
    fn tmpdir(name: &str) -> std::path::PathBuf {
        let d = std::env::temp_dir().join(format!("kafd_wlog_{}_{name}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(&d).unwrap();
        d
    }

    /// Zmiana jednego atomu dopisuje ramkę do `.kafs`, a koperty `.kafd`
    /// nie rusza. Usunięcie i liczniki idą ramkami, odczyt odtwarza stan.
    #[cfg(feature = "substrate")]
    #[test]
    fn worldlog_appends_changes_and_replays() {
        use karmazyn_substrate::Store;
        let dir = tmpdir("append");
        let path = dir.join("swiat.kafd");
        let crypt = crate::Crypt::with_master(&[3u8; 32]);
        let s = Store::new(true);
        let root = s.bubble_new("r", None);
        s.set_root(root);
        let mut ids = Vec::new();
        for i in 0..50 {
            let a = s.atom_new("var", &format!("x{i}"), 60.0);
            s.atom_set_guest(a, 0, Some(vec![b'z'; 200]));
            s.bind(root, &format!("x{i}"), a).unwrap();
            ids.push(a);
        }
        let mut log = WorldLog::new(&path, &crypt);
        assert_eq!(log.load(&s).unwrap(), None);
        let first = log.save(&s).unwrap();
        assert!(first.compacted, "nowy świat: pełny zapis");
        let kafd_before = std::fs::read(&path).unwrap();

        // samo stygnięcie: jedna ramka licznika, bez przepisywania atomów
        s.settle(3);
        assert_eq!(log.save(&s).unwrap().frames, 1);

        // jeden atom: jedna ramka, koperta nietknięta
        s.atom_set_guest(ids[7], 0, Some(b"nowe".to_vec()));
        let r = log.save(&s).unwrap();
        assert_eq!((r.frames, r.compacted), (1, false));
        assert_eq!(std::fs::read(&path).unwrap(), kafd_before, "koperta przepisana");
        assert!(log.journal_bytes() > 8);
        let raw = std::fs::read(log.kafs()).unwrap();
        assert!(!raw.windows(4).any(|w| w == b"nowe"), "dane jawne w dzienniku");

        // nowy atom (+ zmieniony bąbel, + liczniki), usunięty atom (+ bąbel)
        let extra = s.atom_new("var", "nowy", 70.0);
        s.bind(root, "nowy", extra).unwrap();
        s.unbind(root, "x3");
        s.delete_atom(ids[3]);
        assert_eq!(log.save(&s).unwrap().frames, 4);

        let t = Store::new(true);
        let mut back = WorldLog::new(&path, &crypt);
        let rep = back.load(&t).unwrap().unwrap();
        assert_eq!((rep.atoms, rep.bubbles, rep.replayed, rep.truncated), (50, 1, 6, false));
        assert_eq!(t.atom_payload(ids[7]).as_deref(), Some(&b"nowe"[..]));
        assert!(!t.has_atom(ids[3]));
        assert_eq!(t.lookup(root, "nowy"), Some(extra));
        assert!(t.atom_new("kolejny", "", 50.0) > extra, "licznik id z ramki @native");
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// Compact daje migawkę taką jak pełny zapis (`save_store`) tego samego
    /// stanu, a urwany ogon dziennika po twardym wyłączeniu odpada.
    #[cfg(feature = "substrate")]
    #[test]
    fn worldlog_compact_equals_full_save_and_survives_torn_tail() {
        use karmazyn_substrate::Store;
        let dir = tmpdir("compact");
        let path = dir.join("swiat.kafd");
        let crypt = crate::Crypt::with_master(&[3u8; 32]);
        let s = Store::new(true);
        let root = s.bubble_new("r", None);
        s.set_root(root);
        let a = s.atom_new("var", "x", 60.0);
        s.bind(root, "x", a).unwrap();
        let mut log = WorldLog::new(&path, &crypt);
        log.save(&s).unwrap();
        s.atom_set_guest(a, 0, Some(b"pierwsza".to_vec()));
        log.save(&s).unwrap();
        let good = log.journal_bytes();

        // urwana ramka: dziennik obcięty do ostatniej dobrej
        {
            use std::io::Write;
            let mut f = std::fs::OpenOptions::new().append(true).open(log.kafs()).unwrap();
            f.write_all(&[crate::FT_ATOM, 0, 0, 0, 99, 1, 2]).unwrap();
        }
        let t = Store::new(true);
        let mut back = WorldLog::new(&path, &crypt);
        let rep = back.load(&t).unwrap().unwrap();
        assert!(rep.truncated);
        assert_eq!(back.journal_bytes(), good);
        assert_eq!(t.atom_payload(a).as_deref(), Some(&b"pierwsza"[..]));

        // compact = pełny zapis: te same dokumenty i META (bez `saved`)
        back.compact(&t).unwrap();
        assert_eq!(back.journal_bytes(), 8);
        let full = dir.join("pelny.kafd");
        save_store(&t, &full, &crate::Crypt { world: Some("swiat".into()), ..crypt.clone() }).unwrap();
        let x = World::read(&path, Some("swiat"), Some(&[3u8; 32])).unwrap();
        let y = World::read(&full, Some("swiat"), Some(&[3u8; 32])).unwrap();
        assert_eq!(x.docs, y.docs);
        let strip = |m: &Map<String, Value>| {
            let mut m = m.clone();
            m.remove("saved");
            m
        };
        assert_eq!(strip(&x.meta), strip(&y.meta));
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// Stygnięcie wraca tym samym zanikiem. Korzeń jest tylko jawny,
    /// a bąbel bez `bid` jest korzeniem przez funkcję substratu.
    #[cfg(feature = "substrate")]
    #[test]
    fn worldlog_restores_temperature_and_explicit_roots() {
        use karmazyn_substrate::Store;
        let dir = tmpdir("temp");
        let path = dir.join("swiat.kafd");
        let crypt = crate::Crypt::with_master(&[3u8; 32]);
        let s = Store::new(true);
        let root = s.bubble_new("r", None);
        s.set_root(root);
        let a = s.atom_new("var", "x", 50.0);
        s.bind(root, "x", a).unwrap();
        let mut log = WorldLog::new(&path, &crypt);
        log.save(&s).unwrap();
        s.settle(10);
        let live = s.get_atom_t(a).unwrap();
        log.save(&s).unwrap();
        let t = Store::new(true);
        WorldLog::new(&path, &crypt).load(&t).unwrap().unwrap();
        assert!((t.get_atom_t(a).unwrap() - live).abs() < 1e-9);
        assert!(t.is_root(root));

        let loose = {
            let mut v = Map::new();
            v.insert("label".into(), Value::from("luz"));
            v.insert("bid".into(), Value::from(9u64));
            v.insert("bindings".into(), Value::Object(Map::new()));
            v.insert("parent".into(), Value::Null);
            let mut meta = Map::new();
            meta.insert("v".into(), Value::Object(v));
            encode_doc(BUBBLE_S, "luz", 50.0, meta, b"")
        };
        let legacy = {
            let mut v = Map::new();
            v.insert("label".into(), Value::from("stary"));
            v.insert("bindings".into(), Value::Object(Map::new()));
            let mut meta = Map::new();
            meta.insert("v".into(), Value::Object(v));
            encode_doc(BUBBLE_S, "stary", 50.0, meta, b"")
        };
        let docs = vec![
            ("b9".to_string(), loose),
            ("cell_b".to_string(), legacy),
        ];
        let mut extra = Map::new();
        let mut native = Map::new();
        native.insert("next_bubble".into(), Value::from(10u64));
        native.insert("ticks".into(), Value::from(0u64));
        extra.insert("native".into(), Value::Object(native));
        let path2 = dir.join("korzenie.kafd");
        write_world(&path2, &docs, extra, &crypt, 1.0).unwrap();
        let u = Store::new(true);
        load_store(&u, &path2, &crypt).unwrap();
        assert!(!u.is_root(9), "bąbel z bid i bez flagi root nie jest korzeniem");
        let roots = u.root_ids();
        assert_eq!(roots.len(), 1, "tylko bąbel bez bid");
        assert_ne!(roots[0], 9);
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// Świat z obcymi id (zapis Pythona) dostaje pełny zapis przy pierwszej
    /// zmianie, żeby dziennik nie zdublował dokumentów.
    #[cfg(feature = "substrate")]
    #[test]
    fn worldlog_foreign_ids_force_full_save() {
        use karmazyn_substrate::Store;
        let dir = tmpdir("foreign");
        let path = dir.join("swiat.kafd");
        let crypt = crate::Crypt::with_master(&[3u8; 32]);
        let docs = vec![("cell_1".to_string(), encode_doc("var", "x", 55.0, Map::new(), b"py"))];
        let mut extra = Map::new();
        extra.insert("origin".into(), Value::from("python"));
        write_world(&path, &docs, extra, &crypt, 1.0).unwrap();

        let s = Store::new(true);
        let mut log = WorldLog::new(&path, &crypt);
        assert_eq!(log.load(&s).unwrap().unwrap().atoms, 1);
        let r = log.save(&s).unwrap();
        assert!(r.compacted);
        let w = World::read(&path, Some("swiat"), Some(&[3u8; 32])).unwrap();
        assert_eq!(w.docs.len(), 1);
        assert!(w.docs[0].id.starts_with('a'));
        let _ = std::fs::remove_dir_all(&dir);
    }
}
