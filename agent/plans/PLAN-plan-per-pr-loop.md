# PLAN-plan-per-pr-loop: releases on every merge, AI-driven merges behind server-side protection, one live branch around the clock, one plan per PR, per-commit review

Status: approved -- operator rulings 2026-10-02 (PR #591), worklist #f2677b82 #7c70e8b9 #8306113e #aefc44a6 #17a2e92b
Depends-On: PLAN-ci-verdict.md#A -- merge decisions need a trustworthy green; boxes R1-R3, M6, B1 and V1 can start before it
Owner: d778be9d
Priority: P1 -- the operator's operating model for every PR after #591
Concurrency: parallel -- writers with disjoint file ownership per box group
Owns: .claude/rediacc_hooks/guards/block_push_to_protected_branch.py, .claude/rediacc_hooks/guards/block_git_force_push.py, .claude/rediacc_hooks/guards/block_second_branch.py, .claude/rediacc_hooks/guards/block_second_open_pr.py, .claude/rediacc_hooks/git/githooks.py, .claude/commands/pr-merge.md, .claude/agents/pr-babysitter.md, .github/workflows/promote-stable.yml, .ci/rediacc_ci/release/check_soak_period.py
Revalidated: 2026-10-23 @ daab83af1f31

<!-- preflight:begin -->
```text
preflight 2026-10-23 @ daab83af1f31
open boxes: 1 (partial 1)
citations: 0 unresolved, 2 drifted, 1 relocated
  relocated plan line 26: .claude/rediacc_hooks/git/githooks.py line 169-207 -> 187-225
overlap since dd9de2761f15: 68 commit(s) (first 30 shown)
  012529e6380d fix(release): the nightly drift waiver keys on step names derived from the upstream gates, and the t
  a89fe21367d7 chore(agent): publish the 1020-1 PR snapshot and record the session state
  9542b049d575 chore(agent): record the session state, ledgers and worklist events before the rebase onto main
  87fa76120c16 chore(agent): record session d778be9d's worklist, ledger and queue render before the main hotfix swi
  2d272d67d79e fix(hooks): /branch-rebase runs over the never-committed settings.local.json, and the ref hook tells
  33c328464cc6 refactor(ci): the App key's job-local alias is BWS_GITHUB_APP_PRIVATE_KEY, and secret-rename protect
  62ff4e271500 chore(agent): record session d778be9d's worklist, STATE and ledgers before the rebase onto main
  84e60433df78 fix(hooks): the merge phase's pointer-bump push needs no turbo reason
  ca717bcf8604 feat(ci): every job that reaches R2 installs the pinned aws CLI v2 and exports AWS_BIN
    plan agent/plans/PLAN-pin-awscli-toolchain-python-compatible.md
  0acb2a91de75 fix(www): the build writes its search index into the build output, and check:ci-gate-tree-writes fol
  68b5f243b41c docs: comments and docstrings state what the code does
  4c4f9ef7b582 fix(cd): Verify stable moves the production tag with the App token, which holds workflows:write
  2ee2d7713602 fix(hooks): guards drop their inline markers (DTZ, lazy-import and fail-open sites)
  cc7216720010 docs(hooks): guards, commands and the output style speak effort and phase
  19f231b2ed17 feat(hooks): one registry of generated artifacts, judged at commit time against the staged tree
  c004509a42d2 fix(ci): no-auto-cancel holds a failing run open but not a hung one, and the docs stop saying the la
  7892031862b8 chore(agent): session state names the second CI red and its fix, with the push time corrected
  3d8994ad6ae5 chore(agent): session records after the red-fix push of PR 600
  e892e9eba558 chore(agent): session state, worklist and the PR snapshot before the red-fix push
  a1fdeab00b00 chore(agent): session state, worklist and the PR snapshot after the first CI run of PR 600
  cf74c2800854 chore(agent): session state and worklist at the first window with no open review finding
  35b7f7434fa6 chore(agent): session state before the first push of 1008-1
  7964155b17df chore(agent): session state and hook ledgers before the rebase onto origin/main
  df3d4a783a53 fix(hooks): the hooks, not /branch-rebase's prose, refuse a remote branch delete, a forced or path c
  ff5d83bbc818 fix(ci): every remaining port prefixes its diagnostics and usage with its own module name, not a del
  0bc59b00d16a fix(commands): no command carries disable-model-invocation; /handoff and /standing-orders are invoca
  434b2b4e8897 feat(ci): check:ci-scope-mirrors holds the PR-scope rules in .claude's commands, agent, skills and o
    plan agent/plans/PLAN-scope-mirrors.md
  389b4135a24d refactor(ci): W11-B: common.sh is deleted, its call sites run Python, ~55 tests stop copying it, and
  fec2254c5c5e fix(ci): twenty-two ops review findings: subject runners prepend .ci to PYTHONPATH, a failed chain-s
  876d7b249019 docs(plans): the deferral plan ticks C1-C5 and L1-L5 and lands D1-D3, and PLAN-retire-bash-oracles g
    plan agent/plans/PLAN-deferred-findings-block-merge.md
    plan agent/plans/PLAN-retire-bash-oracles.md
dependencies: 1
  ok PLAN-ci-verdict.md#A -- task A is ticked
```
<!-- preflight:end -->

## Operator rulings (2026-10-02), condensed

1. Every merge to main may release; `bump-none` is not a default. Investigate the nightly edge->stable promotion and fix it in-session if missing or broken.
2. /pr-merge and /pr-babysit are AI-invokable. main moves through `gh pr merge <n> --rebase --auto`. A direct push to main is allowed to the AI only for the "branch can't be rebased" fallback, and only as a single-refspec, no-force fast-forward of the live branch tip that is the open PR's head with CI Complete SUCCESS on that sha (read through ci-trace), with the plan's boxes all ticked or an operational reason in the PR body. Server-side rulesets back this up (no force push, no deletion, linear history, CI Complete required; the bot bypasses only the PR requirement), shown to the operator as an exact diff once before applying. The live MMDD-N branch may be force-pushed with --force-with-lease only. "Operator-only main push" wording goes.
3. One live branch, 24/7: after a merge and branch deletion, the loop cuts the next MMDD-N from main; a genuine second branch stays refused.
4. One plan per PR (exceptions recorded in the PR body); implement boxes, commit and tick with sha, push verified batches with a receipt and ci-trace --wait, babysit in parallel, merge when every box is ticked and CI Complete is SUCCESS, then cut the next branch and start the next queued plan. #591 finishes as-is, stripe 23 included.
5. Per-commit haiku review through a Claude hook replaces PR-level Claude review (the Claude GitHub app is uninstalled); retire the PR-review dependencies that would stall the loop.

## Evidence (2026-10-02)

- Promotion exists: `.github/workflows/promote-stable.yml` (cron `0 6 * * *`, `workflow_dispatch force`, `workflow_run` on Console CI main). 57 of the last 60 runs are `schedule`, 3 `workflow_dispatch`, 0 `workflow_run`. Every run since 2026-09-15 skipped the deploy jobs: run 36863680473 printed "Edge version: 1.4.0 (released: 2026-09-30T05:28:45Z) / Edge release age: 1 days (soak: 7 days) / Edge needs 6 more day(s) of soak". Last real promotions: 2026-09-14 (schedule, run 34842203116) and 2026-09-05 (dispatch).
- The nightly waiver (`rediacc_ci.release.nightly_tested_edge`: a green scheduled Console CI on main whose head contains the edge commit skips the soak) never fires: the scheduled Console CI on main has FAILED every day from 2026-09-25 to 2026-10-01 (the last green on main is the 2026-09-30T04:44Z push run).
- Soak starvation: `check_soak_period` judges only the newest edge; with a release on every merge, the newest edge is almost always under 7 days old, so stable never promotes.
- Release decision: `.ci/rediacc_ci/ci/dispatch_release.py` (`SKIP_LABEL = "bump-none"` :73, `STABLE_LABEL = "release"` :75, fail-open doctrine :7); `ci.yml` initialize `--decide-only` gates the sentinel and the cd-v2 dispatch.
- Console ruleset 12344707 "Branch Protection": target `~DEFAULT_BRANCH` (main), rules `pull_request`, `required_status_checks` (strict; `CI Complete`, `Review Complete`, integration 15368 = GitHub Actions), `deletion`, `non_fast_forward`; no `required_linear_history`; bypass: RepositoryRole 5 (admin) always, Integration 2772000 always. renet, account and elite are private on GitHub Free: rulesets and branch protection return 403 (not available on the plan); homebrew-tap: none (404).
- `Review Complete` is posted by `review-status.yml` from the `<!-- claude-reviewed: <sha> -->` marker that `claude-review.yml` (Claude app) wrote; with the app gone no PR can satisfy it. `.claude/commands/pr-merge.md` (its finish-line bullet as of a8ee5bd09) and `.claude/agents/pr-babysitter.md` (its finish-line paragraph and loop step as of a8ee5bd09) require the marker and resolved threads. `agent/plans/PLAN-per-commit-review.md` (13 tasks) exists, held 2026-09-26, not implemented.
- Guards: `block_push_to_protected_branch` refuses every push to main (`!` only); git pre-push (`.claude/rediacc_hooks/git/githooks.py:187-225`) refuses main (COMMIT_POLICY_OK override); `block_git_force_push` refuses `--force-with-lease` too (mediated verb `worklist.py --git force-push <branch>`); `block_second_branch` decides consumed names from `gh pr list --state all` heads (:96); `block_second_open_pr` fails closed on gh errors; `block_admin_merge` bans `--admin`; `block_premature_ready` gates `gh pr ready` on CI Complete.

## Boxes

### Releases
- [x] R1 Find and fix the root cause of the scheduled Console CI on main failing every night since 2026-09-25 (trace each night's first real failure with ci-trace once PLAN-ci-verdict B lands; raw reads until then), so the nightly waiver can fire.
    (preflight) 2026-10-23 partial: R1 root cause found and fixed in code: OBS rebuilds the openSUSE Ceph package past the pin; private/renet 7070d28 bumps the pin to .105 and e28e2f8df/f8d184807 add the scheduled auto-bump. Remaining: one green scheduled Console CI run on main after the merge (#753d4fdc)
    (ticked) 2026-10-24T12:40:02Z by d778be9d: found and fixed on 1023-1 (investigation row 270c47ad7): the nightly on main 403f47b9 failed from six classes, not one: npm audit (83dfdb272, c9d5c7d1b, a54cd111e), OBS ceph rebuild (renet eb66a5d via 5f39f337c), pin freshness, deps freshness and plan housekeeping (already fixed on the branch), shard receipts (follows Code 3); the scheduled reader that hid them fixed in e9054dfa0..ce8c3fe1c. The first green scheduled run after the merge is still to come and is tracked by #cba857c9 (the nightly waiver cannot fire before it)
- [x] R2 Soak starvation: `check_soak_period` promotes the NEWEST edge release that is at least SOAK_DAYS old (walking back from the newest), not only the newest one; red-first test with three edges (1, 4, 9 days old -> the 9-day one promotes; 1 and 4 alone -> nothing).
    (ticked) 2026-10-02T09:40:59Z by d778be9d: commit:a004eb7d5 check_soak_period promotes the newest soaked edge (walk-back), red-first test with 1/4/9-day edges; R2 channel-snapshot limit is #51ea3682
- [x] R3 Release on every merge that changes the product: skill and doc text stops suggesting a hand-applied `bump-none` (pr-merge, pr-babysitter, release-process.md, ci-gates.md). The bump is decided once at a green head by Console CI's `pr-labels` job from the per-commit reviews: `bump-major`/`bump-minor` from the highest verdict, no label for a patch, and `bump-none` only when every commit's review says `none` (operator rulings 2026-10-02, #e1e9edf7). Verify dispatch_release's fail-open path on a real merge (M7).
    (ticked) 2026-10-04T16:08:24Z by d778be9d: commit:d16bc52d2 the pr-labels job decides the bump; no doc suggests a hand label; #592, #593 and #594 were auto-labelled and released v1.5.0 to v1.7.0

### Merge authorization and main protection
- [x] M1 /pr-merge and /pr-babysit AI-invokable: remove "only when the user asked" / "Only run when the user has asked" from `.claude/commands/pr-merge.md` and the pr-babysit skill, any frontmatter that disables model invocation, and every guard or hook message that enforces it.
    (ticked) 2026-10-02T10:59:31Z by d778be9d: commit:d164b94e1 /pr-merge and /pr-babysit AI-invokable; Who runs this paragraph
- [x] M2 `block_push_to_protected_branch` + git pre-push allow exactly the fast-forward fallback: single refspec `<live branch tip sha>:main` or `<live branch>:main`, no `--force`/`--force-with-lease`/`+`/`--delete`/tags/`--all`/`--mirror`; `git merge-base --is-ancestor origin/main <sha>` true; `<sha>` is the head of the open PR for the live branch; CI Complete SUCCESS on that sha read through `ci-trace.py` (never a raw read); the plan's boxes all ticked or the PR body has an `Operational-Reason:` line. Everything else to main stays refused; `block_commit_on_main` [hotfix] rule unchanged. Red-first EDGE_CASES for each condition, golden regen.
    (ticked) 2026-10-02T11:25:39Z by d778be9d: commit:74dbedc27 conditions a-d + git-level hook; commit:3c9dad656 condition e (plan boxes ticked or Operational-Reason); suites 71 cases 0 failures
- [x] M3 `block_git_force_push`: `--force-with-lease` (only that form, with or without an expected sha) is allowed to the single live MMDD-N branch, never main, never another branch, never `--force`/`+refspec`; red-first.
    (ticked) 2026-10-02T10:37:04Z by d778be9d: commit:74dbedc27 lease forms allowed only to origin and the live branch; --force/-f/+refspec/main/other branches refused; red-first on fixtures
- [x] M4 Server-side rulesets: console ruleset 12344707 gains `required_linear_history`; keeps `deletion`, `non_fast_forward`, required `CI Complete`; `Review Complete` leaves the required list (V3); bypass narrowed so the bot/AI identity bypasses only `pull_request` (rulesets cannot scope a bypass per rule: if they cannot, record the exact limit and the nearest safe shape). Submodules: GitHub Free blocks rulesets on private repos (403); OPERATOR DECISION (worklist [?]): upgrade the org plan or accept hook-only protection there. Show ruleset JSON before/after; present the exact diff to the operator once before applying.
    (ticked) 2026-10-02T09:38:42Z by d778be9d: split applied, recorded at agent/worklist/d778be9d.jsonl:5552: 24351140 history safety (deletion, non_fast_forward, required_linear_history, no bypass) + 12344707 (pull_request rebase-only, required CI Complete; bypass admin + Integration 2772000, which advance_contract_floor and update_homebrew_tap need, since a bypass cannot be scoped per rule); submodules hook-only per operator ruling (403 on GitHub Free)
- [x] M5 Record the ruling and remove "only the operator pushes it" / "operator-only main push" from CLAUDE.md Session Defaults rule 1, docs/agent-reference/ci-gates.md "Commit policy", pr-merge.md and every hook message, in the same change as M2-M3.
    (ticked) 2026-10-02T11:25:40Z by d778be9d: commit:d164b94e1 docs half (CLAUDE.md, ci-gates.md, pr-merge.md, output style); commit:3c9dad656 hook half (block_commit_on_main, worklist_messages, wl_judge, wl_bravedefault)
- [x] M6 `block_second_branch` / `block_second_open_pr` / git reference-transaction: the merged-and-deleted transition. Red-first tests: previous PR MERGED + its branch deleted -> new `MMDD-(MAX+1)` from main allowed; previous PR open -> refused; previous PR merged but branch still present -> allowed only after deletion; same-day MAX over merged names (the 0826-1 double-take). Real run on the next transition (M7).
    (ticked) 2026-10-02T10:37:05Z by d778be9d: commit:74dbedc27 merged-and-deleted transition, 31 suite cases incl. two same-day numbering cases; real run is M7
- [x] M7 Real run: merge #591 through the loop (after its boxes, stripe 23 and green), confirm the release dispatch, delete-on-merge, the next branch cut from main, and the guards' behaviour live.
    (ticked) 2026-10-04T16:08:25Z by d778be9d: commit:59ba0c756 #591 merged through the fast-forward fallback with Plan: and Operational-Reason: lines; v1.7.0 is tagged on #594's merge

### Plan-per-PR loop
- [x] L1 Loop definition in `.claude/agents/pr-babysitter.md` and the pr-babysit/pr-merge skills: implement boxes with writers, commit each verified unit and tick its box with the sha, push verified batches with a clean-clone ci:quick receipt, arm ci-trace --wait (automatic after PLAN-ci-verdict G), babysit reds in parallel, merge when every box is ticked AND CI Complete SUCCESS on the head (ci-trace), then cut the next branch and start the next queued plan.
    (ticked) 2026-10-02T10:59:32Z by d778be9d: commit:d164b94e1 loop definition in pr-babysitter.md (section + step 9) and the pr-babysit/pr-merge commands
- [x] L2 Plan queue: an ordered queue of approved plans (a `Queue:` header or a queue file under agent/plans) the loop pulls from; one plan per PR by default; a multi-plan PR records `Operational-Reason:` in its body. A gate refuses /pr-merge when the PR's plan has an unticked box and no `Operational-Reason:`.
    (ticked) 2026-10-02T11:25:38Z by d778be9d: commit:3c9dad656 plan queue + merge gate (open boxes without Operational-Reason refused), red-first 3+9+2; live: gh pr merge 591 refused for no Plan line
- [x] L3 Finish condition evidence: the merge step prints the plan's box ledger, the CI Complete verdict and sha from ci-trace, and the release decision.
    (ticked) 2026-10-02T10:59:33Z by d778be9d: commit:d164b94e1 merge-step evidence block: box ledger, CI Complete verdict+sha via ci-trace --json, review check, release decision

### Reviews
- [x] V1 Activate PLAN-per-commit-review (lift its hold for this ruling); implement its tasks T1-T13 with haiku as the reviewer model; the hook reviews each commit, records `agent/reviews/<branch>/<sha40>.md`.
    (ticked) 2026-10-02T09:08:55Z by d778be9d: commit:e4ce01a2b per-commit haiku review live (post-bash trigger, wl_review, records, three guards); fixes 3e93a0ff9 7343c2aab; receipt 309/309 at 7d3ae72bb
- [x] V2 Retire PR-level Claude review: `claude-review.yml`/`claude-review-reusable.yml` disabled or removed (the app is uninstalled); `review-status.yml` either removed or repointed to the per-commit review records.
    (ticked) 2026-10-02T10:37:20Z by d778be9d: commit:6566f46aa workflows removed + submodule callers (account 654d186, renet 8194a19); commit:eb932d04d review code, gates and goldens removed
- [x] V3 Stall removal: `Review Complete` leaves the ruleset's required checks (part of M4's single diff); .claude/commands/pr-merge.md:111 and .claude/agents/pr-babysitter.md:16,122 drop the claude-reviewed marker and thread preconditions in favour of "every commit since the base has a per-commit review record with no open blocker"; `block_premature_ready` and `block_admin_merge` reviewed for review-only conditions. Show before/after of what each blocked.
    (ticked) 2026-10-02T10:37:02Z by d778be9d: commit:5d671c01c docs + merge arm on per-commit review refusals (fail closed) + block_premature_ready text; Review Complete left the ruleset (agent/worklist/d778be9d.jsonl:5552)

## Open operator decisions
- M4 submodules: GitHub Free cannot hold rulesets for private repos (403). Upgrade, or hook-only protection for renet/account/elite? DEFAULT: hook-only; console gets the ruleset.
- M4 diff approval: the exact ruleset JSON diff is shown once before applying (the operator's own requirement).
