#!/usr/bin/env python3
"""Control harness for block_review_file_shell_write: the shell half of "a review record is never edited by hand".

The cases and the runner live in `test-block_review_file_edit.py` beside this file, so the two halves are judged by one set of rules; this file runs the shell cases through dispatch.py in both directions, then plants the guard's DEFECT and requires the run to fail.

The cases below are this guard's own, added to the shared shell cases: the operand arms read the words as bash expands them (#f6334e52), and the glob pre-filter reads only a glob that can spell the review directory as one (#a1852a9e). Each MUTANT plants the defect one of them fixed and must turn at least one row, so neither fix is pinned by a harness that cannot see it.

    test-block_review_file_shell_write.py
"""

import importlib
import importlib.util
import json
import pathlib
import sys
import typing

SHARED = pathlib.Path(__file__).resolve().with_name("test-block_review_file_edit.py")
STEM = "block_review_file_shell_write"

OWN_CASES = [
    # #f6334e52: each refusal was allowed (rc 0) at a7b3a36f6, because the operand was read as typed (`$D/y.md`).
    ("tee through an assigned directory", "D=agent/reviews/x; tee $D/y.md", True),
    ("sudo tee through an assigned directory", "D=agent/reviews/x; sudo tee $D/y.md", True),
    ("timeout tee through an assigned directory", "D=agent/reviews/x; timeout 5 tee $D/y.md", True),
    ("tee through a quoted braced variable", 'D=agent/reviews/x; tee "${D}/y.md"', True),
    ("truncate through an assigned directory", "D=agent/reviews/x; truncate -s 0 $D/y.md", True),
    ("sed -i through an assigned directory", "D=agent/reviews/x; sed -i s/a/b/ $D/y.md", True),
    ("cp onto an assigned directory", "D=agent/reviews/x; cp /tmp/a.md $D/", True),
    ("tee through an assigned directory, elsewhere", "D=plain; tee $D/y.md", False),
    ("cat through an assigned directory", "D=agent/reviews/x; cat $D/y.md", False),
    ("tee through an unset variable", "tee $UNSET_REVIEW_DIR/y.md", False),
    # #a1852a9e: the first two were refused (rc 2) at a7b3a36f6 for the `.*` inside the sed or perl expression.
    ("sed -i with .* then the script runs", "sed -i 's/a.*b/c/' x.py && python3 x.py", False),
    (
        "perl -pi with .* then the script runs",
        "perl -pi -e 's/a.*b/c/' x.py && python3 x.py",
        False,
    ),
    ("cp onto a glob that reads as the directory", "cp x agent/revi*s/", True),
    ("sed -i with .* on a globbed review file", "sed -i 's/a.*b/c/' agent/revi*s/x/y.md", True),
    ("tee onto a glob under cd agent", "cd agent && tee revi*s/y.md", True),
    ("xargs cp fed a glob under cd agent", "cd agent && echo revi*s/x | xargs cp a", True),
    # A glob in the directory the run executes in is read as one in its word is: this was allowed (rc 0) at a7b3a36f6.
    ("tee under a globbed cd", "cd agen? && tee revi*s/x.md", True),
    ("tee under a globbed cd, a sibling directory", "cd agen? && tee reviews-old/x.md", False),
]

MUTANTS = [
    (
        "operands read as typed only (#f6334e52)",
        (
            "what = _operand_write(run, name, list(words), where, base, cwd)",
            "what = _operand_write(run, name, argv, where, base, cwd)",
        ),
    ),
    (
        "any glob character sends the command on (#a1852a9e)",
        ("and not _globs_reviews(cmd, cwd)", 'and not any(ch in cmd for ch in "*?[{")'),
    ),
    (
        "the pre-filter blind to a glob word",
        ("        if any(spells(w, where) for w in words):", "        if False:"),
    ),
    (
        "the run directory joined as typed",
        (
            "for w in joined for form in _review_forms(w)",
            (
                "for w in joined[:1] for form in [*_review_forms(w), *("
                "str(cwd).rstrip('/') + '/' + f for f in _review_forms(w) if cwd)]"
            ),
        ),
    ),
]


def _shared():
    spec = importlib.util.spec_from_file_location("review_file_harness", SHARED)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load %s" % SHARED)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _planted(shared, old, new):
    """The guard with `old` replaced by `new`, run in-process; None when `old` is not in the guard outside its DEFECT declaration."""
    shared._syspath.on_sys_path(str(shared.HERE.parents[2]))
    hookio = importlib.import_module("rediacc_hooks.hookio")
    good = importlib.import_module("rediacc_hooks.guards.%s" % STEM)
    src = pathlib.Path(str(good.__file__)).read_text(encoding="utf-8")
    if old not in shared._outside_defect(src):
        return None
    ns: dict[str, typing.Any] = {"__name__": "planted_" + STEM, "__file__": good.__file__}
    exec(compile(src.replace(old, new), str(good.__file__), "exec"), ns)

    def run(_stem, payload):
        event = hookio.Event(json.dumps(payload))
        rc = ns["run"](event)
        _rc, out, err = event.result(rc)
        return rc, out + err

    return run


def main():
    shared = _shared()
    shared.SHELL_CASES = [*shared.SHELL_CASES, *OWN_CASES]
    total = shared.main((STEM,))
    own = [(n, {"tool_name": "Bash", "tool_input": {"command": c}}, r) for n, c, r in OWN_CASES]
    fails = 0
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
    print("MUTANT FAILURES: %d" % fails)
    return 1 if total or fails else 0


if __name__ == "__main__":
    sys.exit(main())
