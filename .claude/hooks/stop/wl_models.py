"""The Claude model ids the Stop hook's model calls use, read from `.ci/config/well-known.env`.

ONE SOURCE. `WK_CLAUDE_HAIKU_MODEL` in the well-known registry is the only place a model id is written: the Stop-hook judge (wl_judge.JUDGE_MODEL), the plan recommender that reuses it, and the per-commit reviewer (wl_review.load_config) all read it from here, so an upgrade is that one line. `check:ci-literal-sources` refuses the id typed out anywhere else.

Read once per process, on the first call to haiku_model(), like every well-known value: a long-lived process keeps the id it started with, and the next hook process picks up an edit.

THE READER IS FOUND, NOT ASSUMED. `.ci/rediacc_ci/well_known.py` is stdlib-only, so it is executed from its file under a private name, as rediacc_hooks/wellknown.py does. It is looked for above this file first, then above the live `.claude/rediacc_hooks` a last-known-good snapshot links in, then above the working directory: several suites copy this directory into a temp root (test_wl_lkg, test_wl_cadence, test_stop_hook_edit_check) while the process runs from the checkout, and a fixed parents[2] hop crashed every one of them on import (2026-10-08). The same search order as wl_store's appender. None found is a loud ImportError, never a silent default.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

_READER_REL = (".ci", "rediacc_ci", "well_known.py")
_NAME = "wl_models._well_known_reader"


def _reader_path() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    linked = pathlib.Path(__file__).absolute().parents[2] / "rediacc_hooks"
    cwd = pathlib.Path.cwd().resolve()
    starts = [*here.parents]
    if linked.exists():
        starts += [*linked.resolve().parents]
    starts += [cwd, *cwd.parents]
    for root in starts:
        candidate = root.joinpath(*_READER_REL)
        if candidate.is_file():
            return candidate
    raise ImportError(
        "wl_models: no %s above %s, the snapshot link, or %s" % ("/".join(_READER_REL), here, cwd)
    )


def _load():
    cached = sys.modules.get(_NAME)
    if cached is not None:
        return cached
    path = _reader_path()
    spec = importlib.util.spec_from_file_location(_NAME, path)
    if spec is None or spec.loader is None:
        raise ImportError("wl_models: cannot load the well-known reader from %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[_NAME] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        # A failed import must not leave a half-initialised module for the next caller to take from the cache.
        sys.modules.pop(_NAME, None)
        raise
    return module


def haiku_model() -> str:
    """The Haiku id, resolved on first CALL, not at import: the stop-hook edit check imports every module inside a temp root that holds no .ci tree, and an import-time read crashed it there."""
    return _load().CLAUDE_HAIKU_MODEL
