# PLAN: durable sub-agent reports, and a pushed inbox

Branch `0804-1`. Written 2026-08-05. Planning only; nothing here has been implemented.

Two asks from the operator:

- **(A)** A teammate's report arrives by SendMessage into the lead's conversation and
  nowhere the lead can look afterwards. After compaction, a substantive report and a
  silent agent are indistinguishable to a fresh session.
- **(B)** The inbox is polled by a `*/5` cron running `worklist.py --poll <me>`. Almost
  every firing prints nothing, and each one costs a full session turn. "Kind of ping when
  ready not loop."

Hard constraint: linux, windows, macOS, on amd64 and arm64.

---

## 0. What I verified myself, and what it changes

The brief's findings held up. Three things I probed independently changed the design, so
they lead.

### 0.1 The harness already has the exact event this needs, and it carries the report

`SubagentStop` is real in the installed binary (`~/.local/share/claude/versions/2.1.222`,
49 hits). Its input payload, read out of the binary's own schema strings, is:

```
last_assistant_message   "Text content of the last assistant message before stopping.
                          Avoids the need to read and parse the transcript file."
agent_transcript_path
background_tasks
session_crons
stop_hook_active
```

plus the common fields, of which two matter:

```
agent_id     "Subagent identifier. Present only when the hook fires from within a
              subagent. Absent for the main thread, even in --agent sessions."
agent_type   "Agent type name (e.g. general-purpose, code-reviewer)."
```

**This inverts the capture half of (A) completely.** The report does not have to be
scraped out of a transcript. The harness hands it over as a string, with the agent's id,
its type, and a path to its full transcript, at the exact moment it finishes. There is no
polling, no join on agent NAME, no guessing which `agent-<name>-<16hex>.jsonl` belongs to
which task.

One constraint on this event, also from the binary: `SubagentStop`'s
`hookSpecificOutput.additionalContext` is *"non-error feedback delivered to the subagent;
the subagent continues so it can act on it."* It talks **to the subagent, not to the
parent**. So `SubagentStop` is a capture hook only. Surfacing to the lead is a separate
mechanism (§2.3).

The binary also exposes `SubagentStart`, `TeammateIdle` (`teammate_name`), `TaskCreated`
and `TaskCompleted` (`task_subject`). They are fallbacks, not the primary wire; see §5.1.

### 0.2 The `no-poll` friction has a free-file escape the brief did not name

`wl_checks.py:2196` blocks a session that has any cron but no poll cron. `is_poll_cron`
(`wl_checks.py:275`) tests `POLL_SCHEDULE_RE` (`wl_checks.py:86`):

```
^(\*/(5|10|20|40)( \*){4}|0( \*){4})$
```

`0 * * * *` matches. **An hourly poll cron satisfies the check.** That is a 12x cut in
idle turns available on day one with no edit to any held file, and it doubles as the
backstop for the waiter. Friction 1 is therefore neutralised in Phase 1, not deferred.

### 0.3 The pure-wait check-in friction is real, and it cannot be dodged in free files

I traced `wl_checks.py:1646` (`if live_bg and not open_items:`) through the v17 latch
reset at `wl_checks.py:1683`. The 15-minute clock is **wall-time**, seeded on first sight
of the wait state and re-stamped only when it fires. Aligning a waiter's timeout to
`BG_REPORT_MIN` does not make the two coincide: the clock keeps running across the
relaunch, so a 10-minute waiter still eats a check-in at minute 20, 40, 60. There is no
timeout length that avoids it.

`classify_items` (`wl_store.py:661`) confirms a `- [>]` in-flight item is **not** in
`open_items`, so leasing an item does not suppress `_in_pure_wait` either.

So the honest arithmetic for a session with **no open items** (the only state where this
fires):

| shape | idle turns/hour | inbox latency |
|---|---|---|
| `*/5` poll cron (today, busy rung) | 12 | up to 5 min |
| `0 * * * *` poll cron (today, quiet rung) | 1 | up to 60 min |
| waiter + hourly cron (Phase 1) | 4 (check-ins) + 1 | seconds |
| waiter, Phase 2 (`wl_checks` taught) | 0 | seconds |

Phase 1 is a 3x win against the busy rung and a 4x loss against the quiet rung. It buys
latency, not turn count. **Turn count only goes to zero in Phase 2, in `wl_checks.py`.** I
am saying that plainly rather than claiming Phase 1 finishes (B).

I rejected raising `BG_REPORT_MIN` through a settings.json `env` block. It is free-file
reachable and it would work, but it weakens supervision of every genuine long-running
background job in the repo to buy a cosmetic win for the waiter. Not worth it.

### 0.4 Two corrections to the brief, arriving after this plan was drafted

Recorded here rather than absorbed silently, because one of them changed a design decision
and the other changed the argument for one.

**C1. The `.requests` ack ledger is NOT a read-marker, and cannot be borrowed as a
precedent for unread-ness.** The brief called it "the only unread-ness mechanism that
already survives a session restart." It is not an unread mechanism at all. Only the ASKER
may ack (`wl_requests.py:381-382`), and only after the request is already resolved
(`wl_requests.py:383-384`); the fold consumes it solely in the `mine` branch
(`wl_requests.py:246-268`) to decide whether the asker still owes action on an answer. It
is the terminal close of the asker's own loop. **For a recipient there is no read marker
anywhere in the system today**, and "unread" is currently computed as "not resolved and
not escalated", which conflates *I have not seen it* with *I have seen it and am
deliberately still working on it*.

Two consequences, both of which changed the plan:

- **The waiter must arm against a baseline, not against emptiness.** This is a real bug
  the correction caught, and §2.2 is rewritten for it. My original step 3 said "wake when
  the classified slice is non-empty." Under C1 that slice includes any request the session
  has already seen and is deliberately still working on, so the waiter would fire
  instantly on launch, every launch, forever. It must snapshot `S.my_requests_sig` and the
  set of live request ids at startup and wake only on what is NEW relative to that
  snapshot.
- **The report index's read marker is new construction with no precedent to copy.**
  §1.2 keeps the append-only-fold *discipline* of `.requests` (which is unaffected by C1),
  but the read semantics are now stated deliberately rather than inherited, and the
  reader-scoping choice is promoted to Open Question 8.

**C2. Report sizes, measured.** Over `~/.claude/projects/-home-muhammed-monorepo-console/
reports/`, markdown only, n=47: **min 3 938 B, median 17 575 B, max 115 720 B.** An
agent's in-transcript final message is much smaller, about 1.5 KB for `rm-deployments`.

This does not change the design, it hardens the argument for it, in two directions:

- The **median** report is over 4x `AGENT_STATE_MAX_CHARS = 4000` (`wl_store.py:82`). Not
  the tail, the median. Any carrier with a cap is dead on arrival, which retires the
  "just use `--state`" alternative for good rather than on a tail-risk argument.
- A 115 KB body inlined into the worklist event log would be roughly one sixth of the
  entire current log in a single record, on a file `S.load` re-reads **in full on every
  stop**. So inlining costs more on every future stop, not once at write time. §1.3's
  pointer-plus-body-elsewhere shape was already chosen; this is the stronger reason for
  it, and it is now stated there.
- The gap between the two figures also calibrates §1.2's `silent` floor: what
  `SubagentStop` hands over is the ~1.5 KB final message, not the ~17 KB authored report,
  so a 200-char floor separates "said nothing" from "said something" without catching
  terse but real reports.

Unchanged: the harness does notify on a non-zero background exit (exit 3 produced a
"failed" notification naming the code). §2.4's recommendation against using that for the
ordinary timeout path stands on its own reasoning, not on any doubt about the mechanism.

---

## 1. Design for (A): capture at SubagentStop, index by branch, surface at
   SessionStart and PostCompact

**(A) is not a persistence problem.** The brief established that; §0.1 makes it sharper.
It is *capture at a known moment*, *addressing that survives a restart*, and
*unread-ness*.

### 1.1 New file: `.claude/hooks/stop/wl_report.py`

New file, so it is free of the ownership map. Verbs, invoked directly (no dispatch through
the held `worklist.py`):

```
wl_report.py --subagent-stop        # hook mode, reads the event JSON on stdin
wl_report.py --session-start        # hook mode, emits additionalContext
wl_report.py --post-compact         # hook mode, emits additionalContext
wl_report.py --list [--unread]      # human/model read path
wl_report.py --show <id>            # the full body
wl_report.py --read <id> [<id>...]  # mark read
wl_report.py --scan                 # self-heal from the subagents dir (§5.1)
```

### 1.2 What `--subagent-stop` writes

On each fire, from the event:

1. Resolve the repo root with `C.project_root(CLAUDE_PROJECT_DIR or event.cwd)` and the
   branch with `C.git_branch(root)`. **Branch, not session.** `C.same_session`
   (`wl_core.py:144`) matches by prefix, and a restarted session has a new id, so anything
   addressed session-to-session is unreachable after a restart. Branch is the only key
   that survives, and it is the key `.agent/<branch>/` and `docs/agent/<branch>/` already
   use.
2. Write the body verbatim to
   `<store>/<branch>/<utcstamp>-<agent_type|name>-<agent_id[:8]>.md`, with a small
   front-matter block: agent id, agent type, parent session id, branch, cwd,
   `agent_transcript_path`, byte length. Bodies are stored **whole**, uncapped. That is the
   point of the mechanism, and the existing verbs all fail here for exactly this reason
   (`--state` 4000 chars, `--ask` 1000, `--add`/`--update` flatten newlines and render at
   90 chars, against a measured report population of min 3 938 B / **median 17 575 B** /
   max 115 720 B, n=47 (§0.4 C2). The median is the disqualifying figure, not the max.
3. Append **one line, hard-capped at 1024 bytes**, to `<store>/index.jsonl`:

```json
{"ev":"report","id":"<agent_id[:12]>","at":"<ISO8601Z>","branch":"main",
 "agent":"plan-reportinbox","type":"in_process_teammate","session":"d136ac61",
 "body":"main/20260805T1432Z-plan-reportinbox-e4010c81.md","bytes":18432,
 "silent":false,"title":"<first non-empty line, 120 chars>",
 "transcript":"/home/.../subagents/agent-a....jsonl"}
```

`silent: true` when `last_assistant_message` is empty or under a floor (proposed 200
chars, calibrated in §0.4 C2 against a typical captured final message of about 1.5 KB).
**This is the answer to "an agent that reports substantively and one that goes idle
silently are indistinguishable."** The distinction becomes a field, set at the moment the
agent stops, by the harness's own account of what it said.

Read-marks go to a separate append-only `<store>/read.jsonl`
(`{"ev":"read","id":...,"by":"<session8>","at":...}`). The index is never edited.

**The read marker is new construction. There is no precedent in this system to copy, and
the one the brief pointed at does not exist** (§0.4 C1: acks are the asker's terminal
close, not a recipient's read receipt; for a recipient there is no read marker at all
today). What `.requests` does supply, and what is borrowed here, is the append-only fold
*discipline*: state is derived, no writer rewrites another writer's line. The read
*semantics* are therefore stated explicitly rather than inherited:

- **A read mark is a BRANCH-level fact, not a per-reader one.** Any session on the branch
  marking a report read clears it from the surfaced block for every session on that
  branch. `by` is recorded as provenance only and is never a scoping key.
- The reason is exactly C1's trap one layer down. A per-reader marker needs a reader
  identity, the only identity available is the session id, and `C.same_session`
  (`wl_core.py:144`) matches by prefix, so a restarted session is a different reader. A
  per-reader ledger would therefore resurrect every report as unread on every restart,
  which is louder than having no marker at all and defeats the thing (A) exists to fix.
- The cost, named rather than buried: two concurrent sessions in one worktree on one
  branch share the ledger, so one can clear a report the other never saw. Only the
  *surfacing* is suppressed; the index is append-only and `--list --all` always shows
  everything. Open Question 8 puts the alternative to the operator.

### 1.3 Why the index needs no lock, and therefore no `fcntl`

One `os.open(..., O_WRONLY|O_CREAT|O_APPEND)` plus one `os.write` of a single line under
1024 bytes. POSIX guarantees atomicity for appends up to `PIPE_BUF` (4096 on Linux);
Windows serialises `O_APPEND` writes at the OS level. Bodies never contend because each
report gets a uniquely named file.

This is deliberate and load-bearing for portability: **the new code takes no lock, so it
imports no `fcntl`, so it does not inherit the Windows import death in `wl_store.py:46`.**
The 1024-byte index cap is what keeps that guarantee true, and it must be enforced by
truncating `title`, never by dropping fields.

The separation also has a cost argument independent of locking, sharpened by §0.4 C2.
Bodies must never be inlined into the worklist event log: a single 115 KB report would be
about one sixth of the entire current log in one record, on a file `S.load` re-reads **in
full on every stop**. Inlining is not a one-time write cost, it is a tax on every future
stop for the life of the log. Pointer in the index, body in its own file, and the index
line small enough to append atomically. The three constraints agree.

### 1.4 Where the store lives

Recommended default: `$HOME/.claude/agent-reports/<repo-slug>/`, where `<repo-slug>` is
the same slug `C.worklist_for` (`wl_core.py:161`) already derives from the repo root, so
worktrees stay separate without inventing a second naming scheme. Override:
`WORKLIST_REPORTS_DIR`.

Rejected, one line each:

- `/tmp/claude-worklist/` beside the worklist: dies on reboot
  (`/usr/lib/tmpfiles.d/tmp.conf:11`, `systemd-tmpfiles-setup.service --remove --boot`).
- `docs/agent/<branch>/`: tracked, and auto-dumping ~142 reports per session into a
  tracked directory poisons every PR diff. CLAUDE.md mandates *plans* there, which are
  authored and few, not machine-emitted and many.
- `.agent/<branch>/`: gitignored and in-repo, so it is safe, but it dies with the worktree
  and reports are useful across worktrees.
- Guessing Claude Code's own `~/.claude/projects/<munged-path>/` naming: it is a different
  munging from the worklist slug and it is an internal detail. `reports/` under it is
  precedent (`.claude/agents/pr-babysitter.md:146`) for *authored* round logs, not for a
  machine-written index.

This is Open Question 1 regardless; the operator may prefer in-repo.

### 1.5 Surfacing, without touching `wl_checks.py`

`.claude/settings.json` is free. Hook events accept a **list** of groups, and the file
already proves it (PreToolUse has two). So Phase 1 adds three entries:

```
SubagentStop  -> wl_report.py --subagent-stop
SessionStart  -> wl_report.py --session-start     (beside the existing worklist.py entry)
PostCompact   -> wl_report.py --post-compact      (beside the existing worklist.py entry)
```

Each emits its own `{"systemMessage": ..., "hookSpecificOutput": {"additionalContext":
...}}`, exactly as `handle_session_start` (`wl_checks.py:1226`) already does. Multiple
hooks on one event each deliver their own output.

`--session-start` must mirror the existing handler's compaction rule: `handle_session_start`
returns early on `source == "compact"` because Claude Code fires SessionStart *and*
PostCompact on every compaction and the duplicate was a real defect
(`wl_checks.py:1232-1241`). The new handler does the same, and does its work in
`--post-compact`.

The emitted block is the **unread index, collapsed**: one line per unread report
(`id`, age, agent name, `silent` flag, title), capped at, say, 25 lines with a count of the
remainder, plus the exact `wl_report.py --show <id>` and `--read <id>` commands. Bodies are
never inlined; at a median of 17.5 KB and a max of 115 KB (§0.4 C2) even a handful would be
a context bomb on every compaction.

**So (A) closes entirely in free files.** Capture at `SubagentStop`, index keyed by
branch, surfaced on the two events that mark the boundary a fresh session crosses. Phase 2
consolidation (a sticky `outq_add` line on ordinary stops) is a nicety, not a gap.

---

## 2. Design for (B): a blocking waiter, launched as a background shell task

### 2.1 The push mechanism is the background-task completion notification

There is no way for an external process to inject a turn into a session. The one push
channel that exists is the harness notifying the session when a background task finishes,
which the lead verified today (a background command exiting 3 produced a notification
naming the status and the exit code). So the shape is forced:

> A background shell task blocks until something arrives for this session, then exits.
> Its exit is the ping.

### 2.2 New file: `.claude/hooks/stop/wl_wait.py`

```
python3 /abs/path/.claude/hooks/stop/wl_wait.py <session-8-prefix> --timeout <minutes>
```

Launched with `run_in_background: true`. Absolute path, **no quotes anywhere in the
command line**. That is not cosmetic: `wl_liveness._needle` (`wl_liveness.py:175-187`)
takes the longest quote-free segment and requires >= 12 chars, and
`verify_background` (`wl_liveness.py:235-263`) only reaches `confirmed` for
`type == "shell"` tasks with a usable needle. A quoted command would render `unverifiable`,
which is what makes a healthy waiter look possibly stuck. The path alone is well over 12
chars, so this is satisfied by construction as long as nothing wraps it in quotes.

**Step 0, at launch: ARM AGAINST A BASELINE.** Before the loop starts, snapshot

- `S.my_requests_sig(worklist, session_id)` (`wl_store.py:1151`), and
- the set of request ids in this session's classified slice right now
  (`to_me + broadcasts_awaiting_me + answered_unacked_mine`), and
- the set of unread report ids in the index.

**This is the correction in §0.4 C1 applied, and without it the waiter is broken.** The
original draft said "wake when the classified slice is non-empty." C1 establishes that a
recipient has no read marker, so that slice is *not* an inbox of unseen things: it is
everything unresolved, including the request the session has already read and is
deliberately still working on. A waiter armed on emptiness would therefore fire
immediately on launch, be relaunched, fire immediately again, and spin, turning the push
mechanism into a busy loop that is strictly worse than the cron it replaces. The wake
condition is **new relative to the baseline**, never **non-empty**.

The baseline is process-local and deliberately not persisted. A waiter is a single
bounded wait; persisting its baseline would recreate the read-marker problem C1 describes,
in a file, with no owner.

Loop, once every `WORKLIST_WAIT_TICK_S` (default 2s):

1. `os.stat()` on `<worklist>.requests` for `(size, mtime_ns)`. Nothing else. The file is
   strictly append-only and never compacted (`wl_store.py:822`), so size is a sound change
   detector, and `stat()` is the only watch primitive portable to all three OSes (I
   re-confirmed the brief's probe: `epoll` is linux-only, `kqueue` absent here,
   `inotify`/`watchdog` not installed, and `pip install` is refused under PEP 668, with
   `wl_core.py:1-6` standing on "stdlib-only, no sibling imports").
2. Also `os.stat()` `<store>/index.jsonl`, so **the same waiter wakes on a new sub-agent
   report**, not only on a cross-session request. One mechanism serves both halves.
3. On any size/mtime change, **fold and classify before deciding to wake**. Cheap gate
   first: if `my_requests_sig` still equals the baseline, nothing touching this session
   changed and the tick ends there. That is what keeps foreign repo traffic from waking
   the waiter, which would be a new source of empty wake-ups and the exact cost being
   removed. Only when the signature moves does it run
   `wl_requests.classify_requests` (`wl_requests.py:238`) for the payload.
4. **Diff against the baseline**, and wake only on ids not in it: a genuinely new `ask`
   addressed to this session or broadcast, a new answer or decline on one of its own asks,
   or a new unread report id. Print those in `poll_cli`'s format (`wl_requests.py:439-458`,
   reusable verbatim, including the `--answer` / `--decline` / `--ack` command lines), plus
   the new report lines, and exit 0. Pre-existing items are **not** reprinted; they were
   already in the session's context when it launched the waiter.
5. On timeout: print one bounded line and exit 0 (Open Question 2).

One consequence worth stating, because it is a behaviour change and not an oversight: a
request that arrived *before* the waiter launched and has been sitting unanswered will not
wake it. That is correct under C1 (the session has seen it; it is in its context; the
escalation ladder at `wl_requests.py:110-235` already owns the case where it is neglected
for hours), but it does mean the waiter is a *change* detector and never a *backlog*
detector. The hourly poll cron in §3 Phase 1 is what still surfaces a backlog, which is a
second reason to keep it (Open Question 4).

**Never holds a lock.** Readers take none by design (`wl_requests.py:50-53`). This is
the sharpest hazard in the whole design: `_append_lines` (`wl_store.py:250`) takes a
**blocking** `LOCK_EX`, so an hour-long holder would stall every `--ask`/`--add`/`--tick`
in the repo, and worse, the two `LOCK_EX|LOCK_NB` paths that give up *quietly* on
contention (`wl_requests.py:196-199` escalation, `wl_store.py:789-791` dead-session
cleanup) would become permanent silent no-ops. The waiter must never open a lock file,
and the test in §6 asserts it.

### 2.3 The poll marker: do not write one

`--poll` writes a single-use pollmark (`wl_requests.py:430-433`, consumed at
`wl_checks.py:856-861`) that lets the next stop take the silent fast path. **The waiter
must not write one**, in either outcome:

- Woke on arrival: the following turn is a turn where the session *acts*, and it must not
  claim the silent fast path.
- Timed out empty: that turn genuinely is a no-op, but the pollmark would have to be
  written *before* the waiter knows which case it is in, which is precisely the bug in
  today's `--poll`.

Cost of not writing it: a timeout wake pays a full stop battery instead of a silent one.
At one timeout per 110 minutes that is negligible, and it fails in the safe direction.
Teaching `wl_checks` to accept a waiter-issued marker is Phase 2 work.

### 2.4 Exit codes

Recommended: **exit 0 on both arrival and timeout**, discriminated by stdout. Exit 2 for
misuse (matching `worklist.py:481/532`); exit 1 stays unused by this tool since it means
"rejected write" elsewhere (`worklist.py:294-296`).

The lead proved non-zero exits *do* notify with status "failed" and the code named. I am
declining to use that for the ordinary timeout path: making the normal, expected outcome
arrive as a failure notification trains both the operator and the model to ignore failure
notifications, and that is a worse defect than the one being fixed. Exit codes stay for
genuine failure.

There is a **residual uncertainty here I could not close**: the lead's test proved a
*non-zero* exit notifies. I did not verify that a background task exiting **0 with no
stdout at all** produces a notification. If it does not, a silent timeout would strand the
session with no wake-up. That is an independent reason to print the bounded timeout line
(Open Question 2), and §6.4 prescribes the probe.

### 2.5 Timeout length

Recommended default 110 minutes, just under `MAX_LEASE_MIN = 120` (`wl_core.py:58`), so a
waiter can be covered end to end by one `- [>]` lease carrying `worker:<bg-id>`. Aligning
the timeout to `BG_REPORT_MIN` buys nothing (§0.3), so it should be chosen against the
lease cap instead.

---

## 3. Sequencing against the ownership map

**HELD by another live session (do not edit):** `worklist.py`, `wl_checks.py`,
`worklist_messages.py`, `test-worklist-v5.sh`.
**FREE:** `wl_requests.py`, `wl_store.py`, `wl_core.py`, `wl_liveness.py`,
`.claude/settings.json`, and any new file.

The answer to the brief's question is **yes, a genuinely useful increment lands entirely
in free files**, and it is most of the work.

### Phase 0 (probe first, ~15 minutes, no production code)

Nothing in Phase 1 is worth writing until these are answered live. Each is a one-shot
logger hook wired into settings.json (free), writing raw stdin to a scratch file:

- **P0.1** Does `SubagentStop` fire for `taskKind: in_process_teammate` (the named
  teammates this session uses), or only for `Task`-tool sub-agents? This is the single
  largest uncertainty in the plan. The binary string
  `"Converting Stop hook to SubagentStop for <x> (subagents trigger SubagentStop)"` sits in
  the *frontmatter-hook* registration path, which suggests all subagents, but it does not
  prove it for teammates.
- **P0.2** Does it fire when an agent is interrupted or errors? The string
  `"[runAgent] SubagentStop on interrupted query failed:"` implies it is attempted; confirm
  the payload is still usable.
- **P0.3** Confirm the exact key names on the wire (`agent_id`, `agent_type`,
  `agent_transcript_path`, `last_assistant_message`). These came from schema strings in the
  binary, which is strong evidence but not the same as a captured payload.
- **P0.4** Does a background task exiting 0 with empty stdout notify the session? (§2.4)

If P0.1 comes back negative for teammates, the design does **not** collapse: §5.1's
`--scan` fallback becomes the primary capture path for teammates, driven by `TaskCompleted`
(which carries `task_subject`) and by the waiter's own tick. Capture quality drops from
"the harness hands you the report" to "read the last assistant record out of
`agent-<name>-<16hex>.jsonl`", which the lead already did successfully in one pass.

### Phase 1 (free files only)

| # | change | file | held? |
|---|---|---|---|
| 1.1 | report capture + index + surfacing | **new** `.claude/hooks/stop/wl_report.py` | no |
| 1.2 | the blocking waiter | **new** `.claude/hooks/stop/wl_wait.py` | no |
| 1.3 | its test harness | **new** `.claude/hooks/stop/test-report-inbox.sh` | no |
| 1.4 | wire SubagentStop + second SessionStart + second PostCompact | `.claude/settings.json` | no |
| 1.5 | guard the `fcntl` import; keep read paths alive on Windows | `wl_store.py`, `wl_requests.py` | no |
| 1.6 | `TMPDIR` -> `tempfile.gettempdir()` | `wl_core.py:162` | no |
| 1.7 | demote the poll cron to `0 * * * *` | operator/session action, no file | n/a |

1.7 is not a code change: it is `CronDelete` + `CronCreate` on the running session, and it
alone takes idle poll turns from 12/hour to 1/hour while satisfying the `no-poll` check
(§0.2).

### Phase 2 (needs held files; land when they free)

| # | change | file | why it waits |
|---|---|---|---|
| 2.1 | `--wait` and `--reports` verb aliases so there is one CLI door | `worklist.py` | dispatch is a held file |
| 2.2 | accept a `confirmed` waiter in place of a poll cron in the `no-poll` check | `wl_checks.py:2196` | friction 1's real fix; lets the hourly cron go away |
| 2.3 | suppress the pure-wait check-in when the only live bg task is a `confirmed` waiter | `wl_checks.py:1646-1683` | friction 2's only real fix (§0.3) |
| 2.4 | sticky `outq_add` line for unread reports on ordinary stops | `wl_checks.py` | consolidation; §1.5 already covers the compaction boundary |
| 2.5 | test cases into the 431-case harness | `test-worklist-v5.sh` | held; Phase 1 ships its own file |

2.3 has a principled justification, not just convenience: v17 already reads
`verify_background` on **every** pure-wait stop because "a worker dying is the one change a
byte-level view cannot see" (`wl_checks.py:1668-1671`). A waiter whose liveness is
OS-confirmed and whose *exit is itself the wake-up* needs no human check-in. Its liveness
is the report. The check should fire on an unverifiable or suspect waiter exactly as it
does today.

---

## 4. The two frictions, answered directly

**Friction 1, `no-poll` (`wl_checks.py:2196-2197`).** Avoided in Phase 1 with no held-file
edit, by keeping an hourly `0 * * * *` poll cron, which `POLL_SCHEDULE_RE` accepts (§0.2).
The cron is also the backstop for a waiter that dies unnoticed. Removed for real in Phase 2
by 2.2.

**Friction 2, the 15-minute pure-wait check-in (`wl_checks.py:1646-1683`,
`BG_REPORT_MIN = 15`).** **Cannot be avoided in free files.** I traced it and there is no
timeout length, no lease, and no item state that suppresses it: the clock is wall-time and
`- [>]` items are excluded from `open_items` (`wl_store.py:661-706`). Phase 1 pays 4
check-ins per idle hour, which is 3x better than the `*/5` rung and 4x worse than the
`0 * * * *` rung. Phase 2's 2.3 is the fix. I considered and rejected raising
`BG_REPORT_MIN` via a settings.json `env` block: free-file reachable, but it degrades
supervision of every real background job in the repo.

---

## 5. Robustness

### 5.1 Self-healing capture, so the index does not depend on one hook firing

`wl_report.py --scan` walks `~/.claude/projects/<proj>/*/subagents/*.meta.json`, and for
any agent with no index entry whose `.jsonl` has stopped growing for N minutes, extracts
the last `type: "assistant"` text and indexes it with `source: "scan"`. The waiter runs
`--scan` on a low duty cycle (say every 60 ticks) since it is awake anyway.

This makes the index correct regardless of which of `SubagentStop` / `TaskCompleted` /
`TeammateIdle` actually fire for which task kind, which is the Phase 0 unknown. The meta
sidecar carries `agentType`, `description`, `name`, `taskKind`, `teamName`; the transcript
records carry `agentId`, `sessionId`, `gitBranch`, `cwd`, `timestamp`. Between them there
is enough to build a full index entry without the hook. I verified both shapes directly.

### 5.2 Failure modes that must fail safe

- Report store unwritable: the hook prints nothing, exits 0. A capture hook must never
  wedge a subagent's stop.
- `index.jsonl` has a torn tail: readers skip unparseable lines, same rule as `.requests`.
- Waiter crashes: the hourly poll cron still delivers, at the old latency. This is why 1.7
  stays in place through Phase 1.
- Waiter is `unverifiable`: the existing pure-wait ladder reports it as such, which is the
  behaviour we want and the reason the command must stay quote-free.

---

## 6. Testing: proving each piece can FIRE

Phase 1 ships `.claude/hooks/stop/test-report-inbox.sh` (new file, since the 431-case
harness is held). Every case asserts **both** the positive and its negation, per the
repo's standing rule that a gate which cannot fail is worthless.

### 6.1 Waiter

1. **It can fire.** Start the waiter against a scratch worklist with a 60s timeout, append
   an `ask` addressed to `<me>`, assert it exits 0 within 5s and stdout contains
   `INBOX #<rid>` and the `--answer` command line. *Control:* the same run with no append
   must reach the timeout.
2. **It does not fire on foreign traffic.** Start it, append an `ask` from and to two other
   prefixes, assert it is still running after 10s and that stdout is empty. This is the
   test that proves the fold in step 3 of §2.2 is real and that size alone is not the wake
   condition. *Control:* flip the `to` field to `<me>` in the same fixture and assert it
   does wake.
2b. **It does not fire on a pre-existing request** (the §0.4 C1 regression). Seed the
   `.requests` log with an unresolved `ask` addressed to `<me>` *before* launching the
   waiter, then launch it and assert it is still running after 10s with empty stdout. This
   is the spin-loop case, and it is the one bug in this plan that a correction caught
   rather than a test, so it gets a permanent test. *Control:* with that same seeded
   request still unresolved, append a second `ask` to `<me>` and assert the waiter wakes
   and prints **only** the second one, never the seeded one.
3. **It never takes the lock.** With the waiter running, run `worklist.py --ask` from a
   second process and assert it completes in under 1s. *Control:* the same measurement
   while a deliberate `LOCK_EX` holder runs, asserting it does block, so the test is proven
   able to detect the failure it is checking for.
4. **Torn tail.** Append a truncated line with no newline, assert the waiter neither
   crashes nor wakes.
5. **Misuse.** Short prefix -> exit 2, message on stderr, nothing on stdout.

### 6.2 Report capture

6. **Substantive report.** Feed `--subagent-stop` a synthetic payload on stdin, assert a
   body file exists with the exact bytes, one index line appended, `silent:false`, and the
   index line under 1024 bytes.
7. **Silent agent.** Same with `last_assistant_message: ""`, assert `silent:true`. *This is
   the case (A) exists for*, so it gets its own assertion, not a shared one.
8. **Index atomicity.** Fire 50 `--subagent-stop` invocations concurrently, assert exactly
   50 parseable lines and zero interleaved ones. This is the test that validates the
   no-lock decision in §1.3; if it fails, the design needs a lock and the portability story
   changes.
9. **Branch keying.** Fire under two different `WORKLIST_AGENT_BRANCH` values, assert the
   bodies land in separate subdirectories and both index lines carry the right branch.

### 6.3 Surfacing

10. **Unread appears.** Run `--session-start`, assert `additionalContext` names the unread
    report ids. Mark them read with `--read`, run again, assert the hook emits **nothing**.
    Both halves are required: an empty surface is only meaningful if a non-empty one was
    demonstrated first.
10b. **Read marks are branch-scoped and survive a session change** (§1.2, the C1-driven
    decision). Mark read as session A, run `--session-start` with a *different*
    `session_id` on the same branch, assert it emits nothing. *Control:* run it with a
    different `WORKLIST_AGENT_BRANCH` and assert the report is unread there. This is what
    proves the ledger is keyed on branch and not on the reader, which is the whole reason
    it does not resurrect on restart.
11. **Compaction path.** `--session-start` with `source: "compact"` must emit nothing;
    `--post-compact` must emit. Mirrors `wl_checks.py:1232-1241`.

### 6.4 Live probes (not automatable, must be run by hand)

12. Phase 0's P0.1 to P0.4.
13. End to end: spawn a trivial teammate, let it report, compact the lead, and confirm the
    report id shows up in the PostCompact context. This is the only test that proves the
    whole (A) chain, and it cannot be faked with fixtures.

---

## 7. Portability

**New code (`wl_report.py`, `wl_wait.py`) is portable from the start:**

- No `fcntl` (§1.3 removes the need for a lock in the new write path).
- No `os.pread` / `os.pwrite`.
- No `os.getuid()`; where a scratch path is needed, `tempfile.gettempdir()` and
  `getpass.getuser()` behind a `try`.
- No `/proc`, no `ps`.
- Waiting is `os.stat()` + `time.sleep()` only. `time.monotonic()` for the timeout, never
  wall clock.
- Paths via `pathlib`; no hard-coded separators.
- Hook commands in settings.json use `python3`, matching the existing entries. **This is a
  known Windows gap** (Windows ships `python`, not `python3`) and I am deliberately not
  fixing it here, because the existing worklist hooks have the same gap and changing the
  interpreter invocation for all of them is its own task.

**Pre-existing breaks I recommend touching (both free, both one line, both no-ops on
Linux):**

- `wl_store.py:46` and `worklist.py:109` import `fcntl` at module scope, so on Windows the
  hook does not degrade, it dies at import. Phase 1 guards the import in `wl_store.py` and
  `wl_requests.py` (free) so that **read** paths, which take no lock by design, keep
  working, and **write** paths raise a clear named error. `worklist.py:109` is held and
  stays broken for now. This does not make the hook Windows-complete; it makes the new
  read-only surfaces usable there.
- `wl_core.py:162` reads `TMPDIR` only, while Windows sets `TEMP`/`TMP`.
  `tempfile.gettempdir()` honours `TMPDIR` first on POSIX, so this is byte-identical on
  Linux and macOS.

**Pre-existing breaks I am NOT fixing, and why:**

- `os.pread`/`os.pwrite` in `_append_lines` (`wl_store.py:255`) and `compact`
  (`wl_store.py:805`): Unix-only, and they sit in the two most load-bearing writes in the
  system. Porting them is a real change to the durability story and does not belong in a
  task about reports and inboxes.
- `os.getuid()` unguarded at `wl_liveness.py:213`.
- The `/proc` scan with a `ps` fallback and no Windows path.
- **The ~20 other hooks in settings.json are `bash` scripts.** I agree with the brief:
  this is a far larger Windows problem than the Python modules, and it is out of scope. It
  is worth saying out loud that until those are addressed, "the worklist works on Windows"
  cannot be true no matter how portable the Python is. That belongs in its own plan.

amd64 vs arm64 is a non-issue: nothing in the hook tree is architecture-sensitive.

---

## 8. Open questions for the operator

Each is a real choice I should not make alone. Defaults are what I will do if there is no
answer.

**Q1. Which durability tier holds the report bodies and index?**
- **(a) `$HOME/.claude/agent-reports/<repo-slug>/` (recommended default).** Reboot-safe,
  outside git, never pollutes a PR diff, survives a worktree being deleted. Cost: a fresh
  clone of the repo on another machine has none of it, and it is invisible to code review.
- (b) Tracked `docs/agent/<branch>/`. Reports become reviewable artifacts and travel with
  the repo. Cost: roughly 142 machine-written files per session landing in PR diffs. I
  think this is disqualifying, but it is the operator's call and it is the tier CLAUDE.md
  names for plans.
- (c) Gitignored `.agent/<branch>/`. In-repo and branch-scoped, no diff pollution. Cost:
  dies with the worktree, and reports are often wanted after the branch is gone.

**Q2. On timeout, does the waiter print nothing or one bounded line?**
- **(a) One bounded line, exit 0 (recommended).** `INBOX-WAIT: 110m elapsed, nothing for
  <me>`. Both precedents exist and point opposite ways: `--poll` prints nothing on an empty
  inbox by explicit operator contract (`wl_requests.py:438`), while the repo's standing
  "prove the instrument" rule says a check you cannot see run is worthless. The tiebreaker
  is §2.4's unresolved question: I have not confirmed that an exit-0, zero-output
  background task notifies the session at all. If it does not, a silent timeout is a
  session that never wakes up.
- (b) Print nothing. Cheapest possible turn, consistent with `--poll`. Accepts the
  notification risk above.
- (c) Non-zero exit to signal timeout. Proven to notify, but it makes the normal outcome
  arrive as a "failed" notification, which teaches everyone to ignore failure
  notifications.

**Q3. Waiter timeout length.**
- **(a) 110 minutes (recommended).** Just under `MAX_LEASE_MIN = 120`, so one `- [>]` lease
  covers a whole waiter.
- (b) 15 to 20 minutes. More wake-ups, but the session re-evaluates its situation more
  often and a dead waiter is noticed sooner.

**Q4. Does the waiter replace the poll cron in Phase 1, or run beside it?**
- **(a) Beside an hourly `0 * * * *` cron (recommended).** Satisfies the `no-poll` check
  with zero held-file edits, and backstops a waiter that dies. Cost: one extra turn per
  hour.
- (b) Delete the cron entirely. Cheapest, but every stop is then blocked by the `no-poll`
  violation until Phase 2 lands, which is strictly worse than the status quo.

**Q5. Capture every sub-agent, or only named teammates?**
- **(a) Capture all, surface all unread, collapsed (recommended).** ~142 index lines per
  session at roughly 200 bytes each is about 28 KB of index; bodies are on disk and never
  inlined. Completeness is the point: the silent-agent case is only detectable if the
  silent agent is captured.
- (b) Capture only `in_process_teammate` tasks. A tenth of the volume, but a `Task`
  sub-agent that found something real and went unread is exactly the failure being fixed.

**Q6. Retention.** Nothing prunes the store today. Recommended default: prune bodies older
than 30 days on `--scan`, keep index lines forever (they are small and they are the
history). Alternative: keep everything and let the operator prune by hand.

**Q7. Are the Phase 2 `wl_checks.py` edits worth making at all?** They are the only way to
get idle turns to zero (§0.3), but they touch a file another session holds and they change
a supervision check that exists for good reasons. If the answer is no, Phase 1 stands on
its own with 4 check-ins per idle hour, and (B) is delivered as a latency win rather than
a cost win. I recommend yes, but scheduled deliberately once the file frees, not squeezed
in.

**Q8. Is a report "read" a branch-level fact or a per-reader one?** New, raised by §0.4 C1:
there is no existing read marker anywhere in this system, so this is a genuine first-time
choice rather than a convention to follow, and the brief's stated precedent turned out not
to be one.
- **(a) Branch-level (recommended default).** Any session on the branch marking a report
  read clears it from the surfaced block for everyone on that branch; the index still holds
  everything and `--list --all` always shows it. Survives a restart correctly, which is the
  requirement. Cost: two concurrent sessions in one worktree share the ledger, so one can
  clear a report the other never saw.
- (b) Per-reader, keyed by session id. Each session sees what it personally has not read.
  Cost: `C.same_session` (`wl_core.py:144`) matches by prefix, so a restarted session is a
  *different* reader and every report resurrects as unread on every restart. That is louder
  than having no marker at all and defeats the thing (A) exists to fix. I do not recommend
  it, but it is the shape most people expect from the word "unread", so it should be a
  conscious rejection rather than an omission.
- (c) Per-reader keyed by something stabler than the session id (branch plus a declared
  agent name, say). Gets both properties, at the cost of inventing an identity concept the
  system does not have. Worth doing only if (a)'s concurrent-session cost bites in practice.

---

## 9. Things I am not sure about

Flagged rather than guessed.

1. **Whether `SubagentStop` fires for `in_process_teammate` teammates.** The largest
   unknown. Phase 0 P0.1. §5.1 is the fallback and it is real, but it is meaningfully worse
   than the hook.
2. **Whether an exit-0, zero-stdout background task notifies the session.** The lead proved
   the non-zero case only. Phase 0 P0.4, and it drives Q2.
3. **The exact hook payload key names.** Read from schema strings in the binary, which is
   strong but is not a captured payload. Phase 0 P0.3.
4. **Whether multiple hooks on one event reliably deliver each one's
   `additionalContext`.** The settings shape allows the list and PreToolUse already uses it,
   but I did not find explicit merge semantics for `additionalContext` from two hooks on the
   same event. If only one survives, §1.5 must instead extend the *existing* handlers, which
   are in the held `wl_checks.py`, and (A)'s surfacing moves to Phase 2. **This is the single
   assumption most likely to move the plan's phase boundary, so probe it in Phase 0
   alongside P0.1.**
5. **The 1024-byte atomic-append assumption on Windows.** POSIX `PIPE_BUF` is well
   documented; the Windows guarantee is weaker in the literature than I would like. Test 8
   in §6.2 is the check, and it must be run on Windows before anyone claims portability, not
   only on Linux.
6. **Whether an hourly poll cron feels acceptable to the operator in the interim.** It is a
   12x cut, but it is still a loop, and the ask was explicitly "ping when ready not loop."
   Q4 exists for that reason, and §2.2's closing note gives it a second job: the waiter is
   a change detector, never a backlog detector, so something still has to surface a request
   that predates the waiter.
7. **How often the branch-level read ledger's shared-clearing actually bites** (§1.2, Q8).
   Two concurrent sessions in one worktree on one branch is this repo's normal state, not
   an edge case, so option (a)'s cost is not hypothetical. I still recommend it, because
   option (b) is broken in a worse and less visible way, but I would not be surprised to be
   sent back here.
8. **Whether anything else in this plan rests on a premise I inherited rather than
   checked.** Two of the brief's stated facts turned out to be wrong or imprecise (§0.4),
   one of which was hiding a spin-loop bug in the waiter. The claims I verified myself are
   cited with `file:line` or with the binary probe that produced them; the ones I did not
   are in this list. Anything in the plan that is neither is worth a second look before it
   is built on.
