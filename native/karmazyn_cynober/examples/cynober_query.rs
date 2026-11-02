//! `cynober_query <host> <port> <zapytanie> [zapytanie...]` — każde zapytanie
//! na tym samym tunelu. Wypisuje JSON: `{"session": {...}, "answers": [...]}`.
//!
//! Media przez KAFS: `@put:<id>:<tekst>` wysyła tekst jako medium,
//! `@putbig:<id>:<bajty>` wysyła tyle bajtów wzoru `i % 251` (kilka ramek),
//! `@get:<id>` pobiera i oddaje `{"media": {"size", "mime", "sha256", "text"}}`.

use karmazyn_cynober::Client;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::time::Duration;

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}

fn run(c: &mut Client, q: &str) -> Result<Value, String> {
    if let Some(rest) = q.strip_prefix("@put:") {
        let (id, text) = rest.split_once(':').unwrap_or((rest, ""));
        return c.put_media(id, text.as_bytes(), "text/plain", None).map_err(|e| e.0);
    }
    if let Some(rest) = q.strip_prefix("@putbig:") {
        let (id, n) = rest.split_once(':').unwrap_or((rest, "0"));
        let data: Vec<u8> = (0..n.parse::<usize>().unwrap_or(0)).map(|i| (i % 251) as u8).collect();
        return c.put_media(id, &data, "application/octet-stream", None).map_err(|e| e.0);
    }
    if let Some(id) = q.strip_prefix("@get:") {
        let (data, mime, _) = c.get_media(id).map_err(|e| e.0)?;
        let text = if data.len() <= 4096 { String::from_utf8(data.clone()).ok() } else { None };
        return Ok(json!({"media": {
            "size": data.len(), "mime": mime,
            "sha256": hex(&Sha256::digest(&data)), "text": text,
        }}));
    }
    c.query(q).map_err(|e| e.0)
}

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
        "remote_version": i.remote_version, "kafs": c.kafs_enabled(),
    });
    let mut answers = Vec::new();
    for q in &args[2..] {
        answers.push(match run(&mut c, q) {
            Ok(v) => v,
            Err(e) => json!({"client_error": e}),
        });
    }
    println!("{}", json!({"session": session, "answers": answers}));
}
