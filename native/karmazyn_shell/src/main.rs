//! KarmazynOS native shell (Stage 2 MVP) — pure Rust over substrate rlib.
//!
//!   cd native/karmazyn_shell
//!   cargo run --release
//!
//! Commands: help | stats | atom <s> <e> [t] | heat <id> | tick [n] | settle <n>
//!           bubble [label] | root <bid> | bind <bid> <name> <aid> | lookup <bid> <name>
//!           has <aid> | t <aid> | quit

use karmazyn_substrate::{state_for_t, Store, T_INIT};
use std::io::{self, BufRead, Write};

fn main() {
    let thermal = true;
    let store = Store::new(thermal);
    println!("karmazyn_shell 0.1 — Stage 2 MVP (native, no Python)");
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
  help | quit"
    );
}
