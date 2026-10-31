#!/usr/bin/env python3
"""Control harness for block_suppressions_shell_write: the shell half of "no NEW inline suppression marker".

The cases and the runner live in `test-block_suppressions.py` beside this file, so the two halves are judged by one set of rules; this file runs the shell cases through dispatch.py in both directions, then plants the guard's DEFECT and requires the run to fail.

The cases below are this guard's own, added to the shared shell cases: a redirect target is read as typed and as bash expands it (#7b3f34ae). Each MUTANT plants the defect that fix removed and must turn at least one row.

    test-block_suppressions_shell_write.py
"""

import importlib.util
import json
import pathlib
import sys
import typing

SHARED = pathlib.Path(__file__).resolve().with_name("test-block_suppressions.py")
STEM = "block_suppressions_shell_write"


def _shared():
    spec = importlib.util.spec_from_file_location("suppressions_harness", SHARED)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load %s" % SHARED)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _own_cases(shared):
    """Rows measured at e76fe1061: each refusal was allowed (rc 0), because the redirect target was read as typed (`$F`)."""
    marker = "y = 1  %s: F401" % shared.NQ
    return [
        (
            "append through an assigned file name",
            "F=%s; echo '%s' >> $F" % (shared.KEPT, marker),
            True,
        ),
        (
            "append through a braced file name",
            "F=%s; echo '%s' >> ${F}" % (shared.KEPT, marker),
            True,
        ),
        (
            "append through a name assigned in an if",
            "F=%s.txt; if true; then F=%s; fi; echo '%s' >> $F"
            % (shared.KEPT, shared.KEPT, marker),
            True,
        ),
        (
            "append through a name assigned to a non-source file (control)",
            "F=%s.txt; echo '%s' >> $F" % (shared.KEPT, marker),
            False,
        ),
        ("append through an unset variable (control)", "echo '%s' >> $UNSET_F" % marker, False),
        # Review ff357dfa.1: text the hook cannot read (`$X` is assigned nowhere in the command, so its value is unknowable to the hook, whatever the calling shell holds), appended through an assigned source name, stays allowed as the typed form does (measured rc 0 for both), because no marker is spelled.
        (
            "append of unexpandable text through an assigned name (control)",
            'F=%s; echo "$X" >> $F' % shared.KEPT,
            False,
        ),
        (
            "append of unexpandable text to the typed name (control)",
            'echo "$X" >> %s' % shared.KEPT,
            False,
        ),
        (
            "redirect bash refuses as ambiguous (control)",
            "F=\"%s %s\"; echo '%s' >> $F" % (shared.KEPT, shared.KEPT, marker),
            False,
        ),
    ]


MUTANTS = [
    (
        "a redirect's append flag read as typed (#7b3f34ae)",
        (
            'appends = {target for op, target in _redirects(analysis) if op in (">>", "&>>")}',
            'appends = {target for op, target in analysis.writes if op in (">>", "&>>")}',
        ),
    ),
    (
        "a run's redirect targets read as typed (#7b3f34ae)",
        (
            "targets = shellscan.redirect_targets(run) + (",
            "targets = list(run.writes) + (",
        ),
    ),
]


def _planted(shared, old, new):
    """The guard with `old` replaced by `new`, run in-process; None when `old` is not in the guard outside its DEFECT declaration."""
    shared._syspath.on_sys_path(str(shared.HERE.parents[2]))
    hookio = shared.importlib.import_module("rediacc_hooks.hookio")
    good = shared.importlib.import_module("rediacc_hooks.guards.%s" % STEM)
    src = pathlib.Path(str(good.__file__)).read_text(encoding="utf-8")
    if old not in shared._outside_defect(src):
        return None
    mutant = shared.SCRATCH / ("mutant_%s.py" % STEM)
    shared.SCRATCH.mkdir(parents=True, exist_ok=True)
    mutant.write_text(src.replace(old, new), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("mutant_" + STEM, mutant)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load the planted copy of %s" % STEM)
    broken = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(broken)
    ns: dict[str, typing.Any] = vars(broken)

    def run(_stem, payload):
        event = hookio.Event(json.dumps(payload))
        rc = ns["run"](event)
        _rc, out, err = event.result(rc)
        return rc, out + err

    return run


def main():
    shared = _shared()
    own_rows = _own_cases(shared)
    shared.SHELL_CASES = [*shared.SHELL_CASES, *own_rows]
    total = shared.main((STEM,))
    own = [(n, {"tool_name": "Bash", "tool_input": {"command": c}}, r) for n, c, r in own_rows]
    fails = 0
    try:
        for label, (old, new) in MUTANTS:
            runner = _planted(shared, old, new)
            if runner is None:
                fails += 1
                print("plant %-52s *** FAIL *** it no longer applies to the guard" % label)
                continue
            turned = shared.run_cases(STEM, own, runner, quiet=True)
            fails += not turned
            print(
                "plant %-52s turns %d row(s) %s"
                % (label, turned, "ok" if turned else "*** FAIL *** the harness cannot see it")
            )
    finally:
        shared.shutil.rmtree(str(shared.SCRATCH), ignore_errors=True)
        shared.OUTSIDE.unlink(missing_ok=True)
    print("MUTANT FAILURES: %d" % fails)
    return 1 if total or fails else 0


if __name__ == "__main__":
    sys.exit(main())
