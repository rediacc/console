"""Put `.claude` on `sys.path` so a standalone guard harness in this directory can import `rediacc_hooks`.

Imported for its SIDE EFFECT, once per harness:

    import _hookpath
    from rediacc_hooks import hookio

The line carries no marker: `lint.pyflakes.allowed-unused-imports` in the root pyproject.toml names `_hookpath`, with its BLOCKER reason, so ruff does not report the import as unused.

A harness runs BY PATH (`python3 .claude/rediacc_hooks/guards/test-<guard>.py`), which puts only this directory on `sys.path[0]`; that is why `import _hookpath` resolves with no hop of its own and why `rediacc_hooks` does not until this has run. Doing the hop as a statement in the harness instead makes every import after it E402, and the same import-for-effect spelling is the one `.ci/scripts/quality/_cipath.py` settles on, with the measurements.

The insert itself is the canonical one, `rediacc_hooks/syspath.py`, loaded by path because the package it belongs to is not importable yet (test_canonical_sys_path_hop).
"""

import importlib.util
import pathlib

_SYSPATH_FILE = pathlib.Path(__file__).resolve().parents[1] / "syspath.py"
_SPEC = importlib.util.spec_from_file_location("rediacc_hooks_syspath", _SYSPATH_FILE)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(
        "_hookpath cannot load %s. This file has moved: it must stay in "
        ".claude/rediacc_hooks/guards/, beside the rediacc_hooks package it opens." % _SYSPATH_FILE
    )
_SYSPATH = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_SYSPATH)
_SYSPATH.on_sys_path(_SYSPATH.CLAUDE_DIR)
