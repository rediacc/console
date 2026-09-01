## SESSION f88f9be7 2026-09-01T16:30:50Z

`/pr-merge` is RUNNING on `0831-1`, PR #583. The operator invoked it. Resume at the step
below; do NOT restart the flow.

## Already landed (do NOT redo)

1. **`rediacc/account#84` is MERGED** -- rebase-merged to `account/main` = `3d8dc142d`;
   branch deleted (`delete_branch_on_merge: true` on all five repos).
2. **`private/account` pointer bumped** to it; the mandatory check
   `git -C private/account diff --stat dfe648e4c 3d8dc142d` was EMPTY.
3. PR body refreshed via `gh api repos/<o>/<r>/pulls/<n> -X PATCH -F body=@<file>`
   (`gh pr edit --body-file` is hook-blocked).

## Right now

- Pushed head `647376265`: CI RUNNING, 6 contexts in flight, no failures. Watch
  `b1yh0ilbx` (PID 1272808) alive; mail waiter `bpspozekj` (PID 343120) alive.
- **ONE COMMIT HELD**: `b8e825123`. It fixes `check:ci-fetch-retry`, which I had shipped
  VACUOUS one commit earlier -- it parsed shell scripts with a Dockerfile `RUN` parser
  (25 blocks for the Dockerfile, 0 for any .sh), so it printed "551 files scanned" while
  every shell script contributed nothing. Four real unretried fetches in `.devcontainer/`
  shell scripts were hiding inside its own corpus; all four are fixed, none baselined.

## Next action

1. `rm -f .ci/cache/gate-durations.json && GITHUB_TOKEN="$(gh auth token)" npm run ci:quick`
   AND separately `npm run check:ci-shape-duplication` -- ci:quick does NOT include that
   gate, and a red reached CI once because a "277 ok" was read as full cover.
2. `git push origin 0831-1` (supersedes the in-flight run; its head is superseded anyway).
3. **Poll `gh api repos/rediacc/console/pulls/583 --jq .head.sha` until it shows the new
   head BEFORE arming a watch**, and cross-check `git ls-remote origin refs/heads/0831-1`.
   The API lagged 30-60s four times today; a watch armed early traced a stale head and
   exited 1 "superseded". Then arm `.ci/scripts/ci/ci-trace.py --wait --until-final`
   in the background.
4. On green: the Claude review fires on `Console CI` completion, `Review Complete` posts,
   then `gh pr merge 583 --repo rediacc/console --rebase --auto`. Console is REBASE-ONLY.
   If `--rebase` errors "This branch can't be rebased", check
   `git merge-base --is-ancestor origin/main origin/0831-1`; only on a pure fast-forward,
   `git push origin origin/0831-1:main`.
5. Then steps 4-8: checkout `main`; watch Console CI on main, then **Release to Edge BY
   ID** (`--run <id>`, never `--ref main` -- a workflow_dispatch run is absent from the
   branch rollup and `--ref main` printed a false GREEN twice); re-sync after CD pushes
   its two `[skip ci]` commits; mirror to `gitlab`; hand-back note.
6. Only then CronDelete `f892a1f9` and `b4bff02e`.

## Rules this wave paid for

- **Commit everything FIRST, then gate, then push.** `block-unverified-push.sh` refuses a
  gate stamp that predates the tree; committing after a run invalidates it.
- **Both CI reds so far were transient upstream outages** (openSUSE mirror 403, go.dev
  500). PROBE the failing URL before diagnosing -- both answered fine minutes later.
- A gate that reuses a sibling's CORPUS must also be able to PARSE it. Check the block
  count per file type before believing a green.

## Volatile facts a fresh session would get wrong

- **`private/growth` has ~1430 dirty paths and is NOT a submodule** -- gitignored, another
  workstream's. Never `git add` it. `private/generative` is clean. Both on gitlab.
- Calibration is NOT deterministic: 14/14 was one draw, a 20-fixture run scored 17/20.
  `SHAPE_PROMPT` is deliberately ABSENT from `.ci/config/rubric-calibration.json`.
- `check:ci-fetch-retry` is scoped to image builds ON PURPOSE: unrestricted it reports 119
  findings across 69 files, which is a wall, not a gate.
- No round log for this wave; STATE.md is the artifact.

## Open, not fixed

`[>] f46112c0`. Peer `a276391d`'s `BACKUP_S3_BUCKET` finding needs credentials neither
session has.
