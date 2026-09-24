# PLAN: Stop-hook retro, 2026-09-24 (first retro, lead session d778be9d)

Status: ready
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
- `st_sig` comes from `wl_store.state_world_sig` (`.claude/hooks/stop/wl_store.py line 2563-2602 (blob 63cdd1d7cd2a17655a07c02b9797248cc0c2e33b)`), which hashes the harness task statuses and `rev-parse HEAD` (`:2595-2600`).
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
- The tick evidence `agent/plans/PLAN-stop-hook-retro-<date>.md` :1 resolves as a file:line citation.
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
- [x] **R20260924.4** `no-remaining` banks on `items_sig`, not `st_sig` (`wl_checks.py :2304`, `:3656`). Test: `test_wl_remaining_bank.py`.
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
- [ ] **R20260924.11** Retro order on the band path, after the STATE.md write, with the `RETRO_ORDER` text and an `ordered` ledger row (`band-notice.py`, `ctx_budget.py`). Test: `test-context-bands.py`, including mutations.
- [ ] **R20260924.12** Retro order on the PostCompact path, with the `agent_id` guard (`wl_checks.handle_post_compact`, `worklist_messages.CTX_POSTCOMPACT_RETRO`). Test: `test_wl_retro.py`.
- [ ] **R20260924.13** `wl_retro.sync` writes the tracked, dispatched and saved rows and creates the tracking item. `worklist.py --retro-brief` prints the brief with `#id`, the byte range and the do-not-re-propose list. Test: `test_wl_retro.py`.
- [ ] **R20260924.14** Add box P3.1 to PLAN-stop-hook-continuity.md, pointing at R.11 to R.13, and document the band-notice "does not instruct" exception in its docstring.
- [ ] **R20260924.15** After R.1 to R.13 land, re-count all seven frictions on the next session's `.blocklog` and record the before and after numbers in this plan's Status.

### Critical Files for Implementation
- /home/developer/console/.claude/hooks/stop/wl_reggate.py
- /home/developer/console/.claude/hooks/stop/wl_checks.py
- /home/developer/console/.claude/hooks/stop/wl_roster.py
- /home/developer/console/.claude/hooks/stop/wl_report.py
- /home/developer/console/.claude/hooks/context/band-notice.py
