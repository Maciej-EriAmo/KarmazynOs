//! Usługi: bąble kodu wykonywane przez gościa Lua w tym procesie. Nie ma
//! osobnych procesów ani własnej maszyny stanów — rządzi prawo substratu.
//!
//! - **reach = czy.** Bąbel-korzeń `uslugi` wiąże nazwę usługi z atomem `src`
//!   jej bąbla kodu. Powiązanie znaczy „ma żyć”; `usluga down` je zdejmuje.
//! - **T = kiedy.** W każdej epoce, po `tick`, usługa robi jeden krok, gdy jej
//!   `src` jest HOT albo WARM. Udany krok grzeje `src` (odczyt). Błąd nie
//!   grzeje, więc usługa, która pada, stygnie: po kilku epokach jest COLD i
//!   nie wstaje, dalej schodzi do TOMB. `usluga up` przywraca T_INIT.
//! - Chunk, który zwróci `false`, skończył pracę: powiązanie znika.

use karmazyn_lua::Evaluator as LuaEvaluator;
use karmazyn_substrate::{state_for_t, AtomId, BubbleId, Store, T_INIT};

pub const LABEL: &str = "uslugi";

fn bubble(store: &Store, create: bool) -> Option<BubbleId> {
    let found = store
        .bubble_ids()
        .into_iter()
        .filter(|b| store.bubble_label(*b).as_deref() == Some(LABEL))
        .max();
    match found {
        Some(b) => Some(b),
        None if create => {
            let b = store.bubble_new(LABEL, None);
            store.set_root(b);
            Some(b)
        }
        None => None,
    }
}

fn bound(store: &Store) -> Vec<(String, AtomId)> {
    let Some(bid) = bubble(store, false) else {
        return Vec::new();
    };
    let mut v = store.bubble_bindings(bid).unwrap_or_default();
    v.sort();
    v
}

pub fn up(store: &Store, lua: &LuaEvaluator, label: &str) -> Result<String, String> {
    if !LuaEvaluator::code_label(label) {
        return Err("usage: usluga up <etykieta>".into());
    }
    let src = lua
        .code_src(store, label)
        .ok_or_else(|| format!("usługa: brak bąbla kodu {label}"))?;
    let bid = bubble(store, true).expect("bąbel uslugi");
    store.bind(bid, label, src).map_err(|e| e.to_string())?;
    store.atom_set_t(src, T_INIT);
    Ok(format!("{label}: w zasięgu, T={T_INIT}"))
}

pub fn down(store: &Store, label: &str) -> Result<String, String> {
    let bid = bubble(store, false).ok_or_else(|| format!("usługa: {label} nie jest usługą"))?;
    store
        .unbind(bid, label)
        .map(|_| format!("{label}: poza zasięgiem"))
        .ok_or_else(|| format!("usługa: {label} nie jest usługą"))
}

/// `  STAN  T  etykieta` dla każdej usługi.
pub fn list(store: &Store) -> Vec<String> {
    bound(store)
        .into_iter()
        .map(|(name, aid)| match store.get_atom_t(aid) {
            Some(t) => format!("  {:<4}  {t:>5.1}  {name}", state_for_t(t)),
            None => format!("  ----   ----  {name} (źródło zniknęło)"),
        })
        .collect()
}

pub fn count(store: &Store) -> usize {
    bound(store).len()
}

/// Jeden krok wszystkich usług w tej epoce. Zwraca (usługa, notatka) do
/// dziennika: wypisane linie, błędy i koniec pracy.
pub fn step(store: &Store, lua: &LuaEvaluator) -> Vec<(String, String)> {
    let mut notes = Vec::new();
    let Some(bid) = bubble(store, false) else {
        return notes;
    };
    for (name, aid) in bound(store) {
        let Some(t) = store.get_atom_t(aid) else {
            store.unbind(bid, &name);
            notes.push((name, "źródło zniknęło, poza zasięgiem".into()));
            continue;
        };
        if !matches!(state_for_t(t), "HOT" | "WARM") {
            continue;
        }
        match lua.run_service(store, &name) {
            Ok((more, out)) => {
                if !out.is_empty() {
                    notes.push((name.clone(), out));
                }
                if more {
                    store.heat(aid);
                } else {
                    store.unbind(bid, &name);
                    notes.push((name, "skończyła, poza zasięgiem".into()));
                }
            }
            Err(e) => {
                let first = e.lines().next().unwrap_or("").trim();
                notes.push((name, format!("błąd: {first}")));
            }
        }
    }
    notes
}

#[cfg(test)]
mod tests {
    use super::*;
    use karmazyn_substrate::T_HOT;

    fn epoch(s: &Store, lua: &LuaEvaluator) -> Vec<(String, String)> {
        s.tick();
        step(s, lua)
    }

    #[test]
    fn healthy_service_stays_hot() {
        let s = Store::new(true);
        let lua = LuaEvaluator::new(&s);
        lua.code_write(&s, "licz", b"n = (n or 0) + 1").unwrap();
        up(&s, &lua, "licz").unwrap();
        for _ in 0..30 {
            assert!(epoch(&s, &lua).is_empty());
        }
        assert_eq!(lua.eval_line(&s, "return n"), "30");
        let t = s.get_atom_t(lua.code_src(&s, "licz").unwrap()).unwrap();
        assert!(t >= T_HOT, "T={t}");
    }

    #[test]
    fn failing_service_cools_by_store_law() {
        let s = Store::new(true);
        let lua = LuaEvaluator::new(&s);
        lua.code_write(&s, "pada", b"proby = (proby or 0) + 1 error('nie')").unwrap();
        up(&s, &lua, "pada").unwrap();
        let mut errors = 0;
        for _ in 0..60 {
            errors += epoch(&s, &lua).len();
        }
        // stygnie z T_INIT do COLD w kilka epok, potem już nie wstaje
        assert!((1..15).contains(&errors), "errors={errors}");
        assert_eq!(lua.eval_line(&s, "return proby"), errors.to_string());
        assert!(list(&s)[0].contains("TOMB"), "{:?}", list(&s));

        // up przywraca T_INIT i usługa znów próbuje
        up(&s, &lua, "pada").unwrap();
        assert_eq!(epoch(&s, &lua).len(), 1);
    }

    #[test]
    fn finishing_and_down_leave_reach() {
        let s = Store::new(true);
        let lua = LuaEvaluator::new(&s);
        lua.code_write(&s, "raz", b"print('zrobione') return false").unwrap();
        lua.code_write(&s, "stoi", b"return true").unwrap();
        up(&s, &lua, "raz").unwrap();
        up(&s, &lua, "stoi").unwrap();
        let notes = epoch(&s, &lua);
        assert_eq!(
            notes,
            vec![
                ("raz".to_string(), "zrobione".to_string()),
                ("raz".to_string(), "skończyła, poza zasięgiem".to_string()),
            ]
        );
        assert_eq!(count(&s), 1);
        down(&s, "stoi").unwrap();
        assert_eq!(count(&s), 0);
        assert!(down(&s, "stoi").is_err());
        assert!(up(&s, &lua, "brak").is_err());
        // bąbel kodu zostaje: usługa to tylko powiązanie
        assert!(lua.code_src(&s, "stoi").is_some());
    }
}
