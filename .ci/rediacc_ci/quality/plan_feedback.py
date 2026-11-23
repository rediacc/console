"""check:ci-plan-feedback -- every `Feedback:` id a live plan names is in the public feedback snapshot (agent/plans/PLAN-rdc-feedback.md R10, D5, box T3).

THE CLAIM. A plan's `Feedback:` header line links it to field reports by their 12-hex short fingerprint (plangen writes it for a confirmed report, `rediacc_ci.feedback.link` adds matches). `agent/ledgers/feedback-snapshot.json` is the public record of which fingerprints exist, written by `link` and `ship` from the admin export. An id on a plan that the snapshot does not hold is a link to nothing: a typo, a purged report, or a snapshot nobody refreshed.

THE GRAMMAR IS NOT HERE. `rediacc_ci.feedback.link` owns the `Feedback:` line (`feedback_line`, header only, before the first `## `) and the snapshot shape (`read_snapshot`), so the gate, the two verbs and plangen read one definition.

WHICH PLANS: the top-level `agent/plans/PLAN-*.md` files. `_done/` and `_removed/` are not live.

FINDINGS, EACH WITH A PLANTED CONTROL IN `--selftest`:

    F1  an id on a plan's `Feedback:` line that the snapshot does not hold
    F2  a token on a `Feedback:` line that is not 12 lowercase hex
    F3  a plan carries the line while the snapshot is missing, unreadable, or empty:
        never a pass, since every id would then be unchecked
    F4  the snapshot exists but holds another shape, or a row with any key beyond
        id, status and fixed_in (the repository is public), checked even when no
        plan carries the line
    F0  the vacuity floor: zero plan files read is CANNOT RUN (exit 77), never green

Zero plans carrying the line is a PASS, and the success line prints the plan count, the carrier count and the snapshot size, so a collapse to zero is visible.

    --check        (the default) controls first, then the verdict
    --selftest     the planted controls alone, real files under a scratch root included
    --root <dir>   judge another tree

Exit codes: 0 green, 1 findings, 2 a control failed or bad usage, 77 cannot run.

---- gate ----
step: Plan feedback links
needs: none
lane: quality-static
selftest: true
why: a plan's Feedback: line is how a field report learns it was fixed; an id
     the public snapshot does not hold links the plan to nothing, and the ship
     step then never marks the report fixed-in-vX.
---- end gate ----
"""

from __future__ import annotations

import io
import json
import pathlib
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout

from rediacc_ci import controls, paths
from rediacc_ci.feedback import link

CONTROL_FLOOR = 14
FIX = (
    "run `PYTHONPATH=.ci python3 -m rediacc_ci.feedback.link run --plan <plan>` (or `... ship run`) "
    "to refresh the snapshot from the export, or correct the id; never add an id to the snapshot by hand"
)


class CannotRunError(RuntimeError):
    """The gate is not seeing the tree; its green would mean nothing."""


def evaluate(plans: dict[str, str], snapshot: str | None) -> tuple[list[str], dict[str, int]]:
    """(findings, shape) for plan texts keyed by repo-relative path and the snapshot text (None: absent)."""
    if not plans:
        msg = "zero plan files under agent/plans; the gate is not seeing the tree"
        raise CannotRunError(msg)
    findings: list[str] = []
    rows = None
    snap_error = None
    if snapshot is not None:
        with tempfile.TemporaryDirectory(prefix="plan-feedback-read-") as tmp:
            path = pathlib.Path(tmp) / "feedback-snapshot.json"
            path.write_text(snapshot, encoding="utf-8")
            try:
                rows = link.read_snapshot(path)
            except link.SnapshotError as exc:
                snap_error = str(exc)
                findings.append("F4 %s: %s" % ("/".join(link.SNAPSHOT_PARTS), snap_error))
    known = {r["id"] for r in rows or []}
    carriers = 0
    ids_total = 0
    for rel in sorted(plans):
        held = link.feedback_line(plans[rel])
        if held is None:
            continue
        carriers += 1
        ids_total += len(held.ids)
        findings += [
            "F2 %s: Feedback: token %r is not a 12-hex short fingerprint" % (rel, bad)
            for bad in held.bad
        ]
        if not held.ids and not held.bad:
            findings.append("F2 %s: the Feedback: line names no id" % rel)
        if rows is None or not known:
            continue
        findings += [
            "F1 %s: Feedback: id %s is not in the snapshot; %s" % (rel, i, FIX)
            for i in held.ids
            if i not in known
        ]
    if carriers and snap_error is None and (rows is None or not known):
        state = "missing" if rows is None else "empty"
        findings.append(
            "F3 %d plan(s) carry a Feedback: line while %s is %s, so every id is unchecked; %s"
            % (carriers, "/".join(link.SNAPSHOT_PARTS), state, FIX)
        )
    shape = {
        "plans": len(plans),
        "carriers": carriers,
        "ids": ids_total,
        "snapshot": -1 if rows is None else len(rows),
    }
    return findings, shape


def read_tree(root: pathlib.Path) -> tuple[dict[str, str], str | None]:
    plans = {
        paths.relative_to_root(p, root): p.read_text(encoding="utf-8", errors="replace")
        for p in link.live_plans(root)
    }
    snap = root.joinpath(*link.SNAPSHOT_PARTS)
    return plans, (snap.read_text(encoding="utf-8") if snap.is_file() else None)


def check(root: pathlib.Path) -> int:
    findings, shape = evaluate(*read_tree(root))
    snap = "absent" if shape["snapshot"] < 0 else "%d fingerprint(s)" % shape["snapshot"]
    summary = "%d live plan(s), %d carry Feedback: with %d id(s), snapshot %s" % (
        shape["plans"],
        shape["carriers"],
        shape["ids"],
        snap,
    )
    if findings:
        for f in findings:
            print("✗ %s" % f, file=sys.stderr)
        print("✗ plan feedback: %d finding(s) over %s" % (len(findings), summary), file=sys.stderr)
        return 1
    print("✓ plan feedback: %s" % summary)
    return 0


# ---- controls ------------------------------------------------------------------------------------

A = "a" * 12
B = "b" * 12


def _plan(feedback: str | None = None) -> str:
    rows = ["# PLAN: x", "", "Status: draft", "Owns: agent/plans/PLAN-x.md"]
    if feedback is not None:
        rows.append("Feedback: %s" % feedback)
    return "\n".join([*rows, "", "## Boxes", "", "- [ ] T1 [writer] x", ""])


def _snap(*ids: str, extra: dict | None = None) -> str:
    rows = [{"id": i, "status": "planned", "fixed_in": None, **(extra or {})} for i in ids]
    return json.dumps({"version": 1, "fingerprints": rows})


def _codes(plans: dict[str, str], snapshot: str | None) -> list[str]:
    return sorted(f.split(" ", 1)[0] for f in evaluate(plans, snapshot)[0])


def _quiet_check(root: pathlib.Path) -> int:
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        try:
            return check(root)
        except CannotRunError:
            return 77


def _write_root(base: pathlib.Path, plans: dict[str, str], snapshot: str | None) -> pathlib.Path:
    for name, text in plans.items():
        target = base / "agent" / "plans" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    if snapshot is not None:
        target = base.joinpath(*link.SNAPSHOT_PARTS)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(snapshot, encoding="utf-8")
    return base


def selftest() -> int:
    """Controls before plants: a gate that flags everything fails the controls, one that flags nothing fails the plants."""
    tally = controls.Controls("plan feedback", floor=CONTROL_FLOOR)
    p = "agent/plans/PLAN-x.md"
    q = "agent/plans/PLAN-y.md"
    # Controls: must stay green.
    tally.check(
        "control: an id present in the snapshot passes", _codes({p: _plan(A)}, _snap(A)), []
    )
    tally.check(
        "control: zero plans with the line pass, even with no snapshot",
        _codes({p: _plan(), q: _plan()}, None),
        [],
    )
    tally.check(
        "control: two ids, comma separated, both present, pass",
        _codes({p: _plan("%s, %s" % (A, B))}, _snap(A, B)),
        [],
    )
    tally.check(
        "control: a Feedback: line below the first ## heading is not a header line",
        _codes({p: _plan() + "\nFeedback: %s\n" % A}, _snap(B)),
        [],
    )
    tally.check(
        "control: the success shape counts plans, carriers, ids and snapshot rows",
        evaluate({p: _plan(A), q: _plan()}, _snap(A, B))[1],
        {"plans": 2, "carriers": 1, "ids": 1, "snapshot": 2},
    )
    # Plants: must fire.
    tally.check(
        "F1 planted: an id absent from the snapshot", _codes({p: _plan(A)}, _snap(B)), ["F1"]
    )
    tally.check(
        "F1 planted: one of two ids absent", _codes({p: _plan("%s %s" % (A, B))}, _snap(A)), ["F1"]
    )
    tally.check(
        "F2 planted: a token that is not 12 hex", _codes({p: _plan("abc123")}, _snap(A)), ["F2"]
    )
    tally.check("F2 planted: an empty Feedback: line", _codes({p: _plan("")}, _snap(A)), ["F2"])
    tally.check(
        "F3 planted: an empty snapshot while a plan carries the line",
        _codes({p: _plan(A)}, _snap()),
        ["F3"],
    )
    tally.check(
        "F3 planted: a missing snapshot while a plan carries the line",
        _codes({p: _plan(A)}, None),
        ["F3"],
    )
    tally.check(
        "F4 planted: a snapshot row carrying a field beyond id, status, fixed_in",
        _codes({p: _plan()}, _snap(A, extra={"argv": "rdc repo up"})),
        ["F4"],
    )
    tally.check(
        "F4 planted: a snapshot of another version",
        _codes({p: _plan()}, '{"version": 2, "fingerprints": []}'),
        ["F4"],
    )
    tally.raises(
        "F0 planted: zero plans read is CANNOT RUN, never green",
        CannotRunError,
        evaluate,
        {},
        _snap(A),
    )
    # The real-file path: the same `check` the CLI runs, over a scratch root.
    with tempfile.TemporaryDirectory(prefix="plan-feedback-") as tmp:
        root = _write_root(pathlib.Path(tmp), {"PLAN-x.md": _plan(A)}, _snap(A))
        tally.check("real files, control: a present id exits 0", _quiet_check(root), 0)
        (root / "agent" / "plans" / "PLAN-y.md").write_text(_plan(B), encoding="utf-8")
        tally.check("real files, plant: an absent id exits 1", _quiet_check(root), 1)
        done = root / "agent" / "plans" / "_done"
        done.mkdir()
        (root / "agent" / "plans" / "PLAN-y.md").replace(done / "PLAN-y.md")
        tally.check("real files, control: a _done plan is not live", _quiet_check(root), 0)
    with tempfile.TemporaryDirectory(prefix="plan-feedback-") as tmp:
        tally.check(
            "real files, F0: an empty plans tree exits 77", _quiet_check(pathlib.Path(tmp)), 77
        )
    return 0 if tally.report() else 1


def main(argv: list[str]) -> int:
    try:
        if "--selftest" in argv:
            return selftest()
        root = paths.repo_root()
        if "--root" in argv:
            i = argv.index("--root")
            if i + 1 >= len(argv):
                print("✗ --root needs a directory", file=sys.stderr)
                return 2
            root = pathlib.Path(argv[i + 1])
        unknown = [a for a in argv if a.startswith("--") and a not in ("--root", "--check")]
        if unknown:
            print("✗ unknown flag(s): %s" % " ".join(unknown), file=sys.stderr)
            return 2
        refused = controls.controls_first("plan feedback", selftest)
        if refused:
            return refused
        return check(root)
    except CannotRunError as exc:
        print("⚠ CANNOT RUN (exit 77, which is not a verdict): %s" % exc, file=sys.stderr)
        return 77


if __name__ == "__main__":
    from rediacc_ci.quality import gate_args

    gate_args.parse(
        "check_plan_feedback.py",
        sys.argv[1:],
        switches=("--selftest", "--check"),
        valued=("--root",),
    )
    sys.exit(main(sys.argv[1:]))
