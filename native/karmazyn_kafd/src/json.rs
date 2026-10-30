//! META JSON tak jak `json.dumps(obj, ensure_ascii=False)` w Pythonie:
//! separatory `", "` i `": "`, kolejność kluczy jak przy wstawianiu,
//! znaki spoza ASCII bez ucieczek.

use serde_json::ser::{CompactFormatter, Formatter};
use serde_json::{Map, Value};
use std::io::{self, Write};

struct PyFormatter;

impl Formatter for PyFormatter {
    fn begin_array_value<W: ?Sized + Write>(&mut self, w: &mut W, first: bool) -> io::Result<()> {
        if first {
            Ok(())
        } else {
            w.write_all(b", ")
        }
    }

    fn begin_object_key<W: ?Sized + Write>(&mut self, w: &mut W, first: bool) -> io::Result<()> {
        if first {
            Ok(())
        } else {
            w.write_all(b", ")
        }
    }

    fn begin_object_value<W: ?Sized + Write>(&mut self, w: &mut W) -> io::Result<()> {
        w.write_all(b": ")
    }

    // reszta (liczby, napisy, ucieczki) jak w trybie zwartym
    fn write_f64<W: ?Sized + Write>(&mut self, w: &mut W, value: f64) -> io::Result<()> {
        CompactFormatter.write_f64(w, value)
    }
}

pub(crate) fn dumps(obj: &Map<String, Value>) -> Vec<u8> {
    let mut out = Vec::new();
    let mut ser = serde_json::Serializer::with_formatter(&mut out, PyFormatter);
    serde::Serialize::serialize(obj, &mut ser).expect("JSON do pamięci");
    out
}

pub(crate) fn loads(bytes: &[u8]) -> Option<Map<String, Value>> {
    match serde_json::from_slice::<Value>(bytes) {
        Ok(Value::Object(m)) => Some(m),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn matches_python_dumps() {
        // json.dumps({"label": "żółw", "n": [1, 2], "o": {"a": True}, "s": "a\"\n\x1f"},
        //            ensure_ascii=False)
        let v = json!({"label": "żółw", "n": [1, 2], "o": {"a": true}, "s": "a\"\n\u{1f}"});
        let Value::Object(m) = v else { unreachable!() };
        assert_eq!(
            String::from_utf8(dumps(&m)).unwrap(),
            r#"{"label": "żółw", "n": [1, 2], "o": {"a": true}, "s": "a\"\n\u001f"}"#
        );
        assert_eq!(dumps(&Map::new()), b"{}");
    }
}
