## SESSION f88f9be7 2026-09-01T14:40:30Z

`/pr-merge` is RUNNING on `0831-1`, PR #583. The operator invoked it. Resume the flow at
the step below; do NOT restart it.

## Already landed (do NOT redo)

1. **`rediacc/account#84` is MERGED** -- rebase-merged to `account/main` = `3d8dc142d`;
   its branch is deleted (`delete_branch_on_merge: true` on all five repos).
2. **`private/account` pointer bumped** to it, after the mandatory check:
   `git -C private/account diff --stat dfe648e4c 3d8dc142d` was EMPTY.
3. **Pushed head `805982a9a`**, carrying 18 previously-held commits.
4. PR body refreshed (use `gh api repos/<o>/<r>/pulls/<n> -X PATCH -F body=@<file>`;
   `gh pr edit --body-file` is hook-blocked).

## The Review Complete block is GONE; nothing waits on the operator

#583 was stuck because the OLD head `2f94fe197` was green with no review run against it.
`Claude Review` fires on `workflow_run: ["Console CI"] completed`, so a green run on a NEW
head triggers it. The head moved, so the path exists. Escape hatch if delivery silently
misses (documented in `claude-review.yml`): `gh workflow run "Claude Review" -f
pr_number=583`. Do NOT use `--admin`.

## Right now

- CI on `805982a9a`: **14 contexts in flight, 1 retryable failure pending a watchdog
  rerun**. NOT actionable -- the watchdog auto-retries and racing it makes things worse.
- Watch alive: PID 500644 (`b98my7tmk`). Mail waiter alive: PID 343120 (`bpspozekj`).
- **TWO COMMITS UNPUSHED**: `79e85f0fa` (a new pre-bash guard) and `a41be0f71` (its class
  sweep). A `ci:quick` is running now because `block-unverified-push.sh` requires the gate
  run to have judged THIS tree.
- **The new guard will REFUSE `gh pr merge` until those are pushed.** That is deliberate:
  merging deletes the branch and would orphan them.

## Next action

1. On a clean `ci:quick`: `git push origin 0831-1`. This cancels the in-flight run and
   starts a fresh one -- that is the cheaper order, because the current run's head is
   superseded either way.
2. Re-arm `.ci/scripts/ci/ci-trace.py --wait --until-final` in the background, and re-read
   the head first: a watch armed during a push traced the stale head and exited 1
   ("superseded") once already this session.
3. On green: the review fires, `Review Complete` posts, then
   `gh pr merge 583 --repo rediacc/console --rebase --auto`. Console is REBASE-ONLY.
   If `--rebase` errors "This branch can't be rebased", check
   `git merge-base --is-ancestor origin/main origin/0831-1`; only on a pure fast-forward,
   `git push origin origin/0831-1:main`.
4. Then `/pr-merge` steps 4-8: checkout `main`; watch Console CI on main, then the
   **Release to Edge** run **BY ID** (`--run <id>`, never `--ref main` -- a
   workflow_dispatch run is absent from the branch rollup and `--ref main` printed a false
   GREEN twice); re-sync after CD pushes its two `[skip ci]` commits; mirror to `gitlab`;
   hand-back note.
5. Only then CronDelete `f892a1f9` and `b4bff02e`. Still deliberately ARMED, because the
   push in step 1 starts a run that needs watching.

## Volatile facts a fresh session would get wrong

- **`private/growth` has ~1430 dirty paths and is NOT a submodule** -- gitignored, another
  workstream's. Never `git add` it. `private/generative` is clean. Both are on gitlab.
- The judged-rule calibration is NOT deterministic: 14/14 was one draw, a 20-fixture run
  scored 17/20. `SHAPE_PROMPT` is deliberately ABSENT from
  `.ci/config/rubric-calibration.json`; do not "fix" that.
- `check:ci-git-history-depth` deliberately does NOT follow the step->script hop: it
  produced 89 false findings because the scripts are already shallow-safe.
- No round log exists for this wave; STATE.md is the artifact.

## Open, not fixed

`[>] f46112c0`, leased to `b98my7tmk` until 15:23Z. Peer `a276391d`'s `BACKUP_S3_BUCKET`
finding needs credentials neither session has.
