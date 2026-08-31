## SESSION f88f9be7 2026-08-31T20:40Z

Running `/pr-babysit` INLINE on branch `0831-1`. I am the babysitter; principal is the
operator. Loop and mechanics: `.claude/agents/pr-babysitter.md`. Round log (the deep
state, read it before touching anything):
`~/.claude/projects/-home-developer-console/reports/pr-babysit-0831-1.md`.

## Next action

W4's second half. Two READ-ONLY sonnet agents are returning the nine
`techDiff.description` values per locale with the btrfs explainer clause removed
(`a1eb57074f0095fe7` = de/es/fr/it/pt/tr, `adc82fbd732af86d5` = ru/ja/ko/zh/ar/et).
When they land: splice them myself (single owner), rebuild www, verify the popover at
390/768/1024/1440, `npm run i18n:generate-hashes`, `npm run ci:quick`, push, re-arm the
CI watch.

## PRs

- console **#583** DRAFT https://github.com/rediacc/console/pull/583 @ `bb50d5fe9`
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

## Uncommitted right now (W4 part 2, in flight)

`en.json` + 12 locales carry the new `solutions.mechanism.cow`; the nine English
`techDiff.description` values are collapsed; `SPTechDiff.astro` renders the shared
explainer beside `mechanism-cow.svg` inside the popover; `SolutionPage`/`PersonaPage`
pass `mechanismNote`; `solution-pages.css` has `.sp-mechanism*`. The twelve locales'
nine descriptions still hold the OLD English's clause -- that is what the two agents
are producing.

## Open worklist

- `#d84b5b51` W4 (in progress, above)
- `#7ecac9ea` SWEEP: 113 bounded `printf|echo | grep -q` sites under pipefail

## Live machinery (session-only, dies with this session)

- CI watch `b0ty48qxb` on `bb50d5fe9` -- IN FLIGHT
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
