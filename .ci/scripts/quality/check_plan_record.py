#!/usr/bin/env python3
"""check:ci-plan-record -- a compacted plan must PROVE what it claims.

WHY THIS GATE EXISTS. `wl_planrec.py` lets a finished `agent/PLAN-*.md` shrink
into a record that keeps its own path, so the 2,539 existing citations of those
paths still resolve and the housekeeping clock stops demanding a deletion the
operator forbids. That trade only works if the record's pointers are real. A
record whose blob does not exist is strictly WORSE than the deleted plan it
replaced: the plan at least announced its own absence, while a record announces
a recovery command that silently returns nothing.

So every claim a record makes is re-derived here from git and from the committed
box ledger, and none of it is believed.

WHAT IS ASSERTED, one rule per planted control in `--selftest`:

  R1  POINTER RESOLUTION. `Full-Text-Blob:` names a real blob. When the optional
      `Full-Text: <sha9> <path>` half is present its sha is a real commit, is an
      ANCESTOR of origin/main, and its path is the record's own path.
  R2  BLOB EQUALITY. `git rev-parse <sha9>:<path>` equals `Full-Text-Blob`. This
      is what stops a record naming a landed commit that carried different bytes.
  R3  THE SIZE RATIO, in both directions. The record fits its budget
      (`RECORD_MAX_BYTES` + `RECORD_PER_BOX_BYTES` per box), and the blob is at
      least `BLOB_RATIO`x the record. The floor is the anti-vacuity half: without
      it a "compaction" that pointed at a blob the same size as the record would
      satisfy every other rule while having compacted nothing.
  R4  `done=` IS PROVED AGAINST THE LEDGER AT THAT COMMIT. `git show
      <sha9>:.ci/config/plan-boxes.json` must carry the box's signature under
      `done_sigs` for this plan. Both directions: a `- [x]` box marked
      `abandoned` whose signature IS in the CURRENT ledger is red too, because
      that is a proof that was available and was not used.
  R5  `(record)` INSIDE A BOX LINE IS RED. The annotation belongs on its own
      four-space line beneath the box. Inside the box it becomes part of the task
      text, which changes the task signature -- and a changed signature is
      exactly what `check_plan_boxes.py`'s A1 reports as a vanished box.
  R6  AN UNFILLED PLACEHOLDER UNDER `compacted` IS RED. `--why author` writes
      `<FILL: ...>` slots on purpose; shipping one means the record was generated
      and never read. `parked` is exempt: its work is unfinished by definition.
  R7  THE SIGNATURE MATCHES. `Record-Sig:` equals `wl_planrec.record_sig`, which
      canonicalises status, pointer and the box table -- and deliberately NOT the
      prose, so a record stays editable.
  R8  `agent/INDEX.md` EQUALS THE RENDER. `--update` writes it.

WHAT IS DELIBERATELY NOT ASSERTED, stated so a green is not read as more than it
is.

  * Nothing here judges whether `## Why` is TRUE or `## Lessons` is useful. A
    record can pass every rule above and still be a bad summary of a good plan.
    The rules cover the half a machine can settle -- do the pointers resolve, do
    the numbers add up, is the proof really a proof -- and the other half is a
    reader's.
  * `## History` is APPEND-ONLY by convention and nothing here enforces it. It
    could be enforced from this lane (quality-branch has the base ref), and it is
    not, because the cost of getting it wrong runs the wrong way: a false red on
    a legitimately reworded history line teaches a session to stop writing the
    section. The pointer, the boxes and the signature are what a reader RELIES
    on, and all three are checked; `## History` is a courtesy log. Losing a line
    of it loses nothing recoverable -- the blob still carries the plan, and
    `git log --find-object` still carries the commit.
  * R6 is stricter than it may look, and deliberately so. `wl_planrec.render`
    NEVER emits an empty prose section: an empty one becomes `<FILL: why>`. So
    `--why auto` over a plan with no Why/Problem/Status section produces a record
    that is RED under `compacted` until a person writes the paragraph. That is
    the intended outcome rather than a gap -- a record with no Why is the reading
    copy of a plan nobody can now judge, and the machinery must not be able to
    manufacture one unattended. `--park` is the escape while the work is live.

WHY THIS GATE IS HAND-REGISTERED, and it must stay that way. It needs
`fetch-depth: 0` (R1's ancestor test and R4's ledger walk both read history) AND
the PR head ref. Exactly one lane provides both: `quality-branch`. That lane has
no `- id: setup` step, and the driver contract's invariant 11 records what a
generated region there does -- every emitted step carries
`if: steps.setup.outcome == 'success'`, which in a lane with no such step is
false, so every gate SKIPS while the job reports green. So this gate carries no
`---- gate ----` header and its workflow step is written by hand.

Exit 0 green, 1 findings or vacuous input, 2 instrument control failed.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(
    os.environ.get("PLAN_RECORD_ROOT") or pathlib.Path(__file__).resolve().parents[3]
)
sys.path.insert(0, str(ROOT / ".claude" / "hooks" / "stop"))

try:
    import wl_checks as CK
    import wl_planrec as R
except ImportError as _exc:  # pragma: no cover -- exercised by test-gate-anti-vacuity.sh
    # A check that cannot see must SAY it cannot see. The record grammar lives in
    # wl_planrec and there is deliberately no second copy of it here: a gate that
    # re-implemented the parser would drift from the writer, and the first symptom
    # would be a green run over records it was reading wrong.
    print(
        f"VACUOUS INPUT: cannot import the record parser from "
        f"{ROOT / '.claude' / 'hooks' / 'stop'} ({_exc}). This gate reads the record "
        f"grammar ONLY through wl_planrec, so without it there is nothing to compare "
        f"and no verdict to give.",
        file=sys.stderr,
    )
    sys.exit(1)

# Floor over the PLAN corpus, not over the records. Zero records is the correct
# state today (phase 1 builds the machinery; no real plan is compacted yet), so a
# floor on records would be a gate that cannot pass. A floor on the plans is what
# catches the glob losing the corpus -- the same number check_plan_boxes.py uses.
MIN_PLAN_FILES = int(os.environ.get("PLAN_RECORD_MIN_PLANS", "20"))


def _git(root, *args):
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    return r.stdout.strip() if r.returncode == 0 else ""


# ---------------------------------------------------------------------------
# The rules.


# One `git show <sha>:<ledger>` per (repo, COMMIT), not per box. The 33-plan wave
# this gate was built for carries several boxes each, and one plan's boxes were
# almost always ticked in the same ledger regeneration -- so without this the
# gate pays a git process per box to read the same blob back.
#
# THE ROOT IS PART OF THE KEY. `main()` runs `selftest()` against a throwaway
# fixture repo BEFORE it judges the real tree, through this same module-level
# dict. Keying on the commit alone would let a fixture sha answer for a real one;
# collisions are not realistic, but "not realistic" is a worse reason than
# "cannot happen", and the second costs one tuple.
_LEDGER_CACHE = {}


def ledger_at(root, commit):
    key = (str(root), commit)
    if key not in _LEDGER_CACHE:
        _LEDGER_CACHE[key] = R.ledger_at(root, commit)
    return _LEDGER_CACHE[key]


def problems_for(root, rel, text, current_ledger):
    """[str] -- every rule this one record breaks. Empty means it holds.

    `current_ledger` is passed in rather than read per record: R4's second
    direction consults it once per box, and re-reading a 40 KB JSON file for each
    of them is how a gate over 81 plans becomes the slowest step in its lane.
    """
    rec = R.parse(text)
    if rec is None:
        return []
    out = ["%s: %s" % (rel, p) for p in rec["problems"]]

    # ---- R1 pointer resolution ------------------------------------------
    blob = rec["blob"]
    blob_ok = False
    if blob:
        blob_ok, why = R.resolve(root, "blob", blob)
        if not blob_ok:
            out.append(
                "%s: Full-Text-Blob %s does not resolve to a blob here (%s). The record's "
                "recovery recipe returns NOTHING, which is worse than the deleted plan it "
                "replaced -- that at least announced its own absence" % (rel, blob[:12], why)
            )
    if rec["full_text_sha"]:
        sha, path = rec["full_text_sha"], rec["full_text_path"]
        ok, why = R.resolve(root, "ancestor", sha)
        if not ok:
            out.append(
                "%s: Full-Text names commit %s, which %s. A commit recorded on a branch is "
                "REWRITTEN by `gh pr merge --rebase`, so an unlanded sha here is a pointer "
                "with an expiry date -- omit the Full-Text line and let the blob carry it, "
                "or re-derive it after the merge" % (rel, sha, why)
            )
        elif path != rel:
            out.append(
                "%s: Full-Text names path %s, which is not this record's own path. A record "
                "keeps its plan's path precisely so citations still resolve; pointing "
                "elsewhere silently breaks that" % (rel, path)
            )
        else:
            # ---- R2 blob equality ---------------------------------------
            at = _git(root, "rev-parse", "%s:%s" % (sha, path))
            if at != blob:
                out.append(
                    "%s: the blob at %s:%s is %s, but Full-Text-Blob says %s. One of the two "
                    "pointers names bytes the other does not, and a reader following the "
                    "commit gets a different document from one following the blob"
                    % (rel, sha[:9], path, (at or "nothing")[:12], blob[:12])
                )

    # ---- R3 size, in both directions -------------------------------------
    n_boxes = len(rec["boxes"])
    size = len(text.encode("utf-8"))
    budget = R.size_budget(n_boxes)
    if size > budget:
        out.append(
            "%s: the record is %d bytes against a budget of %d (%d KB + %d B per box, %d "
            "box(es)). A record that needs more than that is not a record, it is the plan "
            "again -- and the plan is already in the blob"
            % (rel, size, budget, R.RECORD_MAX_BYTES // 1024, R.RECORD_PER_BOX_BYTES, n_boxes)
        )
    if blob_ok:
        raw = _git(root, "cat-file", "-s", blob)
        try:
            blob_size = int(raw)
        except ValueError:
            blob_size = -1
        if blob_size >= 0 and blob_size < size * R.BLOB_RATIO:
            out.append(
                "%s: the pointed blob is %d bytes and the record is %d, a ratio of %.2f "
                "against a floor of %.1f. Nothing was compacted. This is the ANTI-VACUITY "
                "half of the size rule: without it, a record pointing at a blob its own size "
                "would satisfy every other rule here while having achieved nothing"
                % (rel, blob_size, size, (blob_size / size if size else 0), R.BLOB_RATIO)
            )

    # ---- R4 done= proved against the ledger ------------------------------
    for b in rec["boxes"]:
        done, sig, mark = b["done"], b["sig"], b["mark"]
        if mark == "x" and done == "open":
            out.append(
                "%s: box %r is ticked but records `done=open`. The mark and the claim "
                "disagree; one of them is wrong and the record cannot say which"
                % (rel, b["body"][:60])
            )
            continue
        if mark != "x" and done != "open":
            out.append(
                "%s: box %r is OPEN but records `done=%s`. An open box has nothing to "
                "attest" % (rel, b["body"][:60], done)
            )
            continue
        if done == "open":
            continue
        if done == "abandoned":
            # THE SECOND DIRECTION, and it is what stops `abandoned` being a
            # dodge. If the current ledger attests this signature, a proof was
            # available and the record declined to use it.
            if R.attested_at(current_ledger, rel, sig):
                out.append(
                    "%s: box %r records `done=abandoned`, but %s attests signature %s under "
                    "done_sigs for this plan RIGHT NOW. `abandoned` means no proof exists; a "
                    "proof exists. Re-run `worklist.py --plan-compact` to pick it up"
                    % (rel, b["body"][:60], R.LEDGER_REL, sig)
                )
            continue
        ok, why = R.resolve(root, "commit", done)
        if not ok:
            out.append(
                "%s: box %r records `done=%s`, which is not a commit here (%s)"
                % (rel, b["body"][:60], done, why)
            )
            continue
        ledger = ledger_at(root, done)
        if ledger is None:
            out.append(
                "%s: box %r records `done=%s`, but %s does not exist at that commit, so "
                "nothing there attests the tick" % (rel, b["body"][:60], done, R.LEDGER_REL)
            )
        elif not R.attested_at(ledger, rel, sig):
            out.append(
                "%s: box %r records `done=%s`, and the ledger AT THAT COMMIT does not carry "
                "signature %s under done_sigs for %s. The proof is asserted, not present"
                % (rel, b["body"][:60], done, sig, rel)
            )

    # ---- R5 `(record)` inside a box line ----------------------------------
    # rec["problems"] already carries this one -- parse() finds it while it has
    # the raw line in hand, which is the only place the distinction between "in
    # the box" and "on the annotation line" still exists. Folded in at the top.

    # ---- R6 an unfilled placeholder under `compacted` ---------------------
    if rec["status"] == R.STATUS_COMPACTED:
        hits = R.PLACEHOLDER_RE.findall(text)
        if hits:
            out.append(
                "%s: %d unfilled placeholder(s) %s under `Status: compacted`. `--why author` "
                "writes those slots on purpose; shipping one means the record was generated "
                "and never read. (`parked` is exempt -- its work is unfinished by definition.)"
                % (rel, len(hits), ", ".join(sorted(set(hits))[:3]))
            )

    # ---- R7 the signature -------------------------------------------------
    want = R.record_sig(rec)
    if rec["record_sig"] and rec["record_sig"] != want:
        out.append(
            "%s: Record-Sig says %s and the record's own spine hashes to %s. The signature "
            "covers status, pointer and the box table -- NOT the prose -- so this means one "
            "of those was edited by hand. Re-derive it, or revive and re-compact"
            % (rel, rec["record_sig"], want)
        )
    return out


def index_problems(root, rows, update=False):
    """R8. `agent/INDEX.md` is a second reading of the records, so it is checked
    for EQUALITY rather than for containment: a stale row is exactly as wrong as
    a missing one, and only equality catches both.

    An EMPTY render means "no records", and an ABSENT file is equal to it. A repo
    with nothing compacted must not be forced to carry a generated table that
    says nothing -- that is the committed-lie shape `agent/README.md:11` names.
    """
    want = R.render_index(rows)
    path = pathlib.Path(root) / R.INDEX_REL
    try:
        got = path.read_text(encoding="utf-8")
    except OSError:
        got = ""
    if got == want:
        return []
    if update and want:
        R.write_atomic(path, want)
        print(f"✓ wrote {R.INDEX_REL}: {len(rows)} record(s)")
        return []
    if not want:
        # ZERO RECORDS AND A NON-EMPTY INDEX. `--update` deliberately does NOT
        # "fix" this by truncating the file: nothing in this program deletes a
        # committed document, and an --update that silently emptied one would be
        # the first. It is reported in both modes, with the removal left to a
        # person who can see what the file still claims.
        return [
            (
                f"{R.INDEX_REL} exists ({len(got)} bytes) but there are no compacted or "
                f"parked records to index. Every record it names has been revived or "
                f"removed. Delete the file by hand -- `--update` will not truncate a "
                f"committed document."
            )
        ]
    return [
        (
            f"{R.INDEX_REL} disagrees with the records on disk "
            f"({len(got)} bytes present, {len(want)} bytes derived from "
            f"{len(rows)} record(s)). Regenerate and commit it:\n"
            f"      npm run check:ci-plan-record -- --update\n"
            f"      git add {R.INDEX_REL}"
        )
    ]


# ---------------------------------------------------------------------------
# CONTROL FIRST. Every verdict above is meaningless if these do not fire, so the
# fixture is a REAL git repository with a real origin/main, a real ledger and a
# real blob. Nothing here is mocked: R1's ancestor test, R2's `rev-parse
# <sha>:<path>` and R4's `git show <sha>:<ledger>` are the rules most likely to
# be satisfied by a stub while being broken against git.


def _run(cwd, *args):
    subprocess.run(args, cwd=str(cwd), check=True, capture_output=True, text=True)


def build_fixture(td):
    """A tiny repo carrying one plan, one ledger commit, and a `main` to be an
    ancestor of. Returns (root, rel, record_text).

    BUILT BY CONSTRUCTION, not by substituting into a copy of the real tree.
    `check-control-vacuity.sh` exempts construction for exactly this reason: a
    fixture assembled from known-bad parts cannot fail to contain the defect,
    whereas a substitution can silently miss and leave a control that proves the
    clean case twice.
    """
    root = pathlib.Path(td) / "repo"
    (root / "agent").mkdir(parents=True)
    (root / ".ci" / "config").mkdir(parents=True)
    _run(root, "git", "init", "-q", "-b", "main")
    _run(root, "git", "config", "user.email", "fixture@example.invalid")
    _run(root, "git", "config", "user.name", "fixture")

    rel = "agent/PLAN-fixture.md"
    task_done = "a finished task long enough for the parser to keep it"
    task_open = "an unfinished task long enough for the parser to keep it"
    plan = (
        "# Fixture plan\n"
        "Status: executing\n"
        "Owner: deadbeef\n"
        "\n"
        "## Problem\n"
        "A fixture needs a body long enough that the record is genuinely smaller than\n"
        "the plan, because the size ratio is one of the rules under test and a rule\n"
        "that cannot be satisfied by the fixture is a rule nothing here proves.\n"
        + ("Padding line that exists to make the blob big enough to compact.\n" * 220)
        + "\n## Tasks\n"
        f"- [x] {task_done}\n"
        f"- [ ] {task_open}\n"
    )
    (root / rel).write_text(plan, encoding="utf-8")

    sig_done = R.box_sig(task_done)
    sig_open = R.box_sig(task_open)

    def write_ledger(done_sigs):
        (root / R.LEDGER_REL).write_text(
            json.dumps(
                {
                    "plans": {
                        rel: {
                            "status": "executing",
                            "owner": "deadbeef",
                            "open": 1,
                            "done": len(done_sigs),
                            "open_sigs": [sig_open],
                            "done_sigs": list(done_sigs),
                        }
                    }
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    # TWO LEDGER COMMITS, and the shape is the point rather than a convenience.
    # The first has the box still OPEN, the second attests the tick. That is what
    # makes R4 testable at all: a single-commit fixture has no commit whose ledger
    # lacks the signature, so the "asserted, not present" plant cannot be built
    # and the control silently proves nothing. It also exercises the oldest-first
    # walk in `ledger_history` -- `done=` must name the SECOND commit, and the
    # assertion straight after build_fixture checks exactly that.
    write_ledger([])
    (root / "package.json").write_text(
        json.dumps({"scripts": {"check:ci-plan-record": "x"}}) + "\n", encoding="utf-8"
    )
    _run(root, "git", "add", "-A")
    _run(root, "git", "commit", "-qm", "fixture: the box is open")
    before = _git(root, "rev-parse", "HEAD")

    write_ledger([sig_done])
    _run(root, "git", "add", "-A")
    _run(root, "git", "commit", "-qm", "fixture: the box is ticked")
    # A remote-tracking ref so the `ancestor` resolver has an origin/main to
    # answer against, without a network or a second repository.
    _run(root, "git", "update-ref", "refs/remotes/origin/main", "HEAD")

    text, _notes = R.compact(root, rel, "deadbeef", why="auto", park=True)
    return root, rel, text, before


def selftest():
    """Plant ONE defect per rule, require the matching finding, and require the
    clean record to stay SILENT. The silent case is not a formality: "every
    fixture reds" is a check that cannot pass, and it is the shape a gate takes
    on when a refactor breaks its parser."""
    bad = 0

    def ck(label, ok, detail=""):
        nonlocal bad
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
        if not ok:
            bad += 1
            if detail:
                print(f"        {detail}")

    with tempfile.TemporaryDirectory() as td:
        try:
            root, rel, clean, before = build_fixture(td)
        except Exception as exc:  # noqa: BLE001 -- a broken fixture must be LOUD
            ck("the fixture builds at all", False, repr(exc))
            return 1
        ledger = json.loads((root / R.LEDGER_REL).read_text(encoding="utf-8"))

        def judge(text):
            return problems_for(root, rel, text, ledger)

        # The clean case, FIRST. Everything below is measured against it.
        got = judge(clean)
        ck("CONTROL: a well-formed record is silent", got == [], f"got {got}")

        rec = R.parse(clean)
        ck(
            "CONTROL: the fixture record really is a record, with both boxes",
            rec is not None and len(rec["boxes"]) == 2,
            f"got {rec and len(rec['boxes'])}",
        )
        ck(
            "CONTROL: the fixture's done box carries a real ledger commit, not `abandoned`",
            any(b["done"] not in ("open", "abandoned") for b in (rec["boxes"] if rec else [])),
            f"got {[b['done'] for b in (rec['boxes'] if rec else [])]}",
        )

        def plant(label, text, needle):
            g = judge(text)
            hit = any(needle in p for p in g)
            ck(label, hit, f"needle {needle!r} not in {g}")

        # R1a: a blob that does not exist.
        plant(
            "R1: an unresolvable Full-Text-Blob is reported",
            clean.replace("Full-Text-Blob: " + rec["blob"], "Full-Text-Blob: " + "0" * 40),
            "does not resolve to a blob",
        )
        # R1b: a commit that is not an ancestor of origin/main. An all-zero sha is
        # not a commit at all, which is the same rule's other exit.
        plant(
            "R1: a Full-Text commit that does not resolve is reported",
            clean.replace(
                "Full-Text: %s %s" % (rec["full_text_sha"], rel),
                "Full-Text: 0123456ab %s" % rel,
            ),
            "Full-Text names commit",
        )
        # R1c: the pointer names someone else's path.
        plant(
            "R1: a Full-Text path that is not the record's own is reported",
            clean.replace(
                "Full-Text: %s %s" % (rec["full_text_sha"], rel),
                "Full-Text: %s agent/PLAN-elsewhere.md" % rec["full_text_sha"],
            ),
            "which is not this record's own path",
        )
        # R2: the commit is real and landed, and carries DIFFERENT bytes. Built by
        # pointing Full-Text-Blob at the LEDGER's blob, which resolves (so R1
        # passes) and is not the plan's (so only R2 can fire).
        other = _git(root, "rev-parse", "HEAD:" + R.LEDGER_REL)
        plant(
            "R2: a real blob that is not the one at <sha>:<path> is reported",
            clean.replace("Full-Text-Blob: " + rec["blob"], "Full-Text-Blob: " + other),
            "One of the two pointers names bytes the other does not",
        )
        # R3 floor: point at a blob smaller than the record. The ledger blob is
        # small, so the same substitution serves -- and its R2 finding is a
        # different string, so the two rules stay separately observable.
        plant(
            "R3: a blob smaller than the record is reported as nothing compacted",
            clean.replace("Full-Text-Blob: " + rec["blob"], "Full-Text-Blob: " + other),
            "Nothing was compacted",
        )
        # R3 ceiling: an oversized record.
        plant(
            "R3: a record over its byte budget is reported",
            clean.replace("## Why\n", "## Why\n" + ("x" * 80 + "\n") * 200, 1),
            "against a budget of",
        )
        done_line = next(
            ln
            for ln in clean.splitlines()
            if "(record)" in ln and "done=" in ln and "open" not in ln
        )
        # THE OLDEST-FIRST WALK, asserted before the plants that depend on it.
        # `done=` must name the commit that FIRST attested the tick, which is the
        # second of the two. Naming the newest instead would be a date with no
        # meaning -- the ledger is rewritten wholesale by --update, so every
        # signature in it appears in every later commit.
        ck(
            "CONTROL: done= names the FIRST attesting commit, not the newest",
            R.sha9(_git(root, "rev-parse", "HEAD")) in done_line
            and R.sha9(before) not in done_line,
            f"done_line={done_line!r} before={R.sha9(before)}",
        )
        # R4a: done= names a real, landed commit whose ledger does NOT attest the
        # signature -- the commit from before the box was ticked.
        plant(
            "R4: a done= commit whose ledger does not attest the signature is reported",
            clean.replace(
                done_line,
                "    (record) sig=%s done=%s" % (rec["boxes"][0]["sig"], R.sha9(before)),
            ),
            "does not carry signature",
        )
        # R4b: `abandoned` while the current ledger holds the proof.
        plant(
            "R4: `abandoned` over a signature the ledger attests NOW is reported",
            clean.replace(done_line, "    (record) sig=%s done=abandoned" % rec["boxes"][0]["sig"]),
            "a proof exists",
        )
        # R4c: the mark and the claim disagree.
        plant(
            "R4: a ticked box recording done=open is reported",
            clean.replace(done_line, "    (record) sig=%s done=open" % rec["boxes"][0]["sig"]),
            "The mark and the claim disagree",
        )
        # R5: the annotation moved INSIDE the box line.
        box_line = next(ln for ln in clean.splitlines() if ln.startswith("- [x] "))
        plant(
            "R5: `(record)` inside a box line is reported",
            clean.replace(box_line, box_line + " (record)"),
            "carries `(record)` inside it",
        )
        # R6: a placeholder under `compacted`. The fixture is `parked` (it has an
        # open box), so the status is flipped as part of the plant -- which is
        # also the control for `parked` being EXEMPT, asserted straight after.
        with_ph = clean.replace("## Why\n", "## Why\n" + R.placeholder("why") + "\n", 1)
        plant(
            "R6: an unfilled placeholder under `compacted` is reported",
            with_ph.replace("Status: parked", "Status: compacted", 1),
            "unfilled placeholder",
        )
        g = judge(with_ph)
        ck(
            "R6 CONTROL: the same placeholder under `parked` is NOT reported",
            not any("unfilled placeholder" in p for p in g),
            f"got {g}",
        )
        # R7: a hand-edited spine.
        plant(
            "R7: a Record-Sig that does not match the spine is reported",
            clean.replace("Record-Sig: " + rec["record_sig"], "Record-Sig: 00000000"),
            "hashes to",
        )
        # R7 CONTROL: editing PROSE must NOT move the signature, or the record
        # becomes un-editable and people work around it instead of using it.
        edited = clean.replace("## Lessons\n", "## Lessons\n- a sharpened lesson\n", 1)
        er = R.parse(edited)
        ck(
            "R7 CONTROL: sharpening the prose does not move the signature",
            er is not None and R.record_sig(er) == rec["record_sig"],
            f"{er and R.record_sig(er)} vs {rec['record_sig']}",
        )

        # R8, both directions.
        rows = [(rel, "parked", 1, 1, 0, rec["blob"])]
        (root / rel).write_text(clean, encoding="utf-8")
        ck(
            "R8: a missing agent/INDEX.md over a non-empty record set is reported",
            index_problems(root, rows) != [],
        )
        R.write_atomic(root / R.INDEX_REL, R.render_index(rows))
        ck(
            "R8 CONTROL: a matching agent/INDEX.md is silent",
            index_problems(root, rows) == [],
            f"got {index_problems(root, rows)}",
        )
        ck(
            "R8: a PRESENT index over ZERO records is reported",
            index_problems(root, []) != [],
            f"got {index_problems(root, [])}",
        )
        (root / R.INDEX_REL).unlink()
        ck(
            "R8 CONTROL: an ABSENT index over ZERO records is silent",
            R.render_index([]) == "" and index_problems(root, []) == [],
            f"render_index([])={R.render_index([])!r} problems={index_problems(root, [])}",
        )

        # THE ANTI-VACUITY CONTROL FOR THE WHOLE GATE: a plain plan is not a
        # record and must produce NOTHING. Without this, a parse() that returned
        # a record for every file would look identical to a clean tree.
        ck(
            "CONTROL: the gate says nothing about a file that is not a record",
            judge("# P\nStatus: executing\n\n## Tasks\n- [ ] something entirely ordinary\n") == [],
        )
    return bad


# ---------------------------------------------------------------------------


def main(argv):
    update = "--update" in argv
    print("plan records: controls first, then the verdict")
    if selftest():
        print(
            "✗ instrument control failed; every verdict below would be meaningless",
            file=sys.stderr,
        )
        return 2
    if "--selftest" in argv:
        print("✓ selftest only; the real tree was not judged")
        return 0

    recs = CK.plan_records(ROOT)
    if len(recs) < MIN_PLAN_FILES:
        print(
            f"VACUOUS INPUT: found {len(recs)} plan file(s) under agent/, floor is "
            f"{MIN_PLAN_FILES}. The glob lost the corpus; refusing a verdict rather than "
            f"reporting a clean tree for files nobody read.",
            file=sys.stderr,
        )
        return 1

    try:
        current = json.loads((ROOT / R.LEDGER_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(
            f"✗ cannot read {R.LEDGER_REL} ({exc}); every `done=` claim would be "
            f"unverifiable, so this gate refuses a verdict rather than passing them.",
            file=sys.stderr,
        )
        return 1

    problems, n_records = [], 0
    for rel, status, _n in recs:
        if status not in R.RECORD_STATES:
            continue
        try:
            text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            problems.append(f"{rel}: cannot be read ({exc})")
            continue
        n_records += 1
        problems.extend(problems_for(ROOT, rel, text, current))

    rows = R.index_rows(ROOT, recs)
    problems.extend(index_problems(ROOT, rows, update=update))

    if problems:
        print(
            f"✗ plan records: {len(problems)} problem(s) across {n_records} record(s):",
            file=sys.stderr,
        )
        for p in problems:
            print(f"    {p}", file=sys.stderr)
        print(
            "\n  A record stands in for a plan that is no longer in the file, so a claim it\n"
            "  cannot prove is a document that lies quietly. Revive it, fix the plan, and\n"
            "  compact it again:\n"
            "    .claude/hooks/stop/worklist.py --plan-revive <me> <path> --write",
            file=sys.stderr,
        )
        return 1

    print(
        f"✓ plan records: {len(recs)} plan file(s) (floor {MIN_PLAN_FILES}), "
        f"{n_records} compacted or parked record(s), every pointer resolves, every "
        f"`done=` is attested by {R.LEDGER_REL} at the commit it names, and "
        f"{R.INDEX_REL} matches."
    )
    if n_records == 0:
        print(
            "  0 records is the expected state until the first compaction wave. The rules\n"
            "  above ran against the planted fixtures in --selftest, not against nothing."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
