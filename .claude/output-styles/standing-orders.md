---
name: Standing Orders
description: The session defaults from CLAUDE.md, injected at system-prompt level so they survive compaction
keep-coding-instructions: true
---

# Standing orders for this repo

These are not suggestions and they are not per-task. They hold for every task, in this repo and its submodules, and the operator should never have to restate them.

## 1. Verified work is committed as it lands, on the one branch

Uncommitted work is not allowed to pile up into a mountain nobody can review. A verified unit (one purpose inside one epic, its acceptance check run with the exit code read, only paths this session owns) is committed right away with `git commit -F <msg> -- <paths>` and a `PR-TASK:` trailer, before the next unit starts; a worklist item is ticked with `commit:<sha>`. Writers never commit: the lead commits their spot-checked output. Pushes are separate: <!-- scope: pr.push-cadence -->at an epic milestone, at least every 2 hours of committed work, and before a stop that leaves unpushed commits. <!-- scope: pr.turbo-batch-end -->Under `turbo: on` with `turbo_push: batch-end` (the default) the batch is verified locally and pushed once when it completes; until then `block_turbo_early_push` refuses a push or `gh pr create` that names no operational reason, `TURBO_PUSH_REASON='<kind>: <why>'` with kind `ci-cd`, `red-fix`, `deadline` or `backup`, and a `backup` push, admitted once `backup_push_h` fires, opens no PR. A completed batch pushes and opens its PR with no reason; the hooks decide push timing, so it is never asked.

<!-- scope: pr.one-branch-one-pr -->One branch and one PR per repository, with no agent path to a second: `block_second_branch` and `block_second_open_pr` refuse it, and a second one is the operator's own `!` command. <!-- scope: pr.merge-condition -->`main` moves through the PR merge (`gh pr merge --rebase --auto` once every plan box is ticked, or the PR body carries an `Operational-Reason:` line, with CI Complete SUCCESS on the head, `wl_review.py --check` at exit 0 and the required Review Complete green), takes a commit only as a `[hotfix]` with a `Hotfix-Evidence:` trailer (pushed by the operator), and admits one direct push: <!-- scope: pr.ff-fallback -->the guarded fast-forward fallback `git push origin <branch>:main` for a PR GitHub cannot rebase, admitted only with CI Complete SUCCESS on the open PR's head and an `Operational-Reason:` line in its body (operator ruling 2026-10-02).

Do not ask permission for this. It is settled, and asking spends a round trip repeating a rule already written down. `.claude/rediacc_hooks/guards/block_settled_questions.py` (chain `pre-ask`) refuses such a question outright. If a decision genuinely belongs to the operator, park it as a worklist `[?]` carrying its own `DEFAULT:` and keep working.

## 2. Ask for the big-bang, not for permission to patch one thing

When findings cluster, do not propose the minimal patch and do not ask about them one at a time. Put the whole cluster into a single plan (root cause, siblings, tests, regenerated artifacts, submodules included) and ask to run that. The ask decides PACKAGING, never WHETHER the findings get fixed.

## 3. A finding is fixed in the session that finds it

A workaround is a bug report. Discovery is always in scope and so is the fix. Sweep the class, not the instance: before calling a bug fixed, look for its siblings. Filing an issue closes nothing.

## 4. Verification comes before the claim

Run the real thing and read stdout and stderr separately. A plan's claim about unread code is a hypothesis. Do not trust a report that has not been spot-checked, including a subagent's and this session's own from earlier. Name the gates that ran and the ones that were skipped, and never call a failure pre-existing without showing that none of its findings are in files this session
touched.

## 5. The commit is the safety net

Committed work survives; uncommitted work does not, and the tree usually holds uncommitted work from other sessions. Never `git checkout`, `restore`, `stash` or `clean` to undo a mistake of this session's own making; repair forward instead, with a new commit when the mistake is already committed (no amending).

## 6. The Stop hook runs at one effort level

How hard the Stop hook pushes is one `effort` level in `agent/plans/QUEUE.md` `## Settings` (`quiet` < `low` < `smart` < `high` < `ultra`), and `.claude/config/effort.json` says which check blocks or advises at each. The level is the operator's dial, not a way past a block; the FLOOR (the hook cannot see, CI red, a dead writer, an unread report, a wait with no wake-up timer) blocks at every level. A PR wind-down is a phase, `worklist.py --phase <me> babysit|merge`, which only parks work and ends with `--phase <me> build` or the merge.

The table tunes itself from outcomes, never from annoyance. Every check the hook emits is recorded in `agent/ledgers/effort-outcomes.jsonl` with what followed within 3 stops (work, paperwork, overruled or expired). Near compaction (85% of the auto-compact threshold) the hook asks once per context for the `effort-tuner` sub-agent, handed this context's rows and observations. A threshold changes only through it or through `worklist.py --effort-propose <me> <key> <verdict>@<level> '<evidence citing eo- rows>'`, never by editing `effort.json` by hand. Promotions apply with a report line, demotions wait for the operator's one batched /ask, and the FLOOR is never tuned (agent/plans/PLAN-stop-hook-effort-tuning.md).
