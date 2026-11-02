//! Dziennik startu i poleceń. Pamięć zawsze; plik, gdy da się go otworzyć.
//!
//! `KARMAZYN_LOG=<ścieżka>` wskazuje plik. `none` zostawia samą pamięć.
//! Bez zmiennej: `<data_home>/log/karmazyn.log` (na płycie `/data/cynober`,
//! po montażu dysku). Dziennik jest wspólny z wątkiem nadzoru, więc stan
//! trzyma `Mutex`.

use std::collections::VecDeque;
use std::fs::{File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::{Mutex, MutexGuard};
use std::time::{SystemTime, UNIX_EPOCH};

const CAP: usize = 500;

struct Entry {
    unix_ms: u64,
    source: String,
    message: String,
}

struct LogInner {
    entries: VecDeque<Entry>,
    file: Option<File>,
    path: Option<PathBuf>,
    file_error: Option<String>,
}

pub struct Log {
    inner: Mutex<LogInner>,
}

fn lock(inner: &Mutex<LogInner>) -> MutexGuard<'_, LogInner> {
    inner.lock().unwrap_or_else(|e| e.into_inner())
}

impl Log {
    pub fn memory() -> Self {
        Log {
            inner: Mutex::new(LogInner {
                entries: VecDeque::new(),
                file: None,
                path: None,
                file_error: None,
            }),
        }
    }

    /// Otwiera plik według środowiska. Błąd pliku zostawia dziennik w pamięci.
    pub fn bind_from_env(&self) {
        {
            let g = lock(&self.inner);
            if g.path.is_some() || g.file_error.is_some() {
                return;
            }
        }
        let path = match std::env::var("KARMAZYN_LOG") {
            Ok(v) if v.trim().is_empty() || v.trim() == "none" => return,
            Ok(v) => PathBuf::from(v.trim()),
            Err(_) => karmazyn_kafd::cipher::data_home().join("log").join("karmazyn.log"),
        };
        if let Err(e) = self.attach_path(&path) {
            lock(&self.inner).file_error = Some(e);
        }
    }

    pub fn attach_path(&self, path: &Path) -> Result<(), String> {
        if let Some(parent) = path.parent() {
            if !parent.as_os_str().is_empty() {
                std::fs::create_dir_all(parent)
                    .map_err(|e| format!("{}: {e}", parent.display()))?;
            }
        }
        let mut opts = OpenOptions::new();
        opts.create(true).append(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            opts.mode(0o600);
        }
        let file = opts
            .open(path)
            .map_err(|e| format!("{}: {e}", path.display()))?;
        let mut g = lock(&self.inner);
        g.file = Some(file);
        g.path = Some(path.to_path_buf());
        g.file_error = None;
        Ok(())
    }

    pub fn record(&self, source: &str, message: &str) {
        let message = message.replace(['\n', '\r'], " ");
        let unix_ms = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0);
        let line = format_line(unix_ms, source, &message);
        let mut g = lock(&self.inner);
        if let Some(file) = g.file.as_mut() {
            let _ = writeln!(file, "{line}");
            let _ = file.flush();
        }
        if g.entries.len() >= CAP {
            g.entries.pop_front();
        }
        g.entries.push_back(Entry {
            unix_ms,
            source: source.to_string(),
            message,
        });
    }

    /// `(ok, opis)` do linii startowej.
    pub fn boot_status(&self) -> (bool, String) {
        let g = lock(&self.inner);
        if let Some(e) = g.file_error.as_ref() {
            return (false, format!("pamięć, plik: {e}"));
        }
        if let Some(p) = g.path.as_ref() {
            return (true, p.display().to_string());
        }
        (true, "pamięć".into())
    }

    pub fn tail(&self, n: usize) -> Vec<String> {
        let g = lock(&self.inner);
        let skip = g.entries.len().saturating_sub(n);
        g.entries
            .iter()
            .skip(skip)
            .map(|e| format_line(e.unix_ms, &e.source, &e.message))
            .collect()
    }
}

pub fn format_line(unix_ms: u64, source: &str, message: &str) -> String {
    format!("{} {source} {message}", format_utc(unix_ms))
}

/// `YYYY-MM-DDTHH:MM:SSZ` z milisekund uniksowych (UTC).
pub fn format_utc(unix_ms: u64) -> String {
    let secs = unix_ms / 1000;
    let (y, m, d) = civil_from_days((secs / 86_400) as i64);
    let tod = secs % 86_400;
    let hh = tod / 3600;
    let mm = (tod % 3600) / 60;
    let ss = tod % 60;
    format!("{y:04}-{m:02}-{d:02}T{hh:02}:{mm:02}:{ss:02}Z")
}

/// Dni od 1970-01-01 → data. Algorytm Howarda Hinnanta (`civil_from_days`).
fn civil_from_days(z: i64) -> (i32, u32, u32) {
    let z = z + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = (z - era * 146_097) as u64;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe as i64 + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = if m <= 2 { y + 1 } else { y };
    (y as i32, m as u32, d as u32)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn utc_epoch_and_known_instant() {
        assert_eq!(format_utc(0), "1970-01-01T00:00:00Z");
        assert_eq!(format_utc(1_700_000_000_000), "2023-11-14T22:13:20Z");
        assert_eq!(format_utc(1_582_934_400_000), "2020-02-29T00:00:00Z");
    }

    #[test]
    fn tail_drops_oldest() {
        let log = Log::memory();
        for i in 0..CAP + 3 {
            log.record("t", &format!("n{i}"));
        }
        let all = log.tail(CAP + 10);
        assert_eq!(all.len(), CAP);
        assert!(all[0].ends_with(" n3"));
        assert!(all.last().unwrap().ends_with(&format!(" n{}", CAP + 2)));
    }

    #[test]
    fn file_gets_one_line_per_record() {
        let dir = std::env::temp_dir().join(format!("klog-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("karmazyn.log");
        let log = Log::memory();
        log.attach_path(&path).unwrap();
        log.record("boot", "ok store\nz drugą");
        let text = std::fs::read_to_string(&path).unwrap();
        assert_eq!(text.lines().count(), 1);
        assert!(text.contains(" boot ok store z drugą"));
        assert!(log.boot_status().0);
        let _ = std::fs::remove_dir_all(&dir);
    }
}
