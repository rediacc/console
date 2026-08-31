## SESSION f88f9be7 2026-08-31T20:40Z

Running `/pr-babysit` INLINE on branch `0831-1`. I am the babysitter; principal is the
operator. Loop and mechanics: `.claude/agents/pr-babysitter.md`. Round log (the deep
state, read it before touching anything):
`~/.claude/projects/-home-developer-console/reports/pr-babysit-0831-1.md`.

## Next action

Wait on CI watch `bolahleo6` (head `5d1213f5c`). Everything the operator's plan asked for
has landed; the only open item is the `[?]` below. On green: refresh the round log, flip
#583 out of draft, request Claude review, tear down the two crons.

## PRs

- console **#583** DRAFT https://github.com/rediacc/console/pull/583 @ `5d1213f5c`
- account **#84** https://github.com/rediacc/account/pull/84 (consumed by #583's pointer)

## Operator rulings (authoritative, do not re-litigate)

- **R1. ALL remaining plan work rides #583.** Do not open a second PR.
- **R2. Overlays centre on the VIEWPORT** site-wide. DONE in f73d9c328.
- **R3. Fix the vitest flake properly in the submodule.** DONE, account#84.
- Operator correction 2026-08-31T19:0xZ: CLAUDE.md already mandates fix-on-sight and
  big-bang, so STOP ASKING permission for either. Settle it and execute.

## Landed this stretch

- `1abdaf621` W2: SPProblem timeline behind a native popover (worklist #167dbe32 ticked)
- `d2dd21be2` W5: 5 hand-authored textless SVGs in a new `src/assets/images/disclosure/`
  + resolver, on all four disclosure triggers; 3 derived stat-callout glyphs in
  `icons.ts`; fixed a 227px horizontal overflow from `.sp-callout-pop` at 1024 and a
  trigger stretching to 576px in the SPProblem grid (worklist #9dff7331 ticked)
- `a8a872b29` the tutorial-player gate no longer trusts agent-browser's exit status, and
  `check-agent-browser-exit.sh` now scans JS/TS too; knip unused export dropped
- `4ca07f0cb` `test-run-sh.sh` SIGPIPE race under pipefail (the CI red)
- `4298b44e3` + `bb50d5fe9` W4 part 1: one spelling for the IBM citation across 13 sites,
  4 translated report titles restored, 16 stray `[n]` markers removed, and
  `check-locale-only-edits.ts` gained a narrow marker-repair exemption with 5 controls
- `03b6259b6` W4 part 2: nine btrfs re-explanations collapsed into one
  `solutions.mechanism.cow`, rendered once beside the CoW diagram in the mechanism popover
- `f24b3a8a4` TRAP_FLOOR ratcheted to 50 (the CI red), plus a fast-lane advisory so an
  unratcheted floor is named where the mistake is made
- `c7970a9e8` + `5d1213f5c` 60 pipefail/grep -q races drained across 27 files
- `9b1f68a28` setup-idempotency no longer reads a neighbour gate's fixture as a mutation

## Uncommitted right now

Nothing. Tree clean.

## Open worklist

- `#d84b5b51` is a `[?]`: re-syncing the 12 locales' nine `techDiff.description` values,
  which translate the pre-round-6 English. DEFAULT is a dedicated pass after #583 merges.
  All numbers are in the deferral text.

## Live machinery (session-only, dies with this session)

- CI watch `bolahleo6` on `5d1213f5c` -- IN FLIGHT
- heartbeat cron `f892a1f9` (:23), mail poll cron `b4bff02e` (:47)
- Tear the two crons down at the finish line and say so in the final report.

## Traps this session paid for

- **`--mark-done --all-stale` is a BULK verb.** Run to close the one key the gate named,
  it stamped 1,965 per locale (23,561 total). The pipeline's "stale" is "CRC not in the
  ledger"; the gate's is "was naturalized, English changed". Repaired forward from
  `git show HEAD:` + a 12-CRC splice. Written up in TRAPS.md and in memory.
- **agent-browser prints its diagnosis on STDOUT and still exits 1**, so `String(error)`
  on an execFileSync throw drops the only copy of the reason.
- **`printf | grep -q` under pipefail is a race** even for a 1 KB producer.
- **Never read a CI verdict through a pipe.** `npm run ci | tail` returns tail's status.
- `git commit --amend` is hook-blocked during babysitting; make each fix a NEW commit.
- The round log lives at the projects path, NOT repo `reports/` (gitignored).
- A www build needs `GITHUB_TOKEN` or `downloads.astro` fails on the GitHub rate limit.
- The pre-push hook hashes the WHOLE tree: do not touch a file (even
  `.ci/cache/gate-durations.json`) between `ci:quick` and `git push`.
- Peer session owns SPHero/PersonaPage/SPHomePage/SPHomeVideo/persona-pages.ts. My edits
  there are additive; their video wiring must stay.
