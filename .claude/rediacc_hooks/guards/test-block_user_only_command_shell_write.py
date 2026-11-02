#!/usr/bin/env python3
"""Control harness for block_user_only_command_shell_write: the shell half of "no command or skill is user-only".

The cases and the runner live in `test-block_user_only_command.py` beside this file, so the two halves are judged by one set of rules; this file runs the shell cases through dispatch.py in both directions, then plants the guard's DEFECT and requires the run to fail.

The cases below are this guard's own, added to the shared shell cases: a redirect target is read as typed and as bash expands it (#7b3f34ae). Each MUTANT plants the defect that fix removed and must turn at least one row.

    test-block_user_only_command_shell_write.py
"""

import importlib.util
import json
import pathlib
import sys
import tempfile
import typing

SHARED = pathlib.Path(__file__).resolve().with_name("test-block_user_only_command.py")
STEM = "block_user_only_command_shell_write"


def _shared():
    spec = importlib.util.spec_from_file_location("user_only_harness", SHARED)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load %s" % SHARED)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _own_cases(shared):
    """Rows measured at e76fe1061: each refusal was allowed (rc 0), because the redirect target was read as typed (`$D/zz.md`, `$L`)."""
    key = shared.K
    return [
        (
            "append of the key through an assigned directory",
            'D=.claude/commands; echo "%s: true" >> $D/zz.md' % key,
            True,
        ),
        (
            "overwrite with the key through an assigned directory",
            'D=.claude/commands; echo "%s: true" > $D/zz.md' % key,
            True,
        ),
        (
            "append of the key through a name assigned in an if",
            'D=elsewhere; if true; then D=.claude/commands; fi; echo "%s: true" >> $D/zz.md' % key,
            True,
        ),
        (
            "append to the exception list through an assigned name",
            "L=%s; echo '{}' >> $L" % shared.LIST,
            True,
        ),
        (
            "append of the key to a listed command through an assigned directory",
            "D=.claude/commands; cat >> $D/listed.md <<'EOF'\n---\n%s: true\n---\nEOF" % key,
            True,
        ),
        (
            "an assigned directory holding no command (control)",
            'D=docs; echo "%s: true" >> $D/zz.md' % key,
            False,
        ),
        (
            "plain text into a command through an assigned directory (control)",
            "D=.claude/commands; echo plain >> $D/zz.md",
            False,
        ),
        (
            "the key through an unset variable (control)",
            'echo "%s: true" >> $UNSET_D/zz.md' % key,
            False,
        ),
    ]


MUTANTS = [
    (
        "a run's redirects read as typed (#7b3f34ae)",
        [
            (
                "        for target in shellscan.redirect_targets(run):\n            why = redirect_refusal",
                "        for target in run.writes:\n            why = redirect_refusal",
            )
        ],
    ),
    (
        "the append flag read as typed (#7b3f34ae)",
        [
            (
                'appends = {target for op, target in _redirects(analysis) if op in (">>", "&>>")}',
                'appends = {target for op, target in analysis.writes if op in (">>", "&>>")}',
            )
        ],
    ),
    (
        "the exception list's redirects read as typed, both loops (#7b3f34ae)",
        [
            (
                "    for _op, target in _redirects(analysis):\n        if _is_list(target, base=_base(None, cwd)):",
                "    for _op, target in analysis.writes:\n        if _is_list(target, base=_base(None, cwd)):",
            ),
            (
                "        for target in shellscan.redirect_targets(run):\n            if _is_list(target, prefix, base):",
                "        for target in run.writes:\n            if _is_list(target, prefix, base):",
            ),
        ],
    ),
]


def _planted(shared, scratch, pairs):
    """The guard with `old` replaced by `new`, imported in-process from `scratch`; None when `old` is not in the guard outside its DEFECT declaration."""
    shared._syspath.on_sys_path(str(shared.HERE.parents[2]))
    hookio = importlib.import_module("rediacc_hooks.hookio")
    good = importlib.import_module("rediacc_hooks.guards.%s" % STEM)
    src = pathlib.Path(str(good.__file__)).read_text(encoding="utf-8")
    if any(old not in shared._outside_defect(src) for old, _new in pairs):
        return None
    for old, new in pairs:
        src = src.replace(old, new)
    mutant = scratch / "mutant_guard.py"
    mutant.write_text(src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("mutant_" + STEM, mutant)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load the planted copy of %s" % STEM)
    broken: typing.Any = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(broken)

    def run(_stem, payload):
        event = hookio.Event(json.dumps(payload))
        rc = broken.run(event)
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
    with tempfile.TemporaryDirectory(prefix="uo-guard-mutants-") as tmp:
        root = pathlib.Path(tmp) / "world"
        scratch = pathlib.Path(tmp) / "planted"
        scratch.mkdir()
        for label, pairs in MUTANTS:
            runner = _planted(shared, scratch, pairs)
            if runner is None:
                fails += 1
                print("plant %-52s *** FAIL *** it no longer applies to the guard" % label)
                continue
            turned = shared.run_cases(STEM, own, runner, root, quiet=True)
            fails += not turned
            print(
                "plant %-52s turns %d row(s) %s"
                % (label, turned, "ok" if turned else "*** FAIL *** the harness cannot see it")
            )
    print("MUTANT FAILURES: %d" % fails)
    return 1 if total or fails else 0


if __name__ == "__main__":
    sys.exit(main())
