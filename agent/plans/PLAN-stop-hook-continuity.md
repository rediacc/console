# PLAN: Stop-hook continuity. Make it surface what it computes, and stop generating turns

Status: draft. This plan came from read-only research and no code has changed. It is not adopted by any session, so its boxes are advisory until the lead adopts it.
Owner: d778be9d
First-Seen: 2026-09-24
Updated: 2026-09-24

**Line numbers.** They refer to the working tree on branch `0923-1` as it stands mid-way through the cross-session messaging removal. That removal is uncommitted and edits most of these files, so line numbers in `wl_checks.py` will shift. Every citation also names its function or constant, so a writer can re-anchor on the symbol.

The operator asked:

> *"when you step back and look at stop hook. What was annoying? How that thing could be better in terms of automated context/flow/job/plan/task continuity? ... there is/was an auto heal planning about the stop hook ... it hasn't popped up. Honestly there are other popup features that never popped up at all."*

**The short answer.** `run_stop` has one exit that releases advisories and runs the judge-side features. Any static violation makes the stop take the block exit first (`.claude/hooks/stop/wl_checks.py:3725-3840`), and a busy session always has one. So everything computed after that exit, or queued for the allow path, is invisible for exactly as long as the session is productive. Meanwhile the block itself serves one check per stop, and several of the checks it serves ask the agent to restate facts the hook already holds.

## Operator rulings (2026-09-24, /ask)

- **P0.1/P0.2 block output: "One quoted + others named".** This supersedes the 2026-07-31 "single and focused message" rule for blocked stops. One check stays quoted in full. Every other outstanding check gets one line (key plus about 150 characters), plus a digest of at most 6 queued advisories.
- **P1.4 status ping: "Evidence counts as status".** The 20-minute number stays. Transcript growth since the last stop, or a tool call in flight, records the status automatically; only real silence blocks, merged into `roster-silent`.

---

## PART 1. Features that never surface

### 1.1 The advisory output queue (outq)

**Mechanism**
- `outq_add` is at `.claude/hooks/stop/wl_checks.py:1033-1097`. It persists immediately and dedupes on `sha1(text)`, with a `REPORT_REFRESH_MIN` of 360 min (`:994`).
- `outq_drain` is at `.claude/hooks/stop/wl_checks.py:1100-1142`. It releases priority tiers in ascending order, and picks at random inside a tier.
- The budget is fixed at `OUTQ_PER_STOP = 3` (`.claude/hooks/stop/wl_checks.py:1001`), and the comment at `:999` says it is "not tunable".
- `OUTQ_MAX = 40` (`:1002`), but `_outq_cap` never drops a sticky entry (`:1019-1030`). That is how the queue reached 58 entries.

**The drain rule**
- `outq_drain` has exactly one call site, on the allow tail (`.claude/hooks/stop/wl_checks.py:4491-4495`).
- A blocked stop appends only the count, `M.N_OUTQ_BLOCKED` (`.claude/hooks/stop/wl_checks.py:3734-3738`). The message itself (`.claude/hooks/stop/worklist_messages.py:1216-1224`) says "the queue drains only on a clean stop".
- A cadence-paused stop exits at `.claude/hooks/stop/wl_checks.py:3689-3711` without draining either.

**The gate that decides everything.** A stop with any static violation exits at `:3746` (focus off) or `:3826` (focus on, the default). The judge section starts at `:3842`, and the allow tail at `:4401`.

**Every producer.** Column "A" says whether the producer is reachable while stops keep blocking:
- **computed** means it is enqueued on a blocked stop.
- **allow-only** means it only runs on the allow tail.
- **judge-only** means it only runs on a stop with zero static violations.

| Line | Key | Prio | Sticky | A | Seen in an always-blocked session? |
|---|---|---|---|---|---|
| 1159 | `agent-corpus-err` | 3 | | allow-only (`agent_hint_queue`, called at `:4461`) | **Never** |
| 1180 | `agent-hint:<name>` | 3 | | allow-only | **Never** |
| 1876 | `resprofile` | 3 | | computed (`:1900`) | **Never** |
| 1917 | `archived` | 1 | yes | computed | **Never** (count only) |
| 2033 / 2075 / 2089 | `reg-forgot` / `reg-flood` / `reg-queue` | 1 | 2 of 3 sticky | computed | **Never** |
| 2302 | `ladder` (the 45-min liveness ping) | **0** | yes | computed | **Never.** The block's `extras` carry only `ci_report` and `queue_note` (`:3731-3733`), so a worker's first warning is hidden and the 90-min block is the first thing the session sees. |
| 2797 | `plan-tasks` (plan box census) | 2 | | computed | **Never.** This is the failure the `N_OUTQ_BLOCKED` comment records (ten boxes unseen across about 20 stops). |
| 2816 | `plan-backlog:<plan>` (wl_backlog: "we plan but don't implement") | 2 | | computed | **Never** |
| 2848 | `plan-clock` (wl_planenforce warn band) | 2 | | computed | **Never** |
| 2916 | `ci-queue` | 0 | | computed | **Yes.** Its body rides the block's `extras` (`:3731-3733`). |
| 3110 | `ci-report` | 0 | | computed | **Yes**, same route. It is also left queued, so it repeats on the next allow stop. |
| 3229 | `agent-peers` | 2 | | computed | **Never** |
| 3287 | `unread-reports` (< 15 min) | 2 | | computed | Only after it graduates to a `vadd` at 15 min (`:3284`) or 45 min (`:3282`) |
| 3298 | `ask-refusals` | 2 | | computed | **Never** |
| 3315 / 3323 | `phantom-blind` / `phantom-identity` | 1 | | computed | **Never** |
| 3343 | checklist advisories | var | | computed | **Never** |
| 3557 | `planfid-degraded` | 1 | | computed | **Never** |
| 4073 | `defer-settle` | 2 | yes | judge-only | **Never** |
| 4131 | `claim-check` | 2 | yes | judge-only | **Never** |
| 4187 | `reg-settled` | 2 | yes | judge-only | **Never** |
| 4233 | `reg-capped` | 1 | yes | judge-only | **Never** |
| 4294 | `audit` | 1 | yes | judge-only | **Never** |
| 4361 | `shapedup` | 2 | | judge-only, and only if `judged_ok` | **Never** |
| 4394 / 4396 | `shapedup-wide` / `-note` | 2 | | judge-only. The comment at `:4378` says it "survives a blocked stop", but it cannot be computed on one. | **Never** |
| 4422 / 4431 / 4451 | `others` / `orphans` / `others-items` | 2 | | allow-only (`:4417-4458`) | **Never** |
| 4448 | `handoff` | 1 | | allow-only | **Never** |
| 4472 | `hint-corpus-err` | 3 | | allow-only | **Never** |
| 4482 | `hint-proposals` | 3 | | allow-only | **Never** |

**Net:** only the two CI notes ever reach a busy session. Everything else is a count.

### 1.2 The "auto heal" the operator remembers

No feature is literally named auto-heal. Searches across `.claude/hooks/stop`, `agent/plans`, `agent/plans/_done`, `docs/agent-reference`, the git log and the older transcripts found none. There are four self-improvement channels, and each is gated where a busy session never goes.

1. **The hint-proposal channel** (the likeliest match: *agents improving the hook's own guidance*).
   - `worklist.py --hint-propose <me> <text> [SOURCE: ...]` (`.claude/hooks/stop/worklist.py:538-560`) appends to `agent/ledgers/hint-proposals.jsonl`.
   - The hook then queues `hint-proposals` (`.claude/hooks/stop/wl_checks.py:4480-4490`), and a human promotes an entry into `docs/agent-reference/HINTS.md`.
   - Its only advertisement is one hint entry, `docs/agent-reference/HINTS.md:107-112`. That entry says so itself: *"This is the sole advertisement of the proposal channel ... Removing this entry silently kills the channel's only way of reaching a session."*
   - Hint lines render only on the allow tail, behind `if parts or wl_popup.should_pop():` (`.claude/hooks/stop/wl_checks.py:4501-4506`). The corpus has 13 entries, one shown per allow stop.
   - The proposal count is also allow-only, at priority 3.
   - **Result:** `agent/ledgers/` contains only `census-claim-check.jsonl`, `census-plan-record.jsonl` and `plan-investigation.jsonl`. **Zero proposals have ever been written.** The loop advertises itself only through itself.
2. **The admission detector** (`wl_admit.py`). It turns `"I clobbered X"` into a tracked prevention item, and its `machinery` residue class is exactly "the hook or a guard needs to change" (`.claude/hooks/stop/wl_admit.py:14-27`).
   - Its docstring promises Tier R: *"every prefilter hit is appended to a log, always, BEFORE any model call"* (`.claude/hooks/stop/wl_admit.py:29-33`). The call-site comment repeats *"The prefilter runs on every stop"* (`.claude/hooks/stop/wl_checks.py:3877`).
   - **Both are false on a blocked stop.** `admit_text`, `prefilter` and `record_hits` sit at `.claude/hooks/stop/wl_checks.py:3880-3910`, after the block exit. A session that admits a mistake while busy leaves no record at all.
3. **The block footer's self-repair order.** `R_BLOCK_FOCUS` (`.claude/hooks/stop/worklist_messages.py:1299-1303`) says: `"A check that fires wrongly is a bug in %s; you are the session that fixes it."` This is the one heal instruction that does surface, because it rides every block. But it has no low-cost outlet: nowhere to record "this check misfired", so the only options are a full fix turn or ignoring it.
4. **The self-improvement program log** (`agent/programs/self-improvement/LOG.md`). Its last entries are dated 2026-09-01. No hook reads it and nothing surfaces it, so it stopped after one session.

### 1.3 Other features gated on conditions a busy session never meets

- **The popup reminder** (`wl_popup.should_pop`, wired at `.claude/hooks/stop/wl_checks.py:4501`; plan `agent/plans/_done/PLAN-popup-reminder.md`). The popup exists only to fire on an otherwise silent clean stop, which a busy session never has.
- **The rotating behavioral hint** (`wl_hints`, `.claude/hooks/stop/wl_checks.py:4494-4506`). Allow tail only. The `wl_hints` docstring says a hint "rides an output the stop was already going to produce", yet a block also produces output and it never rides that one.
- **`judged_ok` only:**
  - the narrow shape rule (`.claude/hooks/stop/wl_checks.py:4343-4377`)
  - the judge stamp line (`:4404-4419`)
  - verdict banking (`:4397`)
- **Judge section only** (zero static violations), all of it:
  - the regression gate, class sweep, proof obligation, brave default, claim check, deferral audit and defer-settle (`.claude/hooks/stop/wl_checks.py:3842-4400`)
  - the widened shape tier
  - the admission detector

  In a busy session, fix-sets pile up unjudged until the first clean stop, which then pays for all of them at once (see 2f).
- **SessionStart and PostCompact only:** the plans census `plans_block`, the design-docs listing and the checklists listing (`handle_session_start`, `.claude/hooks/stop/wl_checks.py:1328-1387`; the comment at `:780` says it "fires at SessionStart and PostCompact OUTSIDE the outq"). A long session that never compacts sees them once.

### 1.4 The rotation: "1 more check outstanding; the next stop surfaces the next one"

**Where it is**
- The text is `R_FOCUS_MORE` (`.claude/hooks/stop/worklist_messages.py:1305-1307`).
- The pick is at `.claude/hooks/stop/wl_checks.py:3767-3797`. It is least-recently-served over the rotating keys, and the sort key is `(covered, served_seq, check_tier, battery_order)`. Exactly one rotating check is quoted (`:3821-3822`), and the rest are a count (`:3825`, `:3835`).

**Why it was designed that way**
- The operator's 2026-07-31 order *"single and focused message at a time"* (`.claude/hooks/stop/wl_checks.py:2332`), after the complaint `"Why I see such a big output?"`.
- The v21 ladder (`:1634-1658`) walks tiers by staleness "UNTIL WE CHECK ALL OF THEM" (`:3784-3785`).
- The design's own worst case is stated plainly: *"Worst-case wait for any rotating check is (distinct outstanding checks - 1) stops"* (`:3766`).

**The cost.** N rotating blockers cost N full turns.

**The precedent that already solves this.** The invariant tier already uses a collapse. At most `ALWAYS_FULL_MAX = 2` are quoted in full, and the rest are *named* on one line each through `R_ALWAYS_COLLAPSED` (`.claude/hooks/stop/wl_checks.py:3808-3820`, `.claude/hooks/stop/worklist_messages.py:508`). The rotating tail never got that treatment.

**The existing escape.** `WORKLIST_FOCUS=off` (`.claude/hooks/stop/wl_checks.py:3742-3764`) quotes every violation in full. That brings back the "big output" the operator rejected.

---

## PART 2. The pain points, verified, with root causes

### a. Serialized blockers
**Confirmed.** See 1.4. The root cause is that the rotating tail is reported as a bare count (`.claude/hooks/stop/wl_checks.py:3825,3835`) rather than named. A second root cause amplifies it: several rotating checks exist only to make the agent restate facts (see b).

### b. Maintenance churn the hook could satisfy itself

| Check | Where | Root cause | Automatable from facts the hook already holds? |
|---|---|---|---|
| **STATE.md rewrite about every 20 min** (`agent-state`, rotating) | vadd `.claude/hooks/stop/wl_checks.py:3171-3191`; verdict `wl_store.agent_state_state` (`:2421-2428`); key `wl_store.state_world_sig` (`:2503-2542`); `AGENT_STATE_STALE_MIN=15` (`.claude/hooks/stop/wl_store.py:75`) | Stale = older than 15 min **and** the structural signature moved. That signature includes `rev-parse HEAD` and the harness task statuses (`:2535-2541`), so **every commit and every new background task** stales it. | **Yes.** The facts half (open, in-flight and deferred items, roster, HEAD, PR, CI) is what `guided_slice`, `wl_roster.summary_lines` and `wl_ci` already compute, and it can be rendered at read time in `handle_post_compact` (`.claude/hooks/stop/wl_checks.py:1390`). The agent keeps only the judgment (`## Next action` plus traps). Staleness should key on judgment facts only: *the items named in `## Next action` have all closed.* |
| **Session brief every 90 min** (`brief`, rotating) | `.claude/hooks/stop/wl_checks.py:2708-2726`; `SESSION_BRIEF_STALE_MIN=90` (`.claude/hooks/stop/wl_store.py:69`); `brief_state` (`:2130-2152`) | The message `V_BRIEF` (`.claude/hooks/stop/worklist_messages.py:173-178`) justifies it as *"Other sessions share this worktree"*. That premise is gone under the single-terminal ruling and the messaging removal. Its surviving uses are peer listing and a liveness proxy (`.claude/hooks/stop/wl_store.py:2168-2173`). | **Yes, delete the demand.** The hook stamps the brief itself on each stop, from the first line of `## Next action` or the newest `[>]` item. A hook that is running is stronger liveness evidence than a hand-typed brief. |
| **Design-doc drift, docs/ci-overhaul** (`docs-drift`, rotating) | `docs_drift` `.claude/hooks/stop/wl_checks.py:547-567`; vadd `:3333-3335`; `DESIGN_DOCS` / `DOCS_DRIFT_MAX=10` / `PROGRAM_SURFACE=".ci .github .claude"` (`:71-74`) | It counts any commit under `.claude`. Hook work is not what the CI-overhaul docs describe, so hook sessions are ordered to edit unrelated docs. | **Delete the Stop vadd.** The SessionStart block already reports DRIFTED or pending (`.claude/hooks/stop/wl_checks.py:1345-1362`). |
| **20-min worker status ping** (`roster-status`, always tier) | `.claude/hooks/stop/wl_checks.py:2389-2395`; `status_at` `.claude/hooks/stop/wl_roster.py:492-515`; `status_due` `:517-524`; `STATUS_PING_MIN=20` (`:37`) | `--status` (`status_verb`, `.claude/hooks/stop/wl_roster.py:729-800`) records transcript size and whether a tool call is in flight. The hook already computes both every stop (`scan_transcript`, `quiet_min`, `inflight`: `.claude/hooks/stop/wl_roster.py:416-428`). | **Yes.** Record an automatic status for every supervised agent whose transcript grew since the last stop, or that has a tool call in flight. What remains is real silence, which `roster-silent` already covers. **Operator decision needed:** the 20-min ping is the operator's number. The default is to keep the number but let evidence answer it. |
| **"Unread sub-agent reports" that repeat task notifications** (`unread-reports`, T_OWED; rotating at 15 min, invariant at 45) | `.claude/hooks/stop/wl_checks.py:3252-3289`; `wl_report.unread` (`.claude/hooks/stop/wl_report.py:277-291`); `--read` (`:965-1000`) | The report id is `short_id(agent_id)` (`.claude/hooks/stop/wl_report.py:367`). The lead's transcript already holds `<task-notification>\n<task-id>{agent_id}</task-id>...<status>completed</status>...<result>` (this session's transcript has 3,457 of them). Nothing joins the two. | **Yes.** Mark a report read automatically when a completed task notification for the same agent id appears in the lead transcript after the capture time. Keep `[SILENT]` reports (an empty `<result>`) as a real signal. |

### c. Lease bookkeeping done by hand

**Verified facts**
- `--lease` takes one item id per call. It requires `worker:<background-task-id>` (`.claude/hooks/stop/worklist.py:1025-1031`) and caps the lease at `MAX_LEASE_MIN=120` (`.claude/hooks/stop/wl_core.py:44`).
- A lease on a shell that exited either fails closed into an open item (`wl_store.classify_items`, `.claude/hooks/stop/wl_store.py:1291-1301`) or reads as `unknown: no meta and not in the event` (`.claude/hooks/stop/wl_roster.py:481-482`). Every new M-live shell therefore needs a new `--lease` on the same items.
- New agents: lineage inheritance exists for **children** (`covered_by` over descendants, `.claude/hooks/stop/wl_roster.py:453-459`), but not for a **successor** agent spawned for the same items.
- Blocked-by: `BLOCKED_ON:` exists only as a deferral justification token (`.claude/hooks/stop/wl_core.py:30-32`). An open `[ ]` item has no way to say "waiting on #x", so the only way to quiet `open-items` and `idle-stall` for it was to lease it to an unrelated shell.
- There is no in-session lead state. `worker:queue` exists only for work held behind the writer cap (`.claude/hooks/stop/wl_roster.py:39`, `.claude/hooks/stop/worklist.py:1032-1042`).

**Design (no escape hatches; every state fails closed to open)**

1. **`worker:lead`.** The lead is driving the item inline.
   - Covered while at least one background task of this session is live, meaning something will wake the lead: an OS-confirmed shell, a fresh subagent or workflow stream, or a shell waiter.
   - While covered, the hook renews `until` at stop time. It appends a `lease` event with `by: hook`, which ends manual renewals.
   - With nothing live, the item fails closed to open exactly as an expired lease does today. The lead can take a stop only while its own machinery will wake it, which is precisely the M-live pattern.
   - Excluded from the roster's writer accounting.
   - At most 3 at once (a sealed literal). Beyond that, the lease is refused.
2. **Inheritance by declaration, verified at stop time.**
   - At each stop, for each live agent in the roster (or each live shell), parse `#<8hex>` item ids from the agent's first prompt record (its transcript head), or from the shell's `description`.
   - An id owned by this session that is open, or leased to a gone or finished worker, gets an automatic `lease` event, `worker:<task-id>`, `by: hook`.
   - This also closes F3 in `PLAN-parallel-writer-roster.md` (a lease-time check is blind to a just-spawned worker), because the check now runs at stop time against the live event.
3. **Batch verbs.**
   - `--lease <me> <id>[,<id>...] +N worker:X` takes a list of ids.
   - `--relay <me> <old-worker> <new-worker>` moves every lease on one worker to another in one event batch.
4. **`BLOCKED_BY:#id[,#id]`.** An item-text token folded into `rec["blocked_by"]`.
   - `classify_items` reports a blocked `[ ]` item as `waiting (#x)` instead of `open`. It is excluded from `open-items`, `idle-stall` and auto-lease.
   - When every blocker reaches `[x]` or `[~]`, the item reverts to open and the hook queues one sticky line: "unblocked #y".
   - The token is refused on a cycle and on an unknown or closed blocker.
   - A chain must end in an ordinary open or `[>]` item, and that root still blocks. It therefore cannot hide work.

### d. Liveness false positives: the remaining siblings

Already fixed: `shell_waiters` (commit 4ee524a1e), the `worker:queue` status (c913c8a37), and `workflow_stream` / `worker_facts` (61ade0880). Siblings that still ignore workflows or waiters:

1. **`wl_liveness.all_waits_live`, `.claude/hooks/stop/wl_liveness.py:300-314`.** Any task type other than `teammate`, `subagent` or a confirmed `shell` returns False (`:309`). A **workflow** is therefore never covered, even though `bg_output_facts` has just computed its fresh stream through `workflow_stream` (`:163-168`). The 15-min pure-wait check-in (`bg-report`, wired at `.claude/hooks/stop/wl_checks.py:2233-2244`) fires on a healthy, streaming workflow. No test covers `all_waits_live`.
2. **`wl_roster.roster` silence, `.claude/hooks/stop/wl_roster.py:527-537`.** A shell waiter has ended its turn by definition, so `inflight` is empty and its transcript does not grow. After 20 min it is reported as `roster-silent` (always tier). Test `test_r3d` (`.claude/rediacc_hooks/tests/test_wl_roster.py:335-347`) plants exactly this agent with a 30-min-old transcript and never asserts on `silent`.
3. **`wl_roster.status_verb`, `.claude/hooks/stop/wl_roster.py:768`.** `silent = not grew and not inflight` records a waiter as SILENT, and the next stop then raises `roster-silent` (the verb's own text at `:790-793`).
4. **`.claude/hooks/stop/wl_checks.py:1939` (`_live_worker_ids`) and `:2259-2270` (`_supervised`).** Both are built from the event's `live_bg`, which lists the waiter's *shell* but not the waiter itself. An expired lease on the waiting agent is not tolerated and fails closed into an open item (`.claude/hooks/stop/wl_store.py:1294`). The stuck detector also does not count the lease as supervision.
5. **`wl_roster.roster` lease coverage, `.claude/hooks/stop/wl_roster.py:470-482`.** A lease on a **workflow** task id matches neither `metas` nor `shells` (shells only). It lands in `unknown: "no meta and not in the event"`, which is wrong because the id is in the event. The roster drops to UNKNOWN.
   - A related gap: `load_metas` (`:89-120`) globs only `subagents/agent-*.meta.json`, not `subagents/workflows/<runId>/`. Workflow agents that edit are invisible to the writer cap.
6. **Minor: `worker_facts`, `.claude/hooks/stop/wl_liveness.py:625`.** It hard-codes `15` instead of `BG_STALE_MIN`, so the two can drift apart.

### e. Hook fragility (a mid-edit NameError on every stop)

**Verified**
- `.claude/hooks/stop/worklist.py:95-115` catches only **import-time** failures into `_BROKEN`. `:2125-2141` then blocks.
- A NameError inside `run_stop` is a **runtime** failure. It reaches the `__main__` handler (`.claude/hooks/stop/worklist.py:2147-2170`), which blocks with the traceback on every stop and tells the session to fix it.
- The live hook runs straight from the working tree (`.claude/settings.json:98-107`). A writer's half-finished edit is therefore every session's Stop hook.
- The "fail closed on crash" rule is right. The defect is that no working version exists to fail *to*.

**Design: last-known-good plus a post-edit check**

1. **LKG snapshot** (new module `wl_lkg.py`).
   - At the end of every stop that did not crash (the normal `emit` or `SystemExit(0)` paths), hash the module set: `worklist.py`, `worklist_messages.py` and `wl_*.py`.
   - If the digest is new, copy the set to `$TMPDIR/claude-worklist/.lkg/<digest>/` and point `.lkg/current` at it. This costs one hash per stop and one copy per change.
   - When there is no LKG yet, fall back to `git archive HEAD .claude/hooks/stop`.
2. **Fallback on failure.** Both `_BROKEN` and the `__main__` crash handler re-run the stop as `python3 .lkg/current/worklist.py`, with the **raw stdin bytes buffered** by `_read_event` and `WORKLIST_LKG_CHILD=1` set as a recursion guard.
   - The LKG verdict is emitted with one prefixed line: `live hook crashed (NameError at wl_checks.py:N); this verdict is from the last-known-good snapshot <digest8> (<age>)`.
   - It is still a full battery, so it is not an escape hatch.
   - If the LKG also fails, or the live tree has crashed for 30 min or more **and** no file in `.claude/hooks/stop/` changed in the last 10 min (nobody is mid-edit), the current crash block fires as before.
3. **Post-edit check** (a new PostToolUse member, `hooks/context/stop-hook-edit-check.py`).
   - On Edit, Write or MultiEdit of `.claude/hooks/stop/*.py`, run `ruff check --select F821,F811,E999 <file>`. Ruff is at `~/.local/bin/ruff`, and `python_lint.py` already depends on it.
   - Then run a subprocess import smoke test of the stop directory.
   - Report any failure to the *writer* immediately, in its own turn. It warns and never blocks, like `warn_hook_change.py`.

### f. Judge demands that arrive one at a time after a fix

**Verified**
- All three questions are already asked **in one judge call**: `regression_gate`, `class_sweep` and `proof_obligation` are appended together (`.claude/hooks/stop/wl_judge.py:731-745`, `:769`).
- `apply_order` *appends* both a fired sweep and a fired proof onto the verdict (`.claude/hooks/stop/wl_judge.py:864-880`, `.claude/hooks/stop/wl_rules.py:274-288`).
- **Serialization happens in rendering.** When the regression gate blocks, `.claude/hooks/stop/wl_checks.py:4252-4261` emits `payload` alone and drops `verdict["reason"]` and `["next_action"]`, which already carry the sweep and proof orders. Those survive only as `Demand` markers, which come back as "followup" questions on a later judged stop (`wl_classsweep.apply_verdict`, `:463-495`).
- `brave_default` is deliberately skipped on fix stops (`.claude/hooks/stop/wl_judge.py:752-755`) and whenever a sweep fired (`:881-887`, "ONE ORDER PER STOP").
- The whole judge is unreachable while static violations exist (1.3). Fix-sets accumulate and are then judged in one burst.

**Fix.** On a regression-gate block, render every obligation the same verdict fired as one numbered block (gate, sweep, proof). The judge call and the demand markers stay unchanged, so this is a rendering change only.

---

## PART 3. The plan

Order: root causes first. Deletions and automation come before anything new.

### Constraint: files owned by the messaging-removal writers (do not touch until their step 13 commit lands)

The source is `agent/plans/PLAN-remove-cross-session-messaging.md` §1 and §3.

**Writer A (stop core)**
- `.claude/hooks/stop/`: `worklist.py`, `wl_checks.py`, `wl_store.py`, `wl_core.py`, `wl_liveness.py`, `wl_checklist.py`, `wl_report.py`, `wl_profile.py`, `wl_epic.py`, `worklist_messages.py`, `test-always-tier.py`, `test-teammate-idle.py`, `wl_roster.py` (their step 11). `wl_requests.py` and `wl_wait.py` are deleted.
- `.claude/rediacc_hooks/tests/`: `wlfix.py`, `test_wl_requests.py` (deleted), `test_wl_message_catalogue.py` (renamed), `test_wl_waiter_controls.py`, `test_wl_background_waits.py`, `test_wl_report_inbox.py`, `test_wl_identity.py`, `test_wl_ci_queue_and_mail.py`, `test_wl_checklists.py`, `test_wl_report_queue.py`, `test_wl_guide_and_deferrals.py`, `test_wl_agent_docs_and_focus.py`, `test_wl_priority_ladder.py`, `test_wl_idle_and_evidence.py`, `test_wl_drift_loops_freshness.py`, `test_wl_core_blocking.py`, `test_wl_roster.py`, `test_wl_messaging_removed.py` (new).

**Writer B (wiring and periphery)**
- `.claude/rediacc_hooks/lifecycle.py`, `.claude/settings.json`, `.claude/rediacc_hooks/hookio.py`, `.claude/rediacc_hooks/guards/*.py` (the ORDER sweep covers 31 files), `.claude/oracles/pre-bash/*`, `.claude/rediacc_hooks/tests/hookcases.py`, `.claude/hooks/trapguard/dispatch.py`.
- `.ci/scripts/ci/ci-trace.py`, `.ci/rediacc_ci/review/standing_orders_brief.py` with its test and goldens, `.ci/rediacc_ci/quality/hook_integrity.py`.
- `docs/agent-reference/{TRAPS.md,ci-gates.md,worklist-v10-brief.md}`, `.claude/skills/{migrate,ci-watch}/SKILL.md`.
- `.ci/config/{env-manifest,python-env-registry,prose-style-baseline,python-types-baseline}.json`, `.ci/policy/worklist-env-registry.json`, `scripts/data/{hook-inventory-baseline.json,doc-registry-preport.json,doc-registry.md}`.

**Consequence.** Nearly every file in this plan is on that list. Only **new files** may start now (Phase 1). Everything that edits an existing file waits for the messaging commit (Phase 2).

### Prioritized changes

Each change lists the files it touches and a **control test** (the test that must fail without the change), plus its paired inverse where one is needed. Test files are new unless marked.

**P0: make the hook deliver what it already computes**

- [ ] **P0.1 Name the rotating tail instead of counting it.** Replace the `R_FOCUS_MORE` count with an `R_ROTATING_COLLAPSED` list, one line per outstanding rotating check (`key: first line[:150]`, ladder order). Keep exactly one check quoted in full. Named checks do not spend display latches: only full quotes spend them, and `spend_display_latches` stays unchanged.
  - Files: `wl_checks.py` (block render, `:3821-3840`), `worklist_messages.py`.
  - Control, in `test_wl_continuity_surface.py`: 3 rotating violations (`brief`, `docs-drift`, `pr-stale`). The **first** block contains the first line of all three. Today it contains one plus "2 more check(s)".
  - Inverse: the invariant collapse is unchanged (`test_232` still passes).
- [ ] **P0.2 Advisory digest on blocked stops.** Replace the bare `N_OUTQ_BLOCKED` count with at most 6 lines of `key: first line`, highest priority first.
  - An entry whose whole text is one line (every sticky `reg-settled`, `claim-check`, `audit`, `archived` or `defer-settle` fact, and the `ladder` ping) is **delivered and removed** by the digest.
  - Multi-line bodies stay queued until a clean stop.
  - Files: `wl_checks.py` (`:3734-3738`, a helper beside `outq_drain`), `worklist_messages.py`.
  - Control: a blocked stop with a queued sticky `ladder` ping and a `plan-tasks` body. The block reason contains the ping text and `plan-tasks:`. Today it contains only "N advisory section(s) are queued".
  - Second control: the next blocked stop no longer shows the ping (it was delivered).
- [ ] **P0.3 Delete the peer-only producers.** Remove `agent-peers` (`:3213-3238`), `others` (`:4417-4424`) and `others-items` (`:4449-4458`). Under the single-terminal ruling they have no reader. Keep `orphans` and `handoff`, and let them ride the digest.
  - Files: `wl_checks.py`, `worklist_messages.py` (`N_AGENT_PEERS` and others), `test_wl_state_document.py` (the 29k cases are deleted or rewritten).
  - Control: a peer STATE directory exists and the outq holds no `agent-peers` key. Today it does (`test_29k` asserts that it does).
- [ ] **P0.4 Move the admission Tier R prefilter and record above the block exit,** so the docstring's "always" is true. The model call stays on the judge path.
  - Files: `wl_checks.py` (move `:3880-3885` above the cadence and block section).
  - Control: a blocked stop whose last message says `I clobbered the file` produces a Tier R row. Today no row is written.
- [ ] **P0.5 Give the self-repair order an outlet, and let the hint line ride blocks.**
  - Change the `R_BLOCK_FOCUS` footer to: `...you are the session that fixes it, or, if it cannot be fixed this turn, worklist.py --hint-propose <me> '<lesson>' SOURCE: <check-key>`.
  - Allow the rotating hint line on a block at most once per 30 min (a ledger stamp in `state_doc["hints"]`).
  - Files: `wl_checks.py`, `worklist_messages.py`.
  - Control: the first block of a session contains `--hint-propose`. Today it does not.
  - Inverse: a second block inside 30 min carries no hint line.

**P1: delete or automate the churn checks**

- [ ] **P1.1 Delete the `brief` vadd and let the hook stamp the brief.** The hook stamps it on each stop from the `## Next action` lead line, else from the newest `[>]` item. `missing` is filled the same way.
  - Files: `wl_checks.py` (`:2708-2726`), `wl_store.py` (an `auto_brief` writer beside `read_briefs`), `worklist_messages.py` (`V_BRIEF` goes), `test_wl_core_blocking.py` (edit tests 04 and 05).
  - Control: a fresh session with no brief. After one stop there is no `brief` violation, and `.sessions` holds its entry. Today it blocks with "session brief is missing".
- [ ] **P1.2 Key STATE.md staleness on judgment facts only.**
  - Drop `HEAD` and task statuses from the staleness trigger.
  - Stale means: the 15-min age has passed **and** every `#id` named under `## Next action` has left the open state, or the section names no `#id` and the owned item set changed.
  - `handle_post_compact` renders a computed facts block beside the body (guide slice, roster summary, HEAD and branch).
  - Files: `wl_store.py` (`state_world_sig`, `agent_state_state`), `wl_checks.py` (`handle_post_compact`).
  - Control: a document 16 min old, then a commit that moves HEAD. No `agent-state` violation. Today: `stale`.
  - Inverse: tick the item named in `## Next action`. `agent-state` fires.
- [ ] **P1.3 Delete the Stop `docs-drift` vadd.** The SessionStart note stays.
  - Files: `wl_checks.py` (`:3333-3335`), `worklist_messages.py` (`V_DOCS_DRIFT`), `test_wl_drift_loops_freshness.py`.
  - Control: 11 commits touching `.claude` with docs untouched. No `docs-drift`. Today: blocked.
  - Inverse: SessionStart still says "DRIFTED by 11 commits".
- [ ] **P1.4 Let evidence answer the status ping** (operator ruling needed; the default is to implement).
  - Each stop, append an automatic `status` event (`by: hook`) for every supervised live agent whose transcript grew since the last stop or has a tool call in flight.
  - `roster-status` then fires only when no evidence arrived within 20 min, which is the same condition as `roster-silent`. Merge the two keys.
  - Files: `wl_roster.py`, `wl_checks.py` (`:2389-2402`), `worklist_messages.py`, `test-always-tier.py`, `test_wl_roster.py`.
  - Control: a leased agent whose transcript grows every stop, and whose last `--status` is 25 min old. No `roster-status`. Today: `test_r5` shape, due.
  - Inverse: no growth for 21 min gives `roster-silent`.
- [ ] **P1.5 Auto-read reports the lead already received.**
  - Add `wl_report.delivered_ids(transcript_path, since_offset)`, an incremental scan for `<task-id>X</task-id>...<status>completed</status>` with a non-empty `<result>`.
  - `unread()` excludes those agents' reports and appends a `read` event with `by: <me>` and `via: task-notification`.
  - Files: `wl_report.py`, `wl_checks.py` (`:3253-3256`), `test_wl_report_inbox.py`.
  - Control: a report captured for agent X, plus a planted notification for X in the lead transcript. No `unread-reports`. Today it fires.
  - Inverse: without the notification it still fires. A `[SILENT]` report still fires.

**P1: liveness siblings (all fail today)**

- [ ] **P1.6 `all_waits_live` accepts a workflow whose `facts` stream is fresh.**
  - Files: `.claude/hooks/stop/wl_liveness.py:300-314`, `test_wl_background_waits.py`.
  - Control: a pure wait on one live workflow with fresh agent transcripts, with `bgwait` due. No `bg-report`.
  - Inverse: stale agent transcripts do give `bg-report`.
- [ ] **P1.7 A shell waiter is not silent.** In `roster()`, exclude `waiters` from `silent` and satisfy `status_due` for a waiter whose shell is running. `status_verb` labels it `WAITING on shell <id>` rather than SILENT.
  - Files: `.claude/hooks/stop/wl_roster.py:527-537,768`, `test_wl_roster.py`.
  - Control: extend `test_r3d` with `assert W4 not in v["silent"]` (fails today; W4's transcript is 30 min quiet).
  - Inverse: `test_r3e`'s gone shell still reads as dead.
- [ ] **P1.8 Waiters count as live worker ids.** Add `wl_liveness.live_worker_ids(event, live_bg, cwd, sid)`, the union of `live_bg` ids and `wl_roster.shell_waiters`. Use it at `.claude/hooks/stop/wl_checks.py:1939` and `:2261`.
  - Files: `wl_liveness.py`, `wl_checks.py`.
  - Control: an **expired** lease on waiter W4 whose shell is running. The item stays in-flight and does not enter `open-items`.
- [ ] **P1.9 Roster covers leases on workflow ids through `workflow_stream`,** and `load_metas` also reads `subagents/workflows/*/agent-*.meta.json` so workflow writers count toward the cap.
  - Files: `.claude/hooks/stop/wl_roster.py:89-120,470-482`, `test_wl_roster.py`.
  - Control: `worker:wf_x` on a live, fresh workflow is `covered`, not `unknown`.

**P2: lease continuity**

- [ ] **P2.1 `worker:lead`.** Covered while any session background task is live, auto-renewed by the hook while covered, capped at 3, fails closed.
  - Files: `worklist.py` (`--lease`, `:1025-1042`), `wl_store.py` (`classify_items`), `wl_roster.py` (skip from writer accounting), new `wl_leasehelp.py`, `test_wl_leases.py`.
  - Control: an item on `worker:lead` with one live shell stays in-flight across a shell replacement **without a new `--lease`**. Today the lease is refused ("must name its worker (worker:<background-task-id>)").
  - Inverse: with no live task the item is open.
- [ ] **P2.2 Auto-lease from `#id` in a live agent's prompt or a shell's description,** at stop time.
  - Files: `wl_leasehelp.py`, `wl_checks.py` (one call after the roster), `test_wl_leases.py`.
  - Control: a new agent whose prompt names `#abcd1234` (open) holds the lease after one stop.
  - Inverse: an id owned by a peer is not leased.
- [ ] **P2.3 `--lease` with an id list, and `--relay <me> <old> <new>`.**
  - Files: `worklist.py`, `worklist_messages.py` (`USAGE`), `test_wl_identity.py` (the 185 verb set).
  - Control: `--relay` moves 3 leases in one call.
- [ ] **P2.4 `BLOCKED_BY:#id`.**
  - Files: `wl_core.py` (the token), `wl_store.py` (fold and classify), `worklist.py` (validation on `--add` and `--update`), `test_wl_leases.py`.
  - Control: an open item blocked by an open item of the same session does not appear in `open-items` or `idle-stall`, while its blocker does. Ticking the blocker queues "unblocked #y" and the item becomes open.
  - Inverse: a cycle and an unknown blocker are refused with rc 2.

**P2: fragility**

- [ ] **P2.5 LKG snapshot and fallback.**
  - Files: new `wl_lkg.py`, `worklist.py` (buffer the raw stdin in `_read_event`; the `_BROKEN` block at `:2125`; `__main__` at `:2147`), new `test_wl_lkg.py`. The test copies `STOP_DIR` to a temp directory, runs a clean stop there to seed the LKG, plants `undefined_name()` in `run_stop`, and stops again.
  - Control: the verdict names the snapshot and the battery's checks. Today: "Stop hook CRASHED".
  - Inverses: with no LKG and no git, the crash block is unchanged. With the snapshot also broken, the crash block is unchanged.
- [ ] **P2.6 Post-edit check for the stop modules.**
  - Files: new `.claude/hooks/context/stop-hook-edit-check.py`, `lifecycle.py` (the post-tool member), `settings.json` (the post-tool timeout sum), a `test_settings_collapse.py` update, and `scripts/data/hook-inventory-baseline.json` if the counter requires it.
  - Control: an Edit payload on a copy containing an F821 undefined name. The warning text names the line.
  - Inverse: a clean file produces no output.

**P2: judge rendering**

- [ ] **P2.7 One block for every fired fix obligation.**
  - Files: `wl_checks.py` (`:4252-4261`), `worklist_messages.py`, `test_wl_regression_gate.py` (edited).
  - Control: a stubbed verdict with `regression_gate` blocking **and** `class_sweep` fired. The block text contains both the gate instruction and the sweep's `search`. Today it contains only the gate payload.

### Writer split (2 disjoint sets)

**Phase 1** (start now: new files only, no collision)
- **Writer Y:** `wl_lkg.py`, `wl_leasehelp.py` (pure parsers for `#id` and `BLOCKED_BY`, and the `worker:lead` coverage predicate), `.claude/hooks/context/stop-hook-edit-check.py`, `test_wl_lkg.py` (in-process unit tests only), `test_wl_leases.py` (unit tests for the helpers only).
- **Writer X:** idle in this phase, or drafts `test_wl_continuity_surface.py` as in-process tests of the pure render helpers it will add. It holds that file only.

**Phase 2** (gate: the messaging-removal commit, their step 13, has landed and `git status .claude/` is clean)

| Writer X, the stop surface | Writer Y, state, liveness, leases and robustness |
|---|---|
| `wl_checks.py`, `worklist_messages.py`, `test-always-tier.py` | `wl_store.py`, `wl_core.py`, `wl_liveness.py`, `wl_roster.py`, `wl_report.py`, `worklist.py`, `wl_lkg.py`, `wl_leasehelp.py` |
| Tests: `test_wl_continuity_surface.py`, `test_wl_report_queue.py`, `test_wl_advisories_rotation.py`, `test_wl_priority_ladder.py`, `test_wl_core_blocking.py`, `test_wl_drift_loops_freshness.py`, `test_wl_state_document.py`, `test_wl_regression_gate.py` | Tests: `test_wl_roster.py`, `test_wl_background_waits.py`, `test_wl_report_inbox.py`, `test_wl_identity.py`, `test_wl_leases.py`, `test_wl_lkg.py`, `test_settings_collapse.py` |
| Items: P0.1 to P0.5, P1.3, and the wl_checks halves of P1.1, P1.2, P1.4, P1.5, P1.8 and P2.2, plus P2.7 | Items: the helper halves of P1.1, P1.2, P1.4 and P1.5, plus P1.6, P1.7, P1.9, P2.1, P2.3 to P2.6, the `lifecycle.py` and `settings.json` edit, and **all registries** (`.ci/config/*.json`, `.ci/policy/worklist-env-registry.json`, `scripts/data/*`), run after X is green |

**Sequencing inside Phase 2**
- Y lands each helper first: `live_worker_ids`, `auto_brief`, `delivered_ids`, the new staleness predicate, auto-status.
- X then makes the one-line call-site change in `wl_checks.py`.
- X adds **no** environment reads. Env-var drains for deleted checks (`WORKLIST_DOCS_DRIFT_MAX`, and `WORKLIST_BRIEF_STALE_MIN` if unused) are done by Y after X is green.
- `wl_roster.py` stays sealed: no environment reads, literals only (`test_r6b`).

### Gates to run

```
python3 -m pytest .claude/rediacc_hooks/tests -q -n auto
python3 .claude/hooks/stop/test-always-tier.py        # ladder keys after roster-status merge / brief & docs-drift deletion
python3 .claude/hooks/stop/test-popup.py
python3 .claude/hooks/stop/test-teammate-idle.py
python3 .claude/hooks/stop/test-planfile.py && python3 .claude/hooks/stop/test-backlog.py   # outq consumers
npm run check:ci-pytest
npm run check:ci-hook-integrity
npm run check:ci-hooks-resolvable
npm run check:ci-dead-python          # deleted messages/helpers
npm run check:ci-env-manifest
npm run check:ci-python-env-registry
npm run check:ci-worklist-env-registry  # sealed wl_roster stays env-free
npm run check:ci-prose-style
npm run check:ci-python-types
npm run check:ci-python-lint
npm run check:ci-judged-rule-wiring   # P2.7 touches judged-rule rendering only; hash must not move
npm run check:ci-shape-duplication
npm run ci:quick                      # then full `npm run ci` before push
```

**Live smoke check** (never plant a defect in the live tree):
- After P0.1 and P0.2, the lead's next blocked stop names every rotating check and shows the digest.
- After P2.5, the LKG directory `$TMPDIR/claude-worklist/.lkg/current` exists and matches the live digest.

### Critical Files for Implementation
- /home/developer/console/.claude/hooks/stop/wl_checks.py
- /home/developer/console/.claude/hooks/stop/wl_roster.py
- /home/developer/console/.claude/hooks/stop/wl_liveness.py
- /home/developer/console/.claude/hooks/stop/wl_store.py
- /home/developer/console/.claude/hooks/stop/worklist.py
