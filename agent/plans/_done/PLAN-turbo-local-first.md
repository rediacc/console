# PLAN: turbo = local-first (one push, one PR, one CI cycle per batch)

Status: done -- 2026-10-08, every box ticked; was approved -- operator 2026-10-08: "when turbo is enabled, I'd lean to complete the plans locally since CI checks slow downs. Let's check the current system and adjust it." and, on the same day, "there should be a plan to implement, implement it first!" <!-- style-ok -->
Depends-On: no-dep -- extends agent/plans/PLAN-stop-hook-turbo.md (all boxes ticked) rather than waiting on it
Owner: d778be9d
First-Seen: 2026-10-08
Priority: P0 -- the operator's direct order; each early push costs a full CI cycle per commit batch
Concurrency: parallel -- three writers with disjoint files (Tasks)
Owns: .claude/hooks/stop/wl_planqueue.py, .claude/rediacc_hooks/plan_gate.py, .claude/hooks/stop/wl_prscope.py, .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/worklist_messages.py, .claude/hooks/stop/wl_judge.py, .claude/hooks/stop/wl_loopspeed.py, .claude/hooks/stop/worklist.py, .claude/hooks/post-bash/arm_ci_watch.py, CLAUDE.md, .claude/output-styles/standing-orders.md, .claude/rediacc_hooks/guards/block_settled_questions.py, .claude/skills/pr-epics/trailers.md, .claude/agents/pr-babysitter.md, .claude/commands/pr-merge.md, agent/plans/QUEUE.md
Worklist: #7afa92f1

The design below is the opus Plan agent's (2026-10-08). Its line citations were read at that time, and the writers re-verify them (rule 3).

## Tasks

- [x] LF-min W2+W1: the minimal first step. wl_checks.loop_next_text's no-PR arm returns the N_TURBO_LOCAL advisory under turbo while the batch is not ready, and wl_prscope.done() computes the no-PR plan set under turbo (D1). Tests LF1 and LF3 with their controls.
    (ticked) 2026-10-08 by d778be9d: bbb1e6146 (wl_prscope no-PR batch + N_TURBO_LOCAL advisory; LF1/LF3 with controls)
- [x] LF-W1 settings and model: `turbo_push: batch-end|pr` and `backup_push_h` in wl_planqueue SETTINGS_KEYS, plan_gate defaults, and `plan_gate.batch_body`. Tests LF3 and LF7 in test_wl_queue_settings.py and test_wl_prscope.py.
    (ticked) 2026-10-08 by d778be9d: bbb1e6146 (settings keys, plan_gate.batch_body, LoopState fields; LF3/LF7) and eea06d5d1 (plan_gate._read non-UTF-8)
- [x] LF-W2 stop arms: D2 (N_TURBO_LOCAL / V_LOOP_NEXT_BATCH_OPEN with the batch-end checklist), D3 (turbo-next silent on a live batch-end PR, firing on a no-PR branch), D4 (receipt-behind and N_RECEIPT_EARLY silent on a no-PR batch, plus the new backup-push advisory in wl_loopspeed), D6 (the judge paragraph and the conditional FORBIDDEN_ORDERS), and `worklist.py --batch-body <me>`. Tests LF1, LF2, LF4, LF5 and LF8, plus the mutation control.
    (ticked) 2026-10-08 by d778be9d: bbb1e6146 (D2/D3/D4/D6, --batch-body; LF1/LF2/LF4/LF5/LF8 + mutation; 431 passed), 05b3ac110 (mypy narrowing), c77ca9465 (N_RECEIPT_EARLY quiet in post-bash)
- [x] LF-W3 post-bash and prose: D5 (arm_ci_watch arms nothing with no open PR, test LF6) and D7 (the CLAUDE.md rule-1 sentence and its mirrors, the block_settled_questions MESSAGE with its re-frozen golden, QUEUE.md header and Settings bullets, the PLAN-stop-hook-turbo D5/D8 "superseded under batch-end" note). The lead runs gen:docs.
    (ticked) 2026-10-08 by d778be9d: 9ef3ab0b4 (arm_ci_watch no-PR skip, LF6 41 passed; rule-1 sentence and its mirrors; golden 104 passed)
- [x] LF-guard (operator 2026-10-08): a pre-bash guard `block_turbo_early_push` refuses `git push` and `gh pr create` while (a) `turbo: on` and (b) any plan under QUEUE.md `## Promoted` still has an open box, unless (c) the command declares an operational reason (`TURBO_PUSH_REASON=<kind>:<why>` prefix; kinds: `ci-cd` the plan needs a CI/CD-only check, `red-fix` a fix for a red on the live PR, `deadline` production or CD state that cannot wait, `backup` only when the oldest unpushed commit is older than `backup_push_h`, verified by the guard). Each admitted reason is appended to agent/ledgers/turbo-push-reasons.jsonl; a bare or unknown reason is refused.
    (ticked) 2026-10-08 by d778be9d: c315dc38b (block_turbo_early_push, 44 cases, planted defect red; refuses git push origin 1008-1 on the real tree)
- [x] LF-live: on branch 1008-1 with no PR, a real Stop shows the N_TURBO_LOCAL advisory rather than "Open it", and `worklist.py --batch-body d778be9d` prints a body whose `Plan:` line names the batch.
    (ticked) 2026-10-08 by d778be9d: the real Stop hook on 1008-1 printed "TURBO LOCAL-FIRST: 37 commit(s) on 1008-1 are held locally; batch 0/3 finished" instead of "Open it", and worklist.py --batch-body d778be9d printed "Plan: agent/plans/PLAN-turbo-local-first.md" (2026-10-08)

## Evidence: what forces or nudges an early push

1. **The "Open it" block (this is the only hard block).** `.claude/hooks/stop/wl_checks.py:2632-2639`: on a no-PR branch with any commit ahead of `origin/main`, the hook returns `V_LOOP_NEXT_NO_PR_OPEN` (`.claude/hooks/stop/worklist_messages.py:2812-2818`: ci:quick, push, `gh pr create --draft`) as a block. It never checks `state.turbo`. The block becomes advisory only while a background task runs or CI is pending (`.claude/hooks/stop/wl_checks.py:4494-4502`). This is the "20 commit(s) ... Open it" message.
2. **Turbo needs a PR to work at all.**
   - In `.claude/hooks/stop/wl_prscope.py:180-185`, `done()` computes `plans` and `finished` only for LIVE or UNREADABLE. On a no-PR branch the plan set is empty.
   - So `wl_planenforce` stays silent (`.claude/hooks/stop/wl_planenforce.py:3`: "An empty scope (… no PR yet) is silent").
   - `turbo_next_text` returns nothing unless the PR is live (`.claude/hooks/stop/wl_checks.py:2673`). `LOOP_NEXT_TURBO` says "once the branch's PR is open" (`.claude/hooks/stop/worklist_messages.py:2841-2843`).
   - `batch_ready` (`.claude/hooks/stop/wl_prscope.py:140-144`) is consulted only on a live PR (`.claude/hooks/stop/wl_checks.py:2645-2646`).
   - Result: under turbo, no batch can form until a PR exists. That is the structural push for an early PR.
3. **Plans join only through a pushed PR body.** `.claude/hooks/post-bash/refresh_pr_body.py:2,128` fires only on `git push` and appends `turbo_named` plans to an existing PR. `plan_gate.record_turbo_named` and `turbo_named` (`.claude/rediacc_hooks/plan_gate.py:449-485`) are local and already keyed by branch.
4. **Advisories, never blocks** (`.claude/hooks/stop/wl_checks.py:4229-4280`; focus releases them, `.claude/hooks/stop/wl_standdown.py:165`):
   - `receipt-behind` (`N_RECEIPT_BEHIND`, `.claude/hooks/stop/worklist_messages.py:1435`)
   - `ci-hold` ("hold these %d local commit(s) until it settles", `:1440`)
   - `N_RECEIPT_EARLY` (`:1450`, "a stop with unpushed commits" counts as push-due)
   - `.claude/hooks/post-bash/loop_speed_note.py:60-73` on push.
5. **The 2-hour rule exists only as prose.** No hook measures it. It appears in:
   - `CLAUDE.md:22`
   - `.claude/output-styles/standing-orders.md:13`
   - `.claude/rediacc_hooks/guards/block_settled_questions.py:113` (and its golden at `tests/goldens/block_settled_questions.jsonl`)
   - `.claude/skills/pr-epics/trailers.md:37`
   - `.claude/agents/pr-babysitter.md:100-101` ("a stop with unpushed commits" counts as push-due)
   - `.claude/commands/pr-merge.md:340`
6. **The judge.** `JUDGE_PROMPT` (`.claude/hooks/stop/worklist_messages.py:2000-2032`) does not ask for a PR. It already says "leaving it unpushed is almost always available". It does read the hook's own LOOP NEXT block text, though, so it echoes "open it". `FORBIDDEN_ORDERS` (`.claude/hooks/stop/wl_judge.py:1034-1041`) strips merge, push-main and release orders, but not "push / open the PR".
7. **Push guard.** `block_unverified_push` requires a `ci:quick` receipt for any push, and refuses a live branch that is behind `origin/main`. Neither forces a push. A backup push still needs a receipt, which is cheap because receipts are incremental.
8. **Focus and wake.** Focus is tied to a PR number (`wl_standdown.pr_token`), so it is inert with no PR. `wl_wake`'s 2-hour figure (`.claude/hooks/stop/wl_wake.py:29`) is the harness timer ceiling, not a push rule.

**CI triggers.** `ci.yml` `on:` is `push: branches: [main]`, `pull_request: [opened, synchronize]`, schedule and dispatch. No workflow runs on a push to a non-main branch (`ci-obs-mirror` and `ci-vm-bake` are main-only too). ci.yml has no draft filter, so a draft PR runs the full CI.
- **A plain `git push -u origin <branch>` with no PR triggers no CI.** That is the backup valve.
- One side effect to check: `arm_ci_watch.py` arms a `ci-trace --wait` on any push of the live branch, even with no PR. It must skip when there is no open PR.

**What local runs cannot cover (only CI does):**
- The VM E2E matrix across 5 distros: `tests`, `ops-tests`, `elite-run-test`, `breakpoint-lifecycle`. The e2e-local recipe covers one distro or suite on the KVM fleet.
- `build-renet`, `build-docker`, `build-devcontainer`, `build-cli`, `package-tests`, `update-flow-test`.
- `validate-install` / `validate-promote` (install matrix).
- `deploy-preview` and `smoke-test-preview` (cloud), `stripe-sandbox`.
- `check-release-state`, `review-gate`, and the `ciOnly` gates (`scripts/ci-runner/manifest.ts:792`).
- PR-event gates: P-A1 reads the PR body at the `opened` event (`.ci/scripts/quality/check_plan_implementation.py:179`), plus the PR-description freshness check.

## Design

**Settings** (`wl_planqueue` BOOL/INT/SETTINGS_KEYS, `plan_gate._default_settings`, QUEUE.md bullets):
- `turbo_push: batch-end | pr` (default `batch-end`, read only when turbo is on). `pr` keeps today's behaviour exactly.
- `backup_push_h: <int>` (default 4; 0 turns it off). This is the safety valve: when the oldest unpushed commit is older than this, the hook advises a backup push without a PR.

**D1. A local batch on a no-PR branch.** When turbo is on with `batch-end`, `done(NO_PR)` builds a body with `plan_gate.with_plan_line("", head, turbo_named(top, branch))` and computes `plans`, `prereqs` and `finished` exactly as for a live PR. The batch is the queue head plus every plan the hook has named for this branch.
- `wl_planenforce` then blocks on the batch's boxes with no PR, which restores the drive to keep working.
- `turbo_picks` uses `in_set=state.plans` for the no-PR state.
- `turbo_next_text` also fires on a no-PR branch, with message wording that has no PR number.
- `record_named` keeps the record per branch.

**D2. Loop-next on a no-PR branch under batch-end.**
- If the batch is not ready (`batch_ready(state, no open box in the set)` is false): return `(N_TURBO_LOCAL, False)`, an advisory. It reads: "TURBO LOCAL-FIRST: N commits held locally; batch k/batch_size finished; no push or PR until the batch completes."
- If the batch is ready: block with `V_LOOP_NEXT_BATCH_OPEN`, which lists, in order:
  1. `npm run ci`, a whole-lane run using incremental carry.
  2. The `--only` reruns for every gate in the receipt's `droppedTouched`.
  3. The e2e-local `--test` runs for touched lanes (and `--narrow` once PLAN-gate-scheduling-learned T8 lands).
  4. `git push -u origin <b>`.
  5. `gh pr create --draft --body-file`, using a body printed by a new verb `worklist.py --batch-body <me>`. This writes the full `Plan:` line at creation, because `refresh_pr_body` never runs on `gh pr create` and P-A1 reads the body at the `opened` event.

**D3. Live PR under batch-end.** The batch is closed. `turbo-next` stays silent, so no new plan joins the PR during the CI cycle; the writers' slots go to fixing reds. `pr-finish` and loop-next MERGE work as today.

**D4. Advisories.**
- `receipt-behind` and `N_RECEIPT_EARLY` are silent on a no-PR branch while the batch is incomplete.
- `ci-hold` is unchanged (it only applies once a PR is live).
- New `backup-push` advisory (in `wl_loopspeed`): fires when the oldest commit in `origin/<b>..HEAD` (or `origin/main..HEAD` if the branch was never pushed) is older than `backup_push_h`. It reads: "back up with `git push -u origin <b>` (no PR, so no CI run); never `gh pr create` before the batch completes." The reason it exists: the commits live only on this disk, and the valve bounds how much work a lost disk or a stopped session can cost.

**D5. Post-push.** `arm_ci_watch.py` arms nothing when the branch has no open PR. `refresh_pr_body` is unchanged.

**D6. Judge.**
- Add one paragraph to `JUDGE_PROMPT` when `turbo_push=batch-end` and the batch is incomplete: "unpushed commits and no PR are the intended state; never advise push, PR or CI before the batch completes; advance the batch's boxes."
- Add conditional `FORBIDDEN_ORDERS` patterns `\bgh\s+pr\s+create\b` and `open (a|the) (draft )?PR`, applied only in that state.

**D7. Prose.**
- `CLAUDE.md:22` becomes: "Pushes are backups and CI triggers, never one per commit: at an epic milestone, at least every 2 hours of committed work, and before a stop that leaves unpushed commits. **Under `turbo: on` with `turbo_push: batch-end` (the default) the batch is verified locally and pushed once when it completes; until then only a backup push with no PR is allowed, when `backup_push_h` fires.**"
- Mirror that wording in `.claude/output-styles/standing-orders.md:13`, `.claude/skills/pr-epics/trailers.md:37`, `block_settled_questions.py` MESSAGE plus a re-frozen golden, `.claude/agents/pr-babysitter.md:96-101`, `.claude/commands/pr-merge.md:340`, `LOOP_NEXT_TURBO`, and QUEUE.md's header and `## Settings` bullets.
- Amend PLAN-stop-hook-turbo D5 and D8 with a "superseded by D1-D3 under batch-end" note. Run gen:docs.

**Risk.** One big CI cycle can surface several reds at once, and the watchdog cancels the rest of the matrix after the first failure. Mitigations:
- The batch-end checklist above: full `npm run ci`, `droppedTouched` reruns, e2e-local for each touched lane.
- PLAN-gate-scheduling-learned's ledger, `--narrow` and stage-red streaming for targeted re-runs.
- Carried reds stay explicit (`carried-reds.json`).
- Writers sit idle on new plans during the roughly 50-minute cycle. That is accepted, because the one-branch rule forbids starting the next batch elsewhere.

## Tests (each fails without its change)

All of these go in `test_wl_prscope.py` and `test_wl_loop_next.py` (same shard, `.ci/config/shards/quality-pytest.json:208`), `test_wl_queue_settings.py`, `test_wl_loopspeed.py`, and the post-bash tests.

- **LF1.** Turbo, batch-end, no PR, 5 commits, batch 1/3: loop-next is advisory and the stop is allowed. Controls: `turbo_push: pr` blocks with "Open it"; turbo off blocks.
- **LF2.** Batch ready on a no-PR branch: blocks with `V_LOOP_NEXT_BATCH_OPEN`, and the printed body names every batch plan.
- **LF3.** No-PR state with named plans gives `plans` equal to the queue head plus the named plans. Control: turbo off gives `()`.
- **LF4.** `turbo-next` names picks on a no-PR branch, and is silent on a live batch-end PR. Control: `pr` mode names picks on the live PR.
- **LF5.** `backup-push` fires above `backup_push_h` and is silent below it or when set to 0.
- **LF6.** `arm_ci_watch` with no PR arms nothing. Control: with a PR it arms.
- **LF7.** The settings parser accepts the new keys and rejects bad values (RQ-SETTINGS finding).
- **LF8.** The judge sanitiser removes "gh pr create" in batch-end, and keeps it in `pr` mode.
- **Mutation control.** Force `turbo_push` to always read `pr`, and LF1 and LF2 must go red.
