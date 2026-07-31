//! Atom model + temperature FSM (mirrors karmazyn_atom.py).
//!
//! Thermal constants live in `karmazyn_slab` (shared with freestanding kentry).

pub use karmazyn_slab::{
    clamp_t, state_for_t, AtomId, DECAY_DEFAULT, HEAT_READ, T_HOT, T_INIT, T_MAX, T_TOMB, T_WARM,
};

#[allow(dead_code)]
pub const HEAT_WRITE: f64 = 5.0;

#[derive(Debug, Clone)]
pub struct Atom {
    pub id: AtomId,
    pub s: String,
    pub e: String,
    pub t: f64,
    /// Opaque language payload handle (Python object id, or 0 = none).
    /// Native core never inspects it — only passes to env_of callback.
    pub value_token: u64,
    pub reads: u64,
    pub writes: u64,
}

impl Atom {
    pub fn new(id: AtomId, s: impl Into<String>, e: impl Into<String>, t: f64) -> Self {
        Self {
            id,
            s: s.into(),
            e: e.into(),
            t: clamp_t(t),
            value_token: 0,
            reads: 0,
            writes: 0,
        }
    }

    #[inline]
    pub fn state(&self) -> &'static str {
        state_for_t(self.t)
    }

    #[inline]
    pub fn is_dead(&self) -> bool {
        self.t < T_TOMB
    }

    pub fn decay(&mut self, rate: f64) {
        let r = if rate < 0.0 { 0.0 } else { rate };
        self.t = clamp_t(self.t * r);
    }

    pub fn heat(&mut self, amount: f64) {
        let a = if amount < 0.0 { 0.0 } else { amount };
        self.t = clamp_t(self.t + a);
    }

    pub fn touch(&mut self) {
        self.reads += 1;
        self.heat(HEAT_READ);
    }
}
