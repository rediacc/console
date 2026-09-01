## SESSION f88f9be7 2026-09-01T16:13:38Z

`/pr-merge` is RUNNING on `0831-1`, PR #583. The operator invoked it. Resume at the step
below; do NOT restart the flow.

## Already landed (do NOT redo)

1. **`rediacc/account#84` is MERGED** -- rebase-merged to `account/main` = `3d8dc142d`;
   branch deleted (`delete_branch_on_merge: true` on all five repos).
2. **`private/account` pointer bumped** to it; the mandatory check
   `git -C private/account diff --stat dfe648e4c 3d8dc142d` was EMPTY.
3. PR body refreshed via `gh api repos/<o>/<r>/pulls/<n> -X PATCH -F body=@<file>`
   (`gh pr edit --body-file` is hook-blocked).

## Right now: the pushed head is DOOMED, one commit is held

Pushed head `75d8274e0` is RED: `Build (Docker) / Devcontainer (amd64)` failed on
`curl: (22) ... error: 500` fetching the Go tarball. PROBED -- that URL answers 302 now,
so it was a transient go.dev outage, not our code.

The real defect was the class around it, and it is FIXED in the held commit `37a888adf`:
two apt steps had hand-rolled retry loops while EIGHT other fetches in
`.devcontainer/Dockerfile` had none. All nine now share `ARG CURL_RETRY`.

Watch `bar6jfjoa` (PID 1172509) is still alive but is watching that doomed run -- it waits
for a FINAL verdict and other contexts are still going. Do not trust it; re-read.

## Next action

1. `rm -f .ci/cache/gate-durations.json && GITHUB_TOKEN="$(gh auth token)" npm run ci:quick`
   AND, separately, `npm run check:ci-shape-duplication` -- ci:quick does NOT include that
   gate, and a red reached CI because a "275 ok" was read as full cover.
2. `git push origin 0831-1` (this supersedes the doomed run).
3. **Poll `gh api repos/rediacc/console/pulls/583 --jq .head.sha` until it shows the new
   head BEFORE arming a watch.** The API lagged 30-60s three times; a watch armed early
   traced a stale head and exited 1 "superseded". Then arm
   `.ci/scripts/ci/ci-trace.py --wait --until-final` in the background.
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

## Ordering rules this wave paid for

- **Commit everything FIRST, then gate, then push.** `block-unverified-push.sh` refuses a
  gate stamp that predates the tree, and committing after a run invalidates it.
- Two CI reds so far were BOTH transient upstream outages (openSUSE mirror 403, go.dev
  500). Probe the URL before diagnosing; both answered fine minutes later.

## Volatile facts a fresh session would get wrong

- **`private/growth` has ~1430 dirty paths and is NOT a submodule** -- gitignored, another
  workstream's. Never `git add` it. `private/generative` is clean. Both on gitlab.
- Calibration is NOT deterministic: 14/14 was one draw, a 20-fixture run scored 17/20.
  `SHAPE_PROMPT` is deliberately ABSENT from `.ci/config/rubric-calibration.json`.
- `check:ci-git-history-depth` deliberately does NOT follow the step->script hop: 89 false
  findings, because the scripts are already shallow-safe.
- No round log for this wave; STATE.md is the artifact.

## Open, not fixed

`[>] f46112c0`. Peer `a276391d`'s `BACKUP_S3_BUCKET` finding needs credentials neither
session has.
