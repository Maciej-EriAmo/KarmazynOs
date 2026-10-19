"""Składa initramfs newc: jeden plik `init` (statyczny ELF shella)."""
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
    if len(sys.argv) != 3:
        print("usage: pack_initramfs.py <init-elf> <out.cpio>", file=sys.stderr)
        return 2
    elf = Path(sys.argv[1]).read_bytes()
    out = Path(sys.argv[2])
    out.parent.mkdir(parents=True, exist_ok=True)
    blob = _entry(1, "init", elf, 0o100755) + _entry(2, "TRAILER!!!", b"", 0)
    out.write_bytes(blob)
    print(f"initramfs {out} bytes={len(blob)} init={len(elf)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
