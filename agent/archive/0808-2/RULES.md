# RULES: branch 0808-2 (the gate-test convention gate)

**SHARPEN THIS FILE. Do not append to it.** Settled facts and standing
constraints. Wrong rule -> edit it here, not below it.
Sharpened from `.agent/0807-5/RULES.md` on 2026-08-08 by session d136ac61.

**0807-5's branch-specific content did NOT carry forward.** That branch was the
edge smoke-test retry; its incident narrative, its `fetch_retry` reasoning and its
"do not re-cut the release" note all belong to work that has MERGED. Repeating
them here would describe a job already finished. What carried is the standing
constraints block, which belongs to the session rather than the branch.

## What this branch is

ONE commit: `check:ci-gate-id-convention`, plus its wiring. It enforces the
registration convention that 57 gate scripts already follow and that nothing
checked — which is why the 58th (mine, on #556) broke it and only a human
reviewer noticed.

## Do not re-litigate

- **The invariant is NARROW and must stay narrow.** It applies only to what a
  manifest entry's `run` EXECUTES, including one hop through an npm alias.
  Several legitimate `check:ci-*` quality gates name a gates/ script in their
  `ci: { kind: 'test', test: ... }` field — that says which CI job COVERS them,
  not what they run. Widening the rule to "any entry mentioning gates/" produces
  false positives on those three, and a gate that cries wolf gets ignored.
- **The FLOOR is load-bearing.** Fewer than 40 parsed entries means the regex
  broke; without that check every assertion would pass while measuring nothing.
- The control plants the exact 2026-08-08 shape (a gates/ script reached via
  `npm run check:ci-*`). If it ever stops firing, the gate is dead — fix the
  mutant, never delete the control.

## Context this branch was cut from (all MERGED, do not redo)

```
console main = c3428568b   v1.2.19 RELEASED (edge deployed, tag cut)
renet  main = 2a8ec0d15    (overlayfs work/work exclude, #101)
merged: console #552 #554 #555 #556, account #77, renet #100 #101
closed: renet #99 (verified duplicate), console #553 (superseded by #555)
```

**KNOWN GAP, needs its own PR:** console `main` still records renet
`325905214`, while renet main is `2a8ec0d15`. The overlayfs fix is merged in
renet but not yet referenced by console. Do NOT bolt that pointer bump onto an
unrelated PR — keeping submodule bumps separate is why renet #101 landed cleanly.

## Standing constraints

- **AUTOPILOT is active** (operator invoked `/pr-merge`, then slept). Landing PRs
  is authorised. `--admin` and force-push are NOT, and both are hook-blocked. If
  something cannot merge legitimately, **STOP AND REPORT**.
- Never push `main` directly. The single exception is /pr-merge step 5: a
  MAIN-ONLY failure in the release path of a merge this command performed. Even
  then, keep it surgical and say so loudly. Re-cutting a release is NEVER
  included — that is the operator's call.
- Never `git checkout/restore/stash/clean` to undo a mistake. Repair forward.
- Never `git add -A`. Stage by explicit path. NEVER stage
  `.claude/settings.local.json`, `private/generative`, or `private/growth` —
  those last two are GitLab-hosted sibling repos, gitignored on purpose, and
  `private/growth` currently holds 1 uncommitted path belonging to ANOTHER
  session. Leave it alone.
- **Answer the top-level review SUMMARY, not just the inline threads.** A summary
  has no thread and `review-findings: []` does not exempt it. Missed FOUR times
  in this wave, costing three force-cancelled runs. Treat resolve-threads and
  answer-summary as ONE indivisible step; notes alone demonstrably did not work.
- **A commit hash quoted in a reply has a shelf life.** GitHub's update-branch can
  rebase a PR mid-review, and every hash already posted becomes unreachable. If
  that happens, correct the thread rather than leaving a reference a reviewer
  will read as fabricated.
- To ask "did the review run?", query the WORKFLOW
  (`gh run list --workflow claude-review.yml`), never `--branch`: a
  `workflow_run` event reports the DEFAULT BRANCH's SHA. Also raise `--limit`;
  review workflows flood the list and once truncated the Console CI run out of view.
- `per_page=30` silently truncates ~95-job runs. Always `per_page=100`. A run
  reports `queued` while ANY job waits for a runner — read JOB counts, not status.
- Verify gate reachability by RUNNING it (`npx tsx scripts/ci-runner/run.ts
  --only <key>`), never by reading `gate: true` off the manifest.
- PRs on `rediacc/console` MUST be created `--draft`, then `gh pr ready` once
  `CI Complete` is green; that flip triggers the review.
- Dependency bumps: NEVER `check:deps --upgrade`. Edit the single pin, then
  `npx -y npm@10 install --package-lock-only --ignore-scripts`.
- shfmt is `-i 4 -ci`. `mapfile` is BANNED. ruff reads the GIT mode, so a
  shebanged `.py` needs `git update-index --chmod=+x`.
- No attribution trailers; no backticks in `git commit -m`; amending is
  hook-blocked — make a NEW commit.
