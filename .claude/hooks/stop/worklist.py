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

WHY v6 (cross-session requests, 2026-07-29, operator request): sessions in one
worktree had no way to hand each other work. The motivating case: one session
found check:ci-tutorial-caption-sync failing on 42 combos, and clearing it
needs a regenerate-and-republish owned by a DIFFERENT session; the only
channel was a paragraph in a commit message nobody is obliged to read. v6
adds a request log at <worklist>.requests -- append-only JSONL (ask / answer /
decline / ack / escalate events; state is a fold, never an edit) -- NOT a
fifth worklist state, because a request is a conversation (a body, an answer
with its own body, an acknowledgement) and the worklist protocol can only
flip single bytes in place. No operation deletes or rewrites shared state, so
there is no delete-then-recreate window where it is absent (the cron lesson):
a missing log simply reads as empty, and every transition is an appended
event that supersedes, never replaces, what came before.

Delivery rides INSIDE the block, untruncated. The motivating failure was a
finding written into a commit message: correct, passive, and read by nobody
until the operator relayed it BY HAND. So the request body and the answer
text are carried whole in the block reason -- the one channel a session
cannot end a turn around -- and never behind a pointer to --requests, which
would make reading them a choice again.

    --ask <me> <to|*> <text>   post; * broadcasts when the owner is unknown
    --answer <me> <id> <text>  resolve it
    --decline <me> <id> <why>  a decline IS an answer and must carry a reason
    --ack <me> <id>            the asker closes the loop
    --requests                 inspect the log

Blocking preserves the ownership rule (block only on YOUR obligations):
  - a direct request blocks its RECIPIENT until answered or declined;
  - a broadcast blocks EACH live session only until THAT session answers or
    declines ("not my area") -- never session A on session B's silence;
  - an unacked answer blocks the ASKER, with the answer text in the block
    reason, because the reason is the only channel the asking MODEL actually
    reads (systemMessage goes to the operator); --ack ends it, permanently.
Dead recipients cannot black-hole a request: liveness comes from the
.sessions briefs (every live session is forced to refresh within 90 min),
and an unanswerable request -- dead or never-briefed recipient past a grace
window, a broadcast with no other live session or all of them declined, or
anything unanswered past WORKLIST_REQUEST_STALE_MIN -- is ESCALATED exactly
once, under a flock, into an operator-visible `- [?]` item owned by the
asker, carrying the ask's own DEFAULT: (or a generic proceed-without-it one).

WHY v7 (regression gates, 2026-07-30, operator request): "you fixed but we
didn't have a mechanism for future regressions." A fix without a gate is a
defect scheduled to return, and the i18n cross-locale bug proved it: fixed by
hand, then invisible to every existing check by construction. v7 makes the
judge ask, on every stop where a fix landed, whether a gate protects it.

Detection is from ARTIFACTS, never prose (prose regexes have fired on
messages describing themselves): commit subjects matching ^(fix|revert)[(!:]
between a per-session marker's last-seen HEAD and current HEAD, plus newly
ticked `- [x]` items owned by this session (the uncommitted-tree default).
A fix-set touching only docs/** and **/*.md never asks. Rejected signals:
"check scripts changed" (that is the REMEDY appearing, not the defect) and
"CI red diagnosed" (no cheap unraced view, and reds are often flakes).

Marker: <worklist>.reggate-<prefix8>, single-writer JSON {head, seen_ticks,
fixsets, gate_runs}. A settled fix-set is NEVER re-asked -- the whole cost
story. FAIL SAFE: a missing marker initialises to current HEAD and asks
nothing that stop; a corrupt one does the same plus ONE systemMessage line
saying settled verdicts were forgotten. Never a block, never silent. No
field-wise salvage: any invalid shape discards the file, because half-parsed
fixsets silently resurrect a blocked question as settled.

Every model claim is VERIFIED against artifacts: a named existing gate must
be a real check:* key (a name that is not is hallucinated coverage and counts
as none); a new gate counts as proven only when it is WIRED (a check:ci-* key
reachable from `npm run ci` TRANSITIVELY -- substring matching produced real
false positives) and its bounded run is green (cached by content hash, so a
red gate is not re-run every stop). A green run of a control-first gate IS
the planted-defect proof, because such a gate self-fails when its control
cannot fire; check-i18n-cross-locale.ts once shipped with a --selftest that
NOTHING invoked, which is the failure this proof rule exists for.

Block ONLY on recurring AND ungated AND unproven AND undeferred, naming three
exits: write the gate control-first (next stop proves it), defer as an
operator-visible `- [?] ... reggate:<sig> ... DEFAULT: ...`, or rebut in the
message the judge re-reads next stop. Verdicts: not-applicable | covered |
one-off | proven | deferred.

WHY v8 (2026-07-30, operator request, the last two bundle items):

I7, COMPLETION EVIDENCE. Spike S-2 was marked completed on the strength of a
DIFFERENT spike's evidence; nothing recorded a result anywhere, and a
planning agent found the hole hours later. So a completion claim must leave
a RECORD: a newly ticked `- [x]` must carry evidence in the LINE ITSELF
(file:line that resolves, a hex id naming a real git object, a run id, an
exit code, or a URL), and a harness task flipping to completed must carry
the same near its #id in the message. Deliberately static and shape-based,
NOT a second judge surface: the line is durable where a judge opinion is
not, and every new tick already flows into the v7 regression question for
model-level scrutiny. The known pressure: the stuck detector made an
evidence-free tick the cheapest way to clear a counter, and this check
raises the price of ticking. The honest cost is one paste (at completion
time the sha/run/path is in hand); the routes around it are fabricating a
pointer (must name a REAL object, so it at least points somewhere the
reggate judge can look) or not tracking work at all (the residual risk,
watched by the judge, not solvable statically).

I6, STATIC IDLE DETECTION. Fires on the FIRST stop where nothing can wake
the session: tasks wait, no fresh [>] lease, no running background task, no
cron, and the waiting tasks are not confirmed operator-blocked ('You (User
Thinks So)'). Disjoint from the stuck detector by geometry: stuck is
active-but-futile and needs three stops; idle-with-nothing-inbound may
produce NO further stops, so the counter never reaches its threshold. That
is the Wave C shape, where the operator had to ping because no third stop
was coming. Every static catch also skips a paid judge call.

WHY v9 (2026-07-30, operator request): the cross-session machinery gets a
STATE and a CADENCE.

1. `waiting-cross-session` joins the Remaining-section vocabulary. It means
"blocked on ANOTHER AI SESSION, with a request outstanding", and it must
EARN its place rather than be a synonym for blocked: the line must carry the
#id of an OPEN request THIS session posted via --ask, and the hook verifies
that id against the .requests log (exists, asked by me, not answered, not
escalated). A verified id substitutes for the <path>:<line> citation the
blocked/parked states require, because the request IS the citation -- and it
is a stronger one, since the hook can check its whole lifecycle. An answered
or escalated id fails loudly: the wait is over and the line is stale.

2. A SECOND cron, and a fast path that makes it affordable. The operator
wants a 5-minute inbox poll beside the hourly work loop, so cross-session
requests are answered in minutes, not hours. A cron firing costs a turn and
a turn costs context, so the poll must be near-free when the inbox is empty:

    worklist.py --poll <8-char-prefix>   # empty inbox: prints NOTHING,
                                         # exits 0. Otherwise: the full
                                         # payloads plus the exact commands.

and the STOP of a no-op poll turn is SILENT: no JSON, no systemMessage,
nothing. Recognition is structural, never prose (this file has been burned
by prose regexes): --poll drops a single-use marker file, and the Stop hook
takes the silent exit only when ALL of these hold, each recomputed by the
hook itself and never trusted from the poll:
  - the marker is fresh (POLL_WINDOW_S) -- and it is CONSUMED either way,
    so one poll cannot vouch for two stops, and a marker lingering into an
    operator-facing turn cannot silence that turn's report;
  - the world signature (task statuses + HEAD + worklist bytes + requests
    bytes) equals the one recorded at the last ALLOWED full-battery stop,
    so any tracked work since then forfeits the fast path;
  - that baseline is younger than POLL_FULL_MAX_MIN (default 70): the fast
    path never rewrites the baseline (only a full allowed stop does), so a
    session can be silent for at most ~70 minutes before a poll stop pays
    the full battery again. Polling harder buys nothing.
  - recomputed live: no open [ ] item of mine, no undefaulted [?], no
    expired [>] lease, an EMPTY inbox, nothing pending escalation, and the
    two-cron shape below.
Why this is not the escape hatch the no-escape-hatch rule forbids: every
condition is an artifact the hook reads itself, the failure mode of every
condition is the FULL battery (never a silent allow), and the residual --
a session that truly changed nothing tracked and owes nothing -- is a stop
the full battery would also have allowed, minus checks that are pure
maintenance of unchanged facts (handover mtime, brief mtime, the judge's
same question about the same world). Skipping THOSE on a proven no-op is
the entire point; anything else re-runs.

The cron SHAPE is enforced: a session with any live cron must carry exactly
one poll cron (schedule */5 * * * *, recognised by shape) and at most one
work cron. The poll cron is NOT a wake-up for the I6 idle check -- it wakes
you only when ANOTHER session acts -- except for tasks in a VERIFIED
waiting-cross-session state, where the answer arriving through the poll is
exactly the wake-up. And cron_memory now counts WORK crons only, because
with two crons a dead work loop behind a surviving poll was invisible to
the old high-water count.

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
  3. A VERIFIED no-op inbox-poll stop (WHY v9), silent by design and bounded
     by POLL_FULL_MAX_MIN.
"""

import datetime
import fcntl
import glob
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

# THE MESSAGE CATALOGUE (operator request, 2026-07-30): user-facing prose
# lives in worklist_messages.py so this file stays loadable as LOGIC. The
# import is guarded DELIBERATELY: a top-level ImportError would crash before
# the __main__ fail-closed wrapper exists, print nothing to stdout, and the
# harness would read that as ALLOW -- the exact hole the wrapper closed. So a
# missing or broken catalogue installs a shim whose every attribute access
# raises: query modes that use no messages (--path, --brief, an empty --poll)
# keep working, and the first message USE on the Stop path raises into the
# crash handler, which BLOCKS carrying the real traceback. Fails closed,
# names itself, never wedges the plumbing.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import worklist_messages as M
except Exception as _catalogue_exc:  # noqa: BLE001 -- must not become an allow

    class _BrokenCatalogue:
        err = "%s: %s" % (type(_catalogue_exc).__name__, _catalogue_exc)

        def __getattr__(self, name):
            raise RuntimeError(
                "message catalogue worklist_messages.py is unusable (%s); "
                "wanted %s" % (self.err, name)
            )

    M = _BrokenCatalogue()

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
                out.append(
                    (str(t.get("id", "?")), str(t.get("subject", ""))[:70], t.get("status"))
                )
    except OSError:
        return []
    out.sort(key=lambda x: int(x[0]) if x[0].isdigit() else 1 << 30)
    return out


def transcript_tail(path, want=None, tries=6, delay=0.25):
    """(last_assistant_text, tool_names_since_last_user, readable) from the tail.

    THE RACE THIS RIDES OUT, found the hard way: the gate blocked a message that
    DID carry its `## Remaining` heading. Re-reading the transcript afterwards
    showed the heading present in a single text block, so the extraction was
    fine and the file simply had not been flushed when the hook ran. A check that
    reads the transcript to judge the message that just ended is racing the
    writer, so when `want` is absent it retries briefly before believing it.

    `readable` distinguishes "I read the message and the heading is absent" from
    "I could not read any assistant text at all". Those need different verdicts:
    the first is the session's fault, the second is this hook's.

    Tail-read, because the transcript is tens of MB and the hook runs on every
    stop. Measured: 2 MB tail + parse is 0.08s / 15 MB RSS on a 36 MB file, so
    this is not the expensive part of anything.
    """
    if not path or not os.path.exists(path):
        return "", [], False
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - TRANSCRIPT_TAIL_BYTES))
            chunk = f.read()
    except OSError:
        return "", [], False
    # Drop the first (probably partial) line unless we read from byte 0.
    lines = chunk.split(b"\n")
    if size > TRANSCRIPT_TAIL_BYTES:
        lines = lines[1:]
    turn_texts, since_user = [], []
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
            turn_texts = []
            continue
        if rtype != "assistant":
            continue
        for block in rec.get("message", {}).get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and block.get("text", "").strip():
                # EVERY narration line before a tool call is its own text block,
                # so the LAST block mid-turn is a one-liner, not the answer. That
                # is what made this check fire on a message that did carry its
                # heading. Judge the whole turn's output instead.
                turn_texts.append(block["text"])
            elif block.get("type") == "tool_use" and block.get("name"):
                since_user.append(block["name"])
    last_text = "\n\n".join(turn_texts)
    readable = bool(last_text)
    if want is not None and readable and want.search(last_text) is None and tries > 1:
        # Not there yet. Give the writer a moment rather than calling the session
        # a liar about a message it actually wrote.
        time.sleep(delay)
        return transcript_tail(path, want, tries - 1, delay)
    return last_text, since_user, readable


# TEN MINUTES, operator directive 2026-07-29. 120 was chosen to keep the write
# cheap, which was optimising the wrong thing: compaction does not wait for a
# convenient moment, so the only useful handover is one that is true RIGHT NOW.
# At this limit it gets rewritten most turns, and that is the intended cost -- a
# 560-character write against losing an operator decision, which has already
# happened once (the autopilot App reported blocked AFTER it was created).
HANDOVER_STALE_MIN = int(os.environ.get("WORKLIST_HANDOVER_STALE_MIN", "10"))
# Consecutive stops that may move nothing before the hook demands a planning or
# investigation agent. Three is the operator's number, not a guess.
STUCK_ROUNDS = int(os.environ.get("WORKLIST_STUCK_ROUNDS", "3"))
HANDOVER_MIN_CHARS = 250
HANDOVER_MAX_CHARS = 600


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
    body = text.strip()
    if len(body) < HANDOVER_MIN_CHARS:
        return "thin", int(age), text
    if len(body) > HANDOVER_MAX_CHARS:
        return "bloated", int(age), text
    if "\n\n" in body:
        return "multi-paragraph", int(age), text
    if age > HANDOVER_STALE_MIN:
        return "stale", int(age), text
    return "ok", int(age), text


DESIGN_DOCS = os.environ.get("WORKLIST_DESIGN_DOCS", "docs/ci-overhaul")
DOCS_DRIFT_MAX = int(os.environ.get("WORKLIST_DOCS_DRIFT_MAX", "10"))
# What counts as "the program surface": changing these is changing the thing the
# design docs describe.
PROGRAM_SURFACE = os.environ.get("WORKLIST_PROGRAM_SURFACE", ".ci .github .claude").split()


def _git(root, *args):
    try:
        r = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=20
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def docs_drift(root):
    """(state, drift_commits, docs_dir) -- how far the code has moved past the docs.

    THE FAILURE THIS CATCHES, measured on the session that asked for it: 44
    commits touching .ci/.github/.claude since the design docs were last updated.
    Those documents are how a NEW or freshly-compacted session understands what
    is being built and why, so code moving without them does not merely leave
    stale prose behind, it deletes the next session's starting context.

    'absent' when there is no such directory, so the check scopes itself to
    projects that actually keep design docs and says so rather than passing
    quietly.
    """
    docs = pathlib.Path(root) / DESIGN_DOCS
    if not docs.is_dir():
        return "absent", 0, str(docs)
    last_docs = _git(root, "log", "-1", "--format=%H", "--", DESIGN_DOCS)
    base = last_docs or _git(root, "merge-base", "HEAD", "origin/main")
    if not base:
        return "absent", 0, str(docs)
    n = _git(root, "rev-list", "--count", "%s..HEAD" % base, "--", *PROGRAM_SURFACE)
    drift = int(n) if n.isdigit() else 0
    return ("drifted" if drift > DOCS_DRIFT_MAX else "ok"), drift, str(docs)


def publish_divergence(root):
    """(state, count, ref) -- has the branch we publish to moved without us?

    OPERATOR'S RULE, "do not trust, verify". This session commits on a LOCAL
    branch and publishes with `git push origin HEAD:<other-branch>`, so the two
    names can diverge silently: another session, or a merge on the remote, puts
    commits on the published ref that local HEAD does not contain, and the next
    push either fails confusingly or publishes over work nobody looked at.

    The dangerous direction is remote-ahead. Local-ahead is just unpushed work.
    """
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if not branch or branch == "HEAD":
        return "unknown", 0, ""
    # The published ref is whatever the PR is on; default to the sibling name the
    # session pushes to, overridable for other setups.
    target = os.environ.get("WORKLIST_PUBLISH_REF", "")
    if not target:
        return "unset", 0, ""
    ref = "origin/%s" % target
    if not _git(root, "rev-parse", "--verify", "--quiet", ref):
        return "missing", 0, ref
    n = _git(root, "rev-list", "--count", "%s" % ref, "^HEAD")
    ahead = int(n) if n.isdigit() else 0
    if ahead:
        return "diverged", ahead, ref
    # THE SECOND TRAP, found by a verification agent rather than by reasoning: a
    # LOCAL branch sharing the publish target's name, left behind by an earlier
    # rename. Nothing in the publish flow touches it, so it rots invisibly; the
    # cost lands on whoever checks it out next and pushes from a stale base.
    if _git(root, "rev-parse", "--verify", "--quiet", target):
        behind = _git(root, "rev-list", "--count", ref, "^%s" % target)
        unique = _git(root, "rev-list", "--count", target, "^%s" % ref)
        if behind.isdigit() and int(behind) > 0:
            return "stale-local", int(behind), "%s (local, %s unique)" % (target, unique or "?")
    return "ok", 0, ref


def pr_body_freshness(root):
    """(state, detail) -- did we push after the last PR-description edit?

    FAIL FAST TO SAVE A CI ROUND. `Quality / Static` runs a PR-description
    freshness gate, and the cost of failing it is a full ~55-minute round for a
    mistake that takes ten seconds to fix. This session has made it twice, both
    times by treating the body refresh as a separate step instead of part of the
    push, which its own memory says not to do.

    Scoped to WORKLIST_PUBLISH_REF, so a session that has not opted in pays
    nothing. When it IS set and the lookup fails, that is reported as a hook-side
    inability rather than passing quietly.
    """
    target = os.environ.get("WORKLIST_PUBLISH_REF", "")
    if not target:
        return "unset", ""
    tip = _git(root, "log", "-1", "--format=%cI", "origin/%s" % target)
    if not tip:
        return "no-ref", "origin/%s" % target
    # GRAPHQL, NOT `gh pr list --json lastEditedAt`. That field does not exist on
    # `pr list` OR on `pr view` -- both error out and print the valid-field list.
    # This check found that itself on its first run, by reporting the failure as
    # a blind read instead of passing quietly, which is the whole argument for
    # making blindness its own verdict.
    slug = _git(root, "config", "--get", "remote.origin.url")
    m = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?$", slug or "")
    if not m:
        return "unreadable", "could not derive owner/name from %r" % slug
    query = (
        '{repository(owner:"%s",name:"%s"){pullRequests('
        'headRefName:"%s",states:OPEN,first:1){nodes{number lastEditedAt updatedAt}}}}'
        % (m.group(1), m.group(2), target)
    )
    try:
        out = subprocess.run(
            ["gh", "api", "graphql", "-f", "query=" + query],
            capture_output=True, text=True, timeout=25, cwd=str(root),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return "unreadable", str(exc)[:120]
    if out.returncode != 0:
        return "unreadable", (out.stderr or "")[-120:]
    try:
        rows = json.loads(out.stdout)["data"]["repository"]["pullRequests"]["nodes"]
    except (ValueError, KeyError, TypeError):
        return "unreadable", "graphql response had no pullRequests.nodes"
    if not rows:
        return "no-pr", target
    pr = rows[0]
    edited = pr.get("lastEditedAt") or pr.get("updatedAt") or ""
    if not edited:
        return "unreadable", "PR carries neither lastEditedAt nor updatedAt"

    def parse(ts):
        try:
            return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None

    t_commit, t_edit = parse(tip), parse(edited)
    if t_commit is None or t_edit is None:
        return "unreadable", "could not parse %r / %r" % (tip, edited)
    if t_commit > t_edit:
        return "stale", "PR #%s body edited %s, tip pushed %s" % (
            pr.get("number", "?"),
            t_edit.strftime("%H:%M:%SZ"),
            t_commit.strftime("%H:%M:%SZ"),
        )
    return "ok", ""


def stuck_rounds(worklist, session_id, tasks, head, exempt):
    """(count, fired, why) -- how many consecutive stops have moved NOTHING?

    THE OPERATOR'S RULE, IN THEIR WORDS: "I'd go with employing a
    planning/investigation agent if we cannot solve in last 3 round." Three
    identical stops means the APPROACH is wrong, not that it deserves a fourth
    attempt. The remedy is prescribed rather than left open, because "try
    harder" is what a stuck session already believes it is doing.

    It generalises past any single failure. It covers the eleven consecutive
    self-cancelled CI runs (three rounds of pushing with nothing learned), and
    it covers the Wave C sit (three stops reporting the same blocker nobody had
    verified), without needing a separate detector for either.

    The signature is deliberately COARSE: the harness task list plus HEAD. A
    commit moves it, ticking a task moves it, changing a task's status moves
    it. Talking does not. That is the point, since every one of the failures
    this catches involved a session that was producing text and no artifacts.

    It fires and then RESETS, so it nags at 3, 6, 9 rather than every stop once
    stuck. A session needs room to actually run the agent it was told to run,
    and a check that fires forever is one the session learns to route around.

    TWO TIERS, because a single signature can be bought off. The first version
    of this shipped with a DEAD head leg (it resolved the repo from the
    worklist's own tmp directory, so git returned nothing and the docstring's
    "a commit moves it" was false for every real stop). Fixing that naively
    would have been worse than the bug: any commit, including a one-line doc
    tweak, would reset the counter, so the commit-trivia treadmill and the
    eleven-push storm would both escape. So:

      * TASKS-ONLY signature, threshold 2x. Commits cannot touch it. This is
        what catches a session committing noise while the real problem sits.
      * TASKS+HEAD signature, threshold 1x. Real progress resets this sooner.

    Commits buy slack, never immunity.

    `exempt` (a live background task) suppresses the ordinary fire, because the
    remedy is already running. It does NOT stop the counting: a watch left
    running forever would otherwise silence this permanently, so at 3x the
    threshold it fires anyway to say the remedy itself has stalled.
    """
    # tasks are (id, subject, status); the STATUS is what has to move.
    base = "|".join(sorted("%s:%s" % (i, st) for i, _, st in tasks))

    def dig(s):
        return hashlib.sha1(s.encode("utf-8", "replace")).hexdigest()[:12]

    sigs = (dig(base), dig(base + "#" + (head or "")))
    p = worklist.with_suffix(".stuck-%s" % (session_id or "unknown")[:8])
    try:
        parts = p.read_text().strip().split()
        prev, counts = (parts[0], parts[1]), [int(parts[2]), int(parts[3])]
    except (OSError, ValueError, IndexError):
        prev, counts = ("", ""), [0, 0]
    counts = [c + 1 if sigs[i] == prev[i] else 1 for i, c in enumerate(counts)]

    # thresholds: tasks-only is slower to fire, tasks+HEAD is the normal one
    limits = (STUCK_ROUNDS * 2, STUCK_ROUNDS)
    hit = [i for i in (0, 1) if counts[i] >= limits[i]]
    why = ""
    if hit and exempt:
        # A running agent excuses the ordinary fire, but not forever.
        hit = [i for i in hit if counts[i] >= limits[i] * 3]
        why = "exempt-overrun" if hit else ""
    elif hit:
        why = "tasks-only" if 0 in hit else "tasks+head"
    fired = bool(hit)
    try:
        p.write_text(
            "%s %s %d %d"
            % (sigs[0], sigs[1], *[0 if i in hit else counts[i] for i in (0, 1)])
        )
    except OSError:
        pass
    return max(counts), fired, why


CITE_RE = re.compile(
    # LEADING DOT ALLOWED. `\b[\w]` cannot start on a dot, so `.ci/x.sh:9`
    # matched but CAPTURED `ci/x.sh`, which resolves to nothing on disk. That
    # silently excluded `.ci/`, `.github/` and `.claude/`, which is most of this
    # program's surface: a citation check that looked strict was unsatisfiable
    # for exactly the paths it most needed to accept. Caught by the check firing
    # on a tick of mine that cited .ci/scripts/autopilot/autopilot-gate.sh.
    r"(?<![\w./-])(\.?[\w][\w./-]*\.(?:py|ts|tsx|js|cjs|mjs|sh|json|md|ya?ml|go|toml))"
    r":(\d+)(?:-\d+)?\b"
)


def citation_state(root, text):
    """(ok, detail) -- does this line cite a source that REALLY says so?

    The Wave C failure was a blocker nobody had verified: "blocked on Wave B
    landing", when 05-execution-guide.md:108 says the opposite in plain words.
    Nothing in the hook challenged it, because the shape of the report was
    valid and only its content was wrong.

    Requiring a <path>:<line> is not bureaucracy, it is a FORCING FUNCTION:
    producing the citation means opening the file, and opening that file is the
    exact moment the claim collapses. So the check is deliberately cheap and
    deliberately not clever. It proves the file exists and the line is real,
    nothing more. Whether the cited text actually SUPPORTS the claim is the
    judge's question, and the citation is what lets the judge read it.
    """
    m = CITE_RE.search(text or "")
    if not m:
        return False, "carries no <path>:<line> citation"
    rel, line = m.group(1), int(m.group(2))
    p = pathlib.Path(root) / rel
    if not p.is_file():
        return False, "cites %s, which does not exist" % rel
    try:
        n = len(p.read_text(errors="replace").splitlines())
    except OSError:
        return False, "cites %s, which cannot be read" % rel
    if line > n:
        return False, "cites %s:%d but that file has only %d lines" % (rel, line, n)
    return True, "%s:%d" % (rel, line)


def cited_excerpts(root, message, limit=3, span=4):
    """Quote what the session cited, so the judge can check it rather than guess.

    The citation check (citation_state) only proves a source EXISTS. That is the
    cheap half, and on its own it is gameable: any real file and any in-range
    line satisfies it, including one that says the opposite of the claim. This
    supplies the text so the expensive half can happen in the judge, which is
    already being paid for on quiet stops.

    Bounded on purpose. At most `limit` citations, +/- `span` lines each, so the
    prompt grows by a few hundred tokens rather than with the size of the
    program. Whole-document injection was considered and rejected: docs/ alone
    is thousands of lines and the cost would scale with the repo.
    """
    out, seen = [], set()
    for m in CITE_RE.finditer(message or ""):
        rel, line = m.group(1), int(m.group(2))
        if (rel, line) in seen:
            continue
        seen.add((rel, line))
        p = pathlib.Path(root) / rel
        try:
            lines = p.read_text(errors="replace").splitlines()
        except OSError:
            continue
        if line > len(lines):
            continue
        lo, hi = max(0, line - 1 - span), min(len(lines), line + span)
        body = "\n".join(
            "    %s%d| %s" % (">" if n == line else " ", n, lines[n - 1])
            for n in range(lo + 1, hi + 1)
        )
        out.append("  %s:%d\n%s" % (rel, line, body))
        if len(out) >= limit:
            break
    return "\n".join(out)


def cron_memory(worklist, session_id, live_count):
    """(died, remembered_max) -- was a loop running before that is gone now?

    WHY THIS REPLACED A DECLARATION. v5 first made the session declare its next
    cron fire and blocked when that timestamp went stale. That check fired on its
    author twice: once on genuinely bad date arithmetic, and once simply because
    the loop had fired and the declaration had not been renewed yet. The second
    is not a defect, it is the design demanding maintenance of a fact the harness
    already reports.

    `session_crons` in the Stop event is authoritative, so the only thing worth
    remembering is the HIGH-WATER count. A session that once had a cron and now
    has none has lost its loop, which is the failure the operator actually cares
    about ("sometimes you stop the hourly loop and never start it again"). A
    session that never had one is not doing anything wrong.

    v9: the caller passes the WORK-cron count, not the total. With the
    5-minute poll enforced, a total-count high-water mark would read a dead
    work loop behind a surviving poll as "still has a cron" -- exactly the
    loss this check exists to catch.
    """
    p = worklist.with_suffix(".croncount-%s" % (session_id or "unknown")[:8])
    try:
        remembered = int(p.read_text().strip())
    except (OSError, ValueError):
        remembered = 0
    if live_count > remembered:
        try:
            p.write_text(str(live_count))
        except OSError:
            pass
        remembered = live_count
    return (remembered >= 1 and live_count == 0), remembered


def next_fire(expr):
    """Best-effort next UTC fire for the simple 'M H|* * * *' shapes we use.

    Deliberately not a cron parser. Anything it does not recognise is returned as
    the raw expression, because a wrong timestamp is worse than an honest one.
    """
    parts = (expr or "").split()
    if len(parts) != 5 or not parts[0].isdigit() or parts[1] != "*":
        return expr or "?"
    minute = int(parts[0])
    now = datetime.datetime.now(datetime.timezone.utc)
    nxt = now.replace(minute=minute, second=0, microsecond=0)
    if nxt <= now:
        nxt += datetime.timedelta(hours=1)
    return nxt.strftime("%Y-%m-%dT%H:%M:%SZ")


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


# ---- v6: cross-session requests -------------------------------------------
REQUEST_BODY_MAX = 1000
# Same charset the worklist owner tag accepts, so a request's from/to can be
# written into a `- [?]` line on escalation without re-validation.
PREFIX_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")


def requests_path(worklist):
    return worklist.with_suffix(".requests")


def same_session(a, b):
    """Two prefixes/ids denote one session when either is a prefix of the
    other. Symmetric, because CLI callers pass short prefixes while the Stop
    event carries the full id, and either side of a comparison can be either."""
    return bool(a) and bool(b) and (a.startswith(b) or b.startswith(a))


def append_request_event(worklist, obj):
    """One event = one full line = ONE write() on an O_APPEND handle, taken
    under a blocking flock on <requests>.lock (its own lock file, so it never
    contends with the worklist cleaner's lock). The flock makes concurrent
    writers a settled question rather than an unlikely one: they serialize
    absolutely, and the lock is held for microseconds. Readers take no lock;
    a torn trailing line is only possible on a crash mid-write, fails
    json.loads, and is skipped by every reader."""
    p = requests_path(worklist)
    with open(str(p) + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, separators=(",", ":")) + "\n")


def read_requests(worklist):
    """{id: request} folded from the append-only event log. State is DERIVED,
    never edited: an answer, decline, ack or escalation is an appended event,
    so no writer ever rewrites another's line -- the same lost-update
    discipline the worklist itself uses."""
    p = requests_path(worklist)
    reqs = {}
    if not p.exists():
        return reqs
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return reqs
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        rid, kind = ev.get("id"), ev.get("ev")
        if kind == "ask" and rid and rid not in reqs:
            reqs[rid] = {
                "id": rid,
                "from": str(ev.get("from", "")),
                "to": str(ev.get("to", "*")),
                "at": str(ev.get("at", "")),
                "body": str(ev.get("body", "")),
                "answers": [],
                "declines": [],
                "acked": False,
                "escalated": "",
            }
        elif rid in reqs:
            r = reqs[rid]
            if kind == "answer":
                r["answers"].append(ev)
            elif kind == "decline":
                r["declines"].append(ev)
            elif kind == "ack":
                r["acked"] = True
            elif kind == "escalate" and not r["escalated"]:
                r["escalated"] = str(ev.get("why", "escalated"))
    return reqs


def request_resolved(r):
    """A direct request is resolved by an answer OR a decline: a refusal with
    a reason IS an answer. A broadcast is resolved only by an answer -- a
    decline there just releases the decliner ("not my area")."""
    if r["answers"]:
        return True
    return r["to"] != "*" and bool(r["declines"])


def _stamp_age_min(stamp):
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%MZ"):
        try:
            when = datetime.datetime.strptime(stamp, fmt).replace(tzinfo=datetime.timezone.utc)
        except (TypeError, ValueError):
            continue
        return (datetime.datetime.now(datetime.timezone.utc) - when).total_seconds() / 60.0
    return None


def brief_age_min(worklist, prefix):
    """Minutes since `prefix` last refreshed its .sessions brief, or None if
    it never briefed. The briefs file is the liveness oracle here: the brief
    check forces every live session to refresh within SESSION_BRIEF_STALE_MIN,
    so silence much longer than that is real absence, not shyness. Freshest
    match wins when a short prefix matches several -- the conservative
    direction, as in owner_age_hours."""
    ages = []
    now = datetime.datetime.now(datetime.timezone.utc)
    for k, (when, _text) in read_briefs(worklist).items():
        if same_session(k, prefix) and when is not None:
            ages.append((now - when).total_seconds() / 60.0)
    return min(ages) if ages else None


def escalate_requests(worklist, session_id, dry_run=False):
    """Promote unanswerable requests to operator-visible `- [?]` items.

    `dry_run` (v9): report what WOULD escalate without appending anything.
    The poll fast path uses it to forfeit the silent exit when an escalation
    is due, so escalation always happens on a FULL stop that reports it --
    an escalation performed silently would be an operator-visible event that
    nobody surfaced.

    THE DEAD-RECIPIENT PROBLEM. A request nobody will ever be blocked on is a
    silent black hole, and blocking the SENDER instead would punish the one
    session that did the right thing. So ANY session's stop escalates when:
      - a direct request's recipient has no fresh brief (older than
        WORKLIST_REQUEST_DEAD_MIN, default 180 min, or none at all) and the
        request is past WORKLIST_REQUEST_GRACE_MIN (default 30 -- grace for a
        recipient that has not briefed YET);
      - a broadcast has no other live session to answer it, or every live
        session has declined it;
      - anything is unanswered past WORKLIST_REQUEST_STALE_MIN (default 240),
        live recipient or not: a recipient that never stops never runs this
        hook, and four hours of silence is the operator's business.
    Escalation appends an `escalate` event plus a `- [?]` worklist line owned
    by the ASKER, carrying the ask's own DEFAULT: (or a generic
    proceed-without-it one), so the existing deferral machinery reports it to
    the operator every stop without wrongly blocking anyone. Check-then-append
    is not idempotent, so it runs under an exclusive NON-BLOCKING flock with a
    re-read inside the lock: the losing racer skips and retries next stop,
    and a request is escalated exactly once."""
    stale_min = float(os.environ.get("WORKLIST_REQUEST_STALE_MIN", "240"))
    dead_min = float(os.environ.get("WORKLIST_REQUEST_DEAD_MIN", "180"))
    grace_min = float(os.environ.get("WORKLIST_REQUEST_GRACE_MIN", "30"))
    reqs = read_requests(worklist)
    if not reqs:
        return []
    now = datetime.datetime.now(datetime.timezone.utc)
    live = {
        k
        for k, (when, _t) in read_briefs(worklist).items()
        if when is not None and (now - when).total_seconds() / 60.0 <= dead_min
    }

    def unanswerable(r):
        if r["escalated"] or r["acked"] or request_resolved(r):
            return ""
        age = _stamp_age_min(r["at"])
        if age is None:
            return ""
        if age >= stale_min:
            return "unanswered for %dmin" % age
        if r["to"] != "*":
            seen = brief_age_min(worklist, r["to"])
            if (seen is None or seen > dead_min) and age >= grace_min:
                return "recipient %s %s" % (
                    r["to"],
                    "never briefed" if seen is None else "silent for %dmin" % seen,
                )
            return ""
        others = {k for k in live if not same_session(k, r["from"])}
        if not others:
            return "no other live session to answer"
        if all(
            any(same_session(str(d.get("by", "")), k) for d in r["declines"]) for k in others
        ):
            return "every live session declined"
        return ""

    candidates = [(r, unanswerable(r)) for r in reqs.values()]
    candidates = [(r, why) for r, why in candidates if why]
    if not candidates:
        return []
    if dry_run:
        return ["#%s to %s: %s" % (r["id"], r["to"], why) for r, why in candidates]
    escalated = []
    with open(str(requests_path(worklist)) + ".lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return []  # another stop is escalating; it wins, next stop retries
        current = read_requests(worklist)  # re-read under the lock
        stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        for r, why in candidates:
            fresh = current.get(r["id"])
            if fresh is None or fresh["escalated"] or fresh["acked"] or request_resolved(fresh):
                continue
            with open(requests_path(worklist), "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "ev": "escalate",
                            "id": r["id"],
                            "by": (session_id or "unknown")[:8],
                            "at": stamp,
                            "why": why,
                        },
                        separators=(",", ":"),
                    )
                    + "\n"
                )
            body = r["body"]
            if not DEFAULT_TOKEN.search(body):
                body += " DEFAULT: the asker proceeds without an answer and says so in its summary"
            with open(worklist, "a", encoding="utf-8") as f:
                f.write(
                    "- [?] (%s) request #%s to %s went unanswered (%s): %s\n"
                    % (r["from"] or "unknown", r["id"], r["to"], why, body)
                )
            escalated.append("#%s to %s: %s" % (r["id"], r["to"], why))
    return escalated


def classify_requests(reqs, session_id):
    """(to_me, broadcasts_awaiting_me, answered_unacked_mine, open_mine).

    The ownership rule, applied to requests: a session is only ever blocked
    on its OWN obligations -- answering what is addressed to it (a broadcast
    is addressed to everyone, but only until THIS session responds) and
    acting on answers to what it asked. Never on another session's silence."""
    to_me, bcast, answered_mine, open_mine = [], [], [], []
    for r in sorted(reqs.values(), key=lambda x: x["at"]):
        mine = bool(session_id) and same_session(r["from"], session_id)
        resolved = request_resolved(r)
        if mine:
            if resolved and not r["acked"]:
                answered_mine.append(r)
            elif not resolved and not r["escalated"]:
                open_mine.append(r)
            continue
        if resolved or r["escalated"] or not session_id:
            continue
        if r["to"] == "*":
            if not any(same_session(str(d.get("by", "")), session_id) for d in r["declines"]):
                bcast.append(r)
        elif same_session(r["to"], session_id):
            to_me.append(r)
    return to_me, bcast, answered_mine, open_mine


def request_cli(argv, worklist):
    """--ask / --answer / --decline / --ack / --requests. See WHY v6. Exits
    non-zero on misuse, so a session cannot mistake a rejected post for a
    delivered one."""

    def die(msg):
        print(msg, file=sys.stderr)
        sys.exit(1)

    def request_body(what):
        """Join, flatten, and LENGTH-CHECK the free-text argument. Over-length
        is REFUSED, never silently clipped: a write-time truncation would be
        the commit-message defect one layer down, losing the tail (often the
        crucial part) while telling the sender it was delivered."""
        body = " ".join(argv[3:]).replace("\n", " ").strip()
        if len(body) > REQUEST_BODY_MAX:
            die(M.CLI_BODY_REFUSED % (what, len(body), REQUEST_BODY_MAX))
        return body

    mode = argv[0]
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if mode == "--requests":
        reqs = read_requests(worklist)
        if not reqs:
            print("no requests recorded (%s)" % requests_path(worklist))
            return
        for r in sorted(reqs.values(), key=lambda x: x["at"]):
            state = (
                "acked" if r["acked"]
                else "answered" if request_resolved(r)
                else "escalated" if r["escalated"]
                else "open"
            )
            print("#%s %s %s -> %s [%s] %s" % (r["id"], r["at"], r["from"], r["to"], state, r["body"]))
            for a in r["answers"]:
                print("    answer by %s at %s: %s" % (a.get("by", "?"), a.get("at", "?"), a.get("body", "")))
            for d in r["declines"]:
                print("    decline by %s at %s: %s" % (d.get("by", "?"), d.get("at", "?"), d.get("reason", "")))
            if r["escalated"]:
                print("    escalated: %s" % r["escalated"])
        return
    if len(argv) < 3:
        die(M.CLI_REQUEST_USAGE)
    me = argv[1]
    if not PREFIX_RE.match(me):
        die("bad prefix %r: pass YOUR session-id prefix first" % me)
    if mode == "--ask":
        to = argv[2]
        if to != "*" and not PREFIX_RE.match(to):
            die("bad recipient %r: a session prefix from the .sessions briefs, or * to broadcast" % to)
        if to != "*" and same_session(me, to):
            die("that request is addressed to yourself; use the worklist for your own items")
        body = request_body("request body")
        if not body:
            die("an empty request asks nothing: say what you need, why, and a DEFAULT: if unanswered")
        rid = hashlib.sha1(
            ("%d|%d|%s|%s" % (time.time_ns(), os.getpid(), me, body)).encode("utf-8")
        ).hexdigest()[:8]
        append_request_event(
            worklist, {"ev": "ask", "id": rid, "from": me, "to": to, "at": stamp, "body": body}
        )
        if to == "*":
            dead_min = float(os.environ.get("WORKLIST_REQUEST_DEAD_MIN", "180"))
            others = [
                k
                for k in read_briefs(worklist)
                if not same_session(k, me)
                and (brief_age_min(worklist, k) or dead_min + 1) <= dead_min
            ]
            print(
                "request #%s broadcast: %d other live session(s) will each be blocked "
                "until they answer or decline%s"
                % (
                    rid,
                    len(others),
                    "" if others else "; NONE are live, so it will escalate to the operator",
                )
            )
        else:
            seen = brief_age_min(worklist, to)
            print(
                "request #%s posted to %s (%s)"
                % (
                    rid,
                    to,
                    "never briefed here; if it stays silent this escalates to the operator"
                    if seen is None
                    else "last seen %dm ago" % seen,
                )
            )
        return
    rid = argv[2]
    r = read_requests(worklist).get(rid)
    if r is None:
        die("no request #%s here (list them with --requests)" % rid)
    if mode == "--ack":
        if not same_session(me, r["from"]):
            die("only the asker (%s) can ack #%s" % (r["from"], rid))
        if not request_resolved(r):
            die("#%s has no answer yet; acking now would silence it unanswered" % rid)
        if r["acked"]:
            print("#%s already acked" % rid)
            return
        append_request_event(worklist, {"ev": "ack", "id": rid, "by": me, "at": stamp})
        print("acked #%s; it will not block you again" % rid)
        return
    body = request_body("answer/decline text")
    if same_session(me, r["from"]):
        die("#%s is your own request; answering yourself defeats the mechanism" % rid)
    if mode == "--answer":
        if not body:
            die("an empty answer answers nothing")
        append_request_event(worklist, {"ev": "answer", "id": rid, "by": me, "at": stamp, "body": body})
        print("answered #%s; %s is blocked on acting on it at their next stop" % (rid, r["from"]))
        return
    if mode == "--decline":
        if not body:
            die("a decline without a reason is a stall, not an answer: say why not")
        append_request_event(worklist, {"ev": "decline", "id": rid, "by": me, "at": stamp, "reason": body})
        print(
            "declined #%s%s"
            % (
                rid,
                " (broadcast: this releases only you)" if r["to"] == "*" else "; the asker gets your reason",
            )
        )
        return
    die("unknown request mode %s" % mode)


# ---- v7: regression-gate enforcement ---------------------------------------
FIX_SUBJECT = re.compile(r"^(fix|revert)[(!:]")
REGGATE_TIMEOUT_S = int(os.environ.get("WORKLIST_REGGATE_TIMEOUT_S", "120"))
REGGATE_VERDICTS = ("not-applicable", "covered", "one-off", "proven", "deferred")
# Where a freshly written gate leaves its artifact. Both shapes exist in this
# repo; anything else is not a gate the ci chain can run.
CHECK_SCRIPT_GLOBS = ("scripts/check-*.ts", ".ci/scripts/quality/check-*.sh")


def reggate_path(worklist, session_id):
    return worklist.with_suffix(".reggate-%s" % (session_id or "unknown")[:8])


def load_reggate(path):
    """(state, forgot). FAIL SAFE by contract: a missing marker returns the
    empty default (the caller fills head and asks nothing that stop); a
    corrupt one does the same PLUS forgot=True, which the caller surfaces as
    one systemMessage line. No field-wise salvage: any invalid shape discards
    the whole file, because half-parsed fixsets silently resurrect a blocked
    question as settled. Never a block, never silent."""
    default = {"head": "", "seen_ticks": [], "fixsets": {}, "gate_runs": {}}
    if not path.exists():
        return default, False
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        ok = (
            isinstance(d, dict)
            and isinstance(d.get("head"), str)
            and isinstance(d.get("seen_ticks"), list)
            and all(isinstance(t, str) for t in d.get("seen_ticks", []))
            and isinstance(d.get("fixsets"), dict)
            and all(
                isinstance(v, dict) and v.get("verdict") in REGGATE_VERDICTS
                for v in d.get("fixsets", {}).values()
            )
            and isinstance(d.get("gate_runs"), dict)
        )
    except (OSError, ValueError):
        ok, d = False, None
    if not ok:
        return default, True
    return d, False


def save_reggate(path, state):
    # Whole-file rewrite is correct here for the same reason as the handover:
    # the marker is per-session, so there is no second writer to race.
    try:
        path.write_text(json.dumps(state, indent=1), encoding="utf-8")
    except OSError:
        pass


def _tick_id(line):
    return hashlib.sha1(line.strip().encode("utf-8", "replace")).hexdigest()[:12]


def mine_tick_ids(lines, session_id):
    out = []
    for line in lines:
        m = ITEM.match(line)
        if m and m.group("state") == "x" and owned_by_me(m.group("owner"), session_id):
            out.append(_tick_id(line))
    return out


def _hash_file(path):
    try:
        return hashlib.sha1(pathlib.Path(path).read_bytes()).hexdigest()[:16]
    except OSError:
        return ""


def seed_gate_hashes(root):
    """Hashes of every existing check script, recorded at marker init so only
    scripts that are NEW or CHANGED after that point ever count as candidate
    proof (or get run). Without this seed, the first fix-signal stop in a real
    repo would treat ~all 90 existing gates as candidates and try to run them."""
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = {}
    for pat in CHECK_SCRIPT_GLOBS:
        for f in glob.glob(os.path.join(str(root), pat)):
            rel = os.path.relpath(f, str(root)).replace(os.sep, "/")
            digest = _hash_file(f)
            if digest:
                out[rel] = {"hash": digest, "exit": -3, "at": stamp}  # -3 = seeded, never run
    return out


def fix_signals(root, lines, session_id, state):
    """(descriptions, ids, new_tick_ids, current_head).

    ARTIFACTS, never prose. Primary: commit subjects matching FIX_SUBJECT in
    marker-head..HEAD. Secondary: newly ticked `- [x]` lines owned by this
    session, covering the uncommitted-tree default. The skip filter is
    deliberately narrow: a fix commit touching only docs/** and **/*.md never
    asks; everything else does, and the judge's four questions sort the
    one-offs out. A rewound or unreachable old head yields an empty log,
    which reads as no signals and lets head self-heal by advancing."""
    head = _git(root, "rev-parse", "HEAD")
    commits, new_ticks = [], []
    if state["head"] and head and state["head"] != head:
        for row in _git(
            root, "log", "--format=%H%x09%s", "%s..%s" % (state["head"], head)
        ).splitlines():
            sha, _, subj = row.partition("\t")
            if not FIX_SUBJECT.match(subj):
                continue
            files = _git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", sha).splitlines()
            if files and all(f.startswith("docs/") or f.endswith(".md") for f in files):
                continue
            commits.append((sha, "%s %s" % (sha[:7], subj)))
    for line in lines:
        m = ITEM.match(line)
        if m and m.group("state") == "x" and owned_by_me(m.group("owner"), session_id):
            tid = _tick_id(line)
            if tid not in state["seen_ticks"]:
                new_ticks.append((tid, line.strip()))
    descriptions = [d for _, d in commits] + ["tick: " + t[:120] for _, t in new_ticks]
    ids = sorted([s for s, _ in commits] + [t for t, _ in new_ticks])
    # new_ticks stays (id, line) pairs: I7 needs the LINE to check evidence,
    # the absorb/settle sites need the id. Returning ids only here once made
    # the I7 unpack crash, and a crashed hook reads as ALLOW -- fail-open.
    return descriptions, ids, new_ticks, head


def package_scripts(root):
    try:
        d = json.loads((pathlib.Path(root) / "package.json").read_text(encoding="utf-8"))
        s = d.get("scripts")
        return s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        return {}


def gate_reachable(scripts, target):
    """Is `target` TRANSITIVELY reachable from the `ci` script via `npm run`
    references? Transitive, because ci reaches most gates through batch keys.
    NOT a substring test: a gate's name inside an `echo` is not reachability,
    and the substring version produced real false positives on this repo."""
    seen, todo = set(), ["ci"]
    while todo:
        k = todo.pop()
        if k in seen or k not in scripts:
            continue
        seen.add(k)
        todo.extend(re.findall(r"npm run\s+(?:--silent\s+)?([A-Za-z0-9:._-]+)", scripts[k]))
    return target in seen


def prove_new_gate(root, scripts, state):
    """(proven, notes). A claimed gate must leave ARTIFACTS, each verified:
    a NEW or CHANGED check script (content hash vs the marker), a check:* key
    whose command runs it, reachability from `npm run ci` (transitive, see
    gate_reachable), and a bounded green run. Runs are cached by content hash
    so a red gate is not re-run every stop and a green one is not re-paid.
    A green run of a control-first gate IS the planted-defect proof, because
    such a gate self-fails when its own control cannot fire -- the
    check-i18n-cross-locale.ts --selftest that NOTHING invoked is the exact
    failure this rule exists for, and check-gate-reachability.ts exists
    because a gate can be defined yet never run."""
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    notes, proven = [], False
    for pat in CHECK_SCRIPT_GLOBS:
        for f in sorted(glob.glob(os.path.join(str(root), pat))):
            rel = os.path.relpath(f, str(root)).replace(os.sep, "/")
            digest = _hash_file(f)
            if not digest:
                continue
            prev = state["gate_runs"].get(rel)
            if prev and prev.get("hash") == digest:
                continue  # neither new nor changed: proves nothing for THIS fix
            key = next(
                (k for k in sorted(scripts) if k.startswith("check:") and rel in scripts[k]),
                "",
            )
            if not key:
                state["gate_runs"][rel] = {"hash": digest, "exit": -1, "at": stamp}
                notes.append("%s: no check:* key runs it" % rel)
                continue
            if not gate_reachable(scripts, key):
                state["gate_runs"][rel] = {"hash": digest, "exit": -2, "at": stamp}
                notes.append(
                    "%s: %s is defined but NOT reachable from `npm run ci` "
                    "(defined-but-never-run is the check-gate-reachability failure)"
                    % (rel, key)
                )
                continue
            try:
                pr = subprocess.run(
                    ["npm", "run", "--silent", key],
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    timeout=REGGATE_TIMEOUT_S,
                )
                code = pr.returncode
            except subprocess.TimeoutExpired:
                code = 124
            except (OSError, subprocess.SubprocessError):
                code = 127
            state["gate_runs"][rel] = {"hash": digest, "exit": code, "at": stamp}
            notes.append("%s via `npm run %s`: exit %d" % (rel, key, code))
            if code == 0:
                proven = True
    if not notes:
        notes.append("no new or changed check script found; a claimed gate must leave one")
    return proven, "; ".join(notes)


def apply_regression_verdict(rg, scripts, root, state, sig, lines, me8):
    """('malformed'|'settle'|'block', payload, detail).

    Deterministic mapping from the judge's regression_gate object to an
    action, with every model claim VERIFIED against artifacts:
      applicable false                      -> settle 'not-applicable'
      existing_gate is a REAL check:* key   -> settle 'covered'
      existing_gate names a key that is not -> hallucinated coverage, counts
                                               as none, falls through
      recurring false                       -> settle 'one-off'
      a `- [?]` line carrying reggate:<sig> -> settle 'deferred' (the deferral
                                               machinery prints it every stop)
      a new/changed gate, wired + green     -> settle 'proven'
      otherwise: recurring AND ungated AND unproven AND undeferred -> block,
      naming the three exits. gate_needed=false with recurring=true and no
      real coverage is incoherent and blocks too; the REBUT exit lets the
      judge re-answer coherently next stop."""
    fields = (
        "applicable", "blind_spot", "existing_gate", "recurring",
        "gate_needed", "gate_proven", "instruction",
    )
    if not isinstance(rg, dict) or any(k not in rg for k in fields):
        return "malformed", "regression_gate missing or incomplete: %r" % (rg,), ""
    if rg["applicable"] is False:
        return "settle", "not-applicable", str(rg["blind_spot"])[:160]
    keys = [k for k in scripts if k.startswith("check:")]
    hall, eg = "", str(rg["existing_gate"] or "").strip()
    if eg:
        if eg in keys:
            return "settle", "covered", eg
        hall = eg
    if rg["recurring"] is False and not hall:
        return "settle", "one-off", str(rg["blind_spot"])[:160]
    token = "reggate:%s" % sig[:8]
    for ln in lines:
        m = ITEM.match(ln)
        if m and m.group("state") == "?" and token in ln:
            return "settle", "deferred", token
    proven, notes = prove_new_gate(root, scripts, state)
    if proven:
        return "settle", "proven", notes[:300]
    reason = M.R_REGGATE_BLOCK % (
        str(rg["blind_spot"])[:300],
        str(rg["instruction"])[:300],
        "" if not hall else M.R_REGGATE_HALLUCINATED % hall,
        "" if not notes else "  gate probe: %s\n" % notes[:400],
        me8,
        token,
    )
    return "block", reason, ""


# The four-question regression prompt lives in worklist_messages.REGGATE_PROMPT.


# ---- v8: completion evidence (I7) ------------------------------------------
RUN_ID_RE = re.compile(r"\b\d{9,}\b")
EXIT_RE = re.compile(r"\bexit(?:\s+code)?\s*[:=]?\s*\d+\b", re.I)
URL_RE = re.compile(r"https?://\S+")
SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b")


def completion_evidence(root, text):
    """Does `text` carry something evidence-shaped for a completion claim?

    Shapes, cheapest first: a run-id-sized number, an exit code, a URL, a
    file:line that RESOLVES (citation_state, so a fabricated path or line
    fails), or a hex string naming a REAL git object (verified, so a
    decorative 'deadbee' cannot pass; at most five candidates checked to
    bound the git calls). Deliberately shape-based: whether the evidence
    SUPPORTS the claim is the reggate judge's question, since every new tick
    already flows into it. This check only guarantees a completion leaves a
    RECORD, which is exactly what S-2 lacked."""
    if RUN_ID_RE.search(text) or EXIT_RE.search(text) or URL_RE.search(text):
        return True
    if citation_state(root, text)[0]:
        return True
    for m in list(SHA_RE.finditer(text))[:5]:
        if _git(root, "rev-parse", "--verify", "--quiet", m.group(0) + "^{object}"):
            return True
    return False


def task_statuses(session_id):
    """{id: (status, subject)} for ALL harness tasks, completed included.
    pending_tasks() serves the queue; this serves the completion-evidence
    check, which needs the TRANSITION into completed, not the queue."""
    if not session_id:
        return {}
    home = os.environ.get("WORKLIST_TASKS_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude", "tasks"
    )
    d = os.path.join(home, "session-" + session_id[:8])
    out = {}
    try:
        for f in glob.glob(os.path.join(d, "*.json")):
            try:
                with open(f, encoding="utf-8") as fh:
                    t = json.load(fh)
            except (OSError, ValueError):
                continue
            if t.get("id") is not None:
                out[str(t["id"])] = (str(t.get("status", "")), str(t.get("subject", ""))[:70])
    except OSError:
        return {}
    return out


# ---- v9: waiting-cross-session + the 5-minute inbox poll --------------------
# The poll cron is recognised by SCHEDULE SHAPE, not by id or prompt text:
# schedules are structural, survive restarts, and a work cron cannot claim the
# shape without also BECOMING a 5-minute loop. By definition, the 5-minute
# schedule IS the poll.
POLL_SCHEDULE_RE = re.compile(r"^\*/5( \*){4}$")
# A poll marker older than this cannot vouch for THIS stop. The marker is
# single-use (consumed on first sight), so the window only needs to cover one
# poll turn; too small merely costs one full battery, the safe direction.
POLL_WINDOW_S = int(os.environ.get("WORKLIST_POLL_WINDOW_S", "600"))
# The fast path expires: at most this many minutes since the last ALLOWED
# full-battery stop before a poll stop pays the battery again. Just over the
# hourly work loop, so the shape is one full report per hour with free polls
# between, and a session cannot live on polls alone.
POLL_FULL_MAX_MIN = int(os.environ.get("WORKLIST_POLL_FULL_MAX_MIN", "70"))
# Request ids are sha1[:8], so 8 hex chars; a #id on a Remaining line is only
# accepted if it also resolves in the .requests log, so a task id that happens
# to be 8 digits cannot satisfy the state by shape alone.
XSESSION_ID_RE = re.compile(r"#([0-9a-f]{8})\b")


def is_poll_cron(c):
    if not isinstance(c, dict):
        return False
    sched = " ".join(str(c.get("schedule", "")).split())
    return bool(POLL_SCHEDULE_RE.match(sched))


def xsession_ok(line, reqs, session_id):
    """(ok, why) for a 'waiting-cross-session' Remaining line.

    The state must EARN its place or it is a synonym for 'blocked': the line
    must name an OPEN request id from the .requests log that THIS session
    asked. That id is checkable across its whole lifecycle, so it substitutes
    for the <path>:<line> citation the blocked/parked states require -- the
    request IS the citation. Fails loudly on a stale id: an answered request
    means the wait is over, an escalated one means the operator holds it now.
    """
    known = [i for i in XSESSION_ID_RE.findall(line) if i in reqs]
    if not known:
        return False, (
            "names no request id from the log; post the ask with --ask and put "
            "its #id on the line"
        )
    why = ""
    for rid in known:
        r = reqs[rid]
        if not same_session(r["from"], session_id):
            why = (
                "#%s was asked by %s, not by you; only your own outstanding "
                "request is your waiting state" % (rid, r["from"] or "unknown")
            )
        elif r["escalated"]:
            why = (
                "#%s already ESCALATED to the operator; the [?] item carries it "
                "now, so update this line" % rid
            )
        elif request_resolved(r):
            why = (
                "#%s is already ANSWERED; the wait is over, act on the answer "
                "and --ack it" % rid
            )
        else:
            return True, rid
    return False, why


def pollmark_path(worklist, prefix):
    return worklist.with_suffix(".pollmark-%s" % (prefix or "unknown")[:8])


def pollbase_path(worklist, session_id):
    return worklist.with_suffix(".pollbase-%s" % (session_id or "unknown")[:8])


def bank_pollbase(worklist, session_id, event):
    """Record the world as the poll fast path's baseline.

    OPERATOR DECISION, 2026-07-30, overriding the original v9 rule that only an
    ALLOWED stop may bank. The original rule deadlocked in practice: a session
    with any open task blocks on the Remaining check, a blocked stop never
    reached the write, and with no baseline every five-minute poll paid the full
    battery -- while each of those polls was itself another stop that moved
    nothing, feeding the stuck detector. Measured on this session: pollbase was
    never created once across an entire night.

    Banking on a blocked stop is deliberately NOT an escape hatch, because the
    baseline is only half the fast path. poll_fast_path still recomputes every
    other condition from artifacts (single-use marker, horizon, unchanged world
    signature, cron shape, no open or undefaulted or expired-lease items, empty
    inbox). What banking buys is only this: a poll that changes nothing can
    recognise that nothing changed. The moment real work lands, the signature
    moves and the battery returns on its own.
    """
    try:
        pollbase_path(worklist, session_id).write_text(
            json.dumps(
                {
                    "sig": world_sig(
                        project_root(event.get("cwd") or os.getcwd()),
                        worklist,
                        session_id,
                    ),
                    "at": datetime.datetime.now(datetime.timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                }
            ),
            encoding="utf-8",
        )
    except OSError:
        pass


def world_sig(root, worklist, session_id):
    """Coarse world signature: task statuses + HEAD + worklist bytes +
    requests bytes. Deliberately the same altitude as the stuck detector's
    signature (tasks + HEAD), plus the two shared files, because those four
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

    ts = task_statuses(session_id)
    blob = "|".join(
        [
            ",".join("%s:%s" % (i, st) for i, (st, _s) in sorted(ts.items())),
            _git(root, "rev-parse", "HEAD"),
            digest(worklist),
            digest(requests_path(worklist)),
        ]
    )
    return hashlib.sha1(blob.encode("utf-8", "replace")).hexdigest()[:16]


def poll_fast_path(worklist, session_id, event):
    """True iff this stop is a PROVEN no-op inbox poll (see WHY v9).

    Every condition is recomputed here from artifacts; nothing is trusted
    from the poll command, whose only contributions are the single-use
    marker (the structural declaration that this turn WAS a poll) and the
    printed inbox. Every failure path returns False, which means the FULL
    battery -- the fast path can never fail into a silent allow.
    """
    mark = pollmark_path(worklist, (session_id or "unknown")[:8])
    try:
        fresh = time.time() - mark.stat().st_mtime <= POLL_WINDOW_S
        # CONSUMED either way, before any other verdict: one poll vouches for
        # at most one stop, and a marker lingering into an operator-facing
        # turn must not silence that turn's report.
        mark.unlink()
    except OSError:
        return False
    if not fresh:
        return False
    base_p = pollbase_path(worklist, session_id)
    try:
        base_sig = json.loads(base_p.read_text(encoding="utf-8"))["sig"]
        if time.time() - base_p.stat().st_mtime > POLL_FULL_MAX_MIN * 60:
            return False  # the horizon: a poll stop now pays the battery
    except (OSError, ValueError, KeyError, TypeError):
        return False
    root = project_root(event.get("cwd") or os.getcwd())
    if world_sig(root, worklist, session_id) != base_sig:
        return False  # tracked work happened since the last full stop
    crons = event.get("session_crons") or []
    if len([c for c in crons if is_poll_cron(c)]) != 1:
        return False
    if len([c for c in crons if not is_poll_cron(c)]) > 1:
        return False
    try:
        lines = worklist.read_text().splitlines() if worklist.exists() else []
    except OSError:
        return False
    for line in lines:
        m = ITEM.match(line)
        if not m or not owned_by_me(m.group("owner"), session_id):
            continue
        state = m.group("state")
        if state == " ":
            return False
        if state == "?" and not DEFAULT_TOKEN.search(line):
            return False
        if state == ">" and lease_state(line) != "fresh":
            return False  # an expiring lease is a wake-up; the battery says so
    to_me, bcast, answered, _mine = classify_requests(read_requests(worklist), session_id)
    if to_me or bcast or answered:
        return False  # the inbox is the poll's whole subject; deliver it loudly
    if escalate_requests(worklist, session_id, dry_run=True):
        return False  # due escalations happen on a full stop that reports them
    return True


JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["stop", "continue"]},
        "reason": {"type": "string", "maxLength": 300},
        "next_action": {"type": "string", "maxLength": 200},
        # v7: OPTIONAL at the top level (verified: --json-schema accepts a
        # conditionally-required object and returns cleanly with it omitted,
        # so ONE schema, no variants), but its own properties are all
        # required. On a fix-signal stop a missing or malformed object is a
        # judge error and fails closed, same as an invalid verdict.
        "regression_gate": {
            "type": "object",
            "properties": {
                "applicable": {"type": "boolean"},
                "blind_spot": {"type": "string", "maxLength": 300},
                "existing_gate": {"type": "string", "maxLength": 100},
                "recurring": {"type": "boolean"},
                "gate_needed": {"type": "boolean"},
                "gate_proven": {"type": "boolean"},
                "instruction": {"type": "string", "maxLength": 300},
            },
            "required": [
                "applicable", "blind_spot", "existing_gate", "recurring",
                "gate_needed", "gate_proven", "instruction",
            ],
            "additionalProperties": False,
        },
    },
    "required": ["verdict", "reason", "next_action"],
    "additionalProperties": False,
}

# The stop-legitimacy prompt lives in worklist_messages.JUDGE_PROMPT.


def resolve_claude():
    return shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")


def run_judge(remaining_lines, leases, message, streak, loop_desc, citations=None, extra=""):
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
    prompt = M.JUDGE_PROMPT % {
        "streak": streak,
        "remaining": "\n".join("  " + r for r in remaining_lines[:20]) or "  (none tracked)",
        "leases": leases,
        "loop": loop_desc,
        "message": (message or "(the session produced no text)")[-6000:],
        "citations": citations or "  (none cited)",
    } + (extra or "")
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

    # BEFORE every other arm. Asking a tool how to use it must never reach the
    # Stop-hook path, which reads stdin as JSON and, finding none, emits a block
    # telling the caller they have a hook bug. That happened, and the answer to
    # "how do I use this" was a wall of unrelated advice.
    if sys.argv[1:2] and sys.argv[1] in ("--help", "-h", "help"):
        print(M.USAGE)
        return

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
    if sys.argv[1:2] == ["--session-start"]:
        try:
            ev = json.load(sys.stdin)
        except (json.JSONDecodeError, ValueError):
            ev = {}
        root = project_root(os.environ.get("CLAUDE_PROJECT_DIR") or ev.get("cwd") or os.getcwd())
        docs = pathlib.Path(root) / DESIGN_DOCS
        if not docs.is_dir():
            sys.exit(0)
        files = sorted(f for f in docs.iterdir() if f.is_file() and f.suffix == ".md")
        listing = "\n".join(
            "  %s (%d lines)"
            % (f.relative_to(root), len(f.read_text(errors="replace").splitlines()))
            for f in files
        )
        state, drift, _ = docs_drift(root)
        stale = (
            ""
            if state != "drifted"
            else M.CTX_SESSION_START_STALE % (drift, " ".join(PROGRAM_SURFACE))
        )
        emit(
            {
                "systemMessage": "SessionStart: %d design doc(s) in %s%s"
                % (
                    len(files),
                    DESIGN_DOCS,
                    "" if state != "drifted" else " (DRIFTED by %d commits)" % drift,
                ),
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": M.CTX_SESSION_START % (DESIGN_DOCS, listing, stale),
                },
            }
        )
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
            msg = M.CTX_POSTCOMPACT_MISSING % (handover_path(wl, sid), (sid or "unknown")[:8])
        else:
            msg = M.CTX_POSTCOMPACT_BRIEFING % (DESIGN_DOCS, text.strip())
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
    if sys.argv[1:2] and sys.argv[1] in ("--ask", "--answer", "--decline", "--ack", "--requests"):
        request_cli(
            sys.argv[1:], worklist_for(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        )
        return
    if sys.argv[1:2] == ["--poll"]:
        # `worklist.py --poll <8-char-prefix>`: the 5-minute inbox poll (WHY
        # v9). EMPTY inbox: print NOTHING, exit 0, so the poll turn costs the
        # session almost no context. Non-empty: the full payloads plus the
        # exact commands. Either way it drops the single-use poll marker that
        # lets the Stop hook recognise this turn structurally.
        wl = worklist_for(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        me = sys.argv[2] if len(sys.argv) > 2 else ""
        if not PREFIX_RE.match(me) or len(me) < 8:
            # A short prefix would name a DIFFERENT marker than the Stop hook
            # derives from the full session id, silently disabling the fast
            # path, so misuse is refused rather than half-working.
            print(
                "usage: --poll <your-8-char-session-id-prefix> (got %r)" % me,
                file=sys.stderr,
            )
            sys.exit(1)
        try:
            pollmark_path(wl, me).write_text(
                datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                encoding="utf-8",
            )
        except OSError:
            pass  # no marker means no fast path: the safe direction
        to_me, bcast, answered, _mine = classify_requests(read_requests(wl), me)
        if not (to_me or bcast or answered):
            sys.exit(0)  # print NOTHING: the operator's contract for this mode
        for r in to_me + bcast:
            print(
                "INBOX #%s from %s (%s, asked %s): %s"
                % (
                    r["id"],
                    r["from"],
                    "to you" if r["to"] != "*" else "broadcast",
                    r["at"],
                    r["body"],
                )
            )
            print("    answer:  %s --answer %s %s '<what you did or know>'" % (__file__, me, r["id"]))
            print("    decline: %s --decline %s %s '<why not>'" % (__file__, me, r["id"]))
        for r in answered:
            print("ANSWERED #%s (you asked: %s)" % (r["id"], r["body"][:120]))
            for a in r["answers"]:
                print("    answer by %s at %s: %s" % (a.get("by", "?"), a.get("at", "?"), a.get("body", "")))
            for d in r["declines"]:
                print("    decline by %s at %s: %s" % (d.get("by", "?"), d.get("at", "?"), d.get("reason", "")))
            print("    ack when acted on: %s --ack %s %s" % (__file__, me, r["id"]))
        sys.exit(0)

    # CI NO-OP, and it is placed HERE rather than beside the STOPHOOK_CHILD guard
    # on purpose. Everything above this line is a read-only query mode that a
    # runner may legitimately want (`--path`, `--handover`); exiting at the top of
    # main() would break those silently. The thing that must not happen on a
    # runner is the BLOCK below: CLAUDE.md tells a session to append `- [ ]` items
    # and this hook refuses to end a turn while any remain, so an unattended model
    # in Actions burns its turn budget against a gate no human will ever answer.
    # Required by the autopilot design (docs/ci-overhaul/03-v2-autonomy.md:375-377).
    if os.environ.get("GITHUB_ACTIONS") == "true":
        sys.exit(0)

    try:
        event = json.load(sys.stdin)
        event_ok = isinstance(event, dict)
    except (json.JSONDecodeError, ValueError):
        # A malformed event used to degrade to {} silently, which quietly turns
        # EVERY check into "session_id is empty, nothing is configured" and
        # produces confusing advice (it told a test to run `--brief unknown`).
        # Fail loudly instead: a Stop payload this hook cannot parse is a bug.
        event, event_ok = {}, False
    worklist = worklist_for(
        os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd()
    )
    counter = worklist.with_suffix(".blocks")

    session_id = event.get("session_id", "")

    # ---- v9: the no-op inbox-poll fast path (see WHY v9) --------------------
    # SILENT by design: a verified no-op poll stop exits 0 with NO output at
    # all, because at a 5-minute cadence even a one-line systemMessage is a
    # context fire-hose. Every condition inside is recomputed from artifacts;
    # any exception falls through to the full battery, never into an allow.
    # (A silent stop deliberately skips the .lastevent capture below, so the
    # last FULL stop's event stays available for debugging.)
    if event_ok:
        try:
            if poll_fast_path(worklist, session_id, event):
                sys.exit(0)
        except SystemExit:
            raise
        except Exception:  # noqa: BLE001 -- a broken fast path must cost, not excuse
            pass

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

    # v6: escalate unanswerable requests BEFORE reading the worklist, so a
    # freshly appended `- [?]` is classified by this very stop. Then classify
    # the log for this session's own obligations. Neither may break gating.
    req_escalated = []
    try:
        req_escalated = escalate_requests(worklist, session_id)
    except Exception:  # noqa: BLE001 -- escalation must never break gating
        req_escalated = []
    all_reqs = {}
    try:
        all_reqs = read_requests(worklist)
        req_to_me, req_bcast, req_answered, req_open_mine = classify_requests(
            all_reqs, session_id
        )
    except Exception:  # noqa: BLE001 -- a corrupt log must not wedge every stop
        all_reqs = {}
        req_to_me, req_bcast, req_answered, req_open_mine = [], [], [], []

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

    # ---- v7: regression-gate detection (see WHY v7). Never breaks gating. ---
    reg_root = project_root(event.get("cwd") or os.getcwd())
    reg_marker = reggate_path(worklist, session_id)
    reg_signals, reg_ids, reg_new_ticks, reg_sig, reg_head = [], [], [], "", ""
    reg_state, reg_forgot, reg_settled = None, False, None
    reg_done_tasks = []
    try:
        reg_state, reg_forgot = load_reggate(reg_marker)
        reg_cur_tasks = task_statuses(session_id)
        if not reg_state["head"]:
            # FAIL SAFE: first sight (or a corrupt marker just discarded)
            # initialises to the present and asks nothing this stop. Seeding
            # the check-script hashes here is what keeps prove_new_gate from
            # ever treating the ~90 pre-existing gates as candidates, and
            # seeding task statuses is what keeps I7 from demanding evidence
            # for completions that predate the marker.
            reg_state["head"] = _git(reg_root, "rev-parse", "HEAD")
            reg_state["seen_ticks"] = mine_tick_ids(lines, session_id)
            reg_state["gate_runs"] = seed_gate_hashes(reg_root)
            reg_state["task_status"] = {i: st for i, (st, _s) in reg_cur_tasks.items()}
            save_reggate(reg_marker, reg_state)
        else:
            # I7: a task that FLIPPED to completed since the last stop must
            # carry evidence (checked in the violations pass below).
            prev_ts = reg_state.get("task_status") or {}
            reg_done_tasks = [
                (i, sub)
                for i, (st, sub) in sorted(reg_cur_tasks.items())
                if st == "completed" and prev_ts.get(i) in ("pending", "in_progress")
            ]
            reg_signals, reg_ids, reg_new_ticks, reg_head = fix_signals(
                reg_root, lines, session_id, reg_state
            )
            if reg_ids:
                reg_sig = hashlib.sha1("|".join(reg_ids).encode("utf-8")).hexdigest()[:12]
            if reg_ids and reg_sig in reg_state["fixsets"]:
                # Already settled: absorb and never re-ask. The whole cost story.
                reg_state["head"] = reg_head or reg_state["head"]
                reg_state["seen_ticks"] = sorted(
                    set(reg_state["seen_ticks"]) | {t for t, _ln in reg_new_ticks}
                )
                save_reggate(reg_marker, reg_state)
                reg_signals, reg_ids = [], []
            elif not reg_ids and reg_head and reg_head != reg_state["head"]:
                # Only non-fix or doc-only-fix commits landed: nothing to ask,
                # ever, so the marker just advances.
                reg_state["head"] = reg_head
                save_reggate(reg_marker, reg_state)
    except Exception:  # noqa: BLE001 -- detection must never break gating
        reg_signals, reg_ids, reg_sig, reg_done_tasks = [], [], "", []
        if reg_state is None:
            reg_state = {"head": "", "seen_ticks": [], "fixsets": {}, "gate_runs": {}}

    # ---- v5: gather EVERY static violation, then emit ONE block -------------
    # Five independent blocking checks would cost five turns to clear, which is
    # the "stuck in a loop" the old MAX_BLOCKS existed to paper over. One
    # pre-flight, one block, every violation named at once.
    judged_ok = None
    tasks = pending_tasks(session_id)
    # THE EVENT ALREADY CARRIES ALL OF THIS. I built transcript parsing, a flush
    # retry and a whole-turn accumulator before reading a captured Stop payload
    # and finding `last_assistant_message`, `session_crons` and `background_tasks`
    # sitting in it. The transcript path stays as a FALLBACK for older payloads,
    # but the event is authoritative: it is exact, unraced, and immune to the
    # narration-block bug that made this check fire on its own author.
    last_msg = event.get("last_assistant_message") or ""
    msg_readable = bool(last_msg)
    if not msg_readable:
        last_msg, _tools, msg_readable = transcript_tail(
            event.get("transcript_path", ""), want=REMAINING_HEADING
        )
    live_crons = event.get("session_crons") or []
    # v9: the two-cron shape. The poll cron is identified by schedule shape
    # and is deliberately NOT a work wake-up: it wakes the session only when
    # another session acts.
    live_poll_crons = [c for c in live_crons if is_poll_cron(c)]
    live_work_crons = [c for c in live_crons if not is_poll_cron(c)]
    live_bg = [b for b in (event.get("background_tasks") or []) if b.get("status") == "running"]
    # Keep the raw event: when a check fires wrongly the first question is always
    # "what did the hook actually receive", and that is unanswerable afterwards.
    try:
        worklist.with_suffix(".lastevent-%s.json" % (session_id or "unknown")[:8]).write_text(
            json.dumps({k: v for k, v in event.items() if k != "transcript"}, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass
    bstate, bage, others_briefs = brief_state(worklist, session_id)
    lstate, lnext, llabel, others_loops, lcrons = loop_state(worklist, session_id)
    hstate, hage, _htext = handover_state(worklist, session_id)

    remaining_lines = (
        ["[ ] " + i for i in open_items]
        + ["task #%s [%s] %s" % (i, st, sub) for i, sub, st in tasks]
        + ["[?] " + d for d in deferred]
        + ["[>] " + f for f in in_flight]
    )
    something_remains = bool(remaining_lines)

    # STUCK DETECTION. Runs before the others so the count advances on every
    # stop, including the ones where something else already fired: a session
    # blocked three times running on the same check has also moved nothing.
    # Derive the repo from the EVENT, exactly like docs_drift below. Resolving
    # it from worklist.parent (a tmp dir) is what made the HEAD leg dead.
    stuck_n, stuck_fired, stuck_why = stuck_rounds(
        worklist,
        session_id,
        tasks,
        _git(project_root(event.get("cwd") or os.getcwd()), "rev-parse", "HEAD"),
        bool(live_bg),
    )

    violations = []
    if stuck_fired and something_remains:
        # TIER-ACCURATE HEADLINE. This used to assert "not one task changed
        # status AND HEAD did not advance" for every tier, which is FALSE for
        # the tasks-only tier: that one fires precisely BECAUSE commits do not
        # count, so it fires while HEAD is moving. A blocker that overstates
        # its own evidence teaches the session to distrust it.
        violations.append(
            M.V_STUCK
            % (
                M.STUCK_HEADLINES.get(stuck_why, "NOTHING HAS MOVED"),
                stuck_n,
                M.STUCK_DETAILS.get(stuck_why, ""),
            )
        )
    if not event_ok:
        violations.append(M.V_EVENT_UNPARSEABLE % __file__)
    if open_items:
        violations.append(
            M.V_OPEN_ITEMS % (len(open_items), "\n".join("    " + i for i in open_items))
        )
    undefaulted = [d for d in deferred if not DEFAULT_TOKEN.search(d)]
    if undefaulted:
        violations.append(
            M.V_UNDEFAULTED
            % (len(undefaulted), "\n".join("    " + d[:150] for d in undefaulted))
        )
    me8 = (session_id or "unknown")[:8]
    if req_to_me or req_bcast:
        rows = []
        for r in req_to_me + req_bcast:
            seen = brief_age_min(worklist, r["from"])
            rows.append(
                "    #%s from %s (%s, asked %s; asker %s): %s"
                % (
                    r["id"],
                    r["from"],
                    "to you" if r["to"] != "*" else "broadcast",
                    r["at"],
                    "never briefed" if seen is None else "last seen %dm ago" % seen,
                    # THE WHOLE BODY, deliberately. The operator relayed a finding
                    # by hand because it lived in a commit message nobody reads;
                    # a truncated block that points at --requests re-creates that
                    # defect, because reading the rest is again a choice. The
                    # payload rides inside the obstacle. Bounded by
                    # REQUEST_BODY_MAX at write time, so this cannot balloon.
                    r["body"],
                )
            )
        violations.append(
            M.V_REQUESTS_WAITING % (len(req_to_me) + len(req_bcast), "\n".join(rows), me8, me8)
        )
    if req_answered:
        rows = []
        for r in req_answered:
            rows.append("    #%s (you asked: %s)" % (r["id"], r["body"][:120]))
            # Full answer/decline text, same reasoning as the request body
            # above: this block IS the delivery, and a truncation would make
            # the crucial detail depend on the asker choosing to run
            # --requests. Both are REQUEST_BODY_MAX-bounded at write time.
            for a in r["answers"]:
                rows.append(
                    "      ANSWER by %s at %s: %s"
                    % (a.get("by", "?"), a.get("at", "?"), str(a.get("body", "")))
                )
            for d in r["declines"]:
                rows.append(
                    "      DECLINED by %s at %s: %s"
                    % (d.get("by", "?"), d.get("at", "?"), str(d.get("reason", "")))
                )
        violations.append(M.V_ANSWERS_UNACKED % ("\n".join(rows), me8))
    # ---- I7: a completion claim must leave a RECORD (see WHY v8) -----------
    ev_ticks = [
        line[:150]
        for _tid, line in reg_new_ticks
        if not completion_evidence(reg_root, line)
    ]
    ev_tasks = []
    for i, sub in reg_done_tasks:
        row = next(
            (ln for ln in (last_msg or "").splitlines() if re.search(r"#%s\b" % re.escape(i), ln)),
            "",
        )
        if not (row and completion_evidence(reg_root, row)):
            ev_tasks.append("#%s %s" % (i, sub))
    if ev_ticks or ev_tasks:
        violations.append(
            M.V_COMPLETION_EVIDENCE
            % (
                ""
                if not ev_ticks
                else M.V_COMPLETION_TICKS % "\n".join("    " + t for t in ev_ticks),
                ""
                if not ev_tasks
                else M.V_COMPLETION_TASKS % "\n".join("    " + t for t in ev_tasks),
            )
        )
    # Persist ONLY the transitions that passed: an unevidenced completion
    # keeps its previous status in the marker, so it is re-detected and
    # re-checked next stop rather than slipping through on a later block.
    if reg_state is not None and reg_state.get("head"):
        try:
            held = {t.split()[0].lstrip("#") for t in ev_tasks}
            prev_ts = reg_state.get("task_status") or {}
            new_ts = {i: st for i, (st, _s) in task_statuses(session_id).items()}
            for i in held:
                if i in prev_ts:
                    new_ts[i] = prev_ts[i]
            if new_ts != prev_ts:
                reg_state["task_status"] = new_ts
                save_reggate(reg_marker, reg_state)
        except Exception:  # noqa: BLE001 -- bookkeeping must never break gating
            pass
    # ---- I6: static idle detection (see WHY v8) is BELOW the Remaining scan
    # since v9, because a VERIFIED waiting-cross-session task counts as having
    # a wake-up (the enforced poll delivers the answer that unblocks it), and
    # that verification happens in the scan.
    if bstate != "ok":
        violations.append(
            M.V_BRIEF
            % (
                bstate,
                "" if bage is None else " (%d min old, limit %d)" % (bage, SESSION_BRIEF_STALE_MIN),
                (session_id or "unknown")[:8],
            )
        )
    pstate, pahead, pref = publish_divergence(project_root(event.get("cwd") or os.getcwd()))
    if pstate == "stale-local":
        violations.append(M.V_STALE_LOCAL % (pref, pahead))
    if pstate == "diverged":
        violations.append(M.V_DIVERGED % (pref, pahead, pref))
    fstate, fdetail = pr_body_freshness(project_root(event.get("cwd") or os.getcwd()))
    if fstate == "stale":
        violations.append(M.V_PR_STALE % fdetail)
    elif fstate == "unreadable":
        violations.append(M.V_PR_UNREADABLE % fdetail)
    # v9: count WORK crons only. With two crons, a dead work loop behind a
    # surviving 5-minute poll was invisible to a total-count high-water mark,
    # and the work loop dying quietly is the exact failure the operator named.
    loop_died, had_crons = cron_memory(worklist, session_id, len(live_work_crons))
    if loop_died:
        violations.append(M.V_LOOP_DIED % had_crons)
    if something_remains and hstate != "ok":
        violations.append(
            M.V_HANDOVER
            % (
                hstate,
                "" if hage is None else " (%d min old, limit %d)" % (hage, HANDOVER_STALE_MIN),
                HANDOVER_MIN_CHARS,
                HANDOVER_MAX_CHARS,
                (session_id or "unknown")[:8],
            )
        )
    dstate, ddrift, ddir = docs_drift(project_root(event.get("cwd") or os.getcwd()))
    if dstate == "drifted":
        violations.append(M.V_DOCS_DRIFT % (ddrift, " ".join(PROGRAM_SURFACE), ddir))
    # v9: the two-cron shape (operator directive). A looped session carries
    # exactly one 5-minute inbox poll beside at most one work loop.
    if live_crons and not live_poll_crons:
        violations.append(M.V_NO_POLL_CRON % me8)
    if len(live_work_crons) > 1:
        violations.append(
            M.V_MANY_WORK_CRONS
            % (
                len(live_work_crons),
                ", ".join(
                    "%s (%s)" % (c.get("id", "?"), c.get("schedule", "?"))
                    for c in live_work_crons
                ),
            )
        )
    if len(live_poll_crons) > 1:
        violations.append(M.V_MANY_POLL_CRONS % len(live_poll_crons))
    # A "blocked on you" claim the operator never confirmed is a guess about
    # someone else's intent, and it is how work parks itself indefinitely. The
    # confirmed form carries the operator's own words back.
    unconfirmed = [
        i
        for i, _, _ in tasks
        if re.search(r"#%s\b[^\n]*\bYou\b" % re.escape(i), last_msg or "")
        and not re.search(
            r"#%s\b[^\n]*You \(User Thinks So\)" % re.escape(i), last_msg or ""
        )
    ]
    if unconfirmed:
        violations.append(M.V_UNCONFIRMED % ", ".join("#" + i for i in unconfirmed))
    # THE TASK LIST IS THE OPERATOR'S VIEW. They see "23 tasks (17 done, 6 open)"
    # in the app, so a Remaining section that omits one of those six is out of
    # sync with what they are looking at. Every open task id must appear.
    missing_ids = [i for i, _, _ in tasks if not re.search(r"#%s\b" % re.escape(i), last_msg or "")]
    # EVERY REMAINING ITEM MUST DECLARE ITS STATE. "who it is blocked on" is not
    # the same question as "is anyone working it": a list where six items all look
    # alike cannot tell the operator what is moving and what is parked. The word
    # must also AGREE with the harness, which is the list they see in their app.
    state_re = re.compile(
        r"\b(ongoing|in progress|in-progress|pending|blocked|parked|waiting-cross-session)\b",
        re.I,
    )
    ONGOING = {"ongoing", "in progress", "in-progress"}
    unstated, mislabelled, uncited, xw_bad, xw_ok = [], [], [], [], []
    if REMAINING_HEADING.search(last_msg or ""):
        section = (last_msg or "")[REMAINING_HEADING.search(last_msg).start():]
        for tid, _sub, status in tasks:
            line = next(
                (ln for ln in section.splitlines() if re.search(r"#%s\b" % re.escape(tid), ln)),
                "",
            )
            if not line:
                continue  # the missing-id check below already covers this
            found = state_re.search(line)
            if not found:
                unstated.append(tid)
                continue
            word = found.group(1).lower()
            # A BLOCKER IS A CLAIM ABOUT REALITY, SO IT NEEDS A SOURCE.
            # Scoped deliberately narrow. Exempt anything already backed by
            # machinery this hook can SEE: a running background task or a live
            # lease means there is a real, named object being waited on, and
            # "blocked on the operator" has its own check above. What survives
            # the filter is exactly the Wave C class: a prose blocker naming a
            # phase of this project, which is the one shape nobody can check.
            # v9: waiting-cross-session is exempt from the file citation
            # because its request id IS the citation, verified in xsession_ok
            # across the request's whole lifecycle.
            if word == "waiting-cross-session":
                ok, detail = xsession_ok(line, all_reqs, session_id)
                if ok:
                    xw_ok.append(tid)
                else:
                    xw_bad.append("#%s: %s" % (tid, detail))
            elif word in ("blocked", "parked") and not live_bg and not in_flight:
                if not re.search(r"\byou\b", line, re.I):
                    ok, detail = citation_state(
                        project_root(event.get("cwd") or os.getcwd()), line
                    )
                    if not ok:
                        uncited.append("#%s %s" % (tid, detail))
            if status == "in_progress" and word not in ONGOING:
                mislabelled.append("#%s is in_progress but reads '%s'" % (tid, word))
            elif status == "pending" and word in ONGOING:
                mislabelled.append("#%s is pending but reads '%s'" % (tid, word))
    # ---- I6: static idle detection (see WHY v8; moved below the scan in v9) -
    # Disjoint from the stuck detector by geometry: stuck is active-but-futile
    # and needs three stops; this is inactive-with-nothing-inbound, whose
    # deadliest form produces NO further stops, so the counter never fires.
    # Scoped to tasks: open [ ] items and undefaulted [?] already block above,
    # and a worklist of defaulted [?] is time-boxed autonomy, which may stop.
    # v9: only WORK crons count as a wake-up (a poll fires but advances
    # nothing by itself), and a VERIFIED waiting-cross-session task is exempt,
    # because the enforced poll delivers the answer that unblocks it.
    idle_tasks = [
        i
        for i, _, _ in tasks
        if i not in xw_ok
        and not re.search(r"#%s\b[^\n]*You \(User Thinks So\)" % re.escape(i), last_msg or "")
    ]
    if idle_tasks and not in_flight and not live_bg and not live_work_crons and not open_items:
        violations.append(M.V_IDLE % ", ".join("#" + i for i in idle_tasks[:8]))
    if xw_bad:
        violations.append(M.V_XSESSION_BAD % ("\n".join("    " + b for b in xw_bad), me8))
    # CLAUDE.md rule 2 says discovery is always in scope and FIXING is the default;
    # the "found, not fixed" list is meant as a last resort, not a parking bay. A
    # session that ends every turn with one has converted a fixing rule into a
    # reporting habit, which is exactly what the operator objected to.
    # ANCHORED TO A LINE START, because the first version matched the phrase
    # ANYWHERE and promptly fired on a message that was DESCRIBING this very
    # check ("2. \"Found, not fixed\" is now a blocking phrase"). A gate that
    # cannot survive being written about is too broad. A real list leads a line,
    # optionally behind markdown emphasis or a heading marker; a mention sits
    # mid-sentence or inside quotes or backticks, none of which match here.
    if uncited:
        violations.append(M.V_UNCITED % "\n".join("    " + u for u in uncited))
    if re.search(r"^[ \t>*_#-]{0,6}found,?[ \t]+not[ \t]+fixed\b", last_msg or "", re.I | re.M):
        violations.append(M.V_FOUND_NOT_FIXED)
    if unstated:
        violations.append(M.V_UNSTATED % ", ".join("#" + i for i in unstated))
    if mislabelled:
        violations.append(M.V_MISLABELLED % "; ".join(mislabelled))
    # DELIBERATELY NOT CHECKED: "no task is in_progress". A queue where everything
    # is honestly parked is a legitimate state, and blocking on it would nag a
    # session that is correctly waiting. The case that actually matters -- driving
    # something while the operator's list still shows it pending -- is caught by
    # the agreement check above, which fires when the message says "ongoing" and
    # the harness disagrees.
    if tasks and REMAINING_HEADING.search(last_msg or "") and missing_ids:
        violations.append(
            M.V_OUT_OF_SYNC % (len(missing_ids), ", ".join("#" + i for i in missing_ids))
        )
    if something_remains and not msg_readable:
        violations.append(
            M.V_HOOK_BLIND
            % (
                event.get("transcript_path", ""),
                worklist.with_suffix(".lastevent-%s.json" % (session_id or "unknown")[:8]),
                __file__,
            )
        )
    elif something_remains and not REMAINING_HEADING.search(last_msg or ""):
        violations.append(M.V_NO_REMAINING % "\n".join("    " + r for r in remaining_lines[:12]))

    if violations:
        counter.write_text(str(int(counter.read_text()) + 1 if counter.exists() else 1))
        # Bank BEFORE emitting, because emit() exits the process (see :406) and
        # this is the path a busy session actually takes. See bank_pollbase.
        bank_pollbase(worklist, session_id, event)
        emit(
            {
                "systemMessage": "Stop hook: %d check(s) failed, continuing. %s%s"
                % (
                    len(violations),
                    violations[0].split("\n")[0][:110],
                    # The reggate fail-safe promises ONE line, never silence,
                    # even on a stop that blocks for other reasons.
                    ""
                    if not reg_forgot
                    else " [reggate marker was corrupt; settled verdicts forgotten]",
                ),
                "decision": "block",
                "reason": M.R_BLOCK
                % (len(violations), "\n\n".join("  " + v for v in violations), __file__),
            }
        )

    # ---- v5: static checks clean. Ask a model whether stopping is honest. ----
    # v7: a fix-signal stop consults the judge even with an empty queue,
    # because "I fixed it, all done" is exactly the stop the regression
    # question exists for.
    if (something_remains or reg_signals) and not JUDGE_DISABLED:
        streak = int(counter.read_text()) if counter.exists() else 0
        reg_scripts = package_scripts(reg_root) if reg_signals else {}
        reg_extra = ""
        if reg_signals:
            reg_extra = M.REGGATE_PROMPT % {
                "fixset": "\n".join("  " + s for s in reg_signals[:12]),
                "keys": "\n".join(
                    "  " + k for k in sorted(k for k in reg_scripts if k.startswith("check:"))
                )
                or "  (none)",
            }
        verdict, err = run_judge(
            remaining_lines, len(in_flight), last_msg, streak,
            "none declared" if lstate == "none"
            else "%s, next fire %s (%d cron%s)"
            % (llabel or "unlabelled", lnext.strftime("%Y-%m-%dT%H:%M:%SZ"), lcrons,
               "" if lcrons == 1 else "s"),
            cited_excerpts(project_root(event.get("cwd") or os.getcwd()), last_msg),
            extra=reg_extra,
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
                    "reason": M.R_JUDGE_UNAVAILABLE % (err, __file__, JUDGE_MODEL),
                }
            )
        # v7: the regression verdict is processed BEFORE the stop/continue
        # verdict, so a settle persists (and a regression block fires) even
        # when the judge would also say continue for other reasons.
        if reg_signals:
            kind, payload, detail = apply_regression_verdict(
                verdict.get("regression_gate"), reg_scripts, reg_root,
                reg_state, reg_sig, lines, (session_id or "unknown")[:8],
            )
            save_reggate(reg_marker, reg_state)  # persist gate_runs regardless
            if kind == "malformed":
                counter.write_text(str(streak + 1))
                emit(
                    {
                        "systemMessage": "Stop hook: fix landed but the judge "
                        "returned no usable regression_gate. Blocking, per "
                        "no-escape-hatch.",
                        "decision": "block",
                        "reason": M.R_REGGATE_MALFORMED % (payload, __file__),
                    }
                )
            if kind == "settle":
                rg = verdict.get("regression_gate") or {}
                reg_state["fixsets"][reg_sig] = {
                    "verdict": payload,
                    "existing_gate": str(rg.get("existing_gate", ""))[:100],
                    "blind_spot": str(rg.get("blind_spot", ""))[:300],
                    "at": datetime.datetime.now(datetime.timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                }
                reg_state["head"] = reg_head or reg_state["head"]
                reg_state["seen_ticks"] = sorted(
                    set(reg_state["seen_ticks"]) | {t for t, _ln in reg_new_ticks}
                )
                save_reggate(reg_marker, reg_state)
                reg_settled = (payload, detail)
            if kind == "block":
                counter.write_text(str(streak + 1))
                emit(
                    {
                        "systemMessage": "Stop hook: a fix landed with no "
                        "regression gate (fix-set %s). Blocking." % reg_sig[:8],
                        "decision": "block",
                        "reason": payload,
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
                    "reason": M.R_JUDGE_CONTINUE
                    % (
                        verdict["reason"],
                        verdict["next_action"],
                        "\n".join("  " + r for r in remaining_lines[:12]),
                    ),
                }
            )

    if True:
        counter.unlink(missing_ok=True)
        # An allowed stop banks the baseline too. A fast-path stop still must
        # not extend its own horizon: that bound is what stops the silent path
        # becoming a way to live on polls alone, and it survives this change
        # because poll_fast_path returns before reaching here.
        bank_pollbase(worklist, session_id, event)
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
        if req_open_mine:
            rows = []
            for r in req_open_mine:
                if r["to"] == "*":
                    who = "broadcast"
                else:
                    seen = brief_age_min(worklist, r["to"])
                    who = "to %s, %s" % (
                        r["to"],
                        "never briefed" if seen is None else "last seen %dm ago" % seen,
                    )
                rows.append("  #%s (%s; asked %s) %s" % (r["id"], who, r["at"], r["body"][:120]))
            parts.append(
                "Requests you posted, still OPEN (they block their recipients, never you):\n"
                + "\n".join(rows)
            )
        if req_escalated:
            parts.append(
                "Requests ESCALATED to operator-visible [?] items (nobody left to block):\n"
                + "\n".join("  " + e for e in req_escalated)
            )
        if reg_settled:
            parts.append(
                "Regression gate: fix-set %s settled as %s (%s); it will not be asked again."
                % (reg_sig[:8], reg_settled[0], (reg_settled[1] or "")[:160])
            )
        if reg_forgot:
            parts.append(
                "Regression marker was corrupt and has been re-initialised; previously "
                "settled verdicts were forgotten, so an old fix-set may be asked once more."
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


# GUARDED, so the module can be imported and its pure helpers tested directly.
# A bare main() call meant `import worklist` ran the whole Stop path against
# whatever happened to be on stdin, which is why the citation excerpter had no
# unit-level control until now.
if __name__ == "__main__":
    # FAIL CLOSED ON CRASH. This was the hook's global escape hatch and nobody
    # put it there on purpose: an unhandled exception prints a traceback to
    # stderr and NOTHING to stdout, the harness sees no decision, and the stop is
    # ALLOWED. So any bug anywhere in this file silently disabled EVERY check at
    # once, which is the exact opposite of the no-escape-hatch rule the rest of
    # it is built on. It is not hypothetical: a v8 cut crashed on a tuple unpack
    # and the stop sailed through; only a suite needle assertion caught it.
    #
    # A crash is now a BLOCK carrying the traceback, because a hook that cannot
    # decide must not be the way out, and the session that hits it is the one
    # positioned to fix it. Deliberately outside main() so it covers every mode.
    try:
        main()
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001 - a bare crash must not become an allow
        import traceback

        emit(
            {
                "systemMessage": "Stop hook CRASHED; blocking rather than waving the stop "
                "through. Fix %s." % __file__,
                "decision": "block",
                "reason": "THIS IS A HOOK BUG: %s crashed, so none of its checks ran.\n\n%s\n"
                "A crash used to print to stderr and nothing to stdout, which the harness "
                "reads as ALLOW, so one bug disabled every check silently. It now blocks. "
                "Fix the traceback above, then stop again."
                % (__file__, traceback.format_exc()[-1800:]),
            }
        )
