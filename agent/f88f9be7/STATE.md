## SESSION f88f9be7 2026-09-01T19:13:58Z

`/pr-merge` is RUNNING on `0831-1`, PR #583. The operator invoked it. Resume below; do NOT
restart the flow.

## Already landed (do NOT redo)

1. **`rediacc/account#84` MERGED** -> `account/main` = `3d8dc142d`; branch deleted.
2. **`private/account` pointer bumped**; the tree check
   `git -C private/account diff --stat dfe648e4c 3d8dc142d` was EMPTY.
3. PR body refreshed via `gh api repos/<o>/<r>/pulls/<n> -X PATCH -F body=@<file>`.

## Right now

- Head `605969882` is **RED**: `Quality / Packages` -> Tutorial player release gate,
  **the 5th occurrence**. Job `99986123077`. **NO WATCH ARMED** (`b1veabonq` exited 1).
- Tree clean; `6775f2381` is the last commit. A `ci:quick` + `check:lint` +
  `check:ci-shape-duplication` run was in flight when compaction neared -- **re-run it**,
  do not assume it passed.

## The 5th red is almost certainly the known flake -- CHECK, do not assume

Two distinct failure modes have hit this gate; do not conflate them:
- an ~8% flake at the FIRST navigation, 28.4/29.0/29.0s against agent-browser's 25s
  default (a fixed CEILING);
- a regression I introduced in `c6a7c36c8` and fixed in `aa6542874` (readiness matcher
  tested each CHUNK; now tests the accumulated buffer).

**FIRST ACTION on this red: `gh run download <run-id> -n tutorial-player-release-gate-1`.**
`summary.json` names which mode it was -- a first-navigation timeout, or
"Timed out waiting for astro dev server to start" (the matcher). That artifact caught my
own regression once already. Do NOT re-diagnose from code.

Also: **read the STEP conclusion, never the run's.** A cancelled job with a passing step
is a PASS; misreading that produced a wrong diagnosis today.

## Next action

1. Download the artifact above and classify the red from `summary.json`.
2. `rm -f .ci/cache/gate-durations.json && GITHUB_TOKEN="$(gh auth token)" npm run ci:quick`,
   AND separately `npm run check:lint` and `npm run check:ci-shape-duplication` --
   ci:quick defers the first and omits the second; that gap cost two CI rounds today.
3. `git push origin 0831-1` if anything is held.
4. **Poll `gh api repos/rediacc/console/pulls/583 --jq .head.sha` until it shows the new
   head BEFORE arming a watch**, then arm `.ci/scripts/ci/ci-trace.py --wait --until-final`
   in the background.
5. On green: the review fires on `Console CI` completion, `Review Complete` posts, then
   `gh pr merge 583 --repo rediacc/console --rebase --auto`. Console is REBASE-ONLY. If
   `--rebase` errors "can't be rebased", check
   `git merge-base --is-ancestor origin/main origin/0831-1`; only on a pure fast-forward,
   `git push origin origin/0831-1:main`.
6. Then steps 4-8: checkout `main`; Console CI on main; **Release to Edge BY ID**
   (`--run <id>`, never `--ref main`); re-sync after CD's two `[skip ci]` commits; mirror
   to `gitlab`; hand-back note.
7. Only then CronDelete `f892a1f9` and `b4bff02e`.

## Shipped this session, do not re-do

`wl_histfirst` (`def1c34e2`): on a red the block now PRINTS the commits between the last
green head and the red, and which touch files named like the failing job. Mechanical, not
judged -- `wl_core.emit` exits before `wl_judge.run_judge`. Demands nothing.
NOT done: history prose in `.claude/skills/ci-watch/SKILL.md` and
`docs/agent-reference/TRAPS.md`, both verified to contain none.

## Volatile facts a fresh session would get wrong

- **Do NOT run `npm run ci` locally beside a live CI watch.** 4 of 343 red, ALL FALSE.
- **`private/growth` has ~1430 dirty paths and is NOT a submodule** -- never `git add` it.
- `check:ci-fetch-retry` is scoped to image builds ON PURPOSE: unrestricted, 119 findings.
- `wl_wait.py` must launch as a harness background task, never with a shell ampersand.

## Open, not fixed

`[>] f46112c0`. Peer `a276391d`'s `BACKUP_S3_BUCKET` needs credentials neither has.
