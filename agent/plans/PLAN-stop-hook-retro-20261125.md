Status: ready
Depends-On: no-dep -- stop-hook retro fixes stand alone; R20261125.5 lands after R20261117.2-.4 per its sequencing note
Priority: P2 -- stop-hook friction, five measured causes of lost turns
Concurrency: parallel
Owns: .claude/hooks/stop/wl_review.py, .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/wl_store.py, .claude/hooks/stop/wl_writersnow.py, .claude/hooks/stop/wl_judge.py, .claude/hooks/post-bash/review_commit.py, .claude/rediacc_hooks/tests/**
First-Seen: 2026-11-25
Owner: d778be9d (adopted from retro plan-agent 20261125)
Updated: 2026-11-25

# PLAN: Stop-hook retro, 2026-11-25 (band early, lead session d778be9d, tracking #deda0678)

**Scope.** This retro covers lead transcript bytes 1747609620 to 1918359412 of `d778be9d-a8e6-4b88-a419-e8a03e7e9888.jsonl`, from 2026-11-17T20:03Z to 2026-11-25T01:59Z.

The blocklog (`/tmp/claude-worklist/home_developer_console.blocklog-d778be9d.jsonl`, its last 427 rows) holds 427 blocked stops from 2026-11-17T20:06:58Z to 2026-11-25T01:19:37Z. The transcript holds 430 matching `Stop hook feedback` user turns. The blocks were led by:
- judge 192 (193 continue verdicts, 4 sweep demands, 3 proof demands)
- worktree-unlanded 40, roster-dead 40, commit-review 32
- plan-unimplemented 15, agent-state 15, bg-orphan 14, idle-capacity 14
- wake-timer 12, open-items 9, writers-now-due 7
- ladder-gone 5, ci-red 5, plan-box-owed 5
- defer-expired 4, wisdom-due 4, bg-report 3, unread-reports 3
- loop-next 2, ready-ticks 2
- judge-unavailable 1, deferred-finding 1, agent-pushback 1, defer-audit 1

By day:

| Day | Blocks |
|---|---|
| 11-17 | 37 |
| 11-18 | 161 |
| 11-19 | 105 |
| 11-20 | 23 |
| 11-21 | 42 |
| 11-22 | 1 |
| 11-24 | 53 |
| 11-25 | 5 |

Other ledgers in the window:
- 31 hint proposals
- 23 admissions
- the tick-refusal rows the brief lists

**Fixed before or during this window, not re-ranked:**
- **Judge continues resting on omitted ids.** 75 of the 192 continue verdicts cite MISSING IDS or tracked ids the message never names. The last one was at 2026-11-20T03:20:36Z. J1 (e60b367ffd, 2026-11-23) removed that fact, and `grep "MISSING IDS" .claude/hooks/stop/*.py` is now empty. This supersedes R20261117.1, and PLAN-stop-hook-store-status X1 records that.
- **Review finding named only in an item's note.** On 11-21, 6359c982.1 blocked 31 stops between 14:40:02Z and 15:35:19Z (1878513023 to 1881137103). At 14:51:53Z (1879672571) the lead leased #c276a9df to the live shell b0dltogiw with a note naming the finding, and the blocks went on. Back then the stand-down read only the item text. 038dd3d737 (2026-11-23) makes `review_items` (`.claude/hooks/stop/wl_checks.py:1765-1779`) read the text, the last note and the lease note. Friction 1 covers what remains.
- **Writers that die on `API Error: No response from API` with no SubagentStop** (lead context 3). Covered by e31b42fa63 and `.claude/hooks/stop/wl_roster_resume.py`, measured on agent a7795c6bbb38b95da.
- **check_plan_folders F3 against `--sweep`** (context 5). Fixed by b8e0d3ab91 (F3 holds).
- **require-testid against the Radix Select review fix** (context 6). The lead fixed it at 01:33Z (1917779349 onward). The sha was not re-read here.
- **writers-now-due inside the survey window** (context 1). fff4243468 moved the grace from 30 to 50 minutes. Friction 3 covers what that leaves.

**Already covered by open boxes, not re-proposed:**
- **Judge orders writers for items finished in a lease** (hints 2026-11-17T20:55Z, 23:03Z and 2026-11-19T19:40Z) and for items that wait only on a push-triggered proof (hint 2026-11-19T11:52Z). Covered by R20261117.2 and .3.
- **worktree-unlanded holding a deliberately parked renet lease, a drill or a ci:quick clone** (hints 2026-11-17T20:59Z, 21:01Z; 2026-11-18T08:01Z, 13:47Z). Covered by R20261117.6.
- **Wake-timer blocks** (12 led). Covered by R20261117.5.
- **roster-dead manual re-leases** (40 led). Covered by R20261122.1.

**Counted from the ledger only.** The transcript text for these was not read, so nothing is claimed about whether they were correct:
- idle-capacity 14 (12 on 11-19)
- plan-unimplemented 15
- bg-orphan 14
- ladder-gone 5
- ci-red 5 (11-20)
- plan-box-owed 5
- open-items 9
- bg-report 3, unread-reports 3

## Ranking by cost to the session

| Rank | Point | Count in this window | Turns lost | Already fixed by? |
|---|---|---|---|---|
| 1 | The commit-review block never names its own stand-down: put the finding id in the note of a `[>]` item leased to a live worker | 4 led blocks on 9a666914.1 (21:04:53Z to 21:14:39Z, 1911707465 to 1911994677), plus 1 more at 00:25:30Z (1915642406). The 31-block 11-21 burst is the same blind spot under the old code. | 5 stop turns. One wrong hint proposal ("no way to mark it in-flight", 1912028232). The 11-21 burst cost 31 turns over 55 min, 19 of them one-line "still waiting" replies (1879744551 to 1880761346). | Partly: 038dd3d737 reads the notes. The block text still offers only fixed, not-a-bug and waived (`.claude/hooks/stop/wl_review.py:2803-2810`). |
| 2 | agent-state forces a STATE.md rewrite whenever any owned item moves, and its text does not say that naming ids in `## Next action` keys freshness to those ids | 14 led blocks + 9 named on 11-24/25 | 33 `--state` rewrites totalling 78,129 command characters between 07:26Z and 01:59Z (1886994138 to 1918351937), about one every 34 min | no |
| 3 | writers-now-due judges a running survey by a timer, not by whether the survey agent is live | 5 wrong texts: 19:33:02Z and 19:43:57Z (round 8c010031, 34 and 45 min), 00:25:31Z, 00:26:42Z and 00:30:23Z (round 315bd55a, 35 to 40 min) | 5 turns | Partly: fff4243468 (grace 50 min). The measured worst survey is 48 min, so the margin is 2 min. |
| 4 | A `git commit` whose output goes through a filter fails silently on a commit-policy refusal and leaves the index staged | 1 incident. Commit at 01:13:54Z (1917079925) returned no output. A cherry-pick failed at 01:24:12Z (1917483812). | 14m26s, from 01:13:54Z to the recovered commit and `--quit` at 01:28:20Z (1917559166). Two regenerate-and-retry commits. | no |
| 5 | The judge orders AskUserQuestion while the operator is away (/awk). The pre-ask guard refuses that question, and the defer audit later rules the other way. | 1 judge continue at 22:40:06Z (1913793311), then 1 defer-audit block at 23:54:10Z (1915466134) | 2 turns, and one [?] judged twice in opposite directions | no |

## 1. The commit-review block hides the in-flight route it already honours

**What happened.**
- At 21:04:53Z the block named [high] 9a666914.1 (`scripts/ci-runner/gates.lock.json`). The lead had handed the finding to red-gate fixer adad7d5647ae0b548 by SendMessage. No leased item named the finding.
- Three more blocks followed: 21:05:44Z, 21:11:16Z and 21:14:39Z.
- At 21:14:32Z the lead wrote "a finding can't be marked as in progress with a live writer" (1911991274). It then filed hint 2026-11-24T21:14:49Z asking for a holder mechanism (1912028232).
- At 21:21:45Z, for an unrelated reason, it ran `--update d778be9d e32de9b1 'scope added: review 9a666914.1 class ...'` (1912152813). That item was leased to the live writer af57af2e30689c63f. The next block (21:25:19Z) was roster-dead. The finding had stood down.
- Same shape on 11-21: 31 blocks on 6359c982.1 with the finding named only in a lease note. That is the defect 038dd3d737 fixed later.

**Root cause.**
- The stand-down has existed since 63f9f96b3d (2026-10-15). `branch_state` moves a finding to `blocking_in_flight` when the text of a live `[>]` item names it (`.claude/hooks/stop/wl_review.py:2746-2747`). `stop_lines` then turns it into a note (`:3041-3042`, `:3068-3072`).
- The block prints only `mark_commands(f.id)` (`:3047`), which offers fixed, not-a-bug and waived (`:2803-2810`). The lead could not discover the route from the text it was given.
- Residual (hint 2026-11-21T14:46Z): a finding whose fix waits on a push-built artifact has no live worker once the gate run ends. The same route covers it when the item is leased to the CI watch task.

**Fix.** Add a fourth line to `mark_commands`:

```
in flight with a live writer: worklist.py --update <me> <its [>] item> '<finding-id> ...' (the finding waits as a note while that worker is live)
```

When the block names a finding and a live `[>]` item of this session exists, also print that item's id. Then the lead can run the command without looking it up.

## 2. agent-state re-demands STATE.md on every owned-item change

**What happened.**
- 14 led blocks and 9 named ones on 11-24/25, for example 14:09:13Z (1901478815). The text read: "stale (18 min old; your world signature moved)". <!-- style-ok -->
- The CHANGES block of that stop shows why: #f55c6a82 was ticked by a writer and #3a102a4c was added by a writer.
- The lead's rewrite at 14:09Z (1901508991) has a `## Next action` that names no item id.
- With 6 to 16 live writers, the owned set moves every few minutes. The lead rewrote and committed STATE.md 33 times in 18.5 h, for 78,129 command characters.

**Root cause.**
- `agent_state_status` (`.claude/hooks/stop/wl_store.py:3230-3253`) already keys freshness to the ids `## Next action` names, when it names any. Otherwise it falls back to the whole owned-item signature after `AGENT_STATE_STALE_MIN = 15` (`:80`).
- `_agent_state_because` (`.claude/hooks/stop/wl_checks.py:2346-2348`) says only "your world signature moved". It never tells the lead that naming `#ids` would make the document stale only once they close. <!-- style-ok -->

**Fix.**
- **(a)** When the stale verdict came through the signature branch (no ids named), append this to the reason: "`## Next action` names no #id, so any owned-item change stales it; name the ids of the next steps and it stays fresh until they close".
- **(b)** Count the ids under `## Delegated` (the `#<id>` tokens) as named, alongside `## Next action`. The 14:09Z document named 8 delegated ids, and none of them had closed.

## 3. writers-now-due counts a live survey as missing

**What happened.**
- Round 315bd55a started at 23:49:56Z. Its survey agent was still working when writers-now-due fired at 00:25:31Z, 00:26:42Z and 00:30:23Z ("not counted: survey never written within 30 min of the start", 1915850536).
- Round 8c010031 (18:58:51Z) did the same at 19:33:02Z and 19:43:57Z.
- fff4243468 measured surveys at 21, 28, 21, 23 and 48 min and set the grace to 50.

**Root cause.** `judge_round` (`.claude/hooks/stop/wl_writersnow.py:160-167`) reads only the file's existence against `SURVEY_GRACE_MIN` (`:30`). A survey slower than 50 min under load fires again, and the round's own leased survey item is never consulted.

**Fix.**
- `judge_round` takes a `survey_live` predicate. The caller (`.claude/hooks/stop/wl_checks.py:7080-7098`) passes True when a live background agent of this session has the round's survey path in its first prompt (the `claiming_prompts` reader at `:1782`), or when a `[>]` item naming the round id is leased to a live worker.
- A missing survey counts while `survey_live` holds. The 50-minute timer stays as the fallback when liveness is unknown.

## 4. A filtered `git commit` hides the policy refusal

**What happened.**
- At 01:13:54Z the lead committed the plan-folders sweep with `... 2>&1 | grep -E '^\[|BLOCK' | cut -c1-60` (1917079925) and got "(Bash completed with no output)".
- The git-level commit-policy hook had refused because the QUEUE.md and INDEX.md regions needed regenerating. Its text matched neither pattern. The deletions stayed staged.
- At 01:24:12Z, `git cherry-pick --continue` failed with "your local changes would be overwritten" (1917483812). The lead diagnosed it at 01:24:22Z (1917503945), regenerated, and committed c36f781dda at 01:27:38Z. <!-- style-ok -->

**Root cause.**
- The refusal lines start with `commit-policy:` (`.claude/rediacc_hooks/git/githooks.py:74`), which a filter for git's own `[branch sha]` success line drops.
- `.claude/hooks/post-bash/review_commit.py` already parses `git commit` at command position and knows that "a failed commit made no new sha" (its docstring), but it says nothing.

**Fix.** In `review_commit.py`, when the command ran `git commit` at command position, read HEAD before and after:
- The before value comes from the reviewer's per-repo last-seen sha, or from `ORIG_HEAD`-free `git rev-parse HEAD` cached by the pre-bash chain.
- When HEAD did not move and `git diff --cached --quiet` is non-zero, emit additionalContext: "COMMIT DID NOT LAND: HEAD is still <sha> and N paths are staged; rerun without the output filter to read the refusal".

## 5. The judge does not know the operator is away

**What happened.**
- At 22:33:09Z the lead parked the AP2, AP5, AP8 and AP9 deps-waiver decision until the operator returned (1913763528). The operator had been away since about 20:55Z.
- The judge answered continue: "Ask it now with AskUserQuestion. A deferred operator decision is not a wait." (1913793311).
- `block_away_questions` refuses exactly that question while /awk stands. So the lead parked it as a `[?]` with a DEFAULT (1913844327).
- 74 min later the deferral audit reopened it as session-decidable and ordered a writer (1915466134). The lead complied at 23:54:20Z.

**Root cause.**
- `.claude/hooks/stop/wl_judge.py` has no away fact. The only "away" in it is an unrelated comment (`:943`). Its rule treats every parked operator decision as an ask owed now.
- The away flag lives in `.claude/hooks/stop/wl_away.py` and is read only by the pre-ask guard (`.claude/rediacc_hooks/guards/block_away_questions.py:39-60`).

**Fix.**
- `_judge_facts` adds `OPERATOR AWAY since <ts> (AskUserQuestion is refused; a [?] with DEFAULT is the legal park)` when `wl_away.away(transcript)` is set.
- The settle chain reads a continue whose next_action demands AskUserQuestion while away as stop, unless the `[?]` lacks a DEFAULT.

## Decisions

- **D1 (friction 1).**
  - DEFAULT: extend the block text, with no new resolution state.
  - WHY: the stand-down exists and works (1912152813). The 5 surviving blocks and one wrong hint came only from not knowing about it.
  - HOW: a fourth line in `mark_commands`, plus the id of a live `[>]` item of this session when one exists.
- **D2 (friction 2).**
  - DEFAULT: message fix, and count the `## Delegated` ids as named.
  - WHY: id-keyed freshness already exists (`wl_store.py:3236-3245`). 33 rewrites in 18.5 h came from the unnamed-signature fallback.
  - HOW: `_agent_state_because` takes a `keyed` flag, and `next_action_ids` reads `## Delegated` too.
- **D3 (friction 3).**
  - DEFAULT: liveness first, timer as fallback.
  - WHY: a 2-minute margin over a load-dependent duration will fail again.
  - HOW: a `survey_live` argument to `judge_round`.
- **D4 (friction 4).**
  - DEFAULT: an advisory after the call, no pre-bash refusal of pipes.
  - WHY: piping output is legitimate everywhere else, and hint 2026-11-19T06:54Z already records pipe-after-git false refusals at the pre-bash guard.
  - HOW: `review_commit.py`, using the HEAD and index state it can already read.
- **D5 (friction 5).**
  - DEFAULT: away becomes a judge fact, and an ask demand while away is read as stop.
  - WHY: the judge and the pre-ask guard contradicted each other, and the defer audit then contradicted the judge.
  - HOW: `_judge_facts` and one settle rule in `wl_judge.py`.

## Sequencing

1. R20261125.1 and .2 first: they touch disjoint files and remove the most turns.
2. R20261125.3 and .4 are independent.
3. R20261125.5 touches `wl_judge.py`, which R20261117.2 to .4 also edit. Land it after those, or in the same writer.
4. R20261125.6 runs after .1 to .5 land.

## Tasks

- [x] **R20261125.1** Add the in-flight route to `mark_commands` (`.claude/hooks/stop/wl_review.py:2803-2810`): `worklist.py --update <me> <its [>] item> '<finding-id> ...'`. `stop_lines` (`:3043-3051`) names a live `[>]` item of this session when one exists. Fixtures: an open high finding with no naming item gives a block that holds the update line. Writing the id into a live item's lease note gives a note, not a block. The same note on a dead worker gives a block. Test: .claude/rediacc_hooks/tests/test_wl_review_deferrals.py.
    (ticked) 2026-11-25T03:29:19Z by d778be9d: landed 85ee5a2794; retro test files 79 passed rc 0, test-always-tier rc 0
- [x] **R20261125.2** `_agent_state_because` (`.claude/hooks/stop/wl_checks.py:2329-2348`) appends the "name the ids in `## Next action`" sentence when the stale verdict came through the signature fallback. `next_action_ids` also reads `#<id>` tokens under `## Delegated` (`.claude/hooks/stop/wl_store.py:3236-3245`). Fixtures: the 14:09Z body (8 delegated ids, all open) with a moved signature gives ok. Inverse: no ids anywhere and a moved signature gives stale with the new sentence. All named ids closed gives stale. Test: .claude/rediacc_hooks/tests/test_wl_agent_state_keyed.py.
    (ticked) 2026-11-25T03:29:20Z by d778be9d: landed 5be6080d1b; retro test files 79 passed rc 0, test-always-tier rc 0
- [x] **R20261125.3** `judge_round` (`.claude/hooks/stop/wl_writersnow.py:160-167`) takes `survey_live`. A missing survey counts while it holds. The caller at `.claude/hooks/stop/wl_checks.py:7080` derives it from live agent prompts naming the survey path, or from a live `[>]` item naming the round id. Fixtures: a round 55 min old with a live survey agent counts. The same round with no live agent gives `WHY_NEVER_WRITTEN`. A round 35 min old with no agent still counts (the timer fallback). Test: .claude/rediacc_hooks/tests/test_wl_writersnow.py.
    (ticked) 2026-11-25T03:29:21Z by d778be9d: landed ec1021d695; retro test files 79 passed rc 0, test-always-tier rc 0
- [x] **R20261125.4** `.claude/hooks/post-bash/review_commit.py`: after a command-position `git commit`, if HEAD is unchanged and the index holds staged paths, emit additionalContext "COMMIT DID NOT LAND ...", naming the staged count and asking for a rerun without the output filter. Fixtures: a commit refused by a failing pre-commit hook through `| grep '^\['` gives the notice. A successful commit gives none. `echo git commit` gives none. Test: .claude/rediacc_hooks/tests/test_post_bash_commit_landed.py.
    (ticked) 2026-11-25T03:29:22Z by d778be9d: landed 433dcdb5b4; retro test files 79 passed rc 0, test-always-tier rc 0
- [ ] **R20261125.5** `_judge_facts` (`.claude/hooks/stop/wl_checks.py`) renders `OPERATOR AWAY since <ts>` from `wl_away.away(transcript)`. A settle rule in `.claude/hooks/stop/wl_judge.py` reads as stop any continue whose next_action demands AskUserQuestion while away and the parked item is a `[?]` with DEFAULT. Fixtures: the 22:40:06Z verdict with the away flag set and #fe286806 deferred with DEFAULT gives stop. With no away flag it gives continue. While away, a `[?]` with no DEFAULT gives continue. Test: .claude/rediacc_hooks/tests/test_wl_judge_facts.py.
- [ ] **R20261125.6** After .1 to .5 land, re-count on the next window's blocklog and transcript. Record before and after for:
  - commit-review blocks on a finding a live writer holds (against 5);
  - agent-state blocks per 18 h (against 14 led) and `--state` rewrites per 18 h (against 33);
  - writers-now-due blocks while a survey agent was live (against 5);
  - silent failed commits (against 1);
  - judge AskUserQuestion demands while away (against 1).

  Test: .claude/rediacc_hooks/tests/test_wl_retro.py.

### Critical Files for Implementation
- /home/developer/console/.claude/hooks/stop/wl_review.py
- /home/developer/console/.claude/hooks/stop/wl_store.py
- /home/developer/console/.claude/hooks/stop/wl_writersnow.py
- /home/developer/console/.claude/hooks/post-bash/review_commit.py
- /home/developer/console/.claude/hooks/stop/wl_judge.py
