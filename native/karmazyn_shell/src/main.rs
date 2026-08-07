//! KarmazynOS native shell (Stage 2) — pure Rust over substrate rlib.
//!
//!   cd native/karmazyn_shell
//!   cargo run --release
//!   cargo run --release -- -e "atom var x 50" -e stats -e quit
//!   cargo run --release -- examples/smoke.ksh
//!
//! Commands: help | version | stats | atom | upsert | heat | tick | settle |
//!           bubble | bubbles | roots | binds | info | root | unroot |
//!           bind | unbind | lookup | has | t | set_t | dead | del |
//!           val | setval | list | assert | echo | save | load | quit

use karmazyn_substrate::{state_for_t, Store, T_INIT};
use std::env;
use std::io::{self, BufRead, Write};
use std::process;

const VERSION: &str = env!("CARGO_PKG_VERSION");

#[derive(Clone, Copy, PartialEq, Eq)]
enum Outcome {
    Ok,
    Quit,
    Err,
}

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
            match dispatch(&store, &cmd) {
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

    println!("karmazyn_shell {VERSION} — Stage 2 (native, no Python)");
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
        match dispatch(&store, line) {
            Outcome::Ok => {}
            Outcome::Quit => break,
            Outcome::Err => {
                // interactive: print already done; stay in REPL
            }
        }
    }
    println!("bye");
}

fn dispatch(s: &Store, line: &str) -> Outcome {
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
        "load" => {
            let Some(path) = parts.get(1) else {
                println!("usage: load <path>");
                return Outcome::Err;
            };
            match s.load_snapshot_file(path) {
                Ok(()) => {
                    let st = s.stats();
                    println!(
                        "loaded {path}  atoms={} bubbles={} reaped={}",
                        st.total, st.bubbles, st.reaped
                    );
                }
                Err(e) => {
                    println!("load err: {e}");
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
                return Outcome::Err;
            };
            s.settle(n);
            println!("settle {n}");
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
  tick [n]                      one tick or settle n
  settle <n>                    n ticks
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
  save <path> / load <path>     KSUB_SNAP v1 (no Python)
  help | quit

batch: non-zero exit if a command fails (assert/save/bind/…)"
    );
}
