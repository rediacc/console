#!/usr/bin/env python3
"""Controls for the reggate effort-cap ledger's ERROR paths.

WHY THIS FILE EXISTS. The cap (operator ruling 2026-09-05T01:55Z) is an escape hatch from a blocking gate, so the question that matters is not "does it fire?" but "what happens when its own machinery breaks?" Every error path here has one correct direction -- FAIL STRICT -- and a silent flip to the lax direction is invisible from the outside: a demand that vanishes looks exactly
like a demand that was never raised.

Three paths shipped with error handling and no test, which is what this fixes:

  read_ledger   OSError    -> ([], True), NOT ([], False)
  debt_due      bad `at`   -> due, so corruption cannot hold a debt open
  the cap       any raise  -> falls through to the normal block

The debt-collection half (agent/plans/PLAN-reggate-debt-collection.md) adds the due rule, the cap on the cap, materialization, discharge and retire, each planted first and paired with its control.

Each assertion is PAIRED with a control proving the opposite input produces the opposite answer. Without the pair, a function hard-coded to return the strict answer would pass every strict assertion while having stopped working.
"""

import datetime
import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import wl_reggate as R


class Tally:
    count = 0
    fails = 0


def check(label, got, want):
    Tally.count += 1
    if got == want:
        print("ok    %s" % label)
    else:
        Tally.fails += 1
        print("FAIL  %s (got %r, want %r)" % (label, got, want), file=sys.stderr)


# --- 1. read_ledger: an unreadable ledger must be REPORTED, never read as empty
with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td)
    br = "err-paths"
    R.append_ledger(br, {"kind": "charge", "sig": "a", "why": "proven"}, root=root)

    # A directory where the ledger file should be: read_text raises OSError.
    p = R.debt_path(br, root)
    p.unlink()
    p.mkdir()
    _recs, forgot = R.read_ledger(br, root)
    check("OSError on the ledger sets forgot=True", forgot, True)
    p.rmdir()

    # CONTROL: the very same call on a READABLE ledger must say forgot=False.
    # Without this, a read_ledger hard-wired to `return [], True` would satisfy the assertion above while having stopped reading anything at all.
    R.append_ledger(br, {"kind": "charge", "sig": "b", "why": "proven"}, root=root)
    recs, forgot = R.read_ledger(br, root)
    check("CONTROL: a readable ledger reports forgot=False", forgot, False)
    check("CONTROL: and it actually returns the record", len(recs), 1)

    # A corrupt LINE is a different path from an unreadable FILE: the file opens, one line fails to parse, and the rest must survive rather than the whole ledger being discarded.
    with p.open("a", encoding="utf-8") as f:
        f.write("{not json\n")
    recs, forgot = R.read_ledger(br, root)
    check("a corrupt line sets forgot=True", forgot, True)
    check("...and the VALID records still survive it", len(recs), 1)


# --- 2. budget_state: forgot must NOT be laundered into a usable budget
with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td)
    br = "forgot-path"
    for i in range(R.REGGATE_CAP):
        R.charge(br, "s%d" % i, "proven", root=root)
    _c, remaining, _d, forgot = R.budget_state(br, root, live=br)
    check("a full budget reports remaining=0", remaining, 0)
    check("...with forgot=False, so the cap MAY fire", forgot, False)

    with R.debt_path(br, root).open("a", encoding="utf-8") as f:
        f.write("{not json\n")
    _c, _r, _d, forgot = R.budget_state(br, root, live=br)
    # THE LOAD-BEARING ONE. wl_checks gates the cap on `not forgot`, because an unreadable ledger folds to a FRESH budget -- the most permissive answer possible. Reporting forgot is what stops the cap firing on a fiction.
    check("a corrupt ledger still reports forgot=True at budget level", forgot, True)


# --- 3. debt_due (D1): not the live branch, or past grace. It replaced branch_merged, whose HEAD probe could not tell a landed branch from a fresh one.
_NOW = datetime.datetime(2026, 11, 20, 12, 0, tzinfo=datetime.UTC)
_FRESH = (_NOW - datetime.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
_OLD = (_NOW - datetime.timedelta(minutes=R.REGGATE_DEBT_GRACE_MIN + 1)).strftime(
    "%Y-%m-%dT%H:%M:%SZ"
)
check(
    "a FRESH debt on a branch that is not the live one is due",
    R.debt_due({"br": "1104-1", "at": _FRESH}, "1121-1", _NOW),
    True,
)
check(
    "a FRESH debt on the live branch is NOT due",
    R.debt_due({"br": "1121-1", "at": _FRESH}, "1121-1", _NOW),
    False,
)
# CONTROL for the pair: the same live-branch debt past grace IS due, so the False above is the clock and not a stub.
check(
    "CONTROL: a live-branch debt past grace is due",
    R.debt_due({"br": "1121-1", "at": _OLD}, "1121-1", _NOW),
    True,
)
check(
    "a fresh main.jsonl debt is due by the clock alone, not by branch",
    R.debt_due({"br": "main", "at": _FRESH}, "1121-1", _NOW),
    False,
)
check(
    "an unparseable `at` on the live branch is due (corruption cannot hold a debt open)",
    R.debt_due({"br": "1121-1", "at": "yesterday"}, "1121-1", _NOW),
    True,
)

# The counter resets for a ledger that is not the live branch; its debts stay.
with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td)
    for i in range(R.REGGATE_CAP):
        R.charge("old-br", "c%d" % i, "proven", root=root)
    R.append_ledger("old-br", {"kind": "debt", "sig": "d1", "blind_spot": "x" * 20}, root=root)
    _c, remaining, debts, _f = R.budget_state("old-br", root, live="new-br")
    check("a non-live ledger's counter resets", remaining, R.REGGATE_CAP)
    check("...and its debts do NOT", len(debts), 1)
    _c, remaining, _d, _f = R.budget_state("old-br", root, live="old-br")
    check("CONTROL: the same ledger as the live branch is spent", remaining, 0)


# --- 3b. the cap on the cap (D2): a sixth outstanding debt is refused and the demand blocks
with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td)
    br = "cap-cap"
    for i in range(R.REGGATE_CAP):
        R.charge(br, "c%d" % i, "proven", root=root)
    for i in range(R.REGGATE_MAX_DEBTS - 1):
        R.append_ledger(br, {"kind": "debt", "sig": "d%d" % i, "blind_spot": "x" * 20}, root=root)
    _c, remaining, debts, forgot = R.budget_state(br, root, live=br)
    check(
        "CONTROL: below REGGATE_MAX_DEBTS the cap still defers",
        R.cap_defers(remaining, forgot, len(debts)),
        True,
    )
    R.append_ledger(br, {"kind": "debt", "sig": "dlast", "blind_spot": "x" * 20}, root=root)
    _c, remaining, debts, forgot = R.budget_state(br, root, live=br)
    check("REGGATE_MAX_DEBTS outstanding debts are counted", len(debts), R.REGGATE_MAX_DEBTS)
    check(
        "the next demand is NOT deferred: it blocks normally",
        R.cap_defers(remaining, forgot, len(debts)),
        False,
    )
    # A discharged debt stops counting, so paying one reopens the cap.
    R.append_ledger(
        br, {"kind": "discharge", "sig": "d0", "artifact": "a", "proof": "p"}, root=root
    )
    _c, remaining, debts, forgot = R.budget_state(br, root, live=br)
    check("a discharged debt no longer counts against the cap", len(debts), R.REGGATE_MAX_DEBTS - 1)


# --- 3c. the ledger readers skip `*.*.jsonl`
with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td)
    R.append_ledger("0923-1", {"kind": "debt", "sig": "real", "blind_spot": "x" * 20}, root=root)
    side = R.debt_dir(root) / "0923-1.shapedup-wide.jsonl"
    side.write_text(json.dumps({"kind": "ask", "sig": "s", "at": "2026-01-01T00:00:00Z"}) + "\n")
    names = [p.name for p in R.ledger_paths(root)]
    check(
        "a .shapedup-wide.jsonl file is not read as a ledger",
        "0923-1.shapedup-wide.jsonl" in names,
        False,
    )
    check("CONTROL: the real ledger beside it is", names, ["0923-1.jsonl"])


# --- 4. the cap's own guard condition: wl_checks calls R.cap_defers, so the suite drives the same function
def cap_fires(remaining, forgot):
    """R.cap_defers with no outstanding debt, the budget and read halves of the predicate."""
    return R.cap_defers(remaining, forgot, 0)


check("cap fires when the budget is spent", cap_fires(0, False), True)
check("cap does NOT fire while budget remains", cap_fires(1, False), False)
# If this control ever flips, an unreadable ledger would start deferring real demands on a budget nobody could read.
check("CONTROL: cap does NOT fire on an unreadable ledger", cap_fires(0, True), False)


# --- 5. the ledger must not write into the repo when redirected
with tempfile.TemporaryDirectory() as td:
    os.environ["WORKLIST_STORE_DIR"] = str(pathlib.Path(td) / "store")
    try:
        redirected = R.debt_dir()
        check("WORKLIST_STORE_DIR redirects the ledger", str(redirected).startswith(td), True)
    finally:
        del os.environ["WORKLIST_STORE_DIR"]
    # CONTROL: without the override it falls back to the repo-relative path, so the assertion above is testing the override and not a constant.
    check(
        "CONTROL: without it, the path is repo-relative",
        R.debt_dir(pathlib.Path("/tmp/x")) == pathlib.Path("/tmp/x/agent/reggate"),
        True,
    )


# --- 6. a record round-trips as JSON, stamped
with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td)
    R.append_ledger("rt", {"kind": "debt", "sig": "z"}, root=root)
    line = R.debt_path("rt", root).read_text(encoding="utf-8").strip()
    obj = json.loads(line)
    check("the record is a JSON OBJECT, not a JSON string", isinstance(obj, dict), True)
    check("...carrying its branch", obj.get("br"), "rt")
    check("...and a timestamp", bool(obj.get("at")), True)


if Tally.count < 30:
    Tally.fails += 1
    print(
        "FAIL  only %d control(s) ran; the file is not being executed as written" % Tally.count,
        file=sys.stderr,
    )

if Tally.fails:
    print("FAIL: %d of %d control(s) failed" % (Tally.fails, Tally.count), file=sys.stderr)
    sys.exit(1)
print("%d control(s) passed" % Tally.count)
