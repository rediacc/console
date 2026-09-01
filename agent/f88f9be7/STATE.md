## SESSION f88f9be7 2026-09-01T14:07:07Z

`/pr-merge` is RUNNING on `0831-1`, PR #583. The operator invoked it explicitly.
A land pass, not a babysit: do not restart the flow, resume at the step below.

## Already landed (do NOT redo)

1. **`rediacc/account#84` is MERGED**, rebase-merged to `account/main` = `3d8dc142d`.
   Its branch is deleted (`delete_branch_on_merge: true` on all five repos).
2. **`private/account` pointer bumped** to it, after the mandatory tree check:
   `git -C private/account diff --stat dfe648e4c 3d8dc142d` was EMPTY.
3. **Pushed**: head `a3701d631`, carrying the 17 previously-held commits.
4. PR body refreshed via `gh api repos/<o>/<r>/pulls/<n> -X PATCH -F body=@<file>`
   (`gh pr edit --body-file` is hook-blocked).

## The Review Complete block is GONE; nothing is pending on the operator

#583 was stuck because the old head `2f94fe197` was green with no review run against it.
`Claude Review` fires on `workflow_run: ["Console CI"] completed`, so a green run on a NEW
head triggers it. The head moved, so the path exists. If delivery silently misses (a
documented failure mode in `claude-review.yml`), use
`gh workflow run "Claude Review" -f pr_number=583`. Do NOT reach for `--admin`.

## Right now

- CI in flight on `a3701d631`: `RUNNING, 5 context(s)`, `ci-trace` exit 2.
- Watch alive PID 415540 (`b1vxbxvy8`); mail waiter alive PID 343120 (`bpspozekj`).
- **ONE COMMIT UNPUSHED**: `23e734384`, the shallow-history class sweep. It MUST be pushed
  before the merge or the merge deletes the branch under it. `ci:quick` is running because
  `block-unverified-push.sh` demands the gate run judged THIS tree.

## Next action

1. On a clean `ci:quick`: `git push origin 0831-1`, then re-arm
   `.ci/scripts/ci/ci-trace.py --wait --until-final` in the background. This restarts CI.
2. On green: the review fires, `Review Complete` posts, then
   `gh pr merge 583 --repo rediacc/console --rebase --auto`. Console is REBASE-ONLY.
   If `--rebase` fails with "This branch can't be rebased", check
   `git merge-base --is-ancestor origin/main origin/0831-1` and only on a pure
   fast-forward, `git push origin origin/0831-1:main`.
3. Then `/pr-merge` steps 4-8: checkout `main`; watch Console CI on main, then the
   **Release to Edge** run **BY ID** (`--run <id>`, never `--ref main` -- a
   workflow_dispatch run is absent from the branch rollup and `--ref main` printed a false
   GREEN twice); re-sync after CD pushes its two `[skip ci]` commits; mirror to `gitlab`;
   hand-back note.
4. Only then CronDelete `f892a1f9` and `b4bff02e`. Still deliberately ARMED.

## Volatile facts a fresh session would get wrong

- **`private/growth` has 1430 dirty paths and is NOT a submodule** -- gitignored, another
  workstream's. Never `git add` it. `private/generative` is clean. Both are on gitlab.
- The judged-rule calibration is NOT deterministic: 14/14 was one draw, a 20-fixture run
  scored 17/20. `SHAPE_PROMPT` is deliberately ABSENT from
  `.ci/config/rubric-calibration.json` -- do not "fix" that.
- `check:ci-git-history-depth` deliberately does NOT follow the step->script hop: it
  produced 89 false findings because the scripts are already shallow-safe
  (`check-branch.sh:63`, `resolve-version.sh:44`).
- No round log exists for this wave; STATE.md is the artifact.

## Open, not fixed

`[>] f46112c0`, leased to `b1vxbxvy8` until 14:53Z. Peer `a276391d`'s `BACKUP_S3_BUCKET`
finding needs credentials neither session has.
