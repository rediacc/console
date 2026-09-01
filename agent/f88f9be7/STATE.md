## SESSION f88f9be7 2026-09-01T20:25Z

`/pr-merge` is RUNNING on `0831-1`, PR #583. The operator invoked it. Resume below; do NOT
restart the flow. **#583 merges with NO automated review -- SETTLED, never re-ask.**

## Already landed (do NOT redo)

1. **`rediacc/account#84` MERGED** -> `account/main` = `3d8dc142d`; branch deleted.
2. **`private/account` pointer bumped**; the tree diff was EMPTY.
3. **The 5-run tutorial-player red is FIXED** (`16fc6d946`, `e4ba1e65f`). See below.

## Right now

- Head `e4ba1e65f`, pushed. `ci-trace --wait --until-final` armed as bg `b1mqquvtc`.
- Gates before that push: `ci:quick` 277/277, `check:lint` 0, `check:ci-shape-duplication` 0.
- Tree clean.

## The 5 reds were ONE real bug, not a flake. Do not re-litigate.

**GitHub Actions always sets `CI=true`; astro's colour library then colours its banner with
no TTY, and the escape lands exactly between `in` and the space:**
`\x1b[2mready in\x1b[22m 4739`. The matcher tested RAW bytes, so it returned TRUE on a
plain capture and FALSE on the CI capture -- measured both ways by running the real
command. A gate that could never pass in CI and always passed locally, which is exactly
what a flaky runner looks like. The old `includes('ready')` survived colour by accident.

Fixed by stripping ANSI **on ingest**: new `packages/www/scripts/lib/dev-server-ready.js`,
7 vitest controls carrying the REAL captured bytes plus a vacuity control asserting the CI
bytes do NOT match unstripped. vitest now includes `scripts/**/__tests__`.

**Two instruments that prolonged the misreading, both fixed:**
- `pressureDetected` was `slowBoot || highLoad`, and slowBoot is the timeout restated -- so
  every timeout printed "SYSTEM UNDER LOAD" at `load/core=0.06`. It told the reader to
  dismiss the failure it had just detected. Now load-only; a slow boot on an idle machine
  prints the OPPOSITE reading.
- `serverLog` was omitted from the crash summary -- the one path that needed it.

Swept the class: `lib/scenes/browser.ts` parsed spawned stdout the same raw way.
Verified by running the real gate under `CI=true` (exit 0, 5/5) and forcing the crash path.

## Next action

1. Read `b1mqquvtc`. **Read the STEP conclusion, never the run's** -- a cancelled job with
   a passing step is a PASS.
2. On green: `gh pr merge 583 --repo rediacc/console --rebase --auto`. Console is
   REBASE-ONLY. If `--rebase` errors "can't be rebased", check
   `git merge-base --is-ancestor origin/main origin/0831-1`; only on a pure fast-forward,
   `git push origin origin/0831-1:main`.
3. Then steps 4-8: checkout `main`; Console CI on main; **Release to Edge BY ID**
   (`--run <id>`, never `--ref main`); re-sync after CD's two `[skip ci]` commits; mirror
   to `gitlab`; hand-back note.
4. Then CronDelete `f892a1f9`, `b4bff02e` AND `467ccd9f`, and say so in the final report.
5. On a NEW red: poll `gh api .../pulls/583 --jq .head.sha` until it shows the pushed head
   BEFORE arming a watch, else the watch traces the stale head and exits 1.

## Shipped this session, do not re-do

`wl_histfirst` (`def1c34e2`): on a red, prints the commits between last-green and the red
and which touch files named like the failing job. Mechanical, not judged.
NOT done: history prose in `.claude/skills/ci-watch/SKILL.md` and
`docs/agent-reference/TRAPS.md`, both verified to contain none.

## Volatile facts a fresh session would get wrong

- **Do NOT run `npm run ci` locally beside a live CI watch.** 4 of 343 red, ALL FALSE.
- **`private/growth` has ~1430 dirty paths and is NOT a submodule** -- never `git add` it.
- Commits need `PR-TASK: 23ac415a`; `Co-Authored-By` is hook-BLOCKED here.
- `wl_wait.py` must launch as a harness background task, never with a shell ampersand.

## Open, not fixed

`[>] f46112c0`. Peer `a276391d`'s `BACKUP_S3_BUCKET` needs credentials neither has.
