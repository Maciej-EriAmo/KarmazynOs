//! Full Store snapshot (atoms + bubbles + binds + roots) — Stage 2 persist.
//!
//! Text format v1 (no serde / no Python):
//! ```text
//! KSUB_SNAP 1
//! META thermal=1 decay=0.92 reaped=0 next_atom=2 next_bubble=1
//! ATOM id s e t token
//! PAYLOAD id hex            # optional guest blob (v2)
//! BUBBLE id label parent   # parent=-1 if none
//! BIND bid name aid
//! ROOT bid
//! END
//! ```
//! Fields `s`, `e`, `label`, `name` use backslash escapes: `\\` `\n` `\t` `\|` `\ `.

use crate::atom::{clamp_t, Atom, AtomId, T_INIT};
use crate::store::{Bubble, BubbleId, Store};
use std::collections::{HashMap, HashSet};
use std::fmt::Write as _;
use std::fs;
use std::path::Path;

pub const SNAP_VERSION: u32 = 2;

#[derive(Debug, Clone)]
pub struct AtomSnap {
    pub id: AtomId,
    pub s: String,
    pub e: String,
    pub t: f64,
    pub value_token: u64,
    pub payload: Option<Vec<u8>>,
}

#[derive(Debug, Clone)]
pub struct BubbleSnap {
    pub id: BubbleId,
    pub label: String,
    pub parent: Option<BubbleId>,
}

#[derive(Debug, Clone)]
pub struct BindSnap {
    pub bid: BubbleId,
    pub name: String,
    pub aid: AtomId,
}

#[derive(Debug, Clone)]
pub struct StoreSnapshot {
    pub thermal: bool,
    pub decay: f64,
    pub reaped: u64,
    pub next_atom: AtomId,
    pub next_bubble: BubbleId,
    pub atoms: Vec<AtomSnap>,
    pub bubbles: Vec<BubbleSnap>,
    pub binds: Vec<BindSnap>,
    pub roots: Vec<BubbleId>,
}

impl Store {
    /// Export full structural snapshot (hooks not included).
    pub fn export_snapshot(&self) -> StoreSnapshot {
        let g = self.lock();
        let mut atoms: Vec<AtomSnap> = g
            .atoms
            .values()
            .map(|a| AtomSnap {
                id: a.id,
                s: a.s.clone(),
                e: a.e.clone(),
                t: a.t,
                value_token: a.value_token,
                payload: a.payload.clone(),
            })
            .collect();
        atoms.sort_by_key(|a| a.id);

        let mut bubbles: Vec<BubbleSnap> = g
            .bubbles
            .values()
            .map(|b| BubbleSnap {
                id: b.id,
                label: b.label.clone(),
                parent: b.parent,
            })
            .collect();
        bubbles.sort_by_key(|b| b.id);

        let mut binds = Vec::new();
        for b in g.bubbles.values() {
            let mut names: Vec<_> = b.bindings.keys().cloned().collect();
            names.sort();
            for name in names {
                if let Some(&aid) = b.bindings.get(&name) {
                    binds.push(BindSnap {
                        bid: b.id,
                        name,
                        aid,
                    });
                }
            }
        }
        binds.sort_by(|a, b| (a.bid, &a.name).cmp(&(b.bid, &b.name)));

        StoreSnapshot {
            thermal: g.thermal,
            decay: g.decay,
            reaped: g.reaped,
            next_atom: g.next_atom,
            next_bubble: g.next_bubble,
            atoms,
            bubbles,
            binds,
            roots: g.roots.clone(),
        }
    }

    /// Replace store content from snapshot (hooks cleared / kept empty).
    pub fn import_snapshot(&self, snap: &StoreSnapshot) {
        let mut g = self.lock();
        g.atoms.clear();
        g.bubbles.clear();
        g.roots.clear();
        g.retained_tomb.clear();
        g.thermal = snap.thermal;
        g.decay = snap.decay;
        g.reaped = snap.reaped;
        g.next_atom = snap.next_atom;
        g.next_bubble = snap.next_bubble;
        g.ticking = false;

        for a in &snap.atoms {
            let tt = clamp_t(if a.t.is_nan() { T_INIT } else { a.t });
            let mut atom = Atom::new(a.id, a.s.clone(), a.e.clone(), tt);
            atom.value_token = a.value_token;
            atom.payload = a.payload.clone();
            g.atoms.insert(a.id, atom);
            if a.id >= g.next_atom {
                g.next_atom = a.id.saturating_add(1);
            }
        }

        for b in &snap.bubbles {
            g.bubbles.insert(
                b.id,
                Bubble {
                    id: b.id,
                    label: b.label.clone(),
                    parent: b.parent,
                    bindings: HashMap::new(),
                },
            );
            if b.id >= g.next_bubble {
                g.next_bubble = b.id.saturating_add(1);
            }
        }

        for bind in &snap.binds {
            if !g.atoms.contains_key(&bind.aid) {
                continue;
            }
            if let Some(bubble) = g.bubbles.get_mut(&bind.bid) {
                bubble.bindings.insert(bind.name.clone(), bind.aid);
            }
        }

        let known: HashSet<BubbleId> = g.bubbles.keys().copied().collect();
        g.roots = snap
            .roots
            .iter()
            .copied()
            .filter(|r| known.contains(r))
            .collect();
    }

    pub fn save_snapshot_file(&self, path: impl AsRef<Path>) -> Result<(), String> {
        let text = self.export_snapshot().to_text();
        fs::write(path.as_ref(), text).map_err(|e| e.to_string())
    }

    pub fn load_snapshot_file(&self, path: impl AsRef<Path>) -> Result<(), String> {
        let text = fs::read_to_string(path.as_ref()).map_err(|e| e.to_string())?;
        let snap = StoreSnapshot::from_text(&text)?;
        self.import_snapshot(&snap);
        Ok(())
    }
}

impl StoreSnapshot {
    pub fn to_text(&self) -> String {
        let mut out = String::new();
        let _ = writeln!(out, "KSUB_SNAP {SNAP_VERSION}");
        let _ = writeln!(
            out,
            "META thermal={} decay={} reaped={} next_atom={} next_bubble={}",
            if self.thermal { 1 } else { 0 },
            self.decay,
            self.reaped,
            self.next_atom,
            self.next_bubble
        );
        for a in &self.atoms {
            let _ = writeln!(
                out,
                "ATOM {} {} {} {} {}",
                a.id,
                escape_field(&a.s),
                escape_field(&a.e),
                a.t,
                a.value_token
            );
            if let Some(p) = &a.payload {
                if !p.is_empty() {
                    let _ = writeln!(out, "PAYLOAD {} {}", a.id, hex_encode(p));
                }
            }
        }
        for b in &self.bubbles {
            let parent = b.parent.map(|p| p as i64).unwrap_or(-1);
            let _ = writeln!(
                out,
                "BUBBLE {} {} {}",
                b.id,
                escape_field(&b.label),
                parent
            );
        }
        for bind in &self.binds {
            let _ = writeln!(
                out,
                "BIND {} {} {}",
                bind.bid,
                escape_field(&bind.name),
                bind.aid
            );
        }
        for r in &self.roots {
            let _ = writeln!(out, "ROOT {r}");
        }
        let _ = writeln!(out, "END");
        out
    }

    pub fn from_text(text: &str) -> Result<Self, String> {
        let mut thermal = true;
        let mut decay = crate::atom::DECAY_DEFAULT;
        let mut reaped = 0u64;
        let mut next_atom = 0u32;
        let mut next_bubble = 0u32;
        let mut atoms = Vec::new();
        let mut bubbles = Vec::new();
        let mut binds = Vec::new();
        let mut roots = Vec::new();
        let mut saw_header = false;
        let mut saw_end = false;

        for (lineno, raw) in text.lines().enumerate() {
            let line = raw.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            let mut parts = split_fields(line);
            if parts.is_empty() {
                continue;
            }
            let tag = parts.remove(0);
            match tag.as_str() {
                "KSUB_SNAP" => {
                    let ver: u32 = parts
                        .first()
                        .ok_or_else(|| format!("line {}: missing version", lineno + 1))?
                        .parse()
                        .map_err(|_| format!("line {}: bad version", lineno + 1))?;
                    if ver != 1 && ver != SNAP_VERSION {
                        return Err(format!("unsupported snapshot version {ver}"));
                    }
                    saw_header = true;
                }
                "META" => {
                    for p in &parts {
                        if let Some((k, v)) = p.split_once('=') {
                            match k {
                                "thermal" => thermal = v != "0",
                                "decay" => {
                                    decay = v.parse().map_err(|_| {
                                        format!("line {}: bad decay", lineno + 1)
                                    })?
                                }
                                "reaped" => {
                                    reaped = v.parse().map_err(|_| {
                                        format!("line {}: bad reaped", lineno + 1)
                                    })?
                                }
                                "next_atom" => {
                                    next_atom = v.parse().map_err(|_| {
                                        format!("line {}: bad next_atom", lineno + 1)
                                    })?
                                }
                                "next_bubble" => {
                                    next_bubble = v.parse().map_err(|_| {
                                        format!("line {}: bad next_bubble", lineno + 1)
                                    })?
                                }
                                _ => {}
                            }
                        }
                    }
                }
                "ATOM" => {
                    if parts.len() < 5 {
                        return Err(format!("line {}: ATOM needs 5 fields", lineno + 1));
                    }
                    atoms.push(AtomSnap {
                        id: parts[0]
                            .parse()
                            .map_err(|_| format!("line {}: bad atom id", lineno + 1))?,
                        s: unescape_field(&parts[1]),
                        e: unescape_field(&parts[2]),
                        t: parts[3]
                            .parse()
                            .map_err(|_| format!("line {}: bad t", lineno + 1))?,
                        value_token: parts[4]
                            .parse()
                            .map_err(|_| format!("line {}: bad token", lineno + 1))?,
                        payload: None,
                    });
                }
                "PAYLOAD" => {
                    if parts.len() < 2 {
                        return Err(format!("line {}: PAYLOAD needs id hex", lineno + 1));
                    }
                    let id: AtomId = parts[0]
                        .parse()
                        .map_err(|_| format!("line {}: bad payload id", lineno + 1))?;
                    let blob = hex_decode(&parts[1])
                        .map_err(|e| format!("line {}: payload hex: {e}", lineno + 1))?;
                    if let Some(a) = atoms.iter_mut().rev().find(|a| a.id == id) {
                        a.payload = Some(blob);
                    } else {
                        return Err(format!("line {}: PAYLOAD for unknown atom {id}", lineno + 1));
                    }
                }
                "BUBBLE" => {
                    if parts.len() < 3 {
                        return Err(format!("line {}: BUBBLE needs 3 fields", lineno + 1));
                    }
                    let parent_i: i64 = parts[2]
                        .parse()
                        .map_err(|_| format!("line {}: bad parent", lineno + 1))?;
                    bubbles.push(BubbleSnap {
                        id: parts[0]
                            .parse()
                            .map_err(|_| format!("line {}: bad bubble id", lineno + 1))?,
                        label: unescape_field(&parts[1]),
                        parent: if parent_i < 0 {
                            None
                        } else {
                            Some(parent_i as u32)
                        },
                    });
                }
                "BIND" => {
                    if parts.len() < 3 {
                        return Err(format!("line {}: BIND needs 3 fields", lineno + 1));
                    }
                    binds.push(BindSnap {
                        bid: parts[0]
                            .parse()
                            .map_err(|_| format!("line {}: bad bid", lineno + 1))?,
                        name: unescape_field(&parts[1]),
                        aid: parts[2]
                            .parse()
                            .map_err(|_| format!("line {}: bad aid", lineno + 1))?,
                    });
                }
                "ROOT" => {
                    let bid: u32 = parts
                        .first()
                        .ok_or_else(|| format!("line {}: ROOT needs id", lineno + 1))?
                        .parse()
                        .map_err(|_| format!("line {}: bad root", lineno + 1))?;
                    roots.push(bid);
                }
                "END" => {
                    saw_end = true;
                    break;
                }
                other => {
                    return Err(format!("line {}: unknown tag {other}", lineno + 1));
                }
            }
        }

        if !saw_header {
            return Err("missing KSUB_SNAP header".into());
        }
        if !saw_end {
            return Err("missing END".into());
        }

        Ok(StoreSnapshot {
            thermal,
            decay,
            reaped,
            next_atom,
            next_bubble,
            atoms,
            bubbles,
            binds,
            roots,
        })
    }
}

fn hex_encode(b: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(b.len() * 2);
    for &x in b {
        out.push(HEX[(x >> 4) as usize] as char);
        out.push(HEX[(x & 0xf) as usize] as char);
    }
    out
}

fn hex_decode(s: &str) -> Result<Vec<u8>, String> {
    if s.len() % 2 != 0 {
        return Err("odd length".into());
    }
    let mut out = Vec::with_capacity(s.len() / 2);
    let bytes = s.as_bytes();
    let nibble = |c: u8| -> Result<u8, String> {
        match c {
            b'0'..=b'9' => Ok(c - b'0'),
            b'a'..=b'f' => Ok(c - b'a' + 10),
            b'A'..=b'F' => Ok(c - b'A' + 10),
            _ => Err("bad hex".into()),
        }
    };
    let mut i = 0;
    while i < bytes.len() {
        let hi = nibble(bytes[i])?;
        let lo = nibble(bytes[i + 1])?;
        out.push((hi << 4) | lo);
        i += 2;
    }
    Ok(out)
}

fn escape_field(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for c in s.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            ' ' => out.push_str("\\s"),
            '\t' => out.push_str("\\t"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '|' => out.push_str("\\|"),
            _ => out.push(c),
        }
    }
    if out.is_empty() {
        out.push_str("\\0");
    }
    out
}

fn unescape_field(s: &str) -> String {
    if s == "\\0" {
        return String::new();
    }
    let mut out = String::with_capacity(s.len());
    let mut chars = s.chars().peekable();
    while let Some(c) = chars.next() {
        if c == '\\' {
            match chars.next() {
                Some('\\') => out.push('\\'),
                Some('s') => out.push(' '),
                Some('t') => out.push('\t'),
                Some('n') => out.push('\n'),
                Some('r') => out.push('\r'),
                Some('|') => out.push('|'),
                Some('0') => {}
                Some(other) => {
                    out.push('\\');
                    out.push(other);
                }
                None => out.push('\\'),
            }
        } else {
            out.push(c);
        }
    }
    out
}

fn split_fields(line: &str) -> Vec<String> {
    line.split_whitespace().map(|s| s.to_string()).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::Store;

    #[test]
    fn snapshot_roundtrip_text() {
        let s = Store::new(true);
        let root = s.bubble_new("root bubble", None);
        s.set_root(root);
        let a = s.atom_new("var", "hello world", 50.0);
        s.atom_set_value_token(a, 99);
        s.bind(root, "x y", a).unwrap();
        s.settle(5);

        let text = s.export_snapshot().to_text();
        assert!(text.contains("KSUB_SNAP 2"));
        assert!(text.contains("ATOM"));
        assert!(text.contains("ROOT"));

        let s2 = Store::new(false);
        let snap = StoreSnapshot::from_text(&text).expect("parse");
        s2.import_snapshot(&snap);

        assert!(s2.has_atom(a));
        assert!((s2.get_atom_t(a).unwrap() - s.get_atom_t(a).unwrap()).abs() < 1e-12);
        assert_eq!(s2.atom_value_token(a), Some(99));
        assert_eq!(s2.lookup(root, "x y"), Some(a));
        assert_eq!(s2.stats().bubbles, 1);
        assert_eq!(s2.stats().total, 1);
    }

    #[test]
    fn snapshot_payload_travels_with_atom() {
        let s = Store::new(false);
        let a = s.atom_new("var", "clo", 50.0);
        s.atom_set_guest(a, 7, Some(b"lambda".to_vec()));
        let text = s.export_snapshot().to_text();
        assert!(text.contains("PAYLOAD"));
        let s2 = Store::new(false);
        s2.import_snapshot(&StoreSnapshot::from_text(&text).unwrap());
        assert_eq!(s2.atom_payload(a).as_deref(), Some(&b"lambda"[..]));
        assert_eq!(s2.atom_value_token(a), Some(7));
        s2.delete_atom(a);
        assert!(s2.atom_payload(a).is_none());
    }

    #[test]
    fn snapshot_v1_still_loads() {
        let text = "KSUB_SNAP 1\nMETA thermal=0 decay=0.92 reaped=0 next_atom=1 next_bubble=0\nATOM 0 var x 50 99\nEND\n";
        let snap = StoreSnapshot::from_text(text).expect("v1");
        let s = Store::new(true);
        s.import_snapshot(&snap);
        assert_eq!(s.atom_value_token(0), Some(99));
        assert!(s.atom_payload(0).is_none());
    }

    #[test]
    fn snapshot_file_roundtrip() {
        let dir = std::env::temp_dir().join(format!(
            "ksub_snap_{}",
            std::process::id()
        ));
        let _ = fs::create_dir_all(&dir);
        let path = dir.join("store.ksub");

        let s = Store::new(true);
        let b = s.bubble_new("r", None);
        s.set_root(b);
        let a = s.atom_new("s", "e", 42.0);
        s.bind(b, "k", a).unwrap();
        s.save_snapshot_file(&path).expect("save");

        let s2 = Store::new(true);
        s2.load_snapshot_file(&path).expect("load");
        assert!(s2.has_atom(a));
        // check T before lookup — thermal lookup touches (heats) the atom
        assert!((s2.get_atom_t(a).unwrap() - 42.0).abs() < 1e-12);
        assert_eq!(s2.lookup(b, "k"), Some(a));

        let _ = fs::remove_file(&path);
        let _ = fs::remove_dir(&dir);
    }
}
