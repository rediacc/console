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

The sidecars (.requests, .sessions, .loop, .handover-*, .reggate-*,
.pollbase-*, .pollmark-*, .cistate-*, .cimark-*, .stuck-*, .croncount-*,
.blocks) keep their v5-v9 formats and names: their shapes are pinned by the
suite and by living sessions, and consolidating them buys nothing. New v10
state (liveness ladder, task ages, judge cache, autonomy windows, handover
world-signature) lives in ONE new per-session doc, <worklist>.state-<prefix>.json.
"""

import fcntl
import hashlib
import json
import os
import pathlib
import re
import tempfile
import time

import wl_core as C

SESSION_BRIEF_MAX = 200
SESSION_BRIEF_STALE_MIN = int(os.environ.get("WORKLIST_BRIEF_STALE_MIN", "90"))

# FIFTEEN MINUTES, operator directive 2026-07-30, raised from the ten set on
# 2026-07-29. Since v10 the clock only matters when the WORLD has moved: a
# handover is stale when it is old AND the world signature has changed since
# it was written. The pure-age rule it replaces was outpaced by the 5-minute
# poll cron (a quiet session went stale every other poll and could never take
# the silent path), which was fixing the constant when the KEY was wrong:
# staleness is about the document no longer matching reality, and an unchanged
# world cannot invalidate it.
#
# Why ten was still too tight even world-keyed: a productive turn moves the
# world several times, so the rewrite demand landed mid-task rather than at a
# natural boundary, and each rewrite costs a full round trip against the
# 1500-char budget. Fifteen spans a normal working turn without letting a
# document drift far enough from reality to mislead the session that inherits
# it. It stays an env override so a session with a different cadence can tune
# it without editing code.
HANDOVER_STALE_MIN = int(os.environ.get("WORKLIST_HANDOVER_STALE_MIN", "15"))
HANDOVER_MIN_CHARS = 250
# 1500, operator directive 2026-07-30: the 600 cap burned three rewrites in
# one night (649, 620, 611 chars) before fitting. With the larger budget the
# one-paragraph rule (a proxy for the old cap) relaxes to a fragmentation
# guard: up to 3 paragraphs, because a handoff prompt is still not a report.
HANDOVER_MAX_CHARS = int(os.environ.get("WORKLIST_HANDOVER_MAX_CHARS", "1500"))
HANDOVER_MAX_PARAGRAPHS = 3

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


def handover_path(worklist, session_id):
    return worklist.with_suffix(".handover-%s.md" % (session_id or "unknown")[:8])


def requests_path(worklist):
    return worklist.with_suffix(".requests")


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
        fcntl.flock(lock, fcntl.LOCK_EX)
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            size = os.fstat(fd).st_size
            blob = b""
            if size and os.pread(fd, 1, size - 1) != b"\n":
                blob = b"\n"
            blob += "".join(
                json.dumps(p, separators=(",", ":")) + "\n" for p in payloads
            ).encode("utf-8")
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
        text = line[m.end():].strip()
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
                "first": at,
                "upd": at,
                "origin": "cli",
            }
            cli_ids.add(rid)
        elif kind in ("state", "update", "lease", "tomb"):
            rec = records.get(ev.get("id"))
            if rec is None:
                continue
            if kind == "state":
                rec["state"] = ev.get("s", rec["state"])
                note = str(ev.get("note", "")).strip()
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
                pass  # the stamp bump below is the whole point
            elif kind == "lease":
                rec["state"] = ">"
                rec["until"] = str(ev.get("until", ""))
                rec["worker"] = str(ev.get("worker", ""))
                note = str(ev.get("note", "")).strip()
                if note and note not in rec["text"]:
                    rec["text"] = (rec["text"] + "  " + note).strip()
            elif kind == "tomb":
                rec["state"] = "~"
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
        for k in md_keys - set(parsed):
            dele.append(k)
        return add, chg, dele

    parsed = parse_md_items(md_bytes)
    records, md_keys, cli_ids, last_h = build(_read_events(worklist))
    if last_h != md_hash:
        at = C.stamp_now()
        if sync:
            with open(events_lock_path(worklist), "w") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
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
                    fd = os.open(
                        events_path(worklist), os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o644
                    )
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
                    "id": a["k"], "state": a["s"], "md_s": a["s"], "owner": a["o"],
                    "text": a["t"], "first": at, "upd": at, "origin": "md",
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
        [{"ev": "add", "id": rid, "at": C.stamp_now(), "by": by,
          "s": state, "o": owner if owner is not None else by, "t": text}],
    )
    return rid


def set_state(worklist, by, item_id, state, note="", extra=None):
    ev = {"ev": "state", "id": item_id, "at": C.stamp_now(), "by": by,
          "s": state, "note": note}
    if extra:
        ev.update(extra)
    append_events(worklist, [ev])


def update_item(worklist, by, item_id, note):
    append_events(
        worklist,
        [{"ev": "update", "id": item_id, "at": C.stamp_now(), "by": by, "note": note}],
    )


def lease_item(worklist, by, item_id, until, worker, note=""):
    append_events(
        worklist,
        [{"ev": "lease", "id": item_id, "at": C.stamp_now(), "by": by,
          "until": until, "worker": worker, "note": note}],
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

def classify_items(fold, session_id):
    """(open_items, others, deferred, in_flight) as display strings / recs,
    the v2-v9 state machine unchanged: open blocks, [?] is reported, fresh
    [>] is allowed-and-reported, an expired or invalid lease fails closed
    into an open item."""
    open_items, others, deferred, in_flight = [], {}, [], []
    for rec in fold.items:
        state, owner, line = rec["state"], rec["owner"], rec["line"]
        mine = C.owned_by_me(owner, session_id)
        if state == " ":
            if mine:
                open_items.append(line)
            else:
                others.setdefault(owner, []).append(line)
        elif state == "?" and mine:
            deferred.append(rec)
        elif state == ">":
            if not mine:
                others.setdefault(owner, []).append(line)
                continue
            ls = C.lease_state(line)
            if ls == "fresh":
                in_flight.append(rec)
            else:
                # Fail closed: an expired or malformed lease is an open item.
                open_items.append(
                    "%s   <- [>] lease %s; finish it, renew the lease, or tick it"
                    % (line, ls)
                )
    return open_items, others, deferred, in_flight


# ---- dead-session cleanup (v4, extended to CLI items) -----------------------

def owner_age_hours(owner, projects_dir):
    """Hours since the owner's newest transcript write, or None if no
    transcript matches (unknown owner: word label, foreign machine). The
    newest match wins so a short prefix matching several sessions reads as
    the LIVELIEST of them -- the conservative direction."""
    import glob as _glob
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
            tomb_item(worklist, (session_id or "unknown")[:8], rec["id"],
                      "owner %s dead ~%dh" % (owner, age))
            archived.append("%s   (was [%s], owner %s dead ~%dh)"
                            % (rec["line"], rec["state"], owner, age))
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
            if bracket < 0 or raw[bracket + 1: bracket + 2] != state.encode():
                continue
            if state == "x" or age >= archive_h:
                flips.append((line_start + bracket + 1, state.encode(), line.strip(), owner, age))
            else:
                orphaned.append("%s   (owner dead ~%dh)" % (line.strip(), age))
        if flips:
            lock_path = str(worklist) + ".lock"
            with open(lock_path, "w") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    return archived, orphaned, changed  # another cleaner holds it
                with open(worklist, "r+b") as f:
                    current = f.read()
                    for pos, expected, text, owner, age in flips:
                        # Re-verify under the lock: offsets of existing lines
                        # never move (no-truncate invariant), but another
                        # cleaner may have flipped this byte already.
                        if len(current) > pos and current[pos: pos + 1] == expected:
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
            fcntl.flock(lock, fcntl.LOCK_EX)
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
        fcntl.flock(lock, fcntl.LOCK_EX)
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
            for r in fold.items if r["origin"] == "md"
        ]
        out.append({"ev": "md", "at": at, "h": fold.md_hash, "add": md_add})
        for r in fold.items:
            if r["origin"] != "cli":
                continue
            out.append({"ev": "add", "id": r["id"], "at": r["first"], "by": "compact",
                        "s": r["state"], "o": r["owner"], "t": r["text"]})
            if r.get("until") or r.get("worker"):
                out.append({"ev": "lease", "id": r["id"], "at": r["upd"], "by": "compact",
                            "until": r.get("until", ""), "worker": r.get("worker", "")})
        fd, tmp = tempfile.mkstemp(dir=str(ep.parent), prefix=ep.name)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for ev in out:
                f.write(json.dumps(ev, separators=(",", ":")) + "\n")
        os.replace(tmp, ep)
        print("events log compacted to %d record(s)" % len(out))


# ---- briefs / loop / handover (v5 sidecars, formats unchanged) --------------

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

    WHY DECLARED AND NOT DISCOVERED. Measured: cron state lives nowhere on disk.
    `CronList` shows the live crons, but grepping ~/.claude for their ids hits
    ONLY the transcript, and scanning a 4 MB transcript tail for `CronCreate`
    tool_use records returns ZERO because the calls scrolled out long ago. So
    the hook cannot see the loop; the session DECLARES it and the hook holds it
    to the declaration."""
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


def handover_shape(body):
    """The SHAPE half of handover_state, over a body that is not on disk yet.

    Extracted so `--handover` can refuse a bad document AT WRITE TIME using the
    identical rule the Stop check reads with. It used to accept any body, print
    "handover written", and let the check reject it on the next stop. An
    accept-then-reject asymmetry is worse than a plain bug here: the session is
    told the document is fine, so the one artifact designed to survive
    compaction sits there in a state nothing will fix until a stop happens to
    notice. Measured 2026-07-30: a 1931-char handover was accepted with rc=0
    against a 1500-char limit.

    Shape only. Staleness stays in handover_state, because it needs the file's
    mtime and the world signature, neither of which exists before the write.

    Returns (verdict, detail) with verdict "ok" when the body may be written.
    """
    text = (body or "").strip()
    if len(text) < HANDOVER_MIN_CHARS:
        return "thin", "%d chars, minimum %d" % (len(text), HANDOVER_MIN_CHARS)
    if len(text) > HANDOVER_MAX_CHARS:
        return "bloated", "%d chars, maximum %d" % (len(text), HANDOVER_MAX_CHARS)
    paras = len([b for b in text.split("\n\n") if b.strip()])
    if paras > HANDOVER_MAX_PARAGRAPHS:
        return "fragmented", "%d paragraphs, maximum %d" % (paras, HANDOVER_MAX_PARAGRAPHS)
    return "ok", "%d chars, %d paragraph(s)" % (len(text), paras)


def handover_state(worklist, session_id, cur_sig=None, saved_sig=None):
    """('missing'|'thin'|'bloated'|'fragmented'|'stale'|'ok', age_min, text).

    WHY THIS EXISTS. Compaction silently drops context, and a session lost a
    real operator decision that way: the rediacc-autopilot App had already
    been created, the operator had said so, and after a compact it was
    reported as blocked-on-operator. The transcript is not the recovery
    mechanism, because the thing that failed IS the transcript being
    summarised.

    v10 staleness is WORLD-KEYED: old age alone no longer stales a handover;
    the world signature must also have moved since it was written (see the
    HANDOVER_STALE_MIN comment). A handover with no recorded signature
    (written by an older flow) falls back to the pure-age rule once; the
    rewrite records the signature and the fallback never fires again.
    """
    p = handover_path(worklist, session_id)
    if not p.exists():
        return "missing", None, ""
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        age = (time.time() - p.stat().st_mtime) / 60.0
    except OSError:
        return "missing", None, ""
    body = text.strip()
    if len(body) < HANDOVER_MIN_CHARS:
        return "thin", int(age), text
    if len(body) > HANDOVER_MAX_CHARS:
        return "bloated", int(age), text
    if len([b for b in body.split("\n\n") if b.strip()]) > HANDOVER_MAX_PARAGRAPHS:
        return "fragmented", int(age), text
    if age > HANDOVER_STALE_MIN:
        world_moved = (saved_sig is None) or (cur_sig is not None and cur_sig != saved_sig)
        if world_moved:
            return "stale", int(age), text
    return "ok", int(age), text


# ---- world signature --------------------------------------------------------

def world_sig(root, worklist, session_id):
    """Coarse world signature: task statuses + HEAD + markdown bytes + event
    log bytes + requests bytes. Deliberately the same altitude as the stuck
    detector's signature (tasks + HEAD), plus the shared files, because those
    are the artifacts every other check reads. Known residual, shared with
    the stuck detector and documented rather than papered over: uncommitted
    source edits with no task/tick/commit are invisible. A dirty-tree hash
    was considered and rejected -- other sessions edit this tree
    continuously, so it would break the signature on every poll and turn the
    fast path off in exactly the environment it was built for."""

    def digest(p):
        try:
            return hashlib.sha1(pathlib.Path(p).read_bytes()).hexdigest()
        except OSError:
            return "absent"

    ts = C.task_statuses(session_id)
    blob = "|".join(
        [
            ",".join("%s:%s" % (i, st) for i, (st, _s) in sorted(ts.items())),
            C._git(root, "rev-parse", "HEAD"),
            digest(worklist),
            digest(events_path(worklist)),
            digest(requests_path(worklist)),
        ]
    )
    return hashlib.sha1(blob.encode("utf-8", "replace")).hexdigest()[:16]
