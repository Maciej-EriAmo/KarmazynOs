//! TB.3 — golden: K0 `state_code` / decay law ↔ Rust `state_for_t` / constants.
//!
//! Source of truth for *codes* is the same thresholds as `toolchain/kcc/examples/thermal.k0`.
//! This module lives next to freestanding law so host + kentry stay aligned with own-compiler K0.

/// K0 `state_code` (3 HOT, 2 WARM, 1 COLD, 0 TOMB) — keep in sync with thermal.k0.
#[inline]
pub fn k0_state_code(t: f64) -> i32 {
    let x = crate::clamp_t(t);
    if x >= crate::T_HOT {
        3
    } else if x >= crate::T_WARM {
        2
    } else if x >= crate::T_TOMB {
        1
    } else {
        0
    }
}

#[inline]
pub fn k0_code_to_name(code: i32) -> &'static str {
    match code {
        3 => "HOT",
        2 => "WARM",
        1 => "COLD",
        _ => "TOMB",
    }
}

/// K0 `decay_once` with default rate.
#[inline]
pub fn k0_tick_t(t: f64) -> f64 {
    crate::clamp_t(t * crate::DECAY_DEFAULT)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{state_for_t, DECAY_DEFAULT, T_HOT, T_INIT, T_TOMB, T_WARM};

    const SAMPLES: &[f64] = &[
        100.0, 80.0, 70.0, 69.999, 50.0, 30.0, 29.999, 10.0, 2.0, 1.999, 1.0, 0.0, T_INIT,
        T_HOT, T_WARM, T_TOMB,
    ];

    #[test]
    fn k0_state_code_matches_state_for_t() {
        for &t in SAMPLES {
            let code = k0_state_code(t);
            let name = state_for_t(t);
            assert_eq!(
                k0_code_to_name(code),
                name,
                "t={t}: k0 code {code} vs state_for_t={name}"
            );
        }
    }

    #[test]
    fn k0_thresholds_match_slab_consts() {
        assert!((T_HOT - 70.0).abs() < 1e-12);
        assert!((T_WARM - 30.0).abs() < 1e-12);
        assert!((T_TOMB - 2.0).abs() < 1e-12);
        assert!((T_INIT - 50.0).abs() < 1e-12);
        assert!((DECAY_DEFAULT - 0.92).abs() < 1e-12);
    }

    #[test]
    fn k0_tick_decay_matches() {
        let t1 = k0_tick_t(50.0);
        assert!((t1 - 46.0).abs() < 1e-9);
        // 80 ticks from T_INIT → dead (same as host COOL)
        let mut t = T_INIT;
        for _ in 0..80 {
            t = k0_tick_t(t);
        }
        assert!(t < T_TOMB, "after 80 ticks t={t}");
    }
}
