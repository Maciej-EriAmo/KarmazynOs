//! Kod na szwie substratu: bąbel z etykietą, treść w atomie `src`.
//!
//! Narzędzie shell woła po etykiecie. Biblioteka `require` jest widoczna
//! tylko z wołającego: powiązanie (bind o nazwie modułu na atom `src`)
//! albo bąbel o tej etykiecie na drodze rodzica (reach idzie w górę).

use karmazyn_substrate::{AtomId, BubbleId, Store, T_INIT};

/// Nazwa wiązania, pod którą leży źródło.
pub const SRC: &str = "src";

pub fn is_label(name: &str) -> bool {
    !name.is_empty()
        && !name.contains('/')
        && !name.contains('\\')
        && !name.contains('@')
        && !name.chars().any(|c| c.is_whitespace() || c.is_control())
}

/// Najnowszy bąbel z etykietą.
pub fn newest(store: &Store, label: &str) -> Option<BubbleId> {
    store
        .bubble_ids()
        .into_iter()
        .filter(|b| store.bubble_label(*b).as_deref() == Some(label))
        .max()
}

fn src_aid(store: &Store, bid: BubbleId) -> Option<AtomId> {
    store
        .bubble_bindings(bid)?
        .into_iter()
        .find(|(n, _)| n == SRC)
        .map(|(_, a)| a)
        .filter(|a| store.has_atom(*a))
}

/// Najnowszy bąbel z etykietą, który ma źródło.
pub fn find(store: &Store, label: &str) -> Option<BubbleId> {
    store
        .bubble_ids()
        .into_iter()
        .filter(|b| store.bubble_label(*b).as_deref() == Some(label) && src_aid(store, *b).is_some())
        .max()
}

pub fn read(store: &Store, label: &str) -> Option<Vec<u8>> {
    let bid = find(store, label)?;
    store.atom_payload(src_aid(store, bid)?)
}

/// Zakłada albo nadpisuje bąbel kodu. Bąbel jest korzeniem, więc vacuum
/// nie zbiera źródła. Najnowszy bąbel o tej etykiecie dostaje `src`,
/// gdy już istnieje (także bez źródła).
pub fn write(store: &Store, label: &str, data: &[u8]) -> Result<BubbleId, String> {
    if !is_label(label) {
        return Err(format!("kod: zła etykieta {label}"));
    }
    let bid = match newest(store, label) {
        Some(b) => b,
        None => store.bubble_new(label, None),
    };
    store.set_root(bid);
    if let Some(aid) = src_aid(store, bid) {
        let token = store.atom_value_token(aid).unwrap_or(0);
        if !store.atom_set_guest(aid, token, Some(data.to_vec())) {
            return Err(format!("kod: atom {aid} zniknął"));
        }
        return Ok(bid);
    }
    let aid = store.atom_new(label, "lua", T_INIT);
    store
        .atom_set_guest(aid, 0, Some(data.to_vec()))
        .then_some(())
        .ok_or_else(|| format!("kod: atom {aid} zniknął"))?;
    store.bind(bid, SRC, aid).map_err(|e| e.to_string())?;
    Ok(bid)
}

/// Powiązanie: bąbel `from` wiąże nazwę `to` z atomem `src` biblioteki.
pub fn link(store: &Store, from: &str, to: &str) -> Result<(), String> {
    if !is_label(from) || !is_label(to) {
        return Err("kod: zła etykieta powiązania".into());
    }
    let from_b = newest(store, from).ok_or_else(|| format!("kod: brak bąbla {from}"))?;
    let to_b = find(store, to).ok_or_else(|| format!("kod: brak biblioteki {to}"))?;
    let aid = src_aid(store, to_b).ok_or_else(|| format!("kod: {to} bez źródła"))?;
    store.bind(from_b, to, aid).map_err(|e| e.to_string())
}

/// Źródło modułu widziane z `caller`.
/// Najpierw powiązanie (lookup idzie też do rodziców), potem etykieta
/// na drodze rodzica.
pub fn source_for(store: &Store, caller: BubbleId, name: &str) -> Option<Vec<u8>> {
    if !is_label(name) {
        return None;
    }
    if let Some(aid) = store.lookup(caller, name) {
        if store.atom_se(aid).is_some_and(|(_, e)| e == "lua") {
            return store.atom_payload(aid);
        }
    }
    let mut cur = Some(caller);
    while let Some(id) = cur {
        if store.bubble_label(id).as_deref() == Some(name) {
            if let Some(aid) = src_aid(store, id) {
                return store.atom_payload(aid);
            }
        }
        cur = store.bubble_parent(id).flatten();
    }
    None
}

/// Etykiety bąbli, które mają źródło. Posortowane, bez powtórzeń.
pub fn labels(store: &Store) -> Vec<String> {
    let mut names: Vec<String> = store
        .bubble_ids()
        .into_iter()
        .filter(|b| src_aid(store, *b).is_some())
        .filter_map(|b| store.bubble_label(b))
        .collect();
    names.sort();
    names.dedup();
    names
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn link_and_parent_reach_source() {
        let s = Store::new(true);
        write(&s, "mat", b"return 1").unwrap();
        write(&s, "suma", b"return require('mat')").unwrap();
        let suma = find(&s, "suma").unwrap();
        assert!(source_for(&s, suma, "mat").is_none());
        link(&s, "suma", "mat").unwrap();
        assert_eq!(
            source_for(&s, suma, "mat").as_deref(),
            Some(&b"return 1"[..])
        );

        let mat = find(&s, "mat").unwrap();
        let child = s.bubble_new("dziecko", Some(mat));
        s.set_root(child);
        assert_eq!(
            source_for(&s, child, "mat").as_deref(),
            Some(&b"return 1"[..])
        );
    }

    #[test]
    fn write_overwrites_same_bubble() {
        let s = Store::new(true);
        let a = write(&s, "hej", b"return 1").unwrap();
        let b = write(&s, "hej", b"return 2").unwrap();
        assert_eq!(a, b);
        assert_eq!(read(&s, "hej").as_deref(), Some(&b"return 2"[..]));
        assert_eq!(labels(&s), vec!["hej".to_string()]);
        assert!(is_label("powitanie"));
        assert!(!is_label("bin/x"));
        assert!(!is_label(""));
    }
}
