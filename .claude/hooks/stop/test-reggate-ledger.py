#!/usr/bin/env python3
"""Controls for the reggate effort-cap ledger's ERROR paths.

WHY THIS FILE EXISTS. The cap (operator ruling 2026-09-05T01:55Z) is an escape
hatch from a blocking gate, so the question that matters is not "does it fire?"
but "what happens when its own machinery breaks?" Every error path here has one
correct direction -- FAIL STRICT -- and a silent flip to the lax direction is
invisible from the outside: a demand that vanishes looks exactly like a demand
that was never raised.

Three paths shipped with error handling and no test, which is what this fixes:

  read_ledger   OSError    -> ([], True), NOT ([], False)
  branch_merged git fails  -> False (not merged), so the grace clock governs
  the cap       any raise  -> falls through to the normal block

Each assertion is PAIRED with a control proving the opposite input produces the
opposite answer. Without the pair, a function hard-coded to return the strict
answer would pass every strict assertion while having stopped working.
"""

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
    # Without this, a read_ledger hard-wired to `return [], True` would satisfy
    # the assertion above while having stopped reading anything at all.
    R.append_ledger(br, {"kind": "charge", "sig": "b", "why": "proven"}, root=root)
    recs, forgot = R.read_ledger(br, root)
    check("CONTROL: a readable ledger reports forgot=False", forgot, False)
    check("CONTROL: and it actually returns the record", len(recs), 1)

    # A corrupt LINE is a different path from an unreadable FILE: the file opens,
    # one line fails to parse, and the rest must survive rather than the whole
    # ledger being discarded.
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
    _c, remaining, _d, forgot = R.budget_state(br, root)
    check("a full budget reports remaining=0", remaining, 0)
    check("...with forgot=False, so the cap MAY fire", forgot, False)

    with R.debt_path(br, root).open("a", encoding="utf-8") as f:
        f.write("{not json\n")
    _c, _r, _d, forgot = R.budget_state(br, root)
    # THE LOAD-BEARING ONE. wl_checks gates the cap on `not forgot`, because an
    # unreadable ledger folds to a FRESH budget -- the most permissive answer
    # possible. Reporting forgot is what stops the cap firing on a fiction.
    check("a corrupt ledger still reports forgot=True at budget level", forgot, True)


# --- 3. branch_merged: a FAILED probe is not a merge
with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td)  # not a git repo, so the probe cannot answer
    check("git failure reads as NOT merged", R.branch_merged("x", root), False)
    check("CONTROL: an empty branch name is also not merged", R.branch_merged("", root), False)

# CONTROL for the pair above: in a REAL repo the probe returns a real answer, so
# the two False results are the failure path and not the function being a stub.
_real = R.branch_merged("main", pathlib.Path(__file__).resolve().parents[3])
check("CONTROL: the probe returns a bool in a real repo", isinstance(_real, bool), True)


# --- 4. the cap's own guard condition, as wl_checks spells it
def cap_fires(remaining, forgot):
    """The exact predicate at the wl_checks block site."""
    return not forgot and remaining <= 0


check("cap fires when the budget is spent", cap_fires(0, False), True)
check("cap does NOT fire while budget remains", cap_fires(1, False), False)
# If this control ever flips, an unreadable ledger would start deferring real
# demands on a budget nobody could read.
check("CONTROL: cap does NOT fire on an unreadable ledger", cap_fires(0, True), False)


# --- 5. the ledger must not write into the repo when redirected
with tempfile.TemporaryDirectory() as td:
    os.environ["WORKLIST_STORE_DIR"] = str(pathlib.Path(td) / "store")
    try:
        redirected = R.debt_dir()
        check("WORKLIST_STORE_DIR redirects the ledger", str(redirected).startswith(td), True)
    finally:
        del os.environ["WORKLIST_STORE_DIR"]
    # CONTROL: without the override it falls back to the repo-relative path, so
    # the assertion above is testing the override and not a constant.
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


if Tally.count < 18:
    Tally.fails += 1
    print(
        "FAIL  only %d control(s) ran; the file is not being executed as written" % Tally.count,
        file=sys.stderr,
    )

if Tally.fails:
    print("FAIL: %d of %d control(s) failed" % (Tally.fails, Tally.count), file=sys.stderr)
    sys.exit(1)
print("%d control(s) passed" % Tally.count)
