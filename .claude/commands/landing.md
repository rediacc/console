---
description: The one landing routine, run in the landing tree in the order the landing Stop hook's state names - babysit the landing PR to green (inline, or as a background pr-babysitter teammate with `bg` first), rebase-merge submodule PRs first and auto-merge the console PR at the finish condition, watch the release (Console CI on main + CD edge deploy) to green, carry any main-only hotfix, and notify the development session once the release is fully green so promotion brings the next PR. Every rule of the babysit loop is in .claude/agents/pr-babysitter.md.
argument-hint: "[bg] [MMDD-N] [short summary of the change to seed intent/PR titles]"
# Model-invocable, as every command is (operator ruling 2026-10-09: no command or skill is
# user-only; a hook and check:ci-model-invocable-commands refuse the flag). Operator ruling
# 2026-10-02 (PLAN-plan-per-pr-loop M1): the per-PR loop starts this itself and merges once
# its finish condition holds (every plan box ticked, CI Complete and Review Complete green on
# the head, wl_review.py --check and wl_prreview.py --check rc 0). The guardrails are the
# hooks: block_admin_merge, block_push_to_protected_branch and block_premature_ready decide
# what a merge may do. PLAN-simple-two-tree-loop B9 folded /pr-babysit and /pr-merge into
# this file, and both remain as one-line pointers to it.
allowed-tools: Bash(git branch:*), Bash(git status:*), Bash(git submodule status:*), Bash(gh pr list:*), Bash(gh pr view:*), Bash(date:*), Bash(./run.sh worktree landing --status)
---

## Current state

- Today (branch base): !`date +%m%d`
- Development tree branch (this checkout): !`git branch --show-current`
- Landing tree (the record `rediacc-landing.json` in `git rev-parse --git-common-dir` names its path and branch): !`./run.sh worktree landing --status`
- Live local branches besides `main`: !`git branch --format='%(refname:short)' | grep -vx main | tr '\n' ' '; echo`
- Working tree: !`git status --short | grep -v '.claude/settings.local.json' || echo '(clean aside from settings.local.json)'`
- Submodule pointers: !`git submodule status private/renet private/account private/elite private/homebrew-tap 2>/dev/null || echo '(unavailable)'`
- Existing date branches (console remote): !`git branch -r | grep "$(date +%m%d)-" || echo '(none yet)'`
- Date names ALREADY CONSUMED (PR heads, merged included): !`gh pr list --state all --limit 100 --json headRefName --jq '.[].headRefName' 2>/dev/null | grep "^$(date +%m%d)-" | sort -u | tr '\n' ' ' || echo '(none yet)'`
- Open PRs on the current branch:
!`cb="$(git branch --show-current)"; for r in console renet account elite homebrew-tap; do p=$(gh pr list --repo rediacc/$r --head "$cb" --state open --json number,title,mergeStateStatus --jq '.[] | " #\(.number) [\(.mergeStateStatus)] \(.title)"' 2>/dev/null); [ -n "$p" ] && echo "rediacc/$r:" && echo "$p"; done; true`

## Arguments

- The first whitespace-delimited token of `$ARGUMENTS` exactly `bg` selects delegate mode for the babysit half; anything else, no arguments included, selects inline mode.
- A token of the form `MMDD-N` names the branch to land; without one the branch is the landing tree's.
- The rest of `$ARGUMENTS` seeds the intent summary.

## The order: one landing state, one step

The landing Stop hook reads one state from the world on every stop and names its step; the state table and the long-red rules are in `.claude/agents/pr-babysitter.md` section *Landing states and the long-red rules*. This routine holds those steps in the same order, so a restart resumes at whatever state the world is in:

| State | Section below |
|---|---|
| L-CI, L-FIX, L-REVIEW | *Babysit*: the pr-babysitter loop, steps 1 to 8 |
| L-MERGE | *Land*, steps 0 to 3 |
| L-RELEASE | steps 4 to 6b |
| L-HOTFIX | step 5's hotfix bullet, the tree on local `main` (step 4) |
| L-IDLE | step 7, then the step-8 report |

## Babysit (L-CI, L-FIX, L-REVIEW)

The session reads `.claude/agents/pr-babysitter.md` in full and runs it: as the babysitter in inline mode (section *Modes*), or as the lead in delegate mode (section *Delegate mode: the lead's side*). Its loop step 9 hands the PR to *Land* below once the finish condition holds.

## Land: the PRs for the landing branch (L-MERGE onward)

The command merges the landing branch's coordinated PRs (parent repo `rediacc/console` plus any submodule PRs on the **same branch name**) and ends with the landing tree on a clean `origin/main`. Without an `MMDD-N` argument the branch is the landing branch. **This is the release path: a merge to `console/main` auto-triggers the edge deploy (`cd-release-edge.yml`) UNLESS the PR carries the `bump-none` label, in which case the merge is deliberately release-free and steps 5 and 6 shrink to almost nothing.** The label is never applied by hand: Console CI's `pr-labels` job decides the bump once at the green head from the per-commit reviews (`bump-major`/`bump-minor` from the highest verdict, no label for a patch, `bump-none` only when every commit's review says `none`).

**Two trees.** The landing tree (`git -C /home/developer/console-landing`, or the path in the record) holds the branch of the open landing PR, and this routine runs there: the landing session babysits, merges, watches the release and carries a main-only hotfix; the development session builds on a branch stacked on the landing branch. Every `git` call below names the landing tree, so `$ARGUMENTS` and the state block read its branch, never the development tree's. After the merge the landing tree sits on `origin/main` (detached) through the release watch and any hotfix, and leaves only through promotion (step 7).

**Who runs this.** Operator ruling 2026-10-02 (agent/plans/PLAN-plan-per-pr-loop.md, box M1): the per-PR loop in `.claude/agents/pr-babysitter.md` runs *Land* itself when its finish condition holds, and the operator may invoke it too. The finish condition is the gate, not an ask: <!-- scope: pr.merge-condition -->every box of the PR's plan ticked (or an `Operational-Reason:` line in the PR body, which admits the merge with boxes still open), `CI Complete` SUCCESS on the head (`ci-trace.py`), `wl_review.py --check` at exit 0, and `Review Complete` green on the head with `wl_prreview.py --check` at exit 0; the merge itself is `gh pr merge --rebase --auto` (step 3).

<!-- scope: pr.submodule-branch-name -->Submodule PRs are matched by the console branch name; the naming rule and the rename trap are in `.claude/agents/pr-babysitter.md` loop step 3.<!-- /scope -->

Submodule map (path → GitHub repo): `private/renet` → `rediacc/renet`, `private/account` → `rediacc/account`, `private/elite` → `rediacc/elite`, `private/homebrew-tap` → `rediacc/homebrew-tap`.

### 0. Preconditions (stop and report if any fail)

### Console itself has TWO remotes, and only one of them is GitHub

`origin` is GitHub; `gitlab` is `gitlab.rediacc.io/rediacc-org/github/console.git`. PR and merge tooling that assumes GitHub silently does the wrong thing elsewhere, so `git remote -v` comes before any reasoning about "the remote". Nothing pushes to `gitlab` automatically, which is why step 6b exists. The remote lives only in local `.git/config`, so a fresh clone lacks it and step 6b reports a skip until it is added back.

### Sibling repos under `private/` that are NOT submodules

- <!-- scope: pr.sibling-repos -->Discovery and handling are in `.claude/agents/pr-babysitter.md` section *Preflight*; *Land* runs that check before landing anything.<!-- /scope -->
- **Merge order when a console change and a change in such a repo belong together** (the U2 decision, taken by default on 2026-09-20 in favour of the documented clone-and-remote procedure over promoting `private/growth` to a submodule, which is hard to reverse): the sibling repo's own PR lands FIRST and only on the operator's explicit request, then the console PR, because nothing in console pins the sibling by commit (there is no pointer to bump) and a console change that depends on the sibling would otherwise merge ahead of the thing it needs. The console PR body names the pair so a reviewer can find the other half.

### Stray worktrees from past sessions

`git worktree list` can hold entries this session never created: a prior session's scratch worktree, abandoned mid-task. They are invisible to everything above: `git status` in the main checkout says nothing about them, and neither does the sibling-repo check.

They are discovered every run, before landing anything:

```bash
git worktree list
```

Each entry besides the current one is checked for what it holds before anything touches it, the same "identify whose work it is first" rule the dirty-tree precondition below applies to the main checkout:

```bash
git -C <worktree-path> status --short
git -C <worktree-path> diff --stat  # and per-submodule, if any submodule shows dirty too
```

A lease tree (under `.claude/worktrees/`) is never removed by hand: `git worktree remove|prune|lock` on it is hook-refused. `./run.sh worktree leases` lists them, `./run.sh worktree gc` shows which are safe, and `./run.sh worktree gc --write` removes only those that hold nothing dirty and no unlanded commit.

The landing tree (the path in `rediacc-landing.json`) is never removed and never counted as debris: it is the one tree this routine runs in. Any other worktree with nothing dirty and nothing unpushed is debris and is removed:

```bash
git worktree remove <worktree-path>
git worktree prune
```

A worktree with dirty content is **not** automatically debris, even if it looks stale. Each file is checked for whether it is safe to discard:
- **Byte-identical to (or a strict subset of) what the current `main` already has**
(`diff <worktree-file> <main-checkout-equivalent>`): safe, the work already landed by another path and this is a leftover draft.
- **Not found in `main`, not matched by any open PR, genuinely orphaned**: not deleted silently. It is reported and asked about, the same as an unclear dirty file in the main tree. Worktree content carries the same loss risk as working-tree content; it is only easier to forget.

Observed live 2026-08-01: six stray worktrees had accumulated in one checkout. Two held real, substantial uncommitted work from other sessions (a ~270-line CLI+Go feature, six locale files' worth of in-progress translation). Both turned out fully superseded by `main` (verified byte-identical or a strict subset before deleting), established by checking, not assumed from how old the worktree looked.

**Creating a new worktree from inside `/landing` (or any assistant session) is hook-blocked.** `.claude/rediacc_hooks/guards/block_worktree_add.py` refuses `git worktree add` from the assistant's own Bash tool unconditionally; a writer's tree is a lease, from `./run.sh worktree lease`. `./run.sh worktree landing --promote` moves a branch into the existing landing tree and is unaffected by the hook. A flow that genuinely needs a new worktree (normally none; steps 4-6 operate on the existing checkout) asks the operator to run the command through the `!` prefix.

- The landing tree's branch is **not** `main`, and it matches the landing branch shown above (or the `MMDD-N` argument).
- Working tree is clean except `.claude/settings.local.json` (left uncommitted; never `git add`ed).

**A tree that is NOT clean is not just a stop: whose work it is comes first.** The tree is shared: a concurrent session may hold uncommitted work in it, and that work is *not* part of this land. Steps 4 and 6 run `git switch --detach origin/main` in the landing tree, which carries uncommitted changes across silently when they do not conflict and aborts mid-way when they do. Neither outcome is one to discover after a merge has landed.

  So the report names what is dirty and who it belongs to, and **never** `git add`, `stash`, `restore`
or `checkout` touches those paths to make the precondition pass, because that destroys another session's work and is banned by CLAUDE.md. Either the operator lands with the dirty tree acknowledged (the changes ride along untouched, which is safe as long as they do not overlap what `main` moved), or the other session commits first. Observed live: a session held 18 uncommitted paths through a `/pr-merge`; nothing was lost, but only because `main`'s two new commits touched none of them.

A dirty path that **does** overlap what `main` moved makes `git checkout main` abort outright (it does not silently clobber). A diff that is genuinely orphaned on investigation (no commit in the branch's history ever referenced it, it sat untouched across many rounds, nothing in flight needs it: `git log --all -- <path>`, and whether the content is even still needed, e.g. a semver range bump the lockfile already satisfies) may be committed by the running session (never stashed or discarded) to unblock the checkout, with a message stating plainly that it was found orphaned and why it is safe to land. This is committing to preserve, not deciding the change was wanted; when whose work it is or why it exists is unclear, the command stops and asks.
- A `rediacc/console` PR exists for this branch; its number is noted.
- <!-- scope: pr.finish-sequence -->The console PR arrives at the babysitter's finish line, `.claude/agents/pr-babysitter.md` loop step 8 (the per-commit review precondition is its loop step 7).<!-- /scope --> A deferral refusal is settled by `worklist.py --triage <me> '<finding>'`, then a fix marked `fixed <sha>`, or, for an OPERATOR-ONLY verdict, an AskUserQuestion and `waived #<item> ASKED:<YYYY-MM-DDTHH:MM>Z`. A PR still in draft is flipped ready (`gh pr ready`; `block-premature-ready` verifies `CI Complete` is green) and its human review threads resolved before proceeding. `block-admin-merge` refuses a `gh pr merge` while the head branch fails the per-commit review precondition. Never a merge over red, over an open review finding, over an unanswered PR review summary, or over unresolved threads.
- `/code-review ultra` is available as an optional deep pre-land review for a big wave (operator-invoked; it does not replace the per-commit review).

### 1. Merge submodule PRs first (submodule-first, rebase)
**All 5 repos (console + 4 submodules) are rebase-merge only, since 2026-07-30.** `--squash` is rejected outright: `gh pr merge <n> --squash` fails with `GraphQL: Squash merges are not allowed on this repository.`, so the merge goes straight to `--rebase`. `git branch --merged` lies about ancestry on these repos (a rebased PR's commits are never literally on the base branch under the old SHAs), so "is this landed" is judged by PR **state** (`gh pr view --json state` → `MERGED`), never by `--merged`/`--contains`.

For each submodule that has an **open PR on this branch** (the list above):
- `mergeStateStatus` reads `CLEAN` and there are **no unresolved review threads** (`gh api graphql` reviewThreads → all `isResolved:true`). Unresolved threads are resolved first (substantive reply + `resolveReviewThread`), because they block the console `Submodule Branches` gate while the console PR is open.
  - A **failing but non-required** check shows as `mergeStateStatus: UNSTABLE`, not `CLEAN`, and that alone is no stop. GraphQL says whether it is actually required: `pullRequest.commits.nodes[].commit.statusCheckRollup.contexts.nodes[].isRequired(pullRequestNumber: <n>)`. `isRequired:false` on the only failing context means the PR is safely mergeable despite UNSTABLE.
- Rebase-merge: `gh pr merge <n> --repo rediacc/<r> --rebase`. **GitHub deletes the head
branch** -- `delete_branch_on_merge` is `true` on all five repos (`gh api repos/rediacc/<r> --jq '.delete_branch_on_merge, .allow_squash_merge, .allow_rebase_merge'`). This line once claimed the setting was FALSE on submodules and that keeping the branch preserved a gate fallback; both were invented, and believing merged branch names stay visible is what let `0826-1` be picked twice on 2026-08-26. The gate does not need the ref: `check-submodule-branches.sh` finds merged work with `gh pr list --head <branch> --state merged`.
- The new submodule `main` HEAD is captured: `gh api repos/rediacc/<r>/commits/main --jq .sha`. This is the **rebased tip commit**, a new SHA even for a single-commit PR (rebase always creates new commit objects), tree-identical to the branch tip but not the same object.

**A submodule PR GitHub cannot rebase** (`GraphQL: This branch can't be rebased`, as rediacc/account#102 and rediacc/renet#121 were on 2026-11-22) that is a pure fast-forward lands by the session's own push, `git -C private/<sm> push origin <branch-tip-sha>:main`, never `--merge` or `--squash`.
`block_push_to_protected_branch` admits it only as one refspec with nothing forced, from a submodule the `.gitmodules` registers, when the sha is that submodule's `origin/<branch>` with `origin/main` as its ancestor, its PR in `rediacc/<sm>` is OPEN with that head, `mergeStateStatus` CLEAN and no unresolved review thread, and the console PR for the same branch is OPEN (operator ruling ASKED:2026-11-22T11:11Z).
No rebase happened, so the pointer in step 2 is the branch tip itself.

### 2. Update console submodule pointers to the merged commits
A rebase means the branch-tip commits are **not literally on** the submodule's `main` (new SHAs from the replay), so the pointer moves. For each merged submodule:
- `git -C private/<sm> fetch origin main`
- **Safety check:** `git -C private/<sm> diff --stat <old-branch-tip-sha> <new-main-sha>` must be **empty** (rebase preserves tree content exactly; only the commit SHA changes). A non-empty diff stops the land: something diverged (e.g. main advanced mid-merge).
- `git -C private/<sm> checkout <new-main-sha>` (detached at the merged commit).

Then in the console repo: `git add private/renet private/account …` (only the merged pointers), commit (`chore(submodules): bump pointers to merged main commits`), and push to the branch. This re-runs console CI; the `Submodule Branches` gate now passes via the **ancestor-of-main (pointer-bump-only)** path in `.ci/scripts/quality/check-submodule-branches.sh`. The landing freeze admits this commit because every bumped gitlink is an ancestor of its submodule's origin/main (`.claude/rediacc_hooks/pr_freeze.py` rule 6).

The console PR body is refreshed before the push (the staleness gate reads `updatedAt`; the body must actually change): it summarizes the merges and the pointer bump.

### 3. Wait for the fast-path run, then auto-merge the console PR
The pointer bump changed only submodule SHAs (trees verified identical in step 2), so the push is a **pointer-bump fast path**: `.ci/rediacc_ci/ci/detect_pointer_bump.py` sets `pointer_bump_only=true` in the `initialize` job and `ci.yml` skips `build-renet` (and everything cascading from it: the other builds, tests, install-matrix, preview) plus `migration-test`, `stripe-sandbox`, `package-tests`, and `ops-tests`. Only `quality`, `review-gate`, and `ci-complete` run, so the run goes green in **minutes**, and `assert_ci_complete.py` accepts the skipped builds under this flag. The pointer-bump commit still gets a per-commit review record, written as `Verdict: skipped (gitlink-only)` with no model call; it is committed with `.claude/hooks/stop/worklist.py --review-commit <me>` before the push, because `block_push_with_unrecorded_reviews` refuses a push while a finished record is uncommitted.
- **One receipt per push, and no push into a running run.** The pre-push receipt is schema 2 and incremental: it carries every gate whose input hash is unchanged, so it is built once when the push is due, not after each commit. While the PR's run on the pushed head is in progress and not red, further commits wait locally until it settles; a fix for a red pushes at once. The hooks say both as advisories (agent/plans/PLAN-fast-loop.md); nothing refuses the push.
- The run is traced with `.ci/scripts/ci/ci-trace.py --wait` (run_in_background: true). No hand-rolled loop: ad-hoc watch commands are refused by `block-adhoc-sanctioned.sh`, and a hand-rolled watch left running blocks the Stop hook. The script keys on the PR HEAD, so a watchdog rerun and a superseded run are both handled structurally. Exit 0 green, 1 red, 2 no verdict, 3 head moved. **One wait per command**: a second wait chained onto the same watch can swallow the CI verdict, since the notification fires on process exit (observed 2026-08-24, ninety minutes lost).
- <!-- scope: pr.review-answer -->**The PR review is waited on, then answered.** `Review Complete` is a required check (operator ruling 2026-10-03, PLAN-github-pr-review-restore GR8): the PR does not merge until it is green on the head. Once the PR is ready, `python3 .claude/hooks/stop/wl_prreview.py --wait` starts in the background (one wait per command, bounded at 35 minutes by its default `--timeout 2100`). Its exit code decides the next move:
  - **0, reviewed.** `wl_prreview.py --status` names the token and the findings. `current`, `capped` and `exhausted` are green. `outage` is green too, and it is the one excused case: the LLM was unavailable for the head's last attempt, which is recorded under DECISIONS in the round log. `hygiene` means findings or threads are unanswered: each finding is triaged as fixed, not-a-bug with evidence, or waived with an operator ASKED: for an operator-only triage (a deferral is refused), and the dispositions are written with `wl_prreview.py --draft > <file>`. Each fix is committed first, `wl_prreview.py --answer <file>` runs citing the local sha (it accepts a `fixed <sha40>` that is an ancestor of local HEAD), and only then is the fix pushed: a push over an unanswered summary fails `Review Gate`, and the watchdog cancels the run. A summary whose findings fence is an empty array needs no reply. The follow-up review of the new head repeats the cycle, bounded by the review budget's cap tiers.
  - **4, failed-run.** The Claude Review run failed for a reason other than an outage. That is work, not an excuse: the run is found (`gh run list --repo rediacc/console --workflow ops-claude-review.yml --limit 5`), the failure read (`.ci/scripts/ci/ci-trace.py --run <id> --why`, then `--job <id> --log`), the cause fixed, the review re-dispatched with `gh workflow run ops-claude-review.yml -f pr_number=<console-pr>`, and the wait started again.
  - **3, timeout or no review.** Never a pass, and never a reason to merge. A Claude Review run for the head is checked for, re-dispatched when none exists, and waited on again.
  - `wl_prreview.py --check` then reads rc 0 (no summary, or the newest one answered or empty with every finding thread resolved); rc 1 is an unanswered summary or an unresolved thread to answer, and rc 2 (the API could not be read) is retried, not merged over.<!-- /scope -->
- **The finish evidence is printed before the merge command, every time** (PLAN-plan-per-pr-loop box L3). The merge is the AI's own call, so the record of why it was allowed is the evidence printed here, in this order, into the transcript and the round log:

  ```bash
  # 1. the plan's box ledger: the plan this PR carries (the plan the PR body names).
  #    No worklist verb prints a single plan's ledger, so the plan file is read with
  #    the box grammar, and the committed ledger beside it.
  plan=agent/plans/PLAN-<slug>.md
  grep -nE '^\s*- \[[ ?>]\] ' "$plan" || echo "every box ticked: $plan"
  jq --arg p "$plan" '.plans[$p] | {status, open, done}' .ci/config/plan-boxes.json
  # 2. the CI Complete verdict and the sha it judged
  .ci/scripts/ci/ci-trace.py --json | jq '{verdict, ci_complete, head, run, pr}'
  # 3. the per-commit reviews
  python3 .claude/hooks/stop/wl_review.py --check
  # 4. the PR review: Review Complete's token on the head, and the summary answered
  python3 .claude/hooks/stop/wl_prreview.py --status
  python3 .claude/hooks/stop/wl_prreview.py --check
  # 5. the release decision pr-labels took at the green head ("patch" when it set none)
  gh pr view <console-pr> --repo rediacc/console --json labels \
    -q '[.labels[].name | select(startswith("bump-"))] | if length == 0 then "patch" else join(",") end'
  ```

  The merge goes ahead only when (1) shows no open box (or the PR body carries `Operational-Reason:` for a recorded exception), (2) reads `verdict: green` with `ci_complete: success` on the PR head, (3) exits 0, and (4) shows `Review Complete` green on the head (`current`, `capped`, `exhausted` or `outage`) with `--check` at exit 0. The release decision in (5) is reported, never changed by hand.
- When `CI Complete` and `Review Complete` are green: `gh pr merge <console-pr> --repo rediacc/console --rebase --auto` (console is rebase-only too, same policy as the submodules since 2026-07-30; `--squash` is rejected here as well. `--rebase --auto` is the sanctioned merge, which GitHub lands the moment required checks are green. `--admin` is banned by the `block-admin-merge` hook; there is no place for it here).
- **`gh pr merge --rebase` can fail outright on a very large PR with `GraphQL: This branch can't be rebased`, even when every check is green and `mergeable_state` reads `clean`.** Confirmed live 2026-08-31 on a 134-commit / 53,747-line PR: `gh api repos/<owner>/<repo>/pulls/<n> --jq '{mergeable, mergeable_state, rebaseable}'` showed `mergeable:true, mergeable_state:"clean", rebaseable:false` -- GitHub computes `rebaseable` separately from `mergeable` and appears to give up on it past some size threshold, distinct from and not documented alongside `mergeable_state`. This is NOT a real merge conflict (`git merge --merged`/branch-protection checks are unaffected) and is NOT the "unresolved thread" or "stale head" case the rest of this section covers.

**The first question is whether the branch is a pure fast-forward** (the common case for a PR built the way this workflow builds one -- rebased onto `main` throughout, never merged from `main`):
  ```
  git merge-base --is-ancestor origin/main origin/<branch> && echo "pure fast-forward"
  ```
When that prints `pure fast-forward`, the sanctioned recovery is a **direct fast-forward push of the branch tip onto `main`** -- not `--merge` (adds a merge commit, breaking this repo's linear-history convention for the first time) and not `--squash` (rejected outright on this repo, and it would collapse every commit besides):
  ```
  git push origin origin/<branch>:main
  ```
This is git-level identical to what a rebase-merge would have produced (nothing to replay: `main` is already an ancestor, so this is a plain fast-forward, not a force-push, and `block_git_force_push` does not apply).

<!-- scope: pr.ff-fallback -->**The push is this session's own, typed here.** Operator ruling 2026-10-02 (PLAN-plan-per-pr-loop boxes M2 and M5): `block_push_to_protected_branch` admits exactly this one push to `main`, and refuses it unless every condition below reads true. Anything it cannot read is a refusal, and a refusal names the condition that failed.
  - **Shape:** one `git push` to `origin` with exactly one refspec `<src>:main`, where `<src>` names the PR's `MMDD-N` branch (`<branch>`, `origin/<branch>`, or a `refs/` spelling of either) or its tip sha (never `HEAD`). The branch is read from the refspec, never from the checkout, so the push works from any checkout, and no flag but `-q`/`-v`: no `--force`, `--force-with-lease`, `+`, `--delete`, `--tags`, `--follow-tags`, `--all` or `--mirror`.
  - **Local facts:** the checkout is the console's own (the main checkout or the landing tree); the commit is exactly `origin/<branch>`, the pushed tip of the `MMDD-N` branch the refspec names (or, for a sha, of any `MMDD-N` branch on the remote); `origin/main` is its ancestor (`commit_policy.ff_fallback_refusal`).
  - **The PR:** that commit is the head of the OPEN PR for the branch (`gh pr view`), and `CI Complete` is SUCCESS on it, read through `.ci/scripts/ci/ci-trace.py --json --ref <branch>`, never a raw check read.
  - **The reason:** the PR body carries an `Operational-Reason:` line naming the "can't be rebased" refusal. The plan's box ledger becomes the alternative proof once box L2 links a PR to its plan (`agent/plans/QUEUE.md`).<!-- /scope -->

The git-level `pre-push` hook admits the same push without any override (one ref equal to `origin/<branch>`, with `main` as its ancestor), so no operator `!` line and no `COMMIT_POLICY_OK=1` is involved. The `ci:quick` receipt rule (`block_unverified_push`) still applies. GitHub auto-detects the PR's commits landing in `main` and flips it to `MERGED` on its own; `gh pr view <console-pr> --json state,mergedAt` verifies it, same as the normal path. The head branch is still auto-deleted (`delete_branch_on_merge` is a repo setting, not something the merge mechanism controls).

When the ancestry check does NOT print "pure fast-forward" (main has moved ahead of this branch), this fallback does not apply. The branch is rebased onto `origin/main` for real first (a normal, non-empty rebase), pushed with `git push --force-with-lease origin <branch>` (`block_git_force_push` admits `--force-with-lease` to the single live `MMDD-N` branch and nowhere else), CI Complete awaited on the new head, and `--rebase --auto` retried. Picking `--merge`/`--squash` unilaterally changes `main`'s permanent history against documented policy, and the server-side ruleset requires linear history anyway.
- Verify: `gh pr view <console-pr> --repo rediacc/console --json state` → `MERGED`, and capture `console/main` HEAD.

### 4. Move the landing tree to main (first pass; see step 6)
- `git fetch origin --prune`
- In the landing tree: `git switch --detach origin/main`. The landing tree stays on main through the release watch and any hotfix, in one of two shapes: detached at `origin/main` to watch, or on the local `main` branch to commit a hotfix. A `[hotfix]` commit on a detached HEAD is refused (`block_commit_on_main`), so the L-HOTFIX state first moves the tree onto the branch with `git switch main` and `git merge --ff-only origin/main`, and commits there (step 5). `./run.sh worktree landing` refuses to reuse a tree in either shape and names promotion as the exit.
- `git submodule update --init --recursive` takes **all** submodules, not just the merged ones. The old form named only the merged pointers, which left `private/homebrew-tap` and `private/elite` sitting at whatever commit the previous branch had them at while `main`'s record moved on.
- Verify: the landing tree's HEAD == `origin/main`, working tree clean (only `settings.local.json` may differ), `git submodule status` shows no `+`/`-`.

### 5. Watch the release land (the merge to main IS the edge release, unless bump-none)

**FIRST, CHECK FOR `bump-none`. A release-free merge is a normal outcome, not a missing step.**

```bash
gh pr view <console-pr> --repo rediacc/console --json labels -q '[.labels[].name] | join(", ")'
```

When the label set contains `bump-none`, this merge earns no release: ci.yml's `pr-labels` job sets `bump-none` when every reviewed commit's per-commit review record carries the `Labels:` verdict `bump=none`, which means no git tag, no GitHub Release, no R2 upload, **no edge deploy**. Its commits ship with the next release-worthy merge. Console CI still runs on `main` and still does the real Docker build and push, so it must still go green, but the release decider (`rediacc_ci.ci.dispatch_release`, run by initialize) deliberately skips and **no Release run ever appears**. The decision is confirmed from the run rather than inferred from an absence:

```bash
.ci/scripts/ci/ci-trace.py --run <main-ci-run> --jobs --json \
  | jq -r '.[] | select(.name=="Finalize Release Sentinel") | .job_id'
.ci/scripts/ci/ci-trace.py --job <that-id> --log
# the log prints the verdict verbatim, e.g.
#   release SKIPPED: #567 carries 'bump-none'
```

**Why this is called out.** Observed live on 2026-08-10: a session merged a `bump-none` PR, watched Console CI on `main` go green, then went looking for the Release run and found only runs from the previous day. Nothing was wrong. But "the release run is missing" and "the release was correctly skipped" look identical from a run list, and the first reading invites re-dispatching a release nobody wanted, which ships artifacts. The label is read first, then the sentinel job's own words.

When `bump-none` applies, the rest of step 5 does not: there is no Release run to watch, no tag to report, and nothing deployed to edge, and step 6 shrinks to one fast-forward.

For a release-worthy merge, everything below applies as written.

The push to `console/main` runs **Console CI** (`ci.yml`; on `main` it does the **real** Docker build+push, not the PR dry-run). When Console CI goes green, its finalize step **dispatches the Release workflow** (`cd-release-edge.yml`): git tag → GitHub Release → R2 upload → **deploy edge**. Both do main-only work that PR CI only dry-ran, so they can fail where every PR check was green. The land is not done until this is green.
- The **Console CI** run for the merged commit is found with `.ci/scripts/ci/ci-trace.py --runs --ref main` (event `push`, matching the merged SHA) and traced by id with `.ci/scripts/ci/ci-trace.py --run <id> --wait` (or `--ref main --wait`), run_in_background: true. A bare `--wait` on `main` reads the current branch's PR and gives no verdict. On `main` the watchdog auto-retries transient failures; `--run` reads per-job conclusions of that run, so a rerun lands as a new attempt of the same id rather than fooling it.
- **One merge, one real run.** When the merged SHA shows two Console CI push runs, the later one is a no-op by design: its Duplicate Run Check (`rediacc_ci.ci.sibling_runs dedupe`) finds the earlier run, every job skips, it ends green and its summary names the original, which is the one traced. The release gate refuses to dispatch while another push run on the same SHA concluded failure, and names that run (`sibling_runs release-gate`); the fix is that run's red, never a dispatch around it. An EARLIER run on the SHA that was cancelled as a whole refuses too, unless the releasing run is its clean retry: attempt 1, with no job failed, cancelled or timed out (operator ruling 2026-10-06). A re-attempted retry therefore never releases after a cancel; a new commit is pushed, or the operator dispatches by hand once the commit is known good. A red push run on `main` blocks the Stop hook until an item carries `push:ci run:<id>` (2026-10-06: v1.8.0 released while run 37437282770 on the same SHA was still queued, and that run then failed).
- Console CI on `main` is green **before** the Release run exists. Once it exists, the **CD - Release to Edge** run (`.ci/scripts/ci/ci-trace.py --runs --ref main --workflow "CD - Release to Edge"`, event `workflow_dispatch`, matching the merged SHA) is watched **by id**: `.ci/scripts/ci/ci-trace.py --run <id> --wait` (run_in_background: true). That is the run that actually tags and deploys edge.

**NOT "the same way" as the branch watch above, and this cost a false green.** A branch's GraphQL `statusCheckRollup` does NOT contain a `workflow_dispatch` run's check runs. Measured 2026-08-26 on Release run 32968110599 (head `1c006e53`): the REST check-runs API for that exact commit showed `in_progress Tag & Release`, while the rollup for `refs/heads/main` returned 81 contexts, state SUCCESS, **none in flight**. So `--wait --ref main` printed `GREEN ... every context succeeded or was skipped` and exited 0 while the release was mid-flight, twice, including with `--until-final`. `--run` reads per-JOB conclusions instead (in-flight → exit 2, completed-success → 0, unreadable → 2).
- **Read before classifying.** A failed CD step is surfaced loudly with its exact name, and its COMPLETE log is read first. The edge may be left partially deployed.
- **Doing nothing comes first.** The watchdog's AI classifier auto-retries transient failures on `main` by itself (observed: a wrangler `Network connection lost.` during `d1 export` was classified `transient (0.8)` and re-dispatched without intervention). A retry already in flight is checked for before acting; a second actor racing the watchdog is how a half-deployed edge gets worse.
- **Then the classification: transient, or main-only?** The PR was green, so a failure appearing now is one of exactly two things, and they need opposite responses. The test is one command: **did this job run and pass on the PR run?**

  ```bash
  .ci/scripts/ci/ci-trace.py --run <pr-run-id> --jobs --json \
    | jq -r '.[]|select(.name=="<failed job>")|"\(.conclusion) \(.name)"'
  ```

  `.ci/scripts/ci/ci-trace.py --history "<failed job>"` answers the same question across the job's last 5 completed runs.

  - **It ran and passed on the PR → transient.** Same code, same job, different outcome. It is NOT fixed; the watchdog auto-retries these itself. (Real case: `Migration Test` passed on PR run 29844923209, then died on `main` with wrangler `Network connection lost.` mid `d1 export`, was classified `transient (0.8)` and cleared on the auto-retry. A "fix" would have been a change to working code.)
  - **It never ran on the PR, or runs differently there → main-only.** Then it is genuinely untestable by a PR, and that is what licenses the next bullet.

- **A main-only code fix is a `[hotfix]` commit DIRECTLY ON `main`, in the landing tree, not a new branch or PR.** The rule is inverted here for a reason that is about INSTRUMENTS, not urgency: **a PR cannot exercise the thing that broke.** It would go green while proving nothing, because the failing path is one PR CI structurally never runs. The verification loop for these fixes is the next `main` run, not a PR check.

Main-only surfaces in this repo: `finalize-release-sentinel`, `pipeline-sentinel`, `check-release-state`, `build-devcontainer-manifest` (all gated `github.event_name == 'push'` / `refs/heads/main`), the entire Release workflow (`cd-release-edge.yml`, dispatch-only), and Docker, which PR CI only DRY-RUNS while `main` does the real build+push.

The release state is no longer main-only. `cd-preflight` (CD Preflight in `ci.yml`) runs on every same-repo PR as well as on `main` and predicts the bijection, floor, pointer, version and Validate Promotion failures that `check-release-state` and cd-release-edge used to surface only after the merge (docs/agent-reference/release-process.md *CD preflight*). A red CD Preflight on the PR is therefore a PR fix, not a `[hotfix]`; a DRIFT it names in live R2 state (a sentinel with no tag) is repaired with the remediation it prints, and a `check-release-state` red on `main` that CD Preflight passed on the PR is the main-only case above.

  So the fix is committed on the local `main` branch in the landing tree (step 4 names the switch onto it) as a hotfix, and the push is handed to the operator. The commit shape is what `block_commit_on_main` admits (docs/agent-reference/ci-gates.md *Commit policy*):
  - the subject ends in `[hotfix]` (`fix(ci): <what> [hotfix]`), and the message carries a `Hotfix-Evidence: <red main run id or actions/runs URL>` trailer;
  - at most 5 files, named by pathspec: `git commit -F <msg> -- <paths>` (`git add -A` is still banned); no `PR-TASK:` trailer, since `main` has no epic;
  - never `[no-review]`: a hotfix gets no PR, so the per-commit review is the only one it has.

  The push is the operator's: `block_push_to_protected_branch` admits only the step-3 fast-forward fallback (the open PR's head), which a commit made on `main` never is, and the git-level `pre-push` hook refuses it for everyone else, so the report names the commit and the exact line for the operator to run, `! COMMIT_POLICY_OK=1 git push origin main`. The report states plainly which commit went on `main` and why.
  - This is the ONLY situation in which committing on `main` is allowed without the operator calling it a hotfix in the task. It applies **after** a merge performed by *Land*, to a failure in that merge's own release path. Everything else goes on a feature branch.
  - It does **not** extend to re-cutting a release. Re-dispatching stays the operator's call (`gh workflow run "CD - Release to Edge" -f ci_run_id=<console-ci-run-id> -f release_mode=retry`), because that ships artifacts rather than fixing code.

### 6. Re-sync main after the release run

The merge releases edge through CD, but CD no longer pushes to console `main`: the contract floor is an ordinary commit in the next PR and there is no console homebrew gitlink bump. The merge (or a hotfix) is therefore the last write to `main`, and the landing tree is at most one fast-forward behind. An agent may also release edge itself with `release:local --channel edge` (docs/agent-reference/release-process.md).

- `git fetch origin --prune`
- In the landing tree: `git switch --detach origin/main`. A tree on the local `main` branch for a hotfix leaves it the same way, once the operator's push has put the hotfix on `origin/main`; until that push the tree stays on `main`, because detaching there would leave the unpushed hotfix only on the local branch.
- `git submodule update --init --recursive`
- Verify clean: `git status --short` shows nothing but `.claude/settings.local.json`, and `git submodule status` shows no `+`/`-`.

**A submodule that still shows dirty is decided by which commit is NEWER, never by whose work it is:**

```bash
rec=$(git ls-tree HEAD private/<sm> | awk '{print $3}')
cd private/<sm> && git fetch origin -q
git merge-base --is-ancestor "$rec" origin/main && echo "record BEHIND origin/main"
git merge-base --is-ancestor origin/main "$rec" && echo "record AHEAD"
```

Worktree **behind** the record ⇒ the checkout is stale ⇒ `git submodule update`, **commit nothing**. Committing it would roll that submodule back a release. The naive test ("this isn't the session's work, leave it out") gives the right answer here only by luck, and the opposite instinct ("the pointer is dirty, carry it at its latest") ships the rollback.

### 6b. Mirror `main` to the GitLab remote, so it cannot go stale again

This repo has a **second remote**, `gitlab` (`gitlab.rediacc.io/rediacc-org/github/console.git`). It is not a live mirror and nothing pushes to it automatically, which is exactly how it drifted: on 2026-08-23 its `main` was found sitting at `09b0b7716` while GitHub's was at `b75c44d58`, an ancestor and months behind. This step exists so that gap never reopens.

It goes **here**, after step 6 and before step 7, and the position is load-bearing in both directions. Earlier than step 6 mirrors a `main` that has not been re-synced, the very drift this prevents. Later than step 7 dilutes step 7's hand-back, whose subject is that the landing tree stops touching `main`.

```bash
if git remote get-url gitlab >/dev/null 2>&1; then
    GIT_TERMINAL_PROMPT=0 timeout 120 \
        git push gitlab refs/heads/main:refs/heads/main --follow-tags
else
    echo "no gitlab remote configured in this checkout; skipping (report it)"
fi
```

**The session runs this push itself** (operator ruling 2026-10-03, worklist #1cad85a1), with no `COMMIT_POLICY_OK` and no operator `!`. `block_push_to_protected_branch` and the git-level `pre-push` hook admit exactly this shape: one push to the remote named `gitlab`, the single refspec `refs/heads/main:refs/heads/main` (or `main:main`), no flag but `--follow-tags`, `-q` or `-v`, from the console checkout itself, where every URL of `gitlab` is `https://gitlab.rediacc.io/rediacc-org/github/console.git` and local `main` is exactly `origin/main`. Step 6 runs first so local `main` matches GitHub's; a refusal naming `main` ahead or behind means that re-sync did not happen, and the fix is the re-sync, never another spelling of the push.

Four things this respects, in order of how likely they are to bite:

- **The remote may not exist.** `gitlab` lives only in local `.git/config`; it is not tracked,
so a fresh clone lacks it. `git remote get-url gitlab` probes it, and an absent remote is **reported and the land continues**. A missing mirror never fails a merge that already landed.
- **Credentials may be absent or expired.** GitLab is self-hosted and answers a redirect to a
sign-in page. `GIT_TERMINAL_PROMPT=0` plus a timeout is what stops a non-interactive session hanging on a credential prompt. A reported skip beats an unreported hang.
- **The refspec is explicit. Never `--mirror` from a working checkout.** In a working tree
`--mirror` also pushes `refs/remotes/*` and deletes anything on GitLab not present locally. The mirror form is correct only from a bare mirror clone during a deliberate history rewrite, which is an operator-run one-off, not this step.
- **Never force.** Once both remotes share history this is always a fast-forward. A rejection as
non-fast-forward means GitLab has diverged again: **report and stop**, no force flag. A forced push from a stale local `main` would silently overwrite the mirror, and `block_git_force_push`, `block_push_to_protected_branch` and the `pre-push` hook all refuse it anyway.

The outcome goes in the step-8 report either way, including a skip. A mirror that quietly stops being written is indistinguishable from one that is up to date, which is how the first drift went unnoticed for months.

### 7. Hand back: the release goes green, then promotion brings the next PR

Steps 4 and 6 leave the landing tree on `origin/main` (detached), which is right for verifying the release and a **loaded gun for whatever happens next**: `main` is the one branch this repo forbids pushing, and a tree parked there invites the next piece of work to be written straight onto it. A session once finished a merge, stayed on `main`, and built an entire feature there, 26 new files across 18 paths, before anything noticed. `block_commit_on_main` now refuses any commit there that is not a `[hotfix]`, and the landing freeze keeps feature work in the development tree, but a refusal is a late place to find out. So the hand-back is explicit:

- **Sweep for a review that landed after the merge.** A follow-up Claude review can finish after `--rebase --auto` lands (the review of a pointer-bump head, or a re-dispatch still in flight). `python3 .claude/hooks/stop/wl_prreview.py --status --pr <merged-console-pr>` reads it; each finding it lists that has no answer becomes a worklist item (`worklist.py --add <me> "<finding> from PR #<n>'s late review"`), fixed on the next branch like any other finding, never dropped because the PR is closed.
- **Delete the merged local branch in every repository**, console and each submodule that carried it, once `gh pr view <n> --repo rediacc/<r> --json state` reads `MERGED`: `git branch -D <merged>` (and `git -C private/<sm> branch -D <merged>`). A merged branch is no longer live, and leaving it behind makes the next name harder to read.
- **Notify the development session once the release is fully green** (Console CI on main and the edge release both SUCCESS at the merged sha): the landing Stop hook prints the `cd-done` notice. The next PR is taken only after that.
- **Promotion is the development session's, at a commit boundary.** `./run.sh worktree landing --promote` refuses a dirty tree, an unmerged landing PR, a release that is not fully green, and a development plan with an open `[writer]` box; it rebases the development branch onto `origin/main` with `--git rebase-proof` (landing's copies drop out as absorbed), moves it into the landing tree, rewrites the record, cuts the next development branch in the main checkout and prints the line that brings up the next PR, which is run. With no development commits ahead of `origin/main` it reports that the landing tree idles and exits 0.
- <!-- scope: pr.consumed-names -->A branch cut from `main`, needed only when no live branch exists in either tree, takes its name by the MAX+1 recipe of `.claude/agents/pr-babysitter.md` loop step 2.<!-- /scope -->
- **Refresh the PR-condition ledger on the next branch.** `npx tsx scripts/gates/check-pr-condition-ledger.ts --refresh` records every PR a `REVISIT WHEN PR #N MERGES` clause names that has merged since; when `.ci/config/merged-prs.json` changes, it is the branch's first commit, and the offline `pr-conditions` probe in check:ci-suppression-liveness then reds any hold whose PR just merged (agent/plans/PLAN-k3s-137-and-pr-conditions.md, B).
- **The next plan.** <!-- scope: pr.one-plan-per-pr -->One plan per PR, and a plan rides exactly one PR: the plans the development branch built ride the promoted PR, and <!-- scope: pr.queued-plan-start -->a queued plan starts only when the hook names it (`loop-next` after a merge), in the development tree.
  When a plan starts, <!-- scope: pr.epic-carries-plan -->its epic is created with `worklist.py --epic <me> new --plan <rel> <title>` and the plan's items are attached to it, because the Stop hook blocks a stop only on items under the PR plan set's epics. <!-- scope: pr.plan-set -->The PR body's `Plan:` lines define the PR's plan set: one plan by default, every listed plan when an `Operational-Reason:` line records the operator adding them, and in every case their unfinished prerequisites (`Depends-On:`), which the Stop hook, the CI plan gate (check:ci-plan-implementation, rule P-A1) and the merge gate count alike.<!-- /scope -->
- Uncommitted work in the landing tree (the §0 shared-tree case) is named again here: it now sits on a detached `origin/main` and moves with the promoted branch only if it is committed first.

### 8. Report
Each merged commit (renet / account / console → their rebased-tip SHAs on main), the landing tree in sync with `origin/main`, **the step-6b GitLab mirror outcome, including a skip and its reason**, and the release outcome: Console CI green, Release/CD green with the new version tag and edge deployed (or the exact failed step). A step-5 `[hotfix]` on `main` is stated with its SHA, the failure it repaired, and whether the operator has pushed it. The report includes the step-3 finish evidence (box ledger, CI Complete verdict and sha, review check, the Review Complete token and `wl_prreview.py --check`, release decision), the step-7 late-review sweep (no late findings, or the worklist items filed for them), and the hand-back (the `cd-done` notice, or what still holds the release). **No** release re-cut: a re-dispatch ships artifacts and stays the operator's call.
