//! Re-export freestanding slab from `karmazyn_slab` (R5).
//!
//! Implementation lives in `native/karmazyn_slab` so `boot/kentry` can link
//! the same reach-GC law without pulling host `std` Store.

pub use karmazyn_slab::{
    Bid, BumpAlloc, FixedLabel, SlabAtom, SlabAtoms, SlabBubble, SlabStore, BUMP_HEAP_SIZE,
    MAX_ATOMS, MAX_BINDS, MAX_BUBBLES, MAX_LABEL, MAX_ROOTS,
};
