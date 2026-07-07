---
description: Commit uncommitted work across the console monorepo and its submodules, open coordinated PRs (submodule-first), and babysit CI to all-green: run local gates, reply to and resolve bot reviews, and loop on failures. Stops at green PRs; does not merge. Use after broad changes when you want PRs opened and driven green.
argument-hint: "[short summary of the change to seed PR titles/descriptions]"
disable-model-invocation: true
allowed-tools: Bash(git branch:*), Bash(git status:*), Bash(git submodule status:*), Bash(date:*)
---

## Current state

- Today (branch base): !`date +%m%d`  (feature branches are `MMDD-N`)
- Current branch: !`git branch --show-current`
- Console tree (excl. settings.local.json): !`git status --short | grep -v '.claude/settings.local.json' | wc -l | tr -d ' '` changed path(s)
- Submodules with changes: !`git status --short private/renet private/account private/elite private/homebrew-tap 2>/dev/null || echo '(none)'`
- Existing date branches (console remote): !`git branch -r | grep "$(date +%m%d)-" || echo '(none yet)'`

## Task: open coordinated PRs and drive CI to all-green

Take the uncommitted work in this monorepo (console parent + any dirty submodules), land it on coordinated feature branches, open PRs submodule-first, and babysit CI until **every** check on **every** PR is green. **Do NOT merge and do NOT push to `main`.** Green PRs are the finish line; `/pr-merge` lands them afterward. `$ARGUMENTS`, if given, is a short summary of the change to seed PR titles/descriptions; otherwise infer intent from the diff.

`CLAUDE.md` is authoritative for the repo's CI fix cycle, watchdog behavior, BLOCKER convention, and lockfile/i18n/deps quick-fixes. This command is the orchestration around those rules.

**First, figure out where you are** and skip ahead accordingly:
- Uncommitted work, no PRs yet → run the full flow from step 1.
- Branches already pushed and PRs open for this work → resume at step 6 (CI) and step 7 (bot reviews); do not re-create anything.

### Guardrails (never violate)
- **Never** `git restore` / `git reset` / `git checkout` a tracked path to discard work. Commit ALL of it (staged + unstaged). If something is clearly an accidental artifact (a large binary, build output, tsc-emit `.js` shadowing a `.ts`), unstage it and gitignore it (keep the file on disk) and flag it. Do not delete the user's work.
- **Never** push to `main`, and **never** merge a PR.
- Leave `.claude/settings.local.json` uncommitted when it is only local-permission noise.
- Submodule-first, every cycle: commit + push + PR each dirty submodule before the parent, and re-point the parent's submodule pointer.

### 1. Survey
`git status` in console and each submodule that has changes (see the list above). Identify what changed and which submodules are involved. Scan for stray artifacts that must not be committed (files larger than ~5MB, ELF/binaries, build output). Unstage + gitignore any; flag them.

### 2. Branch naming
Base is today's `MMDD` (shown above). In **each** repo (console + every dirty submodule), run `git fetch origin --prune` first (the state block above reads possibly-stale local refs), then `git branch -r | grep <MMDD>` and choose the next free `<MMDD>-<N>`, using the **same N** across all of them.

### 3. Submodules first
For each dirty submodule (`private/renet`, `private/account`, ...):
- Verify it is at/on `origin/main`, then `git checkout -b <MMDD>-N`.
- `git add -A` (excluding flagged artifacts), commit with a Conventional-Commit message.
- Push to **origin** (GitHub). Console CI submodule-inits from GitHub, not GitLab, so a GitLab-only push is invisible to it.
- `gh pr create` with a Conventional-Commit title.

### 4. Console
- `git checkout -b <MMDD>-N`, `git add -A`, then unstage `.claude/settings.local.json` if it is local noise.
- Confirm the submodule pointers are staged at the **new** submodule branch commits (`git ls-files -s private/renet private/account`).
- Commit (Conventional-Commit title), then `git fetch origin && git rebase origin/main` (commit first, the tree is dirty).
  - Conflicts: **never** resolve lockfiles wholesale. Do targeted resolution, then `npx -y npm@10 ci --dry-run` in each touched workspace (root, `private/account`, `private/account/web`, `private/account/e2e`). Regenerate search indexes with `cd packages/www && node scripts/generate-search-index.js`; never hand-merge them. For generated types/docs, re-run their generator; never hand-edit.
- Push and `gh pr create`. In the description, give the key numbers and, crucially, spell out any **user-facing surface change** (e.g. CLI commands added/removed) versus what is provably unchanged, and link the submodule PRs.

### 5. Local gates before trusting CI
Run the `npm run ci` sub-checks locally: parallelize independent ones and background the slow ones (`check:types`, `lint:unused`, `check:lint`, `check:ci-renet`, `check:ci-account-server`, `check:test-cli`). Fix failures properly (no suppression without a substantive `BLOCKER:` reason). Also build www and the CLI bundle (`./rdc.sh --version`) to catch build breaks. Known **environmental** local reds that are NOT real failures: `validate:tutorial-audio` (R2 media cache absent locally) and `check:actions` (not a CI gate; pre-existing action-pin freshness).

### 6. Babysit CI to green
- Background-watch each run: `gh run watch <id> --repo rediacc/console --exit-status --interval 100` (run_in_background: true); the harness notifies on completion.
- On failure, read the **COMPLETE** failed-step log before diagnosing (`gh run view --repo rediacc/console --job <id> --log`). Suspect your own commits first; reproduce in a clean room before calling anything "transient". Fix, commit (submodule-first, re-point parent), push. **Batch** fixes into one push (each push restarts the whole pipeline).
- Watchdog: a run ending `cancelled` **with a failed job** was killed by the watchdog for that failure. `cancelled` is NEVER green. `cancelled` with zero failed jobs means your own newer push superseded it. Prefer a fresh commit over `gh run rerun` (rerun only genuinely-transient failures on **failed**, not cancelled, runs).
- **Every** job must be green (100+ steps; the deploy-preview job is among the last), not just quality and builds.

### 7. Bot reviews (each push gets reviewed within minutes)
After each push, fetch review comments on **every** PR (console + submodules): `gh api repos/<owner>/<repo>/pulls/<n>/comments`. Fix what is real; reply **substantively** to every thread (low-effort "done"/"fixed" do not count); resolve each thread via GraphQL `resolveReviewThread` (get thread IDs with a `reviewThreads` query). Unresolved threads fail `Quality / Review Gate` (console) and `Quality / Submodule Branches` (submodule PRs). Re-check for fresh comments after each push, before the gates do.

### 8. PR description freshness
Refresh the console PR body **immediately before every subsequent push** (the staleness gate compares `updatedAt` to new commits). The body must actually change: summarize the new commits; identical text does not bump the timestamp.

### 9. Persist until green, then stop
This may take many CI cycles over a long time. Keep looping (investigate, fix, commit submodule-first, re-point, push, watch) until every job on every PR is green. For genuinely idle waits on external state the harness cannot track, schedule a periodic wake-up. Record durable state in the session memory as you go, so a context summary does not lose the thread. When all PRs are green, report the PR links + headline results and **stop**. Do not merge and do not push to `main`.
