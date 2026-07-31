#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""karmazyn_studio — tryb Studio (SDL2/pygame × matryca T Stage 1).

  python software/karmazyn_studio.py
  python software/karmazyn_studio.py --python
  python karmazyn_boot.py --studio

Wymaga: pygame (SDL2). Headless smoke: SDL_VIDEODRIVER=dummy (ograniczone).
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "software"), os.path.join(ROOT, "kernel"),
          os.path.join(ROOT, "native")):
    if p not in sys.path:
        sys.path.insert(0, p)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="KarmazynOs Studio (SDL2)")
    ap.add_argument("--python", action="store_true", help="substrat python (referencja)")
    ap.add_argument("--native", "--rust", action="store_true", help="substrat native (default)")
    ap.add_argument("--width", type=int, default=960)
    ap.add_argument("--height", type=int, default=640)
    ap.add_argument("--check", action="store_true",
                    help="tylko sprawdź pygame + boot thermal, bez pętli okna")
    args = ap.parse_args(argv)

    if args.python:
        os.environ["KARMAZYN_SUBSTRATE"] = "python"
    elif args.native or os.environ.get("KARMAZYN_SUBSTRATE") is None:
        # prefer native when available
        os.environ.setdefault("KARMAZYN_SUBSTRATE", "native")

    from karmazyn_io_sdl import sdl_available, run_studio, KarmazynStudio, SdlIo

    if not sdl_available():
        print("FAIL: pygame/SDL2 niedostępne.  pip install pygame", file=sys.stderr)
        return 2

    if args.check:
        import karmazyn_boot as boot
        store, shell = boot.boot(verbose_events=False)
        if shell.thermal is None:
            print("FAIL: brak ThermalSurface (Stage 1)", file=sys.stderr)
            return 1
        # podmiana na SdlIo bez otwierania display
        sio = SdlIo()
        shell.thermal.io = sio
        shell.io = sio
        st = shell.thermal.stats()
        print("OK studio check")
        print(f"  sdl=pygame  thermal_stage={st.get('stage')}  io_ids={st.get('name_to_aid')}")
        print(f"  substrate store={type(store).__name__}")
        # smoke heat + project
        shell.thermal.heat_input()
        recs = shell.thermal.project_hot(limit=5, mark_visible=False)
        print(f"  project_hot sample={len(recs)}  T_console={shell.thermal.stats()['T_console']}")
        return 0

    return run_studio(width=args.width, height=args.height)


if __name__ == "__main__":
    raise SystemExit(main())
