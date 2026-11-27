#!/usr/bin/env python3
"""The cases of both halves of "the live-proof ledger is written only by the recorder" (agent/plans/PLAN-tested-on-bench.md box V10), their scratch world, and the runner they share.

The Edit cases are run by `test-block_guarded_path_edit.py` (the ledger row of block_guarded_path_edit, which merged the three path-judged edit halves under CR5), and the shell cases by `test-block_live_proof_ledger_shell_write.py`, each through dispatch.py in both directions, because a one-sided control is satisfiable by a broken hook: one that always refuses passes the refusal cases, one that never refuses passes the allowed ones. Each suite then plants its guard's
declared plant in-process and the run MUST fail, which is the proof the cases can.

THE WORLD is a scratch checkout under the system temp directory holding a real `agent/ledgers/live-proof.jsonl` with one recorder-shaped row, a symlink to it, and a directory link to `agent/ledgers`, so the on-disk readings (a glob, a link, a `cd`) are exercised against files that exist. Every payload runs with that directory as its `cwd`.

Not a suite itself: the leading underscore keeps it out of the guard glob and out of the per-guard `test-<stem>.py` credit.
"""

import atexit
import importlib
import importlib.util
import json
import pathlib
import shutil
import tempfile

import _hookpath

from rediacc_hooks.guards import _edit_suite
from rediacc_hooks.tests.fixtures.guards.loader import load_table

HERE = pathlib.Path(__file__).resolve()
_SYSPATH = importlib.util.spec_from_file_location(
    "rediacc_hooks_syspath", HERE.parent.parent / "syspath.py"
)
if _SYSPATH is None or _SYSPATH.loader is None:
    raise SystemExit("%s: rediacc_hooks/syspath.py is missing" % __file__)
_syspath = importlib.util.module_from_spec(_SYSPATH)
_SYSPATH.loader.exec_module(_syspath)

# The ledger path is the guard's own constant, read rather than retyped. That is also why this script can build its scratch world while untracked: the shell half reads an untracked script by path, and a string constant naming the ledger at a write target would be refused, which is the guard working; a value read from a module is not a constant it can see (a residue the guard's docstring names).
_syspath.on_sys_path(str(HERE.parents[2]))
L = importlib.import_module("rediacc_hooks.guards.block_guarded_path_edit").LEDGER_REL
NEEDLE = "live_proof record"
WORLD = pathlib.Path(tempfile.mkdtemp(prefix="test-live-proof-ledger-"))
atexit.register(shutil.rmtree, str(WORLD), True)
(WORLD / "agent" / "ledgers").mkdir(parents=True)
# A row of the recorder's shape (schema 1, id lp-<12 hex>), the thing a forger would copy and edit.
ROW = {
    "schema": 1,
    "id": "lp-0123456789ab",
    "tier": "live",
    "status": "VERIFIED",
    "plan": "agent/plans/PLAN-x.md",
    "box": "LP-bench",
    "target": "bench",
    "dirty": False,
    "check": {"id": "cli-bench", "rc": 0, "log_sha256": "0" * 64},
}
ROW_LINE = json.dumps(ROW, separators=(",", ":"))
(WORLD / L).write_text(ROW_LINE + "\n", encoding="utf-8")
(WORLD / "agent" / "ledgers" / "effort-outcomes.jsonl").write_text("", encoding="utf-8")
(WORLD / "lp").symlink_to(WORLD / L)
(WORLD / "ld").symlink_to(WORLD / "agent" / "ledgers", target_is_directory=True)
CWD = str(WORLD)


def _edit(tool, path, **extra):
    return {"tool_name": tool, "tool_input": {"file_path": path, **extra}, "cwd": CWD}


# The Edit cases stay code: each payload carries the scratch world's directory as its cwd, and one names the ledger by its absolute path there.
EDIT_CASES = [
    # (name, payload, refused?)
    ("Write a planted row over the ledger", _edit("Write", L, content=ROW_LINE + "\n"), True),
    (
        "Edit a FAILED row into VERIFIED",
        _edit("Edit", L, old_string='"status":"FAILED"', new_string='"status":"VERIFIED"'),
        True,
    ),
    ("Write the ledger by absolute path", _edit("Write", str(WORLD / L), content="x"), True),
    ("MultiEdit the ledger", _edit("MultiEdit", L, edits=[]), True),
    ("Write through a symlink to the ledger", _edit("Write", "lp", content="x"), True),
    ("Write through a directory link", _edit("Write", "ld/live-proof.jsonl", content="x"), True),
    ("Write via a dot-dot spelling", _edit("Write", "agent/x/../ledgers/live-proof.jsonl"), True),
    (
        "NotebookEdit naming the ledger",
        {"tool_name": "NotebookEdit", "tool_input": {"notebook_path": L}, "cwd": CWD},
        True,
    ),
    # Another .jsonl ledger is the agent store row's to refuse (block_guarded_path_edit reads both rows); a non-jsonl file beside the ledger is neither row's.
    (
        "Write the feedback snapshot beside it",
        _edit("Write", "agent/ledgers/feedback-snapshot.json"),
        False,
    ),
    ("Write a plan naming the ledger", _edit("Write", "agent/plans/PLAN-x.md", content=L), False),
    ("Write a sibling backup", _edit("Write", "agent/ledgers/live-proof.jsonl.bak"), False),
    ("Write the kept log", _edit("Write", ".ci/cache/live-proof/lp-0123456789ab.log"), False),
    ("no path", {"tool_name": "Write", "tool_input": {"content": "x"}, "cwd": CWD}, False),
]

# The shell cases are data (CR5): `(name, command, refused?)` rows in tests/fixtures/guards/block_live_proof_ledger_shell_write.json, read by that directory's one loader, and `suites()` hands each the world's cwd. They spell the ledger literally, so a guard whose LEDGER_REL moved would leave every refused row judging a path nothing protects: the suite stops there instead.
SHELL_CASES = load_table("block_live_proof_ledger_shell_write", "SHELL_CASES")
if not any(L in command for _name, command, refused in SHELL_CASES if refused):
    raise SystemExit("no refused shell case names the ledger %s; the fixture rows have drifted" % L)


# The runner is `_edit_suite`'s, shared by the four edit/shell twin suites (CR5); a refusal must name the recorder.
STYLE = _edit_suite.Style(says=NEEDLE, width=52, rc=True)
via_dispatch = _edit_suite.via_dispatch
_outside_defect = _edit_suite.outside_defect


def run_cases(stem, cases, runner, quiet=False):
    return _edit_suite.run_cases(stem, cases, runner, STYLE, quiet)


def suites():
    shell = [
        (n, {"tool_name": "Bash", "tool_input": {"command": c}, "cwd": CWD}, r)
        for n, c, r in SHELL_CASES
    ]
    return {"block_live_proof_ledger_shell_write": shell}


def main(stems=("block_live_proof_ledger_shell_write",)):
    return _edit_suite.finish(sum(_edit_suite.judge(stem, suites()[stem], STYLE) for stem in stems))
