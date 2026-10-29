//! Store: atoms + bubbles + roots + reach-GC.
//! Mirrors the law of karmazyn_substrate.py (without Python EventBus / HRR).

use crate::atom::{Atom, AtomId, DECAY_DEFAULT, T_INIT};
use std::collections::{HashMap, HashSet};
use std::sync::{Arc, Mutex};

pub type BubbleId = u32;

/// env_of hook: value_token → optional bubble id (0 = none).
pub type EnvOfFn = Arc<dyn Fn(u64) -> Option<BubbleId> + Send + Sync>;
/// extra_reach hook: returns additional reachable atom ids.
pub type ExtraReachFn = Arc<dyn Fn() -> Vec<AtomId> + Send + Sync>;

#[derive(Debug, Clone)]
pub struct Bubble {
    #[allow(dead_code)]
    pub id: BubbleId,
    #[allow(dead_code)]
    pub label: String,
    pub parent: Option<BubbleId>,
    pub bindings: HashMap<String, AtomId>,
}

#[derive(Debug, Clone, Default)]
pub struct Stats {
    pub total: usize,
    pub hot: usize,
    pub warm: usize,
    pub cold: usize,
    pub tomb: usize,
    pub alive: usize,
    pub dead: usize,
    pub reaped: u64,
    pub retained_tomb: usize,
    pub bubbles: usize,
}

pub(crate) struct Inner {
    pub(crate) atoms: HashMap<AtomId, Atom>,
    pub(crate) bubbles: HashMap<BubbleId, Bubble>,
    pub(crate) roots: Vec<BubbleId>,
    pub(crate) next_atom: AtomId,
    pub(crate) next_bubble: BubbleId,
    pub(crate) thermal: bool,
    pub(crate) decay: f64,
    pub(crate) reaped: u64,
    pub(crate) retained_tomb: HashSet<AtomId>,
    pub(crate) ticking: bool,
    /// Rośnie przy każdej zmianie, która może DODAĆ osiągalność (bind, root,
    /// token, upsert, haki, import). Tick nie zbiera, gdy zmienił się od migawki.
    pub(crate) reach_gen: u64,
    env_of_hooks: Vec<(String, EnvOfFn)>,
    extra_reach_hooks: Vec<(String, ExtraReachFn)>,
}

impl Inner {
    fn new(thermal: bool, decay: f64) -> Self {
        Self {
            atoms: HashMap::new(),
            bubbles: HashMap::new(),
            roots: Vec::new(),
            next_atom: 0,
            // 0 jest wartownikiem „brak bąbla” w haku env_of (C ABI i PyO3).
            next_bubble: 1,
            thermal,
            decay,
            reaped: 0,
            retained_tomb: HashSet::new(),
            ticking: false,
            reach_gen: 0,
            env_of_hooks: Vec::new(),
            extra_reach_hooks: Vec::new(),
        }
    }

    pub(crate) fn touch_reach(&mut self) {
        self.reach_gen = self.reach_gen.wrapping_add(1);
    }

    fn purge_bindings(&mut self, aid: AtomId) {
        for b in self.bubbles.values_mut() {
            b.bindings.retain(|_k, v| *v != aid);
        }
    }

    fn reach_snap(&self) -> ReachSnap {
        let mut bubbles = HashMap::new();
        for (id, b) in &self.bubbles {
            let binds: Vec<AtomId> = b.bindings.values().copied().collect();
            bubbles.insert(*id, (b.parent, binds));
        }
        ReachSnap {
            gen: self.reach_gen,
            roots: self.roots.clone(),
            bubbles,
            tokens: self
                .atoms
                .iter()
                .map(|(id, a)| (*id, a.value_token))
                .collect(),
            env_hooks: self.env_of_hooks.iter().map(|(_, f)| f.clone()).collect(),
            extra_hooks: self.extra_reach_hooks.iter().map(|(_, f)| f.clone()).collect(),
        }
    }

    /// `reap == false`: tylko chłodzenie. Martwe atomy czekają na następny tick.
    fn apply_reach(&mut self, reach: &HashSet<AtomId>, reap: bool) {
        let aids: Vec<AtomId> = self.atoms.keys().copied().collect();
        for aid in &aids {
            if let Some(a) = self.atoms.get_mut(aid) {
                a.decay(self.decay);
            }
        }
        for aid in aids {
            let dead = self.atoms.get(&aid).map(|a| a.is_dead()).unwrap_or(false);
            if !dead {
                self.retained_tomb.remove(&aid);
                continue;
            }
            if !reap {
                continue;
            }
            if reach.contains(&aid) {
                self.retained_tomb.insert(aid);
            } else {
                self.purge_bindings(aid);
                if self.atoms.remove(&aid).is_some() {
                    self.retained_tomb.remove(&aid);
                    self.reaped += 1;
                }
            }
        }
    }
}

struct ReachSnap {
    gen: u64,
    roots: Vec<BubbleId>,
    bubbles: HashMap<BubbleId, (Option<BubbleId>, Vec<AtomId>)>,
    tokens: HashMap<AtomId, u64>,
    env_hooks: Vec<EnvOfFn>,
    extra_hooks: Vec<ExtraReachFn>,
}

impl ReachSnap {
    fn reach(&self) -> HashSet<AtomId> {
        let mut reach = HashSet::new();
        let mut seen = HashSet::new();
        let mut stack: Vec<BubbleId> = self.roots.clone();
        while let Some(bid) = stack.pop() {
            if !seen.insert(bid) {
                continue;
            }
            let Some((parent, binds)) = self.bubbles.get(&bid) else {
                continue;
            };
            for aid in binds {
                if let Some(tok) = self.tokens.get(aid) {
                    reach.insert(*aid);
                    for f in &self.env_hooks {
                        if let Some(env_b) = f(*tok) {
                            stack.push(env_b);
                            break;
                        }
                    }
                }
            }
            if let Some(p) = parent {
                stack.push(*p);
            }
        }
        for f in &self.extra_hooks {
            for aid in f() {
                reach.insert(aid);
            }
        }
        reach
    }
}

/// Czyści `ticking` także gdy hak albo apply spanikuje.
struct TickEnd<'a>(&'a Store);

impl Drop for TickEnd<'_> {
    fn drop(&mut self) {
        if let Ok(mut g) = self.0.inner.lock() {
            g.ticking = false;
        }
    }
}

/// Thread-safe Store handle (mirrors Python Store.lock / RLock).
#[derive(Clone)]
pub struct Store {
    inner: Arc<Mutex<Inner>>,
}

impl Store {
    pub fn new(thermal: bool) -> Self {
        Self {
            inner: Arc::new(Mutex::new(Inner::new(thermal, DECAY_DEFAULT))),
        }
    }

    pub(crate) fn lock(&self) -> std::sync::MutexGuard<'_, Inner> {
        self.inner.lock().unwrap_or_else(|e| e.into_inner())
    }

    pub fn atom_new(&self, s: &str, e: &str, t: f64) -> AtomId {
        let mut g = self.lock();
        let id = g.next_atom;
        g.next_atom = g.next_atom.saturating_add(1);
        g.atoms.insert(id, Atom::new(id, s, e, if t.is_nan() { T_INIT } else { t }));
        id
    }

    pub fn atom_set_value_token(&self, aid: AtomId, token: u64) -> bool {
        self.atom_set_guest(aid, token, None)
    }

    /// Set token + optional guest blob (Python: `atom.metadata["v"] = obj`).
    /// Blob is owned by the atom: vacuum and snapshot take it along.
    pub fn atom_set_guest(&self, aid: AtomId, token: u64, payload: Option<Vec<u8>>) -> bool {
        let mut g = self.lock();
        let thermal = g.thermal;
        g.touch_reach();
        if let Some(a) = g.atoms.get_mut(&aid) {
            a.value_token = token;
            a.payload = payload;
            if thermal {
                a.mark_write();
            }
            true
        } else {
            false
        }
    }

    pub fn atom_payload(&self, aid: AtomId) -> Option<Vec<u8>> {
        self.lock().atoms.get(&aid).and_then(|a| a.payload.clone())
    }

    pub fn atom_value_token(&self, aid: AtomId) -> Option<u64> {
        let g = self.lock();
        g.atoms.get(&aid).map(|a| a.value_token)
    }

    pub fn has_atom(&self, aid: AtomId) -> bool {
        self.lock().atoms.contains_key(&aid)
    }

    pub fn get_atom_t(&self, aid: AtomId) -> Option<f64> {
        self.lock().atoms.get(&aid).map(|a| a.t)
    }

    pub fn get_atom_state(&self, aid: AtomId) -> Option<String> {
        self.lock().atoms.get(&aid).map(|a| a.state().to_string())
    }

    pub fn atom_is_dead(&self, aid: AtomId) -> Option<bool> {
        self.lock().atoms.get(&aid).map(|a| a.is_dead())
    }

    /// All live atom ids (order not guaranteed).
    pub fn atom_ids(&self) -> Vec<AtomId> {
        self.lock().atoms.keys().copied().collect()
    }

    /// Set absolute temperature (no heat/touch counters). Returns false if missing.
    pub fn atom_set_t(&self, aid: AtomId, t: f64) -> bool {
        use crate::atom::clamp_t;
        let mut g = self.lock();
        if let Some(a) = g.atoms.get_mut(&aid) {
            a.t = clamp_t(if t.is_nan() { T_INIT } else { t });
            true
        } else {
            false
        }
    }

    /// Upsert atom with fixed id (snapshot restore / host import).
    pub fn atom_upsert(
        &self,
        aid: AtomId,
        s: &str,
        e: &str,
        t: f64,
        value_token: u64,
    ) -> bool {
        use crate::atom::clamp_t;
        let mut g = self.lock();
        g.touch_reach();
        let tt = clamp_t(if t.is_nan() { T_INIT } else { t });
        if let Some(a) = g.atoms.get_mut(&aid) {
            a.s = s.to_string();
            a.e = e.to_string();
            a.t = tt;
            a.value_token = value_token;
        } else {
            let mut atom = Atom::new(aid, s, e, tt);
            atom.value_token = value_token;
            g.atoms.insert(aid, atom);
            g.retained_tomb.remove(&aid);
        }
        if aid >= g.next_atom {
            g.next_atom = aid.saturating_add(1);
        }
        true
    }

    /// Replace atom registry with snapshot (transaction rollback).
    /// Entries: (id, S, E, T, value_token). Bubbles/roots unchanged;
    /// dangling bindings to removed atoms are purged.
    pub fn restore_atoms(&self, entries: &[(AtomId, String, String, f64, u64)]) {
        use crate::atom::clamp_t;
        let mut g = self.lock();
        g.touch_reach();
        let keep: HashSet<AtomId> = entries.iter().map(|e| e.0).collect();
        let remove: Vec<AtomId> = g
            .atoms
            .keys()
            .copied()
            .filter(|id| !keep.contains(id))
            .collect();
        for aid in remove {
            g.purge_bindings(aid);
            g.retained_tomb.remove(&aid);
            g.atoms.remove(&aid);
        }
        let mut max_id = 0u32;
        for (id, s, e, t, token) in entries {
            max_id = max_id.max(*id);
            let tt = clamp_t(if t.is_nan() { T_INIT } else { *t });
            if let Some(a) = g.atoms.get_mut(id) {
                a.s = s.clone();
                a.e = e.clone();
                a.t = tt;
                a.value_token = *token;
            } else {
                let mut atom = Atom::new(*id, s.clone(), e.clone(), tt);
                atom.value_token = *token;
                g.atoms.insert(*id, atom);
            }
            g.retained_tomb.remove(id);
        }
        g.next_atom = max_id.saturating_add(1).max(g.next_atom);
    }

    /// Explicit heat — same as a **read** (`touch` / `HEAT_READ`), matching Python Store.heat.
    /// (Not HEAT_WRITE; writes use [`Self::atom_set_value_token`].)
    /// Note: [`Self::lookup`] also touches under thermal mode.
    pub fn heat(&self, aid: AtomId) -> bool {
        let mut g = self.lock();
        if let Some(a) = g.atoms.get_mut(&aid) {
            a.touch();
            true
        } else {
            false
        }
    }

    pub fn delete_atom(&self, aid: AtomId) -> bool {
        let mut g = self.lock();
        if !g.atoms.contains_key(&aid) {
            return false;
        }
        g.purge_bindings(aid);
        g.retained_tomb.remove(&aid);
        g.atoms.remove(&aid).is_some()
    }

    pub fn bubble_new(&self, label: &str, parent: Option<BubbleId>) -> BubbleId {
        let mut g = self.lock();
        if g.next_bubble == 0 {
            g.next_bubble = 1;
        }
        let id = g.next_bubble;
        g.next_bubble = g.next_bubble.saturating_add(1);
        g.bubbles.insert(
            id,
            Bubble {
                id,
                label: label.to_string(),
                parent,
                bindings: HashMap::new(),
            },
        );
        id
    }

    pub fn bind(&self, bid: BubbleId, name: &str, aid: AtomId) -> Result<(), &'static str> {
        let mut g = self.lock();
        if !g.atoms.contains_key(&aid) {
            return Err("bind: atom missing");
        }
        let b = g.bubbles.get_mut(&bid).ok_or("bind: bubble missing")?;
        b.bindings.insert(name.to_string(), aid);
        g.touch_reach();
        Ok(())
    }

    pub fn unbind(&self, bid: BubbleId, name: &str) -> Option<AtomId> {
        let mut g = self.lock();
        g.bubbles.get_mut(&bid)?.bindings.remove(name)
    }

    pub fn lookup(&self, bid: BubbleId, name: &str) -> Option<AtomId> {
        let mut g = self.lock();
        let thermal = g.thermal;
        let mut cur = Some(bid);
        while let Some(id) = cur {
            let parent = g.bubbles.get(&id).map(|b| b.parent);
            let aid = g.bubbles.get(&id).and_then(|b| b.bindings.get(name).copied());
            if let Some(aid) = aid {
                if g.atoms.contains_key(&aid) {
                    if thermal {
                        if let Some(a) = g.atoms.get_mut(&aid) {
                            a.touch();
                        }
                    }
                    return Some(aid);
                }
            }
            cur = parent.flatten();
        }
        None
    }

    pub fn set_root(&self, bid: BubbleId) {
        let mut g = self.lock();
        if g.bubbles.contains_key(&bid) && !g.roots.contains(&bid) {
            g.roots.push(bid);
            g.touch_reach();
        }
    }

    pub fn unset_root(&self, bid: BubbleId) {
        let mut g = self.lock();
        g.roots.retain(|x| *x != bid);
    }

    pub fn register_env_of<F>(&self, name: &str, f: F)
    where
        F: Fn(u64) -> Option<BubbleId> + Send + Sync + 'static,
    {
        let mut g = self.lock();
        g.env_of_hooks.retain(|(n, _)| n != name);
        g.env_of_hooks.insert(0, (name.to_string(), Arc::new(f)));
        g.touch_reach();
    }

    pub fn unregister_env_of(&self, name: &str) {
        self.lock().env_of_hooks.retain(|(n, _)| n != name);
    }

    pub fn register_extra_reach<F>(&self, name: &str, f: F)
    where
        F: Fn() -> Vec<AtomId> + Send + Sync + 'static,
    {
        let mut g = self.lock();
        g.extra_reach_hooks.retain(|(n, _)| n != name);
        g.extra_reach_hooks.insert(0, (name.to_string(), Arc::new(f)));
        g.touch_reach();
    }

    pub fn unregister_extra_reach(&self, name: &str) {
        self.lock()
            .extra_reach_hooks
            .retain(|(n, _)| n != name);
    }

    pub fn tick(&self) {
        let snap = {
            let mut g = self.lock();
            if !g.thermal || g.ticking {
                return;
            }
            g.ticking = true;
            g.reach_snap()
        };
        // Haki env_of / extra_reach poza mutexem: callback może wejść
        // z powrotem w has_atom / get (std::Mutex nie jest reentrantny).
        let _end = TickEnd(self);
        let reach = snap.reach();
        let mut g = self.lock();
        // Coś mogło stać się osiągalne po migawce: nie zbieraj w tym ticku.
        let reap = g.reach_gen == snap.gen;
        g.apply_reach(&reach, reap);
    }

    pub fn settle(&self, n: u32) {
        for _ in 0..n {
            self.tick();
        }
    }

    pub fn stats(&self) -> Stats {
        let g = self.lock();
        let mut st = Stats {
            reaped: g.reaped,
            bubbles: g.bubbles.len(),
            ..Default::default()
        };
        for a in g.atoms.values() {
            st.total += 1;
            match a.state() {
                "HOT" => st.hot += 1,
                "WARM" => st.warm += 1,
                "COLD" => st.cold += 1,
                _ => st.tomb += 1,
            }
            if a.is_dead() {
                st.dead += 1;
            } else {
                st.alive += 1;
            }
        }
        st.retained_tomb = g
            .retained_tomb
            .iter()
            .filter(|id| g.atoms.get(id).map(|a| a.is_dead()).unwrap_or(false))
            .count();
        st
    }

    pub fn atom_count(&self) -> usize {
        self.lock().atoms.len()
    }

    /// Atom labels (S, E) if present.
    pub fn atom_se(&self, aid: AtomId) -> Option<(String, String)> {
        self.lock()
            .atoms
            .get(&aid)
            .map(|a| (a.s.clone(), a.e.clone()))
    }

    pub fn bubble_ids(&self) -> Vec<BubbleId> {
        self.lock().bubbles.keys().copied().collect()
    }

    pub fn bubble_label(&self, bid: BubbleId) -> Option<String> {
        self.lock().bubbles.get(&bid).map(|b| b.label.clone())
    }

    pub fn bubble_parent(&self, bid: BubbleId) -> Option<Option<BubbleId>> {
        self.lock().bubbles.get(&bid).map(|b| b.parent)
    }

    pub fn bubble_bindings(&self, bid: BubbleId) -> Option<Vec<(String, AtomId)>> {
        self.lock().bubbles.get(&bid).map(|b| {
            let mut v: Vec<_> = b
                .bindings
                .iter()
                .map(|(n, a)| (n.clone(), *a))
                .collect();
            v.sort_by(|a, b| a.0.cmp(&b.0));
            v
        })
    }

    pub fn root_ids(&self) -> Vec<BubbleId> {
        self.lock().roots.clone()
    }

    pub fn is_root(&self, bid: BubbleId) -> bool {
        self.lock().roots.contains(&bid)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::atom::T_TOMB;

    /// Enough ticks to cool T_INIT * 0.92^n below T_TOMB.
    const COOL: u32 = 80;

    #[test]
    fn orphan_dies() {
        let s = Store::new(true);
        let a = s.atom_new("var", "orphan", f64::NAN);
        s.settle(COOL);
        assert!(!s.has_atom(a));
        assert_eq!(s.stats().reaped, 1);
    }

    #[test]
    fn restore_atoms_rollback() {
        let s = Store::new(false);
        let a0 = s.atom_new("var", "keep", 50.0);
        s.atom_set_value_token(a0, 42);
        let snap = vec![(a0, "var".into(), "keep".into(), 50.0, 42u64)];
        let a1 = s.atom_new("var", "gone", 50.0);
        assert!(s.has_atom(a1));
        s.restore_atoms(&snap);
        assert!(s.has_atom(a0));
        assert!(!s.has_atom(a1));
        assert_eq!(s.atom_value_token(a0), Some(42));
        // re-insert with fixed id after delete
        s.delete_atom(a0);
        s.restore_atoms(&[(7, "S".into(), "E".into(), 12.5, 0)]);
        assert!(s.has_atom(7));
        assert!((s.get_atom_t(7).unwrap() - 12.5).abs() < 1e-9);
        assert!(!s.has_atom(a0));
    }

    #[test]
    fn root_retains_tomb() {
        let s = Store::new(true);
        let root = s.bubble_new("root", None);
        s.set_root(root);
        let a = s.atom_new("var", "keep", f64::NAN);
        s.bind(root, "keep", a).unwrap();
        s.settle(COOL);
        assert!(s.has_atom(a));
        assert!(s.atom_is_dead(a).unwrap());
        assert_eq!(s.stats().retained_tomb, 1);
    }

    #[test]
    fn unset_root_then_reap() {
        let s = Store::new(true);
        let root = s.bubble_new("root", None);
        s.set_root(root);
        let a = s.atom_new("var", "x", f64::NAN);
        s.bind(root, "x", a).unwrap();
        s.settle(COOL);
        assert!(s.has_atom(a));
        s.unset_root(root);
        s.settle(2);
        assert!(!s.has_atom(a));
    }

    #[test]
    fn env_of_closure_survives() {
        let s = Store::new(true);
        let root = s.bubble_new("root", None);
        s.set_root(root);
        let inner = s.bubble_new("inner", None);
        let n = s.atom_new("var", "n", f64::NAN);
        s.bind(inner, "n", n).unwrap();
        // value_token encodes inner bubble id for env_of
        let clo = s.atom_new("var", "clo", f64::NAN);
        s.atom_set_value_token(clo, inner as u64);
        s.bind(root, "clo", clo).unwrap();
        s.register_env_of("guest", |tok| {
            if tok == 0 {
                None
            } else {
                Some(tok as BubbleId)
            }
        });
        s.settle(100);
        assert!(s.has_atom(n));
        assert_eq!(s.lookup(inner, "n"), Some(n));
    }

    #[test]
    fn guest_payload_dies_with_atom() {
        let s = Store::new(true);
        let a = s.atom_new("var", "clo", f64::NAN);
        s.atom_set_guest(a, 2, Some(vec![1, 2, 3]));
        assert_eq!(s.atom_payload(a).as_deref(), Some(&[1, 2, 3][..]));
        s.settle(COOL);
        assert!(!s.has_atom(a));
        assert!(s.atom_payload(a).is_none());
    }

    #[test]
    fn extra_reach_protects() {
        use std::sync::atomic::{AtomicU32, Ordering};
        static HELD: AtomicU32 = AtomicU32::new(u32::MAX);
        let s = Store::new(true);
        let a = s.atom_new("var", "flat", f64::NAN);
        HELD.store(a, Ordering::SeqCst);
        s.register_extra_reach("guest", || {
            let id = HELD.load(Ordering::SeqCst);
            if id == u32::MAX {
                vec![]
            } else {
                vec![id]
            }
        });
        s.settle(COOL);
        assert!(s.has_atom(a));
        HELD.store(u32::MAX, Ordering::SeqCst);
        s.settle(2);
        assert!(!s.has_atom(a));
    }

    #[test]
    fn bind_during_tick_is_not_reaped() {
        use std::sync::atomic::{AtomicBool, Ordering};
        let s = Store::new(true);
        let root = s.bubble_new("root", None);
        s.set_root(root);
        let a = s.atom_new("var", "late", 0.0);
        assert_eq!(s.atom_is_dead(a), Some(true));
        let fired = Arc::new(AtomicBool::new(false));
        let (s2, f2) = (s.clone(), fired.clone());
        // hak chodzi po migawce, przed apply: tu "inny wątek" przypina martwy atom
        s.register_extra_reach("late_bind", move || {
            if !f2.swap(true, Ordering::SeqCst) {
                s2.bind(root, "late", a).unwrap();
            }
            vec![]
        });
        s.tick();
        assert!(s.has_atom(a), "atom przypięty w trakcie ticka zniknął");
        assert_eq!(s.bubble_bindings(root), Some(vec![("late".to_string(), a)]));
        assert_eq!(s.stats().reaped, 0);
        // następny tick widzi powiązanie: martwy, ale osiągalny
        s.tick();
        assert!(s.has_atom(a));
        assert_eq!(s.stats().retained_tomb, 1);
        s.unregister_extra_reach("late_bind");
    }

    #[test]
    fn state_thresholds() {
        assert!(T_TOMB > 0.0);
        let s = Store::new(false);
        let a = s.atom_new("x", "e", 80.0);
        assert_eq!(s.get_atom_state(a).as_deref(), Some("HOT"));
    }
}
