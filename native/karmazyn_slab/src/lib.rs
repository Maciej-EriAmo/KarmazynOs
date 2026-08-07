//! Fixed-capacity slab + bump + **reach-GC** — freestanding `no_std` (R5).
//!
//! Shared by:
//! - `karmazyn_substrate` (host tests / re-export)
//! - `boot/kentry` (static mut demo: atom / tick / stats)
//!
//! Layout avoids `HashMap` / `String` / growable `Vec`.
//! Does **not** replace production host `Store` (Z0: evolve carefully).
//!
//! Law:
//!   temperature → WHEN candidate for GC
//!   reachability → WHETHER remove
//!   cold + unreachable → vacuum (reap)
//!   cold + reachable → retained TOMB

#![no_std]

#[cfg(test)]
mod golden_k0;

// ── thermal / id primitives (no String — host Atom stays in substrate) ─────

pub const T_INIT: f64 = 50.0;
pub const T_MAX: f64 = 100.0;
pub const T_HOT: f64 = 70.0;
pub const T_WARM: f64 = 30.0;
pub const T_TOMB: f64 = 2.0;
pub const DECAY_DEFAULT: f64 = 0.92;
/// ΔT on read / explicit heat (touch) — larger than write.
pub const HEAT_READ: f64 = 10.0;
/// ΔT on write (value token / mutation) — smaller than read (mirrors karmazyn_atom.py).
pub const HEAT_WRITE: f64 = 5.0;

pub type AtomId = u32;
/// Local bubble id (same role as host `BubbleId`).
pub type Bid = u32;

#[inline]
pub const fn clamp_t(t: f64) -> f64 {
    if t < 0.0 {
        0.0
    } else if t > T_MAX {
        T_MAX
    } else {
        t
    }
}

/// HOT / WARM / COLD / TOMB — single source of truth for T classification.
#[inline]
pub fn state_for_t(t: f64) -> &'static str {
    if t >= T_HOT {
        "HOT"
    } else if t >= T_WARM {
        "WARM"
    } else if t >= T_TOMB {
        "COLD"
    } else {
        "TOMB"
    }
}

// ── hard caps ──────────────────────────────────────────────────────────────

/// Sized so `SlabStore` fits tests without stack overflow (~tens of KB).
/// Freestanding: one `static mut` instance, not stack locals.
pub const MAX_ATOMS: usize = 256;
pub const MAX_BUBBLES: usize = 64;
pub const MAX_LABEL: usize = 32;
pub const MAX_ROOTS: usize = 16;
pub const MAX_BINDS: usize = 8;
pub const BUMP_HEAP_SIZE: usize = 16 * 1024;

// ── bump ───────────────────────────────────────────────────────────────────

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

// ── labels / atoms / bubbles ───────────────────────────────────────────────

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

// ── SlabStore ──────────────────────────────────────────────────────────────

/// Minimal fixed store with **reach-GC** (same law as production Store).
///
/// Slot allocation: **scan free** (`used == false`). Monotonic `next_*` was
/// wrong after vacuum — full table + reaps left no way to allocate again.
pub struct SlabStore {
    atoms: [SlabAtom; MAX_ATOMS],
    bubbles: [SlabBubble; MAX_BUBBLES],
    roots: [Option<Bid>; MAX_ROOTS],
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
    /// Const constructor for `static mut` freestanding instances.
    pub const fn new() -> Self {
        Self {
            atoms: [SlabAtom::empty(); MAX_ATOMS],
            bubbles: [SlabBubble::empty(); MAX_BUBBLES],
            roots: [None; MAX_ROOTS],
            root_len: 0,
            decay: DECAY_DEFAULT,
            reaped: 0,
            retained: [false; MAX_ATOMS],
            reach_buf: [false; MAX_ATOMS],
            seen_b_buf: [false; MAX_BUBBLES],
        }
    }

    /// Full wipe (demo / freestanding restart). BSS-sized; not for hot path.
    pub fn reset(&mut self) {
        *self = Self::new();
    }

    pub fn set_decay(&mut self, decay: f64) {
        self.decay = if !(decay > 0.0) {
            // NaN, ≤0 → default
            DECAY_DEFAULT
        } else {
            decay
        };
    }

    pub fn decay(&self) -> f64 {
        self.decay
    }

    /// First free atom slot, or `None` if table full.
    fn alloc_atom_slot(&self) -> Option<usize> {
        for i in 0..MAX_ATOMS {
            if !self.atoms[i].used {
                return Some(i);
            }
        }
        None
    }

    /// First free bubble slot, or `None` if table full.
    /// Note: bubbles are not auto-vacuumed (only atoms); freelist helps if
    /// caller uses [`Self::bubble_drop`] or `reset`.
    fn alloc_bubble_slot(&self) -> Option<usize> {
        for i in 0..MAX_BUBBLES {
            if !self.bubbles[i].used {
                return Some(i);
            }
        }
        None
    }

    pub fn atom_new(&mut self, s: &str, e: &str, t: f64) -> Option<AtomId> {
        let id = self.alloc_atom_slot()? as AtomId;
        let t = if t.is_nan() { T_INIT } else { t };
        self.atoms[id as usize] = SlabAtom {
            used: true,
            s: FixedLabel::from_str(s),
            e: FixedLabel::from_str(e),
            t: clamp_t(t),
            value_token: 0,
            env_bubble: None,
        };
        self.retained[id as usize] = false;
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
        let amount = if amount.is_nan() || amount < 0.0 {
            0.0
        } else {
            amount
        };
        let a = &mut self.atoms[id as usize];
        a.t = clamp_t(a.t + amount);
        true
    }

    pub fn set_env_bubble(&mut self, id: AtomId, bid: Option<Bid>) -> bool {
        if !self.has_atom(id) {
            return false;
        }
        if let Some(b) = bid {
            if (b as usize) >= MAX_BUBBLES || !self.bubbles[b as usize].used {
                return false;
            }
        }
        self.atoms[id as usize].env_bubble = bid;
        true
    }

    pub fn bubble_new(&mut self, parent: Option<Bid>) -> Option<Bid> {
        if let Some(p) = parent {
            if (p as usize) >= MAX_BUBBLES || !self.bubbles[p as usize].used {
                return None;
            }
        }
        let id = self.alloc_bubble_slot()? as Bid;
        self.bubbles[id as usize] = SlabBubble {
            used: true,
            parent,
            binds: [BindSlot::empty(); MAX_BINDS],
        };
        Some(id)
    }

    /// Drop a non-root bubble (explicit free for freelist reuse).
    /// Returns false if missing, is root, or still has used binds.
    pub fn bubble_drop(&mut self, bid: Bid) -> bool {
        let bi = bid as usize;
        if bi >= MAX_BUBBLES || !self.bubbles[bi].used {
            return false;
        }
        for r in 0..self.root_len {
            if self.roots[r] == Some(bid) {
                return false;
            }
        }
        for slot in &self.bubbles[bi].binds {
            if slot.used {
                return false;
            }
        }
        // clear env_bubble refs pointing here
        for a in self.atoms.iter_mut() {
            if a.env_bubble == Some(bid) {
                a.env_bubble = None;
            }
        }
        // clear parent links
        for b in self.bubbles.iter_mut() {
            if b.parent == Some(bid) {
                b.parent = None;
            }
        }
        self.bubbles[bi] = SlabBubble::empty();
        true
    }

    pub fn bind(&mut self, bid: Bid, name: &str, aid: AtomId) -> bool {
        if (bid as usize) >= MAX_BUBBLES || !self.bubbles[bid as usize].used {
            return false;
        }
        if !self.has_atom(aid) {
            return false;
        }
        let b = &mut self.bubbles[bid as usize];
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
        false
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
        let mut n = 0usize;
        for a in self.atoms.iter() {
            if a.used {
                n += 1;
            }
        }
        n
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

// ── thin wrapper ───────────────────────────────────────────────────────────

/// Simple atom table without bubbles (prefer [`SlabStore`]).
pub struct SlabAtoms {
    inner: SlabStore,
}

impl SlabAtoms {
    pub const fn new() -> Self {
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
        self.inner.set_decay(rate);
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

// ── tests (host: cargo test enables std for assert macros) ─────────────────

#[cfg(test)]
mod tests {
    use super::*;

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
        let mut long = [b'x'; MAX_LABEL + 20];
        let l = FixedLabel::from_bytes(&long);
        assert_eq!(l.as_bytes().len(), MAX_LABEL);
        long[0] = b'y';
        let _ = long;
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
        s.set_decay(0.1);
        let aid = s.atom_new("x", "keep", 50.0).unwrap();
        let bid = s.bubble_new(None).unwrap();
        assert!(s.bind(bid, "v", aid));
        assert!(s.set_root(bid));
        s.settle(30);
        assert!(s.has_atom(aid), "rooted cold atom must not vacuum");
        assert!(s.is_retained(aid) || s.get_t(aid).unwrap() >= T_TOMB);
    }

    #[test]
    fn orphan_vacuum() {
        let mut s = SlabStore::new();
        s.set_decay(0.1);
        let aid = s.atom_new("x", "orphan", 50.0).unwrap();
        s.settle(30);
        assert!(!s.has_atom(aid), "orphan must vacuum");
        assert!(s.reaped >= 1);
    }

    #[test]
    fn env_bubble_extends_reach() {
        let mut s = SlabStore::new();
        s.set_decay(0.1);
        let outer = s.atom_new("o", "outer", 50.0).unwrap();
        let inner = s.atom_new("i", "inner", 50.0).unwrap();
        let b_out = s.bubble_new(None).unwrap();
        let b_in = s.bubble_new(None).unwrap();
        s.bind(b_out, "x", outer);
        s.bind(b_in, "y", inner);
        s.set_env_bubble(outer, Some(b_in));
        s.set_root(b_out);
        s.settle(25);
        assert!(s.has_atom(outer));
        assert!(s.has_atom(inner), "env_bubble must keep inner reachable");
    }

    #[test]
    fn parent_chain_reach() {
        let mut s = SlabStore::new();
        s.set_decay(0.1);
        let aid = s.atom_new("a", "child", 50.0).unwrap();
        let parent = s.bubble_new(None).unwrap();
        let child = s.bubble_new(Some(parent)).unwrap();
        s.bind(child, "v", aid);
        // Root child: walk visits binds then parent UP.
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
    fn freelist_reuses_after_vacuum() {
        let mut s = SlabStore::new();
        s.set_decay(0.1);
        // fill all atom slots
        for _ in 0..MAX_ATOMS {
            assert!(s.atom_new("s", "e", 5.0).is_some());
        }
        assert!(s.atom_new("s", "e", 5.0).is_none());
        // no roots → all orphans vacuum after cool
        s.settle(40);
        assert_eq!(s.count_atoms(), 0, "all orphans vacuumed");
        assert!(s.reaped >= MAX_ATOMS as u64);
        // freelist must allow full refill
        for i in 0..MAX_ATOMS {
            assert!(s.atom_new("s", "reuse", 50.0).is_some(), "reuse i={i}");
        }
        assert!(s.atom_new("s", "e", 50.0).is_none());
    }

    #[test]
    fn heat_ignores_negative() {
        let mut s = SlabStore::new();
        let id = s.atom_new("a", "b", 50.0).unwrap();
        let t0 = s.get_t(id).unwrap();
        assert!(s.heat(id, -20.0));
        assert_eq!(s.get_t(id).unwrap(), t0);
    }

    #[test]
    fn bubble_drop_frees_slot() {
        let mut s = SlabStore::new();
        // fill all bubbles
        for _ in 0..MAX_BUBBLES {
            assert!(s.bubble_new(None).is_some());
        }
        assert!(s.bubble_new(None).is_none());
        // drop id 0 (empty binds, not root)
        assert!(s.bubble_drop(0));
        assert!(s.bubble_new(None).is_some());
    }

    #[test]
    fn set_env_rejects_dead_bubble() {
        let mut s = SlabStore::new();
        let aid = s.atom_new("a", "b", 50.0).unwrap();
        assert!(!s.set_env_bubble(aid, Some(99)));
        assert!(!s.set_env_bubble(aid, Some(0))); // bubble 0 not created
    }

    #[test]
    fn unset_root_then_reap_strict() {
        let mut s = SlabStore::new();
        s.set_decay(0.1);
        let aid = s.atom_new("x", "y", 50.0).unwrap();
        let bid = s.bubble_new(None).unwrap();
        s.bind(bid, "v", aid);
        s.set_root(bid);
        s.settle(20);
        assert!(s.has_atom(aid));
        s.unset_root(bid);
        s.settle(20);
        assert!(!s.has_atom(aid), "after unset_root cold atom must vacuum");
        assert!(s.reaped >= 1);
    }

    #[test]
    fn slab_atoms_wrapper_tick_decay() {
        let mut s = SlabAtoms::new();
        let id = s.atom_new("a", "b", 5.0).unwrap();
        for _ in 0..40 {
            s.tick_decay(0.5);
        }
        assert!(!s.has(id));
        assert!(s.reaped() >= 1);
    }

    #[test]
    fn const_new_static_ready() {
        static mut S: SlabStore = SlabStore::new();
        unsafe {
            let store = &mut *core::ptr::addr_of_mut!(S);
            let id = store.atom_new("k", "entry", T_INIT).unwrap();
            assert!(store.has_atom(id));
            store.tick();
        }
    }
}
