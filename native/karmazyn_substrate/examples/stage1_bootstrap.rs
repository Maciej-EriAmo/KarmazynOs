//! Stage 1 bootstrap gate — pure Rust, no Python.
//!
//!   cd native/karmazyn_substrate
//!   cargo run --example stage1_bootstrap --release
//!
//! Covers: Store open, atoms, HOT/WARM/COLD/TOMB, tick+settle, reach-GC, stats.
//! See Documents/BOOTSTRAP_STAGES.pl.md (Stage 1 exit criterion).

use karmazyn_substrate::{
    state_for_t, Store, T_HOT, T_INIT, T_TOMB, T_WARM,
};

fn main() {
    println!("=== KarmazynOS Stage 1 bootstrap ===");
    println!("ABI thresholds: HOT>={T_HOT} WARM>={T_WARM} TOMB>={T_TOMB}");

    let s = Store::new(true);

    // ── temperature FSM labels (T_INIT=50 → WARM; HOT only ≥ T_HOT=70) ─────
    assert_eq!(state_for_t(80.0), "HOT");
    assert_eq!(state_for_t(T_HOT), "HOT");
    assert_eq!(state_for_t(T_INIT), "WARM");
    assert_eq!(state_for_t(T_WARM), "WARM");
    assert_eq!(state_for_t(T_TOMB), "COLD"); // boundary still COLD
    assert_eq!(state_for_t(T_TOMB - 0.01), "TOMB");
    println!("  [ OK ] HOT / WARM / COLD / TOMB labels");

    // ── orphan vacuum (unreachable + cold → GC) ────────────────────────────
    let orphan = s.atom_new("var", "orphan", f64::NAN);
    assert!(s.has_atom(orphan));
    s.settle(80);
    assert!(!s.has_atom(orphan), "orphan must be vacuumed");
    println!("  [ OK ] orphan vacuum (reach-GC)");

    // ── root retains TOMB ──────────────────────────────────────────────────
    let root = s.bubble_new("root", None);
    s.set_root(root);
    let keep = s.atom_new("var", "keep", 50.0);
    s.atom_set_value_token(keep, 42);
    s.bind(root, "keep", keep).expect("bind");
    s.settle(80);
    assert!(s.has_atom(keep), "rooted atom survives");
    assert_eq!(s.atom_is_dead(keep), Some(true), "cooled to TOMB");
    println!("  [ OK ] root retains TOMB");

    // ── heat revives ───────────────────────────────────────────────────────
    assert!(s.heat(keep));
    assert_eq!(s.atom_is_dead(keep), Some(false));
    let t_after = s.get_atom_t(keep).unwrap();
    assert!(t_after >= T_TOMB, "heat must lift T above TOMB");
    println!("  [ OK ] heat revive (T={t_after:.3})");

    // ── tick path (single step) ────────────────────────────────────────────
    let hot = s.atom_new("probe", "tick", T_INIT);
    s.bind(root, "tick", hot).expect("bind tick");
    let t0 = s.get_atom_t(hot).unwrap();
    s.tick();
    let t1 = s.get_atom_t(hot).unwrap();
    assert!(t1 < t0, "tick must decay T");
    println!("  [ OK ] tick decay ({t0:.3} → {t1:.3})");

    // ── unset_root then reap ───────────────────────────────────────────────
    s.unset_root(root);
    s.settle(80);
    assert!(!s.has_atom(keep), "after unset_root, cold atoms reaped");
    assert!(!s.has_atom(hot));
    println!("  [ OK ] unset_root → reap");

    let st = s.stats();
    println!(
        "  stats: total={} hot={} warm={} cold={} tomb={} reaped={} bubbles={}",
        st.total, st.hot, st.warm, st.cold, st.tomb, st.reaped, st.bubbles
    );
    println!("=== STAGE1_OK ===");
}
