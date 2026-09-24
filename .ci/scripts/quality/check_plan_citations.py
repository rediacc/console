#!/usr/bin/env python3
"""check:ci-plan-citations -- a citation ADDED to agent/ must resolve today.

WHY THIS GATE EXISTS, and it has a measurement rather than an opinion.

`agent/` is where this repo keeps the reasoning behind its own machinery, and the value of a plan or a record is entirely in the pointers it carries: a file:line, a gate id, another plan, a commit or a blob. Measured 2026-09-06 while designing W12: of 71 commit-shaped tokens already cited across those files, **37 no longer resolve**. More than half of the durable pointers this tree
relies on are dead, and nothing reported it -- not one of them.

The cure is NOT a sweep of the 37. A sweep fixes a day; this gate fixes the slope. It judges ONLY the lines a change ADDS, so:

  * the existing dead citations are not this change's problem and do not red it;
  * a change that adds a NEW dead pointer is red at the moment it is cheapest to
    fix, which is while the author still knows what they meant.

WHAT IS ASSERTED. Every citation on an added line resolves, using `wl_planrec.resolve` and NOTHING ELSE. There is deliberately no second copy of any resolver here: `citation_state`'s path regex alone carries five separately paid-for extension rounds (dotfiles, .astro, .mdx, .cast, leading dots), and a fresh regex in this file would re-open every one of them. Five kinds:

  fileline   `path/to/file.ext:123` -- the file exists and has that many lines.
  plan       `agent/PLAN-x.md` -- on disk (a COMPACTED record still is, which is
             the whole point of compacting in place rather than deleting).
  gate       `check:x` -- a key in package.json's scripts.
  object     a 7-to-40 hex token -- a real blob OR a real commit. Either is
             legitimate in a plan and demanding one would flag the other.

WHAT IS DELIBERATELY NOT ASSERTED, so a green is not read as more than it is:

  * Nothing here checks that the cited line SAYS what the sentence claims. That
    is `wl_checks.cited_excerpts`'s job and ultimately a reader's. This proves
    the pointer lands somewhere, which is the half a machine can settle.
  * An ALL-DIGIT hex token is never judged. `[0-9a-f]{7,40}` also matches a CI
    run id (100500447167), a date and an issue number, and those are the
    evidence shapes `wl_checks.completion_evidence` treats as first-class.
    Laundering a run id out of a plan to defend against an all-digit git object,
    which does not occur, would destroy the most citable fact in the file. The
    same asymmetry, in the same direction, as `wl_planrec.launder`.
  * A line INSIDE a fenced code block is skipped. A plan that shows the reader
    `git show <40 hex>` as an example is documenting a command, not citing an
    object, and reding on it would teach sessions to stop writing examples.
  * Only `agent/` is in scope. That is where the durable records live and where
    the 37 dead pointers were measured. Widening this to `docs/` is a separate
    decision with a much larger blast radius, and it should be made on its own
    evidence rather than as a side effect of this gate.

THE ANTI-VACUITY HALVES, both of them, because "no findings" and "read nothing" look identical from the outside:

  1. THE CONTROL. `selftest()` runs the real extractor and the real resolvers
     over four tokens that CANNOT resolve and four that MUST, against this
     repository rather than a fixture. Both directions, and the silent half is
     not a formality: "everything reds" is a check that cannot pass, which is
     the shape a gate takes on when a resolver breaks.
  2. THE PARSER-BLIND FLOOR. The extractor is also run over the WHOLE tracked
     `agent/**/*.md` corpus. If that corpus is non-empty and yields ZERO
     citations, the extractor is blind -- a broken regex, a collapsed glob -- and
     the gate refuses a verdict instead of reporting a clean diff. The floor is
     corpus-derived rather than a hand-typed count, per the driver contract's
     floor policy: it is "the corpus must not be silent", not "there must be N".

WHY IT READS THE WORKING TREE, not just HEAD. `git diff <base> -- agent` with no `...` compares the base commit to the WORKING TREE, so it judges uncommitted work too. This program's normal deliverable is an uncommitted tree, and a gate that could only see committed lines would be green on exactly the state it is meant to police. In CI on a pull request the working tree is the head
commit, so the same code path answers the same question.

Exit 0 green, 1 findings or vacuous input, 2 instrument control failed.

---- gate ----
step: Plan citations
needs: none
lane: quality-branch
---- end gate ----
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

import _cipath  # noqa: F401
from rediacc_ci import paths
from rediacc_ci.quality import plan_lifecycle as PL

ROOT = pathlib.Path(
    os.environ.get("PLAN_CITATIONS_ROOT") or pathlib.Path(__file__).resolve().parents[3]
)
# The hop onto the Stop hook's directory, through the package's own resolver. `paths.on_sys_path` is idempotent where a bare `sys.path.insert(0, d)` is not, and `paths.hooks_stop_dir` is the ONE place the `.claude/hooks/stop` literal lives, so the move planned for that program is a one-line change there rather than a sweep of nine call sites. ROOT is passed explicitly: this gate
# honours its own PLAN_CITATIONS_ROOT override, which the resolver's default root does not read.
#
# THIS IS THE GATE THAT GAINED A PACKAGE DEPENDENCY TO LOSE ITS HOP, and it is the only one of the five: the other four already imported `rediacc_ci`. Said out loud because it is a real trade, not a free tidy -- `.ci/rediacc_ci` must now be present for this gate to start. Every harness that runs it already copies that directory (`.ci/rediacc_ci/tests/gates/test_gate_gate_anti_vacuity.py` names it explicitly), and
# a missing package fails loudly at the import rather than skipping a check.
paths.on_sys_path(paths.hooks_stop_dir(ROOT))

try:
    import wl_checks as CK
    import wl_planfid as PFID
    import wl_planrec as R
except ImportError as _exc:  # pragma: no cover -- exercised by `.ci/rediacc_ci/tests/gates/test_gate_gate_anti_vacuity.py`
    # A check that cannot see must SAY it cannot see. Every resolver this gate uses lives in those modules on purpose; without them there is nothing to compare and no verdict to give.
    print(
        f"VACUOUS INPUT: cannot import the citation resolvers from "
        f"{ROOT / '.claude' / 'hooks' / 'stop'} ({_exc}). This gate resolves pointers ONLY "
        f"through wl_planrec/wl_checks, so without them it has no oracle.",
        file=sys.stderr,
    )
    sys.exit(1)

#: The corpus, and the predicate that defines it. `agent/` holds three different
#: kinds of document and only one of them belongs here.
#:
#: THE TEST IS OWNERSHIP: can the person who READS the finding fix it?
#:
#:   agent/PLAN-*.md, agent/INDEX.md   IN SCOPE. Shared, durable, and editable by
#:       any session. These are also where the defect was measured: 37 of 71
#:       commit-shaped tokens cited across the PLANS no longer resolve.
#:
#:   agent/<session>/STATE.md          OUT. It is per-session and, by construction
#:       (`wl_store.py:403`), READ-ONLY to every session but its owner -- writable
#:       only through `worklist.py --state`, which rewrites the whole section. A
#:       red here names a line the reader is forbidden to touch, possibly written
#:       by a session that no longer exists. That is a finding with no legal
#:       remedy, which is how a gate earns a suppression.
#:
#:   agent/pr/*.md, agent/worklist/*   OUT. Generated. The fix for a dead pointer
#:       in a generated file is a change to the generator, and reporting it at the
#:       artifact teaches the wrong lesson.
#:
#: WHAT THIS CANNOT SEE, stated so a green is not read as more than it is: a dead
#: pointer added to a STATE.md is invisible here. Measured 2026-09-06, this branch
#: has two of them (`promote-stable.yml:68`, which lives at
#: `.github/workflows/promote-stable.yml`, and `65820fd74`, a private/account
#: gitlink that is not an object in this repository). Both are real and both were
#: found by this gate before the scope was narrowed; they are reported to the
#: driver rather than silently dropped. The narrowing is about who can act on a
#: finding, not about whether the finding is true.
SCOPE_DIR = "agent"
SCOPE_SUFFIX = ".md"


def in_scope(rel):
    """Is this path one any session may fix? See the SCOPE_DIR block above."""
    if not rel or not rel.endswith(SCOPE_SUFFIX):
        return False
    if rel == "agent/INDEX.md":
        return True
    # Every folder a plan may sit in, which since the tree-lifecycle change is four rather than one. A prefix test here would drop the whole corpus the day the migration lands, and the gate would go green over a scope it had stopped reading.
    return PL.is_plan_path(rel)


#: An object citation must be at least this long. NINE, and the number is
#: MEASURED rather than borrowed from git.
#:
#: `wl_planrec.HEXTOK_RE` matches 7 to 40 hex because 7 is git's own abbreviation
#: floor, and that is right for LAUNDERING (where a false positive costs one
#: `[unresolved]` in model prose). It is wrong here, because in `agent/` an
#: 8-hex token is overwhelmingly a SESSION PREFIX, a PR-TASK id or an epic id --
#: none of which is a git object and none of which is meant to be one.
#:
#: Measured 2026-09-06 over the lines this branch adds under agent/: 28 object
#: tokens of length 8, of which **20 of 20 distinct ones resolve to nothing**,
#: because every one is an identity rather than a sha; and 11 of length 9, of
#: which 8 resolve and 1 does not. So a floor of 9 removes an entire false
#: class and keeps the true finding. Nine is also this repo's own convention:
#: `wl_planrec.sha9` is what `done=` and `Full-Text:` are written with.
#:
#: WHAT IT CANNOT SEE, said out loud: a genuinely dead 7- or 8-character sha is
#: now invisible to this gate. That is the trade, taken knowingly, because the
#: alternative is a gate that reds on every session id in every STATE.md and is
#: therefore switched off within a day.
OBJECT_MIN = int(os.environ.get("PLAN_CITATIONS_OBJECT_MIN", "9"))

#: The trailing 12-hex group of a canonical UUID
#: (`nnnnnnnn-nnnn-nnnn-nnnn-NNNNNNNNNNNN`) is always pure hex and always
#: satisfies HEXTOK_RE once it reaches OBJECT_MIN, so a Stripe secret id, a DB
#: row id or a JWT claim quoted in a plan reads as a dead git object citation
#: purely by coincidence of shape. Measured 2026-09-14: 9 such tokens across
#: this corpus, none of them a git object and none of them a typo -- the same
#: false-positive class `aea2bc733552` was, one docstring up, but for UUIDs
#: rather than shape-duplication fingerprints. Matched by requiring the four
#: preceding hex groups immediately before the candidate token, so a bare hex
#: run with no UUID dashes in front of it is unaffected.
UUID_TAIL_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-([0-9a-f]{12})", re.IGNORECASE
)

#: A REGISTRY DIGEST IS NEVER A GIT OBJECT, and it is the same false-positive
#: class as the UUID tail above: a long hex run that satisfies HEXTOK_RE purely
#: by coincidence of shape, sitting behind an unambiguous marker that says what
#: it really is. `sha256:` is that marker, and nothing in this repository's
#: history is addressed that way.
#:
#: Measured 2026-09-15, on `agent/plans/PLAN-w7p4w-docker-cutover.md` as committed by
#: 696a45bf9: four findings, all of them container image digests cited as the
#: EVIDENCE that a canary image shared no layers with `:edge`/`:stable` --
#: `sha256:27bb0e6e2c...b7f2d` (x3) and `sha256:a77e698892cc...`. None resolves
#: in this clone or in any of the four submodules, correctly, because none is a
#: git object. The gate was asking a plan to prove a registry digest is a commit.
#:
#: The alternative was rewording the plan to break the hex run, which would have
#: contorted correct content to satisfy a check AND destroyed the digests that
#: were the point of the sentence.
#:
#: Matched by requiring the `sha256:` immediately before the candidate, so a bare
#: hex run without it is unaffected -- the same narrowing UUID_TAIL_RE uses, and
#: for the same reason: this must not become a general amnesty for long tokens.
#: An ellipsised digest (`sha256:27bb0e6e2c...b7f2d`) is matched on its leading
#: run, which is the part HEXTOK_RE would otherwise have judged.
DIGEST_RE = re.compile(r"sha256:([0-9a-f]{7,64})", re.IGNORECASE)

#: A TEST'S OWN CONTENT FINGERPRINT IS NEVER A GIT OBJECT, and this is the same
#: marker-behind-the-token shape DIGEST_RE uses, for the same reason.
#: `shape_fingerprints()` below already answers this question for ONE fingerprint
#: scheme, and it does it from the seed file because there is a seed file to read.
#: `.ci/rediacc_ci/tests/test_canonical_sys_path_hop.py:185` defines a second
#: scheme -- a sha1 prefix over `ast.unparse` output, the stable id its BASELINE
#: and FRESH tables key on -- and there is no data file anywhere that carries
#: those values, so no authority exists to read. The marker is the authority
#: instead, exactly as `sha256:` is for a registry digest.
#:
#: Measured 2026-09-23 on `agent/plans/_done/PLAN-sys-path-canonical-form.md`: six
#: findings, all of them the two fingerprints in its Findings table, none of them
#: resolvable and none of them ever intended to be. The workaround reached for
#: first was inserting a hyphen into each value so it fell under the object floor,
#: which silenced the gate by corrupting the data the table exists to carry.
#:
#: Matched by requiring `fingerprint:` immediately before the candidate, so a bare
#: hex run without it is unaffected.
FINGERPRINT_RE = re.compile(r"fingerprint:([0-9a-f]{7,64})", re.IGNORECASE)

#: A BACKGROUND AGENT ID IS NEVER A GIT OBJECT, and this is the third instance
#: of the same false-positive class the two blocks above answer: a long hex run
#: that satisfies HEXTOK_RE by coincidence of shape alone.
#:
#: The harness mints one id per background agent as `a` followed by 16 hex
#: characters, so exactly 17. Plans name them constantly, because naming the
#: worker that did a piece of work is how a plan records provenance -- `## Root
#: cause (Plan agent a2fd17b15c79c8ceb)` is the shape, and there are three more
#: in one paragraph of `agent/plans/_done/PLAN-fix-stop-hook-completion-evidence-refire.md`,
#: whose own prose at :16 already says these are "worker ids that are not git
#: objects". The gate was asking a plan to prove a subagent id is a commit.
#:
#: Measured over `agent/` on 2026-09-23: 13 distinct 17-character hex tokens
#: across four plans. Every one begins with `a`, and not one resolves as a blob
#: or a commit in this clone.
#:
#: THE LENGTH IS THE MARKER, since an agent id carries no `sha256:`-style prefix
#: and the sentences around it vary too much to key on. 17 is a length git never
#: emits here: `core.abbrev` is unset, `git rev-parse --short HEAD` yields 9 on
#: this tree, and a full id is 40. Requiring the leading `a` as well keeps this
#: from becoming the general amnesty for long tokens DIGEST_RE's note warns
#: against -- a 16- or 18-character run is untouched, and so is a 17-character
#: one that starts with anything else. The residual risk is a sha deliberately
#: abbreviated to exactly 17 that also starts with `a`, and the cost of that is
#: one missed dead pointer, never a false accusation.
AGENT_ID_RE = re.compile(r"(?<![0-9a-zA-Z])(a[0-9a-f]{16})(?![0-9a-zA-Z])")

#: A STOP-HOOK TICK ID IS NEVER A GIT OBJECT, the fourth instance of the class
#: the three blocks above answer: a 12-hex run that satisfies HEXTOK_RE by
#: coincidence of shape alone.
#:
#: `wl_reggate` mints one id per settled fix-set and per judged class, and a plan
#: that reconstructs a stop-by-stop timeline has to name them -- that IS the
#: evidence. Measured 2026-09-23: ten findings in
#: `agent/plans/PLAN-sweep-obligation-carry-forward.md`, every one a tick id in
#: its own timeline table, and two more in
#: `agent/plans/_done/PLAN-fix-stop-hook-completion-evidence-refire.md`. Not one
#: was ever meant to resolve, and the gate was asking those plans to prove a
#: marker key is a commit.
#:
#: Matched by requiring `tick:` immediately before the candidate, the same
#: marker-behind-the-token shape DIGEST_RE and FINGERPRINT_RE use and for the
#: same reason: a bare hex run without the marker stays judged, so this cannot
#: become the general amnesty for long tokens DIGEST_RE's note warns against.
TICK_ID_RE = re.compile(r"tick:([0-9a-f]{7,64})", re.IGNORECASE)

#: THE SAME ID AS A PATH COMPONENT, which is the one place the marker above
#: cannot be written without corrupting the evidence. The Stop hook's judge
#: markers live at `/tmp/claude-worklist/.judge/<rule>-<tick id>.json`, and a
#: plan quoting that path is quoting a filename, not citing an object.
#:
#: Deliberately keyed on the whole `/.judge/` shape rather than on
#: "<word>-<hex>.json" anywhere, so a genuinely dead sha inside some other
#: filename is still reported.
MARKER_FILE_RE = re.compile(r"/\.judge/[a-z][a-z0-9_]*-([0-9a-f]{7,64})\.json")

#: How many findings are printed before the tail is summarised. A wall of
#: findings is a wall nobody reads to the end of, and the fix for the first is
#: usually the fix for the rest.
MAX_SHOWN = int(os.environ.get("PLAN_CITATIONS_MAX_SHOWN", "40"))


def _git(*args) -> str:
    r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=False)
    return r.stdout if r.returncode == 0 else ""


def base_ref() -> str | None:
    """The commit this branch diverged from, or None.

    The same resolution order `check_plan_boxes.base_ref` uses, and for the same reason: CI hands us a branch NAME on a pull_request event and nothing at all on a push, so the merge-base is computed rather than assumed. Diffing against the tip of main would attribute every commit main gained since the branch started to this branch, and every stale citation in them with it.
    """
    cand = os.environ.get("PLAN_CITATIONS_BASE") or ""
    if not cand:
        br = os.environ.get("GITHUB_BASE_REF") or ""
        cand = f"origin/{br}" if br else "origin/main"
    for ref in (cand, cand.replace("origin/", ""), "origin/main", "main"):
        if not ref:
            continue
        got = _git("merge-base", "HEAD", ref).strip()
        if got:
            return got
    return None


HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def added_lines(base):
    """[(rel, lineno, text)] for every line this branch ADDS under the scope.

    Line numbers are the NEW file's, tracked through the hunk headers, because a finding a reader cannot open is a finding they will not act on.
    """
    out = []
    raw = _git("diff", "--unified=0", "--no-color", base, "--", SCOPE_DIR)
    rel, lineno = None, 0
    for line in raw.split("\n"):
        if line.startswith("+++ "):
            path = line[4:].strip()
            # A PATH CONTAINING A SPACE IS QUOTED by git in the diff header, and an unstripped quote makes the `.md` suffix test false -- so the file would be silently skipped rather than judged. Silence is the one failure mode this gate cannot afford, since it is indistinguishable from a clean file.
            if len(path) > 1 and path[0] == '"' and path[-1] == '"':
                path = path[1:-1]
            rel = None if path == "/dev/null" else path.removeprefix("b/")
            continue
        m = HUNK_RE.match(line)
        if m:
            lineno = int(m.group(1))
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue
        if in_scope(rel):
            out.append((rel, lineno, line[1:]))
        lineno += 1
    return out


def _origin_last_content(origin):
    """The newest blob at `origin` that is not itself a stub, or "".

    `carried_lines` used only the blob at `base`, and on a long-lived branch `base` (the merge-base with main) can predate the plan entirely, or predate a reflow that rewrapped every line after `base` but before the move -- either way the base blob shares no verbatim lines with the moved file, and a move that carried no new citation reads as if it had written every line in the
    document. Walking history from HEAD finds the content the move actually carried, regardless of how far behind `base` sits.
    """
    log = _git("log", "--format=%H", "--", origin)
    for sha in log.split("\n"):
        if not sha:
            continue
        raw = _git("show", "%s:%s" % (sha, origin))
        if raw and not PL.looks_like_stub(raw):
            return raw
    return ""


def carried_lines(root, base, rel):
    """The lines `rel` already carried, under the path it moved from.

    A set of whole lines rather than a diff: the question is only whether THIS change wrote the citation, and a line that is verbatim in a pre-move document was not written here whatever moved around it. It errs in the safe direction -- a genuinely new citation line is in neither blob, so it is still judged.

    UNION OF TWO READS, not one. `git show <base>:<origin>` is kept because it is cheap and correct on a short-lived branch; `_origin_last_content` is added because `base` alone is wrong whenever the origin predates `base` or a reflow already changed every line's text since `base` -- measured 2026-09-21, the 103-plan migration's own base blob excluded ONLY 3370 of the roughly 3650
    lines it should have.
    """
    origin = PL.moved_from(root, rel)
    if not origin:
        return frozenset()
    from_base = _git("show", "%s:%s" % (base, origin))
    lines = set(from_base.split("\n")) if from_base else set()
    lines |= set(_origin_last_content(origin).split("\n"))
    return frozenset(lines)


def drop_moved_lines(root, base, rows):
    """`rows` without the lines a stubbed move carried in from another path."""
    carried = {}
    out = []
    for rel, lineno, text in rows:
        if rel not in carried:
            carried[rel] = carried_lines(root, base, rel)
        if text in carried[rel]:
            continue
        out.append((rel, lineno, text))
    return out


def fenced_lines(root, rel):
    """The set of 1-based line numbers inside a fenced code block in `rel`.

    Read from the NEW file rather than inferred from the diff, because a hunk carries no fence context: an added line in the middle of a block looks exactly like an added line in prose. `PFID.FENCE_RE` is the same fence test `plan_tasks` uses, so "inside a fence" means here what it means everywhere
    else in this repo.
    """
    try:
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    out, fenced = set(), False
    for i, raw in enumerate(text.splitlines(), start=1):
        if PFID.FENCE_RE.match(raw):
            fenced = not fenced
            out.add(i)
            continue
        if fenced:
            out.add(i)
    return out


def citations(text):
    """[(kind, token)] for every pointer on one line, in resolve()'s kinds.

    THE ORDER MATTERS and it is the order `wl_planrec.launder` uses: file:line first, because a path fragment inspected as hex would be rewritten out from under the citation resolver. Plans before gates before objects for the same reason -- each later shape is a superset of characters the earlier one owns.
    """
    out, spans = [], []

    def take(rx, kind, group=0):
        for m in rx.finditer(text or ""):
            if any(m.start() < e and s < m.end() for s, e in spans):
                continue
            spans.append((m.start(), m.end()))
            out.append((kind, m.group(group)))

    take(CK.CITE_RE, "fileline")
    take(R.PLAN_REF_RE, "plan")
    take(R.GATE_RE, "gate")
    uuid_tail_spans = [u.span(1) for u in UUID_TAIL_RE.finditer(text or "")]
    digest_spans = [d.span(1) for d in DIGEST_RE.finditer(text or "")]
    agent_id_spans = [a.span(1) for a in AGENT_ID_RE.finditer(text or "")]
    fingerprint_spans = [f.span(1) for f in FINGERPRINT_RE.finditer(text or "")]
    tick_id_spans = [t.span(1) for t in TICK_ID_RE.finditer(text or "")]
    tick_id_spans += [t.span(1) for t in MARKER_FILE_RE.finditer(text or "")]
    for m in R.HEXTOK_RE.finditer(text or ""):
        if any(m.start() < e and s < m.end() for s, e in spans):
            continue
        tok = m.group(1)
        # See the docstring: an all-digit token is a run id, a date or an issue number far more often than it is a git object, and it is never judged.
        if tok.isdigit() or len(tok) < OBJECT_MIN:
            continue
        # The trailing group of a UUID, not a git object. See UUID_TAIL_RE.
        if (m.start(1), m.end(1)) in uuid_tail_spans:
            continue
        # A container image digest, not a git object. See DIGEST_RE.
        if (m.start(1), m.end(1)) in digest_spans:
            continue
        # A background agent id, not a git object. See AGENT_ID_RE.
        if (m.start(1), m.end(1)) in agent_id_spans:
            continue
        # A test's own content fingerprint, not a git object. See FINGERPRINT_RE.
        if (m.start(1), m.end(1)) in fingerprint_spans:
            continue
        # A stop-hook tick id, not a git object. See TICK_ID_RE and MARKER_FILE_RE.
        if (m.start(1), m.end(1)) in tick_id_spans:
            continue
        # A SHAPE FINGERPRINT IS NOT A GIT OBJECT, and it looks exactly like one: 12 hex characters, which this gate judges as an abbreviated sha and can never resolve. `check:ci-shape-duplication` prints these and tells the reader to cite them -- "put its FINGERPRINT into shape-duplication-seed.json" -- so a plan explaining WHY a shape was accepted has to name it, and every such
        # plan line was an unresolvable-pointer failure. Measured 2026-09-08: `94f3f7e6f351` and `aea2bc733552` both reported that way, while an earlier plan's `98b21fa52e5d` passed only because it happens to prefix a real object in this clone -- so the gate was already wrong here and was being saved by coincidence.
        #
        # The seed file is the authority, not a pattern: a token is a fingerprint only if the corpus actually carries it, which cannot silence a typo'd sha.
        if tok in shape_fingerprints(ROOT):
            continue
        out.append(("object", tok))
    return out


_SHAPE_FINGERPRINTS: dict[str, frozenset[str]] = {}


def shape_fingerprints(root=None):
    """Every fingerprint `check:ci-shape-duplication` has recorded, seeded or accepted.

    Read from the seed rather than pattern-matched, so a hex token only stops being an object citation when the duplication corpus really carries it. A missing or malformed seed yields the EMPTY set, which fails safe: every hex token stays judged as an object.
    """
    root = ROOT if root is None else root
    key = str(root)
    if key not in _SHAPE_FINGERPRINTS:
        seed = pathlib.Path(root) / "scripts" / "data" / "shape-duplication-seed.json"
        try:
            data = json.loads(seed.read_text(encoding="utf-8"))
            names = set(data.get("shapes") or []) | set((data.get("accepted") or {}).keys())
        except (OSError, ValueError, AttributeError):
            names = set()
        _SHAPE_FINGERPRINTS[key] = frozenset(str(n) for n in names)
    return _SHAPE_FINGERPRINTS[key]


def submodule_paths(root):
    """The submodule prefixes declared in `.gitmodules`, or ().

    Read from the file rather than hardcoded, because the set changes and a hardcoded list would go stale in exactly the direction that produces false findings: a submodule added later would not be recognised.
    """
    out = []
    for ln in _git("config", "-f", ".gitmodules", "--get-regexp", r"\.path$").split("\n"):
        parts = ln.split()
        if len(parts) == 2 and (pathlib.Path(root) / parts[1]).is_dir():
            out.append(parts[1])
    return tuple(out)


def commit_is_reachable(root, token) -> bool:
    """Is `token` a commit REACHABLE FROM HEAD, not merely present in this clone?

    PRESENCE IS THE WRONG QUESTION FOR A COMMIT, and asking it has now cost two CI rounds. A rewrite -- `filter-branch`, a rebase, `gh pr merge --rebase` -- leaves the pre-rewrite commits sitting in the object database, reachable from reflogs and `refs/original`. `git cat-file -t` happily answers `commit` for every one of them on the machine that did the rewrite, and a FRESH CLONE
    has none of them. So a citation to an orphan passes locally and fails in CI, which is the worst of both: green where it is cheap to fix, red where it is expensive.

    Round 43 of this wave recorded exactly this after the operator-authorised history rewrite -- 149 stale shas all resolved locally while not one was an ancestor of HEAD -- and named `git merge-base --is-ancestor` as the honest test. It was written down and not wired in; measured 2026-09-15, six orphaned citations in agent/plans/PLAN-b2-emit-matrix.md passed this gate locally and
    reddened `Quality / Branch` in CI.

    ONLY COMMITS GET THIS TEST, and the asymmetry is the design rather than an exception. A blob or tree is CONTENT-addressed: it is an ancestor of nothing, `--is-ancestor` is meaningless for it, and demanding reachability would flag every correctly-cited blob. That is also precisely why this gate's own advice
    for a rewritten commit is "cite the blob id instead" -- a blob survives the
    rewrite the commit does not.

    SAFE ON THIS REPOSITORY'S CI because `quality-branch` checks out with `fetch-depth: 0` (full COMMIT history) and `filter: blob:none` (blobs lazily fetched). Ancestry needs commits, which are all present; it never needs a blob.
    """
    if not R.resolve(root, "commit", token)[0]:
        return False
    r = subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", token, "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return r.returncode == 0


def unresolved(root, kind, token):
    """(bad, why) -- False means the pointer lands somewhere real.

    `object` is the one kind with THREE acceptable answers, so it is asked up to three times. Demanding a blob would flag every legitimate commit, demanding a commit would flag every blob, and a record is entitled to carry any of the three -- a `tree` is rare (a citation into a `git filter-branch`/rewrite control naming a tree id directly) but a real, correctly-cited object that
    neither `blob` nor `commit` resolves.

    A COMMIT MUST ALSO BE REACHABLE FROM HEAD; a blob or tree need only exist. See `commit_is_reachable` for why the two differ.
    """
    if kind == "object":
        if (
            R.resolve(root, "blob", token)[0]
            or commit_is_reachable(root, token)
            or R.resolve(root, "tree", token)[0]
        ):
            return False, ""
        if R.resolve(root, "commit", token)[0]:
            return True, (
                "is a commit that EXISTS in this clone but is not an ancestor of HEAD, so "
                "a fresh checkout will not have it at all. That is what a rewrite leaves "
                "behind -- `filter-branch`, a rebase, or `gh pr merge --rebase` -- and it "
                "is why this passes locally and reds in CI. Cite the commit it became, or "
                "the blob id (`git hash-object <file>`), which is content-addressed and "
                "survives the rewrite"
            )
        return True, (
            "names neither a blob nor a commit in this clone. Three things it could be, "
            "and the fix differs: (a) a commit sha on a branch, which `gh pr merge "
            "--rebase` REWRITES -- cite the blob id instead (`git hash-object <file>`), "
            "which is content-addressed and survives the merge; (b) a SUBMODULE gitlink, "
            "which is never an object in this repository -- name the submodule beside it "
            "so a reader knows where to look; (c) a typo"
        )
    ok, why = R.resolve(root, kind, token)
    if ok:
        return False, why
    if kind == "fileline":
        # A SUBMODULE-RELATIVE PATH IS STILL A FINDING, but not the one the plain message describes. A plan about renet naturally writes `pkg/chunkstore/uploader.go:71`, which is a real file -- inside private/renet, and unreachable from the console root where every reader of the plan is standing. "Does not exist" sends them looking for a deleted file; naming the submodule turns the
        # same red into a one-word fix. Measured 2026-09-06 over the whole plan corpus: 40 of the unresolvable file:line citations, and this class is most of them.
        head = token.split(":", 1)[0]
        for sub in submodule_paths(root):
            if (pathlib.Path(root) / sub / head).is_file():
                return True, (
                    "does not exist at the repository root, but %s/%s does. Write the "
                    "submodule-qualified path so a reader standing in this repo can "
                    "follow it" % (sub, head)
                )
    return True, why


def absent_submodules(root):
    """Declared submodule paths whose working tree is NOT populated here.

    WHY THIS EXISTS. `quality-branch` -- the lane that runs this gate -- checks out
    with no `submodules:` key, which is GitHub Actions' default of false. So in CI
    `private/renet/**` is an empty directory, and every `private/renet/pkg/...:NNN` citation in the corpus resolved to "does not exist": 22 findings on the first real run, every one of them a correct pointer into code the lane had chosen not to fetch.

    That direction of wrongness is the expensive one. A false POSITIVE here asks a reader to DELETE a citation that is perfectly good, and the gate's own advice block tells them how ("a file:line that moved needs re-reading"). Follow it and you lose the pointer permanently.

    SCOPED TO THIS GATE ON PURPOSE, and this is the part not to "simplify" later. The obvious fix is to teach `citation_state()` about submodules, and that would be wrong: it is shared with the stop hook's own claim-verification (`worklist.py`, `wl_planrec.py`, `test-completion-evidence.py`), where a session DOES have the submodule checked out, so "I cannot verify this" must stay a
    refusal rather than become a skip. Widening the shared resolver would teach the anti-hallucination check to wave through exactly the claims it exists to catch. So the filter lives here, in the caller, and the resolver keeps failing closed.
    """
    # `-f <root>/.gitmodules`, NOT the bare relative name. `_git` anchors every call to the module-level ROOT, so a bare `.gitmodules` reads the real repo's
    # while the `root / path` below reads the caller's -- the two agree in
    # production (root IS ROOT) and diverge in any fixture, which is how a control
    # for this function came back naming three submodules the fixture never had.
    # A helper whose two halves read different trees is a helper that cannot be tested, and an untestable filter that excuses a whole directory is the last thing this gate should carry.
    out = []
    manifest = pathlib.Path(root) / ".gitmodules"
    if not manifest.is_file():
        return out
    for line in _git("config", "-f", str(manifest), "--get-regexp", r"\.path$").split("\n"):
        parts = line.split()
        if len(parts) != 2:
            continue
        path = pathlib.Path(root) / parts[1]
        # Populated means "has content". An uninitialised submodule is an empty directory, not a missing one, so `is_dir()` alone answers yes and would make this filter inert in precisely the case it is written for.
        if not path.is_dir() or not any(path.iterdir()):
            out.append(parts[1])
    return sorted(out)


def problems_for(root, rows, skip_prefixes=()):
    """[str] -- one finding per unresolvable citation on an added line."""
    out, fences = [], {}
    for rel, lineno, text in rows:
        if rel not in fences:
            fences[rel] = fenced_lines(root, rel)
        if lineno in fences[rel]:
            continue
        for kind, token in citations(text):
            # Only a PATH citation can point into a submodule. An object or gate token that happens to start with those characters is not excused.
            if kind in ("fileline", "plan") and any(
                token.startswith(p + "/") for p in skip_prefixes
            ):
                continue
            bad, why = unresolved(root, kind, token)
            if bad:
                out.append(f"{rel}:{lineno}: adds {kind} citation `{token}` -- {why}")
    return out


def corpus_citations(root):
    """(files, citations) over the whole tracked corpus. The parser-blind floor.

    Counted with the SAME extractor the diff uses, which is the only way the count means anything: a floor computed by a second, healthier parser would stay comfortably above zero while the real one saw nothing.
    """
    listing = _git("ls-files", "--", SCOPE_DIR).split("\n")
    files = [f for f in listing if in_scope(f.strip())]
    n = 0
    for rel in files:
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for raw in text.splitlines():
            n += len(citations(raw))
    return len(files), n


# --------------------------------------------------------------------------- CONTROL FIRST. Against the REAL repository rather than a fixture, deliberately: every oracle here is a property of THIS tree (a plan on disk, a gate in
# package.json, a commit in this history), so a fixture would prove that the
# resolvers work on a fixture. What must be true is that they work here.


def selftest(root):
    """Plant one unresolvable pointer per kind and require a finding; then the same four kinds resolvable and require SILENCE. Returns the number of control failures."""
    bad = 0

    def ck(label, ok, detail=""):
        nonlocal bad
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
        if not ok:
            bad += 1
            if detail:
                print(f"        {detail}")

    plans = [f for f in _git("ls-files", "--", SCOPE_DIR).split("\n") if "/PLAN-" in f]
    # IN-SCOPE ONLY, not just "the alphabetically first /PLAN- path under agent/": `git ls-files` sorts `agent/PLAN-*.md` before `agent/archive/...` while any flat-root stub existed, but the 2026-09-22 cleanup deleted every one of those, so plans[0] could silently become an archive path that neither PLAN_REF_RE nor in_scope() recognises -- exactly the failure that surfaced when it did.
    scoped = [p for p in plans if in_scope(p)]
    head = _git("rev-parse", "HEAD").strip()
    if not plans or not scoped or not head:
        ck(
            "the control has something real to point at",
            False,
            f"{len(plans)} plan(s), {len(scoped)} in scope, HEAD={head!r}",
        )
        return bad

    dead = [
        ("fileline", "agent/PLAN-there-is-no-such-plan-zzz.md:9"),
        ("plan", "agent/PLAN-there-is-no-such-plan-zzz.md"),
        ("gate", "check:no-such-gate-zzz"),
        ("object", "deadbeef" * 5),
    ]
    live = [
        ("fileline", "package.json:1"),
        ("plan", scoped[0]),
        ("gate", "check:ci-plan-record"),
        ("object", head),
    ]
    for kind, token in dead:
        got, _why = unresolved(root, kind, token)
        ck(f"an unresolvable {kind} citation is reported ({token[:44]})", got)
    for kind, token in live:
        got, why = unresolved(root, kind, token)
        ck(f"CONTROL: a real {kind} citation is SILENT ({token[:44]})", not got, why)

    # THE ANCESTRY RULE FOR COMMITS, both directions. An ORPHAN IS CONSTRUCTED rather than borrowed from this clone's reflog: the whole point is that a fresh CI checkout has no orphans, so a control that relied on finding one would silently stop testing anything there -- which is the exact failure mode this rule exists to close.
    tree = _git("rev-parse", "HEAD^{tree}").strip()
    # THE IDENTITY IS SUPPLIED, because `commit-tree` refuses without one: "Author identity unknown -- Please tell me who you are". A GitHub runner configures no git identity at any scope, so this control built its orphan fine on every developer machine and FAILED on the runner -- the exact environment-dependence it exists to catch, in the control itself. `-c` rather than env vars:
    # it is scoped to this one command and cannot leak into anything else the gate runs.
    orphan = _git(
        "-c",
        "user.name=plan-citations control",
        "-c",
        "user.email=control@invalid",
        "commit-tree",
        tree,
        "-m",
        "plan-citations control: unreachable",
    ).strip()
    if orphan:
        ck(
            "an ORPHANED commit is reported even though it EXISTS in this clone "
            "(the rewrite shape: passes locally, reds in a fresh checkout)",
            unresolved(root, "object", orphan)[0],
            unresolved(root, "object", orphan)[1],
        )
        ck(
            "CONTROL: and the orphan really IS present, so the finding is about "
            "REACHABILITY and not about a missing object",
            R.resolve(root, "commit", orphan)[0],
        )
    else:
        ck("the ancestry control could build an orphan to test with", False)

    blob = _git("rev-parse", "HEAD:package.json").strip()
    ck(
        "CONTROL: a real BLOB citation is untouched by the ancestry rule -- it is "
        "content-addressed and an ancestor of nothing",
        blob and not unresolved(root, "object", blob)[0],
        blob,
    )
    ck(
        "CONTROL: a real TREE citation is untouched for the same reason",
        tree and not unresolved(root, "object", tree)[0],
        tree,
    )

    # THE SUBMODULE PRE-FILTER, both directions, because a skip is one typo away
    # from a suppression and this one excuses an entire directory tree.
    rows = [("agent/PLAN-zzz.md", 1, "see private/zzz/pkg/NOPE/nope.go:99")]
    ck(
        "a citation into an ABSENT submodule is skipped, not reported",
        problems_for(root, rows, ("private/zzz",)) == [],
    )
    ck(
        "CONTROL: the same dead citation IS reported when the submodule is present",
        len(problems_for(root, rows, ())) == 1,
        problems_for(root, rows, ()),
    )
    ck(
        "CONTROL: the skip is scoped to that submodule, not to every path",
        len(problems_for(root, [("agent/PLAN-zzz.md", 1, "see nope/nope.go:9")], ("private/zzz",)))
        == 1,
    )
    # An OBJECT token is not a path, so a prefix that looks like one must not excuse it. Without this, "private/renet" in the skip set could be read as licence to drop any citation whose text begins with those bytes.
    ck(
        "CONTROL: a dead OBJECT citation is never excused by the submodule skip",
        len(
            problems_for(
                root, [("agent/PLAN-zzz.md", 1, "at %s" % ("deadbeef" * 5))], ("private/zzz",)
            )
        )
        == 1,
    )
    # THE DETECTOR ITSELF, on a fixture, because its first version read `.gitmodules` from the real repo while testing paths under the root it was handed -- agreeing in production and answering nonsense anywhere else, which is exactly the shape that cannot be controlled and so never is.
    with tempfile.TemporaryDirectory() as td:
        fx = pathlib.Path(td)
        (fx / ".gitmodules").write_text(
            '[submodule "private/aaa"]\n\tpath = private/aaa\n\turl = x\n'
            '[submodule "private/bbb"]\n\tpath = private/bbb\n\turl = y\n',
            encoding="utf-8",
        )
        (fx / "private" / "aaa").mkdir(parents=True)
        (fx / "private" / "bbb").mkdir(parents=True)
        (fx / "private" / "bbb" / "f.txt").write_text("x", encoding="utf-8")
        ck(
            "an EMPTY submodule directory reads as absent, a populated one does not",
            absent_submodules(fx) == ["private/aaa"],
            absent_submodules(fx),
        )
    # ON THE REAL TREE, and phrased so it holds in BOTH environments -- which the
    # first version did not. It asserted `absent_submodules(root) == []`, i.e. that
    # every submodule is populated. That is true on a developer checkout and FALSE in `quality-branch`, the very lane this filter exists for, so the commit that added the filter shipped a control that could only pass where the filter was unnecessary. CI failed it immediately and was right to.
    #
    # What is actually invariant is AGREEMENT with the filesystem: whatever the
    # function returns must be a declared submodule, and must really be missing or
    # empty. That catches a filter inventing a skip -- the direction that matters -- without asserting anything about which lane is running it.
    declared = []
    manifest = pathlib.Path(root) / ".gitmodules"
    if manifest.is_file():
        for line in _git("config", "-f", str(manifest), "--get-regexp", r"\.path$").split("\n"):
            bits = line.split()
            if len(bits) == 2:
                declared.append(bits[1])
    reported = absent_submodules(root)
    ck(
        "every path it reports absent is a DECLARED submodule",
        all(p in declared for p in reported),
        (reported, declared),
    )
    # DELIBERATELY ONLY ONE ASSERTION HERE. The two obvious companions -- "everything reported really is empty on disk" and "every empty one is reported" -- restate `absent_submodules`'s own definition back at it, so they cannot fail unless the
    # function contradicts itself line to line. Controls that cannot fail are what
    # this whole gate estate keeps getting caught by, and adding two of them to look thorough would be the same mistake in a new place. The independent check is the SUBSET one above (a path it invents would not be declared) and the tempdir fixture, whose expectation is built without calling the function at all.

    # The EXTRACTOR, separately from the resolvers: a line carrying all four shapes must yield all four. A resolver that works over an extractor that sees nothing is a gate that cannot fail.
    probe = f"see {scoped[0]}:12 and {scoped[0]} plus check:ci-plan-record at {head[:12]}"
    kinds = {k for k, _t in citations(probe)}
    ck(
        "the extractor finds all four citation kinds on one line",
        kinds == {"fileline", "plan", "gate", "object"},
        f"got {sorted(kinds)}",
    )
    # And the two documented exemptions, both directions.
    ck(
        "an all-digit run id is NOT treated as an object",
        not any(t == "100500447167" for _k, t in citations("run 100500447167 failed")),
    )
    ck(
        "CONTROL: a hex-and-letter token IS treated as an object",
        any(k == "object" for k, _t in citations("at c6d3af163 the branch point")),
    )
    ck(
        "the tail of a UUID is NOT treated as an object",
        not any(
            k == "object"
            for k, _t in citations("Stripe secret 8f14e45f-ceea-467e-b7a1-3fda6dabc123 leaked")
        ),
    )
    ck(
        "CONTROL: the same 12 hex characters WITHOUT the UUID dashes ARE",
        any(k == "object" for k, _t in citations("Stripe secret 3fda6dabc123 leaked")),
    )
    # THE FINGERPRINT EXEMPTION, both directions: the marker is what licenses it, so the same token without the marker must still be judged. See FINGERPRINT_RE.
    ck(
        "a hex run behind a `fingerprint:` marker is NOT treated as an object",
        not any(
            k == "object" for k, _t in citations("the site hashes to fingerprint:c1e552fa19e9")
        ),
    )
    ck(
        "CONTROL: the same token WITHOUT the marker IS",
        any(k == "object" for k, _t in citations("the site hashes to c1e552fa19e9")),
    )
    # THE TICK-ID EXEMPTION, both directions on each of its two matchers, because each one is licensed by a different marker and a control over only one of them would leave the other able to exempt anything. See TICK_ID_RE and MARKER_FILE_RE.
    ck(
        "a hex run behind a `tick:` marker is NOT treated as an object",
        not any(k == "object" for k, _t in citations("the fix-set tick:a64d5c5e0a28 settled")),
    )
    ck(
        "CONTROL: the same tick id WITHOUT the marker IS",
        any(k == "object" for k, _t in citations("the fix-set a64d5c5e0a28 settled")),
    )
    ck(
        "a tick id inside a `/.judge/` marker filename is NOT treated as an object",
        not any(
            k == "object"
            for k, _t in citations("/tmp/claude-worklist/.judge/classsweep-0a598f50c372.json")
        ),
    )
    ck(
        "CONTROL: the same filename OUTSIDE `/.judge/` still carries an object",
        any(
            k == "object"
            for k, _t in citations("/tmp/claude-worklist/marks/classsweep-0a598f50c372.json")
        ),
    )
    # THE AGENT-ID EXEMPTION, both directions and on the length boundary, because the whole narrowing is the length. See AGENT_ID_RE.
    ck(
        "a 17-character background agent id is NOT treated as an object",
        not any(k == "object" for k, _t in citations("Root cause (Plan agent a2fd17b15c79c8ceb)")),
    )
    ck(
        "CONTROL: one character SHORTER, and it is an object again",
        any(k == "object" for k, _t in citations("Root cause (Plan agent a2fd17b15c79c8ce)")),
    )
    ck(
        "CONTROL: one character LONGER, and it is an object again",
        any(k == "object" for k, _t in citations("Root cause (Plan agent a2fd17b15c79c8ceb0)")),
    )
    ck(
        "CONTROL: 17 hex characters NOT starting with `a` are an object",
        any(k == "object" for k, _t in citations("Root cause (Plan agent b2fd17b15c79c8ceb)")),
    )
    # THE FLOOR, both directions. An 8-hex session prefix must not be judged and a 9-hex sha must be; a floor that silently drifted to 7 would red on every session id in every STATE.md, which is how a gate gets switched off.
    ck(
        "an 8-hex session prefix is NOT treated as an object",
        not any(k == "object" for k, _t in citations("session d1589e0b wrote this")),
    )
    ck(
        "CONTROL: one more character IS",
        any(k == "object" for k, _t in citations("session d1589e0bc wrote this")),
    )
    # THE SCOPE PREDICATE, both directions. A narrowed scope is the one change that can quietly turn a working gate into one that reads nothing, so the boundary is pinned rather than described.
    ck("a plan is in scope", in_scope(scoped[0]))
    ck("...and so is the index", in_scope("agent/INDEX.md"))
    ck("CONTROL: a per-session STATE.md is NOT", not in_scope("agent/d1589e0b/STATE.md"))
    ck("CONTROL: a generated PR body is NOT", not in_scope("agent/pr/some-branch.md"))
    ck("CONTROL: a file outside agent/ is NOT", not in_scope("docs/agent-reference/TRAPS.md"))

    # The submodule advice, both directions. Skipped rather than failed when the submodules are not checked out, because a shallow CI checkout is a real environment and a control that cannot run must say so instead of reding.
    subs = submodule_paths(root)
    if subs:
        probe = ""
        for sub in subs:
            for cand in sorted(pathlib.Path(root, sub).rglob("*.go"))[:1]:
                probe = str(cand.relative_to(pathlib.Path(root, sub)))
        if probe:
            got, why = unresolved(root, "fileline", probe + ":1")
            ck("a submodule-relative path is reported AS a submodule path", got and "but " in why)
            ck("...naming where it really is", any(s2 in why for s2 in subs), why)
        got, why = unresolved(root, "fileline", "package.json:1")
        ck("CONTROL: a root-relative path is not given submodule advice", not got)
    else:
        print("  SKIP  submodule advice: no submodule is checked out here")
    return bad


def main(argv):
    root = ROOT
    print("plan citations: controls first, then the verdict")
    if selftest(root):
        print(
            "✗ instrument control failed; every verdict below would be meaningless",
            file=sys.stderr,
        )
        return 2
    if "--selftest" in argv:
        print("✓ selftest only; the diff was not judged")
        return 0

    n_files, n_cites = corpus_citations(root)
    if n_files and not n_cites:
        print(
            f"VACUOUS INPUT: {n_files} tracked file(s) under {SCOPE_DIR}/ and the extractor "
            f"found ZERO citations in any of them. That is a blind parser, not a clean "
            f"corpus -- refusing a verdict rather than reporting a green diff nothing read.",
            file=sys.stderr,
        )
        return 1

    base = base_ref()
    if base is None:
        # NOT a failure and not a pass-by-default. With no base there is no set of ADDED lines, which is the only thing this gate judges. Saying so is the honest answer; inventing a base would judge the whole corpus and red on the 37 dead pointers this gate deliberately does not own.
        print(
            f"✓ plan citations: no merge base against origin/main or main, so there are no "
            f"ADDED lines to judge. The corpus is {n_files} file(s) carrying {n_cites} "
            f"citation(s) and was not judged -- this gate rules on what a change adds."
        )
        return 0

    raw_rows = added_lines(base)
    rows = drop_moved_lines(root, base, raw_rows)
    if len(rows) != len(raw_rows):
        print(
            "  %d added line(s) were carried in by a stubbed plan move and are not judged "
            "as additions; %d remain" % (len(raw_rows) - len(rows), len(rows))
        )
    # PRINTED EVERY RUN, whether or not anything was skipped, so an exclusion can never become invisible debt: a reader of a green run sees exactly which citations this process was not in a position to judge.
    absent = absent_submodules(root)
    if absent:
        print(
            "  not judged, submodule not checked out in this job (%s): citations under %s"
            % (os.environ.get("GITHUB_JOB", "local"), ", ".join(absent))
        )
    else:
        print("  every declared submodule is populated, so no citation was skipped")
    problems = problems_for(root, rows, absent)
    if problems:
        print(
            f"✗ plan citations: {len(problems)} unresolvable pointer(s) on lines this "
            f"change adds to a plan or to {R.INDEX_REL}:",
            file=sys.stderr,
        )
        for p in problems[:MAX_SHOWN]:
            print(f"    {p}", file=sys.stderr)
        if len(problems) > MAX_SHOWN:
            print(f"    ...and {len(problems) - MAX_SHOWN} more", file=sys.stderr)
        print(
            "\n  A pointer that does not resolve costs the next reader a `git show` and a\n"
            "  wrong conclusion, which is worse than no pointer at all. Measured 2026-09-06:\n"
            "  37 of 71 commit-shaped tokens already cited in agent/ are dead. This gate\n"
            "  judges only what YOUR change adds, so every finding above is fixable now:\n"
            "    * a commit sha on a branch is rewritten by `gh pr merge --rebase` -- cite\n"
            "      the blob (`git hash-object <file>`), which survives the rebase;\n"
            "    * a file:line that moved needs re-reading, which is the point of the rule;\n"
            "    * an example rather than a citation belongs inside a fenced code block,\n"
            "      which this gate skips.",
            file=sys.stderr,
        )
        return 1

    print(
        f"✓ plan citations: {len(rows)} added line(s) in plans or {R.INDEX_REL} since "
        f"{base[:9]}, every citation on them resolves. Corpus floor: {n_files} in-scope "
        f"file(s) carrying {n_cites} citation(s), so the extractor is not blind.\n"
        f"  NOT judged, and deliberately: agent/<session>/STATE.md (read-only to every "
        f"session but its owner) and the generated agent/pr and agent/worklist trees. "
        f"See the SCOPE block for the ownership rule and the two real findings it costs."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
