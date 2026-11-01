# PLAN: Stop-hook retro, 2026-11-01 (band late, covers early #b4940dfa; lead session 45048a90)

Status: ready
Depends-On: no-dep -- cites no other plan
Priority: P2 -- refusal wording that cost calls, no wrong block
Concurrency: parallel -- touches only the stop hook's refusal text
Owns: .claude/hooks/stop/worklist.py, .claude/hooks/stop/worklist_messages.py, .claude/hooks/stop/wl_store.py, .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/wl_report.py, .claude/rediacc_hooks/tests/test_wl_tick_commit_ref.py, .claude/rediacc_hooks/tests/test_wl_state_document.py, .claude/rediacc_hooks/tests/test_wl_report_inbox.py
First-Seen: 2026-11-01
Owner: 45048a90 (adopted from retro retro-late 20261101)
Updated: 2026-11-01

**Scope.** This retro covers lead transcript bytes 0 to 10523302. That runs to 2026-11-01T19:45:02Z, the last record in the range, at line 4380 and offset 10521114. The early band (#b4940dfa) has the same session and date and a range contained in this one, so this single retro answers both. No `PLAN-stop-hook-retro-20261101.md` exists yet, so the task numbering starts at R20261101.1. The boxes in `PLAN-stop-hook-retro-20260924.md` and `-20260925.md` were not re-proposed. Of those, R20260924.21 (the ready-to-paste `ASKED:` hint) and R20260924.8 (the extra accepted evidence shapes) held, and are cited below.

Counts for the window:
- **Blocked stops:** 3 rows in `/tmp/claude-worklist/home_developer_console.blocklog-45048a90.jsonl`:
  - 13:23:51Z `unread-reports`.
  - 14:02:34Z `roster-dead`.
  - 19:54:37Z `wake-timer`.
  - Each row has `named: []` and `judge: {}`, so there were 0 continue, 0 sweep and 0 proof flags.
- **Third block not readable:** only the first two blocks are in the transcript range. The `wake-timer` block at 19:54:37Z is after the last record (19:45:02Z), so it has no transcript evidence here and is not analysed. The next band should cover it.
- **Hint proposals, judge verdicts:** none.
- **Admissions:** 1 row, `damage-verb`, `ts` 18:24:34Z.
  - **Span:** it quotes the lead reporting the deletion of `mail-verify`. The only transcript occurrence is the lead's final message at 17:34:28Z, line 3744, offset 8677663.
  - **No block, no cost:** that sentence reports the lead cleaning up its own temporary restore repo. The ledger timestamp is 50 minutes after the message, so the row could not be tied to a stop. It is ledger-only, produced by Tier R with no model call, and is not ranked.
- **Refused `--tick` calls:** 9 rows in `home_developer_console.tick-refusals-45048a90.jsonl`, 5 `no-evidence` and 4 `no-commit-ref`. They fall on three items:
  - #6c84ff1f: rows at 15:45:56, 15:46:05 and 15:47:21.
  - #6c63dfb8: rows at 16:53:26, 16:53:37, 16:53:38, 16:53:48 and 16:58:33.
  - #51d75260: one row at 16:53:50.
- **Other refusals found in the transcript:** `worklist.py --state` refused 4 times between 19:40:34Z and 19:40:49Z (lines 4321, 4330, 4338 and 4352).

**Line numbers** refer to the working tree at about 20:00Z on 2026-11-01.

**Legitimate blocks, not frictions:**
- **`roster-dead` at 14:02:34Z (line 1807, offset 4759783):**
  - It named #cfed8c4a, leased to worker a40d8d8be3b7bba0d, which had finished and reported.
  - The lead re-leased it to the live measuring run in one call (line 1813, offset 4778232) and finished its turn 13 s after the block (line 1817, offset 4784501).
  - The block was correct and cost 1 call.
- **The #6c84ff1f refusals were right in outcome.** The lead tried to tick it as an investigation with no fix. A fix then landed in private/renet, and the tick naming that commit was accepted at 15:58:36Z (line 3115, offset 7259344).
- **The #51d75260 `no-evidence` row at 16:53:50Z was correct.** It cited `ASKED:2026-11-01T16:13Z`. The AskUserQuestion answers in this range are at 16:42:40, 16:47:36 and 16:51:14 and later (lines 3186, 3220 and 3262), none within 300 s of 16:13. `.claude/hooks/stop/wl_checks.py:301` (`ASKED_WINDOW_S = 300`) did its job.

## Ranking by cost to the session

| Rank | Point | Count in this window | Turns lost | Already fixed by? |
|---|---|---|---|---|
| 1 | #1: the two tick gates are serial, and the first refusal does not name the second | 9 refusal rows (5 no-evidence, 4 no-commit-ref) across 3 items, in 7 tool calls | about 4 calls whose main purpose was the retry, 0 blocked stops, and 5 min 19 s from first refusal to tick on #6c63dfb8 | **R20260924.21 held** (the `ASKED:` hint appeared at 16:53:37), but it only helps the first gate |
| 2 | #2: a decision-only tick has no honest commit reason, so the lead attached an unrelated HEAD | 4 of the 9 rows: the no-commit-ref rows at 16:53:38, 16:53:48 and 16:58:33, and the no-evidence row at 16:53:50; and 2 ticks closed on `commit:<HEAD> decision only` (line 3328) | 2 retries, and the 2 closing ticks cite a commit that holds none of the work | No |
| 3 | #3: `--state` reports one shape verdict per attempt | 4 refusals in 20 s: no-dir, unfocused, bloated by 320 chars, bloated by 4 chars | 4 extra calls, at the moment the context was nearly full | No |
| 4 | #4: the unread-reports block does not say how to list or mark the reports | 1 block, 4 calls (2 of them dead ends), 27 s | 1 turn | No |

---

## 1. The two tick gates are serial, and the first refusal does not name the second

**What happened.**
- **#6c84ff1f, the first tick (line 2932, offset 6932137, refused 15:45:56):** the evidence was `nocommit:cause found by journal: R2 chunk PUT HTTP 503 at 02:26 ...`. It had no sha, run id, exit code, URL or resolving file:line. `#0d5a1fd5` is a worklist id, not a git object. The result was `no-evidence`.
- **The retry (line 2952, offset 6963861, refused 15:46:05):** it was refused the same way. Nothing in the `no-evidence` text mentions that a commit reference is also required.
- **The third attempt (line 2958, offset 6977160):** it added `exit code: 1`, so the evidence gate passed. It was then refused at 15:47:21 by the second gate, `no-commit-ref`: `nocommit:read-only` is not in `NOCOMMIT_REASONS`.
- **#6c63dfb8 (line 3269, offset 7582237):**
  - 16:53:26: `ASKED:2026-11-01T16:3Z` was refused as `no-evidence` (a malformed minute).
  - 16:53:37 (line 3287, offset 7611203): the lead sent a deliberate probe tick with the evidence `x` to make the hook print its ASKED hint. It printed `ASKED:2026-11-01T16:51Z`.
  - 16:53:38: with the right ASKED, the evidence gate passed and the `no-commit-ref` gate refused.
  - 16:53:48 (line 3298, offset 7629295) and 16:58:33 (line 3315, offset 7648667): `nocommit:operator decision ...` was refused twice. The regex captures `operator`, which is not one of `no-tracked-change`, `research` or `operator-deferred`.
- **The lead's pipes hid the refusal text.** The calls ended in `| tail -1 | cut -c1-60` or `cut -c1-80`, so the lead mostly saw only the last line. In `CLI_TICK_NO_COMMIT_REF` the last line is the usage template `'commit:<sha> <evidence>'`, and the vocabulary sits on line 1 and 2. That is why the same wrong reason was sent again after 5 minutes.

**Root cause.**
- `.claude/hooks/stop/worklist.py:1518-1530`: the `--tick` arm tests `CK.completion_evidence` first and dies with `M.CLI_TICK_NO_EVIDENCE`. It reaches `commit_ref_problem` (`.claude/hooks/stop/worklist.py:1269`) only after that gate passes. A refusal therefore reveals one gate at a time.
- `.claude/hooks/stop/worklist_messages.py:1653-1667`: `CLI_TICK_NO_EVIDENCE` lists seven accepted evidence shapes and never mentions `commit:` or `nocommit:`.
- `.claude/hooks/stop/worklist.py:1256-1262`: `CLI_TICK_NO_COMMIT_REF` puts the reason vocabulary in its first two lines and a bare template on the last line.
- R20260924.8 and R20260924.21 added the evidence shapes and the ASKED hint, but only to the first gate.

**Fix.**
- Compute both gate verdicts before refusing, and print every unmet requirement in one refusal.
- Put the two forms on the final line of both messages: `'<evidence> commit:<sha>'` and `'<evidence> nocommit:no-tracked-change|research|operator-deferred'`.
- Keep the ASKED hint on both refusals.
- Keep the refusal ledger rows as they are (`no-evidence` and `no-commit-ref` stay distinct), and add the gates that were also unmet to the row.

## 2. A decision-only tick has no honest commit reason, so the lead attached an unrelated HEAD

**What happened.**
- #6c63dfb8 and #51d75260 record operator /ask decisions, and the follow-up work is tracked as #11c0d336. There is nothing to commit for them.
- None of `no-tracked-change`, `research` and `operator-deferred` describes "the operator decided, the work is tracked elsewhere". The lead tried `nocommit:operator` twice (16:53:48 and 16:58:33), and `nocommit:recorded` once on #51d75260 (line 3298).
- It closed both at 16:58:45Z (line 3328, offset 7673292) with `commit:$h decision only`, where `$h` is `git rev-parse --short HEAD`. That was the unrelated commit ccb55d69a, "point renet at 43f0795".
- The commit gate is documented as shape-only (`.claude/hooks/stop/worklist.py:1250`, "Shape-only beside the door gate"), so a decorative sha passes.
- The evidence for these ticks, a verified `ASKED:` minute, is already stronger than the commit reference.

**Root cause.**
- `.claude/hooks/stop/worklist.py:1254`: `NOCOMMIT_REASONS` has three entries and none covers an operator ruling.
- `.claude/hooks/stop/worklist.py:1281-1285` (`commit_ref_problem`): a named `door:` stands in for the commit reference, but a verified `ASKED:` does not, although `wl_checks._asked_in_transcript` (`.claude/hooks/stop/wl_checks.py:363`) already verifies it.

**Fix.** Let an `ASKED:` that `_asked_in_transcript` verifies stand in for the commit reference, the way a named door does. A malformed or unmatched ASKED still fails the evidence gate as before. Do not add a free-text reason.

## 3. `--state` reports one shape verdict per attempt

**What happened.** The lead wrote its session state because the context was nearly full (line 4313, offset 10428297). The four refusals came 4 to 6 s apart:
- 19:40:34 (line 4321, offset 10431544): `agent/45048a90/` does not exist, and the tool never creates it.
- 19:40:38 (line 4330, offset 10447488): `unfocused`, no `## Big pieces` section.
- 19:40:44 (line 4338, offset 10463511): `bloated`, 4320 chars against a maximum of 4000.
- 19:40:49 (line 4352, offset 10481814): `bloated`, 4004 chars.

The write was accepted at 19:40:54 (line 4356, offset 10487797). The body had the Big pieces problem all along, but the size problem masked it. Then the size fix overshot by 4 characters.

**Root cause.**
- `.claude/hooks/stop/wl_store.py:2576-2606` (`agent_state_shape`): it returns on the first failing test, in the order thin, bloated, aimless, waitled, unfocused. A body with two problems reports one.
- `.claude/hooks/stop/worklist.py:2699`: the `--state` arm calls it once and refuses.
- The overage is not named, only the totals.

**Fix.**
- Add `agent_state_problems(body)` that returns every failing verdict.
- Have `--state` print all of them, with the number of characters over the cap.
- Keep `agent_state_shape` returning the first verdict, because `.claude/hooks/stop/wl_store.py:2805` and the guard use it.
- Leave the no-dir refusal as it is. `--state` NEVER creating the directory is a deliberate rule (`.claude/hooks/stop/worklist_messages.py:938`), but the refusal can sit in the same list.

## 4. The unread-reports block does not say how to list or mark the reports

**What happened.**
- At 13:23:51Z the Stop hook blocked on 18 unread reports (line 1262, offset 3782580). All 18 were captured by the predecessor session d778be9d, 3.4 to 18.6 h before the stop. The report store shows 1201 of the 1211 reports on branch 1023-1 since 2026-10-23 are d778be9d's.
- All 18 were under the 24 h `_foreign_and_stale` cut (`.claude/hooks/stop/wl_report.py:317`), so the block was correct. Opening a session on a predecessor's unread reports is the documented design.
- The cost was in finding the commands:
  - Line 1274 (offset 3808518): `wl_report.py --help` answered `unknown mode --help`.
  - Line 1280 (offset 3839096): `wl_report.py --unread` answered `unknown mode --unread`.
  - Line 1290 (offset 3846445): `--list 45048a90` ignores the positional argument and printed the whole branch index, 1201 lines.
  - Line 1295 (offset 3864432): a one-liner filtered the unread ids and marked 18 read.
- The lead read 3 of the 18 bodies, `head -25` each, and judged the others from their one-line titles (its message at line 1299, offset 3871255). That took 27 s and 4 calls.

**Root cause.**
- `.claude/hooks/stop/worklist_messages.py:606-614` (`N_UNREAD_REPORTS`) gives `--show <id>` and `--read <me> <id>...` but not the listing command.
- `.claude/hooks/stop/wl_checks.py:5158` writes `(%d older not shown)` with no command. The sibling text at `.claude/hooks/stop/wl_report.py:691` does say `--list --unread for all`.
- `.claude/hooks/stop/wl_report.py:1233` answers an unknown mode with one line and no usage. The usage line (`.claude/hooks/stop/wl_report.py:1029-1038`) prints only when there are no arguments.
- `.claude/hooks/stop/worklist.py:3282-3291` already has a `--reports` shortcut that lists unread reports, and the message never names it.

**Fix.**
- Add `list unread: worklist.py --reports` to `N_UNREAD_REPORTS`.
- Add the same command to the `older not shown` line at `.claude/hooks/stop/wl_checks.py:5158`.
- Make an unknown mode in `wl_report.py` print the usage line.

## Decisions

- **R20261101.1 (both gates in one refusal).**
  - DEFAULT: both gates are evaluated and named together, and the final line carries both forms.
  - WHY: 9 ticks were refused on 3 items. The hook behaved as designed on every one, but each refusal showed only the next gate.
  - HOW: restructure the `.claude/hooks/stop/worklist.py:1518-1530` block, and edit the two messages in `worklist_messages.py` and `.claude/hooks/stop/worklist.py:1256`.
- **R20261101.2 (verified ASKED stands in for the commit reference).**
  - DEFAULT: it stands in, but only for ASKED text that `_asked_in_transcript` verifies.
  - WHY: otherwise a decision-only tick must cite an unrelated commit, which is worse evidence than the operator's answer. Adding a reason such as `nocommit:decision` would accept free assertion, so it is not proposed.
  - HOW: pass the lead transcript into `commit_ref_problem`.
- **R20261101.3 (all `--state` problems at once).**
  - DEFAULT: `--state` prints all of them.
  - WHY: 4 refusals in 20 s while the context was nearly full.
  - HOW: `agent_state_problems` returns the list, and `agent_state_shape` keeps its signature.
- **R20261101.4 (name the listing command).**
  - DEFAULT: the block names `--reports`.
  - WHY: this is 4 calls at one block, the cheapest and lowest-value of the four, but the fix is one line of text.
  - HOW: edit the message and the older-not-shown line, and make the unknown mode print usage. Do not add a read-all verb, since bulk-marking already costs only one line of shell.
- **Not proposed.**
  - The `roster-dead` block (it was right).
  - The `damage-verb` admission (ledger-only, no cost).
  - The `wake-timer` block (outside the range).
  - The lead's own habit of piping refusals through `tail -1 | cut`. The hook cannot change that, so R20261101.1 moves the vocabulary to the last line.

## Sequencing

1. R20261101.1 first. It changes the `--tick` arm and both messages.
2. R20261101.2 next. It touches `commit_ref_problem` in the same function, so it follows .1 rather than racing it.
3. R20261101.3 and R20261101.4 are independent of the tick work and of each other. They can run in parallel with .1.

## Tasks

- [ ] **R20261101.1** `--tick` evaluates the evidence gate and the commit-reference gate together, names every unmet requirement in one refusal, and ends both refusal messages with a line carrying the `commit:<sha>` and `nocommit:<no-tracked-change|research|operator-deferred>` forms. Test: .claude/rediacc_hooks/tests/test_wl_tick_commit_ref.py.
- [ ] **R20261101.2** A verified `ASKED:<minute>Z` stands in for the commit reference on a `--tick`. An ASKED that matches no AskUserQuestion answer still fails, and a `nocommit:` word outside the three reasons is still refused. Test: .claude/rediacc_hooks/tests/test_wl_tick_commit_ref.py.
- [ ] **R20261101.3** `worklist.py --state` reports every failing shape verdict (and the overage in characters) in one refusal, while `agent_state_shape` keeps returning the first. Test: .claude/rediacc_hooks/tests/test_wl_state_document.py.
- [ ] **R20261101.4** The unread-reports block, and its `older not shown` line, name `worklist.py --reports`, and `wl_report.py` prints its usage line on an unknown mode. Test: .claude/rediacc_hooks/tests/test_wl_report_inbox.py.

### Critical Files for Implementation
- /home/developer/console/.claude/hooks/stop/worklist.py
- /home/developer/console/.claude/hooks/stop/worklist_messages.py
- /home/developer/console/.claude/hooks/stop/wl_store.py
- /home/developer/console/.claude/hooks/stop/wl_checks.py
- /home/developer/console/.claude/hooks/stop/wl_report.py
