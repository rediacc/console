---
description: Land the current branch's stacked PRs: squash-merge submodule PRs first, bump the console pointers to the merged commits, admin-squash-merge the console PR, check out main, then watch the release pipeline (Console CI on main + CD edge deploy) to green. Use when all three PRs are green and you want to release without re-typing the submodule sequence and --admin.
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

### 4. Check out main
- `git fetch origin --prune`
- `git checkout main && git merge --ff-only origin/main`
- `git submodule update --init private/renet private/account …`
- Verify: local `main` == `origin/main`, working tree clean (only `settings.local.json` may differ), submodules at the merged commits (`git submodule status` shows no `+`/`-`).

### 5. Watch the release land (the merge to main IS the edge release)
The push to `console/main` runs **Console CI** (`ci.yml`; on `main` it does the **real** Docker build+push, not the PR dry-run). When Console CI goes green, its finalize step **dispatches the Release workflow** (`cd-v2.yml`): git tag → GitHub Release → R2 upload → **deploy edge**. Both do main-only work that PR CI only dry-ran, so they can fail where every PR check was green. The land is not done until this is green.
- Find the **Console CI** run for the merged commit: `gh run list --repo rediacc/console --branch main --workflow "Console CI" --limit 3` (event `push`, matching the merged SHA), then arm a terminal-state watch (run_in_background: true; the process exit notifies on completion — do NOT use `gh run watch`, it has dropped silently on terminal runs): `R=<run-id>; until [ "$(gh run view $R --repo rediacc/console --json status --jq .status)" = "completed" ]; do sleep 20; done; gh run view $R --repo rediacc/console --json conclusion,jobs`.
- Console CI on `main` is green **before** the Release run exists. Once it is, find the **Release** run (`gh run list --repo rediacc/console --workflow "Release" --limit 3`, event `workflow_dispatch`, matching the merged SHA) and background-watch it the same way. That is the run that actually tags and deploys edge.
- **Monitor-and-report only.** If a CD step fails, surface the exact failed step loudly and read its COMPLETE log before classifying. The edge may be left partially deployed. **Do NOT** push to `main`, re-run, or re-dispatch the release to "fix" it: a code fix goes through a fresh PR (use `/pr-babysit`); a genuinely transient infra failure is the user's call to re-dispatch (`gh workflow run "Release" -f ci_run_id=<console-ci-run-id> -f release_mode=retry`).

### 6. Report
State each merged commit (renet / account / console → their squash SHAs on main), confirm local `main` is in sync, and give the release outcome: Console CI green, Release/CD green with the new version tag + edge deployed (or the exact failed step if not). **Do not** merge anything else, push to `main`, or re-cut a release.
