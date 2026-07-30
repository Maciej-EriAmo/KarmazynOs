"""karmazyn_lua — interpreter Lua 5.5 (podzbiór) na substracie KarmazynOS.

Wersja: 0.9.0 — gość + host projektu + karmazyn.* + macierz lua_bin (26/28).
"""

__version__ = "0.9.0"
__version_info__ = (0, 9, 0)

from .lib import mount, LuaLib, install_env_of, resolve_caps, install_tools
from .values import lua_env_of, compose_phi
from .project import (
    ProjectSpec, install_project_searcher, install_memory_searcher,
    put_memory_module, clear_memory_module, attach_lua_bin,
)
from .session import (
    mount_session, open_project, run_entry, check_project,
    reload_module, check_buffer, set_project, GuestSession,
)
from .editor_bridge import EditorBridge

__all__ = [
    "__version__",
    "mount", "LuaLib", "install_env_of", "resolve_caps", "install_tools",
    "lua_env_of", "compose_phi",
    "ProjectSpec", "install_project_searcher", "install_memory_searcher",
    "put_memory_module", "clear_memory_module", "attach_lua_bin",
    "mount_session", "open_project", "run_entry", "check_project",
    "reload_module", "check_buffer", "set_project", "GuestSession",
    "EditorBridge",
]
