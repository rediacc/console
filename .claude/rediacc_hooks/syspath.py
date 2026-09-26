"""The ONE canonical way onto sys.path for code under `.claude`.

`.ci` code has `rediacc_ci.paths.on_sys_path`; `.claude` code cannot reach it, because importing it needs `.ci` on sys.path first, which is the hop being replaced. This module is the `.claude` side of the same rule, pinned by `.ci/rediacc_ci/tests/test_canonical_sys_path_hop.py`: every other file under `.claude` calls `on_sys_path` here instead of writing `sys.path.insert` by hand.

TWO WAYS IN. A guard, a pytest module or anything else already importing `rediacc_hooks` writes `from rediacc_hooks import syspath`. A script OUTSIDE the package (a Stop-hook suite, a context hook, a standalone test script) cannot import it by name before `.claude` is on the path, so it loads this file BY PATH with `importlib.util.spec_from_file_location`, the same way those scripts already load `rediacc_ci/runtmp.py`. That is why this module is stdlib-only and must stay so.

THE STRING IS INSERTED EXACTLY AS GIVEN, NOT RESOLVED. The scoped callers remove the entry in a `finally` by the same string they passed in; resolving it here would make that removal miss whenever the caller's path was not already canonical.
"""

import pathlib
import sys

#: `<repo>/.claude`, the directory that makes `import rediacc_hooks` work.
CLAUDE_DIR = pathlib.Path(__file__).resolve().parents[1]
#: `<repo>/.claude/hooks/stop`, where `worklist.py` and the `wl_*` modules live.
STOP_DIR = CLAUDE_DIR / "hooks" / "stop"


def on_sys_path(directory: pathlib.Path | str) -> bool:
    """Put `directory` at the FRONT of sys.path, once. True when this call inserted it.

    IDEMPOTENT, which a bare `sys.path.insert(0, d)` is not: run twice, it leaves two copies and a later removal takes out only one. The return value exists for scoped callers, which remove the entry again only when they were the ones that added it.
    """
    text = str(directory)
    if text in sys.path:
        return False
    sys.path.insert(0, text)
    return True


__all__ = ["CLAUDE_DIR", "STOP_DIR", "on_sys_path"]
