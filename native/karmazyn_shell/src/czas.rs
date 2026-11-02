//! Protokół sprawdzania czasu przy starcie.
//!
//! 1. Stempel na dysku: ostatni zaakceptowany czas uniksowy
//!    (`<data_home>/clock.stamp`, albo `KARMAZYN_CLOCK=<ścieżka>`).
//!    Cofnięty zegar nie przesuwa stempla. `KARMAZYN_CLOCK=none` pomija stempel.
//! 2. Gdy jest `KARMAZYN_NTP=<host[:port]>`, jedno zapytanie SNTP (RFC 4330,
//!    port 123). Rozjazd ponad 2 s jest ostrzeżeniem. Zegar systemu zostaje:
//!    to sprawdzenie, nie krok.

use std::io::{ErrorKind, Write};
use std::net::{ToSocketAddrs, UdpSocket};
use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

/// Sekundy, o które zegar może zostać w tyle za stemplem (szybki restart).
pub const SLACK_SECS: u64 = 2;
/// Rozjazd SNTP, od którego linia startowa jest ostrzeżeniem.
pub const SKEW_MS: i64 = 2_000;
const NTP_UNIX: u64 = 2_208_988_800;
const TIMEOUT: Duration = Duration::from_secs(2);

#[derive(Clone, Copy)]
pub enum StampIn {
    Missing,
    Bad,
    At(u64),
}

pub struct StampOut {
    pub ok: bool,
    pub detail: String,
    /// Nowy stempel do zapisania. `None` = nie ruszaj pliku.
    pub write: Option<u64>,
}

pub struct Report {
    pub ok: bool,
    pub detail: String,
}

pub fn judge_stamp(now: u64, prev: StampIn) -> StampOut {
    match prev {
        StampIn::Missing => StampOut {
            ok: true,
            detail: "lokalny, pierwszy stempel".into(),
            write: Some(now),
        },
        StampIn::Bad => StampOut {
            ok: false,
            detail: "stempel uszkodzony".into(),
            write: None,
        },
        StampIn::At(at) if now + SLACK_SECS < at => StampOut {
            ok: false,
            detail: format!("cofnięty o {}s wobec stempla", at - now),
            write: None,
        },
        StampIn::At(at) => StampOut {
            ok: true,
            detail: "lokalny, stempel zgodny".into(),
            write: (now >= at).then_some(now),
        },
    }
}

pub fn offset_detail(host: &str, offset_ms: i64) -> (bool, String) {
    if offset_ms.abs() > SKEW_MS {
        (
            false,
            format!("SNTP {host} offset {offset_ms:+} ms (rozjazd, zegar zostaje)"),
        )
    } else {
        (true, format!("SNTP {host} offset {offset_ms:+} ms"))
    }
}

/// Składa wynik stempla i opcjonalnego SNTP. `host` jest w tekście SNTP.
pub fn compose(stamp: Option<StampOut>, ntp: Option<Result<i64, String>>, host: Option<&str>) -> Report {
    let mut ok = true;
    let mut parts = Vec::new();
    if let Some(host) = host {
        match ntp {
            Some(Ok(ms)) => {
                let (good, text) = offset_detail(host, ms);
                ok &= good;
                parts.push(text);
            }
            Some(Err(e)) => {
                ok = false;
                parts.push(format!("SNTP {host}: {e}"));
            }
            None => {}
        }
    }
    if let Some(st) = stamp {
        ok &= st.ok;
        parts.push(st.detail);
    }
    if parts.is_empty() {
        parts.push("lokalny".into());
    }
    Report {
        ok,
        detail: parts.join("; "),
    }
}

pub fn check_from_env() -> Report {
    let ntp = nonempty("KARMAZYN_NTP");
    let stamp = stamp_path_from_env();
    check_with(ntp.as_deref(), stamp.as_deref(), SystemTime::now(), query_sntp_bounded)
}

pub fn check_with(
    ntp: Option<&str>,
    stamp: Option<&Path>,
    now: SystemTime,
    query: impl FnOnce(&str) -> Result<i64, String>,
) -> Report {
    let now_sec = match now.duration_since(UNIX_EPOCH) {
        Ok(d) => d.as_secs(),
        Err(_) => {
            return Report {
                ok: false,
                detail: "zegar przed epoką uniksa".into(),
            };
        }
    };
    let (stamp_out, stamp_err) = match stamp {
        None => (None, None),
        Some(path) => match read_stamp(path) {
            Ok(prev) => {
                let judged = judge_stamp(now_sec, prev);
                if let Some(sec) = judged.write {
                    if let Err(e) = write_stamp(path, sec) {
                        return Report {
                            ok: false,
                            detail: format!("{}; stempel: {e}", judged.detail),
                        };
                    }
                }
                (Some(judged), None)
            }
            Err(e) => (None, Some(e)),
        },
    };
    if let Some(e) = stamp_err {
        let mut report = compose(None, ntp.map(query), ntp);
        report.ok = false;
        let extra = format!("stempel: {e}");
        report.detail = if report.detail == "lokalny" {
            extra
        } else {
            format!("{}; {extra}", report.detail)
        };
        return report;
    }
    let ntp_result = ntp.map(query);
    compose(stamp_out, ntp_result, ntp)
}

fn stamp_path_from_env() -> Option<PathBuf> {
    match std::env::var("KARMAZYN_CLOCK") {
        Ok(v) if v.trim().is_empty() || v.trim() == "none" => None,
        Ok(v) => Some(PathBuf::from(v.trim())),
        Err(_) => Some(karmazyn_kafd::cipher::data_home().join("clock.stamp")),
    }
}

fn nonempty(key: &str) -> Option<String> {
    std::env::var(key)
        .ok()
        .map(|v| v.trim().to_string())
        .filter(|v| !v.is_empty())
}

fn read_stamp(path: &Path) -> Result<StampIn, String> {
    match std::fs::read_to_string(path) {
        Ok(s) => match s.trim().parse::<u64>() {
            Ok(n) => Ok(StampIn::At(n)),
            Err(_) => Ok(StampIn::Bad),
        },
        Err(e) if e.kind() == ErrorKind::NotFound => Ok(StampIn::Missing),
        Err(e) => Err(format!("{}: {e}", path.display())),
    }
}

fn write_stamp(path: &Path, sec: u64) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        if !parent.as_os_str().is_empty() {
            std::fs::create_dir_all(parent).map_err(|e| format!("{}: {e}", parent.display()))?;
        }
    }
    let mut opts = std::fs::OpenOptions::new();
    opts.write(true).create(true).truncate(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        opts.mode(0o600);
    }
    let mut f = opts
        .open(path)
        .map_err(|e| format!("{}: {e}", path.display()))?;
    writeln!(f, "{sec}").map_err(|e| e.to_string())?;
    f.sync_all().map_err(|e| e.to_string())?;
    Ok(())
}

pub fn server_addr(host: &str) -> String {
    match host.rsplit_once(':') {
        Some((_, port)) if !port.is_empty() && port.parse::<u16>().is_ok() => host.to_string(),
        _ => format!("{host}:123"),
    }
}

/// Pakiet klienta: LI=0, VN=4, tryb 3. Znacznik nadania na offsetcie 40.
pub fn request_packet(t1: u64) -> [u8; 48] {
    let mut pkt = [0u8; 48];
    pkt[0] = 0x23;
    pkt[40..48].copy_from_slice(&t1.to_be_bytes());
    pkt
}

/// Z odpowiedzi serwera: (czas odbioru T2, czas nadania T3). `t1` musi wrócić
/// jako znacznik pochodzenia.
pub fn read_reply(buf: &[u8], t1: u64) -> Result<(u64, u64), String> {
    if buf.len() < 48 {
        return Err("krótka odpowiedź".into());
    }
    if buf[0] & 0x07 != 4 {
        return Err("to nie odpowiedź serwera".into());
    }
    if buf[1] == 0 {
        let code = String::from_utf8_lossy(&buf[12..16]);
        let code = code.trim_end_matches(char::from(0));
        return Err(format!("kiss-o'-death {code}"));
    }
    let origin = u64::from_be_bytes(buf[24..32].try_into().unwrap());
    if origin != t1 {
        return Err("cudza odpowiedź".into());
    }
    let t2 = u64::from_be_bytes(buf[32..40].try_into().unwrap());
    let t3 = u64::from_be_bytes(buf[40..48].try_into().unwrap());
    if t3 == 0 {
        return Err("pusty znacznik nadania".into());
    }
    Ok((t2, t3))
}

pub fn unix_to_ntp(t: SystemTime) -> u64 {
    let d = t.duration_since(UNIX_EPOCH).unwrap_or_default();
    let sec = d.as_secs() + NTP_UNIX;
    let frac = (u64::from(d.subsec_nanos()) << 32) / 1_000_000_000;
    (sec << 32) | frac
}

fn ntp_us(ntp: u64) -> i128 {
    let sec = i128::from(ntp >> 32);
    let frac = i128::from(ntp & 0xffff_ffff);
    sec * 1_000_000 + (frac * 1_000_000) / 0x1_0000_0000
}

/// Połowa ((T2−T1) + (T3−T4)), w milisekundach.
pub fn offset_ms(t1: u64, t2: u64, t3: u64, t4: u64) -> i64 {
    let off_us = ((ntp_us(t2) - ntp_us(t1)) + (ntp_us(t3) - ntp_us(t4))) / 2;
    (off_us / 1000) as i64
}

pub fn query_sntp(host: &str, timeout: Duration) -> Result<i64, String> {
    let addr = server_addr(host);
    let sock = UdpSocket::bind("0.0.0.0:0").map_err(|e| format!("gniazdo: {e}"))?;
    sock.set_read_timeout(Some(timeout)).map_err(|e| e.to_string())?;
    sock.set_write_timeout(Some(timeout)).map_err(|e| e.to_string())?;
    let dest = addr
        .to_socket_addrs()
        .map_err(|e| e.to_string())?
        .next()
        .ok_or_else(|| format!("{addr}: brak adresu"))?;
    let t1 = unix_to_ntp(SystemTime::now());
    sock.send_to(&request_packet(t1), dest)
        .map_err(|e| format!("zapis: {e}"))?;
    let mut buf = [0u8; 128];
    let (n, _) = sock.recv_from(&mut buf).map_err(|e| {
        if e.kind() == ErrorKind::TimedOut || e.kind() == ErrorKind::WouldBlock {
            "brak odpowiedzi".to_string()
        } else {
            format!("odczyt: {e}")
        }
    })?;
    let t4 = unix_to_ntp(SystemTime::now());
    let (t2, t3) = read_reply(&buf[..n], t1)?;
    Ok(offset_ms(t1, t2, t3, t4))
}

pub fn query_sntp_bounded(host: &str) -> Result<i64, String> {
    let host = host.to_string();
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::spawn(move || {
        let _ = tx.send(query_sntp(&host, TIMEOUT));
    });
    match rx.recv_timeout(TIMEOUT + Duration::from_millis(500)) {
        Ok(r) => r,
        Err(std::sync::mpsc::RecvTimeoutError::Timeout) => Err("przekroczony czas".into()),
        Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => Err("sprawdzenie przerwane".into()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stamp_first_match_and_rollback() {
        let first = judge_stamp(1_700, StampIn::Missing);
        assert!(first.ok);
        assert_eq!(first.write, Some(1_700));
        assert_eq!(first.detail, "lokalny, pierwszy stempel");

        let ok = judge_stamp(1_800, StampIn::At(1_700));
        assert!(ok.ok);
        assert_eq!(ok.write, Some(1_800));

        let slack = judge_stamp(1_699, StampIn::At(1_700));
        assert!(slack.ok);
        assert_eq!(slack.write, None);

        let back = judge_stamp(1_000, StampIn::At(1_700));
        assert!(!back.ok);
        assert_eq!(back.write, None);
        assert_eq!(back.detail, "cofnięty o 700s wobec stempla");

        assert!(!judge_stamp(1, StampIn::Bad).ok);
    }

    #[test]
    fn compose_joins_sntp_and_stamp() {
        let stamp = judge_stamp(10, StampIn::At(10));
        let report = compose(Some(stamp), Some(Ok(3)), Some("10.0.2.2"));
        assert!(report.ok);
        assert_eq!(
            report.detail,
            "SNTP 10.0.2.2 offset +3 ms; lokalny, stempel zgodny"
        );
        let skew = compose(None, Some(Ok(5_000)), Some("pool.ntp.org"));
        assert!(!skew.ok);
        assert!(skew.detail.contains("rozjazd"));
        let down = compose(None, Some(Err("brak odpowiedzi".into())), Some("pool.ntp.org"));
        assert!(!down.ok);
        assert_eq!(down.detail, "SNTP pool.ntp.org: brak odpowiedzi");
        assert_eq!(compose(None, None, None).detail, "lokalny");
    }

    #[test]
    fn sntp_packet_and_offset() {
        let t1 = unix_to_ntp(UNIX_EPOCH + Duration::from_secs(1_700_000_000));
        let pkt = request_packet(t1);
        assert_eq!(pkt[0], 0x23);
        assert_eq!(u64::from_be_bytes(pkt[40..48].try_into().unwrap()), t1);

        let sec = 1u64 << 32;
        assert_eq!(offset_ms(0, sec, sec, 0), 1000);
        assert_eq!(offset_ms(sec, 0, 0, sec), -1000);
        assert_eq!(offset_ms(sec, sec, sec, sec), 0);

        let mut reply = [0u8; 48];
        reply[0] = 0x24;
        reply[1] = 2;
        reply[24..32].copy_from_slice(&t1.to_be_bytes());
        reply[32..40].copy_from_slice(&sec.to_be_bytes());
        reply[40..48].copy_from_slice(&(sec + 1).to_be_bytes());
        assert_eq!(read_reply(&reply, t1).unwrap(), (sec, sec + 1));
        reply[0] = 0x23;
        assert!(read_reply(&reply, t1).is_err());
        reply[0] = 0x24;
        assert!(read_reply(&reply, t1 + 1).is_err());
        assert!(read_reply(&reply[..20], t1).is_err());
        reply[1] = 0;
        reply[12..16].copy_from_slice(b"RATE");
        assert_eq!(read_reply(&reply, t1).unwrap_err(), "kiss-o'-death RATE");
        reply[1] = 2;
        reply[40..48].fill(0);
        assert!(read_reply(&reply, t1).is_err());
        assert_eq!(server_addr("10.0.2.2"), "10.0.2.2:123");
        assert_eq!(server_addr("10.0.2.2:123"), "10.0.2.2:123");
    }

    #[test]
    fn stamp_file_roundtrip_without_network() {
        let dir = std::env::temp_dir().join(format!("kczas-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let path = dir.join("clock.stamp");
        let now = UNIX_EPOCH + Duration::from_secs(1_700_000_100);
        let first = check_with(None, Some(&path), now, |_| unreachable!());
        assert!(first.ok);
        assert_eq!(first.detail, "lokalny, pierwszy stempel");
        assert_eq!(std::fs::read_to_string(&path).unwrap().trim(), "1700000100");

        let later = check_with(None, Some(&path), now + Duration::from_secs(30), |_| unreachable!());
        assert!(later.ok);
        assert_eq!(std::fs::read_to_string(&path).unwrap().trim(), "1700000130");

        let back = check_with(None, Some(&path), now, |_| unreachable!());
        assert!(!back.ok);
        assert!(back.detail.contains("cofnięty"));
        assert_eq!(std::fs::read_to_string(&path).unwrap().trim(), "1700000130");

        let skew = check_with(Some("10.0.2.2"), Some(&path), now + Duration::from_secs(40), |_| {
            Ok(9_000)
        });
        assert!(!skew.ok);
        assert!(skew.detail.contains("rozjazd"));
        let _ = std::fs::remove_dir_all(&dir);
    }
}
