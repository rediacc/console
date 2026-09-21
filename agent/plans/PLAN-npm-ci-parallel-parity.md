# PLAN: npm run ci parity gate + parallel runner
Status: compacted
First-Seen: 2026-09-17
Owner: ci-parallel-plan agent, branch 0731-2
Full-Text: f7a5351a9 agent/PLAN-npm-ci-parallel-parity.md
Full-Text-Blob: 579a43b2793afd84e1ec525e2c236f98ed11e94e
Record-Sig: 0fe02d7f

## Why
`npm run ci` was a single 93-step `&&` chain in package.json, 17.4 minutes serially, and BOTH existing parity gates parsed that string as their input. The moment the chain became a runner invocation, both would read an empty chain and go green over everything: issue #549's failure class, manufactured at scale. So the runner and a rewritten parity gate could not land separately, and
the plan's one non-negotiable constraint was one branch, one PR, both halves.

## Outcome
SHIPPED, both halves in one commit, aa3ada325. Measured against the tree 2026-09-06. `scripts/ci-runner/` carries run.ts, pool.ts, exec.ts, report.ts and manifest.ts and has since grown gate-spec.ts, lanes.ts, surface.ts and the generated gates.lock.json. `scripts/gates/check-ci-parity.ts` replaced both old parity scripts, which are gone from the tree, and `.ci-chain-exempt` was
folded into `.ci-parity-exempt` with the `ci-only` / `local-only` direction tags. The `ci` key runs `--selftest` before the real run, which is stronger than the plan asked for. CORRECTION TO THE PLAN'S OWN HEADER: the two commit shas its `## Status` line offers as its evidence do not resolve in this repository today, and its date is five days later than the real landing. Cite
aa3ada325 instead.

## Lessons
- This plan is itself an instance of the defect W12 exists for. Its own evidence
pointers were rebased away and nothing ever reported it; the record's `Full-Text-Blob` is content-addressed and cannot rot the same way.
- The load-bearing constraint held. One commit created the runner, the unified
gate and both gate suites, and deleted the two scripts it replaced, so there was never a window in which a parity gate read an empty chain.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:08:52Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: package.json, .ci/scripts/quality/check-command-tree.sh, .ci/scripts/quality/check-cli-contract.sh, docs/agent-reference/ci-gates.md, docs/agent-reference/suppressions.md, .ci/scripts/ci/scope-map.cjs, scripts/gates/check-suppression-liveness.ts
Gates: check:ci-account-no-admin-role, check:ci-account-no-node-env-routes, check:ci-account-portal, check:ci-account-scope-audit, check:ci-account-server, check:ci-autopilot-workflow, check:ci-command-planes, check:ci-cta-bolt, check:ci-dead-bash, check:ci-editorconfig, check:ci-external-links, check:ci-i18n-cross-locale, check:ci-jq-boolean-default, check:ci-locale-sources, check:ci-lockfile, check:ci-no-otlp-creds, check:ci-parity, check:ci-quality-gates, check:ci-rdc-sh-env, check:ci-redirects
Why-Source: author
Read-History: `git show 579a43b2793afd84e1ec525e2c236f98ed11e94e` recovers the text; `git log --find-object=579a43b2793afd84e1ec525e2c236f98ed11e94e --all` names the commit

## History
- 2026-09-06T17:08:52Z compacted by 8f55d4f0 from `done` (record-sig 0fe02d7f)
