//! Atom model + temperature FSM (mirrors karmazyn_atom.py).
//!
//! Thermal constants live in `karmazyn_slab` (shared with freestanding kentry).

pub use karmazyn_slab::{
    clamp_t, state_for_t, AtomId, DECAY_DEFAULT, HEAT_READ, HEAT_WRITE, T_HOT, T_INIT, T_MAX,
    T_TOMB, T_WARM,
};

#[derive(Debug, Clone)]
pub struct Atom {
    pub id: AtomId,
    pub s: String,
    pub e: String,
    pub t: f64,
    /// Opaque language payload handle (tag / env id). Core never interprets it
    /// except passing it to `env_of`.
    pub value_token: u64,
    /// Guest blob owned by the atom (Python: `metadata["v"]` for objects).
    /// Vacuum / snapshot travel with the atom. Core does not parse it.
    pub payload: Option<Vec<u8>>,
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
            payload: None,
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

    /// Read path: bump reads + HEAT_READ (lookup, explicit Store::heat).
    pub fn touch(&mut self) {
        self.reads += 1;
        self.heat(HEAT_READ);
    }

    /// Write path: bump writes + HEAT_WRITE (value token set, etc.).
    pub fn mark_write(&mut self) {
        self.writes += 1;
        self.heat(HEAT_WRITE);
    }
}
