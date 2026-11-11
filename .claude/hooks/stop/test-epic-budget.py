#!/usr/bin/env python3
"""wl_epic.render keeps the PR epic block under GitHub's PR body limit (65,536 characters).

2026-11-11: branch 1104-1 carried 313 open backlog items and the published block was 66,965 bytes, so no PR body could hold the block check:ci-pr-epic-block demands. The backlog now stops at BLOCK_BUDGET and names how many it left out. A small backlog renders whole (the control).

Runs as `python3 .claude/hooks/stop/test-epic-budget.py`; exit 0 when every check holds.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

HERE = pathlib.Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location("wl_epic", HERE / "wl_epic.py")
if _SPEC is None or _SPEC.loader is None:
    raise SystemExit("cannot load wl_epic.py")
E = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(E)

FAILS: list[str] = []


def check(name: str, ok: bool) -> None:
    print(("PASS  " if ok else "FAIL  ") + name)
    if not ok:
        FAILS.append(name)


def item(n: int) -> dict:
    return {
        "id": "%08x" % n,
        "state": " ",
        "text": "an open backlog item number %d with enough words to look like a real line of the worklist"
        % n,
    }


def render_with(n_items: int) -> str:
    recs = [item(i) for i in range(n_items)]
    fold = types.SimpleNamespace(items=recs)
    E.load_epics = dict
    E.backlog_items = lambda *_a, **_k: list(recs)
    return E.render(fold, [])


big = render_with(2000)
check(
    "a 2000-item backlog renders under BLOCK_BUDGET plus one marker line",
    len(big) <= E.BLOCK_BUDGET + 200,
)
check("and stays under GitHub's 65,536-character body limit", len(big) < 65536)
check("and names how many items it left out", "more open item(s) not listed here" in big)
small = render_with(5)
check("CONTROL: a 5-item backlog lists all five", all(("#%08x" % i) in small for i in range(5)))
check("CONTROL: and prints no left-out line", "more open item(s) not listed here" not in small)

sys.exit(1 if FAILS else 0)
