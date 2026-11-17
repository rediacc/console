# PLAN: Stop-hook retro, 2026-11-17 (band early, lead session d778be9d, tracking #9821cec6)

Status: ready
Depends-On: no-dep -- no box waits on another plan
Priority: P1 -- 49 of the 103 judge blocks in this window demanded a full id table, and 37 lead replies restated one
Concurrency: parallel -- R20261117.1 to .4 all edit wl_checks._judge_facts, wl_judge.render_facts and JUDGE_FACTS, so they go on one writer; .5, .6, .7 and .8 are independent of each other
Owns: .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/wl_judge.py, .claude/hooks/stop/worklist_messages.py, .claude/hooks/stop/wl_store.py, .claude/hooks/stop/wl_wake.py, .claude/hooks/stop/wl_worktrees.py, .ci/rediacc_ci/dev/worktree_lease.py, .ci/rediacc_ci/quality/agent_session_archival.py, .claude/hooks/stop/wl_retro.py, .claude/config/effort.json, .claude/rediacc_hooks/tests/test_wl_judge_facts.py, .claude/rediacc_hooks/tests/test_wl_judge_held.py, .claude/rediacc_hooks/tests/test_wl_wake.py, .claude/hooks/stop/test-wl_worktrees.py, .claude/rediacc_hooks/tests/test_wl_archival_due.py, .claude/rediacc_hooks/tests/test_wl_retro.py
First-Seen: 2026-11-17
Owner: d778be9d (adopted from retro aa09ed5219a7c43b7 20261117)
Updated: 2026-11-17

**Scope.** The brief gives lead transcript bytes 1517665944 to 1747609620, which run from 2026-11-10T14:57:50Z to 2026-11-17T19:40Z. The ledgers start later than that:
- The blocklog file was created at 2026-11-14T05:10:30Z.
- The judge log was created at 2026-11-15T17:31:44Z.
- The `/tmp/claude-worklist` directory itself was created at 2026-11-13T19:38Z, so the older rows went with whatever cleared /tmp.

A timestamp bisection puts 2026-11-14T05:01Z at offset 1652847674. The bytes from 1652847674 to the end hold exactly 198 Stop blocks and 103 judge blocks, which match the brief's counts. So every count below is measured on bytes 1652847674 to 1747609620.

Bytes 1517665944 to 1652847674 hold another 146 judge blocks (2026-11-10: 18, 11-11: 49, 11-12: 38, 11-13: 41). No ledger row exists for any of them. They are left out of the counts, and losing them is friction 6. No `PLAN-stop-hook-retro-20261117.md` existed, so numbering starts at R20261117.1. Line numbers refer to the tree at 4dfb2e094b (2026-11-17 20:09 +0100).

Counts for the window:
- **Blocked stops:** 198.
  - Leading keys: judge 103, roster-dead 24, worktree-unlanded 22, bg-orphan 14, wake-timer 9, open-items 5, plan-unimplemented 5, commit-review 4, wisdom-due 4, ladder-gone 2, unread-reports 2.
  - 1 each: idle-capacity, bg-report, giveup-claim:does-not-reproduce, giveup-claim:impossible.
- **Judge verdicts:** 175 rows (103 continue, 72 stop), with 0 sweep demands and 0 proof demands.
- **What the 103 judge blocks were about.** Each block is classified by its reason and next action. A block can fall in more than one class.
  - **Missing ids:** 49. 22 replies were full tables naming 15 or more ids, 17 replies made no work call, and the replies came to 144,613 characters.
  - **W2.x orders on PLAN-ciquick-cpu:** 14. 12 full tables, 5 replies with no work call, 38,214 characters.
  - **"WAKE TIMER: none armed":** 13. 5 replies with no work call, 30,518 characters.
  - **Other:** 33, of which 6 had no work call.
  - **Across all 103 replies:** 37 named 15 or more ids, 30 made no work call (no Agent, Edit, Write, SendMessage, commit, cherry-pick, tick, plan-investigate, npm run, pytest or worktree land before the next block), and they totalled 281,833 characters.
- **Admissions:** 6 rows say a wake timer the lead called armed had already fired: 11-16 05:15:59, 06:40:59, 07:09:56, 07:32:12, 14:35:36 and 11-17 11:42:25.
- **Hint rows matching the brief's friction:** 2026-11-17T18:00:38Z (W2.6), 2026-11-17T19:36:38Z (W2.3/W2.4/W10), 2026-11-17T14:50:38Z and 2026-11-13T10:33:28Z (superseded lease commit), 2026-11-16T01:59:26Z (drill hold).

**Legitimate or already fixed, not ranked:**
- **roster-dead (24):** each named a writer that had finished.
- **bg-orphan (14):** the session's own duplicate or undeclared wait loops, for example 11-16T02:33:08 at offset 1699827140 ("duplicate wait loop: a newer one polls the same [ -s /tmp/leg3-79b7.time ]").
- **open-items, plan-unimplemented and wisdom-due:** each fired on a real state.
- **unlanded-lease during the eu release (10 occurrences, 2026-11-16 17:55:52 to 18:22:26, offsets 1718236779 to 1719077080):** the lead replied "landing them earlier would change the tree being shipped" six times. 90118fb656 fixed it at 18:47Z. After that the hold message "held for the running release:local" appears at 18:48:44 (1719849230), 19:25:59, 19:34:06 and 19:37:33.
- **commit-review 11-17 13:38/13:39 on unreachable commits:** 2 blocks, already covered by hint row 2026-11-17T13:39:04Z.

## Ranking by cost to the session

| Rank | Point | Count in this window | Turns lost | Already fixed by? |
|---|---|---|---|---|
| 1 | #1: the judge's MISSING IDS ignores ids the lead named minutes earlier on items that have not changed, so a summary always fails | 49 blocks | 17 replies with no work call; 22 full tables; 144,613 reply characters | No. R20261110.4 made the omission measured, but has no bank. The bank that exists (`last_report_sig`) only feeds `no-remaining`, and only behind a `## Remaining` heading |
| 2 | #2: the judge orders work that is finished in a lease (W2.3, W2.4, W10, #5e6608ca) and work blocked by a recorded BLOCKED_BY (W2.6) | 7 of the 14 W2.x orders | 5 replies with no work call; 2 hint rows; 1 unneeded writer start, though the third W2.6 ask did yield a real slice (D2) | No. R20261110.5 `item_workers` carries no lease state; `settle_closed_reraise` covers closed items only |
| 3 | #3: wake-timer state: ALREADY ARMED leaves the shorter old timer, and a timer that has fired still counts as a waker until its notification is delivered | 13 judge blocks, 6 admissions | 5 replies with no work call | R20261110.4 `wake_until` holds. These are the cases it exposes |
| 4 | #4: unlanded-lease has no honest form for "superseded by a regeneration that has not landed", and no drill hold | 3 blocks on lease agent-abb3779a0acb10c25, 1 during drills | about 6.5 min reading gc and lease code (14:50:08 to 14:56:37) | No. Hint rows 2026-11-13T10:33:28Z and 2026-11-17T14:50:38Z |
| 5 | #5: a 14-day clock gate (agent-session-archival) went red while the push waited on receipts | 1 push refusal | 2 tooling commits plus one extra ci:quick (bruae2g2n) | The two tooling bugs are fixed (170a147937, private/bin cb061d3933). Nothing warns before the clock crosses |
| 6 | #6: the stop ledgers live in /tmp and lost 2026-11-10 to 11-14 | 146 judge blocks with no row | the retro cannot measure them | No |

---

## 1. MISSING IDS ignores a table the lead just wrote

**What happened.**
- 49 of 103 judge blocks rested at least partly on omitted ids. 22 were answered with a full table naming 15 or more ids, and 17 replies made no work call at all.
- From 11-17T11:18 on, every id-flag came shortly after a full table. 13 flags name ids in their visible reason (the ledger cuts reasons at 300 characters). In each of the 13, every id named also appeared in the lead's previous full table, written 3 to 76 minutes earlier. Examples:
  - 11:18:17 (offset 1733082721) flags 17 ids, all in the 11:07:59 table.
  - 17:14:30 (1743453265) flags 7 ids, all in the 17:11:05 table.
  - 17:45:50 (1744460007) flags 7 ids, all in the 17:39:50 table.
  - 18:33:37 (1745905012) flags 4 ids, all in the 18:28:59 table.
- The 19:30:49 message ("The open items are unchanged from the table above") was judged at 19:36:43 (1747365277): "names none of the 24 open ids in MISSING IDS". The table above it, at 19:20:45, named 27 ids.
- The operator's ruling stands: out-of-sync blocks at smart (`.claude/config/effort.json`, tuned "promote" 2026-11-06T14:23:19Z, review_after 2026-11-20). So `settle_by_effort` (`.claude/hooks/stop/wl_judge.py:1375`) correctly does not dissolve these continues. The defect is the measurement, not the level.

**Root cause.**
- `_judge_facts` computes `missing = [i for i in tracked if not _item_id_named(i, message)]` (`.claude/hooks/stop/wl_checks.py:3307`), against the last message only.
- A bank exists. `state_doc["last_report_sig"]` is set at `.claude/hooks/stop/wl_checks.py:4136-4138`, keyed on `report_items_sig` (`.claude/hooks/stop/wl_store.py:2978`: id, state, owner and a basetext hash, which an `--update` does not move). But only `no-remaining` reads it (`.claude/hooks/stop/wl_checks.py:6164-6170`), and only behind `REMAINING_HEADING` (`:85`).
- The lead's tables were headed "Every open item:", so even that bank was never set.
- The deterministic `out-of-sync` (`:6144`) has the same blind spot.

**Fix.**
- **Bank per item, not per message.** On every stop, for each tracked id the last message names, store `state_doc["named_ids"][id] = (item key, stamp)`. The item key is the `report_items_sig` element for that record.
- **MISSING IDS subtracts banked ids.** `missing` drops an id whose banked key equals its current key and whose stamp is under `NAMED_BANK_MIN` (D1).
- **The prompt names what was subtracted.** `JUDGE_FACTS` gains `BANKED (named at HH:MMZ, unchanged since): #...`. The checklist line at `.claude/hooks/stop/worklist_messages.py:2231-2235` adds "an id under BANKED is not an omission".
- **The deterministic check uses the same subtraction.** `out-of-sync` at `:6144` uses the same set, so the two checks never disagree.

## 2. The judge orders finished-in-lease and blocked work

**What happened.**
- **Finished work ordered again (4 times):**
  - 18:22:18 (1745455368): "advance the deferred W2.3 ee3be061, W2.4 e67fef60 and W10 96e623c9". Lead at 18:23:02: "W2.3, W2.4 and W10 are already finished in their writers' copies."
  - 18:28:46 (1745664243): "write the W10 ratchet wiring and W2.4 hash contract on disk". Lead at 18:28:59: "already written and committed in their writers' copies."
  - 19:20:31 (1747177977): "start ... W10 96e623c9". Lead at 19:20:45: "W10 ... is already finished in its writer's copy (d2e334c3f9)."
  - 19:36:43 (1747365277): "Start a Plan agent for ee3be061 and e67fef60". The lead filed hint row 19:36:38Z.
- **The blocked W2.6 ordered three times:** 17:39:09 (1744255290), 18:00:30 (1744957553) and 18:03:58 (1745086650).
  - At 17:39:15 the lead recorded `BLOCKED_BY:#bd56a02f` with the reason: W2.6 needs W2.3+W2.5 and W2.4 on one tree.
  - At 18:00:38 it filed hint row 18:00:38Z.
  - At 18:04:16 it found a separable hand-edit slice and started it (agent at 18:04:36). The third ask was partly right, which shapes D2.

**Root cause.**
- **The display hides the facts.** The judge sees each item as `brief_text`, which is basetext plus the LATEST note only (`.claude/hooks/stop/wl_store.py:1066-1080`, via `brief_line` at `:1083` and `.claude/hooks/stop/wl_checks.py:3918`). The lead's shared push-chain `--update`s (five so far on #042aa19e: "push chain: drills passed…", "…archival gate went red…", "…two upstream-driven reds…") buried "lands after the push" under LATEST.
- **A BLOCKED_BY token is invisible on a live lease.** The token joins `rec["text"]` (`.claude/hooks/stop/wl_store.py:1218-1222`) and never reaches the display. `waiting_on` is computed only for open items (`:1593-1596`) and expired leases (`:1638`), not for a live `[>]`.
- **The remaining list is cut at 20.** `remaining_lines[:20]` is at `.claude/hooks/stop/wl_judge.py:961`. The 19:20:45 table named 27 items. By store creation time, #f0da7369, #042aa19e, #bd56a02f, #8f8401cb and #5e6608ca are rows 20 to 24 (2026-11-17T16:02:31Z to 17:17:35Z), and in-flight lines come last (`.claude/hooks/stop/wl_checks.py:4123-4128`). So the newest W-items reached the judge only as bare ids in MISSING IDS. The block shown to the lead at 19:36:43 listed 12 tracked lines, none of them a W-item.
- **The hook already knows which leases finished.** `wl_worktrees.survey` measures every finished lease and its unlanded commits on each stop (`.claude/hooks/stop/wl_checks.py:2830`, cached in `state_doc["worktrees"]`). A lease id is `agent-<worker id>`, and the item's `lease_workers` holds that worker id. The judge is never told.

**Fix.**
- **(a) A finished-in-lease fact.** `_judge_facts` adds `finished_in_lease`: for each remaining item, each past worker `w` where `agent-<w>` has unlanded commits in the survey cache, with the commits and the active hold (vm:check, ci:quick, release, receipt-for-push, or none).
- **(b) A blocked fact.** `_judge_facts` adds `blocked` for any owned item, `[>]` included, that carries an open BLOCKED_BY. It quotes the note that introduced the token, which the fold now keeps as `rec["blocked_note"]` at `wl_store.py:1218`.
- **(c) Both render in JUDGE_FACTS,** and `brief_text` appends `BLOCKED_BY #x: <note[:120]>` so the lead sees it too.
- **(d) No more 20-line cut.** The judge gets every remaining line, each capped at 160 characters (D4).
- **(e) `settle_finished_reraise`,** next to `settle_closed_reraise` (`.claude/hooks/stop/wl_judge.py:1130`). A continue whose next_action names only finished-in-lease items, by `#id` or by a box token of the item's basetext (`W2.3`, `ee3be061`), is read as stop. A continue naming only blocked items is read as stop on the second identical ask while the blocker's item key is unchanged (D2).

## 3. Wake-timer state the hook knows, found by a model round trip

**What happened.**
- **19:09:39.** The lead armed a 60-minute timer. Task bftv7o62u printed "ALREADY ARMED: session d778be9d's timer (pid 3390750) fires at 19:21Z; not starting a second one." and exited 0 at once (its notification at offset 1747094882). The older timer bavd862u6 ("ARMED … wakes at 19:21Z (40 min)") fired, and its notification was queued at 19:22:25 (1747224499). It was delivered only at 19:30:28 (1747308832), after the 19:30:11 judge block "The message says 'The wake timer is armed', but MEASURED FACTS reads 'WAKE TIMER: none armed'". The lead's claims at 19:10:42 and 19:20:45 rested on the 60-minute arm.
- **11:37.** The timer fired at 11:37:54 (queued at 1733367237) and was delivered at 11:41:05, after the 11:40:50 block (1733402464). The admission at 11:42:25 followed.
- 13 judge blocks were of this kind, and 6 admission rows say the same.

**Root cause.**
- **ALREADY ARMED keeps the earlier fire time.** It exits 0 without moving the fire time (`.claude/hooks/stop/wl_wake.py:174`), and the sleeper reads `doc["until"]` once (`:183`).
- **Two sources disagree.** The deterministic `wake-timer` check (`.claude/hooks/stop/wl_checks.py:4469`) trusts `split_wakers` (`.claude/hooks/stop/wl_wake.py:101-108`), a regex over the harness task list. That list still holds a timer whose exit notification has not been delivered (inferred from the delivery times above). `_judge_facts` reads the lock pid instead (`.claude/hooks/stop/wl_checks.py:3310`). So the cheap check passes, and the model call reports what the lock already said.

**Fix.**
- ALREADY ARMED writes `until = max(holder, requested)` into the lock and prints the new fire time. The sleeper re-reads `until` from the lock on each 30-second tick.
- The `wake-timer` check counts a timer only while `read_lock` names a live `wl_wake` pid with `until > now`. Otherwise it blocks deterministically, before the judge, with "timer <id> fired at HH:MMZ; its notification may still be queued; re-arm: <cmd>".

## 4. Unlanded-lease: superseded-pending and the drill hold

**What happened.**
- **The superseded commit.** Lease agent-abb3779a0acb10c25 held only bddc296634, old traced-paths data that conflicts with manifest.ts and was replaced by the W2.2 re-trace, still to land.
  - The lease blocked at 13:38:15 (1736224463, among six commits), 14:50:08 (1739133381) and 14:55:30 (1739376978).
  - From 14:50:12 to 14:56:37 the lead read `worktree gc --help`, wl_worktrees and worktree_lease, then saved a patch.
  - It got out by leasing #1abe21eb to the new writer with a note naming the old lease id. That makes `_holder` (`.claude/hooks/stop/wl_worktrees.py:213`) read the tree as held: an accident, not a verb.
- **The drill.** One block came during `drill backup` at 11-16T01:59:21 (1698940734). That is hint row 2026-11-16T01:59:26Z, which nothing implements.

**Root cause.**
- `superseded_commits` waives a commit only when its `landed` parts are ancestors of the tip (`.claude/hooks/stop/wl_worktrees.py:300-327`), and `--superseded-by` takes `<lease-sha>=<landed-sha>` only (`.ci/rediacc_ci/dev/worktree_lease.py:894`, `:1729`).
- `worktree_check` holds for vm:check, ci:quick, release and a green receipt (`.claude/hooks/stop/wl_checks.py:2848-2890`), but not for the backup drill.

**Fix.**
- **A pending form.** `--superseded-by <sha>=pending:<lease-id>` writes `{sha, pending}`. `superseded_commits` waives the commit while that lease tree exists with a live holder or unlanded commits. The waiver lapses when the tree is collected, so the block returns until a landed sha is recorded. Hidden work cannot outlive the replacement.
- **The block names the verb.** `V_WORKTREE_UNLANDED` (`.claude/hooks/stop/worklist_messages.py:3463`) adds the pending form.
- **A drill hold.** `drill_running(root)` (argv `rediacc_ci.drills` drill backup or backup-onprem, same-checkout test as `release_local_running` at `.claude/hooks/stop/wl_checks.py:2810`) joins the hold chain.

## 5. A clock gate turned red while the push waited

**What happened.**
- **18:34:44 (1746059024).** The push guard refused: "these readers did not pass at that tree: check:ci-agent-session-archival". S2 said "agent/reviews/1023-1/ belongs to a branch merged 14.0 days ago (> 14.0)".
- **Pruning surfaced two tooling bugs,** fixed in 170a147937 (the census skips review records) and private/bin cb061d3933 (citers skip worklist publications), then the archive 127b931d26 at 18:41.
- **Then another receipt run.** ci:quick ran again (bruae2g2n). It surfaced two upstream-driven reds, which led to the b03d49xpf chain at 19:09:35. The push was still waiting at 19:40.

**Root cause.**
- S2 has a single threshold and no lead time (`.ci/rediacc_ci/quality/agent_session_archival.py:340`, `retention_days` at `:380`).
- Nothing in the Stop hook says a retention clock will cross while the push chain runs.

**Fix.**
- The gate's `--status` prints `due within 48h` rows.
- The Stop hook queues an `archival-due-soon` advisory (priority 2, one per directory per day) when any S1 or S2 directory is within 48 hours of its limit. The lead then archives it in the commit batch before the gate run.
- The new key goes into `.claude/config/effort.json` as advise-only, per the effort-table rule.

## 6. The stop ledgers live in /tmp

**What happened.** The blocklog and judge log for 2026-11-10 to 11-13 are gone. The transcript holds 146 judge blocks from then (offsets 1517665944 to 1652847674) with no row. `/tmp/claude-worklist` was recreated at 2026-11-13T19:38Z, the blocklog at 11-14T05:10:30Z and the judge log at 11-15T17:31:44Z.

**Root cause.** `blocklog` writes `worklist.with_suffix(".blocklog-%s.jsonl")` (`.claude/hooks/stop/wl_checks.py:1328-1343`). The worklist path is `/tmp/claude-worklist/home_developer_console.md`, and the judge, admissions and tick-refusal ledgers sit beside it.

**Fix.** Write the four ledgers under the repo's common git dir (`<git-common-dir>/rediacc-worklist/`). That location survives /tmp clears, stays untracked and is shared by lease trees. `wl_retro` reads the new path, plus the old one when it exists.

## Decisions

- **D1, how long a named id stays banked.**
  - DEFAULT: 120 minutes, and only while the item's key (id, state, owner, basetext hash) is unchanged.
  - WHY: the 13 measured flags followed their table by 3 to 76 minutes. A tick, a re-lease, a deferral or a basetext edit moves the key and the id is demanded again, which keeps the operator-view rule.
  - HOW: R20261117.1.
- **D2, settling orders for blocked items.**
  - DEFAULT: never settle the first ask. Read as stop a repeat of the same order on the same blocked item while the blocker's key is unchanged.
  - WHY: the third W2.6 ask (18:03:58) found a real hand-edit slice (agent at 18:04:36). Settling every ask would have hidden it.
  - HOW: R20261117.3.
- **D3, measured or declared finished-in-lease.**
  - DEFAULT: measured, from the survey cache joined on `agent-<worker>`. No new item token.
  - WHY: the declared form ("lands after the push") was buried by later updates. The lease's unlanded commits cannot be.
  - HOW: R20261117.2.
- **D4, the size of the remaining list.**
  - DEFAULT: every line, 160 characters each.
  - WHY: 27 lines come to about 4,300 characters, under the 6,000 the message already gets (`message[-6000:]`, `.claude/hooks/stop/wl_judge.py:963`).
  - HOW: R20261117.4.
- **D5, when a pending supersession lapses.**
  - DEFAULT: when the pending lease tree is collected, with no time limit.
  - WHY: a pending waiver must not outlive its replacement, and while the replacement lives the old commit has nowhere to go.
  - HOW: R20261117.6.
- **D6, where the ledgers live.**
  - DEFAULT: `<git-common-dir>/rediacc-worklist/`.
  - WHY: durable, untracked, shared by lease trees. `agent/ledgers` would put every block into git churn.
  - HOW: R20261117.8.

## Sequencing

1. R20261117.2, then .3: .3 reads the facts .2 adds.
2. R20261117.1 and .4 edit the same `_judge_facts`, `render_facts` and `JUDGE_FACTS` code as .2, so all of .1 to .4 go on one writer.
3. R20261117.5, .6, .7 and .8 are independent.
4. R20261117.9 comes last, on the next window's blocklog.

## Tasks

- [ ] **R20261117.1** Bank named ids per item. Each stop records `state_doc["named_ids"][id] = (item key, stamp)` for the ids the last message names. `_judge_facts` (`.claude/hooks/stop/wl_checks.py:3307`) and `out-of-sync` (`:6144`) leave out an id whose banked key is current and under `NAMED_BANK_MIN = 120`. `JUDGE_FACTS` lists BANKED, and the checklist (`.claude/hooks/stop/worklist_messages.py:2231-2235`) defers to it. Fixture: the 11:07:59 table naming 17 ids, then a message naming none with every item key unchanged, giving MISSING IDS none. Inverse: one item re-leased, so its id is missing. Inverse: a bank 121 minutes old, so all are missing. Test: .claude/rediacc_hooks/tests/test_wl_judge_facts.py.
- [ ] **R20261117.2** Add `finished_in_lease` and `blocked` to `_judge_facts` and render both. `finished_in_lease` comes from `state_doc["worktrees"]` joined on `agent-<lease_workers>`, with commits and the active hold. `blocked` covers any owned item, `[>]` included, with an open BLOCKED_BY and the `blocked_note` the fold keeps at `.claude/hooks/stop/wl_store.py:1218`. `brief_text` appends `BLOCKED_BY #x: <note>`. Fixture: #042aa19e leased to b03d49xpf with past worker a79c195310d47dda4, and cache `agent-a79c195310d47dda4` with commits, gives the fact rendered with "held for vm:check". #f0da7369 `[>]` with BLOCKED_BY #bd56a02f gives the note in its display line. Test: .claude/rediacc_hooks/tests/test_wl_judge_held.py.
- [ ] **R20261117.3** `settle_finished_reraise` in the settle chain (`.claude/hooks/stop/wl_judge.py:1128-1131`). A continue whose next_action names only finished-in-lease items, by `#id` or by a box token from the item's basetext, is read as stop. A continue naming only blocked items is read as stop on the second identical ask while the blocker's key is unchanged. Fixtures: the 19:36:43 order ("Start a Plan agent for ee3be061 and e67fef60") gives stop. The W2.6 order first gives continue, then gives stop on the repeat. Inverse: an order naming one finished and one open item gives continue. Test: .claude/rediacc_hooks/tests/test_wl_judge_held.py.
- [ ] **R20261117.4** Give the judge every remaining line, each capped at 160 characters, replacing `remaining_lines[:20]` (`.claude/hooks/stop/wl_judge.py:961`). Fixture: 27 remaining lines, where the stub-captured prompt holds all 27 ids. Test: .claude/rediacc_hooks/tests/test_wl_judge_facts.py.
- [ ] **R20261117.5** Make wl_wake honest:
  - ALREADY ARMED writes `until = max(holder, requested)` into the lock and prints it (`.claude/hooks/stop/wl_wake.py:174`).
  - The sleeper re-reads `until` from the lock each tick (`:183`).
  - The `wake-timer` check (`.claude/hooks/stop/wl_checks.py:4469`) counts a timer only on a live lock pid with `until > now`, and otherwise blocks with the fire time and the re-arm command.

  Fixtures: a held lock until 19:21Z and an arm of 60 minutes, giving a lock until 20:09Z and an extended sleeper. A waker task in the harness list with a dead lock pid gives a wake-timer block naming "fired at". Test: .claude/rediacc_hooks/tests/test_wl_wake.py.
- [ ] **R20261117.6** Add `--superseded-by <sha>=pending:<lease-id>` (`.ci/rediacc_ci/dev/worktree_lease.py:1729`). `superseded_commits` (`.claude/hooks/stop/wl_worktrees.py:300`) waives the commit while the pending lease tree exists with a holder or unlanded commits. `V_WORKTREE_UNLANDED` names the form. Add `drill_running(root)` to the hold chain in `worktree_check` (`.claude/hooks/stop/wl_checks.py:2848-2890`). Fixtures: bddc296634 with a pending lease live, so not unlanded; the pending tree collected, so unlanded again. A drill argv of this checkout gives held. Test: .claude/hooks/stop/test-wl_worktrees.py.
- [ ] **R20261117.7** Archival lead time. `check_agent_session_archival --status` prints due-within-48h rows from `.ci/rediacc_ci/quality/agent_session_archival.py`. The Stop hook queues `archival-due-soon` (advise-only, added to `.claude/config/effort.json`). Fixture: a review directory of a branch merged 12.5 days ago gives the advisory and gate rc=0. At 14.1 days, the gate is red and there is no advisory. Test: .claude/rediacc_hooks/tests/test_wl_archival_due.py.
- [ ] **R20261117.8** Move the blocklog, judge, admissions and tick-refusal ledgers to `<git-common-dir>/rediacc-worklist/`. `wl_retro` (`.claude/hooks/stop/wl_retro.py:237`) reads the new path and the old one. Fixture: rows in both paths are counted once each, in time order. Test: .claude/rediacc_hooks/tests/test_wl_retro.py.
- [ ] **R20261117.9** After .1 to .8 land, re-count on the next window's blocklog and judge log and record before and after for the id-flag, W-order and wake classes against this plan's 49, 7 and 13. Test: .claude/rediacc_hooks/tests/test_wl_retro.py.

### Critical Files for Implementation
- /home/developer/console/.claude/hooks/stop/wl_checks.py
- /home/developer/console/.claude/hooks/stop/wl_judge.py
- /home/developer/console/.claude/hooks/stop/wl_store.py
- /home/developer/console/.claude/hooks/stop/wl_wake.py
- /home/developer/console/.claude/hooks/stop/wl_worktrees.py
