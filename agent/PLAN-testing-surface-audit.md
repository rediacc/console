# PLAN: Testing-surface audit, and the gates that close it
Status: compacted
Owner: 97604f47
Full-Text-Blob: 50958743b0369bf4807e1db656bb88a7a58464b5
Record-Sig: b9b1a596

## Why
The operator required 'no gap for testing': every item tested locally must wire into CI. This audit discovered gates that cannot fail (account enum check is blind to wrapped enums and missing paths), tests that don't run (packages/provisioning unit tests, e2e unit tests run only in Lane T which skips on push), and integrations untested (backup GC delete paths never run against real
stores; resolveSnapshotAt has zero coverage).

## Outcome
Audit complete. Ten proposed fixes documented in the plan file (F1-F10), ranging from a GC leg in the backup drill to meta-gates that prevent anti-vacuity registry decay. Status: proposal stage, no fixes implemented. Highest-consequence fix: F1, which catches S3-semantics defects by actually calling delete against live RustFS.

## Lessons
- A gate that runs and cannot fail is invisible without mutation testing. The account enum gate fails silently on both wrapped formatting (repo's own formatter's output) and missing paths (empty dir passes). Inversion required: a control that plants the defect and requires red.
- Test files that exist but no config selects are never caught. The ops-lifecycle orphan has 10 tests, zero configs, and claims coverage of an ops 'reset' verb that does not exist. Gate must enumerate files and require each selected or documented.
- Backup drill asserts control-plane logic with synthetic data (heredocs, hand-built manifests). It never touches the actual S3 delete paths, pagination, or prefix scoping. The byte-identical restore promise rides a single gated test that never runs in CI.
- Lane T (test-only lane) skips on push-to-main. Unit tests in provisioning and e2e live only in Lane T and never run on push. check:ci-parity sees only Lane Q, so the split is invisible to the gate that exists to prevent it.
- Hardcoded paths in npm script bodies are invisible to the path-existence gate, which scans only shell/ts files. Two account role gates carry unresolvable paths in package.json that grep never sees.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: draft
Compacted-By: d778be9d
Compacted-At: 2026-09-20T18:02:42Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: 24c98380, e87fa3ce
Touched: .github/workflows/ci-quality.yml, .ci/scripts/private/run-account.sh, private/account/vitest.config.ts, .ci/scripts/private/run-renet.sh, private/renet/.ci/ci.sh, private/renet/.ci/scripts/test/run-tests.sh, scripts/gates/check-ci-parity.ts, packages/e2e-tests/README.md, scripts/ci-runner/manifest.ts, .ci/scripts/test/run-unit.sh, .ci/scripts/test/run-account-e2e.sh, .ci/scripts/infra/ci-start-elite.sh, .gitignore, .ci/scripts/test/gates/test-gate-paths-exist.sh, private/renet/.ci/scripts/quality/deadcode.sh, .ci/scripts/quality/check-mutate-check.sh, biome.json, private/account/src/db/schema.ts, .ci/scripts/test/gates/test-tutorial-render-queue.sh, .ci/scripts/quality/check-go-deps.sh
Gates: check:ci-account-no-admin-role, check:ci-account-no-node-env-routes, check:ci-e2e-coverage, check:ci-mutate-check, check:ci-parity, check:ci-renet, check:ci-retention-knob-parity, check:ci-tutorial-render-queue, check:i18n, check:test-e2e-unit, check:test-provisioning
Why-Source: model
Read-History: `git show 50958743b0369bf4807e1db656bb88a7a58464b5` recovers the text; `git log --find-object=50958743b0369bf4807e1db656bb88a7a58464b5 --all` names the commit

## History
- 2026-09-20T18:02:42Z compacted by d778be9d from `draft` (record-sig b9b1a596)
