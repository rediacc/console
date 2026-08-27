## SESSION 9d92d9b6 2026-08-27T11:45:39Z

## Where things stand

Branch `0826-3`, **27 commits, nothing pushed, no PR**. #577 (`0826-2`) is the
only open PR and must stay so. Working tree is CLEAN apart from one untracked
stray (below). Recovery tags: `preredo-0826`=3ced1a4d8, `prerebase-0826`=9f3cb9f8c,
`private/account` `prerebase-0826`=3e79b39.

Two commits landed this session:

- **`bd9df8682`** — hook-guard sweep. `check:ci-hook-integrity` had `GUARD_DIR`
  hard-wired to `pre-bash`, so `pre-edit/` and `pre-ask/` were outside BOTH
  assertions. Widened to all three chains; helper-driven cases are now seen.
  **Coverage baseline drained 8 grandfathered gaps to 0** — all 35 guards have a
  case in each direction. Twelve guards were matching MENTION rather than
  execution intent and were narrowed via `pre-bash/lib/command-scan.sh`.
- **`f38d64621`** — the resumable rebase executor, all five PLAN steps.
  `json_union` (5 invariants), `rebase-resolve` (all-or-nothing per halt),
  `rebase-continue [--execute]` (the loop). New gate
  `.ci/scripts/test/gates/test-rebase-resolve.sh`, 8 cases against REAL halted
  rebases, three-point wired. `--skip` is now banned by
  `check:ci-git-tool-safety`.

## Do not undo these

**`block-ci-polling`, `block-ci-reverse-poll` and `block-long-sleep` keep their
prose false positive**, under the operator's 2026-08-25 ruling: it fails LOUDLY
while every narrowing fails SILENTLY, and the ruling names heredoc exemption as
the worst option — which is exactly what `hook_scan_target` does. Routing them
through it was tried this session and two pinned suite cases reverted it. Their
code is byte-identical to HEAD. **Do not re-narrow them.**

`check:ci-pr-task-trailers` stays RED by operator ruling: wait for #577 to merge,
re-rebase onto `origin/main`, base the PR there. Do not weaken it, do not stack a
second PR.

## Verified state

Hook suite **1464 cases / 0 failures**. `npm run ci`: **310 gates, 18 failed**
(was 26; all seven attributable ones fixed). Every one of the 18 was
cross-referenced against the files this session touched — none is attributable
here. They are: `private/account/node_modules` is EMPTY (0 entries), which
accounts for ~15; `ruff` and `aws` are not installed, which accounts for two;
and `check:ci-pr-task-trailers`, deferred above.

## Next action

1. **Nothing is queued for this session.** Both open items are `[?]` awaiting the
   operator (`#7ff62e83` install the account submodule's deps — DEFAULT leave it,
   npm 11 rewrites the lockfile; `#c824d9d7` delete the stray
   `packages/www/--full-page`, a 97KB PNG from ANOTHER session in this shared
   worktree — DEFAULT leave it). Do not act on either without an answer.
2. When #577 merges: `git fetch`, re-rebase `0826-3` onto `origin/main`, then
   verify with `--git snapshot` before and `--git verify-rebase <file>` after.
   Expect patch-identical commits to be ABSORBED, not missing — that distinction
   is what `verify-rebase` exists for, and a commit COUNT cannot make it.
3. Only then open the PR, with `PR-TASK: f2757830`.
