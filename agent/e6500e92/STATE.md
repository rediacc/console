## SESSION e6500e92 2026-08-19T23:58:53Z

## What is true right now

**Operator away, loop autonomous.** Branch `0818-1`, PR **#569 OPEN/READY**. Run
`32303077889` (push 4, `bddc5fcd4`) TERMINAL and UNCHANGED for hours -- confirmed via
direct API repeatedly, no newer push exists. Two real failures on it, both being worked:
`check:ci-browser-smoke` (judged transient, reproduced clean locally, no fix needed, next
push gets a fresh attempt) and `Quality/i18n` (the ONE thing actually blocking progress).

## THE i18n STORY, condensed for a cold reader

1,046 stale translations were blocking `check-i18n-naturalization.ts`. TWO blind retry
sweeps (2h+ each) on homepage/marketing/persona only shaved this from 2028->1079->1046 --
diminishing returns. **Root-caused the real shape of the problem** with a small diagnostic
script (now deleted) comparing en.json hashes against `.naturalized-hashes.json` exactly
as the CI gate does: `personaPages 400, pricing 350, solutionPages 132, disasterRecovery
104, resourcesBrief 60`.

**The `solutionPages` 132 was a surprise**: I'd deliberately never swept that surface
tonight (its FULL delta is ~2213 keys/language of untracked backlog, a separate deferred
wave). But the CI GATE doesn't care about my python pipeline's surface scoping at all --
it just diffs en.json against the ledger directly, so ANY previously-tracked key going
stale blocks CI regardless. Verified the 132 is small and separate from the deferred
backlog: exactly 11 keys x 12 languages, in only 2 of 25 pages
(kubernetesClusterMobility, migrationSafety).

**EXTENDED THE PIPELINE** (small, mechanical, in `private/growth`, NOT console):
`ledger.was_tracked()` + a `regressed_only` filter on `delta.stale_groups()`, wired to a
new `--regressed-only` CLI flag in `main.py`. This isolates EXACTLY the CI-gate-blocking
subset of a surface (previously naturalized, now stale) without touching its untracked
majority. Verified: reports 132 exactly, matching my independent count. ALSO found
`--regressed-only` is a strict subset for `marketing` too (tr 62->42, ru 124->104) but
IDENTICAL for `persona` (54=54, no untracked component there) -- so it is safe and
sometimes cheaper to use everywhere, no downside.

## RUNNING NOW: solution-surface regressed-only sweep, bg pid `2147647`

Log `scratchpad/wave-c-solution.log`. 2/12 languages (`ar` done clean 2/2 applied; `de` in
progress at 7+ min, slower than ar's ~2min but not yet worth intervening). Only 132 total
keys across all 12 languages, so this should finish soon even if de is a slow outlier.

## NEXT (after solution sweep): retry homepage+marketing+persona with --regressed-only

Cheaper and safer than the blind full retry already done twice. Then
`npm run i18n:naturalize-status` for the TRUE remaining count (expect near 0, since
persona's stale is already fully accounted for and marketing's untracked slice is small).

## Next action

1. Check `ps -o etime= -p 2147647` + `tail scratchpad/wave-c-solution.log`. If DONE
   (`===ALL DONE SOLUTION===`): relaunch homepage+marketing+persona with `--regressed-only`
   (same 12-language loop shape as prior sweeps, just add the flag).
2. Once ALL sweeps are done: `npm run i18n:naturalize-status`. If 0: stage
   `packages/www/src/i18n/translations/*.json` (verify every borderline file via
   `git diff HEAD` first, same discipline as every commit this wave), commit, push, arm a
   NEW terminal-state watch.
3. Then C2e `i18n:generate-client -w @rediacc/www`, C-V verify incl. layout-overflow x13.
4. Never merge, never push `main`. Session `3fe0b2ed` still owns tutorial/cast work --
   confirmed multiple times this wave, do not touch.
