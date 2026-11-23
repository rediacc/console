"""The runner the edit/shell twin suites share (PLAN-tooling-code-reduction CR5, D5).

WHY ONE RUNNER. Four edit-half suites (`test-block_review_file_edit.py`, `test-block_user_only_command.py`, `test-block_live_proof_ledger_write.py`, `test-block_protected_files_edit.py`) each carried the same machinery: drive a case through dispatch.py, plant the guard's DEFECT into an in-process copy, run every case against both, print one line per case and hold a floor of four cases each way. The copies differed only in what a refusal must say, the column width and how much of a failure is shown. Those are the arguments here; the cases and their worlds stay in each guard's own suite, which is what the mutation gate runs.

A CASE is `(name, payload, refused)`. A refused case passes only when the guard refuses it AND its text satisfies `says` (the guard's door, so a refusal for some other reason does not count); an allowed case passes only when the guard allows it.

THE PLANT is imported from a copy under a scratch directory, never `exec`ed: `old` must appear in the guard outside its own DEFECT declaration, or the plant would be satisfied by the line that names it.
"""

import ast
import atexit
import importlib
import importlib.util
import json
import pathlib
import shutil
import sys
import tempfile
import typing

from rediacc_hooks.guards import _harness

DISPATCH = str(pathlib.Path(__file__).resolve().parents[1] / "dispatch.py")
FLOOR = 4


def via_dispatch(stem, payload):
    """`(rc, stdout + stderr)` of `payload` through dispatch.py running `stem` alone."""
    p = _harness.run(
        [sys.executable, DISPATCH, stem],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    return p.returncode, p.stdout + p.stderr


def outside_defect(src: str, *names: str) -> str:
    """`src` with every top-level `DEFECT` (or named) assignment removed, so a needle search cannot be satisfied by the declaration that names it.

    `old in src` alone stays true after the guarded line is deleted, because the declaration itself contains the text it plants (measured 2026-10-05).
    """
    wanted = names or ("DEFECT",)
    cut = [
        n
        for n in ast.parse(src).body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id in wanted for t in n.targets)
    ]
    return "\n".join(
        line
        for i, line in enumerate(src.split("\n"), 1)
        if not any(n.lineno <= i <= (n.end_lineno or n.lineno) for n in cut)
    )


def transcript(answer_ts, run_tmp):
    """A lead transcript under `run_tmp` holding one AskUserQuestion and its answer at `answer_ts`, as a path (the four push and release suites shared this copy)."""
    path = pathlib.Path(tempfile.mkdtemp(prefix="transcript-", dir=run_tmp)) / "lead.jsonl"
    records = [
        {
            "type": "assistant",
            "timestamp": "2026-01-01T00:00:10Z",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "AskUserQuestion", "id": "toolu_fixture_ask"}
                ]
            },
        },
        {
            "type": "user",
            "timestamp": answer_ts,
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_fixture_ask", "content": "a"}
                ]
            },
        },
    ]
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return str(path)


_SCRATCH: list[pathlib.Path] = []


def _scratch():
    if not _SCRATCH:
        made = pathlib.Path(tempfile.mkdtemp(prefix="edit-suite-planted-"))
        atexit.register(shutil.rmtree, str(made), True)
        _SCRATCH.append(made)
    return _SCRATCH[0]


def defect_runner(stem):
    """A runner `(stem, payload) -> (rc, text)` over the guard with its declared DEFECT planted, imported in-process from a copy under a scratch directory."""
    hookio = importlib.import_module("rediacc_hooks.hookio")
    good = importlib.import_module("rediacc_hooks.guards.%s" % stem)
    old, new = good.DEFECT
    src = pathlib.Path(str(good.__file__)).read_text(encoding="utf-8")
    if old not in outside_defect(src):
        raise SystemExit("the DEFECT no longer applies to %s outside its own declaration" % stem)
    planted = _scratch() / ("broken_%s.py" % stem)
    planted.write_text(src.replace(old, new), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("broken_" + stem, planted)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load the planted copy of %s" % stem)
    broken: typing.Any = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(broken)

    def run(_stem, payload):
        event = hookio.Event(json.dumps(payload))
        rc = broken.run(event)
        _rc, out, err = event.result(rc)
        return rc, out + err

    return run


class Style(typing.NamedTuple):
    """How one suite judges and prints a case: `says` is the text a refusal must carry, `width` the name column, `shown` how many characters of a failure are printed, `rc` whether a failure shows its exit code, and `prepare` (payload -> payload) sets up the world a case runs in."""

    says: str
    width: int = 52
    shown: int = 160
    rc: bool = False
    prepare: typing.Callable[[dict], dict] | None = None


def run_cases(stem, cases, runner, style, quiet=False):
    """The number of cases `runner` gets wrong, one line per case unless `quiet`."""
    fails = 0
    for name, raw, refused in cases:
        payload = style.prepare(raw) if style.prepare is not None else raw
        rc, text = runner(stem, payload)
        blocked = rc != 0
        ok = blocked == refused and (not refused or style.says in text)
        fails += not ok
        if not quiet:
            failure = ("rc=%d " % rc if style.rc else "") + text[: style.shown]
            print(
                "%-*s want=%-8s %s"
                % (
                    style.width,
                    name,
                    "BLOCKED" if refused else "allowed",
                    "ok" if ok else "*** FAIL *** " + failure,
                )
            )
    return fails


def judge(stem, cases, style, header=True):
    """Every case through dispatch.py, the floor of FLOOR cases each way, then the DEFECT plant, which must turn at least one case; the failure count."""
    if header:
        print("== %s" % stem)
    total = run_cases(stem, cases, via_dispatch, style)
    refusals = sum(1 for c in cases if c[2])
    if refusals < FLOOR or len(cases) - refusals < FLOOR:
        print("FLOOR: at least %d cases of each direction" % FLOOR)
        total += 1
    planted = run_cases(stem, cases, defect_runner(stem), style, quiet=True)
    print(
        "DEFECT planted in %s: %d case(s) fail%s"
        % (stem, planted, "" if planted else "  *** the suite cannot fail ***")
    )
    return total + (planted == 0)


def finish(total):
    """Print the verdict line every twin suite ends with, and return its exit code."""
    print("FAILURES: %d" % total)
    return 1 if total else 0
