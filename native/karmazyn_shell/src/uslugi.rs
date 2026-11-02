//! Nadzór usług: adjutant shella (minister spraw wewnętrznych) pilnuje
//! procesów-posłów, które żyją poza Store. Słownik HOT/WARM/COLD/TOMB jest
//! pożyczony od substratu, ale usługa nie jest atomem i reach-GC jej nie zbiera.
//! Jądro Linuksa daje tu tylko proces.
//!
//! `KARMAZYN_USLUGI` albo `<data_home>/uslugi/<nazwa>/`:
//! - `run` — pierwsza niepusta linia to argv (cudzysłowy jak w shellu),
//!   albo plik binarny (ELF/MZ), który jest odpalany wprost
//! - `oneshot` — gdy plik istnieje, usługa robi jedno przejście i stygnie do WARM
//! - `down` — nie wstaje; `usluga up` kasuje plik, ręczne usunięcie też ją podnosi
//! - `needs` — nazwy zależności, jedna na linię. Start, gdy każda jest HOT albo WARM
//!
//! Długa usługa, która kończy się szybciej niż w sekundę pięć razy z rzędu,
//! stygnie do TOMB i nie wstaje, aż `usluga up` ją podniesie. Wyjście po
//! dłuższym życiu wraca do HOT. Oneshot z kodem innym niż 0 od razu TOMB.
//!
//! Stdin dziecka jest pusty. Stdout i stderr idą do `<katalog>/output.log`.
//! Na Linuksie PID 1 zbiera też osierocone dzieci (`waitpid(-1)`), żeby nie
//! zostały zombie. Dlatego każdy inny proces potomny shella startuje przez
//! [`run_command`]: odbiorca zostawia jego kod w `AWAITED`, zamiast go zgubić.

use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fs::{self, File, OpenOptions};
use std::path::{Path, PathBuf};
#[cfg(windows)]
use std::process::Child;
use std::process::{Command, ExitStatus, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, MutexGuard};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use crate::log::Log;

const FAST: Duration = Duration::from_secs(1);
const BURST: u32 = 5;
const SCAN_EVERY: Duration = Duration::from_secs(5);
const STOP_GRACE: Duration = Duration::from_secs(2);
const TICK: Duration = Duration::from_millis(200);

/// Procesy potomne spoza nadzoru, na które ktoś czeka (pid → surowy status,
/// gdy już zebrany). Odbiorca trzyma tę blokadę przez całe `waitpid(-1)`, a
/// [`run_command`] przez `spawn` i wpis, więc pid nie przemknie między nimi.
#[cfg_attr(windows, allow(dead_code))]
static AWAITED: Mutex<Option<HashMap<u32, Option<i32>>>> = Mutex::new(None);

/// Uruchamia proces i czeka na jego koniec. Jedyna droga do procesów
/// potomnych poza nadzorem: `Command::status()` mógłby stracić kod na rzecz
/// odbiorcy osieroconych dzieci.
// Jeszcze bez wołających w shellu; czeka na pierwszy proces poza nadzorem.
#[allow(dead_code)]
#[cfg(unix)]
pub fn run_command(cmd: &mut Command) -> std::io::Result<ExitStatus> {
    use std::os::unix::process::ExitStatusExt;
    let pid = {
        let mut g = AWAITED.lock().unwrap_or_else(|e| e.into_inner());
        let child = cmd.spawn()?;
        let pid = child.id();
        g.get_or_insert_with(HashMap::new).insert(pid, None);
        pid
    };
    loop {
        let mut status = 0i32;
        let r = unsafe { libc::waitpid(pid as i32, &mut status, libc::WNOHANG) };
        let err = (r < 0).then(std::io::Error::last_os_error);
        let mut g = AWAITED.lock().unwrap_or_else(|e| e.into_inner());
        let map = g.get_or_insert_with(HashMap::new);
        if r == pid as i32 {
            map.remove(&pid);
            return Ok(ExitStatus::from_raw(status));
        }
        if let Some(Some(raw)) = map.get(&pid).copied() {
            map.remove(&pid);
            return Ok(ExitStatus::from_raw(raw));
        }
        if let Some(err) = err {
            let benign = err.raw_os_error() == Some(libc::ECHILD)
                || err.kind() == std::io::ErrorKind::Interrupted;
            if !benign {
                map.remove(&pid);
                return Err(err);
            }
        }
        drop(g);
        std::thread::sleep(Duration::from_millis(10));
    }
}

#[allow(dead_code)]
#[cfg(windows)]
pub fn run_command(cmd: &mut Command) -> std::io::Result<ExitStatus> {
    cmd.status()
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Kind {
    Oneshot,
    Longrun,
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum State {
    Hot,
    Warm,
    Cold,
    Tomb,
}

impl State {
    fn as_str(self) -> &'static str {
        match self {
            State::Hot => "HOT",
            State::Warm => "WARM",
            State::Cold => "COLD",
            State::Tomb => "TOMB",
        }
    }
}

/// Co zrobić po wyjściu procesu. `streak` liczy poprzednie szybkie wyjścia.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Verdict {
    Warm,
    Again,
    Tomb,
}

pub fn after_exit(kind: Kind, code: i32, lived: Duration, streak: u32) -> Verdict {
    if kind == Kind::Oneshot {
        return if code == 0 { Verdict::Warm } else { Verdict::Tomb };
    }
    if lived < FAST && streak + 1 >= BURST {
        Verdict::Tomb
    } else {
        Verdict::Again
    }
}

/// Pierwsza linia `run`: białe znaki dzielą argumenty, `"` grupuje.
pub fn split_argv(line: &str) -> Result<Vec<String>, String> {
    let mut out = Vec::new();
    let mut cur = String::new();
    let mut quote = false;
    let mut chars = line.chars().peekable();
    while let Some(c) = chars.next() {
        match c {
            '"' => quote = !quote,
            '\\' if quote && chars.peek() == Some(&'"') => {
                chars.next();
                cur.push('"');
            }
            c if c.is_whitespace() && !quote => {
                if !cur.is_empty() {
                    out.push(std::mem::take(&mut cur));
                }
            }
            c => cur.push(c),
        }
    }
    if quote {
        return Err("niezamknięty cudzysłów w run".into());
    }
    if !cur.is_empty() {
        out.push(cur);
    }
    if out.is_empty() {
        return Err("pusty run".into());
    }
    Ok(out)
}

pub struct BootSnap {
    pub console: Option<Result<String, String>>,
    pub log_ok: bool,
    pub log_detail: String,
    pub tools: Option<usize>,
    pub disk: Option<(bool, String)>,
    pub net: Option<Result<String, String>>,
    pub czas_ok: bool,
    pub czas_detail: String,
}

enum Live {
    #[cfg(unix)]
    Pid { pid: u32, started: Instant },
    #[cfg(windows)]
    Win { child: Child, started: Instant },
}

impl Live {
    fn started(&self) -> Instant {
        match self {
            #[cfg(unix)]
            Live::Pid { started, .. } => *started,
            #[cfg(windows)]
            Live::Win { started, .. } => *started,
        }
    }

    fn pid(&self) -> u32 {
        match self {
            #[cfg(unix)]
            Live::Pid { pid, .. } => *pid,
            #[cfg(windows)]
            Live::Win { child, .. } => child.id(),
        }
    }
}

struct Svc {
    builtin: bool,
    kind: Kind,
    state: State,
    detail: String,
    needs: Vec<String>,
    dir: Option<PathBuf>,
    want_up: bool,
    live: Option<Live>,
    streak: u32,
    stopping: Option<Instant>,
    gone: bool,
    /// Plik `down` przy ostatnim skanie.
    down_file: bool,
}

impl Svc {
    fn builtin(ok: bool, detail: String) -> Self {
        Svc {
            builtin: true,
            kind: Kind::Oneshot,
            state: if ok { State::Warm } else { State::Tomb },
            detail,
            needs: Vec::new(),
            dir: None,
            want_up: false,
            live: None,
            streak: 0,
            stopping: None,
            gone: false,
            down_file: false,
        }
    }

    fn fresh(dir: PathBuf, kind: Kind, needs: Vec<String>, down: bool) -> Self {
        Svc {
            builtin: false,
            kind,
            state: State::Cold,
            detail: if down { "down".into() } else { String::new() },
            needs,
            dir: Some(dir),
            want_up: !down,
            live: None,
            streak: 0,
            stopping: None,
            gone: false,
            down_file: down,
        }
    }

    /// HOT krócej niż `FAST`: jeszcze nie wiadomo, czy nie padnie od razu.
    fn young(&self) -> bool {
        self.state == State::Hot
            && self.live.as_ref().is_some_and(|l| l.started().elapsed() < FAST)
    }

    fn line(&self, name: &str) -> (bool, String, String) {
        let ok = match self.state {
            State::Hot | State::Warm => true,
            State::Cold => !self.want_up,
            State::Tomb => false,
        };
        let detail = if self.young() {
            format!("startuje, {}", self.detail)
        } else {
            self.detail.clone()
        };
        (ok, name.to_string(), detail)
    }
}

struct Inner {
    dir: PathBuf,
    dir_error: Option<String>,
    services: BTreeMap<String, Svc>,
    last_scan: Instant,
}

pub struct Nadzor {
    inner: Arc<Mutex<Inner>>,
    stop: Arc<AtomicBool>,
    thread: Option<JoinHandle<()>>,
}

fn lock(inner: &Mutex<Inner>) -> MutexGuard<'_, Inner> {
    inner.lock().unwrap_or_else(|e| e.into_inner())
}

pub fn dir_from_env() -> PathBuf {
    match std::env::var("KARMAZYN_USLUGI") {
        Ok(v) if !v.trim().is_empty() => PathBuf::from(v.trim()),
        _ => karmazyn_kafd::cipher::data_home().join("uslugi"),
    }
}

impl Nadzor {
    fn open(dir: PathBuf) -> Self {
        Nadzor {
            inner: Arc::new(Mutex::new(Inner {
                dir,
                dir_error: None,
                services: BTreeMap::new(),
                last_scan: Instant::now() - SCAN_EVERY,
            })),
            stop: Arc::new(AtomicBool::new(false)),
            thread: None,
        }
    }

    /// Wpisuje usługi startu, skanuje katalog, odpala pierwsze przejście
    /// i zostawia wątek, który podnosi upadłe procesy.
    pub fn boot(snap: BootSnap, log: Arc<Log>) -> Self {
        let mut n = Nadzor::open(dir_from_env());
        {
            let mut g = lock(&n.inner);
            g.ensure_dir();
            g.register_boot(&snap);
            g.scan();
        }
        let _ = n.poll();
        n.spawn_thread(log);
        n
    }

    fn spawn_thread(&mut self, log: Arc<Log>) {
        let inner = Arc::clone(&self.inner);
        let stop = Arc::clone(&self.stop);
        self.thread = Some(std::thread::spawn(move || {
            while !stop.load(Ordering::Relaxed) {
                let notes = poll_inner(&inner);
                for note in notes {
                    log.record("usluga", &note);
                }
                std::thread::sleep(TICK);
            }
            lock(&inner).stop_all();
        }));
    }

    pub fn summary(&self) -> (bool, String) {
        let g = lock(&self.inner);
        let external: Vec<&Svc> = g.services.values().filter(|s| !s.builtin).collect();
        let starting = external.iter().filter(|s| s.young()).count();
        let up = external
            .iter()
            .filter(|s| matches!(s.state, State::Hot | State::Warm) && !s.young())
            .count();
        let tomb = external.iter().filter(|s| s.state == State::Tomb).count();
        let mut detail = format!("nadzór, {up} działających");
        if starting > 0 {
            detail = format!("{detail}, {starting} startuje");
        }
        detail = format!("{detail}, katalog {}", g.dir.display());
        if let Some(e) = &g.dir_error {
            detail = format!("{detail}; {e}");
        }
        if tomb > 0 {
            detail = format!("{detail}; {tomb} ostygłych");
        }
        (tomb == 0 && g.dir_error.is_none(), detail)
    }

    /// Linie startowe samych usług z katalogu (wbudowane są już na ekranie).
    pub fn lines(&self) -> Vec<(bool, String, String)> {
        let g = lock(&self.inner);
        g.services
            .iter()
            .filter(|(_, s)| !s.builtin)
            .map(|(name, s)| s.line(name))
            .collect()
    }

    pub fn list(&self) -> Vec<String> {
        let _ = self.poll();
        let g = lock(&self.inner);
        g.services
            .iter()
            .map(|(name, s)| format!("  {:<4}  {:<16}  {}", s.state.as_str(), name, s.detail))
            .collect()
    }

    pub fn status(&self, name: &str) -> Option<String> {
        let _ = self.poll();
        let g = lock(&self.inner);
        g.services
            .get(name)
            .map(|s| format!("  {:<4}  {:<16}  {}", s.state.as_str(), name, s.detail))
    }

    pub fn up(&self, name: &str) -> Result<String, String> {
        let msg = {
            let mut g = lock(&self.inner);
            g.bring_up(name)?
        };
        let _ = self.poll();
        Ok(msg)
    }

    pub fn down(&self, name: &str) -> Result<String, String> {
        let mut g = lock(&self.inner);
        g.bring_down(name)
    }

    fn poll(&self) -> Vec<String> {
        poll_inner(&self.inner)
    }
}

fn poll_inner(inner: &Mutex<Inner>) -> Vec<String> {
    let mut g = lock(inner);
    let mut notes = Vec::new();
    if g.last_scan.elapsed() >= SCAN_EVERY {
        notes.extend(g.scan());
    }
    notes.extend(g.reap());
    notes.extend(g.nudge_stop());
    notes.extend(g.start_ready());
    notes.extend(g.reap());
    notes
}

impl Drop for Nadzor {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Relaxed);
        if let Some(t) = self.thread.take() {
            let _ = t.join();
        }
        lock(&self.inner).stop_all();
    }
}

impl Inner {
    fn ensure_dir(&mut self) {
        if let Err(e) = fs::create_dir_all(&self.dir) {
            self.dir_error = Some(format!("{}: {e}", self.dir.display()));
        }
    }

    fn register_boot(&mut self, snap: &BootSnap) {
        if let Some(c) = &snap.console {
            let (ok, detail) = match c {
                Ok(names) => (true, names.clone()),
                Err(e) => (false, e.clone()),
            };
            self.services.insert("console".into(), Svc::builtin(ok, detail));
        }
        self.services
            .insert("log".into(), Svc::builtin(snap.log_ok, snap.log_detail.clone()));
        self.services.insert("store".into(), Svc::builtin(true, String::new()));
        self.services.insert("lisp".into(), Svc::builtin(true, String::new()));
        self.services.insert("lua".into(), Svc::builtin(true, String::new()));
        if let Some(n) = snap.tools {
            let detail = if n > 0 {
                format!("{n} bąbli")
            } else {
                "brak bąbli kodu".into()
            };
            self.services.insert("narzędzia".into(), Svc::builtin(true, detail));
        }
        if let Some((ok, detail)) = &snap.disk {
            self.services
                .insert("disk".into(), Svc::builtin(*ok, detail.clone()));
        }
        if let Some(net) = &snap.net {
            let (ok, detail) = match net {
                Ok(s) => (true, s.clone()),
                Err(e) => (false, e.clone()),
            };
            self.services.insert("net".into(), Svc::builtin(ok, detail));
        }
        self.services
            .insert("czas".into(), Svc::builtin(snap.czas_ok, snap.czas_detail.clone()));
    }

    fn scan(&mut self) -> Vec<String> {
        self.last_scan = Instant::now();
        let mut notes = Vec::new();
        if self.dir_error.is_some() && !self.dir.is_dir() {
            return notes;
        }
        let rd = match fs::read_dir(&self.dir) {
            Ok(rd) => rd,
            Err(e) => {
                if e.kind() != std::io::ErrorKind::NotFound {
                    self.dir_error = Some(format!("{}: {e}", self.dir.display()));
                }
                return notes;
            }
        };
        let mut seen = BTreeSet::new();
        for ent in rd.filter_map(|e| e.ok()) {
            let name = ent.file_name();
            let Some(name) = name.to_str() else { continue };
            if name == "." || name == ".." || name.starts_with('.') {
                continue;
            }
            let path = ent.path();
            if !path.is_dir() {
                continue;
            }
            let run = path.join("run");
            if !run.is_file() {
                continue;
            }
            seen.insert(name.to_string());
            if self.services.get(name).is_some_and(|s| s.builtin) {
                notes.push(format!("{name}: nazwa zajęta przez usługę wbudowaną"));
                continue;
            }
            let kind = if path.join("oneshot").exists() {
                Kind::Oneshot
            } else {
                Kind::Longrun
            };
            let needs = read_names(&path.join("needs"));
            let down = path.join("down").exists();
            if let Some(svc) = self.services.get_mut(name) {
                svc.kind = kind;
                svc.needs = needs;
                svc.dir = Some(path);
                let was_down = std::mem::replace(&mut svc.down_file, down);
                if was_down && !down && !svc.want_up && svc.state != State::Tomb {
                    svc.want_up = true;
                    svc.streak = 0;
                    svc.detail = "down zdjęty".into();
                    notes.push(format!("{name}: down zdjęty"));
                }
                if down && svc.want_up {
                    svc.want_up = false;
                    svc.stopping = Some(Instant::now());
                    if let Some(live) = svc.live.as_mut() {
                        kill_term(live);
                        svc.detail = format!("zatrzymuję pid {}", live.pid());
                    } else {
                        svc.state = State::Cold;
                        svc.detail = "down".into();
                    }
                    notes.push(format!("{name}: down"));
                }
            } else {
                self.services
                    .insert(name.to_string(), Svc::fresh(path, kind, needs, down));
            }
        }
        let gone: Vec<String> = self
            .services
            .iter()
            .filter(|(name, s)| !s.builtin && s.dir.is_some() && !seen.contains(*name))
            .map(|(name, _)| name.clone())
            .collect();
        for name in gone {
            if let Some(svc) = self.services.get_mut(&name) {
                svc.gone = true;
                svc.want_up = false;
                if let Some(live) = svc.live.as_mut() {
                    kill_term(live);
                    svc.stopping = Some(Instant::now());
                    notes.push(format!("{name}: katalog zniknął"));
                    continue;
                }
            }
            self.services.remove(&name);
        }
        notes
    }

    fn reap(&mut self) -> Vec<String> {
        let mut notes = Vec::new();
        #[cfg(unix)]
        {
            let mut awaited = AWAITED.lock().unwrap_or_else(|e| e.into_inner());
            while let Some((pid, status)) = reap_unix() {
                if let Some(slot) = awaited.as_mut().and_then(|m| m.get_mut(&pid)) {
                    *slot = Some(status);
                    continue;
                }
                let code = status_code(status);
                if let Some(name) = self.owner_of(pid) {
                    notes.push(self.note_exit(&name, code));
                }
            }
        }
        #[cfg(windows)]
        {
            let names: Vec<String> = self.services.keys().cloned().collect();
            for name in names {
                let finished = match self.services.get_mut(&name).and_then(|s| s.live.as_mut()) {
                    Some(Live::Win { child, started }) => match child.try_wait() {
                        Ok(Some(st)) => Some((st.code().unwrap_or(1), started.elapsed())),
                        _ => None,
                    },
                    _ => None,
                };
                if let Some((code, lived)) = finished {
                    notes.push(self.note_exit_lived(&name, code, lived));
                }
            }
        }
        notes
    }

    #[cfg(unix)]
    fn owner_of(&self, pid: u32) -> Option<String> {
        self.services.iter().find_map(|(name, s)| match &s.live {
            Some(Live::Pid { pid: p, .. }) if *p == pid => Some(name.clone()),
            _ => None,
        })
    }

    #[cfg(unix)]
    fn note_exit(&mut self, name: &str, code: i32) -> String {
        let lived = self
            .services
            .get(name)
            .and_then(|s| s.live.as_ref())
            .map(|l| l.started().elapsed())
            .unwrap_or(Duration::ZERO);
        self.note_exit_lived(name, code, lived)
    }

    fn note_exit_lived(&mut self, name: &str, code: i32, lived: Duration) -> String {
        let Some(svc) = self.services.get_mut(name) else {
            return format!("{name}: kod {code}");
        };
        let gone = svc.gone;
        let want_up = svc.want_up;
        let kind = svc.kind;
        let streak = svc.streak;
        svc.live = None;
        svc.stopping = None;
        if gone {
            self.services.remove(name);
            return format!("{name}: koniec po usunięciu katalogu, kod {code}");
        }
        if !want_up {
            let svc = self.services.get_mut(name).unwrap();
            svc.state = State::Cold;
            svc.streak = 0;
            svc.detail = format!("zatrzymana, kod {code}");
            return format!("{name}: zatrzymana, kod {code}");
        }
        let verdict = after_exit(kind, code, lived, streak);
        let fast = lived < FAST;
        let svc = self.services.get_mut(name).unwrap();
        match verdict {
            Verdict::Warm => {
                svc.streak = 0;
                svc.state = State::Warm;
                svc.detail = "oneshot".into();
                format!("{name}: oneshot")
            }
            Verdict::Again => {
                svc.streak = if fast { svc.streak + 1 } else { 0 };
                svc.state = State::Cold;
                svc.detail = format!("kod {code}, restart");
                format!("{name}: kod {code}, restart")
            }
            Verdict::Tomb => {
                svc.streak = if fast { svc.streak + 1 } else { svc.streak };
                svc.state = State::Tomb;
                svc.want_up = false;
                svc.detail = if svc.kind == Kind::Oneshot {
                    format!("oneshot kod {code}")
                } else {
                    format!("ostygła po {} szybkich wyjściach", svc.streak)
                };
                format!("{name}: {}", svc.detail)
            }
        }
    }

    fn nudge_stop(&mut self) -> Vec<String> {
        let mut notes = Vec::new();
        let due: Vec<String> = self
            .services
            .iter()
            .filter(|(_, s)| {
                s.stopping
                    .is_some_and(|t| t.elapsed() >= STOP_GRACE && s.live.is_some())
            })
            .map(|(n, _)| n.clone())
            .collect();
        for name in due {
            if let Some(live) = self.services.get_mut(&name).and_then(|s| s.live.as_mut()) {
                kill_kill(live);
                notes.push(format!("{name}: wymuszam koniec"));
            }
            if let Some(svc) = self.services.get_mut(&name) {
                svc.stopping = None;
            }
        }
        notes
    }

    fn start_ready(&mut self) -> Vec<String> {
        let names: Vec<String> = self
            .services
            .iter()
            .filter(|(_, s)| s.should_start())
            .map(|(n, _)| n.clone())
            .collect();
        let mut notes = Vec::new();
        for name in names {
            if let Some(cycle) = self.find_cycle(&name) {
                if let Some(svc) = self.services.get_mut(&name) {
                    svc.detail = format!("cykl: {}", cycle.join(" → "));
                }
                continue;
            }
            if let Some(wait) = self.unmet(&name) {
                if let Some(svc) = self.services.get_mut(&name) {
                    svc.detail = wait;
                }
                continue;
            }
            notes.push(self.spawn(&name));
        }
        notes
    }

    fn unmet(&self, name: &str) -> Option<String> {
        let needs = &self.services.get(name)?.needs;
        let mut wait = Vec::new();
        for n in needs {
            match self.services.get(n) {
                None => wait.push(format!("brak {n}")),
                Some(s) if matches!(s.state, State::Hot | State::Warm) => {}
                Some(_) => wait.push(n.clone()),
            }
        }
        if wait.is_empty() {
            None
        } else {
            Some(format!("czeka na: {}", wait.join(", ")))
        }
    }

    fn find_cycle(&self, start: &str) -> Option<Vec<String>> {
        fn dfs(
            this: &Inner,
            cur: &str,
            start: &str,
            stack: &mut Vec<String>,
            seen: &mut BTreeSet<String>,
        ) -> bool {
            if !stack.is_empty() && cur == start {
                stack.push(cur.to_string());
                return true;
            }
            if !seen.insert(cur.to_string()) {
                return false;
            }
            stack.push(cur.to_string());
            if let Some(svc) = this.services.get(cur) {
                for n in &svc.needs {
                    if dfs(this, n, start, stack, seen) {
                        return true;
                    }
                }
            }
            stack.pop();
            false
        }
        let mut stack = Vec::new();
        let mut seen = BTreeSet::new();
        if dfs(self, start, start, &mut stack, &mut seen) {
            Some(stack)
        } else {
            None
        }
    }

    fn spawn(&mut self, name: &str) -> String {
        let Some(dir) = self.services.get(name).and_then(|s| s.dir.clone()) else {
            return format!("{name}: brak katalogu");
        };
        let argv = match load_argv(&dir.join("run")) {
            Ok(a) => a,
            Err(e) => return self.fail_spawn(name, e),
        };
        match spawn_live(&dir, &argv) {
            Ok(live) => {
                let pid = live.pid();
                if let Some(svc) = self.services.get_mut(name) {
                    svc.live = Some(live);
                    svc.state = State::Hot;
                    svc.detail = format!("pid {pid}");
                    svc.stopping = None;
                }
                format!("{name}: pid {pid}")
            }
            Err(e) => self.fail_spawn(name, e),
        }
    }

    fn fail_spawn(&mut self, name: &str, err: String) -> String {
        let Some(svc) = self.services.get_mut(name) else {
            return format!("{name}: {err}");
        };
        svc.live = None;
        svc.streak += 1;
        if svc.streak >= BURST {
            svc.state = State::Tomb;
            svc.want_up = false;
            svc.detail = format!("ostygła: {err}");
        } else {
            svc.state = State::Cold;
            svc.detail = err.clone();
        }
        format!("{name}: {err}")
    }

    fn bring_up(&mut self, name: &str) -> Result<String, String> {
        let Some(svc) = self.services.get_mut(name) else {
            return Err(format!("usługa: nie ma `{name}`"));
        };
        if svc.builtin {
            return Err(format!("usługa: `{name}` jest wbudowana i żyje w tym procesie"));
        }
        if svc.live.is_some() {
            return Ok(format!("{name}: już działa"));
        }
        if let Some(dir) = &svc.dir {
            let _ = fs::remove_file(dir.join("down"));
        }
        svc.down_file = false;
        svc.want_up = true;
        svc.streak = 0;
        svc.gone = false;
        if matches!(svc.state, State::Tomb | State::Warm) {
            svc.state = State::Cold;
        }
        svc.detail = "podnoszę".into();
        Ok(format!("{name}: podnoszę"))
    }

    fn bring_down(&mut self, name: &str) -> Result<String, String> {
        let Some(svc) = self.services.get_mut(name) else {
            return Err(format!("usługa: nie ma `{name}`"));
        };
        if svc.builtin {
            return Err(format!("usługa: `{name}` jest wbudowana i żyje w tym procesie"));
        }
        svc.want_up = false;
        if let Some(dir) = &svc.dir {
            svc.down_file = fs::write(dir.join("down"), b"").is_ok();
        }
        if let Some(live) = svc.live.as_mut() {
            kill_term(live);
            svc.stopping = Some(Instant::now());
            svc.detail = format!("zatrzymuję pid {}", live.pid());
            return Ok(format!("{name}: zatrzymuję"));
        }
        svc.state = State::Cold;
        svc.detail = "down".into();
        Ok(format!("{name}: down"))
    }

    fn stop_all(&mut self) {
        let names: Vec<String> = self.services.keys().cloned().collect();
        for name in names {
            if let Some(live) = self.services.get_mut(&name).and_then(|s| s.live.as_mut()) {
                kill_kill(live);
            }
        }
        self.reap();
    }
}

impl Svc {
    fn should_start(&self) -> bool {
        if self.builtin || self.gone || !self.want_up || self.live.is_some() {
            return false;
        }
        if self.state == State::Tomb {
            return false;
        }
        if self.kind == Kind::Oneshot && self.state == State::Warm {
            return false;
        }
        true
    }
}

fn read_names(path: &Path) -> Vec<String> {
    let Ok(text) = fs::read_to_string(path) else {
        return Vec::new();
    };
    text.lines()
        .map(str::trim)
        .filter(|l| !l.is_empty() && !l.starts_with('#'))
        .map(str::to_string)
        .collect()
}

fn load_argv(path: &Path) -> Result<Vec<String>, String> {
    let bytes = fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?;
    if is_binary(&bytes) {
        return Ok(vec![path.display().to_string()]);
    }
    let text = String::from_utf8_lossy(&bytes);
    for line in text.lines() {
        let t = line.trim();
        if t.is_empty() || t.starts_with('#') {
            continue;
        }
        return split_argv(t);
    }
    Err(format!("{}: pusty run", path.display()))
}

fn is_binary(bytes: &[u8]) -> bool {
    bytes.starts_with(b"\x7fELF") || bytes.starts_with(b"MZ") || bytes.iter().take(512).any(|b| *b == 0)
}

fn spawn_live(dir: &Path, argv: &[String]) -> Result<Live, String> {
    if argv.is_empty() {
        return Err("pusty run".into());
    }
    let mut cmd = Command::new(&argv[0]);
    cmd.args(&argv[1..])
        .current_dir(dir)
        .stdin(Stdio::null());
    if let Some(out) = output_file(dir) {
        if let Ok(err) = out.try_clone() {
            cmd.stdout(Stdio::from(out)).stderr(Stdio::from(err));
        }
    } else {
        cmd.stdout(Stdio::null()).stderr(Stdio::null());
    }
    let child = cmd.spawn().map_err(|e| format!("{}: {e}", argv[0]))?;
    #[cfg(unix)]
    {
        let pid = child.id();
        drop(child);
        Ok(Live::Pid {
            pid,
            started: Instant::now(),
        })
    }
    #[cfg(windows)]
    {
        Ok(Live::Win {
            child,
            started: Instant::now(),
        })
    }
}

fn output_file(dir: &Path) -> Option<File> {
    let path = dir.join("output.log");
    let mut opts = OpenOptions::new();
    opts.create(true).append(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        opts.mode(0o600);
    }
    opts.open(path).ok()
}

#[cfg(unix)]
fn kill_term(live: &mut Live) {
    let Live::Pid { pid, .. } = live;
    let _ = unsafe { libc::kill(*pid as i32, libc::SIGTERM) };
}

#[cfg(windows)]
fn kill_term(live: &mut Live) {
    let Live::Win { child, .. } = live;
    let _ = child.kill();
}

#[cfg(unix)]
fn kill_kill(live: &mut Live) {
    let Live::Pid { pid, .. } = live;
    let _ = unsafe { libc::kill(*pid as i32, libc::SIGKILL) };
}

#[cfg(windows)]
fn kill_kill(live: &mut Live) {
    let Live::Win { child, .. } = live;
    let _ = child.kill();
}

#[cfg(unix)]
fn reap_unix() -> Option<(u32, i32)> {
    let mut status = 0i32;
    loop {
        let pid = unsafe { libc::waitpid(-1, &mut status, libc::WNOHANG) };
        if pid > 0 {
            return Some((pid as u32, status));
        }
        if pid == 0 {
            return None;
        }
        let err = std::io::Error::last_os_error();
        if err.kind() == std::io::ErrorKind::Interrupted {
            continue;
        }
        return None;
    }
}

#[cfg(unix)]
fn status_code(status: i32) -> i32 {
    if libc::WIFEXITED(status) {
        libc::WEXITSTATUS(status)
    } else if libc::WIFSIGNALED(status) {
        128 + libc::WTERMSIG(status)
    } else {
        1
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("kuslugi-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn argv_quotes_and_exit_policy() {
        assert_eq!(
            split_argv(r#""C:\Program Files\cmd.exe" /C "exit 0""#).unwrap(),
            vec!["C:\\Program Files\\cmd.exe", "/C", "exit 0"]
        );
        assert!(split_argv("").is_err());
        assert!(split_argv("\"otwarte").is_err());
        assert_eq!(after_exit(Kind::Oneshot, 0, Duration::ZERO, 0), Verdict::Warm);
        assert_eq!(after_exit(Kind::Oneshot, 1, FAST, 0), Verdict::Tomb);
        assert_eq!(
            after_exit(Kind::Longrun, 1, Duration::from_millis(10), 3),
            Verdict::Again
        );
        assert_eq!(
            after_exit(Kind::Longrun, 1, Duration::from_millis(10), 4),
            Verdict::Tomb
        );
        assert_eq!(
            after_exit(Kind::Longrun, 0, Duration::from_secs(3), 4),
            Verdict::Again
        );
    }

    #[test]
    fn down_and_cycle_do_not_spawn() {
        let dir = temp("dep");
        let b = dir.join("b");
        let a = dir.join("a");
        let c = dir.join("c");
        let d = dir.join("d");
        for p in [&b, &a, &c, &d] {
            fs::create_dir_all(p).unwrap();
            fs::write(p.join("run"), "this-binary-is-not-spawned\n").unwrap();
        }
        fs::write(b.join("down"), "").unwrap();
        fs::write(a.join("needs"), "b\n").unwrap();
        fs::write(c.join("needs"), "d\n").unwrap();
        fs::write(d.join("needs"), "c\n").unwrap();
        let n = Nadzor::open(dir.clone());
        n.poll();
        let a = n.status("a").unwrap();
        let b = n.status("b").unwrap();
        let c = n.status("c").unwrap();
        assert!(a.contains("COLD"), "{a}");
        assert!(a.contains("czeka na: b"), "{a}");
        assert!(b.contains("COLD"), "{b}");
        assert!(b.contains("down"), "{b}");
        assert!(c.contains("cykl"), "{c}");
        assert!(c.contains('c') && c.contains('d'), "{c}");
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn removing_down_file_wants_up() {
        let dir = temp("downoff");
        let s = dir.join("s");
        fs::create_dir_all(&s).unwrap();
        fs::write(s.join("run"), "this-binary-is-not-spawned\n").unwrap();
        fs::write(s.join("down"), "").unwrap();
        let n = Nadzor::open(dir.clone());
        n.poll();
        assert!(!lock(&n.inner).services["s"].want_up);
        fs::remove_file(s.join("down")).unwrap();
        lock(&n.inner).scan();
        assert!(lock(&n.inner).services["s"].want_up);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn run_command_returns_exit_code() {
        let mut cmd = if cfg!(windows) {
            let mut c = Command::new(std::env::var("COMSPEC").unwrap_or_else(|_| "cmd.exe".into()));
            c.args(["/C", "exit 3"]);
            c
        } else if Path::new("/bin/sh").exists() {
            let mut c = Command::new("/bin/sh");
            c.args(["-c", "exit 3"]);
            c
        } else {
            return;
        };
        assert_eq!(run_command(&mut cmd).unwrap().code(), Some(3));
    }

    #[test]
    fn oneshot_reaches_warm() {
        let line = if cfg!(windows) {
            let com = std::env::var("COMSPEC").unwrap_or_else(|_| "cmd.exe".into());
            format!("\"{com}\" /C exit 0")
        } else if Path::new("/bin/true").exists() {
            "/bin/true".into()
        } else {
            return;
        };
        let dir = temp("oneshot");
        let s = dir.join("ok");
        fs::create_dir_all(&s).unwrap();
        fs::write(s.join("run"), format!("{line}\n")).unwrap();
        fs::write(s.join("oneshot"), "").unwrap();
        let n = Nadzor::open(dir.clone());
        let deadline = Instant::now() + Duration::from_secs(5);
        let mut text = String::new();
        while Instant::now() < deadline {
            n.poll();
            text = n.status("ok").unwrap_or_default();
            if text.contains("WARM") {
                break;
            }
            std::thread::sleep(Duration::from_millis(30));
        }
        assert!(text.contains("WARM"), "{text}");
        let _ = fs::remove_dir_all(&dir);
    }
}
