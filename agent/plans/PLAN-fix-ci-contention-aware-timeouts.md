# PLAN: contention-aware fix for hardcoded pass/fail timeouts waiting on real infra
Status: compacted
First-Seen: 2026-09-20
Full-Text-Blob: c52485b570655e7c9ac98b3e84c13085c7d6e614
Record-Sig: fd2c0d2a

## Why
A stop-hook judge requested a repo-wide sweep for siblings of the tutorial-player timeout bug: a fixed wall-clock timeout that gates a pass/fail verdict while waiting on real infrastructure (booting servers, containers, VMs), sized on fast machines but firing as false failures under contention on shared runners. A repo-wide grep returned 505+ matches; after reading candidates, 3
genuinely belonged to this bug class, plus 2 related structural findings.

## Outcome
Landed commit [unresolved], 2026-08-28. Implemented: (5a) ci-start-elite.sh and ci-start-account.sh timeouts raised 60s/120s to 180s with load diagnostics; (5b) wait-for-vm-ssh.sh per-VM budget 150s to 180s with docstring sync; (5d) check_tutorial_healthcheck_headroom.py scope widened to .ci/docker/ci/docker-compose.yml. Skipped consolidation (5c) as hygiene. Verified: bash -n,
linting clean, healthcheck gate selftest 3/3 pass, real run covers 4 files (was 3), YAML syntax clean, collateral gates unaffected.

## Lessons
- The repo already had an evidence-based 180s floor from two real incidents (tutorial-player gate and tutorial-healthcheck gate) — anchoring preventive fixes to institutional precedent prevents inventing arbitrary numbers.
- Dead-code duplication existed (unused wait_for() helper in common.sh while three scripts hand-rolled identical loops) — worth consolidating after as hygiene to prevent a fourth copy.
- Existing purpose-built gates were already solving the core problem; the real fix was extending their scope or narrowing deliberately, not creating new gates.
- Scope filtering mattered: 505 grep hits compressed to 3 real candidates by distinguishing 'times out and fails' (this class) from 'times out and falls back' (safe degradation) from 'doesn't gate verdict' (unrelated).
- Preventive fixes anchored to analogy need honesty in commit messages — avoid claiming direct proof where doing preventive-by-analogy to an institutional floor.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: d778be9d
Compacted-At: 2026-09-20T16:39:44Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: e87fa3ce, f2757830
Touched: .ci/scripts/infra/ci-start-elite.sh, .github/workflows/ci.yml, private/elite/docker-compose.yml, .ci/scripts/infra/ci-start-account.sh, .ci/docker/ci/docker-compose.yml, .ci/scripts/infra/wait-for-vm-ssh.sh, .github/workflows/ct-tests.yml, docs/ci-overhaul/06-progress.md, package.json, packages/e2e-tests/playwright.config.ts, .ci/scripts/test/run-account-e2e.sh, .ci/scripts/env/create-e2e-env.sh, private/renet/pkg/daemon/start_foreground.go, .ci/scripts/test/smoke-test-preview.ts, .ci/scripts/lib/common.sh, .ci/scripts/quality/check_tutorial_healthcheck_headroom.py
Gates: check:ci-baseline-key-semantics, check:ci-git-op-conditionals, check:ci-python-lint, check:ci-shell-lint, check:ci-timeout-headroom, check:ci-tutorial-healthcheck-headroom
Why-Source: model
Read-History: `git show c52485b570655e7c9ac98b3e84c13085c7d6e614` recovers the text; `git log --find-object=c52485b570655e7c9ac98b3e84c13085c7d6e614 --all` names the commit

## History
- 2026-09-20T16:39:44Z compacted by d778be9d from `done` (record-sig fd2c0d2a)
