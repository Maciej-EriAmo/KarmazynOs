"""Składa initramfs newc: `init` (statyczny ELF shella) i opcjonalne katalogi.

Katalog `--dir lua_bin=<ścieżka>` trafia płasko pod /lua_bin (bez podkatalogów).
"""
import sys
from pathlib import Path


def _field(n: int) -> bytes:
    return f"{n:08X}".encode("ascii")


def _entry(ino: int, name: str, data: bytes, mode: int) -> bytes:
    name_b = name.encode("ascii") + b"\0"
    header = b"070701" + b"".join(
        [
            _field(ino),
            _field(mode),
            _field(0),
            _field(0),
            _field(1),
            _field(0),
            _field(len(data)),
            _field(0),
            _field(0),
            _field(0),
            _field(0),
            _field(len(name_b)),
            _field(0),
        ]
    )
    blob = bytearray(header)
    blob += name_b
    while len(blob) % 4:
        blob.append(0)
    blob += data
    while len(blob) % 4:
        blob.append(0)
    return bytes(blob)


def main() -> int:
    args = sys.argv[1:]
    dirs = []
    while "--dir" in args:
        i = args.index("--dir")
        if i + 1 >= len(args) or "=" not in args[i + 1]:
            print("--dir wymaga name=path", file=sys.stderr)
            return 2
        name, path = args[i + 1].split("=", 1)
        dirs.append((name.strip("/"), Path(path)))
        del args[i:i + 2]
    if len(args) != 2:
        print("usage: pack_initramfs.py <init-elf> <out.cpio> [--dir name=path]...",
              file=sys.stderr)
        return 2
    elf = Path(args[0]).read_bytes()
    out = Path(args[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    blob = _entry(1, "init", elf, 0o100755)
    ino = 2
    files = 0
    for name, src in dirs:
        if not src.is_dir():
            print(f"brak katalogu: {src}", file=sys.stderr)
            return 1
        blob += _entry(ino, name, b"", 0o040755)
        ino += 1
        for f in sorted(src.iterdir()):
            if not f.is_file():
                continue
            blob += _entry(ino, f"{name}/{f.name}", f.read_bytes(), 0o100644)
            ino += 1
            files += 1
    blob += _entry(ino, "TRAILER!!!", b"", 0)
    out.write_bytes(blob)
    print(f"initramfs {out} bytes={len(blob)} init={len(elf)} files={files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
