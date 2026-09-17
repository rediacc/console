#!/usr/bin/env python3
"""Controls for wl_planrec -- compacting a plan into an attested record.

    python3 .claude/hooks/stop/test-planrec.py

EVERY CASE IS A PAIR, the same discipline as test-planfile.py beside it: a
"this must be reported" is followed by a "this must be SILENT" built from the
same fixture with one thing changed. A suite with only positive cases cannot
tell a working matcher from one that returns the same answer for everything.

THE FIXTURE IS A REAL GIT REPOSITORY, with a real `refs/remotes/origin/main`, a
real ledger with TWO commits, and a real blob. Nothing here is mocked, and that
is not thoroughness for its own sake. Four of this module's rules are exactly
the kind that a stub satisfies while being broken against git:

    resolve(..., "ancestor")   `merge-base --is-ancestor` returns EMPTY output
                               on success, so `wl_core._git` -- which collapses
                               "failed" and "succeeded silently" into "" -- gets
                               it backwards. That is why wl_planrec carries its
                               own `_git_ok`, and why the control below asserts
                               both directions rather than only the true one.
    derive()'s blob            `git hash-object` answers before a commit exists.
    the ledger walk            `git show <sha>:<path>` at a commit whose ledger
                               DIFFERS from HEAD's is the whole point of `done=`,
                               and a one-commit fixture cannot express it.
    revive()                   round-tripping the exact original bytes.

THE ONE PROPERTY THIS FILE EXISTS FOR, if it must be reduced to one: a record's
`(record)` annotation lines must be INVISIBLE to `wl_planfid.plan_tasks`, and the
record must parse to exactly the same boxes as the plan it replaced. That is a
property of a parser this module does not own -- `BULLET_RE` requires a bullet
marker at indent 0-3 -- so it holds today by construction and could be lost by a
change made somewhere else for an unrelated reason. Pinned here so that change
fails loudly instead of quietly turning every compacted record into a source of
phantom boxes for check:ci-plan-boxes.
"""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import wl_checks as K  # noqa: E402
import wl_planfid as P  # noqa: E402
import wl_planfile as F  # noqa: E402
import wl_planrec as R  # noqa: E402


class Tally:
    fails = 0
    count = 0


def control(label, got, want):
    Tally.count += 1
    if got != want:
        Tally.fails += 1
        print("FAIL  %s: got %r, wanted %r" % (label, got, want), file=sys.stderr)


def truthy(label, got):
    Tally.count += 1
    if not got:
        Tally.fails += 1
        print("FAIL  %s: got %r, wanted something truthy" % (label, got), file=sys.stderr)


def falsy(label, got):
    Tally.count += 1
    if got:
        Tally.fails += 1
        print("FAIL  %s: got %r, wanted something falsy" % (label, got), file=sys.stderr)


def raises(label, fn, needle=""):
    Tally.count += 1
    try:
        fn()
    except R.RecordError as exc:
        if needle and needle not in str(exc):
            Tally.fails += 1
            print("FAIL  %s: refused, but not for %r: %s" % (label, needle, exc), file=sys.stderr)
        return
    except Exception as exc:  # noqa: BLE001
        Tally.fails += 1
        print("FAIL  %s: raised %r, wanted a RecordError" % (label, exc), file=sys.stderr)
        return
    Tally.fails += 1
    print("FAIL  %s: did not refuse" % label, file=sys.stderr)


# --------------------------------------------------------------------------- The fixture.

TASK_DONE = "Regenerate the secret reachability baseline with the org admin token"
TASK_OPEN = "Delete the old GitHub org secrets once every consumer reads the vault"
REL = "agent/PLAN-fixture.md"

# Padding is PROSE, never bullets, for the same reason test-planfile.py's is: a bullet in the padding would become a task and quietly change what every case below asserts. It is long because the size ratio is a real rule -- the blob must be at least BLOB_RATIO times the record -- and a fixture that cannot satisfy a rule is a fixture that proves nothing about it.
PAD = (
    "This paragraph exists so the plan is genuinely larger than the record it "
    "compacts into, which is the anti-vacuity half of the size rule.\n" * 200
)

PLAN = (
    "# A fixture plan\n"
    "Status: executing\n"
    "Owner: deadbeef\n"
    "\n"
    "## Problem\n"
    "Something was broken and this plan describes the fix.\n"
    "It cites .ci/config/plan-boxes.json:1 and the gate check:ci-plan-record.\n"
    "\n" + PAD + "\n"
    "## Tasks\n"
    "- [x] " + TASK_DONE + "\n"
    "- [ ] " + TASK_OPEN + "\n"
)


def sh(cwd, *args):
    subprocess.run(args, cwd=str(cwd), check=True, capture_output=True, text=True)


def git_out(cwd, *args):
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=False)
    return r.stdout.strip() if r.returncode == 0 else ""


def build(td):
    """(root, before_sha, after_sha). Two ledger commits: open, then ticked."""
    root = pathlib.Path(td) / "repo"
    (root / "agent").mkdir(parents=True)
    (root / ".ci" / "config").mkdir(parents=True)
    (root / "docs" / "agent-reference").mkdir(parents=True)
    sh(root, "git", "init", "-q", "-b", "main")
    sh(root, "git", "config", "user.email", "t@example.invalid")
    sh(root, "git", "config", "user.name", "t")

    (root / REL).write_text(PLAN, encoding="utf-8")
    (root / "package.json").write_text(
        json.dumps({"scripts": {"check:ci-plan-record": "x", "check:ci-plan-boxes": "y"}}),
        encoding="utf-8",
    )
    (root / "docs" / "agent-reference" / "TRAPS.md").write_text(
        "# Traps\n\n## A trap\nTrap-Id: a-real-trap-id\nEnforced-By: JUDGMENT-ONLY\n",
        encoding="utf-8",
    )

    def ledger(done_sigs):
        (root / R.LEDGER_REL).write_text(
            json.dumps(
                {
                    "plans": {
                        REL: {
                            "status": "executing",
                            "owner": "deadbeef",
                            "open": 1,
                            "done": len(done_sigs),
                            "open_sigs": [R.box_sig(TASK_OPEN)],
                            "done_sigs": list(done_sigs),
                        }
                    }
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    ledger([])
    sh(root, "git", "add", "-A")
    # A PR-TASK trailer, so derive() has a real epic to find rather than a hand-written list. The trailer grammar is scripts/gates/check-pr-task-trailers.ts's.
    sh(root, "git", "commit", "-qm", "fixture: the box is open\n\nPR-TASK: abc123def")
    before = git_out(root, "rev-parse", "HEAD")

    ledger([R.box_sig(TASK_DONE)])
    sh(root, "git", "add", "-A")
    sh(root, "git", "commit", "-qm", "fixture: the box is ticked")
    after = git_out(root, "rev-parse", "HEAD")
    sh(root, "git", "update-ref", "refs/remotes/origin/main", after)
    return root, before, after


TD = tempfile.TemporaryDirectory()
ROOT, BEFORE, AFTER = build(TD.name)
RECORD, NOTES = R.compact(ROOT, REL, "deadbeef", why="auto", park=True)
REC = R.parse(RECORD)

# --------------------------------------------------------------------------- 1. THE GRAMMAR. Parsed back out of the exact bytes that would go on disk. ---------------------------------------------------------------------------
truthy("the rendered record parses as a record", REC is not None)
control("no parse problems in a freshly built record", REC["problems"], [])
control("the fixture has one open box, so the status is `parked`", REC["status"], R.STATUS_PARKED)
control("the H1 is the plan's own heading, not its Status line", REC["title"], "A fixture plan")
control("the Owner is preserved verbatim", REC["owner"], "deadbeef")

# THE HEADER WINDOW. wl_checks reads the first PLAN_HEADER_LINES lines and nothing below it, so a record whose header fell past that line would be invisible to every status consumer in this repo while looking correct.
control("wl_planrec's header window matches wl_checks'", R.HEADER_LINES, K.PLAN_HEADER_LINES)
head = "\n".join(RECORD.splitlines()[: K.PLAN_HEADER_LINES])
truthy("Status is inside the header window", "Status: parked" in head)
truthy("Full-Text-Blob is inside the header window", "Full-Text-Blob:" in head)
truthy("Record-Sig is inside the header window", "Record-Sig:" in head)
# And through the REAL consumer, on disk, not by re-reading the regex here.
(ROOT / REL).write_text(RECORD, encoding="utf-8")
recs = {rel: st for rel, st, _n in K.plan_records(ROOT)}
control("wl_checks.plan_records reads the record's status", recs.get(REL), "parked")
(ROOT / REL).write_text(PLAN, encoding="utf-8")

# --------------------------------------------------------------------------- 2. THE ONE PROPERTY. `(record)` lines must be invisible to the real parser, and the record must parse to exactly the plan's boxes. ---------------------------------------------------------------------------
ann = "    (record) sig=deadbeef done=123456789"
falsy("BULLET_RE does not match a (record) line", P.BULLET_RE.match(ann))
falsy("CHECKBOX_RE does not match a (record) line", P.CHECKBOX_RE.match(ann))
falsy("wl_planfile's open-box regex does not match it", F.OPEN_BOX_LINE.match(ann))
falsy("wl_planfile's done-box regex does not match it", F.DONE_BOX_LINE.match(ann))
control("plan_tasks reads no task out of a (record) line", P.plan_tasks(ann), [])
# The CONTROL for that control: a line that IS a box must be seen, or the four assertions above would hold for a parser that sees nothing at all.
truthy("plan_tasks does read a real box line", bool(P.plan_tasks("- [x] " + TASK_DONE)))

control(
    "the record parses to the plan's OPEN boxes", F.plan_boxes(RECORD)[0], F.plan_boxes(PLAN)[0]
)
control(
    "the record parses to the plan's DONE boxes", F.plan_boxes(RECORD)[1], F.plan_boxes(PLAN)[1]
)
control("both boxes carry an attestation line", len(REC["boxes"]), 2)
truthy("the box lines survive byte-identical", all(b["line"] in PLAN for b in REC["boxes"]))

# The invariant is ENFORCED at construction, not merely observed. A record whose prose smuggled a checkbox in must be refused.
raises(
    "a record that gains a box from lifted prose is refused",
    lambda: R._assert_boxes_preserved(
        PLAN, RECORD + "\n## Extra\n- [ ] " + TASK_OPEN + " twice\n", REL
    ),
    "does not parse to the same boxes",
)
# ...and the same call over the real record must be SILENT.
control(
    "CONTROL: the real record passes the same invariant",
    R._assert_boxes_preserved(PLAN, RECORD, REL),
    None,
)

# `--why auto` lifts sections VERBATIM, and this tree's `## Status` sections routinely quote their own ticked boxes. Stripping them is what makes the invariant above satisfiable rather than a rule that reds on real input.
lifted = R._auto_prose("## Status\nprose here\n- [x] " + TASK_DONE + "\nmore prose\n")
falsy("_auto_prose strips checkbox lines out of lifted text", "- [x]" in lifted["Outcome"])
truthy("CONTROL: _auto_prose keeps the prose around them", "prose here" in lifted["Outcome"])

# ---------------------------------------------------------------------------
# 3. THE SIGNATURE. check_plan_boxes.py hashes the parser's own dedup key; this
# module restates that in four lines and the two must never drift. ---------------------------------------------------------------------------
sys.path.insert(0, str(HERE.parents[2] / ".ci" / "scripts" / "quality"))
try:
    import check_plan_boxes as CPB

    control("box_sig equals the gate's own sig()", R.box_sig(TASK_DONE), CPB.sig(TASK_DONE))
    control("...and for the open task too", R.box_sig(TASK_OPEN), CPB.sig(TASK_OPEN))
except ImportError as _exc:  # pragma: no cover
    Tally.fails += 1
    Tally.count += 1
    print("FAIL  could not import check_plan_boxes to compare sig(): %s" % _exc, file=sys.stderr)

control("Record-Sig in the file matches record_sig()", REC["record_sig"], R.record_sig(REC))
# The signature covers the SPINE and not the prose, in both directions.
prose_edit = R.parse(RECORD.replace("## Lessons\n", "## Lessons\n- a sharpened lesson\n", 1))
control("sharpening prose does not move the signature", R.record_sig(prose_edit), R.record_sig(REC))
spine_edit = R.parse(RECORD.replace("done=open", "done=abandoned", 1))
truthy(
    "changing a done= value DOES move the signature", R.record_sig(spine_edit) != R.record_sig(REC)
)
blob_edit = R.parse(RECORD.replace("Full-Text-Blob: " + REC["blob"], "Full-Text-Blob: " + "1" * 40))
truthy("changing the blob DOES move the signature", R.record_sig(blob_edit) != R.record_sig(REC))

# --------------------------------------------------------------------------- 4. resolve(), all eight kinds, both directions. ---------------------------------------------------------------------------
truthy("resolve blob: a real blob", R.resolve(ROOT, "blob", REC["blob"])[0])
falsy("resolve blob: forty zeros", R.resolve(ROOT, "blob", "0" * 40)[0])
falsy("resolve blob: a COMMIT is not a blob", R.resolve(ROOT, "blob", AFTER)[0])
tree = git_out(ROOT, "rev-parse", AFTER + "^{tree}")
truthy("resolve tree: a real tree", R.resolve(ROOT, "tree", tree)[0])
falsy("resolve tree: forty zeros", R.resolve(ROOT, "tree", "0" * 40)[0])
falsy("resolve tree: a BLOB is not a tree", R.resolve(ROOT, "tree", REC["blob"])[0])
truthy("resolve commit: a real commit", R.resolve(ROOT, "commit", AFTER)[0])
falsy("resolve commit: a made-up sha", R.resolve(ROOT, "commit", "0123456")[0])
truthy("resolve ancestor: a commit on origin/main", R.resolve(ROOT, "ancestor", BEFORE)[0])
sh(ROOT, "git", "checkout", "-q", "-b", "side")
sh(ROOT, "git", "commit", "-q", "--allow-empty", "-m", "only on a branch")
unlanded = git_out(ROOT, "rev-parse", "HEAD")
falsy("resolve ancestor: a commit NOT on origin/main", R.resolve(ROOT, "ancestor", unlanded)[0])
truthy("resolve fileline: a real path and line", R.resolve(ROOT, "fileline", "package.json:1")[0])
falsy("resolve fileline: a path that does not exist", R.resolve(ROOT, "fileline", "nope/x.py:1")[0])
falsy("resolve fileline: a line past the end", R.resolve(ROOT, "fileline", "package.json:9999")[0])
truthy(
    "resolve gate: a script package.json defines",
    R.resolve(ROOT, "gate", "check:ci-plan-record")[0],
)
falsy("resolve gate: a script it does not", R.resolve(ROOT, "gate", "check:ci-invented")[0])
truthy("resolve plan: a plan on disk", R.resolve(ROOT, "plan", REL)[0])
falsy("resolve plan: a plan that is not", R.resolve(ROOT, "plan", "agent/PLAN-nope.md")[0])
truthy("resolve trap: a Trap-Id in TRAPS.md", R.resolve(ROOT, "trap", "a-real-trap-id")[0])
falsy("resolve trap: an invented one", R.resolve(ROOT, "trap", "not-a-trap-id")[0])
Tally.count += 1
try:
    R.resolve(ROOT, "nonsense", "x")
    Tally.fails += 1
    print("FAIL  an unknown resolve kind must raise, not answer", file=sys.stderr)
except ValueError:
    pass

# --------------------------------------------------------------------------- 5. launder(). The model's prose is the only untrusted input this module takes. ---------------------------------------------------------------------------
clean, replaced = R.launder(ROOT, "see package.json:1 and check:ci-plan-record and %s" % AFTER)
control("launder leaves resolvable pointers alone", replaced, [])
control("...and does not rewrite the text", clean.count(R.UNRESOLVED), 0)
dirty, replaced = R.launder(
    ROOT,
    "see nope/x.py:1 and check:ci-invented and agent/PLAN-nope.md and deadbeefdeadbeef",
)
control("launder replaces all four unresolvable shapes", dirty.count(R.UNRESOLVED), 4)
control("...and reports each one", len(replaced), 4)
truthy("...naming the kind it failed", any(x.startswith("fileline:") for x in replaced))
# THE RUN-ID EXCEPTION, both directions. `[0-9a-f]{7,40}` also matches a CI run
# id, and a run id is the most citable fact a record can carry -- laundering one to defend against an all-digit git object would destroy real evidence to prevent a case that does not occur.
kept, rep2 = R.launder(ROOT, "job 100500447167 went red")
control("an all-digit token survives laundering", kept.count(R.UNRESOLVED), 0)
control("...and is not reported", rep2, [])
gone, _ = R.launder(ROOT, "the object deadbeefdeadbeef")
control(
    "CONTROL: a non-digit hex token of the same length does NOT survive",
    gone.count(R.UNRESOLVED),
    1,
)

# ---------------------------------------------------------------------------
# 6. derive(). The pointer, the epics, the gates, the paths, and done=.
# ---------------------------------------------------------------------------
sh(ROOT, "git", "checkout", "-q", "main")
d = R.derive(ROOT, REL)
control("derive reports no problems on a clean plan", d["problems"], [])
control(
    "the blob is git's own hash-object of the file",
    d["blob"],
    git_out(ROOT, "hash-object", "--", str(ROOT / REL)),
)
truthy("the blob resolves", R.resolve(ROOT, "blob", d["blob"])[0])
control("Full-Text names the commit that landed the text", d["commit"], R.sha9(BEFORE))
control("epics come from the PR-TASK trailers", d["epics"], ["abc123def"])
control("cited gates that resolve are recorded", d["gates"], ["check:ci-plan-record"])
truthy("cited paths that resolve are recorded", R.LEDGER_REL in d["touched"])
control(
    "one box attested, one open, none abandoned",
    (d["n_attested"], d["n_open"], d["n_abandoned"]),
    (1, 1, 0),
)
done_marks = {b["body"]: b["done"] for b in d["boxes"]}
control("the OPEN box records done=open", done_marks[TASK_OPEN], "open")
control("the DONE box names the FIRST attesting commit", done_marks[TASK_DONE], R.sha9(AFTER))
truthy(
    "...which is NOT the earlier commit whose ledger lacked it",
    done_marks[TASK_DONE] != R.sha9(BEFORE),
)

hist = R.ledger_history(ROOT)
control("the ledger walk sees both commits", len(hist), 2)
control("...oldest first", hist[0][0], BEFORE)
falsy(
    "the older ledger does not attest the tick",
    R.attested_at(hist[0][1], REL, R.box_sig(TASK_DONE)),
)
truthy("the newer ledger does", R.attested_at(hist[1][1], REL, R.box_sig(TASK_DONE)))
control(
    "done_commit finds the first attesting commit",
    R.done_commit(hist, REL, R.box_sig(TASK_DONE)),
    AFTER,
)
control("...and nothing for a signature nobody attests", R.done_commit(hist, REL, "deadbeef"), "")

# --------------------------------------------------------------------------- 7. compact(): every refusal, and the pair that proves it is not refusing everything. ---------------------------------------------------------------------------
raises(
    "compacting a plan with open boxes and no --park is refused",
    lambda: R.compact(ROOT, REL, "deadbeef", why="auto"),
    "A `compacted` status is in the FINISHED set",
)
truthy(
    "CONTROL: the same plan compacts under --park",
    bool(R.compact(ROOT, REL, "deadbeef", why="auto", park=True)[0]),
)

(ROOT / REL).write_text(PLAN + "\nan uncommitted line\n", encoding="utf-8")
raises(
    "compacting a DIRTY path is refused",
    lambda: R.compact(ROOT, REL, "deadbeef", why="auto", park=True),
    "uncommitted changes",
)
(ROOT / REL).write_text(PLAN, encoding="utf-8")
truthy(
    "CONTROL: once clean again it compacts",
    bool(R.compact(ROOT, REL, "deadbeef", why="auto", park=True)[0]),
)

(ROOT / REL).write_text(RECORD, encoding="utf-8")
sh(ROOT, "git", "add", "-A")
sh(ROOT, "git", "commit", "-qm", "the record lands")
raises(
    "compacting something that is already a record is refused",
    lambda: R.compact(ROOT, REL, "deadbeef", why="auto", park=True),
    "already a record",
)
# ORDER MATTERS HERE. A record just written by `--write` is BOTH a record and a
# dirty path; if the dirty branch won, the message would say "commit the path
# first", and doing that then compacts the RECORD -- pointing the new blob at the record instead of the plan. Pinned so the ordering cannot be shuffled back.
(ROOT / REL).write_text(RECORD + "\nan uncommitted trailing line\n", encoding="utf-8")
raises(
    "a record that is ALSO dirty still reports being a record, not being dirty",
    lambda: R.compact(ROOT, REL, "deadbeef", why="auto", park=True),
    "already a record",
)
(ROOT / REL).write_text(RECORD, encoding="utf-8")
raises(
    "an unknown --why source is refused",
    lambda: R.compact(ROOT, REL, "deadbeef", why="wishful", park=True),
    "--why must be one of",
)
raises(
    "compacting a path that does not exist is refused",
    lambda: R.compact(ROOT, "agent/PLAN-nope.md", "deadbeef"),
    "does not exist",
)

# --------------------------------------------------------------------------- 8. revive(): the round trip, which is the whole promise. ---------------------------------------------------------------------------
body, note = R.revive(ROOT, REL)
control("revive returns the plan's exact original bytes", body, PLAN)
truthy("...and says which blob it came from", REC["blob"][:12] in note)
R.write_atomic(ROOT / REL, body)
control("write_atomic put those bytes on disk", (ROOT / REL).read_text(encoding="utf-8"), PLAN)
# Committed, because that is what a real revive is followed by -- and because every case below compacts again, which refuses a dirty path by design.
sh(ROOT, "git", "add", "-A")
sh(ROOT, "git", "commit", "-qm", "the plan is live again")
raises(
    "reviving something that is not a record is refused",
    lambda: R.revive(ROOT, REL),
    "is not a record",
)
broken = RECORD.replace("Full-Text-Blob: " + REC["blob"], "Full-Text-Blob: " + "0" * 40)
(ROOT / REL).write_text(broken, encoding="utf-8")
raises(
    "reviving from a blob this clone does not have is refused, not guessed at",
    lambda: R.revive(ROOT, REL),
    "which this clone does not have",
)
(ROOT / REL).write_text(PLAN, encoding="utf-8")

# --------------------------------------------------------------------------- 9. Sizes, placeholders and the index. ---------------------------------------------------------------------------
truthy("the record is smaller than the plan", len(RECORD) < len(PLAN))
truthy(
    "...by at least the ratio the gate enforces",
    len(PLAN.encode()) >= len(RECORD.encode()) * R.BLOB_RATIO,
)
control(
    "the size budget grows per box", R.size_budget(2) - R.size_budget(0), 2 * R.RECORD_PER_BOX_BYTES
)
truthy("the record fits its own budget", len(RECORD.encode()) <= R.size_budget(len(REC["boxes"])))

authored, _n = R.compact(ROOT, REL, "deadbeef", why="author", park=True)
truthy("--why author leaves placeholders to fill", R.PLACEHOLDER_RE.search(authored) is not None)
falsy("--why auto fills them from the plan's own sections", R.PLACEHOLDER_RE.search(RECORD) is None)

control("render_index of nothing is the empty string", R.render_index([]), "")
rows = [
    ("agent/PLAN-b.md", "compacted", 3, 0, 0, "b" * 40),
    ("agent/PLAN-a.md", "parked", 1, 2, 0, "a" * 40),
]
idx = R.render_index(rows)
truthy(
    "the index sorts its rows, whatever order it is handed",
    idx.index("PLAN-a.md") < idx.index("PLAN-b.md"),
)
control("...and is a pure function of the set", idx, R.render_index(list(reversed(rows))))
truthy("the index carries the recovery recipe", "git log --find-object=" in idx)
truthy("...and counts both kinds", "1 compacted, 1 parked" in idx)

# --------------------------------------------------------------------------- 10. THE STATUS WIRING, asserted through the real consumers rather than by re-reading the frozensets. A word added to a set nothing consults is a word that changes nothing. ---------------------------------------------------------------------------
truthy("`compacted` is a FINISHED state", "compacted" in F.FINISHED_STATES)
truthy("`parked` is a NOT_STARTED state", "parked" in F.NOT_STARTED_STATES)
falsy("a compacted plan is out of the advisory's scope", F.in_scope_status("compacted"))
falsy("a parked plan is out of the advisory's scope too", F.in_scope_status("parked"))
truthy("`compacted` counts as done to plans_block", "compacted" in K.PLAN_DONE_STATES)
falsy("`parked` deliberately does NOT: its work is unfinished", "parked" in K.PLAN_DONE_STATES)
# The pair: an ordinary status must still be IN scope, or the four assertions above would hold for an in_scope_status that returned False for everything.
truthy("CONTROL: an ordinary status is still in scope", F.in_scope_status("executing"))
truthy("CONTROL: an unparseable status is still in scope", F.in_scope_status("UNKNOWN"))

# --------------------------------------------------------------------------- 10b. THE BYTE-EXACT ROUND TRIP, on a plan whose bytes a stripping reader would
#      damage. `wl_core._git` ends in .strip(); a revive built on it silently
# drops a trailing blank line, and the revived file then no longer hashes to the blob it came from -- which contradicts the single claim the whole design rests on. One plan in the real tree already ends that way. ---------------------------------------------------------------------------
EDGE = "agent/PLAN-edge.md"
EDGE_TEXT = (
    "# Edge\nStatus: executing\n\n## Why\nA reason.\n\n"
    + PAD
    + "\n## Tasks\n- [x] "
    + TASK_DONE
    + "\n\n"
)
(ROOT / EDGE).write_text(EDGE_TEXT, encoding="utf-8")
edge_ledger = json.loads((ROOT / R.LEDGER_REL).read_text(encoding="utf-8"))
edge_ledger["plans"][EDGE] = {
    "status": "executing",
    "owner": "unowned",
    "open": 0,
    "done": 1,
    "open_sigs": [],
    "done_sigs": [R.box_sig(TASK_DONE)],
}
(ROOT / R.LEDGER_REL).write_text(json.dumps(edge_ledger, indent=2) + "\n", encoding="utf-8")
sh(ROOT, "git", "add", "-A")
sh(ROOT, "git", "commit", "-qm", "a plan that ends with a blank line")
sh(ROOT, "git", "update-ref", "refs/remotes/origin/main", "HEAD")
truthy("the edge fixture really does end with a blank line", EDGE_TEXT.endswith("\n\n"))
edge_rec, _n = R.compact(ROOT, EDGE, "deadbeef", why="auto")
R.write_atomic(ROOT / EDGE, edge_rec)
edge_body, _note = R.revive(ROOT, EDGE)
control("revive returns the trailing blank line too", edge_body, EDGE_TEXT)
R.write_atomic(ROOT / EDGE, edge_body)
control(
    "...so the revived file still hashes to Full-Text-Blob",
    git_out(ROOT, "hash-object", "--", str(ROOT / EDGE)),
    R.parse(edge_rec)["blob"],
)

# --------------------------------------------------------------------------- 10c. THE OWNER LINE IS PRESERVED VERBATIM. Resolving it to a session id loses provenance on five of this repo's plans and CHANGES WHAT TWO OF THEM SAY. ---------------------------------------------------------------------------
OWN = "agent/PLAN-owned.md"
OWN_TEXT = PLAN.replace("Owner: deadbeef", "Owner: unowned (drafted by 9d92d9b6, 2026-08-28)")
(ROOT / OWN).write_text(OWN_TEXT, encoding="utf-8")
own_ledger = json.loads((ROOT / R.LEDGER_REL).read_text(encoding="utf-8"))
own_ledger["plans"][OWN] = {
    "status": "executing",
    "owner": "unowned",
    "open": 1,
    "done": 0,
    "open_sigs": [R.box_sig(TASK_OPEN)],
    "done_sigs": [],
}
(ROOT / R.LEDGER_REL).write_text(json.dumps(own_ledger, indent=2) + "\n", encoding="utf-8")
sh(ROOT, "git", "add", "-A")
sh(ROOT, "git", "commit", "-qm", "an unowned plan")
own_rec, _n = R.compact(ROOT, OWN, "deadbeef", why="auto", park=True)
control(
    "the record keeps the whole Owner sentence",
    R.parse(own_rec)["owner"],
    "unowned (drafted by 9d92d9b6, 2026-08-28)",
)
(ROOT / OWN).write_text(own_rec, encoding="utf-8")
control(
    "CONTROL: wl_checks.plan_owner still reads it as UNOWNED, as it did the plan",
    K.plan_owner(ROOT, OWN),
    None,
)
(ROOT / OWN).write_text(OWN_TEXT, encoding="utf-8")

# --------------------------------------------------------------------------- 10d. clip(): a line boundary AND a balanced fence. An odd fence makes plan_tasks treat ## Boxes as fenced, so the record parses to zero boxes and the compaction is refused while blaming the boxes. ---------------------------------------------------------------------------
FENCED = "prose line\n" * 3 + "```\ncode inside a fence\n```\n"
control("clip leaves short text alone", R.clip("abc", 100), "abc")
cut = R.clip(FENCED, 40)
control("clip cuts on a line boundary", cut.count("prose line"), 3)
control("clip re-balances an odd fence", cut.count("```") % 2, 0)
truthy("CONTROL: the raw slice really would have been odd", FENCED[:40].count("```") % 2 == 1)
control(
    "clip keeps at least the first line",
    R.clip("a very long single line here", 4),
    "a very long single line here",
)

# --------------------------------------------------------------------------- 10e. THE SIZE FLOOR AT WRITE TIME. Property 5 says size is bounded in BOTH
#      directions; only the ceiling was enforced until a control asked.
# ---------------------------------------------------------------------------
TINY = "agent/PLAN-tiny.md"
(ROOT / TINY).write_text("# T\nStatus: executing\n\n## Why\nsmall.\n", encoding="utf-8")
tiny_ledger = json.loads((ROOT / R.LEDGER_REL).read_text(encoding="utf-8"))
tiny_ledger["plans"][TINY] = {
    "status": "executing",
    "owner": "unowned",
    "open": 0,
    "done": 0,
    "open_sigs": [],
    "done_sigs": [],
}
(ROOT / R.LEDGER_REL).write_text(json.dumps(tiny_ledger, indent=2) + "\n", encoding="utf-8")
sh(ROOT, "git", "add", "-A")
sh(ROOT, "git", "commit", "-qm", "a plan too small to be worth compacting")
raises(
    "a plan smaller than the blob-ratio floor is refused at WRITE time",
    lambda: R.compact(ROOT, TINY, "deadbeef", why="auto"),
    "nothing would be compacted",
)
truthy(
    "CONTROL: the big fixture is comfortably over the same floor",
    bool(R.compact(ROOT, REL, "deadbeef", why="auto", park=True)[0]),
)

# --------------------------------------------------------------------------- 10f. A DROPPED BOX IS NAMED. plan_tasks discards a box whose normalised key is under 8 characters, so the line exists in the plan and in NEITHER list -- and _assert_boxes_preserved cannot see it, because it runs the same parser on both sides.
# ---------------------------------------------------------------------------
SHORT = "agent/PLAN-short.md"
(ROOT / SHORT).write_text(PLAN + "- [x] ok\n", encoding="utf-8")
short_ledger = json.loads((ROOT / R.LEDGER_REL).read_text(encoding="utf-8"))
short_ledger["plans"][SHORT] = {
    "status": "executing",
    "owner": "unowned",
    "open": 1,
    "done": 1,
    "open_sigs": [R.box_sig(TASK_OPEN)],
    "done_sigs": [R.box_sig(TASK_DONE)],
}
(ROOT / R.LEDGER_REL).write_text(json.dumps(short_ledger, indent=2) + "\n", encoding="utf-8")
sh(ROOT, "git", "add", "-A")
sh(ROOT, "git", "commit", "-qm", "a plan with an unparseable box")
_short_rec, short_notes = R.compact(ROOT, SHORT, "deadbeef", why="auto", park=True)
truthy(
    "a checkbox the parser drops is REPORTED, not silently left out",
    any("NOT in the record" in n for n in short_notes),
)
truthy(
    "CONTROL: the plan with no unparseable box says nothing of the kind",
    not any(
        "NOT in the record" in n for n in R.compact(ROOT, REL, "deadbeef", why="auto", park=True)[1]
    ),
)

# --------------------------------------------------------------------------- 10g. THE LISTINGS. `--plan-compact <me>` with no path is a READ, which is what the compaction wave starts with and what lets the identity suite drive these verbs without planting a git repository per verb. ---------------------------------------------------------------------------
recs_now = K.plan_records(ROOT)
cands = R.candidates(ROOT, recs_now)
by_rel = {c[0]: c for c in cands}
truthy("candidates lists the live plans", REL in by_rel)
control("...and says a parked-needing plan needs --park", "--park" in by_rel[REL][4], True)
(ROOT / OWN).write_text(own_rec, encoding="utf-8")
falsy(
    "...and never lists a record as a candidate",
    OWN in {c[0] for c in R.candidates(ROOT, K.plan_records(ROOT))},
)
recs_list = R.records(ROOT, K.plan_records(ROOT))
truthy("records lists the record", any(r[0] == OWN for r in recs_list))
truthy("...and says its blob resolves", all(r[3] for r in recs_list if r[0] == OWN))
(ROOT / OWN).write_text(OWN_TEXT, encoding="utf-8")

# --------------------------------------------------------------------------- 10h. `--why model` DEGRADES, and the trailer says so. The model arm is the one that can be unavailable in any environment, so the interesting case is the failure: it must fall back to `--why auto` and must NOT leave `Why-Source: model` behind. A record claiming a provenance it does not have is the same
# quiet lie the gate refuses on the reading side.
#
# NO NETWORK IS TOUCHED. `wl_judge.resolve_claude` is `shutil.which` with a `~/.local/bin/claude` fallback, so an empty PATH and an empty HOME make it unresolvable deterministically -- git is kept reachable by absolute path. ---------------------------------------------------------------------------
_gitdir = pathlib.Path(tempfile.mkdtemp())
_gitbin = _gitdir / "git"
_gitbin.symlink_to(shutil.which("git"))
_saved = (os.environ.get("PATH", ""), os.environ.get("HOME", ""))
os.environ["PATH"], os.environ["HOME"] = str(_gitdir), str(_gitdir)
try:
    model_rec, model_notes = R.compact(ROOT, REL, "deadbeef", why="model", park=True)
finally:
    os.environ["PATH"], os.environ["HOME"] = _saved
truthy(
    "an unavailable model degrades to --why auto instead of raising",
    any("falling back to --why auto" in n for n in model_notes),
)
control(
    "...and Why-Source records what actually wrote the prose",
    R.parse(model_rec)["trailer"].get("Why-Source"),
    "auto (--why model degraded)",
)
control(
    "CONTROL: --why auto records itself plainly",
    R.parse(RECORD)["trailer"].get("Why-Source"),
    "auto",
)
control("the degraded record is still a valid record", R.parse(model_rec)["problems"], [])

# --------------------------------------------------------------------------- 12. W12 P2.1 THE EDGE INDEX AND why_lines().
#
# THE THREE ANSWERS ARE THE POINT. "No record names this file" and "there is no index to read" are DIFFERENT results, and both are different from an empty list, which is what a caller reads as breakage. Each is pinned here
#     with its sibling, because a function that returned WHY_NO_EDGE for every
# input would look identical to a working one on a tree with no records. ---------------------------------------------------------------------------
(ROOT / REL).write_text(PLAN, encoding="utf-8")

_rows = [
    ("agent/PLAN-a.md", "compacted", 2, 0, 0, "a" * 40, (".ci/config/plan-boxes.json", "run.sh")),
    ("agent/PLAN-b.md", "parked", 1, 1, 0, "b" * 40, ("run.sh",)),
]
_edges = R.index_edges(_rows)
control(
    "index_edges maps a path to every record naming it",
    _edges.get("run.sh"),
    ["agent/PLAN-a.md", "agent/PLAN-b.md"],
)
control(
    "...and a path only one record names",
    _edges.get(".ci/config/plan-boxes.json"),
    ["agent/PLAN-a.md"],
)
control(
    "CONTROL: a SIX-element row (what check_plan_record.py hand-builds) contributes none",
    R.index_edges([("agent/PLAN-c.md", "compacted", 1, 0, 0, "c" * 40)]),
    {},
)
control("render_edges of nothing is the empty string", R.render_edges({}), "")
truthy("the rendered index carries the edge table", R.EDGE_SECTION in R.render_index(_rows))
falsy(
    "CONTROL: an index whose rows carry no edges carries no edge table",
    R.EDGE_SECTION in R.render_index([("agent/PLAN-c.md", "compacted", 1, 0, 0, "c" * 40)]),
)

# THE ROUND TRIP, which is the property the whole push rests on: what render_edges writes, why_index must read back. Two parsers over one markdown table is exactly the shape that drifts, so it is pinned rather than trusted.
R.write_atomic(ROOT / R.INDEX_REL, R.render_index(_rows))
control("why_index reads back exactly what render_edges wrote", R.why_index(ROOT), _edges)
falsy(
    "...and does NOT mistake the record table's own rows for edges",
    any(k.startswith("agent/PLAN-") for k in R.why_index(ROOT)),
)

# why_lines needs a record ON DISK to quote, so the fixture's record is written to its own path and indexed under a file it touches.
_why_rel = "agent/PLAN-why-fixture.md"
_why_rec = RECORD.replace(
    "## Why\n", "## Why\nBecause the ledger was the only second reading.\n", 1
)
(ROOT / _why_rel).write_text(_why_rec, encoding="utf-8")
R.write_atomic(
    ROOT / R.INDEX_REL,
    R.render_index([(_why_rel, "parked", 1, 1, 0, REC["blob"], ("run.sh",))]),
)
_lines, _state = R.why_lines(ROOT, "run.sh")
control("why_lines FIRES on an indexed path", _state, R.WHY_EDGES)
truthy("...naming the record", any(_why_rel in x for x in _lines))
truthy("...quoting its Why", any("only second reading" in x for x in _lines))
truthy("...and carrying the recovery command", any("git show" in x for x in _lines))
_lines2, _state2 = R.why_lines(ROOT, "no/such/path.ts")
control("CONTROL: an UNindexed path is no-edge, not a hit", _state2, R.WHY_NO_EDGE)
control("...and says nothing rather than guessing", _lines2, [])
(ROOT / R.INDEX_REL).unlink()
control(
    "CONTROL: no index at all is a THIRD answer, not the same as no edge",
    R.why_lines(ROOT, "run.sh")[1],
    R.WHY_NO_INDEX,
)

# An ABSOLUTE path must give the same answer as the repo-relative one. A lookup that missed on the prefix would answer "nothing is recorded" about a file that has a record, which is the one wrong answer this function must not produce.
R.write_atomic(
    ROOT / R.INDEX_REL,
    R.render_index([(_why_rel, "parked", 1, 1, 0, REC["blob"], ("run.sh",))]),
)
(ROOT / "run.sh").write_text("#!/bin/sh\n", encoding="utf-8")
control(
    "an absolute path resolves to the same edge as the relative one",
    R.why_lines(ROOT, str(ROOT / "run.sh"))[1],
    R.WHY_EDGES,
)

# --------------------------------------------------------------------------- 13. W12 P2.3 why_for_paths(): SILENT when nothing matches.
#
# The opposite rule to --plan-why's, deliberately. Both callers APPEND to a block that is already being emitted, so an empty answer must add nothing at all -- a sentence saying "no records" in the PostCompact briefing and in every red-CI block would be noise on every stop. ---------------------------------------------------------------------------
control("why_for_paths adds NOTHING when no path matches", R.why_for_paths(ROOT, ["nope.ts"]), "")
truthy("CONTROL: and does fire when one does", R.why_for_paths(ROOT, ["run.sh"]) != "")
truthy("...naming the record it found", _why_rel in R.why_for_paths(ROOT, ["run.sh"]))
(ROOT / R.INDEX_REL).unlink()
control("with no index at all it is silent too", R.why_for_paths(ROOT, ["run.sh"]), "")

# --------------------------------------------------------------------------- 14. W12 P2.5 --plan-tick.
#
# THE INVARIANT UNDER TEST is the same one compaction has: the evidence line must be INVISIBLE to wl_planfid.plan_tasks, and the box's own signature must not move. A moved signature is what check_plan_boxes.py's A1 reports as a box that VANISHED, so a tick that re-worded its box would look exactly like the abuse that gate exists to catch.
# ---------------------------------------------------------------------------
(ROOT / REL).write_text(PLAN, encoding="utf-8")
_sig_open = R.box_sig(TASK_OPEN)
_before_tasks = P.plan_tasks(PLAN)
_ticked, _doc, _note = R.plan_tick(
    ROOT, REL, _sig_open, "verified by .ci/config/plan-boxes.json:1", "deadbeef"
)

control("the tick moves exactly one box from open to done", F.plan_boxes(_ticked)[0], [])
control("...and both tasks are still done", sorted(F.plan_boxes(_ticked)[1]), sorted(_before_tasks))
control(
    "THE INVARIANT: the parser resolves the SAME task set after the tick",
    sorted(P.plan_tasks(_ticked)),
    sorted(_before_tasks),
)
control(
    "...so the box signature has not moved",
    R.box_sig(next(t for t in P.plan_tasks(_ticked) if t == TASK_OPEN)),
    _sig_open,
)
truthy("the evidence is written into the plan", "plan-boxes.json:1" in _ticked)
truthy(
    "...on a line the record grammar also uses four spaces for",
    any(R.TICK_LINE_RE.match(ln) for ln in _ticked.splitlines()),
)
falsy(
    "CONTROL: and that line is not a bullet at any indent BULLET_RE accepts",
    any(P.BULLET_RE.match(ln) for ln in _ticked.splitlines() if R.TICK_LINE_RE.match(ln)),
)
truthy(
    "the ledger row now attests the ticked signature", _sig_open in _doc["plans"][REL]["done_sigs"]
)
falsy("...and no longer lists it as open", _sig_open in _doc["plans"][REL]["open_sigs"])
control(
    "...with the counts to match", (_doc["plans"][REL]["open"], _doc["plans"][REL]["done"]), (0, 2)
)

# THE RESTATEMENT CONTROL. ledger_row is check_plan_boxes.scan restated, not imported, so the two are asserted equal here -- which is the only thing that keeps the restatement from drifting into a second opinion.
sys.path.insert(0, str(HERE.parents[2] / ".ci" / "scripts" / "quality"))
try:
    import importlib.util as _ilu

    _spec = _ilu.spec_from_file_location(
        "_cpb", HERE.parents[2] / ".ci" / "scripts" / "quality" / "check_plan_boxes.py"
    )
    _cpb = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_cpb)
    (ROOT / REL).write_text(_ticked, encoding="utf-8")
    control(
        "ledger_row is byte-for-byte what check_plan_boxes.scan writes",
        R.ledger_row(ROOT, REL, _ticked),
        _cpb.scan(ROOT)[REL],
    )
except Exception as _exc:  # noqa: BLE001
    truthy("the gate's own scan() could be loaded for the equality control: %r" % _exc, False)
(ROOT / REL).write_text(PLAN, encoding="utf-8")

raises(
    "an empty evidence string is refused",
    lambda: R.plan_tick(ROOT, REL, _sig_open, "", "deadbeef"),
    "evidence is mandatory",
)
raises(
    "...and so is a token one",
    lambda: R.plan_tick(ROOT, REL, _sig_open, "done", "deadbeef"),
    "evidence is mandatory",
)
raises(
    "a selector matching no open box is refused, and lists the open ones",
    lambda: R.plan_tick(ROOT, REL, "zzzzzzzz", "cited .ci/config/plan-boxes.json:1", "deadbeef"),
    "no OPEN box matches",
)
# AMBIGUITY NEEDS ITS OWN FIXTURE, and the first version of this control did not have one: it passed against the "no OPEN box matches" refusal, whose message also contains the word "matches". A control that can be satisfied by the wrong refusal proves nothing about the right one.
_amb = "agent/PLAN-ambiguous.md"
(ROOT / _amb).write_text(
    "# Ambiguous\nStatus: executing\nOwner: deadbeef\n\n## Tasks\n"
    "- [ ] rotate the account signing key in the eu region\n"
    "- [ ] rotate the account signing key in the us region\n",
    encoding="utf-8",
)
raises(
    "an AMBIGUOUS selector is refused rather than resolved by picking the first",
    lambda: R.plan_tick(ROOT, _amb, "rotate the account signing key", "cited package.json:1", "d"),
    "matches 2 open boxes",
)
control(
    "CONTROL: the same fixture, disambiguated, selects exactly one",
    R.select_box(R.open_boxes((ROOT / _amb).read_text()), "eu region")[2],
    "rotate the account signing key in the eu region",
)
raises(
    "a plan with NO open boxes says so rather than reporting no match",
    lambda: R.plan_tick(ROOT, "agent/PLAN-noopen.md", "x", "cited package.json:1", "deadbeef"),
    "does not exist",
)
(ROOT / "agent" / "PLAN-noopen.md").write_text(
    "# No open\nStatus: executing\n\n## Tasks\n- [x] a finished task long enough to count\n",
    encoding="utf-8",
)
raises(
    "...and the same on a plan whose boxes are all ticked",
    lambda: R.plan_tick(ROOT, "agent/PLAN-noopen.md", "x", "cited package.json:1", "deadbeef"),
    "no open boxes to tick",
)
(ROOT / "agent" / "PLAN-noopen.md").unlink()
(ROOT / _amb).unlink()
# A RECORD cannot be ticked in place, and the refusal has to explain why rather
# than merely refuse: its `done=` could name neither a commit that does not exist
# yet nor `abandoned` that the ledger would immediately disprove.
_rec_path = "agent/PLAN-record-fixture.md"
(ROOT / _rec_path).write_text(RECORD, encoding="utf-8")
raises(
    "a compacted record refuses the tick and hands over the revive sequence",
    lambda: R.plan_tick(ROOT, _rec_path, "a", "cited .ci/config/plan-boxes.json:1", "deadbeef"),
    "--plan-revive",
)
(ROOT / _rec_path).unlink()

# tickable(): the listing the write mode's caller needs to get a signature from.
_tk = dict(R.tickable(ROOT, K.plan_records(ROOT)))
truthy(
    "tickable lists the fixture plan's open box", any(b[3] == _sig_open for b in _tk.get(REL, []))
)
(ROOT / "agent" / "PLAN-rec2.md").write_text(RECORD, encoding="utf-8")
falsy(
    "CONTROL: and EXCLUDES a record, whose boxes it cannot flip",
    "agent/PLAN-rec2.md" in dict(R.tickable(ROOT, K.plan_records(ROOT))),
)
(ROOT / "agent" / "PLAN-rec2.md").unlink()

# --------------------------------------------------------------------------- 14b. dirty_paths() and the .strip() that ate the first character.
#
# REGRESSION CONTROL, and the defect was live. Porcelain format is two status characters, a space, then the path, and for an UNSTAGED modification the first character is a space. `wl_core._git` ends in `.strip()`, so the first line of output lost that space and `ln[3:]` returned a truncated path -- `un.sh` for `run.sh`. `candidates()` compares plan paths against this set to print
# "REFUSED: uncommitted changes", so a dirty plan on the FIRST line of git status was listed as ready, which is the opposite of the truth about the one thing that listing exists to say.
#
# Both directions: the modified path is IN the set, and a clean one is NOT. ---------------------------------------------------------------------------
(ROOT / REL).write_text(PLAN + "\nan uncommitted line\n", encoding="utf-8")
_dirty = R.dirty_paths(ROOT, ".")
truthy("dirty_paths reports a modified path by its FULL name", REL in _dirty)
falsy("...not truncated by one character", any(d.endswith(REL[1:]) and d != REL for d in _dirty))
_cands = {c[0]: c[4] for c in R.candidates(ROOT, K.plan_records(ROOT))}
truthy(
    "...so candidates() calls it out rather than offering it", "uncommitted" in _cands.get(REL, "")
)
# Restoring the committed bytes IS the clean state -- no commit needed, and attempting one fails with "nothing to commit", which is the proof.
(ROOT / REL).write_text(PLAN, encoding="utf-8")
falsy("CONTROL: a CLEAN path is not in the set", REL in R.dirty_paths(ROOT, "."))
_cands = {c[0]: c[4] for c in R.candidates(ROOT, K.plan_records(ROOT))}
truthy("...and candidates() offers it again", "uncommitted" not in _cands.get(REL, "ready"))

# --------------------------------------------------------------------------- 15. W12 P2.6 Pointer stamps, in BOTH directions.
#
# `git hash-object` STORES NOTHING without -w, so an id over uncommitted bytes is not a promise of recovery. The stamp must say which case it is in, because a stamp that always printed `git show` would advertise a recovery command that returns nothing -- the exact failure the record gate exists to refuse, one layer down.
# ---------------------------------------------------------------------------
(ROOT / REL).write_text(PLAN, encoding="utf-8")
_blob, _ok, _sent = R.pointer_stamp(ROOT, REL)
truthy("a COMMITTED path stamps a blob that resolves", _ok)
truthy("...and says so with the recovery command", "git show" in _sent)
control(
    "...and the blob is the one git itself computes",
    _blob,
    git_out(ROOT, "hash-object", "--", str(ROOT / REL)),
)
(ROOT / REL).write_text(PLAN + "\nan uncommitted line\n", encoding="utf-8")
_blob2, _ok2, _sent2 = R.pointer_stamp(ROOT, REL)
falsy("CONTROL: an UNCOMMITTED path stamps an id that does not resolve", _ok2)
truthy(
    "...and says the bytes are not in git rather than offering git show", "NOT in this" in _sent2
)
falsy("...and does not offer a recovery command it cannot honour", "git show" in _sent2)
(ROOT / REL).write_text(PLAN, encoding="utf-8")

# --------------------------------------------------------------------------- 16. W12 P2.2 why-on-edit.py, driven as the real hook with real payloads.
#
# BOTH DIRECTIONS PER RULE. A guard that only ever blocks is a guard nobody can work under, and one that never blocks is one nothing proves. ---------------------------------------------------------------------------
HOOK = HERE.parent / "why-on-edit.py"


def hook(payload, cwd):
    r = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(cwd), CTX_BAND_STATE_DIR=str(cwd / ".ctx")),
    )
    return r.returncode, r.stdout, r.stderr


truthy("the hook file exists where settings.json will name it", HOOK.is_file())
_rc, _o, _e = hook({"tool_name": "Bash", "tool_input": {"command": "ls"}}, ROOT)
control("a non-edit tool is ignored entirely", (_rc, _o, _e), (0, "", ""))

# The BLOCK: a new plan whose slug is a subset of an existing one.
(ROOT / "agent" / "PLAN-secret-migration.md").write_text(PLAN, encoding="utf-8")
_rc, _o, _e = hook(
    {
        "tool_name": "Write",
        "session_id": "deadbeef",
        "tool_input": {"file_path": str(ROOT / "agent" / "PLAN-secret-migration-2.md")},
    },
    ROOT,
)
control("a NEW near-duplicate plan is refused", _rc, 2)
truthy("...naming the neighbour it duplicates", "PLAN-secret-migration.md" in _e)
truthy("...and offering --plan-why rather than only saying no", "--plan-why" in _e)

# CONTROL 1: the same slug, but the file already EXISTS. Editing a plan is the normal thing to do and must never be refused.
(ROOT / "agent" / "PLAN-secret-migration-2.md").write_text(PLAN, encoding="utf-8")
_rc, _o, _e = hook(
    {
        "tool_name": "Write",
        "session_id": "deadbeef",
        "tool_input": {"file_path": str(ROOT / "agent" / "PLAN-secret-migration-2.md")},
    },
    ROOT,
)
control("CONTROL: a Write over an EXISTING plan is allowed", _rc, 0)
(ROOT / "agent" / "PLAN-secret-migration-2.md").unlink()

# CONTROL 2: a genuinely different subject sharing one word.
_rc, _o, _e = hook(
    {
        "tool_name": "Write",
        "session_id": "deadbeef",
        "tool_input": {"file_path": str(ROOT / "agent" / "PLAN-secret-rotation-cadence.md")},
    },
    ROOT,
)
control("CONTROL: one shared word out of three is NOT a duplicate", _rc, 0)
(ROOT / "agent" / "PLAN-secret-migration.md").unlink()

# The PUSH, and its silence. No index -> nothing at all on stdout.
_rc, _o, _e = hook(
    {
        "tool_name": "Edit",
        "session_id": "quiet001",
        "tool_input": {"file_path": str(ROOT / "run.sh")},
    },
    ROOT,
)
control("with no index the push is SILENT, not an empty announcement", (_rc, _o.strip()), (0, ""))

R.write_atomic(
    ROOT / R.INDEX_REL,
    R.render_index([(_why_rel, "parked", 1, 1, 0, REC["blob"], ("run.sh",))]),
)
_rc, _o, _e = hook(
    {
        "tool_name": "Edit",
        "session_id": "push0001",
        "tool_input": {"file_path": str(ROOT / "run.sh")},
    },
    ROOT,
)
control("CONTROL: with an edge it speaks", _rc, 0)
truthy("...through additionalContext rather than stderr", "additionalContext" in _o)
truthy("...naming the record", _why_rel in _o)
# ONCE PER PATH PER EPOCH: the same file again in the same epoch is silent.
_rc2, _o2, _e2 = hook(
    {
        "tool_name": "Edit",
        "session_id": "push0001",
        "tool_input": {"file_path": str(ROOT / "run.sh")},
    },
    ROOT,
)
control("the SECOND edit of the same path in one epoch is silent", _o2.strip(), "")
# And a different session (a different epoch ledger) speaks again, which is what proves the silence above was the once-per-epoch rule and not a broken lookup.
_rc3, _o3, _e3 = hook(
    {
        "tool_name": "Edit",
        "session_id": "push0002",
        "tool_input": {"file_path": str(ROOT / "run.sh")},
    },
    ROOT,
)
truthy("CONTROL: a different session speaks again", "additionalContext" in _o3)
(ROOT / R.INDEX_REL).unlink()

# --------------------------------------------------------------------------- 11. THE CONTROL FOR THE CONTROLS. ---------------------------------------------------------------------------
control("the fixture plan really does parse as two tasks", len(P.plan_tasks(PLAN)), 2)
falsy("a plain plan is not a record", R.is_record(PLAN))
truthy("the rendered record IS one", R.is_record(RECORD))
control("parse() returns None for a plain plan rather than a blank record", R.parse(PLAN), None)

if Tally.count < 185:
    Tally.fails += 1
    print(
        "FAIL  only %d control(s) ran; the file is not being executed as written" % Tally.count,
        file=sys.stderr,
    )

TD.cleanup()
if Tally.fails:
    print("FAIL: %d of %d control(s) failed" % (Tally.fails, Tally.count), file=sys.stderr)
    sys.exit(1)
print("%d control(s) passed" % Tally.count)
