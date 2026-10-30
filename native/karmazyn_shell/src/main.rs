//! KarmazynOS native shell (Stage 2) — pure Rust over substrate rlib.
//!
//!   cd native/karmazyn_shell
//!   cargo run --release
//!   cargo run --release -- -e "atom var x 50" -e stats -e quit
//!   cargo run --release -- examples/smoke.ksh
//!
//! Commands: help | version | stats | atom | … | save | load | quit
//! Lisp guest: line starting with `(` → karmazyn_lisp::Evaluator::eval_line.

mod console;
mod disk;
mod editor;
mod ext2;
mod net;

use disk::Storage;
use std::cell::RefCell;
use karmazyn_lisp::Evaluator;
use karmazyn_lua::Evaluator as LuaEvaluator;

use karmazyn_substrate::{state_for_t, Store, StoreSnapshot, T_INIT};
use std::env;
use std::io::{self, BufRead, Write};
use std::process;
use std::thread;
use std::time::Duration;

/// PID 1 kończy jądro razem ze sobą. Na Linuksie zostaje w pętli.
fn is_pid1() -> bool {
    #[cfg(unix)]
    {
        process::id() == 1
    }
    #[cfg(not(unix))]
    {
        false
    }
}

const VERSION: &str = env!("CARGO_PKG_VERSION");

#[derive(Clone, Copy, PartialEq, Eq)]
enum Outcome {
    Ok,
    Quit,
    Err,
}

struct App {
    store: Store,
    lisp: Evaluator,
    lua: LuaEvaluator,
    /// Świat KAFD na dysku (albo `KARMAZYN_WORLD` na hoście).
    storage: RefCell<Option<Storage>>,
    /// Urządzenie, którego nie dało się podłączyć (do `disk format`).
    pending_device: RefCell<Option<String>>,
    /// Tunel do Karmin_DB (`db connect`).
    db: RefCell<Option<karmazyn_cynober::Client>>,
    /// Po każdym poleceniu zapis na dysk, jeśli Store się zmienił.
    autosync: bool,
    /// Skrót ostatniego snapshotu na dysku (albo wczytanego z dysku).
    synced: std::cell::Cell<u64>,
}

fn main() {
    // PID 1: ekran i serial, zanim cokolwiek się wypisze
    let console_line = is_pid1().then(console::setup);
    if matches!(console_line, Some(Ok(_))) {
        // gość Lua (clear_screen) widzi terminal mimo rury konsoli
        env::set_var("KARMAZYN_TTY", "1");
    }
    let thermal = true;
    let store = Store::new(thermal);
    let lisp = Evaluator::new(&store);
    let lua = LuaEvaluator::new(&store);
    // KARMAZYN_LUA_BUDGET=<instrukcje na chunk>, 0 = bez limitu
    if let Some(n) = env::var("KARMAZYN_LUA_BUDGET")
        .ok()
        .and_then(|v| v.trim().parse::<u64>().ok())
    {
        lua.set_budget((n > 0).then_some(n));
    }
    let tools = preload_lua_bin(&lua);
    let autosync_on = env::var("KARMAZYN_AUTOSYNC").map_or(true, |v| v.trim() != "0");
    let mut app = App {
        store,
        lisp,
        lua,
        storage: RefCell::new(None),
        pending_device: RefCell::new(None),
        db: RefCell::new(None),
        autosync: autosync_on,
        synced: std::cell::Cell::new(0),
    };
    let disk_line = open_disk(&mut app);
    let net_line = if is_pid1() { open_net() } else { None };
    let args: Vec<String> = env::args().skip(1).collect();

    // batch: -e "cmd" ...  and/or trailing script file of commands
    let mut batch: Vec<String> = Vec::new();
    let mut i = 0;
    while i < args.len() {
        if args[i] == "-e" || args[i] == "--eval" {
            i += 1;
            if i >= args.len() {
                eprintln!("-e requires a command");
                process::exit(2);
            }
            batch.push(args[i].clone());
            i += 1;
        } else if args[i] == "-V" || args[i] == "--version" {
            println!("karmazyn_shell {VERSION}");
            process::exit(0);
        } else if args[i] == "-h" || args[i] == "--help" {
            println!("karmazyn_shell {VERSION} — native Stage 2 shell (no Python)");
            println!("  interactive:  karmazyn_shell");
            println!("  batch:        karmazyn_shell -e \"atom var x 50\" -e stats");
            println!("  script file:  karmazyn_shell commands.ksh");
            println!("  version:      karmazyn_shell --version");
            process::exit(0);
        } else {
            // treat as script path
            match std::fs::read_to_string(&args[i]) {
                Ok(text) => {
                    for line in text.lines() {
                        let t = line.trim();
                        if !t.is_empty() && !t.starts_with('#') {
                            batch.push(t.to_string());
                        }
                    }
                }
                Err(e) => {
                    eprintln!("cannot read {}: {e}", args[i]);
                    process::exit(1);
                }
            }
            i += 1;
        }
    }

    if !batch.is_empty() {
        println!("karmazyn_shell {VERSION} — batch ({} cmds)", batch.len());
        if let Some((false, msg)) = &disk_line {
            println!("[WARN] disk — {msg}");
        }
        let mut failed = false;
        for cmd in batch {
            println!("k$ {cmd}");
            let outcome = dispatch(&app, &cmd);
            autosync(&app);
            match outcome {
                Outcome::Ok => {}
                Outcome::Quit => break,
                Outcome::Err => {
                    failed = true;
                    break;
                }
            }
        }
        if failed {
            process::exit(1);
        }
        return;
    }

    app.lua.enable_stdin(true);
    print_boot(tools, &disk_line, &console_line, &net_line);
    println!("karmazyn_shell {VERSION} — Stage 2 (native, no Python)");
    println!("thermal={thermal}  lisp: (   lua: `lua <chunk>`   tool: `tool <name> [args]`   type `help`");

    let stdin = io::stdin();
    let mut stdout = io::stdout();
    loop {
        print!("k$ ");
        let _ = stdout.flush();
        let mut line = String::new();
        match stdin.lock().read_line(&mut line) {
            Ok(0) | Err(_) => {
                if is_pid1() {
                    thread::sleep(Duration::from_millis(200));
                    continue;
                }
                break;
            }
            Ok(_) => {}
        }
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let outcome = dispatch(&app, line);
        autosync(&app);
        match outcome {
            Outcome::Ok => {}
            Outcome::Quit => {
                if is_pid1() {
                    println!("pid 1 stays");
                    continue;
                }
                break;
            }
            Outcome::Err => {
                // interactive: print already done; stay in REPL
            }
        }
    }
    println!("bye");
}

fn dispatch(app: &App, line: &str) -> Outcome {
    let t = line.trim();
    if t.starts_with('(') {
        return eval_lisp(app, t);
    }
    if let Some(rest) = t.strip_prefix("lisp ").or_else(|| t.strip_prefix("lisp\t")) {
        return eval_lisp(app, rest.trim());
    }
    if t == "lua" {
        println!("usage: lua <chunk>");
        return Outcome::Err;
    }
    if let Some(rest) = t.strip_prefix("lua ").or_else(|| t.strip_prefix("lua\t")) {
        return eval_lua(app, rest.trim());
    }
    // zapytanie do bazy idzie dosłownie (spacje, cudzysłowy, @ bez zmian)
    if t == "db" {
        return db_cmd(app, "");
    }
    if let Some(rest) = t.strip_prefix("db ").or_else(|| t.strip_prefix("db\t")) {
        return db_cmd(app, rest);
    }
    if t == "tool" || t == ":tool" || t == ":tools" {
        return run_tool(app, "");
    }
    if let Some(rest) = t
        .strip_prefix(":tool ")
        .or_else(|| t.strip_prefix(":tool\t"))
        .or_else(|| t.strip_prefix("tool "))
        .or_else(|| t.strip_prefix("tool\t"))
    {
        return run_tool(app, rest.trim());
    }
    let resolved = match resolve_labels(&app.store, t) {
        Ok(r) => r,
        Err(e) => {
            println!("{e}");
            return Outcome::Err;
        }
    };
    let t = resolved.as_str();
    let parts: Vec<&str> = t.split_whitespace().collect();
    let head = parts.first().copied().unwrap_or("");
    if head.eq_ignore_ascii_case("load") {
        if parts.len() < 2 {
            println!("usage: load <path>");
            return Outcome::Err;
        }
        match app.store.load_snapshot_file(parts[1]) {
            Ok(()) => {
                app.lisp.remount_repl(&app.store);
                app.lua.remount_session(&app.store);
                let st = app.store.stats();
                println!(
                    "loaded {}  atoms={} bubbles={} reaped={}",
                    parts[1], st.total, st.bubbles, st.reaped
                );
                Outcome::Ok
            }
            Err(e) => {
                println!("load err: {e}");
                Outcome::Err
            }
        }
    } else if head.eq_ignore_ascii_case("edit") {
        edit_file(app, &parts)
    } else if head.eq_ignore_ascii_case("sync") {
        disk_sync(app)
    } else if head.eq_ignore_ascii_case("disk") {
        disk_status(app, &parts)
    } else if head.eq_ignore_ascii_case("tick") {
        shell_tick(app, &parts)
    } else if head.eq_ignore_ascii_case("settle") {
        shell_settle(app, &parts)
    } else {
        dispatch_cmd(&app.store, t)
    }
}

/// Store ticks and the Lua session epoch stay on the same count.
fn shell_tick(app: &App, parts: &[&str]) -> Outcome {
    let n = parts.get(1).and_then(|x| x.parse::<u32>().ok()).unwrap_or(1);
    let steps = if n <= 1 { 1 } else { n };
    if steps == 1 {
        app.store.tick();
    } else {
        app.store.settle(steps);
    }
    app.lua.add_epoch(u64::from(steps));
    println!("tick x{n}");
    Outcome::Ok
}

fn shell_settle(app: &App, parts: &[&str]) -> Outcome {
    let Some(n) = parts.get(1).and_then(|x| x.parse::<u32>().ok()) else {
        println!("usage: settle <n>");
        return Outcome::Err;
    };
    app.store.settle(n);
    app.lua.add_epoch(u64::from(n));
    println!("settle {n}");
    Outcome::Ok
}

fn eval_lisp(app: &App, src: &str) -> Outcome {
    // eval_line always returns a string (blad:… is language output, not a shell fail).
    let s = app.lisp.eval_line(&app.store, src);
    if !s.is_empty() {
        println!("{s}");
    }
    Outcome::Ok
}

fn preload_lua_bin(lua: &LuaEvaluator) -> usize {
    if let Ok(dir) = env::var("KARMAZYN_LUA_BIN") {
        return lua.install_preload_dir(dir).unwrap_or(0);
    }
    let Ok(exe) = env::current_exe() else {
        return 0;
    };
    let mut dir = exe.parent().map(|p| p.to_path_buf());
    for _ in 0..8 {
        let Some(d) = dir else {
            return 0;
        };
        let candidate = d.join("lua_bin");
        if candidate.is_dir() {
            return lua.install_preload_dir(&candidate).unwrap_or(0);
        }
        dir = d.parent().map(|p| p.to_path_buf());
    }
    0
}

fn print_boot(
    tools: usize,
    disk: &Option<(bool, String)>,
    console: &Option<Result<Vec<String>, String>>,
    net: &Option<Result<String, String>>,
) {
    let color = console::is_terminal();
    match console {
        Some(Ok(names)) => boot_line(color, "ok", "console", &names.join(" + ")),
        Some(Err(e)) => boot_line(color, "warn", "console", &format!("/dev/console ({e})")),
        None => {}
    }
    boot_line(color, "ok", "store", "");
    boot_line(color, "ok", "lisp", "");
    boot_line(color, "ok", "lua", "");
    if tools > 0 {
        boot_line(color, "ok", "lua_bin", &format!("{tools} narzędzi"));
    } else {
        boot_line(color, "warn", "lua_bin", "brak katalogu");
    }
    if let Some((ok, detail)) = disk {
        boot_line(color, if *ok { "ok" } else { "warn" }, "disk", detail);
    }
    match net {
        Some(Ok(l)) => boot_line(color, "ok", "net", l),
        Some(Err(e)) => boot_line(color, "warn", "net", e),
        None => {}
    }
}

/// PID 1: sterownik sieci (moduły) i adres z `KARMAZYN_IP`. `None` = bez sieci.
fn open_net() -> Option<Result<String, String>> {
    let cfg = match net::config_from_env() {
        Ok(Some(c)) => c,
        Ok(None) => return None,
        Err(e) => return Some(Err(e)),
    };
    let _ = disk::load_modules();
    Some(net::bring_up(&cfg))
}

/// `db connect [host[:port]] [port]` · `db info` · `db close` · `db <zapytanie>`.
/// Zapytanie idzie tunelem Cynober-Secure-1.2 (HSS/ECDH + HSL) do Karmin_DB.
/// Bez `db connect` pierwsze zapytanie łączy z `KARMAZYN_DB=host:port`.
fn db_cmd(app: &App, rest: &str) -> Outcome {
    let rest = rest.trim();
    let (head, tail) = rest.split_once(char::is_whitespace).unwrap_or((rest, ""));
    match head.to_ascii_lowercase().as_str() {
        "" | "info" => {
            match app.db.borrow().as_ref() {
                Some(c) => {
                    let i = &c.info;
                    println!(
                        "db {} {}{} hsl={} psk={} qkd={} epoch={} {} → {}",
                        i.remote_version,
                        i.crypto_mode,
                        i.hss_profile.as_deref().map(|p| format!("/{p}")).unwrap_or_default(),
                        i.hsl,
                        i.psk,
                        i.qkd_hybrid,
                        i.epoch.map(|e| e.to_string()).unwrap_or_else(|| "-".into()),
                        i.node_local,
                        i.node_remote
                    );
                }
                None => println!("db: brak połączenia (`db connect <host> [port]` albo KARMAZYN_DB)"),
            }
            Outcome::Ok
        }
        "close" => {
            *app.db.borrow_mut() = None;
            println!("db: zamknięto");
            Outcome::Ok
        }
        "connect" => {
            let mut it = tail.split_whitespace();
            let target = it.next().map(str::to_string).or_else(|| env::var("KARMAZYN_DB").ok());
            let Some(target) = target else {
                println!("usage: db connect <host> [port]   (albo KARMAZYN_DB=host:port)");
                return Outcome::Err;
            };
            db_connect(app, &target, it.next())
        }
        _ => {
            if app.db.borrow().is_none() {
                let Ok(target) = env::var("KARMAZYN_DB") else {
                    println!("db: brak połączenia (`db connect <host> [port]` albo KARMAZYN_DB)");
                    return Outcome::Err;
                };
                if db_connect(app, &target, None) == Outcome::Err {
                    return Outcome::Err;
                }
            }
            let res = app.db.borrow_mut().as_mut().expect("połączono").query(rest);
            match res {
                Ok(v) => {
                    if let Some(e) = v.get("error") {
                        println!("db error: {e}");
                        return Outcome::Err;
                    }
                    let results = v.get("results").and_then(|r| r.as_array()).cloned().unwrap_or_default();
                    for r in &results {
                        println!("{r}");
                    }
                    let failed = results
                        .iter()
                        .any(|r| r.get("status").and_then(|s| s.as_str()) == Some("error"));
                    if failed { Outcome::Err } else { Outcome::Ok }
                }
                Err(e) => {
                    // po błędzie tunel jest niewiarygodny (jak w cynober_client)
                    *app.db.borrow_mut() = None;
                    println!("db: {e} — tunel zamknięty");
                    Outcome::Err
                }
            }
        }
    }
}

fn db_connect(app: &App, target: &str, port: Option<&str>) -> Outcome {
    let (host, port) = match (target.rsplit_once(':'), port) {
        (_, Some(p)) => (target.to_string(), p.parse().ok()),
        (Some((h, p)), None) if !h.contains(':') => (h.to_string(), p.parse().ok()),
        _ => (target.to_string(), Some(karmazyn_cynober::DEFAULT_PORT)),
    };
    let Some(port) = port else {
        println!("db: zły port");
        return Outcome::Err;
    };
    match karmazyn_cynober::Client::connect(&host, port, Duration::from_secs(30)) {
        Ok(c) => {
            let i = &c.info;
            println!(
                "db: {host}:{port} {}{}{} hsl={} {}",
                i.crypto_mode,
                i.hss_profile.as_deref().map(|p| format!("/{p}")).unwrap_or_default(),
                if i.psk { "+psk" } else { "" },
                i.hsl,
                i.node_remote
            );
            *app.db.borrow_mut() = Some(c);
            Outcome::Ok
        }
        Err(e) => {
            println!("db: {host}:{port}: {e}");
            Outcome::Err
        }
    }
}

/// Trwałość: `KARMAZYN_WORLD=<plik.kafd>` wprost (host), inaczej PID 1
/// podłącza `KARMAZYN_DISK` (domyślnie /dev/vda) jako ext4 pod /data.
/// Świat z dysku wraca do Store. `None` = trwałość wyłączona.
fn open_disk(app: &mut App) -> Option<(bool, String)> {
    let world = env::var("KARMAZYN_WORLD").ok().map(|w| w.trim().to_string());
    let (storage, line) = match world {
        Some(w) if w == "none" => return None,
        Some(w) if !w.is_empty() => (Some(Storage::new(w.clone().into(), None)), Ok(String::new())),
        _ => {
            let dev = match env::var("KARMAZYN_DISK") {
                Ok(p) if p.trim().is_empty() || p.trim() == "none" => return None,
                Ok(p) => p.trim().to_string(),
                Err(_) if is_pid1() => disk::DEFAULT_DEVICE.to_string(),
                Err(_) => return None,
            };
            if !is_pid1() {
                return Some((false, format!("{dev}: dysk tylko jako PID 1; na hoście KARMAZYN_WORLD=<plik.kafd>")));
            }
            *app.pending_device.borrow_mut() = Some(dev.clone());
            disk::attach_device(&dev, false)
        }
    };
    let mut detail = match line {
        Ok(d) => d,
        Err(e) => return Some((false, e)),
    };
    let st = storage?;
    *app.pending_device.borrow_mut() = None;
    let ok = attach_world(app, st, &mut detail);
    Some((ok, detail))
}

/// Wczytuje świat do Store i podpina magazyn. Opis dopisuje do `detail`.
fn attach_world(app: &App, st: Storage, detail: &mut String) -> bool {
    let sep = if detail.is_empty() { "" } else { ", " };
    let world = st.world.display().to_string();
    let ok = match st.load(&app.store) {
        Ok(Some(_)) => {
            app.lisp.remount_repl(&app.store);
            app.lua.remount_session(&app.store);
            let s = app.store.stats();
            detail.push_str(&format!("{sep}świat {world} atoms={} bubbles={}", s.total, s.bubbles));
            true
        }
        Ok(None) => {
            let how = if app.autosync { "autosync" } else { "`sync` zapisze stan" };
            detail.push_str(&format!("{sep}nowy świat {world}, {how}"));
            true
        }
        Err(e) => {
            detail.push_str(&format!("{sep}{e}"));
            false
        }
    };
    *app.storage.borrow_mut() = Some(st);
    // stan po starcie (wczytany albo pusty) liczy się jako zapisany
    app.synced.set(content_hash(&app.store.export_snapshot()));
    ok
}

/// Skrót treści Store dla autosync: atomy (S, E, token, payload), bąble,
/// powiązania, korzenie. Bez T i liczników META, więc odczyt, który tylko
/// grzeje atom, nie pisze na dysk. Temperaturę zapisuje `sync` albo
/// następna zmiana treści.
fn content_hash(snap: &StoreSnapshot) -> u64 {
    use std::hash::{Hash, Hasher};
    let mut h = std::collections::hash_map::DefaultHasher::new();
    for a in &snap.atoms {
        (a.id, &a.s, &a.e, a.value_token, &a.payload).hash(&mut h);
    }
    for b in &snap.bubbles {
        (b.id, &b.label, b.parent).hash(&mut h);
    }
    let mut binds: Vec<_> = snap.binds.iter().map(|b| (b.bid, &b.name, b.aid)).collect();
    binds.sort();
    binds.hash(&mut h);
    let mut roots = snap.roots.clone();
    roots.sort();
    roots.hash(&mut h);
    h.finish()
}

/// Zapis na dysk, gdy treść różni się od ostatnio zapisanej (`content_hash`).
/// `None` = nic do zrobienia (brak dysku, autosync wyłączony, bez zmian).
fn write_if_changed(app: &App) -> Option<Result<usize, String>> {
    let guard = app.storage.borrow();
    // świat nieczytelny: cicho (linia startowa, `disk` i `sync` mówią o tym)
    let st = guard.as_ref().filter(|s| s.writable())?;
    let h = content_hash(&app.store.export_snapshot());
    if h == app.synced.get() {
        return None;
    }
    let r = st.save(&app.store);
    if r.is_ok() {
        app.synced.set(h);
    }
    Some(r)
}

/// Po każdym poleceniu. Cicho, gdy się udało; błąd idzie na ekran.
fn autosync(app: &App) {
    if !app.autosync {
        return;
    }
    if let Some(Err(e)) = write_if_changed(app) {
        println!("autosync err: {e}");
    }
}

/// `edit <katalog>/<plik>`: edytor z kursorem na pliku fs. W bin/ i lib/
/// sprawdza składnię przy zapisie (ostrzega, zapisuje mimo to).
fn edit_file(app: &App, parts: &[&str]) -> Outcome {
    let target = parts.get(1).copied().unwrap_or("");
    let Some((dir, file)) = target
        .split_once('/')
        .filter(|(d, f)| !d.is_empty() && !f.is_empty() && !f.contains('/'))
    else {
        println!("usage: edit <katalog>/<plik>   np. edit bin/hej, edit lib/mat");
        return Outcome::Err;
    };
    let code = dir == "bin" || dir == "lib";
    let text = app
        .lua
        .fs_read(&app.store, dir, file)
        .map(|b| String::from_utf8_lossy(&b).into_owned())
        .unwrap_or_default();
    let mut save = |text: &str| -> Result<String, String> {
        let warn = if code {
            app.lua.check_syntax(target, text).err()
        } else {
            None
        };
        let kind = if code { "lua" } else { "text" };
        app.lua.fs_write(&app.store, dir, file, kind, text.as_bytes())?;
        let disk = match (app.autosync, write_if_changed(app)) {
            (true, Some(Ok(_))) => ", świat zapisany".to_string(),
            (true, Some(Err(e))) => format!(", dysk: {e}"),
            _ => String::new(),
        };
        Ok(match warn {
            Some(e) => format!("Zapisano{disk}, ale błąd składni: {e}"),
            None => format!("Zapisano {target}{disk}"),
        })
    };
    match editor::run(target, &text, &mut save) {
        Ok(()) => {
            println!("edit: zamknięto {target}");
            Outcome::Ok
        }
        Err(e) => {
            println!("{e}");
            Outcome::Err
        }
    }
}

fn disk_sync(app: &App) -> Outcome {
    let guard = app.storage.borrow();
    let Some(st) = guard.as_ref() else {
        println!("sync: brak świata (dysk albo KARMAZYN_WORLD)");
        return Outcome::Err;
    };
    let snap = app.store.export_snapshot();
    match st.save(&app.store) {
        Ok(n) => {
            app.synced.set(content_hash(&snap));
            let bytes = std::fs::metadata(&st.world).map(|m| m.len()).unwrap_or(0);
            println!("sync {} dokumenty={n} bytes={bytes}", st.world.display());
            Outcome::Ok
        }
        Err(e) => {
            println!("sync err: {e}");
            Outcome::Err
        }
    }
}

fn disk_status(app: &App, parts: &[&str]) -> Outcome {
    if parts.get(1).is_some_and(|p| p.eq_ignore_ascii_case("format")) {
        return disk_format(app);
    }
    let guard = app.storage.borrow();
    let Some(st) = guard.as_ref() else {
        match app.pending_device.borrow().as_deref() {
            Some(d) => println!("disk: {d} niepodłączony (`disk format` założy ext2)"),
            None => println!("disk: brak (KARMAZYN_DISK albo KARMAZYN_WORLD)"),
        }
        return Outcome::Err;
    };
    let head = std::fs::read(&st.world).ok();
    let (bytes, kind) = match &head {
        Some(b) if b.starts_with(b"KAFX") => (b.len(), "KAFX (AES-GCM)"),
        Some(b) if b.starts_with(b"KAFD") => (b.len(), "KAFD jawny"),
        Some(b) => (b.len(), "nieznany"),
        None => (0, "brak pliku"),
    };
    println!(
        "disk {} świat={} {kind} bytes={bytes} zapisy={} autosync={}{}",
        st.device.as_deref().unwrap_or("-"),
        st.world.display(),
        st.saves(),
        if app.autosync { "on" } else { "off" },
        if st.writable() { "" } else { " ZAPIS WSTRZYMANY" }
    );
    Outcome::Ok
}

/// `disk format`: tylko dysk, którego nie podłączono (nieznane dane).
/// Czyści go, zakłada ext2, montuje i zaczyna nowy świat.
fn disk_format(app: &App) -> Outcome {
    if app.storage.borrow().is_some() {
        println!("disk format: dysk już podłączony — format usunąłby świat");
        return Outcome::Err;
    }
    let Some(dev) = app.pending_device.borrow().clone() else {
        println!("disk format: brak urządzenia do sformatowania");
        return Outcome::Err;
    };
    match disk::attach_device(&dev, true) {
        (Some(st), Ok(mut detail)) => {
            *app.pending_device.borrow_mut() = None;
            attach_world(app, st, &mut detail);
            println!("disk format: {detail}");
            Outcome::Ok
        }
        (_, Err(e)) | (None, Ok(e)) => {
            println!("disk format: {e}");
            Outcome::Err
        }
    }
}

fn boot_line(color: bool, code: &str, name: &str, detail: &str) {
    let tag = match (color, code) {
        (true, "ok") => "[\x1b[1;32m OK \x1b[0m]",
        (false, "ok") => "[ OK ]",
        (true, _) => "[\x1b[1;33mWARN\x1b[0m]",
        (false, _) => "[WARN]",
    };
    if detail.is_empty() {
        println!("  {tag} {name}");
    } else {
        println!("  {tag} {name} — {detail}");
    }
}

fn run_tool(app: &App, name: &str) -> Outcome {
    if name.is_empty() {
        let names = app.lua.all_tool_names(&app.store);
        if names.is_empty() {
            println!("usage: tool <name>  (brak lua_bin)");
            return Outcome::Err;
        }
        println!("narzędzia (fs bin + lua_bin):");
        for n in names {
            println!("  {n}");
        }
        println!("uzycie: tool ls");
        return Outcome::Ok;
    }
    match app.lua.run_tool(&app.store, name) {
        Ok(s) if s.starts_with("blad:") => {
            println!("{s}");
            Outcome::Err
        }
        Ok(s) => {
            if !s.is_empty() {
                println!("{s}");
            }
            Outcome::Ok
        }
        Err(e) => {
            println!("{e}");
            Outcome::Err
        }
    }
}

fn eval_lua(app: &App, src: &str) -> Outcome {
    let s = app.lua.eval_line(&app.store, src);
    if !s.is_empty() {
        println!("{s}");
    }
    Outcome::Ok
}

/// `@etykieta` w poleceniu powłoki → id najnowszego bąbla z tą etykietą.
/// Skrypty nie zależą od tego, ile bąbli założyły sesje (repl, lua, fs).
fn resolve_labels(s: &Store, line: &str) -> Result<String, String> {
    if !line.contains('@') {
        return Ok(line.to_string());
    }
    let mut out = Vec::new();
    for word in line.split_whitespace() {
        match word.strip_prefix('@').filter(|l| !l.is_empty()) {
            Some(label) => {
                let bid = s
                    .bubble_ids()
                    .into_iter()
                    .filter(|b| s.bubble_label(*b).as_deref() == Some(label))
                    .max()
                    .ok_or_else(|| format!("brak bąbla @{label}"))?;
                out.push(bid.to_string());
            }
            None => out.push(word.to_string()),
        }
    }
    Ok(out.join(" "))
}

fn dispatch_cmd(s: &Store, line: &str) -> Outcome {
    let parts: Vec<&str> = line.split_whitespace().collect();
    if parts.is_empty() {
        return Outcome::Ok;
    }
    let cmd = parts[0].to_ascii_lowercase();
    match cmd.as_str() {
        "q" | "quit" | "exit" => return Outcome::Quit,
        "help" | "?" => print_help(),
        "version" | "ver" => {
            println!("karmazyn_shell {VERSION}");
        }
        "stats" => {
            let st = s.stats();
            println!(
                "total={} hot={} warm={} cold={} tomb={} alive={} dead={} reaped={} retained_tomb={} bubbles={}",
                st.total,
                st.hot,
                st.warm,
                st.cold,
                st.tomb,
                st.alive,
                st.dead,
                st.reaped,
                st.retained_tomb,
                st.bubbles
            );
        }
        "save" => {
            let Some(path) = parts.get(1) else {
                println!("usage: save <path>");
                return Outcome::Err;
            };
            match s.save_snapshot_file(path) {
                Ok(()) => println!("saved {path}"),
                Err(e) => {
                    println!("save err: {e}");
                    return Outcome::Err;
                }
            }
        }
        "atom" => {
            if parts.len() < 3 {
                println!("usage: atom <s> <e> [t]");
                return Outcome::Err;
            }
            let t = parts
                .get(3)
                .and_then(|x| x.parse::<f64>().ok())
                .unwrap_or(T_INIT);
            let id = s.atom_new(parts[1], parts[2], t);
            let st = s.get_atom_t(id).map(state_for_t).unwrap_or("?");
            println!(
                "aid={id} state={st} t={:.3}",
                s.get_atom_t(id).unwrap_or(-1.0)
            );
        }
        "upsert" => {
            // upsert <aid> <s> <e> [t] [token]
            if parts.len() < 4 {
                println!("usage: upsert <aid> <s> <e> [t] [token]");
                return Outcome::Err;
            }
            let Ok(aid) = parts[1].parse::<u32>() else {
                println!("bad aid");
                return Outcome::Err;
            };
            let t = parts
                .get(4)
                .and_then(|x| x.parse::<f64>().ok())
                .unwrap_or(T_INIT);
            let tok = parts
                .get(5)
                .and_then(|x| x.parse::<u64>().ok())
                .unwrap_or(0);
            if s.atom_upsert(aid, parts[2], parts[3], t, tok) {
                println!(
                    "upsert aid={aid} t={t:.3} token={tok} state={}",
                    s.get_atom_t(aid).map(state_for_t).unwrap_or("?")
                );
            } else {
                println!("upsert failed");
                return Outcome::Err;
            }
        }
        "info" => {
            let Some(id) = parts.get(1).and_then(|x| x.parse::<u32>().ok()) else {
                println!("usage: info <aid>");
                return Outcome::Err;
            };
            match s.atom_se(id) {
                Some((ss, ee)) => {
                    let t = s.get_atom_t(id).unwrap_or(-1.0);
                    let st = s.get_atom_t(id).map(state_for_t).unwrap_or("?");
                    let dead = s.atom_is_dead(id).unwrap_or(false);
                    let tok = s.atom_value_token(id).unwrap_or(0);
                    println!(
                        "aid={id} s={ss} e={ee} t={t:.3} state={st} dead={dead} token={tok}"
                    );
                }
                None => {
                    println!("no atom {id}");
                    return Outcome::Err;
                }
            }
        }
        "heat" => {
            let Some(id) = parts.get(1).and_then(|x| x.parse::<u32>().ok()) else {
                println!("usage: heat <aid>");
                return Outcome::Err;
            };
            if s.heat(id) {
                println!(
                    "aid={id} t={:.3} state={}",
                    s.get_atom_t(id).unwrap_or(-1.0),
                    s.get_atom_t(id).map(state_for_t).unwrap_or("?")
                );
            } else {
                println!("no atom {id}");
                return Outcome::Err;
            }
        }
        "bubble" => {
            // bubble [label] [parent_bid]
            let label = parts.get(1).copied().unwrap_or("b");
            let parent = parts.get(2).and_then(|x| x.parse::<u32>().ok());
            if parts.get(2).is_some() && parent.is_none() {
                println!("usage: bubble [label] [parent_bid]");
                return Outcome::Err;
            }
            let bid = s.bubble_new(label, parent);
            match parent {
                Some(p) => println!("bid={bid} parent={p}"),
                None => println!("bid={bid}"),
            }
        }
        "bubbles" | "listb" => {
            let mut ids = s.bubble_ids();
            ids.sort_unstable();
            if ids.is_empty() {
                println!("(no bubbles)");
            } else {
                for bid in ids {
                    let label = s.bubble_label(bid).unwrap_or_else(|| "?".into());
                    let parent = match s.bubble_parent(bid) {
                        Some(Some(p)) => format!("{p}"),
                        Some(None) => "-".into(),
                        None => "?".into(),
                    };
                    let root = if s.is_root(bid) { "root" } else { "" };
                    let nbind = s
                        .bubble_bindings(bid)
                        .map(|b| b.len())
                        .unwrap_or(0);
                    println!(
                        "bid={bid} label={label} parent={parent} binds={nbind} {root}"
                    );
                }
            }
        }
        "roots" => {
            let roots = s.root_ids();
            if roots.is_empty() {
                println!("(no roots)");
            } else {
                for bid in roots {
                    let label = s.bubble_label(bid).unwrap_or_else(|| "?".into());
                    println!("root bid={bid} label={label}");
                }
            }
        }
        "binds" => {
            let Some(bid) = parts.get(1).and_then(|x| x.parse::<u32>().ok()) else {
                println!("usage: binds <bid>");
                return Outcome::Err;
            };
            match s.bubble_bindings(bid) {
                None => {
                    println!("no bubble {bid}");
                    return Outcome::Err;
                }
                Some(v) if v.is_empty() => println!("(no bindings)"),
                Some(v) => {
                    for (name, aid) in v {
                        println!("{name} → {aid}");
                    }
                }
            }
        }
        "root" => {
            let Some(bid) = parts.get(1).and_then(|x| x.parse::<u32>().ok()) else {
                println!("usage: root <bid>");
                return Outcome::Err;
            };
            s.set_root(bid);
            println!("root={bid}");
        }
        "unroot" => {
            let Some(bid) = parts.get(1).and_then(|x| x.parse::<u32>().ok()) else {
                println!("usage: unroot <bid>");
                return Outcome::Err;
            };
            s.unset_root(bid);
            println!("unset_root={bid}");
        }
        "bind" => {
            if parts.len() < 4 {
                println!("usage: bind <bid> <name> <aid>");
                return Outcome::Err;
            }
            let Ok(bid) = parts[1].parse::<u32>() else {
                println!("bad bid");
                return Outcome::Err;
            };
            let Ok(aid) = parts[3].parse::<u32>() else {
                println!("bad aid");
                return Outcome::Err;
            };
            match s.bind(bid, parts[2], aid) {
                Ok(()) => println!("bound {} → {aid} in bubble {bid}", parts[2]),
                Err(e) => {
                    println!("bind err: {e}");
                    return Outcome::Err;
                }
            }
        }
        "lookup" => {
            if parts.len() < 3 {
                println!("usage: lookup <bid> <name>");
                return Outcome::Err;
            }
            let Ok(bid) = parts[1].parse::<u32>() else {
                println!("bad bid");
                return Outcome::Err;
            };
            match s.lookup(bid, parts[2]) {
                Some(aid) => println!("aid={aid}"),
                None => println!("(none)"),
            }
        }
        "unbind" => {
            if parts.len() < 3 {
                println!("usage: unbind <bid> <name>");
                return Outcome::Err;
            }
            let Ok(bid) = parts[1].parse::<u32>() else {
                println!("bad bid");
                return Outcome::Err;
            };
            match s.unbind(bid, parts[2]) {
                Some(aid) => println!("unbound {} → was aid={aid}", parts[2]),
                None => {
                    println!("(none)");
                    return Outcome::Err;
                }
            }
        }
        "has" => {
            let Some(id) = parts.get(1).and_then(|x| x.parse::<u32>().ok()) else {
                println!("usage: has <aid>");
                return Outcome::Err;
            };
            println!("{}", s.has_atom(id));
        }
        "t" => {
            let Some(id) = parts.get(1).and_then(|x| x.parse::<u32>().ok()) else {
                println!("usage: t <aid>");
                return Outcome::Err;
            };
            match s.get_atom_t(id) {
                Some(t) => println!("t={t:.6} state={}", state_for_t(t)),
                None => {
                    println!("no atom {id}");
                    return Outcome::Err;
                }
            }
        }
        "set_t" | "sett" => {
            if parts.len() < 3 {
                println!("usage: set_t <aid> <t>");
                return Outcome::Err;
            }
            let Some(id) = parts.get(1).and_then(|x| x.parse::<u32>().ok()) else {
                println!("bad aid");
                return Outcome::Err;
            };
            let Some(t) = parts.get(2).and_then(|x| x.parse::<f64>().ok()) else {
                println!("bad t");
                return Outcome::Err;
            };
            if s.atom_set_t(id, t) {
                println!(
                    "aid={id} t={t:.3} state={}",
                    state_for_t(t)
                );
            } else {
                println!("no atom {id}");
                return Outcome::Err;
            }
        }
        "dead" | "is_dead" => {
            let Some(id) = parts.get(1).and_then(|x| x.parse::<u32>().ok()) else {
                println!("usage: dead <aid>");
                return Outcome::Err;
            };
            match s.atom_is_dead(id) {
                Some(d) => println!("{}", d),
                None => {
                    println!("no atom {id}");
                    return Outcome::Err;
                }
            }
        }
        "del" | "delete" | "rm" => {
            let Some(id) = parts.get(1).and_then(|x| x.parse::<u32>().ok()) else {
                println!("usage: del <aid>");
                return Outcome::Err;
            };
            if s.delete_atom(id) {
                println!("deleted {id}");
            } else {
                println!("no atom {id}");
                return Outcome::Err;
            }
        }
        "val" | "value" | "getval" => {
            let Some(id) = parts.get(1).and_then(|x| x.parse::<u32>().ok()) else {
                println!("usage: val <aid>");
                return Outcome::Err;
            };
            match s.atom_value_token(id) {
                Some(v) => println!("token={v}"),
                None => {
                    println!("no atom {id}");
                    return Outcome::Err;
                }
            }
        }
        "setval" | "set_value" => {
            if parts.len() < 3 {
                println!("usage: setval <aid> <u64>");
                return Outcome::Err;
            }
            let Some(id) = parts.get(1).and_then(|x| x.parse::<u32>().ok()) else {
                println!("bad aid");
                return Outcome::Err;
            };
            let Some(tok) = parts.get(2).and_then(|x| x.parse::<u64>().ok()) else {
                println!("bad token");
                return Outcome::Err;
            };
            if s.atom_set_value_token(id, tok) {
                println!("aid={id} token={tok}");
            } else {
                println!("no atom {id}");
                return Outcome::Err;
            }
        }
        "list" | "atoms" | "ls" => {
            let mut ids = s.atom_ids();
            ids.sort_unstable();
            if ids.is_empty() {
                println!("(no atoms)");
            } else {
                for id in ids {
                    let t = s.get_atom_t(id).unwrap_or(-1.0);
                    let st = s.get_atom_t(id).map(state_for_t).unwrap_or("?");
                    let dead = s.atom_is_dead(id).unwrap_or(false);
                    let se = s
                        .atom_se(id)
                        .map(|(a, b)| format!("{a}/{b}"))
                        .unwrap_or_else(|| "?".into());
                    println!("aid={id} {se} t={t:.3} state={st} dead={dead}");
                }
            }
        }
        "echo" => {
            if parts.len() > 1 {
                println!("{}", parts[1..].join(" "));
            }
        }
        "assert" => {
            // batch-friendly checks (exit Err if false)
            //   assert has <aid>
            //   assert nohas <aid>
            //   assert lookup <bid> <name> <aid>
            //   assert dead <aid>
            //   assert nodead <aid>
            //   assert t <aid> <op> <f64>   op: eq|gt|lt|ge|le
            //   assert val <aid> <u64>
            //   assert stats <field> <op> <n>  field: total|alive|dead|bubbles|reaped|…
            //   assert root <bid>
            //   assert noroot <bid>
            if parts.len() < 2 {
                println!(
                    "usage: assert has|nohas|dead|nodead|lookup|t|val|stats|root|noroot …"
                );
                return Outcome::Err;
            }
            let sub = parts[1].to_ascii_lowercase();
            let ok = match sub.as_str() {
                "has" => {
                    let Some(id) = parts.get(2).and_then(|x| x.parse::<u32>().ok()) else {
                        println!("usage: assert has <aid>");
                        return Outcome::Err;
                    };
                    s.has_atom(id)
                }
                "nohas" | "nothas" | "!has" => {
                    let Some(id) = parts.get(2).and_then(|x| x.parse::<u32>().ok()) else {
                        println!("usage: assert nohas <aid>");
                        return Outcome::Err;
                    };
                    !s.has_atom(id)
                }
                "dead" => {
                    let Some(id) = parts.get(2).and_then(|x| x.parse::<u32>().ok()) else {
                        println!("usage: assert dead <aid>");
                        return Outcome::Err;
                    };
                    s.atom_is_dead(id) == Some(true)
                }
                "nodead" | "alive" => {
                    let Some(id) = parts.get(2).and_then(|x| x.parse::<u32>().ok()) else {
                        println!("usage: assert nodead <aid>");
                        return Outcome::Err;
                    };
                    s.atom_is_dead(id) == Some(false)
                }
                "lookup" => {
                    if parts.len() < 5 {
                        println!("usage: assert lookup <bid> <name> <aid>");
                        return Outcome::Err;
                    }
                    let Ok(bid) = parts[2].parse::<u32>() else {
                        println!("bad bid");
                        return Outcome::Err;
                    };
                    let Ok(want) = parts[4].parse::<u32>() else {
                        println!("bad aid");
                        return Outcome::Err;
                    };
                    s.lookup(bid, parts[3]) == Some(want)
                }
                "t" => {
                    if parts.len() < 5 {
                        println!("usage: assert t <aid> eq|gt|lt|ge|le <f64>");
                        return Outcome::Err;
                    }
                    let Some(id) = parts.get(2).and_then(|x| x.parse::<u32>().ok()) else {
                        println!("bad aid");
                        return Outcome::Err;
                    };
                    let op = parts[3].to_ascii_lowercase();
                    let Some(rhs) = parts.get(4).and_then(|x| x.parse::<f64>().ok()) else {
                        println!("bad f64");
                        return Outcome::Err;
                    };
                    match s.get_atom_t(id) {
                        None => false,
                        Some(t) => match op.as_str() {
                            "eq" | "==" => (t - rhs).abs() < 1e-9,
                            "gt" | ">" => t > rhs,
                            "lt" | "<" => t < rhs,
                            "ge" | ">=" => t >= rhs,
                            "le" | "<=" => t <= rhs,
                            _ => {
                                println!("assert t: bad op (eq|gt|lt|ge|le)");
                                return Outcome::Err;
                            }
                        },
                    }
                }
                "val" | "token" => {
                    if parts.len() < 4 {
                        println!("usage: assert val <aid> <u64>");
                        return Outcome::Err;
                    }
                    let Some(id) = parts.get(2).and_then(|x| x.parse::<u32>().ok()) else {
                        println!("bad aid");
                        return Outcome::Err;
                    };
                    let Some(want) = parts.get(3).and_then(|x| x.parse::<u64>().ok()) else {
                        println!("bad token");
                        return Outcome::Err;
                    };
                    s.atom_value_token(id) == Some(want)
                }
                "stats" => {
                    if parts.len() < 5 {
                        println!(
                            "usage: assert stats <field> eq|gt|lt|ge|le <n>"
                        );
                        return Outcome::Err;
                    }
                    let field = parts[2].to_ascii_lowercase();
                    let op = parts[3].to_ascii_lowercase();
                    let Some(rhs) = parts.get(4).and_then(|x| x.parse::<u64>().ok()) else {
                        println!("bad n");
                        return Outcome::Err;
                    };
                    let st = s.stats();
                    let lhs: u64 = match field.as_str() {
                        "total" => st.total as u64,
                        "hot" => st.hot as u64,
                        "warm" => st.warm as u64,
                        "cold" => st.cold as u64,
                        "tomb" => st.tomb as u64,
                        "alive" => st.alive as u64,
                        "dead" => st.dead as u64,
                        "reaped" => st.reaped,
                        "retained_tomb" | "retained" => st.retained_tomb as u64,
                        "bubbles" => st.bubbles as u64,
                        _ => {
                            println!(
                                "assert stats: field total|hot|warm|cold|tomb|alive|dead|reaped|retained|bubbles"
                            );
                            return Outcome::Err;
                        }
                    };
                    match op.as_str() {
                        "eq" | "==" => lhs == rhs,
                        "gt" | ">" => lhs > rhs,
                        "lt" | "<" => lhs < rhs,
                        "ge" | ">=" => lhs >= rhs,
                        "le" | "<=" => lhs <= rhs,
                        _ => {
                            println!("assert stats: bad op");
                            return Outcome::Err;
                        }
                    }
                }
                "root" => {
                    let Some(bid) = parts.get(2).and_then(|x| x.parse::<u32>().ok()) else {
                        println!("usage: assert root <bid>");
                        return Outcome::Err;
                    };
                    s.is_root(bid)
                }
                "noroot" => {
                    let Some(bid) = parts.get(2).and_then(|x| x.parse::<u32>().ok()) else {
                        println!("usage: assert noroot <bid>");
                        return Outcome::Err;
                    };
                    !s.is_root(bid)
                }
                other => {
                    println!("assert: unknown check `{other}`");
                    return Outcome::Err;
                }
            };
            if ok {
                println!("assert ok");
            } else {
                println!("assert FAILED: {}", parts[1..].join(" "));
                return Outcome::Err;
            }
        }
        other => {
            println!("unknown command: {other} (help)");
            return Outcome::Err;
        }
    }
    Outcome::Ok
}

fn print_help() {
    println!(
        "commands:
  version                       shell version
  stats                         store counters
  list | atoms                  list atoms (s/e, T, state)
  bubbles | listb               list bubbles
  roots                         list root bubble ids
  binds <bid>                   list bindings in bubble
  info <aid>                    atom s/e/t/token
  atom <s> <e> [t]              create atom (default t=T_INIT)
  upsert <aid> <s> <e> [t] [tok]  create/update fixed id
  heat <aid>                    +HEAT_READ (same as touch / read)
  set_t <aid> <t>               absolute T (no heat counters)
  tick [n]                      n store ticks and the same lua epoch
  settle <n>                    n ticks and the same lua epoch
  bubble [label] [parent]       new bubble (optional parent)
  @label                        w każdym poleceniu: id najnowszego bąbla z etykietą
  root <bid> / unroot <bid>     root set
  bind <bid> <name> <aid>       bind name → atom
  unbind <bid> <name>           remove binding
  lookup <bid> <name>           resolve (also +HEAT_READ if thermal)
  has <aid> / t <aid> / dead <aid>
  del <aid>                     delete atom
  val <aid>                     read value token
  setval <aid> <u64>            write token (+HEAT_WRITE if thermal)
  assert has|nohas|dead|nodead|lookup|t|val|stats|root|noroot …
  echo <text>
  save <path> / load <path>     KSUB_SNAP v1. load remounts lisp and lua
  sync                          świat KAFD (KAFX) na dysk: /data/cynober/worlds/*.kafd
                                po każdym poleceniu sam, gdy zmieniła się treść
                                (KARMAZYN_AUTOSYNC=0 wyłącza)
  edit <katalog>/<plik>         edytor z kursorem (^S zapis, ^Q wyjście, ^K linia, ^L odśwież)
  disk / disk format            stan świata / ext2 na dysku z nieznanymi danymi
  db connect <host> [port]      tunel Cynober-Secure-1.2 (HSS/ECDH + HSL) do Karmin_DB
  db <zapytanie>                KarminQL przez tunel (np. db ZDROWIE); db info / db close
  (define x 10) / lisp <expr>   mini-Lisp guest (atoms = vars)
  lua <chunk>                   Lua guest (mlua). return karmazyn._VERSION
                                limit instrukcji na chunk: KARMAZYN_LUA_BUDGET (0 = brak)
  tool <name> [args] | :tool    narzędzie: najpierw fs bin/<name>, potem lua_bin. bare tool lists names
  help | quit

batch: non-zero exit if a command fails (assert/save/bind/…)"
    );
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn label_refs_resolve_to_newest_bubble() {
        let s = Store::new(true);
        let first = s.bubble_new("r", None);
        let other = s.bubble_new("x", None);
        assert_eq!(resolve_labels(&s, "bind @r v 0").unwrap(), format!("bind {first} v 0"));
        let newer = s.bubble_new("r", Some(other));
        assert_eq!(
            resolve_labels(&s, "bubble c @x  @r").unwrap(),
            format!("bubble c {other} {newer}")
        );
        assert_eq!(resolve_labels(&s, "echo a@b @").unwrap(), "echo a@b @");
        assert!(resolve_labels(&s, "root @brak").unwrap_err().contains("@brak"));
    }

    #[test]
    fn content_hash_ignores_heat_not_content() {
        let s = Store::new(true);
        let a = s.atom_new("x", "y", 50.0);
        let b = s.bubble_new("dir", None);
        s.set_root(b);
        s.bind(b, "x", a).unwrap();
        let h0 = content_hash(&s.export_snapshot());

        s.heat(a);
        s.settle(3);
        assert!(s.has_atom(a));
        assert_eq!(content_hash(&s.export_snapshot()), h0);

        s.atom_set_value_token(a, 7);
        let h1 = content_hash(&s.export_snapshot());
        assert_ne!(h1, h0);
        s.atom_set_guest(a, 7, Some(b"kod".to_vec()));
        assert_ne!(content_hash(&s.export_snapshot()), h1);
        s.unbind(b, "x");
        assert_ne!(content_hash(&s.export_snapshot()), h1);
    }
}
