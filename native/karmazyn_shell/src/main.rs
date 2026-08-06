//! KarmazynOS native shell (Stage 2) — pure Rust over substrate rlib.
//!
//!   cd native/karmazyn_shell
//!   cargo run --release
//!   cargo run --release -- -e "atom var x 50" -e stats -e quit
//!
//! Commands: help | stats | atom | heat | tick | settle | bubble | root | bind |
//!           lookup | has | t | save <path> | load <path> | quit

use karmazyn_substrate::{state_for_t, Store, T_INIT};
use std::env;
use std::io::{self, BufRead, Write};
use std::process;

fn main() {
    let thermal = true;
    let store = Store::new(thermal);
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
        } else if args[i] == "-h" || args[i] == "--help" {
            println!("karmazyn_shell — native Stage 2 shell (no Python)");
            println!("  interactive:  karmazyn_shell");
            println!("  batch:        karmazyn_shell -e \"atom var x 50\" -e stats");
            println!("  script file:  karmazyn_shell commands.ksh");
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
        println!("karmazyn_shell 0.2 — batch ({} cmds)", batch.len());
        for cmd in batch {
            println!("k$ {cmd}");
            if !dispatch(&store, &cmd) {
                break;
            }
        }
        return;
    }

    println!("karmazyn_shell 0.2 — Stage 2 (native, no Python)");
    println!("thermal={thermal}  type `help`");

    let stdin = io::stdin();
    let mut stdout = io::stdout();
    loop {
        print!("k$ ");
        let _ = stdout.flush();
        let mut line = String::new();
        if stdin.lock().read_line(&mut line).is_err() {
            break;
        }
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        if !dispatch(&store, line) {
            break;
        }
    }
    println!("bye");
}

fn dispatch(s: &Store, line: &str) -> bool {
    let parts: Vec<&str> = line.split_whitespace().collect();
    let cmd = parts[0].to_ascii_lowercase();
    match cmd.as_str() {
        "q" | "quit" | "exit" => return false,
        "help" | "?" => print_help(),
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
                return true;
            };
            match s.save_snapshot_file(path) {
                Ok(()) => println!("saved {path}"),
                Err(e) => println!("save err: {e}"),
            }
        }
        "load" => {
            let Some(path) = parts.get(1) else {
                println!("usage: load <path>");
                return true;
            };
            match s.load_snapshot_file(path) {
                Ok(()) => {
                    let st = s.stats();
                    println!(
                        "loaded {path}  atoms={} bubbles={} reaped={}",
                        st.total, st.bubbles, st.reaped
                    );
                }
                Err(e) => println!("load err: {e}"),
            }
        }
        "atom" => {
            if parts.len() < 3 {
                println!("usage: atom <s> <e> [t]");
                return true;
            }
            let t = parts
                .get(3)
                .and_then(|x| x.parse::<f64>().ok())
                .unwrap_or(T_INIT);
            let id = s.atom_new(parts[1], parts[2], t);
            let st = s
                .get_atom_t(id)
                .map(state_for_t)
                .unwrap_or("?");
            println!("aid={id} state={st} t={:.3}", s.get_atom_t(id).unwrap_or(-1.0));
        }
        "heat" => {
            let Some(id) = parts.get(1).and_then(|x| x.parse::<u32>().ok()) else {
                println!("usage: heat <aid>");
                return true;
            };
            if s.heat(id) {
                println!(
                    "aid={id} t={:.3} state={}",
                    s.get_atom_t(id).unwrap_or(-1.0),
                    s.get_atom_t(id).map(state_for_t).unwrap_or("?")
                );
            } else {
                println!("no atom {id}");
            }
        }
        "tick" => {
            let n = parts
                .get(1)
                .and_then(|x| x.parse::<u32>().ok())
                .unwrap_or(1);
            if n <= 1 {
                s.tick();
            } else {
                s.settle(n);
            }
            println!("tick x{n}");
        }
        "settle" => {
            let Some(n) = parts.get(1).and_then(|x| x.parse::<u32>().ok()) else {
                println!("usage: settle <n>");
                return true;
            };
            s.settle(n);
            println!("settle {n}");
        }
        "bubble" => {
            let label = parts.get(1).copied().unwrap_or("b");
            let bid = s.bubble_new(label, None);
            println!("bid={bid}");
        }
        "root" => {
            let Some(bid) = parts.get(1).and_then(|x| x.parse::<u32>().ok()) else {
                println!("usage: root <bid>");
                return true;
            };
            s.set_root(bid);
            println!("root={bid}");
        }
        "unroot" => {
            let Some(bid) = parts.get(1).and_then(|x| x.parse::<u32>().ok()) else {
                println!("usage: unroot <bid>");
                return true;
            };
            s.unset_root(bid);
            println!("unset_root={bid}");
        }
        "bind" => {
            if parts.len() < 4 {
                println!("usage: bind <bid> <name> <aid>");
                return true;
            }
            let Ok(bid) = parts[1].parse::<u32>() else {
                println!("bad bid");
                return true;
            };
            let Ok(aid) = parts[3].parse::<u32>() else {
                println!("bad aid");
                return true;
            };
            match s.bind(bid, parts[2], aid) {
                Ok(()) => println!("bound {} → {aid} in bubble {bid}", parts[2]),
                Err(e) => println!("bind err: {e}"),
            }
        }
        "lookup" => {
            if parts.len() < 3 {
                println!("usage: lookup <bid> <name>");
                return true;
            }
            let Ok(bid) = parts[1].parse::<u32>() else {
                println!("bad bid");
                return true;
            };
            match s.lookup(bid, parts[2]) {
                Some(aid) => println!("aid={aid}"),
                None => println!("(none)"),
            }
        }
        "has" => {
            let Some(id) = parts.get(1).and_then(|x| x.parse::<u32>().ok()) else {
                println!("usage: has <aid>");
                return true;
            };
            println!("{}", s.has_atom(id));
        }
        "t" => {
            let Some(id) = parts.get(1).and_then(|x| x.parse::<u32>().ok()) else {
                println!("usage: t <aid>");
                return true;
            };
            match s.get_atom_t(id) {
                Some(t) => println!("t={t:.6} state={}", state_for_t(t)),
                None => println!("no atom {id}"),
            }
        }
        other => println!("unknown command: {other} (help)"),
    }
    true
}

fn print_help() {
    println!(
        "commands:
  stats                         store counters
  atom <s> <e> [t]              create atom (default t=T_INIT)
  heat <aid>                    heat atom
  tick [n]                      one tick or settle n
  settle <n>                    n ticks
  bubble [label]                new bubble
  root <bid> / unroot <bid>     root set
  bind <bid> <name> <aid>       bind name → atom
  lookup <bid> <name>           resolve binding
  has <aid> / t <aid>           probe atom
  save <path> / load <path>     KSUB_SNAP v1 persist (no Python)
  help | quit"
    );
}
