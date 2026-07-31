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
//! R3 freestanding prep: [`slab`] (fixed capacity, bump) — nie zastępuje jeszcze [`Store`].

mod atom;
mod store;
mod ffi;
pub mod slab;

pub use atom::{state_for_t, Atom, AtomId, DECAY_DEFAULT, HEAT_READ, T_HOT, T_INIT, T_MAX, T_TOMB, T_WARM};
pub use slab::{
    BumpAlloc, FixedLabel, SlabAtoms, SlabStore, MAX_ATOMS, MAX_BINDS, MAX_BUBBLES, MAX_LABEL,
    MAX_ROOTS,
};
pub use store::{BubbleId, Store, Stats};

/// Crate / ABI version string (NUL-terminated for C).
pub const ABI_VERSION: &str = "0.1.0-karmazyn-substrate\0";
