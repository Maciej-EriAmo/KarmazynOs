"""karmazyn_lua.editor_bridge — cienki most edytora → GuestSession.

Edytor / IDE z CLI nie omija sesji: ten sam check/run/reload co host.
Gość pozostaje w bąblu (bez ambient FS). Host podaje treść bufora lub path.

put_buffer(name, text):
  - check_buffer (parse)
  - put_memory_module → require "name" widzi treść (searcher memory)

Przykład:
  from editor_bridge import EditorBridge
  br = EditorBridge(project="examples/hello")
  br.put_buffer("draft", "return {v=1}")
  print(br.eval("return require('draft').v"))
"""

from __future__ import annotations

import os

from .session import GuestSession, check_buffer as _check_buffer
from .project import put_memory_module, clear_memory_module


class EditorBridge:
    """Most hosta: bufory edytora + projekt na jednym GuestSession."""

    def __init__(self, project=None, store=None, tools=None, caps=None,
                 lua_bin=None, strict=None, **kwargs):
        self.session = GuestSession(
            store=store,
            project=project,
            tools=tools,
            caps=caps,
            lua_bin=lua_bin,
            strict=strict,
            **kwargs,
        )
        # name -> source (overlay; zsynchronizowane z memory searcher)
        self._buffers = {}

    @property
    def project(self):
        return self.session.project

    def set_project(self, root):
        return self.session.set_project(root)

    def put_buffer(self, name, text, as_module=True):
        """Zapamiętaj bufor edytora.

        as_module=True → require(name) ładuje ten tekst (memory searcher).
        name: 'util' lub 'lib.panel' (bez .lua).
        """
        mod = name
        if mod.endswith(".lua"):
            mod = mod[:-4].replace("\\", "/").replace("/", ".")
        self._buffers[name] = text
        if as_module:
            put_memory_module(self.session.ev, mod, text)
        return mod

    def clear_buffer(self, name=None):
        if name is None:
            self._buffers.clear()
            clear_memory_module(self.session.ev, None)
            return
        self._buffers.pop(name, None)
        mod = name[:-4] if name.endswith(".lua") else name
        mod = mod.replace("\\", "/").replace("/", ".")
        clear_memory_module(self.session.ev, mod)

    def check_buffer(self, name, text=None):
        """Parse bufora; text=None → z put_buffer / dysku projektu."""
        if text is None:
            text = self._buffers.get(name)
        if text is None and self.project is not None:
            path = name
            if not os.path.isabs(path):
                path = os.path.join(self.project.root, name)
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    text = f.read()
        if text is None:
            return f"@{name}: brak treści bufora"
        err = _check_buffer(name, text, chunkname="@" + name.replace("\\", "/"))
        return err  # None = OK

    def check_all(self):
        """Diagnostyki projektu (pliki na dysku) + bufory w pamięci."""
        diags = list(self.session.diagnostics())
        for name, text in sorted(self._buffers.items()):
            err = _check_buffer(name, text)
            if err:
                diags.append(err)
        return diags

    def run(self, entry=None, strict_project=None):
        """Jak CLI run / boot :run — ten sam bąbel sesji."""
        return self.session.run(entry=entry, strict_project=strict_project)

    def reload(self, name=None):
        return self.session.reload(name)

    def eval(self, line):
        return self.session.eval(line)
