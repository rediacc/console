"""The test tables of `warn_writer_brief`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

import importlib
import pathlib

from rediacc_hooks import hookio, syspath
from rediacc_hooks.guards.warn_writer_brief import STOP_DIR
from rediacc_hooks.tests.fixtures.guards.loader import load_table

# ---- the differential's world: a tree whose review store holds three fixed doc findings on a/x.py ------
WORLD = hookio.golden_world("rediacc-guard-writerbrief-world")


_SID = "c0ffee11-1111-2222-3333-444444444444"


def _brief_world(_unused):
    """WORLD/tree: a project root (a `.git` directory) whose agent/reviews holds three fixed medium doc-contradicts-code findings on a/x.py, rendered by `wl_review` itself. `a/**` matches no file of the real checkout, so the gen-docs half is never asked and the cases answer the same wherever they run."""
    tree = pathlib.Path(WORLD) / "tree"
    (tree / ".git").mkdir(parents=True, exist_ok=True)
    syspath.on_sys_path(STOP_DIR)
    review_mod = importlib.import_module("wl_review")
    at = "2026-11-10T00:00:00Z"
    for n in range(3):
        sha = ("%08x" % (n + 1)) + "0" * 32
        finding = review_mod.Finding(
            "%s.1" % sha[:8],
            "medium",
            "a/x.py",
            1,
            "in-diff",
            "The docstring says the guard refuses, but it returns ALLOW on that path.",
            "fixed %s | abcdef01 %s" % ("f" * 40, at),
        )
        review = review_mod.Review(
            sha=sha,
            subject="s",
            branch="1110-1",
            reviewed_at=at,
            model="m",
            verdict="findings",
            findings=[finding],
        )
        target = review_mod.review_path(tree, "1110-1", sha)
        target.parent.mkdir(parents=True, exist_ok=True)
        hookio.write_world_file(target, review_mod.render(review))
    return WORLD


FIXTURES = {"writerbrief-world": _brief_world}


# CLAUDE_PROJECT_DIR is read by wl_core's root resolution, never by this guard.
ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    ("writerbrief", {"CLAUDE_PROJECT_DIR": "{FIXTURE:writerbrief-world}/tree"}, {})
]


def _spawn(kind, text):
    return {
        "tool_name": "Agent",
        "session_id": _SID,
        "cwd": "/nonexistent-writer-brief-fixture",
        "tool_input": {"subagent_type": kind, "description": "fixture", "prompt": text},
    }


EDGE_CASES = load_table("warn_writer_brief", "EDGE_CASES")
