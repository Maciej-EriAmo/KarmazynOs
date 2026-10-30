//! Test krzyżowy z DBase/karmazyn_kafd.py (uruchamia go cross/cross_check.py).
//!
//!   kafd_cross write <dir>   rust_v20.kafd rust_v21.kafd rust_flow.kafs
//!                            rust_journal.kafs rust_compact.kafd
//!                            rust_kafx.kafd (nonce 05×12) rust_enc_journal.kafs
//!                            rust_enc_compact.kafd (master z CYNOBER_MASTER_KEY)
//!                            rust_vfs.kafd (vfs_pack) rust_world.kafd (save_store)
//!   kafd_cross read <dir>    opis plików py_* jako JSON (stdout)
//!
//! Dane wejściowe i czas (1700000000, "2023-11-14 22:13") są te same co w skrypcie.

use karmazyn_kafd::cipher::wrap_kafx_with_nonce;
use karmazyn_kafd::{
    compact_journal, world, Atom, Crypt, FlowReader, FlowWriter, Journal, Layout, Reader, Writer,
    A_PHI_ATOM, A_RAW, A_THERMAL, MIME_THERMAL,
};
use karmazyn_substrate::Store;
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
    let mut j = Journal::open_with(&jp, false, &jm, &Crypt::plain())?;
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
    let rep = compact_journal(&cj, &dir.join("rust_compact_now.kafd"), Layout::Footer, true, Some(cm.clone()), &Crypt::plain())?;
    assert_eq!(rep.atoms, 2);
    let j2 = Journal::open_with(&jp, false, &Map::new(), &Crypt::plain())?;
    let mut w = Writer::new(Layout::Footer).with_meta(cm).with_created(UNIX, CREATED);
    for a in j2.atoms(0.0)? {
        w.add(a);
    }
    std::fs::write(dir.join("rust_compact.kafd"), w.build())?;

    // szyfrowanie: master z CYNOBER_MASTER_KEY (jak w Pythonie)
    let v21 = std::fs::read(dir.join("rust_v21.kafd"))?;
    std::fs::write(dir.join("rust_kafx.kafd"), wrap_kafx_with_nonce(&v21, "cross", None, &[5u8; 12])?)?;
    let enc = Crypt { world: Some("cross_enc".into()), encrypt: Some(true), master: None };
    let ep = dir.join("rust_enc_journal.kafs");
    let _ = std::fs::remove_file(&ep);
    let mut j = Journal::open_with(&ep, false, &jm, &enc)?;
    j.append_atom(&all[3])?;
    j.append_atom(&all[0])?;
    j.checkpoint(417, "seal", 40.0, 70.0, 0)?;
    j.close(false)?;
    let ec = dir.join("rust_enc_compact_src.kafs");
    std::fs::copy(&ep, &ec)?;
    let Value::Object(em) = json!({"source": "kafs-journal", "frames": 2}) else { unreachable!() };
    compact_journal(&ec, &dir.join("rust_enc_compact.kafd"), Layout::Footer, true, Some(em), &enc)?;

    // świat DBase: vfs_pack bajt w bajt + zapis natywnego Store
    std::fs::write(dir.join("rust_vfs.kafd"), vfs_docs_blob())?;
    let s = Store::new(true);
    let a = s.atom_new("var", "x", 80.0);
    let b = s.atom_new("plik", "kod", 50.0);
    s.atom_set_guest(b, 3, Some(b"return 1".to_vec()));
    let fs_root = s.bubble_new("fs", None);
    s.set_root(fs_root);
    let bin = s.bubble_new("bin", Some(fs_root));
    s.bind(bin, "hej", b).map_err(|e| karmazyn_kafd::Error(e.into()))?;
    s.bind(fs_root, "x", a).map_err(|e| karmazyn_kafd::Error(e.into()))?;
    let crypt = Crypt { world: None, encrypt: Some(true), master: None };
    world::save_store(&s, &dir.join("rust_world.kafd"), &crypt)?;
    Ok(())
}

fn png() -> Vec<u8> {
    let mut p = b"\x89PNG\r\n\x1a\n".to_vec();
    p.extend([0u8; 16]);
    p
}

/// Te same dokumenty co `vfs_docs()` w skrypcie Pythona.
fn vfs_docs_blob() -> Vec<u8> {
    let obj = |v: Value| match v {
        Value::Object(m) => m,
        _ => unreachable!(),
    };
    let docs = vec![
        ("a0".to_string(), world::encode_doc("document", "tekst", 60.0, Map::new(), b"")),
        (
            "a1".to_string(),
            world::encode_doc("media", "obraz.png", 42.5, obj(json!({"mime": "image/png"})), &png()),
        ),
        (
            "b1".to_string(),
            world::encode_doc(
                "__bubble__",
                "docs",
                50.0,
                obj(json!({"v": {"label": "docs", "bindings": {"tekst": "a0"}}})),
                b"",
            ),
        ),
        ("notatka.txt".to_string(), b"zwykly tekst".to_vec()),
    ];
    let meta = obj(json!({"format": world::STORE_META, "saved": 1_700_000_000.0, "count": 4}));
    world::vfs_pack(&docs, meta, karmazyn_kafd::F_PHI_NATIVE, Some((UNIX, CREATED)))
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
    for name in ["py_v20.kafd", "py_v21.kafd", "py_compact.kafd", "py_kafx.kafd", "py_enc_compact.kafd"] {
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

    let enc = Crypt { world: Some("cross_enc".into()), encrypt: Some(true), master: None };
    for (name, crypt) in [("py_journal.kafs", Crypt::plain()), ("py_enc_journal.kafs", enc)] {
        let j = Journal::open_with(dir.join(name), false, &Map::new(), &crypt)?;
        let ck = j.last_checkpoint.clone().unwrap();
        let ja: Vec<Value> = j.atoms(0.0)?.iter().map(describe).collect();
        out.insert(
            name.into(),
            json!({"frames": j.n_frames, "last_tick": j.last_tick,
                   "checkpoint": {"tick": ck.tick, "n_frames": ck.n_frames, "causality": ck.causality},
                   "atoms": ja}),
        );
    }

    // świat zapisany przez Python (save_documents, KAFX) → snapshot Store
    let w = world::World::read(&dir.join("py_world.kafd"), None, None)?;
    let snap = world::snapshot_from_world(&w);
    let se = |aid: u32| {
        let a = snap.atoms.iter().find(|a| a.id == aid).unwrap();
        format!("{}/{}", a.s, a.e)
    };
    let atoms: Vec<Value> = snap
        .atoms
        .iter()
        .map(|a| json!({"S": a.s, "E": a.e, "T": a.t,
                        "data": a.payload.clone().unwrap_or_default().iter().map(|b| format!("{b:02x}")).collect::<String>()}))
        .collect();
    let bubbles: Vec<Value> = snap
        .bubbles
        .iter()
        .map(|b| {
            let mut binds = Map::new();
            for x in snap.binds.iter().filter(|x| x.bid == b.id) {
                binds.insert(x.name.clone(), Value::from(se(x.aid)));
            }
            json!({"label": b.label, "root": snap.roots.contains(&b.id), "bindings": binds})
        })
        .collect();
    out.insert("py_world.kafd".into(), json!({"format": w.meta["format"], "atoms": atoms, "bubbles": bubbles}));
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
