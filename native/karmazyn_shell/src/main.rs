//! KarmazynOS native shell (Stage 2) — pure Rust over substrate rlib.
//!
//!   cd native/karmazyn_shell
//!   cargo run --release
//!   cargo run --release -- -e "atom var x 50" -e stats -e quit
//!   cargo run --release -- examples/smoke.ksh
//!
//! Commands: help | version | stats | atom | … | save | load | quit
//! Lisp guest: line starting with `(` → karmazyn_lisp::Evaluator::eval_line.

mod disk;
mod editor;

use disk::Disk;
use karmazyn_lisp::Evaluator;
use karmazyn_lua::Evaluator as LuaEvaluator;

use karmazyn_substrate::{state_for_t, Store, StoreSnapshot, T_INIT};
use std::env;
use std::io::{self, BufRead, IsTerminal, Write};
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
    disk: Option<Disk>,
    /// Po każdym poleceniu zapis na dysk, jeśli Store się zmienił.
    autosync: bool,
    /// Skrót ostatniego snapshotu na dysku (albo wczytanego z dysku).
    synced: std::cell::Cell<u64>,
}

fn main() {
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
        disk: None,
        autosync: autosync_on,
        synced: std::cell::Cell::new(0),
    };
    let disk_line = open_disk(&mut app);
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
    print_boot(tools, &disk_line);
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
        disk_status(app)
    } else if head.eq_ignore_ascii_case("tick") {
        shell_tick(app, &parts)
    } else if head.eq_ignore_ascii_case("settle") {
        shell_settle(app, &parts)
    } else {
        dispatch_cmd(&app.store, line)
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

fn print_boot(tools: usize, disk: &Option<(bool, String)>) {
    let color = io::stdout().is_terminal();
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
}

/// KARMAZYN_DISK=<urządzenie albo plik>; PID 1 bez zmiennej bierze /dev/vda.
/// Najnowszy snapshot z dysku wraca do Store. `None` = dysk wyłączony.
fn open_disk(app: &mut App) -> Option<(bool, String)> {
    let path = match env::var("KARMAZYN_DISK") {
        Ok(p) if p.trim().is_empty() || p.trim() == "none" => return None,
        Ok(p) => p.trim().to_string(),
        Err(_) if is_pid1() => disk::DEFAULT_DEVICE.to_string(),
        Err(_) => return None,
    };
    let warn = if is_pid1() {
        disk::prepare(std::path::Path::new(&path))
    } else {
        Vec::new()
    };
    let d = Disk::new(&path);
    let line = match d.read_latest() {
        Err(e) => {
            let mut msg = e;
            if !warn.is_empty() {
                msg = format!("{msg} ({})", warn.join("; "));
            }
            return Some((false, msg));
        }
        Ok(None) => (
            true,
            format!(
                "{path} pusty{}",
                if app.autosync { ", autosync" } else { ", `sync` zapisze stan" }
            ),
        ),
        Ok(Some((slot, data))) => match String::from_utf8(data)
            .map_err(|e| e.to_string())
            .and_then(|t| StoreSnapshot::from_text(&t))
        {
            Ok(snap) => {
                app.store.import_snapshot(&snap);
                app.lisp.remount_repl(&app.store);
                app.lua.remount_session(&app.store);
                let st = app.store.stats();
                (
                    true,
                    format!("{path} gen={} atoms={} bubbles={}", slot.gen, st.total, st.bubbles),
                )
            }
            Err(e) => (false, format!("{path} gen={}: {e}", slot.gen)),
        },
    };
    app.disk = Some(d);
    // stan po starcie (wczytany albo pusty) liczy się jako zapisany
    app.synced.set(content_hash(&app.store.export_snapshot()));
    Some(line)
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
fn write_if_changed(app: &App) -> Option<Result<disk::Slot, String>> {
    let d = app.disk.as_ref()?;
    let snap = app.store.export_snapshot();
    let h = content_hash(&snap);
    if h == app.synced.get() {
        return None;
    }
    let text = snap.to_text();
    let r = d.write_next(text.as_bytes());
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
            (true, Some(Ok(s))) => format!(", dysk gen={}", s.gen),
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
    let Some(d) = &app.disk else {
        println!("sync: brak dysku (KARMAZYN_DISK)");
        return Outcome::Err;
    };
    let snap = app.store.export_snapshot();
    let text = snap.to_text();
    match d.write_next(text.as_bytes()) {
        Ok(s) => {
            app.synced.set(content_hash(&snap));
            println!("sync {} gen={} bytes={}", d.path().display(), s.gen, s.len);
            Outcome::Ok
        }
        Err(e) => {
            println!("sync err: {e}");
            Outcome::Err
        }
    }
}

fn disk_status(app: &App) -> Outcome {
    let Some(d) = &app.disk else {
        println!("disk: brak (KARMAZYN_DISK)");
        return Outcome::Err;
    };
    match (d.size(), d.slots()) {
        (Ok(size), Ok(slots)) => {
            println!(
                "disk {} size={size} autosync={}",
                d.path().display(),
                if app.autosync { "on" } else { "off" }
            );
            for (name, s) in ["A", "B"].iter().zip(slots) {
                match s {
                    Some(s) => println!("  {name} gen={} bytes={}", s.gen, s.len),
                    None => println!("  {name} pusty"),
                }
            }
            Outcome::Ok
        }
        (Err(e), _) | (_, Err(e)) => {
            println!("disk err: {e}");
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
  sync                          snapshot na dysk (KARMAZYN_DISK, slot A/B)
                                po każdym poleceniu sam, gdy zmieniła się treść
                                (KARMAZYN_AUTOSYNC=0 wyłącza)
  edit <katalog>/<plik>         edytor z kursorem (^S zapis, ^Q wyjście, ^K linia)
  disk                          stan dysku i slotów
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
