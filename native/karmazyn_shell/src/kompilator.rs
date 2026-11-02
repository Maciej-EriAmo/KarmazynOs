//! Minister kcc w shellu: źródło K0 z bąbla kodu → C99 w atomie `c` tego
//! samego bąbla. Bez plików i bez procesów: `#include "lib.k0"` szuka bąbla
//! kodu o etykiecie `lib.k0`, wynik trwa w Store razem ze światem.
//!
//! Na płycie nie ma kompilatora C ani modelu uruchamiania natywnych programów,
//! więc łańcuch kończy się na C (`kcc <etykieta> --c` pokazuje źródło).

use karmazyn_lua::Evaluator as LuaEvaluator;
use karmazyn_substrate::{AtomId, BubbleId, Store, T_INIT};

/// Nazwa powiązania z wynikiem C w bąblu źródła.
pub const C_BIND: &str = "c";

#[derive(Debug)]
pub struct Wynik {
    pub c: String,
    pub atom: AtomId,
}

/// Najnowszy bąbel kodu z etykietą (z atomem `src`).
fn bubble(store: &Store, label: &str) -> Option<BubbleId> {
    store
        .bubble_ids()
        .into_iter()
        .filter(|b| {
            store.bubble_label(*b).as_deref() == Some(label)
                && store
                    .bubble_bindings(*b)
                    .is_some_and(|bs| bs.iter().any(|(n, _)| n == "src"))
        })
        .max()
}

pub fn compile(store: &Store, lua: &LuaEvaluator, label: &str, safe: bool) -> Result<Wynik, String> {
    let load = |name: &str| -> Result<String, String> {
        lua.code_read(store, name)
            .map(|b| String::from_utf8_lossy(&b).into_owned())
            .ok_or_else(|| format!("brak bąbla kodu {name}"))
    };
    let src = kcc::preprocess::load_with_loader(label, &load)?;
    let c = kcc::compile(&src, safe)?;
    let bid = bubble(store, label).ok_or_else(|| format!("brak bąbla kodu {label}"))?;
    let payload = Some(c.clone().into_bytes());
    let existing = store
        .bubble_bindings(bid)
        .unwrap_or_default()
        .into_iter()
        .find(|(n, _)| n == C_BIND)
        .map(|(_, a)| a)
        .filter(|a| store.has_atom(*a));
    let atom = match existing {
        Some(a) => {
            store.atom_set_guest(a, 0, payload);
            a
        }
        None => {
            let a = store.atom_new(label, "c", T_INIT);
            store.atom_set_guest(a, 0, payload);
            store.bind(bid, C_BIND, a).map_err(|e| e.to_string())?;
            a
        }
    };
    Ok(Wynik { c, atom })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn k0_from_bubbles_with_include_lands_in_c_atom() {
        let s = Store::new(true);
        let lua = LuaEvaluator::new(&s);
        lua.code_write(&s, "lib.k0", b"fn one() -> i32 { return 1; }\n").unwrap();
        lua.code_write(&s, "hello.k0", b"#include \"lib.k0\"\nfn main() -> i32 { return one() - 1; }\n")
            .unwrap();
        let w = compile(&s, &lua, "hello.k0", false).unwrap();
        assert!(w.c.contains("one") && w.c.contains("main"), "{}", w.c);
        assert_eq!(s.atom_payload(w.atom).as_deref(), Some(w.c.as_bytes()));
        // drugi raz: ten sam atom, nowa treść
        lua.code_write(&s, "hello.k0", b"fn main() -> i32 { return 7; }\n").unwrap();
        let again = compile(&s, &lua, "hello.k0", true).unwrap();
        assert_eq!(again.atom, w.atom);
        // błąd K0 i brak bąbla
        lua.code_write(&s, "zly.k0", b"fn main() -> i32 { return x; }\n").unwrap();
        assert!(compile(&s, &lua, "zly.k0", false).is_err());
        assert!(compile(&s, &lua, "brak.k0", false).unwrap_err().contains("brak bąbla kodu brak.k0"));
    }
}
