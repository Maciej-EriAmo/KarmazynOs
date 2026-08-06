//! TB.3 / TB.3b — golden: K0 thermal + store_mini reach law ↔ slab.
//!
//! - **TB.3:** `state_code` / decay ↔ `state_for_t` / constants (`thermal.k0`).
//! - **TB.3b:** reach-GC scenarios A–D from `store_mini.k0` ↔ [`crate::SlabStore`]
//!   with the same default decay (`0.92`) and settle counts (`80` / `4`).
//!
//! K0 smoke (`verify_kcc` runs `store_mini` binary, exit 0) proves own-compiler path.
//! These tests prove the **law** matches freestanding slab (stage0 rustc, not kcc).

use crate::SlabStore;

/// K0 `state_code` (3 HOT, 2 WARM, 1 COLD, 0 TOMB) — keep in sync with thermal.k0.
#[inline]
pub fn k0_state_code(t: f64) -> i32 {
    let x = crate::clamp_t(t);
    if x >= crate::T_HOT {
        3
    } else if x >= crate::T_WARM {
        2
    } else if x >= crate::T_TOMB {
        1
    } else {
        0
    }
}

#[inline]
pub fn k0_code_to_name(code: i32) -> &'static str {
    match code {
        3 => "HOT",
        2 => "WARM",
        1 => "COLD",
        _ => "TOMB",
    }
}

/// K0 `decay_once` with default rate.
#[inline]
pub fn k0_tick_t(t: f64) -> f64 {
    crate::clamp_t(t * crate::DECAY_DEFAULT)
}

/// store_mini.k0 `settle(..., 80)` — cool from T_INIT under default decay.
pub const K0_STORE_SETTLE_COOL: u32 = 80;
/// store_mini.k0 after `unset_root` — short settle to reap TOMB.
pub const K0_STORE_SETTLE_REAP: u32 = 4;

/// Fresh slab with **K0 default** decay (not the fast 0.1 used in some unit tests).
fn store_mini_slab() -> SlabStore {
    let mut s = SlabStore::new();
    s.set_decay(crate::DECAY_DEFAULT);
    s
}

/// Scenario A — orphan vacuum (store_mini.k0 lines ~279–286).
pub fn scenario_orphan_vacuum(s: &mut SlabStore) -> bool {
    s.reset();
    s.set_decay(crate::DECAY_DEFAULT);
    let orphan = match s.atom_new("o", "orphan", crate::T_INIT) {
        Some(id) => id,
        None => return false,
    };
    s.settle(K0_STORE_SETTLE_COOL);
    // K0: if used_a[orphan] { return 2; }  → must be gone
    !s.has_atom(orphan)
}

/// Scenario B — root retains dead atom as TOMB (store_mini ~288–306).
/// Returns `(alive_slot, is_dead)` matching K0 checks 7 and 8.
pub fn scenario_root_retains_tomb(s: &mut SlabStore) -> Option<(bool, bool)> {
    s.reset();
    s.set_decay(crate::DECAY_DEFAULT);
    let root = s.bubble_new(None)?;
    if !s.set_root(root) {
        return None;
    }
    let keep = s.atom_new("k", "keep", crate::T_INIT)?;
    if !s.bind(root, "n100", keep) {
        return None;
    }
    s.settle(K0_STORE_SETTLE_COOL);
    let alive = s.has_atom(keep);
    let dead = s.get_t(keep).map(|t| t < crate::T_TOMB).unwrap_or(false);
    Some((alive, dead))
}

/// Scenario C — unset_root then short settle reaps (store_mini ~308–314).
/// Builds B state then unsets root (same sequence as K0 `main`).
pub fn scenario_unset_root_reaps(s: &mut SlabStore) -> Option<bool> {
    s.reset();
    s.set_decay(crate::DECAY_DEFAULT);
    let root = s.bubble_new(None)?;
    if !s.set_root(root) {
        return None;
    }
    let keep = s.atom_new("k", "keep", crate::T_INIT)?;
    if !s.bind(root, "n100", keep) {
        return None;
    }
    s.settle(K0_STORE_SETTLE_COOL);
    if !s.has_atom(keep) {
        return Some(false);
    }
    s.unset_root(root);
    s.settle(K0_STORE_SETTLE_REAP);
    Some(!s.has_atom(keep))
}

/// Scenario D — child is root; bind on child retains after cool (store_mini ~316–332).
pub fn scenario_child_root_retains(s: &mut SlabStore) -> Option<bool> {
    s.reset();
    s.set_decay(crate::DECAY_DEFAULT);
    let p = s.bubble_new(None)?;
    let c = s.bubble_new(Some(p))?;
    let a = s.atom_new("a", "child", crate::T_INIT)?;
    if !s.set_root(c) {
        return None;
    }
    if !s.bind(c, "n1", a) {
        return None;
    }
    s.settle(K0_STORE_SETTLE_COOL);
    Some(s.has_atom(a))
}

/// Packed result codes mirroring store_mini `main` exit codes (0 = all OK).
/// 2=orphan fail, 7=root lost, 8=not dead, 9=unset fail, 10=child fail.
pub fn store_mini_exit_code(s: &mut SlabStore) -> i32 {
    if !scenario_orphan_vacuum(s) {
        return 2;
    }
    match scenario_root_retains_tomb(s) {
        Some((true, true)) => {}
        Some((false, _)) => return 7,
        Some((_, false)) => return 8,
        None => return 5,
    }
    match scenario_unset_root_reaps(s) {
        Some(true) => {}
        Some(false) => return 9,
        None => return 9,
    }
    match scenario_child_root_retains(s) {
        Some(true) => {}
        Some(false) => return 10,
        None => return 11,
    }
    0
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{state_for_t, DECAY_DEFAULT, T_HOT, T_INIT, T_TOMB, T_WARM};

    const SAMPLES: &[f64] = &[
        100.0, 80.0, 70.0, 69.999, 50.0, 30.0, 29.999, 10.0, 2.0, 1.999, 1.0, 0.0, T_INIT,
        T_HOT, T_WARM, T_TOMB,
    ];

    #[test]
    fn k0_state_code_matches_state_for_t() {
        for &t in SAMPLES {
            let code = k0_state_code(t);
            let name = state_for_t(t);
            assert_eq!(
                k0_code_to_name(code),
                name,
                "t={t}: k0 code {code} vs state_for_t={name}"
            );
        }
    }

    #[test]
    fn k0_thresholds_match_slab_consts() {
        assert!((T_HOT - 70.0).abs() < 1e-12);
        assert!((T_WARM - 30.0).abs() < 1e-12);
        assert!((T_TOMB - 2.0).abs() < 1e-12);
        assert!((T_INIT - 50.0).abs() < 1e-12);
        assert!((DECAY_DEFAULT - 0.92).abs() < 1e-12);
    }

    #[test]
    fn k0_tick_decay_matches() {
        let t1 = k0_tick_t(50.0);
        assert!((t1 - 46.0).abs() < 1e-9);
        // 80 ticks from T_INIT → dead (same as host COOL)
        let mut t = T_INIT;
        for _ in 0..80 {
            t = k0_tick_t(t);
        }
        assert!(t < T_TOMB, "after 80 ticks t={t}");
    }

    // ── TB.3b store_mini reach scenarios (default decay, same settle counts) ─

    #[test]
    fn store_mini_a_orphan_vacuum() {
        let mut s = store_mini_slab();
        assert!(
            scenario_orphan_vacuum(&mut s),
            "K0 A: orphan must vacuum after {K0_STORE_SETTLE_COOL} ticks @ 0.92"
        );
        assert!(s.reaped >= 1);
    }

    #[test]
    fn store_mini_b_root_retains_tomb() {
        let mut s = store_mini_slab();
        let (alive, dead) = scenario_root_retains_tomb(&mut s).expect("setup B");
        assert!(alive, "K0 B: rooted atom must keep slot (TOMB)");
        assert!(dead, "K0 B: after cool atom must be dead (t < T_TOMB)");
        // slab marks retained when cold+reachable
        // find keep: only atom left
        assert_eq!(s.count_atoms(), 1);
    }

    #[test]
    fn store_mini_c_unset_root_reaps() {
        let mut s = store_mini_slab();
        assert!(
            scenario_unset_root_reaps(&mut s).unwrap_or(false),
            "K0 C: after unset_root + {K0_STORE_SETTLE_REAP} ticks, TOMB reaped"
        );
    }

    #[test]
    fn store_mini_d_child_root_retains() {
        let mut s = store_mini_slab();
        assert!(
            scenario_child_root_retains(&mut s).unwrap_or(false),
            "K0 D: bind on child-root retains after cool"
        );
    }

    #[test]
    fn store_mini_main_exit_zero() {
        let mut s = store_mini_slab();
        let code = store_mini_exit_code(&mut s);
        assert_eq!(
            code, 0,
            "packed scenarios A–D must match store_mini.k0 main exit 0 (got {code})"
        );
    }
}
