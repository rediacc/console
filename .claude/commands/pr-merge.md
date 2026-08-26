---
description: Land the current branch's stacked PRs: rebase-merge submodule PRs first, bump the console pointers to the merged commits, wait for the fast-path CI run and auto-merge the console PR (flipping it ready first if needed), check out main, watch the release pipeline (Console CI on main + CD edge deploy) to green, then RE-SYNC main because CD pushes a homebrew-tap pointer bump and a release-state commit back to main after the merge. Use when the console PR is ready + Claude-reviewed with threads resolved, and you want to release without re-typing the submodule sequence.
argument-hint: "[branch]  (optional; defaults to the current branch)"
disable-model-invocation: true
allowed-tools: Bash(git branch:*), Bash(git status:*), Bash(git submodule status:*), Bash(gh pr list:*), Bash(gh pr view:*)
---

## Current state

- Branch: !`git branch --show-current`
- Working tree: !`git status --short | grep -v '.claude/settings.local.json' || echo '(clean aside from settings.local.json)'`
- Submodule pointers: !`git submodule status private/renet private/account private/elite private/homebrew-tap 2>/dev/null || echo '(unavailable)'`
- Open PRs on the current branch:
  !`cb="$(git branch --show-current)"; for r in console renet account elite homebrew-tap; do p=$(gh pr list --repo rediacc/$r --head "$cb" --state open --json number,title,mergeStateStatus --jq '.[] | "  #\(.number) [\(.mergeStateStatus)] \(.title)"' 2>/dev/null); [ -n "$p" ] && echo "rediacc/$r:" && echo "$p"; done; true`

## Task: land the stacked PRs for branch `$ARGUMENTS`

Merge the current branch's coordinated PRs (parent repo `rediacc/console` + any submodule PRs on the **same branch name**) and end on a clean local `main`. If `$ARGUMENTS` is empty, use the current branch. **This is the release path: a merge to `console/main` auto-triggers the edge deploy (`cd-v2.yml`) UNLESS the PR carries the `bump-none` label, in which case the merge is deliberately release-free and steps 5 and 6 shrink to almost nothing. Only run when the user has asked to land the PRs.**

Submodule map (path → GitHub repo): `private/renet` → `rediacc/renet`, `private/account` → `rediacc/account`, `private/elite` → `rediacc/elite`, `private/homebrew-tap` → `rediacc/homebrew-tap`.

### 0. Preconditions (stop and report if any fail)

### Console itself has TWO remotes, and only one of them is GitHub

`origin` is GitHub; `gitlab` is `gitlab.rediacc.io/rediacc-org/github/console.git`. This is
the same lesson as the sibling repos below, one level up: PR and merge tooling that assumes
GitHub silently does the wrong thing elsewhere, so check `git remote -v` before reasoning
about "the remote". Nothing pushes to `gitlab` automatically, which is why step 6b exists.
The remote lives only in local `.git/config`, so a fresh clone does not have it and step 6b
will report a skip until someone adds it back.

### Sibling repos under `private/` that are NOT submodules

Some checkouts contain independent git repos under `private/` that are **not** console submodules and are gitignored. They are invisible to `git status`, to `git submodule status`, and to every submodule-shaped instruction here. Agents have repeatedly assumed everything under `private/` is a submodule and walked straight past uncommitted or unmerged work in them.

Discover them, never hardcode them:

```bash
for d in private/*/; do
  d="${d%/}"; [ -e "$d/.git" ] || continue
  git config -f .gitmodules --get-regexp path 2>/dev/null \
    | awk '{print $2}' | grep -qx "$d" || echo "NON-SUBMODULE: $d"
done
```

For each one found:
- It is **NOT** part of the console PR. Never `git add` it, never bump a pointer for it, never sweep it into the snapshot. Console gitignores it deliberately.
- **Do** check it for uncommitted changes and unmerged branches, and report what you find. Do not commit, merge, or delete branches in it without an explicit request.
- Its remote may not be GitHub. Check `git -C <dir> remote get-url origin` before reaching for `gh`; PR/merge tooling that assumes GitHub silently fails elsewhere.
- Reading ahead/behind: `git rev-list --left-right --count origin/main...HEAD` prints `<on main only> <on branch only>`. The **second** number is the branch's own unmerged commits. Misreading it as "behind" turns weeks of unmerged work into "stale checkout, ignore it", and this has actually happened.

### Stray worktrees from past sessions

`git worktree list` can hold entries this session never created: a prior session's
scratch worktree, abandoned mid-task. They are invisible to everything above: `git status`
in the main checkout says nothing about them, and neither does the §0 sibling-repo check.

Discover them every run, before landing anything:

```bash
git worktree list
```

For each entry besides the one you are running in, check what it actually holds before
touching it, the same "identify whose work it is first" rule the dirty-tree precondition
below applies to the main checkout, just one directory over:

```bash
git -C <worktree-path> status --short
git -C <worktree-path> diff --stat  # and per-submodule, if any submodule shows dirty too
```

A worktree with nothing dirty and nothing unpushed is debris, so remove it:

```bash
git worktree remove <worktree-path> --force
git worktree prune
```

A worktree with dirty content is **not** automatically debris, even if it looks stale.
Verify, per file, whether the content is safe to discard before removing anything:
- **Byte-identical to (or a strict subset of) what the current `main` already has**
  (`diff <worktree-file> <main-checkout-equivalent>`) → safe, the work already landed by some
  other path and this is a leftover draft. Removing the worktree loses nothing.
- **Not found in `main`, not matched by any open PR, genuinely orphaned** → do not delete
  silently. Report what it is and ask, the same as an unclear dirty file in the main tree.
  Worktree content has exactly the same loss risk as working-tree content, it is just easier
  to forget it exists.

Observed live 2026-08-01: six stray worktrees had accumulated in one checkout. Two held real,
substantial uncommitted work from other sessions (a ~270-line CLI+Go feature, six locale
files' worth of in-progress translation). Both turned out to be fully superseded by `main`
(verified byte-identical / a strict subset before deleting), but that was established by
checking, not assumed from how old or untouched the worktree looked.

**Creating a new worktree from inside `/pr-merge` (or any assistant session) is hook-blocked.**
`.claude/hooks/pre-bash/block-worktree-add.sh` refuses `git worktree add` from the assistant's
own Bash tool unconditionally. If this flow genuinely needs one (it normally does not; steps
4-6 operate on the existing checkout), ask the operator to run the command themselves via the
`!` prefix. This does not affect step 7's `git checkout -b <MMDD-N>` guidance, which creates a
branch in the current checkout, not a new worktree, and is unaffected by the hook.

- Current branch is **not** `main`, and it matches the branch shown above (or the `$ARGUMENTS` override).
- Working tree is clean except `.claude/settings.local.json` (leave that uncommitted; never `git add` it).

  **If it is NOT clean, do not just stop. Identify whose work it is first.** This tree is
  shared: a concurrent session may hold uncommitted work in it, and that work is *not* part of
  this land. Steps 4 and 6 run `git checkout main` / `git merge --ff-only`, which carry
  uncommitted changes across silently when they do not conflict and abort mid-way when they do.
  Neither outcome is one you want to discover after a merge has already landed.

  So: report what is dirty and who it belongs to, and **never** `git add`, `stash`, `restore`
  or `checkout` those paths to make the precondition pass, because that destroys another session's
  work and is banned by CLAUDE.md. Either the operator lands with the dirty tree acknowledged
  (the changes ride along untouched, which is safe as long as they do not overlap what `main`
  moved), or the other session commits first. Observed live: a session held 18 uncommitted
  paths through a `/pr-merge`; nothing was lost, but only because `main`'s two new commits
  happened to touch none of them.

  If the dirty path **does** overlap what `main` moved, `git checkout main` aborts outright
  (it will not silently clobber). If, on investigation, the diff is genuinely orphaned, with no
  commit in the branch's own history ever referenced it, it sat untouched across many rounds,
  and it is not part of anything currently in flight (check `git log --all -- <path>` and think
  about whether the content is even still needed, e.g. a semver range bump the lockfile already
  satisfies), the running session may commit it itself (never stash/discard) to unblock the
  checkout, with a message stating plainly that it was found orphaned and why it's safe to land.
  This is committing to preserve, not deciding the change was wanted; if genuinely unsure whose
  work it is or why it exists, stop and ask instead.
- A `rediacc/console` PR exists for this branch. Note its number.
- The console PR should arrive at the babysitter's finish line: **flipped ready, Claude-reviewed (a `<!-- claude-reviewed: <sha> -->` marker matching the current head), and zero unresolved review threads**, with the latest console CI run green (`gh run list --repo rediacc/console --branch <branch> --workflow "Console CI" --limit 1`, then confirm `conclusion=success`). If it is still a draft, flip it ready (`gh pr ready`; the `block-premature-ready` hook verifies `CI Complete` is green), wait for the Claude review to complete, and resolve its threads before proceeding. Never merge over red or over unresolved threads.
- `/code-review ultra` is available as an optional deep pre-land review for a big wave (operator-invoked; it does not replace the automated Claude review).

### 1. Merge submodule PRs first (submodule-first, rebase)
**All 5 repos (console + 4 submodules) are rebase-merge only, since 2026-07-30.**
`--squash` is rejected outright: `gh pr merge <n> --squash` fails with `GraphQL: Squash merges
are not allowed on this repository.` Do not try it first and fall back. Go straight to
`--rebase`. `git branch --merged` lies about ancestry on these repos (a rebased PR's commits are
never literally on the base branch under the old SHAs), so judge "is this landed" by PR **state**
(`gh pr view --json state` → `MERGED`), never by `--merged`/`--contains`.

For each submodule that has an **open PR on this branch** (check the list above):
- Confirm `mergeStateStatus` is `CLEAN` and there are **no unresolved bot review threads** (`gh api graphql` reviewThreads → all `isResolved:true`). If unresolved threads remain, resolve them first (substantive reply + `resolveReviewThread`), because they block the console `Submodule Branches` gate while the console PR is still open.
  - A **failing but non-required** check (e.g. a broken submodule Claude Review job) shows as `mergeStateStatus: UNSTABLE`, not `CLEAN`, and that alone does not mean stop. Confirm with GraphQL whether it's actually required before treating it as a blocker: `pullRequest.commits.nodes[].commit.statusCheckRollup.contexts.nodes[].isRequired(pullRequestNumber: <n>)`. `isRequired:false` on the only failing context means the PR is safely mergeable despite UNSTABLE.
- Rebase-merge: `gh pr merge <n> --repo rediacc/<r> --rebase`. **Do not delete the branch** (`delete_branch_on_merge` is false on submodules; keeping it preserves the gate's fallback path).
- Capture the new submodule `main` HEAD: `gh api repos/rediacc/<r>/commits/main --jq .sha`. This is the **rebased tip commit**, a new SHA even for a single-commit PR (rebase always creates new commit objects), tree-identical to the branch tip but not the same object.

### 2. Update console submodule pointers to the merged commits
Rebase means the branch-tip commits are **not literally on** the submodule's `main` (new SHAs from the replay), so the pointer must move. For each merged submodule:
- `git -C private/<sm> fetch origin main`
- **Safety check:** `git -C private/<sm> diff --stat <old-branch-tip-sha> <new-main-sha>` must be **empty** (rebase preserves tree content exactly; only the commit SHA changes). If it is not empty, stop: something diverged (e.g. main advanced mid-merge).
- `git -C private/<sm> checkout <new-main-sha>` (detached at the merged commit).

Then in the console repo: `git add private/renet private/account …` (only the merged pointers), commit (`chore(submodules): bump pointers to merged main commits`), and push to the branch. This re-runs console CI; the `Submodule Branches` gate now passes via the **ancestor-of-main (pointer-bump-only)** path in `.ci/scripts/quality/check-submodule-branches.sh`.

Refresh the console PR body before pushing (staleness gate reads `updatedAt`; the body must actually change): summarize the merges + pointer bump.

### 3. Wait for the fast-path run, then auto-merge the console PR
The pointer bump changed only submodule SHAs (trees verified identical in step 2), so the push is a **pointer-bump fast path**: `.ci/scripts/ci/detect-pointer-bump.sh` sets `pointer_bump_only=true` in the `initialize` job and `ci.yml` skips `build-renet` (and everything cascading from it: the other builds, tests, install-matrix, preview) plus `migration-test`, `stripe-sandbox`, `package-tests`, and `ops-tests`. Only `quality`, `review-gate`, and `ci-complete` run, so the run goes green in **minutes**, and `assert-ci-complete.sh` accepts the skipped builds under this flag. The pointer-only diff deliberately triggers **no** Claude re-review.
- Trace it with `.ci/scripts/ci/ci-trace.py --wait` (run_in_background: true). Do NOT hand-roll a loop: ad-hoc watch commands are refused by `block-adhoc-sanctioned.sh`, and a hand-rolled watch left running blocks the Stop hook. The script keys on the PR HEAD, so a watchdog rerun and a superseded run are both handled structurally. Exit 0 green, 1 red, 2 no verdict, 3 head moved. **One wait per command**. Never chain "then wait for the review marker" onto the same watch, because the notification fires on process exit and a red run posts no review, so the CI verdict would never wake you (observed 2026-08-24, ninety minutes lost).
- When `CI Complete` is green: `gh pr merge <console-pr> --repo rediacc/console --rebase --auto` (console is rebase-only too, same policy as the submodules since 2026-07-30; `--squash` is rejected here as well. `--rebase --auto` is the sanctioned merge, which GitHub lands the moment required checks are green. `--admin` is banned by the `block-admin-merge` hook; there is no place for it here).
- If `Review Complete` hasn't posted for the pointer-bump head yet (Claude Review deliberately does not re-run for a pointer-only diff, so nothing auto-triggers review-status.yml for this new SHA either): nudge it with a throwaway PR comment (`gh pr comment <console-pr> --body "..."`, fires the `issue_comment` trigger). The currency check recognizes a gitlink-only diff as reviewed-equivalent, so this posts clean without spending review budget.
- Verify: `gh pr view <console-pr> --repo rediacc/console --json state` → `MERGED`, and capture `console/main` HEAD.

### 4. Check out main (first pass, since it will go stale again in step 5, see step 6)
- `git fetch origin --prune`
- `git checkout main && git merge --ff-only origin/main`
- `git submodule update --init --recursive` takes **all** submodules, not just the merged ones. The old form named only the merged pointers, which left `private/homebrew-tap` and `private/elite` sitting at whatever commit the previous branch had them at while `main`'s record moved on.
- Verify: local `main` == `origin/main`, working tree clean (only `settings.local.json` may differ), `git submodule status` shows no `+`/`-`.

### 5. Watch the release land (the merge to main IS the edge release, unless bump-none)

**FIRST, CHECK FOR `bump-none`. A release-free merge is a normal outcome, not a missing step.**

```bash
gh pr view <console-pr> --repo rediacc/console --json labels -q '[.labels[].name] | join(", ")'
```

If the label set contains `bump-none`, the automated review has declared this merge earns no
release: no git tag, no GitHub Release, no R2 upload, **no edge deploy**. Its commits ship with
the next release-worthy merge. Console CI still runs on `main` and still does the real Docker
build and push, so it must still go green, but `dispatch-release.sh` will deliberately skip and
**no Release run will ever appear**. Confirm the decision from the run rather than inferring it
from an absence:

```bash
gh run view <main-ci-run> --repo rediacc/console --json jobs \
  -q '.jobs[] | select(.name=="Finalize Release Sentinel") | .databaseId'
# then read that job's log; it prints the verdict verbatim, e.g.
#   release SKIPPED: #567 carries 'bump-none'
```

**Why this is called out.** Observed live on 2026-08-10: a session merged a `bump-none` PR,
watched Console CI on `main` go green, then went looking for the Release run and found only
runs from the previous day. Nothing was wrong. But "the release run is missing" and "the
release was correctly skipped" look identical from a run list, and the first reading invites
re-dispatching a release nobody wanted, which ships artifacts. Read the label first, then the
sentinel job's own words.

When `bump-none` applies, the rest of step 5 does not: there is no Release run to watch, no
tag to report, and nothing deployed to edge. **Step 6 also shrinks** -- CD pushes its two
`[skip ci]` commits back to `main` only when a release actually happens, so a `bump-none` merge
leaves the local checkout exactly one fast-forward behind and no submodule pointer moves.

For a release-worthy merge, everything below applies as written.

The push to `console/main` runs **Console CI** (`ci.yml`; on `main` it does the **real** Docker build+push, not the PR dry-run). When Console CI goes green, its finalize step **dispatches the Release workflow** (`cd-v2.yml`): git tag → GitHub Release → R2 upload → **deploy edge**. Both do main-only work that PR CI only dry-ran, so they can fail where every PR check was green. The land is not done until this is green.
- Find the **Console CI** run for the merged commit: `gh run list --repo rediacc/console --branch main --workflow "Console CI" --limit 3` (event `push`, matching the merged SHA), then trace it with `.ci/scripts/ci/ci-trace.py --wait` (run_in_background: true). On `main` the watchdog auto-retries transient failures; the script reads the head's check rollup, so a rerun replaces the old attempt rather than fooling it.
- Console CI on `main` is green **before** the Release run exists. Once it is, find the **Release to Edge** run (`gh run list --repo rediacc/console --workflow "Release to Edge" --limit 3`, event `workflow_dispatch`, matching the merged SHA) and watch it **by id**: `.ci/scripts/ci/ci-trace.py --run <id> --wait` (run_in_background: true). That is the run that actually tags and deploys edge.

  **NOT "the same way" as the branch watch above, and this cost a false green.** A branch's GraphQL `statusCheckRollup` does NOT contain a `workflow_dispatch` run's check runs. Measured 2026-08-26 on Release run 32968110599 (head `1c006e53`): the REST check-runs API for that exact commit showed `in_progress  Tag & Release`, while the rollup for `refs/heads/main` returned 81 contexts, state SUCCESS, **none in flight**. So `--wait --ref main` printed `GREEN ... every context succeeded or was skipped` and exited 0 while the release was mid-flight. That happened twice, including with `--until-final`. Following this step as it was previously written would certify a release that had not run. `--run` reads per-JOB conclusions instead (in-flight → exit 2, completed-success → 0, unreadable → 2).
- **Read before classifying.** If a CD step fails, surface the exact failed step loudly and read its COMPLETE log first. The edge may be left partially deployed.
- **Prefer doing nothing.** The watchdog's AI classifier auto-retries transient failures on `main` by itself (observed: a wrangler `Network connection lost.` during `d1 export` was classified `transient (0.8)` and re-dispatched without intervention). Check whether a retry is already in flight before acting; a second actor racing the watchdog is how a half-deployed edge gets worse.
- **First, classify: transient, or main-only?** The PR was green, so a failure appearing now is one of exactly two things, and they need opposite responses. The test is one command: **did this job run and pass on the PR run?**

  ```bash
  gh run view <pr-run-id> --repo rediacc/console --json jobs \
    --jq '.jobs[]|select(.name=="<failed job>")|"\(.conclusion) \(.name)"'
  ```

  - **It ran and passed on the PR → transient.** Same code, same job, different outcome. Do NOT fix it. The watchdog auto-retries these itself. (Real case: `Migration Test` passed on PR run 29844923209, then died on `main` with wrangler `Network connection lost.` mid `d1 export`, was classified `transient (0.8)` and cleared on the auto-retry. A "fix" would have been a change to working code.)
  - **It never ran on the PR, or runs differently there → main-only.** Then it is genuinely untestable by a PR, and that is what licenses the next bullet.

- **A main-only code fix goes DIRECTLY ON `main`, not through a new branch or PR.** The rule is inverted here for a reason that is about INSTRUMENTS, not urgency: **a PR cannot exercise the thing that broke.** It would go green while proving nothing, because the failing path is one PR CI structurally never runs. The verification loop for these fixes is the next `main` run, not a PR check.

  Main-only surfaces in this repo: `finalize-release-sentinel`, `pipeline-sentinel`, `check-release-state`, `build-devcontainer-manifest` (all gated `github.event_name == 'push'` / `refs/heads/main`), the entire Release workflow (`cd-v2.yml`, dispatch-only), and Docker, which PR CI only DRY-RUNS while `main` does the real build+push.

  So: commit on `main` and push. Keep it surgical (name the paths, `git add -A` is still banned) and state plainly in the report that you pushed to `main` and why.
  - This is the ONLY situation in which pushing `main` is allowed without a fresh per-task request. It applies **after** a merge performed by this command, to a failure in that merge's own release path. Everything else still goes through `/pr-babysit`.
  - It does **not** extend to re-cutting a release. Re-dispatching stays the operator's call (`gh workflow run "Release to Edge" -f ci_run_id=<console-ci-run-id> -f release_mode=retry`), because that ships artifacts rather than fixing code.

### 6. Re-sync main AFTER the release run, because CD pushes to main during step 5

**This step is not optional for a release-worthy merge, and step 4 does not cover it.** (For a `bump-none` merge there is no release run, so none of the two commits below are written and the checkout is at most one fast-forward behind. Re-sync anyway, it is cheap, but do not go hunting for a homebrew-tap pointer move that never happened.) The release run does not only tag and deploy; it pushes **two commits back to `main`** after your merge, every single time:

```
chore(release): update homebrew-tap submodule pointer [skip ci]
chore(release-state): advance contract floor to vX.Y.Z [skip ci]
```

(10 of the last 30 commits on `main` are the first of those. It is the rule, not an edge case.)

So when step 4 ran, `main` was correct. By the time step 5 finishes, the local checkout is **2 commits behind** *and* its `private/homebrew-tap` record is one commit behind what `origin/main` now records. The next session opens on a tree showing `M private/homebrew-tap`, which is the trap, because that dirty pointer is **stale, not ahead**.

Once the Release run is green:
- `git fetch origin --prune`
- `git merge --ff-only origin/main`
- `git submodule update --init --recursive`
- Verify clean: `git status --short` shows nothing but `.claude/settings.local.json`, and `git submodule status` shows no `+`/`-`.

**If a submodule still shows dirty, decide by which commit is NEWER, never by whose work it is:**

```bash
rec=$(git ls-tree HEAD private/<sm> | awk '{print $3}')
cd private/<sm> && git fetch origin -q
git merge-base --is-ancestor "$rec" origin/main && echo "record BEHIND origin/main"
git merge-base --is-ancestor origin/main "$rec" && echo "record AHEAD"
```

Worktree **behind** the record ⇒ the checkout is stale ⇒ `git submodule update`, **commit nothing**. Committing it would roll that submodule back a release. The naive test ("this isn't my work, leave it out") gives the right answer here only by luck, and the opposite instinct ("the pointer is dirty, carry it at its latest") ships the rollback.

### 6b. Mirror `main` to the GitLab remote, so it cannot go stale again

This repo has a **second remote**, `gitlab`
(`gitlab.rediacc.io/rediacc-org/github/console.git`). It is not a live mirror and nothing
pushes to it automatically, which is exactly how it drifted: on 2026-08-23 its `main` was
found sitting at `09b0b7716` while GitHub's was at `b75c44d58`, an ancestor and months
behind. This step exists so that gap never reopens.

It goes **here**, after step 6 and before step 7, and the position is load-bearing in both
directions. Earlier than step 6 and you mirror a `main` that is two commits stale, because CD
pushes the release commits back after the merge, which is the very drift this prevents. Later
than step 7 and it dilutes step 7's hard boundary, whose whole subject is that the session is
parked on `main` and must stop touching things.

```bash
if git remote get-url gitlab >/dev/null 2>&1; then
    GIT_TERMINAL_PROMPT=0 timeout 120 \
        git push gitlab refs/heads/main:refs/heads/main --follow-tags
else
    echo "no gitlab remote configured in this checkout; skipping (report it)"
fi
```

Four things this must respect, in order of how likely they are to bite:

- **The remote may not exist.** `gitlab` lives only in local `.git/config`; it is not tracked,
  so a fresh clone does not have it. Probe with `git remote get-url gitlab` and, if it is
  absent, **report and continue**. A missing mirror must never fail a merge that already
  landed.
- **Credentials may be absent or expired.** GitLab is self-hosted and answers a redirect to a
  sign-in page. `GIT_TERMINAL_PROMPT=0` plus a timeout is what stops a non-interactive session
  hanging on a credential prompt. A skip you report beats a hang you do not.
- **Push the refspec explicitly. Never `--mirror` from a working checkout.** In a working tree
  `--mirror` also pushes `refs/remotes/*` and deletes anything on GitLab not present locally.
  The mirror form is correct only from a bare mirror clone during a deliberate history
  rewrite, which is an operator-run one-off, not this step.
- **Never force.** Once both remotes share history this is always a fast-forward. If it is
  ever rejected as non-fast-forward, GitLab has diverged again: **report and stop**, do not
  reach for a force flag. A forced push from a stale local `main` would silently overwrite the
  mirror, and `.claude/hooks/pre-bash/block-git-force-push.sh` will refuse it anyway.

Report the outcome in step 8 either way, including a skip. A mirror that quietly stops being
written is indistinguishable from one that is up to date, which is how the first drift went
unnoticed for months.

### 7. Hand the tree back safely: you are now sitting on `main`

Steps 4 and 6 leave the checkout on `main`, which is correct for verifying the release but is a
**loaded gun for whatever happens next**: `main` is the one branch this repo forbids pushing,
and a tree parked there invites the next piece of work to be written straight onto it.

That is not hypothetical. A session finished a `/pr-merge`, stayed on `main`, and built an
entire feature there, 26 new files across 18 paths, before anything noticed. It reached a
branch only because `/pr-babysit` happened to be invoked afterwards and created one. Nothing
was lost, but the recovery was luck, not design: had the operator not run `/pr-babysit`, the
work would still be uncommitted on `main`, one careless `git commit` away from a forbidden push.

So finish by making the state explicit rather than leaving it implied:

- Confirm and **state in the report** that the checkout is on `main` and that `main` is
  read-only here: the next task must start with a fresh `MMDD-N` branch (`/pr-babysit` does
  this, or `git checkout -b <MMDD-N>` by hand) **before** any tracked file is edited.
- If the tree already carries uncommitted work (the §0 shared-tree case), say so again here:
  that work is now sitting on `main` and needs a branch before it can be committed at all.
- Do **not** pre-create the next branch yourself. The branch name encodes the next wave's date
  and number, and guessing it produces stray `MMDD-N` refs that the next `/pr-babysit` then has
  to skip past.

### 8. Report
State each merged commit (renet / account / console → their rebased-tip SHAs on main), confirm local `main` is in sync, **state the step-6b GitLab mirror outcome explicitly, including a skip and its reason**, and give the release outcome: Console CI green, Release/CD green with the new version tag + edge deployed (or the exact failed step if not). If step 5 required a fix pushed directly to `main`, state that explicitly with its SHA and the failure it repaired. Close with the step-7 hand-back note (on `main`, branch before editing). **Do not** merge anything else or re-cut a release.
