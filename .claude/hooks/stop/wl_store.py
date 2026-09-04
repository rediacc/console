"""wl_store: the v10 item store, sidecars, and session state.

STORAGE MODEL (v10). Items live in an append-only JSONL EVENT LOG at
<worklist>.events.jsonl, folded into state on read. The markdown file is an
INBOX, not the store: sessions with current instructions use the CLI verbs
(--add/--tick/--defer/--lease/--update), while anything written into the
markdown by hand or by a session with older instructions is folded in by a
whole-file DIFF SYNC. A line written to the old file and silently ignored
would be the lost-work failure this program exists to prevent, so the sync
is not a compatibility shim; it is the safety net for exactly that failure.

WHY a diff sync and not an append offset: the markdown is MUTATED in place
by its writers (ticking flips a state byte, evidence is edited into a line,
the dead-session cleaner pwrites `~`), so any importer keyed on byte offsets
corrupts on the first in-place edit. The sync parses the whole file, diffs
against the fold's view of the markdown, and appends small `md` events
(add/chg/del). Identity of a markdown line is sha1(owner|text) EXCLUDING the
state byte, so the common flow -- tick a line in place without changing its
text -- is a `chg` that keeps the item's first-seen stamp. An edited text is
del+add and honestly resets the clock: an edit IS an update.

WHY events and not a JSON document: a document is a whole-file rewrite by
nature, which is the lost-update hazard the old `>>` discipline existed to
avoid. One event = one write() on an O_APPEND fd under a blocking flock on
<events>.lock, the discipline proven by the .requests sidecar. Readers take
no lock; a torn tail line (crash mid-write) fails json.loads and is skipped.
NEW hardening over the .requests original: before appending, the writer
checks the file's last byte under the lock and heals a missing newline, so
a torn tail can never concatenate with the next event and corrupt both.

CRASH STORY, complete: append crash = torn tail, healed on next append,
skipped by every reader. Session-doc crash = tempfile + os.replace, old doc
survives. Compact crash = tempfile + os.replace, log intact. Sync crash
after fold, before append = nothing written, next invocation re-syncs.

The sidecars (.requests, .sessions, .loop, .reggate-*,
.pollbase-*, .pollmark-*, .cistate-*, .cimark-*, .ciqueue-*, .stuck-*,
.croncount-*, .blocks-*, .waiter-*, .waiternudge-*, .state-*, .events.*,
.lastevent-*, .reaped-*, .agentstate.*,
.epics, .resprofile.*)
keep their v5-v9 formats and names: their shapes
are pinned by the suite and by living sessions, and consolidating them buys
nothing. New v10 state (liveness ladder, task ages, judge cache, autonomy
windows, STATE.md world-signature) lives in ONE new per-session doc,
<worklist>.state-<prefix>.json.

THIS LIST IS LOAD-BEARING, not documentation. .ci/scripts/quality/
check-tracked-sidecars.sh parses it to decide what git must never track, so a
sidecar missing from it is a sidecar the gate is blind to. That already
happened: .waiter-* and .state-* were absent when the gate was written, so a
planted tracked heartbeat passed cleanly. It happened AGAIN and was found
while adding .agentstate.*: ELEVEN suffixes this module and its siblings
actually write (.events.*, .lastevent-*, .ciqueue-*, .waiternudge-*,
.reaped-*, .agentstate.* among them) were absent, so the
list was checked against the code rather than against memory --
grepping the hook directory for with_suffix call sites enumerates the truth.
Add new sidecars HERE when you add them, and keep the parenthesised shape the
parser depends on (no nested parentheses: the parser stops at the first `)`).
The compact-recovery document itself lives in the repo at
agent/<session>/STATE.md (tracked), not in TMPDIR.
"""

try:
    import fcntl
except ImportError:  # Windows: no POSIX advisory locking
    fcntl = None
import calendar
import contextlib
import glob as _glob
import hashlib
import json
import os
import pathlib
import re
import socket
import tempfile
import time

import wl_core as C

# Kept as module constants so the lock sites read the same with or without the
# module present. The values are POSIX's and are only ever passed to _flock.
LOCK_EX = getattr(fcntl, "LOCK_EX", 2)
LOCK_NB = getattr(fcntl, "LOCK_NB", 4)


def _flock(handle, flags):
    """flock, or a NAMED refusal on a platform that has none.

    WHY A SHIM RATHER THAN A BARE MODULE-SCOPE IMPORT. `import fcntl` at the top
    of this file means the module does not DEGRADE on Windows, it DIES at
    import -- and it takes every read-only path down with it, including the
    report inbox and the waiter, which import this module purely to reuse its
    fold and take no lock at all. The read paths never needed fcntl; only the
    writes do. So the import is guarded, reads keep working everywhere, and a
    write on a platform without locking fails with a sentence naming the reason
    instead of an ImportError raised from a file nobody was looking at.

    This does NOT make the hook Windows-complete: `_append_lines` still uses
    os.pwrite, and ~20 sibling hooks are bash. It makes the read-only surfaces
    usable there, which is what the new inbox needs.
    """
    if fcntl is None:
        raise RuntimeError(
            "worklist WRITES need file locking, which this platform does not "
            "provide (fcntl is POSIX-only). Read-only paths still work."
        )
    fcntl.flock(handle, flags)


SESSION_BRIEF_MAX = 200
SESSION_BRIEF_STALE_MIN = int(os.environ.get("WORKLIST_BRIEF_STALE_MIN", "90"))

# The compact-recovery document is `agent/<session>/STATE.md` (operator
# redesign, 2026-07-30, replacing the single per-session handover). The split
# is BY LIFETIME: STATE.md is rewritten and freshness-gated; RULES.md is
# sharpened and never age-gated; TRAPS.md is shared, append-only, and feeds the
# judge headings. Only STATE.md can go stale by the clock, so only it has
# constants here.
#
# FIFTEEN MINUTES, unchanged from the handover it replaces. Since v10 the
# clock only matters when the WORLD has moved: the document is stale when it
# is old AND the world signature has changed since it was written. The pure-age
# rule was outpaced by the 5-minute poll cron (a quiet session went stale every
# other poll and could never take the silent path); staleness is about the
# document no longer matching reality, and an unchanged world cannot
# invalidate it.
AGENT_STATE_STALE_MIN = int(os.environ.get("WORKLIST_AGENT_STATE_STALE_MIN", "15"))
AGENT_STATE_MIN_CHARS = 250
# 4000, up from the handover's 1500. The premise of the split is that the old
# cap was strangling the WRONG file: measured, ~40% of every handover was
# standing rules re-typed verbatim, and 8 rewrites in one session were refused
# as over-budget, with the hard-won trap the first thing trimmed. Rules and
# traps now live in their own unbudgeted files, so STATE.md needs room for
# state alone; 4000 still refuses a pasted transcript.
AGENT_STATE_MAX_CHARS = int(os.environ.get("WORKLIST_AGENT_STATE_MAX_CHARS", "4000"))

# The cap is FLAT again, and that is only sound because the budget and the
# document now have the same scope. It was briefly scaled by the number of
# `## SESSION` headings, because the budget was per SESSION while the document
# was per BRANCH: measured 2026-08-05 with a 1899-char neighbour, one session
# had ~1850 usable and was refused ELEVEN times across three refresh cycles,
# deleting real content each round to fit -- and the cheapest way to satisfy a
# flat cap was to delete the OTHER session's block. Scaling the cap treated the
# symptom. The real defect was that `--state` rewrote the whole file, so on
# 2026-08-09 a session obeyed a staleness nag and destroyed a peer's entire
# document describing a live campaign. Since that fix the document is a set of
# OWNED SECTIONS merged one at a time (agent_state_parse / _render), the cap
# applies to ONE section, and no budget pressure can reach a neighbour.

# The heading that owns a section. The owner group is deliberately wider than
# hex so the `legacy` pseudo-owner parses through the same path, and the tail
# is captured whole so a heading a human annotated survives a round trip.
AGENT_STATE_HEAD_RE = re.compile(
    r"^##[ \t]+SESSION[ \t]+([A-Za-z0-9_-]{4,32})\b[ \t]*(.*)$", re.MULTILINE
)
# The section's own age lives in its heading, not in a sidecar: a sidecar is
# invisible to the human reading the file, and the file being readable is what
# made the 2026-08-09 loss recoverable at all. Seconds optional, because the
# headings live sessions were already writing by hand carry minute stamps.
AGENT_STATE_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?Z")
AGENT_STATE_TS_FMTS = ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%MZ")
# Content that predates the section format, or any text before the first
# heading, is owned by nobody. It is adopted under this pseudo-owner rather
# than deleted, and ages out through the ordinary reap path.
AGENT_STATE_LEGACY_OWNER = "legacy"


# A second session arriving on a branch has no recorded signature for a
# document the first session wrote. The old pure-age fallback would order it
# rewritten immediately, reproducing the exact churn the redesign fixes, so an
# UNSIGNED document is ADOPTED on first sight instead -- bounded by this
# horizon so an abandoned one is not.
AGENT_STATE_ADOPT_MAX_MIN = int(os.environ.get("WORKLIST_AGENT_ADOPT_MAX_MIN", "60"))
# The one structural demand on STATE.md. Length is a proxy for value; the
# presence of a next action IS the value, and it cannot be satisfied by
# padding. Case-insensitive, any heading level.
AGENT_NEXT_RE = re.compile(r"^\s*#{1,6}\s*next action\b", re.IGNORECASE | re.MULTILINE)

# THE FIRST STEP OF '## Next action' MAY NOT BE A WAIT.
#
# WHY (operator, 2026-08-19): "you should continue for the rest of the remaining
# tasks instead of waiting only for CI... this is a general problem after
# compaction. WHY THIS HAPPENS? WE MUST SOLVE THE ROOT OF THE PROBLEM FIRST."
#
# The root cause was not a missing instrument. The Stop battery printed "39 OPEN
# worklist item(s). Do the next one" on essentially every stop, and the no-op
# wake ladder correctly stayed silent because the session was never idle: it
# ticked, leased and pushed on every wake. It was busy on the wrong thing.
#
# What made that survive COMPACTION is this document. A session whose
# '## Next action' opened with "1. Watch <worker>" handed exactly that priority
# to whoever picked the session up, who then did CI first and rewrote the
# document saying "watch CI first" again. The inversion was authored, inherited,
# and re-authored, once per compaction, with nothing in the loop to break it.
#
# So a wait may APPEAR in the next action; it may not LEAD it. A background watch
# is a CONDITION the session is under, not an action a recovered session takes:
# the watch is already armed and will wake somebody by itself, whereas the open
# items will not. Leading with it spends the one artifact designed to survive
# compaction on the one instruction that needs no carrying.
#
# Deliberately BODY-ONLY, with no store lookup: "lead with real work" holds even
# at zero open items, and a rule that reads the store would be unable to explain
# itself from the text a session just wrote.
AGENT_WAIT_LEAD_RE = re.compile(
    r"^\s*(?:[-*+]|\d+[.)])?\s*"
    r"(?:then\s+|first[,:]?\s+|just\s+|simply\s+)?"
    r"(?:wait(?:\s+for|ing)?|watch(?:ing)?|poll(?:ing)?|monitor(?:ing)?"
    r"|keep\s+watching|re-?arm|await(?:ing)?|sit\s+on|babysit)\b",
    re.IGNORECASE,
)

# A [?] whose DEFAULT has stood unanswered this long is EXECUTED, not
# restated: the operator said they almost always take the recommended
# action, so the recommendation IS the decision after the window closes.
DEFER_WINDOW_MIN = int(os.environ.get("WORKLIST_DEFER_WINDOW_MIN", "120"))
# Drain cap: at most this many expired deferrals are demanded per stop, so
# a migrated backlog (39 live [?] at the time of writing) arrives as a
# bounded queue, not a wall.
DEFER_EXEC_PER_STOP = int(os.environ.get("WORKLIST_DEFER_EXEC_PER_STOP", "3"))

# v12 (operator, 2026-07-30): a [?] costs nothing to create and nothing to
# hold, and 30+ of them sat 117 minutes untouched -- one requesting a feature
# that had ALREADY been built. So a deferral must now EARN its seat: --defer
# validates a WHY/HOW at creation, a deferral that has sat JUSTIFY_AGE_MIN
# without one is demanded (bounded per stop, same drain shape as the expired
# queue), and a justified one that has sat DEFER_AUDIT_MIN faces the judge's
# audit (bounded batch, riding the existing judge call so a stop never pays
# a second model invocation).
JUSTIFY_AGE_MIN = int(os.environ.get("WORKLIST_JUSTIFY_AGE_MIN", "30"))
JUSTIFY_PER_STOP = int(os.environ.get("WORKLIST_JUSTIFY_PER_STOP", "3"))
DEFER_AUDIT_MIN = int(os.environ.get("WORKLIST_DEFER_AUDIT_MIN", "45"))
DEFER_AUDIT_BATCH = int(os.environ.get("WORKLIST_DEFER_AUDIT_BATCH", "4"))


# ---- paths ------------------------------------------------------------------


def events_path(worklist):
    return worklist.with_suffix(".events.jsonl")


def teammate_idle_path(worklist):
    """Where TeammateIdle edges are journalled.

    A SIDECAR, not an event in the worklist log, and the distinction is
    deliberate. The event log is the worklist's own history and every record in
    it is folded into item state on read; a teammate going idle changes no
    item's state (the plan is emphatic that nothing auto-ticks and nothing
    auto-unleases), so putting it there would grow the fold's input with
    records the fold must then learn to ignore. It is telemetry about a WORKER,
    read only when something asks about one.
    """
    return worklist.with_suffix(".teammate-idle.jsonl")


def events_lock_path(worklist):
    return worklist.with_suffix(".events.lock")


def state_path(worklist, session_id):
    return worklist.with_suffix(".state-%s.json" % (session_id or "unknown")[:8])


def briefs_path(worklist):
    return worklist.with_suffix(".sessions")


def loop_path(worklist):
    return worklist.with_suffix(".loop")


def agent_root(root):
    return pathlib.Path(root) / "agent"


# Directory names under agent/ that are NOT sessions. Shape cannot tell them
# apart -- `archive` and `programs` both fit the sanitised 8-character session
# slug -- so they are named. Getting this wrong is quiet: a listing that counted
# `archive` as a peer would report a session that does not exist, and one that
# missed a real peer would report nobody there.
AGENT_RESERVED_DIRS = frozenset({"archive", "programs", "worklist"})


def agent_session_slug(me):
    """The DIRECTORY NAME one session owns under agent/.

    Sanitised and truncated to 8 characters, because the SAME session arrives
    here as a full uuid on the Stop event and as a short prefix from the CLI.
    An untruncated name would give one session TWO directories -- the exact
    split-brain the per-session layout exists to remove -- and the [:8] rule is
    the one `state_path` above already uses, so a session's store sidecar and
    its notes directory carry one name.
    """
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(me or "unknown"))[:8] or "unknown"


def agent_session_dir(root, me):
    """agent/<session>/ -- ONE session's own notes, and the reason the tree
    moved out of a single shared STATE.md on 2026-08-14: a peer can no longer
    overwrite what it cannot address. Peers stay VISIBLE as siblings
    (agent_peer_sections below); they simply stop being writable.

    NO BRANCH COMPONENT since 2026-08-18 (operator decision: "avoid using
    branch name in folder path, instead let's only use the session name"). The
    branch was never the right key for this document and the tree showed it:
    ONE session, 97604f47, owned three STATE.md files at once -- under `main`,
    `0815-1` and `backup-storage` -- because a `/pr-merge` moved the checkout
    under a live session and the hook silently started writing somewhere else.
    Its compact-recovery document is exactly the artifact that must not fork
    when the branch does. The session id is stable for the session's whole
    life, which is the lifetime this document has; a branch is not.

    Two consequences fall straight out and are load-bearing, not incidental:
    a DETACHED HEAD no longer makes the check blind (there is no branch to
    resolve), and a rebase or a branch rename can no longer strand a session's
    only recovery document at a path nothing reads.
    """
    return agent_root(root) / agent_session_slug(me)


def agent_state_path(root, me):
    return agent_session_dir(root, me) / "STATE.md"


def agent_rules_path(root, me):
    """RULES.md, YOURS if you keep one, otherwise the tree's.

    STATE.md is per session because two sessions writing one file destroyed a
    live document. RULES.md is not that: it holds settled facts and standing
    constraints, and nothing about it is per session -- which is why no session
    directory in this repo has ever carried one (verified against the tree, not
    assumed).

    It used to sit at BRANCH level and be copied forward, verbatim, from branch
    to branch. That ritual was the tell: a document copied unchanged across
    every branch was never per-branch, it was repo-level with a manual copy
    step. With the branch gone from the path it lives at `agent/RULES.md`, one
    document every session reads, sharpened in place.

    The session copy still WINS if it exists. Two places rather than one is a
    real cost, paid because the alternative was a PostCompact briefing that
    silently reported "(none)" for a file sitting one directory up.
    """
    own = agent_session_dir(root, me) / "RULES.md"
    return own if own.exists() else agent_root(root) / "RULES.md"


def agent_plan_dir(root):
    """The tree ROOT, deliberately one level ABOVE the session directories: a
    plan belongs to the work rather than to whoever happened to write it, and
    --triage names the path before any session owns it. That property is what
    the branch level used to provide and what `agent/` provides now."""
    return agent_root(root)


def agent_traps_path(root):
    # NOT under agent_root: TRAPS is branch-independent standing reference, not
    # per-session working state, so it lives with the other human-facing docs.
    #
    # The merge it was waiting for has landed. Two corpora existed, ~90% apart:
    # a 272-line gitignored file the hook actually READ, and a 631-line tracked
    # file that reached nobody programmatically. 18 headings against 22, three
    # shared. The machine briefed every session from the shorter, staler one --
    # and among the 15 entries only that file held was "A background agent goes
    # idle WITHOUT sending its report", which happened three times in the
    # session that found it. Merged to 838 lines / 37 headings, nothing lost
    # from either side, and this now points at the corpus a human also reads.
    return pathlib.Path(root) / "docs" / "agent-reference" / "TRAPS.md"


def agent_session_dirs(root):
    """Every session directory under agent/, name-sorted, minus the reserved
    names. [] when the tree is absent or unreadable, never an exception: peer
    visibility is a courtesy to the reader and must never be able to fail a
    stop."""
    try:
        return sorted(
            (
                p
                for p in agent_root(root).iterdir()
                if p.is_dir() and p.name not in AGENT_RESERVED_DIRS
            ),
            key=lambda p: p.name,
        )
    except OSError:
        return []


def agent_peer_sections(root, session_id):
    """Every OTHER session's sections, read from the SIBLING directories.

    This is what peer visibility became when the shared document was split
    (2026-08-14). Before, every section sat in one file and a whole-file write
    could delete the lot; now each session owns a directory, and a peer's
    STATE.md is READ-ONLY to everyone else by construction. Losing sight of
    them was never the goal: a session that cannot see what its peers are doing
    duplicates their work, or edits under them.

    Each file is parsed against ITS OWN mtime, so an unstamped peer document
    ages by its own clock rather than by whoever wrote last -- the per-file
    version of the per-section fix that made the old shared document honest.
    """
    out = []
    for d in agent_session_dirs(root):
        if C.same_session(d.name, session_id):
            continue
        p = d / "STATE.md"
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            mtime = p.stat().st_mtime
        except OSError:
            continue
        for s in agent_state_parse(text, mtime):
            if C.same_session(s["owner"], session_id):
                continue
            # An unowned (legacy) section in a peer's directory is attributed to
            # the DIRECTORY, which is now the authoritative owner: reporting it
            # as `legacy` would hide which session a reader must not disturb.
            if s["owner"] == AGENT_STATE_LEGACY_OWNER:
                # New binding rather than rebinding the loop variable: ruff's
                # PLW2901 objects because a reader scanning the loop cannot tell
                # which `s` a later line means.
                out.append(dict(s, owner=d.name))
            else:
                out.append(s)
    return out


def agent_state_lock_path(worklist):
    # In TMPDIR beside the store, NOT under agent/: the notes tree stays free
    # of machine artifacts, and the lock shares the store's lifetime.
    return worklist.with_suffix(".agentstate.lock")


def _agent_slot_suffix(me):
    """`.<session>` for the sidecar slots below, or '' when the caller names
    nobody. Sanitised, because a session id reaching here from the CLI is free
    text and a slash in a suffix is a path, not a name."""
    m = re.sub(r"[^A-Za-z0-9._-]", "_", str(me)) if me else ""
    return "." + m if m else ""


def agent_state_backup_path(worklist, me=""):
    """The ONE previous STATE.md, so a clobber is undoable.

    Last-write-wins within a session is deliberate (see worklist.py --state): a
    document whose contract is "rewrite every time" has no merge semantics.
    What was NOT deliberate is that the loss is permanent. Two live sessions
    shared one document once, and 84611aab replaced b9491d9c's 0-minute-old
    document TWICE; both bodies were gone for good, because the event log
    stores worklist item text and never STATE bodies, and the success line
    echoes only the first line back. One backup turns "sorry, rewrite it" into
    a `cp`. Same TMPDIR-beside-the-lock placement, for the same reason.

    SESSION-SCOPED since the tree split (2026-08-14). While every session wrote
    one shared document, a peer's backup held that whole document including my
    section, so a shared slot lost nothing. Once each session writes its own
    STATE.md, a shared slot means my peer's next write overwrites the only copy
    of MY replaced body.

    The slot used to carry the BRANCH too (review finding
    3688784930/3688787780, when the document itself was per branch). The branch
    left the document's path on 2026-08-18, so it leaves the slot with it: a
    mirror keyed more finely than the thing it mirrors is not safer, it is
    fragmented. One STATE.md per session now has exactly one `.prev` beside it,
    and a session whose checkout changes branch mid-flight keeps the backup of
    the document it is actually writing.
    """
    return worklist.with_suffix(".agentstate.prev%s.md" % _agent_slot_suffix(me))


def agent_state_reaped_path(worklist, me=""):
    """APPEND-ONLY archive of sections reaped as dead. Same session-scoping
    rule as the backup slot beside it.

    Separate from `.prev` and strictly stronger, because the hazard is
    different. `.prev` covers one generation of a document a session CHOSE to
    replace; reaping deletes a section NOBODY chose to delete, so it appends
    instead of overwriting. One append per dead session, which is small enough
    that unbounded growth is the right trade against ever losing the last words
    of a session that died mid-campaign.
    """
    return worklist.with_suffix(".agentstate.reaped%s.md" % _agent_slot_suffix(me))


# The ceiling on how many TRAPS.md titles a per-stop prompt carries.
#
# THE OLD VALUE WAS 40, AND THE FILE REACHED EXACTLY 40 ON 2026-08-23. That is
# not a near miss: the 41st entry would have been invisible, and the truncation
# is SILENT -- no warning, no marker, the list simply ends. Worse, the walk is
# top-down, so it kept the OLDEST titles and dropped the NEWEST, which is
# backwards for a corpus that is append-only and whose newest entries are the
# ones the current wave just paid for.
#
# If this cap ever bites for real, the decision is already made and does not
# need re-litigating: keep the TAIL, not the head, with the sentinel element
# first so the reader knows something was dropped. Silent truncation of any
# kind is what made 40 a defect rather than a limit.
TRAP_HEADING_CAP = 120


def trap_headings(root):
    """The `## ` heading texts of TRAPS.md, in file order. [] when absent or
    unreadable, never an exception.

    ONLY `##`, never `###`, never body lines: the judge gets TITLES of
    hard-won facts, one line each, because the file is designed to grow
    forever and feeding it whole to a per-stop model call would turn an
    intentionally-growing file into a per-stop cost multiplier.
    `TRAP_HEADING_CAP` is that ceiling, and when it bites the list gains ONE
    synthetic final element naming how many were dropped -- both consumers
    join with `"  - " + h` (`wl_checks.py`, `wl_judge.py`), so a synthetic
    element needs no call-site change.

    The cap was 40 and the file REACHED 40 on 2026-08-23 -- one entry from
    silent truncation that would have kept the OLDEST titles and dropped the
    NEWEST. The history and the keep-the-TAIL decision for the next time it
    bites are recorded on `TRAP_HEADING_CAP` directly above, so neither gets
    re-litigated from scratch.

    Headings inside FENCED CODE BLOCKS are examples, not entries; see
    `trap_entries`, which this now delegates to."""
    entries = trap_entries(root)
    out = [e["title"][:120] for e in entries[:TRAP_HEADING_CAP]]
    remaining = len(entries) - len(out)
    if remaining > 0:
        out.append(
            "(+%d further entries not shown; read docs/agent-reference/TRAPS.md in full)"
            % remaining
        )
    return out


# Only entries the machine is NOT already watching reach a model prompt, so the
# corpus can grow mechanized entries for free. TRAP_PROMPT_CAP is belt and
# braces against a pathological corpus, never the mechanism; it overflows LOUDLY
# for the same reason TRAP_HEADING_CAP does.
TRAP_PROMPT_CAP = 60

TRAILER_KEYS = ("Trap-Id:", "Enforced-By:", "Residue:")


def trap_entries(root):
    """Every `## ` entry of TRAPS.md as {line, title, id, enforced, residue}.

    FENCED CODE BLOCKS ARE NOT ENTRIES, and the bare `startswith("## ")` this
    replaces could not tell the difference. Latent while no trap body contained
    a fenced `## ` line; ACTIVATED by the registry, because once
    check:ci-trap-registry requires a Trap-Id per entry, a `## ` inside a
    fenced markdown example becomes a phantom entry with no id and the gate
    reds on a document that is correct. A trap body carrying a markdown example
    is ordinary, and this file's own header now carries fenced examples.

    The trailer is read only from the block between the heading and the first
    blank line, so a body paragraph that opens with "Residue:" stays body.

    [] when absent or unreadable, never an exception: the corpus is reference
    material, and a stop must not die because a doc moved.
    """
    try:
        text = agent_traps_path(root).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    entries = []
    fence = ""
    in_trailer = False
    for n, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip(" \t")
        if stripped.startswith(("```", "~~~")):
            char = stripped[0]
            if not fence:
                fence = char
            elif fence == char:
                fence = ""
            continue
        if fence:
            continue
        if line.startswith("## ") and not line.startswith("### "):
            entries.append(
                {"line": n, "title": line[3:].strip(), "id": "", "enforced": "", "residue": ""}
            )
            in_trailer = True
            continue
        if in_trailer:
            if not line.strip():
                in_trailer = False
                continue
            for key, field in zip(TRAILER_KEYS, ("id", "enforced", "residue"), strict=True):
                if line.startswith(key):
                    entries[-1][field] = line[len(key) :].strip()
                    break
            else:
                in_trailer = False
    return entries


def trap_prompt_lines(root):
    """The trap lines a MODEL still needs, and only those.

    A trap whose Enforced-By names live instruments is watched by something that
    fires whether or not anyone reads, so it leaves the prompt permanently: it
    is the gate's business now, not the judge's. What is left is the residue,
    rendered as the residue SENTENCE rather than the title, because the sentence
    is the part no instrument reaches and the title is just its name.

    Growth in the mechanized population therefore costs no prompt, and growth in
    the residue is exactly the thing that should cost attention. An entry with
    no trailer at all is UNCLASSIFIED, not clean, so it stays in the prompt as
    its title: unknown is never folded into fine.
    """
    out = []
    entries = trap_entries(root)
    for e in entries:
        if e["residue"]:
            out.append(e["residue"])
        elif not e["enforced"]:
            out.append(e["title"][:120])
    kept = out[:TRAP_PROMPT_CAP]
    if len(out) > len(kept):
        kept.append(
            "(+%d further residue entries not shown; read docs/agent-reference/TRAPS.md in full)"
            % (len(out) - len(kept))
        )
    return kept


def requests_path(worklist):
    return worklist.with_suffix(".requests")


def intents_path(worklist):
    return worklist.with_suffix(".intents")


# An intent is a statement of PLAN, never evidence of work. The ceiling exists
# because an intent that outlives its own horizon while the checks it covered are
# still outstanding must become a violation rather than a mute button.
INTENT_MAX_CHARS = 240
INTENT_DEFAULT_MIN = int(os.environ.get("WORKLIST_INTENT_DEFAULT_MIN", "45"))
INTENT_MAX_MIN = int(os.environ.get("WORKLIST_INTENT_MAX_MIN", "120"))


def record_intent(worklist, me, text, covers, minutes):
    """Append one intent. A SIDECAR, never the event log.

    The event log is folded by `compact` down to the minimal item-reproducing
    set, so a novel event kind there would be silently destroyed. `.requests` is
    the precedent this follows.
    """
    _append_lines(
        intents_path(worklist),
        str(intents_path(worklist)) + ".lock",
        [
            {
                "at": C.stamp_now(),
                "by": (me or "")[:8],
                "text": (text or "")[:INTENT_MAX_CHARS],
                "covers": sorted({c for c in (covers or []) if c})[:12],
                "min": max(1, min(int(minutes or INTENT_DEFAULT_MIN), INTENT_MAX_MIN)),
            }
        ],
    )


def live_intent(worklist, session_id, now=None):
    """(intent_or_None, expired_or_None) for THIS session.

    Returns the newest unexpired intent, and separately the newest EXPIRED one
    whose horizon has passed -- the caller turns that second value into a
    violation, which is what stops `--intent` becoming a way to go quiet
    indefinitely.
    """
    p = intents_path(worklist)
    if not p.exists():
        return None, None
    now = now or C.utcnow()
    live, expired = None, None
    try:
        rows = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None, None
    for line in rows:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not C.same_session(str(rec.get("by") or ""), session_id):
            continue
        when = C.parse_stamp(str(rec.get("at") or ""))
        if when is None:
            continue
        age_min = (now - when).total_seconds() / 60.0
        if age_min <= float(rec.get("min") or INTENT_DEFAULT_MIN):
            live = rec
        else:
            expired = rec

    return live, expired


# ---- per-session state doc --------------------------------------------------


def load_state(worklist, session_id):
    """The v10 per-session doc. A corrupt or missing doc is the empty default:
    every consumer treats absent keys as first sight, which can delay a nudge
    by one stop but can never fail open on an obligation check."""
    try:
        d = json.loads(state_path(worklist, session_id).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(worklist, session_id, doc):
    """tempfile + os.replace: single writer (per-session), atomic on crash."""
    p = state_path(worklist, session_id)
    try:
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=p.name)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=1)
        os.replace(tmp, p)
    except OSError:
        pass


# ---- the event log ----------------------------------------------------------


def _append_lines(path, lock_path, payloads):
    """Append JSONL lines under a blocking flock, healing a torn tail first.

    One os.write per batch. The heal: if the file's last byte is not a
    newline (a writer crashed mid-line), prepend one, so the torn fragment
    stays its own unparseable line instead of corrupting this event too.
    """
    with open(lock_path, "w") as lock:
        _flock(lock, LOCK_EX)
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            size = os.fstat(fd).st_size
            blob = b""
            if size and os.pread(fd, 1, size - 1) != b"\n":
                blob = b"\n"
            blob += "".join(json.dumps(p, separators=(",", ":")) + "\n" for p in payloads).encode(
                "utf-8"
            )
            os.write(fd, blob)
        finally:
            os.close(fd)


# ---------------------------------------------------------------------------
# THE TRACKED STORE. agent/worklist/<writer8>.jsonl, one append-only file per
# WRITER identity, committed like every other artifact under agent/.
#
# WHY IT LEFT TMPDIR. The log held the only record of what a session still owed,
# and TMPDIR does not survive a machine. The operator switches machines mid-wave;
# on the new one every open item, every deferral and every lease simply did not
# exist. Moving it into git is what makes `git pull` carry the work.
#
# WHY PER WRITER AND NOT ONE FILE. Both sides of a merge append at EOF, so a
# single shared file conflicts on every concurrent append from two branches. A
# session id exists in exactly one harness process, so a per-writer file has
# exactly one appender and two machines produce disjoint paths that git merges
# without ever consulting content. When a conflict does happen (the same writer
# on two machines, or a compaction), the resolution is UNION -- keep both sides,
# drop the markers -- because the reader sorts by timestamp before folding, so
# the union of two histories is a valid history. That property is the whole
# design; do not "optimise" the sort away.
#
# ONLY THE LOG MOVED. Every sidecar named in this module's docstring is
# per-machine runtime state (locks, caches, transcripts, briefs, .lastevent) and
# stays in TMPDIR. The lock is still the TMPDIR one: one machine, N sessions,
# one flock, which is exactly the scope a lock can cover.
STORE_DIR_NAME = "worklist"


def store_dir(root=None):
    """The tracked event-log directory. $WORKLIST_STORE_DIR overrides it, which
    is what lets a test fixture point the store somewhere disposable."""
    override = os.environ.get("WORKLIST_STORE_DIR")
    if override:
        return pathlib.Path(override)
    if root is None:
        root = C.project_root(C.project_start())
    return agent_root(root) / STORE_DIR_NAME


def writer_path(writer, root=None):
    return store_dir(root) / ("%s.jsonl" % agent_session_slug(writer))


# Writer names that are not session identities. They get their own file rather
# than being forced onto whichever session happened to trigger them, so a
# machine-level write never lands in a person's file.
_NON_SESSION_WRITERS = frozenset({"compact", "unknown", "md", "import"})


def identity_activity(worklist, root=None):
    """{prefix: (n_events, first_at)} for every SESSION identity this store
    carries, counted from the writer (`by`) AND the owner (`o`).

    WHY BOTH FIELDS, and it was measured on the operator's own store on
    2026-09-04 rather than imagined. compact() re-emits the entire fold through
    snapshot_events(by="compact"), so a compaction ERASES the writer of every
    historical event while preserving its owner. Both readers of "which
    identities does this store know about" -- the phantom backstop in
    wl_checks.phantom_identities and the age gate in --reassign -- scanned `by`
    alone. After any compaction they therefore saw NO identities at all, while
    the code that actually moves the work, three lines below the age gate,
    selects on `owner`.

    That disagreement is not academic. Three fixture items reached the live
    store owned by prefixes that had never written under their own name, and
    the result was an item unreachable through every sanctioned verb at once:
    --tick refused it ("owned by deadpeer; never tick another session's
    tracking"), and --reassign, the designated repair verb, refused the same
    item as "has written no events at all". Counting an identity's OWNED events
    as its own is what makes the derivation agree with the selection it exists
    to serve.

    ONE SET OF NON-SESSION NAMES, shared with _writer_for. wl_checks kept its
    own copy that omitted "import", so an imported store could surface the
    importer as a phantom identity; two spellings of "this name is not a
    person" is the same drift in miniature.
    """
    counts, first_at = {}, {}
    for ev in _read_events(worklist, root):
        at = str(ev.get("at") or "")
        # A SET PER EVENT: `by` and `o` are usually the same prefix, and
        # counting such an event twice would inflate the event count the
        # backstop reports to the operator.
        for who in {str(ev.get("by") or ""), str(ev.get("o") or "")}:
            if not who or who in _NON_SESSION_WRITERS or not C.PREFIX_RE.match(who):
                continue
            counts[who] = counts.get(who, 0) + 1
            if who not in first_at or (at and at < first_at[who]):
                first_at[who] = at
    return {k: (n, first_at.get(k, "")) for k, n in counts.items()}


def _writer_for(payloads, explicit=None):
    if explicit:
        return agent_session_slug(explicit)
    for ev in payloads:
        by = str((ev or {}).get("by") or "")
        if by and by not in _NON_SESSION_WRITERS and C.PREFIX_RE.match(by):
            return agent_session_slug(by)
    me = C.resolve_session_id()
    return agent_session_slug(me[:8]) if me else "_shared"


_BRANCH_CACHE = {}


def _branch_of(root):
    """Cached: git_branch shells out, and this runs on every append."""
    key = str(root)
    if key not in _BRANCH_CACHE:
        try:
            _BRANCH_CACHE[key] = C.git_branch(root) or ""
        except Exception:  # noqa: BLE001 -- a branch is context, never a reason to lose an event
            _BRANCH_CACHE[key] = ""
    return _BRANCH_CACHE[key]


_HOST_CACHE = {}


def host_hash():
    """A HASH of the hostname, never the hostname. This file is tracked and
    public; which machine an event came from is needed to tell "this box" from
    "another box", and the name itself is not."""
    if "h" not in _HOST_CACHE:
        try:
            _HOST_CACHE["h"] = hashlib.sha1(
                socket.gethostname().encode("utf-8", "replace")
            ).hexdigest()[:8]
        except Exception:  # noqa: BLE001
            _HOST_CACHE["h"] = "unknown0"
    return _HOST_CACHE["h"]


def append_events(worklist, payloads, writer=None, root=None):
    if not payloads:
        return
    if root is None:
        root = C.project_root(C.project_start())
    br = _branch_of(root)
    hh = host_hash()
    for ev in payloads:
        if isinstance(ev, dict):
            ev.setdefault("h", hh)
            if br:
                ev.setdefault("br", br)
            # A SUB-SECOND SEQUENCE, because `at` has second resolution and the
            # sort below would otherwise break ties by FILENAME. Measured: the
            # stop-gate judge reopens an item and the session ticks it in the
            # same second; the reopen is written by writer `judge` and the tick
            # by the session, so sorting on `at` alone put judge.jsonl last and
            # the reopen won -- the item stayed open and an allowed stop became
            # a block. Events written before this field sort as 0, which keeps
            # their existing (stable, file-order) behaviour.
            ev.setdefault("ns", time.time_ns())
    target = writer_path(_writer_for(payloads, writer), root)
    with contextlib.suppress(OSError):
        target.parent.mkdir(parents=True, exist_ok=True)
    _append_lines(target, events_lock_path(worklist), payloads)


def _parse_events(text):
    out = []
    for line in text.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue  # torn tail, or a conflict marker: skipped by contract
        if isinstance(ev, dict):
            out.append(ev)
    return out


def _read_events(worklist, root=None):
    """Every tracked writer file, PLUS the legacy TMPDIR log while it exists,
    folded in timestamp order.

    THE LEGACY UNION IS WHAT MAKES THE MOVE GAP-FREE. Until `--import-tmp` has
    run on this host, the old log still holds open items; reading both means no
    item stops blocking merely because the code changed under it. The writer
    never appends to the legacy file again, so the two cannot diverge.

    THE SORT IS LOAD-BEARING. File name order is not time order, and after a
    merge one file can hold events older than another's first line. Sorting by
    the stamp (which is `%Y-%m-%dT%H:%M:%SZ`, so lexical order is chronological)
    is what makes a union of histories fold to the same state as one history.
    """
    out = []
    try:
        for f in sorted(store_dir(root).glob("*.jsonl")):
            try:
                out.extend(_parse_events(f.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                continue
    except OSError:
        pass
    legacy = events_path(worklist)
    if legacy.exists():
        with contextlib.suppress(OSError):
            out.extend(_parse_events(legacy.read_text(encoding="utf-8", errors="replace")))
    # (at, ns): the stamp orders across machines and the nanosecond counter
    # orders within a second on this one. A missing ns sorts first inside its
    # second, which is where an older event belongs.
    out.sort(key=lambda e: (str(e.get("at") or ""), int(e.get("ns") or 0)))
    return out


def item_key(owner, text):
    """Identity of a markdown line: owner + text, EXCLUDING the state byte,
    so an in-place tick keeps its stamps while a text edit resets them."""
    return hashlib.sha1(
        ("%s|%s" % (owner or "", text.strip())).encode("utf-8", "replace")
    ).hexdigest()[:12]


def new_item_id(text):
    return hashlib.sha1(
        ("%d|%d|%s" % (time.time_ns(), os.getpid(), text)).encode("utf-8", "replace")
    ).hexdigest()[:8]


def parse_md_items(md_bytes):
    """{key: {"s","o","t"}} from the markdown. `[~]` lines are absent by
    definition (tombstones read as deletions), and later duplicates of one
    (owner, text) pair collapse onto the same key, last state wins."""
    out = {}
    for raw in md_bytes.split(b"\n"):
        try:
            line = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        m = C.ITEM_ANY.match(line)
        if not m:
            continue
        state = m.group("state")
        if state == "~":
            continue
        owner = m.group("owner")
        text = line[m.end() :].strip()
        out[item_key(owner, text)] = {"s": state, "o": owner, "t": text}
    return out


def _render_line(rec):
    """The legacy one-line shape, so every consumer that greps or regexes
    worklist lines (the battery, the suite's needles, the reggate token scan)
    keeps working against fold output byte-for-byte for md-origin items."""
    tag = "(%s) " % rec["owner"] if rec["owner"] else ""
    line = "- [%s] %s%s" % (rec["state"], tag, rec["text"])
    if rec.get("until") and "until:" not in rec["text"]:
        line += " until:%s" % rec["until"]
    if rec.get("worker") and "worker:" not in rec["text"]:
        line += " worker:%s" % rec["worker"]
    return line


def brief_text(rec, cap=None):
    """basetext + LATEST note only -- the v14 display identity.

    rec['text'] accumulates every state/lease note forever; one live item
    reached ~20 concatenated update lines and every block that mentioned it
    printed them all. Logic (DEFAULT_TOKEN scans, lease_state, the reggate
    token scan) still reads the FULL line; only human-facing rendering goes
    through here. Items folded before v14 have no basetext, so the fallback
    splits at the first double space, which is exactly the join the
    accumulator uses. With a cap, base and note split it roughly in half so
    the newest information survives truncation."""
    base = (rec.get("basetext") or "").strip()
    if not base:
        base = str(rec.get("text", "")).strip().split("  ", 1)[0]
    note = str(rec.get("lastnote", "")).strip()
    if not note or note == base or note in base:
        return base[:cap] if cap else base
    if cap:
        half = max(30, cap // 2 - 6)
        return "%s ... LATEST: %s" % (base[:half], note[:half])
    return "%s  LATEST: %s" % (base, note)


def brief_line(rec):
    """brief_text in the one-line item shape, until:/worker: tail included so
    a displayed lease still names its worker and expiry."""
    tag = "(%s) " % rec["owner"] if rec["owner"] else ""
    txt = brief_text(rec)
    line = "- [%s] %s%s" % (rec["state"], tag, txt)
    if rec.get("until") and "until:" not in txt:
        line += " until:%s" % rec["until"]
    if rec.get("worker") and "worker:" not in txt:
        line += " worker:%s" % rec["worker"]
    return line


def _fold_events(events):
    """(records, md_keys, cli_ids, last_md_hash, lineage). Chronological single
    pass; a later event wins, which is exactly the right answer for the one real
    conflict (a CLI tick vs a later deliberate markdown re-open).

    `lineage` is the list of proven compaction edges, in order. It is a LIST and
    not a fold-to-latest: a session can compact more than once, and the chain
    a276391d -> 74de73ca -> ... is only resolvable if every hop survives."""
    records, md_keys, cli_ids = {}, set(), set()
    lineage = []
    last_md_hash = ""
    for ev in events:
        kind = ev.get("ev")
        at = str(ev.get("at", ""))
        if kind == "md":
            last_md_hash = str(ev.get("h", ""))
            for a in ev.get("add") or []:
                k = a.get("k")
                if not k:
                    continue
                rec = records.setdefault(
                    k, {"id": k, "first": str(a.get("at", at)) or at, "origin": "md"}
                )
                rec["state"] = a.get("s", " ")
                rec["md_s"] = a.get("s", " ")
                rec["owner"] = a.get("o")
                rec["text"] = str(a.get("t", ""))
                # First sight wins: a later md sync replaces `text` wholesale
                # (possibly already-accumulated), but the display identity is
                # whatever the item FIRST said.
                rec.setdefault("basetext", str(a.get("t", "")))
                rec.setdefault("lastnote", "")
                rec.setdefault("upd", rec["first"])
                md_keys.add(k)
            for c in ev.get("chg") or []:
                rec = records.get(c.get("k"))
                if rec is not None:
                    rec["state"] = c.get("s", rec["state"])
                    rec["md_s"] = c.get("s", rec.get("md_s", " "))
                    rec["upd"] = at
            for k in ev.get("del") or []:
                md_keys.discard(k)
        elif kind == "lineage":
            # ONE conversation, two session ids, proven by wl_lineage.py before
            # this event was ever written (a compaction boundary the successor
            # opens with, PLUS conversational record uuids the two transcripts
            # share). Nothing is rewritten here: the `(prefix)` tag inside each
            # item still names the session that really wrote it, which is true.
            prev, nxt = str(ev.get("prev", "")), str(ev.get("next", ""))
            if prev and nxt:
                lineage.append(
                    {
                        "prev": prev,
                        "next": nxt,
                        "via": str(ev.get("via", "")),
                        "ev_id": str(ev.get("ev_id", "")),
                        "shared": ev.get("shared"),
                        "prev_tx": str(ev.get("prev_tx", "")),
                        "next_tx": str(ev.get("next_tx", "")),
                        "at": at,
                    }
                )
            continue  # not an item event; there is no `rec` to stamp below
        elif kind == "add":
            rid = ev.get("id")
            if not rid:
                continue
            records[rid] = {
                "id": rid,
                "state": ev.get("s", " "),
                "owner": ev.get("o"),
                "text": str(ev.get("t", "")),
                # v14: the display identity. `text` accumulates every note
                # forever (the durable history --list shows); rendering the
                # whole accumulation in blocks was the single largest noise
                # source of the v13 night, so displays show basetext + the
                # LATEST note only, via brief_line().
                # COMPACT CARRY-OVER. A normal `add` has no bt/ln/tr/ju and
                # falls back exactly as before; a compact-written `add` carries
                # them so the rewrite is not lossy. See compact() for why.
                "basetext": str(ev.get("bt", ev.get("t", ""))),
                "lastnote": str(ev.get("ln", "")),
                "first": at,
                "upd": str(ev.get("upd") or at),
                "origin": "cli",
            }
            if ev.get("tr"):
                records[rid]["triage"] = ev["tr"]
            if ev.get("ju"):
                records[rid]["just"] = ev["ju"]
            cli_ids.add(rid)
        elif kind == "reassign":
            # v19: an item's OWNER moves to a live session. Appended, never
            # rewritten, like every other event here -- that is what makes the
            # lock-free fold sound, and it keeps the log truthful about who
            # actually wrote the item. Only the `o` field moves; `by` on the
            # original events still names the phantom, because it really did
            # write them.
            rec = records.get(ev.get("id"))
            if rec is not None:
                rec["owner"] = ev.get("o")
                rec["upd"] = at
        elif kind in ("state", "update", "lease", "unlease", "tomb", "triage"):
            rec = records.get(ev.get("id"))
            if rec is None:
                continue
            if kind == "state":
                rec["state"] = ev.get("s", rec["state"])
                note = str(ev.get("note", "")).strip()
                if note:
                    rec["lastnote"] = note
                if note and note not in rec["text"]:
                    rec["text"] = (rec["text"] + "  " + note).strip()
                # v12: --defer records its justification as a REAL field, so
                # downstream consumers read data they wrote, not re-parsed
                # prose. The text still carries the tokens (the note above),
                # which is what survives compaction and the markdown inbox.
                j = ev.get("j")
                if isinstance(j, dict) and j:
                    rec["just"] = j
            elif kind == "update":
                # The stamp bump below is the point; the note additionally
                # becomes the item's display note (v14) -- before that,
                # --update notes were recorded and never shown anywhere.
                note = str(ev.get("note", "")).strip()
                if note:
                    rec["lastnote"] = note
            elif kind == "lease":
                rec["state"] = ">"
                rec["until"] = str(ev.get("until", ""))
                rec["worker"] = str(ev.get("worker", ""))
                # Absent on events written before this field existed, which
                # reads as False: an old lease is treated as unverifiable rather
                # than as dead. That is the safe direction -- the age ladder
                # still catches a genuine stall, whereas a false "gone" sends a
                # session hunting a worker that never existed.
                rec["worker_verified"] = bool(ev.get("worker_verified"))
                note = str(ev.get("note", "")).strip()
                if note:
                    rec["lastnote"] = note
                if note and note not in rec["text"]:
                    rec["text"] = (rec["text"] + "  " + note).strip()
            elif kind == "unlease":
                # THE RELEASE ARM. Moves a [>] back to plain open and CLEARS the
                # worker and expiry, because a released item that keeps its old
                # worker string still reads as claimed to every liveness check
                # that looks at the field rather than the state.
                #
                # Deliberately does not touch `done`: releasing says "no worker
                # rides this", never "this finished". The whole point is to give
                # a session an honest exit that is neither a false tick nor a
                # false lease.
                rec["state"] = " "
                rec["until"] = ""
                rec["worker"] = ""
                note = str(ev.get("t", "")).strip()
                if note:
                    rec["lastnote"] = note
            elif kind == "tomb":
                rec["state"] = "~"
            elif kind == "triage":
                # v16: the size verdict --triage recorded for this finding.
                # Only 'plan-subagent' carries a plan path, and the guide
                # probes that path on disk, so a "big" finding whose design
                # was never written is visible instead of forgotten.
                rec["triage"] = {
                    "v": str(ev.get("v", "")),
                    "plan": str(ev.get("plan", "")),
                }
            rec["upd"] = at
    return records, md_keys, cli_ids, last_md_hash, lineage


class Fold:
    """One read of the world's items, shared by every consumer of a stop.

    items: live records (state != '~'), each carrying id, state, owner, text,
    line (rendered legacy shape), first/upd stamps, origin, until/worker.
    """

    def __init__(self, items, md_hash, lineage=()):
        self.items = items
        self.md_hash = md_hash
        self.lineage = list(lineage)
        self.by_id = {r["id"]: r for r in items}

    def aliases_of(self, session_id):
        """Every id proven to be the same conversation as `session_id`.

        TRANSITIVE and walked in BOTH directions, because a session that has
        compacted twice reaches its oldest self only through the middle hop, and
        because the id we are asked about may be any link in the chain. Bounded
        by the number of edges, so a cycle (which cannot arise from real
        evidence, but could from a hand-edited log) terminates rather than hangs.
        """
        if not session_id or not self.lineage:
            return set()
        adj = {}
        for e in self.lineage:
            adj.setdefault(e["prev"], set()).add(e["next"])
            adj.setdefault(e["next"], set()).add(e["prev"])
        # Start from every node the argument is a prefix of, or that is a prefix
        # of it: callers pass short tags, the Stop event carries the full uuid.
        seen = {n for n in adj if C.same_session(n, session_id)}
        stack = list(seen)
        while stack:
            for nxt in adj.get(stack.pop(), ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return {n for n in seen if not C.same_session(n, session_id)}

    def lines(self):
        return [r["line"] for r in self.items]


def load(worklist, sync=True):
    """Fold the event log, first syncing any markdown change into it.

    The sync runs under the events lock: fold, diff the parsed markdown
    against the fold's markdown view, append the diff, patch the in-memory
    fold. Concurrent syncers serialize on the lock and the loser sees no
    remaining diff. With `sync=False` (read-only callers) the markdown is
    still PARSED if it disagrees with the fold, so a reader never ignores a
    line it can see, but nothing is written.
    """
    md_bytes = b""
    if worklist.exists():
        try:
            md_bytes = worklist.read_bytes()
        except OSError:
            md_bytes = b""
    md_hash = hashlib.sha1(md_bytes).hexdigest()[:16]

    def build(events):
        records, md_keys, cli_ids, last_h, lin = _fold_events(events)
        return records, md_keys, cli_ids, last_h, lin

    def diff(records, md_keys, parsed, at):
        add, chg, dele = [], [], []
        for k, it in parsed.items():
            if k not in md_keys:
                add.append({"k": k, "s": it["s"], "o": it["o"], "t": it["t"], "at": at})
            else:
                rec = records.get(k) or {}
                if rec.get("md_s") != it["s"]:
                    chg.append({"k": k, "s": it["s"]})
        dele.extend(md_keys - set(parsed))
        return add, chg, dele

    parsed = parse_md_items(md_bytes)
    records, md_keys, cli_ids, last_h, lineage = build(_read_events(worklist))
    if last_h != md_hash:
        at = C.stamp_now()
        if sync:
            with open(events_lock_path(worklist), "w") as lock:
                _flock(lock, LOCK_EX)
                # Re-fold under the lock: another syncer may have won.
                records, md_keys, cli_ids, last_h, lineage = build(_read_events(worklist))
                if last_h != md_hash:
                    add, chg, dele = diff(records, md_keys, parsed, at)
                    ev = {"ev": "md", "at": at, "h": md_hash}
                    if add:
                        ev["add"] = add
                    if chg:
                        ev["chg"] = chg
                    if dele:
                        ev["del"] = dele
                    # Append INSIDE the held lock via the raw writer (the
                    # public append_events would deadlock re-taking it). The
                    # TARGET is the tracked store, same as every other write;
                    # only the locking differs.
                    ev.setdefault("h", host_hash())
                    _md_target = writer_path(_writer_for([ev]))
                    with contextlib.suppress(OSError):
                        _md_target.parent.mkdir(parents=True, exist_ok=True)
                    fd = os.open(_md_target, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o644)
                    try:
                        size = os.fstat(fd).st_size
                        blob = b"" if not size or os.pread(fd, 1, size - 1) == b"\n" else b"\n"
                        blob += (json.dumps(ev, separators=(",", ":")) + "\n").encode("utf-8")
                        os.write(fd, blob)
                    finally:
                        os.close(fd)
                    records, md_keys, cli_ids, last_h, lineage = build(_read_events(worklist))
        else:
            # Read-only view: overlay the parsed markdown without writing.
            add, chg, dele = diff(records, md_keys, parsed, at)
            for a in add:
                records[a["k"]] = {
                    "id": a["k"],
                    "state": a["s"],
                    "md_s": a["s"],
                    "owner": a["o"],
                    "text": a["t"],
                    "first": at,
                    "upd": at,
                    "origin": "md",
                }
                md_keys.add(a["k"])
            for c in chg:
                records[c["k"]]["state"] = c["s"]
            for k in dele:
                md_keys.discard(k)

    items = []
    for k in list(md_keys) + [i for i in cli_ids if i not in md_keys]:
        rec = records.get(k)
        if rec is None or rec.get("state") == "~":
            continue
        rec = dict(rec)
        rec["line"] = _render_line(rec)
        items.append(rec)
    items.sort(key=lambda r: (r.get("first", ""), r["id"]))
    fold = Fold(items, md_hash, lineage)
    # BIND ONCE, HERE, and only for the identity this process actually resolved
    # to. Every ownership question downstream goes through wl_core.owned_by_me,
    # so binding at the single load point is what makes the compaction fix
    # impossible to roll out half-applied. A process with no resolvable identity
    # binds nothing and behaves exactly as it did before lineage existed.
    me = C.resolve_session_id()
    if me:
        C.bind_lineage(me, fold.aliases_of(me))
    return fold


# ---- item verbs (CLI-origin events) ----------------------------------------


def add_item(worklist, by, text, state=" ", owner=None):
    rid = new_item_id(text)
    append_events(
        worklist,
        [
            {
                "ev": "add",
                "id": rid,
                "at": C.stamp_now(),
                "by": by,
                "s": state,
                "o": owner if owner is not None else by,
                "t": text,
            }
        ],
    )
    return rid


def set_state(worklist, by, item_id, state, note="", extra=None):
    ev = {"ev": "state", "id": item_id, "at": C.stamp_now(), "by": by, "s": state, "note": note}
    if extra:
        ev.update(extra)
    append_events(worklist, [ev])


def update_item(worklist, by, item_id, note):
    append_events(
        worklist,
        [{"ev": "update", "id": item_id, "at": C.stamp_now(), "by": by, "note": note}],
    )


def triage_item(worklist, by, item_id, verdict, reason, plan=""):
    """Record a --triage verdict against an item.

    Written ONLY on a real judge answer: a degraded triage prints the
    self-assessment and records nothing, because the machinery must never
    claim a verdict it did not produce. `plan` is the committed plan path and
    is meaningful for 'plan-subagent' alone.
    """
    ev = {
        "ev": "triage",
        "id": item_id,
        "at": C.stamp_now(),
        "by": by,
        "v": verdict,
        "reason": reason,
    }
    if plan:
        ev["plan"] = plan
    append_events(worklist, [ev])


def lease_item(worklist, by, item_id, until, worker, note="", worker_verified=False):
    """Record a lease, INCLUDING whether the worker was verifiable when taken.

    That bit is the difference between "this worker died" and "this worker was
    never something the OS could confirm". The liveness ladder used to conflate
    them: any id absent from the harness snapshot was reported as gone, so an
    Agent leased by NAME -- which can never appear in a background-task list --
    was accused of being dead while it was demonstrably writing files. The caller
    already computes this at lease time to print its warning; it simply threw the
    answer away.
    """
    append_events(
        worklist,
        [
            {
                "ev": "lease",
                "id": item_id,
                "at": C.stamp_now(),
                "by": by,
                "until": until,
                "worker": worker,
                "note": note,
                "worker_verified": bool(worker_verified),
            }
        ],
    )


def tomb_item(worklist, by, item_id, why):
    append_events(
        worklist,
        [{"ev": "tomb", "id": item_id, "at": C.stamp_now(), "by": by, "why": why}],
    )


def deferral_justification(rec):
    """The merged WHY/HOW/... record for a [?] item: the event's `j` field
    where the CLI wrote one, overlaid on a token-parse of the text, which is
    what a markdown-written deferral or a compacted log still carries. The
    event field wins per key; the parse fills the gaps."""
    parsed = C.parse_justification(rec.get("text", ""))
    j = rec.get("just")
    if isinstance(j, dict):
        parsed.update({k: v for k, v in j.items() if isinstance(v, str) and v})
    return parsed


# ---- classification ---------------------------------------------------------


def classify_items(fold, session_id, live_worker_ids=None):
    """(open_items, others, deferred, in_flight) as display strings / recs,
    the v2-v9 state machine unchanged: open blocks, [?] is reported, fresh
    [>] is allowed-and-reported, an expired or invalid lease fails closed
    into an open item.

    v14 gap 4: an EXPIRED (never invalid) lease whose worker id appears in
    `live_worker_ids` (the OS-verified running background tasks) is tolerated
    as in-flight instead of failing closed, with `lease_tolerated` stamped on
    the rec so displays can say so. A long job outliving the lease cap while
    its watcher is demonstrably alive is supervision, not abandonment; the
    moment the worker disappears the item fails closed exactly as before."""
    open_items, others, deferred, in_flight = [], {}, [], []
    for rec in fold.items:
        state, owner, line = rec["state"], rec["owner"], rec["line"]
        # v14: DISPLAY strings are brief (basetext + latest note); every
        # decision below still reads the full line (lease_state, ownership).
        disp = brief_line(rec)
        mine = C.owned_by_me(owner, session_id)
        if state == " ":
            if mine:
                open_items.append(disp)
            else:
                others.setdefault(owner, []).append(disp)
        elif state == "?" and mine:
            deferred.append(rec)
        elif state == ">":
            if not mine:
                others.setdefault(owner, []).append(disp)
                continue
            ls = C.lease_state(line)
            if ls == "fresh":
                in_flight.append(rec)
            elif ls == "expired" and rec.get("worker") and rec["worker"] in (live_worker_ids or ()):
                rec["lease_tolerated"] = True
                in_flight.append(rec)
            else:
                # Fail closed: an expired or malformed lease is an open item.
                open_items.append(
                    "%s   <- [>] lease %s; finish it, renew the lease, or tick it" % (disp, ls)
                )
    return open_items, others, deferred, in_flight


# ---- dead-session cleanup (v4, extended to CLI items) -----------------------


def owner_age_hours(owner, projects_dir):
    """Hours since the owner's newest transcript write, or None if no
    transcript matches (unknown owner: word label, foreign machine). The
    newest match wins so a short prefix matching several sessions reads as
    the LIVELIEST of them -- the conservative direction."""
    if not owner or not projects_dir:
        return None
    matches = _glob.glob(os.path.join(projects_dir, owner + "*.jsonl"))
    if not matches:
        return None
    newest = max(os.path.getmtime(m) for m in matches)
    return (time.time() - newest) / 3600.0


# ---------------------------------------------------------------------------
# LIVENESS, from artifacts and nothing else.
#
# ONE definition, shared by /migrate's refusal and the Stop hook's handoff
# block, because two definitions of "is that session still running" drift and
# the expensive direction is the silent one: moving work out from under a
# session that is still doing it.
#
# The four verdicts and what each MEANS, stated because "remote" is the one
# that surprises people:
#   live    an artifact on THIS machine says it acted recently -> never migrate
#   idle    artifacts exist here, all older than LIVE_MIN       -> migratable
#   remote  no local artifact at all; its events carry a foreign host hash. It
#           may well still be running over there. This machine CANNOT know, and
#           pretending otherwise would be the vacuous check this repo keeps
#           finding. The safeguard is not a timer, it is the operator: /migrate
#           lists it, says so in the option text, and moves nothing unasked.
#   unknown no events by that prefix anywhere -> nothing to migrate
LIVE_MIN = int(os.environ.get("WORKLIST_LIVE_MIN", "30"))


def session_liveness(worklist, prefix, projects_dir=None, events=None):
    """(verdict, evidence). Evidence names the artifact and its age, never a
    bare verdict: a refusal a reader cannot check is a refusal they will route
    around."""
    p = str(prefix or "")[:8]
    if not p:
        return "unknown", "no prefix given"

    # 1. .lastevent-<p>.json -- written on EVERY full stop, so a running
    #    session always has a fresh one.
    le = worklist.with_suffix(".lastevent-%s.json" % p)
    try:
        if le.exists():
            age_min = (time.time() - le.stat().st_mtime) / 60.0
            if age_min <= LIVE_MIN:
                return "live", ".lastevent-%s.json written %d min ago" % (p, age_min)
    except OSError:
        pass

    # 2. the .sessions brief, the oracle the brief check already forces every
    #    live session to refresh.
    try:
        when, _txt = read_briefs(worklist).get(p, (None, ""))
        if when is not None:
            age_min = (C.utcnow() - when).total_seconds() / 60.0
            if age_min <= SESSION_BRIEF_STALE_MIN:
                return "live", "session brief refreshed %d min ago" % age_min
    except Exception:  # noqa: BLE001 -- a brief is evidence, never a crash
        pass

    # 3. its transcript on this machine.
    try:
        h = owner_age_hours(p, projects_dir)
    except Exception:  # noqa: BLE001
        h = None
    if h is not None and h * 60.0 <= LIVE_MIN:
        return "live", "transcript written %d min ago" % (h * 60.0)

    # 4. its own newest event, but only when that event came from THIS host --
    #    a foreign host's timestamp says nothing about a process here.
    if events is None:
        events = _read_events(worklist)
    mine_host, newest, newest_host = host_hash(), "", ""
    for ev in events:
        if str(ev.get("by") or "")[:8] != p:
            continue
        at = str(ev.get("at") or "")
        if at > newest:
            newest, newest_host = at, str(ev.get("h") or "")
    if not newest:
        return "unknown", "no events by %s in the store" % p
    if newest_host and newest_host == mine_host:
        try:
            age_min = (C.utcnow() - C.parse_stamp(newest)).total_seconds() / 60.0
        except Exception:  # noqa: BLE001
            age_min = None
        if age_min is not None and age_min <= LIVE_MIN:
            return "live", "wrote to the store %d min ago on this machine" % age_min

    # REMOTE requires POSITIVE evidence of another host. Without a host stamp
    # the honest answer is `idle` (no artifact here), not a claim about a
    # machine this one has never seen.
    if h is None and not le.exists() and newest_host and newest_host != mine_host:
        return "remote", (
            "last seen %s on another host; this machine cannot tell whether it "
            "is still running" % newest
        )
    return "idle", "no artifact here newer than %d min (newest event %s)" % (LIVE_MIN, newest)


def snapshot_events(fold, by="compact"):
    """The minimal, LOSSLESS set of events that folds back to `fold`.

    Extracted from compact() so the importer writes exactly what a compaction
    would: the same carry-over of bt/ln/upd/tr/ju (whose loss turned a justified
    deferral into an unjustified one, and collapsed every liveness age onto
    creation time) and the same lease re-emission. Two writers of this shape
    would drift; one is the point.
    """
    at = C.stamp_now()
    out = []
    md_add = [
        {"k": r["id"], "s": r["state"], "o": r["owner"], "t": r["text"], "at": r["first"]}
        for r in fold.items
        if r["origin"] == "md"
    ]
    if md_add:
        out.append({"ev": "md", "at": at, "h": fold.md_hash, "add": md_add})
    out.extend(
        [
            {
                "ev": "lineage",
                "at": e.get("at", at),
                "by": by,
                "prev": e["prev"],
                "next": e["next"],
                "via": e.get("via", ""),
                "ev_id": e.get("ev_id", ""),
                "shared": e.get("shared"),
                "prev_tx": e.get("prev_tx", ""),
                "next_tx": e.get("next_tx", ""),
            }
            for e in fold.lineage
        ]
    )
    for r in fold.items:
        if r["origin"] != "cli":
            continue
        add_ev = {
            "ev": "add",
            "id": r["id"],
            "at": r["first"],
            "by": by,
            "s": r["state"],
            "o": r["owner"],
            "t": r["text"],
        }
        for key, field in (
            ("bt", "basetext"),
            ("ln", "lastnote"),
            ("tr", "triage"),
            ("ju", "just"),
        ):
            if r.get(field) and not (field == "basetext" and r["basetext"] == r["text"]):
                add_ev[key] = r[field]
        if r.get("upd") and r["upd"] != r["first"]:
            add_ev["upd"] = r["upd"]
        if r.get("mg"):
            add_ev["mg"] = r["mg"]
        out.append(add_ev)
        # ONLY FOR AN ITEM THAT IS ACTUALLY IN FLIGHT. The fold's lease arm sets
        # state = ">" unconditionally, and a DONE item that was leased at some
        # point still carries `until`/`worker` as history -- so re-emitting the
        # lease for it RESURRECTS it. Measured on this repo's own store while
        # verifying the importer: 39 of 189 items flipped from [x] to [>] and
        # the open count went from 5 to 44. compact() carried the identical
        # construction, so every compaction had been quietly reopening old
        # work; folding both onto this one builder fixes it in both places.
        if r["state"] == ">" and (r.get("until") or r.get("worker")):
            out.append(
                {
                    "ev": "lease",
                    "id": r["id"],
                    "at": r["upd"],
                    "by": by,
                    "until": r.get("until", ""),
                    "worker": r.get("worker", ""),
                }
            )
    return out


# Shapes that must never reach a TRACKED file. Not an exhaustive secret
# detector and not sold as one: it catches the classes that have actually
# turned up in this repo's own artifacts, at the door, where the cost of a
# false positive is retyping one note.
_SECRET_SHAPES = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY"),
    re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bwhsec_[A-Za-z0-9]{24,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{32,}"),
)

_CONFLICT_RE = re.compile(r"^(<<<<<<<|=======|>>>>>>>)")


def secret_shapes_in(text):
    """Which secret shapes a string carries. Names the SHAPE, never the match:
    echoing the value back is the thing being prevented."""
    return [r.pattern for r in _SECRET_SHAPES if r.search(str(text or ""))]


def compact_store(worklist, root=None, me=None, projects_dir=None):
    """Compact the TRACKED store: one snapshot, and only files nobody else can
    still be appending to are cleared.

    THE HAZARD, and why this is not just "rewrite the directory". Each file in
    agent/worklist/ belongs to a different session, possibly on a different
    machine. Rewriting one that a LIVE peer is appending to loses whatever it
    wrote between this read and this write -- silently, because an append to a
    file that has since been replaced simply lands in the old inode or past the
    truncation point.

    So: the fold is GLOBAL (an item added by one session and ticked by another
    only folds correctly when every file is read), the snapshot is written to
    the compactor's own file, and the ONLY files cleared are this session's own
    and those whose writer is demonstrably not live. A live peer's file is left
    exactly as it is; its events then simply outrank the snapshot's, which is
    correct, because they are the newer truth.

    The snapshot's `add` events carry each item's ORIGINAL `first` timestamp, so
    a straggling event from a peer sorts after them and still wins.
    """
    if root is None:
        root = C.project_root(C.project_start())
    d = store_dir(root)
    try:
        files = sorted(d.glob("*.jsonl"))
    except OSError:
        return
    if not files:
        return
    me8 = agent_session_slug((me or C.resolve_session_id() or "compact")[:8])
    fold = load(worklist, sync=False)
    events = _read_events(worklist, root)
    dead_h = float(os.environ.get("WORKLIST_DEAD_HOURS", "24"))
    keep, clear = [], []
    for f in files:
        writer = f.stem
        if writer == me8 or writer.startswith("_"):
            clear.append(f)
            continue
        verdict, why = session_liveness(worklist, writer, projects_dir, events)
        newest = ""
        for ev in events:
            if str(ev.get("by") or "")[:8] == writer and str(ev.get("at") or "") > newest:
                newest = str(ev.get("at") or "")
        old_enough = True
        if newest:
            try:
                old_enough = (C.utcnow() - C.parse_stamp(newest)).total_seconds() / 3600.0 >= dead_h
            except Exception:  # noqa: BLE001
                old_enough = False
        if verdict in ("idle", "remote", "unknown") and old_enough:
            clear.append(f)
        else:
            keep.append((f, verdict, why))

    payload = snapshot_events(fold, by="compact")
    for ev in payload:
        ev.setdefault("h", host_hash())
    target = writer_path(me8, root)
    with open(events_lock_path(worklist), "w") as lock:
        _flock(lock, LOCK_EX)
        fd, tmp = tempfile.mkstemp(dir=str(d), prefix="compact")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for ev in payload:
                f.write(json.dumps(ev, separators=(",", ":")) + "\n")
        os.replace(tmp, target)
        for f in clear:
            if f == target:
                continue
            with contextlib.suppress(OSError):
                f.unlink()
    print(
        "event log: compacted %d file(s) into %s (%d event(s) for %d item(s))"
        % (len(clear), target.name, len(payload), len(fold.items))
    )
    for f, verdict, why in keep:
        print("  kept %s: writer is %s (%s)" % (f.name, verdict, why))


def doctor(root=None):
    """(problems, files, events) over the tracked store.

    WHAT IT EXISTS TO CATCH, all three of which are silent by default:
      * a merge conflict left in a store file -- `_read_events` skips
        unparseable lines by contract, so `<<<<<<<` costs you events and says
        nothing at all;
      * a torn or garbage line, same silence;
      * a secret-shaped string, which matters now in a way it never did in
        TMPDIR: these files are committed and pushed.
    """
    problems, nfiles, nevents = [], 0, 0
    d = store_dir(root)
    try:
        files = sorted(d.glob("*.jsonl"))
    except OSError as exc:
        return ["cannot read %s (%s)" % (d, exc)], 0, 0
    for f in files:
        nfiles += 1
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            problems.append("%s: unreadable (%s)" % (f.name, exc))
            continue
        for i, line in enumerate(lines, 1):
            if not line.strip():
                continue
            if _CONFLICT_RE.match(line):
                problems.append(
                    "%s:%d: merge conflict marker -- resolve by UNION (keep both "
                    "sides, delete the markers); the fold sorts by timestamp, so "
                    "the union of two histories is a valid history" % (f.name, i)
                )
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                problems.append(
                    "%s:%d: unparseable, so this event is SKIPPED on every read" % (f.name, i)
                )
                continue
            if not isinstance(ev, dict):
                problems.append("%s:%d: not a JSON object" % (f.name, i))
                continue
            nevents += 1
            shapes = secret_shapes_in(line)
            if shapes:
                problems.append(
                    "%s:%d: carries a secret-shaped string (%s) and this file is "
                    "TRACKED -- rotate it, then rewrite the line" % (f.name, i, ", ".join(shapes))
                )
    return problems, nfiles, nevents


def import_legacy(worklist, again=False, root=None):
    """Snapshot the legacy TMPDIR log into the tracked store, once per host.

    THE MOVE IS GAP-FREE WITHOUT THIS, and that is exactly why it is a separate
    verb rather than something that happens on its own. `_read_events` unions
    the legacy file, so every open item keeps blocking from the moment the code
    changes; what the union does NOT do is make that history portable, because
    it lives in TMPDIR on one machine. This is the step that puts it in git.

    Per host, because two machines each have their own TMPDIR log and a shared
    filename would collide; the host hash keeps them apart and the union folds
    both. The legacy file is RENAMED rather than deleted -- an import that got
    something wrong should be recoverable from the bytes it read.
    """
    if root is None:
        root = C.project_root(C.project_start())
    legacy = events_path(worklist)
    if not legacy.exists():
        return None, "no legacy log at %s; nothing to import" % legacy
    target = store_dir(root) / ("_import-%s.jsonl" % host_hash())
    if target.exists() and not again:
        return None, (
            "%s already exists, so this host has been imported; pass --again to "
            "redo it (the existing file is left in place)" % target
        )
    fold = load(worklist, sync=False)
    payload = snapshot_events(fold, by="import")
    for ev in payload:
        ev.setdefault("h", host_hash())
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        for ev in payload:
            f.write(json.dumps(ev, separators=(",", ":")) + "\n")
    moved = legacy.with_suffix(".jsonl.imported-%s" % re.sub(r"[^0-9A-Za-z]", "", C.stamp_now()))
    try:
        legacy.rename(moved)
    except OSError as exc:
        return target, "wrote %s but could NOT rename %s (%s): it is still being read" % (
            target,
            legacy,
            exc,
        )
    return target, "imported %d item(s) and %d lineage edge(s) into %s; legacy log kept at %s" % (
        len([e for e in payload if e.get("ev") == "add"]),
        len(fold.lineage),
        target,
        moved,
    )


def migrate_candidates(worklist, fold, me, projects_dir=None, events=None):
    """Sessions with un-migrated remaining work that are not demonstrably live.

    Returns a list of dicts, richest first: the operator picks from this and
    nothing moves until they do.
    """
    me8 = str(me or "")[:8]
    mine = {me8} | set(fold.aliases_of(me8) if hasattr(fold, "aliases_of") else [])
    if events is None:
        events = _read_events(worklist)
    already = {str((r.get("mg") or {}).get("from") or "") for r in fold.items if r.get("mg")}
    handed = set()
    for ev in events:
        if str(ev.get("ev") or "") == "brief" and ev.get("about"):
            handed.add(str(ev["about"])[:8])

    by_owner = {}
    for rec in fold.items:
        st = rec.get("state", " ")
        if st not in (" ", ">", "?"):
            continue
        owner = str(rec.get("owner") or "")[:8]
        rid = str(rec.get("id") or "")
        if not owner or owner in mine or rid in already:
            continue
        by_owner.setdefault(owner, []).append((rid, rec))

    my_branch = _branch_of(C.project_root(C.project_start()))
    out = []
    for owner, items in by_owner.items():
        verdict, why = session_liveness(worklist, owner, projects_dir, events)
        if verdict in ("live", "unknown"):
            continue
        newest, branch, hh = "", "", ""
        for ev in events:
            if str(ev.get("by") or "")[:8] != owner:
                continue
            at = str(ev.get("at") or "")
            if at > newest:
                newest, branch, hh = at, str(ev.get("br") or ""), str(ev.get("h") or "")
        counts = {"open": 0, "inflight": 0, "deferred": 0}
        for _rid, rec in items:
            counts[{" ": "open", ">": "inflight", "?": "deferred"}[rec["state"]]] += 1
        out.append(
            {
                "prefix": owner,
                "verdict": verdict,
                "evidence": why,
                "counts": counts,
                "newest": newest,
                "branch": branch,
                # AN EVENT WITH NO HOST STAMP IS NOT "ANOTHER HOST". Every
                # event written before the tracked store existed carries no
                # `h`, and calling those foreign would tell the operator a
                # session ran somewhere it did not.
                "host": (
                    "this machine"
                    if hh == host_hash()
                    else ("another host" if hh else "host unrecorded")
                ),
                "handed_off": owner in handed,
                "items": [
                    {"id": rid, "state": rec["state"], "text": brief_text(rec)[:160]}
                    for rid, rec in sorted(items, key=lambda kv: kv[0])
                ],
            }
        )
    out.sort(
        key=lambda c: (
            0 if c["branch"] == my_branch else 1,
            0 if c["host"] == "this machine" else 1,
            c["newest"],
        )
    )
    return out


def migrate_items(worklist, fold, me, prev, projects_dir=None, events=None):
    """Re-tag prev's remaining items to me. (moved, refused) or raises ValueError.

    RE-TAG, not alias: the operator chose it, and it has the property that
    matters here -- after the move the items are MINE, so the Stop hook blocks
    on them exactly as it would on work I typed myself. An alias would have left
    them owned by a session that no longer exists.

    The originals are ticked `[x]` with a note naming the new id. Nothing is
    deleted and nothing is rewritten; both facts stay in an append-only log, so
    the history still says who really did the work.
    """
    me8, prev8 = str(me or "")[:8], str(prev or "")[:8]
    if not me8 or not prev8:
        raise ValueError("both a session and a predecessor are required")
    mine = {me8} | set(fold.aliases_of(me8) if hasattr(fold, "aliases_of") else [])
    if prev8 in mine:
        raise ValueError(
            "%s is already yours (same session, or a proven lineage edge); "
            "there is nothing to migrate" % prev8
        )
    if events is None:
        events = _read_events(worklist)
    verdict, why = session_liveness(worklist, prev8, projects_dir, events)
    if verdict == "live":
        raise ValueError(
            "%s is LIVE here (%s). Migrating would move work out from under a "
            "running session. Re-check with the same rule once it stops." % (prev8, why)
        )
    if verdict == "unknown":
        raise ValueError("no events by %s in the store (%s)" % (prev8, why))

    already = {str((r.get("mg") or {}).get("from") or "") for r in fold.items if r.get("mg")}
    at = C.stamp_now()
    payloads, moved, refused = [], [], []
    for rec in sorted(fold.items, key=lambda r: str(r.get("id") or "")):
        rid = str(rec.get("id") or "")
        if str(rec.get("owner") or "")[:8] != prev8:
            continue
        st = rec.get("state", " ")
        if st not in (" ", ">", "?"):
            continue
        if rid in already:
            refused.append((rid, "already migrated"))
            continue
        text = str(rec.get("text") or "")
        new_id = new_item_id(text + at + rid)
        note = "migrated from #%s (%s)" % (rid, prev8)
        if st == ">":
            # THE LEASE IS NOT CARRIED. Its worker was a background task of the
            # PREVIOUS session, on the previous machine; re-leasing would claim
            # a live worker that cannot exist and stop the liveness ladder from
            # ever asking about it.
            note += "; lease on worker:%s reset by migration" % (rec.get("worker") or "?")
        add = {
            "ev": "add",
            "id": new_id,
            "at": at,
            "by": me8,
            "s": "?" if st == "?" else " ",
            "o": me8,
            "t": text,
            "bt": str(rec.get("basetext") or text),
            "ln": (note + (": " + str(rec.get("lastnote"))) if rec.get("lastnote") else note)[:400],
            "mg": {
                "from": rid,
                "o": prev8,
                "first": str(rec.get("first") or ""),
                "was": st,
                "worker": str(rec.get("worker") or ""),
                "until": str(rec.get("until") or ""),
            },
        }
        if st == "?":
            # THE DEFERRAL WINDOW IS PRESERVED, which is the whole point of
            # carrying `upd`: a [?] whose clock restarted would hand the
            # operator's default another full window before it executes.
            add["upd"] = str(rec.get("upd") or at)
        if rec.get("triage"):
            add["tr"] = rec["triage"]
        if rec.get("just"):
            add["ju"] = rec["just"]
        payloads.append(add)
        payloads.append(
            {
                "ev": "state",
                "id": rid,
                "at": at,
                "by": me8,
                "s": "x",
                "note": "migrated to #%s (%s) by /migrate" % (new_id, me8),
                "mg": {"to": new_id},
            }
        )
        moved.append((rid, new_id, st))
    if payloads:
        payloads.append(
            {"ev": "brief", "by": me8, "about": prev8, "at": at, "t": "handed off to %s" % me8}
        )
        append_events(worklist, payloads, writer=me8)
    return moved, refused


def cleanup_dead_sessions(worklist, fold, session_id, projects_dir):
    """Tombstone dead sessions' items. Markdown lines are flipped to `~` IN
    PLACE (os.pwrite of one byte, v4 discipline: file length only grows, so
    racing appends are safe); CLI-origin items get a `tomb` event. Returns
    (archived_lines, orphaned_lines, changed)."""
    dead_h = float(os.environ.get("WORKLIST_DEAD_HOURS", "24"))
    archive_h = float(os.environ.get("WORKLIST_ARCHIVE_HOURS", "168"))
    archived, orphaned, changed = [], [], False
    ages = {}

    def age_of(owner):
        if owner not in ages:
            ages[owner] = owner_age_hours(owner, projects_dir)
        return ages[owner]

    # CLI-origin items: same policy, expressed as events.
    for rec in fold.items:
        owner = rec["owner"]
        if rec["origin"] != "cli" or owner is None or C.owned_by_me(owner, session_id):
            continue
        age = age_of(owner)
        if age is None or age < dead_h:
            continue
        if rec["state"] == "x" or age >= archive_h:
            tomb_item(
                worklist,
                (session_id or "unknown")[:8],
                rec["id"],
                "owner %s dead ~%dh" % (owner, age),
            )
            archived.append(
                "%s   (was [%s], owner %s dead ~%dh)" % (rec["line"], rec["state"], owner, age)
            )
            changed = True
        else:
            orphaned.append("%s   (owner dead ~%dh)" % (rec["line"], age))

    # Markdown lines: the v4 in-place byte flip, verbatim.
    if worklist.exists():
        data = worklist.read_bytes()
        flips, offset = [], 0
        for raw in data.split(b"\n"):
            line_start, offset = offset, offset + len(raw) + 1
            try:
                line = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            m = C.ITEM.match(line)
            if not m:
                continue
            state, owner = m.group("state"), m.group("owner")
            if owner is None or C.owned_by_me(owner, session_id):
                continue  # untagged or mine: never auto-archived
            age = age_of(owner)
            if age is None or age < dead_h:
                continue  # unknown or alive
            bracket = raw.find(b"[")
            if bracket < 0 or raw[bracket + 1 : bracket + 2] != state.encode():
                continue
            if state == "x" or age >= archive_h:
                flips.append((line_start + bracket + 1, state.encode(), line.strip(), owner, age))
            else:
                orphaned.append("%s   (owner dead ~%dh)" % (line.strip(), age))
        if flips:
            lock_path = str(worklist) + ".lock"
            with open(lock_path, "w") as lock:
                try:
                    _flock(lock, LOCK_EX | LOCK_NB)
                except OSError:
                    return archived, orphaned, changed  # another cleaner holds it
                with open(worklist, "r+b") as f:
                    current = f.read()
                    for pos, expected, text, owner, age in flips:
                        # Re-verify under the lock: offsets of existing lines
                        # never move (no-truncate invariant), but another
                        # cleaner may have flipped this byte already.
                        if len(current) > pos and current[pos : pos + 1] == expected:
                            os.pwrite(f.fileno(), b"~", pos)
                            archived.append(
                                "%s   (was [%s], owner %s dead ~%dh)"
                                % (text, expected.decode(), owner, age)
                            )
                            changed = True
                if changed:
                    stamp = C.stamp_now()
                    note = (
                        "- NOTE cleanup %s: tombstoned %d dead-session item(s) "
                        "(state -> [~]); compact with worklist.py --compact\n"
                        % (stamp, len(archived))
                    )
                    with open(worklist, "a") as f:
                        f.write(note)
    return archived, orphaned, changed


# ---- compact ----------------------------------------------------------------


def compact(worklist):
    """Operator-run. Drops `[~]` markdown lines (the v5 behavior, verbatim:
    exclusive blocking lock, size re-check, atomic replace), then rewrites
    the event log to the minimal set reproducing the current fold, under the
    events lock so appenders serialize against it. The .requests sidecar is
    never touched.

    "Minimal" means minimal EVENTS, not minimal information: the retained `add`
    carries the derived display identity, triage verdict and deferral
    justification forward, because those are folded state that no surviving
    event would otherwise reproduce."""
    tomb = re.compile(r"^\s*-\s*\[~\]")
    if worklist.exists():
        lock_path = str(worklist) + ".lock"
        with open(lock_path, "w") as lock:
            _flock(lock, LOCK_EX)
            done = False
            for _ in range(5):
                data = worklist.read_bytes()
                lines = data.decode("utf-8").splitlines(keepends=True)
                kept = [ln for ln in lines if not tomb.match(ln)]
                dropped = len(lines) - len(kept)
                if dropped == 0:
                    print("nothing to compact: 0 tombstones")
                    done = True
                    break
                fd, tmp = tempfile.mkstemp(dir=str(worklist.parent), prefix=worklist.name)
                with os.fdopen(fd, "w") as f:
                    f.writelines(kept)
                if worklist.stat().st_size == len(data):  # no append landed since read
                    os.replace(tmp, worklist)
                    print("compacted: dropped %d tombstoned line(s)" % dropped)
                    done = True
                    break
                os.unlink(tmp)  # an append raced us; re-read and retry
            if not done:
                print("gave up after 5 attempts: file kept changing (sessions active?)")
    else:
        print("nothing to compact: %s absent" % worklist)

    # Event-log compaction: fold, then rewrite as one snapshot-shaped set.
    ep = events_path(worklist)
    if not ep.exists():
        compact_store(worklist)
        return
    with open(events_lock_path(worklist), "w") as lock:
        _flock(lock, LOCK_EX)
        # sync=False, DELIBERATELY: load(sync=True) takes this same flock on a
        # second fd, and flock conflicts across fds within one process, so a
        # sync here deadlocks against ourselves (found by tracing, missed by
        # case 78 whose fixture had no events file yet; the suite now drives
        # this path with one). The read-only overlay folds any unsynced
        # markdown state in memory, and the rewrite below records it with the
        # current markdown hash, so nothing raced is lost.
        fold = load(worklist, sync=False)
        # ONE SNAPSHOT BUILDER, shared with import_legacy. This was a second
        # hand-rolled copy, and the copies had already diverged in the way that
        # matters: it re-emitted a lease for any item carrying `until`/`worker`,
        # which the fold reads as state ">", so every compaction quietly
        # reopened work that was already done. Measured on this repo's own
        # store while verifying the importer: 39 of 189 items would have
        # flipped from [x] to [>], taking the open count from 5 to 44.
        out = snapshot_events(fold, by="compact")
        fd, tmp = tempfile.mkstemp(dir=str(ep.parent), prefix=ep.name)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for ev in out:
                f.write(json.dumps(ev, separators=(",", ":")) + "\n")
        os.replace(tmp, ep)
        print("events log compacted to %d record(s)" % len(out))


# ---- briefs / loop / agent-state (agent/<session>/STATE.md) -----------------


def read_briefs(worklist):
    """{prefix: (datetime_or_None, text)} from <worklist>.sessions.

    Format, one per line:  <prefix> <ISO8601Z> <=200 chars of what you are doing
    Last line for a prefix wins, so refreshing is an append, never a rewrite --
    the same lost-update discipline the item store uses."""
    p = briefs_path(worklist)
    out = {}
    if not p.exists():
        return out
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    for line in lines:
        parts = line.strip().split(None, 2)
        if len(parts) < 2:
            continue
        prefix, stamp = parts[0], parts[1]
        text = parts[2] if len(parts) > 2 else ""
        out[prefix] = (C.parse_stamp(stamp), text[:SESSION_BRIEF_MAX])
    return out


def brief_state(worklist, session_id, briefs=None):
    """('ok'|'missing'|'stale', minutes_old_or_None, others_text)."""
    briefs = read_briefs(worklist) if briefs is None else briefs
    mine = None
    for prefix, val in briefs.items():
        if session_id and session_id.startswith(prefix):
            mine = val
            break
    others = "\n".join(
        "  %s  %s" % (k, v[1])
        for k, v in sorted(briefs.items())
        if not (session_id and session_id.startswith(k))
    )
    if mine is None:
        return "missing", None, others
    when = mine[0]
    if when is None:
        return "stale", None, others
    age = (C.utcnow() - when).total_seconds() / 60.0
    if age > SESSION_BRIEF_STALE_MIN:
        return "stale", int(age), others
    return "ok", int(age), others


def brief_age_min(worklist, prefix, briefs=None):
    """Minutes since `prefix` last refreshed its .sessions brief, or None if
    it never briefed. Freshest match wins when a short prefix matches
    several -- the conservative direction, as in owner_age_hours."""
    ages = []
    now = C.utcnow()
    briefs = read_briefs(worklist) if briefs is None else briefs
    for k, (when, _text) in briefs.items():
        if C.same_session(k, prefix) and when is not None:
            ages.append((now - when).total_seconds() / 60.0)
    return min(ages) if ages else None


def sole_live_session(worklist, session_id):
    """True iff THIS session is the only one with a fresh .sessions brief.

    Reuses the existing liveness oracle rather than inventing one: the brief
    check forces every live session to refresh within SESSION_BRIEF_STALE_MIN,
    so a stale or absent brief is real absence. No brief at all returns False --
    solitude is unproven, and the brief violation is already firing anyway."""
    now = C.utcnow()
    live = [
        prefix
        for prefix, (when, _t) in read_briefs(worklist).items()
        if when is not None and (now - when).total_seconds() / 60.0 <= SESSION_BRIEF_STALE_MIN
    ]
    return len(live) == 1 and bool(session_id) and session_id.startswith(live[0])


def loop_state(worklist, session_id):
    """('none'|'ok'|'overdue', next_fire_or_None, label, others_text, count).

    HISTORICAL: this record predates the Stop event carrying the full cron
    expansion. `session_crons` now includes each task's schedule AND prompt,
    so the live truth is computable (wl_core.cron_next) and the checks that
    matter prefer it. This declared record survives ONLY
    as the fallback for contexts with no event in hand (the CLI) and for the
    declared-vs-live divergence check; its stamped next-fire goes stale on
    write, which is why nothing reports it when a live schedule is visible."""
    p = loop_path(worklist)
    if not p.exists():
        return "none", None, "", "", 0
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "none", None, "", "", 0
    entries = {}
    for line in lines:
        parts = line.strip().split(None, 2)
        if len(parts) < 2:
            continue
        when = C.parse_stamp(parts[1])
        if when is None:
            continue
        rest = parts[2].split(None, 1) if len(parts) > 2 else []
        count = int(rest[0]) if rest and rest[0].isdigit() else 1
        entries[parts[0]] = (when, rest[1] if len(rest) > 1 else "", count)
    mine = None
    for prefix, val in entries.items():
        if session_id and session_id.startswith(prefix):
            mine = val
            break
    others = "\n".join(
        "  %s  next %s  %s" % (k, v[0].strftime("%H:%MZ"), v[1])
        for k, v in sorted(entries.items())
        if not (session_id and session_id.startswith(k))
    )
    if mine is None:
        return "none", None, "", others, 0
    now = C.utcnow()
    return ("overdue" if mine[0] <= now else "ok"), mine[0], mine[1], others, mine[2]


def agent_state_shape(body):
    """Shape verdict for a STATE.md body not yet on disk: thin | bloated |
    aimless | ok, plus a detail string.

    Extracted so BOTH write paths (`worklist.py --state` and the PreToolUse
    guard) refuse a bad document AT WRITE TIME with the identical rule the Stop
    check reads with. The handover this replaces once accepted any body and let
    the check reject it a stop later; an accept-then-reject asymmetry leaves
    the one artifact designed to survive compaction broken while the session
    believes it is fine.

    `aimless` replaces the old fragmented/paragraph guard, which was an
    explicit proxy for a 600-char cap and counted every markdown heading as a
    paragraph (split on blank lines), which is why the old message had to
    forbid headings outright. Presence of a `## Next action` section is a
    strictly better gate: it targets the one question STATE.md exists to
    answer, and padding cannot satisfy it.

    The subject is ONE SECTION, not the whole document, so the cap is flat
    again (see AGENT_STATE_MAX_CHARS).
    """
    text = (body or "").strip()
    if len(text) < AGENT_STATE_MIN_CHARS:
        return "thin", "%d chars, minimum %d" % (len(text), AGENT_STATE_MIN_CHARS)
    if len(text) > AGENT_STATE_MAX_CHARS:
        return "bloated", "%d chars, maximum %d" % (len(text), AGENT_STATE_MAX_CHARS)
    m = AGENT_NEXT_RE.search(text)
    if not m:
        return "aimless", "no '## Next action' section; the next action IS the value"
    lead, lead_text = agent_next_lead(text, m.end())
    if lead == "wait":
        return "waitled", "the first step is %r; a wait is a CONDITION, not a next action" % (
            lead_text[:70],
        )
    return "ok", "%d chars" % len(text)


def agent_next_lead(text, start):
    """('wait'|'work'|'empty', first_step_text) for the '## Next action' section.

    The FIRST non-blank, non-heading line after the heading is the step that a
    recovered session reads as its instruction, so that is the only line judged.
    A wait mentioned in step 2 or later is fine and often correct; what is
    refused is a wait occupying the position that tells someone what to do.
    """
    for raw in text[start:].splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):  # the next heading: the section held no step
            break
        return ("wait" if AGENT_WAIT_LEAD_RE.match(line) else "work"), line
    return "empty", ""


def agent_state_stamp(epoch):
    """An ISO8601Z heading stamp for `epoch` seconds. Seconds included: the
    staleness threshold is 15 MINUTES and a minute-truncated stamp reads up to
    59 seconds older than the truth, which is exactly the sort of quiet
    off-by-one that makes a boundary case pass for the wrong reason."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


# A stamp this far in the FUTURE is not a stamp, it is a wrong clock. Found on
# the live main-branch STATE.md while driving this code for the first time: a
# session's hand-written heading read 101 minutes ahead, almost certainly local
# time written with a Z. Trusting it would make that section PERMANENTLY fresh,
# which is a strictly worse failure than the unstamped fallback -- the whole
# point of per-section staleness is that a section cannot dodge its own clock.
# So a future stamp is treated exactly like an unparseable one: fall back to the
# file's mtime and record stamped=False, which is the honest answer and which
# the 24-hour reap path still bounds.
AGENT_STATE_FUTURE_SKEW_SEC = 300


def _agent_state_ts(tail, fallback):
    """(epoch, stamped) for a heading tail: the first ISO8601Z stamp anywhere
    in it, else `fallback` with stamped=False. A stamp in the future beyond
    AGENT_STATE_FUTURE_SKEW_SEC is not trusted (see above)."""
    m = AGENT_STATE_TS_RE.search(tail or "")
    if m:
        for fmt in AGENT_STATE_TS_FMTS:
            try:
                ts = calendar.timegm(time.strptime(m.group(0), fmt))
            except ValueError:
                continue
            if ts > time.time() + AGENT_STATE_FUTURE_SKEW_SEC:
                return fallback, False
            return ts, True
    return fallback, False


def agent_state_parse(text, mtime):
    """A STATE.md body -> the ordered list of sections it holds.

    Each section is {"owner", "tail", "ts", "stamped", "body"}: `tail` is the
    heading text after the owner (kept verbatim so a human's annotation
    survives a round trip), `ts` is epoch seconds from the stamp in that tail,
    and `stamped` says whether the stamp was really there.

    NEVER RAISES, and never discards. A document with no headings -- every
    STATE.md written before 2026-08-09, plus anything a raw `cat >` produced --
    becomes ONE section owned by the `legacy` pseudo-owner carrying the whole
    text. Text before the first heading is the same case. Silently dropping
    either would be the loss this whole redesign exists to prevent, arriving
    through the parser instead of through the writer.
    """
    text = text or ""
    heads = list(AGENT_STATE_HEAD_RE.finditer(text))
    sections = []
    preamble = (text[: heads[0].start()] if heads else text).strip()
    if preamble:
        ts, stamped = mtime, False
        sections.append(
            {
                "owner": AGENT_STATE_LEGACY_OWNER,
                "tail": "%s (adopted from a pre-section document)" % agent_state_stamp(mtime),
                "ts": ts,
                "stamped": stamped,
                "body": preamble,
            }
        )
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        tail = m.group(2).strip()
        ts, stamped = _agent_state_ts(tail, mtime)
        sections.append(
            {
                "owner": m.group(1),
                "tail": tail,
                "ts": ts,
                "stamped": stamped,
                "body": text[m.end() : end].strip(),
            }
        )
    return sections


def agent_state_render(sections):
    """The inverse of agent_state_parse, and idempotent on anything this
    program wrote: render(parse(x)) == x for such an x. Order is preserved,
    because a diff between two writes must show exactly one section changed."""
    out = []
    for s in sections:
        head = "## SESSION %s" % s["owner"]
        if s.get("tail"):
            head += " " + s["tail"]
        out.append(head + "\n\n" + (s["body"] or "").strip() + "\n")
    return "\n".join(out)


def agent_state_mine(sections, session_id):
    """This caller's own section, or None.

    C.same_session rather than C.owned_by_me: the CLI passes a short prefix and
    the Stop event carries the full uuid, and either side of this comparison
    can be either. owned_by_me is one-directional, so a session that once wrote
    a longer tag than the prefix it later passes would grow a SECOND section
    for itself -- harmless to peers but a document that nags forever.
    """
    for s in sections:
        if s["owner"] != AGENT_STATE_LEGACY_OWNER and C.same_session(s["owner"], session_id):
            return s
    return None


def agent_state_dead(sections, session_id, projects_dir, now=None):
    """(kept, reaped) under the repo's ONE liveness notion.

    A section is dead when its owner is not the caller AND either the owner's
    newest transcript is at least WORKLIST_DEAD_HOURS old, or the owner has no
    transcript at all (a `legacy` pseudo-owner, or a session whose transcripts
    live on another machine) and the section's OWN stamp is that old. Falling
    back to the section stamp keeps one horizon instead of inventing a second.

    The caller's own section is NEVER reaped, at any age: a session's own stale
    section is a nag, not garbage.
    """
    now = time.time() if now is None else now
    dead_h = float(os.environ.get("WORKLIST_DEAD_HOURS", "24"))
    kept, reaped = [], []
    for s in sections:
        if C.same_session(s["owner"], session_id):
            kept.append(s)
            continue
        age_h = owner_age_hours(s["owner"], projects_dir)
        if age_h is None:
            age_h = (now - s["ts"]) / 3600.0
        (reaped if age_h >= dead_h else kept).append(s)
    return kept, reaped


def agent_state_state(root, session_id="", cur_sig=None, saved_sig=None):
    """('no-dir'|'missing'|'thin'|'bloated'|'aimless'|'stale'|'ok',
    age_min, my_body).

    WHY THIS EXISTS. Compaction silently drops context, and a session lost a
    real operator decision that way: the rediacc-autopilot App had already been
    created, the operator had said so, and after a compact it was reported as
    blocked-on-operator. The transcript is not the recovery mechanism, because
    the thing that failed IS the transcript being summarised.

    Staleness is WORLD-KEYED, unchanged from v10: age alone never stales the
    document; the world signature must also have moved since it was recorded.

    ADOPT-ON-FIRST-SIGHT was forced by the document once being shared.
    `saved_sig is None` used to fall back to pure age and demand a rewrite;
    with a shared document that would order a second session to rewrite what
    the first wrote thirty seconds ago. An unsigned document young enough
    (<= AGENT_STATE_ADOPT_MAX_MIN) is "ok" and the CALLER banks the signature.

    THERE IS NO 'no-branch' VERDICT ANY MORE (2026-08-18). It existed only
    because the document's path needed a branch to resolve, and it made a
    detached HEAD -- which this operator gets on every interactive rebase --
    silently disable the whole check. The path is now keyed on the session
    alone, so the blind case has no cause and the check runs mid-rebase.

    PER-SESSION since 2026-08-09, and this is the half that matters. The
    verdict is about the CALLER'S OWN SECTION and nothing else. Age comes from
    that section's heading stamp, not from the file's mtime, because mtime is
    per FILE while the obligation is per SESSION: a peer's write used to reset
    everyone's clock, so B's stale document read "ok" the moment A wrote, and
    wl_checks then banked A's world signature as B's own. A peer's MALFORMED
    section never blocks me either -- blocking me on a section I must not edit
    leaves deletion as the only way to clear the gate, which is precisely the
    incentive that destroyed a live campaign's document.

    NAMED RESIDUAL, fail-open by at most one peer-write interval: a section
    whose heading carries no parseable stamp (only reachable by a raw
    `cat > STATE.md`, since Write and Edit are both denied) falls back to the
    file's mtime, which is the NEWEST write to the file, so it can read fresher
    than it is. Treating it as permanently stale would nag forever on a
    document the tool did not write; the reap path still bounds it at 24 hours.

    OSError degrades to "missing", which BLOCKS: a permissions problem on
    agent/ must not read as a clean bill.
    """
    # MY OWN directory: since the split each session owns one, and the tool
    # still never creates it (the RULES.md copy-forward is a judgement call). A
    # session joining a checkout a peer already bootstrapped must still make its
    # own, or it would have nowhere to write.
    if not agent_session_dir(root, session_id).is_dir():
        return "no-dir", None, ""
    p = agent_state_path(root, session_id)
    if not p.exists():
        return "missing", None, ""
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        mtime = p.stat().st_mtime
    except OSError:
        return "missing", None, ""
    sections = agent_state_parse(text, mtime)
    mine = agent_state_mine(sections, session_id)
    if mine is None:
        # No section of my own. An UNOWNED preamble is judged as if it were
        # mine, which reproduces the single-session behaviour this file had
        # before sections existed -- including the adopt grace below, and
        # including the stale verdict once that grace runs out. Peers' sections
        # are not adoptable: writing my own costs one command and destroys
        # nothing, so there is no churn to avoid any more.
        mine = next((s for s in sections if s["owner"] == AGENT_STATE_LEGACY_OWNER), None)
        if mine is None:
            return "missing", None, ""
    body = mine["body"]
    age = max(0.0, (time.time() - mine["ts"]) / 60.0)
    verdict, _detail = agent_state_shape(body)
    if verdict != "ok":
        return verdict, int(age), body
    if age <= AGENT_STATE_STALE_MIN:
        return "ok", int(age), body
    if saved_sig is None:
        if age <= AGENT_STATE_ADOPT_MAX_MIN:
            return "ok", int(age), body
        return "stale", int(age), body
    if cur_sig is not None and cur_sig != saved_sig:
        return "stale", int(age), body
    return "ok", int(age), body


def agent_state_briefing(root, session_id, projects_dir=""):
    """(own_body_or_None, peers_rendered, n_live_peers) for PostCompact and for
    the Stop check's peer note.

    Two READS, not one, since the tree split: my own body comes from my own
    directory, and the peers come from the sibling directories beside it. A
    missing or unreadable file of my own must NOT cost me the peer block --
    the two failures are unrelated, and a compacted session with no document
    of its own is exactly the one that most needs to see what else is running.

    Dead sections are SKIPPED here, never removed: a read-only path that
    deletes anything in a peer's directory is the fastest route to the next
    clobber. Only the write path prunes, and only inside its own document.
    """
    mine = None
    p = agent_state_path(root, session_id)
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        mtime = p.stat().st_mtime
    except OSError:
        text, mtime = "", 0.0
    if text:
        sections = agent_state_parse(text, mtime)
        mine = agent_state_mine(sections, session_id)
        if mine is None:
            mine = next((s for s in sections if s["owner"] == AGENT_STATE_LEGACY_OWNER), None)
    live, _dead = agent_state_dead(agent_peer_sections(root, session_id), session_id, projects_dir)
    now = time.time()
    rows = [
        "--- SESSION %s, written %d minutes ago. NOT YOURS: read it, never "
        "rewrite or delete it.\n%s" % (s["owner"], int(max(0.0, (now - s["ts"]) / 60.0)), s["body"])
        for s in live
    ]
    return (mine["body"] if mine else None), "\n\n".join(rows), len(rows)


# ---- world signature --------------------------------------------------------


def world_sig(root, worklist, session_id, fold=None, transcript_path=None):
    """THIS SESSION's world: task statuses + HEAD + the structure of the items
    it owns + the requests that involve it. Keyed by the poll fast path (has
    anything moved since the last full stop?) and by the judge verdict cache.

    v17 (2026-08-04): it used to hash the BYTES of the markdown, the event log
    and the requests file. All three are SHARED across every session in the
    repo, so one teammate's --add, --tick, --lease or --update broke every
    other session's baseline, forfeited their silent poll and invalidated
    their judge cache. Measured on the live store before the fix: 32 of 32
    events in a 3-hour window came from other sessions, polluting 18 of the 36
    five-minute windows -- roughly half of all poll stops paid the full
    battery, plus a paid judge call, for work that was none of their business.
    That is the exact failure the docstring below already argued against for a
    dirty-tree hash, committed one paragraph later against shared files.

    A dirty-tree hash was considered and rejected for the same reason -- other
    sessions edit this tree continuously. Known residual, shared with the
    stuck detector and documented rather than papered over: this session's own
    uncommitted source edits with no task/tick/commit are invisible.

    Nothing foreign that could change this session's OBLIGATIONS is dropped: a
    request addressed to it or broadcast is inside the slice below, and
    poll_fast_path re-checks the inbox, the ladder and the deferral windows
    from artifacts anyway. What is dropped is foreign BOOKKEEPING, which was
    never this session's business.

    An UNOWNED item counts as this session's (C.owned_by_me), matching the
    rule that an untagged item is yours: such an item blocks this session, so
    it must move the signature."""
    ts = C.task_statuses(session_id, transcript_path)
    try:
        f = fold if fold is not None else load(worklist, sync=False)
        items = "|".join(
            "%s:%s:%s"
            % (
                r["id"],
                r["state"],
                hashlib.sha1(
                    str(r.get("basetext") or r.get("text") or "").encode("utf-8", "replace")
                ).hexdigest()[:8],
            )
            for r in sorted(f.items, key=lambda x: x["id"])
            if C.owned_by_me(r.get("owner"), session_id)
        )
    except Exception:  # noqa: BLE001 -- an unreadable store must still yield a stable key
        items = "unreadable"
    blob = "|".join(
        [
            ",".join("%s:%s" % (i, st) for i, (st, _s) in sorted(ts.items())),
            C._git(root, "rev-parse", "HEAD"),
            items,
            my_requests_sig(worklist, session_id),
        ]
    )
    return hashlib.sha1(blob.encode("utf-8", "replace")).hexdigest()[:16]


def my_requests_sig(worklist, session_id):
    """A digest of the request events that involve THIS session, and only
    those. Deliberately parsed here rather than through wl_requests, which
    imports this module: the poll baseline must not depend on an import cycle.

    Two passes, because a follow-up event (answer, ack, decline, escalation)
    carries the request id but not its from/to: pass one collects the ids of
    asks this session sent, was sent, or that were broadcast; pass two hashes
    every event touching one of those ids."""
    p = requests_path(worklist)
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        # An ABSENT file must hash exactly like a file holding only other
        # sessions' traffic, or the first foreign --ask in a repo moves this
        # session's signature and forfeits its silent poll -- the very bug
        # this function exists to close, reintroduced by a sentinel string.
        lines = []
    evs = []
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict):
            evs.append(ev)
    mine = set()
    for ev in evs:
        if ev.get("ev") != "ask":
            continue
        to = str(ev.get("to", "*"))
        if (
            to == "*"
            or C.same_session(to, session_id)
            or C.same_session(str(ev.get("from", "")), session_id)
        ):
            mine.add(str(ev.get("id") or ""))
    blob = "\n".join(
        json.dumps(ev, sort_keys=True, separators=(",", ":"))
        for ev in evs
        if str(ev.get("id") or "") in mine
    )
    return hashlib.sha1(blob.encode("utf-8", "replace")).hexdigest()[:16]


def state_world_sig(root, worklist, session_id, fold=None, transcript_path=None):
    """The STATE.md staleness key (v14 gap 5): task statuses + HEAD + item
    STRUCTURE (id, state, owner, basetext), deliberately NOT the raw byte
    digests world_sig used to take. Under the byte key every self-inflicted
    append (--lease renewal, --update note, --brief) staled the very document
    the session had just refreshed: six near-identical forced rewrites in one
    night. Structure moves when work moves (an item added, ticked, reopened,
    a commit, a task flip), which is exactly when the recovery document
    genuinely needs rewriting.

    Still SEPARATE from world_sig after v17 made that one structural too, but
    NO LONGER by covering every item byte-for-byte. That was the v18 bug: with
    ~48 addressable agents in one worktree, ANY peer's --add/--tick/--state moved
    this key, so a check whose contract is "an unchanged world never stales it"
    degenerated into "fires every 15 minutes" and was indistinguishable from
    wall-clock at the point of observation. A session measured TEN forced
    continuations in one night, several of them this check firing while the
    session was doing exactly what its STATE.md already described.

    The fix is the one v17 already applied to world_sig (see :1519): scope the
    detail to MY items. A peer's bookkeeping is not a reason to rewrite my
    recovery document. But a peer starting a genuinely new program still is, so
    their items survive as a COARSE BUCKET (count//10) rather than as content:
    ten peer items appearing moves the key, one peer ticking one does not.
    Deliberately asymmetric, and the asymmetry is the whole point."""
    ts = C.task_statuses(session_id, transcript_path)
    try:
        f = fold if fold is not None else load(worklist, sync=False)
        mine, peers = [], 0
        for r in sorted(f.items, key=lambda x: x["id"]):
            if C.owned_by_me(r.get("owner"), session_id):
                mine.append(
                    "%s:%s:%s:%s"
                    % (
                        r["id"],
                        r["state"],
                        r.get("owner") or "",
                        hashlib.sha1(
                            str(r.get("basetext") or r.get("text") or "").encode("utf-8", "replace")
                        ).hexdigest()[:8],
                    )
                )
            else:
                peers += 1
        # Peers as a bucket, not as content: a new PROGRAM arriving on the branch
        # still stales the recovery document, a peer's routine tick does not.
        items = "|".join(mine) + "|peers:%d" % (peers // 10)
    except Exception:  # noqa: BLE001 -- an unreadable store must still yield a stable key
        items = "unreadable"
    blob = "|".join(
        [
            ",".join("%s:%s" % (i, st) for i, (st, _s) in sorted(ts.items())),
            C._git(root, "rev-parse", "HEAD"),
            items,
        ]
    )
    return hashlib.sha1(blob.encode("utf-8", "replace")).hexdigest()[:16]
