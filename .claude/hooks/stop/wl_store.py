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
.lastevent-*, .emails, .emailunconf-*, .failwarned, .reaped-*, .agentstate.*)
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
actually write (.events.*, .lastevent-*, .emails, .emailunconf-*, .ciqueue-*,
.waiternudge-*, .failwarned, .reaped-*, .agentstate.*) were absent, so the
list was checked against the code rather than against memory --
grepping the hook directory for with_suffix call sites enumerates the truth.
Add new sidecars HERE when you add them, and keep the parenthesised shape the
parser depends on (no nested parentheses: the parser stops at the first `)`).
The compact-recovery document itself lives in the repo at
.agent/<branch>/STATE.md (gitignored), not in TMPDIR.
"""

try:
    import fcntl
except ImportError:  # Windows: no POSIX advisory locking
    fcntl = None
import calendar
import glob as _glob
import hashlib
import json
import os
import pathlib
import re
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

# The compact-recovery document is `.agent/<branch>/STATE.md` (operator
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


def events_lock_path(worklist):
    return worklist.with_suffix(".events.lock")


def state_path(worklist, session_id):
    return worklist.with_suffix(".state-%s.json" % (session_id or "unknown")[:8])


def briefs_path(worklist):
    return worklist.with_suffix(".sessions")


def loop_path(worklist):
    return worklist.with_suffix(".loop")


def agent_root(root):
    return pathlib.Path(root) / ".agent"


def agent_branch_dir(root, branch):
    return agent_root(root) / branch


def agent_state_path(root, branch):
    return agent_branch_dir(root, branch) / "STATE.md"


def agent_rules_path(root, branch):
    return agent_branch_dir(root, branch) / "RULES.md"


def agent_traps_path(root):
    return agent_root(root) / "TRAPS.md"


def agent_state_lock_path(worklist):
    # In TMPDIR beside the store, NOT under .agent/: the notes tree stays free
    # of machine artifacts, and the lock shares the store's lifetime.
    return worklist.with_suffix(".agentstate.lock")


def agent_state_backup_path(worklist, branch=""):
    """The ONE previous STATE.md, so a clobber is undoable.

    Per-branch last-write-wins is deliberate (see worklist.py --state): a
    document whose contract is "rewrite every time" has no merge semantics.
    What was NOT deliberate is that the loss is permanent. Two live sessions
    share branch 0730-2 today, and 84611aab replaced b9491d9c's 0-minute-old
    document TWICE; both bodies were gone for good, because the event log
    stores worklist item text and never STATE bodies, and the success line
    echoes only the first line back. One backup turns "sorry, rewrite it" into
    a `cp`. Same TMPDIR-beside-the-lock placement, for the same reason.

    BRANCH-SCOPED (review finding 3688784930/3688787780): the slot was one
    file per worklist, so writes on DIFFERENT branches shared it and a
    branch-A write silently destroyed the only copy of branch-B's replaced
    body -- the exact loss the backup exists to prevent. The branch rides
    the suffix; a branchless caller keeps the legacy name.
    """
    if branch:
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(branch))
        return worklist.with_suffix(".agentstate.prev.%s.md" % safe)
    return worklist.with_suffix(".agentstate.prev.md")


def agent_state_reaped_path(worklist, branch=""):
    """APPEND-ONLY archive of sections reaped as dead. Same branch-sanitising
    rule as the backup slot beside it.

    Separate from `.prev` and strictly stronger, because the hazard is
    different. `.prev` covers one generation of a document a session CHOSE to
    replace; reaping deletes a section NOBODY chose to delete, so it appends
    instead of overwriting. One append per dead session per branch, which is
    small enough that unbounded growth is the right trade against ever losing
    the last words of a session that died mid-campaign.
    """
    if branch:
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(branch))
        return worklist.with_suffix(".agentstate.reaped.%s.md" % safe)
    return worklist.with_suffix(".agentstate.reaped.md")


def trap_headings(root):
    """The `## ` heading texts of TRAPS.md, in file order. [] when absent or
    unreadable, never an exception.

    ONLY `##`, never `###`, never body lines: the judge gets TITLES of
    hard-won facts, one line each, because the file is designed to grow
    forever and feeding it whole to a per-stop model call would turn an
    intentionally-growing file into a per-stop cost multiplier. Caps are the
    ceiling if it outgrows what anyone reviews."""
    try:
        text = agent_traps_path(root).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out = []
    for line in text.splitlines():
        if line.startswith("## ") and not line.startswith("### "):
            out.append(line[3:].strip()[:120])
            if len(out) >= 40:
                break
    return out


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


def append_events(worklist, payloads):
    if not payloads:
        return
    _append_lines(events_path(worklist), events_lock_path(worklist), payloads)


def _read_events(worklist):
    p = events_path(worklist)
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue  # torn tail or garbage: skipped by contract
        if isinstance(ev, dict):
            out.append(ev)
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
    """(records, md_keys, cli_ids, last_md_hash). Chronological single pass;
    a later event wins, which is exactly the right answer for the one real
    conflict (a CLI tick vs a later deliberate markdown re-open)."""
    records, md_keys, cli_ids = {}, set(), set()
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
                "basetext": str(ev.get("t", "")),
                "lastnote": "",
                "first": at,
                "upd": at,
                "origin": "cli",
            }
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
    return records, md_keys, cli_ids, last_md_hash


class Fold:
    """One read of the world's items, shared by every consumer of a stop.

    items: live records (state != '~'), each carrying id, state, owner, text,
    line (rendered legacy shape), first/upd stamps, origin, until/worker.
    """

    def __init__(self, items, md_hash):
        self.items = items
        self.md_hash = md_hash
        self.by_id = {r["id"]: r for r in items}

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
        records, md_keys, cli_ids, last_h = _fold_events(events)
        return records, md_keys, cli_ids, last_h

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
    records, md_keys, cli_ids, last_h = build(_read_events(worklist))
    if last_h != md_hash:
        at = C.stamp_now()
        if sync:
            with open(events_lock_path(worklist), "w") as lock:
                _flock(lock, LOCK_EX)
                # Re-fold under the lock: another syncer may have won.
                records, md_keys, cli_ids, last_h = build(_read_events(worklist))
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
                    # public append_events would deadlock re-taking it).
                    fd = os.open(events_path(worklist), os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o644)
                    try:
                        size = os.fstat(fd).st_size
                        blob = b"" if not size or os.pread(fd, 1, size - 1) == b"\n" else b"\n"
                        blob += (json.dumps(ev, separators=(",", ":")) + "\n").encode("utf-8")
                        os.write(fd, blob)
                    finally:
                        os.close(fd)
                    records, md_keys, cli_ids, last_h = build(_read_events(worklist))
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
    return Fold(items, md_hash)


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
    never touched."""
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
        at = C.stamp_now()
        out = []
        md_add = [
            {"k": r["id"], "s": r["state"], "o": r["owner"], "t": r["text"], "at": r["first"]}
            for r in fold.items
            if r["origin"] == "md"
        ]
        out.append({"ev": "md", "at": at, "h": fold.md_hash, "add": md_add})
        for r in fold.items:
            if r["origin"] != "cli":
                continue
            out.append(
                {
                    "ev": "add",
                    "id": r["id"],
                    "at": r["first"],
                    "by": "compact",
                    "s": r["state"],
                    "o": r["owner"],
                    "t": r["text"],
                }
            )
            if r.get("until") or r.get("worker"):
                out.append(
                    {
                        "ev": "lease",
                        "id": r["id"],
                        "at": r["upd"],
                        "by": "compact",
                        "until": r.get("until", ""),
                        "worker": r.get("worker", ""),
                    }
                )
        fd, tmp = tempfile.mkstemp(dir=str(ep.parent), prefix=ep.name)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for ev in out:
                f.write(json.dumps(ev, separators=(",", ":")) + "\n")
        os.replace(tmp, ep)
        print("events log compacted to %d record(s)" % len(out))


# ---- briefs / loop / agent-state (.agent/<branch>/STATE.md) ------------------


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
    if not AGENT_NEXT_RE.search(text):
        return "aimless", "no '## Next action' section; the next action IS the value"
    return "ok", "%d chars" % len(text)


def agent_state_stamp(epoch):
    """An ISO8601Z heading stamp for `epoch` seconds. Seconds included: the
    staleness threshold is 15 MINUTES and a minute-truncated stamp reads up to
    59 seconds older than the truth, which is exactly the sort of quiet
    off-by-one that makes a boundary case pass for the wrong reason."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


# A stamp this far in the FUTURE is not a stamp, it is a wrong clock. Found on
# the live .agent/main/STATE.md while driving this code for the first time: a
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


def agent_state_state(root, branch, session_id="", cur_sig=None, saved_sig=None):
    """('no-branch'|'no-dir'|'missing'|'thin'|'bloated'|'aimless'|'stale'|'ok',
    age_min, my_body).

    WHY THIS EXISTS. Compaction silently drops context, and a session lost a
    real operator decision that way: the rediacc-autopilot App had already been
    created, the operator had said so, and after a compact it was reported as
    blocked-on-operator. The transcript is not the recovery mechanism, because
    the thing that failed IS the transcript being summarised.

    Staleness is WORLD-KEYED, unchanged from v10: age alone never stales the
    document; the world signature must also have moved since it was recorded.

    ADOPT-ON-FIRST-SIGHT was forced by the document becoming per-BRANCH.
    `saved_sig is None` used to fall back to pure age and demand a rewrite;
    with a shared document that would order a second session to rewrite what
    the first wrote thirty seconds ago. An unsigned document young enough
    (<= AGENT_STATE_ADOPT_MAX_MIN) is "ok" and the CALLER banks the signature.

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
    .agent/ must not read as a clean bill.
    """
    if not branch:
        return "no-branch", None, ""
    if not agent_branch_dir(root, branch).is_dir():
        return "no-dir", None, ""
    p = agent_state_path(root, branch)
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


def agent_state_briefing(root, branch, session_id, projects_dir=""):
    """(own_body_or_None, peers_rendered, n_live_peers) for PostCompact and for
    the Stop check's peer note.

    Dead sections are SKIPPED here, never removed: a read-only path that
    mutates the shared document is the fastest route to the next clobber. Only
    the write path reaps.
    """
    if not branch:
        return None, "", 0
    p = agent_state_path(root, branch)
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        mtime = p.stat().st_mtime
    except OSError:
        return None, "", 0
    sections = agent_state_parse(text, mtime)
    mine = agent_state_mine(sections, session_id)
    if mine is None:
        mine = next((s for s in sections if s["owner"] == AGENT_STATE_LEGACY_OWNER), None)
    live, _dead = agent_state_dead(sections, session_id, projects_dir)
    now = time.time()
    rows = []
    for s in live:
        if s is mine:
            continue
        rows.append(
            "--- SESSION %s, written %d minutes ago. NOT YOURS: read it, never "
            "rewrite or delete it.\n%s"
            % (s["owner"], int(max(0.0, (now - s["ts"]) / 60.0)), s["body"])
        )
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
