#!/usr/bin/env python3
"""Controls for the plan-implementation gate: wl_planenforce, the investigation verb, and the two clauses that make it "investigate BEFORE implementing".

    python3 .claude/hooks/stop/test-planenforce.py

Discovered and run by `.claude/rediacc_hooks/tests/test_hooks_delegates.py`, whose TAILED glob picks up every `test-*.py` under this directory. That wiring is not optional and not assumed: `check:ci-test-file-orphans` exists because `test-teammate-idle.py` shipped with 20 controls and ran nowhere, passing 20/20 to whoever invoked it by hand and counting as coverage in review.

C1 THROUGH C10 ARE THE DESIGN'S OWN CONTROL LIST, and two of them are load-bearing in a way the others are not:

  C2 is the half that proves this is not a wall. A control file with only
     positive cases will happily flag the whole tree, so every "this must be
     refused" here is paired with a "this must be ACCEPTED" built from the same
     fixture with one thing changed.
  C6 is the single most important plant in the set, because Clause 2 is the
     only place the mechanism holds an opinion the session did not supply.
     Every other clause can be satisfied by finding any real pointer; that one
     compares two of the session's own claims against each other across a git
     revision, so a fabricated investigation contradicts the fabricated tick.
     It is therefore pinned from BOTH sides: the contradiction is refused, and
     the same `absent` row with a citation that genuinely did not exist at the
     recorded head is ACCEPTED.

THE FIXTURES ARE REAL GIT REPOSITORIES, not stubs, because the clauses are statements about git topology (`merge-base --is-ancestor`, `cat-file -e <commit>:<path>`) and a stubbed oracle would prove only that the stub was called.
"""

import ast
import atexit
import datetime as dt
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

# NO `sys.path` HOP, DELIBERATELY, AND IT IS NOT AN OVERSIGHT. Every sibling suite in this directory carries one and every one of them is frozen in `test_canonical_sys_path_hop.py`'s shrink-only baseline; adding a thirty-fourth is exactly what that baseline forbids. None is needed: this file is only ever invoked BY PATH -- by hand, and by `test_hooks_delegates.py`, which runs
# `[sys.executable, str(HOOKS / relative)]` -- and a path invocation puts the script's own directory on `sys.path[0]` before the first import runs. The modules beside it therefore import by name already.
import wl_checks as K
import wl_core as CORE
import wl_planenforce as E
import wl_planrec as R

# A PRIVATE TMPDIR FOR THE WHOLE RUN, removed at exit. The ledgers under test take a flock sidecar at `$TMPDIR/claude-worklist/.judge/<ledger>-<sha1 of the ledger path>.lock`, and every fixture here is a fresh random directory, so each run left new lock files in the machine-wide /tmp that nothing removed. The code under test reads TMPDIR at call time, so pointing it here keeps those sidecars, and every other temp directory this suite makes, inside one directory deleted at exit.
_PRIVATE_TMP = tempfile.mkdtemp(prefix="planenforce-suite-")
atexit.register(shutil.rmtree, _PRIVATE_TMP, ignore_errors=True)
os.environ["TMPDIR"] = _PRIVATE_TMP
tempfile.tempdir = _PRIVATE_TMP

HERE = pathlib.Path(__file__).resolve().parent

REPO = HERE.parent.parent.parent
GATE = REPO / ".ci" / "scripts" / "quality" / "check_plan_implementation.py"

ME = "d778be9d"


class Tally:
    fails = 0
    count = 0


def control(label, got, want):
    Tally.count += 1
    if got == want:
        print("  PASS  %s" % label)
    else:
        Tally.fails += 1
        print("  FAIL  %s: got %r, wanted %r" % (label, got, want), file=sys.stderr)


def truthy(label, got):
    Tally.count += 1
    if got:
        print("  PASS  %s" % label)
    else:
        Tally.fails += 1
        print("  FAIL  %s: got %r, wanted something truthy" % (label, got), file=sys.stderr)


def refused(label, fn, needle=""):
    """`fn` must raise RecordError, and its message must carry `needle`.

    THE NEEDLE IS NOT DECORATION. A refusal that fires for the wrong reason is indistinguishable from the right one at the exit code, and this whole design has five separate refusal paths on one verb: a plant that tripped the note-length floor instead of the pointer floor would look caught while the clause it targets never ran.
    """
    Tally.count += 1
    try:
        fn()
    except R.RecordError as exc:
        if needle and needle not in str(exc):
            Tally.fails += 1
            print(
                "  FAIL  %s: refused, but for the wrong reason: %s" % (label, exc), file=sys.stderr
            )
            return
        print("  PASS  %s" % label)
        return
    except Exception as exc:  # noqa: BLE001
        Tally.fails += 1
        print("  FAIL  %s: raised %r, wanted a RecordError" % (label, exc), file=sys.stderr)
        return
    Tally.fails += 1
    print("  FAIL  %s: was ACCEPTED, so the refusal path does not run" % label, file=sys.stderr)


def accepted(label, fn):
    """The other half of every pair. `fn` must NOT raise."""
    Tally.count += 1
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        Tally.fails += 1
        print("  FAIL  %s: refused with %s" % (label, exc), file=sys.stderr)
        return
    print("  PASS  %s" % label)


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )


PLAN_BODY = (
    """# PLAN: a fixture

Status: draft
Owner: %s
First-Seen: 2026-01-01

This paragraph exists only to carry the fixture past wl_planfid.MIN_PLAN_CHARS so
that the plan is read at all rather than discarded as too short to be a plan. It is
prose rather than bullets on purpose, so nothing in it can be mistaken for a task
and quietly change what these controls assert. The same padding convention is used
by test-planfile.py next door, and for the same reason: a fixture that silently
falls under a floor produces a clean run that means nothing at all.

## Tasks

- [ ] The first fixture task, long enough for the parser to keep it as a real box
- [ ] The second fixture task, also long enough for the parser to keep it
"""
    % ME
)


def make_tree(tmp):
    """A real git repository carrying one plan, one box ledger, one clock and one seed file.

    Returns (root, rel, sigs, c0). `c0` is the commit every `head` in these controls is recorded against, and `seed.txt` is a file that EXISTS at `c0` -- which is what makes C6's contradiction checkable and its negative control possible.
    """
    root = pathlib.Path(tmp)
    (root / "agent" / "plans").mkdir(parents=True)
    (root / "agent" / "ledgers").mkdir(parents=True)
    (root / ".ci" / "config").mkdir(parents=True)
    git(root, "init", "-q")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "user.name", "fixture")
    # `ci` reaches ONE key by `npm run`, so the other is a gate that exists and that nothing runs -- which is exactly the shape C7 plants.
    (root / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "ci": "npm run --silent check:ci-fixture-live",
                    "check:ci-fixture-live": "true",
                    "check:ci-fixture-orphan": "true",
                }
            }
        ),
        encoding="utf-8",
    )
    (root / "seed.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    rel = "agent/plans/PLAN-fixture.md"
    (root / rel).write_text(PLAN_BODY, encoding="utf-8")
    (root / ".ci" / "config" / "plan-implementation.json").write_text(
        json.dumps(
            {
                "baseline_open": 2,
                "baseline_at": "2026-01-01",
                "drain_per_day": 1,
                "warn_slack": 0,
                "floor_open": 0,
            }
        ),
        encoding="utf-8",
    )
    row = R.ledger_row(root, rel, PLAN_BODY)
    (root / R.LEDGER_REL).write_text(
        json.dumps({"plans": {rel: row}}, indent=2) + "\n", encoding="utf-8"
    )
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "fixture c0")
    c0 = git(root, "rev-parse", "HEAD").stdout.strip()
    sigs = [b[3] for b in R.open_boxes(PLAN_BODY)]
    return root, rel, sigs, c0


def inv(
    root,
    rel,
    sig,
    verdict,
    head,
    pointers,
    note="the fixture investigation note, written long enough to clear the forty-character floor",
):
    """Append one investigation row DIRECTLY, bypassing the verb's own validation.

    Deliberate: these rows are the INPUT to the clauses, and a plant that had to pass `plan_investigate` first could not express the two shapes the clauses exist to catch (a row whose head is later than the commit, a row whose negative claim is false).
    """
    return R.append_investigation(
        root,
        {
            "by": ME,
            "plan": rel,
            "sig": sig,
            "verdict": verdict,
            "head": head,
            "br": "fixture",
            "pointers": [list(p) for p in pointers],
            "resolved": [[p[0], True, "claimed"] for p in pointers],
            "note": note,
        },
    )


NOTE_OK = (
    "grepped the whole tree for the symbol and read the two call sites it has; "
    "the work is there and only the box was left open"
)


# --------------------------------------------------------------------------- 1. THE CLOCK (C8). Three points, because a clock asserted at one point is a constant that happens to hold today.


def clock_controls():
    print("1. the ceiling (C8)")
    clock = {
        "baseline_open": 100,
        "baseline_at": "2026-01-01",
        "drain_per_day": 7,
        "warn_slack": 20,
        "floor_open": 0,
    }
    control(
        "C8a: day 0's ceiling equals the baseline", E.ceiling(clock, dt.date(2026, 1, 1)), (100, 0)
    )
    control(
        "C8b: day 1's ceiling has dropped by drain_per_day",
        E.ceiling(clock, dt.date(2026, 1, 2)),
        (93, 1),
    )
    control(
        "C8c: the ceiling never goes under floor_open", E.ceiling(clock, dt.date(2027, 1, 1))[0], 0
    )
    control(
        "C8d: a landing date in the FUTURE is day 0, never negative slack",
        E.ceiling(clock, dt.date(2025, 12, 1)),
        (100, 0),
    )
    control(
        "C8e: at the baseline on day 0 the verdict is not a block",
        E.assess(clock, 100, 0, dt.date(2026, 1, 1))["state"] == E.BLOCK,
        False,
    )
    control(
        "C8f: at the baseline on day 1 with nothing closed, the verdict IS a block",
        E.assess(clock, 100, 0, dt.date(2026, 1, 2))["state"],
        E.BLOCK,
    )
    control(
        "C8g: on day 1 with exactly drain_per_day closed, the block is gone",
        E.assess(clock, 93, 0, dt.date(2026, 1, 2))["state"] == E.BLOCK,
        False,
    )
    control(
        "C8h: the block names the exact number of boxes that ends it",
        E.assess(clock, 100, 0, dt.date(2026, 1, 2))["gap"],
        7,
    )
    # THE WARN BAND, and its negative. A band that is never entered and never left is a constant in the other direction.
    control(
        "C8i: inside warn_slack of the ceiling the verdict is warn, not block",
        E.assess(clock, 88, 0, dt.date(2026, 1, 2))["state"],
        E.WARN,
    )
    control(
        "C8j: clear of the warn band the verdict is silent",
        E.assess(clock, 60, 0, dt.date(2026, 1, 2))["state"],
        E.SILENT,
    )
    # THE LIVE-PEER SUBTRACTION, both directions.
    control(
        "C8k: boxes owned by a LIVE peer are subtracted from the comparison",
        E.assess(clock, 100, 40, dt.date(2026, 1, 2))["state"],
        E.SILENT,
    )
    control(
        "C8k2: a partial subtraction lands in the warn band rather than jumping straight to silent",
        E.assess(clock, 100, 20, dt.date(2026, 1, 2))["state"],
        E.WARN,
    )
    control(
        "C8k3: the subtraction is stated as a number, not applied invisibly",
        E.assess(clock, 100, 40, dt.date(2026, 1, 2))["comparable"],
        60,
    )
    control(
        "C8l: with no live peer the same corpus blocks, so the subtraction is real",
        E.assess(clock, 100, 0, dt.date(2026, 1, 2))["state"],
        E.BLOCK,
    )
    # A MISSING CONFIG IS REPORTED, NEVER TREATED AS A DRAINED CORPUS.
    with tempfile.TemporaryDirectory() as tmp:
        _clock2, problem = E.load_clock(tmp)
        truthy("C8m: an absent clock config is a reported problem, not a silent default", problem)
    clock3, problem3 = E.load_clock(str(REPO))
    control("C8n: the real config parses with no problem", problem3, "")
    control(
        "C8o: the real config carries every key both halves read",
        sorted(k for k in E.CLOCK_KEYS if k in clock3),
        sorted(E.CLOCK_KEYS),
    )


# --------------------------------------------------------------------------- 2. THE INVESTIGATION VERB (C3, C4, C7), and its accepted half.


def verb_controls(root, rel, sigs, c0):
    print("2. the investigation verb (C3, C4, C7)")
    sig = sigs[0]

    def call(verdict, pointers, note=NOTE_OK):
        return lambda: R.plan_investigate(root, rel, sig, verdict, pointers, note, ME)

    accepted(
        "C3 CONTROL: two resolving pointers of two kinds are ACCEPTED",
        call("present", ["fileline:seed.txt:1", "commit:" + c0]),
    )
    refused(
        "C3: a commit pointer naming a plausible hex that is not an object is refused",
        call("present", ["fileline:seed.txt:1", "commit:deadbee1f"]),
        "do not resolve",
    )
    refused(
        "C3b: the refusal names WHICH kind failed",
        call("present", ["fileline:seed.txt:1", "commit:deadbee1f"]),
        "commit",
    )
    refused(
        "C3c: a fileline past the end of a real file is refused",
        call("present", ["fileline:seed.txt:9999", "commit:" + c0]),
        "do not resolve",
    )
    refused(
        "C4: two pointers of the SAME kind are refused",
        call("present", ["fileline:seed.txt:1", "fileline:seed.txt:2"]),
        "DISTINCT kinds",
    )
    refused(
        "C4b: one pointer is refused, whatever it resolves to",
        call("present", ["commit:" + c0]),
        "at least 2 are required",
    )
    refused(
        "a note under the 40-character floor is refused",
        call("present", ["fileline:seed.txt:1", "commit:" + c0], "done it, works"),
        "at least 40 are required",
    )
    refused(
        "a verdict outside the three is refused",
        call("finished", ["fileline:seed.txt:1", "commit:" + c0]),
        "not one of",
    )
    refused(
        "a pointer with no `<kind>:` prefix is refused",
        call("present", ["seed.txt:1", "commit:" + c0]),
        "is not `<kind>:<token>`",
    )
    refused(
        "a pointer naming a kind nothing can resolve is refused",
        call("present", ["vibes:seed.txt:1", "commit:" + c0]),
        "which nothing here can resolve",
    )
    accepted(
        "C7 CONTROL: a gate reachable from `npm run ci` is ACCEPTED",
        call("present", ["gate:check:ci-fixture-live", "fileline:seed.txt:1"]),
    )
    refused(
        "C7: a gate that exists in package.json but is NOT reachable from `npm run ci` is refused",
        call("present", ["gate:check:ci-fixture-orphan", "fileline:seed.txt:1"]),
        "NOT reachable from `npm run ci`",
    )
    refused(
        "an ambiguous box selector is refused rather than resolved by first match",
        lambda: R.plan_investigate(
            root,
            rel,
            "fixture task",
            "present",
            ["fileline:seed.txt:1", "commit:" + c0],
            NOTE_OK,
            ME,
        ),
        "matches 2 open boxes",
    )
    # THE ROW ITSELF: `head` must be the tree the claim is about, not a label.
    row, _resolved = R.plan_investigate(
        root, rel, sig, "absent", ["fileline:seed.txt:1", "commit:" + c0], NOTE_OK, ME
    )
    control("the row records HEAD at write time", row["head"], c0)
    control("the row records the box signature, not its text", row["sig"], sig)
    control("the row records the verdict verbatim", row["verdict"], "absent")
    truthy("the row records every pointer it resolved", len(row["resolved"]) == 2)


# --------------------------------------------------------------------------- 3. THE TICK (C1, C2, C5, C6). Every case here drives the real `plan_tick`.


def tick_controls():
    print("3. the tick, and the two clauses (C1, C2, C5, C6)")
    with tempfile.TemporaryDirectory() as tmp:
        root, rel, sigs, c0 = make_tree(tmp)
        sig = sigs[0]

        # C1 -- THE INVESTIGATION-LESS TICK. The evidence is 22 characters and clears BOTH the length floor and completion_evidence's EXIT_RE branch, so the refusal can only be the investigation clause.
        truthy(
            "C1 SETUP: the plant's evidence really does clear the old bar",
            K.completion_evidence(root, "exit 0, done, verified"),
        )
        refused(
            "C1: a tick with shape-only evidence and NO investigation row is refused",
            lambda: R.plan_tick(root, rel, sig, "exit 0, done, verified", ME),
            "no investigation row",
        )
        # T2 -- the two tick verbs had drifted, and the drift is closed. This is the plan's acceptance criterion 5.
        refused(
            "T2: `done it, works` is refused where --plan-tick accepted it before",
            lambda: R.plan_tick(root, rel, sig, "done it, works", ME),
            "carries nothing checkable",
        )

        # C2 -- THE GENUINELY INVESTIGATED TICK PASSES. Same fixture, one row added.
        inv(root, rel, sig, "present", c0, [("fileline", "seed.txt:1"), ("commit", c0)])
        accepted(
            "C2: a tick backed by a real investigation row is ACCEPTED",
            lambda: R.plan_tick(root, rel, sig, "landed at %s, see seed.txt:1" % c0, ME),
        )
        text, doc, _note = R.plan_tick(root, rel, sig, "landed at %s, see seed.txt:1" % c0, ME)
        truthy("C2b: the accepted tick really flips the box", text.count("- [x]") == 1)
        truthy(
            "C2c: the accepted tick writes an evidence line into the plan", "    (ticked) " in text
        )
        truthy(
            "C2d: the accepted tick moves the signature in the ledger",
            sig in doc["plans"][rel]["done_sigs"],
        )

        # C2e -- THE STOP-HOOK HALF IS SILENT ON THE SAME FIXTURE, at a ceiling that admits it.
        clock, _p = E.load_clock(root)
        control(
            "C2e: the hook half is silent on this fixture at its own baseline",
            E.assess(clock, 2, 0, dt.date(2026, 1, 1))["state"] == E.BLOCK,
            False,
        )
        control(
            "C1c: and it BLOCKS on the same fixture one day later with nothing closed",
            E.assess(clock, 2, 0, dt.date(2026, 1, 2))["state"],
            E.BLOCK,
        )


def clause_controls():
    print("4. Clause 1 and Clause 2 (C5, C6)")

    # C5 -- THE INVESTIGATION WRITTEN AFTER THE IMPLEMENTATION COMMIT.
    with tempfile.TemporaryDirectory() as tmp:
        root, rel, sigs, c0 = make_tree(tmp)
        sig = sigs[0]
        (root / "later.txt").write_text("added after c0\n", encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "fixture c1")
        c1 = git(root, "rev-parse", "HEAD").stdout.strip()
        truthy(
            "C5 SETUP: c1 really is a descendant of c0",
            R._git_ok(root, "merge-base", "--is-ancestor", c0, c1),
        )
        # The row's head is c1, and the tick cites c0. c0 cannot descend from a head recorded later.
        inv(root, rel, sig, "absent", c1, [("fileline", "seed.txt:1"), ("commit", c1)])
        refused(
            "C5: a row whose head POSTDATES the cited commit is refused by Clause 1",
            lambda: R.plan_tick(root, rel, sig, "implemented in %s, see seed.txt:1" % c0, ME),
            "CLAUSE 1",
        )
        accepted(
            "C5 CONTROL: the same row with a tick citing c1 is ACCEPTED",
            lambda: R.plan_tick(root, rel, sig, "implemented in commit %s" % c1, ME),
        )

    # C5b -- A `present` ROW CITING THE COMMIT THAT DID THE WORK. `present` means the work landed BEFORE the investigation, so that commit cannot descend from the row's head by construction; Clause 1 refusing it made every honest "search first" tick uncitable by sha (three writers, 2026-09-24).
    with tempfile.TemporaryDirectory() as tmp:
        root, rel, sigs, c0 = make_tree(tmp)
        sig = sigs[0]
        (root / "later.txt").write_text("added after c0\n", encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "fixture c1")
        c1 = git(root, "rev-parse", "HEAD").stdout.strip()
        inv(root, rel, sig, "present", c1, [("fileline", "seed.txt:1"), ("commit", c1)])
        accepted(
            "C5b: a PRESENT row citing the earlier commit that did the work is ACCEPTED",
            lambda: R.plan_tick(root, rel, sig, "landed in %s, see seed.txt:1" % c0, ME),
        )

    # C11 -- WHERE THE EVIDENCE LINE GOES. Inserting it at box+1 split a wrapped box from its own continuation (three writers, 2026-09-24); it belongs after the continuation, and never past the next box.
    wrapped = [
        "- [ ] Rename the thing and keep\n",
        "      its continuation attached.\n",
        "- [ ] The next box.\n",
    ]
    truthy(
        "C11: the evidence slot follows a wrapped box's continuation",
        R._evidence_slot(wrapped, 0) == 2,
    )
    truthy(
        "C11 CONTROL: an unwrapped box's slot is the next line",
        R._evidence_slot(["- [ ] One line.\n", "- [ ] Two.\n"], 0) == 1,
    )
    truthy(
        "C11 CONTROL: a blank line ends the box",
        R._evidence_slot(["- [ ] Box\n", "\n", "      not a continuation\n"], 0) == 1,
    )

    # C6 -- THE FALSIFIABLE NEGATIVE CLAIM. The most important plant in the set.
    with tempfile.TemporaryDirectory() as tmp:
        root, rel, sigs, c0 = make_tree(tmp)
        sig = sigs[0]
        (root / "later.txt").write_text("this file did NOT exist at c0\n", encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "fixture c1")
        c1 = git(root, "rev-parse", "HEAD").stdout.strip()
        truthy("C6 SETUP: seed.txt existed at c0", R._blob_lines_at(root, c0, "seed.txt") == 3)
        truthy(
            "C6 SETUP: later.txt did NOT exist at c0",
            R._blob_lines_at(root, c0, "later.txt") is None,
        )
        inv(root, rel, sig, "absent", c0, [("fileline", "seed.txt:1"), ("commit", c0)])
        refused(
            "C6: an `absent` row whose tick cites a file:line that ALREADY resolved at its own head is refused",
            lambda: R.plan_tick(root, rel, sig, "implemented it, see seed.txt:2 in %s" % c1, ME),
            "CLAUSE 2",
        )
        truthy(
            "C6b: the refusal offers the honest alternative rather than only accusing",
            "the real verdict was `present`"
            in _why(root, rel, sig, "implemented it, see seed.txt:2 in %s" % c1),
        )
        accepted(
            "C6 CONTROL: the SAME `absent` row is ACCEPTED when the tick cites a file that did not exist at that head",
            lambda: R.plan_tick(root, rel, sig, "implemented it, see later.txt:1 in %s" % c1, ME),
        )
        # C6d -- THE FIX THAT EDITS AN EXISTING LINE. The file existed at the head, but the cited line CHANGED after it, so the citation points at new work, not at something the investigation could have found (2026-09-24: an edit to an existing file was uncitable by file:line).
        seed = root / "seed.txt"
        rows = seed.read_text(encoding="utf-8").splitlines()
        rows[1] = rows[1] + " -- edited by the fix"
        seed.write_text("\n".join(rows) + "\n", encoding="utf-8")
        accepted(
            "C6d: an `absent` row is ACCEPTED when the cited line changed after its head",
            lambda: R.plan_tick(root, rel, sig, "implemented it, see seed.txt:2 in %s" % c1, ME),
        )
        # AND THE OTHER DIRECTION: a `present` row is never subject to Clause 2, or the clause would be a blanket ban on citing anything old.
        with tempfile.TemporaryDirectory() as tmp2:
            root2, rel2, sigs2, c02 = make_tree(tmp2)
            inv(
                root2, rel2, sigs2[0], "present", c02, [("fileline", "seed.txt:1"), ("commit", c02)]
            )
            accepted(
                "C6c CONTROL: a `present` row citing a file that existed at its head is ACCEPTED",
                lambda: R.plan_tick(
                    root2, rel2, sigs2[0], "already there at seed.txt:1, %s" % c02, ME
                ),
            )


def _why(root, rel, sig, evidence):
    try:
        R.plan_tick(root, rel, sig, evidence, ME)
    except R.RecordError as exc:
        return str(exc)
    return ""


# --------------------------------------------------------------------------- 5. THE NEIGHBOURS (C9). A new blocking module that silently promoted a neighbouring advisory would be the exact conflation the brief forbids.


def neighbour_controls():
    print("5. the neighbours stay advisory (C9)")
    src = (HERE / "wl_backlog.py").read_text(encoding="utf-8")
    control("C9a: wl_backlog still mentions no vadd anywhere in its source", "vadd(" in src, False)
    tree = ast.parse((HERE / "wl_planenforce.py").read_text(encoding="utf-8"))
    writes = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr in ("write_text", "write_atomic", "append_investigation", "unlink")
    ]
    control("C9b: wl_planenforce writes NOTHING; it only reads and renders", writes, [])
    control(
        "C9c: wl_planenforce never imports wl_checks, which imports it",
        "import wl_checks" in (HERE / "wl_planenforce.py").read_text(encoding="utf-8"),
        False,
    )
    checks = (HERE / "wl_checks.py").read_text(encoding="utf-8")
    truthy(
        "C9d: `plan-tasks` is still delivered by outq_add and never by vadd",
        'outq_add(worklist, session_id, state_doc, "plan-tasks"' in checks,
    )
    truthy(
        "C9e: `plan-backlog` is still delivered by outq_add and never by vadd",
        'outq_add(\n                worklist, session_id, state_doc, "plan-backlog:%s"' in checks
        or '"plan-backlog:%s"' in checks,
    )
    truthy(
        "C9f: the new key IS a vadd, and is on the ladder at T_MISSION",
        'vadd("plan-unimplemented"' in checks and K.check_tier("plan-unimplemented") == K.T_MISSION,
    )
    # C9h -- THE PEER-LIVENESS ORACLE IS wl_backlog's, CALLED, NOT A SECOND OPINION. Two mechanisms print a `--migrate --plan` recipe now; if they nominated different plans a session reading both would have to reconcile them, which is exactly the kind of avoidable work a block should not create.
    #
    # SYNTHETIC INPUTS, not the live tree. This case used to feed both calls `recs`/`boxes` read straight off `root`, which made C9h2's anti-vacuity SETUP a bet on the shared repo currently having some OTHER peer sitting idle on an open-boxed plan -- true by luck on 2026-09-08 when this was written, false on 2026-09-23 after a long session drained most of the backlog onto its
    # own name. `_dead_peer` takes `recs`/`boxes`/`plan_owner`/`events` as plain data, so the equivalence this control exists to prove (wl_planenforce calls wl_backlog rather than reimplementing it) needs no real plan file and no real worklist event: a fabricated idle owner proves the delegation exactly as well and never goes quiet because of what other sessions did meanwhile.
    import wl_backlog as BL  # noqa: PLC0415 -- read here, never imported by the module under test's own hot path

    root = str(REPO)
    dp_recs = [("agent/plans/PLAN-c9h-synthetic-dead-peer.md", "executing", 1)]
    dp_boxes = {"agent/plans/PLAN-c9h-synthetic-dead-peer.md": (2, None)}

    def dp_owner(_root, _rel):
        return "fakeded1"

    wl = CORE.worklist_for(CORE.project_start())
    dp_old_stamp = (CORE.utcnow() - dt.timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    dp_events = [{"by": "fakeded1", "at": dp_old_stamp, "h": "synthetic-host"}]
    direct = BL._dead_peer(root, dp_recs, dp_boxes, dp_owner, ME, wl, None, dp_events)
    through = E.dead_peer_recipe(root, dp_recs, dp_boxes, dp_owner, ME, wl, None, dp_events)
    control(
        "C9h: the block's idle-peer oracle IS wl_backlog._dead_peer, not a copy", through, direct
    )
    truthy(
        "C9h2 SETUP: the synthetic idle peer really lands, so the comparison above is not over None",
        direct is not None,
    )

    # THE TWO SUITES THAT PIN THE NEIGHBOURS, run rather than asserted about.
    for suite in ("test-planfile.py", "test-backlog.py"):
        done = subprocess.run(
            [sys.executable, str(HERE / suite)],
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        # THE TAIL IS PRINTED ON FAILURE, not just the exit code. These two suites read the REAL tree in places, so a peer session ticking a box mid-run can red them for a reason that has nothing to do with this change; a bare exit code sends the next reader to re-run it blind. Observed live on 2026-09-22 while another agent was draining boxes in this checkout.
        if done.returncode != 0:
            print(
                "        %s tail:\n%s" % (suite, (done.stdout + done.stderr)[-1200:]),
                file=sys.stderr,
            )
        control("C9g: %s still passes untouched" % suite, done.returncode, 0)


# --------------------------------------------------------------------------- 6. THE RECURSIVE CLAUSE (C10). The check of the check.


def wiring_controls():
    print("6. both halves read the same clock (C10)")
    truthy("C10 SETUP: the CI gate exists where the wiring says it does", GATE.is_file())
    src = GATE.read_text(encoding="utf-8")

    # READ FROM THE AST, NOT FROM A SUBSTRING. The first spelling of these two searched the gate's source for the literal `CLOCK_KEYS is not E.CLOCK_KEYS`, and renaming the import alias from `E` to `enforce` -- a change that alters nothing about the claim -- turned both controls red. A control that a rename can break is a control that a rename can also silently satisfy.
    def compares_identity(name):
        """True when the gate contains an `X is not <something>.name` comparison."""
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Compare) or not node.ops:
                continue
            if not isinstance(node.ops[0], ast.IsNot):
                continue
            left, right = node.left, node.comparators[0]
            if (
                isinstance(left, ast.Name)
                and left.id == name
                and isinstance(right, ast.Attribute)
                and right.attr == name
            ):
                return True
        return False

    truthy(
        "C10a: the CI gate reads wl_planenforce's OWN key tuple rather than a copy",
        compares_identity("CLOCK_KEYS"),
    )
    truthy(
        "C10b: the CI gate reads wl_planfile's OWN FINISHED_STATES rather than a copy",
        compares_identity("FINISHED_STATES"),
    )
    control(
        "C10b2 CONTROL: the AST probe answers False for a name the gate does not compare that way",
        compares_identity("MIN_PLANS"),
        False,
    )
    truthy(
        "C10c: the CI gate names the same config file", 'CONFIG_REL = "%s"' % E.CONFIG_REL in src
    )
    # NOT A WORD SEARCH. The gate's own docstring says it ships with no allowlist, so grepping for the WORD finds the sentence that promises its absence -- which would make this control fire on the documentation and go quiet if the documentation were deleted. What is searched for is a DATA STRUCTURE: a module-level binding whose name is one of the escape-hatch words.
    hatch = re.findall(
        r"(?mi)^(ALLOWLIST|ALLOW_LIST|EXEMPT|EXEMPTIONS|SUPPRESS\w*|BYPASS\w*|SKIP_\w+|IGNORE_\w+)\s*[:=]",
        src,
    )
    control("C10d: the CI gate defines no allowlist, exemption or bypass structure", hatch, [])
    truthy(
        "C10d2: and the control can see one -- the same pattern finds check_test_file_orphans' EXEMPT",
        re.findall(
            r"(?mi)^(ALLOWLIST|ALLOW_LIST|EXEMPT|EXEMPTIONS|SUPPRESS\w*|BYPASS\w*|SKIP_\w+|IGNORE_\w+)\s*[:=]",
            (GATE.parent / "check_test_file_orphans.py").read_text(encoding="utf-8"),
        ),
    )
    # DRIVEN, not read: the gate's own selftest must catch every plant it declares.
    done = subprocess.run(
        [sys.executable, str(GATE), "--selftest"],
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    control("C10e: the CI gate's own control pass exits 0", done.returncode, 0)
    truthy(
        "C10f: and it says so rather than passing silently",
        "control" in (done.stdout + done.stderr).lower(),
    )


def main():
    print("plan implementation enforcement: controls first, then any verdict")
    clock_controls()
    with tempfile.TemporaryDirectory() as tmp:
        root, rel, sigs, c0 = make_tree(tmp)
        verb_controls(root, rel, sigs, c0)
    tick_controls()
    clause_controls()
    neighbour_controls()
    wiring_controls()
    print("\n%d control(s) ran, %d failed" % (Tally.count, Tally.fails))
    return 1 if Tally.fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
