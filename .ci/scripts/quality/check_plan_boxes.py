#!/usr/bin/env python3
"""check:ci-plan-boxes -- the committed ledger of every open checkbox in agent/PLAN-*.md.

WHY A LEDGER AND NOT A GREP. Two reasons, both measured on this tree.

1. A NAIVE GREP REDS ON NON-TASKS. `grep -F -- '- [ ]'` finds 93 hits; the anchored
   line count finds 89; `wl_planfid.plan_tasks` -- the parser the Stop hook actually
   uses -- finds 88. The five differences are four bits of PROSE ABOUT the checkbox
   grammar and one fenced CODE SAMPLE at agent/PLAN-fix-in-session-rule.md:352, which
   depicts a line the hook prints. A CI gate built on grep fails the build on a code
   sample. So this gate IMPORTS the real parser rather than reimplementing it, which
   makes the fence rule a structural property instead of a test: there is no second
   parser that can drift, and the same rule that makes :352 a non-finding makes
   wrapping a real box in a fence a DETECTABLE cheat.

2. A GATE THAT REDS ON OPEN BOXES GETS SWITCHED OFF. An audit of all 88 open boxes on
   2026-09-02 found 14 done-but-unticked and 58 legitimately open -- most of them other
   sessions' work. Failing on the mere existence of an open box would have been red on
   eight files at once, on the branch introducing the gate. So this asserts the LEDGER
   AGREES WITH THE TREE, and leaves the stock visible in one reviewable file where
   `open: 22 -> 21` beside a `- [x]` is the whole story in two lines.

WHAT IS ASSERTED (agent/PLAN-plan-file-lifecycle.md's G-A0..G-A6):

THE `G-` PREFIX IS LOAD-BEARING, ADOPTED 2026-09-08 (box X0.1). Three id schemes
collided on the same-looking token, and two adjacent plan boxes ended up pointing at
OPPOSITE FILES because of it: `A5`/`A6` here are GATE RULES, while
`docs/ci-overhaul/04-decisions.md` section A item 6 (`:22-23`, "Do not stick on what
I say. Better ideas are welcomed") is an OPERATOR RULING. W12 P2.7 cited "A5 in
04-decisions.md", where `grep -cE 'A5'` on that file returns 0 -- it meant this file
all along. So gate rules are `G-A<n>`, operator decisions are `D-A<n>`, and a bare
`A5` is now wrong in both directions rather than ambiguous in both.

  G-A0  every plan on disk has a ledger entry whose status, owner, open/done counts and
      task signatures match, and every ledger entry names a plan that exists.
  G-A1  no box open at the MERGE-BASE may be gone at HEAD. It must be ticked, still
      open, moved to another plan, archived, or in a plan G-A5 permitted deleting.
      This one assertion subsumes most of the ways a box can be made to disappear:
      deleting the line, un-checkboxing it, rewriting its text, wrapping it in a
      fence, or renaming the plan out of the glob all end the same way.
  G-A2  the archive is APPEND-ONLY and takes only byte-identical renames. `git diff
      -M100% BASE...HEAD` compares TREES, so editing a plan and archiving it in a
      separate commit is still R09x -- there is no commit-ordering dodge.
  G-A3  a FINISHED `Status:` may not sit over open boxes. This INVERTS the Stop hook's
      own frozenset: there the status means "stop nagging", here it means "that
      header switches the advisory off over live boxes". Same constant, imported,
      so the two halves cannot drift.
  G-A4  a plan this branch ADDS with open boxes must resolve an `Owner:`, because the
      advisory only chases plans a session owns.
  G-A5  a plan may NEVER be deleted wholesale while deleting it loses a box. Age
      grants nothing; it is reported so the message can name the right door. The
      doors are tick, move, `git mv` into the archive, and
      `worklist.py --plan-compact --park`, and every one of them KEEPS the box.
  G-A6  the scan is not vacuous: a floor on plan files, a floor on total open boxes, and
      a refusal to judge when the parser resolves NOTHING from a tree that plainly
      contains checkbox lines.

G-A1..G-A5 NEED A BASE, so they run in quality-branch (pull_request only). When there is
no base, or the base predates the ledger, they are SKIPPED and the summary says so --
a skip must never read as a clean result.

THE DEADLOCK THAT USED TO EXIST, AND THE AMNESTY IT BOUGHT, REMOVED 2026-09-09 (W12
P2.7a). The housekeeping gate once DEMANDED deletion past delete_days while G-A5
REFUSED it before, so the two were kept complements over one number in
.ci/config/plan-lifecycle.json -- and G-A1 stood down for age-retired plans for the
same reason. That bargain is over: `.ci/scripts/quality/check-plan-housekeeping.sh:51`
now reads "THE REMEDY IS NO LONGER 'DELETE IT', AND THAT WORD IS GONE ON PURPOSE",
and the third door, compaction, keeps the plan AT ITS OWN PATH with its box lines
byte-identical (wl_planrec.py property 2). Nothing the housekeeping gate demands now
destroys a box, so nothing needs an exemption from G-A1 or G-A5.

WHAT THE AMNESTY WAS ACTUALLY DOING, measured end to end on a scratch tree the day it
was removed: a 41-day-old plan deleted wholesale, carrying ONE open box that survived
nowhere, exited 0 and printed "21 box(es) open at <base> all survive at HEAD" over a
base that held 22. Not merely permitted -- ASSERTED to be fine. The two gates still
share the one number, because the message names the housekeeping window when it quotes
the compaction remedy, and two copies of `33` would still be two copies.

TASK SIGNATURES are the first 8 hex of sha256 over `wl_planfid._norm(task)[:120]` --
EXACTLY the key the parser already dedups on. Not the raw text: re-wrapping a line must
be free, and rewriting what it says must not be. That choice is what lets the later
transition rule ask "did this box survive?" as set membership rather than as a
token-overlap guess.

REGENERATE with `--update`. The ledger is committed, so a stale one is a red with a
one-command fix, and the regeneration is what makes the base-vs-head comparison
meaningful later: G-A1 reads the BASE ledger via `git show`, which no working tree can
rewrite.

---- gate ----
step: Plan checkbox ledger
needs: none
selftest: true
lane: quality-branch
---- end gate ----
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import _cipath  # noqa: F401
from rediacc_ci import controls, paths

ROOT = Path(os.environ.get("PLAN_BOXES_ROOT") or Path(__file__).resolve().parents[3])
# The hop onto the Stop hook's directory, through the package's own resolver.
# `paths.on_sys_path` is idempotent where a bare `sys.path.insert(0, d)` is not,
# and `paths.hooks_stop_dir` is the ONE place the `.claude/hooks/stop` literal
# lives, so the move planned for that program is a one-line change there rather
# than a sweep of nine call sites. ROOT is passed explicitly: this gate honours
# its own PLAN_BOXES_ROOT override, which the resolver's default root does not read.
paths.on_sys_path(paths.hooks_stop_dir(ROOT))

try:
    import wl_checks as CK
    import wl_planfid as PFID
    import wl_planfile as PF
except ImportError as _exc:  # pragma: no cover -- exercised by test-gate-anti-vacuity.sh
    # NOT a traceback. Importing the Stop hook's parser is this gate's ONLY way of
    # reading a checkbox (see the docstring), so a tree without .claude/hooks/stop is a
    # tree this gate cannot judge -- and a crash there reads to a reader, and to the
    # anti-vacuity harness, as an unrelated bug rather than as blindness. A check that
    # cannot see must SAY it cannot see.
    print(
        f"VACUOUS INPUT: cannot import the Stop hook's plan parser from "
        f"{ROOT / '.claude' / 'hooks' / 'stop'} ({_exc}). This gate reads checkboxes "
        f"ONLY through wl_planfid.plan_tasks -- a grep gets the answer wrong on fenced "
        f"code samples -- so without it there is nothing to compare and no verdict to "
        f"give.",
        file=sys.stderr,
    )
    sys.exit(1)

LEDGER = ROOT / ".ci" / "config" / "plan-boxes.json"
PLAN_GLOB = "PLAN-*.md"

# Floors. Measured 2026-09-02: 10 plan files carry boxes out of 70 total, 83 open and 37
# ticked. The file floor is deliberately well under the total -- it guards against the
# glob losing the corpus, not against ordinary housekeeping -- and the box floor guards
# against a parser that silently resolves nothing.
MIN_PLAN_FILES = int(os.environ.get("PLAN_BOXES_MIN_PLANS", "20"))
MIN_OPEN_BOXES = int(os.environ.get("PLAN_BOXES_MIN_OPEN", "1"))

LIFECYCLE = ROOT / ".ci" / "config" / "plan-lifecycle.json"
# FINISHED comes from the Stop hook, imported rather than restated: G-A3 INVERTS it
# (there the status means "stop nagging"; here it means "this header switches the
# advisory off over live boxes"), and the two halves must never drift apart.
FINISHED = PF.FINISHED_STATES


def _lifecycle() -> dict:
    """warn_days / delete_days / archive_dir, shared with the housekeeping gate.

    Not inlined. G-A5 REFUSES a deletion that gate DEMANDS, so the two predicates
    must be complements over one number or a plan can be simultaneously
    must-delete and must-not-delete.
    """
    try:
        return json.loads(LIFECYCLE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"delete_days": 33, "archive_dir": "agent/archive/plans"}


ARCHIVE_DIR = _lifecycle().get("archive_dir", "agent/archive/plans")


# A path-shaped token: one or more directory components before a dotted
# basename. Only the basename survives into `loose_sig`.
PATHISH_RE = re.compile(r"(?:[\w.@~-]+/)+([\w.@~-]+\.[A-Za-z0-9]{1,6})")


def sig(task: str) -> str:
    """The parser's OWN dedup key, hashed. See the module docstring.

    UNCHANGED ON PURPOSE. The ledger committed at the base ref is keyed by this
    function, and G-A1's whole claim to be unforgeable is that it reads that
    committed record; re-keying it would make every historical box look deleted
    at once. Move tolerance lives in `loose_sig`, which is computed from git's
    own copy of the base plan TEXT, so it is exactly as unforgeable.
    """
    return hashlib.sha256(PFID._norm(task)[:120].encode("utf-8")).hexdigest()[:8]


def loose_sig(task: str) -> str:
    """`sig` with directory prefixes stripped from the paths the box cites.

    A box's identity is the TASK, not the spelling of the paths in it. Without
    this, moving a cited file re-signs every box that cites it and G-A1 reports
    the move as a DELETION, offering three remedies (tick it, mark it `[?]`,
    archive the plan) of which none is true and all three falsify the record.
    Measured 2026-09-09: moving 125 gates from `scripts/` to `scripts/gates/`
    reddened four boxes across three plans that way.

    `_norm` cannot do this itself -- it is shared with the Stop hook's task
    matching, where a cited directory is real evidence about which file a claim
    means. The discrimination lost here is two boxes whose first 120 normalised
    characters differ ONLY by a directory prefix; the basename stays, so
    everything else is kept.
    """
    return hashlib.sha256(
        PFID._norm(PATHISH_RE.sub(r"\1", task))[:120].encode("utf-8")
    ).hexdigest()[:8]


def scan(root: Path) -> dict:
    """{relpath: {status, owner, open, done, task_sigs}} for every plan under agent/."""
    out: dict[str, dict] = {}
    for rel, status, _lines in CK.plan_records(root):
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        open_t, done_t = PF.plan_boxes(text)
        out[rel] = {
            "status": status,
            "owner": CK.plan_owner(root, rel) or "unowned",
            "open": len(open_t),
            "done": len(done_t),
            "open_sigs": sorted({sig(t) for t in open_t}),
            "done_sigs": sorted({sig(t) for t in done_t}),
        }
    return out


def raw_box_lines(root: Path) -> int:
    """Checkbox-shaped lines counted with NO parser at all.

    The anti-vacuity oracle, and the only thing that can tell "there are no boxes" apart
    from "the parser stopped seeing them". It is deliberately dumber than plan_boxes --
    it counts the fenced sample and the prose too -- so it is only ever compared as
    `plainly non-zero`, never for equality.
    """
    n = 0
    for rel, _s, _l in CK.plan_records(root):
        for ln in (root / rel).read_text(encoding="utf-8", errors="replace").splitlines():
            if PF.OPEN_BOX_LINE.match(ln) or PF.DONE_BOX_LINE.match(ln):
                n += 1
    return n


def vacuity_problems(scanned: dict, raw: int) -> list[str]:
    """G-A6. Every way this scan can see nothing and report success."""
    out = []
    if len(scanned) < MIN_PLAN_FILES:
        out.append(
            f"VACUOUS INPUT: scanned {len(scanned)} plan file(s) under agent/, floor is "
            f"{MIN_PLAN_FILES}. The glob lost the corpus; refusing a verdict rather than "
            f"reporting a clean ledger for files nobody read"
        )
    total_open = sum(p["open"] for p in scanned.values())
    total_done = sum(p["done"] for p in scanned.values())
    if raw > 0 and total_open + total_done == 0:
        out.append(
            f"VACUOUS INPUT: {raw} checkbox-shaped line(s) exist in agent/PLAN-*.md and "
            f"the parser resolved NONE of them. wl_planfid.plan_tasks has stopped seeing "
            f"tasks; a clean report here would be indistinguishable from a broken parser"
        )
    elif total_open < MIN_OPEN_BOXES and raw > 0:
        out.append(
            f"VACUOUS INPUT: {total_open} open box(es) against {raw} raw checkbox line(s), "
            f"floor is {MIN_OPEN_BOXES}"
        )
    return out


def diff_problems(scanned: dict, ledger: dict) -> list[str]:
    """G-A0. The ledger and the tree, in both directions."""
    out = []
    plans = ledger.get("plans") or {}
    out.extend(
        f"{rel} carries {scanned[rel]['open']} open and {scanned[rel]['done']} ticked "
        f"box(es) but has no ledger entry -- a plan nothing records is a plan whose "
        f"boxes can vanish unnoticed"
        for rel in sorted(set(scanned) - set(plans))
    )
    out.extend(
        f"{LEDGER.name} still has an entry for {rel}, which is not in agent/ any more"
        for rel in sorted(set(plans) - set(scanned))
    )
    for rel in sorted(set(scanned) & set(plans)):
        got, want = scanned[rel], plans[rel]
        out.extend(
            f"{rel}: {field} is {got[field]!r}, ledger says {want.get(field)!r}"
            for field in ("status", "owner", "open", "done")
            if got[field] != want.get(field)
        )
        for field in ("open_sigs", "done_sigs"):
            if sorted(got[field]) != sorted(want.get(field) or []):
                gone = sorted(set(want.get(field) or []) - set(got[field]))
                new = sorted(set(got[field]) - set(want.get(field) or []))
                out.append(
                    f"{rel}: {field} disagree -- {len(gone)} in the ledger and not the "
                    f"tree ({', '.join(gone[:4]) or 'none'}), {len(new)} in the tree and "
                    f"not the ledger ({', '.join(new[:4]) or 'none'})"
                )
    return out


def base_ref() -> str | None:
    """The commit this branch diverged from, or None when there is no base.

    CI hands us `GITHUB_BASE_REF` (a branch name on a `pull_request` event and
    nothing at all on `push`), so the merge-base is computed rather than assumed:
    diffing against the tip of main would attribute every commit main gained
    since the branch started to this branch.

    None is not a failure. G-A0 and G-A6 read only the working tree and still run;
    the transition rules simply have nothing to compare against, and say so.
    """
    cand = os.environ.get("PLAN_BOXES_BASE") or ""
    if not cand:
        br = os.environ.get("GITHUB_BASE_REF") or ""
        cand = f"origin/{br}" if br else "origin/main"
    for ref in (cand, cand.replace("origin/", ""), "origin/main", "main"):
        if not ref:
            continue
        r = _git("merge-base", "HEAD", ref)
        if r:
            return r.strip()
    return None


def _git(*args: str) -> str | None:
    r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=False)
    return r.stdout if r.returncode == 0 else None


def base_ledger(base: str) -> tuple[dict, str | None]:
    """The ledger AS OF the base commit. This is what makes G-A1 unforgeable.

    G-A0 forces the head ledger to match the head tree, so a session that deletes a
    box must regenerate it -- and then the head ledger agrees with the tree and
    says nothing. The BASE ledger is read out of git, which a working tree cannot
    rewrite, so the two together make "did this box survive?" answerable.
    """
    raw = _git("show", f"{base}:{LEDGER.relative_to(ROOT)}")
    if raw is None:
        # ABSENT IS EXPECTED EXACTLY ONCE: on the branch that introduces the
        # ledger, the base predates it. Failing here would make the gate
        # unshippable on its own branch, which is the shape the plan warned
        # against. It is a SKIP, not a pass -- main() says so in the summary,
        # so "G-A1..G-A5 did not run" can never read as "G-A1..G-A5 found nothing".
        return {}, None
    try:
        return json.loads(raw), None
    except ValueError as exc:
        # A ledger that EXISTS and does not parse is a different thing entirely:
        # something is wrong with a file this gate depends on, and skipping would
        # hide it.
        return {}, f"the ledger at {base[:9]} does not parse ({exc}); G-A1 is blind"


def renames_into_archive(base: str) -> tuple[set[str], list[str]]:
    """({new archive paths that are byte-identical renames}, {problems}).

    A2a. `git diff --find-renames -M100%` compares TREES, not commits, which is
    the whole reason the two-commit dodge cannot work: editing a plan and then
    archiving it in a separate commit still leaves the net content different from
    base, so the similarity is below 100 and it reports R09x rather than R100.
    """
    out = _git("diff", "--name-status", "--find-renames", "-M100%", f"{base}...HEAD")
    if out is None:
        return set(), [f"cannot diff {base[:9]}...HEAD; G-A2 is blind"]
    ok, problems = set(), []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].startswith("R") and parts[2].startswith(ARCHIVE_DIR):
            if parts[0] == "R100":
                ok.add(parts[2])
            else:
                problems.append(
                    f"{parts[1]} -> {parts[2]} is {parts[0]}, not R100: the content changed "
                    f"between {base[:9]} and HEAD. Archiving is for history you did NOT "
                    f"touch, so archiving it now would retire boxes this branch is "
                    f"responsible for. Two commits do not help -- this compares TREES"
                )
        elif len(parts) == 2 and parts[0] in ("M", "D") and parts[1].startswith(ARCHIVE_DIR):
            problems.append(
                f"{parts[1]} was {'modified' if parts[0] == 'M' else 'deleted'} in the "
                f"archive. The archive is APPEND-ONLY: a plan retired there is frozen, "
                f"which is what keeps its boxes findable and its age clock ticking"
            )
        elif len(parts) == 2 and parts[0] == "A" and parts[1].startswith(ARCHIVE_DIR):
            problems.append(
                f"{parts[1]} was ADDED to the archive rather than renamed into it. Use "
                f"`git mv` on an untouched plan; a fresh file there is a plan whose "
                f"history -- and whose boxes -- were left behind"
            )
    return ok, problems


def _name_status(base: str) -> list[tuple[str, str]]:
    out = _git(
        "diff", "--name-status", "--find-renames", "-M100%", f"{base}...HEAD", "--", "agent/"
    )
    rows = []
    for line in (out or "").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            rows.append((parts[0], parts[-1]))
    return rows


def _touched_plans(base: str) -> set[str]:
    return {p for st, p in _name_status(base) if st != "D" and p.startswith("agent/PLAN-")}


def _added_plans(base: str) -> set[str]:
    return {p for st, p in _name_status(base) if st == "A" and p.startswith("agent/PLAN-")}


def _content_age_days(rel: str, base: str) -> int | None:
    """Days since the newest commit that CHANGED this file, as of the base.

    Content age, not "last commit touching the path": otherwise moving a plan
    would reset its clock and archiving would become a way to cheat the age gate.
    """
    when = _git("log", "-1", "--format=%cI", base, "--", rel)
    if not when or not when.strip():
        return None
    try:
        then = dt.datetime.fromisoformat(when.strip())
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=dt.UTC)
    return (dt.datetime.now(dt.UTC) - then).days


def transition_problems(scanned: dict, base: str) -> tuple[list[str], int]:
    """G-A1..G-A5. Returns (problems, boxes_compared).

    G-A1 is the load-bearing one and it subsumes most of the cheats: deleting a box
    line, un-checkboxing it, rewriting its text, fencing it, or renaming the plan
    out of the glob all end the same way -- a signature that was open at base has
    no legal home at head.
    """
    problems: list[str] = []
    ledger, err = base_ledger(base)
    if err:
        return [err], -1
    if not ledger:
        return [], -1
    archived_ok, arch_problems = renames_into_archive(base)
    problems += arch_problems

    head_open: dict[str, str] = {}
    head_done: dict[str, str] = {}
    for rel, rec in scanned.items():
        for bsig in rec["open_sigs"]:
            head_open.setdefault(bsig, rel)
        for bsig in rec["done_sigs"]:
            head_done.setdefault(bsig, rel)

    # THE SECOND CHANCE, and why it reads git rather than the ledger. A box whose
    # cited file MOVED is re-signed, and to `sig` that is indistinguishable from a
    # deletion plus an unrelated addition. The ledger cannot answer this -- it
    # stores signatures, not text -- so the base plan's own bytes are fetched from
    # git and re-signed loosely. That is the same unforgeable source the base
    # ledger comes from: a working tree cannot rewrite `git show <base>:<path>`.
    head_loose: set[str] = set()
    for rel in scanned:
        try:
            text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        o, d = PF.plan_boxes(text)
        head_loose.update(loose_sig(t) for t in o)
        head_loose.update(loose_sig(t) for t in d)

    _base_loose_cache: dict[str, dict[str, str]] = {}

    def _moved_not_deleted(rel: str, gone: str) -> bool:
        """Did the box `gone` survive at HEAD with only its citations re-spelled?"""
        if rel not in _base_loose_cache:
            raw = _git("show", f"{base}:{rel}")
            m: dict[str, str] = {}
            if raw is not None:
                o, d = PF.plan_boxes(raw)
                for t in list(o) + list(d):
                    m.setdefault(sig(t), loose_sig(t))
            _base_loose_cache[rel] = m
        loose = _base_loose_cache[rel].get(gone)
        return loose is not None and loose in head_loose

    base_plans = ledger.get("plans") or {}
    lifecycle = _lifecycle()

    # THERE IS NO AGE AMNESTY ANY MORE (W12 P2.7a, 2026-09-09). This block used to
    # compute a `retired` set -- plans older than delete_days that the branch had
    # deleted -- and exempt them from BOTH G-A1 and G-A5, on the reasoning that the
    # housekeeping gate DEMANDED their deletion and two gates must not deadlock over
    # one number. That reasoning expired: `.ci/scripts/quality/check-plan-housekeeping.sh:51`
    # now says "THE REMEDY IS NO LONGER 'DELETE IT', AND THAT WORD IS GONE ON
    # PURPOSE", and .ci/config/plan-lifecycle.json calls compaction THE THIRD DOOR.
    #
    # The doors that remain all PRESERVE the box, so no deadlock survives the change:
    #   - `worklist.py --plan-compact --park` keeps the plan at its own path and copies
    #     every box line BYTE-IDENTICALLY (wl_planrec.py's property 2 exists precisely
    #     so a compaction cannot look like a disappearance). `--park` rather than plain
    #     `--plan-compact` because `compacted` is in FINISHED_STATES and G-A3 refuses a
    #     finished status over open boxes; `parked` is not, deliberately.
    #   - `git mv` untouched into the archive, which G-A2 accepts at R100.
    #   - tick the box, or move it to a live plan.
    #
    # WHAT THE AMNESTY WAS COSTING, measured on a real scratch tree before it was
    # removed: a 41-day-old plan deleted wholesale, carrying one open box that
    # survived nowhere, exited 0 -- and the success line ASSERTED "21 box(es) open at
    # <base> all survive at HEAD" when 22 were open and one had just been destroyed.
    # An instrument that reports work it did not do is the failure this file is for.
    # ARCHIVING IS A LEGAL HOME AND G-A1 DID NOT KNOW IT, found 2026-09-09 by the
    # control that replaced the age amnesty. G-A1's own message has always listed
    # "not archived" among the ways a box may be gone and told the reader to
    # `git mv` the plan into the archive -- but only G-A5 consulted `archived_ok`,
    # so doing that reddened G-A1 on any plan the amnesty did not cover. Measured
    # against the committed file the same day: a YOUNG plan moved into the archive
    # at R100 reported "is GONE at HEAD ... not archived" while the identical move
    # on a 999-day-old plan was silent. That is age deciding whether a correct
    # action is correct, which it never should have. One predicate now, shared, so
    # the two rules cannot disagree again.
    def _archived(rel: str) -> bool:
        return any(a.endswith("/" + rel.rsplit("/", 1)[-1]) for a in archived_ok)

    compared = 0
    for rel, rec in sorted(base_plans.items()):
        archived_here = rel not in scanned and _archived(rel)
        for bsig in rec.get("open_sigs") or []:
            compared += 1
            # Counted as compared and as SURVIVING: an R100 rename means the box
            # line is byte-identical in agent/archive/plans/, and G-A2 keeps that
            # directory append-only, so it is findable rather than gone.
            if archived_here:
                continue
            if bsig in head_open or bsig in head_done:
                continue
            if _moved_not_deleted(rel, bsig):
                continue
            where = "deleted" if rel not in scanned else "gone from"
            problems.append(
                f"{rel}: a box open at {base[:9]} (sig {bsig}) is GONE at HEAD -- not "
                f"ticked, not moved to another plan, not archived. A box is the only "
                f"durable record of a task once a context ends; deleting the line does "
                f"not finish the work, it hides it. If you did it, tick it. If it is "
                f"blocked, mark it `- [?]`. If the plan is history, `git mv` it "
                f"untouched into {ARCHIVE_DIR}/ ({where} that plan)"
            )

    # G-A5: a plan may NEVER be deleted wholesale while deleting it loses a box.
    # Age is reported for context and grants nothing. If every box it held survives
    # in another plan, the file is a husk and removing it costs nothing; firing
    # there would punish exactly the tidying this whole check wants.
    for rel in sorted(set(base_plans) - set(scanned)):
        if _archived(rel):
            continue
        lost = [
            g
            for g in (base_plans[rel].get("open_sigs") or [])
            if g not in head_open and g not in head_done and not _moved_not_deleted(rel, g)
        ]
        if not lost:
            continue
        age = _content_age_days(rel, base)
        aged = age is not None and age > lifecycle["delete_days"]
        problems.append(
            f"{rel} was DELETED, losing {len(lost)} open box(es) that survive nowhere. "
            f"It is {age if age is not None else 'an unknown number of'} day(s) old"
            + (
                f", past the {lifecycle['delete_days']}-day housekeeping window -- and that "
                f"window has never licensed a DELETION. Its remedy is COMPACTION: "
                f"`worklist.py --plan-compact --park {rel}` keeps the plan at its own path "
                f"(so every citation still resolves) and copies each box line "
                f"byte-identically, which is why it cannot look like this. `--park`, not "
                f"plain `--plan-compact`: `compacted` is a FINISHED status and G-A3 refuses "
                f"one over open boxes"
                if aged
                else f", inside the {lifecycle['delete_days']}-day housekeeping window"
            )
            + ". Tick the box, move it to a live plan, `git mv` this file untouched into "
            f"{ARCHIVE_DIR}/, or compact it. Deleting it does not finish the work, it hides it"
        )

    # G-A3/A4 are properties of HEAD alone, but only for plans this branch touched --
    # judging a plan the branch never opened would be a demand about somebody
    # else's file.
    touched = _touched_plans(base)
    for rel in sorted(touched & set(scanned)):
        rec = scanned[rel]
        if rec["status"] in FINISHED and rec["open"]:
            problems.append(
                f"{rel} says Status: {rec['status']} but has {rec['open']} open box(es). "
                f"The Stop hook exempts finished plans from its advisory, so that header "
                f"switches the check off for this file -- which is why CI treats it as a "
                f"red rather than as an exemption"
            )
    for rel in sorted(_added_plans(base) & set(scanned)):
        if scanned[rel]["open"] and scanned[rel]["owner"] == "unowned":
            problems.append(
                f"{rel} is NEW on this branch and carries {scanned[rel]['open']} open "
                f"box(es) with no resolvable `Owner:`. The Stop hook's advisory only "
                f"blocks on plans a session owns, so unowned debt is debt nothing chases"
            )
    return problems, compared


def selftest() -> int:
    """Control-first: every verdict below is meaningless if these do not fire.

    C-FENCE is the load-bearing one. It plants the exact defect that motivated the
    parser choice -- a fenced code sample and a line of prose about the grammar, beside
    one real box -- and then plants the NAIVE implementation and requires it to get the
    answer WRONG. A defect detector that cannot detect the historical defect is broken,
    and saying so is cheaper than a clean run that means nothing.
    """
    bad = 0
    fixture = (
        "Status: executing\n\n# F\n\n"
        "## Tasks\n\n"
        "- [ ] a real open task that is long enough to parse\n"
        "- [x] a real ticked task that is long enough to parse\n\n"
        "States are `- [ ]` open and `- [x]` done, described in prose.\n\n"
        "```\n"
        "  - [ ] #<id> (upd <age>) a SAMPLE of a printed line, not a task\n"
        "```\n"
    )
    open_t, done_t = PF.plan_boxes(fixture)
    ok = len(open_t) == 1 and len(done_t) == 1
    print(f"  {'PASS' if ok else 'FAIL'}  C-FENCE: a fenced sample and grammar prose are not tasks")
    if not ok:
        print(f"        open={open_t}\n        done={done_t}")
        bad += 1
    naive = fixture.count("- [ ]")
    ok = naive == 3 and len(open_t) == 1
    print(
        f"  {'PASS' if ok else 'FAIL'}  C-FENCE CONTROL: the naive grep gets it WRONG "
        f"({naive} vs 1), so the parser choice is load-bearing"
    )
    if not ok:
        bad += 1

    # The signature must survive re-wrapping and must NOT survive a rewrite.
    a = sig("close   the   shadow   compare\nbefore deleting")
    b = sig("Close the shadow compare before deleting.")
    c = sig("delete the org secrets before the shadow compare")
    ok = a == b and a != c
    print(
        f"  {'PASS' if ok else 'FAIL'}  a re-wrapped box keeps its signature, a rewritten one does not"
    )
    if not ok:
        bad += 1

    # A MOVED citation is a re-spelling, not a new task. `sig` must NOT absorb it
    # -- the base ledger is keyed by `sig` and re-keying it would make every
    # historical box look deleted -- so the tolerance lives in `loose_sig`, and
    # both halves of that split are asserted here. The pair is the real
    # 2026-09-09 case: `scripts/` -> `scripts/gates/`.
    was = "Write `scripts/check-player-css-scope.ts` with the six floors and eight selftest plants, BEFORE any source change"
    now = was.replace("scripts/", "scripts/gates/")
    ok = loose_sig(was) == loose_sig(now)
    print(f"  {'PASS' if ok else 'FAIL'}  a box whose cited file MOVED keeps its LOOSE signature")
    if not ok:
        print(f"        {loose_sig(was)} != {loose_sig(now)}")
        bad += 1

    ok = sig(was) != sig(now)
    print(
        f"  {'PASS' if ok else 'FAIL'}  CONTROL: `sig` itself does NOT absorb the move, "
        f"so the ledger key is unchanged and the second chance is load-bearing"
    )
    if not ok:
        bad += 1

    # ... and the other control, because stripping directories could have collapsed
    # the basename too, which would make every box about a different file one box.
    d1 = loose_sig(
        "Write `scripts/gates/check-alpha.ts` with the six floors and eight selftest plants"
    )
    d2 = loose_sig(
        "Write `scripts/gates/check-beta.ts` with the six floors and eight selftest plants"
    )
    ok = d1 != d2
    print(
        f"  {'PASS' if ok else 'FAIL'}  CONTROL: two boxes citing DIFFERENT files still "
        f"have different loose signatures"
    )
    if not ok:
        bad += 1

    # ---- G-A1..G-A5, the transition rules ---------------------------------------
    # These are the assertions most able to go silently vacuous: they compare two
    # trees, and a comparison that resolves to nothing looks exactly like a
    # comparison that found nothing wrong. Each rule is planted, and each plant
    # has a pair proving the legitimate path is NOT reported -- a gate that reds
    # on ticking a box teaches sessions not to tick boxes.
    def tp(base_plans, head, **kw):
        """transition_problems with git and the lifecycle stubbed out."""
        saved = {
            k: globals()[k]
            for k in (
                "base_ledger",
                "renames_into_archive",
                "_touched_plans",
                "_added_plans",
                "_content_age_days",
            )
        }
        globals()["base_ledger"] = lambda _b: ({"plans": base_plans}, None)
        globals()["renames_into_archive"] = lambda _b: (set(kw.get("archived", [])), [])
        globals()["_touched_plans"] = lambda _b: set(kw.get("touched", head))
        globals()["_added_plans"] = lambda _b: set(kw.get("added", []))
        globals()["_content_age_days"] = lambda _r, _b: kw.get("age", 1)
        try:
            return transition_problems(head, "0123456789abcdef")[0]
        finally:
            globals().update(saved)

    open_row = {
        "status": "executing",
        "owner": "x",
        "open": 1,
        "done": 0,
        "open_sigs": ["aa"],
        "done_sigs": [],
    }
    ticked_row = dict(open_row, open=0, done=1, open_sigs=[], done_sigs=["aa"])
    gone_row = dict(open_row, open=0, done=0, open_sigs=[], done_sigs=[])

    a1_cases = [
        (
            "G-A1: a box open at base and GONE at head is reported",
            {"agent/PLAN-a.md": open_row},
            {"agent/PLAN-a.md": gone_row},
            "is GONE at HEAD",
        ),
        (
            "G-A1: renaming the plan out of the glob does not hide its boxes",
            {"agent/PLAN-a.md": open_row},
            {},
            "is GONE at HEAD",
        ),
    ]
    for label, b, h, needle in a1_cases:
        got = tp(b, h)
        hit = any(needle in g for g in got)
        print(f"  {'PASS' if hit else 'FAIL'}  {label}")
        if not hit:
            bad += 1
            print(f"        got {got}")

    a1_pairs = [
        (
            "G-A1 CONTROL: TICKING a box is silent -- the legitimate path",
            {"agent/PLAN-a.md": open_row},
            {"agent/PLAN-a.md": ticked_row},
        ),
        (
            "G-A1 CONTROL: MOVING a box to another plan is silent",
            {"agent/PLAN-a.md": open_row},
            {"agent/PLAN-b.md": open_row},
        ),
        (
            "G-A1 CONTROL: leaving it open is silent",
            {"agent/PLAN-a.md": open_row},
            {"agent/PLAN-a.md": open_row},
        ),
    ]
    for label, b, h in a1_pairs:
        got = tp(b, h)
        print(f"  {'PASS' if got == [] else 'FAIL'}  {label}")
        if got:
            bad += 1
            print(f"        got {got}")

    # G-A5 IS NEVER-DELETE (W12 P2.7a). Age no longer buys anything, so the pair is
    # no longer young-vs-aged: it is "the box is lost" vs "the box survives". The
    # 41-day case is spelled out on its own because it is the exact shape that
    # PASSED before this rule changed, and the aged message must name COMPACTION.
    delete_days = _lifecycle()["delete_days"]
    young = tp({"agent/PLAN-a.md": open_row}, {}, age=1)
    ok = any("was DELETED, losing" in g for g in young)
    print(f"  {'PASS' if ok else 'FAIL'}  G-A5: deleting a young plan with open boxes is refused")
    if not ok:
        bad += 1

    aged = tp({"agent/PLAN-a.md": open_row}, {}, age=41)
    ok = any("was DELETED, losing" in g for g in aged)
    print(
        f"  {'PASS' if ok else 'FAIL'}  G-A5: a 41-day-old plan whose one open box survives "
        f"NOWHERE is refused (this passed until 2026-09-09)"
    )
    if not ok:
        bad += 1
        print(f"        got {aged}")
    # The 41 must be past the shared window, or the case above is not the case it
    # claims to be and would keep passing if delete_days were raised.
    ok = delete_days < 41
    print(
        f"  {'PASS' if ok else 'FAIL'}  G-A5 PRECONDITION: 41 is past delete_days "
        f"({delete_days}), so the case above really is the aged one"
    )
    if not ok:
        bad += 1
    ok = any("--plan-compact --park" in g for g in aged)
    print(f"  {'PASS' if ok else 'FAIL'}  G-A5: the aged remedy names COMPACTION, not deletion")
    if not ok:
        bad += 1
    ok = not any("Deletion is for" in g or "before that, archive" in g for g in aged)
    print(f"  {'PASS' if ok else 'FAIL'}  G-A5: no message offers deletion as a remedy")
    if not ok:
        bad += 1

    # G-A1 had the same amnesty and lost it too: the vanished signature must now be
    # reported for an aged plan, which is the half a reader would not think to check.
    ok = any("is GONE at HEAD" in g for g in aged)
    print(
        f"  {'PASS' if ok else 'FAIL'}  G-A1: an aged plan's vanished box is reported too "
        f"(the amnesty covered both rules)"
    )
    if not ok:
        bad += 1

    # THE THREE DOORS, each a control that must NOT fire. Without these the rule
    # above would red on exactly the tidying it wants.
    a5_pairs = [
        (
            "G-A5 CONTROL: an aged HUSK -- every box survives elsewhere -- is silent",
            {"agent/PLAN-a.md": open_row},
            {"agent/PLAN-b.md": open_row},
            {"age": 999},
        ),
        (
            "G-A5 CONTROL: an aged plan `git mv`d untouched into the archive is silent",
            {"agent/PLAN-a.md": open_row},
            {},
            {"age": 999, "archived": [f"{ARCHIVE_DIR}/PLAN-a.md"]},
        ),
        (
            "G-A5 CONTROL: a COMPACTED plan keeps its path and its boxes, so it is silent",
            {"agent/PLAN-a.md": open_row},
            {"agent/PLAN-a.md": dict(open_row, status="parked")},
            {"age": 999},
        ),
    ]
    for label, b, h, kw in a5_pairs:
        got = tp(b, h, **kw)
        print(f"  {'PASS' if got == [] else 'FAIL'}  {label}")
        if got:
            bad += 1
            print(f"        got {got}")

    # AGE MUST NOT DECIDE WHETHER A CORRECT ACTION IS CORRECT. Before 2026-09-09 the
    # YOUNG half of this pair reported "is GONE at HEAD ... not archived" on a plan
    # that had just been archived exactly as the message demands. Both halves are
    # asserted, because a control that only exercises the aged half would have gone
    # green over the bug it exists to catch.
    for age in (1, 999):
        got = tp(
            {"agent/PLAN-a.md": open_row},
            {},
            age=age,
            archived=[f"{ARCHIVE_DIR}/PLAN-a.md"],
        )
        print(
            f"  {'PASS' if got == [] else 'FAIL'}  G-A1/G-A5 CONTROL: an R100 archive is "
            f"silent at age {age} -- one predicate, no age term"
        )
        if got:
            bad += 1
            print(f"        got {got}")

    # G-A3: a finished status over open boxes. The pair matters -- a status the
    # advisory still admits must NOT be reported, or every live plan reds.
    fin = next(iter(FINISHED))
    got = tp({}, {"agent/PLAN-a.md": dict(open_row, status=fin)})
    ok = any("switches the check off" in g for g in got)
    print(f"  {'PASS' if ok else 'FAIL'}  G-A3: Status: {fin} over open boxes is refused")
    if not ok:
        bad += 1
    got = tp({}, {"agent/PLAN-a.md": open_row})
    print(
        f"  {'PASS' if got == [] else 'FAIL'}  G-A3 CONTROL: an in-scope status over open boxes is silent"
    )
    if got:
        bad += 1
    # And the plan this branch never TOUCHED is not judged -- demanding a header
    # change in somebody else's file is how a gate gets routed around.
    got = tp({}, {"agent/PLAN-a.md": dict(open_row, status=fin)}, touched=set())
    print(f"  {'PASS' if got == [] else 'FAIL'}  G-A3 CONTROL: an untouched plan is not judged")
    if got:
        bad += 1

    # G-A4: new debt must name an owner.
    got = tp({}, {"agent/PLAN-a.md": dict(open_row, owner="unowned")}, added={"agent/PLAN-a.md"})
    ok = any("no resolvable" in g for g in got)
    print(f"  {'PASS' if ok else 'FAIL'}  G-A4: a NEW plan with open boxes and no Owner is refused")
    if not ok:
        bad += 1
    got = tp({}, {"agent/PLAN-a.md": dict(open_row, owner="unowned")}, added=set())
    print(
        f"  {'PASS' if got == [] else 'FAIL'}  G-A4 CONTROL: an EXISTING unowned plan is not judged"
    )
    if got:
        bad += 1

    # G-A0 must fire in both directions, and stay silent on agreement.
    tree = {
        "p.md": {
            "status": "executing",
            "owner": "x",
            "open": 2,
            "done": 1,
            "open_sigs": ["aa", "bb"],
            "done_sigs": ["cc"],
        }
    }
    same = {"plans": {"p.md": dict(tree["p.md"])}}
    cases = [
        ("a plan with no ledger entry", tree, {"plans": {}}, "has no ledger entry"),
        ("a ledger entry with no plan", {}, same, "not in agent/ any more"),
        (
            "a count the ledger disagrees with",
            tree,
            {"plans": {"p.md": dict(tree["p.md"], open=1)}},
            "ledger says",
        ),
        (
            "a box the ledger still lists",
            tree,
            {"plans": {"p.md": dict(tree["p.md"], open_sigs=["aa", "bb", "zz"])}},
            "open_sigs disagree",
        ),
    ]
    for label, t, led, needle in cases:
        got = diff_problems(t, led)
        hit = any(needle in g for g in got)
        print(f"  {'PASS' if hit else 'FAIL'}  {label} is reported")
        if not hit:
            bad += 1
            print(f"        got {got}")
    ok = diff_problems(tree, same) == []
    print(f"  {'PASS' if ok else 'FAIL'}  CONTROL: a ledger that agrees is silent")
    if not ok:
        bad += 1

    # G-A6, whose whole job is to refuse rather than pass.
    ok = any("glob lost the corpus" in m for m in vacuity_problems({}, 0))
    print(f"  {'PASS' if ok else 'FAIL'}  an empty corpus refuses rather than passing")
    if not ok:
        bad += 1
    blind = {f"p{i}.md": {"open": 0, "done": 0} for i in range(MIN_PLAN_FILES)}
    ok = any("resolved NONE of them" in m for m in vacuity_problems(blind, 40))
    print(f"  {'PASS' if ok else 'FAIL'}  raw checkbox lines the parser resolves to zero refuse")
    if not ok:
        bad += 1
    return bad


def main(argv: list[str]) -> int:
    update = "--update" in argv
    if refusal := controls.controls_first("plan checkbox ledger", selftest):
        return refusal

    scanned = scan(ROOT)
    raw = raw_box_lines(ROOT)
    problems = vacuity_problems(scanned, raw)
    if problems:
        print(f"✗ plan checkbox ledger ({len(problems)} problem(s)):", file=sys.stderr)
        for p in problems:
            print(f"    {p}", file=sys.stderr)
        return 1

    if update:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        doc = {
            "$comment": (
                "GENERATED by .ci/scripts/quality/check_plan_boxes.py --update. Do not "
                "hand-edit: the point of this file is that it is a SECOND reading of the "
                "plan files, so a hand-edit is the one thing that can make it agree with "
                "a tree it does not describe. Signatures are the parser's own dedup key "
                "hashed, so re-wrapping a box is free and rewriting it is not."
            ),
            "plans": {k: scanned[k] for k in sorted(scanned)},
        }
        LEDGER.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        print(
            f"✓ wrote {LEDGER.relative_to(ROOT)}: {len(scanned)} plan(s), "
            f"{sum(p['open'] for p in scanned.values())} open, "
            f"{sum(p['done'] for p in scanned.values())} ticked"
        )
        return 0

    try:
        ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(
            f"✗ {LEDGER.relative_to(ROOT)} is missing, so nothing can be compared.\n"
            f"  Generate and commit it:\n"
            f"    npm run check:ci-plan-boxes -- --update\n"
            f"    git add {LEDGER.relative_to(ROOT)}",
            file=sys.stderr,
        )
        return 1
    except (OSError, ValueError) as exc:
        print(
            f"✗ cannot read {LEDGER.relative_to(ROOT)} ({exc}); refusing a verdict", file=sys.stderr
        )
        return 1

    problems = diff_problems(scanned, ledger)
    # G-A1..G-A5. Only once G-A0 agrees: comparing a base ledger against a head tree the
    # head ledger does not describe would report the ledger's own staleness as a
    # vanished box, which blames the wrong thing.
    compared = 0
    base = None if problems else base_ref()
    if base:
        tprob, compared = transition_problems(scanned, base)
        problems += tprob
    if problems:
        print(
            f"✗ plan checkbox ledger: {len(problems)} disagreement(s) with the tree",
            file=sys.stderr,
        )
        for p in problems:
            print(f"    {p}", file=sys.stderr)
        print(
            "\n  A box is the only durable record of a task once a context ends, so the\n"
            "  ledger exists to make one disappearing visible in a diff.\n"
            "  If you ticked, added or moved a box on purpose, regenerate and commit:\n"
            "    npm run check:ci-plan-boxes -- --update\n"
            f"    git add {LEDGER.relative_to(ROOT)}",
            file=sys.stderr,
        )
        return 1

    print(
        f"✓ plan boxes: {len(scanned)} plan file(s) (floor {MIN_PLAN_FILES}) agree with "
        f"{LEDGER.relative_to(ROOT)} -- {sum(p['open'] for p in scanned.values())} open, "
        f"{sum(p['done'] for p in scanned.values())} ticked, "
        f"{raw} raw checkbox line(s) seen"
    )
    if base and compared < 0:
        print(
            f"  G-A1..G-A5 DID NOT RUN: {base[:9]} carries no {LEDGER.name}, so there is no "
            f"base to compare against. Expected exactly once -- on the branch that "
            f"introduces the ledger. This is a SKIP, not a clean result."
        )
    elif base:
        print(
            f"✓ transitions: {compared} box(es) open at {base[:9]} all survive at HEAD "
            f"(ticked, moved, or still open); the archive took only byte-identical "
            f"renames; no finished-status plan hides open boxes; no new plan carries "
            f"unowned debt"
        )
    else:
        print("  NO BASE REF: G-A1..G-A5 did not run. G-A0 and G-A6 above still did.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
