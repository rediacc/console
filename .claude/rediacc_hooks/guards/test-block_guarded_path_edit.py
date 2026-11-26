#!/usr/bin/env python3
"""Control harness for block_guarded_path_edit, the one pre-edit guard over the three path-judged rows of `_write_rules.ROWS` (PLAN-tooling-code-reduction CR5).

Each row keeps the cases its own guard was judged by before the merge: the review record cases of `_review_file_suite.py` (once block_review_file_edit's), the ledger cases of `_live_proof_ledger_suite.py` (once block_live_proof_ledger_write's), and the round log cases below (once block_roundlog_write's, which its golden still judges as well). Every case runs through dispatch.py in both directions, with a floor of four cases each way per row,
because a one-sided control is satisfiable by a broken hook.

Then each row's plant is put in an in-process copy of the guard and must turn at least one case OF ITS OWN ROW: the DEFECT for the round log, `MUTANTS["review_file"]` and `MUTANTS["live_proof_ledger"]` for the other two. A plant that only turned another row's cases would be proof of nothing about its own.

    test-block_guarded_path_edit.py        every row's cases through dispatch.py, then each row's plant
"""

import importlib.util
import pathlib
import sys

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

REVIEW = _load("_review_file_suite")
LEDGER = _load("_live_proof_ledger_suite")

# (row, its cases, how a refusal reads, the plant that removes it: None is the DEFECT).
ROWS = [
    ("review_file", REVIEW.EDIT_CASES, REVIEW.STYLE, "review_file"),
    ("live_proof_ledger", LEDGER.EDIT_CASES, LEDGER.STYLE, "live_proof_ledger"),
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
