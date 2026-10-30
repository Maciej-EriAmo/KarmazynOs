//! Test krzyżowy z DBase/karmazyn_kafd.py (uruchamia go cross/cross_check.py).
//!
//!   kafd_cross write <dir>   rust_v20.kafd rust_v21.kafd rust_flow.kafs
//!                            rust_journal.kafs rust_compact.kafd
//!   kafd_cross read <dir>    opis plików py_* jako JSON (stdout)
//!
//! Dane wejściowe i czas (1700000000, "2023-11-14 22:13") są te same co w skrypcie.

use karmazyn_kafd::{
    compact_journal, Atom, FlowReader, FlowWriter, Journal, Layout, Reader, Writer, A_PHI_ATOM,
    A_RAW, A_THERMAL, MIME_THERMAL,
};
use serde_json::{json, Map, Value};
use std::path::Path;

const UNIX: u64 = 1_700_000_000;
const CREATED: &str = "2023-11-14 22:13";

fn thermal() -> Vec<u8> {
    let mut d = vec![2u8, 0];
    d.extend(UNIX.to_le_bytes());
    d.extend(417u64.to_le_bytes());
    d.extend(0u32.to_le_bytes());
    d.extend(40f32.to_le_bytes());
    d.extend(70f32.to_le_bytes());
    d.extend_from_slice(b"rest-of-frame");
    d
}

fn atoms() -> Vec<Atom> {
    let mut png = b"\x89PNG\r\n\x1a\n".to_vec();
    png.extend([0u8; 100]);
    vec![
        Atom::new("doc.readme", b"Dokumentacja KarmazynOS\n".to_vec(), "text/plain", 45.0, 100.0, A_RAW),
        Atom::new("img.logo", png, "image/png", 72.0, 100.0, A_RAW),
        Atom::new(
            "shell.init",
            br#"{"id": "shell.init", "S": "sys"}"#.to_vec(),
            "application/x-phi-atom",
            85.0,
            100.0,
            A_PHI_ATOM,
        ),
        Atom::new("tick.417", thermal(), MIME_THERMAL, 55.5, 100.0, A_THERMAL),
        Atom::new("ąę.utf", b"x".to_vec(), "text/plain", 12.25, 100.0, A_RAW),
    ]
}

fn meta() -> Map<String, Value> {
    let Value::Object(m) = json!({"label": "cross", "opis": "żółw"}) else { unreachable!() };
    m
}

fn write(dir: &Path) -> karmazyn_kafd::Result<()> {
    for (name, layout) in [("rust_v20.kafd", Layout::TableFirst), ("rust_v21.kafd", Layout::Footer)] {
        let mut w = Writer::new(layout).with_meta(meta()).with_created(UNIX, CREATED);
        for a in atoms() {
            w.add(a);
        }
        std::fs::write(dir.join(name), w.build())?;
    }
    let mut f = FlowWriter::new(meta());
    for a in atoms() {
        f.add(a);
    }
    std::fs::write(dir.join("rust_flow.kafs"), f.build())?;

    let jp = dir.join("rust_journal.kafs");
    let _ = std::fs::remove_file(&jp);
    let Value::Object(jm) = json!({"world": "cross"}) else { unreachable!() };
    let mut j = Journal::open(&jp, false, &jm)?;
    let all = atoms();
    j.append_atom(&all[3])?;
    j.append_atom(&all[0])?;
    j.checkpoint(417, "seal", 40.0, 70.0, 0)?;
    j.close(false)?;

    // compact na kopii dziennika (oryginał zostaje do porównania)
    let cj = dir.join("rust_compact_src.kafs");
    std::fs::copy(&jp, &cj)?;
    let Value::Object(cm) = json!({"source": "kafs-journal", "frames": 2}) else { unreachable!() };
    // Writer w compact bierze czas „teraz”; do porównania bajtów piszemy ręcznie tak samo
    let rep = compact_journal(&cj, &dir.join("rust_compact_now.kafd"), Layout::Footer, true, Some(cm.clone()))?;
    assert_eq!(rep.atoms, 2);
    let j2 = Journal::open(&jp, false, &Map::new())?;
    let mut w = Writer::new(Layout::Footer).with_meta(cm).with_created(UNIX, CREATED);
    for a in j2.atoms(0.0)? {
        w.add(a);
    }
    std::fs::write(dir.join("rust_compact.kafd"), w.build())?;
    Ok(())
}

fn describe(a: &Atom) -> Value {
    json!({
        "id": a.id, "mime": a.mime, "T": a.t, "T_max": a.t_max,
        "state": a.state, "atype": a.atype,
        "data": a.data.iter().map(|b| format!("{b:02x}")).collect::<String>(),
    })
}

fn read(dir: &Path) -> karmazyn_kafd::Result<Value> {
    let mut out = Map::new();
    for name in ["py_v20.kafd", "py_v21.kafd", "py_compact.kafd"] {
        let r = Reader::from_path(dir.join(name))?;
        let mut ids: Vec<&str> = r.atom_ids();
        ids.sort();
        let atoms: Vec<Value> = ids
            .iter()
            .map(|id| describe(&r.get_atom(id).unwrap().unwrap()))
            .collect();
        let ticks: Vec<Value> = r
            .tick_index()
            .iter()
            .map(|t| json!({"tick": t.tick, "T_min": t.t_min, "T_max": t.t_max, "kind": t.kind}))
            .collect();
        out.insert(
            name.into(),
            json!({"version": r.version(), "flags": r.flags(), "meta": r.meta(), "atoms": atoms, "ticks": ticks}),
        );
    }
    let blob = std::fs::read(dir.join("py_flow.kafs"))?;
    let mut fr = FlowReader::new(&blob[..], true);
    fr.read_header()?;
    let flow: Vec<Value> = fr.atoms(0.0)?.iter().map(describe).collect();
    out.insert("py_flow.kafs".into(), json!({"meta": fr.meta(), "atoms": flow}));

    let j = Journal::open(dir.join("py_journal.kafs"), false, &Map::new())?;
    let ck = j.last_checkpoint.clone().unwrap();
    let ja: Vec<Value> = j.atoms(0.0)?.iter().map(describe).collect();
    out.insert(
        "py_journal.kafs".into(),
        json!({"frames": j.n_frames, "last_tick": j.last_tick,
               "checkpoint": {"tick": ck.tick, "n_frames": ck.n_frames, "causality": ck.causality},
               "atoms": ja}),
    );
    Ok(Value::Object(out))
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let (Some(mode), Some(dir)) = (args.get(1), args.get(2)) else {
        eprintln!("usage: kafd_cross write|read <dir>");
        std::process::exit(2);
    };
    let dir = Path::new(dir);
    let res = match mode.as_str() {
        "write" => write(dir).map(|_| Value::from("ok")),
        "read" => read(dir),
        _ => {
            eprintln!("usage: kafd_cross write|read <dir>");
            std::process::exit(2);
        }
    };
    match res {
        Ok(v) => println!("{}", serde_json::to_string(&v).unwrap()),
        Err(e) => {
            eprintln!("kafd_cross: {e}");
            std::process::exit(1);
        }
    }
}
