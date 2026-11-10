# PLAN: Stop-hook retro, 2026-11-10 (band early, lead session d778be9d, tracking #cb6c78eb)

Status: ready
Depends-On: no-dep -- no box waits on another plan
Priority: P1 -- at 2026-11-10T09:01Z the operator turned the stop-gate judge off because "it pings too often"
Concurrency: parallel -- R20261110.1 to .5 all edit worklist_messages.py and wl_judge.py, so run them on one writer; .6 and .7 are independent
Owns: .claude/hooks/stop/wl_judge.py, .claude/hooks/stop/worklist_messages.py, .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/wl_planrec.py, .claude/hooks/stop/worklist.py, .claude/hooks/stop/wl_report.py, .claude/hooks/stop/wl_roster.py, .claude/rediacc_hooks/tests/test_wl_judge_local_batch.py, .claude/rediacc_hooks/tests/test_wl_judge_receipt_inflight.py, .claude/rediacc_hooks/tests/test_wl_judge_facts.py, .claude/rediacc_hooks/tests/test_wl_interim_reports.py, .claude/rediacc_hooks/tests/test_wl_retro.py
First-Seen: 2026-11-10
Owner: d778be9d (adopted from retro a3e8877d1c647e3cb 20261110)
Updated: 2026-11-10

**Scope.** The brief gives lead transcript bytes 238604947 to 1517665944, which run from 2026-09-25T13:32Z to 2026-11-10T14:34Z. Every ledger row the brief names falls inside a narrower stretch: blocklog rows run from 2026-11-09T19:54:35Z to 2026-11-10T14:55:56Z, and judge rows from 2026-11-09T19:56:54Z to 2026-11-10T09:01:35Z. A bisection by timestamp puts the start of that stretch at offset 1480817994 (record 2026-11-09T19:49:15Z). So this retro measures bytes 1480817994 to 1517665944. Bytes 238604947 to 1480817994 have no blocklog or judge rows to count against, and the retros 20260925 and 20261101 already covered their frictions. That range is not analysed here.

No `PLAN-stop-hook-retro-20261110.md` existed, so task numbering starts at R20261110.1. Line numbers refer to the working tree at acc34f7387 (2026-11-10 15:58 +0100).

Counts for the window:
- **Blocked stops:** 131 in `home_developer_console.blocklog-d778be9d.jsonl`. The `judge` key led 88 of them. Other leading keys: roster-dead 13 (also named on 11), worktree-unlanded 9 (1), plan-unimplemented 7 (3), wake-timer 3 (1), wisdom-due 2, commit-review 2 (2), unread-reports 2 (1), and 1 each for open-items, defer-expired, agent-pushback:pr-babysitter, ladder-gone and bg-orphan.
- **Judge verdicts:** 120 rows (88 continue, 32 stop), carrying 0 sweep demands and 0 proof demands.
- **Judge streaks:** the longest run of consecutive `continue` verdicts was 12 (2026-11-10 04:09:03 to 05:04:51). Ten runs went past 3, which adds up to 36 continues beyond the third in a run.
- **Hook time on judge stops:** measured from the lead's last record to the judge block, median 115 s, p90 288 s, 217.6 min in total over the 88 stops.
- **Restatement:** 50 of the 88 judge blocks were answered with no work call (no Agent, Edit, Write, commit, cherry-pick, tick, plan verb, npm, pytest or ssh before the next stop). Those replies added up to 79,720 characters.
- **Operator intervention:** a queued operator command at 09:01:28Z (offset 1508876351) said "switch to low mode at queue.md it pings too often". The lead set `effort: low` at 09:01:53Z (offset 1508895482), which turns the judge off. #fcbed611 tracks restoring it. The judge log has no row after 09:01:35Z.
- **Tick refusals:** 6 rows, each settled with one retry. Admissions: 4 rows, all ledger-only, with no block keyed on them.

**Classifying the 88 continues.** The script read the `reason` field of each continue:
- **local (55):** the reason matches `turbo|0/3|locally|local work|on disk|unpushed`. 33 of these were answered with no work call.
- **checklist (22):** the reason does not match local, but matches the JUDGE_PROMPT checklist (omitted ids, schedule, complicated, operator never asked). 12 were answered with no work call.
- **other (11):** 5 answered with no work call.

**Legitimate blocks, not ranked:**
- **roster-dead (13):** every one named a writer that had in fact finished. The lead landed or recorded its work at once, for example 19:57:28 at offset 1481233373 and 20:54:00 at 1485512130.
- **plan-unimplemented (7):** each fired after a background task really had ended. At 22:16:44 (1487311463) ci:quick was over. At 22:45:21 (1487791310) the fleet was up. At 22:48:19 (1487923348) the drills were done, and `drill backup` had failed. Each block caught a finished task the lead had not looked at yet.
- **Other legitimate blocks:** worktree-unlanded, wake-timer, wisdom-due, defer-expired (03:24:11) and ladder-gone (04:51:21) were all correct.
- **commit-review 07:25:05:** this finding belonged to a live writer, which the hint row of 2026-11-08T17:19:26Z already covers.
- **agent-pushback 03:34:59:** it fired on "can't be done as planned". A pushback fires once per session, which caps its cost.
- **Tick refusals:** R20261101.1 and R20261101.3 held. The `--state` refusals at 20:42:29 and 07:10:29 named every problem in one message.

## Ranking by cost to the session

| Rank | Point | Count in this window | Turns lost | Already fixed by? |
|---|---|---|---|---|
| 1 | #1: the local-batch paragraph orders "advance the open boxes locally" when no open box has local work | 55 continues; 16 replies restating the box table | 33 replies with no work call; judge switched off by the operator at 09:01Z | No. Hint rows 2026-11-09T22:13:49Z, 533bfb90 and 8ed821a7 proposed it; nothing landed |
| 2 | #2: the judge orders live-tree commits while vm:check or ci:quick is building a receipt | 12 lead replies explaining that a commit voids the receipt; 4 "other" continues ordering held edits | about 12 turns | No. `vm_check_running` and `ci_quick_running` exist (wl_checks.py:2649, :2729) but the judge never reads them |
| 3 | #3: the checklist asks the model to check facts the hook already holds (wake time, the worker behind an item) | 22 continues resting on the checklist alone; 8 schedule demands, 15 complicated demands | 12 replies with no work call, plus a Plan agent spawned only to satisfy a demand (04:34:11) | No |
| 4 | #4: interim [SILENT] captures block as unread reports | 2 led, 1 named | 2 turns | **R20260924.7 did not hold** on these captures |
| 5 | #5: a content-free verdict ("Duplicate call ignored." / "Ignore.") blocks as a continue | 1 | 1 turn | No |

---

## 1. The local-batch paragraph orders local box work that does not exist

**What happened.**
- **The paragraph:** the branch was filling a turbo batch with no PR, so every judge call carried JUDGE_LOCAL_BATCH. 55 continues ordered local box work, and 36 of them quote "0/3 plans finished".
- **What the boxes needed:** the open boxes of the PR plan set were 22, then 21. They needed a PR preview (A1a), CI run ids (A4d, J6, J9), a nightly (K10), elite live (I3), hostinger or bench (Q2, H3, L2, LP-*), or the receipts (P15). The lead had already written investigation rows saying so. For example, A1a got its row at 19:59:01 (offset 1481364236 onward), and A4d was committed at 04:24:43.
- **The streak of 04:09 to 04:33:**
  - At 04:13:18 (1493820829) the judge said the batch's open boxes had not been checked.
  - At 04:13:29 (1493844952) the lead replied "I've already checked every unchecked box in the batch ... The 22 open boxes, by plan", with each box's reason.
  - The judge then gave the same order again at 04:17:30 (1493936103), 04:19:22 (1493971475) and 04:21:17 (1493998970), saying "its open boxes are never checked", and again at 04:31:59 (1495988676).
  - At 04:32:15 (1496021277) the lead replied with a second full table.
- **Repeated tables:** 16 replies to a judge continue name 12 to 14 of the box ids, so each is a full box table. They are at offsets 1484306017, 1484621129, 1487111609, 1487537139, 1487701996, 1489090709, 1489335292, 1490148500, 1490202824, 1492526091, 1493844952, 1496021277, 1506391913, 1506951164, 1508461914 and 1508823368.
- **The cost:** the operator's 09:01:28Z order to drop to `effort: low` turned the whole judge off, not just this order.

**Root cause.**
- `JUDGE_LOCAL_BATCH`, `.claude/hooks/stop/worklist_messages.py:3314-3319`, states the conclusion without any condition: "the next action advances the batch's open boxes locally" (:3318).
- `wl_checks._judge_local_batch`, `.claude/hooks/stop/wl_checks.py:3111-3118`, passes only `{"finished", "batch"}`. The judge learns no box, no tag and no investigation verdict.
- The judge sees only the last message (`message[-6000:]`, `.claude/hooks/stop/wl_judge.py:957`), so the table given two stops earlier no longer exists for it.
- The facts are on disk:
  - `wl_boxready.non_writer` and `post_merge` (`.claude/hooks/stop/wl_boxready.py:48`, `:54`) read box tags.
  - `agent/ledgers/plan-investigation.jsonl` holds 60 rows written in the window, 43 present and 17 partial.
- Tags alone cannot decide this, because A1a, A4d, I3, J6, J9, K10, P15, Q2 and Q16 carry no tag (`agent/plans/PLAN-backup-program.md:109-614`), and `startable` (`wl_boxready.py:65`) reads an untagged box as startable.
- A `partial` row does not say which part is owed. `INV_VERDICTS`, `wl_planrec.py:2291`, holds only absent, present and partial, with free-text notes.

**Fix.**
- (a) `--plan-investigate ... partial` takes `--owed live|ci|post-push|operator|code`, stored as `owed` on the row (`wl_planrec.append_investigation`, `:2321`).
- (b) `wl_checks._batch_box_facts(state, root)`, for every open box of `state.plans`, returns one of three classes:
  - `non-writer`: by tag.
  - `owed:<kind>`: the newest row for (plan, sig) is partial with `owed` other than `code`.
  - `local`: anything else.
- (c) `_judge_local_batch` adds `open`, `local` and the rows.
- (d) `JUDGE_LOCAL_BATCH` splits in two:
  - With `local == 0`, a paragraph that lists each box with its class and says there is no local box work, so a named live wait is a legitimate stop.
  - With `local > 0`, a paragraph that names those boxes, so an order must name one.
- (e) `settle_batch_no_local` joins the settle chain (`wl_judge.py:1114-1117`). When `local == 0`, a continue whose reason or order matches `turbo|batch|open boxes|locally` and names no tracked `#id` outside the batch is read as stop.

## 2. The judge orders live-tree commits while a receipt is being built

**What happened.**
- 12 judge blocks drew a lead reply explaining that a commit now would void the receipt being built, at 20:15:51, 20:28:10, 22:03:15, 22:09:22, 22:13:41, 22:28:10, 22:42:16, 23:12:05, 08:49:35, 08:53:06, 08:59:04 and 09:01:35.
- 4 "other" continues ordered edits held back for exactly this reason:
  - 23:12:05: "That is a reason to work elsewhere, not a reason to stop."
  - 23:16:13: the #313e832f records.
  - 00:40:14: "plan text under agent/plans is not a ...".
  - 02:15:48: #63c8f457 and #16cd32b3, "That constrains where the edits go, not whether they ...".
- The repo shows the cost of a commit here. The hint row of 2026-11-06T01:25:58Z records vm:check run 1 failing V1.1 because a commit landed mid-run. The hint row of 2026-11-07T13:05:12Z records the backup receipt being keyed on the tree.

**Root cause.**
- JUDGE_PROMPT states as fact that "unpushed work cannot disturb a run in flight" (`worklist_messages.py:2191-2193`, inside the CI-wait paragraph at :2179). That is false for vm:check, which rebuilds the CLI from the live tree on each rdc call, and for ci:quick and the backup receipt, which are keyed on the tree.
- The hook can already tell such a run is live: `vm_check_running` (`wl_checks.py:2649`) and `ci_quick_running` (`:2729`) back the unlanded-lease stand-down. `run_judge` (`wl_judge.py:868-980`) never receives either.

**Fix.**
- `run_judge` takes `receipt_run` (`"vm:check"`, `"ci:quick"` or None), and the call site at `wl_checks.py:6561` sets it from the two functions.
- When it is set, `M.JUDGE_RECEIPT_IN_FLIGHT` is appended after `extra`, like the local-batch paragraph. It says: a commit or edit in the main checkout now voids the receipt this run is producing; local work during the run means a writer in a lease tree; never order a main-checkout edit or commit.
- The sentence at :2192-2193 gains "except while a vm:check or ci:quick run is building a receipt on this tree".
- `sanitize_next_action` (`wl_judge.py:1303`) gains `RECEIPT_ORDERS` (`commit|edit|land|cherry-pick` without `lease`/`worktree`). With `receipt_run` set, a matching order is rewritten to a `V_JUDGE_RECEIPT_ORDER_REJECTED` text, the way LOCAL_BATCH_ORDERS is handled.

## 3. The checklist asks the model to check facts the hook already holds

**What happened.**
- 22 continues rested on the JUDGE_PROMPT checklist alone. Across all continues there were 26 id-omission mentions, 8 schedule demands and 15 complicated demands. These numbers come from a reason regex plus a negation filter for the schedule clause.
- **Schedule, wake timer already armed:** at 20:36:18 the judge objected that the message 'says only "wake timer armed"'. At 08:20:57 it said 'only "wake timer is armed", no time'. In both cases the hook's own wake lock holds the fire time.
- **Complicated, work already delegated:**
  - At 23:20:25 and 23:24:22 the judge demanded a Plan agent for K1.7's "unknown" root cause. The K1.7 diagnosis agent ab68f85bb599acb4a had already finished at 21:37:27 (a roster-dead row), and the lead read `k17-diagnosis.md` at 21:37:32.
  - At 04:15:18 and 08:20:57 it called backup-large-2g's root cause unknown. Its diagnosis file dates from 01:44Z, and the fix c8982cac had landed (lead, 04:29:14, offset 1495824289).
  - At 04:34:11 (offset 1496065254), 16 s after the 04:33:55 demand, the lead spawned a Plan agent for K1.3, a thread already held by a diagnosis agent and a renet writer.
- **Id omissions:** these demands were correct where checked. At 08:59:04 the message judged (offset 1508777920) did leave out 14 of the 16 box ids named. They cost a model round trip (median 115 s) to find something a set difference finds.

**Root cause.**
- The checklist, `worklist_messages.py:2229-2242`, ends with 'Answer "continue" if any of these is missing'.
- The prompt gives the judge only a lease count (`"leases": leases`, `wl_judge.py:955`) and the remaining lines (`:954`). It gets no wake fire time, no worker per item and no worker type.
- `wl_wake.read_lock(me)` (`.claude/hooks/stop/wl_wake.py:63`) returns `until`, and `is_waker_pid` (`:49`) proves the timer is live.

**Fix.**
- Before `run_judge`, `wl_checks` computes three facts and passes them as `facts`:
  - (a) `missing_ids`: ids in `remaining_lines` that appear nowhere in the message.
  - (b) `wake_until`: from a live wake lock.
  - (c) `item_workers`: for each remaining item, its current and past `worker:` ids with agent type and report title, from the store's lease history and `wl_report` rows.
- `M.JUDGE_FACTS` renders them as measured facts.
- The checklist text changes:
  - The id check becomes "use MISSING IDS; never claim an omission it does not list".
  - The schedule check passes when `wake_until` is present.
  - The complicated check passes for an item with a Plan or writer worker in `item_workers`.

## 4. Interim [SILENT] captures block as unread reports (R20260924.7 did not hold)

**What happened.**
- At 08:53:29 the unread-reports key led a block on `5bff99729ead`: "The runs have not finished yet. I'm waiting on the background notification".
- At 12:40:52 it led again, with roster-dead named, on `1e3c9d6b17e9` and `-2` ("Waiting on the test run's completion notification", "Waiting for regolden to finish.").
- Each of the three index rows in `~/.claude/agent-reports/home_developer_console/index.jsonl` has `silent: true` and no `interim` key.
- Agent aaaeb1e3c9d6b17e9 had launched background shell `bn3oml4sf` at 12:35:45Z. Its `<task-id>` notification first appears at 12:40:00Z, after the 12:39:17Z capture. So at capture time the agent was waiting on an armed shell, which is the case R.7 holds.

**Root cause (inferred).**
- `wl_roster.transcript_waiting` (`.claude/hooks/stop/wl_roster.py:585-597`) returns "" unless `_record_is_idle(last_record(...))` holds.
- In the transcript, the record just before the end_turn assistant record (12:39:17.626Z) is an `api-request` (12:39:15.931Z). If SubagentStop fires before the end_turn record is flushed, the last record is not an assistant record. `_record_is_idle` (`wl_liveness.py:425-447`) then answers False, and `wl_report` (`:949-954`) writes no `interim`.
- This is inferred from record order; it was not reproduced.

**Fix.** On the SubagentStop capture path (`wl_report.py:949-954`), the event itself proves the turn ended, so call a `transcript_armed(jsonl, now)` variant that skips the idle-record test and keeps the WAIT_HORIZON and `armed_shells` checks.

## 5. A content-free verdict blocks as a continue

**What happened.** At 21:21:06 (offset 1486457014) the block read `reason: Duplicate call ignored.` and `next action: Ignore.` This judge row (2026-11-09T21:21:05Z) is the only one in the file with that text. The lead restated its Remaining list (21:21:11), at a cost of 1 turn.

**Root cause.**
- The schema (`wl_judge.py:66-72`) accepts any string.
- `settle_wait_only_continue` (`:1229`) only catches wait-only orders.
- `sanitize_next_action` (`:1303`) only rewrites forbidden orders.

**Fix.** Add `settle_contentless`, run first in the chain at `:1114`. It reads a continue as stop, and queues a `judge-contentless` advisory, when either holds:
- `next_action`, stripped of punctuation, is in `{ignore, none, n/a, nothing, ""}`;
- `reason` is under 40 characters and names no `#id`, file or run.

## Decisions

- **D1, how a partial box declares what it owes.**
  - DEFAULT: a new required `--owed <kind>` on partial investigations; older partial rows count as `local` until re-recorded.
  - WHY: a free-text note cannot be read mechanically, and counting every partial row as non-local would hide real code gaps.
  - HOW: the R20261110.1 verb change. The lead re-records the open boxes once.
- **D2, a hard cap on judge streaks.**
  - DEFAULT: no cap. Keep v5's "no cap" (`wl_judge.py:27`).
  - WHY: within a run, the 4th and later continues repeated one of the previous three orders only 5 times in 36 (Jaccard of 0.25 or more on reason words). So a similarity cap would not have fired; frictions 1 to 3 are the causes.
  - HOW: R20261110.8 re-counts the streaks after the fixes.
- **D3, whether a running receipt suppresses the order or only advises against it.**
  - DEFAULT: suppress, by sanitising the order as LOCAL_BATCH_ORDERS does.
  - WHY: the lead declined the order 12 times; advice alone was not followed by the judge.
  - HOW: R20261110.3.
- **D4, restoring effort.**
  - DEFAULT: #fcbed611 stays as filed (smart near compaction). Lift `low` earlier only on the operator's word, after R20261110.2 and .3 land.
  - WHY: the operator set it.
  - HOW: AskUserQuestion once .2 and .3 are merged.

## Sequencing

1. R20261110.1, then .2: .2 reads the `owed` field.
2. R20261110.3 and .4 edit the same JUDGE_PROMPT region, so they go on one writer, after .2.
3. R20261110.5, .6 and .7 are independent.
4. R20261110.8 comes last, on the next session's blocklog.

## Tasks

- [ ] **R20261110.1** `--plan-investigate ... partial` requires `--owed live|ci|post-push|operator|code` and stores `owed` on the row (`wl_planrec.append_investigation` `:2321`, `worklist.py` `:1380`). A partial without it is refused, and the refusal names the flag. Test: .claude/rediacc_hooks/tests/test_wl_judge_local_batch.py.
- [ ] **R20261110.2** Add `wl_checks._batch_box_facts`: each open box of the batch is classed non-writer by tag, `owed:<kind>` by its newest partial row, or `local`. `_judge_local_batch` carries `open`, `local` and the rows. `JUDGE_LOCAL_BATCH` gets the `local == 0` and `local > 0` variants. `settle_batch_no_local` reads a batch-box order as stop when `local == 0`. The fixture is the 04:13:18 state, 22 boxes all non-local, where the stub-captured prompt carries the no-local variant and a "advance the batch's open boxes" continue settles to stop. The inverse: one box with no row stays `local`, and the continue stands. Test: .claude/rediacc_hooks/tests/test_wl_judge_local_batch.py.
- [ ] **R20261110.3** When `vm_check_running()` or `ci_quick_running(root)` is true, append `JUDGE_RECEIPT_IN_FLIGHT`, qualify the sentence at `worklist_messages.py:2192-2193`, and sanitise main-checkout commit and edit orders (`RECEIPT_ORDERS`). Fixture: a held vm:check lock whose pid has a vm_check argv, and the 23:12:05 order. Inverse: a free lock, where the order passes. Test: .claude/rediacc_hooks/tests/test_wl_judge_receipt_inflight.py.
- [ ] **R20261110.4** Add `JUDGE_FACTS`: `missing_ids` as a set difference against the message, and `wake_until` from a live `wl_wake.read_lock`. The checklist (`worklist_messages.py:2229-2242`) defers to both. Fixture: the 08:20:57 message, with "wake timer is armed" and a live lock until 08:50Z. The prompt states the schedule check passed. Inverse: a dead lock pid. Test: .claude/rediacc_hooks/tests/test_wl_judge_facts.py.
- [ ] **R20261110.5** Add `item_workers` to `JUDGE_FACTS`: current and past `worker:` ids per remaining item, with agent type and report title. The complicated check passes for an item with a Plan or writer worker. Fixture: K1.7 with finished worker ab68f85bb599acb4a (23:20:25). Test: .claude/rediacc_hooks/tests/test_wl_judge_facts.py.
- [ ] **R20261110.6** The SubagentStop capture (`wl_report.py:949-954`) calls a `transcript_armed` that skips `_record_is_idle`, so a silent capture with an armed shell is written `interim`. Fixture: a transcript whose last record is an `api-request` after a `backgroundTaskId` with no `<task-id>`, which gives `interim` set. Inverse: the notification present, which gives no `interim`. Test: .claude/rediacc_hooks/tests/test_wl_interim_reports.py.
- [ ] **R20261110.7** Add `settle_contentless`: a continue with a non-order `next_action`, or a reason under 40 characters naming nothing, reads as stop with a `judge-contentless` advisory. Fixture: the 21:21:06 verdict. Test: .claude/rediacc_hooks/tests/test_wl_judge_facts.py.
- [ ] **R20261110.8** After .1 to .7 land, re-count on the next session's blocklog and judge log, and record the before and after numbers in this plan's Status:
  - the local, checklist and other continue classes (55, 22 and 11 here);
  - restatement replies with no work call (50);
  - the longest continue streak (12);
  - `unread-reports` blocks on [SILENT] interim captures (3).

  Test: .claude/rediacc_hooks/tests/test_wl_retro.py.

### Critical Files for Implementation
- /home/developer/console/.claude/hooks/stop/worklist_messages.py
- /home/developer/console/.claude/hooks/stop/wl_judge.py
- /home/developer/console/.claude/hooks/stop/wl_checks.py
- /home/developer/console/.claude/hooks/stop/wl_planrec.py
- /home/developer/console/.claude/hooks/stop/wl_report.py
