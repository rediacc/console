# PLAN: stand the stop hook down while every writer slot is live

Status: done
Owner: d778be9d
First-Seen: 2026-09-24
Depends-On: no-dep -- edits .claude/hooks/stop/{wl_checks,wl_roster,wl_liveness,worklist_messages}.py and one new test; no open plan owns those regions
Worklist: #064a3fd1

**Operator order, 2026-09-24:** "the stop hook should not be invoked (or should skip the order) when writer slots are full! There could be exceptions like 2% compaction etc."

- [x] T1 Implement sections 1-7 below in one pass (lead inline or one writer), with tests/test_wl_cap_wait.py and the mutation controls.
  Done: commit d393a4e8c; test_wl_cap_wait.py 16 passed (2026-09-25 re-run), 5 mutation controls.
    (ticked) 2026-09-26T16:32:02Z by d778be9d: retroactive record: closed by b5a4e3a13 (2026-09-25) docs(plans): land the _done copy of the cap-saturated-wait plan and it -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites

# Plan: a cap-saturated wait state for the Stop hook (read-only design)

## 0. What the code does now, and two corrections to the brief

The blocks the lead hit come from four places:

- **(a) The quiet ladder fires on `worker:queue` items. This is a bug of its own.** `wl_liveness.ladder` skips only workers that have a subagent meta (`.claude/hooks/stop/wl_liveness.py:685-698`). `queue` has no meta, so a queue item falls through. A lease written by the CLI stores `worker_verified=False`: the id `queue` is never in the harness list (`.claude/hooks/stop/worklist.py:1170-1178`). The item therefore goes to `teammate_state("queue")`, gets "unverifiable" (`.claude/hooks/stop/wl_liveness.py:454-456`), and drops into the plain age rungs 45/90/120 (`.claude/hooks/stop/wl_liveness.py:782-789`, constants at `:46-48`). Those become `ladder-investigate` and `ladder-resolve` blocks at `.claude/hooks/stop/wl_checks.py:3687-3713`. The roster already treats the queue as "bounded by its own lease expiry" (`.claude/hooks/stop/wl_roster.py:628`), so the ladder should never see it.
- **(b) The judge blocks.** The lead's block log `/tmp/claude-worklist/home_developer_console.blocklog-d778be9d.jsonl` shows 11 of its last 15 blocks with `key: judge` and `sweep`/`proof` flags. The judge runs whenever `something_remains` (`.claude/hooks/stop/wl_checks.py:4211`). Its continue exit is at `:4642`, and it prints `R_JUDGE_CONTINUE` ("Do the next action, then stop", `.claude/hooks/stop/worklist_messages.py:1369-1373`).
- **(c) and (d) are the roster's own keys.** `queue-slot` (`.claude/hooks/stop/wl_checks.py:2703-2714`) and `roster-dead` (`:2697-2702`).
- **Correction 1: fresh queue leases do not keep `_in_pure_wait` from applying.** `classify_items` puts a fresh lease in `in_flight`, not `open_items` (`.claude/hooks/stop/wl_store.py:1312-1313`). Only an **expired** queue lease fails closed into an open item (`:1317-1321`, mirrored in `.claude/hooks/stop/wl_roster.py:518-519`). That happens at the latest 120 minutes after leasing (`.claude/hooks/stop/wl_core.py:46`). A queue that sits longer than 2 hours breaks the wait; step 2 closes that.
- **Correction 2: the babysitter does count toward the cap.** The lead's own `.lastevent-d778be9d.json` lists it as `type: subagent, agent_type: pr-babysitter`. The roster counts only `type == "subagent"` rows (`.claude/hooks/stop/wl_roster.py:440-441`), so a teammate-type babysitter would not count; this one does.

## 1. The predicate: `wl_roster.cap_saturated_wait`

It goes in **`/home/developer/console/.claude/hooks/stop/wl_roster.py`**, next to `ROSTER_SUPPRESSES` (`:49`).

- That module owns `WRITER_CAP` and the verdict.
- It is sealed: no environment reads, per `.claude/rediacc_hooks/tests/test_wl_roster.py:614-629` and `.ci/policy/worklist-env-registry.json`.
- The function must be pure. Every input is passed in by the caller.

```python
def cap_saturated_wait(verdict, open_items, actionable_tasks):
    return bool(verdict) and not verdict.get("blind") \
        and len(verdict.get("writers") or ()) >= WRITER_CAP \
        and not open_items and not actionable_tasks
```

How each condition maps to data that already exists:

- **Live writers are verified, not claimed.** `verdict["writers"]` holds only agents that the harness lists **and** whose transcript is not proven finished (`.claude/hooks/stop/wl_roster.py:438-464`). Each is a writer by type or by edit evidence (`:480`, `:487-491`). The verdict is `_roster` at `.claude/hooks/stop/wl_checks.py:2237-2241`.
  - `>=` includes an over-cap roster. Its `roster-cap` block is kept (section 3).
  - A writer that is live but silent stays in the count. The kept `roster-silent` key is what answers it.
- **No plain `[ ]` item.** Use `open_items` from `S.classify_items` (`.claude/hooks/stop/wl_checks.py:2200`). It already contains every state that is not allowed here:
  - plain `[ ]` (`.claude/hooks/stop/wl_store.py:1290-1291`);
  - expired or malformed leases (`:1317-1321`);
  - a `worker:lead` lease with nothing live (`:1307-1310`).
  - Items waiting on `BLOCKED_BY` are left out on purpose (`:1288-1289`), which covers "blocked on something external".
- **The other disallowed item states surface as kept keys, not as a predicate term:**
  - leased to a finished worker: `roster-dead`;
  - an unleased writer: `roster-unleased`;
  - an expired DEFAULT: `defer-expired`;
  - a `[?]` without a DEFAULT: `undefaulted`.
  - So "predicate true and no kept key fired" is exactly the operator's condition "every item is in an allowed state". It also keeps any exception as one focused block instead of the whole battery.
- **No harness task the session could do now.** Call `C.actionable_tasks(session_id, event.get("transcript_path"))` (`.claude/hooks/stop/wl_core.py:614`). Reuse `_bg_actionable` (`.claude/hooks/stop/wl_checks.py:2492`) when the pure-wait branch already computed it.

**Where to call it.** In `wl_checks.py`, directly after the pure-wait block (after `:2538`) and before the stuck detector (`:2567`):

```python
_in_cap_wait = False
with contextlib.suppress(Exception):
    _in_cap_wait = wl_roster.cap_saturated_wait(_roster, open_items, _bg_actionable if _in_pure_wait else C.actionable_tasks(...))
```

## 2. Steps in order (one writer, one pass)

1. **Fix the ladder at its source.**
   - File: `.claude/hooks/stop/wl_liveness.py:682-698`.
   - Inside the existing `try` that imports `wl_roster`, bind `queue_w = wl_roster.QUEUE_WORKER`. In the `except` branch, fall back to the literal `"queue"`.
   - Change line `:697` to `if wid and (wid in roster_ids or wid == queue_w): continue`.
   - This runs whether or not the cap is full. When a slot frees, `queue-slot` names the item. When the lease expires, the item fails closed to open.
   - This alone removes blocker (a), and also the false `ladder-gone` that a `worker_verified=True` queue lease would trigger (`.claude/hooks/stop/wl_liveness.py:701`).
2. **Renew queue leases while the cap is full (recommended; the operator may veto it).**
   - Model it on the existing renewal of the covering lead lease (`.claude/hooks/stop/wl_checks.py:2203-2218`).
   - Move the `_roster` computation (`:2237-2241`) above `classify_items` (`:2200`). It reads only the event, the fold and `state_doc`, never the classify outputs.
   - When `len(_roster["writers"]) >= WRITER_CAP`, renew each owned `[>]` lease whose worker is `QUEUE_WORKER`, that is fresh or expired, and that has less than `wl_leasehelp.LEAD_RENEW_BELOW_MIN` (30) minutes left. Skip any lease whose note carries a `HOLD_FOR` (check with `wl_roster.hold_target(r)`), so R.5's bounded reservation keeps its expiry.
   - Renew with `S.lease_item(worklist, me8, id, C.stamp_ahead(C.MAX_LEASE_MIN)[:16]+"Z", "queue", "auto-renew: cap full", worker_verified=False)`.
   - If anything was renewed, reload the fold and recompute the roster, then classify.
   - Why: without this, a queue that waits longer than 120 minutes turns into open items and ends the saturated state.
3. **Hoist `expired`.** Move the list at `.claude/hooks/stop/wl_checks.py:2878-2886` above the pure-wait block and reuse it at `:2483-2487` and `:2887`. This is a pure refactor.
4. **Compute `_in_cap_wait`** as in section 1. Then pass `supervised=_supervised or _in_cap_wait` to `stuck_rounds` (`:2567-2575`). Without this, the 3x overrun, which counts without firing while saturated, fires on the first stop after saturation ends (`.claude/hooks/stop/wl_checks.py:116-164`).
5. **Skip paid work that would be thrown away.**
   - Guard `planfid_check` with `and not _in_cap_wait` (`:3810`). It is in the always tier because it pays for a model call (I1).
   - Guard the `audit_batch` build with `and not _in_cap_wait` (`:4149`).
6. **Apply the suppression filter.** Place it immediately after the HONEST block (`:3867-3902`) and before `if bgwait_due:` (`:3903`):
   - `violations = [v for v in violations if wl_roster.cap_wait_keeps(v[0], v[1], compaction_due)]`;
   - then repeat the stand-down of `bgwait_due` from `:3890-3891`;
   - then, if `violations` is empty, put `N_CAP_WAIT` at the head of `guide` (replacing `_honest`, not added to it), set `guide_empty=False`, and set `state_doc["capwait"] = {"at": now, "dropped": [keys]}` for later audit.
7. **Skip the judge.**
   - Change `:4211` to `if (something_remains or reg_signals) and not wl_judge.JUDGE_DISABLED and not _in_cap_wait:`.
   - Also change the admission path (`:4179`) so it still runs when the main judge is skipped: `...and not wl_judge.JUDGE_DISABLED and not _in_cap_wait)`. An admission of breakage must never go unseen.
   - Unsettled regression fix-sets are not lost. The marker advances only when a fix-set settles or has no ids (`:2385-2403`), so the next stop without saturation asks again.

## 3. What is dropped and what still blocks

Put a **keep-list** in `wl_roster.py` beside `ROSTER_SUPPRESSES`: `CAP_WAIT_KEEPS` plus `cap_wait_keeps(key, always, compaction_due)`. A keep-list follows "should not be invoked": a check added later defaults to standing down, which matches `check_tier`'s rule that unknown keys are hygiene (`.claude/hooks/stop/wl_checks.py:1974`).

### Dropped in the cap-saturated wait

| Check | Key(s) | Where it is added |
|---|---|---|
| 45/90/120 ladder (age-only rungs) | `ladder-investigate`, `ladder-resolve` | `.claude/hooks/stop/wl_checks.py:3687-3692`, `:3708-3713` |
| The 45-minute ping | outq entry `ladder` (not a block) | `.claude/hooks/stop/wl_checks.py:2591-2601`; for queue items it is gone after step 1 |
| Judge consult, including "Do the next action", SWEEP THE CLASS, PROOF OBLIGATION, the reggate, defer-audit and shapedup | none (step 7) | `.claude/hooks/stop/wl_checks.py:4211-4717`; exits at `:4359`, `:4451`, `:4568`, `:4584`, `:4622`, `:4642`, `:4682` |
| Stuck detector | `stuck` | `.claude/hooks/stop/wl_checks.py:2795-2806` |
| Idle-stall, solo-grind, sweep-moment | `idle-stall`, `solo-grind`, `sweep-moment` | `.claude/hooks/stop/wl_checks.py:2824-2831`, `:3451-3454`, `:2867-2868` |
| 15-minute background check-in | `bg-report` | `.claude/hooks/stop/wl_checks.py:2767-2794` |
| Report shape | `no-remaining`, `out-of-sync`, `unstated`, `mislabelled`, `unconfirmed`, `uncited` | `.claude/hooks/stop/wl_checks.py:3839-3849`, `:3822-3827`, `:3804-3807`, `:3636-3637`, `:3762-3763` |
| STATE.md (except the compaction case below) | `agent-state` (every verdict, not only `stale`), `agent-absent` | `.claude/hooks/stop/wl_checks.py:3456-3476`, `:3488-3493` |
| Intent, plan and checklist freshness | `intent-expired`, `plan-drift`, `plan-adopted`, `plan-unimplemented`, `plan-fidelity`, `cl-producing`, `cl-flip`, `cl-waves` | `.claude/hooks/stop/wl_checks.py:3000-3031`, `:3055-3131`, `:3601` |
| Mission items the writers already own | `pr-finish` (only when `always` is false), `ci-red`, `review-red`, `ci-waiting` | PR/CI section around `:3140-3380`; `ci-waiting` at `:3758` |
| Git and cron hygiene | `stale-local`, `diverged`, `pr-stale`, `submodule`, `loop-died`, `broken-schedule`, `many-work-crons`, `bg-orphan`, `idle` | various |
| External readers that are not the hook itself | `ci-unreadable`, `review-unreadable`, `pr-unreadable` | `:3228`, `:3293`, `:3191` |
| Pending ask | `pending-ask` | `:2850-2851`. Judgment call: ending the turn is the legitimate outcome in this state. |

### Kept: these still block when the cap is saturated

- **Compaction near and STATE.md not current.**
  - Keep `agent-state` and `agent-absent` exactly when `compaction_due` is true.
  - Definition: `compaction_due = late_band and astate in ("missing","thin","bloated","aimless","stale","waitled","no-dir")`. `astate` comes from `:2443-2449`, after the live-intent override at `:3442-3443`.
  - `late_band` is read by a new helper in `wl_checks`, `_ctx_late_band(session_id)`: lazily `import wl_retro`, then `cb = wl_retro.ctx()` (`.claude/hooks/stop/wl_retro.py:40-49`), then `int(cb.load_state(session_id).get("band", -1)) >=` the index of `"late"` in `cb.BANDS`.
  - The late band is 0.98 of the threshold, i.e. about 2% until auto-compact (`.claude/hooks/context/ctx_budget.py:66`). `band-notice.py` writes `st["band"]` at `:265`, re-seats it at `:207`, and resets it after each compaction (`:211-220`).
  - If the context module cannot be loaded (for example in an LKG snapshot, per `.claude/hooks/stop/wl_retro.py:11`), return False. The PreCompact snapshot covers that case.
  - Append a one-line note `M.N_CAP_WAIT_COMPACTION` to the agent-state text so the reader sees why this one was kept.
- **A writer found dead, or a lease on a finished worker.**
  - A writer proven finished drops out of `writers` (`.claude/hooks/stop/wl_roster.py:448-454`). The cap is then below 4, the predicate is false, and `queue-slot` fires.
  - `roster-dead` (`.claude/hooks/stop/wl_checks.py:2697`) and `roster-unleased` (`:2691`) are kept, and so are `ladder-gone` and `ladder-idle` (`:3693-3707`).
- **Expired DEFAULT:** `defer-expired` (`:2887-2903`), plus `undefaulted` (`:2871-2876`).
- **A free slot with queued work:** `queue-slot` (`:2703-2714`). While saturated this cannot fire, because `free = 0` (`.claude/hooks/stop/wl_roster.py:542-546`).
- **The rest of the roster:** `roster-cap` (`:2669-2681`) and `roster-silent` (`:2683-2689`).
- **Hook integrity:**
  - `event-unparseable` (`:2807-2808`), `hook-blind` (`:3828-3838`), `cl-shape` (`:3605`);
  - `pr-finish` when `always=True`, i.e. the "THIS IS A HOOK BUG" branch at `:3383-3390`;
  - import failures never reach `run_stop`: they are handled at `.claude/hooks/stop/worklist.py:2297`, crashes fall back to LKG at `:2340-2360`, and the judge-unavailable exit is skipped along with the judge.
- **Checks whose one-shot latch is spent when computed, not when shown (I1).** Hiding their text would use up the latch unseen: `agent-bootstrap` (`:3480-3487`), `agent-pushback:*` and `giveup-claim:*` (`:3406-3432`).
- **Owed and ledger honesty:**
  - `unread-reports` (`:3545-3547`): a finished worker's report;
  - `completion` (`:2946-2959`): a tick without evidence;
  - `adhoc-watch` and `adhoc-watch-broken` (`:3208-3214`): a banned polling loop that is live right now;
  - `found-not-fixed`, `deferred-finding` and `deflected-finding` (`:3764-3788`): the lead's own words abandoning findings; one turn fixes them with `--add` then `--lease … worker:queue`.
- **Secrets and safety.** `run_stop` contains no secret-scanning check: "secret" appears only in comments at `.claude/hooks/stop/wl_checks.py:407`, `:2463` and `:3035`. Secret checks live in the pre-tool and pre-commit guards, which this change does not touch. The admission detector stays (step 7).

## 4. What the allow prints

Add `N_CAP_WAIT` to `worklist_messages.py`, next to `N_ROSTER_HONEST` (`:2500`). One line:

```
CAP-SATURATED WAIT: %d/%d writer slots live (%s); %d item(s) queued behind the cap; %d work-order check(s) stood down until a slot frees. Next status due %s.
```

- Build the `%s` list from `_roster["writers"]` and `_roster["rows"][w]["type"]`, as short ids.
- Take the queued count from `_roster["queued"]`.
- Take the next status time from `wl_roster.next_status_due(_roster)`.

After it come the guide as usual (`:4721`) and `outq_drain` (`:4791`), so advisories still drain.

## 5. How it fits with `_in_pure_wait`: a sibling state, not an extension

Add a sibling state rather than widening pure wait:

- Pure wait (`:2472-2538`) does not look at the roster. It owns the 15-minute check-in for shells and teammates, and its latch reset (`:2534-2538`) relies on its exact entry condition. Widening it would change that clock for waits that have nothing to do with the roster.
- The cap-saturated wait is stronger (judge, report shape, hygiene) and must depend on the verified roster, which pure wait does not read.
- The two combine cleanly. `_in_cap_wait` reuses pure wait's `_bg_actionable`, and it drops `bg-report`.
- The HONEST filter still runs first and is unchanged. The new filter is a stricter second pass placed after it.

## 6. Tests

New file: `/home/developer/console/.claude/rediacc_hooks/tests/test_wl_cap_wait.py`. Run it from the repo root with `.ci/cache/toolchain/uv-tools/pytest/bin/python -m pytest .claude/rediacc_hooks/tests/test_wl_cap_wait.py`.

**How the harness fakes live writers.** Reuse `mk_sub`, `plant_lease`, `W1`-`W4` and `verdict` from `.claude/rediacc_hooks/tests/test_wl_roster.py:47-196`.

- `mk_sub` writes `agent-<id>.meta.json` (fields `agentType`, `spawnDepth`, `parentAgentId`) and `agent-<id>.jsonl` under `<CLAUDE_CONFIG_DIR>/projects/<munged proj>/<SID>/subagents/`.
- It then appends `{"id","type":"subagent","status":"running","agent_type"}` to `fix.bg`, which becomes the event's `background_tasks` (`.claude/rediacc_hooks/tests/wlfix.py:483-492`).
- `last="end_turn"` plus an age makes an agent proven finished.
- `plant_lease(fix, id, "queue", lease_age_min=…)` backdates the store events.
- Harness tasks come from `fix.task(...)`.
- The judge is observed with `capturing_judge` and `prompt_of` (`.claude/rediacc_hooks/tests/test_wl_judge_fixset_scope.py:39-56`) and `wl.runj()`.
- The band state is planted as `<CTX_BAND_STATE_DIR>/deadbeef.json` containing `{"band": 1, ...}`; set `fix.env["CTX_BAND_STATE_DIR"]`, which `.claude/hooks/context/ctx_budget.py:295` honours.

| Test | Setup | Expected |
|---|---|---|
| `c1_saturated_plus_queued_allows` | 4 writers leased; 3 queue leases aged 95 min; a continue-judge shim; run with `runj` | Allow. Output contains `CAP-SATURATED WAIT: 4/4` and `3 item(s) queued`. It does not contain "IN-FLIGHT WORK HAS GONE QUIET" or "Do the next action". `prompt.txt` does not exist (judge never called). |
| `c1_control_three_live_calls_judge` | Same, but W4 is not live | Block with "QUEUED WORK AND A FREE WRITER SLOT", which is also the brief's case "3/4 live plus queued blocks with the free-slot message". |
| `c2_saturated_plus_open_item_blocks` | c1 plus `add_item("- [ ] (deadbeef) x")` | Block, `open-items`. |
| `c3_saturated_compaction_stale_state_blocks` | c1 plus band 1 plus a missing or stale STATE.md | Block with the STATE.md demand and the compaction note. |
| `c3_control_early_band` | band 0 | Allow. |
| `c4_saturated_dead_writer` | Two cases. (i) W4 `end_turn` and aged, so 3 live: block with `queue-slot`. (ii) 4 live plus an item leased to a finished 5th agent | (ii) blocks with "LEASED TO A FINISHED WORKER". |
| `c5_saturated_expired_default_blocks` | Plant a `[?]` whose add event is 130 min old and carries `DEFAULT:` (pattern from `.claude/rediacc_hooks/tests/test_wl_guide_and_deferrals.py:196-209`) | Block with "execute its DEFAULT now". |
| `c6_actionable_task_blocks` | c1 plus a pending task with no blocker | Not a cap wait: the judge runs. |
| `c7_queue_lease_renewed` | Queue lease `until` 10 min ahead | Afterwards the store has a new lease event about 120 min ahead. Control: at 3/4 there is no renewal. |
| `c8_ladder_skips_queue` | Queue lease aged 95 min with the cap not full | Neither "GONE QUIET" nor "worker:queue is NOT in the harness" appears. |
| `c9_keeps_are_real_keys` | Static check | Every key in `CAP_WAIT_KEEPS` has a `vadd` producer in `wl_checks.py`, using the same source scan as `test-always-tier.py`. |

**Mutation controls** follow the house rule of mutating a copy, never the shared tree (`docs/agent-reference/TRAPS.md:288-291`), and reuse the copy pattern of `.claude/rediacc_hooks/tests/test_wl_lkg.py:18-23`:

- Copy the stop and context directories to `fix.base/hooks/{stop,context}`, so `wl_retro`'s `parents[1]/context` lookup still resolves. Set `fix.hook`.
- Parametrize over each exception, removing it in the copy:
  - `roster-dead`, `queue-slot`, `defer-expired` and `open-items` taken out of `CAP_WAIT_KEEPS`, or out of the predicate for `open_items`;
  - `_ctx_late_band` forced to `return False`.
- Run the matching case (c2 to c5) against the copy and assert it now **allows**, which proves that case detects the exception.
- Add one more mutant with `>= WRITER_CAP` changed to `>= 99`, and assert that c1 now blocks.

## 7. Messages, docs and wiring

- **`worklist_messages.py`:** add `N_CAP_WAIT` and `N_CAP_WAIT_COMPACTION`, and register both in `ARITY` in `test_wl_message_catalogue.py`.
- **`CLAUDE.md`:**
  - `:99-102`, rule "A push-back is not a work order": add the exception. When all 4 writer slots are live and every remaining item is leased or queued, the hook stands down; stopping is correct, and the queue drains as slots free.
  - `:78`: add that a `worker:queue` lease never enters the 45/90/120 ladder.
  - `:131`: mention `worker:queue` and the cap-saturated wait.
- **`agent/plans/PLAN-parallel-writer-roster.md`:** add a dated section recording this operator order.
- **Wiring:** nothing new is needed.
  - No new module: `wl_retro` is already in `worklist.py`'s `_MODS` (`:108`).
  - `stop-hook-edit-check.py` derives its coverage from lifecycle `PATTERNS` (its docstring).
  - No new environment variable, so the env registry and the sealed-module test (`.claude/rediacc_hooks/tests/test_wl_roster.py:614`) still pass.

## Still unverified (hypotheses)

- `teammate_state("queue")` was not run to confirm it returns "unverifiable"; this is inferred from `_teammate_meta` finding no meta.
- The keep/drop split for `pending-ask`, `ci-red` and `pr-finish` is a judgment call, not required by the operator's text.

### Critical Files for Implementation
- /home/developer/console/.claude/hooks/stop/wl_checks.py
- /home/developer/console/.claude/hooks/stop/wl_roster.py
- /home/developer/console/.claude/hooks/stop/wl_liveness.py
- /home/developer/console/.claude/hooks/stop/worklist_messages.py
- /home/developer/console/.claude/rediacc_hooks/tests/test_wl_cap_wait.py (new; helpers from test_wl_roster.py and wlfix.py)
