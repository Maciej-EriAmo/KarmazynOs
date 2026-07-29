#!/usr/bin/env python3
"""Wejście CLI z katalogu LUA (bez instalacji pakietu).

  python run_lua.py run examples/hello
  python run_lua.py check examples/hello
  python run_lua.py path util -p examples/hello
"""
from cli import main
import sys

if __name__ == "__main__":
    sys.exit(main())
