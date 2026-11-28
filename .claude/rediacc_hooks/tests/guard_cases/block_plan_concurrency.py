"""The test tables of `block_plan_concurrency`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

import datetime
import json
import pathlib

from rediacc_hooks import hookio

# ---- the differential's world: a tree with an exclusive plan E held by a peer's fresh lease ------
WORLD = hookio.golden_world("rediacc-guard-planconc-world")


_SID = "c0ffee11-1111-2222-3333-444444444444"


_PEER = "0dd0dd00"


_PLAN = "# PLAN: %s\n\nStatus: in-progress\nOwner: %s\nDepends-On: no-dep -- a fixture plan for the concurrency guard\nPriority: P2\nConcurrency: %s\nOwns: %s\n\n## Tasks\n\n- [ ] T1 a box\n"


def _conc_world(_unused):
    """WORLD/tree (a plan tree: E exclusive, F parallel with Owns inside E's) and WORLD/store (a peer's fresh lease on an E-linked item).

    F overlaps E because an exclusive plan is a mutex over ITS files (711841c55, operator ruling 2026-10-28): a disjoint F would be admitted, and the mutex refusal the DEFECT removes would never be reached."""
    tree = pathlib.Path(WORLD) / "tree"
    plans = tree / "agent" / "plans"
    plans.mkdir(parents=True, exist_ok=True)
    (tree / ".git").mkdir(exist_ok=True)
    hookio.write_world_file(
        plans / "PLAN-e.md",
        _PLAN % ("e", _PEER, "exclusive -- regenerates every golden file", "docs/e/**"),
    )
    hookio.write_world_file(
        plans / "PLAN-f.md", _PLAN % ("f", _SID[:8], "parallel", "docs/e/golden/**")
    )
    store = pathlib.Path(WORLD) / "store"
    store.mkdir(parents=True, exist_ok=True)
    (pathlib.Path(WORLD) / "tmp").mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now(datetime.UTC)
    at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    until = (now + datetime.timedelta(minutes=100)).strftime("%Y-%m-%dT%H:%MZ")
    rows = [
        {"ev": "add", "id": "e0e0e0e0", "at": at, "by": _PEER, "s": " ", "o": _PEER, "t": "(%s) regenerate goldens PLAN-e.md [e1e1e1e1]" % _PEER},
        {"ev": "lease", "id": "e0e0e0e0", "at": at, "by": _PEER, "until": until, "worker": "a9e9e9e9e9", "note": "", "worker_verified": True},
        {"ev": "add", "id": "f0f0f0f0", "at": at, "by": _SID[:8], "s": " ", "o": _SID[:8], "t": "(%s) edit docs PLAN-f.md [f1f1f1f1]" % _SID[:8]},
    ]  # fmt: skip
    hookio.write_world_file(
        store / ("%s.jsonl" % _PEER), "".join(json.dumps(r) + "\n" for r in rows)
    )
    return WORLD


FIXTURES = {"planconc-world": _conc_world}


# The variables are read by wl_core / wl_store, never by this guard.
ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    (
        "planconc",
        {
            "CLAUDE_PROJECT_DIR": "{FIXTURE:planconc-world}/tree",
            "WORKLIST_STORE_DIR": "{FIXTURE:planconc-world}/store",
            "TMPDIR": "{FIXTURE:planconc-world}/tmp",
        },
        {},
    )
]


def _spawn(kind, text, session=_SID):
    return {
        "tool_name": "Agent",
        "session_id": session,
        "cwd": "/nonexistent-plan-concurrency-fixture",
        "tool_input": {"subagent_type": kind, "description": "fixture", "prompt": text},
    }


EDGE_CASES = [
    ("writer-for-another-plan-under-a-live-mutex", _spawn("general-purpose", "work #f0f0f0f0")),
    ("writer-for-the-exclusive-plan-itself", _spawn("general-purpose", "Plan: PLAN-e.md")),
    ("reader-under-a-live-mutex", _spawn("Explore", "Plan: PLAN-f.md")),
    ("planless-writer-with-unknown-files", _spawn("general-purpose", "fix a typo")),
    (
        "planless-writer-with-disjoint-owns",
        _spawn("general-purpose", "fix a typo\nOwns: docs/zz/**"),
    ),
    (
        "the-holder-session-itself",
        _spawn("general-purpose", "Plan: PLAN-f.md", session=_PEER + "-aaaa"),
    ),
    ("not-a-spawn", {"tool_name": "Bash", "tool_input": {"command": "true"}}),
]
