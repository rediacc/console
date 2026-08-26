# PLAN: stop-report output queue (one section per stop, priority + FIFO)
Status: done
Owner: queue-plan agent, branch 0731-2
Updated: 2026-07-31

## Status

Implemented in full; header flipped 2026-08-05 after verification (see git log b389ac305 / b685cd590). Everything below is the plan as written at design time and is superseded by this line.

HISTORICAL NOTE, 2026-08-26: the `wl_email` module cited throughout as the
one-shot exemplar has been REMOVED (the operator email channel is gone). The
queue design it motivated is unchanged, and case 176 now proves the same
one-shot property on request escalation. Do not go looking for `wl_email.py`.

Design complete, nothing implemented. Every line number below was read on
2026-07-31 against the working tree at `.claude/hooks/stop/`. The suite stands
at 382 cases green; this plan adds 5 case groups (173 to 177) and migrates 0
existing cases, with 4 named as at-risk and the reason each one survives.

Two asks are folded into one plan because they change the same 20 lines:

1. The allow report still emits every fired section at once. It becomes
   guide + judge line + AT MOST N queued sections (N default 1).
2. The judge approval line prints `reason[:120]` on every approval. It becomes
   a bare stamp, with the full reason only on a context-fresh or
   reason-changed stop.

## What exists today

The allow path builds `parts = [guide]` at `wl_checks.py:2398` and appends
every fired section unconditionally through `wl_checks.py:2498`, then emits one
joined message at `wl_checks.py:2503`. The sections, in their current append
order:

| Line | Section | Producer |
|---|---|---|
| 2404 | judge approval line | `wl_judge.run_judge` / `cached_stop_verdict` |
| 2413 | `audit_note` | judge `defer_audit`, banked at 2324 to 2331 |
| 2415 | `ci_report` | `wl_ci.ci_trouble`, 1739 to 1795 |
| 2417 | `queue_note` | `wl_ci.ci_queue_state`, 1714 to 1732 |
| 2419 | `email_note` | `wl_email.pump`, 1175 to 1179 |
| 2421 | `agent_note` | detached-HEAD note, 1830 to 1831 |
| 2423 | ladder pings | `wl_liveness.ladder`, 1442 to 1451 |
| 2440 | poll-backoff tip | `poll_backoff_tip`, wl_checks.py:113 |
| 2442 | other-session briefs | `S.brief_state`, 1300 |
| 2444 | archived items | `S.cleanup_dead_sessions`, 1134 to 1147 |
| 2449 | orphaned items | same call |
| 2469 | requests you posted | `wl_requests.classify_requests`, 1162 |
| 2474 | requests escalated | `wl_requests.escalate_requests`, 1152 to 1158 |
| 2479 | reggate settled | 2279 to 2292 |
| 2484 | reggate flood absorbed | 1234 to 1246 |
| 2488 | reggate marker corrupt | `wl_reggate.load_reggate`, 1208 |
| 2498 | other sessions have items | `classify_items`, 1189 |

The first diet landed today: `_report_latch` at `wl_checks.py:884` gates the
backoff tip (2438), other-session briefs (2441) and orphans (2448) on a
change-or-`REPORT_REFRESH_MIN` window, and the in-flight and deferred sections
were deleted as guide duplicates (comment at 2453). Case 172 at
`test-worklist-v5.sh:5447` pins that. Everything else still fires on every
stop, which is the residual the operator is complaining about.

## Finding, not asked for: the block path already loses three one-shots

This is a defect the queue fixes for free, and it decides the design, so it
goes first.

`run_stop` emits and exits at `wl_checks.py:2033` when any static check fires.
`C.emit` calls `sys.exit(0)` (`wl_core.py:159-161`), so nothing after that line
runs. Three sections are COMPUTED and their state COMMITTED before that emit,
and their text is only appended on the allow path:

- ladder pings: `wl_liveness.ladder` records fired rungs against the item's
  stamp (`wl_liveness.py:337-350`, "Once-per-rung"), and `wl_checks.py:1451`
  saves that state doc. If this stop then blocks, the rung is spent and its
  text is never emitted. It cannot re-fire until the item's stamp moves.
- archived items: `S.cleanup_dead_sessions` at `wl_checks.py:1141` flips the
  store to `[~]`. An archived item never re-reports.
- escalated requests: `wl_requests.escalate_requests` at `wl_checks.py:1154`
  appends the escalate event and the `- [?]` item exactly once
  (`wl_requests.py:110-138`).

`ci_report`, `queue_note` and `email_note` escape this only because someone
already noticed the shape and bolted them onto the block body as `extras`
(`wl_checks.py:2046-2050`). `audit_note` and `reg_settled` are computed after
the block emit, so they are never produced on a block and never lost.

**Consequence for this design: entries are enqueued at COMPUTE time, at the
producer call site, not at the emit site.** An entry that lands in the state
doc the moment its producer spends its budget survives a block stop, a judge
block, a crash, and a restart, and drains on the next allow stop. Enqueuing in
the `parts` block instead would preserve the existing bug and dress it up.

## Design

### D1. The queue lives in the per-session state doc

`S.load_state` / `S.save_state` (`wl_store.py:217-237`) already carry `focus`,
`report_seen`, `ladder`, `tasks_seen`, `defer_audit`, `judge_cache`,
`agent_boot_told`, `state_sig`. One new top-level key:

```json
"outq": {
  "seq": 41,
  "items": [
    {"key": "email:9f2a1c",
     "prio": 1,
     "sticky": true,
     "sig": "9f2a1c33b0d7",
     "text": "<the section body, verbatim>",
     "at": "2026-07-31T15:40:12Z",
     "seq": 37}
  ],
  "shown": {"others": {"sig": "ab12cd34ef56", "at": "2026-07-31T15:40:12Z"}}
}
```

`shown` is the old `report_seen` map under a new name, and it governs volatile
keys only. Migration: on first sight, if `outq` is absent and `report_seen` is
present, seed `shown` from it and leave `report_seen` in place unread. Without
this the upgrade stop re-shows every latched advisory at once, which is the
exact symptom being fixed. Do not delete `report_seen`; a sole-operator clean
break still should not make the first upgraded stop noisier than the last one.

### D2. Two functions, added to `wl_checks.py` beside `_report_latch`

`_report_latch` (`wl_checks.py:884-902`) is DELETED and its three call sites
(2438, 2441, 2448) become `outq_add` calls. Its semantics survive intact inside
`outq_add`; nothing about the change-or-window rule is being weakened.

Put both functions in `wl_checks.py`, not `wl_store.py`: the priority table is
report policy, `wl_checks` already mutates the state doc directly in four
places, and splitting the two halves across modules buys nothing here.

```python
OUTQ_PER_STOP = int(os.environ.get("WORKLIST_REPORT_PER_STOP", "1"))
OUTQ_MAX = int(os.environ.get("WORKLIST_OUTQ_MAX", "40"))


def outq_add(worklist, session_id, state_doc, key, text, prio,
             sticky=False, refresh_min=None, on_change=True):
    """Queue one allow-report section. Persists the state doc immediately.

    Returns True when an entry was added or refreshed, False when the call
    was absorbed (unchanged content inside its refresh window, or already
    queued). The return value is for the suite and for callers that want to
    skip building an expensive body; nothing in run_stop needs it.
    """
```

`outq_add` PERSISTS on every call. That is deliberate and it is the whole
safety argument: six of the emit paths in `run_stop` (2249, 2269, 2295, 2312,
2352, 2372) do not save the state doc before emitting, so a "save at the end"
contract would silently lose whatever was enqueued after `wl_checks.py:1451`.
The cost is at most about ten `tempfile` plus `os.replace` writes on a path
that already runs `git` and `gh` subprocesses. Do not optimise this away.

Behaviour:

- `sig = hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:12]`
- **sticky (a one-shot)**: the entry key is `"%s:%s" % (key, sig)`, so two
  different one-shot bodies under the same section name never collide and
  never overwrite each other. If that exact entry key is already queued, no-op
  (idempotent under a retried stop). There is deliberately NO shown-ledger for
  sticky keys: a one-shot producer does not re-fire by construction, and a
  ledger that could suppress one is a way to lose it. Showing a one-shot twice
  is cosmetic; dropping one is the failure this whole section exists to
  prevent.
- **volatile**: the entry key is `key`. If an entry with that key is queued:
  same `sig` means no-op and it keeps its FIFO position; a different `sig`
  means replace `text` and `sig` and re-stamp `seq` to the new sequence number,
  which moves it to the back of its priority class (the operator's "changed
  content re-enqueues at its priority"). If no entry is queued, consult
  `shown[key]`: skip when `on_change` and the sig matches and
  `C.stamp_age_min(shown[key]["at"]) < (refresh_min or REPORT_REFRESH_MIN)`,
  otherwise append.
- **`on_change=False`** (the backoff tip only, whose wording carries a live
  minute counter so a content hash re-fires every stop): identity is the KEY
  alone. Already queued means update the text in place WITHOUT moving `seq`, so
  the freshest wording rides the position it already earned. Not queued means
  enqueue only when `shown[key]` is older than `refresh_min`.
- **Cap**: after appending, if `len(items) > OUTQ_MAX`, drop non-sticky
  entries, lowest priority first then oldest first, until the cap holds. Never
  drop a sticky entry, even if stickies alone exceed the cap.

```python
def outq_drain(worklist, session_id, state_doc, n):
    """(texts, remaining). The n highest-priority entries, FIFO inside a
    priority class. Removes them, records shown[] for the volatile ones, and
    persists before returning, because the caller emits and exits."""
```

- sort by `(prio, seq)`, take the first `n`
- for each drained volatile entry set `shown[key] = {"sig": sig, "at": now}`;
  sticky entries record nothing (see above)
- delete exactly the drained entries from `items`, by identity, never by
  slicing or clearing
- persist, return `(texts, len(items))`

### D3. Priority ladder

Three classes. More would be a taxonomy nobody can apply consistently at a new
call site.

**0, actionable this session.** It changes what the session should do in the
next few minutes.

- `ci_report` (CI on your PR is red, downgraded or retry-pending)
- `queue_note` (the CI queue is saturated, do not push)
- ladder pings (a worker of yours has gone quiet; verify it)

**1, operator-relevant or a spend that must be visible.** Nothing to do right
now, but it records money spent, a mutation performed, or a question that left
the building. Every sticky one-shot except the ladder ping sits here.

- `email_note` (a digest went to the operator, or the channel is broken)
- `audit_note` (a paid judge interrogation happened and banked verdicts)
- escalated requests (a request became an operator-visible `[?]`)
- archived items (the store was mutated on this session's behalf)
- reggate settled, reggate flood absorbed, reggate marker corrupt

**2, informational.** True, worth saying eventually, worth saying never in the
same breath as class 0.

- other-session briefs
- orphaned items
- poll-backoff tip
- requests you posted (explicitly "they block their recipients, never you",
  `wl_checks.py:2470`)
- `agent_note` (the detached-HEAD blindness note)
- other sessions have items and you have none

Ladder pings sit at 0 rather than 1 despite being sticky, because the text is a
direct instruction ("verify each worker is really progressing", and it becomes
a block at 90 minutes per `worklist_messages.py:538-544`). Being sticky is
about never losing it; being class 0 is about when it lands.

### D4. Sticky inventory, verified against each producer

Sticky means the producer spends a budget or mutates state at COMPUTE time, so
the text cannot be regenerated by re-running the stop. Each one below was
confirmed by reading the producer, not by inference.

| Section | Sticky | Evidence |
|---|---|---|
| `email_note` | yes | `wl_email.pump` appends the ledger under flock and SENDS; the unconfigured and failed warnings latch on marker files (`wl_email.py:446-512`) |
| ladder pings | yes | fired rungs recorded against the item's stamp in `state_doc["ladder"]` (`wl_liveness.py:337-350`), saved at `wl_checks.py:1451` |
| `audit_note` | yes | verdicts banked into `state_doc["defer_audit"]` and saved at `wl_checks.py:2331` BEFORE the note is built at 2333; the banked check at 2141-2147 skips those items forever |
| reggate settled | yes | fixset persisted at `wl_checks.py:2281-2291`, absorbed at 1249-1256 on every later stop |
| reggate flood | yes | `seen_ticks` absorbed and saved at `wl_checks.py:1239-1242` |
| reggate corrupt | yes | `load_reggate` discards the marker; the flag is true only on the discovering pass (`wl_checks.py:1208`) |
| archived items | yes | `S.cleanup_dead_sessions` flips state to `[~]` (`wl_checks.py:1141`) |
| escalated requests | yes | `escalate_requests` appends the event plus the `[?]` exactly once (`wl_requests.py:110-138`) |
| `ci_report` | no | recomputed from `wl_ci.ci_trouble` each stop; the `soft` and `downgraded` returns (`wl_ci.py:607`, `wl_ci.py:620`) write no marker |
| `queue_note` | no | recomputed from `wl_ci.ci_queue_state` each stop |
| `agent_note` | no | recomputed from the branch state each stop |
| other-session briefs | no | recomputed from `.sessions` |
| orphaned items | no | recomputed until auto-archive |
| requests you posted | no | recomputed from the request log |
| backoff tip | no | recomputed, and its wording changes every stop |
| other sessions have items | no | recomputed from `classify_items` |

### D5. Call sites, exactly

Each producer gains one `outq_add` immediately after the value is computed.
The `parts` block at 2412 to 2498 is DELETED and replaced by a drain.

| Where | Call |
|---|---|
| after 1147 | `if archived: outq_add(..., "archived", <2444 body>, 1, sticky=True)` |
| after 1158 | `if req_escalated: outq_add(..., "req-escalated", <2474 body>, 1, sticky=True)` |
| after 1179 | `if email_note: outq_add(..., "email", email_note, 1, sticky=True)` |
| after 1246 | `if reg_flood: outq_add(..., "reg-flood", <2484 body>, 1, sticky=True)` |
| after 1208 block | `if reg_forgot: outq_add(..., "reg-forgot", <2488 body>, 1, sticky=True)` |
| after 1451 | `if ladder_pings: outq_add(..., "ladder", M.N_LADDER_PING % (...), 0, sticky=True)` |
| after 1732 | `if queue_note: outq_add(..., "ci-queue", queue_note, 0)` |
| after 1795 | `if ci_report: outq_add(..., "ci-report", ci_report, 0)` |
| after 1831 | `if agent_note: outq_add(..., "agent-blind", agent_note, 2)` |
| after 2292 | `if reg_settled: outq_add(..., "reg-settled", <2479 body>, 1, sticky=True)` |
| after 2338 | `if audit_note: outq_add(..., "audit", audit_note, 1, sticky=True)` |

The four remaining sections have no earlier producer and are enqueued where the
allow path already computes them, just before the drain: the backoff tip
(`outq_add(..., "backoff", tip, 2, refresh_min=BACKOFF_NOTE_MIN,
on_change=False)`), other-session briefs (`"others"`, 2), orphans
(`"orphans"`, 2), requests you posted (`"req-open"`, 2), other sessions have
items (`"others-items"`, 2). Reuse the existing keys `backoff`, `others` and
`orphans` verbatim so the `report_seen` migration in D1 matches them.

`ci_report`, `queue_note` and `email_note` KEEP their `extras` append at
`wl_checks.py:2046-2050`. They are enqueued as well; a volatile entry shown on
a block ride still drains later, which is a duplicate, not a loss. Fix the
duplicate by having the block path drain nothing and clear nothing: leave
`extras` exactly as it is. Do not try to teach the block path about the queue.

### D6. The new allow tail

Replacing `wl_checks.py:2398-2503`:

```python
parts = [guide]
if judged_ok:
    parts.append(judge_line)          # see D7; never queued
texts, remaining = outq_drain(worklist, session_id, state_doc, OUTQ_PER_STOP)
parts.extend(texts)
if remaining:
    parts.append(M.N_OUTQ_MORE % remaining)
S.save_state(worklist, session_id, state_doc)
C.emit({"systemMessage": "\n\n".join(parts)})
```

The `if parts:` guard at 2499 goes away; `parts` always holds the guide, so it
was never false. Keep the `S.save_state` even though `outq_drain` persists:
the pop in D7 and any late `focus` mutation ride on it, and one redundant
atomic write is cheaper than reasoning about which mutation happened last.

**The `+N more queued` tail is mandatory**, for the reason spelled out at
`wl_checks.py:989` for the guide's own truncation: a silent cap reads as "that
is everything". A session that can see three sections are waiting can raise
`WORKLIST_REPORT_PER_STOP` for one turn if it wants them now.

Invariants this preserves, all of which must be asserted somewhere in the
suite: the guide leads; the poll fast path (`wl_checks.py:1122-1129`) exits
before `load_state` and so never touches the queue; `emit` exits the process,
so the drain persists before it returns.

### D7. The judge line

Not a queue entry. It is one line, its whole purpose is that a paid model call
is never invisible (`wl_checks.py:2400-2403`), and the operator requires a
post-compact session to get the full statement unconditionally. Queuing it
would make both properties probabilistic. It rides the header, right after the
guide, exactly where it sits today.

What changes is the verbosity:

```python
fresh = state_doc.pop("ctx_fresh", None)          # exactly once, by popping
rsn = (verdict or {}).get("reason", "")
rsig = hashlib.sha1(rsn.encode("utf-8", "replace")).hexdigest()[:12]
stamp = "approved (cached)" if judge_cached else "approved"
if fresh or (not judge_cached and rsig != state_doc.get("judge_reason_sig")):
    parts.append(M.N_JUDGE_STAMP_FULL % (wl_judge.JUDGE_MODEL, stamp, rsn[:400]))
    state_doc["judge_reason_sig"] = rsig
else:
    parts.append(M.N_JUDGE_STAMP % (wl_judge.JUDGE_MODEL, stamp))
```

- The pop happens only inside the `if judged_ok:` branch, so a blocked stop
  cannot consume the marker, and a session with `WORKLIST_JUDGE=off` holds it
  until its first judged stop. Both are correct.
- `judge_reason_sig` is set only when the full reason is shown, so the next
  genuinely different reason still fires.
- A cached verdict replays the banked reason (`wl_judge.py:205-219`), so
  excluding cached from the signature arm is belt and braces rather than load
  bearing. Keep it: it matches the operator's wording and makes the rule
  readable.
- `bank_stop_verdict` already truncates at `[:200]` (`wl_judge.py:227`), so
  `[:400]` is a ceiling that only bites on a fresh uncached verdict. It is
  there so "full" stays bounded.

**Setting the marker.** Add to `wl_checks.py`:

```python
def mark_context_fresh(event, why):
    """Record that this session's context was just (re)built, so the next
    judged stop states the full approval reason instead of the stamp. Never
    raises: a context marker must not be able to wedge a SessionStart."""
    try:
        wl = C.worklist_for(
            os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd()
        )
        sid = event.get("session_id", "")
        doc = S.load_state(wl, sid)
        doc["ctx_fresh"] = {"why": why, "at": C.stamp_now()}
        S.save_state(wl, sid, doc)
    except Exception:  # noqa: BLE001
        pass
```

Call it as the FIRST statement of `handle_session_start`
(`wl_checks.py:995`) and of `handle_post_compact` (`wl_checks.py:1045`).
First, not last: `handle_session_start` returns early at 1032-1033 when there
are no design docs and no plans, and a project in that shape would otherwise
never be marked.

Known and accepted gap: `S.state_path` keys on `(session_id or "unknown")[:8]`
(`wl_store.py:127-128`), so a SessionStart event without a `session_id` writes
a marker the stop path never reads. The failure direction is the quiet one (the
stamp instead of the reason), and the signature latch still fires the full
reason on a fresh session because a fresh state doc has no
`judge_reason_sig`. The marker is genuinely load bearing only for
**post-compact**, which keeps its state doc and would otherwise see an
unchanged signature. That is the case the operator called out, and
`handle_post_compact` reads `event.get("session_id", "")` at
`wl_checks.py:1055`, so it is covered.

### D8. Do not merge this with the block-path focus rotation

The v13 focus block (`wl_checks.py:2071-2112`) stays exactly as it is. It is
LRU over check KEYS among violations that are ALL outstanding right now, and
every rotating one is recomputed from artifacts on the next stop, which is why
rotating them loses nothing. The queue is the opposite: FIFO with priority over
entries that PERSIST because their producers cannot regenerate them.

The recommendation is that they stay separate permanently, not just for now. A
block must state a reason that is true at the moment it blocks; a queued entry
is by construction aged, and an aged entry may describe a violation the session
has since fixed. Absorbing the focus rotation into the queue would let a gate
block on stale evidence, which is worse than the duplication it would remove.

### D9. Message constants

Add three to `worklist_messages.py`, and add all three to the `ARITY` dict in
case 117 (`test-worklist-v5.sh:2276`), which exists to catch exactly the
placeholder drift these introduce:

```python
N_JUDGE_STAMP = "Stop-gate judge (%s) %s."
N_JUDGE_STAMP_FULL = "Stop-gate judge (%s) %s: %s"
N_OUTQ_MORE = (
    "(%d more report section(s) queued; one is released per stop, highest "
    "priority first, oldest first inside a priority. Raise "
    "WORKLIST_REPORT_PER_STOP to drain faster.)"
)
```

ARITY entries: `"N_JUDGE_STAMP": ("m", "approved")`,
`"N_JUDGE_STAMP_FULL": ("m", "approved", "why")`, `"N_OUTQ_MORE": (3,)`.

The eight inline section bodies at 2444, 2449, 2469, 2474, 2479, 2484, 2488 and
2498 stay inline as f-string-free `%` expressions. Moving them into the
catalogue is a bigger diff with no gate behind it; leave them where they are.

## Suite work

Every behaviour gets a FIRE case and a CONTROL case that differs by one planted
fact, per the file's own standing discipline. New groups run after 172, at the
end of `test-worklist-v5.sh`. Record the case count before and after.

### 173. one section per stop, the rest queue

FIRE: a fixture where three class-2 volatile sections fire together (a fresh
other-session brief, an orphaned item, and a poll-backoff tip). Assert the
guide is present, EXACTLY ONE of the three section headers is present (count
the matches, do not test them one at a time), and `N_OUTQ_MORE` reports 2.

CONTROL: same fixture with `WORKLIST_REPORT_PER_STOP=3`. All three headers
present, `N_OUTQ_MORE` absent.

### 174. FIFO inside a priority class

Enqueue three class-2 sections in a known order across three stops, then drain
over three stops with N=1 and assert the emission order matches the enqueue
order. The cleanest fixture is the same three as 173, introduced one stop at a
time so their `seq` values are unambiguous.

CONTROL: touch the middle section's content on the second stop so it
re-enqueues, and assert it now comes out LAST. That is the operator's
"changed content re-enqueues at its priority", proven rather than asserted.

### 175. priority beats FIFO, with a planted defect

FIRE: enqueue a class-2 section (other-session brief) on stop 1 and let it sit
by setting N=0 for that stop, or simply enqueue it and then arrange for stop 2
to also produce a class-0 section (the `ci_report` downgraded note, which case
124 at `test-worklist-v5.sh:2630` already knows how to produce). On stop 2 with
N=1, assert the CI note is emitted and the older brief is not.

CONTROL: with the CI run green, the brief drains on the next stop.

PLANTED DEFECT, mandatory, and record the exact failure text in the case
comment: temporarily change `outq_drain`'s sort key from `(prio, seq)` to
`(seq,)`, run the suite, confirm 175 FAILS and 173 and 174 still pass, then
revert. A priority ladder nobody has watched invert is a ladder nobody knows is
wired up.

### 176. a one-shot is never dropped, with a planted defect

This is the property that matters most, so the fixture is built so the one-shot
LOSES its first stop.

FIRE, three stops:

1. Arrange a class-0 `ci_report` (downgraded, per case 124's fixture) AND an
   `email_note` at the same time. Use `WORKLIST_EMAIL_TRANSPORT=file:<dir>`
   (documented at `wl_email.py:49-55`) so nothing touches the network. With
   N=1 the CI note wins; assert the email note is ABSENT from stop 1.
2. Turn the CI run green so no class-0 section is produced. Assert the email
   note APPEARS on stop 2. The proof is that `wl_email.pump` sends nothing on
   stop 2 (its ledger already holds the send, `wl_email.py:479-481`), so the
   text can only have come from the queue.
3. Assert `N_OUTQ_MORE` is absent on stop 3, so the queue actually emptied.

CONTROL: the same fixture with no CI trouble at all. The email note appears on
stop 1, which proves stop 2 in the FIRE leg was a delay and not the normal
path.

PLANTED DEFECT, mandatory: in `outq_drain`, replace the per-entry removal with
`items[:] = []` (a plausible "reset the queue after draining" bug). Confirm 176
FAILS at leg 2 with the email note never arriving, and that 173 still PASSES,
which is the point: a cheap drop bug is invisible to the headline case and only
this one catches it. Revert.

### 177. judge verbosity

Needs a judge that approves, which the suite does not have today: every
judge-on case runs with `PATH="$BASE/binonly"` and no `claude`, so
`run_judge` fails closed (case 11 at `test-worklist-v5.sh:331`). Add a shim at
`$BASE/binonly/claude` that ignores its arguments and prints

```json
{"structured_output":{"verdict":"stop","reason":"<fixture reason>","next_action":""}}
```

on stdout, exit 0. That satisfies `run_judge`'s parse at `wl_judge.py:277-288`.
Pin `WORKLIST_JUDGE_CACHE_MIN=0` so every stop pays a fresh call and
`judge_cached` is False throughout, which is what makes the signature latch the
thing under test rather than the cache.

Three legs:

1. FIRE: `python3 "$HOOK" --session-start` with a fixture event, then a judged
   allow stop. Assert the fixture reason text is present.
2. CONTROL: another judged allow stop with the SAME reason. Assert
   `Stop-gate judge` is present and the reason text is ABSENT. This is the
   whole ask: the stamp alone on an ordinary stop.
3. FIRE again: `python3 "$HOOK" --post-compact`, then a judged allow stop.
   Assert the reason text is back, even though `judge_reason_sig` still holds
   its signature. This is the post-compact requirement, and leg 2 is what makes
   it meaningful.

Add a fourth assertion in the same group: change the shim's reason and run a
stop with no marker at all; the new reason must appear (the signature arm),
and a repeat of it must not.

## Migration: existing cases that touch allow-report sections

Grepping the suite for every section string turns up exactly four sites, and
all four survive. State this in the implementation report with the observed
pass counts, do not take it on faith from this plan.

- `test-worklist-v5.sh:5470,5482,5497` (case 172, other-session briefs). Its
  fixture produces one advisory and no class-0 or class-1 section, so with N=1
  the brief is the single drained entry and all three assertions hold
  unchanged. If the queue starts holding a stray sticky entry from an earlier
  case, this is the first case to break; it is `setup`-isolated, so it should
  not.
- `test-worklist-v5.sh:2916,2931` (case 137, ladder pings). The ping is class 0
  and its fixture produces nothing else, so it drains on the same stop. The
  CONTROL at 2931 asserts ABSENCE, which the queue cannot break.
- `test-worklist-v5.sh:2636` (case 124, `retry allowlist`). `ci_run` drives a
  stop that ALLOWS with `ci_report` as the only section, and `ci_report` is
  class 0. Drains immediately.
- `test-worklist-v5.sh:4202,4221` (cases 157 and 157c, the queue-saturation
  note). Same shape: `queue_note` is class 0 and nothing competes.
- `test-worklist-v5.sh:4211,4244` and `157b`, `157d` assert ABSENCE. Unaffected
  by definition.
- Cases 111 (`test-worklist-v5.sh:2123`) and 114 (2218) assert on
  `"operator may answer"`, which is a GUIDED SLICE line from
  `guided_slice` (`wl_checks.py:976`), not a report section. The guide leads
  every allow report, so these are untouched. They are listed here because they
  look like allow-report assertions and are not.

Nothing in the suite asserts on two report sections in one output, which is why
the migration set is empty. That is also the reason the operator is only now
complaining: the multi-section shape was never tested.

## Implementation order

1. `outq_add` and `outq_drain` in `wl_checks.py`, `_report_latch` deleted, the
   `report_seen` seed in place. No call sites yet.
2. Enqueue call sites (D5), `parts` block replaced by the drain (D6).
3. Judge line and `mark_context_fresh` (D7), constants (D9), case 117 ARITY.
4. Cases 173 to 177, each written to FAIL first against the unmodified
   behaviour where that is possible, then pass.
5. Both planted-defect proofs, reverted, with the observed failure text
   recorded in the case comments.
6. `shfmt -i 4 -ci -d .claude/hooks/stop/test-worklist-v5.sh` clean, whole
   suite green, before-and-after case counts reported.

## Explicitly out of scope

- Any change to the poll fast path (`wl_checks.py:1122-1129`).
- Any change to the block-path focus rotation (D8).
- Moving the eight inline section bodies into the message catalogue.
- Removing `report_seen` from existing state docs.
