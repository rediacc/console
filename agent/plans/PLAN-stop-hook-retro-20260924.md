# PLAN: Stop-hook retro, 2026-09-24 (first retro, lead session d778be9d)

Status: ready
Depends-On: no-dep -- related, not ordered: PLAN-stop-hook-continuity.md is cited for what it already landed and for the P3.1 retro procedure
First-Seen: 2026-09-24
Owner: d778be9d (adopted from retro a2799d9c9d4c45615 2026-09-24)
Updated: 2026-09-24

**Scope.** This retro covers the friction the Stop hook caused lead session d778be9d on 2026-09-24, from 03:50Z to 15:26Z. That window holds 118 blocked stops, 18 judge calls (10 `continue`, 8 `stop`) and 94 `--tick` calls. Where it helps to show a trend, counts across the whole 9-day transcript (2026-09-15 to 09-24) are given too. It also designs worklist #6e834f1a, the retro that runs at the moment before compaction.

**Line numbers.** They refer to the working tree at about 15:30Z on 2026-09-24. The continuity work is still uncommitted, so every citation also names a function or constant to re-anchor on.

**Not re-proposed.** PLAN-stop-hook-continuity.md already landed P0.1 to P2.7 (all except P2.6). Several of today's blocks predate those boxes and are already fixed:
- STATE.md staleness: 14 blocks, fixed by P1.2.
- `brief`: 5 blocks, fixed by P1.1.
- WORKER STATUS DUE: 12 blocks, fixed by P1.4.
- Substantive unread reports: 22 blocks, fixed by P1.5.
- Hook crash: 4 blocks at 11:11 to 11:12Z, fixed by P2.5 LKG.

Only the friction that survives the current code is below.

## Ranking by cost to the session

| Rank | Point | Today | All 9 days | Turns lost today | Fixed by today's continuity work? |
|---|---|---|---|---|---|
| 1 | #1: the judge demands a sweep or proof for work that has not landed, or is not the lead's | 6 of the 10 judge blocks (12:24, 12:26, 14:07, 14:57, 15:04, 15:06). All 10 carried a sweep or proof demand. | 144 of 177 judge blocks carried a sweep or proof demand | about 6, each with investigation tool calls and a writer message | No |
| 2 | #3: a `no-remaining` block on a short progress reply | 6. The replies were 255 to 1,473 characters. | 45 | 6 full restatements | No. P1.2 re-keyed STATE.md only. |
| 3 | #2: queue leases reported as "a slot is free now: start it", plus a stale cap estimate | 6 blocks carried queue lines (5 as the headline). 1 of 5 spawn refusals counted a finished writer. | 10 | 6, plus 1 slot the lead was holding and was forced to fill (13:34) | No. The `live_estimate` waiter fix covers the opposite direction. |
| 4 | #4: interim [SILENT] `waiting on my background task` reports | 3 (15:02, 15:14, 15:17) | 5 blocks with only [SILENT] reports, 4 of them interim waits | 3 | No. P1.5 excludes [SILENT] reports on purpose. |
| 5 | #7: the judge's next-action grep does not match the real change | 3 of the 10 (09:45 DROPPED; 14:07 and 14:57 on `post-tool`) | 7 DROPPED | overlaps #1 | No |
| 6 | #5: `--tick` evidence refusals | 22 refused calls (24 ids) out of 94 tick calls | not measured | 0 stops, about 22 retry tool calls | No |
| 7 | #6: liveness-ladder advisories starve the digest | 9 of the 9 digests since 13:59 were 6 identical `ladder` lines. 0 of 52 one-line advisories delivered. The queue grew from 40 to 87. | not measured | 0 turns, but total information loss | P0.2 built the outlet, and ladder entries block it |

---

## 1. The judge's class sweep and proof obligation fire on work that has not landed, or is not the lead's

**Frequency.** 6 of today's 10 judge blocks:
- 12:24 and 12:26: the temp-dir writer's 175 files, uncommitted and in flight. At 12:26 the lead said "still in progress and uncommitted".
- 14:07 and 14:57: the "hook timeout values" class. At 14:07 the lead said `I made no such change`. The 135 to 75 edit sat in the shared tree, and the babysitter committed it later.
- 15:04 and 15:06: the 47-alias conversion, which writer a023840 still had in flight. This is hint-proposal (a).

**Root cause.**
- `wl_reggate.fixset_files`, `.claude/hooks/stop/wl_reggate.py:316-332`. A tick-based fix-set has no commit, so it falls back to `git status --porcelain` of the whole shared worktree (`:329-331`), and that includes every live writer's uncommitted edits.
- `wl_judge.run_judge`, `.claude/hooks/stop/wl_judge.py:751-760`, injects that list as FIXSET_GROUND_TRUTH. The model then reads the lead's message, which describes the writer's dispatch, together with the writer's files, and infers a "landed bulk transform".
- `wl_reggate.fix_signals`, `:376-388`, also takes every `fix(` commit in marker..HEAD. On a branch where the babysitter commits everyone's work, that has no author scope.
- Misfires compound. A fired demand is carried forward as STILL OWED (`wl_classsweep.enforce`, `:389-393`), and a FOLLOWUP only accepts evidence in the last message (`prompt_section`, `:216-228`; `message[-6000:]` at `wl_judge.py`, JUDGE_PROMPT). At 14:57 the lead re-ran a sweep it had already run two turns earlier: `I ran it two turns ago, but the evidence has to be here`.

**Already fixed?** No. Today's diff to `wl_classsweep`, `wl_proofcheck` and `wl_reggate` only factors out `_clean` and `run_quiet`.

**Change.**
- (a) Add `wl_roster.live_writer_paths(cwd, sid, event)`: the `file_path` of every Edit, Write or MultiEdit tool_use in the transcripts of writers that are live now. `scan_transcript` already walks these transcripts.
- (b) In `fixset_files`, subtract those paths on the status-fallback arm, under provenance `"status-minus-live-writers"`. When nothing is left, `run_judge` omits `sweep_extra` and `proof_extra`. The obligation belongs in the writer's tick, as hint-proposal (a) says.
- (c) Discharge an outstanding demand when the lead transcript, after the demand's `at`, holds a Bash tool_use whose command contains the demand's search pattern and has a tool_result.

**Test.** New file `.claude/rediacc_hooks/tests/test_wl_judge_fixset_scope.py`.
- The fixture: a fixture repo, a tick owned by the lead that touches code, and `packages/x/a.ts` modified in the tree. A live writer's transcript (meta plus jsonl, last record an in-flight tool_use) holds an Edit of `packages/x/a.ts`.
- The control: the assembled judge prompt (a stub `claude` captures argv) contains `PROOF_MARKER` before the change and does not after it.
- The inverse: the same edit by a proven-finished writer is still in the fix-set.
- For (c): an outstanding demand `grep -r 'post-tool' ...` plus a later transcript Bash call `grep -rn 'post-tool' ...`. `prompt_section(False, outstanding)` returns FOLLOWUP_PROMPT before the change and `""` after it.

## 2. `no-remaining` fires on short progress replies

**Frequency.** 6 today (04:06, 06:50, 09:52, 13:38, 15:00, 15:14) and 45 across the 9 days. Every one forced a full restatement, for example 15:14:07 followed by 15:14:21.

**Root cause.**
- The bank key is `st_sig` (`.claude/hooks/stop/wl_checks.py:2304-2305`, compared at `:3652-3662`).
- `st_sig` comes from `wl_store.state_world_sig` (`.claude/hooks/stop/wl_store.py:2563-2602`), which hashes the harness task statuses and `rev-parse HEAD` (`:2595-2600`).
- In a session with a babysitter committing and shells flipping, it moves nearly every turn.
- P1.2 introduced `items_sig` (`wl_store.state_items_sig`, `:2413`; used at `.claude/hooks/stop/wl_checks.py:2275`), but only for STATE.md. The comment at `:2274` keeps `st_sig` for report banking on purpose.

**Already fixed?** No.

**Change.** Bank and compare `last_report_sig` on `items_sig`, the owned items' structure (id, state, owner, basetext). A background-task flip or someone else's commit then no longer demands a restatement. An add, tick, deferral or state change still does.

**Test.** New file `.claude/rediacc_hooks/tests/test_wl_remaining_bank.py`.
- The control: bank a message with `## Remaining`, flip one harness task to completed, and add a commit. The next message has no Remaining. `no-remaining` fires before the change and does not fire after it.
- The inverse: tick an owned item, and it fires.

## 3. Queue leases shown as "a slot is free now: start it", and the stale cap estimate

**Frequency.**
- 6 blocks carried queue lines: 09:50, 09:53, 11:05, 13:34, 14:45 and 15:08. At 15:08:58 there were 15 lines, all of them "start it", while only 1 slot was free.
- At 13:34 the lead wrote: `I was holding the last slot for the babysitter's plan-evidence writer, but the stop hook requires a free slot to be used.`
- There were 5 spawn refusals today. The one at 15:08:28 listed `a9130421dc7d46527`. That writer's transcript ended at 15:06:19: its last record is idle and it has no armed shells. The lead wrote: "The cap check still counts the stop-hook writer, which has finished."

**Root cause.**
- `wl_roster.roster`, `.claude/hooks/stop/wl_roster.py:521-526`. When `len(writers) < WRITER_CAP`, **every** `worker:queue` item becomes `leased_dead`. There is no comparison against the number of free slots, and there is no way to reserve a slot.
- `defect_rows`, `:945`, renders those items under V_ROSTER_DEAD (`.claude/hooks/stop/worklist_messages.py:2429-2436`, key `roster-dead`). A queue is not a finished worker.
- The cap estimate. `live_estimate` (`:705`) trusts the previous Stop event (`lastevent`, `:716-725`).
- `shell_waiters` (`:342-365`) turns an agent into a live "waiter" whenever the event lists as running a shell whose `backgroundTaskId` appears in that agent's transcript. Unlike `transcript_waiting` (`:389-401`), it never checks `armed_shells`, meaning whether the agent's own transcript already received that shell's `<task-id>`.
- a9130421 launched `b97piyqux` and `by0qlir2f`. The event that could have confirmed this has since been overwritten, so this cause is the most likely one, not a proven one.

**Already fixed?** Partly, in the other direction only. Today's `transcript_waiting` change stops the estimate from under-counting an agent that is waiting on its shell. Nothing stops it over-counting a finished one.

**Change.**
- (a) Split the queue out of `roster-dead` into its own key, `queue-slot`. Name only the K oldest queued items, where K is the number of free slots: "K slot(s) free, N queued: start #a[, #b]". The rest stay covered.
- (b) Allow one slot reservation: a `worker:queue` lease text carrying `HOLD_FOR:#<id>`. The id must be an open or `[>]` item owned by the session, at most 1 is allowed, and it expires with the lease (at most 120 minutes). A reserved slot does not count as free.
- (c) In `shell_waiters`, require `sid in armed_shells(jsonl)`.
- (d) In `live_estimate`, drop any agent whose `<status>completed</status>` task-notification reached the lead transcript after the lastevent's mtime. Reuse the `wl_report.delivered_ids` scan without its non-empty `<result>` filter.

**Test.** New file `.claude/rediacc_hooks/tests/test_wl_queue_slots.py`.
- (a) 3 live writers and 12 queue items. Before the change there are 12 "start it" lines under `roster-dead`. After it there is 1 line under `queue-slot`.
- (b) A `HOLD_FOR:#open` lease gives no block. `HOLD_FOR:#closed` is refused at `--lease`.
- (c) The event lists shell S. The agent transcript holds S's launch, a later `<task-id>S</task-id>` and an idle last record. Before the change `live_writers_estimate` counts the agent. After it, it does not.
- (d) The agent is listed as running in lastevent, and the lead transcript has a later completed notification for it. It is excluded after the change.

## 4. Interim [SILENT] reports block the stop (hint-proposal b)

**Frequency.** 3 today, all interim waits:
- 15:02: "Waiting on the suite result."
- 15:14: "Waiting for the background test run (`b5qnfbl1g`...)"
- 15:17: `I'll wait for this notification now.`

Across the 9 days, 4 of the 5 blocks carrying only [SILENT] reports were interim waits. Since P1.5, these are the only unread-report blocks left.

**Root cause.**
- `wl_report.capture` marks the entry `silent` when `sends == 0` and the body is shorter than SILENT_FLOOR=200 (`.claude/hooks/stop/wl_report.py:538`, `:52`).
- `mark_delivered` never auto-reads a silent entry (`:369`), by design, because an empty `<result>` is a real signal (`:352`).
- Nothing tells "went idle saying nothing" apart from "ended its turn to wait on its own shell". `wl_roster.transcript_waiting` already computes the second fact.

**Already fixed?** No.

**Change.**
- At capture (`--subagent-stop`, `:976`), store `interim: <shell id>` when `transcript_waiting(agent jsonl)` is non-empty.
- `unread()` (`:277`) skips an interim entry while its agent is still waiting, and marks it read `via: superseded` once a later capture from the same agent exists.
- If the agent finishes without a later capture, the entry comes back as unread. It fails closed.

**Test.** New file `.claude/rediacc_hooks/tests/test_wl_interim_reports.py`.
- The control: capture `I'll wait for this notification now.` with a transcript whose last record is idle and holds an armed `backgroundTaskId`. `unread()` returns it before the change and is empty after it.
- The first inverse: append the `<task-id>` notification plus a final idle record, with no later capture. It is returned again.
- The second inverse: a later capture `-2` marks the interim entry superseded.

## 5. The judge's next-action greps do not match the real change

**Frequency.** 3 of today's 10:
- 09:45: "Command DROPPED: it names .ci/.claude/scripts".
- 14:07 and 14:57: `grep -r 'post-tool' ...` against a change that edited a timeout number.

The 15:04 and 15:06 greps matched a class whose change had not landed; that case is #1. Across the 9 days there were 7 DROPPED commands.

**Root cause.**
- `wl_classsweep.validate_search` (`:310`) checks only that the command is safe and parses, and that its paths exist.
- `enforce` (`:378-430`) deliberately grounds only `defect_class` against the fix-set (`:394-399`).
- A search that cannot find the fixed instance cannot find its siblings, and nothing checks that.

**Already fixed?** No.

**Change.**
- Add `search_hits_instance(search, root, ids)`. It extracts the pattern argument from `grep`, `rg` or `git grep` and applies it to the +/- lines of the fix-set's diff. It runs only when the provenance is `diff-tree`.
- On zero hits, the action becomes `V_ACTION_UNGROUNDED`: "the judge's search does not match the fix's own changed lines; name a search that finds the fixed instance, then count its siblings". The demand stays; only the command is replaced.

**Test.** Add to `test_wl_judge_fixset_scope.py`.
- The control: a fixture commit changes `"timeout": 135` to `75` in settings.json, and the payload search is `grep -r 'post-tool' .claude/settings.json`. Before the change the action is V_ACTION with that grep. After it, the action is V_ACTION_UNGROUNDED.
- The inverse: `grep -rn '"timeout"' .claude/settings.json` keeps V_ACTION.

## 6. `--tick` evidence refusals

**Frequency.** 22 refused calls, covering 24 ids, out of 94 tick calls. None became a blocked stop, so the cost is about 22 retry tool calls. The refused evidence falls into four groups:
- `rc=0` or `rc 0`: 4 (709a4f9d, 5e4fa041, 4b5f4fe2, 874a70d1).
- An operator `/ask` ruling quoted with its timestamp and nothing else: about 8 (0c8a6cff, b7f799c5, 4e845910, 28be556a, da8127bc, 6ed39ac5, and 2 in the 07:18 loop).
- A bare basename or a path without a line: about 8, for example e6588e10 with `.claude/rediacc_hooks/guards/block_host_toolchain_run.py:391`.
- Other: 4.

**Root cause.**
- `.claude/hooks/stop/worklist.py:946-947` calls `wl_checks.completion_evidence` (`.claude/hooks/stop/wl_checks.py:269-306`).
- `EXIT_RE` (`:264`) accepts only `exit`, `exit code` or `exit=`, so `rc=0` fails.
- `CITE_RE` resolution needs a path from the repo root.
- No shape accepts a verifiable operator answer.

**Already fixed?** No.

**Change.**
- `EXIT_RE` also accepts `\brc\s*[:= ]\s*\d+`.
- A bare `name.ext:N` resolves when exactly one tracked file (`git ls-files`) has that basename.
- A new shape `ASKED:<ISO minute>` passes only when the lead transcript holds an AskUserQuestion tool_result within 5 minutes of that time.
- Every refusal is appended to `.tick-refusals-<sid>.jsonl`, so the next retro can count them without grepping the transcript.

**Test.** New file `.claude/rediacc_hooks/tests/test_wl_tick_evidence_shapes.py`.
- `completion_evidence(root, "87 cases rc=0")` is False before the change and True after it.
- A unique basename citation passes. An ambiguous one still fails.
- `ASKED:2026-09-24T07:18Z` passes against a planted AskUserQuestion result and fails without one.
- The paired inverse: "done, works" still fails.

## 7. Liveness-ladder advisories starve the digest

**Frequency.** The queue held 83 entries at 15:17: 20 `ladder`, 31 `reg-settled`, 21 `claim-check`, 10 `reg-flood` and 1 `audit`. The oldest ladder entry dates from 2026-09-23 13:06Z. Every digest since P0.2 landed (9 of 9, 13:59 to 15:17) showed six identical `ladder: Liveness ping (45-minute rung...` lines. Not one of the 52 one-line advisories was delivered.

**Root cause.** Four things combine:
- `outq_add` keys a sticky entry as `key:sig` (`.claude/hooks/stop/wl_checks.py:1045`). The ladder producer (`:2424-2432`) enqueues each new ping set as a new sticky entry at priority 0.
- `_outq_cap` never drops a sticky entry (`:1019-1030`).
- `outq_digest` sorts by priority and takes the first 6 (`:1163-1168`). It delivers only single-line bodies (`:1170-1176`), and ladder bodies are always multi-line.
- No entry is retracted when its item moves.

The result is permanent head-of-line blocking.

**Already fixed?** No. P0.2 built the outlet, and this defect blocks it.

**Change.**
- Make `ladder` one non-sticky entry, keyed `ladder` and rebuilt every stop from the current `ladder_pings`. When no ping is live, it is removed. That keeps the "cannot regenerate" concern in `:2425` true, because the current pings are recomputed.
- In the digest, collapse same-key entries into one line: `ladder: N quiet in-flight subjects (#a, #b, ...)`.
- A one-time migration drops the existing `ladder:<sig>` entries.

**Test.** Add to `.claude/rediacc_hooks/tests/test_wl_advisories_rotation.py`.
- The control: 20 multi-line sticky ladder entries plus 30 one-line priority-2 entries. `outq_digest` returns 6 `ladder` lines and delivers 0 before the change. After it, it returns 1 `ladder` line and delivers at least 5.
- The retraction check: once the item moves, the `ladder` entry is gone on the next stop.

---

## 8. Worklist #6e834f1a: the retro before compaction

**Trigger.**
- In `band-notice.py`, when a band is crossed (`:230`), also set `st["retro_due"] = {band, at, usage}`. Do not order anything yet.
- The order is emitted on the first later PostToolUse where STATE.md's mtime moved after `retro_due.at`. That is the existing mtime tracking at `:221`, and it is what "AFTER the STATE.md write" means here.
- In `wl_checks.handle_post_compact` (`:1441`), append the order after the briefing, the facts and the plans. On the missing-STATE arm, it says `after you write STATE.md`.

**Once per session per band, never for a subagent.**
- The dedupe key is `(session8, band)`, with band in `{early, late, post-compact}`. The ledger is the source of truth, because the band state file is reset on every epoch (`band-notice.py`, usage-drop reset).
- The ledger is read only while an order is pending.
- The existing `agent_id` guard (`.claude/hooks/context/band-notice.py:170`) covers the band path. Add the same guard as the first line of `handle_post_compact`.
- A session therefore gets at most 3 retros. Each covers the transcript bytes since the previous row's `to_off`, so no two retros overlap.

**Exact notice text** (band path, a new constant `RETRO_ORDER` in ctx_budget.py):

```
Stop-hook retro due (standing procedure PLAN-stop-hook-continuity.md P3.1, operator order 2026-09-24; band %(band)s, session %(me8)s). STATE.md was rewritten at %(state_at)s, after this band was crossed, so the recovery document is safe; this session's stop-hook experience is still in context and on disk.
  1. Print the brief:  python3 .claude/hooks/stop/worklist.py --retro-brief %(me8)s %(band)s
  2. Dispatch ONE Agent with subagent_type Plan and run_in_background true, with that brief as its prompt. Plan agents are read-only and do not count toward the writer cap.
  3. Save what it returns verbatim to agent/plans/PLAN-stop-hook-retro-%(date)s.md (update the file if it exists).
The tracking item is created at your next stop and auto-leased to the agent from the #id in its brief. Ledger: agent/ledgers/stop-hook-retros.jsonl. Emitted once per session per band.
```

**PostCompact text** (a new constant `CTX_POSTCOMPACT_RETRO` in worklist_messages.py):

```
STOP-HOOK RETRO (standing procedure PLAN-stop-hook-continuity.md P3.1): compaction replaced this session's context, but its transcript is intact at %(transcript)s. After reading the briefing above, run `python3 .claude/hooks/stop/worklist.py --retro-brief %(me8)s post-compact` and dispatch it as ONE background Agent with subagent_type Plan; save what it returns to agent/plans/PLAN-stop-hook-retro-%(date)s.md. It covers transcript bytes %(from)d-%(to)d, everything since the last retro. Emitted once per session.
```

The band-notice docstring rule "It does not instruct" (`.claude/hooks/context/band-notice.py:7-12`) gets one documented exception, citing this operator order. The text is framed as a repo procedure, not as a system command.

**Ledger** (`agent/ledgers/stop-hook-retros.jsonl`). Rows are append-only, one line each, with O_APPEND and under 4 KB:
- `{"ev":"ordered","at","session","band","epoch","usage","threshold","transcript","from_off","to_off","state_md_at"}`, written by band-notice or by handle_post_compact.
- `{"ev":"tracked","item"}`, written by `--retro-brief` or by `wl_retro.sync` at the stop.
- `{"ev":"dispatched","agent"}`, written by `wl_retro.sync` when the P2.2 auto-lease links the item to the Plan agent.
- `{"ev":"saved","plan","tasks_open","tasks_total"}`, written by `wl_retro.sync` when the item is ticked.

**How the tasks are tracked.**
- A new module, `.claude/hooks/stop/wl_retro.py`, runs `sync` on every stop. For each `ordered` row with no `tracked` row, it adds an owned item: "(me8) stop-hook retro <band> <date>: dispatch the Plan agent (--retro-brief) and save agent/plans/PLAN-stop-hook-retro-<date>.md".
- The ordinary `open-items` check then enforces it, so no new block key is needed.
- The brief contains `#<item>`, which P2.2's auto-lease (`wl_leasehelp.auto_lease_candidates`, `:137`) turns into a lease on the Plan agent.
- The tick evidence `agent/plans/PLAN-stop-hook-retro-<date>.md`, line 1, resolves as a file:line citation.
- The brief requires the plan's header to read `Owner: <me8> (adopted from retro <agent-id> <date>)`. `wl_planfile.is_adopted` (`:342`, marker `(adopted from`) then fires `plan-adopted` (`.claude/hooks/stop/wl_checks.py:2861-2871`) until every `- [ ]` box is an item or a `[?]` deferral.
- Task ids use the form `R<date>.<n>`, so a later retro updates boxes instead of duplicating them.

**What the brief contains** (`worklist.py --retro-brief <me> <band>`):
- The transcript path and its byte range.
- Block counts per key from a new `.blocklog-<sid>.jsonl`, with one row per blocked stop: key, named keys and judge flags. This replaces grepping a 222 MB transcript.
- The hint-proposals rows since the previous retro.
- The judge log rows (`.judge-<sid>.jsonl`), the admissions log and the tick-refusal log.
- A do-not-re-propose list: every `PLAN-stop-hook-*` box and its state.
- The required output format: this document's format.

**Test.**
- Extend `.claude/hooks/context/test-context-bands.py`:
  - An early crossing with no STATE.md write gives no order and no row.
  - Touching STATE.md, then a tool call, gives an order containing `--retro-brief abcd1234 early` and 1 row.
  - The next tool call is silent.
  - An `agent_id` event is silent and writes no row.
  - An epoch reset followed by a second early crossing and a STATE.md write gives no order.
  - A late crossing plus a STATE.md write gives an order and a 2nd row.
  - Mutations: removing the `agent_id` guard, removing the dedupe, or ordering at the crossing must each fail one of the cases above.
- New file `.claude/rediacc_hooks/tests/test_wl_retro.py`:
  - `handle_post_compact` emits the order once. A second call does not. An `agent_id` event does not.
  - One `ordered` row leads to exactly one owned item across two stops.
  - `--retro-brief` prints `#<id>` and the previous row's `to_off`.
  - Ticking with the plan path appends a `saved` row with the task counts.
- Every one of these fails on the current tree, because the feature does not exist yet.

## Decisions (default applies unless the operator says otherwise)

- **Dedupe key.** DEFAULT: literal, `(session, band)`, with post-compact counted as a band. WHY: that is the order as written. HOW: switching to `(session, epoch, band)` is a one-line change in the ledger lookup. A 9-day lead with 26 compactions, like this one, would then get a retro per compaction.
- **Slot reservation `HOLD_FOR`.** DEFAULT: at most 1, expiring with its lease, and it must name a live owned item. WHY: the lead needs to hold a slot (13:34), and a bounded reservation cannot hide work. HOW: operator veto.

## Sequencing

- Writer A owns `.claude/hooks/stop/**` and does R.1 to R.7.
- Writer B does R.8. Its files are `.claude/hooks/context/**` plus `wl_retro.py`, `worklist.py --retro-brief` and `handle_post_compact`. B starts after a887086 ticks P2.6, because a887086 owns `.claude/hooks/context/**`. B's `wl_checks.py` and `worklist.py` edits wait for Writer A's tick.

## Tasks

- [x] **R20260924.1** The judge fix-set excludes live writers' edit paths (`wl_reggate.fixset_files`, `wl_roster.live_writer_paths`), and sweep/proof are not asked when nothing is left. Test: `test_wl_judge_fixset_scope.py`.
    (ticked) 2026-09-24T15:50:09Z by d778be9d: .claude/hooks/stop/wl_roster.py:709 live_writer_paths, .claude/hooks/stop/wl_reggate.py:325 fixset_files status-minus-live-writers (plus _porcelain_path :316, the stripped-first-line bug), .claude/hooks/stop/wl_judge.py:743; .claude/rediacc_hooks/tests/test_wl_judge_fixset_scope.py:134 fails on the pre-change copy, 9 passed after
- [x] **R20260924.2** An outstanding sweep or proof demand is discharged by lead transcript evidence of its search (`wl_classsweep.prompt_section` / `apply_verdict`). Test: `test_wl_judge_fixset_scope.py`.
    (ticked) 2026-09-24T15:50:21Z by d778be9d: .claude/hooks/stop/wl_classsweep.py:332 sweep_evidenced + :378 discharge_if_evidenced, wired at .claude/hooks/stop/wl_judge.py:748; wl_rules.Demand carries first_at; .claude/rediacc_hooks/tests/test_wl_judge_fixset_scope.py:230 and :273 fail on the pre-change copy and pass after, adversarial :282 passes both
- [x] **R20260924.3** `search_hits_instance` grounds the judge's search in the fix's own diff, with V_ACTION_UNGROUNDED on zero hits. Test: `test_wl_judge_fixset_scope.py`.
    (ticked) 2026-09-24T15:50:47Z by d778be9d: .claude/hooks/stop/wl_classsweep.py:263 search_hits_instance + V_ACTION_UNGROUNDED :544, enforce/apply_verdict take instance, run_judge fixset_instance from wl_checks for diff-tree only; .claude/rediacc_hooks/tests/test_wl_judge_fixset_scope.py:329 fails on the pre-change copy and passes after, inverse :338 passes both
- [x] **R20260924.4** `no-remaining` banks on `items_sig`, not `st_sig` (`.claude/hooks/stop/wl_checks.py:2304`, `:3656`). Test: `test_wl_remaining_bank.py`.
    (ticked) 2026-09-24T15:52:52Z by d778be9d: .claude/hooks/stop/wl_checks.py:2300 banks and compares report_sig from .claude/hooks/stop/wl_store.py:2563 report_items_sig; state_world_sig removed as dead; .claude/rediacc_hooks/tests/test_wl_remaining_bank.py:36 fails on the pre-change copy and passes after, inverse :47 passes both
- [x] **R20260924.5** Queue items get their own key, `queue-slot`, naming only the K oldest for K free slots, plus one `HOLD_FOR:#id` reservation (`.claude/hooks/stop/wl_roster.py:521-526`, `:945`). Test: `test_wl_queue_slots.py`.
    (ticked) 2026-09-24T15:56:04Z by d778be9d: .claude/hooks/stop/wl_roster.py:541 queue_start names the K oldest, HOLD_FOR :68/hold_valid :78, key queue-slot at .claude/hooks/stop/wl_checks.py:2533, --lease reservation at .claude/hooks/stop/worklist.py:1062; .claude/rediacc_hooks/tests/test_wl_queue_slots.py:54 and :89 fail on the pre-change copy and pass after
- [x] **R20260924.6** `shell_waiters` requires an armed shell, and `live_estimate` drops agents whose completion reached the lead transcript. Test: `test_wl_queue_slots.py`.
    (ticked) 2026-09-24T15:56:04Z by d778be9d: .claude/hooks/stop/wl_roster.py:375 shell_waiters requires armed_shells, :864 _completed_since via wl_report.delivered_ids(require_result=False); .claude/rediacc_hooks/tests/test_wl_queue_slots.py:167 and :216 fail on the pre-change copy and pass after, inverses :176 :223 pass both
- [x] **R20260924.7** Interim-wait captures are held while the agent waits, superseded by a later capture, and fail closed (`wl_report.capture`, `unread`). Test: `test_wl_interim_reports.py`.
    (ticked) 2026-09-24T15:57:36Z by d778be9d: .claude/hooks/stop/wl_report.py:638 records interim at --subagent-stop, :277 unread holds/supersedes it, :315 _still_waiting; .claude/rediacc_hooks/tests/test_wl_interim_reports.py:77 and the supersede case fail on the pre-change copy and pass after, fail-closed inverse and adversarial pass both
- [x] **R20260924.8** Tick evidence accepts `rc=N`, a unique basename:line and a verified `ASKED:<ts>`, and logs refusals (`wl_checks.EXIT_RE`, `completion_evidence`, `.claude/hooks/stop/worklist.py:946`). Test: `test_wl_tick_evidence_shapes.py`.
    (ticked) 2026-09-24T15:59:21Z by d778be9d: .claude/hooks/stop/wl_checks.py:267 EXIT_RE takes rc=N, :279 _bare_cite_resolves, :301 _asked_in_transcript, :343 completion_evidence(transcript); refusals logged by .claude/hooks/stop/worklist.py:861; .claude/rediacc_hooks/tests/test_wl_tick_evidence_shapes.py fails 4 on the pre-change copy, 6 passed after
- [x] **R20260924.9** `ladder` becomes one rebuilt, non-sticky entry, the digest collapses same-key entries, and old `ladder:<sig>` entries are migrated (`.claude/hooks/stop/wl_checks.py:1045`, `:1157-1183`, `:2424-2432`). Test: `test_wl_advisories_rotation.py`.
    (ticked) 2026-09-24T16:01:33Z by d778be9d: .claude/hooks/stop/wl_checks.py:2533 one rebuilt non-sticky ladder entry plus the legacy migration, :1235 _outq_group_line and :1249 outq_digest collapse; ping labels lead with #id; .claude/rediacc_hooks/tests/test_wl_advisories_rotation.py:659 and :696 fail on the pre-change copy and pass after
- [x] **R20260924.10** `.blocklog-<sid>.jsonl`: one row per blocked stop (key, named keys, judge flags), written at the block exit in `wl_checks.run_stop`. Test: `test_wl_retro.py`.
    (ticked) 2026-09-24T16:02:58Z by d778be9d: .claude/hooks/stop/wl_checks.py:1178 blocklog and judge_flags, called at every block exit of run_stop (battery focus-off, focused, judge unavailable, reggate, defer audit, judge continue, shapedup); .claude/rediacc_hooks/tests/test_wl_retro.py battery and judge cases fail on the pre-change copy and pass after, allow inverse passes both
- [x] **R20260924.11** Retro order on the band path, after the STATE.md write, with the `RETRO_ORDER` text and an `ordered` ledger row (`band-notice.py`, `ctx_budget.py`). Test: `test-context-bands.py`, including mutations.
    (ticked) 2026-09-24T16:47:48Z by d778be9d: .claude/hooks/context/band-notice.py:236 orders after the STATE.md write, ledger helpers and RETRO_ORDER at .claude/hooks/context/ctx_budget.py:424; .claude/hooks/context/test-context-bands.py:520 test_retro fails 5 checks on the HEAD copy, suite 101 checks 0 failures, three retro mutants each turn a retro check red
- [x] **R20260924.12** Retro order on the PostCompact path, with the `agent_id` guard (`wl_checks.handle_post_compact`, `worklist_messages.CTX_POSTCOMPACT_RETRO`). Test: `test_wl_retro.py`.
    (ticked) 2026-09-24T16:47:48Z by d778be9d: .claude/hooks/stop/wl_checks.py:1644 handle_post_compact orders the post-compact retro once, agent_id guarded, CTX_POSTCOMPACT_RETRO at .claude/hooks/stop/worklist_messages.py:1632; .claude/rediacc_hooks/tests/test_wl_retro.py:108 and :126 fail on the pre-change copy, :131 fails with the guard removed
- [x] **R20260924.13** `wl_retro.sync` writes the tracked, dispatched and saved rows and creates the tracking item. `worklist.py --retro-brief` prints the brief with `#id`, the byte range and the do-not-re-propose list. Test: `test_wl_retro.py`.
    (ticked) 2026-09-24T16:47:48Z by d778be9d: .claude/hooks/stop/wl_retro.py:101 sync writes tracked, dispatched and saved rows, called before run_stop at .claude/hooks/stop/worklist.py:2319, --retro-brief at .claude/hooks/stop/worklist.py:586; .claude/rediacc_hooks/tests/test_wl_retro.py:139 :167 :211 :234 fail on the pre-change copy and pass after
- [x] **R20260924.14** Add box P3.1 to PLAN-stop-hook-continuity.md, pointing at R.11 to R.13, and document the band-notice "does not instruct" exception in its docstring.
    (ticked) 2026-09-24T16:47:48Z by d778be9d: agent/plans/PLAN-stop-hook-continuity.md:376 box P3.1 points at R.11 to R.13; the exception is documented at .claude/hooks/context/band-notice.py:13
- [ ] **R20260924.15** After R.1 to R.13 land, re-count all seven frictions on the next session's `.blocklog` and record the before and after numbers in this plan's Status.

### Critical Files for Implementation
- /home/developer/console/.claude/hooks/stop/wl_reggate.py
- /home/developer/console/.claude/hooks/stop/wl_checks.py
- /home/developer/console/.claude/hooks/stop/wl_roster.py
- /home/developer/console/.claude/hooks/stop/wl_report.py
- /home/developer/console/.claude/hooks/context/band-notice.py

---

# Second retro (band early, 19:37Z; tracking #4f167b47, Plan agent ab3a6ddab93217bdc)

**Scope.** The brief reported every input as "(none)". That is wrong, and it is finding #1 below. The brief took its window from the previous `ordered` row in `agent/ledgers/stop-hook-retros.jsonl`: ledger row 1, `post-compact`, at 19:01:46Z, with `from_off 0` and `to_off 235805252`. (The lead addendum quotes `2358052`, which is a typo.) No retro ever covered the range behind that row. The first retro covered 03:50Z to 15:26Z. So this retro covers **15:26Z to 19:37:41Z**, read from the ledgers directly:
- 19 rows in `.blocklog-d778be9d.jsonl`, 16:10:30Z to 18:31:58Z.
- 2 hint proposals, at 18:32:22Z and 18:37:25Z.
- 15 judge rows, 15:46:07Z to 17:25:36Z: 10 `continue` and 5 `stop`.
- 6 rows in `.tick-refusals-d778be9d.jsonl`.
- 2 admission rows at 18:36Z.
- Lead transcript bytes 235805252 to 236722957 (19:01:54Z to 19:37:39Z). This range has 0 blocked stops and 0 judge calls, but it has the pre-bash guard blocks in #3.

Six blocks fell between 15:26Z and 16:02Z, before the blocklog existed (R.10). They are counted from the transcript at 223761681, 223884915, 224003640, 224492187, 225751082 and 225887797. Their keys (unread reports, a 32-line `roster-dead` queue, judge and announced-question) all predate R.5 and R.7, and they are not re-proposed.

**Line numbers** refer to the tree at 19:40Z on 2026-09-24 (HEAD after `d393a4e8c`).

## Ranking by cost to the session

| Rank | Point | Count in this window | Turns lost | Already fixed by? |
|---|---|---|---|---|
| 1 | #1: a sub-agent's PostCompact wrote the lead's `post-compact` retro row | 1 ledger row (row 1, 19:01:46Z). It hid 19 blocklog rows, 2 hints, 15 judge rows, 6 tick refusals and 2 admissions from this brief. | 0 so far. The retro inputs were wrong, and the lead's real post-compact retro is now suppressed for good. | No. R.12's `agent_id` guard assumed a payload shape nobody had measured. |
| 2 | #2: sweep and proof demands the lead had already answered are still carried | 7 of 9 judge blocks carried sweep or proof (blocklog rows 16:10:30, 16:13:17, 16:17:15, 16:23:57, 16:29:10, 16:57:32, 17:19:59). 7 of them carried a STILL OWED. | About 7 stops, plus 8 sweep Bash calls | R.1 to R.3 are live (ticked 15:50Z) but do not hold for `find`, near-literal reruns, truncated demands, proof, submodule files, or UNVERIFIED classes |
| 3 | #3: pre-bash guards judge the state an earlier clause of the same command is about to change | 3 blocks (19:01:33, 19:02:10, 19:28:10), 1 wasted `ci:quick` (3 min 33 s), 1 undercount (19:02:40) | 3, plus about 4 tool calls | No |
| 4 | #4: tick evidence refusals | 6 refusals (tick-refusals rows 1 to 6) | 0 stops, 6 retries | Partly. R.8 added `ASKED:`, but the refusal text never names it. Sibling repos are not covered. |
| 5 | #5: the submodule pointer check ignores a KEEP decision the lead recorded | 2 blocks on the same move (15:58:03, 16:15:36), plus 1 lag case (18:31:58) and hint row 18:32:22 | 2, plus 1 workaround (staging a gitlink to silence the check) | No |
| 6 | Judge blocks whose own reason says the wait is legitimate | 2 (17:23:56, 17:25:36) | 2 | **Yes**: `d393a4e8c` (`wl_roster.cap_saturated_wait`, `.claude/hooks/stop/wl_checks.py:2599`). Not re-proposed. |

These are working as designed and are not friction:
- `agent-state` 16:54:10 and 17:40:20: STATE.md was 36 and 49 minutes old and the world had moved.
- `roster-dead` 16:55:06, 18:04:44 and 18:15:47: workers that really had finished.
- `ladder-investigate` 17:13:10.
- `open-items` 17:22:19: an item added 21 s earlier.
- The 18:36:10Z admission: the judge cleared it as `none`.

**Data for R20260924.15 (not a new box).** From 16:10Z to 18:31Z, with R.1 to R.10 live:
- `no-remaining` led 0 blocks.
- Unread reports: 0 blocks.
- `queue-slot` led 0 blocks. It was named twice, at 16:55:06 and 18:31:58, instead of the old 15-line "start it".
- The ladder produced 0 blocks.
- Judge sweep or proof: 7 blocks. This is the one friction of the first seven that did not fall.

---

## 1. A sub-agent's PostCompact wrote the lead's `post-compact` retro row

**What happened.**
- The pr-babysitter `a149262d8b6a1601f` compacted at 19:01:44.440Z: `subagents/agent-a149262d8b6a1601f.jsonl` line 7512 is `"isSidechain":true,"agentId":"a149262d8b6a1601f","subtype":"compact_boundary"`.
- 1.6 s later, `stop-hook-retros.jsonl` got an `ordered` row with `session d778be9d`, `band post-compact`, `transcript` = the **lead's** path, and `to_off 235805252`. That number is exactly the lead transcript's size at that moment: the next lead record starts at byte 235805252, at 19:01:54Z.
- The lead did not compact. Its last `compact_boundary` is at byte 228480152, 16:25:21.620Z, with `isSidechain:false`.
- The lead never saw the order: no `STOP-HOOK RETRO (standing` text appears in bytes 235805252 to 236722957.
- Consequences, each measured or read from code:
  - **(a)** The brief for the `early` row (19:37:41Z) took `since = 19:01:46Z` (`.claude/hooks/stop/wl_retro.py:229`, `earlier[-1].at`). That printed "(none)" for all five logs.
  - **(b)** `retro_ordered` dedupes on `(session, band)` (`.claude/hooks/context/ctx_budget.py:472`). The lead's real compaction can therefore never order its own post-compact retro.
  - **(c)** The ledger has a `tracked` row only for `early` (item 4f167b47, 19:38:15Z). So `wl_retro.sync`'s loop over `ordered` rows (`wl_retro.py`, `sync`) will add a second, spurious owned item, "stop-hook retro post-compact", at the lead's next stop.
  - **(d)** `mark_context_fresh` (`.claude/hooks/stop/wl_checks.py:1582`) is the first statement of `handle_post_compact`. It stamped the **lead's** `ctx_fresh` for the babysitter's compaction.

**Root cause.**
- `wl_checks.handle_post_compact`, `.claude/hooks/stop/wl_checks.py:1647`: `if sid and not event.get("agent_id")`.
- The row's existence proves the babysitter's PostCompact payload carried the lead's `session_id` and `transcript_path` and **no** `agent_id`. That matches the TeammateIdle measurement recorded at `.claude/hooks/stop/worklist.py:1650`: no `agent_id`.
- R.12's control (`.claude/rediacc_hooks/tests/test_wl_retro.py:132-134`) plants `agent_id="agent_01xyz"`. It pins a payload shape that was assumed, never measured, so the test passes while the guard does nothing in practice.
- Secondary cause:
  - `retro_from_off` (`.claude/hooks/context/ctx_budget.py:480`) takes the window start from any previous `ordered` row, whether or not that retro was ever dispatched or saved.
  - `brief` does the same with `since` (`.claude/hooks/stop/wl_retro.py:229`).
  - As a result, one bad row swallows a range nobody reviewed.

**Fix.**
- (a) Add `ctx_budget.compaction_owner(transcript_path, sid, now)`. It reads the last 2 MB of the lead transcript; after the lead's 16:25 compaction, 276,732 bytes of records followed the boundary before `pr-link` (228480152 to 228756884).
  - It returns `"lead"` when the newest `compact_boundary` with `isSidechain:false` is within `COMPACT_ATTRIB_S=120` of now.
  - It returns `"agent:<id>"` when a `<dir>/<sid>/subagents/agent-*.jsonl` modified in the last 120 s holds such a boundary and the lead's does not.
  - Otherwise it returns `"unknown"`.
- `handle_post_compact` orders the retro and calls `mark_context_fresh` only on `"lead"`. The briefing itself is still emitted (see Decisions).
- (b) The retro window and `since` start at the newest previous row that reached `saved`, falling back to `dispatched`. They do not start at the newest `ordered` row.
- (c) Add a `voided` ledger event: `{"ev":"voided","session","band","why"}`. `retro_ordered`, `retro_from_off` and `sync` skip a voided pair, which frees its dedupe key. Append one migration row voiding `(d778be9d, post-compact)` with `why: "sub-agent a149262d8b6a1601f compaction 19:01:44Z"`.

**Test.** `test_wl_retro.py`.
- The control uses the measured shape: a PostCompact event with the lead's `session_id` and `transcript_path` and no `agent_id`. The boundary is planted only in `subagents/agent-X.jsonl`.
  - Before the change: 1 row and the order text.
  - After: 0 rows, no order, and `ctx_fresh` untouched.
- The inverse: the boundary in the lead transcript gives 1 row and the order.
- The mutant: reverting to the `agent_id`-only guard makes the control write a row.
- Window test: an `ordered` post-compact row with no `saved` row, then an `early` order. The brief's `from_off` and `since` come from the last `saved` row. A `voided` row gives no tracking item at `sync`, and the pair can be ordered again.

## 2. Sweep and proof demands the lead had already answered are still carried

**What happened.** Transcript offsets of the blocks and the lead's answers:
- **Demand never discharged by a near-literal rerun.**
  - 16:10:30 (226759215) demanded `grep -r 'bash_results\|oracle' .ci/rediacc_ci/ .claude/rediacc_hooks/ ...`.
  - At 16:10:39 (226826801) the lead ran `grep -rln 'bash_results\|ORACLES\b\|\.claude/oracles' .ci/rediacc_ci/ .claude/rediacc_hooks/`: the same paths and a shared alternative.
  - It was still owed at 16:13:17, 16:17:15 and 16:29:10.
- **`find` demand never discharged even when run verbatim.**
  - 16:29:10 (229081719) demanded `find .ci/rediacc_ci -name '*shadow_driver.py' -type f`.
  - The lead ran exactly that at 16:29:15 (229129805) and reported "0 still call `mkdtemp(`".
  - It was still owed at 16:57:32 (231132460) and 17:19:59 (231522129).
- **The owed search is cut off before the lead can see it.** Block texts read "STILL OWED: A bash orac" (16:13:17) and "...Python withou" (16:17:15). The search that R.2 needs the lead to rerun is never shown.
- **Proof has no discharge at all.** Proof STILL OWED rode 16:10:30, 16:23:57 and 16:29:10.
- **The fix-set cannot see submodule content.**
```
  - At 16:23:57 (228361085) the judge said "no test files appear in this fix-set". The tests were in `private/account` commit `aea435154`.
```
```
  - The lead spent a turn at 16:24:04 (228428817) showing `git -C private/account show --stat aea435154`.
```
- **UNVERIFIED still blocks.** At 15:49:19 and 16:10:30 the block's own text said "UNVERIFIED: git's own file list for this fix-set does not match" the class. Both blocked anyway.
- **Feature ticks were asked for class sweeps whose "class" is not a code defect.** 16:57:32 was "Retro work completed but not formally recorded". 17:19:59 was "Judge search logic that identifies whether a pattern matches". The lead ran 4 Bash sweeps (231175637 to 231200957, and 231566350) and found 0 copies.

**Root cause.**
- `wl_classsweep.search_pattern` (`.claude/hooks/stop/wl_classsweep.py:226-260`) reads only the tools in `_SEARCH_TOOLS` (`:217`: grep, egrep, fgrep, rg) and `git grep`. `find` gives `""`, and `sweep_evidenced` returns False when the pattern is under 3 characters (`:342`).
- `sweep_evidenced` requires the demand's whole pattern as a substring of the command (`:364`).
- `wl_rules.apply_order` cuts `reason` at 400 characters and `next_action` at 200 (`.claude/hooks/stop/wl_rules.py:292-293`). The STILL OWED sentence, added by `wl_classsweep.enforce` (`:573-577`) and `wl_proofcheck.enforce`, sits at the end of `reason`, so the cap eats it.
- `wl_judge.run_judge` discharges sweep demands only. `PF.load_outstanding()` is used raw (`.claude/hooks/stop/wl_judge.py:750`).
- `wl_reggate.fixset_files` (`.claude/hooks/stop/wl_reggate.py:325`) lists a gitlink path such as `private/account`, never the files in the submodule's commits.
- The UNVERIFIED sentence only annotates (`.claude/hooks/stop/wl_classsweep.py:578-583`, `.claude/hooks/stop/wl_proofcheck.py:205`). The fire still blocks.

**Already fixed?** R.1, R.2 and R.3 are cited, but each holds only for its own narrow shape. None of the causes above is covered.

**Fix.**
- (a) `search_pattern` also reads `find ... -name|-iname|-path <glob>`. `sweep_evidenced` accepts a later Bash call with a tool_result when both hold:
  - it contains at least one of the demand pattern's alternatives (split on `\|` and `|`) of 6 or more characters;
  - it names at least one of the demand's path operands.
- (b) Render STILL OWED as its own line in the block, outside the 400-character cap, as `STILL OWED (run to discharge): <full search>`.
- (c) `wl_proofcheck.discharge_if_evidenced` does the same for proof: a later Bash call with a result that runs `shape_cluster_diff` (`PROOF_PHRASE`) on a path named in the demand's `scope`.
- (d) On the status arm, `fixset_files` expands a gitlink path. When `git diff HEAD -- <gitlink>` shows `a..b`, it adds `<sub>/<file>` for each entry of `git -C <sub> diff --name-only a b`.
- (e) A fresh sweep or proof fire whose `scope_grounded` is False goes to the advisory queue (`outq_add`, key `sweep-ungrounded`) instead of blocking. See Decisions.

**Test.** Add to `test_wl_judge_fixset_scope.py`.
- (a) The demand `grep -r 'bash_results\|oracle' .ci/x/`, then a transcript call `grep -rln 'bash_results\|ORACLES' .ci/x/`: discharged after the change, not before. The demand `find .ci/x -name '*d.py' -type f` run verbatim: discharged after. Inverse: `grep -r 'oracle' docs/` (shares no path) is still owed.
- (b) A block whose owed search is 250 characters shows it in full after the change and cuts it before.
- (c) A proof demand with scope `packages/x`, then a transcript call `shape_cluster_diff.py --rev HEAD packages/x`: discharged.
- (d) The fixture: a submodule whose commit adds `tests/a.test.ts`. After the change, `fixset_files` contains `sub/tests/a.test.ts`.
- (e) The fire with `defect_class` not matching the files: the verdict stays `stop` and one `sweep-ungrounded` advisory is queued. Inverse: a grounded class still blocks.

## 3. Pre-bash guards judge the state an earlier clause of the same command is about to change

**What happened.**
- **19:01:33 (235788851), the bulk-transform guard.** It reported "BLOCKED: 54 staged file(s)". The command (235785506) was `P="... $(ls .../cli.json)"; git commit -q -F $M -- $P`. The 54 were another writer's staged deletions ("A3's staged deletions stay untouched", 235865931). The commit that landed, `1b1a3f398`, has 17 files (235859819).
- **19:02:40 (235855993), the same guard the other way.** The pathspec `$P agent/pr/0923-1.md` passed on 1 counted file for a 17-file commit.
- **19:02:10 (235826760), the untagged-commit guard.** It reported "PR-TASK id 'e4eaf80b' names no epic": the command ran `worklist.py --publish` first. That `--publish` lacked its branch argument and would not have written the file anyway. The lead spent 3 calls finding that out (19:02:16 to 19:02:37).
- **19:28:10 (236588456), the push guard.** It reported "carried ... NOT failing any more: check:ci-paths-origin". The command (236584886) wrote the message file, committed the carry-file fix, ran `ci:quick` and then pushed. The guard judged `carried-reds.json` at the pre-commit HEAD. Because the whole command was refused, the `printf` that wrote `c11-msg.txt` never ran. The lead's split retry (236598224) then failed with "could not read log file" and still spent a full `ci:quick` run, 19:28:18 to 19:31:51 (236602209), on an uncommitted tree.

**Root cause.**
- Every guard runs once, at PreToolUse, before any clause runs.
- `block_unproven_bulk_transform._commit_pathspecs` (`.claude/rediacc_hooks/guards/block_unproven_bulk_transform.py:145-150`) returns the literal token `$P`.
  - `_pathspecs_resolve` (`:122-142`) fails on it, and `run` falls back to `_staged_files` (`:274-275`), which is the shared index.
  - The block text then states the index count as the commit's own count (`BLOCK_COMMIT`, `:57`).
- `block_untagged_commit.py` (snapshot read at `:272`) and `block_unverified_push.py` (`_carried_at_head`, `:235`) read state that an earlier clause (`--publish`, `git commit`, `ci:quick`) was about to change. Their messages never say so.
- `worklist.py --publish` needs an explicit branch (`.claude/hooks/stop/worklist.py:1887`) instead of defaulting to HEAD's branch.

**Fix.**
- (a) Add `shellscan.earlier_mutators(cmd, verb)`: the simple commands before the guarded verb that write guard inputs (`git commit|add|rm`, `npm run ci:quick`, `worklist.py --publish`, and `>` redirections).
- When a guard is about to refuse and such a mutator exists, it refuses with a new `V_SPLIT` message instead: "Nothing in this command ran, including `<first clause>`. This guard judged `<input>` as it was before `<mutator>`. Run `<mutator>` as its own call, then `<verb>`." The guards keep failing closed.
- (b) The bulk guard expands `$NAME` and `${NAME}` pathspec tokens from a literal `NAME=...` assignment earlier in the same command. It globs `$(ls <glob>)` in cwd. A token that is still unexpandable is reported as "pathspec `$P` could not be expanded; 54 is the shared index, not this commit".
- (c) `--publish <me>` defaults its branch to `git rev-parse --abbrev-ref HEAD` when it is not detached.

**Test.** New file `.claude/rediacc_hooks/tests/test_guard_chained_state.py`, with a fixture repo.
- 60 staged unrelated deletions plus `P="a.ts b.ts"; git commit -F m -- $P`. It refuses citing 60 before the change, and allows after (2 files).
- Inverse: `P="$(git ls-files '*.ts')"` over 25 files is still refused, now with the expanded count.
- `printf ... > m; git commit -F m -- x; git push`, with HEAD carrying a stale carry file: the refusal contains `V_SPLIT` and names `git commit`.
- The `--publish` default: `worklist.py --publish <me>` on branch `t-1` writes `agent/pr/t-1.md`.

## 4. Tick evidence refusals

**What happened.** Tick-refusals rows:
- Rows 1 to 3 (16:05:52, 16:06:11, 16:07:30): 3 refusals on #7d4e2829 quoting "operator /ask 2026-09-24T16:0xZ".
- Row 4 (18:04:52): #bc32947d, "test_bash_semantics 257 passed", with no path:line.
- Rows 5 and 6 (18:37:08, 18:37:16): #3f65e5c8 with 7-hex and then 40-hex shas from `private/generative`, `private/growth` and `private/growth/corporate/legal-tax/maasikas.emta.ee`. Hint row 18:37:25. The lead switched to GitLab URLs at 18:37:25 (235205145).

**Root cause.**
- `M.CLI_TICK_NO_EVIDENCE` (`.claude/hooks/stop/worklist_messages.py:1438-1443`) lists "a real sha, a run id, a file:line that resolves, an exit code, or a URL". It never names R.8's `rc=N` or `ASKED:<YYYY-MM-DDTHH:MM>`, and the lead wrote "16:0xZ".
- `completion_evidence` (`.claude/hooks/stop/wl_checks.py:375`) resolves shas only in the console and its 4 submodules (`private/renet`, `homebrew-tap`, `elite`, `account`). The independent repos `private/generative` and `private/growth` (and the nested `maasikas.emta.ee`) are never tried.
- The budget of 5 calls is counted per candidate and per root (`:376-383`).

**Already fixed?** R.8 added the `ASKED:` shape, but nothing tells the session it exists. Sibling repos are not covered.

**Fix.**
- The refusal lists every accepted shape. When the lead transcript holds an AskUserQuestion result within the last 2 hours, it prints the ready-to-paste `ASKED:<minute>` of the newest one (reusing `_asked_in_transcript`'s scan).
- `roots` adds every non-submodule git repo under `private/` up to depth 4, found by one cached walk.
- Each root is asked once with `git cat-file --batch-check` over all candidates, so the cost is the number of roots, not candidates times roots.

**Test.** Add to `test_wl_tick_evidence_shapes.py`.
- A sha that exists only in a sibling fixture repo `private/sib` (not a submodule): False before the change, True after.
- A fabricated 40-hex sha: still False, in at most `len(roots)` subprocess calls.
- The refusal text for a planted AskUserQuestion at 16:04: contains `ASKED:2026-09-24T16:04`.

## 5. The submodule pointer check ignores a KEEP decision the lead recorded

**What happened.**
```
- The same move, `private/account 9fda8c7c2 -> aea435154`, blocked at 15:58:03 (225751082) and at 16:15:36 (blocklog row 3, 227451953), 17.5 minutes apart.
```
- Item #f2dd1732's note already recorded "account pointer 9fda8c7 -> aea4351 ...: KEEP".
- The lead said "the check fires on the unstaged gitlink every stop" and staged the gitlink only to silence it (227488025).
```
- 18:31:58 (`ba7d9e313 -> 2d1da2201`) is the tree lagging the babysitter's snapshot commits (hint row 18:32:22). That cause is not proven here, and no box is filed for it.
```

**Root cause.** `submodule_decision_recorded` (`.claude/hooks/stop/wl_checks.py:1022-1060`) accepts only a **ticked** item containing `sha[:9]`. A decision recorded in an open `[>]` item's note, with a 7-character sha, never matches. The check therefore falls back to the 15-minute latch (`SUBMODULE_LATCH_MIN`, `:1008`).

**Fix.** Also accept an owned open or `[>]` item whose latest note carries `KEEP` or `DROP`, the submodule path, and a sha prefix of 7 or more characters that the target sha starts with.

**Test.** New file `.claude/rediacc_hooks/tests/test_wl_submodule_decision.py`.
- The control: a `[>]` item noting `private/account 9fda8c7 -> aea4351: KEEP`. The predicate is False before the change and True after.
- Inverse: a note without KEEP or DROP stays False. A different sha stays False.

---

## Decisions (default applies unless the operator says otherwise)

- **A PostCompact whose owner cannot be determined.**
  - DEFAULT: order no retro and leave `ctx_fresh` untouched. The briefing is still emitted.
  - WHY: a wrong row permanently takes a band and blinds the next brief (#1). A missing order costs one retro, and R.17 makes the next retro cover the range anyway.
  - HOW: switch `compaction_owner == "unknown"` to order the retro, a one-line change.
- **The briefing a sub-agent gets on compaction.**
  - DEFAULT: keep the full briefing, prefixed with one line: "This compaction is sub-agent <id>'s; the STATE.md below is the lead's."
  - WHY: no harm was measured, and the babysitter's context after compaction is not in its transcript.
  - HOW: veto, which suppresses the lead's STATE.md for sub-agents.
- **An UNVERIFIED sweep or proof fire.**
  - DEFAULT: an advisory, not a block.
  - WHY: its own sentence says git's file list does not match the class (15:49:19, 16:10:30).
  - HOW: veto keeps today's annotate-and-block behaviour.
- **Near-literal discharge.**
  - DEFAULT: at least one alternative of 6 or more characters, and at least one shared path operand.
  - WHY: the lead's 16:10:39 sweep shares `bash_results` and both paths with the demand.
  - HOW: tighten to require every alternative.
- **Sibling repos for tick evidence.**
  - DEFAULT: git repos under `private/` up to depth 4.
  - WHY: `maasikas.emta.ee` sits at depth 4.
  - HOW: widen or narrow `SIBLING_DEPTH`.

## Sequencing

- **Writer A** does R.16 and R.17: `ctx_budget.py`, `wl_checks.handle_post_compact`, `wl_retro.py`, and `test_wl_retro.py`. Do this first, because it protects the next retro's inputs, and append the migration `voided` row before the lead's next stop, so #1 consequence (c) never fires.
- **Writer B** does R.18 and R.19: `wl_classsweep.py`, `wl_proofcheck.py`, `wl_rules.py`, `wl_judge.py`, `wl_reggate.py`.
- **Writer C** does R.22: `.claude/rediacc_hooks/guards/*`, `shellscan.py`, and `worklist.py --publish`. This is independent of A and B.
- R.20 and R.21 (`wl_checks.completion_evidence`, `worklist_messages.py`) and R.23 (`wl_checks.submodule_decision_recorded`) touch `wl_checks.py`. They start after Writer A ticks.

## Tasks

- [x] **R20260924.16** PostCompact attributes the compaction before acting: `ctx_budget.compaction_owner` (the lead transcript's `isSidechain:false` boundary within 120 s, else a `subagents/agent-*.jsonl` boundary). `handle_post_compact` orders the retro and marks `ctx_fresh` only for `"lead"` (`.claude/hooks/stop/wl_checks.py:1582`, `:1647`). The fixture uses the measured payload: no `agent_id`, the lead's `transcript_path`. Test: `.claude/rediacc_hooks/tests/test_wl_retro.py`.
    (ticked) 2026-09-24T20:12:47Z by d778be9d: ctx_budget.compaction_owner .claude/hooks/context/ctx_budget.py:560, gated in wl_checks.handle_post_compact; controls .claude/rediacc_hooks/tests/test_wl_retro.py:299 (measured shape) and :332 (mutant); test_wl_retro 18 passed rc=0; real replay at 19:01:46Z -> agent:a149262d8b6a1601f, 16:25:30Z -> lead
- [x] **R20260924.17** Retro windows start at the previous `saved` (or `dispatched`) row, not the previous `ordered` row (`ctx_budget.retro_from_off` `:480`, `wl_retro.brief` `:229`). A `voided` event frees a misattributed `(session, band)`. One migration row voids `(d778be9d, post-compact)` of 19:01:46Z. Test: `.claude/rediacc_hooks/tests/test_wl_retro.py`.
    (ticked) 2026-09-24T20:12:47Z by d778be9d: retro_window_start and retro_live/retro_void .claude/hooks/context/ctx_budget.py:473, brief recomputes the window; tests .claude/rediacc_hooks/tests/test_wl_retro.py:356 and :378, 18 passed rc=0; migration voided row agent/ledgers/stop-hook-retros.jsonl:8 via retro_void
- [x] **R20260924.18** Sweep and proof discharge read what the lead actually ran:
  - `search_pattern` reads `find -name/-iname/-path`.
  - `sweep_evidenced` accepts a shared alternative of 6 or more characters plus a shared path.
  - `wl_proofcheck` gains `discharge_if_evidenced`, wired at `.claude/hooks/stop/wl_judge.py:750`.
  - STILL OWED renders on its own line with the full search, outside `wl_rules.apply_order`'s 400-character cap.
    (ticked) 2026-09-24T20:47:47Z by d778be9d: find/near-literal discharge .claude/hooks/stop/wl_classsweep.py:352, PF.discharge_if_evidenced .claude/hooks/stop/wl_proofcheck.py:196 wired at .claude/hooks/stop/wl_judge.py:753, STILL OWED line .claude/hooks/stop/wl_rules.py:293; test_wl_judge_fixset_scope 23 passed rc=0

  Test: `.claude/rediacc_hooks/tests/test_wl_judge_fixset_scope.py`.
- [x] **R20260924.19** `fixset_files` expands a changed gitlink into `<sub>/<file>` entries, and an ungrounded (UNVERIFIED) fresh sweep or proof fire is queued as the `sweep-ungrounded` advisory instead of blocking (`.claude/hooks/stop/wl_reggate.py:325`, `.claude/hooks/stop/wl_classsweep.py:578`, `.claude/hooks/stop/wl_proofcheck.py:205`). Test: `.claude/rediacc_hooks/tests/test_wl_judge_fixset_scope.py`.
    (ticked) 2026-09-24T20:47:47Z by d778be9d: gitlink expansion .claude/hooks/stop/wl_reggate.py:366, ungrounded fresh fire -> sweep-ungrounded advisory .claude/hooks/stop/wl_checks.py:4616; test_wl_judge_fixset_scope 23 passed rc=0
- [x] **R20260924.20** Tick evidence resolves shas in non-submodule sibling repos under `private/` (depth 4 or less), with one `cat-file --batch-check` per root (`wl_checks.completion_evidence` `:375-384`). Test: `.claude/rediacc_hooks/tests/test_wl_tick_evidence_shapes.py`.
    (ticked) 2026-09-24T20:47:47Z by d778be9d: evidence_roots and one cat-file --batch-check per root .claude/hooks/stop/wl_checks.py:438; test_wl_tick_evidence_shapes 10 passed rc=0
- [x] **R20260924.21** The tick refusal names every accepted shape, including `rc=N` and `ASKED:<YYYY-MM-DDTHH:MM>`, and prints the newest AskUserQuestion answer minute from the lead transcript (`worklist_messages.CLI_TICK_NO_EVIDENCE` `:1438`, `.claude/hooks/stop/worklist.py:861`). Test: `.claude/rediacc_hooks/tests/test_wl_tick_evidence_shapes.py`.
    (ticked) 2026-09-24T20:47:48Z by d778be9d: every shape plus ASKED hint .claude/hooks/stop/worklist_messages.py:1440 and tick_refusal_hint .claude/hooks/stop/wl_checks.py:357; test_wl_tick_evidence_shapes 10 passed rc=0
- [x] **R20260924.22** Pre-bash guards name a same-command mutator:
  - `shellscan.earlier_mutators`, and `V_SPLIT` in the bulk-transform, untagged-commit and push guards.
  - The bulk guard expands `$VAR` pathspecs from same-command assignments and never reports the shared index as the commit's count (`.claude/rediacc_hooks/guards/block_unproven_bulk_transform.py:145`, `:274`).
  - `worklist.py --publish <me>` defaults to HEAD's branch (`.claude/hooks/stop/worklist.py:1887`).
    (ticked) 2026-09-24T20:48:07Z by d778be9d: shellscan.earlier_mutators/split_refusal/V_SPLIT/assignments_before .claude/rediacc_hooks/shellscan.py:1631; V_SPLIT in .claude/rediacc_hooks/guards/block_unproven_bulk_transform.py:368, .claude/rediacc_hooks/guards/block_untagged_commit.py:299, .claude/rediacc_hooks/guards/block_unverified_push.py:231; $VAR pathspec expansion .claude/rediacc_hooks/guards/block_unproven_bulk_transform.py:192 with shared-index wording COUNT_UNEXPANDED :62; --publish defaults to HEAD .claude/hooks/stop/worklist.py:1900; tests .claude/rediacc_hooks/tests/test_guard_chained_state.py 8 passed rc=0 (7 failed before), test_guards_differential 5946 passed rc=0

  Test: `.claude/rediacc_hooks/tests/test_guard_chained_state.py`.
- [x] **R20260924.23** `submodule_decision_recorded` accepts an owned open or `[>]` item whose note carries KEEP or DROP, the path, and a sha prefix of 7 or more characters (`.claude/hooks/stop/wl_checks.py:1022`). Test: `.claude/rediacc_hooks/tests/test_wl_submodule_decision.py`.
    (ticked) 2026-09-24T20:47:48Z by d778be9d: open-item KEEP/DROP arm .claude/hooks/stop/wl_checks.py:1108; test_wl_submodule_decision 6 passed rc=0

### Critical Files for Implementation
- /home/developer/console/.claude/hooks/stop/wl_checks.py
- /home/developer/console/.claude/hooks/context/ctx_budget.py
- /home/developer/console/.claude/hooks/stop/wl_retro.py
- /home/developer/console/.claude/hooks/stop/wl_classsweep.py
- /home/developer/console/.claude/rediacc_hooks/guards/block_unproven_bulk_transform.py
