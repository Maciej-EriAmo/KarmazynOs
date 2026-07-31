//! Fixed-capacity slab + bump — freestanding prep (R3).
//!
//! Works with `std` tests today. Target freestanding (L4 G): same layout,
//! no `HashMap`/`String`. Does **not** replace `Store` yet (Z0: evolve carefully).
//!
//! Limits (gate before G):
//! - MAX_ATOMS / MAX_BUBBLES fixed
//! - labels: fixed `[u8; MAX_LABEL]` (not growable String)
//! - bump region optional for future payloads

#![allow(dead_code)]

use crate::atom::{clamp_t, state_for_t, AtomId, DECAY_DEFAULT, T_INIT, T_TOMB};

/// Hard caps for freestanding / constrained hosts.
pub const MAX_ATOMS: usize = 4096;
pub const MAX_BUBBLES: usize = 1024;
pub const MAX_LABEL: usize = 64;
pub const MAX_ROOTS: usize = 64;
pub const BUMP_HEAP_SIZE: usize = 64 * 1024;

/// Bump allocator over a fixed byte buffer (no free).
pub struct BumpAlloc {
    heap: [u8; BUMP_HEAP_SIZE],
    offset: usize,
}

impl BumpAlloc {
    pub const fn new() -> Self {
        Self {
            heap: [0; BUMP_HEAP_SIZE],
            offset: 0,
        }
    }

    pub fn reset(&mut self) {
        self.offset = 0;
    }

    pub fn used(&self) -> usize {
        self.offset
    }

    pub fn remaining(&self) -> usize {
        BUMP_HEAP_SIZE.saturating_sub(self.offset)
    }

    /// Allocate `size` bytes, 8-byte aligned. None if OOM.
    pub fn alloc(&mut self, size: usize) -> Option<*mut u8> {
        let align = 8usize;
        let start = (self.offset + align - 1) & !(align - 1);
        let end = start.checked_add(size)?;
        if end > BUMP_HEAP_SIZE {
            return None;
        }
        self.offset = end;
        Some(unsafe { self.heap.as_mut_ptr().add(start) })
    }
}

/// Fixed label (S or E field) — freestanding-friendly.
#[derive(Clone, Copy)]
pub struct FixedLabel {
    buf: [u8; MAX_LABEL],
    len: u8,
}

impl FixedLabel {
    pub const fn empty() -> Self {
        Self {
            buf: [0; MAX_LABEL],
            len: 0,
        }
    }

    pub fn from_bytes(src: &[u8]) -> Self {
        let mut out = Self::empty();
        let n = src.len().min(MAX_LABEL);
        out.buf[..n].copy_from_slice(&src[..n]);
        out.len = n as u8;
        out
    }

    pub fn from_str(s: &str) -> Self {
        Self::from_bytes(s.as_bytes())
    }

    pub fn as_bytes(&self) -> &[u8] {
        &self.buf[..self.len as usize]
    }

    pub fn as_str(&self) -> &str {
        core::str::from_utf8(self.as_bytes()).unwrap_or("")
    }
}

#[derive(Clone, Copy)]
pub struct SlabAtom {
    pub used: bool,
    pub s: FixedLabel,
    pub e: FixedLabel,
    pub t: f64,
    pub value_token: u64,
}

impl SlabAtom {
    pub const fn empty() -> Self {
        Self {
            used: false,
            s: FixedLabel::empty(),
            e: FixedLabel::empty(),
            t: 0.0,
            value_token: 0,
        }
    }
}

/// Minimal fixed store: atom_new / heat / decay tick (no reach-GC yet).
/// Reach-GC stays in full `Store` until freestanding port (R5/G).
pub struct SlabAtoms {
    slots: [SlabAtom; MAX_ATOMS],
    next: u32,
    pub reaped: u64,
}

impl SlabAtoms {
    pub fn new() -> Self {
        Self {
            slots: [SlabAtom::empty(); MAX_ATOMS],
            next: 0,
            reaped: 0,
        }
    }

    pub fn atom_new(&mut self, s: &str, e: &str, t: f64) -> Option<AtomId> {
        if (self.next as usize) >= MAX_ATOMS {
            return None;
        }
        let id = self.next;
        self.next = self.next.saturating_add(1);
        let slot = &mut self.slots[id as usize];
        slot.used = true;
        slot.s = FixedLabel::from_str(s);
        slot.e = FixedLabel::from_str(e);
        slot.t = clamp_t(if t.is_nan() { T_INIT } else { t });
        slot.value_token = 0;
        Some(id)
    }

    pub fn has(&self, id: AtomId) -> bool {
        (id as usize) < MAX_ATOMS && self.slots[id as usize].used
    }

    pub fn get_t(&self, id: AtomId) -> Option<f64> {
        if !self.has(id) {
            return None;
        }
        Some(self.slots[id as usize].t)
    }

    pub fn heat(&mut self, id: AtomId, amount: f64) -> bool {
        if !self.has(id) {
            return false;
        }
        let a = &mut self.slots[id as usize];
        a.t = clamp_t(a.t + amount);
        true
    }

    /// Thermal decay only (no reach walk) — freestanding tick MVP.
    pub fn tick_decay(&mut self, rate: f64) {
        let r = if rate < 0.0 { DECAY_DEFAULT } else { rate };
        for slot in self.slots.iter_mut() {
            if !slot.used {
                continue;
            }
            slot.t = clamp_t(slot.t * r);
            if slot.t < T_TOMB {
                // vacuum without reach: drop cold atoms (lab freestanding)
                *slot = SlabAtom::empty();
                self.reaped = self.reaped.saturating_add(1);
            }
        }
    }

    pub fn count_used(&self) -> usize {
        self.slots.iter().filter(|s| s.used).count()
    }

    pub fn state_of(&self, id: AtomId) -> Option<&'static str> {
        self.get_t(id).map(state_for_t)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::atom::{HEAT_READ, T_HOT, T_WARM};

    #[test]
    fn bump_alloc_basic() {
        let mut b = BumpAlloc::new();
        let p1 = b.alloc(16).expect("a");
        let p2 = b.alloc(32).expect("b");
        assert!(p2 as usize >= p1 as usize + 16);
        assert!(b.used() >= 48);
        b.reset();
        assert_eq!(b.used(), 0);
    }

    #[test]
    fn bump_oom() {
        let mut b = BumpAlloc::new();
        assert!(b.alloc(BUMP_HEAP_SIZE + 1).is_none());
    }

    #[test]
    fn fixed_label_truncates() {
        let long = "x".repeat(MAX_LABEL + 20);
        let l = FixedLabel::from_str(&long);
        assert_eq!(l.as_bytes().len(), MAX_LABEL);
    }

    #[test]
    fn slab_atom_new_heat_state() {
        let mut s = SlabAtoms::new();
        let id = s.atom_new("S", "hello", T_INIT).unwrap();
        assert!(s.has(id));
        assert_eq!(s.state_of(id), Some("WARM"));
        s.heat(id, 40.0);
        assert!(s.get_t(id).unwrap() >= T_HOT || s.get_t(id).unwrap() > T_WARM);
        let _ = HEAT_READ;
    }

    #[test]
    fn slab_tick_decay_reaps() {
        let mut s = SlabAtoms::new();
        let id = s.atom_new("a", "b", 5.0).unwrap(); // near TOMB
        for _ in 0..50 {
            s.tick_decay(0.5);
        }
        assert!(!s.has(id) || s.get_t(id).unwrap_or(0.0) < T_TOMB || s.reaped > 0);
        // after enough decay should be reaped
        assert!(s.reaped >= 1 || !s.has(id));
    }

    #[test]
    fn slab_capacity() {
        let mut s = SlabAtoms::new();
        for i in 0..MAX_ATOMS {
            assert!(s.atom_new("s", "e", 50.0).is_some(), "i={i}");
        }
        assert!(s.atom_new("s", "e", 50.0).is_none());
        assert_eq!(s.count_used(), MAX_ATOMS);
    }
}
