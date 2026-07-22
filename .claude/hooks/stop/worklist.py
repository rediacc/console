#!/usr/bin/env python3
"""Stop hook: refuse to end a turn while the session worklist has open items.

WHY: the failure this prevents is stopping to REPORT a discovery instead of
acting on it.

WHY v2: v1's oracle was `- [ ]`, and I close items by editing that file. The
thing being gated wrote the gate's input, so I closed the last item by ticking
it "cannot be done" on a claim I never probed (docker was right there). A gate
whose subject controls its oracle is not a gate.

v2 does not try to detect a dishonest tick, which is not decidable. It makes the
escape a SEPARATE state the harness reports, so a deferral reaches the operator
through the tool layer instead of through a paragraph in my summary:

    - [ ] open        blocks the stop
    - [x] done        silent
    - [?] deferred    allowed, but printed back to the operator every time
    - [>] in-flight   delegated to BACKGROUND work (agent/task); allowed while
                      its lease is fresh, printed back every time, and blocks
                      again the moment the lease expires

A `- [?]` is a QUESTION, not a footnote. Raise it with AskUserQuestion.

WHY v3 (`- [>]`, 2026-07-22, operator request): v2 had no representation for
"a background agent/task is working this item right now", so a session that
delegated correctly was blocked for doing nothing wrong -- and the block
pushed it toward busywork or premature ticks. The hook cannot SEE harness
background state (a Stop hook gets only the event JSON), so v3 does not
guess: the session declares the delegation with a LEASE it must renew:

    - [>] (5546d4bb) until:2026-07-22T11:30Z docs rewrite -> docs-writer agent

Fail-closed rules: no parseable `until:` token, a lease in the past, or a
lease more than MAX_LEASE_MIN ahead of now all count as OPEN and block. A
lease is a promise to come back, not an exemption.

WHY v4 (dead-session cleanup, 2026-07-22, operator request): items from
crashed or abandoned sessions lingered forever. Cleanup must not rewrite the
file: appenders use lock-less `>>`, and a read-modify-rename would eat any
append that lands in the window (the exact lost-update hazard the file header
warns about). So the automatic path never moves a byte that exists:

    - liveness oracle: newest mtime of <projects-dir>/<owner-prefix>*.jsonl
      (the transcript every live session writes continuously). No matching
      transcript (word labels, foreign machines) = UNKNOWN = never touched.
    - archival = flipping the state byte to `~` IN PLACE (os.pwrite of one
      byte, under a non-blocking flock on <worklist>.lock, after re-reading
      and re-verifying the byte under the lock). File length only ever grows
      (an appended audit NOTE line), so racing `>>` appends are safe, racing
      cleaners are serialized, and a reader at any instant sees a valid file.
    - policy: a DEAD (>WORKLIST_DEAD_HOURS, default 24) session's `[x]` is
      tombstoned immediately; its `[ ]`/`[?]`/`[>]` are REPORTED as orphaned
      until WORKLIST_ARCHIVE_HOURS (default 168), then tombstoned. Unfinished
      work is surfaced for a week before it is archived, never dropped
      silently. `[~]` lines are invisible to the parser.
    - `--compact` (manual, operator-run) physically drops `[~]` lines; it is
      the one op that must rewrite, so it takes the lock, re-checks the file
      size before an atomic replace, and still documents the microscopic
      append race -- run it when sessions are quiet.

STATE: one worklist per PROJECT, at $TMPDIR/claude-worklist/<repo-slug>.md.

    WORKLIST=$(.claude/hooks/stop/worklist.py --path)

Two rejected alternatives, both tried:
  - per USER (v1): every project shared one list. Plainly wrong.
  - per SESSION: isolates concurrent sessions, but the list dies with the
    session. Unfinished work vanishing the moment you restart is the exact
    failure this hook exists to prevent, so session isolation buys the wrong
    thing. Two sessions in one worktree are working on one repo; seeing each
    other's open items is a feature.

Keyed on the git root, so `--path` works from any subdirectory and needs no
argument.

SAFETY, because a Stop hook you cannot escape is worse than no hook:
  1. MAX_BLOCKS consecutive blocks, then it gives up and says so.
  2. Deleting or emptying the worklist allows stopping immediately.
  3. Removing the hook from .claude/settings.json disables it.
The counter resets whenever open items reach zero, so later work gets a fresh
budget.
"""

import datetime
import fcntl
import glob
import json
import os
import pathlib
import re
import sys
import tempfile
import time

MAX_BLOCKS = 25
# Leases beyond this horizon are invalid: a `- [>]` marked "until next year"
# would be a bypass, not a delegation.
MAX_LEASE_MIN = 120
# `- [ ] (5546d4bb) do the thing`  ->  state " ", owner "5546d4bb"
# Owner accepts any word-ish label, not just hex: a named agent tagged items
# "(perf6-daemon)", the old hex-only charset failed to parse it, the item read
# as UNTAGGED, and untagged defaults to mine -- so every OTHER session was
# blocked on that agent's work. Non-prefix labels now parse as owners and are
# reported-never-blocking for everyone (including the labeler: only a tag that
# is a PREFIX of your session id binds you -- use your session prefix if you
# want the hook to hold you to an item).
ITEM = re.compile(r"^\s*-\s*\[(?P<state>[ x?>])\]\s*(?:\((?P<owner>[A-Za-z0-9][A-Za-z0-9._-]*)\)\s*)?")
LEASE = re.compile(r"until:(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?)Z")


def lease_state(line):
    """'fresh' | 'expired' | 'invalid' for a `- [>]` line's until: token."""
    m = LEASE.search(line)
    if not m:
        return "invalid"
    stamp = m.group(1)
    fmt = "%Y-%m-%dT%H:%M:%S" if stamp.count(":") == 2 else "%Y-%m-%dT%H:%M"
    try:
        until = datetime.datetime.strptime(stamp, fmt).replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return "invalid"
    now = datetime.datetime.now(datetime.timezone.utc)
    if until <= now:
        return "expired"
    if until > now + datetime.timedelta(minutes=MAX_LEASE_MIN):
        return "invalid"
    return "fresh"


def owned_by_me(owner, session_id):
    """An UNTAGGED item is mine: that is the safe default, since the cost of
    wrongly claiming one is doing a little extra work, while the cost of wrongly
    disowning one is silently dropping it. A tag is a PREFIX of the session id
    (CLAUDE.md asks for a short prefix, not the whole uuid)."""
    if owner is None:
        return True
    return bool(session_id) and session_id.startswith(owner)


def project_root(start):
    """Nearest ancestor holding .git. This repo uses worktrees, where .git is a
    FILE, not a directory, so test existence rather than is_dir()."""
    p = pathlib.Path(start).resolve()
    for candidate in [p, *p.parents]:
        if (candidate / ".git").exists():
            return candidate
    return p


def worklist_for(start):
    d = pathlib.Path(os.environ.get("TMPDIR", "/tmp")) / "claude-worklist"
    d.mkdir(parents=True, exist_ok=True)
    root = project_root(start)
    slug = re.sub(r"[^A-Za-z0-9._-]", "_", str(root)).strip("_")
    return d / (slug + ".md")


def emit(obj):
    print(json.dumps(obj))
    sys.exit(0)


def owner_age_hours(owner, projects_dir):
    """Hours since the owner's newest transcript write, or None if no
    transcript matches (unknown owner: word label, foreign machine). The
    newest match wins so a short prefix matching several sessions reads as
    the LIVELIEST of them -- the conservative direction."""
    if not owner or not projects_dir:
        return None
    matches = glob.glob(os.path.join(projects_dir, owner + "*.jsonl"))
    if not matches:
        return None
    newest = max(os.path.getmtime(m) for m in matches)
    return (time.time() - newest) / 3600.0


def cleanup_dead_sessions(worklist, session_id, projects_dir):
    """Tombstone dead sessions' items by flipping the state byte to `~` in
    place. Returns (archived_lines, orphaned_lines). Never raises; never
    truncates; never moves an existing byte. See docstring (WHY v4)."""
    dead_h = float(os.environ.get("WORKLIST_DEAD_HOURS", "24"))
    archive_h = float(os.environ.get("WORKLIST_ARCHIVE_HOURS", "168"))
    data = worklist.read_bytes()
    flips, orphaned, offset = [], [], 0
    for raw in data.split(b"\n"):
        line_start, offset = offset, offset + len(raw) + 1
        try:
            line = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        m = ITEM.match(line)
        if not m:
            continue
        state, owner = m.group("state"), m.group("owner")
        if owner is None or owned_by_me(owner, session_id):
            continue  # untagged or mine: never auto-archived
        age = owner_age_hours(owner, projects_dir)
        if age is None or age < dead_h:
            continue  # unknown or alive
        bracket = raw.find(b"[")
        if bracket < 0 or raw[bracket + 1 : bracket + 2] != state.encode():
            continue
        if state == "x" or age >= archive_h:
            flips.append((line_start + bracket + 1, state.encode(), line.strip(), owner, age))
        else:
            orphaned.append("%s   (owner dead ~%dh)" % (line.strip(), age))
    if not flips:
        return [], orphaned

    archived = []
    lock_path = str(worklist) + ".lock"
    with open(lock_path, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return [], orphaned  # another cleaner holds it; next stop retries
        with open(worklist, "r+b") as f:
            current = f.read()
            for pos, expected, text, owner, age in flips:
                # Re-verify under the lock: offsets of existing lines never
                # move (no-truncate invariant), but another cleaner may have
                # flipped this byte already.
                if len(current) > pos and current[pos : pos + 1] == expected:
                    os.pwrite(f.fileno(), b"~", pos)
                    archived.append("%s   (was [%s], owner %s dead ~%dh)" % (text, expected.decode(), owner, age))
        if archived:
            stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
            note = "- NOTE cleanup %s: tombstoned %d dead-session item(s) (state -> [~]); compact with worklist.py --compact\n" % (stamp, len(archived))
            with open(worklist, "a") as f:
                f.write(note)
    return archived, orphaned


def compact(worklist):
    """Operator-run: physically drop `[~]` tombstone lines. The one op that
    rewrites, so: exclusive blocking lock, size re-check before an atomic
    replace, and a documented microscopic race with lock-less appenders --
    run when sessions are quiet."""
    if not worklist.exists():
        print("nothing to compact: %s absent" % worklist)
        return
    lock_path = str(worklist) + ".lock"
    tomb = re.compile(r"^\s*-\s*\[~\]")
    with open(lock_path, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for _ in range(5):
            data = worklist.read_bytes()
            lines = data.decode("utf-8").splitlines(keepends=True)
            kept = [ln for ln in lines if not tomb.match(ln)]
            dropped = len(lines) - len(kept)
            if dropped == 0:
                print("nothing to compact: 0 tombstones")
                return
            fd, tmp = tempfile.mkstemp(dir=str(worklist.parent), prefix=worklist.name)
            with os.fdopen(fd, "w") as f:
                f.writelines(kept)
            if worklist.stat().st_size == len(data):  # no append landed since read
                os.replace(tmp, worklist)
                print("compacted: dropped %d tombstoned line(s)" % dropped)
                return
            os.unlink(tmp)  # an append raced us; re-read and retry
        print("gave up after 5 attempts: file kept changing (sessions active?)")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--path":
        print(worklist_for(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--compact":
        compact(worklist_for(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))
        return

    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        event = {}
    worklist = worklist_for(
        os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd()
    )
    counter = worklist.with_suffix(".blocks")

    session_id = event.get("session_id", "")

    archived, orphaned = [], []
    if worklist.exists():
        # Dead-session cleanup runs before classification so a tombstoned
        # line is invisible to this very pass. Never let it break the gate.
        projects_dir = os.environ.get("WORKLIST_PROJECTS_DIR") or (
            os.path.dirname(event["transcript_path"]) if event.get("transcript_path") else ""
        )
        try:
            archived, orphaned = cleanup_dead_sessions(worklist, session_id, projects_dir)
        except Exception:  # noqa: BLE001 -- cleanup must never break gating
            archived, orphaned = [], []

    lines = worklist.read_text().splitlines() if worklist.exists() else []

    open_items, others, deferred, in_flight = [], {}, [], []
    for line in lines:
        m = ITEM.match(line)
        if not m:
            continue
        state, owner = m.group("state"), m.group("owner")
        mine = owned_by_me(owner, session_id)
        if state == " ":
            if mine:
                open_items.append(line.strip())
            else:
                others.setdefault(owner, []).append(line.strip())
        elif state == "?" and mine:
            deferred.append(line.strip())
        elif state == ">":
            if not mine:
                others.setdefault(owner, []).append(line.strip())
                continue
            ls = lease_state(line)
            if ls == "fresh":
                in_flight.append(line.strip())
            else:
                # Fail closed: an expired or malformed lease is an open item.
                open_items.append(
                    "%s   <- [>] lease %s; finish it, renew the lease, or tick it"
                    % (line.strip(), ls)
                )

    def other_sessions_note():
        if not others:
            return ""
        return "\n".join(
            "  %d open item(s) owned by session %s" % (len(v), k) for k, v in sorted(others.items())
        )

    if not open_items:
        counter.unlink(missing_ok=True)
        parts = []
        if archived:
            parts.append(
                "Worklist: archived %d dead-session item(s) (state -> [~]):\n%s"
                % (len(archived), "\n".join("  " + a for a in archived))
            )
        if orphaned:
            parts.append(
                "Worklist: %d ORPHANED item(s) (owner session dead; auto-archive after %sh):\n%s"
                % (len(orphaned), os.environ.get("WORKLIST_ARCHIVE_HOURS", "168"), "\n".join("  " + o for o in orphaned))
            )
        if in_flight:
            # Allowed to stop, but never silently: the operator sees what is
            # still riding on background work every single time.
            parts.append(
                "Worklist: %d item(s) in flight on background work (lease-fresh):\n%s"
                % (len(in_flight), "\n".join("  " + d for d in in_flight))
            )
        if deferred:
            # The operator sees these even if my summary buries them.
            parts.append(
                "Worklist: %d item(s) deferred rather than done:\n%s"
                % (len(deferred), "\n".join("  " + d for d in deferred))
            )
        if others:
            # Reported, never blocked on. Blocking one session on another's
            # items deadlocks it: it cannot do them without racing live work in
            # the same tree, and it must not tick or delete someone else's
            # tracking. Surfacing beats blocking.
            parts.append("Worklist: nothing open for this session.\n" + other_sessions_note())
        if parts:
            emit({"systemMessage": "\n\n".join(parts)})
        return

    count = int(counter.read_text()) if counter.exists() else 0
    if count >= MAX_BLOCKS:
        counter.unlink(missing_ok=True)
        emit(
            {
                "systemMessage": "Stop hook: hit the %d-block cap with %d item(s) still open in %s. "
                "Letting the turn end so you are not stuck in a loop."
                % (MAX_BLOCKS, len(open_items), worklist)
            }
        )

    counter.write_text(str(count + 1))
    emit(
        {
            # `reason` is fed to the model; only `systemMessage` reaches the
            # operator. v1 set reason alone, so every block was INVISIBLE from
            # the outside: the operator saw a long turn and no explanation of
            # why it kept going. A supervisor nobody can see supervising is
            # indistinguishable from one that is not running.
            "systemMessage": "Stop hook: %d item(s) still open, continuing (block %d/%d). %s%s"
            % (
                len(open_items),
                count + 1,
                MAX_BLOCKS,
                open_items[0][:70],
                ("  [+%d owned by other sessions]" % sum(len(v) for v in others.values()))
                if others
                else "",
            ),
            "decision": "block",
            "reason": "Do not stop yet: %d open item(s) on the session worklist (%s).\n\n%s\n\n"
            "Pick the next open item and do it. Tick with '- [x]' as they land and append what you discover.\n"
            "If an item needs an OPERATOR DECISION, mark it '- [?]' and ask via AskUserQuestion. "
            "If a BACKGROUND agent/task is actively working an item, mark it "
            "'- [>] (prefix) until:<ISO8601>Z <text>' (UTC lease, max %d min ahead, renew on wake) "
            "and the stop is allowed while the lease is fresh. "
            "Do not tick '- [x]' on a claim you have not probed: run the command that proves it first.\n"
            "Block %d of %d."
            % (
                len(open_items),
                worklist,
                "\n".join("  " + i for i in open_items),
                MAX_LEASE_MIN,
                count + 1,
                MAX_BLOCKS,
            )
        }
    )


main()
