## SESSION e6500e92 2026-08-18T23:56:25Z

# pr-babysit 0818-1 LIVE, round 10 pending. Two PRs open. Working tree CLEAN.

Round log outranks this file:
`/home/muhammed/.claude/projects/-home-muhammed-monorepo-console/reports/pr-babysit-0818-1.md`
(read its wave header + STATUS block first). `.claude/agents/pr-babysitter.md` is the
mechanics. I am the babysitter, the operator is the principal, so tier-3 items are DECIDED
and logged under DECISIONS, never asked.

## PRs and head

- **console rediacc/console#569**, DRAFT, branch `0818-1`, head **`58f3f0ba`**, pushed.
  Body refreshed, `lastEditedAt` 23:55:11Z. The PR-Description gate reads `lastEditedAt`,
  NOT `updatedAt`, and a push bumps only the latter, so verify with the GraphQL query.
- **account rediacc/account#80**, head `d4094cc7`, review answered; its gate verified by
  running `check-review-report-replies.sh` against the live PR, exit 0.
- 11 commits, `97d7c55c` (snapshot, 1,168 files, net -19,790) through `58f3f0ba`.

## CI

Run **32199152941** on `58f3f0ba` IN FLIGHT. Watch armed as background task `b1cb1x0h3`;
heartbeat cron `76e2b5f2` at :23. Reds per round so far: 2, 3, 1, 1, 1, 1, 2, 1. **Every
round's fix has held in the following run**, confirmed in that run's log.

**Count CANCELLED separately every time.** A watchdog-cancelled job did not pass, it did not
run, and it is invisible to a `conclusion=="failure"` filter. Runs have been ending
`cancelled` with one real red plus several cancelled siblings.

## Everything was green LOCALLY before this push

typecheck, check:lint, lint:unused, check:ci-dead-bash, check:format, em-dash-surfaces,
tsc (www and cli), knip, hydration-clean, dead-css, css-dom-refs, layout-overflow,
search-index, docs-structure-parity, cli-contract, translation-hashes, deps.

## Two traps this wave paid for, both still live risks

1. **`Quality / Code` runs FOUR checks** (eslint, knip, dead-bash, typecheck). Clearing one
   promotes the next, so a green eslint does not mean that job passes. Run
   `npm run typecheck` too: per-package `tsc` is NOT the same gate and missing it cost a round.
2. **Changing `packages/cli/src/i18n/locales/**` invalidates THREE generated trees**, each
   gated in a different lane: `packages/shared/src/cli-contract/data/**`
   (`generate:cli-contract -w @rediacc/cli`), `.claude/skills/rdc/reference.md`
   (`generate-skill-reference.ts`, writes to STDOUT), and
   `packages/www/src/content/docs/<lang>/cli-application.md` (`generate:cli-docs -w @rediacc/www`).

## Next action

1. Re-check the run DIRECTLY (`gh api repos/rediacc/console/actions/runs/32199152941`)
   rather than trusting the watch, which can drop silently. Re-arm freely.
2. Per red: read the COMPLETE failed-step log via
   `gh api repos/rediacc/console/actions/jobs/<id>/logs` before diagnosing. Fix at root,
   plant a control, stage SURGICALLY (`git add -A` is banned post-snapshot), refresh the PR
   body so it GENUINELY changes, push once, re-arm.
3. At green: `gh pr ready 569`, then the Claude review, then reply substantively to every
   thread and resolve them. **Never merge, never push `main`.** Tear down cron `76e2b5f2`
   and say so in the final report.

Still open after green: `#2e0695cf`, steps 6-8 of `agent/PLAN-cli-em-dash-lint-gate.md` (add
`packages/cli/{src/i18n/locales,scripts}` to the em-dash gate at ZERO, baseline the
`packages/cli/src` JSDoc residue). Deliberately sequenced after green so a gate edit does not
muddy attribution of the next red.
