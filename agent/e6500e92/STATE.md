## SESSION e6500e92 2026-08-20T04:12:04Z

## What is true right now

Branch `0818-1`, PR **#569 OPEN/READY**. Plan `~/.claude/plans/memoized-gliding-kay.md`.
Local HEAD `15a60a652`, ONE COMMIT AHEAD of the last CI run (`bddc5fcd4`, run
`32303077889`, terminal + red). **Push HELD until the chain below completes.**

## OPERATOR DECISIONS (2026-08-20)

- **L4** 7-baseline cluster RIDES THIS PR. **L5** DRAIN `en.json`'s 65 em dashes ON THIS PR
  (overrides the follow-up default). **L6** run AUTONOMOUSLY to CI green + review + threads
  + `CronDelete 7cb9b31f`.

## THE ORDERED CHAIN -- order is TECHNICAL, not preference

`locale_adapter.py:126` REFUSES to apply when `en.json` changes under a running sweep.
Nothing below may start until bg pid `3182407` exits (now on `ru`; `tr`, `zh` remain).

1. sweep exits -> `npm run i18n:naturalize-status` for the true count
2. `red-gates` drains the 65 em dashes from `en.json` (English conventions; supply the word
   the dash stood in for)
3. `npm run i18n:generate-hashes`
4. **I** run the re-naturalization of the newly-stale delta (`--regressed-only --reprocess`),
   NOT the agent
5. `red-gates` locale em-dash pass + ONE baseline drain, on a FRESH scan taken after step 4
6. `node scripts/generate-search-index.js` **LAST** (any docs edit reddens it)
7. `npm run i18n:generate-client -w @rediacc/www`, layout-overflow x13
8. ONE push, arm a terminal-state watch

## DONE + INDEPENDENTLY VERIFIED BY ME

- **`no-media-quality` label** wired and LIVE. Non-vacuity PROVEN with my own transitive
  resolver: `check:i18n` walks 15 scripts, hits ZERO tutorial validators; controls hit 3+1.
- **Shrink-only composition class CLOSED at 11/11.** `scripts/lib/shrink-only-baseline.ts`
  is the shared guard; `packages/www/scripts/lib/p7-backlog.js::writeBacklog` is the choke
  point covering the last 3 validators. My spot-check: **8 GUARDED, battery=0**, and the
  battery has a control proving a comment mentioning the guard does NOT count as consuming
  it. All 6 live baseline md5s byte-identical. `check:ci-parity` 262 gates / 95 battery.
  It caught 2 REAL violations within an hour of being written.
- **`check:ci-search-index`** green (must be re-run at step 6).

## STILL RUNNING

- **Naturalization sweep**, bg pid `3182407`, `scratchpad/wave-c-reprocess.log`.
- **`red-gates`**: optional `--selftest` for `check-tutorial-parity.ts` only (I WITHDREW the
  `check-cli-docs` half -- it now routes through p7-backlog, whose growth path is already
  proven). Then it HOLDS. Its watcher `brbp1wqf1` is READ-ONLY (runs 2 gates, logs exit
  codes, no edit, no reseed) and will PING rather than act.

## Next action

1. `ps -o etime= -p 3182407`. On `===ALL DONE REPROCESS===` start the chain at step 1 and
   tell `red-gates` English is clear for step 2.
2. `check:ci-em-dash-surfaces` is RED by design right now (the sweep keeps adding dashes);
   that is step 5's job, not a regression.
3. Never merge, never push `main`. `3fe0b2ed` owns all tutorial/cast files; D5 stays OUT.
   Owed once `3fe0b2ed` publishes: remove the label from #569 AND
   `gh label delete no-media-quality`.
