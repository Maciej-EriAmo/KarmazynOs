"""Katalog → archiwum cpio newc (initramfs), ze symlinkami."""
import os
import stat
import sys
from pathlib import Path


def _field(n: int) -> bytes:
    return f"{n:08X}".encode("ascii")


def _pad(blob: bytearray) -> None:
    while len(blob) % 4:
        blob.append(0)


def _entry(ino: int, name: str, data: bytes, mode: int, rdev: int = 0) -> bytes:
    name_b = name.encode("utf-8") + b"\0"
    header = b"070701" + b"".join(
        [
            _field(ino & 0xFFFFFFFF),
            _field(mode & 0xFFFFFFFF),
            _field(0),
            _field(0),
            _field(1),
            _field(0),
            _field(len(data)),
            _field((rdev >> 8) & 0xFFFFFFFF),
            _field(rdev & 0xFF),
            _field(0),
            _field(0),
            _field(len(name_b)),
            _field(0),
        ]
    )
    blob = bytearray(header)
    blob += name_b
    _pad(blob)
    blob += data
    _pad(blob)
    return bytes(blob)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: pack_tree_cpio.py <root> <out.cpio>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1])
    out = Path(sys.argv[2])
    blob = bytearray()
    ino = 1
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        filenames.sort()
        rel = os.path.relpath(dirpath, root).replace("\\", "/")
        if rel != ".":
            blob += _entry(ino, rel, b"", 0o040755)
            ino += 1
        for name in filenames:
            path = Path(dirpath) / name
            rel_name = name if rel == "." else f"{rel}/{name}"
            st = path.lstat()
            mode = st.st_mode
            if stat.S_ISLNK(mode):
                data = os.readlink(path).encode("utf-8")
                blob += _entry(ino, rel_name, data, 0o120777)
            elif stat.S_ISREG(mode):
                data = path.read_bytes()
                base = name
                filemode = 0o100000 | (mode & 0o777)
                if (
                    base in {"init", "busybox", "hsl-check", "karmazyn_shell", "init-hsl"}
                    or base.endswith(".sh")
                ):
                    filemode = 0o100755
                    if not data.startswith(b"\x7fELF"):
                        data = data.replace(b"\r\n", b"\n")
                blob += _entry(ino, rel_name, data, filemode)
            elif stat.S_ISDIR(mode):
                continue
            else:
                continue
            ino += 1
    blob += _entry(ino, "TRAILER!!!", b"", 0)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)
    print(f"cpio {out} bytes={len(blob)} entries={ino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
