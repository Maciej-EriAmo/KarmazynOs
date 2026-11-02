"""Font konsoli VGA z kbd-misc.apk (Alpine): rozpakowany PSF2 z tabelą Unicode.

usage: extract_console_font.py <kbd-misc.apk> <out-dir> [font]

Domyślnie `Lat2-Terminus16` (8x16, 256 glifów, Terminus Font, GPL-2.0+):
ma ąćęłńóśźż, ĄĆĘŁŃÓŚŹŻ i długą kreskę z linii startowych. Shell (PID 1)
wczytuje go na /dev/tty1 przy starcie.
"""
import gzip
import io
import sys
import tarfile
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    apk, out = Path(sys.argv[1]), Path(sys.argv[2])
    name = sys.argv[3] if len(sys.argv) > 3 else "Lat2-Terminus16"
    # apk to sklejone człony gzip (podpis, kontrola, dane); dane zawierają fonty
    tf = tarfile.open(fileobj=io.BytesIO(gzip.decompress(apk.read_bytes())))
    member = f"usr/share/consolefonts/{name}.psfu.gz"
    try:
        raw = gzip.decompress(tf.extractfile(member).read())
    except KeyError:
        print(f"brak {member} w {apk}", file=sys.stderr)
        return 1
    if raw[:4] != b"\x72\xb5\x4a\x86":
        print(f"{member}: to nie PSF2", file=sys.stderr)
        return 1
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.psfu"):
        old.unlink()
    path = out / f"{name}.psfu"
    path.write_bytes(raw)
    print(f"font {path.name} {len(raw)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
