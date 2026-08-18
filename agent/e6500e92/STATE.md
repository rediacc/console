## SESSION e6500e92 2026-08-18T23:16:18Z

# pr-babysit 0818-1 LIVE, round 8 fixes UNCOMMITTED and about to be pushed.

Round log outranks this file:
`/home/muhammed/.claude/projects/-home-muhammed-monorepo-console/reports/pr-babysit-0818-1.md`
(wave header + STATUS block first). `.claude/agents/pr-babysitter.md` is the mechanics. I am
the babysitter, the operator is the principal, so tier-3 items are DECIDED and logged.

## PRs and heads

- **console rediacc/console#569**, DRAFT, branch `0818-1`, pushed head **`603abd7f`**.
- **account rediacc/account#80**, head `d4094cc7`, review answered, its gate verified by
  running `check-review-report-replies.sh` against the live PR, exit 0.
- 8 commits so far, from `97d7c55c` (snapshot, 1,168 files, net -19,790) to `603abd7f`.

## UNCOMMITTED right now: round 8's fixes, 26 files

Fixing run 32193329425's two reds (`Quality / i18n`, `Quality / Code`). All verified locally:
`check:format`, `em-dash-surfaces`, `dead-css`, `css-dom-refs`, `layout-overflow`,
`search-index`, `docs-structure-parity`, `hydration-clean`, `tsc` (www AND cli) all exit 0.
**`check:lint` is still running** (an ~8 minute eslint pass); it went 17 problems to 3 to an
expected 0. Do not commit until it confirms.

The 26 files are: regenerated `public/search-index*.json` (14), two drained
`docs-structure-parity` BASELINE entries, `eslint.config.js` (node globals for
`packages/www/src/plugins/*.mjs`), and the lint fixes in `card-fonts.ts`,
`check-tutorial-card-fonts.ts`, `check-docker-image-freshness.ts`, `check-layout-overflow.ts`,
`Overlay.tsx`, plus `react-lint`'s four React files.

## The four lint findings each had a DIFFERENT right answer

Worth knowing before touching them again: delete an unused parameter (config policy is
delete, not underscore); correct a lying type (`Record<string, string>` hid that indexing
yields undefined at runtime); restructure to a length test when the checker will not accept a
nullish guard; and DECLINE the rule where its own suggestion changes behaviour
(`Overlay.tsx`: `||` treats an empty title as absent, `??` would render an empty header).
None of them was a suppression.

## Next action

1. Read `/tmp/claude-1000/lint5.out` for `LINT-EXIT`. If 0, stage SURGICALLY (`git add -A` is
   banned post-snapshot), commit, refresh the PR body so it GENUINELY changes (the gate reads
   `lastEditedAt`, not `updatedAt`), push once, then arm a terminal-state watch with the
   `until [ status = completed ]` poll in a background task. Never `gh run watch`.
2. Per red: read the COMPLETE failed-step log via
   `gh api repos/rediacc/console/actions/jobs/<id>/logs`. Count CANCELLED separately; a
   cancelled job did not pass, it did not run.
3. At green: `gh pr ready 569`, then the Claude review, then reply substantively to every
   thread and resolve them. **Never merge, never push `main`.** Tear down cron `76e2b5f2`
   and say so in the final report.

Still open after that: `#2e0695cf`, steps 6-8 of `agent/PLAN-cli-em-dash-lint-gate.md`
(add `packages/cli/{src/i18n/locales,scripts}` to the em-dash gate at ZERO, baseline the
`packages/cli/src` JSDoc residue), deliberately sequenced after green.
