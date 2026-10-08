"""The Claude model ids the Stop hook's model calls use, read from `.ci/config/well-known.env`.

ONE SOURCE. `WK_CLAUDE_HAIKU_MODEL` in the well-known registry is the only place a model id is written: the Stop-hook judge (wl_judge.JUDGE_MODEL), the plan recommender that reuses it, and the per-commit reviewer (wl_review.load_config) all read it from here, so an upgrade is that one line. `check:ci-literal-sources` refuses the id typed out anywhere else.

Read once per process at import, like every well-known value: a long-lived process keeps the id it started with, and the next hook process picks up an edit.

Reached through the canonical `.claude` hop (`.claude/rediacc_hooks/syspath.py`), loaded by path because the stop directory is not inside the `rediacc_hooks` package.
"""

from __future__ import annotations

import importlib.util
import pathlib

_SYSPATH = pathlib.Path(__file__).resolve().parents[2] / "rediacc_hooks" / "syspath.py"
_spec = importlib.util.spec_from_file_location("_rediacc_syspath", _SYSPATH)
if _spec is None or _spec.loader is None:
    raise ImportError("cannot load %s" % _SYSPATH)
_syspath = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_syspath)
_syspath.on_sys_path(_syspath.CLAUDE_DIR)

from rediacc_hooks.wellknown import CLAUDE_HAIKU_MODEL  # noqa: E402

HAIKU_MODEL: str = CLAUDE_HAIKU_MODEL
