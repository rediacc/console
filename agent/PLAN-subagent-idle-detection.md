# Subagent idle/liveness detection

Status: ready
Origin: session 0ad063bf, 2026-08-23. Design by a Plan agent, verified against live artifacts.
Operator: approved to build; asked to be present when it starts.

## Why

A lead spawned two writer subagents. Both finished. The lead did not learn either
had stopped, and had no way to tell "still working" from "finished" from "died".
Four things were tried and each failed in a different way:

1. `ListAgents` returned "No reachable agents" while both agents still had recent
   file writes. `docs/agent-reference/TRAPS.md` already records that its silence
   is not death, so it cannot be a liveness signal.
2. **File mtimes.** The lead inferred "both are actively writing" from `stat`.
   This is the error the operator caught: an mtime says when an agent LAST wrote,
   never whether it is alive. A live fact asserted from a lagging indicator.
3. **Waiting for the completion notification.** One agent's `sends: 0` -- it
   finished and wrote its report as plain assistant text, never calling
   `SendMessage`. Per that tool's own docs, plain output is not visible to other
   agents. The lead waited for a message that by design was never coming.
4. `wl_report.py --list --unread` was run BEFORE the report existed and the stale
   answer was treated as current. The report had been on disk, unread, correct,
   from 12:30:50Z.

Cost: four items sat `[>]` on a stopped worker for 3.5 hours, their leases
running 110 minutes past the point the work was done.

## The signal that already exists

**The last JSONL record of a subagent transcript states whether it is mid-turn or
finished**, is self-recorded, and cannot be faked by a self-report:

- finished -> `type: assistant`, `stop_reason: end_turn`, content `['text']`
- working  -> `stop_reason: tool_use`, or `type: user` with `tool_result`, or
  `stop_reason: None` (streaming)

Scored **9/9** against ground truth over this session's nine real transcripts,
and re-scored correctly three hours later after two agents resumed. At 12:30:50Z
it would have said `phase3-release: IDLE`.

## What the hook can and cannot verify today

- `wl_liveness.verify_background()` short-circuits every non-`shell` task to
  `unverifiable`; teammates have no OS process by design.
- `live_teammate_transcripts()` returns a COUNT, not a mapping. Its docstring
  argues no join exists because `background_tasks` descriptions collide -- true
  for anonymous tasks, but NOT for named teammates, whose
  `subagents/agent-a<name>-<hex>.meta.json` carries `"name"`.
- **The structural dead end:** `ladder()` computes
  `gone = wid and wid not in now_bg and rec.get("worker_verified")`.
  `worker_verified` is set only when the id is in the harness's running list, and
  a NAME never is. So for a name-leased teammate `gone` is unreachable BY
  CONSTRUCTION, leaving only the raw 45/90/120 age ladder. That is the blindness.

Do not loosen `gone`; it was deliberately tightened after a false death. Add a
verdict that is POSITIVELY proven instead of inferred from absence.

## Design

One new function, one new verdict, four call sites. No new infrastructure, no
polling, no new files.

**1. `wl_liveness.teammate_state(cwd, session_id, name)` -> (verdict, quiet_min, last_ts, agent_id)**

Resolve by globbing `<proj>/<session_id>/subagents/*.meta.json` and matching
`info["name"]`; on collision take the newest sibling `.jsonl` by mtime. Read the
last parseable record from a bounded tail.

| verdict | condition | meaning |
|---|---|---|
| `idle` | last record is assistant, `stop_reason` in {end_turn, stop_sequence, max_tokens}, no `tool_use` block | positively proven not working |
| `working` | mid-turn AND `quiet_min < BG_STALE_MIN` | verified running |
| `stalled` | mid-turn AND `quiet_min >= BG_STALE_MIN` | SUSPECT, reported in those words, never "dead" |
| `unverifiable` | no meta matches, unreadable, no parseable record | unchanged |

`idle` is not a death claim. It says the worker FINISHED ITS TURN, which is true
whether it is resumable or terminated, and it is backed by a record the agent
wrote about itself. A resumed teammate flips back to `working` on the next stop
because this reads a LEVEL, not a transition.

**Failure direction is safe on purpose.** `stop_reason: None` (streaming
partials, 410 of 701 assistant records in the sample) classifies as `working`. A
false `working` is the status quo; a false `idle` would be new harm. The
classifier never guesses toward idle.

**2. Correlate with the report the agent already filed.** When `idle`, look up
the newest `wl_report` index entry with `agent == name` and `at >= lease at`, via
`wl_report.unread(...)`, already imported in `wl_checks.py`. Carry its id and
title into the message so the next step is `wl_report.py --show <id>` rather than
a status-check round trip. **This is the piece that would have saved the 3.5
hours.**

**3. Wire into `ladder()`.** For each `[>]` item whose `wid` is not in `now_bg`
and not `worker_verified` -- the case that today falls through to pure age --
call `teammate_state`. Return a fifth list, `idles`.

- Report immediately, NON-blocking, on the first stop where the worker is `idle`.
- Block once per stamp when `idle` AND `quiet_min >= WORKER_IDLE_BLOCK_MIN`
  (new, env-tunable, default 15), gated through `fire_once`.
- `blocking_rung_due()` must learn the `idle` key or the poll fast path
  disagrees with the latch -- that exact disagreement is a documented deadlock.
- `stalled` joins `investigates` with stall-specific wording. `unverifiable`
  changes nothing.

**4. Surface in the guide row** so the state is visible before any rung fires:

    - [>] #428406bb (quiet 206m, worker:phase3-release [IDLE 206m]) ...
          it reported: "Phase 3 is complete. Everything is uncommitted."  (report fc3f4a0f5447)
          NEXT: read it (wl_report.py --show fc3f4a0f5447), then --tick / --lease <id> release / re-lease

## What happens to a lease whose worker verifiably stopped

**Nothing automatic.** It must never become "done" and never become "dead". The
item stays `[>]`; the check adds information and offers three exits that already
exist: `--tick` with evidence, `--lease <id> release`, or re-lease to a new
worker. No auto-tick (that is the silent-completion failure), no auto-unlease (an
idle teammate is resumable and one proved it by resuming 11 minutes later).

## Controls

0. **Live, runnable now.** The classifier over this session's real `subagents/`
   dir: six finished Plan/Explore agents must return `idle`, the running ones
   `working`. Already run: 9/9. A real red/green pair from production data.
1. **The mutation pair.** Fixture whose last line is
   `{"type":"assistant","message":{"stop_reason":"end_turn",...}}` -> assert
   `idle`. **Mutate that one field to `tool_use` -> assert the check STOPS
   reporting idle.** Without the second pass the assertion is vacuous.
2. **Stall must not say dead.** Mid-turn last record, `.jsonl` backdated 60 min.
   Assert `stalled`, and assert the emitted text contains neither `dead` nor
   `gone`.
3. **Unverifiable is never accused.** Lease `worker:no-such-agent-name`. Assert
   `unverifiable`, no idle claim, no death claim.
4. **Resume clears the verdict.** Idle fixture, assert idle; append a `tool_use`
   record, assert `working`. Regression guard for the false-death this replaces.
5. **End-to-end.** `[>]` item on an idle worker: assert the guide row carries the
   annotation and the ladder fires ONCE across two stops (the `fire_once` latch),
   then flip to working and assert the annotation disappears.

## Two findings to fix or record while in there

- `wl_report.scan()` decides an agent is finished by **5 minutes of mtime
  silence** -- the same lagging-indicator error, embedded in the self-heal path.
  A slow agent thinking for six minutes gets indexed mid-flight with a partial
  answer. The content check is strictly better and should replace it.
- The root cause of the original silence was `sends: 0`. A line in the
  writer-agent brief template requiring a `SendMessage` on completion prevents
  it. That belongs in the template, not the hooks.

---

## Addendum, 2026-08-23 — the `TeammateIdle` hook event (operator, mid-build)

The operator asked whether `TeammateIdle` (code.claude.com/docs/en/hooks#teammateidle)
could be used instead, and whether the Stop-hook app could be auto-run with parameters
to record the update. Both are right, and both are ADDITIVE. The design above does not
change; it gains a precision layer and loses none of its authority.

**What the docs actually say** (fetched, not assumed): `TeammateIdle` is one of 31 hook
events. It fires "when an agent team teammate is about to go idle", takes **no matcher**
(always fires), receives the common input fields (`session_id`, `transcript_path`, `cwd`,
`hook_event_name`, and `agent_id`/`agent_type` in subagent context), and **can block** —
exit 2 prevents the teammate going idle and it continues working. `SubagentStop` is
already wired here (`.claude/settings.json:171` → `wl_report.py`), which is the precedent
that this class of event reaches this repo at all.

### Why the transcript classifier stays load-bearing

Three reasons, in order of how badly each would bite:

1. **There is no un-idle event.** `SubagentStart` fires at start; nothing fires when an
   idle teammate resumes. A journal of idle edges therefore reports idle FOREVER once
   written. The plan is emphatic that a resumed teammate must flip back to `working` on
   the next stop (Control 4 exists for exactly this, and it guards the false-death this
   whole item replaces). Only a LEVEL read can do that, and the transcript tail is the
   level.
2. **A missing event is not evidence of anything.** If `TeammateIdle` does not fire for
   Agent-tool subagents in this harness — unproven, and "teammate" may well mean the
   agent-teams feature specifically — then absence of a journal entry is indistinguishable
   from a worker that never went idle. That is precisely the `ListAgents` error this plan
   already rejects in its "Why" section: silence read as a signal.
3. **The classifier is proven and the event is not.** 9/9 against ground truth over nine
   real transcripts, re-scored correctly three hours later after two agents resumed.
   Nothing about the event has been observed firing here yet.

### The shape, then

**Journal for the EDGE, transcript for the LEVEL.**

- A new `TeammateIdle` entry in `.claude/settings.json` runs
  `worklist.py --teammate-idle` with the hook payload on stdin. It appends one record —
  name (or `agent_id`), timestamp, session — to a sidecar beside the store, and **always
  exits 0**. It never blocks: exit 2 here would pin a teammate the lead did not ask to
  keep working, which is a worse failure than the one being fixed, and is explicitly out
  of scope.
- `teammate_state()` consults the sidecar FIRST for `quiet_min`, because a self-recorded
  edge timestamp is exact where an mtime is a lower bound. It still classifies the verdict
  from the transcript tail.
- **Where they disagree, the transcript wins toward `working`.** A journal entry saying
  idle plus a transcript whose last record is mid-turn means the teammate resumed after
  the event fired. Same failure direction as the rest of the design: never guess toward
  `idle`.
- If the sidecar is empty or absent, behaviour is exactly the plan above. That is the
  control that keeps this honest — the feature must not depend on an event nobody has
  watched fire.

### Control 6 (new)

Prove the layering, both directions:
- A sidecar entry for a name whose transcript is mid-turn → verdict `working`, NOT idle.
  (Journal alone must never manufacture an idle verdict.)
- An idle transcript with NO sidecar entry → still `idle`, with `quiet_min` from the
  transcript. (The feature degrades to the proven path rather than going silent.)
- An idle transcript WITH a sidecar entry → `idle`, and `quiet_min` comes from the
  sidecar's timestamp, not the mtime.

Whether `TeammateIdle` ever actually fires here is then an observation to make in live
use, not a load-bearing assumption. If it does, the journal sharpens the numbers; if it
never does, nothing regresses.

### Addendum 2 — why NOT a `PreToolUse` heartbeat (operator asked, 2026-08-23)

The operator asked whether a `PreToolUse` hook could supply the missing un-idle
edge: a small fast command on every tool call, recording that the teammate is
alive. The instinct is exactly right — an un-idle signal is what a journal of
idle edges lacks — but the signal it would create **already exists for free.**

`PreToolUse` fires in the teammate's own context and would give
"teammate X was alive at T". That is precisely what the transcript's **mtime**
already says: the harness appends a record per tool call and per assistant
message, so the .jsonl's mtime IS the last-activity timestamp, maintained by the
harness at zero cost. `teammate_state()` already reads it as `quiet_min`.

What a heartbeat would ADD is nothing; what it would COST is real:

- It fires on **every tool call of every agent**. This repo already runs 27
  `PreToolUse` hooks, so the marginal cost is another interpreter spawn per tool
  call, per teammate, forever — on the hot path of every session.
- It is a **second source of truth for a fact the first source already carries**,
  and the two can disagree (a heartbeat written while the transcript write fails,
  or vice versa). The plan's whole discipline is one authority per question.
- It does not fix the case it appears to fix. A teammate that resumes writes to
  its transcript *before* it calls a tool (the assistant record comes first), so
  the transcript sees the resume at least as early as a `PreToolUse` heartbeat
  would, and sometimes earlier.

**Decision: not built.** The un-idle edge is served by the level read that is
already load-bearing. Recorded here so the question is not re-opened from
scratch — it is a good idea whose answer is "we already have it", not "no".

---

## Addendum 3, 2026-08-23 — the live probe, and the two things it overturned

The operator asked for a subagent to be spawned and traced. Three probes were run
(`idle-probe`, `idle-probe2`, `idle-probe3`), each busy ~40-60s then finishing.
This is the observation Addendum 1 said to make in live use, and it did not
confirm what was written there — it corrected it twice.

### Finding 1: `TeammateIdle` DOES fire here, and its payload is undocumented

Addendum 1 called it "unproven, and 'teammate' may well mean the agent-teams
feature specifically". It fires, for an ordinary Agent-tool subagent, within a
second of the turn ending. Traced live:

    20:48:13  working   last=assistant/tool_use/tool_use   journal=3
    20:48:23  working   last=assistant/tool_use/tool_use   journal=3
    20:48:33  idle      last=assistant/end_turn/text       journal=4

But the first two probes journalled `name: null`, and `idle_edge` joins on name,
so **the hook fired correctly and every record it wrote was unusable** — the
failure mode that looks exactly like a hook that never fires. The cause is that
the published hook reference documents **no input schema for TeammateIdle at
all**, so the first cut guessed `agent_id` plus a transcript-sibling lookup. The
real payload, captured by recording the KEYS of any record whose name would not
resolve:

    cwd, hook_event_name, permission_mode, prompt_id, session_id,
    team_name, teammate_name, transcript_path

No `agent_id`. No `name`. The name is `teammate_name`. Reading it fixed the join
on the next probe. **The diagnostic stays in the code**, because the next payload
change will be just as silent as this one.

### Finding 2: the transcript CANNOT always see the end of a turn

This is the one that matters, and no amount of reading would have found it.
`idle-probe3` finished with a last record of:

    assistant / stop_reason: None / ['text']

A streaming partial. This design classifies that as `working` **on purpose** —
410 of 701 assistant records in the original sample are `stop_reason: None`
mid-turn, and the whole failure-direction rule is that a false `idle` is new
harm. But the agent had finished. Its transcript would have read `working`
forever: this item's own blindness, wearing a safer-looking hat.

So the sidecar is **not** merely a precision layer, and Addendum 1 was wrong to
frame it as one. It positively resolves a state the transcript cannot express.
The rule is now:

> An idle edge decides the verdict **only while nothing has been written after
> it**. `last_ts <= edge + IDLE_EDGE_EPSILON_S` (default 2s).

That is what keeps it safe rather than making it a guess. `TeammateIdle` is the
harness stating the teammate went idle — self-recorded, strictly stronger than a
tail read — and a teammate that RESUMES writes, so its mtime moves past the edge
and the verdict falls back to `working`. The epsilon exists because two different
clocks-of-record are being compared (the hook's `time.time()` against a
filesystem mtime); the measured delta on a genuinely idle agent was **-0.1s**,
and a resume is a whole turn of writing.

After the fix, all three probes report `idle` correctly. Control 7 covers the new
path in three arms, including the resume guard — without that arm the other two
would pass equally well for code that ignored a resume entirely, which is the
false death this whole design refuses.

### What this says about the method

Both findings were invisible to inspection and cost one spawned agent each to
find. The docs page had no schema; the classifier's 9/9 score was real but every
one of those nine transcripts happened to end on a clean `end_turn`. A control
suite built only from fixtures the author imagined would have stayed green
through both defects.
