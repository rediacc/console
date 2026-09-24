"""wl_planrec: turn a finished `agent/PLAN-*.md` into an ATTESTED RECORD that keeps its own path, so the plan stops aging out and nothing that cites it breaks.

------------------------------------------------------------------------------
WHY THIS EXISTS, and it has a date on it.

`.ci/scripts/quality/check-plan-housekeeping.sh` DEMANDS deletion of any plan whose file has not moved for `delete_days` (33, from `.ci/config/plan-lifecycle.json`). Measured 2026-09-06 on this tree: 81 tracked plans, **33 of them last touched on 2026-08-21**, which goes red on **2026-09-23**; 13 more follow on 2026-10-06. The operator's standing rule is that NOTHING is deleted.
Those two facts are a deadlock with a date, and this module is the third door: a plan that is finished is COMPACTED IN PLACE -- the file keeps its path and shrinks to a record whose full text lives in a git blob.

Archiving is not that door and never was. The archive is `agent/archive/plans/`, and `.ci/config/plan-lifecycle.json`'s own `$comment` says the clock is CONTENT age precisely so a move cannot reset it. (The gate as written measures
`git log -1 --format=%cI` -- last commit touching the path -- and its
non-recursive `git ls-files agent/PLAN-*.md` glob drops the archive from the corpus entirely, so today archiving hides a plan rather than resetting it. Either way it is not a record, and a hidden plan is exactly the "committed lie" `agent/README.md:11` warns about.)

------------------------------------------------------------------------------
WHY BLOB IDS AND NOT COMMIT SHAS. This is the single load-bearing decision.

This repo merges with `gh pr merge --rebase`. A rebase REWRITES every commit on the branch, so a sha recorded while the work was in flight names nothing once it lands. Measured 2026-09-06: of 71 commit-shaped tokens already cited across the plans in `agent/`, **37 no longer resolve** -- more than half of the durable pointers this tree already relies on are dead, and nothing
reported it.

A blob id is content-addressed: `git hash-object` of the same bytes is the same id in every clone, before the commit exists, after the rebase, and after the history rewrite of #532 that changed every sha in this repo. So:

    THE POINTER IS THE BLOB. The commit is a convenience.

`Full-Text: <sha9> <path>` is therefore OPTIONAL -- legal to omit while the text is not on `origin/main` yet, and upgraded later by the gate's `--update` once it is. `Full-Text-Blob:` is mandatory and is what recovery actually uses:

    git show <blob>                      the text itself, always
    git log --find-object=<blob> --all   which commit(s) carried it

Both commands are written INTO the record, on a `Read-History:` line, because a recovery recipe that lives only in this docstring is a recipe the reader of the record does not have.

------------------------------------------------------------------------------
THE GRAMMAR, and what each part is defending.

    # <title>
    Status: compacted            or `parked`
    Owner: <session or unowned>  preserved verbatim, optional
    Full-Text: <sha9> <path>     optional when Full-Text-Blob is present
    Full-Text-Blob: <blob>       MANDATORY
    Record-Sig: <8hex>

    ## Why / ## Outcome / ## Lessons     prose, three fixed sections
    ## Boxes                             the box lines, BYTE-IDENTICAL
    ## Record                            trailer, TRAPS grammar (`Key: value`)
    ## History                           append-only bullets

Five properties, each with a reason that cost something:

1. THE HEADER FITS IN THE FIRST 10 LINES. `wl_checks.PLAN_HEADER_LINES` is 10 and
   every status/owner regex reads exactly that window. A header on line 11 is a
   header no consumer in this repo can see.

2. BOX LINES ARE BYTE-IDENTICAL. `check_plan_boxes.py`'s A1 asserts that no box
   open at the merge-base is gone at HEAD, and its A0 compares task SIGNATURES --
   the first 8 hex of sha256 over `wl_planfid._norm(task)[:120]`. Compaction that
   re-wrote a box would look exactly like a box being disappeared, which is the
   one thing that gate exists to catch. So the box survives verbatim and the
   record's claim about it goes on a SEPARATE line beneath it.

3. THAT SEPARATE LINE IS INVISIBLE TO THE PARSER, BY CONSTRUCTION AND NOT BY A
   NEW RULE. `wl_planfid.BULLET_RE` requires a bullet marker (`-`, `*`, `+` or
   `N.`) at indent 0-3, and `CHECKBOX_RE` requires `[-*+] [ ]`. A four-space
   `(record) ...` line has neither, so `plan_tasks` skips it without anything
   being added to `plan_tasks`. A parser change would have been the wrong fix:
   the parser is imported by two gates and the Stop hook, and widening it for
   this would put a new exclusion rule in the path of every plan in the tree.
   `test-planrec.py` pins the property so a future BULLET_RE widening cannot
   silently start eating record lines.

4. `## History` IS APPEND-ONLY and `Record-Sig` DOES NOT COVER IT. The signature
   canonicalises status, pointer and the box table only. Sharpening a `## Lessons`
   bullet is therefore free; changing what the record CLAIMS is not. A signature
   over the whole file would make the record un-editable, and an un-editable
   record is one people work around.

5. SIZE IS BOUNDED IN BOTH DIRECTIONS. A record is at most
   `RECORD_MAX_BYTES` + `RECORD_PER_BOX_BYTES` per box, and the blob it points at
   must be at least `BLOB_RATIO`x the record. The floor is the anti-vacuity half:
   without it, "compaction" that pointed at a blob the same size as the record
   would pass every other rule while having compacted nothing.

------------------------------------------------------------------------------
`done=` IS PROVED AGAINST THE LEDGER, NOT ASSERTED.

`.ci/config/plan-boxes.json` is a COMMITTED second reading of every plan's boxes (`check_plan_boxes.py --update`), carrying `done_sigs` per plan. So "when was this box ticked" has a mechanical answer: walk that file's git history oldest-first and find the first commit whose ledger blob lists the box's signature under
`done_sigs`. That commit sha is what `done=` records, and
`check_plan_record.py` re-derives it from `git show <sha>:<ledger>` rather than believing the record.

Three values, and the third one is an admission rather than a claim:

    done=<sha9>      the ledger at <sha9> attests the tick
    done=open        the box is `- [ ]` (only reachable under --park)
    done=abandoned   the box is `- [x]` and NO ledger commit attests it

`abandoned` cannot be used as a dodge: the gate reds when a box marked `abandoned` has its signature in the CURRENT ledger's `done_sigs`, because that is a proof that was available and was not used.

------------------------------------------------------------------------------
WHAT THIS MODULE DOES NOT DO. It never commits, never runs `git checkout`, `restore`, `stash` or `clean`, and never writes a file that is not the record itself or `agent/INDEX.md`. Writes go through a tempfile plus `os.replace`, the same atomicity the worklist store uses, so a crash mid-write cannot leave a plan half-compacted -- which would be a plan whose full text is in neither
the file nor a reachable blob.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import pathlib
import re
import subprocess
import tempfile
from typing import Any

import wl_core as C
import wl_planfid as PFID
import wl_planfile as PF
import wl_proc
import wl_store as S

# --------------------------------------------------------------------------- Bounds and constants.

#: The two record statuses. `compacted` is a finished plan (every box attested);
#: `parked` is a plan with live boxes whose TEXT is compacted but whose work is
#: not done -- so it stays on the housekeeping clock on purpose.
STATUS_COMPACTED = "compacted"
STATUS_PARKED = "parked"
RECORD_STATES = (STATUS_COMPACTED, STATUS_PARKED)

#: Size budget. 6 KB of prose plus 160 bytes per box, which is one box line plus
#: its `(record)` line plus slack. A record that needs more than this is not a
#: record, it is the plan again.
RECORD_MAX_BYTES = int(os.environ.get("WORKLIST_RECORD_MAX_BYTES", str(6 * 1024)))
RECORD_PER_BOX_BYTES = int(os.environ.get("WORKLIST_RECORD_PER_BOX_BYTES", "160"))
#: The blob must be at least this many times the record. See design note 5: this
#: is the ANTI-VACUITY half of the size rule, not a style preference.
BLOB_RATIO = float(os.environ.get("WORKLIST_RECORD_BLOB_RATIO", "2"))

#: The committed second reading of every plan's boxes. `done=` is proved against
#: this file's HISTORY, never against the plan file's own.
LEDGER_REL = ".ci/config/plan-boxes.json"
INDEX_REL = "agent/INDEX.md"
TRAPS_REL = "docs/agent-reference/TRAPS.md"

#: How many lines of a plan the header regexes can see (wl_checks.PLAN_HEADER_LINES).
#: Restated rather than imported so this module does not depend on wl_checks at
#: import time; `test-planrec.py` asserts the two are equal, which is the only
#: thing that could drift.
HEADER_LINES = 10

#: The four prose sections, in render order. `## Boxes` is generated, never authored.
PROSE_SECTIONS = ("Why", "Outcome", "Lessons")

#: An unfilled slot. Deliberately NOT `TBD` or `TODO`, both of which appear in
#: legitimate prose in this tree; `<FILL:` appears nowhere else and so cannot
#: produce a false red.
PLACEHOLDER_RE = re.compile(r"<FILL:[^>]*>")
UNRESOLVED = "[unresolved]"


def placeholder(what: str) -> str:
    return "<FILL: %s>" % what


# --------------------------------------------------------------------------- Line grammars. Every one of these is anchored: a `Status:` in the middle of a sentence is prose, and reading it as a header is how a record starts lying.

HEAD_FIELD_RE = re.compile(r"^([A-Za-z][A-Za-z-]*):[ \t]*(.*)$")

#: The header keys this grammar actually defines. `HEAD_FIELD_RE` matches any
#: `Word:` by shape, which is right when PARSING a header block (an unknown key
#: there is still a header line) and wrong when deciding whether a `# heading` is
#: a header field wearing a hash: `# PLAN: ...` is a title, not a field, and it
#: is how 62 of the 83 plans in this tree name themselves.
HEADER_FIELD_KEYS = frozenset(
    {
        "Status",
        "Owner",
        "Full-Text",
        "Full-Text-Blob",
        "Record-Sig",
        "Compacted-At",
        "Compacted-By",
        "Supersedes",
        "Extends",
        "Related",
    }
)
FULLTEXT_RE = re.compile(r"^Full-Text:[ \t]*([0-9a-f]{7,40})[ \t]+(\S+)[ \t]*$", re.MULTILINE)
FULLTEXT_BLOB_RE = re.compile(r"^Full-Text-Blob:[ \t]*([0-9a-f]{40})[ \t]*$", re.MULTILINE)
RECORD_SIG_RE = re.compile(r"^Record-Sig:[ \t]*([0-9a-f]{8})[ \t]*$", re.MULTILINE)

#: The `(record)` annotation. FOUR spaces exactly, so it can never be a bullet at
#: BULLET_RE's indent 0-3 even if a future edit gives it a leading dash.
#: `done=` takes exactly three shapes and NO placeholder. A literal `done=<sha9>`
#: used to parse, which nothing ever wrote and which `index_rows` would have
#: counted as ATTESTED -- a dead alternation that could only ever inflate the
#: attested column of agent/INDEX.md. Removed rather than special-cased: a
#: hand-written record carrying it now reads as an unannotated box, which is a
#: finding with a clearer message than "that commit does not exist".
RECORD_LINE_RE = re.compile(
    r"^ {4}\(record\) sig=([0-9a-f]{8}) done=([0-9a-f]{9}|open|abandoned)[ \t]*$"
)
#: A box line, with its mark captured. Same shape as wl_planfid.CHECKBOX_RE (all
#: four marks, `[?]`/`[>]` included since 2026-09-22's fix for the identical
#: fallthrough bug there -- a `[?]`/`[>]` box used to vanish from `boxes`
#: entirely here too, and its own valid `(record)` line got misreported as
#: orphaned), kept as one regex here because the record renderer needs the mark
#: and the body from the same match.
BOX_LINE_RE = re.compile(r"^\s*[-*+]\s+\[([ xX?>])\]\s+(\S.*)$")

#: A gate id as `package.json` spells it.
GATE_RE = re.compile(r"\bcheck:[a-z0-9][a-z0-9:-]{2,60}\b")
#: A plan path or slug, in any of the four folders a plan may sit in. The
#: alternation is OPTIONAL and the legacy spelling stays first, because a stub
#: keeps `agent/PLAN-<slug>.md` resolving forever and every one of the 523
#: citations already in this tree uses it. `resolve` below is what turns either
#: spelling into a file. `.ci/rediacc_ci/quality/plan_lifecycle.PLAN_REF_RE` is
#: the same grammar one directory over, and the two are compared by
#: `.ci/rediacc_ci/tests/test_quality_plan_lifecycle.py`.
PLAN_REF_RE = re.compile(r"\bagent/(?:plans/(?:_done/|_removed/)?)?PLAN-[A-Za-z0-9._-]+\.md\b")
#: Every folder a plan may sit in, deepest first. `wl_store.AGENT_PLAN_SUBDIRS` is
#: the same list relative to `agent/`, and `.ci/rediacc_ci/quality/plan_lifecycle`
#: holds the third copy that a gate running without `.claude/` needs; the three
#: are compared by `.ci/rediacc_ci/tests/test_quality_plan_lifecycle.py`.
PLAN_FOLDERS = tuple("agent/%s" % sub if sub else "agent" for sub in S.AGENT_PLAN_SUBDIRS)


def plan_folder(rel):
    """The plan directory `rel` sits in, or "" when it is not in one at all.

    Deepest first, because `agent/plans/_done` is a prefix-extension of `agent/plans` and testing the short one first would file every terminal plan as active.
    """
    for candidate in PLAN_FOLDERS:
        prefix = candidate + "/"
        if rel.startswith(prefix) and "/" not in rel[len(prefix) :]:
            return candidate
    return ""


#: A trap id, as `Trap-Id:` spells it in TRAPS.md.
TRAP_REF_RE = re.compile(r"\btrap:([a-z0-9][a-z0-9-]{2,80})\b")
#: Hex tokens long enough to be a git object. 7 is git's own abbreviation floor.
HEXTOK_RE = re.compile(r"(?<![0-9a-zA-Z])([0-9a-f]{7,40})(?![0-9a-zA-Z])")

PR_TASK_RE = re.compile(r"^[ \t]*`?PR-TASK:[ \t]*([0-9a-f]{6,32})`?[ \t]*$", re.MULTILINE)

#: The evidence line `--plan-tick` writes beneath a box it flips. FOUR spaces and
#: no bullet marker, for exactly the reason the `(record)` line has them: at
#: indent 4 `wl_planfid.BULLET_RE` cannot see it, so the evidence never becomes a
#: phantom task and the box's own signature never moves. The two annotations are
#: deliberately different words -- `(record)` is an ATTESTATION the gate proves
#: against the ledger, `(ticked)` is a NOTE nothing proves -- and conflating them
#: would let a note masquerade as a proof.
TICK_LINE_RE = re.compile(r"^ {4}\(ticked\) ")


class RecordError(Exception):
    """A refusal with a reason a session can act on. Never a traceback."""


# --------------------------------------------------------------------------- git, with a return code. `wl_core._git` collapses "failed" and "succeeded with no output" into the same empty string, which is exactly wrong for `merge-base --is-ancestor`, whose success output IS empty.


def _git_out(root, *args) -> str:
    return C._git(root, *args)


def _git_raw(root, *args) -> str:
    """stdout EXACTLY as git produced it, or "" on failure.

    NOT `wl_core._git`, and the difference is the whole promise of this module. `_git` ends in `r.stdout.strip()`, which exists for the sha-and-branch answers it was written for and is CORRUPTING here: `cat-file blob` returns a document, and stripping it silently drops a leading blank line, a trailing blank line, or trailing whitespace on the last line. A revived file that differs
    from the blob by one byte no longer hashes to `Full-Text-Blob`, so re-compacting it mints a DIFFERENT blob -- which contradicts the one claim this design rests on. Measured 2026-09-06: `agent/PLAN-migrate-command.md` ends with a blank line, so it is already in the affected set.
    """
    try:
        r = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _git_ok(root, *args) -> bool:
    try:
        r = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def sha9(s: str) -> str:
    return (s or "").strip()[:9]


# --------------------------------------------------------------------------- resolve(): one function, eight kinds, no second opinion anywhere.
#
# Every kind here already had a resolver somewhere in this repo, and the point of collecting them is that a record's pointers must all be checkable by ONE call the gate and the CLI share. Reusing rather than reinventing is not tidiness: `citation_state` in particular carries five separately-paid-for extension rounds in its CITE_RE (dotfiles, .astro, .mdx, .cast, leading dots), and
# a fresh path regex here would re-open every one of them.

RESOLVE_KINDS = ("blob", "tree", "commit", "ancestor", "fileline", "gate", "plan", "trap")

#: A flat-layout legacy plan path (`agent/PLAN-<slug>.md`), whose stub the 2026-09-22 cleanup deleted -- see `resolve`'s "plan" kind.
_FLAT_LEGACY_RE = re.compile(r"^agent/PLAN-(.+)\.md$")


def _package_scripts(root) -> dict:
    try:
        data = json.loads((pathlib.Path(root) / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    s = data.get("scripts")
    return s if isinstance(s, dict) else {}


def _trap_ids(root) -> set:
    try:
        text = (pathlib.Path(root) / TRAPS_REL).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    return set(re.findall(r"^Trap-Id:[ \t]*(\S+)[ \t]*$", text, re.MULTILINE))


def resolve(root, kind, token):
    """(ok, detail) -- does this pointer name something that REALLY exists?

    The kinds, and where each one's answer comes from:

      blob      `git cat-file -t` says `blob`. The durable pointer.
      commit    `git rev-parse <t>^{commit}`.
      tree      `git cat-file -t` says `tree`. Rare: a citation into a
                `git filter-branch`/rewrite control that names a tree id
                directly (`git read-tree`, `HEAD^{tree}`) rather than a file
                or a commit. Neither `blob` nor `commit` resolves a tree, so
                without this kind a correctly-cited tree object reads as dead.
      ancestor  a commit AND `git merge-base --is-ancestor <t> origin/main`, so a
                pointer into a branch that was never merged cannot masquerade as
                a landed one. `origin/main` first, plain `main` as the fallback
                for a clone with no remote (the test fixture is one).
      fileline  wl_checks.citation_state, imported lazily -- see the note below.
      gate      a key in package.json's `scripts`. This is the same oracle
                check-trap-registry.sh uses for its `gate:` pointers, so a gate
                id that resolves here resolves there.
      plan      an `agent/PLAN-*.md` on disk.
      trap      a `Trap-Id:` in docs/agent-reference/TRAPS.md.

    wl_checks IS IMPORTED INSIDE THE FUNCTION, not at module top. wl_checks is 6,100 lines and pulls in most of this directory; this module is imported by a CI gate that only needs the parser, and paying that import to answer a question about a blob would make the gate slower than the thing it checks.
    """
    token = (token or "").strip()
    if not token:
        return False, "empty token"
    if kind == "blob":
        got = _git_out(root, "cat-file", "-t", token)
        return (got == "blob"), (got or "no such object")
    if kind == "tree":
        got = _git_out(root, "cat-file", "-t", token)
        return (got == "tree"), (got or "no such object")
    if kind == "commit":
        got = _git_out(root, "rev-parse", "--verify", "--quiet", token + "^{commit}")
        return bool(got), (got[:40] or "no such commit")
    if kind == "ancestor":
        got = _git_out(root, "rev-parse", "--verify", "--quiet", token + "^{commit}")
        if not got:
            return False, "no such commit"
        for ref in ("origin/main", "main"):
            if not _git_out(root, "rev-parse", "--verify", "--quiet", ref):
                continue
            if _git_ok(root, "merge-base", "--is-ancestor", token, ref):
                return True, "ancestor of %s" % ref
            return False, "not an ancestor of %s" % ref
        return False, "neither origin/main nor main exists here"
    if kind == "fileline":
        import wl_checks as CK  # noqa: PLC0415 -- see the docstring

        return CK.citation_state(root, token)
    if kind == "gate":
        scripts = _package_scripts(root)
        if not scripts:
            return False, "package.json has no scripts block to check against"
        return (token in scripts), ("package.json scripts" if token in scripts else "no such gate")
    if kind == "plan":
        # A BARE SLUG IS TRIED IN EVERY FOLDER, deepest first, because a closed plan lives under `agent/plans/_done/` and the slug in a citation does not say so. A full path is taken as written: the stub left at a moved plan's old path used to be a real file, so the legacy spelling resolved there and the citation kept its meaning rather than silently following the move.
        if token.startswith("agent/"):
            candidates = [token]
        else:
            candidates = [
                "%s/PLAN-%s.md" % (d, token) if d else "agent/PLAN-%s.md" % token
                for d in ("agent/plans/_done", "agent/plans/_removed", "agent/plans", "")
            ]
        for rel in candidates:
            if (pathlib.Path(root) / rel).is_file():
                return True, rel
        # THE STUB IS GONE NOW: the 2026-09-22 cleanup deleted every flat-layout `agent/PLAN-<slug>.md` stub the `fce51e202`/`a81967e94` migration left behind, so a full legacy path no longer resolves by itself.
        # The slug survives every move, so re-derive it and try the same folders the bare-slug branch above already searches, same fallback `wl_store.plan_stub_target` uses for `citation_state`.
        m = _FLAT_LEGACY_RE.match(token)
        if m:
            slug = m.group(1)
            for d in ("agent/plans/_done", "agent/plans/_removed", "agent/plans"):
                rel = "%s/PLAN-%s.md" % (d, slug)
                if (pathlib.Path(root) / rel).is_file():
                    return True, rel
        return False, "%s does not exist" % candidates[-1]
    if kind == "trap":
        ids = _trap_ids(root)
        if not ids:
            return False, "%s carries no Trap-Id lines to check against" % TRAPS_REL
        return (token in ids), ("Trap-Id" if token in ids else "no such Trap-Id")
    raise ValueError("unknown resolve kind %r (want one of %s)" % (kind, ", ".join(RESOLVE_KINDS)))


def launder(root, text):
    """(text, [replaced]) -- every unresolvable pointer becomes `[unresolved]`.

    WHY THIS IS NOT OPTIONAL ON MODEL PROSE. A record is the durable artifact, read months later by someone who cannot check it. A model asked to summarise a plan will happily produce a sha-shaped token, and a decorative sha in a record is strictly worse than no sha: it costs the reader a `git show` and a wrong conclusion. The same reasoning is already in `completion_evidence`,
    which verifies hex tokens against real objects rather than accepting the shape.

    Deliberately CONSERVATIVE about what it inspects. Only four shapes -- hex object ids, `file:line` citations, `check:` gate ids and `agent/PLAN-*.md` paths -- because those are the four a reader would try to follow. Prose is left alone; this is not a fact-checker.
    """
    replaced = []
    out = text or ""

    def sub(rx, kind):
        nonlocal out
        pieces, last = [], 0
        for m in rx.finditer(out):
            tok = m.group(0)
            ok, _why = resolve(root, kind, tok)
            if ok:
                continue
            pieces.append(out[last : m.start()])
            pieces.append(UNRESOLVED)
            replaced.append("%s:%s" % (kind, tok))
            last = m.end()
        if pieces:
            pieces.append(out[last:])
            out = "".join(pieces)

    # file:line FIRST. A citation contains no hex-object-shaped token in its path
    # for any real path in this tree, but doing hex first would let a path
    # fragment be rewritten out from under the citation resolver.
    import wl_checks as CK  # noqa: PLC0415 -- see resolve()

    sub(CK.CITE_RE, "fileline")
    sub(PLAN_REF_RE, "plan")
    sub(GATE_RE, "gate")
    # Hex tokens resolve as EITHER a blob or a commit -- both are legitimate in a record, and demanding one would launder the other. Done by hand rather than through `sub` because it is the one kind with two acceptable answers.
    pieces, last = [], 0
    for m in HEXTOK_RE.finditer(out):
        tok = m.group(1)
        # AN ALL-DIGIT TOKEN IS NEVER LAUNDERED, and it is the one exception worth
        # having. `[0-9a-f]{7,40}` also matches a CI run id (`100500447167`), a
        # date and an issue number, and those are exactly the evidence shapes `wl_checks.completion_evidence` treats as first-class. Laundering a run id out of a record would destroy the most citable fact in it to defend against an all-digit git object, which does not occur. Cheap asymmetry, taken in the direction that keeps evidence.
        if tok.isdigit():
            continue
        if resolve(root, "blob", tok)[0] or resolve(root, "commit", tok)[0]:
            continue
        pieces.append(out[last : m.start()])
        pieces.append(UNRESOLVED)
        replaced.append("object:%s" % tok)
        last = m.end()
    if pieces:
        pieces.append(out[last:])
        out = "".join(pieces)
    return out, replaced


# --------------------------------------------------------------------------- Parsing a record.


def _sections(text):
    """{title: body} for every `## ` section, in file order, bodies unstripped.

    Fence-aware, because a `## ` inside a fenced block is a code sample and not a section -- the same distinction `wl_planfid.plan_tasks` makes, and for the same reason: a record that quotes a markdown example must not sprout a phantom section from it.
    """
    out, cur, buf, fenced = {}, None, [], False
    for raw in (text or "").splitlines():
        if PFID.FENCE_RE.match(raw):
            fenced = not fenced
            if cur is not None:
                buf.append(raw)
            continue
        if not fenced and raw.startswith("## "):
            if cur is not None:
                out[cur] = "\n".join(buf).strip("\n")
            cur, buf = raw[3:].strip(), []
            continue
        if cur is not None:
            buf.append(raw)
    if cur is not None:
        out[cur] = "\n".join(buf).strip("\n")
    return out


def _trailer(body):
    """`Key: value` lines from a `## Record` body, in the TRAPS trailer grammar.

    Stops at the first line that is not a trailer, so prose beneath the trailer is not silently read as fields.
    """
    out = {}
    for raw in (body or "").splitlines():
        if not raw.strip():
            continue
        m = HEAD_FIELD_RE.match(raw)
        if not m:
            break
        out[m.group(1)] = m.group(2).strip()
    return out


def _owner_line(head):
    """The raw `Owner:` value, preserved VERBATIM across compaction.

    Not `wl_checks.plan_owner`, which resolves the value down to a session id -- correct for scoping the Stop hook's advisory, and lossy here. A record that rewrote `Owner: unowned (drafted by 9d92d9b6)` as `9d92d9b6` would hand the plan to a session that explicitly disclaimed it, which is the exact defect plan_owner's own docstring records paying for.
    """
    m = re.search(r"^Owner:[ \t]*(.*)$", head or "", re.MULTILINE)
    return m.group(1).strip() if m else ""


def parse(text):
    """A record as a dict, or None when this is not a record at all.

    Never raises: this is called from a CI gate over every plan in the tree, and a malformed file must produce a FINDING rather than a traceback. The dict always carries `problems`, which is where a malformed record's diagnosis lives.
    """
    text = text or ""
    lines = text.splitlines()
    head = "\n".join(lines[:HEADER_LINES])
    m = re.search(r"^\*{0,2}Status\*{0,2}:[ \t]*([A-Za-z-]+)", head, re.MULTILINE)
    status = m.group(1).lower() if m else ""
    if status not in RECORD_STATES:
        return None

    problems = []
    ft = FULLTEXT_RE.search(head)
    blob = FULLTEXT_BLOB_RE.search(head)
    sig = RECORD_SIG_RE.search(head)
    if not blob:
        problems.append(
            "no `Full-Text-Blob: <40 hex>` line in the first %d lines. The blob is the "
            "ONLY mandatory pointer -- a commit sha is rewritten by `gh pr merge "
            "--rebase` and a path can move, but the blob is the content itself" % HEADER_LINES
        )
    if not sig:
        problems.append("no `Record-Sig: <8 hex>` line in the first %d lines" % HEADER_LINES)

    secs = _sections(text)
    boxes, box_problems = parse_boxes(secs.get("Boxes", ""))
    problems.extend(box_problems)

    # `(record)` INSIDE a box line is the shape this rule exists to refuse: it would make the annotation part of the task text, which changes the task signature and so silently breaks the ledger's A0 comparison.
    problems.extend(
        "the box line %r carries `(record)` inside it. The annotation belongs on "
        "its OWN 4-space line beneath the box; inside the box it becomes part of "
        "the task text, which changes the ledger signature" % b["line"][:80]
        for b in boxes
        if "(record)" in b["line"]
    )

    return {
        "status": status,
        "title": lines[0].lstrip("# ").strip() if lines else "",
        "owner": _owner_line(head),
        "full_text_sha": ft.group(1) if ft else "",
        "full_text_path": ft.group(2) if ft else "",
        "blob": blob.group(1) if blob else "",
        "record_sig": sig.group(1) if sig else "",
        "sections": secs,
        "boxes": boxes,
        "trailer": _trailer(secs.get("Record", "")),
        "history": [
            ln for ln in (secs.get("History", "") or "").splitlines() if ln.strip().startswith("-")
        ],
        "problems": problems,
    }


def parse_boxes(body):
    """([box dicts], [problems]) for a `## Boxes` body.

    Each box is {line, mark, body, sig, done}. A box with no `(record)` line
    beneath it is a PROBLEM rather than a silent skip: an unannotated box in a record is a claim with no attestation, which is the whole thing this file is here to stop.
    """
    boxes, problems = [], []
    lines = (body or "").splitlines()
    i = 0
    while i < len(lines):
        m = BOX_LINE_RE.match(lines[i])
        if not m:
            if RECORD_LINE_RE.match(lines[i]):
                problems.append(
                    "a `(record)` line at %r follows no box line" % lines[i].strip()[:60]
                )
            i += 1
            continue
        line, mark, task = lines[i], m.group(1).lower(), m.group(2)
        ann = RECORD_LINE_RE.match(lines[i + 1]) if i + 1 < len(lines) else None
        if not ann:
            problems.append(
                "the box %r carries no `    (record) sig=.. done=..` line beneath it" % task[:70]
            )
            i += 1
            continue
        boxes.append(
            {
                "line": line,
                "mark": mark,
                "body": re.sub(r"[*_`]+", "", task).strip(),
                "sig": ann.group(1),
                "done": ann.group(2),
            }
        )
        i += 2
    return boxes, problems


def is_record(text):
    return parse(text) is not None


# --------------------------------------------------------------------------- The signature.


def record_sig(rec):
    """8 hex over the record's STRUCTURAL SPINE, and nothing else.

    Covered: status, the pointer (both halves), and, per box in file order, the
    raw line plus its signature plus its `done=` value. So a re-worded box, a
    swapped blob, a downgraded status or a forged `done=` all move the signature.

    NOT covered: `## Why`, `## Outcome`, `## Lessons`, `## Record` and `## History`. Prose must stay editable -- `agent/README.md:57` puts durable designs in the "sharpen; edit in place when wrong" lifetime, and a signature that froze the prose would make the record the one document in this tree that cannot be corrected. `## History` is excluded for the same reason plus one more:
    it is append-only, so covering it would invalidate the signature on every append, which is a signature that fails routinely and is therefore ignored.

    The `Record-Sig:` line itself is excluded by construction -- it is not part of the canonical string -- so the signature is computable before it is written.
    """
    parts = [
        "status=%s" % rec.get("status", ""),
        "blob=%s" % rec.get("blob", ""),
        "fulltext=%s %s" % (rec.get("full_text_sha", ""), rec.get("full_text_path", "")),
    ]
    parts.extend(
        "box=%s\t%s\t%s" % (b["line"], b["sig"], b["done"]) for b in rec.get("boxes") or []
    )
    canon = "\n".join(parts)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:8]


def box_sig(task_body):
    """`check_plan_boxes.sig`, restated ONCE and asserted equal by the tests.

    Not imported: this module lives in `.claude/hooks/stop` and the gate lives in `.ci/scripts/quality`, and the import already runs the other way (the gate imports this directory's parser). Importing back would make the two directories mutually dependent for a four-line function. `test-planrec.py` asserts equality against the gate's own implementation, which is what keeps the two
    from drifting.
    """
    return hashlib.sha256(PFID._norm(task_body or "")[:120].encode("utf-8")).hexdigest()[:8]


# ---------------------------------------------------------------------------
# The ledger walk: `done=` comes from history, never from a claim.


def ledger_history(root, ledger_rel=LEDGER_REL):
    """[(commit, {plans: ...})] for the ledger, OLDEST FIRST.

    Oldest first because `done=` records the FIRST commit that attests a tick.
    Taking the newest would record the most recent regeneration of the ledger, which is a date with no meaning: the ledger is rewritten wholesale by `--update`, so every sig in it appears in every later commit.
    """
    out = []
    log = _git_out(root, "log", "--reverse", "--format=%H", "--", ledger_rel)
    for sha in (log or "").split():
        raw = _git_out(root, "show", "%s:%s" % (sha, ledger_rel))
        if not raw:
            continue
        try:
            out.append((sha, json.loads(raw)))
        except ValueError:
            # A commit whose ledger does not parse is SKIPPED, not fatal: the walk is looking for the first commit that attests a sig, and an unparseable intermediate cannot attest anything.
            continue
    return out


def ledger_at(root, commit, ledger_rel=LEDGER_REL):
    """The ledger document as of one commit, or None. This is the ORACLE the gate
    re-derives `done=` from, which is what makes the field unforgeable: a record
    can claim any sha it likes, and `git show <sha>:<ledger>` either carries the signature or it does not."""
    raw = _git_out(root, "show", "%s:%s" % (commit, ledger_rel))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def attested_at(ledger, rel, sig):
    """Does this ledger document attest `sig` as DONE for plan `rel`?"""
    if not isinstance(ledger, dict):
        return False
    entry = (ledger.get("plans") or {}).get(rel)
    if not isinstance(entry, dict):
        return False
    return sig in (entry.get("done_sigs") or [])


def done_commit(history, rel, sig):
    """The first commit in `history` that attests `sig` for `rel`, or ""."""
    for commit, doc in history:
        if attested_at(doc, rel, sig):
            return commit
    return ""


# --------------------------------------------------------------------------- derive(): everything the record can compute about itself.


def derive(root, rel, text=None, history=None):
    """The pointer, the epics, the touched paths, the cited gates, and the boxes
    with their `done=` values. Never raises; refusals come back as `problems`.

    THE POINTER IS COMPUTED FROM CONTENT, NOT FROM THE INDEX. `git hash-object` hashes the bytes on disk, so it answers identically in every clone and after any rebase. That is the property the whole design rests on (see the module docstring).

    IT DOES NOT STORE ANYTHING, and that distinction is load-bearing rather than pedantic. Without `-w`, `hash-object` computes an id and writes no object -- so the id alone is not a promise that anything is recoverable. What makes the pointer real is `compact`'s refusal of a DIRTY path: a committed file's blob is already in the object database and stays reachable through history
    for as long as the repository exists. The refusal and the pointer are therefore one mechanism, not two, and the check below turns that argument into a test -- a blob that does not resolve is reported rather than recorded.

    The commit half is found with `git log --find-object`, restricted to commits that are ANCESTORS OF origin/main. A blob that exists only on this branch has no landed commit yet, and saying so honestly -- by omitting `Full-Text:` -- is better than naming a sha that the merge will rewrite. The gate's `--update` fills it in later, once the text has landed.
    """
    root = pathlib.Path(root)
    p = root / rel
    problems = []
    if text is None:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return {"problems": ["cannot read %s: %s" % (rel, exc)]}

    blob = _git_out(root, "hash-object", "--", str(p)) or ""
    blob = blob.split("\n")[0].strip()
    if len(blob) != 40:
        problems.append(
            "git hash-object could not compute a blob id for %s, so there is no durable "
            "pointer to record" % rel
        )
    elif not resolve(root, "blob", blob)[0]:
        # THE ARGUMENT ABOVE, AS A TEST. `hash-object` without `-w` stores nothing, so a computed id is only a real pointer when the object is already in the database -- which it is, for a committed path. If it is not, the clean-path refusal has been bypassed somehow and the record would advertise a recovery command that returns nothing. Refuse instead of trusting the reasoning.
        problems.append(
            "the blob id for %s computes to %s, but that object is not in this "
            "repository. `git hash-object` does not STORE anything -- the pointer is only "
            "real because a committed file's blob is already there. Commit the path "
            "first" % (rel, blob[:12])
        )

    commit = ""
    if blob:
        found = _git_out(root, "log", "--all", "--format=%H", "--find-object=" + blob, "--", rel)
        for sha in (found or "").split():
            if resolve(root, "ancestor", sha)[0]:
                commit = sha
                break

    open_t, done_t = PF.plan_boxes(text)
    if history is None:
        history = ledger_history(root)
    current = history[-1][1] if history else None

    boxes, seen, dropped = [], set(), []
    for raw in text.splitlines():
        m = BOX_LINE_RE.match(raw)
        if not m:
            continue
        body = re.sub(r"[*_`]+", "", m.group(2)).strip()
        # DEDUPED ON THE PARSER'S OWN KEY, because `plan_tasks` dedupes on it too. Without this a plan that writes the same box twice yields two annotated lines here while `plan_boxes` still resolves one, so the record's `Boxes: N attested` trailer and the ledger's counts disagree -- and the ledger is what `check_plan_boxes.py`'s A0 compares against.
        key = PFID._norm(body)[:120]
        if key in seen:
            continue
        seen.add(key)
        # Only lines the REAL parser resolved as tasks. A checkbox inside a fence is a code sample (`check_plan_boxes.py`'s C-FENCE control is built on exactly this distinction), and annotating one would put a phantom box into the record.
        if body[:300] not in open_t and body[:300] not in done_t:
            # DROPPED, AND SAID SO. `plan_tasks` discards a task whose normalised key is under 8 characters and de-duplicates on that key, so a genuine `- [x] ok` box exists in the plan and reaches neither list. `_assert_boxes_preserved` cannot catch it -- it runs the same parser on both sides, so both sides agree the box is not there. Design property 2 is that box lines survive
            # BYTE-IDENTICAL, so a line that does not survive has to be named rather than silently left behind. Not a refusal: the box is invisible to every other consumer in this repo too, including the ledger the record is measured against, so refusing would block compaction on a line nothing else can see either.
            dropped.append(raw.strip()[:70])
            continue
        mark = m.group(1).lower()
        s = box_sig(body)
        if mark == "x":
            c = done_commit(history, rel, s)
            done = sha9(c) if c else "abandoned"
            if not c and current is not None and attested_at(current, rel, s):
                # Cannot happen with a walk that includes HEAD's ledger commit, and is reported rather than assumed away: it would mean the history walk is blind, which is the vacuity shape this repo refuses to pass through silently.
                problems.append(
                    "box %r is attested in the CURRENT ledger but no commit in the "
                    "ledger's history carries it. The history walk is blind." % body[:60]
                )
        else:
            done = "open"
        boxes.append({"line": raw, "mark": mark, "body": body, "sig": s, "done": done})

    epics = sorted(set(PR_TASK_RE.findall(_git_out(root, "log", "--format=%B", "--", rel) or "")))

    import wl_checks as CK  # noqa: PLC0415 -- see resolve()

    touched = []
    for m in CK.CITE_RE.finditer(text):
        cand = m.group(1)
        if cand not in touched and (root / cand).is_file():
            touched.append(cand)
    gates = sorted({g for g in GATE_RE.findall(text) if resolve(root, "gate", g)[0]})

    return {
        "rel": rel,
        "blob": blob,
        "commit": sha9(commit),
        "boxes": boxes,
        "epics": epics,
        "touched": touched[:20],
        "gates": gates[:20],
        "n_open": sum(1 for b in boxes if b["done"] == "open"),
        "n_abandoned": sum(1 for b in boxes if b["done"] == "abandoned"),
        "n_attested": sum(1 for b in boxes if b["done"] not in ("open", "abandoned")),
        "dropped": dropped,
        "problems": problems,
    }


# --------------------------------------------------------------------------- Rendering.

READ_HISTORY = "`git show %s` recovers the text; `git log --find-object=%s --all` names the commit"


def render(rec):
    """The record, as the exact bytes that go on disk.

    ORDER IS PART OF THE GRAMMAR, not a style choice: the header block must land inside the first HEADER_LINES (10) lines or `wl_checks.plan_records` cannot see the Status line, and the whole file then reads as an ordinary plan with an unparseable header -- which is worse than not compacting it, because it stays on the housekeeping clock while LOOKING like a record.
    """
    status = rec["status"]
    lines = ["# %s" % (rec.get("title") or "record"), "Status: %s" % status]
    if rec.get("owner"):
        lines.append("Owner: %s" % rec["owner"])
    if rec.get("full_text_sha") and rec.get("full_text_path"):
        lines.append("Full-Text: %s %s" % (rec["full_text_sha"], rec["full_text_path"]))
    lines.append("Full-Text-Blob: %s" % rec["blob"])
    lines.append("Record-Sig: %s" % record_sig(rec))
    lines.append("")

    for name in PROSE_SECTIONS:
        lines.append("## %s" % name)
        lines.append((rec.get("sections", {}).get(name) or "").strip() or placeholder(name.lower()))
        lines.append("")

    lines.append("## Boxes")
    if rec.get("boxes"):
        for b in rec["boxes"]:
            lines.append(b["line"])
            lines.append("    (record) sig=%s done=%s" % (b["sig"], b["done"]))
    else:
        lines.append("(this plan carried no checkbox tasks)")
    lines.append("")

    lines.append("## Record")
    tr = rec.get("trailer") or {}
    for k in (
        "Record-Kind",
        "Prior-Status",
        "Compacted-By",
        "Compacted-At",
        "Boxes",
        "Epics",
        "Touched",
        "Gates",
        "Why-Source",
        "Read-History",
    ):
        if tr.get(k):
            lines.append("%s: %s" % (k, tr[k]))  # noqa: PERF401 -- a filtered loop, not a map
    lines.append("")

    lines.append("## History")
    lines.extend(
        h if h.startswith("- ") else "- %s" % h.lstrip("- ") for h in rec.get("history") or []
    )
    return "\n".join(lines).rstrip("\n") + "\n"


def size_budget(n_boxes):
    return RECORD_MAX_BYTES + RECORD_PER_BOX_BYTES * max(0, int(n_boxes))


# --------------------------------------------------------------------------- The index.

INDEX_HEADER = """# Compacted plan records

GENERATED by `npm run check:ci-plan-record -- --update`. Do NOT hand-edit: this file is a second reading of the records, so a hand-edit is the one thing that can make it agree with a tree it does not describe.

A compacted plan keeps its own path, so every citation of it still resolves. Its full text lives in a git BLOB rather than in the file, because this repo merges with `gh pr merge --rebase` and a commit sha recorded on a branch is rewritten at merge -- measured 2026-09-06, 37 of 71 commit-shaped tokens already cited in plans no longer resolve.
A blob id is content-addressed and survives the rebase.

To read one in full:

    git show <blob>
    git log --find-object=<blob> --all

| Plan | Status | attested / open / abandoned | Full-Text-Blob |
|---|---|---|---|
"""


def render_index(rows):
    """The whole of `agent/INDEX.md`, or "" when there is nothing to index.

    "" IS A REAL ANSWER and the gate treats an absent file as equal to it. A repo
    with no records yet must not be forced to carry an empty table, and
    `--update` writing one would be a generated file that says nothing -- the committed-lie shape `agent/README.md:11` names.

    `rows` is [(rel, status, n_attested, n_open, n_abandoned, blob)], sorted here rather than by the caller so the render is a pure function of the SET and two callers cannot disagree about order.
    """
    if not rows:
        return ""
    body = "".join(
        "| %s | %s | %d / %d / %d | `%s` |\n" % (r[0], r[1], r[2], r[3], r[4], r[5])
        for r in sorted(rows)
    )
    n_c = sum(1 for r in rows if r[1] == STATUS_COMPACTED)
    n_p = sum(1 for r in rows if r[1] == STATUS_PARKED)
    return (
        INDEX_HEADER
        + body
        + (
            "\n%d record(s): %d compacted, %d parked. A parked record stays on the "
            "housekeeping clock on purpose -- its work is not finished, only its text "
            "is compacted.\n" % (len(rows), n_c, n_p)
        )
        + render_edges(index_edges(rows))
    )


def index_rows(root, plan_records):
    """[(rel, status, attested, open, abandoned, blob)] for every record on disk.

    `plan_records` is passed in (it is `wl_checks.plan_records(root)`) rather than imported, for the same reason `wl_planfile.plan_rows` takes it: this module is driven by a CI gate and by a test fixture, and neither should have to own the 6,100-line import to enumerate a directory.
    """
    rows = []
    for rel, status, _n in plan_records:
        if status not in RECORD_STATES:
            continue
        try:
            text = (pathlib.Path(root) / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rec = parse(text)
        if rec is None:
            continue
        boxes = rec["boxes"]
        rows.append(
            (
                rel,
                status,
                sum(1 for b in boxes if b["done"] not in ("open", "abandoned")),
                sum(1 for b in boxes if b["done"] == "open"),
                sum(1 for b in boxes if b["done"] == "abandoned"),
                rec["blob"],
                # THE SEVENTH ELEMENT IS OPTIONAL EVERYWHERE IT IS READ, and that is not defensive coding for its own sake: `check_plan_record.py` builds six-element rows by hand in its own R8 controls, and that file has a single owner who is not this one. A render that demanded seven would red a gate's selftest to add a table.
                trailer_paths(rec["trailer"].get("Touched", "")),
            )
        )
    return rows


# --------------------------------------------------------------------------- P2.1 The edge index, and why_lines(): the history, pushed at the edit.
#
# WHAT THIS IS FOR. A record is only worth compacting into if somebody reads it, and nobody goes looking for a record about a file they are about to change -- they do not know it exists. The edge index closes that: every record already carries a `Touched:` trailer naming the paths its plan cited, so the reverse map from PATH to RECORD is already in the tree and merely unwritten.
#
# WHY THE INDEX AND NOT THE RECORDS THEMSELVES. Answering "what is recorded about this file" by opening every record is the cost P1.7 just removed from SessionStart, where opening 79 plans to print 49 filenames was the measured defect. The edge table is ONE file read, and only the records that actually have an edge are then opened. A push that costs a directory walk on every Edit
# is a push that gets turned off.
#
# WHY THE INDEX CAN BE TRUSTED. `agent/INDEX.md` is compared for EQUALITY against `render_index` by check:ci-plan-record's R8. So the edge table is not a cache that can quietly go stale: a stale one is red in CI. That is the whole reason the edges live there rather than in a sidecar nothing checks.

#: How many records one answer names, and how much of each record's `## Why` it
#: quotes. Both are caps on a PUSH -- text the reader did not ask for -- and the
#: failure mode of an uncapped push is that it stops being read at all. Three
#: records is what the widest path in this tree's own corpus would produce.
WHY_MAX_RECORDS = int(os.environ.get("WORKLIST_WHY_MAX_RECORDS", "3"))
WHY_MAX_CHARS = int(os.environ.get("WORKLIST_WHY_MAX_CHARS", "220"))

#: The edge table's own header and row grammar. Written by `render_edges` and
#: read back by `why_index`, which is a round trip through markdown and therefore
#: worth stating once: the FIRST cell is backticked and the row has exactly two
#: cells, neither of which is true of the record table above it, so the two
#: cannot be confused even if a future edit drops the section split.
EDGE_SECTION = "## Files these records touch"
EDGE_ROW_RE = re.compile(r"^\|[ \t]*`([^`|]+)`[ \t]*\|[ \t]*([^|]+?)[ \t]*\|[ \t]*$", re.MULTILINE)

#: The three answers `why_lines` can give, and the middle one is the point of the
#: whole function. "No record names this file" is a RESULT -- it means the search
#: happened and found nothing -- while "there is no index" means the search could
#: not happen. Collapsing them into an empty list would let a blind index look
#: exactly like a clean answer, which is the vacuity shape this repo refuses.
WHY_EDGES = "edges"
WHY_NO_EDGE = "no-edge"
WHY_NO_INDEX = "no-index"


def trailer_paths(value):
    """`Touched: a, b, c` -> ("a", "b", "c"). A tuple, so a row stays hashable and `sorted(rows)` keeps working on it."""
    return tuple(x.strip() for x in (value or "").split(",") if x.strip() and x.strip() != "none")


def index_edges(rows):
    """{path: [record, ...]} from index rows, both keys and values sorted.

    THE SEVENTH ELEMENT IS OPTIONAL. `check_plan_record.py` hand-builds six-element rows in its R8 controls and that file is not this one's to edit, so a row with no edges contributes none rather than raising. The cost of the tolerance is that a caller which forgets the element gets a smaller table instead of an error -- acceptable here because the only two producers of real rows
    are `index_rows` and the gate, and the gate compares the render against the file rather than against a count.
    """
    out = {}
    for row in rows:
        rel = row[0]
        for t in row[6] if len(row) > 6 else ():
            out.setdefault(t, [])
            if rel not in out[t]:
                out[t].append(rel)
    return {k: sorted(v) for k, v in sorted(out.items())}


def render_edges(edges):
    """The edge table, or "" when there are no edges.

    "" is deliberate and matches `render_index`'s own empty answer: a table with no rows is a generated document that says nothing, which is the committed-lie shape `agent/README.md:11` names.
    """
    if not edges:
        return ""
    rows = "".join(
        "| `%s` | %s |\n" % (path, ", ".join(recs)) for path, recs in sorted(edges.items())
    )
    return (
        "\n%s\n\nWhat `--plan-why <path>` answers from. Each row is a path a compacted plan cited, so a session about to edit that path can be handed the plan's reasoning without knowing the record exists.\n\n"
        "| File | Records |\n|---|---|\n%s" % (EDGE_SECTION, rows)
    )


def why_index(root):
    """{path: [record, ...]} read back out of `agent/INDEX.md`. ONE file read.

    Returns {} for an absent file, an index with no edge section, or an
    unreadable one. The three are indistinguishable HERE on purpose -- the distinction that matters to a caller is "is there an index at all", which `why_lines` answers separately by asking whether the file exists.
    """
    try:
        text = (pathlib.Path(root) / INDEX_REL).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    cut = text.find(EDGE_SECTION)
    if cut < 0:
        return {}
    out = {}
    for m in EDGE_ROW_RE.finditer(text[cut:]):
        recs = [r.strip() for r in m.group(2).split(",") if r.strip()]
        if recs:
            out[m.group(1).strip()] = recs
    return out


def why_first_line(text):
    """The first real sentence of a record's `## Why`, or "".

    First LINE and not the whole section, because this is a push: the reader gets one line per record and follows the pointer if it matters. A bullet marker is stripped so a `## Why` written as a list reads the same as one written as a paragraph.
    """
    rec = parse(text)
    if rec is None:
        return ""
    for raw in (rec["sections"].get("Why") or "").splitlines():
        ln = raw.strip().lstrip("-*+ ").strip()
        if ln and not PLACEHOLDER_RE.search(ln):
            return clip(ln, WHY_MAX_CHARS)
    return ""


def why_lines(root, path, index=None, limit=WHY_MAX_RECORDS):
    """([line, ...], state) -- what the compacted history says about `path`.

    `state` is WHY_EDGES, WHY_NO_EDGE or WHY_NO_INDEX. The caller decides how loudly to say each; this function never prints and never guesses.

    THE PATH IS NORMALISED TO THE REPO-RELATIVE SPELLING the index uses, because every caller has a different one: a hook gets an absolute path from the tool payload, a session types `./agent/...`, and the index stores neither. A lookup that missed on the prefix would return WHY_NO_EDGE -- a confident "nothing is recorded" about a file that has a record -- which is the one wrong
    answer this function must not produce.
    """
    root = pathlib.Path(root)
    try:
        rel = str(pathlib.Path(path).resolve().relative_to(root.resolve()))
    except (ValueError, OSError):
        rel = str(path).lstrip("./")
    if index is None:
        index = why_index(root)
    if not index:
        # THE PREDICATE IS "DOES THE FILE CARRY AN EDGE TABLE", NOT "DOES THE FILE EXIST". It used to be `.is_file()`, which was correct only while agent/INDEX.md was written solely by --plan-compact. Since W12 P1.7 the same file also carries a plan CENSUS, so it exists from the first census write even when no plan has been compacted and no edge has ever been recorded. Under the
        # old test that made --plan-why answer WHY_NO_EDGE, which states as fact that the index was read and names no path matching this one -- the confident wrong answer this
        # function's own docstring forbids six lines above.
        try:
            has_edges = EDGE_SECTION in (root / INDEX_REL).read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            has_edges = False
        return [], (WHY_NO_EDGE if has_edges else WHY_NO_INDEX)
    hits = index.get(rel) or []
    if not hits:
        return [], WHY_NO_EDGE
    lines = []
    for r in hits[: max(1, limit)]:
        try:
            text = (root / r).read_text(encoding="utf-8", errors="replace")
        except OSError:
            # A record named by the index and absent from disk is REPORTED rather than skipped. Silence here would be the index quietly describing a tree it does not describe, and R8 is what normally catches that -- but R8 runs in CI and this runs at the edit.
            lines.append("%s: named by %s but not on disk" % (r, INDEX_REL))
            continue
        rec = parse(text)
        why = why_first_line(text)
        lines.append(
            "%s (%s): %s"
            % (r, (rec or {}).get("status", "unparseable"), why or "(no ## Why recorded)")
        )
        if rec and rec.get("blob"):
            lines.append("    full text: git show %s" % rec["blob"])
    if len(hits) > limit:
        lines.append("    ...and %d more record(s); see %s" % (len(hits) - limit, INDEX_REL))
    return lines, WHY_EDGES


# --------------------------------------------------------------------------- P2.3 The two OTHER moments the history is worth pushing, behind one function.
#
# The edit is the first moment (why-on-edit.py). The other two are the moments a session is MOST likely to reason without history and least likely to go looking
# for it:
#
# POSTCOMPACT the transcript is now a summary, so whatever the session knew about why a file is the shape it is has just been thrown away. The files it has in flight have not changed. CI RED wl_histfirst.py already exists because a measured session made 2,494 Bash calls debugging a red gate and ZERO `git log` calls naming the file. The record is the same missed evidence one layer
# up: the commit says what changed, the record says why the plan wanted it that way.
#
# ONE FUNCTION FOR BOTH, and it returns "" rather than a sentence when nothing matches. Both callers APPEND to a block that is already being emitted, so an empty answer must add nothing at all -- this is the opposite of `--plan-why`, where a person asked and silence would read as breakage. Same distinction as why-on-edit.py property 1, for the same reason.


def why_for_paths(root, paths, limit=WHY_MAX_RECORDS):
    """A block naming the records that cover any of `paths`, or "".

    `limit` caps the number of PATHS reported, not the number of records: a session with forty files in flight gets the first few and the pointer to `--plan-why`, because a block nobody finishes reading taught nothing.
    """
    index = why_index(root)
    if not index:
        return ""
    hits, extra = [], 0
    for path in paths:
        lines, state = why_lines(root, path, index=index)
        if state != WHY_EDGES or not lines:
            continue
        if len(hits) >= max(1, limit):
            extra += 1
            continue
        hits.append((path, lines))
    if not hits:
        return ""
    body = ["THE COMPACTED PLAN HISTORY NAMES %d OF THESE FILES." % (len(hits) + extra)]
    for path, lines in hits:
        body.append("  %s" % path)
        body.extend("    %s" % ln for ln in lines)
    if extra:
        body.append("  ...and %d more file(s). Ask: worklist.py --plan-why <path>" % extra)
    body.append(
        "  These plans are finished; their full text is a git blob, not the file. "
        "`git show <blob>` reads one."
    )
    return "\n".join(body)


# --------------------------------------------------------------------------- Writing. Tempfile + os.replace, and NEVER a commit.


def write_atomic(path, text):
    """The worklist store's own write discipline, for the same reason it has it.

    A half-written record is the one state this design cannot survive: the full text would be in neither the file nor a blob anything points at. `os.replace` is atomic within a filesystem, and the tempfile is created in the TARGET directory so it always is one.
    """
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".planrec-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, str(path))
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


# --------------------------------------------------------------------------- P2.6 Pointer stamps: the same idiom, applied to the two OTHER things in this repo that replace a document with a smaller one.
#
# Compaction of a plan is not the only place bytes are overwritten. Two more do it routinely, and until now neither said where the replaced bytes went:
#
# THE EVENT STORE. `wl_store.compact_store` rewrites agent/worklist/*.jsonl into one snapshot and unlinks the rest. Those files are TRACKED, so a committed one's blob is in the object database and survives the unlink -- but only if somebody wrote the id down before it happened.
#
# STATE.md. `worklist.py --state` replaces the outgoing document and keeps ONE copy in a `.prev` slot under TMPDIR, which does not survive a reboot. The document itself is tracked, so the same pointer is available.
#
# WHAT A STAMP IS, and what it is NOT. `git hash-object` computes an id and, with no `-w`, STORES NOTHING. So the id alone is not a promise of recoverability -- it is one exactly when the object is already in the database, which is true for a committed path and false for a dirty one. That is why this returns `resolves` and why the sentence changes with it: a stamp that advertised
# `git show` for bytes git does not have would be the same quiet lie the record gate exists to refuse, one layer down.


def pointer_stamp(root, rel):
    """(blob, resolves, sentence) for the bytes at `rel` RIGHT NOW.

    Call it BEFORE the overwrite. `sentence` is written for a human reading a terminal, and it says which of the two cases holds rather than making the reader infer it from the presence of a hash.
    """
    root = pathlib.Path(root)
    blob = (_git_out(root, "hash-object", "--", str(root / rel)) or "").split("\n")[0].strip()
    if len(blob) != 40:
        return "", False, "%s: no blob id could be computed, so nothing points at these bytes" % rel
    if not resolve(root, "blob", blob)[0]:
        return (
            blob,
            False,
            "%s: blob %s is NOT in this repository -- these bytes were never committed, so "
            "nothing here can recover them and no recovery command is offered" % (rel, blob[:12]),
        )
    return blob, True, "%s: recoverable with `git show %s`" % (rel, blob)


def is_dirty(root, rel):
    """Is this path modified, staged or untracked?

    A dirty path is REFUSED, and the reason is the blob. `git hash-object` hashes the bytes on disk, so compacting a dirty file would mint a pointer to content that exists in no commit and, once the file is overwritten by the record, in no working tree either. The text would be gone. This is the one refusal in this module that protects against data loss rather than against a wrong
    claim.
    """
    return bool(_git_out(root, "status", "--porcelain", "--", rel).strip())


# --------------------------------------------------------------------------- The model call. ONE bounded `claude -p`, in wl_shapedup.ask's shape.

WHY_SCHEMA = {
    "type": "object",
    "properties": {
        "why": {"type": "string", "maxLength": 700},
        "outcome": {"type": "string", "maxLength": 700},
        "lessons": {"type": "array", "maxItems": 5, "items": {"type": "string", "maxLength": 300}},
    },
    "required": ["why", "outcome", "lessons"],
    "additionalProperties": False,
}
ASK_SCHEMA = {
    "type": "object",
    "properties": {"plan_record": WHY_SCHEMA},
    "required": ["plan_record"],
    "additionalProperties": False,
}

WHY_PROMPT = """
COMPACT THIS PLAN INTO A RECORD.

The plan below is finished. Its full text is preserved in a git blob and will still
be recoverable; what you write replaces the READING COPY, so it must carry what a
person needs months from now when the blob is one `git show` away but nobody knows
whether it is worth running.

Three fields, and none of them is a summary of the plan's structure:

  why      what problem existed, in one short paragraph. NOT "this plan proposed
           X" -- the reader can see that. What was broken, and how it was noticed.
  outcome  what is true NOW as a result. Landed, abandoned, superseded by
           something else: say which, and say what a reader can go and look at.
  lessons  at most 5 bullets, each a thing that would be RE-LEARNED the hard way
           without this record. A lesson that is generic advice is worse than no
           lesson: drop it.

DO NOT invent file paths, commit shas, gate ids or plan names. Anything you write
that does not resolve against the real repository is replaced with the literal
text `[unresolved]` before the record is written, which is a visible defect in a
durable document. When you are not certain a pointer is real, describe the thing
in words instead.

The plan:

%(plan)s
"""


def ask_why(plan_text):
    """(fields, error). ONE `claude -p`, never raises. Laundered by the caller.

    THE RECURSION GUARD IS NOT OPTIONAL. `claude -p` fires the Stop hook, and the
    Stop hook is this file's own process tree; without `STOPHOOK_CHILD=1` the
    child blocks on the parent's open items and the call hangs until the timeout. Every other model call in this directory carries it (`wl_shapedup.ask`, `wl_judge.run_triage`, `run_judge`), and this is the fourth.

    The model, the budget and the timeout are wl_judge's -- `WORKLIST_JUDGE_MODEL` defaults to haiku. Not a new knob: a second model setting is a second thing to calibrate, and CLAUDE.md's i18n section already records what happens when the cheap default is not the one that gets used.
    """
    import wl_judge  # noqa: PLC0415 -- see resolve()

    exe = wl_judge.resolve_claude()
    if not exe or not os.path.exists(exe):
        return None, "claude CLI not found"
    env = dict(os.environ)
    env["STOPHOOK_CHILD"] = "1"
    prompt = WHY_PROMPT % {"plan": (plan_text or "")[:40000]}

    # ONE PLACE THAT LAUNCHES IT, so the retry below re-runs the identical call rather than a hand-copied approximation of it.
    def call():
        return wl_proc.run(
            [
                exe,
                "-p",
                prompt,
                "--output-format",
                "json",
                "--json-schema",
                json.dumps(ASK_SCHEMA),
                "--model",
                wl_judge.JUDGE_MODEL,
                "--max-budget-usd",
                wl_judge.JUDGE_BUDGET_USD,
            ],
            timeout=wl_judge.JUDGE_TIMEOUT_S,
            env=env,
        )

    proc = call()
    if proc.timed_out:
        return None, "plan_record model call timed out after %ds" % wl_judge.JUDGE_TIMEOUT_S
    if proc.returncode == wl_proc.SPAWN_FAILED_RC and not proc.stdout:
        return None, "plan_record model call failed: %s" % proc.stderr.strip()

    # A SCHEMA EXHAUSTION IS A SAMPLE, NOT A VERDICT, and this site was the one that had not been told. `check:ci-schema-call-sites` named it, and the reason it matters here is worse than for the judge: this call writes a durable record. Refusing on one non-conforming sample would leave the compaction reporting "the model could not answer" and silently falling back to `--why auto`,
    # which is a provenance the trailer would then have to state truthfully forever.
    #
    # The helper is bounded, not a loop: only the exhaustion subtype, only with budget headroom, only once, and never after a transport failure, which raises above and never reaches here.
    if proc.returncode != 0:
        proc, why = wl_judge.retry_schema_exhaustion("plan_record", proc, call)
        if proc is None:
            return None, why
    try:
        env_out = json.loads(proc.stdout)
    except ValueError as exc:
        return None, "plan_record reply was not JSON: %s" % exc
    if not isinstance(env_out, dict):
        return None, "plan_record reply was not an object"
    if env_out.get("is_error"):
        return None, "plan_record reported is_error (subtype=%s)" % env_out.get("subtype")
    inner = env_out.get("structured_output")
    if not isinstance(inner, dict):
        return None, "plan_record returned no structured_output"
    fields = inner.get("plan_record")
    if not isinstance(fields, dict):
        return None, "plan_record returned no plan_record object"
    return fields, ""


# --------------------------------------------------------------------------- compact() and revive(): the two transitions.

AUTO_SOURCES = ("author", "auto", "model")


#: A box line, matched only to DELETE it from lifted prose. See _auto_prose.
#: All four marks, for the same reason BOX_LINE_RE carries them: a `[?]`/`[>]`
#: line this missed would leak through into the Status quote uncut and get
#: double-counted as a phantom box by wl_planfid.plan_tasks, which already
#: recognizes all four.
ANY_BOX_LINE = re.compile(r"^\s*[-*+]\s+\[[ xX?>]\]\s")


def title_of(text, rel):
    """The record's `# ` heading.

    NOT `lines[0]`, which is what the first cut used and which is wrong on 9 of the 81 plans in this tree: they open with the `Status:` / `Owner:` header block and put the H1 underneath it. Taking line 0 there produced `# Status: partially implemented ...` as the record's title, which puts a SECOND `Status:`-shaped string inside the header window that
    `wl_checks.PLAN_STATUS_INLINE_RE` -- the unanchored fallback -- can match. The anchored regex wins today, so the bug was cosmetic; it is fixed anyway because a header window with two status-shaped lines in it is one edit away
    from being read wrong, and the edit would be somewhere else entirely.

    Falls back to the slug, which always exists and always identifies the plan.
    """
    # FENCED BLOCKS ARE NOT HEADINGS. `# ` opens a comment in shell, python, ruby and every config language these plans quote, so scanning raw lines takes the first COMMENT in the first code block as the plan's title. Measured 2026-09-06: PLAN-lint-rule-matrix-probe.md was compacted to a record titled `# edit line 46: 'SFTPClient' -> 'SFTPClientZZZ'`, which is a line from a shell
    # snippet. A record's title is the one part of it every index and every reader sees first, so this is not cosmetic.
    fenced = False
    for raw in (text or "").splitlines():
        stripped = raw.lstrip()
        if stripped.startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            continue
        if raw.startswith("# "):
            body = raw[2:].strip()
            # A heading that is itself a header FIELD is the header block wearing a hash, not a title.
            #
            # THIS TESTS THE KEY AGAINST THE KNOWN FIELD NAMES, not the shape. It used to be `HEAD_FIELD_RE.match(body)`, which matches any `Word:` at all -- and 62 of the 83 plans in this tree are titled `# PLAN: <something>`. So `PLAN:` read as a header field, every one of those 62 fell through to the slug fallback below, and their records were titled with a slug instead of the
            # name their author gave them. Measured 2026-09-06 during the compaction wave, which was halted because of it. The title is the one part of a record that every index and every reader sees first.
            key = HEAD_FIELD_RE.match(body)
            if body and not (key and key.group(1) in HEADER_FIELD_KEYS):
                return body[:120]
    # OFF BY ONE, fixed 2026-09-06: this read `slug[4:]`, and `len("PLAN-")` is FIVE. Every plan that fell through to the fallback was titled with a leading hyphen -- `# -lint-css-ci-wiring`, `# -greenlight-verify-at-read` -- which reads as a slug rather than a name and is what a reader sees in the index. Written as a len() so the constant and the string cannot drift apart again.
    slug = pathlib.Path(rel).stem
    prefix = "PLAN-"
    return slug.removeprefix(prefix)


def clip(text, limit):
    """`text` cut to at most `limit` characters, on a LINE boundary, with any code fence it opened closed again.

    TWO FAILURES IN ONE FUNCTION, and the second is the expensive one.

    A raw `[:limit]` cuts mid-line, which is ugly. It also cuts BETWEEN a ``` and its partner, which is not ugly at all -- it is a correctness bug. An odd fence count makes `wl_planfid.plan_tasks` treat everything after it as fenced, including `## Boxes`, so the record parses to ZERO boxes and `_assert_boxes_preserved` refuses the compaction while blaming the boxes. Reproduced
    2026-09-06 on a synthetic `## Status` section of 1064 characters of prose followed by a fenced block; no plan in this tree hits it today, and `## Status` sections with fenced blocks are common here, so it is one plan edit away.

    Returns "" only for empty input: a clip that cannot keep a whole first line still keeps that line, because a truncated record is better than a record that silently lost a section.
    """
    text = (text or "").rstrip()
    if not text or len(text) <= limit:
        return text
    kept = []
    used = 0
    for ln in text.splitlines():
        if kept and used + len(ln) + 1 > limit:
            break
        kept.append(ln)
        used += len(ln) + 1
    if sum(1 for ln in kept if PFID.FENCE_RE.match(ln)) % 2:
        kept.append("```")
    return "\n".join(kept).rstrip()


def _auto_prose(text):
    """Why/Outcome/Lessons pulled out of the plan's OWN sections, no model.

    Deliberately dumb. It lifts `## Why`/`## Problem`/`## Status`/`## Outcome` verbatim when they exist and leaves a placeholder when they do not, because a mechanical paraphrase of a design document is exactly the "generic prose" failure `08-driver-contract.md:200` names: it satisfies a length check while dropping the paragraph that named a dated incident.
    """
    secs = _sections(text)
    lower = {k.lower(): v for k, v in secs.items()}

    def pick(*names):
        for n in names:
            v = (lower.get(n) or "").strip()
            if not v:
                continue
            # CHECKBOX LINES ARE STRIPPED, and this is a correctness rule rather than a formatting one. `## Boxes` must be the ONLY place a box appears in a record: `wl_planfid.plan_tasks` counts a checkbox line WHEREVER it sits, so a `## Status` section lifted verbatim (which in this tree routinely quotes its own ticked boxes) would make the record parse to more tasks than the
            # plan did. That disagreement lands in `.ci/config/plan-boxes.json` as a phantom box, and check_plan_boxes.py's A0 reports it against the wrong file. Caught by the render_preserves_boxes assertion in compact(), which is left in place as the standing control for this.
            kept = [ln for ln in v.splitlines() if not ANY_BOX_LINE.match(ln)]
            body = "\n".join(kept).strip()
            if body:
                return clip(body, 1200)
        return ""

    return {
        "Why": pick("why", "problem", "the problem", "motivation", "background"),
        "Outcome": pick("outcome", "status", "result", "results", "what landed"),
        "Lessons": pick("lessons", "traps", "what we learned", "notes"),
    }


def compact(root, rel, me, why="author", park=False, now=None):
    """Build the record for one plan. Returns (text, notes); raises RecordError.

    REFUSALS, and each one is a data-loss or a false-claim guard rather than a style preference:

      dirty path      the blob would point at bytes no commit carries, and the
                      record overwrites the file, so the text would be GONE.
      already a record  compacting a record would point the new blob at the old
                      record rather than at the plan. `--plan-revive` first.
      open boxes      without `--park`. A `compacted` status is in the FINISHED
                      set, and `check_plan_boxes.py`'s A3 refuses a finished
                      status over open boxes -- so this refusal is what keeps the
                      two gates from contradicting each other.

    `--park` records `parked` WHATEVER the box count, including zero. A plan can carry unfinished work in prose with no checkbox anywhere, and until 2026-09-06 that case silently produced `compacted` instead.
    """
    # ARGUMENTS FIRST, before anything reads or hashes a file. A bad `--why` is the caller's typo and must be answered as one; validating it after the is-it-already-a-record check made `--why wishful` on a record report "already a record", which is true and is not the problem the caller has.
    if why not in AUTO_SOURCES:
        raise RecordError("--why must be one of %s" % ", ".join(AUTO_SOURCES))
    root = pathlib.Path(root)
    p = root / rel
    if not p.is_file():
        raise RecordError("%s does not exist" % rel)
    text = p.read_text(encoding="utf-8", errors="replace")
    # ALREADY-A-RECORD IS CHECKED FIRST, and the order was the other way round until it was driven. A record written by `--write` is BOTH a record and (by definition, until it is committed) a dirty path, so the dirty branch won and answered "commit or revert the path first" -- true, and the wrong advice: committing it would compact the record a second time, pointing the new blob at
    # the old RECORD rather than at the plan. `--plan-revive` is the answer, and it is the answer whether the path is dirty or not.
    if is_record(text):
        raise RecordError(
            "%s is already a record. Use `--plan-revive <me> %s --write` to restore its "
            "full text before compacting again -- compacting a record would point the new "
            "blob at the record instead of at the plan." % (rel, rel)
        )
    if is_dirty(root, rel):
        raise RecordError(
            "%s has uncommitted changes. The record's pointer is `git hash-object` of the "
            "bytes on disk, and the record then OVERWRITES those bytes -- compacting a "
            "dirty file would leave the text in no commit and no working tree. Commit or "
            "revert the path first (never `git checkout`: that discards work)." % rel
        )

    d = derive(root, rel, text)
    if d.get("problems"):
        raise RecordError("; ".join(d["problems"]))
    if d["n_open"] and not park:
        raise RecordError(
            "%s carries %d open box(es). A `compacted` status is in the FINISHED set, and "
            "check_plan_boxes.py's A3 refuses a finished status over open boxes -- so "
            "compacting this would make two gates contradict each other. Finish the boxes, "
            "or pass --park to record it as `parked`, which stays on the housekeeping "
            "clock on purpose." % (rel, d["n_open"])
        )

    notes = []
    prose = dict.fromkeys(PROSE_SECTIONS, "")
    why_source = why
    if why == "auto":
        prose.update(_auto_prose(text))
    elif why == "model":
        fields, err = ask_why(text)
        if err:
            notes.append("the model could not answer (%s); falling back to --why auto" % err)
            prose.update(_auto_prose(text))
            # THE TRAILER MUST SAY WHAT ACTUALLY WROTE THE PROSE. It said `model` on this path, which is a record claiming a provenance it does not have -- the exact class of quiet lie the whole gate exists to refuse, inside the writer rather than the reader.
            why_source = "auto (--why model degraded)"
        else:
            lessons = fields.get("lessons") or []
            raw = {
                "Why": str(fields.get("why") or ""),
                "Outcome": str(fields.get("outcome") or ""),
                "Lessons": "\n".join("- %s" % str(x).strip() for x in lessons if str(x).strip()),
            }
            for k, v in raw.items():
                clean, replaced = launder(root, v)
                prose[k] = clean
                if replaced:
                    notes.append(
                        "%s: %d unresolvable pointer(s) laundered to %s -- %s"
                        % (k, len(replaced), UNRESOLVED, ", ".join(replaced[:5]))
                    )

    # `--park` IS AN ASSERTION BY THE CALLER, NOT A DERIVATION FROM THE BOXES. This read `park and d["n_open"]`, so a plan with NO checkbox boxes at all took the `compacted` branch however loudly the caller asked for `parked`: a SILENT no-op that handed the plan a housekeeping exemption it had not earned. agent/plans/PLAN-renet-fetch-hardening.md is the live case found 2026-09-06
    # -- zero boxes, seven of its eight sites still open in prose, and `Status: compacted`.
    #
    # Honouring the flag unconditionally can only err toward MORE nagging, never less: `parked` stays on the housekeeping clock, so a plan parked by mistake keeps asking to be finished. Nothing downstream reads `parked` as implying open boxes -- checked in check_plan_record.py (R6 treats parked as exempt
    # from the placeholder rule and nothing else) and in check-plan-housekeeping.sh
    # (`parked` is deliberately absent from the exemption branch at :431).
    status = STATUS_PARKED if park else STATUS_COMPACTED
    head = "\n".join(text.splitlines()[:HEADER_LINES])
    # THE RAW LINE, not wl_checks.plan_owner. plan_owner RESOLVES the value down to a session id, which is right for scoping the Stop hook's advisory and lossy here. Measured over this tree's 81 plans, resolving loses provenance on five of them and, worse, changes what two of them SAY: Owner: unowned (drafted by 9d92d9b6, 2026-08-28) -> no Owner line at all Owner: whichever session
    # picks it up -> no Owner line at all Owner: session 9d92d9b6, branch 0826-3 -> 9d92d9b6 A record that silently stops saying it is unowned has changed a fact about the plan while claiming to preserve it. plan_owner still reads the record afterwards and resolves the same id it always did, so nothing downstream loses anything by keeping the sentence intact.
    owner = _owner_line(head)
    prior = ""
    m = re.search(r"^\*{0,2}Status\*{0,2}:[ \t]*([A-Za-z-]+)", head, re.MULTILINE)
    if m:
        prior = m.group(1).lower()

    stamp = now or C.stamp_now()
    rec = {
        "status": status,
        "title": title_of(text, rel),
        "owner": owner,
        "full_text_sha": d["commit"],
        "full_text_path": rel if d["commit"] else "",
        "blob": d["blob"],
        "sections": prose,
        "boxes": d["boxes"],
        "history": [],
        "trailer": {
            "Record-Kind": status,
            "Prior-Status": prior or "UNKNOWN",
            "Compacted-By": (me or "")[:12],
            "Compacted-At": stamp,
            "Boxes": "%d attested, %d open, %d abandoned"
            % (d["n_attested"], d["n_open"], d["n_abandoned"]),
            "Epics": ", ".join(d["epics"]) or "none",
            "Touched": ", ".join(d["touched"]) or "none",
            "Gates": ", ".join(d["gates"]) or "none",
            "Why-Source": why_source,
            "Read-History": READ_HISTORY % (d["blob"], d["blob"]),
        },
    }
    if not d["commit"]:
        notes.append(
            "no landed commit carries this text yet, so `Full-Text:` is omitted and the "
            "BLOB is the whole pointer. That is legal; the gate's --update fills the "
            "commit in once the text is on origin/main."
        )
    if d["n_abandoned"]:
        notes.append(
            "%d ticked box(es) have no ledger commit attesting them and are recorded as "
            "`done=abandoned`. If that is wrong, run `npm run check:ci-plan-boxes -- "
            "--update`, commit the ledger, and compact again." % d["n_abandoned"]
        )
    # APPEND, NEVER ASSIGN. Rule 4 of this module's own contract says `## History` IS APPEND-ONLY, and until 2026-09-07 this line was a bare assignment, so the WRITER broke the convention the READER documents: a revive-then-re-compact replaced the single bullet instead of adding one, and every earlier bullet survived only in git. Found by the W12 P3.5 advisory census, whose C9
    # candidate rule flags exactly this shape -- on its first run it named three records whose history had been rewritten rather than extended.
    #
    # The carry-forward needs no blob read: a revived record's `## History` is still in `text`, and parse() already extracts it. When `text` is a plain plan (the ordinary first compaction) the parse yields nothing and the result is byte-identical to the old behaviour. parse() returns None for a source that is not already a record, which is the ORDINARY case (a plain plan being
    # compacted for the first time). Branch on it explicitly rather than letting the normal path fall through an exception handler: an except arm that fires on every healthy call is not a guard, it is control flow wearing a guard's clothes, and it hides the abnormal case it was written for.
    parsed = parse(text)
    carried = [ln for ln in ((parsed or {}).get("history") or []) if ln.strip().startswith("-")]
    rec["history"] = [
        *carried,
        "- %s compacted by %s from `%s` (record-sig %s)"
        % (stamp, (me or "?")[:8], prior or "UNKNOWN", record_sig(rec)),
    ]
    out = render(rec)
    _assert_boxes_preserved(text, out, rel)
    budget = size_budget(len(d["boxes"]))
    # HALVE UNTIL IT FITS, bounded, and RE-CHECK. The first cut halved once with an `if` and returned whatever came out, so a record that was still over budget after one halving shipped over budget and the gate red it forever. Six halvings take any prose this module can hold (3 x 1200 chars) under 200, which is the floor each section keeps.
    for _ in range(6):
        if len(out.encode("utf-8")) <= budget:
            break
        for k in PROSE_SECTIONS:
            prose[k] = clip(prose[k], max(200, len(prose[k]) // 2))
        rec["sections"] = prose
        out = render(rec)
        _assert_boxes_preserved(text, out, rel)
        if "truncated" not in " ".join(notes):
            notes.append(
                "the prose was truncated to fit the %d-byte budget (%d KB + %d B per box)"
                % (budget, RECORD_MAX_BYTES // 1024, RECORD_PER_BOX_BYTES)
            )
    if len(out.encode("utf-8")) > budget:
        raise RecordError(
            "the record for %s is %d bytes and will not fit its %d-byte budget even with "
            "the prose truncated. Shorten the `## Record` trailer inputs (Touched, Gates, "
            "Epics) or compact fewer boxes at once." % (rel, len(out.encode("utf-8")), budget)
        )
    # THE ANTI-VACUITY FLOOR, CHECKED HERE AND NOT ONLY IN CI. Module docstring property 5 says size is bounded in BOTH directions, and until this existed only the ceiling was enforced at write time. Measured 2026-09-06: a 129-byte plan compacted, with no refusal and no note, into an 823-byte record -- 6.4x BIGGER -- whose only exit was `--plan-revive`, and check:ci-plan-record
    # then red the tree until someone found that exit. The smallest real plan here is 3,357 bytes (ratio 4.19), so this refuses a case that does not occur today and cannot be reached by accident tomorrow.
    blob_size = len((text or "").encode("utf-8"))
    rec_size = len(out.encode("utf-8"))
    if blob_size < rec_size * BLOB_RATIO:
        raise RecordError(
            "compacting %s would produce a %d-byte record pointing at a %d-byte blob, a "
            "ratio of %.2f against a floor of %.1f -- nothing would be compacted, and "
            "check:ci-plan-record reds on exactly this. A plan this small is not worth "
            "compacting; leave it, or work on it to reset the clock."
            % (rel, rec_size, blob_size, (blob_size / rec_size if rec_size else 0), BLOB_RATIO)
        )
    if d.get("dropped"):
        notes.append(
            "%d checkbox line(s) are NOT in the record because wl_planfid.plan_tasks does "
            "not resolve them as tasks (too short after normalisation, or a duplicate of "
            "another box): %s. They are invisible to the box ledger too, so nothing else "
            "in this repo tracks them either." % (len(d["dropped"]), "; ".join(d["dropped"][:3]))
        )
    return out, notes


def _assert_boxes_preserved(plan_text, record_text, rel):
    """The one invariant compaction cannot be allowed to break.

    `wl_planfid.plan_tasks` must resolve EXACTLY the same open and done tasks
    from the record as it did from the plan. This is not belt-and-braces: it is
    the precondition of `check_plan_boxes.py`'s A1, which asserts that no box open at the merge-base is gone at HEAD, and which cannot tell "compacted"
    from "quietly deleted". A record that loses a box, gains one from prose it
    lifted, or re-words one so its signature moves is indistinguishable to that gate from the exact abuse it exists to catch.

    Checked here, at the moment of construction, rather than only in the CI gate, because CI is a round trip and the plan's text is still in memory right now. Raising is correct: `compact` has produced nothing yet and the caller writes nothing, so a refusal costs a message and never a file.
    """
    before_open, before_done = PF.plan_boxes(plan_text)
    after_open, after_done = PF.plan_boxes(record_text)
    if before_open == after_open and before_done == after_done:
        return
    lost_o = [t for t in before_open if t not in after_open]
    lost_d = [t for t in before_done if t not in after_done]
    gained = [t for t in after_open + after_done if t not in before_open + before_done]
    raise RecordError(
        "REFUSED: the record for %s does not parse to the same boxes as the plan. "
        "check_plan_boxes.py's A1 cannot tell that apart from a box being deleted, so "
        "this would red the tree. lost-open=%r lost-done=%r gained=%r"
        % (rel, lost_o[:3], lost_d[:3], gained[:3])
    )


CANDIDATES_HEADER = "plan record candidates (oldest first), %d plan(s), %d already record(s):"
RECORDS_HEADER = "plan records on disk, %d of %d plan(s):"


def dirty_paths(root, under="agent"):
    """The set of paths under `under` that git reports as changed.

    ONE `git status --porcelain` for the whole directory, not one per plan. `is_dirty` is the right shape for the single-plan path it guards; asking it 81 times to build a listing is 81 git processes to answer a question one call already answers.

    `_git_raw`, NEVER `_git_out`, AND THE DIFFERENCE WAS A LIVE DEFECT. Porcelain format is two status characters then a space then the path, and for an unstaged modification the FIRST character is a space. `wl_core._git` ends in `.strip()`, which eats it -- so the first line of output loses one character and `ln[3:]` returns a truncated path. Measured 2026-09-06 in a fixture:

        git status --porcelain  ->  ' M run.sh'
        through _git_out        ->  'M run.sh'
        ln[3:]                  ->  'un.sh'

    The consequence was quiet and pointed the wrong way: `candidates()` compares plan paths against this set to print "REFUSED: uncommitted changes", so a dirty plan on the first line of `git status` was listed as **ready**. The write path was never at risk -- `compact` calls `is_dirty`, which tests one path and only for truthiness -- but the LISTING is what the 33-plan wave is
    driven from, and it was telling the driver the opposite of the truth about one plan per run. The same `.strip()` trap `_git_raw` was added for.

    A RENAME reports `R old -> new`, and it is the NEW path that is dirty.
    """
    out = set()
    for ln in (_git_raw(root, "status", "--porcelain", "--", under) or "").splitlines():
        if len(ln) <= 3:
            continue
        rel = ln[3:]
        if " -> " in rel:
            rel = rel.split(" -> ", 1)[1]
        out.add(rel.strip().strip('"'))
    return out


def candidates(root, plan_records):
    """[(rel, status, n_open, n_done, verdict)] for every plan that is not a record.

    THE LISTING THE 33-PLAN WAVE NEEDS. `--plan-compact <me>` with no path answers "what can I compact right now, and what would each one refuse", so the wave is a read before it is a write. It also gives the CLI a `<me>`-taking mode whose effect is a printed line rather than a file, which is what lets the identity suite drive both verbs without planting a git repository per verb.

    Oldest content first, by mtime, because the housekeeping clock is what makes this list urgent and the oldest plan is the one about to go red.
    """
    root = pathlib.Path(root)
    dirty = dirty_paths(root)
    rows = []
    for rel, status, _n in plan_records:
        if status in RECORD_STATES:
            continue
        p = root / rel
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            mtime = p.stat().st_mtime
        except OSError:
            continue
        open_t, done_t = PF.plan_boxes(text)
        if rel in dirty:
            verdict = "REFUSED: uncommitted changes"
        elif open_t:
            verdict = "needs --park (%d open box(es))" % len(open_t)
        else:
            verdict = "ready"
        rows.append((rel, status, len(open_t), len(done_t), verdict, mtime))
    rows.sort(key=lambda r: r[5])
    return [r[:5] for r in rows]


def records(root, plan_records):
    """[(rel, status, blob, resolves)] for every plan that IS a record."""
    root = pathlib.Path(root)
    rows = []
    for rel, status, _n in plan_records:
        if status not in RECORD_STATES:
            continue
        try:
            rec = parse((root / rel).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if rec is None:
            continue
        rows.append((rel, status, rec["blob"], resolve(root, "blob", rec["blob"])[0]))
    return sorted(rows)


# --------------------------------------------------------------------------- P2.5 --plan-tick: flip the box and update the ledger in ONE run.
#
# WHY ONE RUN. A session that ticks a box in `agent/PLAN-x.md` with the Edit tool has done HALF of a two-part change: `.ci/config/plan-boxes.json` is a committed SECOND READING of the same boxes, and check:ci-plan-boxes's A0 compares the two
# for equality. So the tick alone is a red tree, the remedy is a regenerate the
# session has no reason to remember, and the failure arrives in CI a round trip later. Doing both writes from one verb removes the gap entirely.
#
# WHY IT REFUSES A COMPACTED OR PARKED RECORD, and this is a real constraint rather than a scoping decision, so it is stated where the refusal is:
#
#     A record's box carries `    (record) sig=.. done=..`, and
# check_plan_record.py's R4 accepts exactly two shapes for a TICKED box --
#     `done=<commit>` whose ledger AT THAT COMMIT attests the signature, or
#     `done=abandoned` which the CURRENT ledger must NOT attest.
#
# Ticking in place can satisfy neither. Writing the ledger makes `abandoned` a provable lie (R4's second direction fires immediately); not writing it makes
# A0 red instead. And `done=<commit>` cannot name the commit that will carry the
# tick, because that commit does not exist while the file is being written, and nothing here commits. The state is genuinely unrepresentable, so the verb says so and hands over the sequence that IS representable: revive, tick the plan, commit, compact again. That is the same sequence block-compacted-plan-edit.sh prints, which is not a coincidence -- both are the same constraint
# seen from two sides.

#: How the evidence is spelled into the plan. Four spaces and no bullet, so
#: `wl_planfid.BULLET_RE` (indent 0-3, marker required) cannot see it and the
#: box's own signature -- which is `_norm(body)[:120]` of the BOX LINE and
#: nothing else -- does not move. A moved signature is exactly what
#: check_plan_boxes.py's A1 reports as a box that VANISHED.
TICK_EVIDENCE = "    (ticked) %s by %s: %s"

#: Evidence is capped so a paste cannot push a plan past its own budget, and
#: floored so "done" is not accepted as evidence. The floor is the same shape the
#: worklist's own `--tick` uses: a claim with no pointer is not evidence.
TICK_EVIDENCE_MIN = int(os.environ.get("WORKLIST_TICK_EVIDENCE_MIN", "12"))
TICK_EVIDENCE_MAX = int(os.environ.get("WORKLIST_TICK_EVIDENCE_MAX", "300"))


def open_boxes(text):
    """[(line_index, line, body, sig)] for every OPEN box the real parser resolves.

    The line index is what makes the flip surgical: the replacement rewrites one line at one offset and leaves every other byte of the plan alone, so a plan that happens to contain the same sentence twice cannot have the wrong copy edited.
    """
    open_t, _done = PF.plan_boxes(text)
    out = []
    for i, raw in enumerate(text.splitlines()):
        m = BOX_LINE_RE.match(raw)
        if not m or m.group(1).lower() == "x":
            continue
        body = re.sub(r"[*_`]+", "", m.group(2)).strip()
        if body[:300] not in open_t:
            continue
        out.append((i, raw, body, box_sig(body)))
    return out


def done_boxes(text):
    """[(line_index, line, body, sig)] for every DONE box the real parser resolves.

    `open_boxes`'s mirror image, and it exists for exactly one caller: `plan_backfill_investigation`, whose whole subject is a box that is ALREADY `[x]`. Written as a separate function rather than as a flag on `open_boxes`, because a flag would let a mistyped argument hand the tick verbs a done box, and the two verbs must never be able to reach each other's set.
    """
    _open_t, done_t = PF.plan_boxes(text)
    out = []
    for i, raw in enumerate(text.splitlines()):
        m = BOX_LINE_RE.match(raw)
        if not m or m.group(1).lower() != "x":
            continue
        body = re.sub(r"[*_`]+", "", m.group(2)).strip()
        if body[:300] not in done_t:
            continue
        out.append((i, raw, body, box_sig(body)))
    return out


def select_box(boxes, selector, kind="OPEN"):
    """The ONE box `selector` names. Raises RecordError on none and on several.

    Two spellings, and both are needed. A signature is what the ledger and the record speak, so it is what a machine will pass; a substring is what a person has in front of them. AMBIGUITY IS A REFUSAL rather than a first-match, because the whole point of the verb is that it edits a file nobody is watching -- picking one of two candidates silently is how the wrong box gets ticked
    and the evidence lands under it.

    `kind` NAMES THE SET IN THE REFUSAL and changes nothing else. It defaults to `OPEN` so every existing caller's message is byte-identical; `plan_backfill_investigation` passes `DONE`, because a refusal that offered "the open boxes are:" while listing ticked ones would send the reader looking for a box that is not in the list.
    """
    sel = (selector or "").strip()
    if not sel:
        raise RecordError("pass a box to tick: an 8-hex signature, or text from the box line")
    low = sel.lower()
    hits = []
    if re.fullmatch(r"[0-9a-f]{4,8}", low):
        hits = [b for b in boxes if b[3].startswith(low)]
    if not hits:
        hits = [b for b in boxes if low in b[2].lower()]
    if not hits:
        raise RecordError(
            "no %s box matches %r. The %s boxes are:\n%s"
            % (
                kind,
                sel,
                kind.lower(),
                "\n".join("  %s  %s" % (b[3], b[2][:80]) for b in boxes) or "  (none)",
            )
        )
    if len(hits) > 1:
        raise RecordError(
            "%r matches %d %s boxes, and picking one silently is how the wrong box gets "
            "ticked. Pass a signature instead:\n%s"
            % (
                sel,
                len(hits),
                kind.lower(),
                "\n".join("  %s  %s" % (b[3], b[2][:80]) for b in hits),
            )
        )
    return hits[0]


def ledger_row(root, rel, text, moved_at=""):
    """The ledger entry for one plan, computed the way `check_plan_boxes.scan` computes it and not one field differently.

    RESTATED RATHER THAN IMPORTED, for the reason `box_sig` is: the import already runs the other way (the gate imports this directory), and importing back would make the two directories mutually dependent. The equality is pinned by a control in test-planrec.py, which is what keeps the restatement
    from drifting into a second opinion.
    """
    import wl_checks as CK  # noqa: PLC0415 -- see resolve()

    status = ""
    for r, st, _n in CK.plan_records(root):
        if r == rel:
            status = st
            break
    open_t, done_t = PF.plan_boxes(text)
    # `folder` and `moved_at` joined the row on 2026-09-21 with check:ci-plan-folders. `folder` is DERIVED from the path, so it is computed here exactly as the gate computes it. `moved_at` is CARRIED: it records when a closed plan was moved into a terminal folder, nothing in the tree can be read back out of it once a later commit touches the new path, and recomputing it would reset
    # the 40-day retention clock on every surgical write. The previous value is passed in by the caller that has the committed ledger; absent, it is "" and the plan has not moved.
    return {
        "status": status,
        "owner": CK.plan_owner(root, rel) or "unowned",
        "folder": plan_folder(rel),
        "moved_at": moved_at or "",
        "open": len(open_t),
        "done": len(done_t),
        "open_sigs": sorted({box_sig(t) for t in open_t}),
        "done_sigs": sorted({box_sig(t) for t in done_t}),
    }


def merge_ledger(doc, rel, row):
    """The ledger document with ONE plan's row replaced, keys re-sorted.

    Re-sorted because `--update` writes `{k: scanned[k] for k in sorted(scanned)}`
    and the two outputs have to be byte-identical: a surgical write that produced a differently-ordered file would show up as a whole-file diff, and the next session would "fix" it by regenerating, which is the churn this verb exists to remove.
    """
    out = dict(doc if isinstance(doc, dict) else {})
    plans = dict(out.get("plans") or {})
    plans[rel] = row
    out["plans"] = {k: plans[k] for k in sorted(plans)}
    return out


TICKABLE_HEADER = "open boxes that --plan-tick can flip in place (records are excluded):"


def tickable(root, plan_records):
    """[(rel, [box, ...])] for every LIVE plan that still has an open box.

    Records are excluded rather than listed-and-refused, because a listing whose rows mostly cannot be acted on trains the reader to skim it. The refusal in `plan_tick` explains the record case where it is actually reached.
    """
    root = pathlib.Path(root)
    out = []
    for rel, status, _n in plan_records:
        if status in RECORD_STATES:
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        boxes = open_boxes(text)
        if boxes:
            out.append((rel, boxes))
    return sorted(out)


# --------------------------------------------------------------------------- THE INVESTIGATION RECORD (agent/plans/PLAN-plan-implementation-enforcement.md Part 3).
#
# WHAT THIS IS FOR, in the operator's own framing: "we must investigate if they're implemented before implement". CLAUDE.md's "Search first" paragraph already says several campaign boxes closed by finding the work already landed and only the record was stale -- and nothing anywhere in this tree made that question askable, let alone answerable later. This is the mechanism.
#
# ONLY A RE-DERIVATION MAY BLOCK, and that line is inherited rather than chosen here. wl_claimcheck measured both available SEMANTIC tests over 342 real closing-tick notes and found both unusable as blockers: lexical overlap falsely accuses 12.4% of genuine claims, and "the cited sha touches a file the claim names" disagrees with 36% of the ticks carrying both. So nothing below
# scores, rates or judges anything. Every refusal here is a fact a `git` call or a filesystem read produced, and `resolve` above is the only vocabulary it speaks -- no second parser, no fuzzy matcher, no threshold.

INVESTIGATION_REL = ("agent", "ledgers", "plan-investigation.jsonl")

#: The three answers an investigation can reach, and the vocabulary is load-bearing.
#:
#:   absent   the work is not in the tree. Implement it.
#:   present  the work is ALREADY DONE and only the record is stale. A complete,
#:            honourable answer that licenses an immediate --plan-tick, and the
#:            single feature that makes this verb worth a session's time rather
#:            than a tax: it turns "go and check whether this is already done"
#:            from unrewarded diligence into the cheapest way to close a box.
#:   partial  some of it exists; `note` says which part, and the box stays open.
INV_VERDICTS = ("absent", "present", "partial")

#: TWO POINTERS OF TWO DISTINCT KINDS. One pointer is a citation; two of different kinds is a triangulation, and the asymmetry is cheap -- a `fileline` plus a `commit` costs one file read and one `rev-parse`. Two of the SAME kind is refused because the cheapest way to satisfy a pointer count is to cite the same artifact twice.
INV_MIN_POINTERS = 2
INV_MIN_KINDS = 2
#: A note under this is not a note. TICK_EVIDENCE_MIN's 12 characters is the mistake being corrected, not copied: a note is what a LATER reader uses to decide whether to re-open the question, and twelve characters cannot carry that.
INV_NOTE_MIN = 40

#: PLAIN CONSTANTS, no env override, for the reason wl_claimcheck.py:370-372 states: every `WORKLIST_*` name in this tree must be declared in the registry `check:ci-worklist-env-registry` enforces, and adding a name here would red a gate in order to make an untunable rule tunable. Only the CLOCK's numbers live in config (.ci/config/plan-implementation.json), because those WILL
#: be retuned.

POINTER_RE = re.compile(r"^([a-z]+):(.+)$", re.DOTALL)


def investigation_path(root):
    return pathlib.Path(root, *INVESTIGATION_REL)


def _investigation_lock(path):
    """The flock sidecar, in TMPDIR rather than beside the ledger.

    Verbatim the reasoning wl_claimcheck._census_lock records: every other sidecar in this repo sits next to its file and needed a `.gitignore` line to stay out of `git status`, and a fourth untracked `.lock` beside a tracked file is a defect the clean-tree gates would report. The lock arbitrates only between Stop hooks and CLI invocations on ONE machine writing ONE checkout,
    which is exactly the scope a per-machine tmp path serves.
    """
    base = os.path.join(os.environ.get("TMPDIR", "/tmp"), "claude-worklist", ".judge")
    os.makedirs(base, exist_ok=True)
    key = hashlib.sha1(str(path).encode("utf-8", "replace")).hexdigest()[:12]
    return os.path.join(base, "plan-investigation-%s.lock" % key)


def append_investigation(root, row):
    """Append ONE investigation row. Returns the row as written.

    APPEND-ONLY, through the store's own locked append, the same discipline the two ledgers already under agent/ledgers/ use. Never commits -- the same contract every verb in worklist.py keeps, and it matters here for the reason --plan-tick's own success message already says: a tick writes TWO files, and with this the set is THREE, all of which must land in one commit or
    check:ci-plan-boxes reads the ledger's staleness as a box that vanished.
    """
    path = investigation_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(row)
    rec.setdefault("at", C.stamp_now())
    S._append_lines(str(path), _investigation_lock(path), [rec])
    return rec


def read_investigations(root):
    """[row] from the ledger, oldest first. [] when it does not exist.

    NEVER RAISES on a malformed line: the ledger is append-only and two writers under one flock cannot tear a line, but a hand-edit could, and one bad line must not make every row after it invisible. A skipped line is a row that cannot testify, which fails CLOSED here -- the tick it would have licensed is refused for want of a row rather than allowed for want of a reader.
    """
    path = investigation_path(root)
    out: list[Any] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def investigation_for(root, rel, sig, rows=None):
    """The LATEST row about this box, or None.

    LATEST, not first, and the choice closes a cheat rather than expressing a preference. A session that investigated honestly, implemented, and then wrote a SECOND row to dodge Clause 2 would find the second row's `head` is at or past the implementation commit -- so Clause 1 refuses it. Taking the first row instead would let a later row be written and ignored, which is the same
    as not writing it.
    """
    rows = read_investigations(root) if rows is None else rows
    hits = [r for r in rows if r.get("plan") == rel and r.get("sig") == sig]
    return hits[-1] if hits else None


def parse_pointers(tokens):
    """[(kind, token)] from `kind:token` strings. Raises RecordError on a bad shape.

    EXPORTED so the selftest drives it without shelling out, and deliberately dumb: ordinary shell quoting is the interface and no new parser is introduced. The kind must be one of `resolve`'s eight, because `resolve` is the only oracle in this design and a ninth kind would be a pointer nothing can check.
    """
    out = []
    for raw in tokens or []:
        tok = str(raw or "").strip()
        if not tok:
            continue
        m = POINTER_RE.match(tok)
        if not m:
            raise RecordError(
                "pointer %r is not `<kind>:<token>`. The kinds are: %s"
                % (tok, ", ".join(RESOLVE_KINDS))
            )
        kind, value = m.group(1), m.group(2).strip()
        if kind not in RESOLVE_KINDS:
            raise RecordError(
                "pointer %r names kind %r, which nothing here can resolve. The kinds are: %s"
                % (tok, kind, ", ".join(RESOLVE_KINDS))
            )
        if not value:
            raise RecordError("pointer %r carries an empty token" % tok)
        out.append((kind, value))
    return out


def resolve_pointers(root, pointers):
    """[(kind, ok, detail)] -- every pointer put to `resolve`, none of them trusted.

    A `gate:` pointer is held to a SECOND bar: the key must also be reachable from `npm run ci`. `resolve`'s own `gate` kind only asks whether the key exists in package.json, and TRAPS.md's `check-cannot-fail` plus check-gate-reachability.ts both exist because a gate that is defined and never run is the shape this repo keeps paying for. Citing one as proof of implementation would
    be citing a check nobody runs.
    """
    out = []
    for kind, token in pointers:
        try:
            ok, detail = resolve(root, kind, token)
        except ValueError as exc:  # an unknown kind, already refused by parse_pointers
            ok, detail = False, str(exc)
        if ok and kind == "gate":
            try:
                import wl_reggate as RG  # noqa: PLC0415 -- see resolve()

                if not RG.gate_reachable(_package_scripts(root), token, root):
                    ok = False
                    detail = (
                        "%s is a key in package.json but is NOT reachable from `npm run ci`, "
                        "so it is a gate nothing runs" % token
                    )
            except ImportError:
                ok = False
                detail = "cannot import wl_reggate to check `npm run ci` reachability"
        out.append((kind, ok, detail))
    return out


def render_resolution(resolved):
    """The resolution table, printed by --dry-run and quoted in every refusal."""
    return "\n".join(
        "    %-9s %-4s %s" % (kind, "OK" if ok else "FAIL", detail) for kind, ok, detail in resolved
    )


def vet_pointers_and_note(root, pointer_tokens, note):
    """(pointers, resolved, note) once every bar an investigation row must clear is cleared.

    EXTRACTED RATHER THAN COPIED, on the day a second writer of these rows arrived. `plan_investigate` and `plan_backfill_investigation` must hold a row to the SAME four bars -- the pointer count, the distinct-kind count, live re-resolution of every pointer, and the note floor -- and two copies of that block would be two opinions about what a row has to carry. A backfill whose
    bars had quietly drifted below the live verb's is exactly the shape that makes a retroactive record worth less than the one it imitates.
    """
    pointers = parse_pointers(pointer_tokens)
    if len(pointers) < INV_MIN_POINTERS:
        raise RecordError(
            "%d pointer(s); at least %d are required. One pointer is a citation, two of "
            "different kinds is a triangulation. Kinds: %s"
            % (len(pointers), INV_MIN_POINTERS, ", ".join(RESOLVE_KINDS))
        )
    kinds = {k for k, _t in pointers}
    if len(kinds) < INV_MIN_KINDS:
        raise RecordError(
            "all %d pointer(s) are of kind %r; at least %d DISTINCT kinds are required. Citing "
            "the same artifact twice is the cheapest way to satisfy a count, which is why the "
            "count alone is not the rule." % (len(pointers), min(kinds), INV_MIN_KINDS)
        )
    resolved = resolve_pointers(root, pointers)
    dead = [(k, d) for k, ok, d in resolved if not ok]
    if dead:
        raise RecordError(
            "%d of %d pointer(s) do not resolve, so this row would assert something nothing "
            "can check:\n%s\n\nThe whole row is refused rather than the dead pointers dropped: "
            "a record that silently kept its good half would read, later, exactly like one "
            "that was right all along." % (len(dead), len(resolved), render_resolution(resolved))
        )
    n = (note or "").strip()
    if len(n) < INV_NOTE_MIN:
        raise RecordError(
            "the note is %d character(s); at least %d are required. The note is what a LATER "
            "reader uses to decide whether to re-open this question, and `--plan-tick`'s own "
            "%d-character floor is the mistake being corrected here, not copied. Say what was "
            "looked at and what was found." % (len(n), INV_NOTE_MIN, TICK_EVIDENCE_MIN)
        )
    return pointers, resolved, n


def plan_investigate(root, rel, selector, verdict, pointer_tokens, note, me, now=None):
    """(row, resolved) for one investigation. Raises RecordError. WRITES NOTHING.

    Every step is a re-derivation and none of it is trust:

      1. the plan exists and `selector` names exactly ONE open box, through the
         same `open_boxes`/`select_box` pair --plan-tick uses. Ambiguity is a
         refusal rather than a first-match, for the reason select_box states.
      2. `verdict` is one of three.
      3. EVERY pointer resolves NOW, by this process's own git and filesystem
         calls, and the whole row is refused if any one fails, naming which.
      4. at least INV_MIN_POINTERS pointers of at least INV_MIN_KINDS kinds.
      5. the note clears INV_NOTE_MIN characters.

    `head` is `git rev-parse HEAD` at write time, and it is what makes the record an ASSERTION ABOUT A TREE rather than a story: Clause 1 in plan_tick requires the tick's own cited commit to descend from it, which an investigation written after the implementation cannot satisfy.
    """
    root = pathlib.Path(root)
    p = root / rel
    if not p.is_file():
        raise RecordError("%s does not exist" % rel)
    v = str(verdict or "").strip().lower()
    if v not in INV_VERDICTS:
        raise RecordError(
            "verdict %r is not one of %s. There is deliberately no fourth verdict: a box is "
            "not closable by investigating it and declaring it hard, which would make this "
            "whole gate optional in one command. The door for a box that cannot be worked now "
            "is `worklist.py --add` or `worklist.py --defer`, both of which keep it VISIBLE."
            % (verdict, ", ".join(INV_VERDICTS))
        )
    text = p.read_text(encoding="utf-8", errors="replace")
    if is_record(text):
        raise RecordError("%s is a COMPACTED RECORD; its boxes are history, not work" % rel)
    boxes = open_boxes(text)
    if not boxes:
        raise RecordError("%s has no open boxes to investigate" % rel)
    _i, _line, body, sig = select_box(boxes, selector)

    pointers, resolved, n = vet_pointers_and_note(root, pointer_tokens, note)

    head = _git_out(root, "rev-parse", "HEAD") or ""
    row = {
        "at": now or C.stamp_now(),
        "by": (me or "?")[:8],
        "plan": rel,
        "sig": sig,
        "box": body[:200],
        "verdict": v,
        "head": head[:40],
        "br": C.git_branch(root) or "",
        "pointers": [[k, t] for k, t in pointers],
        "resolved": [[k, ok, d] for k, ok, d in resolved],
        "note": n[:600],
    }
    return row, resolved


# --------------------------------------------------------------------------- CLAUSE 1 AND CLAUSE 2: what makes this "investigation BEFORE implementation" rather than a post-hoc story.


def _blob_lines_at(root, commit, rel):
    """How many lines `rel` had at `commit`, or None when it did not exist there.

    `git cat-file -e` first so a missing path is distinguishable from an empty one -- the same reason resolve() checks the object type rather than trusting a non-empty read.
    """
    if not commit or not rel:
        return None
    if not _git_ok(root, "cat-file", "-e", "%s:%s" % (commit, rel)):
        return None
    return len(_git_raw(root, "show", "%s:%s" % (commit, rel)).splitlines())


def clause1_ordering(root, row, evidence):
    """ "" when the ordering holds, else the refusal text. Clause 1 of Part 3.6.

    THE CITED COMMIT MUST DESCEND FROM THE INVESTIGATION'S OWN `head`. An investigation written AFTER the implementation commit cannot satisfy this, because the commit would not be a descendant of a head recorded later. The primitive is `git merge-base --is-ancestor`, the same one resolve()'s `ancestor` kind already uses.

    SILENT WHEN THE EVIDENCE NAMES NO COMMIT. Clause 1 is a statement about two commits and has nothing to say about a tick whose evidence is a file:line or a run id; Clause 2 is what covers that case, and inventing a demand for a sha here would make every honest non-commit tick refusable on a technicality.
    """
    head = str(row.get("head") or "").strip()
    if not head:
        return ""
    shas = []
    seen = set()
    for m in re.finditer(r"(?<![0-9a-zA-Z])([0-9a-f]{7,40})(?![0-9a-zA-Z])", evidence or ""):
        tok = m.group(1)
        if tok in seen:
            continue
        seen.add(tok)
        if _git_out(root, "rev-parse", "--verify", "--quiet", tok + "^{commit}"):
            shas.append(tok)
    if not shas:
        return ""
    if any(_git_ok(root, "merge-base", "--is-ancestor", head, s) for s in shas):
        return ""
    return (
        "CLAUSE 1 (ordering): the investigation row for this box recorded HEAD=%s, and none of "
        "the commit(s) this tick cites (%s) is a DESCENDANT of it. An investigation is only an "
        "investigation if it happened BEFORE the work: a row written after the implementation "
        "commit records a head the commit cannot descend from, which is exactly what this "
        "arithmetic sees. Investigate first, then implement, then tick."
        % (head[:12], ", ".join(s[:12] for s in shas))
    )


def clause2_falsifiable(root, row, evidence):
    """ "" when the negative claim survives, else the refusal text. Clause 2 of Part 3.6.

    A `verdict: "absent"` row is a FALSIFIABLE ASSERTION ABOUT THE TREE AT `row.head`: "this work is not there". So when the tick's own evidence cites a `file:line` that ALREADY RESOLVED at that head, the investigation claimed the absence of something the investigation itself could have found, and the tick is refused.

    THIS IS THE ONLY CLAUSE WHERE THE MECHANISM HOLDS AN OPINION THE SESSION DID NOT SUPPLY, and that is why it is the load-bearing one. Every other clause can be satisfied by finding any real pointer; this one compares two of the session's OWN claims against each other across a git revision, so a fabricated investigation contradicts the fabricated tick.
    """
    if str(row.get("verdict") or "").strip().lower() != "absent":
        return ""
    head = str(row.get("head") or "").strip()
    if not head:
        return ""
    import wl_checks as CK  # noqa: PLC0415 -- see resolve()

    for m in CK.CITE_RE.finditer(evidence or ""):
        cited_rel, line = m.group(1), int(m.group(2))
        n = _blob_lines_at(root, head, cited_rel)
        if n is None or line > n:
            continue
        return (
            "CLAUSE 2 (the negative claim is falsifiable): the investigation row for this box "
            "recorded verdict=absent at HEAD=%s -- an assertion that the work was NOT in the "
            "tree. This tick cites %s:%d, and that file already had %d line(s) at that same "
            "head, so the citation resolved there too. The investigation claimed the absence "
            "of something it could have found.\n\n"
            "Either the investigation was written to satisfy this verb rather than to answer "
            "the question, or the real verdict was `present` (the work was already done and "
            "only the record was stale) -- which is a complete, honourable answer and licenses "
            "an immediate tick. Re-run --plan-investigate with the verdict that is true."
            % (head[:12], cited_rel, line, n)
        )
    return ""


def plan_tick(root, rel, selector, evidence, me, now=None):
    """(new_plan_text, new_ledger_doc, note) for one tick. Raises RecordError.

    Writes NOTHING. The caller writes both files, so a refusal on the second cannot leave the first half-applied.
    """
    root = pathlib.Path(root)
    p = root / rel
    if not p.is_file():
        raise RecordError("%s does not exist" % rel)
    ev = (evidence or "").strip()
    if len(ev) < TICK_EVIDENCE_MIN:
        raise RecordError(
            "evidence is mandatory and must be at least %d characters. A tick with no "
            "evidence is a claim; the point of writing it into the plan is that the next "
            "reader can check it. Name the command, the file:line or the run id."
            % TICK_EVIDENCE_MIN
        )
    # THE TWO TICK VERBS HAD DRIFTED, and this closes it. `worklist.py --tick` has called wl_checks.completion_evidence since v5 and dies with CLI_TICK_NO_EVIDENCE; `--plan-tick` tested only the 12-CHARACTER FLOOR, so `--plan-tick <me> <plan> <sig> "done it, works"` was accepted. That was the widest hole in the tree, in the one verb a plan-implementation gate has to depend on.
    # Both floors apply now: the length floor catches a terse claim and completion_evidence demands something a reader can follow.
    import wl_checks as CK_EV  # noqa: PLC0415 -- see resolve()

    if not CK_EV.completion_evidence(root, ev):
        raise RecordError(
            "evidence is %d character(s) but carries nothing checkable. `worklist.py --tick` "
            "has demanded this since v5 and `--plan-tick` did not, which is how "
            '"done it, works" became an acceptable close on a plan box. Name a real sha, a '
            "run id, a file:line that RESOLVES, an exit code, or a URL." % len(ev)
        )
    text = p.read_text(encoding="utf-8", errors="replace")
    if is_record(text):
        raise RecordError(
            "%s is a COMPACTED RECORD, and a record's box cannot be ticked in place. Its "
            "`done=` must either name a commit whose ledger attests the tick -- which "
            "cannot exist yet -- or say `abandoned`, which the ledger would immediately "
            "disprove. Both are red. Do this instead:\n"
            "    worklist.py --plan-revive <me> %s --write\n"
            "    # tick it as an ordinary plan, then commit\n"
            "    worklist.py --plan-compact <me> %s --write" % (rel, rel, rel)
        )
    boxes = open_boxes(text)
    if not boxes:
        _o, done_t = PF.plan_boxes(text)
        raise RecordError("%s has no open boxes to tick (%d already ticked)." % (rel, len(done_t)))
    i, line, body, sig = select_box(boxes, selector)

    # ---- PROOF OF INVESTIGATION, and it is strictly FORWARD-ONLY.
    #
    # Measured corpus-wide before this was written: 13 `    (ticked) ` evidence lines across all four plan folders, all of them in ONE file, against 589 done boxes. `--plan-tick` has been used on about 2% of the boxes it was written for and the rest were flipped with the Edit tool carrying no evidence of any kind. There is nothing to re-check on them and never will be, so this
    # binds the NEXT tick and never a past one. Saying so here is what stops a later "strengthening" into a rule that reds 576 boxes it cannot possibly judge.
    inv_row = investigation_for(root, rel, sig)
    if inv_row is None:
        raise RecordError(
            "no investigation row for box %s of %s.\n\n"
            "CLAUDE.md's own rule is that several campaign boxes closed by finding the work "
            "ALREADY LANDED and only the record being stale -- not by doing it again. That "
            "sentence has been a norm a session could forget; it is now a step:\n\n"
            "    worklist.py --plan-investigate %s %s %s <absent|present|partial> \\\n"
            "        <kind>:<token> <kind>:<token> -- <what was looked at and what was found>\n"
            "    worklist.py --plan-investigate ... --write\n\n"
            "Two pointers of two distinct kinds, every one re-resolved by this process rather "
            "than trusted. Kinds: %s. A `present` verdict is a COMPLETE answer and licenses "
            "this tick immediately."
            % (sig, rel, (me or "<me>")[:8], rel, sig, ", ".join(RESOLVE_KINDS))
        )
    for clause in (clause1_ordering, clause2_falsifiable):
        problem = clause(root, inv_row, ev)
        if problem:
            raise RecordError(problem)

    lines = text.splitlines(keepends=True)
    eol = "\n" if lines[i].endswith("\n") else ""
    # ONE CHARACTER, at one offset. `line.replace("[ ]", "[x]", 1)` would also rewrite a `[ ]` that appears in the task TEXT of a box about checkboxes, and this repo has plans about checkboxes.
    cut = BOX_LINE_RE.match(line).start(1) - 1
    flipped = line[:cut] + "[x]" + line[cut + 3 :]
    stamp = now or C.stamp_now()
    lines[i] = flipped + eol
    note_line = TICK_EVIDENCE % (stamp, (me or "?")[:8], clip(ev, TICK_EVIDENCE_MAX))
    lines.insert(i + 1, note_line + "\n")
    out = "".join(lines)

    # THE INVARIANT, checked here and not only in CI, for the same reason `_assert_boxes_preserved` is: the plan's text is in memory right now and a refusal costs a message rather than a file. The task must MOVE from open to done and the union must be unchanged -- a tick that also re-worded the box, or that made the evidence line parse as a task, is indistinguishable to
    # check_plan_boxes.py's A1 from a box being deleted.
    before_o, before_d = PF.plan_boxes(text)
    after_o, after_d = PF.plan_boxes(out)
    if (
        sorted(before_o + before_d) != sorted(after_o + after_d)
        or body[:300] in after_o
        or body[:300] not in after_d
    ):
        raise RecordError(
            "REFUSED: ticking %r did not move exactly that one box. before open=%d done=%d, "
            "after open=%d done=%d. check_plan_boxes.py's A1 cannot tell this apart from a "
            "box being deleted, so it would red the tree."
            % (body[:60], len(before_o), len(before_d), len(after_o), len(after_d))
        )

    try:
        doc = json.loads((root / LEDGER_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RecordError(
            "cannot read %s (%s), so the second half of this change -- the committed "
            "reading of the same boxes -- cannot be written. Ticking the plan alone would "
            "red check:ci-plan-boxes." % (LEDGER_REL, exc)
        ) from exc
    # `moved_at` is CARRIED from the committed row. A surgical tick must not reset the retention clock of a plan that has already moved, which recomputing it would do.
    row = ledger_row(root, rel, out, ((doc.get("plans") or {}).get(rel) or {}).get("moved_at", ""))
    note = (
        "box %s moved from open_sigs to done_sigs in %s (%d open, %d done for this plan). "
        "BOTH files must land in the SAME commit." % (sig, LEDGER_REL, row["open"], row["done"])
    )
    return out, merge_ledger(doc, rel, row), note


# --------------------------------------------------------------------------- THE RETROACTIVE BACKFILL, and the one divergence it makes from `plan_investigate` is stated in the open rather than buried.
#
# WHY A SECOND WRITER OF INVESTIGATION ROWS EXISTS AT ALL. `plan_investigate` and `plan_tick` both reach their box through `open_boxes`, which returns only boxes whose mark is not `x`. A box that a sub-agent already flipped with the Edit tool is therefore unreachable by both verbs FOR EVER: the live pipeline structurally refuses to speak about a box that is already closed, which
# is correct for its own job -- investigate, then implement, then tick -- and leaves no way at all to repair a trail that was skipped. Measured on branch `0923-1`: 316 boxes across 31 plans were closed by real, verified work and carry no ledger row, and re-running the live verbs on any one of them refuses outright.
#
# THE DIVERGENCE, AND IT IS THE ONLY ONE. `plan_investigate` stamps `head` with `git rev-parse HEAD` at write time, which is what makes the row an assertion about a tree rather than a story: Clause 1 then demands that the tick's own commit DESCEND from that head, and an investigation written after the work cannot satisfy it. A backfill has no such head to offer honestly -- the
# work is already committed, and stamping the live HEAD would assert an ordering that never happened. So `head` here is `done_commit^`, the immediate parent of the commit that ticked the box. That is a real commit, it is unconditionally an ancestor of `done_commit`, and it is the LAST tree in which the question "is this box's work already present?" was still open. Nothing is
# invented and no ordering is claimed that the history does not already carry.
#
# WHAT IS DELIBERATELY NOT AVAILABLE HERE. There is no verdict argument: `present` is the only honest answer a backfill can give, because the box is closed and the work is in the tree by construction. There is no box-mark write: the mark is already `x` and this verb never touches it. And there is no way in: an open box is refused, so this never becomes a shortcut past a live
# investigation.

#: The single verdict a backfill may record. See the block above: a retroactive row about an already-closed box cannot honestly say `absent`, and `partial` would contradict the `[x]` it is describing.
BACKFILL_VERDICT = "present"


def plan_backfill_investigation(
    root, rel, selector, pointer_tokens, note, me, evidence=None, text=None, history=None, now=None
):
    """(row, resolved, new_text) for ONE already-ticked box. Raises RecordError. WRITES NOTHING.

    The caller writes both halves, the same contract `plan_tick` keeps and for the same reason: a refusal on the second must not be able to leave the first half applied. The ledger half goes through `append_investigation` and nothing else, so there is exactly one piece of row-writing code in this module.

    `text` lets a caller CHAIN insertions through one plan file without re-reading it, which is what makes a batch over a plan's twenty boxes safe: each call recomputes line indices from the text it was handed, so an earlier insertion cannot shift a later one onto the wrong line.

    Every bar `plan_investigate` holds a row to is held here too, through the shared `vet_pointers_and_note`. Two extra refusals are specific to the retroactive case and both are LOUD rather than silent skips:

      * a box that is still OPEN -- it belongs to the live pipeline, which can
        still answer the question honestly, and a backfill row for it would be a
        pre-dated investigation nobody performed.
      * a box whose `done_commit` is "" -- the ledger walk found no commit that
        attests it, which is the `abandoned` vocabulary of this module. A trail
        must not be manufactured for a box no commit ever closed.
    """
    root = pathlib.Path(root)
    p = root / rel
    if not p.is_file():
        raise RecordError("%s does not exist" % rel)
    if text is None:
        text = p.read_text(encoding="utf-8", errors="replace")
    if is_record(text):
        raise RecordError("%s is a COMPACTED RECORD; its boxes are history, not work" % rel)

    # THE OPEN-BOX DOOR IS CHECKED FIRST and refuses before anything else is computed, so the refusal names the real problem rather than "no DONE box matches".
    opens = open_boxes(text)
    try:
        still_open = select_box(opens, selector)
    except RecordError:
        still_open = None
    if still_open is not None:
        raise RecordError(
            "box %s of %s is still OPEN, and a backfill may only describe a box that is already "
            "closed. Backfilling an open box would record an investigation nobody performed and "
            "would license the very tick it was invented to excuse. Use the live pipeline, which "
            "can still answer this honestly:\n"
            "    worklist.py --plan-investigate %s %s %s <absent|present|partial> "
            "<kind>:<token> <kind>:<token> -- <note> --write"
            % (still_open[3], rel, (me or "<me>")[:8], rel, still_open[3])
        )

    dones = done_boxes(text)
    if not dones:
        raise RecordError(
            "%s has no ticked boxes, so there is no closed box to backfill a record for" % rel
        )
    i, _line, body, sig = select_box(dones, selector, kind="DONE")

    # `done=` COMES FROM HISTORY, NEVER FROM A CLAIM -- the same ledger walk `derive` and the gate both use. The commit this finds is the first one whose committed `.ci/config/plan-boxes.json` attests the signature as done, which no working tree can rewrite.
    commit = done_commit(history if history is not None else ledger_history(root), rel, sig)
    if not commit:
        raise RecordError(
            "box %s of %s is ticked in the tree but NO commit's %s attests it as done, so the "
            "ledger walk reads it as abandoned. Refusing rather than skipping it quietly: a "
            "backfill exists to record what really happened, and there is no commit here to "
            "record. Either the tick has not been committed yet -- commit the plan and the box "
            "ledger together, then run this again -- or the box was flipped without the ledger "
            "and check:ci-plan-boxes owns that remedy." % (sig, rel, LEDGER_REL)
        )

    # `done_commit^`, NOT `git rev-parse HEAD`. The block above this function states why at length; the short version is that the parent is the last tree in which this box's question was genuinely open, and it is an ancestor of `done_commit` by construction rather than by assertion.
    head = _git_out(root, "rev-parse", "--verify", "--quiet", "%s^" % commit) or ""
    if not head:
        raise RecordError(
            "%s has no parent commit, so there is no tree in which box %s of %s was still open "
            "and no honest `head` to record. A root commit cannot carry a backfilled "
            "investigation." % (commit[:12], sig, rel)
        )
    # BELT AND BRACES, and cheap: P-A4 re-derives exactly this with `merge-base --is-ancestor`, so asserting it here means a refusal costs a message instead of a red gate.
    if not _git_ok(root, "merge-base", "--is-ancestor", head, commit):
        raise RecordError(
            "%s is not an ancestor of %s, which cannot happen for a parent and its child. "
            "Refusing rather than writing a row the gate would reject." % (head[:12], commit[:12])
        )

    pointers, resolved, n = vet_pointers_and_note(root, pointer_tokens, note)

    ev = (evidence if evidence is not None else n).strip()
    if len(ev) < TICK_EVIDENCE_MIN:
        raise RecordError(
            "the evidence line is %d character(s) and at least %d are required. A backfilled "
            "line is held to the SAME floor a live `--plan-tick` line is, because the next "
            "reader cannot tell the two apart and must not have to." % (len(ev), TICK_EVIDENCE_MIN)
        )
    import wl_checks as CK_EV  # noqa: PLC0415 -- see resolve()

    if not CK_EV.completion_evidence(root, ev):
        raise RecordError(
            "the evidence line carries nothing checkable. `--plan-tick` has demanded this since "
            "the two tick verbs were reconciled, and a retroactive line that fell short of it "
            "would be a weaker record wearing the same grammar. Name the real closing sha, a "
            "file:line that RESOLVES, a run id, an exit code, or a URL."
        )

    row = {
        "at": now or C.stamp_now(),
        "by": (me or "?")[:8],
        "plan": rel,
        "sig": sig,
        "box": body[:200],
        "verdict": BACKFILL_VERDICT,
        "head": head[:40],
        "br": C.git_branch(root) or "",
        "pointers": [[k, t] for k, t in pointers],
        "resolved": [[k, ok, d] for k, ok, d in resolved],
        "note": n[:600],
        # PROVENANCE, IN THE ROW ITSELF. A later reader must be able to tell a row written before the work from one reconstructed after it, and a field is the only place that fact survives. `head_is` spells out the derivation rather than naming it, so the divergence is legible without opening this file.
        "backfill": {"done_commit": commit[:40], "head_is": "done_commit^"},
    }

    # THE EVIDENCE LINE IS INSERTED ONLY IF ABSENT. 95 of the 316 boxes this was written for already carry a well-formed one citing real commits; overwriting those would replace a contemporaneous record with a reconstruction, which is strictly worse. Idempotent for the same reason: a second run over a plan must be a no-op on its text.
    lines = text.splitlines(keepends=True)
    already = i + 1 < len(lines) and TICK_LINE_RE.match(lines[i + 1])
    if already:
        out = text
    else:
        # A PLAN WHOSE LAST LINE HAS NO NEWLINE would otherwise have the evidence spliced onto the end of its own box line, which rewrites the box. Terminating it first is what keeps the insertion a whole line at a whole offset.
        if not lines[i].endswith("\n"):
            lines[i] = lines[i] + "\n"
        stamp = now or C.stamp_now()
        note_line = TICK_EVIDENCE % (stamp, (me or "?")[:8], clip(ev, TICK_EVIDENCE_MAX))
        lines.insert(i + 1, note_line + "\n")
        out = "".join(lines)

    # THE INVARIANT, the same one `plan_tick` checks at the same point and for the same reason. A backfill must move NOTHING: the box was done before and is done after, the open set is untouched, and the inserted line must stay invisible to `wl_planfid.BULLET_RE`. Anything else is indistinguishable to check_plan_boxes.py's A1 from a box being deleted, and the whole point of this
    # verb is that it can be run over 31 plans without perturbing a single signature.
    before_o, before_d = PF.plan_boxes(text)
    after_o, after_d = PF.plan_boxes(out)
    if sorted(before_o) != sorted(after_o) or sorted(before_d) != sorted(after_d):
        raise RecordError(
            "REFUSED: backfilling %r moved a box. before open=%d done=%d, after open=%d done=%d. "
            "check_plan_boxes.py's A1 cannot tell this apart from a box being deleted, so it "
            "would red the tree."
            % (body[:60], len(before_o), len(before_d), len(after_o), len(after_d))
        )
    return row, resolved, out


def revive(root, rel):
    """(full_text, note) -- the plan's own text back from the blob. Raises RecordError.

    The blob first, ALWAYS, and the commit only as a label. That ordering is the whole point of the design: `git cat-file blob <id>` answers in any clone that has the object, whatever happened to the commit that once carried it.
    """
    root = pathlib.Path(root)
    p = root / rel
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise RecordError("cannot read %s: %s" % (rel, exc)) from exc
    rec = parse(text)
    if rec is None:
        raise RecordError("%s is not a record (its Status is not compacted or parked)" % rel)
    if not rec["blob"]:
        raise RecordError(
            "%s carries no Full-Text-Blob, so there is nothing to restore from. Recover it "
            "by hand: `git log --all --oneline -- %s` and `git show <commit>:%s`." % (rel, rel, rel)
        )
    ok, why = resolve(root, "blob", rec["blob"])
    if not ok:
        raise RecordError(
            "%s points at blob %s, which this clone does not have (%s). Fetch the full "
            "history (`git fetch --unshallow --filter=blob:none`) and try again; the blob "
            "is content-addressed, so any clone that has it has the same bytes."
            % (rel, rec["blob"], why)
        )
    # _git_raw, NEVER _git_out. See _git_raw: stripping here would restore a file that no longer hashes to the blob it came from.
    body = _git_raw(root, "cat-file", "blob", rec["blob"])
    if not body:
        raise RecordError("blob %s read back empty; refusing to overwrite the record" % rec["blob"])
    return body, "restored %d byte(s) from blob %s" % (len(body), rec["blob"][:12])
