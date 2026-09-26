# PLAN: Wire the unrun vitest suites into CI (the account gap is elsewhere)
Status: compacted
First-Seen: 2026-09-17
Owner: 97604f47
Full-Text: f7a5351a9 agent/PLAN-wire-account-vitest-ci.md
Full-Text-Blob: 5b450ce4f57e84c5814a44de44b81dc8d1d4c2a1
Record-Sig: 19f0f451

## Why
The brief said private/account's vitest integration suite was never run by CI. It was, and had been on every non-bot run: the invocation is three hops deep and never spells the word `vitest` in a workflow or a `.ci` script, so a literal grep missed it. The plan is mostly that correction, plus the gaps that turned out to be real once the false one was cleared.

## Outcome
SHIPPED, AND THE HEADER IS WRONG: `Status: draft` is stale by a day. Measured 2026-09-06: `check:ci-test-account-web` exists verbatim as designed, with a manifest entry carrying its mutex, weight and heavy flags plus a measured `slow` marker the plan did not specify, locked into the generated runner lockfile, and a workflow step in the quality-packages job. The old console-coverage
key is gone. Gap B landed too: `check:test-www` with its own workflow step and manifest entry, and the asymmetry fix `check:test-shared`, which closed a manifest hole for a step that had run in CI for a long time with no manifest entry at all. The hard-fail-under-CI contract for a missing submodule is committed in `.ci/scripts/private/run-account.sh`. All of it landed in 120cd9e73,
the same commit that added this plan file to the repository.

## Lessons
- A grep for a tool's name cannot find a chain that never spells it. The plan's
first act was to disprove its own brief, and that correction is worth more than the wiring it went on to do.
- A plan committed in the SAME commit as its implementation carries `Status:
draft` forever unless someone edits it afterwards. Nobody did, and a later reader would have concluded the work was never done.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: draft
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:08:55Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: .github/workflows/ci-quality.yml, .ci/scripts/private/run-account.sh, private/account/package.json, scripts/ci-runner/manifest.ts, .ci/scripts/ci/scope-map.cjs, .ci/scripts/test/run-unit.sh, package.json, packages/www/package.json, packages/json/package.json, private/account/src/services/backup-chunk-store.ts
Gates: check:ci-account-scope-audit, check:ci-account-server, check:ci-gate-id-convention, check:ci-parity, check:ci-quality-gates, check:ci-runner-advice, check:ci-scope-completeness, check:ci-secret-reachability, check:ci-shell-lint, check:ci-test-account-web, check:ci-timeout-headroom, check:test-cli, check:test-shared, check:test-workers, check:test-www
Why-Source: author
Read-History: `git show 5b450ce4f57e84c5814a44de44b81dc8d1d4c2a1` recovers the text; `git log --find-object=5b450ce4f57e84c5814a44de44b81dc8d1d4c2a1 --all` names the commit

## History
- 2026-09-06T17:08:55Z compacted by 8f55d4f0 from `draft` (record-sig 19f0f451)
