"""Jądro i moduły z jednego linux-virt.apk, żeby vermagic się zgadzał.

usage: extract_virt_kernel.py <linux-virt.apk> <out-vmlinuz> <out-modules-dir> [moduł]...

Moduły wychodzą rozpakowane (`.ko`): jądro virt nie ma CONFIG_MODULE_DECOMPRESS.
Kolejność ładowania = kolejność alfabetyczna w katalogu, więc zależności muszą
mieć nazwy wcześniejsze (virtio_blk nie ma żadnych).
"""
import gzip
import sys
import tarfile
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    apk, vmlinuz, mods_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    wanted = sys.argv[4:] or ["virtio_blk"]
    tf = tarfile.open(apk, "r:gz")
    vmlinuz.parent.mkdir(parents=True, exist_ok=True)
    vmlinuz.write_bytes(tf.extractfile("boot/vmlinuz-virt").read())
    mods_dir.mkdir(parents=True, exist_ok=True)
    for old in mods_dir.glob("*.ko"):
        old.unlink()
    names = [n for n in tf.getnames() if n.startswith("lib/modules/") and n.endswith(".ko.gz")]
    for mod in wanted:
        hit = [n for n in names if n.rsplit("/", 1)[-1] == f"{mod}.ko.gz"]
        if len(hit) != 1:
            print(f"brak modułu {mod} w {apk}", file=sys.stderr)
            return 1
        data = gzip.decompress(tf.extractfile(hit[0]).read())
        (mods_dir / f"{mod}.ko").write_bytes(data)
        print(f"{mod}.ko {len(data)}")
    print(f"vmlinuz {vmlinuz.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
