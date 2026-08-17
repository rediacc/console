## SESSION 97604f47 2026-08-17T05:32:03Z

Branch `0815-1`, inline /pr-babysit of the backup-storage wave (console#568 + renet#103 + account#79 + elite#15). Directive: drive green, NEVER merge, NEVER push main.

## What is true right now

The agent-folder migration is COMPLETE but UNCOMMITTED. Shape: gitignored `.agent/` is gone; tracked `agent/<branch>/<session-prefix>/` holds STATE/RULES/reports; `agent/<branch>/PLAN-*.md` holds plans; standing lookup docs moved to `docs/agent-reference/` (TRAPS.md, ci-gates.md, suppressions.md, loop-prompt.md, worklist-v10-brief.md, deleted-branches). `.gitignore` no longer hides agent notes and carries a comment saying the absence is deliberate. CI cost is paid by a ZERO-JOB `agent` module (scope-map.cjs:60, rule at :193), not by hiding from git.

Tree: 40 staged (all pure renames, verified mine -- no agent WIP in the index), 50 unstaged tracked, 42 untracked under `agent/`. `.claude/settings.local.json` untouched.

Hook suites GREEN on a stable tree: test-worklist-v5.sh 741/0, test-hooks.sh 884/0 exit 0.

Full battery `npm run ci` is RUNNING as background task bctc0pmug; wave item #1610e234 is leased to it until 06:30Z. Its output file stays EMPTY until it exits (the command pipes through `tail`), so emptiness is not a stall.

## Hazards paid for already

- A background suite output read `713/28`: that run STARTED BEFORE the fixes landed. Stale, not current. Check when a run began before believing its verdict.
- ONE unexplained `876/8` test-hooks run sits between two clean `884/0` runs. Not yet explained. Do NOT run a hook suite concurrently with the battery -- the battery runs all three suites and overlapping runs report garbage.
- `.ci/scripts/test/gates/test-scope-engine.sh:674` names `docs/agent/main/REPORT-...`, a path the migration moved. This is CORRECT and must not be "fixed": it reproduces real incident run 30983418337 and the engine classifies by path pattern, not file existence (`docs/` still matches by prefix).
- worklist.py prints WARNINGS FIRST; piping it through `tail` eats them.
- `git commit` takes the whole INDEX, not the paths named. Verify `git diff --cached` immediately before committing; an agent staged into this index earlier in the wave and a broken tree got pushed once.

## Next action

Wait for bctc0pmug. If green: re-verify `git diff --cached`, then commit the whole migration as ONE coherent change (no attribution trailers) and push to `0815-1`. A fresh review after that push clears `Review Complete` (its marker names an older SHA because the push followed the review -- ordering, not a defect). If the battery is red, fix forward; never checkout/restore/stash a tracked path.

Then operator-only, post-merge: seven R2 buckets (the EU pair needs `--jurisdiction eu`), four `BACKUP_S3_*` secrets all-or-none per worker, bucket-scoped `cf-r2-backup` rotation slug. Only ever touch bucket `rediacc-backups-probe`, never `rediacc-backups`.
