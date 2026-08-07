//! KarmazynOS substrate — native core (Rust).
//!
//! Prawo jądra: temperatura mówi KIEDY, osiągalność mówi CZY.
//!   zimny+nieosiągalny → GC (vacuum)
//!   zimny+osiągalny    → retained TOMB
//!
//! Język gościa NIE żyje tu — tylko haki C ABI:
//!   env_of(value_token) → bubble_id | 0
//!   extra_reach()       → lista atom_id
//!
//! Python/Lua zostają za szwem (cffi / ctypes). Ten crate = kanon Store.
//!
//! R5 freestanding: [`slab`] → crate `karmazyn_slab` (kentry links same law).
//! Host [`Store`] remains std / HashMap until faza G.

mod atom;
mod store;
mod ffi;
mod snapshot;
pub mod slab;

pub use atom::{
    state_for_t, Atom, AtomId, DECAY_DEFAULT, HEAT_READ, HEAT_WRITE, T_HOT, T_INIT, T_MAX, T_TOMB,
    T_WARM,
};
pub use slab::{
    Bid, BumpAlloc, FixedLabel, SlabAtoms, SlabStore, MAX_ATOMS, MAX_BINDS, MAX_BUBBLES, MAX_LABEL,
    MAX_ROOTS,
};
pub use snapshot::{AtomSnap, BindSnap, BubbleSnap, StoreSnapshot, SNAP_VERSION};
pub use store::{BubbleId, Store, Stats};

/// Crate / ABI version string (NUL-terminated for C).
pub const ABI_VERSION: &str = "0.1.0-karmazyn-substrate\0";

#[cfg(test)]
mod reexport_smoke {
    use super::*;

    #[test]
    fn slab_reexport_rooted_survives_tick() {
        let mut s = SlabStore::new();
        let aid = s.atom_new("x", "y", T_INIT).expect("atom");
        let bid = s.bubble_new(None).expect("bubble");
        assert!(s.bind(bid, "v", aid));
        assert!(s.set_root(bid));
        s.tick();
        assert!(s.has_atom(aid));
        assert_eq!(s.count_atoms(), 1);
    }
}

/// Golden T×reach: same law outcomes on host [`Store`] and freestanding [`SlabStore`].
/// R6 — closes dual-path debt before full freestanding Store (faza G).
#[cfg(test)]
mod golden_txreach {
    use super::*;

    /// Cool until dead under default host decay (~0.92^n).
    const HOST_COOL: u32 = 80;
    /// Slab tests use faster decay for short settle.
    const SLAB_DECAY: f64 = 0.1;
    const SLAB_COOL: u32 = 30;

    #[derive(Debug, PartialEq, Eq)]
    struct LawOut {
        orphan_vacuumed: bool,
        rooted_survives_cold: bool,
        rooted_is_dead: bool,
        after_unset_root_reaped: bool,
    }

    fn run_host() -> LawOut {
        let s = Store::new(true);
        // orphan
        let orphan = s.atom_new("var", "orphan", T_INIT);
        s.settle(HOST_COOL);
        let orphan_vacuumed = !s.has_atom(orphan);

        // root retain
        let root = s.bubble_new("root", None);
        s.set_root(root);
        let keep = s.atom_new("var", "keep", T_INIT);
        s.bind(root, "keep", keep).expect("bind");
        s.settle(HOST_COOL);
        let rooted_survives_cold = s.has_atom(keep);
        let rooted_is_dead = s.atom_is_dead(keep) == Some(true);

        s.unset_root(root);
        s.settle(4);
        let after_unset_root_reaped = !s.has_atom(keep);

        LawOut {
            orphan_vacuumed,
            rooted_survives_cold,
            rooted_is_dead,
            after_unset_root_reaped,
        }
    }

    fn run_slab() -> LawOut {
        let mut s = SlabStore::new();
        s.set_decay(SLAB_DECAY);

        let orphan = s.atom_new("var", "orphan", T_INIT).expect("orphan");
        s.settle(SLAB_COOL);
        let orphan_vacuumed = !s.has_atom(orphan);

        let root = s.bubble_new(None).expect("root");
        assert!(s.set_root(root));
        let keep = s.atom_new("var", "keep", T_INIT).expect("keep");
        assert!(s.bind(root, "keep", keep));
        s.settle(SLAB_COOL);
        let rooted_survives_cold = s.has_atom(keep);
        let rooted_is_dead = s
            .get_t(keep)
            .map(|t| t < T_TOMB)
            .unwrap_or(false)
            || s.is_retained(keep);

        s.unset_root(root);
        s.settle(4);
        let after_unset_root_reaped = !s.has_atom(keep);

        LawOut {
            orphan_vacuumed,
            rooted_survives_cold,
            rooted_is_dead,
            after_unset_root_reaped,
        }
    }

    #[test]
    fn host_and_slab_same_txreach_outcomes() {
        let host = run_host();
        let slab = run_slab();
        assert_eq!(
            host, slab,
            "Store (HashMap) and SlabStore must agree on T×reach law outcomes"
        );
        assert!(host.orphan_vacuumed);
        assert!(host.rooted_survives_cold);
        assert!(host.rooted_is_dead);
        assert!(host.after_unset_root_reaped);
    }
}
