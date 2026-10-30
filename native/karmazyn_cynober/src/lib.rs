//! Klient Cynober-Secure-1.2 — natywny odpowiednik `DBase/cynober_client.py`.
//!
//! ```text
//! TCP (L0) → caps (JSON, sort_keys) → anty-replay (ts ±300 s, session_id)
//!          → klucz sesji: HSS (Ring-LWE, standard|production) albo ECDH (X25519)
//!            [+ KARM_PSK: key = SHA-256(key ‖ psk)]
//!            PSK i profil HSS: środowisko, a gdy puste — aktywny profil
//!            w `{data_home}/client.json` (na płycie `/data/cynober/client.json`,
//!            obok `master.key`). Brak pliku = ECDH.
//!          → HSL-1.1: hsl_link / hsl_cap jako "HSL1" ‖ AES-GCM (AAD stałe)
//!            s_target = HKDF(link_seed ‖ sorted(commits) ‖ epoch ‖ ctx, "hsl-prism")
//!          → RPC: zlib(JSON {query, cap, epoch}) w AES-GCM kluczem ramki
//!            HKDF(s_target ‖ AAD, "hsl-frame"), AAD = kierunek klient→serwer
//! ```
//!
//! Ramka TCP: u32 BE długość + dane (≤ 64 MiB). Szyfrogram: nonce 12 B ‖ AES-GCM.
//! Tryb `simple` (PBKDF2 + XOR) i ramki KAFS (media) nie są obsługiwane: klient
//! nie ogłasza ich w caps.

pub mod hss;

use aes_gcm::aead::{Aead, KeyInit, Payload};
use aes_gcm::{Aes256Gcm, Nonce};
use hkdf::Hkdf;
use hmac::{Hmac, Mac};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::io::{Read, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

pub const PROTO_VERSION: &str = "Cynober-Secure-1.2";
pub const SUPPORTED_VERSIONS: [&str; 3] =
    ["Cynober-Secure-1.2", "Cynober-Secure-1.1", "Cynober-Secure-1.0"];
pub const HSL_VERSION: &str = "HSL-1.1";
pub const HSL_TASK: &str = "cynober-rpc";
pub const HSL_PRISMS: [&str; 1] = ["karminql"];
pub const CAP_RPC_QUERY: &str = "rpc:query";
pub const FRAME_MAX: usize = 64 * 1024 * 1024;
pub const REPLAY_WINDOW_SEC: f64 = 300.0;
pub const DEFAULT_PORT: u16 = 8080;
const HSL_MAGIC: &[u8] = b"HSL1";
const AAD_LINK: &[u8] = b"cynober-hsl-link-v1";
const AAD_CAP: &[u8] = b"cynober-hsl-cap-v1";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Error(pub String);

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for Error {}

impl From<std::io::Error> for Error {
    fn from(e: std::io::Error) -> Self {
        Error(e.to_string())
    }
}

pub type Result<T> = std::result::Result<T, Error>;

fn err<T>(m: impl Into<String>) -> Result<T> {
    Err(Error(m.into()))
}

// ── ramki ────────────────────────────────────────────────────────────────

fn send_frame<W: Write>(w: &mut W, data: &[u8]) -> Result<()> {
    if data.len() > FRAME_MAX {
        return err(format!("Payload za duży: {}", data.len()));
    }
    let mut buf = (data.len() as u32).to_be_bytes().to_vec();
    buf.extend_from_slice(data);
    w.write_all(&buf)?;
    w.flush()?;
    Ok(())
}

fn recv_frame<R: Read>(r: &mut R) -> Result<Vec<u8>> {
    let mut h = [0u8; 4];
    r.read_exact(&mut h)
        .map_err(|e| Error(format!("Połączenie zamknięte przed odebraniem danych ({e})")))?;
    let n = u32::from_be_bytes(h) as usize;
    if n > FRAME_MAX {
        return err(format!("Ramka za duża: {n}"));
    }
    let mut b = vec![0u8; n];
    r.read_exact(&mut b)?;
    Ok(b)
}

/// `_send_json`: klucze posortowane (BTreeMap), separatory jak w Pythonie
/// nie mają znaczenia dla parsera po drugiej stronie.
fn to_sorted_json(v: &Value) -> Vec<u8> {
    fn sort(v: &Value) -> Value {
        match v {
            Value::Object(m) => {
                let b: BTreeMap<String, Value> =
                    m.iter().map(|(k, v)| (k.clone(), sort(v))).collect();
                serde_json::to_value(b).expect("mapa")
            }
            Value::Array(a) => Value::Array(a.iter().map(sort).collect()),
            x => x.clone(),
        }
    }
    let sorted = sort(v);
    let mut out = Vec::new();
    write_sorted(&sorted, &mut out);
    out
}

/// Zapis z kluczami w kolejności alfabetycznej niezależnie od cechy
/// `preserve_order` w serde_json (inne crate'y w tej samej kompilacji).
fn write_sorted(v: &Value, out: &mut Vec<u8>) {
    match v {
        Value::Object(m) => {
            let mut keys: Vec<&String> = m.keys().collect();
            keys.sort();
            out.push(b'{');
            for (i, k) in keys.iter().enumerate() {
                if i > 0 {
                    out.extend_from_slice(b", ");
                }
                out.extend(serde_json::to_vec(k).expect("klucz"));
                out.extend_from_slice(b": ");
                write_sorted(&m[*k], out);
            }
            out.push(b'}');
        }
        Value::Array(a) => {
            out.push(b'[');
            for (i, x) in a.iter().enumerate() {
                if i > 0 {
                    out.extend_from_slice(b", ");
                }
                write_sorted(x, out);
            }
            out.push(b']');
        }
        x => out.extend(serde_json::to_vec(x).expect("wartość")),
    }
}

fn send_json(s: &mut TcpStream, v: &Value) -> Result<()> {
    send_frame(s, &to_sorted_json(v))
}

fn recv_json(s: &mut TcpStream) -> Result<Value> {
    let raw = recv_frame(s)?;
    serde_json::from_slice(&raw).map_err(|e| Error(format!("JSON: {e}")))
}

// ── kryptografia ─────────────────────────────────────────────────────────

fn random<const N: usize>() -> Result<[u8; N]> {
    let mut b = [0u8; N];
    getrandom::getrandom(&mut b).map_err(|e| Error(format!("losowość: {e}")))?;
    Ok(b)
}

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}

fn unhex(s: &str) -> Result<Vec<u8>> {
    if !s.len().is_multiple_of(2) {
        return err("hex: nieparzysta długość");
    }
    (0..s.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&s[i..i + 2], 16).map_err(|e| Error(format!("hex: {e}"))))
        .collect()
}

/// `_CryptoLayer.encrypt` w trybach hss/ecdh: nonce 12 ‖ AES-256-GCM.
fn seal(key: &[u8; 32], data: &[u8], aad: &[u8]) -> Result<Vec<u8>> {
    let nonce: [u8; 12] = random()?;
    let ct = Aes256Gcm::new(key.into())
        .encrypt(Nonce::from_slice(&nonce), Payload { msg: data, aad })
        .map_err(|_| Error("AES-GCM: szyfrowanie".into()))?;
    let mut out = nonce.to_vec();
    out.extend(ct);
    Ok(out)
}

fn open(key: &[u8; 32], data: &[u8], aad: &[u8]) -> Result<Vec<u8>> {
    if data.len() < 12 + 16 {
        return err("ramka za krótka");
    }
    Aes256Gcm::new(key.into())
        .decrypt(Nonce::from_slice(&data[..12]), Payload { msg: &data[12..], aad })
        .map_err(|_| Error("AES-GCM: zły klucz albo uszkodzona ramka (InvalidTag)".into()))
}

fn hmac_sha256(key: &[u8], msg: &[u8]) -> [u8; 32] {
    let mut m = <Hmac<Sha256> as Mac>::new_from_slice(key).expect("HMAC dowolny klucz");
    m.update(msg);
    m.finalize().into_bytes().into()
}

/// `karmazyn_hsl._hkdf`: HKDF-SHA256 z solą "karmazyn-hsl-v1".
fn hsl_hkdf(ikm: &[u8], info: &[u8]) -> [u8; 32] {
    let mut out = [0u8; 32];
    Hkdf::<Sha256>::new(Some(b"karmazyn-hsl-v1"), ikm)
        .expand(info, &mut out)
        .expect("32 B");
    out
}

/// Klucz sesji ECDH: HKDF(shared, salt="karmazyn-phi-sync", info="handshake-v1").
fn ecdh_key(shared: &[u8]) -> [u8; 32] {
    let mut out = [0u8; 32];
    Hkdf::<Sha256>::new(Some(b"karmazyn-phi-sync"), shared)
        .expand(b"handshake-v1", &mut out)
        .expect("32 B");
    out
}

fn sha256(parts: &[&[u8]]) -> [u8; 32] {
    let mut h = Sha256::new();
    for p in parts {
        h.update(p);
    }
    h.finalize().into()
}

// ── tożsamość węzła ──────────────────────────────────────────────────────

fn env_nonempty(k: &str) -> Option<String> {
    std::env::var(k).ok().map(|v| v.trim().to_string()).filter(|v| !v.is_empty())
}

/// `cynober_paths.data_home()`.
pub fn data_home() -> PathBuf {
    if let Some(d) = env_nonempty("CYNOBER_DATA_HOME") {
        return PathBuf::from(d);
    }
    if let Some(l) = env_nonempty("LOCALAPPDATA") {
        return PathBuf::from(l).join("Cynober");
    }
    let home = env_nonempty("HOME").or_else(|| env_nonempty("USERPROFILE")).unwrap_or_else(|| "/".into());
    PathBuf::from(home).join(".local").join("share").join("cynober")
}

/// PSK i profil HSS z aktywnego profilu `client.json` (jak
/// `cynober_client_config.apply_profile_secrets`). Sekcja `server` nie jest
/// sekretem klienta. Brak pliku, zły JSON albo brak klucza = puste.
#[derive(Debug, Clone, PartialEq, Eq)]
struct ClientSecrets {
    psk: Option<String>,
    hss_profile: Option<String>,
}

fn text_field(v: &Value, key: &str) -> Option<String> {
    v.get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_string)
}

fn client_secrets_from_value(v: &Value) -> ClientSecrets {
    let Some(profiles) = v.get("profiles").and_then(Value::as_object) else {
        return ClientSecrets { psk: None, hss_profile: None };
    };
    let active = v.get("active").and_then(Value::as_str).unwrap_or("lokalny");
    let Some(profile) = profiles.get(active) else {
        return ClientSecrets { psk: None, hss_profile: None };
    };
    ClientSecrets {
        psk: text_field(profile, "psk"),
        hss_profile: text_field(profile, "hss_profile").map(|s| s.to_lowercase()),
    }
}

fn load_client_secrets(home: &Path) -> ClientSecrets {
    let empty = ClientSecrets { psk: None, hss_profile: None };
    let Ok(raw) = std::fs::read(home.join("client.json")) else {
        return empty;
    };
    let Ok(text) = std::str::from_utf8(&raw) else {
        return empty;
    };
    let Ok(v) = serde_json::from_str::<Value>(text) else {
        return empty;
    };
    client_secrets_from_value(&v)
}

fn nonempty(s: Option<&str>) -> Option<&str> {
    s.map(str::trim).filter(|s| !s.is_empty())
}

/// Środowisko wygrywa z plikiem. Puste (albo same białe znaki) = brak wartości.
fn pick<'a>(from_env: Option<&'a str>, from_file: Option<&'a str>) -> Option<&'a str> {
    nonempty(from_env).or(nonempty(from_file))
}

/// `load_or_create_node_id`: `node_` + 12 hex w `data_home/node_id`.
pub fn node_id() -> String {
    let path = data_home().join("node_id");
    if let Ok(s) = std::fs::read_to_string(&path) {
        let s = s.trim();
        if s.starts_with("node_") && s.len() == 17 {
            return s.to_string();
        }
    }
    let nid = format!("node_{}", hex(&random::<6>().unwrap_or([0; 6])));
    if let Some(d) = path.parent() {
        let _ = std::fs::create_dir_all(d);
    }
    let _ = std::fs::write(&path, &nid);
    nid
}

/// `load_phi2`: Φ² = SHA-256(KARM_PHI2 albo plik `data_home/phi2`, ≥ 32 B).
pub fn load_phi2() -> [u8; 32] {
    if let Some(env) = env_nonempty("KARM_PHI2") {
        let raw = if env.len() >= 64 { unhex(&env).unwrap_or_else(|_| env.clone().into_bytes()) } else { env.into_bytes() };
        return sha256(&[&raw]);
    }
    let path = data_home().join("phi2");
    if let Ok(d) = std::fs::read(&path) {
        if d.len() >= 32 {
            return sha256(&[&d]);
        }
    }
    let seed: [u8; 32] = random().unwrap_or([0; 32]);
    if let Some(d) = path.parent() {
        let _ = std::fs::create_dir_all(d);
    }
    let _ = std::fs::write(&path, seed);
    sha256(&[&seed])
}

/// `karmazyn_qkd.load_qkd_bytes`: KARM_QKD_SEED (hex ≥ 64 zn. albo SHA-256
/// tekstu), KARM_QKD_PATH / KARM_QKD_PIPE (hex ≥ 64 zn. albo SHA-256 bajtów).
pub fn load_qkd_seed() -> Result<Option<Vec<u8>>> {
    if let Some(t) = env_nonempty("KARM_QKD_SEED") {
        if t.len() >= 64 && t.chars().all(|c| c.is_ascii_hexdigit()) {
            return unhex(&t).map(Some);
        }
        return Ok(Some(sha256(&[t.as_bytes()]).to_vec()));
    }
    for k in ["KARM_QKD_PATH", "KARM_QKD_PIPE"] {
        if let Some(p) = env_nonempty(k) {
            let data = std::fs::read(&p)?;
            if data.is_empty() {
                return err(format!("pusty {k}"));
            }
            if k == "KARM_QKD_PATH" {
                if let Ok(text) = std::str::from_utf8(&data) {
                    let t = text.trim();
                    if t.len() >= 64 && t.chars().all(|c| c.is_ascii_hexdigit() || c.is_whitespace()) {
                        let h: String = t.split_whitespace().collect();
                        if h.len() >= 64 {
                            return unhex(&h[..64]).map(Some);
                        }
                    }
                }
            }
            return Ok(Some(sha256(&[&data]).to_vec()));
        }
    }
    Ok(None)
}

fn now_f64() -> f64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs_f64()).unwrap_or(0.0)
}

fn epoch_sec() -> u64 {
    env_nonempty("KARM_HSL_EPOCH_SEC").and_then(|v| v.parse().ok()).filter(|v| *v > 0).unwrap_or(3600)
}

pub fn current_epoch() -> u64 {
    (now_f64() as u64) / epoch_sec()
}

// ── HSL ──────────────────────────────────────────────────────────────────

fn hybrid_link_seed(shared: &[u8], qkd: Option<&[u8]>) -> Vec<u8> {
    match qkd {
        Some(q) if !q.is_empty() => {
            let mut ikm = q.to_vec();
            ikm.extend_from_slice(shared);
            hsl_hkdf(&ikm, b"hsl-hybrid-qkd-v1").to_vec()
        }
        _ => shared.to_vec(),
    }
}

/// `prism_target` z domyślnym zadaniem i pryzmatami.
fn prism_target(shared: &[u8], ca: &[u8; 32], cb: &[u8; 32], epoch: u64, qkd: Option<&[u8]>) -> [u8; 32] {
    // json.dumps({"task", "prisms"}, sort_keys=True, separators=(",", ":"))
    let prisms: Vec<String> = HSL_PRISMS.iter().map(|p| format!("{:?}", p)).collect();
    let ctx = format!("{{\"prisms\":[{}],\"task\":{:?}}}", prisms.join(","), HSL_TASK);
    let (lo, hi) = if ca <= cb { (ca, cb) } else { (cb, ca) };
    let mut m = hybrid_link_seed(shared, qkd);
    m.extend_from_slice(lo);
    m.extend_from_slice(hi);
    m.extend_from_slice(&epoch.to_be_bytes());
    m.extend_from_slice(ctx.as_bytes());
    hsl_hkdf(&m, b"hsl-prism")
}

fn build_aad(source: &str, target: &str, epoch: u64, direction: &str) -> [u8; 32] {
    let payload = format!("{source}\0{target}\0{HSL_TASK}\0{epoch}\0{direction}");
    sha256(&[b"hsl-aad-v1", payload.as_bytes()])
}

fn capability_token(s_target: &[u8; 32], label: &str) -> String {
    hex(&hmac_sha256(s_target, label.as_bytes()))
}

/// Łącze HSL po stronie klienta.
#[derive(Clone)]
pub struct HslLink {
    pub epoch: u64,
    s_target: [u8; 32],
    pub local_id: String,
    pub remote_id: String,
    pub qkd_hybrid: bool,
    shared: Vec<u8>,
    commit_local: [u8; 32],
    commit_remote: [u8; 32],
    qkd: Option<Vec<u8>>,
}

impl HslLink {
    /// Rotacja epoki jak `ensure_epoch` (KPC to lokalna kontrola w Pythonie,
    /// nie wpływa na klucze).
    fn ensure_epoch(&mut self) {
        let e = current_epoch();
        if e != self.epoch {
            self.epoch = e;
            self.s_target = prism_target(&self.shared, &self.commit_local, &self.commit_remote, e, self.qkd.as_deref());
        }
    }

    /// Klient: żądanie (klient→serwer), odpowiedź (serwer→klient) — DBase 4eca597.
    fn aad_request(&self) -> [u8; 32] {
        build_aad(&self.local_id, &self.remote_id, self.epoch, "req")
    }

    fn aad_response(&self) -> [u8; 32] {
        build_aad(&self.remote_id, &self.local_id, self.epoch, "resp")
    }

    fn frame_key(&self, aad: &[u8; 32]) -> [u8; 32] {
        let mut ikm = self.s_target.to_vec();
        ikm.extend_from_slice(aad);
        hsl_hkdf(&ikm, b"hsl-frame")
    }
}

/// Wynik handshake (do `session_info`).
#[derive(Debug, Clone)]
pub struct SessionInfo {
    pub crypto_mode: String,
    pub hss_profile: Option<String>,
    pub psk: bool,
    pub hsl: bool,
    pub qkd_hybrid: bool,
    pub epoch: Option<u64>,
    pub node_local: String,
    pub node_remote: String,
    pub remote_version: String,
}

/// Sesja RPC przez tunel HSS/ECDH + HSL.
pub struct Client {
    sock: TcpStream,
    key: [u8; 32],
    hsl: Option<HslLink>,
    pub info: SessionInfo,
}

fn caps_crypto(hss: Option<hss::Profile>) -> Vec<&'static str> {
    let mut c = vec!["ecdh"];
    if hss.is_some() {
        c.push("hss");
    }
    if let Some(force) = env_nonempty("CYNOBER_FORCE_CRYPTO") {
        match force.to_lowercase().as_str() {
            "ecdh" => return vec!["ecdh"],
            // wymuszony HSS tylko z obsługiwanym profilem; inaczej brak wspólnego trybu
            "hss" => return if hss.is_some() { vec!["hss"] } else { vec![] },
            _ => {}
        }
    }
    c
}

/// `select_crypto_mode` od strony klienta (bez trybu simple).
fn select_mode(local: &[&str], remote: &Value) -> Result<&'static str> {
    let remote: Vec<String> = remote
        .get("crypto")
        .and_then(Value::as_array)
        .map(|a| a.iter().filter_map(|x| x.as_str().map(str::to_string)).collect())
        .unwrap_or_default();
    let min = env_nonempty("CYNOBER_MIN_CRYPTO").unwrap_or_default().to_lowercase();
    let order: &[&'static str] = if min == "hss" { &["hss"] } else { &["hss", "ecdh"] };
    for m in order {
        if local.contains(m) && remote.iter().any(|r| r == m) {
            return Ok(m);
        }
    }
    err(format!(
        "Brak wspólnego trybu krypto: lokalny={local:?} zdalny={remote:?} (simple nieobsługiwany; HSS natywnie: KARM_HSS_PROFILE=standard|production)"
    ))
}

fn validate_remote(local_ts: f64, remote: &Value) -> Result<()> {
    let ts = remote.get("ts").and_then(Value::as_f64).unwrap_or(0.0);
    if ts <= 0.0 {
        return err("Anty-replay: brak znacznika czasu w caps zdalnych");
    }
    if (local_ts - ts).abs() > REPLAY_WINDOW_SEC {
        return err(format!("Anty-replay: różnica zegarów {:.0}s > {REPLAY_WINDOW_SEC:.0}s", (local_ts - ts).abs()));
    }
    if remote.get("session_id").and_then(Value::as_str).unwrap_or("").is_empty() {
        return err("Anty-replay: brak session_id w caps zdalnych");
    }
    Ok(())
}

fn send_hsl(s: &mut TcpStream, key: &[u8; 32], v: &Value, aad: &[u8]) -> Result<()> {
    let enc = seal(key, &to_sorted_json(v), aad)?;
    let mut f = HSL_MAGIC.to_vec();
    f.extend(enc);
    send_frame(s, &f)
}

fn recv_hsl(s: &mut TcpStream, key: &[u8; 32], aad: &[u8]) -> Result<Value> {
    let raw = recv_frame(s)?;
    let plain = match raw.strip_prefix(HSL_MAGIC) {
        Some(enc) => open(key, enc, aad)?,
        None => raw, // stary peer: jawny JSON
    };
    serde_json::from_slice(&plain).map_err(|e| Error(format!("HSL JSON: {e}")))
}

impl Client {
    /// Połączenie + handshake + HSL. `timeout` dotyczy odczytów i zapisów.
    pub fn connect(host: &str, port: u16, timeout: Duration) -> Result<Client> {
        let addr = (host, port)
            .to_socket_addrs()
            .map_err(|e| Error(format!("{host}:{port}: {e}")))?
            .next()
            .ok_or_else(|| Error(format!("{host}:{port}: brak adresu")))?;
        let mut s = TcpStream::connect_timeout(&addr, Duration::from_secs(10))
            .map_err(|e| Error(format!("Nie można połączyć z {host}:{port}: {e}")))?;
        s.set_read_timeout(Some(timeout))?;
        s.set_write_timeout(Some(timeout))?;
        s.set_nodelay(true)?;

        // Plik obok master.key wypełnia puste KARM_PSK / KARM_HSS_PROFILE.
        // Brak pliku i puste środowisko zostawiają ECDH (`proto` nie jest HSS).
        let env_psk = std::env::var("KARM_PSK").ok();
        let env_hss = std::env::var("KARM_HSS_PROFILE").ok();
        let file = load_client_secrets(&data_home());
        let psk = pick(env_psk.as_deref(), file.psk.as_deref())
            .unwrap_or("")
            .to_string();
        let hss_profile = hss::profile_from_name(
            pick(env_hss.as_deref(), file.hss_profile.as_deref()).unwrap_or(""),
        );
        let crypto = caps_crypto(hss_profile);
        let local_ts = now_f64();
        let session_id = hex(&random::<8>()?);
        let local_id = node_id();
        let local_caps = json!({
            "version": PROTO_VERSION,
            "crypto": crypto,
            "hsl": HSL_VERSION,
            "node_id": local_id,
            "ts": local_ts,
            "session_id": session_id,
            "features": [],
        });

        // Faza 0: serwer mówi pierwszy
        let remote_caps = recv_json(&mut s)?;
        if let Some(e) = remote_caps.get("error") {
            return err(format!("Serwer: {e}"));
        }
        send_json(&mut s, &local_caps)?;
        let remote_ver = remote_caps.get("version").and_then(Value::as_str).unwrap_or("").to_string();
        if !SUPPORTED_VERSIONS.contains(&remote_ver.as_str()) || remote_ver == "Cynober-Secure-1.0" {
            return err(format!("Niezgodna wersja protokołu: {remote_ver:?}"));
        }
        validate_remote(local_ts, &remote_caps)?;

        // Faza 1: klucz sesji
        let mode = select_mode(&crypto, &remote_caps)?;
        let mut key = match mode {
            "hss" => {
                let p = hss_profile.expect("hss ogłoszony tylko z profilem");
                let (init, pk) = hss::Initiator::new(p).map_err(Error)?;
                send_json(&mut s, &json!({"mode": "hss", "pubkey": hex(&pk), "hss_profile": p.name}))?;
                let resp = recv_json(&mut s)?;
                if let Some(e) = resp.get("error") {
                    return err(format!("Serwer: {e}"));
                }
                let ack = unhex(resp.get("ack").and_then(Value::as_str).unwrap_or(""))?;
                init.finalize(&ack).map_err(Error)?
            }
            _ => {
                let secret = x25519_dalek::StaticSecret::from(random::<32>()?);
                let public = x25519_dalek::PublicKey::from(&secret);
                send_json(&mut s, &json!({"mode": "ecdh", "pubkey": hex(public.as_bytes())}))?;
                let resp = recv_json(&mut s)?;
                if let Some(e) = resp.get("error") {
                    return err(format!("Serwer: {e}"));
                }
                let pb: [u8; 32] = unhex(resp.get("pubkey").and_then(Value::as_str).unwrap_or(""))?
                    .try_into()
                    .map_err(|_| Error("ECDH: zły klucz publiczny serwera".into()))?;
                let shared = secret.diffie_hellman(&x25519_dalek::PublicKey::from(pb));
                ecdh_key(shared.as_bytes())
            }
        };
        if !psk.is_empty() {
            key = sha256(&[&key, psk.as_bytes()]);
        }

        // Faza 2: HSL (1.2 po obu stronach i flaga hsl)
        let remote_id = remote_caps.get("node_id").and_then(Value::as_str).unwrap_or("unknown").to_string();
        let hsl = if remote_ver == PROTO_VERSION && remote_caps.get("hsl").is_some_and(|h| !h.is_null() && h != false) {
            Some(Self::hsl_link(&mut s, &key, &local_caps, &remote_caps, &local_id, &remote_id)?)
        } else {
            None
        };

        let info = SessionInfo {
            crypto_mode: mode.to_string(),
            hss_profile: (mode == "hss").then(|| hss_profile.unwrap().name.to_string()),
            psk: !psk.is_empty(),
            hsl: hsl.is_some(),
            qkd_hybrid: hsl.as_ref().is_some_and(|h| h.qkd_hybrid),
            epoch: hsl.as_ref().map(|h| h.epoch),
            node_local: local_id,
            node_remote: remote_id,
            remote_version: remote_ver,
        };
        Ok(Client { sock: s, key, hsl, info })
    }

    fn hsl_link(
        s: &mut TcpStream,
        key: &[u8; 32],
        local_caps: &Value,
        remote_caps: &Value,
        local_id: &str,
        remote_id: &str,
    ) -> Result<HslLink> {
        let phi2 = load_phi2();
        let qkd = load_qkd_seed()?;
        let epoch = current_epoch();
        let mut parts: Vec<String> = [
            local_caps.get("session_id"),
            remote_caps.get("session_id"),
            local_caps.get("node_id"),
            remote_caps.get("node_id"),
        ]
        .iter()
        .map(|v| v.and_then(Value::as_str).unwrap_or("").to_string())
        .collect();
        parts.sort();
        let nonce = sha256(&[parts.join("|").as_bytes()]);
        let commit_local = sha256(&[b"hsl-commit-v1", &phi2, &nonce]);
        let fp_local = qkd.as_ref().map(|q| hex(&sha256(&[b"qkd-fp-v1", q]))[..16].to_string());

        let mut msg = json!({
            "type": "hsl_link",
            "version": HSL_VERSION,
            "epoch": epoch,
            "node_id": local_id,
            "commit": hex(&commit_local),
        });
        if let Some(fp) = &fp_local {
            msg["qkd_fp"] = Value::from(fp.clone());
        }
        send_hsl(s, key, &msg, AAD_LINK)?;
        let remote = recv_hsl(s, key, AAD_LINK)?;
        if remote.get("type").and_then(Value::as_str) != Some("hsl_link") {
            return err("HSL: oczekiwano hsl_link, otrzymano inny typ ramki");
        }
        if remote.get("version").and_then(Value::as_str) != Some(HSL_VERSION) {
            return err(format!("HSL: niezgodna wersja {:?}", remote.get("version")));
        }
        let remote_epoch = remote.get("epoch").and_then(Value::as_i64).unwrap_or(-1);
        if remote_epoch != epoch as i64 {
            return err(format!("HSL: rozjazd epok {epoch} vs {remote_epoch} — brak rezonansu sesji"));
        }
        if remote.get("node_id").and_then(Value::as_str) != Some(remote_id) {
            return err("HSL: node_id w linku nie zgadza się z caps");
        }
        let commit_remote: [u8; 32] = unhex(remote.get("commit").and_then(Value::as_str).unwrap_or(""))?
            .try_into()
            .map_err(|_| Error("HSL: niepoprawny commit zdalny".into()))?;
        let fp_remote = remote.get("qkd_fp").and_then(Value::as_str);
        match (&fp_local, fp_remote) {
            (None, None) => {}
            (Some(a), Some(b)) if a == b => {}
            (Some(_), Some(_)) => return err("HSL: rozjazd seeda QKD — fingerprint nie zgadza się"),
            _ => return err("HSL: rozjazd trybu QKD — jedna strona ma KARM_QKD_SEED, druga nie"),
        }

        let s_target = prism_target(key, &commit_local, &commit_remote, epoch, qkd.as_deref());
        send_hsl(s, key, &json!({"type": "hsl_cap", "cap": capability_token(&s_target, "establish")}), AAD_CAP)?;
        let cap = recv_hsl(s, key, AAD_CAP)?;
        if cap.get("type").and_then(Value::as_str) != Some("hsl_cap") {
            return err("HSL: oczekiwano hsl_cap");
        }
        let expected = capability_token(&s_target, "establish");
        let got = cap.get("cap").and_then(Value::as_str).unwrap_or("");
        // porównanie w stałym czasie
        let same = expected.len() == got.len()
            && expected.bytes().zip(got.bytes()).fold(0u8, |acc, (a, b)| acc | (a ^ b)) == 0;
        if !same {
            return err("HSL: brak rezonansu — zdalny link_cap nieprawidłowy");
        }
        Ok(HslLink {
            epoch,
            s_target,
            local_id: local_id.to_string(),
            remote_id: remote_id.to_string(),
            qkd_hybrid: qkd.is_some(),
            shared: key.to_vec(),
            commit_local,
            commit_remote,
            qkd,
        })
    }

    /// Jedno zapytanie KarminQL. Zwraca JSON odpowiedzi (`{"results": [...]}`
    /// albo `{"error": ...}`).
    pub fn query(&mut self, text: &str) -> Result<Value> {
        let mut req = json!({"query": text});
        if let Some(h) = self.hsl.as_mut() {
            h.ensure_epoch();
            req["cap"] = Value::from(capability_token(&h.s_target, CAP_RPC_QUERY));
            req["epoch"] = Value::from(h.epoch);
        }
        let mut z = flate2::write::ZlibEncoder::new(Vec::new(), flate2::Compression::new(6));
        z.write_all(&serde_json::to_vec(&req).expect("JSON"))?;
        let clear = z.finish()?;
        let enc = match &self.hsl {
            Some(h) => {
                let aad = h.aad_request();
                seal(&h.frame_key(&aad), &clear, &aad)?
            }
            None => seal(&self.key, &clear, b"")?,
        };
        send_frame(&mut self.sock, &enc)?;

        let resp = recv_frame(&mut self.sock)?;
        if resp.is_empty() {
            return err("Pusta odpowiedź — serwer zamknął tunel");
        }
        let raw = match &self.hsl {
            Some(h) => {
                let aad = h.aad_response();
                open(&h.frame_key(&aad), &resp, &aad)?
            }
            None => open(&self.key, &resp, b"")?,
        };
        let payload = match raw.first() {
            Some(0x02) => return err("Oczekiwano ramki RPC, otrzymano KAFS"),
            Some(0x01) => &raw[1..],
            _ => &raw[..],
        };
        let mut out = Vec::new();
        flate2::read::ZlibDecoder::new(payload)
            .read_to_end(&mut out)
            .map_err(|e| Error(format!("Uszkodzona odpowiedź RPC: {e}")))?;
        serde_json::from_slice(&out).map_err(|e| Error(format!("Uszkodzona odpowiedź RPC: {e}")))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sorted_json_matches_python_sort_keys() {
        let v = json!({"version": "x", "crypto": ["ecdh"], "a": {"z": 1, "b": true}});
        assert_eq!(
            String::from_utf8(to_sorted_json(&v)).unwrap(),
            r#"{"a": {"b": true, "z": 1}, "crypto": ["ecdh"], "version": "x"}"#
        );
    }

    #[test]
    fn hsl_kdf_vectors_from_python() {
        // karmazyn_hsl.prism_target(b"\xab"*32, link_commit(b"\x01"*32, b"n"),
        //   link_commit(b"\x02"*32, b"n"), 1) — wartość sprawdzona w teście krzyżowym;
        // tu tylko symetria i zależność od epoki
        let ca = sha256(&[b"hsl-commit-v1", &[1u8; 32], b"n"]);
        let cb = sha256(&[b"hsl-commit-v1", &[2u8; 32], b"n"]);
        let k = [0xabu8; 32];
        assert_eq!(prism_target(&k, &ca, &cb, 1, None), prism_target(&k, &cb, &ca, 1, None));
        assert_ne!(prism_target(&k, &ca, &cb, 1, None), prism_target(&k, &ca, &cb, 2, None));
        assert_ne!(prism_target(&k, &ca, &cb, 1, None), prism_target(&k, &ca, &cb, 1, Some(&[9u8; 32])));
    }

    #[test]
    fn seal_open_roundtrip_and_aad() {
        let k = [7u8; 32];
        let c = seal(&k, b"dane", b"aad").unwrap();
        assert_eq!(open(&k, &c, b"aad").unwrap(), b"dane");
        assert!(open(&k, &c, b"inne").is_err());
    }

    fn sample_client_json() -> Value {
        json!({
            "active": "lokalny",
            "profiles": {
                "lokalny": {"psk": "  sekret-sieci  ", "hss_profile": " Standard "},
                "inny": {"psk": "nie-ten", "hss_profile": "production"}
            },
            "server": {"psk": "serwer", "hss_profile": "production"}
        })
    }

    #[test]
    fn client_json_active_profile_supplies_psk_and_hss() {
        let s = client_secrets_from_value(&sample_client_json());
        assert_eq!(s.psk.as_deref(), Some("sekret-sieci"));
        assert_eq!(s.hss_profile.as_deref(), Some("standard"));
        assert_eq!(pick(None, s.psk.as_deref()), Some("sekret-sieci"));
        let prof = hss::profile_from_name(pick(None, s.hss_profile.as_deref()).unwrap_or(""));
        assert_eq!(prof.unwrap().name, "standard");
    }

    #[test]
    fn env_wins_and_proto_stays_ecdh() {
        let s = client_secrets_from_value(&json!({
            "active": "lokalny",
            "profiles": {"lokalny": {"psk": "z-pliku", "hss_profile": "proto"}}
        }));
        assert_eq!(pick(Some("z-env"), s.psk.as_deref()), Some("z-env"));
        assert_eq!(pick(Some("   "), s.psk.as_deref()), Some("z-pliku"));
        assert!(hss::profile_from_name("proto").is_none());
        assert!(hss::profile_from_name("").is_none());
        assert_eq!(hss::profile_from_name("production").unwrap().name, "production");
    }

    #[test]
    fn missing_profile_does_not_borrow_server_or_another_profile() {
        let foreign = client_secrets_from_value(&json!({
            "active": "biuro",
            "profiles": {"dom": {"psk": "cudzy", "hss_profile": "standard"}},
            "server": {"psk": "serwer", "hss_profile": "production"}
        }));
        assert_eq!(foreign, ClientSecrets { psk: None, hss_profile: None });
        let no_hss = client_secrets_from_value(&json!({
            "profiles": {"lokalny": {"psk": ""}}
        }));
        assert!(no_hss.psk.is_none());
        assert!(no_hss.hss_profile.is_none());
        assert!(hss::profile_from_name(pick(None, no_hss.hss_profile.as_deref()).unwrap_or("")).is_none());
    }

    #[test]
    fn secrets_file_beside_master_key_and_absent_file_is_ecdh() {
        let dir = std::env::temp_dir().join(format!("cynober_secrets_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let missing = load_client_secrets(&dir);
        assert_eq!(missing, ClientSecrets { psk: None, hss_profile: None });
        assert_eq!(pick(None, missing.psk.as_deref()).unwrap_or(""), "");
        assert!(hss::profile_from_name(pick(None, missing.hss_profile.as_deref()).unwrap_or("")).is_none());

        std::fs::write(dir.join("master.key"), [1u8; 32]).unwrap();
        std::fs::write(
            dir.join("client.json"),
            br#"{"active":"lokalny","profiles":{"lokalny":{"psk":"z-dysku"}}}"#,
        )
        .unwrap();
        let s = load_client_secrets(&dir);
        assert_eq!(s.psk.as_deref(), Some("z-dysku"));
        assert!(s.hss_profile.is_none());

        std::fs::write(dir.join("client.json"), b"{not json").unwrap();
        assert_eq!(
            load_client_secrets(&dir),
            ClientSecrets { psk: None, hss_profile: None }
        );
        let _ = std::fs::remove_dir_all(&dir);
    }
}
