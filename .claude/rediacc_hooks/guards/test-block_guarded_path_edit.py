#!/usr/bin/env python3
"""Control harness for block_guarded_path_edit, the one pre-edit guard over the four path-judged rows of `_write_rules.ROWS` (PLAN-tooling-code-reduction CR5).

Each row keeps the cases its own guard was judged by before the merge: the review record cases of `_review_file_suite.py` (once block_review_file_edit's), the ledger cases of `_live_proof_ledger_suite.py` (once block_live_proof_ledger_write's), the round log cases below (once block_roundlog_write's, which its golden still judges as well), and the agent store cases below (review finding 896a95d5.3; its shell half is test-block_agent_store_shell_write.py). Every case runs through dispatch.py in both directions, with a floor of four cases each way per row,
because a one-sided control is satisfiable by a broken hook.

Then each row's plant is put in an in-process copy of the guard and must turn at least one case OF ITS OWN ROW: the DEFECT for the round log, `MUTANTS["review_file"]`, `MUTANTS["live_proof_ledger"]` and `MUTANTS["agent_store"]` for the other three. A plant that only turned another row's cases would be proof of nothing about its own.

    test-block_guarded_path_edit.py        every row's cases through dispatch.py, then each row's plant
"""

import atexit
import importlib.util
import pathlib
import shutil
import sys
import tempfile

import _hookpath

from rediacc_hooks.guards import _edit_suite
from rediacc_hooks.tests.guard_cases import block_guarded_path_edit as T

STEM = "block_guarded_path_edit"
HERE = pathlib.Path(__file__).resolve()


def _load(name):
    spec = importlib.util.spec_from_file_location(name.lstrip("_"), HERE.with_name(name + ".py"))
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load %s.py beside %s" % (name, HERE.name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The round log row reads the disk: an existing log is refused, a missing one is created. The world is the golden's own fixed directory, built here as the differential builds it.
T._round_log_world(None)


def _write(path, tool="Write"):
    key = "notebook_path" if tool == "NotebookEdit" else "file_path"
    return {"tool_name": tool, "tool_input": {key: path, "content": "x"}}


ROUNDLOG_CASES = [
    ("Write over an existing round log", _write(T.EXISTING_LOG), True),
    ("NotebookEdit over an existing round log", _write(T.EXISTING_LOG, "NotebookEdit"), True),
    ("Write through a link into reports/", _write(T.WORLD + "/linked/pr-babysit-0831-1.md"), True),
    (
        "Write via a .. detour onto the log",
        _write(T.WORLD + "/reports/x/../pr-babysit-0831-1.md"),
        True,
    ),
    ("Edit of an existing round log", _write(T.EXISTING_LOG, "Edit"), False),
    ("MultiEdit of an existing round log", _write(T.EXISTING_LOG, "MultiEdit"), False),
    ("creating a round log that does not exist", _write(T.MISSING_LOG), False),
    ("a briefing is not a round log", _write(T.EXISTING_BRIEFING), False),
    ("an ordinary file in reports/", _write("reports/notes.md"), False),
]

# The agent store row (review finding 896a95d5.3): a scratch checkout with real stores, so a link and a `..` detour land on files that exist. Each payload carries the world as its cwd.
STORE_WORLD = pathlib.Path(tempfile.mkdtemp(prefix="test-agent-store-edit-"))
atexit.register(shutil.rmtree, str(STORE_WORLD), True)
for _rel in (
    "agent/reggate/main.jsonl",
    "agent/worklist/d778be9d.jsonl",
    "agent/worklist/README.md",
    "agent/ledgers/effort-outcomes.jsonl",
):
    (STORE_WORLD / _rel).parent.mkdir(parents=True, exist_ok=True)
    (STORE_WORLD / _rel).write_text("{}\n", encoding="utf-8")
(STORE_WORLD / "rg").symlink_to(STORE_WORLD / "agent" / "reggate", target_is_directory=True)


def _store(tool, path, **extra):
    return {"tool_name": tool, "tool_input": {"file_path": path, **extra}, "cwd": str(STORE_WORLD)}


_RETIRE = '{"kind":"retire","sig":"0123abcd","asked":"ASKED:2026-11-27T10:00Z"}\n'
_TICK = '{"op":"tick"}'
STORE_CASES = [
    (
        "Write a forged retire line over reggate",
        _store("Write", "agent/reggate/main.jsonl", content=_RETIRE),
        True,
    ),
    (
        "Edit a worklist event",
        _store("Edit", "agent/worklist/d778be9d.jsonl", old_string="{}", new_string=_TICK),
        True,
    ),
    (
        "MultiEdit another ledger",
        _store("MultiEdit", "agent/ledgers/effort-outcomes.jsonl", edits=[]),
        True,
    ),
    ("Write a new reggate file", _store("Write", "agent/reggate/new.jsonl", content="x"), True),
    (
        "Write through a link to the reggate dir",
        _store("Write", "rg/main.jsonl", content="x"),
        True,
    ),
    (
        "Write via a dot-dot detour",
        _store("Write", "agent/x/../reggate/main.jsonl", content="x"),
        True,
    ),
    (
        "Write by absolute path",
        _store("Write", str(STORE_WORLD / "agent/worklist/d778be9d.jsonl"), content="x"),
        True,
    ),
    (
        "Edit the worklist README",
        _store("Edit", "agent/worklist/README.md", old_string="{}", new_string="x"),
        False,
    ),
    (
        "Write the feedback snapshot",
        _store("Write", "agent/ledgers/feedback-snapshot.json", content="{}"),
        False,
    ),
    (
        "Write a plan naming a store",
        _store("Write", "agent/plans/PLAN-x.md", content="agent/reggate/main.jsonl"),
        False,
    ),
    (
        "Write a sibling directory",
        _store("Write", "agent/reggate-old/main.jsonl", content="x"),
        False,
    ),
    (
        "Write a store backup beside it",
        _store("Write", "agent/worklist/d778be9d.jsonl.bak", content="x"),
        False,
    ),
]

REVIEW = _load("_review_file_suite")
LEDGER = _load("_live_proof_ledger_suite")

# (row, its cases, how a refusal reads, the plant that removes it: None is the DEFECT).
ROWS = [
    ("review_file", REVIEW.EDIT_CASES, REVIEW.STYLE, "review_file"),
    ("live_proof_ledger", LEDGER.EDIT_CASES, LEDGER.STYLE, "live_proof_ledger"),
    (
        "agent_store",
        STORE_CASES,
        _edit_suite.Style(says="append-only agent store", rc=True),
        "agent_store",
    ),
    ("roundlog", ROUNDLOG_CASES, _edit_suite.Style(says="worklist.py --roundlog"), None),
]


def main():
    total = 0
    for row, cases, style, mutant in ROWS:
        print("== %s, row %s" % (STEM, row))
        total += _edit_suite.run_cases(STEM, cases, _edit_suite.via_dispatch, style)
        refusals = sum(1 for c in cases if c[2])
        if refusals < _edit_suite.FLOOR or len(cases) - refusals < _edit_suite.FLOOR:
            print("FLOOR: at least %d cases of each direction" % _edit_suite.FLOOR)
            total += 1
        runner = _edit_suite.defect_runner(STEM, mutant)
        turned = _edit_suite.run_cases(STEM, cases, runner, style, quiet=True)
        label = "DEFECT" if mutant is None else "MUTANTS[%r]" % mutant
        print(
            "%s planted: %d case(s) of row %s fail%s"
            % (label, turned, row, "" if turned else "  *** the suite cannot fail ***")
        )
        total += turned == 0
    return _edit_suite.finish(total)


if __name__ == "__main__":
    sys.exit(main())
