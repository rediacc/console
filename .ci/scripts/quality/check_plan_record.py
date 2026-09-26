#!/usr/bin/env python3
"""check:ci-plan-record -- a compacted plan must PROVE what it claims.

WHY THIS GATE EXISTS. `wl_planrec.py` lets a finished `agent/PLAN-*.md` shrink into a record that keeps its own path, so the 2,539 existing citations of those paths still resolve and the housekeeping clock stops demanding a deletion the operator forbids. That trade only works if the record's pointers are real. A record whose blob does not exist is strictly WORSE than the deleted
plan it replaced: the plan at least announced its own absence, while a record announces a recovery command that silently returns nothing.

So every claim a record makes is re-derived here from git and from the committed box ledger, and none of it is believed.

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
  R9  THE CROSS-REFERENCE HEADERS RESOLVE (W12 P3.4b). `Supersedes:`, `Extends:`
      and `Related:` were taught to PARSE by P3.4a -- `wl_planrec.HEADER_FIELD_KEYS`
      lists them so a `# PLAN: ...` heading is not read as a field -- and nothing
      resolved them to anything. `wl_planrec.parse()` does not even return their
      values. THE ARITIES DIFFER, which is why it is three plants and not one:
      `Supersedes` needs at least one pointer, `Extends` exactly one, `Related`
      any number including none. Every pointer that IS present must resolve,
      through the sibling gate's extractor rather than a second copy of it.
      SCOPED TO EVERY PLAN, not to records: both real subjects in this tree carry
      `Status: draft`, so records-only would be a rule with no subject.

THE ADVISORY CENSUS (W12 P3.5), AND WHY IT REFUSES NOTHING. R1..R9 are the rules this gate ENFORCES; the file's docstring has promised R1..R10 since it was written, and the missing rungs are named in "WHAT IS DELIBERATELY NOT ASSERTED" below rather than in the list above -- they are rules that were considered and declined. Turning one on is a one-way door: the day it blocks, it
blocks every open branch at once, and nobody knows today how many records it would refuse.

So it is MEASURED first. Every real-tree run appends one row to `agent/ledgers/census-plan-record.jsonl` recording what each CANDIDATE rule WOULD have refused, per record, with a UTC timestamp. After two weeks of rows, `--census-report` answers "has the window elapsed, and what would have been refused across it" from the rows alone -- not from anyone's memory of how the tree
looked. The candidates:

  C9   HISTORY APPEND-ONLY. The `## History` bullets in the most recent
       COMMITTED version of this record must be a PREFIX of the ones on disk.
       This is the rule the "not asserted" section below declines by name.
  C10  A `parked` RECORD STILL CARRYING `<FILL: ...>`. R6 exempts `parked`
       because its work is unfinished by definition, and that exemption has no
       time bound: a record parked with placeholders forever is a record nobody
       will ever fill.
  C11  THE `Full-Text:` UPGRADE. `Full-Text` is optional while the text is not
       on origin/main yet and is meant to be upgraded once it lands. A record
       whose blob IS reachable from origin/main and still carries no `Full-Text`
       line never took the upgrade.

TWO PROPERTIES OF THE CENSUS, and they are not the same property.

  * A CANDIDATE FIRING NEVER CHANGES A VERDICT OR AN EXIT CODE. That is the
    whole point of an advisory rung. A tree where all three candidates fire on
    every record still exits 0 if R1..R8 hold.
  * A CENSUS THAT RECORDED NOTHING IS AN INSTRUMENT FAILURE AND EXITS 2. An
    advisory check is the easiest thing in the world to make vacuous: delete its
    call site and it reports exactly what a clean tree reports, forever, and the
    two-week clock never starts. So the row is written and then READ BACK, the
    file must have grown, and the census's own count of plans and records must
    AGREE with the verdict loop's -- two readings of the corpus, not one number
    trusted twice. Any of those failing is exit 2, the same code a failed
    `--selftest` uses, because it is the same kind of failure.

WHAT IS DELIBERATELY NOT ASSERTED, stated so a green is not read as more than it is.

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

WHY THIS GATE IS HAND-REGISTERED, and it must stay that way. It needs `fetch-depth: 0` (R1's ancestor test and R4's ledger walk both read history) AND the PR head ref. Exactly one lane provides both: `quality-branch`. That lane has no `- id: setup` step, and the driver contract's invariant 11 records what a generated region there does -- every emitted step carries
`if: steps.setup.outcome == 'success'`, which in a lane with no such step is
false, so every gate SKIPS while the job reports green. So this gate carries no `---- gate ----` header and its workflow step is written by hand.

Exit 0 green, 1 findings or vacuous input, 2 instrument control failed.
"""

from __future__ import annotations

import datetime
import functools
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile

import _cipath  # noqa: F401
from rediacc_ci import paths
from rediacc_ci.controls import plant
from rediacc_ci.quality import plan_lifecycle as PL

ROOT = pathlib.Path(
    os.environ.get("PLAN_RECORD_ROOT") or pathlib.Path(__file__).resolve().parents[3]
)
# THREE HAND-WRITTEN HOPS BECAME ZERO HERE, and the `.ci` one is the reason the
# import block above is now unbroken: this file used to reach the package with
# `sys.path.insert(0, str(ROOT / ".ci"))` and then pay an `E402` for the import that followed it. `import _cipath` is the same hop written where every other gate in this directory writes it, so `from rediacc_ci.controls import plant` is an ordinary import again. It also fixes a latent divergence nothing was exercising: the old spelling loaded the LIBRARY from
# `$PLAN_RECORD_ROOT/.ci`, so pointing this gate at a fixture would have judged the fixture with the fixture's own copy of `controls`. `_cipath` resolves from `__file__`, which is the tree the gate was started from either way.
#
# The other two hops go through the package's resolver. `paths.on_sys_path` is idempotent where `sys.path.insert(0, d)` is not, and `paths.hooks_stop_dir` is the ONE place the `.claude/hooks/stop` literal lives. ROOT is passed explicitly: this gate honours its own PLAN_RECORD_ROOT override, which the resolver's default root does not read.
paths.on_sys_path(paths.hooks_stop_dir(ROOT))

# W12 P3.4b. THE CITATION EXTRACTOR IS BORROWED, NOT REBUILT. `citations()` lives in the sibling gate and its path regex carries five separately paid-for extension rounds (dotfiles, .astro, .mdx, .cast, leading dots). A fresh regex here would re-open every one of them, and the two gates would then disagree about what a pointer even is. Same stance check_plan_citations itself takes
# towards wl_planrec. The sibling is reached from THIS FILE's directory, never
# from ROOT: a fixture override must not be able to swap the extractor out.
paths.on_sys_path(pathlib.Path(__file__).resolve().parent)

try:
    import wl_checks as CK
    import wl_planindex as PI
    import wl_planrec as R
    from check_plan_citations import citations as _citations
    from check_plan_citations import unresolved as _unresolved
except ImportError as _exc:  # pragma: no cover -- exercised by `.ci/rediacc_ci/tests/gates/test_gate_gate_anti_vacuity.py`
    # A check that cannot see must SAY it cannot see. The record grammar lives in wl_planrec and there is deliberately no second copy of it here: a gate that re-implemented the parser would drift from the writer, and the first symptom would be a green run over records it was reading wrong.
    print(
        f"VACUOUS INPUT: cannot import the record parser from "
        f"{ROOT / '.claude' / 'hooks' / 'stop'} ({_exc}). This gate reads the record "
        f"grammar ONLY through wl_planrec, so without it there is nothing to compare "
        f"and no verdict to give.",
        file=sys.stderr,
    )
    sys.exit(1)

# Floor over the PLAN corpus, not over the records. Zero records is the correct state today (phase 1 builds the machinery; no real plan is compacted yet), so a floor on records would be a gate that cannot pass. A floor on the plans is what catches the glob losing the corpus -- the same number check_plan_boxes.py uses.
MIN_PLAN_FILES = int(os.environ.get("PLAN_RECORD_MIN_PLANS", "20"))

# THE ADVISORY CENSUS. `agent/ledgers/census-*.jsonl` is globbed by `--census-report` so that a future per-branch split (the shape `agent/reggate/<branch>.jsonl` already uses, to keep an append-only log out of merge conflicts) needs no reader change. S5 of agent/plans/PLAN-agent-tree-lifecycle.md moved it out of the agent root: a `.jsonl` at the top of a directory of documents
# reaches nobody's eye, which is the class `check:ci-tree-shape` exists for. The DIRECTORY is the constant the glob is taken from, so the two cannot name different places.
CENSUS_DIR = "agent/ledgers"
CENSUS_REL = CENSUS_DIR + "/census-plan-record.jsonl"
CENSUS_GLOB = "census-*.jsonl"

# The POLICY window from the box this census exists to serve ("a two-week advisory census before any blocking rung"), not a floor. It is what `--census-report` compares the recorded span against; it never gates this run.
CENSUS_WINDOW_DAYS = int(os.environ.get("PLAN_RECORD_CENSUS_DAYS", "14"))

# The candidate rules, keyed by the rung a future blocking version would carry. The text is the refusal that rung would print, kept HERE rather than at the three call sites so the census row, the report and the eventual rung cannot drift into describing three different rules.
CANDIDATES = {
    "C9-history-append-only": (
        "`## History` is documented as append-only and this record lost or rewrote a "
        "bullet it carried in its previous committed version"
    ),
    "C10-parked-placeholder": (
        "a `parked` record still carries an unfilled `<FILL: ...>` placeholder; R6 "
        "exempts `parked` and that exemption has no time bound"
    ),
    "C11-fulltext-upgrade": (
        "the blob is reachable from origin/main and the record still carries no "
        "`Full-Text: <sha9> <path>` line, so the upgrade never happened"
    ),
}


def _git(root, *args):
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    return r.stdout.strip() if r.returncode == 0 else ""


# --------------------------------------------------------------------------- W12 P3.4b. R9: the three cross-reference header keys RESOLVE.
#
# P3.4a made `Supersedes`, `Extends` and `Related` PARSE: `wl_planrec.py:203-215` lists them in HEADER_FIELD_KEYS so a `# PLAN: ...` heading is not mistaken for a field. That is the whole of what "parse" bought. NOTHING RESOLVED THEM. Measured 2026-09-09: `wl_planrec.parse()` does not even return their values (`:584-598`), and `git grep Supersedes -- '.ci/scripts/quality/*'`
# returned nothing at all. A plan could say it supersedes a document that does not exist and no instrument would notice, which is the same failure class as the 37 dead citations `check_plan_citations.py` was written for.
#
# THE ARITIES DIFFER, WHICH IS WHY THIS IS THREE RULES AND NOT ONE:
#
# Supersedes AT LEAST ONE pointer. A supersession is an instruction to a reader: go read that instead. Naming nothing is unfalsifiable and unactionable, so it is a finding even though every pointer present resolves. Extends EXACTLY ONE. You extend one document. Two leaves a reader with no way to know which one carries the base they need, and zero is the Supersedes case again.
# Related ANY NUMBER, INCLUDING NONE. This is deliberate asymmetry, not an oversight: `Related:` is a note, and a note whose value is an issue URL or a sentence carries no in-tree pointer and is still a true statement. What is checked is that any pointer it DOES carry resolves.
#
# THE VALUE IS A BLOCK, NOT A LINE, and this is load-bearing rather than generous. Both real users in this tree wrap: `agent/plans/PLAN-bws-rotation-on-failure.md:4-5` puts its only resolvable pointer on the SECOND line, and reading the key's own line alone would report that plan as superseding nothing. The block ends at a blank line, at the next header field, or at a markdown
# heading.
#
# SCOPE IS EVERY PLAN, NOT EVERY RECORD. Both subjects in this tree carry `Status: draft`, so a rule scoped to compaction records would have zero subjects and pass forever, which is the shape this repo calls a rule with no subject.

HEADER_XREF_KEYS = ("Supersedes", "Extends", "Related")
#: (minimum, maximum) pointers. `None` means unbounded.
HEADER_XREF_ARITY = {"Supersedes": (1, None), "Extends": (1, 1), "Related": (0, None)}


def header_xref_block(text, key):
    """The full value of `<key>:` in the header window, continuation lines and all.

    Returns "" when the key is absent. The block ends at a blank line, at another `Word:` header field, or at a `#` heading -- the three things that reliably end a value in this grammar.
    """
    lines = (text or "").splitlines()[: R.HEADER_LINES]
    out, taking = [], False
    for raw in lines:
        if taking:
            stripped = raw.strip()
            if not stripped or stripped.startswith("#") or R.HEAD_FIELD_RE.match(raw):
                break
            out.append(raw)
            continue
        m = R.HEAD_FIELD_RE.match(raw)
        if m and m.group(1) == key:
            taking = True
            out.append(m.group(2))
    return "\n".join(out) if taking else ""


def header_xref_problems(root, rel, text):
    """R9 over one plan. [] when it says nothing about supersession at all."""
    problems = []
    for key in HEADER_XREF_KEYS:
        block = header_xref_block(text, key)
        if not block:
            continue
        found = [pair for line in block.splitlines() for pair in _citations(line)]
        low, high = HEADER_XREF_ARITY[key]
        if len(found) < low:
            problems.append(
                f"{rel}: `{key}:` names {len(found)} resolvable pointer(s) and needs at "
                f"least {low}. Cite the thing it {key.lower()} as a FULL PATH "
                f"(`agent/PLAN-x.md`, or `path/to/file.ext:123`); a cross-reference a "
                f"reader cannot follow is a claim, not a pointer."
            )
        if high is not None and len(found) > high:
            names = ", ".join(f"`{t}`" for _k, t in found)
            problems.append(
                f"{rel}: `{key}:` names {len(found)} pointers ({names}) and takes exactly "
                f"{high}. Split the rest into `Related:`, which takes any number."
            )
        for kind, token in found:
            # `unresolved`, not `R.resolve` directly: the `object` kind has TWO acceptable answers (a blob or a commit) and R.resolve has no such kind at all, so calling it here would raise on a sha-shaped token.
            bad, why = _unresolved(root, kind, token)
            if bad:
                problems.append(f"{rel}: `{key}:` cites {kind} `{token}` -- {why}")
    return problems


def _git_raw(root, *args):
    """`_git` without the `.strip()`.

    C9 compares a committed blob against the bytes on disk, and `_git`'s strip removes the trailing newline from one side only -- which would make EVERY record look modified and hand the census a baseline it never uses. The strip is right for `rev-parse` and wrong for `show`, so both exist.
    """
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    return r.stdout if r.returncode == 0 else ""


# --------------------------------------------------------------------------- The rules.


# One `git show <sha>:<ledger>` per (repo, COMMIT), not per box. The 33-plan wave this gate was built for carries several boxes each, and one plan's boxes were almost always ticked in the same ledger regeneration -- so without this the gate pays a git process per box to read the same blob back.
#
# THE ROOT IS PART OF THE KEY. `main()` runs `selftest()` against a throwaway fixture repo BEFORE it judges the real tree, through this same module-level
# dict. Keying on the commit alone would let a fixture sha answer for a real one;
# collisions are not realistic, but "not realistic" is a worse reason than "cannot happen", and the second costs one tuple.
_LEDGER_CACHE = {}


def ledger_at(root, commit):
    key = (str(root), commit)
    if key not in _LEDGER_CACHE:
        _LEDGER_CACHE[key] = R.ledger_at(root, commit)
    return _LEDGER_CACHE[key]


def legacy_path_of(root, rel):
    """The pre-move path of `rel`, proved by the stub sitting there, or "".

    A stub is the only evidence a move happened that survives into a checkout: `git log` does not follow the rename, and the old path is still OCCUPIED, so nothing else can tell a move from an unrelated file of the same name. The pointer is read and required to name `rel` exactly.
    """
    if not PL.is_plan_path(rel) or PL.folder_of(rel) == PL.AGENT_DIR:
        return ""
    origin = "%s/%s" % (PL.AGENT_DIR, rel.rsplit("/", 1)[-1])
    try:
        probe = (root / origin).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if not PL.looks_like_stub(probe) or PL.parse_plan(origin, probe).moved_to != rel:
        return ""
    return origin


def attested_under_any_path(root, ledger, rel, sig):
    """R4's lookup, under every path this record has ever had.

    A COMMITTED LEDGER IS KEYED BY THE PATH THE PLAN HAD AT THAT COMMIT. The tree-lifecycle move re-keys the current ledger and cannot re-key the historical ones, so without this every `done=` proof in the corpus reads as asserted-and-absent on the day the plans move -- 21 of them did, measured 2026-09-21. The fallback is the stub, not the basename, so it cannot admit a proof
    belonging to a different document.

    THE STUB IS NOT THE ONLY SURVIVING WITNESS. `names_this_record` already falls through to `_named_by_git_history` once a stub is gone (the 2026-09-22 cleanup retired the whole flat-stub class on that premise); this function did not get the same fallback, so a `done=` proof recorded under a pre-move path went back to reading as asserted-and-absent the moment its stub was
    retired, which is the same failure this function exists to prevent, just delayed. `_former_paths_by_git_history` asks git's own rename graph for every name `rel` has ever had and tries the ledger under each.
    """
    if R.attested_at(ledger, rel, sig):
        return True
    origin = legacy_path_of(root, rel)
    if origin and R.attested_at(ledger, origin, sig):
        return True
    return any(
        R.attested_at(ledger, former, sig) for former in _former_paths_by_git_history(root, rel)
    )


def names_this_record(root, rel, path):
    """Whether a `Full-Text:` path names THIS record, directly, through its stub, or through git's own rename history once the stub is gone.

    A record keeps its plan's path precisely so citations resolve, and the tree-lifecycle move keeps that promise with a STUB at the old path rather than with the path itself.
    The pointer is NOT re-spelled at the move: the commit it names carries the text at the OLD path, so `agent/plans/...` would make R2's `git rev-parse <sha>:<path>` resolve to nothing and turn a correct record into a red one.

    The stub is READ rather than assumed. A bare legacy path with no pointer back is still somebody else's document, which is the case R1's third control plants.

    A stub that has since been DELETED -- the 2026-09-22 cleanup retired the whole one-time class of flat-layout stubs left by `fce51e202` and `a81967e94` -- falls through to `_named_by_git_history`, which asks git's own rename graph the same question the stub used to answer on disk.
    """
    if path == rel:
        return True
    try:
        probe = (root / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return _named_by_git_history(root, rel, path)
    return PL.looks_like_stub(probe) and PL.parse_plan(path, probe).moved_to == rel


def _named_by_git_history(root, rel, path):
    """Whether `path` is a git-tracked former name of `rel`.

    For when the stub that used to assert this on disk (`Status: moved` / `Moved-To:`) has since been deleted.
    `git log --follow` walks the rename graph through the deletion just as reliably as through a live stub -- `agent/plans/PLAN-lint-css-ci-wiring.md`'s own history shows a `C099` copy from `agent/PLAN-lint-css-ci-wiring.md` at `fce51e202`, so this recovers exactly what the stub used to assert without needing it to still exist.
    Returns `False` on anything git cannot answer (no repo, no history, no match) rather than guessing.
    """
    return path in _follow_names(root, rel)


def _former_paths_by_git_history(root, rel):
    """{str} -- every git-tracked former name of `rel`, `rel` itself excluded.

    The reverse of `_named_by_git_history`'s question: instead of "was `path` once this file's name", this asks "what were ALL of this file's names". Same `--follow` walk, same fallback role -- for when the stub `attested_under_any_path` would otherwise read through has been deleted.
    """
    return set(_follow_names(root, rel)) - {rel}


@functools.cache
def _follow_names(root, rel):
    """frozenset -- every name `git log --follow` reports for `rel`, walked ONCE per path.

    The walk is the whole cost of this gate: profiled 2026-09-24 at 517s wall, 223s of it in 131 calls to `_former_paths_by_git_history` and 47s in 35 to `_named_by_git_history`, the same `--follow` walk repeated for the same plan because `problems_for` runs once in the verdict and again in `census_row`. The history cannot change during one run, so one walk per path answers every later ask.
    """
    names = _git(root, "log", "--follow", "--name-only", "--format=", "--", rel)
    return frozenset(line.strip() for line in names.splitlines() if line.strip())


def problems_for(root, rel, text, current_ledger):
    """[str] -- every rule this one record breaks. Empty means it holds.

    `current_ledger` is passed in rather than read per record: R4's second direction consults it once per box, and re-reading a 40 KB JSON file for each of them is how a gate over 81 plans becomes the slowest step in its lane.
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
        elif not names_this_record(root, rel, path):
            out.append(
                "%s: Full-Text names path %s, which is neither this record's own path nor "
                "a stub pointing back at it. A record keeps its plan's path precisely so "
                "citations still resolve; pointing elsewhere silently breaks that" % (rel, path)
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
            # THE SECOND DIRECTION, and it is what stops `abandoned` being a dodge. If the current ledger attests this signature, a proof was available and the record declined to use it.
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
        elif not attested_under_any_path(root, ledger, rel, sig):
            out.append(
                "%s: box %r records `done=%s`, and the ledger AT THAT COMMIT does not carry "
                "signature %s under done_sigs for %s. The proof is asserted, not present"
                % (rel, b["body"][:60], done, sig, rel)
            )

    # ---- R5 `(record)` inside a box line ---------------------------------- rec["problems"] already carries this one -- parse() finds it while it has the raw line in hand, which is the only place the distinction between "in the box" and "on the annotation line" still exists. Folded in at the top.

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


def index_problems(root, rows, census="", update=False):
    """R8. `agent/INDEX.md` is a second reading of the records, so it is checked
    for EQUALITY rather than for containment: a stale row is exactly as wrong as
    a missing one, and only equality catches both.

    An EMPTY render means "no records", and an ABSENT file is equal to it. A repo
    with nothing compacted must not be forced to carry a generated table that
    says nothing -- that is the committed-lie shape `agent/README.md:11` names.

    W12 P1.7: `census` IS THE SECOND HALF OF THE SAME FILE, and it is checked by the same equality for the same reason. `wl_planindex` renders a `## Plan census` section that SessionStart reads INSTEAD of opening all 83 plans; the hook's own freshness check is `stat` only (path set plus byte size), so a plan edited to the same length is invisible to it. This byte-equality against a
    full re-read is the half that catches that, which is the only reason the hook is allowed to trust the file at all.

    It defaults to "" so the R8 controls below, which run in a fixture whose plan set is not the one being censused, keep comparing exactly what they always compared. Only the real-tree call site at the bottom passes a census.
    """
    want = R.render_index(rows) + census
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
        # ZERO RECORDS, NO CENSUS, AND A NON-EMPTY INDEX. `--update` deliberately does NOT "fix" this by truncating the file: nothing in this program deletes a committed document, and an --update that silently emptied one would be the first. It is reported in both modes, with the removal left to a person who can see what the file still claims.
        #
        # Since W12 P1.7 this branch is only reachable when there are no plans EITHER, because any plan at all renders a census and makes `want` non-empty. That is the correct narrowing: an index over a tree with no plans and no records really is a document that says nothing.
        return [
            (
                f"{R.INDEX_REL} exists ({len(got)} bytes) but there are no compacted or "
                f"parked records to index. Every record it names has been revived or "
                f"removed. Delete the file by hand -- `--update` will not truncate a "
                f"committed document."
            )
        ]
    # THE CENSUS IS NAMED SEPARATELY. Once agent/INDEX.md carries both tables, a message about "the records on disk" sends the reader to look at the record table when the drift is almost always in the census: 83 plans change far more often than a handful of compaction records do, and SessionStart is what reads the census. Saying "0 record(s)" and nothing else is how a correct
    # verdict gets dismissed as a stale gate.
    n_census = len(PI.parse_census(census)) if census else 0
    return [
        (
            f"{R.INDEX_REL} disagrees with what is on disk "
            f"({len(got)} bytes present, {len(want)} bytes derived from "
            f"{len(rows)} record(s) and {n_census} plan census row(s)). "
            f"SessionStart reads the census section, so a stale one puts every "
            f"session on the slow fallback. Regenerate and commit it:\n"
            f"      npm run check:ci-plan-record -- --update\n"
            f"      git add {R.INDEX_REL}"
        )
    ]


# ---------------------------------------------------------------------------
# THE ADVISORY CENSUS. Nothing below reaches a verdict about a record; the only way any of it changes an exit code is by FAILING TO RECORD, which is exit 2.


def _prior_record_text(root, rel, current):
    """The newest COMMITTED version of `rel` that parses as a record and differs
    from the bytes on disk, or "".

    NOT `HEAD~1` and not the merge-base, and both alternatives were measured before this one was chosen. The merge-base yields ZERO comparable pairs on this branch today: all 32 records were compacted after it, so at the base every one of them is still a plain plan and C9 would have had nothing to say
    while looking exactly as green as a clean corpus. `HEAD~1` is wrong the other
    way -- a record untouched for twenty commits has no diff there either.

    "The previous version that was already a record" is the comparison the append-only convention actually makes, and it is topology-independent: it answers the same on a branch, on main, and in a working tree with uncommitted edits (the identity skip below is what covers that last case -- when nothing is modified, HEAD's own blob IS the bytes on disk and is stepped over).
    """
    # A SEARCH BOUND, NOT A FLOOR (driver contract section 6 governs floors, and this is not one). Exhausting it yields SILENCE, which is a false negative in an advisory census rather than a false red -- the safe direction. It is 100 rather than a handful because of the revive path: a record revived back into a plan, edited for a week and re-compacted has every one of those plan
    # commits sitting between the two record versions, and a tight cap would stop before reaching the baseline exactly when C9 has the most to say.
    log = _git(root, "log", "--format=%H", "--", rel)
    for sha in log.split()[:100]:
        blob = _git_raw(root, "show", "%s:%s" % (sha, rel))
        if not blob or blob == current:
            continue
        if R.parse(blob) is not None:
            return blob
    return ""


_BLOB_INDEX: dict[str, dict[str, list[str]]] = {}


def _commits_touching_blob(root, blob):
    """The newest 20 commits (all refs) whose diff adds or removes `blob`: `git log --all --find-object=<blob> -20`, answered from ONE history walk.

    Profiled 2026-09-24: the census spent 178s of the gate's 222s in 84 `--find-object` walks, one per record, and quality-branch was cancelled at its 12-minute limit with this gate still running. `git log --all --raw -r --no-abbrev` lists every non-merge commit's old and new blob ids in about a second here, newest first, so indexing it once answers every record. Merges are skipped by both forms alike, because `git log` diffs no merge by default.
    """
    key = str(root)
    if key not in _BLOB_INDEX:
        index: dict[str, list[str]] = {}
        sha = ""
        raw = _git(
            root, "log", "--all", "--format=C %H", "--raw", "-r", "--no-abbrev", "--no-renames"
        )
        for line in raw.splitlines():
            if line.startswith("C "):
                sha = line[2:].strip()
                continue
            if not line.startswith(":"):
                continue
            parts = line.split()
            for obj in {parts[2], parts[3]}:
                hits = index.setdefault(obj, [])
                if len(hits) < 20 and (not hits or hits[-1] != sha):
                    hits.append(sha)
        _BLOB_INDEX[key] = index
    # `Full-Text-Blob:` is written as the full 40-hex id (`git hash-object`), which is the form `--raw --no-abbrev` indexes, so no rev-parse is needed to match it.
    return list(_BLOB_INDEX[key].get(blob, []))


def candidate_findings(root, rel, text):
    """[(candidate_id, detail)] -- what a future BLOCKING rung would refuse about this one record. Advisory by construction: the caller records it and does not branch on it."""
    rec = R.parse(text)
    if rec is None:
        return []
    out = []

    # ---- C9 history append-only -----------------------------------------
    prior = _prior_record_text(root, rel, text)
    if prior:
        was = [ln.strip() for ln in (R.parse(prior) or {}).get("history", [])]
        now = [ln.strip() for ln in rec["history"]]
        if now[: len(was)] != was:
            # WHICH bullet broke it, not just that one did. A count alone sends the reader to `git log -p` on a 30 KB file to find out whether a line was deleted or reworded, and those are different defects.
            lost = [b for b in was if b not in now]
            out.append(
                (
                    "C9-history-append-only",
                    "%d bullet(s) before, %d now; the old list is not a prefix of the new "
                    "one. First bullet no longer present: %s"
                    % (
                        len(was),
                        len(now),
                        (lost[0][:110] if lost else "(all still present, but reordered)"),
                    ),
                )
            )

    # ---- C10 a parked record still carrying a placeholder ----------------
    if rec["status"] == R.STATUS_PARKED:
        hits = sorted(set(R.PLACEHOLDER_RE.findall(text)))
        if hits:
            out.append(
                (
                    "C10-parked-placeholder",
                    "%d distinct placeholder(s): %s" % (len(hits), ", ".join(hits[:3])),
                )
            )

    # ---- C11 the Full-Text upgrade that never happened -------------------
    if rec["blob"] and not rec["full_text_sha"]:
        # EVERY COMMIT THAT TOUCHED THE BLOB, not just the newest, and the difference is not a refinement. `--find-object` matches ADDITIONS and DELETIONS alike, so the newest hit for a compacted plan is usually the commit that REMOVED the plan text -- which may sit on an unmerged branch. Taking `-1` therefore answered "not landed" for a blob that landed twenty commits ago; the
        # fixture caught it on the first run.
        carried = _commits_touching_blob(root, rec["blob"])
        for sha in carried:
            ok, _why = R.resolve(root, "ancestor", sha)
            if ok:
                out.append(
                    (
                        "C11-fulltext-upgrade",
                        "blob %s is carried by landed commit %s and no `Full-Text:` line "
                        "names it" % (rec["blob"][:12], sha[:9]),
                    )
                )
                break
    return out


def census_row(root, recs):
    """One row of the census: what the candidates would refuse across the WHOLE corpus, right now.

    `recs` is the gate's own `[(rel, status, lines)]` enumeration. The statuses and the file bytes are RE-READ here rather than taken from the verdict loop, so the two counts `census_append` compares are genuinely two readings.
    """
    flagged = {cid: [] for cid in CANDIDATES}
    by_status = {}
    n_records = 0
    for rel, _status, _lines in recs:
        try:
            text = (pathlib.Path(root) / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rec = R.parse(text)
        st = rec["status"] if rec else "not-a-record"
        by_status[st] = by_status.get(st, 0) + 1
        if rec is None:
            continue
        n_records += 1
        for cid, detail in candidate_findings(root, rel, text):
            flagged[cid].append({"plan": rel, "detail": detail})

    return {
        "ts": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": _git(root, "rev-parse", "HEAD")[:9],
        "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD"),
        "plans_examined": len(recs),
        "records_examined": n_records,
        "by_status": dict(sorted(by_status.items())),
        "would_refuse": sum(len(v) for v in flagged.values()),
        "candidates": {cid: flagged[cid] for cid in sorted(flagged)},
    }


def census_rows(path):
    """Every well-formed row in one census file. A truncated last line is skipped rather than fatal: the file is appended to by concurrent runs in a shared checkout, and losing a verdict over a half-written byte would be the wrong trade for a log whose whole job is to keep accumulating."""
    out = []
    try:
        raw = pathlib.Path(path).read_text(encoding="utf-8")
    except OSError:
        return out
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("ts"):
            out.append(row)
    return out


# The row fields that carry an OBSERVATION. `ts` is deliberately absent: two runs minutes apart over an unchanged tree observe the same thing, and the clock is not the observation.
CENSUS_PAYLOAD_KEYS = ("commit", "plans_examined", "records_examined", "by_status", "candidates")


def census_is_same_day_repeat(last, row):
    """True when `row` observes exactly what `last` observed, ON THE SAME UTC DAY.

    WHY THE FILE IS NOT APPENDED TO ON EVERY SINGLE RUN, stated where the deviation is rather than in a report nobody re-reads. The census file is TRACKED, and three things in this repo react to a modified tracked file: the battery runner's clean-tree guard fails the whole gate battery on one, `wl_git.py`'s `dirt_verdict` counts it as uncommitted real work and blocks the stop
    hook's rebase path, and nothing anywhere caps the size of an append-only file. A row per invocation would put a permanently-dirty file in a shared checkout and grow without bound, and the operator would learn to `git checkout` it -- which is how the two-week window quietly gets reset.

    THE COLLAPSE IS PER UTC DAY, NOT PER PAYLOAD, and that boundary is the load- bearing part. Collapsing on the payload alone would let a tree that does not change for a fortnight record ONE row, and `--census-report` would then compute a span of zero days over a window that really had elapsed. A day boundary always breaks the tie, so the file gains at least one row for every day
    the gate ran, which is exactly what the span is derived from.
    """
    if not last:
        return False
    if str(last.get("ts", ""))[:10] != row["ts"][:10]:
        return False
    return all(last.get(k) == row.get(k) for k in CENSUS_PAYLOAD_KEYS)


def census_append(root, row, expect_plans, expect_records):
    """Record `row`, then READ IT BACK. (ok, message).

    THE FLOORS ARE SET-BASED, and there are four, because an advisory check has no verdict of its own to notice when it stops working:

      1. The census's own plan and record counts must EQUAL the verdict loop's.
         Two readings of the corpus, not one number trusted twice. A glob that
         collapsed, or a `parse()` that started returning None for everything,
         moves one and not the other.
      2. The corpus must be non-empty. `MIN_PLAN_FILES` already refuses before
         this is reached, so this is the belt to those braces -- and it is stated
         over the PLANS, never over the records, for the reason `MIN_PLAN_FILES`
         gives: zero records is a legitimate tree, so a floor on records would be
         a floor that cannot be met.
      3. On an append, the file must hold MORE rows after than before. Not "the
         write did not raise": an append to a path something else truncates, and
         a row that fails to serialise, both raise nothing useful.
      4. On a same-day repeat, where there is deliberately no append, the file
         must ALREADY end with a row whose payload equals this run's. That is a
         stronger read-back than the append path has, and it is what stops the
         collapse from becoming the vacuity hatch: "nothing was written" is only
         acceptable while the thing that would have been written is provably
         already there.
    """
    if row["plans_examined"] != expect_plans or row["records_examined"] != expect_records:
        return False, (
            "CENSUS DISAGREES WITH THE VERDICT: the census read %d plan(s) and %d "
            "record(s); the verdict loop read %d and %d. Two readings of one corpus "
            "returned different sets, so one of them is reading something that is not "
            "there -- and a census over the wrong corpus is worse than none, because "
            "the two-week window would still elapse."
            % (row["plans_examined"], row["records_examined"], expect_plans, expect_records)
        )
    if row["plans_examined"] == 0:
        return False, (
            "VACUOUS CENSUS: 0 plan file(s). A row recording nothing looks exactly like "
            "a row recording a clean corpus, and the window would elapse on rows that "
            "measured nothing."
        )

    path = pathlib.Path(root) / CENSUS_REL
    have = census_rows(path)
    last = have[-1] if have else None
    every_run = os.environ.get("PLAN_RECORD_CENSUS_EVERY_RUN") == "1"

    if not every_run and census_is_same_day_repeat(last, row):
        # FLOOR 4. Re-read from disk rather than trusting `have`, so a file truncated between the two reads is caught rather than assumed away.
        back = census_rows(path)
        if not back or not all(back[-1].get(k) == row.get(k) for k in CENSUS_PAYLOAD_KEYS):
            return False, (
                "CENSUS NOT RECORDED: %s was judged to already hold today's observation "
                "and does not. Nothing was appended and nothing is on disk, which is the "
                "exact shape of an advisory check that silently stopped measuring." % CENSUS_REL
            )
        return True, (
            "✓ census: %s already carries this observation for %s (%d row(s); %d "
            "record(s) examined, %d would be refused). No row appended -- the file is "
            "tracked, and a row per invocation would leave it permanently modified. "
            "Set PLAN_RECORD_CENSUS_EVERY_RUN=1 to force one."
            % (CENSUS_REL, row["ts"][:10], len(back), row["records_examined"], row["would_refuse"])
        )

    before = len(have)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # A TRAILING NEWLINE ON EVERY ROW IS NOT COSMETIC. the editorconfig gate walks `git ls-files` extension-blind and fails any tracked file that does not end with one, so a writer that omitted it on the last row would red a whole-tree gate that has nothing to do with plan records.
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    except (OSError, TypeError, ValueError) as exc:
        return False, "CENSUS NOT RECORDED: cannot append to %s (%s)" % (CENSUS_REL, exc)

    after = census_rows(path)
    if len(after) <= before:
        return False, (
            "CENSUS NOT RECORDED: %s held %d row(s) before the append and %d after. The "
            "write reported success and the file did not grow." % (CENSUS_REL, before, len(after))
        )
    return True, (
        "✓ census: row %d appended to %s at %s -- %d record(s) examined, %d would be "
        "refused by the candidate rules (%s). Nothing WAS refused; run "
        "`npm run check:ci-plan-record -- --census-report` for the window."
        % (
            len(after),
            CENSUS_REL,
            row["ts"],
            row["records_examined"],
            row["would_refuse"],
            ", ".join(
                "%s=%d" % (cid.split("-")[0], len(v))
                for cid, v in sorted(row["candidates"].items())
            ),
        )
    )


def census_report(root, out=sys.stdout, err=sys.stderr):
    """Answer, FROM THE ROWS ALONE: has the two-week window elapsed, and what would have been refused across it. 0 green, 1 when there is nothing to read.

    The elapsed span is derived from the recorded `ts` values, which is the whole reason a timestamp is on every row. Nothing here consults the clock for anything but "now", and nothing consults anyone's memory of when the census started.
    """
    files = sorted((pathlib.Path(root) / CENSUS_DIR).glob(CENSUS_GLOB))
    rows = []
    for f in files:
        rows.extend(census_rows(f))
    if not rows:
        print(
            "VACUOUS CENSUS: no rows in %s (%d file(s) globbed). There is nothing to "
            "report a window over; the census has not run, or its file was removed."
            % (str(pathlib.Path(root) / CENSUS_DIR / CENSUS_GLOB), len(files)),
            file=err,
        )
        return 1

    def when(row):
        return datetime.datetime.strptime(row["ts"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.UTC
        )

    rows.sort(key=when)
    first, last = when(rows[0]), when(rows[-1])
    span = (last - first).total_seconds() / 86400.0
    elapsed = span >= CENSUS_WINDOW_DAYS

    print(
        "plan-record advisory census: %d row(s) across %d file(s)" % (len(rows), len(files)),
        file=out,
    )
    print("  first row  %s" % rows[0]["ts"], file=out)
    print("  last row   %s" % rows[-1]["ts"], file=out)
    print(
        "  span       %.2f day(s) of %d -- window %s"
        % (span, CENSUS_WINDOW_DAYS, "ELAPSED" if elapsed else "NOT yet elapsed"),
        file=out,
    )
    if not elapsed:
        print(
            "  %.2f more day(s) of rows before a blocking rung may be proposed."
            % (CENSUS_WINDOW_DAYS - span),
            file=out,
        )

    total = 0
    for cid in sorted(CANDIDATES):
        runs = [r for r in rows if r.get("candidates", {}).get(cid)]
        plans = sorted({h["plan"] for r in runs for h in r["candidates"][cid]})
        total += len(plans)
        print(
            "\n  %s -- fired in %d of %d run(s), naming %d distinct plan(s)"
            % (cid, len(runs), len(rows), len(plans)),
            file=out,
        )
        print("      would refuse: %s" % CANDIDATES[cid], file=out)
        for pl in plans:
            print("      - %s" % pl, file=out)
        if not plans:
            print(
                "      - nothing, across every recorded row. A rung that refuses nothing "
                "is CHEAP to turn on, not pointless: this is the evidence for that.",
                file=out,
            )
    print(
        "\n  %d distinct plan(s) would be refused in total if all three rungs blocked today."
        % total,
        file=out,
    )
    return 0


# --------------------------------------------------------------------------- CONTROL FIRST. Every verdict above is meaningless if these do not fire, so the fixture is a REAL git repository with a real origin/main, a real ledger and a real blob. Nothing here is mocked: R1's ancestor test, R2's `rev-parse <sha>:<path>` and R4's `git show <sha>:<ledger>` are the rules most likely to
# be satisfied by a stub while being broken against git.


def _run(cwd, *args):
    subprocess.run(args, cwd=str(cwd), check=True, capture_output=True, text=True)


def build_fixture(td):
    """A tiny repo carrying one plan, one ledger commit, and a `main` to be an ancestor of. Returns (root, rel, record_text).

    BUILT BY CONSTRUCTION, not by substituting into a copy of the real tree. `check-control-vacuity.sh` exempts construction for exactly this reason: a fixture assembled from known-bad parts cannot fail to contain the defect, whereas a substitution can silently miss and leave a control that proves the clean case twice.
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

    # TWO LEDGER COMMITS, and the shape is the point rather than a convenience. The first has the box still OPEN, the second attests the tick. That is what makes R4 testable at all: a single-commit fixture has no commit whose ledger lacks the signature, so the "asserted, not present" plant cannot be built and the control silently proves nothing. It also exercises the oldest-first
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
    # A remote-tracking ref so the `ancestor` resolver has an origin/main to answer against, without a network or a second repository.
    _run(root, "git", "update-ref", "refs/remotes/origin/main", "HEAD")

    text, _notes = R.compact(root, rel, "deadbeef", why="auto", park=True)
    return root, rel, text, before


def selftest():
    """Plant ONE defect per rule, require the matching finding, and require the clean record to stay SILENT. The silent case is not a formality: "every fixture reds" is a check that cannot pass, and it is the shape a gate takes on when a refactor breaks its parser."""
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

        def expect_finding(label, text, needle):
            g = judge(text)
            hit = any(needle in p for p in g)
            ck(label, hit, f"needle {needle!r} not in {g}")

        # R1a: a blob that does not exist.
        expect_finding(
            "R1: an unresolvable Full-Text-Blob is reported",
            plant(clean, "Full-Text-Blob: " + rec["blob"], "Full-Text-Blob: " + "0" * 40),
            "does not resolve to a blob",
        )
        # R1b: a commit that is not an ancestor of origin/main. An all-zero sha is not a commit at all, which is the same rule's other exit.
        expect_finding(
            "R1: a Full-Text commit that does not resolve is reported",
            plant(
                clean,
                "Full-Text: %s %s" % (rec["full_text_sha"], rel),
                "Full-Text: 0123456ab %s" % rel,
            ),
            "Full-Text names commit",
        )
        # R1c: the pointer names someone else's path.
        expect_finding(
            "R1: a Full-Text path that is not the record's own is reported",
            plant(
                clean,
                "Full-Text: %s %s" % (rec["full_text_sha"], rel),
                "Full-Text: %s agent/PLAN-elsewhere.md" % rec["full_text_sha"],
            ),
            "neither this record's own path",
        )
        # R1c MIRROR: the same pointer, through the STUB a tree-lifecycle move leaves behind. Only R1's needle is asserted absent, because the fixture's commit does not carry the text at the legacy path and R2 therefore fires on its own account.
        legacy = "agent/PLAN-legacy-fixture.md"
        (root / legacy).write_text(PL.stub_text(legacy, rel, "fixture"), encoding="utf-8")
        through_stub = judge(
            plant(
                clean,
                "Full-Text: %s %s" % (rec["full_text_sha"], rel),
                "Full-Text: %s %s" % (rec["full_text_sha"], legacy),
            )
        )
        ck(
            "R1 CONTROL: a Full-Text path whose stub points back at this record is accepted",
            not any("own path" in p for p in through_stub),
            f"got {through_stub}",
        )
        (root / legacy).unlink()

        # R1 THROUGH GIT HISTORY, no stub on disk at all -- the exact shape the 2026-09-22 flat-stub cleanup leaves behind: a plan git-renamed out of a flat path into agent/plans/, and the flat-path stub since deleted with nothing left to read there.
        # Isolated in its own tiny repo rather than mutated into the shared fixture, so it cannot perturb `rel`'s own commit history for every rule that runs after it.
        with tempfile.TemporaryDirectory() as td2:
            hroot = pathlib.Path(td2) / "hist"
            (hroot / "agent").mkdir(parents=True)
            _run(hroot, "git", "init", "-q", "-b", "main")
            _run(hroot, "git", "config", "user.email", "fixture@example.invalid")
            _run(hroot, "git", "config", "user.name", "fixture")
            gone = "agent/PLAN-legacy-history.md"
            survivor = "agent/plans/PLAN-legacy-history.md"
            (hroot / gone).write_text("placeholder\n", encoding="utf-8")
            _run(hroot, "git", "add", "-A")
            _run(hroot, "git", "commit", "-qm", "fixture: at the flat path")
            (hroot / "agent" / "plans").mkdir(parents=True, exist_ok=True)
            _run(hroot, "git", "mv", gone, survivor)
            _run(
                hroot,
                "git",
                "commit",
                "-qm",
                "fixture: moved into agent/plans/, stub since deleted",
            )
            ck(
                "R1 CONTROL: a Full-Text path whose stub is gone but git rename history confirms it is accepted",
                names_this_record(hroot, survivor, gone),
            )
            ck(
                "R1 CONTROL: an absent path with no git rename history at all is still refused",
                not names_this_record(hroot, survivor, "agent/PLAN-never-existed.md"),
            )
            # R4 THROUGH GIT HISTORY, same fixture, same stub-since-deleted shape: a proof recorded under `gone` before the move must still be found once `survivor` is the only name left on disk.
            hist_ledger = {"plans": {gone: {"done_sigs": ["deadbeef"]}}}
            ck(
                "R4 CONTROL: a proof recorded under a pre-move path is found through git history once the stub is gone",
                attested_under_any_path(hroot, hist_ledger, survivor, "deadbeef"),
            )
            ck(
                "R4 CONTROL: a signature nothing attests is still not found through git history",
                not attested_under_any_path(hroot, hist_ledger, survivor, "0badbeef"),
            )

        # R4 THROUGH THE STUB, both directions. A committed ledger is keyed by the path the plan had at that commit, so without the hop the migration turns every `done=` proof in the corpus into "asserted, not present" on the day it lands.
        moved_rel = "agent/plans/PLAN-moved-fixture.md"
        legacy_rel = "agent/PLAN-moved-fixture.md"
        (root / "agent" / "plans").mkdir(parents=True, exist_ok=True)
        (root / moved_rel).write_text(clean, encoding="utf-8")
        (root / legacy_rel).write_text(
            PL.stub_text(legacy_rel, moved_rel, "fixture"), encoding="utf-8"
        )
        old_ledger = {"plans": {legacy_rel: {"done_sigs": ["abcd1234"]}}}
        ck(
            "R4: a proof recorded under the pre-move path is found through the stub",
            attested_under_any_path(root, old_ledger, moved_rel, "abcd1234"),
        )
        ck(
            "R4 CONTROL: a signature nothing attests is still not found",
            not attested_under_any_path(root, old_ledger, moved_rel, "0badbeef"),
        )
        (root / legacy_rel).unlink()
        ck(
            "R4 CONTROL: with no stub at the old path the legacy proof does not count",
            not attested_under_any_path(root, old_ledger, moved_rel, "abcd1234"),
        )
        (root / moved_rel).unlink()
        # R2: the commit is real and landed, and carries DIFFERENT bytes. Built by pointing Full-Text-Blob at the LEDGER's blob, which resolves (so R1 passes) and is not the plan's (so only R2 can fire).
        other = _git(root, "rev-parse", "HEAD:" + R.LEDGER_REL)
        expect_finding(
            "R2: a real blob that is not the one at <sha>:<path> is reported",
            plant(clean, "Full-Text-Blob: " + rec["blob"], "Full-Text-Blob: " + other),
            "One of the two pointers names bytes the other does not",
        )
        # R3 floor: point at a blob smaller than the record. The ledger blob is small, so the same substitution serves -- and its R2 finding is a different string, so the two rules stay separately observable.
        expect_finding(
            "R3: a blob smaller than the record is reported as nothing compacted",
            plant(clean, "Full-Text-Blob: " + rec["blob"], "Full-Text-Blob: " + other),
            "Nothing was compacted",
        )
        # R3 ceiling: an oversized record.
        expect_finding(
            "R3: a record over its byte budget is reported",
            plant(clean, "## Why\n", "## Why\n" + ("x" * 80 + "\n") * 200, 1),
            "against a budget of",
        )
        done_line = next(
            ln
            for ln in clean.splitlines()
            if "(record)" in ln and "done=" in ln and "open" not in ln
        )
        # THE OLDEST-FIRST WALK, asserted before the plants that depend on it.
        # `done=` must name the commit that FIRST attested the tick, which is the
        # second of the two. Naming the newest instead would be a date with no meaning -- the ledger is rewritten wholesale by --update, so every signature in it appears in every later commit.
        ck(
            "CONTROL: done= names the FIRST attesting commit, not the newest",
            R.sha9(_git(root, "rev-parse", "HEAD")) in done_line
            and R.sha9(before) not in done_line,
            f"done_line={done_line!r} before={R.sha9(before)}",
        )
        # R4a: done= names a real, landed commit whose ledger does NOT attest the
        # signature -- the commit from before the box was ticked.
        expect_finding(
            "R4: a done= commit whose ledger does not attest the signature is reported",
            plant(
                clean,
                done_line,
                "    (record) sig=%s done=%s" % (rec["boxes"][0]["sig"], R.sha9(before)),
            ),
            "does not carry signature",
        )
        # R4b: `abandoned` while the current ledger holds the proof.
        expect_finding(
            "R4: `abandoned` over a signature the ledger attests NOW is reported",
            plant(clean, done_line, "    (record) sig=%s done=abandoned" % rec["boxes"][0]["sig"]),
            "a proof exists",
        )
        # R4c: the mark and the claim disagree.
        expect_finding(
            "R4: a ticked box recording done=open is reported",
            plant(clean, done_line, "    (record) sig=%s done=open" % rec["boxes"][0]["sig"]),
            "The mark and the claim disagree",
        )
        # R5: the annotation moved INSIDE the box line.
        box_line = next(ln for ln in clean.splitlines() if ln.startswith("- [x] "))
        expect_finding(
            "R5: `(record)` inside a box line is reported",
            plant(clean, box_line, box_line + " (record)"),
            "carries `(record)` inside it",
        )
        # R6: a placeholder under `compacted`. The fixture is `parked` (it has an open box), so the status is flipped as part of the plant -- which is also the control for `parked` being EXEMPT, asserted straight after.
        with_ph = plant(clean, "## Why\n", "## Why\n" + R.placeholder("why") + "\n", 1)
        expect_finding(
            "R6: an unfilled placeholder under `compacted` is reported",
            plant(with_ph, "Status: parked", "Status: compacted", 1),
            "unfilled placeholder",
        )
        g = judge(with_ph)
        ck(
            "R6 CONTROL: the same placeholder under `parked` is NOT reported",
            not any("unfilled placeholder" in p for p in g),
            f"got {g}",
        )
        # R7: a hand-edited spine.
        expect_finding(
            "R7: a Record-Sig that does not match the spine is reported",
            plant(clean, "Record-Sig: " + rec["record_sig"], "Record-Sig: 00000000"),
            "hashes to",
        )
        # R7 CONTROL: editing PROSE must NOT move the signature, or the record becomes un-editable and people work around it instead of using it.
        edited = plant(clean, "## Lessons\n", "## Lessons\n- a sharpened lesson\n", 1)
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

        # R8 CENSUS (W12 P1.7), both directions. The census is the half of agent/INDEX.md that SessionStart reads instead of opening every plan, and the hook's own freshness check is `stat` only. So this equality is the ONLY thing standing between a plan edited to the same byte length and a session reading a confidently wrong number. A control that only proved the matching case
        # would leave that unproven.
        cen = PI.render_census(PI.census_rows(root))
        ck(
            "R8 CENSUS CONTROL: the fixture renders a non-empty census naming the plan",
            PI.CENSUS_SECTION in cen and rel in cen,
            f"{cen[:160]!r}",
        )
        # THE PERTURBATION IS ASSERTED TO BE ONE. `str.replace` over a pattern that is not there is a no-op, and a "stale census" that is byte-identical to the fresh one would make the next control pass for the wrong reason.
        drifted = cen.replace("| %d |" % len(cen.splitlines()), "| 99999 |", 1)
        if drifted == cen:
            drifted = cen.replace(f"`{rel}`", "`agent/PLAN-not-on-disk.md`", 1)
        ck(
            "R8 CENSUS CONTROL: the perturbation actually changes the census text",
            drifted != cen,
            "the drifted census is byte-identical to the fresh one",
        )
        R.write_atomic(root / R.INDEX_REL, R.render_index(rows) + cen)
        ck(
            "R8 CENSUS CONTROL: an index carrying the matching census is silent",
            index_problems(root, rows, census=cen) == [],
            f"got {index_problems(root, rows, census=cen)}",
        )
        ck(
            "R8 CENSUS: an index whose census disagrees with the plans is reported",
            index_problems(root, rows, census=drifted) != [],
            "a drifted census was accepted",
        )
        # AND THE MISSING-CENSUS DIRECTION. An index that still carries only the record table, once a census is due, is exactly as wrong as a stale one: the hook would read CENSUS_ABSENT and fall back forever.
        R.write_atomic(root / R.INDEX_REL, R.render_index(rows))
        ck(
            "R8 CENSUS: an index carrying NO census when one is due is reported",
            index_problems(root, rows, census=cen) != [],
            "an index with no census section was accepted",
        )
        (root / R.INDEX_REL).unlink()

        # THE ANTI-VACUITY CONTROL FOR THE WHOLE GATE: a plain plan is not a record and must produce NOTHING. Without this, a parse() that returned a record for every file would look identical to a clean tree.
        ck(
            "CONTROL: the gate says nothing about a file that is not a record",
            judge("# P\nStatus: executing\n\n## Tasks\n- [ ] something entirely ordinary\n") == [],
        )

        # ------------------------------------------------------------------ THE ADVISORY CENSUS, both directions on every candidate.
        #
        # An advisory check is the easiest thing in the world to make vacuous: delete its call site and it reports exactly what a clean corpus reports, forever, while the two-week clock silently never starts. So every candidate is planted AND its negation is planted, and the recorder itself is driven through all four of its floors.
        #
        # THE RECORD IS COMMITTED FIRST, because C9's baseline is "the previous committed version that was already a record" and without a commit there is no baseline -- which would make both C9 controls pass by measuring nothing.
        (root / rel).write_text(clean, encoding="utf-8")
        _run(root, "git", "add", "-A")
        _run(root, "git", "commit", "-qm", "fixture: the plan is compacted into a record")

        def cand(text, at=rel):
            return {cid for cid, _d in candidate_findings(root, at, text)}

        hist_line = R.parse(clean)["history"][0]
        ck(
            "CENSUS CONTROL: the fixture record has a `## History` bullet to compare",
            hist_line.startswith("- ") and hist_line in clean,
            f"got {hist_line!r}",
        )
        ck(
            "CENSUS CONTROL: the previous committed version of the record is found",
            R.parse(_prior_record_text(root, rel, clean + "- later\n")) is not None,
            "no committed baseline; both C9 controls below would prove nothing",
        )

        # C9, the flagged direction: the bullet was REWRITTEN, not appended to. This is the exact shape three real records in agent/ are in -- a revive-and-re-compact replaces the single bullet rather than adding one.
        ck(
            "C9: a `## History` bullet rewritten since the last committed version is flagged",
            "C9-history-append-only" in cand(plant(clean, hist_line, hist_line + " EDITED", 1)),
        )
        # C9, the silent direction: a bullet APPENDED under the same first one.
        ck(
            "C9 CONTROL: APPENDING a bullet is not flagged (that is the convention working)",
            "C9-history-append-only"
            not in cand(clean + "- 2026-01-02T00:00:00Z revived and re-compacted\n"),
        )
        # C9's own vacuity control: with no committed baseline there is nothing to compare, and the candidate must stay SILENT rather than guess.
        ck(
            "C9 CONTROL: a record with no committed history is not flagged",
            "C9-history-append-only"
            not in cand(
                plant(clean, hist_line, hist_line + " EDITED", 1),
                at="agent/PLAN-never-committed.md",
            ),
        )

        # C10, both directions. The fixture is `parked` and `--why auto` left `<FILL: outcome>` and `<FILL: lessons>` in it -- which is precisely the state R6 EXEMPTS, and precisely what the candidate rung would stop exempting forever.
        ck(
            "C10: a `parked` record still carrying `<FILL:>` is flagged",
            "C10-parked-placeholder" in cand(clean),
        )
        ck(
            "C10 CONTROL: the same record with its placeholders written out is not flagged",
            "C10-parked-placeholder"
            not in cand(R.PLACEHOLDER_RE.sub("a paragraph a person wrote", clean)),
        )
        ck(
            "C10 CONTROL: placeholders under `compacted` belong to R6, which already blocks",
            "C10-parked-placeholder"
            not in cand(plant(clean, "Status: parked", "Status: compacted", 1)),
        )

        # C11, both directions.
        ft_line = next(ln for ln in clean.splitlines() if ln.startswith("Full-Text: "))
        ck(
            "C11 CONTROL: a record that already carries `Full-Text:` is not flagged",
            "C11-fulltext-upgrade" not in cand(clean),
        )
        ck(
            "C11: a landed blob with no `Full-Text:` line is flagged",
            "C11-fulltext-upgrade" in cand(plant(clean, ft_line + "\n", "", 1)),
        )

        # ---- THE RECORDER, driven through all four floors ------------------
        fixture_recs = [(rel, "parked", len(clean.splitlines()))]
        row = census_row(root, fixture_recs)
        ck(
            "CENSUS: the row counts the corpus it was handed",
            (row["plans_examined"], row["records_examined"]) == (1, 1),
            f"got {(row['plans_examined'], row['records_examined'])}",
        )
        ck(
            "CENSUS: the row carries what the candidates found, not just that they ran",
            row["would_refuse"] >= 1 and row["candidates"]["C10-parked-placeholder"] != [],
            f"got {row['would_refuse']} and {row['candidates']}",
        )
        # FLOOR 1, the two-readings disagreement.
        ck(
            "CENSUS FLOOR: a count that disagrees with the verdict loop REFUSES",
            census_append(root, row, 99, 1)[0] is False,
        )
        # FLOOR 2, an empty corpus.
        ck(
            "CENSUS FLOOR: a row over ZERO plans REFUSES rather than recording nothing",
            census_append(root, census_row(root, []), 0, 0)[0] is False,
        )
        # FLOOR 3, the append and its read-back.
        ok_w, msg_w = census_append(root, row, 1, 1)
        n_after = len(census_rows(root / CENSUS_REL))
        ck("CENSUS: the first row is recorded", ok_w and n_after == 1, f"{ok_w} {msg_w} {n_after}")
        ck(
            "CENSUS: the recorded row round-trips through the reader byte-identically",
            census_rows(root / CENSUS_REL)[0] == row,
        )
        # FLOOR 4, the same-day collapse -- and it must not become the hatch.
        ok_r, _msg_r = census_append(root, dict(row, ts=row["ts"]), 1, 1)
        ck(
            "CENSUS: a same-day repeat of the same observation appends no second row",
            ok_r and len(census_rows(root / CENSUS_REL)) == 1,
        )
        ck(
            "CENSUS CONTROL: the collapse is per UTC DAY, so tomorrow's identical row lands",
            census_is_same_day_repeat(row, dict(row, ts="2099-01-01T00:00:00Z")) is False,
        )
        ck(
            "CENSUS CONTROL: a DIFFERENT observation on the same day is not a repeat",
            census_is_same_day_repeat(row, dict(row, would_refuse=0, candidates={})) is False,
        )
        os.environ["PLAN_RECORD_CENSUS_EVERY_RUN"] = "1"
        census_append(root, row, 1, 1)
        forced = len(census_rows(root / CENSUS_REL))
        del os.environ["PLAN_RECORD_CENSUS_EVERY_RUN"]
        ck(
            "CENSUS CONTROL: PLAN_RECORD_CENSUS_EVERY_RUN=1 forces the row anyway",
            forced == 2,
            f"got {forced}",
        )

        # ---- THE REPORT, which is the only thing that answers the box ------
        buf = io.StringIO()
        ck(
            "CENSUS REPORT: it reads the recorded rows and answers",
            census_report(root, out=buf) == 0,
        )
        said = buf.getvalue()
        ck(
            "CENSUS REPORT: it names the window and whether it has elapsed",
            "NOT yet elapsed" in said and "day(s) of %d" % CENSUS_WINDOW_DAYS in said,
            f"got {said!r}",
        )
        ck(
            "CENSUS REPORT: it names every candidate and the plans each would refuse",
            all(cid in said for cid in CANDIDATES) and rel in said,
            f"got {said!r}",
        )
        # AND THE OTHER DIRECTION: no rows must REFUSE, not report a clean window.
        (root / CENSUS_REL).unlink()
        ck(
            "CENSUS REPORT: with NO rows it refuses rather than reporting an empty window",
            census_report(root, out=io.StringIO(), err=io.StringIO()) == 1,
        )

        # ---- R9, THREE PLANTS BECAUSE THE ARITIES DIFFER ------------------- One control cannot cover these: `Supersedes` needs at least one pointer, `Extends` needs exactly one, and `Related` needs none. A single fixture would prove whichever arity it happened to have.
        def xref(label, body, needle, want=True):
            got = header_xref_problems(root, "agent/PLAN-x.md", body)
            hit = any(needle in g for g in got)
            ck(label, hit is want, f"needle {needle!r}, want {want}, got {got}")

        real_plan = "agent/PLAN-env-to-bitwarden.md"
        # A plan that resolves in the FIXTURE root, so the silent cases are silent
        # for the right reason. build_fixture writes `rel`; use it.
        here = rel

        # -- Supersedes: at least one -----------------------------------------
        xref(
            "R9 Supersedes: naming no pointer at all is a finding",
            "# t\nSupersedes: the old approach entirely.\n",
            "at least 1",
        )
        xref(
            "R9 CONTROL: Supersedes naming ONE resolvable plan is silent",
            "# t\nSupersedes: `%s` Part 1.\n" % here,
            "Supersedes",
            want=False,
        )
        xref(
            "R9 CONTROL: Supersedes may name SEVERAL, unlike Extends",
            "# t\nSupersedes: `%s` and `%s:1`.\n" % (here, here),
            "takes exactly",
            want=False,
        )
        xref(
            "R9 Supersedes: a pointer that does not resolve is a finding",
            "# t\nSupersedes: `agent/PLAN-no-such-plan-zzz.md`.\n",
            "does not exist",
        )
        # THE CONTINUATION LINE, which is not a nicety: the only real `Supersedes:` user in this tree puts its sole resolvable pointer on the SECOND line, and a line-at-a-time reader reports it as naming nothing.
        xref(
            "R9 CONTROL: a pointer on a CONTINUATION line counts",
            "# t\nSupersedes: the config and its reader entirely, and the\n`%s:1` row.\n" % here,
            "at least 1",
            want=False,
        )

        # -- Extends: exactly one ---------------------------------------------
        xref(
            "R9 Extends: TWO pointers is a finding, because one is the arity",
            "# t\nExtends: `%s` and `%s:1`.\n" % (here, here),
            "takes exactly 1",
        )
        xref(
            "R9 CONTROL: Extends naming exactly one is silent",
            "# t\nExtends: `%s`.\n" % here,
            "Extends",
            want=False,
        )

        # -- Related: any number, including none -------------------------------
        xref(
            "R9 CONTROL: Related naming NOTHING is silent, unlike Supersedes",
            "# t\nRelated: this rhymes with the licence work.\n",
            "Related",
            want=False,
        )
        xref(
            "R9 Related: a pointer it DOES carry must resolve",
            "# t\nRelated: `agent/PLAN-no-such-plan-zzz.md`.\n",
            "does not exist",
        )

        # -- the block reader, both directions ---------------------------------
        ck(
            "R9: the value stops at the next header field",
            header_xref_block("# t\nRelated: a\nOwner: b\n", "Related") == "a",
            header_xref_block("# t\nRelated: a\nOwner: b\n", "Related"),
        )
        ck(
            "R9: the value stops at a blank line",
            header_xref_block("# t\nRelated: a\n\nb\n", "Related") == "a",
        )
        ck(
            "R9 CONTROL: an absent key yields no block, so the rule stays silent",
            header_xref_block("# t\nStatus: draft\n", "Extends") == "",
        )
        ck(
            "R9 CONTROL: a key BELOW the header window is not read",
            header_xref_block("# t\n%sExtends: `%s`\n" % ("f\n" * 12, real_plan), "Extends") == "",
        )

    return bad


# ---------------------------------------------------------------------------


def main(argv):
    update = "--update" in argv
    # A PURE READER, and it runs before anything else on purpose. `--census-report` answers "has the window elapsed" from the recorded rows and must stay usable on a tree whose R1..R8 verdict is red -- the window is about the CANDIDATE rules and has nothing to say about the enforced ones.
    if "--census-report" in argv:
        return census_report(ROOT)
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

    # ---- R9, OVER EVERY PLAN AND NOT ONLY THE RECORDS ---------------------- The loop above filters to RECORD_STATES because R1..R8 are statements about a compaction record. R9 is not: both `Supersedes:` users in this tree carry `Status: draft`, so scoping R9 to records would give it zero subjects and a permanent green. The count is printed below, because a rule whose subject
    # count silently reaches zero is a rule that has stopped asserting anything.
    n_xref = 0
    for rel, _status, _n in recs:
        try:
            text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue  # already reported above for a record; a plain plan is not R9's business
        if not any(header_xref_block(text, k) for k in HEADER_XREF_KEYS):
            continue
        n_xref += 1
        problems.extend(header_xref_problems(ROOT, rel, text))

    rows = R.index_rows(ROOT, recs)
    # THIS DOES OPEN EVERY PLAN, and saying otherwise would be the wrong trade described the wrong way round. `recs` is reused so the directory is not walked twice, but `plan_box_census` reads all 83 files to count boxes. That cost is deliberately paid HERE, once per CI run, so that SessionStart and PostCompact -- which fire on every session and every compaction -- pay one file
    # read instead. The point was never to stop reading the plans; it was to stop reading them on the interactive path.
    census = PI.render_census(
        PI.census_rows(ROOT, plan_records=lambda _r: recs, plan_box_census=CK.plan_box_census)
    )
    problems.extend(index_problems(ROOT, rows, census=census, update=update))

    # ---- THE ADVISORY CENSUS ------------------------------------------------- IT RUNS ON BOTH PATHS, red and green. A measurement window with a hole in it wherever some unrelated rule failed is a window nobody can reason about, and the candidates say nothing about R1..R8 either way.
    #
    # `census_row` is computed from its OWN re-read of every plan; the two counts handed to `census_append` come from the verdict loop above. That is the two-readings floor, and it is why the counts are passed rather than shared.
    census_ok, census_msg = census_append(ROOT, census_row(ROOT, recs), len(recs), n_records)

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
        # The census verdict is reported here too, and it does NOT change this exit code: 1 already says "findings", and a census failure on top of findings is a second thing to fix, not a different one.
        print(("  " + census_msg) if census_ok else ("✗ " + census_msg), file=sys.stderr)
        return 1

    print(
        f"✓ plan records: {len(recs)} plan file(s) (floor {MIN_PLAN_FILES}), "
        f"{n_records} compacted or parked record(s), every pointer resolves, every "
        f"`done=` is attested by {R.LEDGER_REL} at the commit it names, and "
        f"{R.INDEX_REL} matches, census section included "
        f"({len(PI.parse_census(census))} plan row(s) SessionStart reads instead of "
        f"opening the plans). R9: {n_xref} plan(s) carry a "
        f"{'/'.join(HEADER_XREF_KEYS)} header and every pointer in one resolves."
    )
    if n_records == 0:
        print(
            "  0 records is the expected state until the first compaction wave. The rules\n"
            "  above ran against the planted fixtures in --selftest, not against nothing."
        )
    # THE ONE WAY THE CENSUS REACHES AN EXIT CODE, and it is never because a candidate FIRED. Exit 2 is this file's "instrument control failed" code, and a census that recorded nothing is exactly that: it reports what a clean corpus reports, forever, while the two-week clock never starts.
    if not census_ok:
        print("✗ " + census_msg, file=sys.stderr)
        print(
            "  The advisory census is the only thing measuring what a future blocking\n"
            "  rung would refuse. R1..R8 all passed; this exit is about the instrument,\n"
            "  not about the records.",
            file=sys.stderr,
        )
        return 2
    print(census_msg)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
