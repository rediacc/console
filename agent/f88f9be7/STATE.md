## SESSION f88f9be7 2026-09-01T19:09:01Z

`/pr-merge` is RUNNING on `0831-1`, PR #583. The operator invoked it. Resume below; do NOT
restart the flow.

## Already landed (do NOT redo)

1. **`rediacc/account#84` MERGED** -> `account/main` = `3d8dc142d`; branch deleted.
2. **`private/account` pointer bumped**; the mandatory tree check
   `git -C private/account diff --stat dfe648e4c 3d8dc142d` was EMPTY.
3. PR body refreshed via `gh api repos/<o>/<r>/pulls/<n> -X PATCH -F body=@<file>`.

## Right now

- Head `605969882`: CI RUNNING, 4 contexts in flight, no failures. Watch `b1veabonq`
  (PID 2101888) alive; mail waiter relaunched as task `bjiicrimq`.
- **HELD: `def1c34e2` plus an uncommitted guard fix.**

## New this stretch

**`wl_histfirst`** -- the operator's idea. On a red, the block now PRINTS the commits
between the last green head and the red, and which touch files named like the failing job.
This session made ZERO `git log` calls naming the gate that failed four times, while eight
lines of `git log --oneline -- <file>` held both decisive facts. MECHANICAL, not judged,
and structurally so: `wl_core.emit` ends in `sys.exit(0)` and the red-CI block emits at
`wl_checks.py:4987`, UPSTREAM of `wl_judge.run_judge` at `:5326`. It DEMANDS nothing, so
it cannot become a wall.

**`block-shell-background-waiter.sh`** had reopened a false positive it once closed:
quote-stripping turns a QUOTED heredoc delimiter into a bare `<<`, so the heredoc stripper
found none and scanned the document as commands. Heredocs now come off the raw command
FIRST.

NOT done, recommended by the planning agent: history prose in
`.claude/skills/ci-watch/SKILL.md` and `docs/agent-reference/TRAPS.md`.

## Next action

1. `rm -f .ci/cache/gate-durations.json && GITHUB_TOKEN="$(gh auth token)" npm run ci:quick`,
   AND separately `npm run check:lint` and `npm run check:ci-shape-duplication` -- ci:quick
   defers the first and omits the second. That gap cost two CI rounds today.
2. `git push origin 0831-1`.
3. **Poll `gh api repos/rediacc/console/pulls/583 --jq .head.sha` until it shows the new
   head BEFORE arming a watch**, then arm `.ci/scripts/ci/ci-trace.py --wait --until-final`
   in the background.
4. On green: the review fires on `Console CI` completion, `Review Complete` posts, then
   `gh pr merge 583 --repo rediacc/console --rebase --auto`. Console is REBASE-ONLY. If
   `--rebase` errors "can't be rebased", check
   `git merge-base --is-ancestor origin/main origin/0831-1`; only on a pure fast-forward,
   `git push origin origin/0831-1:main`.
5. Then steps 4-8: checkout `main`; Console CI on main; **Release to Edge BY ID**
   (`--run <id>`, never `--ref main`); re-sync after CD's two `[skip ci]` commits; mirror
   to `gitlab`; hand-back note.
6. Only then CronDelete `f892a1f9` and `b4bff02e`.

## The tutorial-player gate: TWO failures, do not conflate

- An ~8% flake at the FIRST navigation, 28.4/29.0/29.0s against agent-browser's 25s
  default -- a fixed CEILING. A PASS sits BETWEEN failures I called consecutive (job
  `99944615218`, STEP = success; its JOB says `cancelled` only because my push superseded
  it). **Read the STEP, not the run.**
- A regression I introduced in `c6a7c36c8`, fixed in `aa6542874`: the readiness matcher
  tested each CHUNK, so boot hung to 180s. Now tests the accumulated buffer.

**If it reds again, download `tutorial-player-release-gate-<attempt>` FIRST.**

## Volatile facts a fresh session would get wrong

- **Do NOT run `npm run ci` locally beside a live CI watch.** 4 of 343 gates red, ALL
  FALSE -- two timeouts under contention, two starved; all pass standalone.
- **`private/growth` has ~1430 dirty paths and is NOT a submodule** -- gitignored, another
  workstream's. Never `git add` it.
- `check:ci-fetch-retry` is scoped to image builds ON PURPOSE: unrestricted, 119 findings.

## Open, not fixed

`[>] f46112c0`. Peer `a276391d`'s `BACKUP_S3_BUCKET` needs credentials neither has.
