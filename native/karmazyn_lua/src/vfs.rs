//! `karmazyn.fs` w Store: katalog to bąbel, plik to atom z treścią w payload.
//! Dokumenty, nie narzędzia. Kod shella żyje w [`crate::code`].
//!
//! ```text
//! bąbel "fs"            korzeń, bez rodzica
//!   bąbel "<katalog>"   rodzic = fs, też korzeń (reach idzie tylko w górę)
//!     <plik> -> atom    S = nazwa, E = rodzaj, payload = bajty treści
//! ```
//!
//! Payload jest w snapshocie KSUB, więc pliki przechodzą przez `save`/`load`
//! i `sync` na dysk razem z resztą Store.

use karmazyn_substrate::{AtomId, BubbleId, Store, T_INIT};

pub const ROOT_LABEL: &str = "fs";
/// Zostawione dla starych światów. Shell już tu nie szuka narzędzi.
#[allow(dead_code)]
pub const BIN_DIR: &str = "bin";
/// Zostawione dla starych światów. `require` idzie przez [`crate::code`].
pub const LIB_DIR: &str = "lib";

fn root(store: &Store, create: bool) -> Option<BubbleId> {
    let found = store.bubble_ids().into_iter().find(|b| {
        store.bubble_label(*b).as_deref() == Some(ROOT_LABEL)
            && store.bubble_parent(*b) == Some(None)
            && store.is_root(*b)
    });
    match found {
        Some(b) => Some(b),
        None if create => {
            let b = store.bubble_new(ROOT_LABEL, None);
            store.set_root(b);
            Some(b)
        }
        None => None,
    }
}

fn dirs_under(store: &Store, root: BubbleId) -> Vec<(String, BubbleId)> {
    let mut out: Vec<(String, BubbleId)> = store
        .bubble_ids()
        .into_iter()
        .filter(|b| store.bubble_parent(*b) == Some(Some(root)))
        .filter_map(|b| store.bubble_label(b).map(|l| (l, b)))
        .collect();
    out.sort();
    out
}

fn dir(store: &Store, name: &str, create: bool) -> Option<BubbleId> {
    let r = root(store, create)?;
    if let Some((_, b)) = dirs_under(store, r).into_iter().find(|(l, _)| l == name) {
        return Some(b);
    }
    if !create {
        return None;
    }
    let b = store.bubble_new(name, Some(r));
    store.set_root(b);
    Some(b)
}

fn file(store: &Store, d: &str, f: &str) -> Option<AtomId> {
    let b = dir(store, d, false)?;
    store.lookup(b, f).filter(|a| store.has_atom(*a))
}

/// Treść pliku. Odczyt grzeje atom (lookup), jak każdy odczyt w Store.
pub fn read(store: &Store, d: &str, f: &str) -> Option<Vec<u8>> {
    let a = file(store, d, f)?;
    Some(store.atom_payload(a).unwrap_or_default())
}

pub fn write(store: &Store, d: &str, f: &str, kind: &str, data: &[u8]) -> Result<(), String> {
    let b = dir(store, d, true).ok_or("fs: brak katalogu")?;
    let a = match store.lookup(b, f).filter(|a| store.has_atom(*a)) {
        Some(a) => a,
        None => {
            let a = store.atom_new(f, kind, T_INIT);
            store.bind(b, f, a).map_err(|e| e.to_string())?;
            a
        }
    };
    let token = store.atom_value_token(a).unwrap_or(0);
    if store.atom_set_guest(a, token, Some(data.to_vec())) {
        Ok(())
    } else {
        Err(format!("fs: atom {a} zniknął"))
    }
}

/// Nazwy katalogów.
pub fn dirs(store: &Store) -> Vec<String> {
    match root(store, false) {
        Some(r) => dirs_under(store, r).into_iter().map(|(l, _)| l).collect(),
        None => Vec::new(),
    }
}

/// Nazwy plików w katalogu (posortowane). Pusty, gdy katalogu nie ma.
pub fn files(store: &Store, d: &str) -> Vec<String> {
    let Some(b) = dir(store, d, false) else {
        return Vec::new();
    };
    let mut out: Vec<String> = store
        .bubble_bindings(b)
        .unwrap_or_default()
        .into_iter()
        .filter(|(_, a)| store.has_atom(*a))
        .map(|(n, _)| n)
        .collect();
    out.sort();
    out
}

pub fn delete(store: &Store, d: &str, f: &str) -> bool {
    let Some(b) = dir(store, d, false) else {
        return false;
    };
    match store.unbind(b, f) {
        Some(a) => {
            store.delete_atom(a);
            true
        }
        None => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn write_read_overwrite_list_delete() {
        let s = Store::new(true);
        assert_eq!(read(&s, "dev", "a"), None);
        write(&s, "dev", "a", "lua", b"return 1").unwrap();
        write(&s, "dev", "b", "txt", b"\xffbin\0").unwrap();
        write(&s, "dev", "a", "lua", b"return 2").unwrap();
        assert_eq!(read(&s, "dev", "a").as_deref(), Some(&b"return 2"[..]));
        assert_eq!(read(&s, "dev", "b").as_deref(), Some(&b"\xffbin\0"[..]));
        assert_eq!(files(&s, "dev"), vec!["a", "b"]);
        assert_eq!(dirs(&s), vec!["dev"]);
        assert!(delete(&s, "dev", "a"));
        assert!(!delete(&s, "dev", "a"));
        assert_eq!(files(&s, "dev"), vec!["b"]);
    }

    #[test]
    fn files_survive_ticks_and_snapshot() {
        let s = Store::new(true);
        write(&s, BIN_DIR, "hello", "lua", b"return 'hej'").unwrap();
        s.settle(500);
        assert_eq!(read(&s, BIN_DIR, "hello").as_deref(), Some(&b"return 'hej'"[..]));

        let text = s.export_snapshot().to_text();
        let s2 = Store::new(true);
        s2.import_snapshot(&karmazyn_substrate::StoreSnapshot::from_text(&text).unwrap());
        assert_eq!(read(&s2, BIN_DIR, "hello").as_deref(), Some(&b"return 'hej'"[..]));
        assert_eq!(dirs(&s2), vec![BIN_DIR.to_string()]);
    }
}
