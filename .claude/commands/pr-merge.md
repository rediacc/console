---
description: Land the current branch's stacked PRs: squash-merge submodule PRs first, bump the console pointers to the merged commits, wait for the fast-path CI run and auto-merge the console PR (flipping it ready first if needed), check out main, watch the release pipeline (Console CI on main + CD edge deploy) to green, then RE-SYNC main because CD pushes a homebrew-tap pointer bump and a release-state commit back to main after the merge. Use when the console PR is ready + Claude-reviewed with threads resolved, and you want to release without re-typing the submodule sequence.
argument-hint: "[branch]  (optional; defaults to the current branch)"
disable-model-invocation: true
allowed-tools: Bash(git branch:*), Bash(git status:*), Bash(git submodule status:*), Bash(gh pr list:*), Bash(gh pr view:*)
---

## Current state

- Branch: !`git branch --show-current`
- Working tree: !`git status --short | grep -v '.claude/settings.local.json' || echo '(clean aside from settings.local.json)'`
- Submodule pointers: !`git submodule status private/renet private/account private/elite private/homebrew-tap 2>/dev/null`
- Open PRs on the current branch:
  !`cb="$(git branch --show-current)"; for r in console renet account elite homebrew-tap; do p=$(gh pr list --repo rediacc/$r --head "$cb" --state open --json number,title,mergeStateStatus --jq '.[] | "  #\(.number) [\(.mergeStateStatus)] \(.title)"' 2>/dev/null); [ -n "$p" ] && echo "rediacc/$r:" && echo "$p"; done; true`

## Task: land the stacked PRs for branch `$ARGUMENTS`

Merge the current branch's coordinated PRs (parent repo `rediacc/console` + any submodule PRs on the **same branch name**) and end on a clean local `main`. If `$ARGUMENTS` is empty, use the current branch. **This is the release path: a merge to `console/main` auto-triggers the edge deploy (`cd-v2.yml`). Only run when the user has asked to land the PRs.**

Submodule map (path → GitHub repo): `private/renet` → `rediacc/renet`, `private/account` → `rediacc/account`, `private/elite` → `rediacc/elite`, `private/homebrew-tap` → `rediacc/homebrew-tap`.

### 0. Preconditions (stop and report if any fail)

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
- Reading ahead/behind: `git rev-list --left-right --count origin/main...HEAD` prints `<on main only> <on branch only>`. The **second** number is the branch's own unmerged commits. Misreading it as "behind" turns weeks of unmerged work into "stale checkout, ignore it" — this has actually happened.

- Current branch is **not** `main`, and it matches the branch shown above (or the `$ARGUMENTS` override).
- Working tree is clean except `.claude/settings.local.json` (leave that uncommitted; never `git add` it).

  **If it is NOT clean, do not just stop — identify whose work it is first.** This tree is
  shared: a concurrent session may hold uncommitted work in it, and that work is *not* part of
  this land. Steps 4 and 6 run `git checkout main` / `git merge --ff-only`, which carry
  uncommitted changes across silently when they do not conflict and abort mid-way when they do.
  Neither outcome is one you want to discover after a merge has already landed.

  So: report what is dirty and who it belongs to, and **never** `git add`, `stash`, `restore`
  or `checkout` those paths to make the precondition pass — that destroys another session's
  work and is banned by CLAUDE.md. Either the operator lands with the dirty tree acknowledged
  (the changes ride along untouched, which is safe as long as they do not overlap what `main`
  moved), or the other session commits first. Observed live: a session held 18 uncommitted
  paths through a `/pr-merge`; nothing was lost, but only because `main`'s two new commits
  happened to touch none of them.
- A `rediacc/console` PR exists for this branch. Note its number.
- The console PR should arrive at the babysitter's finish line: **flipped ready, Claude-reviewed (a `<!-- claude-reviewed: <sha> -->` marker matching the current head), and zero unresolved review threads**, with the latest console CI run green (`gh run list --repo rediacc/console --branch <branch> --workflow "Console CI" --limit 1`, then confirm `conclusion=success`). If it is still a draft, flip it ready (`gh pr ready`; the `block-premature-ready` hook verifies `CI Complete` is green), wait for the Claude review to complete, and resolve its threads before proceeding. Never merge over red or over unresolved threads.
- `/code-review ultra` is available as an optional deep pre-land review for a big wave (operator-invoked; it does not replace the automated Claude review).

### 1. Merge submodule PRs first (submodule-first, squash)
For each submodule that has an **open PR on this branch** (check the list above):
- Confirm `mergeStateStatus` is `CLEAN` and there are **no unresolved bot review threads** (`gh api graphql` reviewThreads → all `isResolved:true`). If unresolved threads remain, resolve them first (substantive reply + `resolveReviewThread`), because they block the console `Submodule Branches` gate while the console PR is still open.
- Squash-merge: `gh pr merge <n> --repo rediacc/<r> --squash`. **Do not delete the branch** (`delete_branch_on_merge` is false on submodules; keeping it preserves the gate's fallback path).
- Capture the new submodule `main` HEAD: `gh api repos/rediacc/<r>/commits/main --jq .sha`. This is the **squash commit**, not the branch tip.

### 2. Update console submodule pointers to the merged commits
Squash means the branch-tip commits are **not** on the submodule's `main`, so the pointer must move. For each merged submodule:
- `git -C private/<sm> fetch origin main`
- **Safety check:** `git -C private/<sm> diff --stat <old-branch-tip-sha> <new-main-sha>` must be **empty** (squash tree == branch tip; content is unchanged). If it is not empty, stop: something diverged (e.g. main advanced mid-merge).
- `git -C private/<sm> checkout <new-main-sha>` (detached at the merged commit).

Then in the console repo: `git add private/renet private/account …` (only the merged pointers), commit (`chore(submodules): bump pointers to merged main commits`), and push to the branch. This re-runs console CI; the `Submodule Branches` gate now passes via the **ancestor-of-main (pointer-bump-only)** path in `.ci/scripts/quality/check-submodule-branches.sh`.

Refresh the console PR body before pushing (staleness gate reads `updatedAt`; the body must actually change): summarize the merges + pointer bump.

### 3. Wait for the fast-path run, then auto-merge the console PR
The pointer bump changed only submodule SHAs (trees verified identical in step 2), so the push is a **pointer-bump fast path**: `.ci/scripts/ci/detect-pointer-bump.sh` sets `pointer_bump_only=true` in the `initialize` job and `ci.yml` skips `build-renet` (and everything cascading from it: the other builds, tests, install-matrix, preview) plus `migration-test`, `stripe-sandbox`, `package-tests`, and `ops-tests`. Only `quality`, `review-gate`, and `ci-complete` run, so the run goes green in **minutes**, and `assert-ci-complete.sh` accepts the skipped builds under this flag. The pointer-only diff deliberately triggers **no** Claude re-review.
- Arm the standard terminal-state watch on that run (run_in_background: true; do NOT use `gh run watch`): `R=<run-id>; until [ "$(gh run view $R --repo rediacc/console --json status --jq .status)" = "completed" ]; do sleep 20; done; gh run view $R --repo rediacc/console --json conclusion,jobs`.
- When `CI Complete` is green: `gh pr merge <console-pr> --repo rediacc/console --squash --auto` (console is squash-only; `--squash --auto` is the sanctioned merge, which GitHub lands the moment required checks are green. `--admin` is banned by the `block-admin-merge` hook; there is no place for it here).
- Verify: `gh pr view <console-pr> --repo rediacc/console --json state` → `MERGED`, and capture `console/main` HEAD.

### 4. Check out main (first pass — it will go stale again in step 5, see step 6)
- `git fetch origin --prune`
- `git checkout main && git merge --ff-only origin/main`
- `git submodule update --init --recursive` — **all** submodules, not just the merged ones. The old form named only the merged pointers, which left `private/homebrew-tap` and `private/elite` sitting at whatever commit the previous branch had them at while `main`'s record moved on.
- Verify: local `main` == `origin/main`, working tree clean (only `settings.local.json` may differ), `git submodule status` shows no `+`/`-`.

### 5. Watch the release land (the merge to main IS the edge release)
The push to `console/main` runs **Console CI** (`ci.yml`; on `main` it does the **real** Docker build+push, not the PR dry-run). When Console CI goes green, its finalize step **dispatches the Release workflow** (`cd-v2.yml`): git tag → GitHub Release → R2 upload → **deploy edge**. Both do main-only work that PR CI only dry-ran, so they can fail where every PR check was green. The land is not done until this is green.
- Find the **Console CI** run for the merged commit: `gh run list --repo rediacc/console --branch main --workflow "Console CI" --limit 3` (event `push`, matching the merged SHA), then arm a terminal-state watch (run_in_background: true; the process exit notifies on completion — do NOT use `gh run watch`, it has dropped silently on terminal runs): `R=<run-id>; until [ "$(gh run view $R --repo rediacc/console --json status --jq .status)" = "completed" ]; do sleep 20; done; gh run view $R --repo rediacc/console --json conclusion,jobs`.
- Console CI on `main` is green **before** the Release run exists. Once it is, find the **Release** run (`gh run list --repo rediacc/console --workflow "Release" --limit 3`, event `workflow_dispatch`, matching the merged SHA) and background-watch it the same way. That is the run that actually tags and deploys edge.
- **Read before classifying.** If a CD step fails, surface the exact failed step loudly and read its COMPLETE log first. The edge may be left partially deployed.
- **Prefer doing nothing.** The watchdog's AI classifier auto-retries transient failures on `main` by itself (observed: a wrangler `Network connection lost.` during `d1 export` was classified `transient (0.8)` and re-dispatched without intervention). Check whether a retry is already in flight before acting; a second actor racing the watchdog is how a half-deployed edge gets worse.
- **First, classify: transient, or main-only?** The PR was green, so a failure appearing now is one of exactly two things, and they need opposite responses. The test is one command — **did this job run and pass on the PR run?**

  ```bash
  gh run view <pr-run-id> --repo rediacc/console --json jobs \
    --jq '.jobs[]|select(.name=="<failed job>")|"\(.conclusion) \(.name)"'
  ```

  - **It ran and passed on the PR → transient.** Same code, same job, different outcome. Do NOT fix it. The watchdog auto-retries these itself. (Real case: `Migration Test` passed on PR run 29844923209, then died on `main` with wrangler `Network connection lost.` mid `d1 export`, was classified `transient (0.8)` and cleared on the auto-retry. A "fix" would have been a change to working code.)
  - **It never ran on the PR, or runs differently there → main-only.** Then it is genuinely untestable by a PR, and that is what licenses the next bullet.

- **A main-only code fix goes DIRECTLY ON `main`, not through a new branch or PR.** The rule is inverted here for a reason that is about INSTRUMENTS, not urgency: **a PR cannot exercise the thing that broke.** It would go green while proving nothing, because the failing path is one PR CI structurally never runs. The verification loop for these fixes is the next `main` run, not a PR check.

  Main-only surfaces in this repo: `finalize-release-sentinel`, `pipeline-sentinel`, `check-release-state`, `build-devcontainer-manifest` (all gated `github.event_name == 'push'` / `refs/heads/main`), the entire Release workflow (`cd-v2.yml`, dispatch-only), and Docker — which PR CI only DRY-RUNS while `main` does the real build+push.

  So: commit on `main` and push. Keep it surgical (name the paths, `git add -A` is still banned) and state plainly in the report that you pushed to `main` and why.
  - This is the ONLY situation in which pushing `main` is allowed without a fresh per-task request. It applies **after** a merge performed by this command, to a failure in that merge's own release path. Everything else still goes through `/pr-babysit`.
  - It does **not** extend to re-cutting a release. Re-dispatching stays the operator's call (`gh workflow run "Release" -f ci_run_id=<console-ci-run-id> -f release_mode=retry`), because that ships artifacts rather than fixing code.

### 6. Re-sync main AFTER the release run — CD pushes to main during step 5

**This step is not optional and step 4 does not cover it.** The release run does not only tag and deploy; it pushes **two commits back to `main`** after your merge, every single time:

```
chore(release): update homebrew-tap submodule pointer [skip ci]
chore(release-state): advance contract floor to vX.Y.Z [skip ci]
```

(10 of the last 30 commits on `main` are the first of those. It is the rule, not an edge case.)

So when step 4 ran, `main` was correct. By the time step 5 finishes, the local checkout is **2 commits behind** *and* its `private/homebrew-tap` record is one commit behind what `origin/main` now records. The next session opens on a tree showing `M private/homebrew-tap` — which is the trap, because that dirty pointer is **stale, not ahead**.

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

### 7. Hand the tree back safely — you are now sitting on `main`

Steps 4 and 6 leave the checkout on `main`, which is correct for verifying the release but is a
**loaded gun for whatever happens next**: `main` is the one branch this repo forbids pushing,
and a tree parked there invites the next piece of work to be written straight onto it.

That is not hypothetical. A session finished a `/pr-merge`, stayed on `main`, and built an
entire feature there — 26 new files across 18 paths — before anything noticed. It reached a
branch only because `/pr-babysit` happened to be invoked afterwards and created one. Nothing
was lost, but the recovery was luck, not design: had the operator not run `/pr-babysit`, the
work would still be uncommitted on `main`, one careless `git commit` away from a forbidden push.

So finish by making the state explicit rather than leaving it implied:

- Confirm and **state in the report** that the checkout is on `main` and that `main` is
  read-only here: the next task must start with a fresh `MMDD-N` branch (`/pr-babysit` does
  this, or `git checkout -b <MMDD-N>` by hand) **before** any tracked file is edited.
- If the tree already carries uncommitted work (the §0 shared-tree case), say so again here —
  that work is now sitting on `main` and needs a branch before it can be committed at all.
- Do **not** pre-create the next branch yourself. The branch name encodes the next wave's date
  and number, and guessing it produces stray `MMDD-N` refs that the next `/pr-babysit` then has
  to skip past.

### 8. Report
State each merged commit (renet / account / console → their squash SHAs on main), confirm local `main` is in sync, and give the release outcome: Console CI green, Release/CD green with the new version tag + edge deployed (or the exact failed step if not). If step 5 required a fix pushed directly to `main`, state that explicitly with its SHA and the failure it repaired. Close with the step-7 hand-back note (on `main`, branch before editing). **Do not** merge anything else or re-cut a release.
