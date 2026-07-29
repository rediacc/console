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

WHY v5 (2026-07-29, operator request): the hook was working exactly as
specified and the specification measured the wrong queue. It blocks only on
`- [ ]`, and a session that records work as `- [x]` after the fact never has
one. Measured on the session that prompted this: ZERO open items all night,
while the harness Task list carried SIX pending. Every "why are you sitting
there" stop was legal. A supervisor cannot force work it cannot see.

Second cause: the hook speaks through `systemMessage`, which is not the message
the operator reads. Its faithful printing of 24 deferrals never landed as "here
is what remains".

v5 therefore:
  1. READS THE HARNESS TASK LIST (~/.claude/tasks/session-<prefix>/*.json) and
     counts `pending`/`in_progress` as remaining work. One queue, not two.
  2. REQUIRES A `## Remaining` SECTION in the last assistant message whenever
     anything remains, so the report lands in the artifact the operator reads.
  3. REQUIRES EVERY `- [?]` TO CARRY `DEFAULT: <what I do if unanswered>`, which
     turns a deferral into time-boxed autonomy instead of a note.
  4. REQUIRES A <=200 CHAR SESSION BRIEF in <worklist>.sessions, refreshed
     within WORKLIST_BRIEF_STALE_MIN, so concurrent sessions can see each other.
     Six sessions were live in this repo when this was written.
  5. ASKS A MODEL when all of the above pass and work still remains. Static
     checks are cheap and certain; the residual question ("is this stop
     legitimate or is it idling?") is a judgement. Only the quiet stops pay.

NO ESCAPE HATCH (operator, explicit). v1-v4 had MAX_BLOCKS: N blocks then give
up. That is the hatch that let a session stop with six pending tasks, so it is
gone. Judge failure, timeout, or malformed output BLOCKS. If that wedges the
session, the session is not frozen -- `decision: block` means "keep working",
so the primary session can and must fix the bug. A block you can fix is a bug
report with teeth, not a deadlock.

RECURSION, the landmine this design walks past. `claude -p` FIRES THE PROJECT'S
STOP HOOK; proven with a marker hook in an isolated project, it fired. Passing
`--settings '{"hooks":{}}'` does NOT suppress it; it still fired. The only
mitigation that works is the STOPHOOK_CHILD env guard, checked as the very first
statement of main(). Remove it and the hook recurses until the machine dies.

What still allows a stop:
  1. Deleting or emptying the worklist AND having no pending tasks.
  2. Removing the hook from .claude/settings.json.
"""

import datetime
import fcntl
import glob
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

# v5: no cap. See "NO ESCAPE HATCH" above. Kept as a name so the counter file
# (used only to TELL the judge it is repeating itself) reads clearly.
JUDGE_MODEL = os.environ.get("WORKLIST_JUDGE_MODEL", "claude-haiku-4-5-20251001")
# Measured on 2026-07-29 with --json-schema: haiku warm $0.011-$0.026 per call
# at 4.9-20.0s; sonnet $0.231 at 12.1s for the same judgement. Haiku it is.
JUDGE_BUDGET_USD = os.environ.get("WORKLIST_JUDGE_BUDGET_USD", "0.10")
JUDGE_TIMEOUT_S = int(os.environ.get("WORKLIST_JUDGE_TIMEOUT_S", "120"))
JUDGE_DISABLED = os.environ.get("WORKLIST_JUDGE") == "off"
SESSION_BRIEF_MAX = 200
SESSION_BRIEF_STALE_MIN = int(os.environ.get("WORKLIST_BRIEF_STALE_MIN", "90"))
# Heading, any level, so "## Remaining" and "### Remaining work" both count.
REMAINING_HEADING = re.compile(r"^[ \t]{0,3}#{1,4}[ \t]*Remaining\b", re.M | re.I)
DEFAULT_TOKEN = re.compile(r"\bDEFAULT:[ \t]*\S")
TRANSCRIPT_TAIL_BYTES = int(os.environ.get("WORKLIST_TAIL_BYTES", "2000000"))
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


def pending_tasks(session_id):
    """Harness Task-list items that are not done, as [(id, subject), ...].

    THE POINT OF v5. The hook used to see only the markdown worklist, and this
    session kept that at zero open items while six tasks sat pending here. Two
    queues, one supervisor, watching the empty one.

    Never raises: a missing or malformed task dir means "no evidence of pending
    work", which cannot manufacture a block out of nothing.
    """
    if not session_id:
        return []
    home = os.environ.get("WORKLIST_TASKS_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude", "tasks"
    )
    d = os.path.join(home, "session-" + session_id[:8])
    out = []
    try:
        for f in sorted(glob.glob(os.path.join(d, "*.json"))):
            try:
                with open(f, encoding="utf-8") as fh:
                    t = json.load(fh)
            except (OSError, ValueError):
                continue
            if t.get("status") in ("pending", "in_progress"):
                out.append((str(t.get("id", "?")), str(t.get("subject", ""))[:70]))
    except OSError:
        return []
    out.sort(key=lambda x: int(x[0]) if x[0].isdigit() else 1 << 30)
    return out


def transcript_tail(path):
    """(last_assistant_text, tool_names_since_last_user) from the JSONL tail.

    Tail-read, because the transcript is tens of MB and the hook runs on every
    stop. Measured: 2 MB tail + parse is 0.08s / 15 MB RSS on a 36 MB file, so
    this is not the expensive part of anything.
    """
    if not path or not os.path.exists(path):
        return "", []
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - TRANSCRIPT_TAIL_BYTES))
            chunk = f.read()
    except OSError:
        return "", []
    # Drop the first (probably partial) line unless we read from byte 0.
    lines = chunk.split(b"\n")
    if size > TRANSCRIPT_TAIL_BYTES:
        lines = lines[1:]
    last_text, tools, since_user = "", [], []
    for raw in lines:
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        rtype = rec.get("type")
        if rtype == "user":
            # A new operator turn resets what "this turn" means.
            since_user = []
            continue
        if rtype != "assistant":
            continue
        for block in rec.get("message", {}).get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and block.get("text", "").strip():
                last_text = block["text"]
            elif block.get("type") == "tool_use" and block.get("name"):
                since_user.append(block["name"])
    tools = since_user
    return last_text, tools


HANDOVER_STALE_MIN = int(os.environ.get("WORKLIST_HANDOVER_STALE_MIN", "120"))
HANDOVER_MIN_CHARS = 200


def handover_path(worklist, session_id):
    return worklist.with_suffix(".handover-%s.md" % (session_id or "unknown")[:8])


def handover_state(worklist, session_id):
    """('missing'|'thin'|'stale'|'ok', minutes_old_or_None, text).

    WHY THIS EXISTS. Compaction silently drops context, and this session lost a
    real operator decision that way: the rediacc-autopilot App had already been
    created, the operator had said so, and after a compact I reported it as
    blocked-on-operator. The transcript is not the recovery mechanism, because
    the thing that failed IS the transcript being summarised.
    """
    p = handover_path(worklist, session_id)
    if not p.exists():
        return "missing", None, ""
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        age = (time.time() - p.stat().st_mtime) / 60.0
    except OSError:
        return "missing", None, ""
    if len(text.strip()) < HANDOVER_MIN_CHARS:
        return "thin", int(age), text
    if age > HANDOVER_STALE_MIN:
        return "stale", int(age), text
    return "ok", int(age), text


def loop_path(worklist):
    return worklist.with_suffix(".loop")


def loop_state(worklist, session_id):
    """('none'|'ok'|'overdue', next_fire_or_None, label, others_text).

    WHY DECLARED AND NOT DISCOVERED. Measured: cron state lives nowhere on disk.
    `CronList` shows the two live crons for this session, but grepping ~/.claude
    for their ids hits ONLY the transcript, and scanning a 4 MB transcript tail
    for `CronCreate` tool_use records returns ZERO because the calls scrolled out
    long ago. So the hook cannot see the loop, and v3 already settled what to do
    about state the hook cannot see: the session DECLARES it and the hook holds
    it to the declaration.

    That is what catches "the loop stopped and nobody restarted it": a
    declaration whose next fire is in the past is a dead loop, and it blocks.
    """
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
        try:
            when = datetime.datetime.strptime(parts[1], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=datetime.timezone.utc
            )
        except ValueError:
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
        "  %s  next %s  %s" % (k, v[0].strftime("%H:%MZ"), v[1])  # noqa: E501
        for k, v in sorted(entries.items())
        if not (session_id and session_id.startswith(k))
    )
    if mine is None:
        return "none", None, "", others, 0
    now = datetime.datetime.now(datetime.timezone.utc)
    return ("overdue" if mine[0] <= now else "ok"), mine[0], mine[1], others, mine[2]


def briefs_path(worklist):
    return worklist.with_suffix(".sessions")


def read_briefs(worklist):
    """{prefix: (datetime_or_None, text)} from <worklist>.sessions.

    Format, one per line:  <prefix> <ISO8601Z> <=200 chars of what you are doing
    Last line for a prefix wins, so refreshing is an append, never a rewrite --
    the same lost-update discipline the worklist itself uses.
    """
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
        try:
            when = datetime.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=datetime.timezone.utc
            )
        except ValueError:
            when = None
        out[prefix] = (when, text[:SESSION_BRIEF_MAX])
    return out


def brief_state(worklist, session_id):
    """('ok'|'missing'|'stale', minutes_old_or_None, others_text)."""
    briefs = read_briefs(worklist)
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
    age = (datetime.datetime.now(datetime.timezone.utc) - when).total_seconds() / 60.0
    if age > SESSION_BRIEF_STALE_MIN:
        return "stale", int(age), others
    return "ok", int(age), others


JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["stop", "continue"]},
        "reason": {"type": "string", "maxLength": 300},
        "next_action": {"type": "string", "maxLength": 200},
    },
    "required": ["verdict", "reason", "next_action"],
    "additionalProperties": False,
}

JUDGE_PROMPT = """\
You are a stop-gate for an autonomous coding session. Decide ONE thing: is
ending the turn right now legitimate, or is the session idling with work it
could be doing?

Answer "stop" when the session is genuinely blocked: waiting on a CI run or a
background task it has already started, or waiting on a decision only the human
can make. Waiting is legitimate; announcing that it is waiting, repeatedly,
while tracked work sits undone is not.

Answer "continue" when tracked work remains that the session could advance
without the human, or when the last message is a status report that moves
nothing forward.

Be strict about one specific failure: reporting a problem instead of fixing it.
This project's rules say defects found on the way get FIXED, not filed.

Consecutive times this gate has already said continue: %(streak)d. If that number
is above 3, weigh heavily whether your advice is actually actionable.

Remaining work the harness is tracking:
%(remaining)s

Fresh background leases (work genuinely in flight): %(leases)d
Declared loop: %(loop)s

Two things to check specifically, because they are how this session drifts:
  - Does the last message list EVERY open task by id? The operator sees the same
    list in their app, so an omission is a report that disagrees with their view.
  - Does it state the loop schedule, so the operator knows when work resumes?
Answer "continue" if either is missing.

The session's last message:
<<<
%(message)s
>>>

Write `reason` and `next_action` as instructions addressed TO the session.
Never use em dashes. Keep next_action concrete and small enough to do now.
"""


def resolve_claude():
    return shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")


def run_judge(remaining_lines, leases, message, streak, loop_desc):
    """(verdict_dict, error_string). Exactly one is non-None.

    Fail CLOSED by contract: every error path returns an error string, and the
    caller turns that into a block. See "NO ESCAPE HATCH".
    """
    exe = resolve_claude()
    if not exe or not os.path.exists(exe):
        return None, "claude CLI not found (looked at PATH and ~/.local/bin/claude)"
    workdir = pathlib.Path(os.environ.get("TMPDIR", "/tmp")) / "claude-worklist" / ".judge"
    try:
        workdir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return None, "judge workdir unusable: %s" % exc
    prompt = JUDGE_PROMPT % {
        "streak": streak,
        "remaining": "\n".join("  " + r for r in remaining_lines[:20]) or "  (none tracked)",
        "leases": leases,
        "loop": loop_desc,
        "message": (message or "(the session produced no text)")[-6000:],
    }
    env = dict(os.environ)
    # THE RECURSION GUARD. `claude -p` fires this very hook; --settings does not
    # suppress it. Without this line the hook forks itself forever.
    env["STOPHOOK_CHILD"] = "1"
    try:
        proc = subprocess.run(
            [
                exe, "-p", prompt,
                "--output-format", "json",
                "--json-schema", json.dumps(JUDGE_SCHEMA),
                "--model", JUDGE_MODEL,
                "--max-budget-usd", JUDGE_BUDGET_USD,
            ],
            capture_output=True,
            text=True,
            timeout=JUDGE_TIMEOUT_S,
            env=env,
            cwd=str(workdir),
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return None, "judge timed out after %ds" % JUDGE_TIMEOUT_S
    except OSError as exc:
        return None, "judge could not be launched: %s" % exc
    if proc.returncode != 0:
        return None, "judge exited %d: %s" % (proc.returncode, (proc.stderr or "")[-300:])
    try:
        env_out = json.loads(proc.stdout)
    except ValueError:
        return None, "judge returned unparseable stdout: %s" % (proc.stdout or "")[-300:]
    if env_out.get("is_error"):
        return None, "judge reported is_error (subtype=%s, api=%s)" % (
            env_out.get("subtype"),
            env_out.get("api_error_status"),
        )
    out = env_out.get("structured_output")
    if not isinstance(out, dict) or out.get("verdict") not in ("stop", "continue"):
        return None, "judge produced no usable structured_output: %s" % repr(out)[:300]
    return out, None


def main():
    # FIRST STATEMENT, DELIBERATELY. `claude -p` runs this hook again; the guard
    # is the only thing that works (--settings with empty hooks does not).
    if os.environ.get("STOPHOOK_CHILD"):
        sys.exit(0)

    if len(sys.argv) > 1 and sys.argv[1] == "--path":
        print(worklist_for(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--compact":
        compact(worklist_for(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))
        return
    if len(sys.argv) > 2 and sys.argv[1] == "--handover":
        # `... --handover <prefix>` with the document on stdin. Whole-file
        # rewrite is correct here: unlike the worklist this file is per-session,
        # so there is no other writer to race.
        wl = worklist_for(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        body = sys.stdin.read()
        handover_path(wl, sys.argv[2]).write_text(body, encoding="utf-8")
        print("handover written for %s (%d chars)" % (sys.argv[2], len(body)))
        return
    if sys.argv[1:2] == ["--post-compact"]:
        # PostCompact hook: the model has just lost its context. Hand the
        # document straight back as additionalContext so continuity does not
        # depend on it remembering to go looking.
        try:
            ev = json.load(sys.stdin)
        except (json.JSONDecodeError, ValueError):
            ev = {}
        wl = worklist_for(os.environ.get("CLAUDE_PROJECT_DIR") or ev.get("cwd") or os.getcwd())
        sid = ev.get("session_id", "")
        state, age, text = handover_state(wl, sid)
        if state == "missing":
            msg = (
                "CONTEXT WAS JUST COMPACTED and there is NO handover document at %s.\n"
                "Reconstruct one from what survived, write it with\n"
                "    .claude/hooks/stop/worklist.py --handover %s <<'EOF' ... EOF\n"
                "and do NOT report anything as blocked-on-operator until you have "
                "re-checked it: that is exactly the error compaction caused last time."
                % (handover_path(wl, sid), (sid or "unknown")[:8])
            )
        else:
            msg = (
                "CONTEXT WAS JUST COMPACTED. Resume from this handover (%s, %d min old). "
                "Trust it over your summarised memory, and re-verify anything it marks "
                "as decided before calling it blocked:\n\n%s" % (state, age or 0, text)
            )
        emit(
            {
                "systemMessage": "PostCompact: handover %s (%s)" % (state, handover_path(wl, sid).name),
                "hookSpecificOutput": {
                    "hookEventName": "PostCompact",
                    "additionalContext": msg,
                },
            }
        )
    if len(sys.argv) > 3 and sys.argv[1] == "--loop":
        # `worklist.py --loop <prefix> <next-ISO8601Z> <label...>`
        wl = worklist_for(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        # sys.argv[4] is the CRON COUNT the session observed via CronList.
        with open(loop_path(wl), "a", encoding="utf-8") as fh:
            fh.write(
                "%s %s %s %s\n"
                % (
                    sys.argv[2],
                    sys.argv[3],
                    sys.argv[4] if len(sys.argv) > 4 else "1",
                    " ".join(sys.argv[5:]).replace("\n", " ")[:120],
                )
            )
        print("loop declared for %s, next fire %s" % (sys.argv[2], sys.argv[3]))
        return
    if len(sys.argv) > 2 and sys.argv[1] == "--brief":
        # `worklist.py --brief <session-prefix> <text...>` -- append, never
        # rewrite, for the same lost-update reason the worklist itself appends.
        wl = worklist_for(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        prefix = sys.argv[2]
        text = " ".join(sys.argv[3:]).replace("\n", " ").strip()[:SESSION_BRIEF_MAX]
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(briefs_path(wl), "a", encoding="utf-8") as fh:
            fh.write("%s %s %s\n" % (prefix, stamp, text))
        print("brief recorded for %s (%d chars)" % (prefix, len(text)))
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

    # ---- v5: gather EVERY static violation, then emit ONE block -------------
    # Five independent blocking checks would cost five turns to clear, which is
    # the "stuck in a loop" the old MAX_BLOCKS existed to paper over. One
    # pre-flight, one block, every violation named at once.
    judged_ok = None
    tasks = pending_tasks(session_id)
    last_msg, tools_this_turn = transcript_tail(event.get("transcript_path", ""))
    bstate, bage, others_briefs = brief_state(worklist, session_id)
    lstate, lnext, llabel, others_loops, lcrons = loop_state(worklist, session_id)
    hstate, hage, _htext = handover_state(worklist, session_id)

    remaining_lines = (
        ["[ ] " + i for i in open_items]
        + ["task #%s %s" % (i, s) for i, s in tasks]
        + ["[?] " + d for d in deferred]
        + ["[>] " + f for f in in_flight]
    )
    something_remains = bool(remaining_lines)

    violations = []
    if open_items:
        violations.append(
            "%d OPEN worklist item(s). Do the next one, or move it to [?]/[>] with the "
            "state that actually applies:\n%s"
            % (len(open_items), "\n".join("    " + i for i in open_items))
        )
    undefaulted = [d for d in deferred if not DEFAULT_TOKEN.search(d)]
    if undefaulted:
        violations.append(
            "%d deferred item(s) carry no DEFAULT:. A '- [?]' without a default is a "
            "note, not a decision. Append 'DEFAULT: <what you will do if the operator "
            "does not answer>' to each, then execute the default next turn:\n%s"
            % (len(undefaulted), "\n".join("    " + d[:150] for d in undefaulted))
        )
    if bstate != "ok":
        violations.append(
            "session brief is %s%s. Other sessions share this worktree and cannot see "
            "what you are doing. Run:\n"
            "    .claude/hooks/stop/worklist.py --brief %s '<=200 chars: what you are "
            "changing right now>'"
            % (
                bstate,
                "" if bage is None else " (%d min old, limit %d)" % (bage, SESSION_BRIEF_STALE_MIN),
                (session_id or "unknown")[:8],
            )
        )
    if lstate == "overdue":
        violations.append(
            "your declared loop is OVERDUE: next fire was %s (%s). Either it fired and "
            "you did not re-declare, or it died and nobody restarted it -- which is the "
            "exact failure this check exists to catch. Re-declare after you confirm the "
            "cron is alive (CronList):\n"
            "    .claude/hooks/stop/worklist.py --loop %s <next-ISO8601Z> '<label>'"
            % (lnext.strftime("%Y-%m-%dT%H:%M:%SZ"), llabel or "no label", (session_id or "")[:8])
        )
    if something_remains and hstate != "ok":
        violations.append(
            "the compact-recovery handover is %s%s. Compaction has already cost this "
            "project one operator decision (the autopilot App was reported blocked "
            "AFTER the operator had created it), and the transcript cannot be the "
            "recovery mechanism because the transcript is what gets summarised. "
            "Refresh it, >=%d chars, covering where to continue and the latest status:\n"
            "    .claude/hooks/stop/worklist.py --handover %s <<'EOF'\n    ...\n    EOF"
            % (
                hstate,
                "" if hage is None else " (%d min old, limit %d)" % (hage, HANDOVER_STALE_MIN),
                HANDOVER_MIN_CHARS,
                (session_id or "unknown")[:8],
            )
        )
    if lcrons > 1:
        violations.append(
            "you declared %d crons. ONE is almost always enough: a second schedule fires "
            "the same review twice at different phases and each firing costs a turn. "
            "Delete the redundant one with CronDelete, then re-declare with the real "
            "count." % lcrons
        )
    # THE TASK LIST IS THE OPERATOR'S VIEW. They see "23 tasks (17 done, 6 open)"
    # in the app, so a Remaining section that omits one of those six is out of
    # sync with what they are looking at. Every open task id must appear.
    missing_ids = [i for i, _ in tasks if not re.search(r"#%s\b" % re.escape(i), last_msg or "")]
    if tasks and REMAINING_HEADING.search(last_msg or "") and missing_ids:
        violations.append(
            "your Remaining section is OUT OF SYNC with the task list the operator sees. "
            "%d open task(s) are not mentioned by id: %s. List every open task, or close "
            "the ones that are done."
            % (len(missing_ids), ", ".join("#" + i for i in missing_ids))
        )
    if something_remains and not REMAINING_HEADING.search(last_msg or ""):
        violations.append(
            "work remains and your last message has no '## Remaining' section. The "
            "operator reads YOUR message, not this hook's output, so a report that "
            "lives only here does not exist. Re-state the answer and end it with a "
            "'## Remaining' section listing what is left and who it is blocked on:\n%s"
            % "\n".join("    " + r for r in remaining_lines[:12])
        )

    if violations:
        counter.write_text(str(int(counter.read_text()) + 1 if counter.exists() else 1))
        emit(
            {
                "systemMessage": "Stop hook: %d check(s) failed, continuing. %s"
                % (len(violations), violations[0].split("\n")[0][:110]),
                "decision": "block",
                "reason": "Do not stop yet. %d check(s) failed:\n\n%s\n\n"
                "Fix all of them in this turn, then stop. There is no block cap: a "
                "check that fires wrongly is a bug in %s and you are the session that "
                "fixes it."
                % (len(violations), "\n\n".join("  " + v for v in violations), __file__),
            }
        )

    # ---- v5: static checks clean. Ask a model whether stopping is honest. ----
    if something_remains and not JUDGE_DISABLED:
        streak = int(counter.read_text()) if counter.exists() else 0
        verdict, err = run_judge(
            remaining_lines, len(in_flight), last_msg, streak,
            "none declared" if lstate == "none"
            else "%s, next fire %s (%d cron%s)"
            % (llabel or "unlabelled", lnext.strftime("%Y-%m-%dT%H:%M:%SZ"), lcrons,
               "" if lcrons == 1 else "s"),
        )
        if err is not None:
            # FAIL CLOSED, by operator instruction. A judge that cannot answer
            # must not become the way out.
            counter.write_text(str(streak + 1))
            emit(
                {
                    "systemMessage": "Stop hook: judge unavailable (%s). Blocking, per "
                    "no-escape-hatch." % err[:110],
                    "decision": "block",
                    "reason": "The stop-gate judge could not answer: %s\n\n"
                    "This is a BUG in the gate, and blocking is deliberate: a judge that "
                    "fails open is an escape hatch. You are the primary session, so fix "
                    "it now in %s. Diagnose with:\n"
                    "    STOPHOOK_CHILD= claude -p 'reply OK' --output-format json "
                    "--model %s\n"
                    "If the model is simply unreachable and you have verified that, set "
                    "WORKLIST_JUDGE=off in the hook env and say so out loud in your "
                    "summary, so a disabled gate is never silent." % (err, __file__, JUDGE_MODEL),
                }
            )
        judged_ok = verdict["verdict"] == "stop"
        if verdict["verdict"] == "continue":
            counter.write_text(str(streak + 1))
            emit(
                {
                    "systemMessage": "Stop hook: judge says continue (%d in a row). %s"
                    % (streak + 1, verdict["reason"][:110]),
                    "decision": "block",
                    "reason": "The stop-gate judge says this stop is not legitimate.\n\n"
                    "  reason:      %s\n  next action: %s\n\n"
                    "Tracked work:\n%s\n\nDo the next action, then stop."
                    % (
                        verdict["reason"],
                        verdict["next_action"],
                        "\n".join("  " + r for r in remaining_lines[:12]),
                    ),
                }
            )

    if True:
        counter.unlink(missing_ok=True)
        parts = []
        if judged_ok:
            # Never let a paid model call be invisible. A gate that spends money
            # without saying so is indistinguishable from one that is not running.
            parts.append(
                "Stop-gate judge (%s) approved this stop: %s"
                % (JUDGE_MODEL, verdict.get("reason", "")[:200])
            )
        if others_briefs:
            parts.append("Other sessions in this worktree:\n" + others_briefs)
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


main()
