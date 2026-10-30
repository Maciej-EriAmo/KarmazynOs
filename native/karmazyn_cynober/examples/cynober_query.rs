//! `cynober_query <host> <port> <zapytanie> [zapytanie...]` — każde zapytanie
//! na tym samym tunelu. Wypisuje JSON: `{"session": {...}, "answers": [...]}`.

use karmazyn_cynober::Client;
use serde_json::{json, Value};
use std::time::Duration;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.len() < 3 {
        eprintln!("usage: cynober_query <host> <port> <zapytanie>...");
        std::process::exit(2);
    }
    let port: u16 = args[1].parse().unwrap_or(karmazyn_cynober::DEFAULT_PORT);
    let mut c = match Client::connect(&args[0], port, Duration::from_secs(30)) {
        Ok(c) => c,
        Err(e) => {
            println!("{}", json!({"error": e.0}));
            std::process::exit(1);
        }
    };
    let i = &c.info;
    let session = json!({
        "crypto_mode": i.crypto_mode, "hss_profile": i.hss_profile, "psk": i.psk,
        "hsl": i.hsl, "qkd_hybrid": i.qkd_hybrid, "epoch": i.epoch,
        "node_local": i.node_local, "node_remote": i.node_remote,
        "remote_version": i.remote_version,
    });
    let mut answers = Vec::new();
    for q in &args[2..] {
        answers.push(match c.query(q) {
            Ok(v) => v,
            Err(e) => json!({"client_error": e.0}),
        });
    }
    println!("{}", Value::from(json!({"session": session, "answers": answers})));
}
