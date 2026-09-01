## SESSION f88f9be7 2026-09-01T15:07:27Z

`/pr-merge` is RUNNING on `0831-1`, PR #583. The operator invoked it. Resume at the step
below; do NOT restart the flow.

## Already landed (do NOT redo)

1. **`rediacc/account#84` is MERGED** -- rebase-merged to `account/main` = `3d8dc142d`;
   branch deleted (`delete_branch_on_merge: true` on all five repos).
2. **`private/account` pointer bumped** to it, after the mandatory check:
   `git -C private/account diff --stat dfe648e4c 3d8dc142d` was EMPTY.
3. **Pushed head `0875535bb`**; CI on it RUNNING, 6 contexts in flight.
4. PR body refreshed via `gh api repos/<o>/<r>/pulls/<n> -X PATCH -F body=@<file>`
   (`gh pr edit --body-file` is hook-blocked).

## Nothing waits on the operator

#583 was stuck because the OLD head `2f94fe197` was green with no review run against it.
`Claude Review` fires on `workflow_run: ["Console CI"] completed`, so a green run on a NEW
head triggers it; the head moved, so the path exists. Escape hatch if delivery misses
(documented in `claude-review.yml`): `gh workflow run "Claude Review" -f pr_number=583`.
Do NOT use `--admin`: hook-banned and unnecessary.

## Right now

- **ONE COMMIT UNPUSHED**: `e8b10da45` (`check:ci-judged-rule-wiring`). The
  `block-merge-with-unpushed` guard added this session REFUSES `gh pr merge` until it is
  pushed -- deliberately, since merging deletes the branch under it.
- Watch alive on `0875535bb` (task `b93wjzvqa`); mail waiter alive (`bpspozekj`).
- Pushing supersedes the in-flight run. Expected: its head is superseded either way.

## Next action

1. `rm -f .ci/cache/gate-durations.json && npm run ci:quick` (275 gates). It must judge
   the CURRENT tree -- `block-unverified-push.sh` refuses otherwise, and committing
   anything after the run invalidates it. Commit FIRST, then gate, then push.
2. `git push origin 0831-1`.
3. **Poll `gh api repos/rediacc/console/pulls/583 --jq .head.sha` until it shows the new
   head BEFORE arming the watch.** The API lagged ~30s twice today; a watch armed early
   traced the stale head and exited 1 "superseded". Then arm
   `.ci/scripts/ci/ci-trace.py --wait --until-final` in the background.
4. On green: review fires, `Review Complete` posts, then
   `gh pr merge 583 --repo rediacc/console --rebase --auto`. Console is REBASE-ONLY. If
   `--rebase` errors "This branch can't be rebased", check
   `git merge-base --is-ancestor origin/main origin/0831-1`; only on a pure fast-forward,
   `git push origin origin/0831-1:main`.
5. Then steps 4-8: checkout `main`; watch Console CI on main, then **Release to Edge BY
   ID** (`--run <id>`, never `--ref main` -- a workflow_dispatch run is absent from the
   branch rollup and `--ref main` printed a false GREEN twice); re-sync after CD pushes
   its two `[skip ci]` commits; mirror to `gitlab`; hand-back note.
6. Only then CronDelete `f892a1f9` and `b4bff02e`. ARMED on purpose: step 2 starts a run.

## Volatile facts a fresh session would get wrong

- **`private/growth` has ~1430 dirty paths and is NOT a submodule** -- gitignored, another
  workstream's. Never `git add` it. `private/generative` is clean. Both on gitlab.
- An `E2E Workers (opensuse-16.0)` red on an earlier head was an upstream mirror 403.
  PROBED: same URL returns HTTP 200 now. Transient, watchdog-owned; do not "fix" it.
- Calibration is NOT deterministic: 14/14 was one draw, a 20-fixture run scored 17/20.
  `SHAPE_PROMPT` is deliberately ABSENT from `.ci/config/rubric-calibration.json`.
- `check:ci-git-history-depth` deliberately does NOT follow the step->script hop: 89 false
  findings, because the scripts are already shallow-safe.
- No round log for this wave; STATE.md is the artifact.

## Open, not fixed

`[>] f46112c0`, leased to `b93wjzvqa` until 16:11Z. Peer `a276391d`'s `BACKUP_S3_BUCKET`
finding needs credentials neither session has.
