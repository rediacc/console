---
description: Land the current branch's stacked PRs: squash-merge submodule PRs first, bump the console pointers to the merged commits, admin-squash-merge the console PR, check out main, watch the release pipeline (Console CI on main + CD edge deploy) to green, then RE-SYNC main because CD pushes a homebrew-tap pointer bump and a release-state commit back to main after the merge. Use when all three PRs are green and you want to release without re-typing the submodule sequence and --admin.
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
- Current branch is **not** `main`, and it matches the branch shown above (or the `$ARGUMENTS` override).
- Working tree is clean except `.claude/settings.local.json` (leave that uncommitted; never `git add` it).
- A `rediacc/console` PR exists for this branch. Note its number.
- The latest **console** CI run for this branch is **green** (`gh run list --repo rediacc/console --branch <branch> --workflow "Console CI" --limit 1`, then confirm `conclusion=success`). If it is not green, stop and tell the user: do not admin-merge over red.

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

### 3. Merge the console PR
The pointer bump changed only submodule SHAs (trees verified identical in step 2), so the just-triggered console CI run is testing the exact code an earlier run already passed. You do **not** need to wait for it:
- `gh pr merge <console-pr> --repo rediacc/console --squash --admin` (console is squash-only; `--admin` bypasses the still-pending re-run since the content is proven-green).
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
- **Monitor-and-report only.** If a CD step fails, surface the exact failed step loudly and read its COMPLETE log before classifying. The edge may be left partially deployed. **Do NOT** push to `main`, re-run, or re-dispatch the release to "fix" it: a code fix goes through a fresh PR (use `/pr-babysit`); a genuinely transient infra failure is the user's call to re-dispatch (`gh workflow run "Release" -f ci_run_id=<console-ci-run-id> -f release_mode=retry`).

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

### 7. Report
State each merged commit (renet / account / console → their squash SHAs on main), confirm local `main` is in sync, and give the release outcome: Console CI green, Release/CD green with the new version tag + edge deployed (or the exact failed step if not). **Do not** merge anything else, push to `main`, or re-cut a release.
