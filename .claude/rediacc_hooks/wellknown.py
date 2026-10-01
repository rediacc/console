"""The well-known values for hook code, read from `.ci/config/well-known.env` through the CI reader.

Use it as `from rediacc_hooks.wellknown import GH_REPO`; the names are `rediacc_ci.well_known`'s.

WHY THE READER IS LOADED BY FILE AND NOT BY IMPORT. The dispatcher runs every guard in one process, and a `.ci` entry on `sys.path` would put `rediacc_ci` on every later guard's import path (see `block_host_toolchain_run`, which scopes its own insert for that reason). The reader needs nothing but `pathlib` and `re`, so it is executed from its file under a private module name and `sys.path` is never touched.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from types import ModuleType

_READER = pathlib.Path(__file__).resolve().parents[2] / ".ci" / "rediacc_ci" / "well_known.py"
_NAME = "rediacc_hooks._well_known_reader"


def _load() -> ModuleType:
    cached = sys.modules.get(_NAME)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(_NAME, _READER)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load the well-known reader from %s" % _READER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[_NAME] = module
    spec.loader.exec_module(module)
    return module


def __getattr__(name: str) -> Any:
    if name.startswith("__"):
        raise AttributeError(name)
    return getattr(_load(), name)
