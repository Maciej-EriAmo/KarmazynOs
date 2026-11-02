//! Dziennik startu, poleceń i servitorów. Wpis jest atomem powiązanym z
//! bąblem-korzeniem `dziennik`: S = źródło, E = `dziennik`, payload = linia
//! `e<epoka> <UTC> <źródło> <treść>`.
//!
//! Ponad `CAP` wpisów najstarsze powiązanie jest zdejmowane. Atom traci
//! zasięg, stygnie w kolejnych tickach i vacuum go zbiera — rozpad wpisu
//! robi prawo Store, nie dziennik. Wpisy nie budzą autosync (`content_hash`
//! je pomija); na dysk idą razem z najbliższym zapisem świata.

use karmazyn_substrate::{AtomId, BubbleId, Store, T_INIT};
use std::time::{SystemTime, UNIX_EPOCH};

pub const LABEL: &str = "dziennik";
/// E atomu wpisu. `content_hash` po nim rozpoznaje wpisy.
pub const E: &str = "dziennik";
pub const CAP: usize = 200;

/// Najnowszy bąbel `dziennik`. `create` zakłada go jako korzeń.
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

/// Wpisy w kolejności zapisu: (numer, atom).
fn entries(store: &Store, bid: BubbleId) -> Vec<(u64, AtomId)> {
    let mut v: Vec<(u64, AtomId)> = store
        .bubble_bindings(bid)
        .unwrap_or_default()
        .into_iter()
        .filter_map(|(name, aid)| name.parse::<u64>().ok().map(|n| (n, aid)))
        .collect();
    v.sort();
    v
}

pub fn record(store: &Store, epoch: u64, source: &str, message: &str) {
    let Some(bid) = bubble(store, true) else { return };
    let list = entries(store, bid);
    let next = list.last().map_or(1, |(n, _)| n + 1);
    let unix = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let message = message.replace(['\n', '\r'], " ");
    let line = format!("e{epoch} {} {source} {message}", format_utc(unix));
    let aid = store.atom_new(source, E, T_INIT);
    if !store.atom_set_guest(aid, 0, Some(line.into_bytes())) {
        return;
    }
    if store.bind(bid, &format!("{next:08}"), aid).is_err() {
        return;
    }
    let over = (list.len() + 1).saturating_sub(CAP);
    for (n, _) in list.iter().take(over) {
        store.unbind(bid, &format!("{n:08}"));
    }
}

/// Ostatnie `n` wpisów, od najstarszego.
pub fn tail(store: &Store, n: usize) -> Vec<String> {
    let Some(bid) = bubble(store, false) else {
        return Vec::new();
    };
    let list = entries(store, bid);
    let skip = list.len().saturating_sub(n);
    list.into_iter()
        .skip(skip)
        .filter_map(|(_, aid)| store.atom_payload(aid))
        .map(|p| String::from_utf8_lossy(&p).into_owned())
        .collect()
}

pub fn count(store: &Store) -> usize {
    bubble(store, false).map_or(0, |b| entries(store, b).len())
}

/// `YYYY-MM-DDTHH:MM:SSZ` z sekund uniksowych (UTC).
pub fn format_utc(secs: u64) -> String {
    let (y, m, d) = civil_from_days((secs / 86_400) as i64);
    let tod = secs % 86_400;
    format!(
        "{y:04}-{m:02}-{d:02}T{:02}:{:02}:{:02}Z",
        tod / 3600,
        (tod % 3600) / 60,
        tod % 60
    )
}

/// Dni od 1970-01-01 → data. Algorytm Howarda Hinnanta (`civil_from_days`).
fn civil_from_days(z: i64) -> (i32, u32, u32) {
    let z = z + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = (z - era * 146_097) as u64;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe as i64 + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = if m <= 2 { y + 1 } else { y };
    (y as i32, m as u32, d as u32)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn utc_epoch_and_known_instant() {
        assert_eq!(format_utc(0), "1970-01-01T00:00:00Z");
        assert_eq!(format_utc(1_700_000_000), "2023-11-14T22:13:20Z");
        assert_eq!(format_utc(1_582_934_400), "2020-02-29T00:00:00Z");
    }

    #[test]
    fn entries_are_atoms_and_old_ones_fall_to_vacuum() {
        let s = Store::new(true);
        for i in 0..CAP + 3 {
            record(&s, 7, "shell", &format!("n{i}\nz drugą"));
        }
        let all = tail(&s, CAP + 10);
        assert_eq!(all.len(), CAP);
        assert!(all[0].starts_with("e7 ") && all[0].ends_with("shell n3 z drugą"));
        assert!(all.last().unwrap().ends_with(&format!(" n{} z drugą", CAP + 2)));
        assert_eq!(count(&s), CAP);
        // trzy odpięte atomy: bez zasięgu stygną i znikają w vacuum
        let before = s.atom_count();
        assert_eq!(before, CAP + 3);
        s.settle(80);
        assert_eq!(s.atom_count(), CAP);
        assert_eq!(tail(&s, 1).len(), 1);
    }
}
