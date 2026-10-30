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
pub use store::{load_store, save_store, snapshot_from_world, world_from_snapshot};

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
        let mut extra = Map::new();
        extra.insert("native".into(), Value::Object(native));
        (docs, extra)
    }

    /// Świat → snapshot Store. Atomy `a{n}` zachowują numer; inne id (świat
    /// z Pythona: `cell_…`) dostają kolejne wolne numery. Bąbel bez `bid`
    /// (zapis Pythona) dostaje nowy numer i jest korzeniem, jak w `restore_bubbles`.
    pub fn snapshot_from_world(w: &World) -> StoreSnapshot {
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
        for (d, v, bid) in recs {
            let bid = bid.unwrap_or_else(|| {
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
            if v.get("root").and_then(Value::as_bool).unwrap_or(true) {
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
        StoreSnapshot {
            thermal: native.get("thermal").and_then(Value::as_bool).unwrap_or(true),
            decay: native
                .get("decay")
                .and_then(Value::as_f64)
                .unwrap_or(karmazyn_substrate::DECAY_DEFAULT),
            reaped: nget("reaped").unwrap_or(0),
            next_atom,
            next_bubble,
            atoms,
            bubbles,
            binds,
            roots,
        }
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
        let snap = snapshot_from_world(&w);
        let counts = (snap.atoms.len(), snap.bubbles.len());
        store.import_snapshot(&snap);
        Ok(counts)
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
}
