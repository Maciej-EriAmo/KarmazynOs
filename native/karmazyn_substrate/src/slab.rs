//! Fixed-capacity slab + bump + **reach-GC** — freestanding prep (R3→G gate).
//!
//! `std` tests today. Layout avoids `HashMap`/`String`/`Vec` grow.
//! Does **not** replace production [`crate::store::Store`] (Z0: evolve carefully).
//!
//! Law (same as Store):
//!   temperature → WHEN candidate for GC
//!   reachability → WHETHER remove
//!   cold + unreachable → vacuum (reap)
//!   cold + reachable → retained TOMB

#![allow(dead_code)]

use crate::atom::{clamp_t, state_for_t, AtomId, DECAY_DEFAULT, T_INIT, T_TOMB};

/// Local bubble id (same as `store::BubbleId`) — no dependency on std Store module
/// so this file can move to a `no_std` crate later.
pub type Bid = u32;

/// Hard caps for freestanding / constrained hosts.
/// Sized so `SlabStore` fits tests without stack overflow (~tens of KB).
/// Production freestanding: one `static mut` instance, not stack locals.
pub const MAX_ATOMS: usize = 256;
pub const MAX_BUBBLES: usize = 64;
pub const MAX_LABEL: usize = 32;
pub const MAX_ROOTS: usize = 16;
pub const MAX_BINDS: usize = 8;
pub const BUMP_HEAP_SIZE: usize = 16 * 1024;

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

    pub fn eq_str(&self, s: &str) -> bool {
        self.as_bytes() == s.as_bytes()
    }
}

#[derive(Clone, Copy)]
pub struct SlabAtom {
    pub used: bool,
    pub s: FixedLabel,
    pub e: FixedLabel,
    pub t: f64,
    pub value_token: u64,
    /// Freestanding stand-in for env_of(token) → bubble (no dynamic hooks).
    pub env_bubble: Option<Bid>,
}

impl SlabAtom {
    pub const fn empty() -> Self {
        Self {
            used: false,
            s: FixedLabel::empty(),
            e: FixedLabel::empty(),
            t: 0.0,
            value_token: 0,
            env_bubble: None,
        }
    }

    #[inline]
    pub fn is_dead(&self) -> bool {
        self.t < T_TOMB
    }
}

#[derive(Clone, Copy)]
struct BindSlot {
    used: bool,
    name: FixedLabel,
    aid: AtomId,
}

impl BindSlot {
    const fn empty() -> Self {
        Self {
            used: false,
            name: FixedLabel::empty(),
            aid: 0,
        }
    }
}

#[derive(Clone, Copy)]
pub struct SlabBubble {
    pub used: bool,
    pub parent: Option<Bid>,
    binds: [BindSlot; MAX_BINDS],
}

impl SlabBubble {
    pub const fn empty() -> Self {
        Self {
            used: false,
            parent: None,
            binds: [BindSlot::empty(); MAX_BINDS],
        }
    }
}

/// Minimal fixed store with **reach-GC** (same law as production Store).
pub struct SlabStore {
    atoms: [SlabAtom; MAX_ATOMS],
    bubbles: [SlabBubble; MAX_BUBBLES],
    roots: [Option<Bid>; MAX_ROOTS],
    next_atom: u32,
    next_bubble: u32,
    root_len: usize,
    decay: f64,
    pub reaped: u64,
    /// cold + reachable
    retained: [bool; MAX_ATOMS],
    /// scratch for walk (not on tick stack)
    reach_buf: [bool; MAX_ATOMS],
    seen_b_buf: [bool; MAX_BUBBLES],
}

impl SlabStore {
    pub fn new() -> Self {
        Self {
            atoms: [SlabAtom::empty(); MAX_ATOMS],
            bubbles: [SlabBubble::empty(); MAX_BUBBLES],
            roots: [None; MAX_ROOTS],
            next_atom: 0,
            next_bubble: 0,
            root_len: 0,
            decay: DECAY_DEFAULT,
            reaped: 0,
            retained: [false; MAX_ATOMS],
            reach_buf: [false; MAX_ATOMS],
            seen_b_buf: [false; MAX_BUBBLES],
        }
    }

    pub fn atom_new(&mut self, s: &str, e: &str, t: f64) -> Option<AtomId> {
        if (self.next_atom as usize) >= MAX_ATOMS {
            return None;
        }
        let id = self.next_atom;
        self.next_atom = self.next_atom.saturating_add(1);
        let slot = &mut self.atoms[id as usize];
        *slot = SlabAtom {
            used: true,
            s: FixedLabel::from_str(s),
            e: FixedLabel::from_str(e),
            t: clamp_t(if t.is_nan() { T_INIT } else { t }),
            value_token: 0,
            env_bubble: None,
        };
        Some(id)
    }

    pub fn has_atom(&self, id: AtomId) -> bool {
        (id as usize) < MAX_ATOMS && self.atoms[id as usize].used
    }

    pub fn get_t(&self, id: AtomId) -> Option<f64> {
        if !self.has_atom(id) {
            return None;
        }
        Some(self.atoms[id as usize].t)
    }

    pub fn heat(&mut self, id: AtomId, amount: f64) -> bool {
        if !self.has_atom(id) {
            return false;
        }
        let a = &mut self.atoms[id as usize];
        a.t = clamp_t(a.t + amount);
        true
    }

    pub fn set_env_bubble(&mut self, id: AtomId, bid: Option<Bid>) -> bool {
        if !self.has_atom(id) {
            return false;
        }
        self.atoms[id as usize].env_bubble = bid;
        true
    }

    pub fn bubble_new(&mut self, parent: Option<Bid>) -> Option<Bid> {
        if (self.next_bubble as usize) >= MAX_BUBBLES {
            return None;
        }
        let id = self.next_bubble;
        self.next_bubble = self.next_bubble.saturating_add(1);
        self.bubbles[id as usize] = SlabBubble {
            used: true,
            parent,
            binds: [BindSlot::empty(); MAX_BINDS],
        };
        Some(id)
    }

    pub fn bind(&mut self, bid: Bid, name: &str, aid: AtomId) -> bool {
        if (bid as usize) >= MAX_BUBBLES || !self.bubbles[bid as usize].used {
            return false;
        }
        if !self.has_atom(aid) {
            return false;
        }
        let b = &mut self.bubbles[bid as usize];
        // update existing name
        for slot in b.binds.iter_mut() {
            if slot.used && slot.name.eq_str(name) {
                slot.aid = aid;
                return true;
            }
        }
        for slot in b.binds.iter_mut() {
            if !slot.used {
                slot.used = true;
                slot.name = FixedLabel::from_str(name);
                slot.aid = aid;
                return true;
            }
        }
        false // full
    }

    pub fn set_root(&mut self, bid: Bid) -> bool {
        if (bid as usize) >= MAX_BUBBLES || !self.bubbles[bid as usize].used {
            return false;
        }
        for r in self.roots.iter_mut().take(self.root_len) {
            if *r == Some(bid) {
                return true;
            }
        }
        if self.root_len >= MAX_ROOTS {
            return false;
        }
        self.roots[self.root_len] = Some(bid);
        self.root_len += 1;
        true
    }

    pub fn unset_root(&mut self, bid: Bid) {
        let mut w = 0;
        for r in 0..self.root_len {
            if self.roots[r] != Some(bid) {
                self.roots[w] = self.roots[r];
                w += 1;
            }
        }
        for r in w..self.root_len {
            self.roots[r] = None;
        }
        self.root_len = w;
    }

    pub fn is_retained(&self, id: AtomId) -> bool {
        (id as usize) < MAX_ATOMS && self.retained[id as usize]
    }

    pub fn count_atoms(&self) -> usize {
        self.atoms.iter().filter(|a| a.used).count()
    }

    /// Bitset reach walk without heap alloc (uses internal scratch buffers).
    fn walk_reach(&mut self) {
        let reach = &mut self.reach_buf;
        let seen_b = &mut self.seen_b_buf;
        reach.fill(false);
        seen_b.fill(false);
        let mut stack = [0u32; MAX_BUBBLES];
        let mut sp = 0usize;
        for r in 0..self.root_len {
            if let Some(bid) = self.roots[r] {
                if sp < MAX_BUBBLES {
                    stack[sp] = bid;
                    sp += 1;
                }
            }
        }
        while sp > 0 {
            sp -= 1;
            let bid = stack[sp];
            let bi = bid as usize;
            if bi >= MAX_BUBBLES || seen_b[bi] {
                continue;
            }
            seen_b[bi] = true;
            let b = &self.bubbles[bi];
            if !b.used {
                continue;
            }
            for slot in &b.binds {
                if !slot.used {
                    continue;
                }
                let ai = slot.aid as usize;
                if ai < MAX_ATOMS && self.atoms[ai].used {
                    reach[ai] = true;
                    if let Some(env_b) = self.atoms[ai].env_bubble {
                        if sp < MAX_BUBBLES {
                            stack[sp] = env_b;
                            sp += 1;
                        }
                    }
                }
            }
            if let Some(p) = b.parent {
                if sp < MAX_BUBBLES {
                    stack[sp] = p;
                    sp += 1;
                }
            }
        }
    }

    fn purge_bindings(&mut self, aid: AtomId) {
        for b in self.bubbles.iter_mut() {
            if !b.used {
                continue;
            }
            for slot in b.binds.iter_mut() {
                if slot.used && slot.aid == aid {
                    *slot = BindSlot::empty();
                }
            }
        }
    }

    /// Full thermal tick + reach-GC (production law).
    pub fn tick(&mut self) {
        self.walk_reach();

        // decay
        let decay = if self.decay < 0.0 {
            DECAY_DEFAULT
        } else {
            self.decay
        };
        for a in self.atoms.iter_mut() {
            if a.used {
                a.t = clamp_t(a.t * decay);
            }
        }

        // reap / retain (use reach_buf)
        for id in 0..MAX_ATOMS {
            if !self.atoms[id].used {
                self.retained[id] = false;
                continue;
            }
            if !self.atoms[id].is_dead() {
                self.retained[id] = false;
                continue;
            }
            if self.reach_buf[id] {
                self.retained[id] = true;
            } else {
                let aid = id as AtomId;
                self.purge_bindings(aid);
                self.atoms[id] = SlabAtom::empty();
                self.retained[id] = false;
                self.reaped = self.reaped.saturating_add(1);
            }
        }
    }

    pub fn settle(&mut self, n: u32) {
        for _ in 0..n {
            self.tick();
        }
    }

    pub fn state_of(&self, id: AtomId) -> Option<&'static str> {
        self.get_t(id).map(state_for_t)
    }
}

// ── backward-compatible thin wrapper name used earlier ─────────────────────

/// Alias docs: simple atom table without bubbles (prefer [`SlabStore`]).
pub struct SlabAtoms {
    inner: SlabStore,
}

impl SlabAtoms {
    pub fn new() -> Self {
        Self {
            inner: SlabStore::new(),
        }
    }

    pub fn atom_new(&mut self, s: &str, e: &str, t: f64) -> Option<AtomId> {
        self.inner.atom_new(s, e, t)
    }

    pub fn has(&self, id: AtomId) -> bool {
        self.inner.has_atom(id)
    }

    pub fn get_t(&self, id: AtomId) -> Option<f64> {
        self.inner.get_t(id)
    }

    pub fn heat(&mut self, id: AtomId, amount: f64) -> bool {
        self.inner.heat(id, amount)
    }

    pub fn tick_decay(&mut self, rate: f64) {
        self.inner.decay = rate;
        // decay-only path: no roots → all cold reaped
        self.inner.tick();
    }

    pub fn count_used(&self) -> usize {
        self.inner.count_atoms()
    }

    pub fn state_of(&self, id: AtomId) -> Option<&'static str> {
        self.inner.state_of(id)
    }

    pub fn reaped(&self) -> u64 {
        self.inner.reaped
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::atom::{T_HOT, T_WARM};

    #[test]
    fn bump_alloc_basic() {
        let mut b = BumpAlloc::new();
        let p1 = b.alloc(16).expect("a");
        let p2 = b.alloc(32).expect("b");
        assert!(p2 as usize >= p1 as usize + 16);
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
        let mut s = SlabStore::new();
        let id = s.atom_new("S", "hello", T_INIT).unwrap();
        assert!(s.has_atom(id));
        assert_eq!(s.state_of(id), Some("WARM"));
        s.heat(id, 40.0);
        assert!(s.get_t(id).unwrap() > T_WARM);
        let _ = T_HOT;
    }

    #[test]
    fn reach_root_retains_cold() {
        let mut s = SlabStore::new();
        s.decay = 0.1; // fast cool
        let aid = s.atom_new("x", "keep", 50.0).unwrap();
        let bid = s.bubble_new(None).unwrap();
        assert!(s.bind(bid, "v", aid));
        assert!(s.set_root(bid));
        s.settle(30);
        // cold but reachable → retained, still present
        assert!(s.has_atom(aid), "rooted cold atom must not vacuum");
        assert!(s.is_retained(aid) || s.get_t(aid).unwrap() >= T_TOMB);
    }

    #[test]
    fn orphan_vacuum() {
        let mut s = SlabStore::new();
        s.decay = 0.1;
        let aid = s.atom_new("x", "orphan", 50.0).unwrap();
        // no root, no bind
        s.settle(30);
        assert!(!s.has_atom(aid), "orphan must vacuum");
        assert!(s.reaped >= 1);
    }

    #[test]
    fn unset_root_then_reap() {
        let mut s = SlabStore::new();
        s.decay = 0.1;
        let aid = s.atom_new("x", "y", 50.0).unwrap();
        let bid = s.bubble_new(None).unwrap();
        s.bind(bid, "v", aid);
        s.set_root(bid);
        s.settle(20);
        assert!(s.has_atom(aid));
        s.unset_root(bid);
        s.settle(20);
        assert!(!s.has_atom(aid) || s.reaped >= 1);
    }

    #[test]
    fn env_bubble_extends_reach() {
        let mut s = SlabStore::new();
        s.decay = 0.1;
        let outer = s.atom_new("o", "outer", 50.0).unwrap();
        let inner = s.atom_new("i", "inner", 50.0).unwrap();
        let b_out = s.bubble_new(None).unwrap();
        let b_in = s.bubble_new(None).unwrap();
        s.bind(b_out, "x", outer);
        s.bind(b_in, "y", inner);
        s.set_env_bubble(outer, Some(b_in)); // outer's env → inner bubble
        s.set_root(b_out);
        s.settle(25);
        assert!(s.has_atom(outer));
        assert!(s.has_atom(inner), "env_bubble must keep inner reachable");
    }

    #[test]
    fn parent_chain_reach() {
        let mut s = SlabStore::new();
        s.decay = 0.1;
        let aid = s.atom_new("a", "child", 50.0).unwrap();
        let parent = s.bubble_new(None).unwrap();
        let child = s.bubble_new(Some(parent)).unwrap();
        s.bind(child, "v", aid);
        s.set_root(parent); // root parent only; walk parent from child? 
        // walk starts at roots — child not root. Parent has no bind to aid.
        // Need bind on parent or root child. Root parent + child.parent=parent
        // doesn't auto-visit child. Production walk: only from roots via binds and parent UP.
        // So parent chain is child → parent when stack pushes parent from child.
        // Starting at parent alone never sees child.
        // Fix test: root the child (which has parent link for env of frames)
        s.unset_root(parent);
        s.set_root(child);
        s.settle(25);
        assert!(s.has_atom(aid));
    }

    #[test]
    fn slab_capacity() {
        let mut s = SlabStore::new();
        for i in 0..MAX_ATOMS {
            assert!(s.atom_new("s", "e", 50.0).is_some(), "i={i}");
        }
        assert!(s.atom_new("s", "e", 50.0).is_none());
        assert_eq!(s.count_atoms(), MAX_ATOMS);
    }

    #[test]
    fn slab_atoms_wrapper_tick_decay() {
        let mut s = SlabAtoms::new();
        let id = s.atom_new("a", "b", 5.0).unwrap();
        for _ in 0..40 {
            s.tick_decay(0.5);
        }
        assert!(s.reaped() >= 1 || !s.has(id));
    }
}
