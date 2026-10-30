//! HSS — Ring-LWE KEM z `DBase/karmazyn_hss.py` (+ `karmazyn_hss_ntt.py`),
//! strona inicjatora (klient).
//!
//! Profile `standard` (n=128, q=3329) i `production` (n=512, q=12289) liczą
//! klucz publiczny i iloczyn przez NTT z wielomianem `a` z SHA-256 seeda —
//! deterministycznie, więc da się je odtworzyć dokładnie. Profil `proto`
//! losuje macierz generatorem NumPy (PCG64) i tu nie jest obsługiwany:
//! klient wtedy nie ogłasza `hss` i rozmowa idzie przez ECDH.
//!
//! Transformata jest odtworzona krok w krok tak, jak w Pythonie (ta sama
//! kolejność operacji, ten sam pierwiastek z `_primitive_root`), bo obie
//! strony muszą policzyć te same liczby.

use sha2::{Digest, Sha256};

pub const SHARED_SALT: &[u8] = b"KARMAZYN_HSS_KEM_SHARED_v3";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Profile {
    pub name: &'static str,
    pub n: usize,
    pub q: i64,
    pub sk_max: i64,
    pub buckets: i64,
    pub recon_tolerance: i64,
    pub a_seed: &'static [u8],
}

impl Profile {
    pub fn pk_bytes(&self) -> usize {
        self.n * 8
    }

    pub fn ack_bytes(&self) -> usize {
        self.pk_bytes() + 4
    }
}

pub const STANDARD: Profile = Profile {
    name: "standard",
    n: 128,
    q: 3329,
    sk_max: 3,
    buckets: 16,
    recon_tolerance: 8,
    a_seed: b"KARMAZYN_HSS_KEM_A_v3_n128",
};

pub const PRODUCTION: Profile = Profile {
    name: "production",
    n: 512,
    q: 12289,
    sk_max: 3,
    buckets: 32,
    recon_tolerance: 24,
    a_seed: b"KARMAZYN_HSS_KEM_A_v3_n512",
};

/// Nazwa profilu → parametry. `standard` i `production` są natywne.
/// `proto`, puste i nieznane dają `None`: klient nie ogłasza HSS.
pub fn profile_from_name(raw: &str) -> Option<Profile> {
    match raw.trim().to_lowercase().as_str() {
        "standard" => Some(STANDARD),
        "production" => Some(PRODUCTION),
        _ => None,
    }
}

/// Profil z `KARM_HSS_PROFILE`. Puste i `proto` → `None` (rozmowa idzie ECDH).
pub fn profile_from_env() -> Option<Profile> {
    profile_from_name(&std::env::var("KARM_HSS_PROFILE").unwrap_or_default())
}

fn mod_pow(base: i64, mut exp: i64, m: i64) -> i64 {
    let mut b = base.rem_euclid(m);
    let mut r = 1i64;
    while exp > 0 {
        if exp & 1 == 1 {
            r = r * b % m;
        }
        b = b * b % m;
        exp >>= 1;
    }
    r
}

fn mod_inv(a: i64, q: i64) -> i64 {
    mod_pow(a, q - 2, q)
}

/// `_primitive_root(q, n)`: najmniejsze g ≥ 2 z g^(2n)=1, g^n=q-1, g^(n/2)≠q-1.
fn primitive_root(q: i64, n: i64) -> i64 {
    assert_eq!(q % (2 * n), 1, "NTT: q ≢ 1 (mod 2n)");
    for g in 2..q {
        if mod_pow(g, 2 * n, q) != 1 {
            continue;
        }
        if mod_pow(g, n, q) == q - 1 && mod_pow(g, n / 2, q) != q - 1 {
            return g;
        }
    }
    panic!("NTT: brak pierwiastka dla q={q}, n={n}");
}

fn bit_reverse(mut x: usize, bits: u32) -> usize {
    let mut r = 0;
    for _ in 0..bits {
        r = (r << 1) | (x & 1);
        x >>= 1;
    }
    r
}

/// `ntt_negacyclic` 1:1.
fn ntt(a: &[i64], q: i64, root: i64, inverse: bool) -> Vec<i64> {
    let n = a.len();
    let bits = n.trailing_zeros();
    let mut out = vec![0i64; n];
    for (i, v) in a.iter().enumerate() {
        out[bit_reverse(i, bits)] = v.rem_euclid(q);
    }
    let mut length = 2;
    while length <= n {
        let half = length / 2;
        let mut step = mod_pow(root, (n / length) as i64, q);
        if inverse {
            step = mod_inv(step, q);
        }
        for start in (0..n).step_by(length) {
            let mut w = 1i64;
            for j in 0..half {
                let u = out[start + j];
                let v = out[start + j + half] * w % q;
                out[start + j] = (u + v).rem_euclid(q);
                out[start + j + half] = (u - v).rem_euclid(q);
                w = w * step % q;
            }
        }
        length *= 2;
    }
    if inverse {
        let inv_n = mod_inv(n as i64, q);
        for v in out.iter_mut() {
            *v = *v * inv_n % q;
        }
    }
    out
}

/// `ntt_poly_mul`.
fn poly_mul(a: &[i64], b: &[i64], p: &Profile) -> Vec<i64> {
    let root = primitive_root(p.q, p.n as i64);
    let fa = ntt(a, p.q, root, false);
    let fb = ntt(b, p.q, root, false);
    let fc: Vec<i64> = fa.iter().zip(&fb).map(|(x, y)| x * y % p.q).collect();
    ntt(&fc, p.q, root, true)
}

/// `kem_poly_a`: SHA-256(a_seed + "_ntt_v1") powielone do n bajtów, mod q.
fn poly_a(p: &Profile) -> Vec<i64> {
    let mut h = Sha256::new();
    h.update(p.a_seed);
    h.update(b"_ntt_v1");
    let d = h.finalize();
    (0..p.n).map(|i| i64::from(d[i % d.len()]) % p.q).collect()
}

fn pubkey(sk: &[i64], p: &Profile) -> Vec<i64> {
    let sk: Vec<i64> = sk.iter().map(|v| v.rem_euclid(p.q)).collect();
    // kem_noise = 0 we wszystkich profilach: pk = a·sk
    poly_mul(&poly_a(p), &sk, p).iter().map(|v| v % p.q).collect()
}

fn dot(sk: &[i64], pk: &[i64], p: &Profile) -> i64 {
    let sk: Vec<i64> = sk.iter().map(|v| v.rem_euclid(p.q)).collect();
    let pk: Vec<i64> = pk.iter().map(|v| v.rem_euclid(p.q)).collect();
    poly_mul(&sk, &pk, p)[0] % p.q
}

fn bucket(d: i64, p: &Profile) -> i64 {
    d.rem_euclid(p.q) / (p.q / p.buckets).max(1)
}

pub fn shared_from_bucket(b: i64) -> [u8; 32] {
    let mut h = Sha256::new();
    h.update((b as u32).to_be_bytes());
    h.update(SHARED_SALT);
    h.finalize().into()
}

fn serialize(v: &[i64]) -> Vec<u8> {
    v.iter().flat_map(|x| x.to_le_bytes()).collect()
}

fn deserialize(b: &[u8], p: &Profile) -> Result<Vec<i64>, String> {
    if b.len() != p.pk_bytes() {
        return Err(format!(
            "HSS KEM pubkey/ack: oczekiwano {} B, jest {}",
            p.pk_bytes(),
            b.len()
        ));
    }
    Ok(b.chunks_exact(8)
        .map(|c| i64::from_le_bytes(c.try_into().unwrap()).rem_euclid(p.q))
        .collect())
}

/// Stan inicjatora między `init` a `finalize`.
pub struct Initiator {
    profile: Profile,
    sk: Vec<i64>,
}

impl Initiator {
    /// `init_session`: sk ∈ [0, sk_max)^n, zwraca bajty klucza publicznego.
    pub fn new(profile: Profile) -> Result<(Initiator, Vec<u8>), String> {
        let mut raw = vec![0u8; profile.n];
        getrandom::getrandom(&mut raw).map_err(|e| e.to_string())?;
        // odrzucanie stronnicze nie ma znaczenia dla zgodności — strona
        // przeciwna używa tylko pk; równomierność jak w numpy niepotrzebna
        let sk: Vec<i64> = raw.iter().map(|b| i64::from(*b) % profile.sk_max).collect();
        let pk = pubkey(&sk, &profile);
        Ok((Initiator { profile, sk }, serialize(&pk)))
    }

    /// `finalize(token, ack)`: ack = pk_b (n×8 B LE) ‖ bucket (u32 BE).
    pub fn finalize(self, ack: &[u8]) -> Result<[u8; 32], String> {
        let p = self.profile;
        if ack.len() != p.ack_bytes() {
            return Err(format!("HSS ack: oczekiwano {} B, jest {}", p.ack_bytes(), ack.len()));
        }
        let pk_b = deserialize(&ack[..p.pk_bytes()], &p)?;
        let hint = i64::from(u32::from_be_bytes(ack[p.pk_bytes()..].try_into().unwrap()));
        let local = bucket(dot(&self.sk, &pk_b, &p), &p);
        if (local - hint).abs() > p.recon_tolerance {
            return Err(format!(
                "HSS KEM ({}): rekonsyliacja nieudana (hint={hint}, local={local})",
                p.name
            ));
        }
        Ok(shared_from_bucket(hint))
    }
}

/// Strona odpowiadająca (tylko do testów zgodności po stronie Rusta).
#[cfg(test)]
pub fn respond(pk_a: &[u8], p: &Profile, sk_b: &[i64]) -> ([u8; 32], Vec<u8>) {
    let pk_a = deserialize(pk_a, p).unwrap();
    let pk_b = pubkey(sk_b, p);
    let b = bucket(dot(sk_b, &pk_a, p), p);
    let mut ack = serialize(&pk_b);
    ack.extend((b as u32).to_be_bytes());
    (shared_from_bucket(b), ack)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roots_match_python() {
        // _primitive_root(3329, 128), _primitive_root(12289, 512) w Pythonie
        assert_eq!(mod_pow(primitive_root(3329, 128), 256, 3329), 1);
        assert_eq!(mod_pow(primitive_root(12289, 512), 1024, 12289), 1);
    }

    #[test]
    fn kem_agrees_on_both_profiles() {
        for p in [STANDARD, PRODUCTION] {
            for _ in 0..5 {
                let (init, pk_a) = Initiator::new(p).unwrap();
                let mut raw = vec![0u8; p.n];
                getrandom::getrandom(&mut raw).unwrap();
                let sk_b: Vec<i64> = raw.iter().map(|b| i64::from(*b) % p.sk_max).collect();
                let (shared_b, ack) = respond(&pk_a, &p, &sk_b);
                assert_eq!(init.finalize(&ack).unwrap(), shared_b, "{}", p.name);
            }
        }
    }

    #[test]
    fn bad_ack_length_is_refused() {
        let (init, _) = Initiator::new(STANDARD).unwrap();
        assert!(init.finalize(&[0u8; 10]).is_err());
    }
}
