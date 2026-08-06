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

pub use atom::{state_for_t, Atom, AtomId, DECAY_DEFAULT, HEAT_READ, T_HOT, T_INIT, T_MAX, T_TOMB, T_WARM};
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
