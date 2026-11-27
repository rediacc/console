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

import contextlib
import datetime
import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import wl_core as C
import wl_epic as E
import wl_reggate as R
import wl_store as S
import worklist_messages as M


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


# --- 7. materialization (D3): a due debt becomes ONE worklist item, once, routed to the right epic
@contextlib.contextmanager
def scratch_store(td):
    """Point the store, the epics and the ledgers at `td` (WORKLIST_STORE_DIR also turns the checkout journal off), and restore the environment after."""
    prev = os.environ.get("WORKLIST_STORE_DIR")
    os.environ["WORKLIST_STORE_DIR"] = str(pathlib.Path(td) / "store")
    (pathlib.Path(td) / "store").mkdir()
    try:
        yield pathlib.Path(td) / "wl.md"
    finally:
        if prev is None:
            del os.environ["WORKLIST_STORE_DIR"]
        else:
            os.environ["WORKLIST_STORE_DIR"] = prev


def stamp(minutes_ago):
    return (C.utcnow() - datetime.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def debt_items(worklist):
    return [r for r in S.load(worklist, sync=False).items if "reggate-debt:" in r.get("text", "")]


def debt(branch, sig, blind, minutes_ago, root, **extra):
    rec = {"kind": "debt", "sig": sig, "blind_spot": blind, "at": stamp(minutes_ago)}
    rec.update(extra)
    R.append_ledger(branch, rec, root=root)


BLIND = "the stop hook never refuses a lease whose worker id is a placeholder"
PR_PLAN = "agent/plans/PLAN-live-pr.md"
OLD = R.REGGATE_DEBT_GRACE_MIN + 5
with tempfile.TemporaryDirectory() as td, scratch_store(td) as wl:
    root = pathlib.Path(td)
    debt("1104-1", "aaaa1111bbbb", BLIND, 5, root, surface="hooks", artifact="x/test.py")
    debt("1121-1", "cccc2222dddd", "a fresh live-branch debt", 5, root)
    debt("1121-1", "eeee3333ffff", "a live-branch debt past its grace", OLD, root)
    pr_epic = E.new_epic("abcd1234", "the live PR", plan=PR_PLAN)
    made = dict(R.materialize(root, wl, "abcd1234", "1121-1", (PR_PLAN,)))
    check(
        "two due debts materialize, the fresh live one does not",
        sorted(made),
        ["aaaa1111bbbb", "eeee3333ffff"],
    )
    texts = {r["id"]: r.get("text", "") for r in debt_items(wl)}
    first = texts.get(made.get("aaaa1111bbbb"), "")
    check("C4: the blind spot returns VERBATIM in the item text", BLIND in first, True)
    check(
        "...tagged with the debt's sig8 and the session",
        "reggate-debt:aaaa1111 (abcd1234)" in first,
        True,
    )
    again = R.materialize(root, wl, "abcd1234", "1121-1", (PR_PLAN,))
    check("materialize runs once: a second stop adds nothing", again, [])
    check("...and the store still holds exactly two debt items", len(debt_items(wl)), 2)
    epics = E.load_epics()
    backlog = R.backlog_epic("abcd1234")
    check(
        "a non-live-branch debt lands in the backlog epic",
        made["aaaa1111bbbb"] in epics[backlog]["covers"],
        True,
    )
    check("the backlog epic carries this plan", epics[backlog].get("plan"), R.BACKLOG_PLAN)
    check(
        "a live-branch debt lands in the PR plan's epic",
        made["eeee3333ffff"] in epics[pr_epic]["covers"],
        True,
    )
    check(
        "CONTROL: the non-live one is NOT in the PR plan's epic",
        made["aaaa1111bbbb"] in epics[pr_epic]["covers"],
        False,
    )

# CONTROL: off the loop (no PR plan) a live-branch debt falls back to the backlog epic rather than to no epic at all.
with tempfile.TemporaryDirectory() as td, scratch_store(td) as wl:
    root = pathlib.Path(td)
    debt("1121-1", "9999aaaa0000", "an old live-branch debt", OLD, root)
    made = dict(R.materialize(root, wl, "abcd1234", "1121-1", ()))
    covers = E.load_epics()[R.backlog_epic("abcd1234")]["covers"]
    check(
        "CONTROL: with no PR plan the live debt joins the backlog epic",
        made.get("9999aaaa0000") in covers,
        True,
    )
    open_n, legacy_n, oldest = R.debt_status(root, legacy={"9999aaaa0000"})
    check("the status counts the unpaid debt and its legacy membership", (open_n, legacy_n), (1, 1))
    check(
        "REGGATE_DEBT_STATUS renders one line",
        M.REGGATE_DEBT_STATUS % (open_n, legacy_n, oldest),
        "REGGATE DEBT: 1 open (1 legacy), oldest %s" % oldest,
    )


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
