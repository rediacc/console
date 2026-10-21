# PLAN: run the backup browse-at e2e tier in CI

Status: approved -- 2026-10-21 under the operator's standing rule that a finding is fixed in the session that finds it (CLAUDE.md rule 2), not a ruling on this plan (worklist #1a07399b); the tier passed on the local fleet but no workflow ran it
Depends-On: PLAN-chunk-store-browse-toc-and-remote.md
First-Seen: 2026-10-21
Owner: d778be9d
Priority: P2 -- the only end-to-end proof of `rdc backup browse --at`, today run by hand only
Concurrency: exclusive -- moves the BROWSE-AT tier out of 26-backup-storage-cli.test.ts, which no other writer may edit meanwhile
Owns: .ci/rediacc_ci/testrun/start_account.py, .ci/rediacc_ci/testrun/start_backup_plane.py, .ci/rediacc_ci/core/account_lifecycle.py, .ci/rediacc_ci/tests/test_testrun_start_account.py, .ci/rediacc_ci/tests/test_testrun_start_backup_plane.py, packages/e2e-tests/tests/26-backup-storage-cli.test.ts, packages/e2e-tests/tests/27-backup-browse-at.test.ts, packages/e2e-tests/src/utils/backup/**, packages/e2e-tests/playwright.backup-browse-at.config.ts, packages/e2e-tests/playwright.config.ts, .github/workflows/ct-tests.yml, .github/workflows/ci.yml, scripts/gates/check-e2e-coverage.ts, .ci/policy/.e2e-coverage-allowlist

The suite-26 BROWSE-AT tier passes on the local KVM fleet, but CI provides none of its four prerequisites, and wiring the current config as is would mislead the coverage gate.

## Findings (checked in the tree, 2026-10-21)

1. Prerequisites CI lacks, each with a no-new-secret source:
   - (a) RustFS on 127.0.0.1:9100 with the local probe bucket (backup_local_plane PROBE_BUCKET): account_lifecycle._start_rustfs (.ci/rediacc_ci/core/account_lifecycle.py:690-755) starts config-rustfs with dev-default keys (private/account/docker-compose.yml:41-50); backup_local_plane.create_bucket (.ci/rediacc_ci/drills/backup_local_plane.py:85-106) adds the bucket.
   - (b) A gateway carrying ACCOUNT_BACKUP_S3_*: rediacc_ci.testrun.start_account already starts src/entry/node.ts with self-minted keys and passes os.environ through; private/account/src/entry/node.ts:56 builds the backup plane from the S3 env.
   - (c) A backup:read token: .ci/rediacc_ci/testrun/start_account.py:44 hard-codes license and subscription scopes only.
   - (d) The 192.168.111.254 address the VMs reach (wire.bridge_host): it must appear in the published account server URL (the renewalUrl stamp, private/account/src/app.ts:542) and in ACCOUNT_BACKUP_S3_ENDPOINT, since SigV4 signs the Host header.
2. check-e2e-coverage.ts strips comments and matches `backup_browse_at` / `backup browse at`; suite 26 names the function only in comments, so deleting the allowlist entry would red as missing. A leg must drive the function through a vault, as suite 25 drives backup_verify.
3. The gate counts whole files, so suite 26's restore literals would mark backup_restore covered while the browse-at tier never runs restore. The tier moves to its own file, 27-backup-browse-at.test.ts.
4. K8s Multinode is at p90 20.0 of a 25 cap (worst 27.1 of 30), so the tier gets a new job rather than joining it.

## Boxes

- [x] B1: start_account gains `--scopes` (default unchanged) and `--advertise-host` (publishes the account server at that host) -- acceptance: unit tests for both options and the unchanged default; check:ci-python-lint rc=0
    (ticked) 2026-10-21T09:59:02Z by d778be9d: commit:d47c66ccb pytest test_testrun_start_account.py 4 new cases, 28 passed with the plane tests; check:ci-python-lint rc=0
- [x] B2: start_rustfs made public in account_lifecycle; new rediacc_ci.testrun.start_backup_plane: RustFS, the probe bucket (fatal on failure), start_account with backup scopes, the S3 env at the bridge host, and a /health probe from worker 11 over SSH -- acceptance: unit tests with the existing fakes; check:ci-python-env-registry and check:ci-python-lint rc=0
    (ticked) 2026-10-21T09:59:04Z by d778be9d: commit:d47c66ccb then 0c651fd75 and 372a2b73 (review fixes); pytest test_testrun_start_backup_plane.py 15 passed; check:ci-python-env-registry and check:ci-python-lint rc=0
- [x] B3: the BROWSE-AT tier moves to packages/e2e-tests/tests/27-backup-browse-at.test.ts with shared helpers under src/utils/backup/, plus a leg that drives the backup_browse_at function through a vault; suite 26 keeps the rest -- acceptance: biome, tsc, check:ci-e2e-case-blind rc=0; suites 26 and 27 pass on the local fleet
    (ticked) 2026-10-21T09:59:05Z by d778be9d: commit:15535159f suite 27 with vault leg 3b; biome and tsc rc=0; check:ci-e2e-case-blind rc=0; suite 27 8 passed on the local fleet
    (evidence) 2026-10-21T11:00Z: after 895ebda28 (signer key shared with the renet build), suite 26 13 passed 0 skipped and suite 27 8 passed 0 skipped on the local fleet through start_backup_plane --worker 11; the 09:05Z suite-27 run had used another account server, and suite 26 failed 2 tests and skipped 6 before the key fix.
- [x] B4: playwright.backup-browse-at.config.ts (no globalSetup, for the reasons in packages/e2e-tests/playwright.backup-storage.config.ts:8-28), gated out of the base playwright.config.ts -- acceptance: E2E Workers does not collect suite 27; check:ci-e2e-skip-hygiene rc=0
    (ticked) 2026-10-21T09:59:06Z by d778be9d: commit:15535159f and 6b1ff489d; base config lists 0 suite-27 tests without BACKUP_BROWSE_AT_SUITE=1; check:ci-e2e-skip-hygiene rc=0
- [x] B5: local proof with only VM_WORKERS=11 through the two new modules -- acceptance: suite 27 passes, no declared skip, with `--fail-on-skip`
    (ticked) 2026-10-21T09:59:07Z by d778be9d: commit:15535159f local run VM_WORKERS=11: 8 passed, 0 skipped, 157 s (reports/backup-browse-at-logs, 2026-10-21T09:05Z) SUPERSEDED: that run used another account server, not start_backup_plane; the 11:00Z evidence line below is the proof.
    (evidence) 2026-10-21T11:00Z: the run through the two new modules: start_backup_plane --worker 11 rc=0 with the preflight matching, then suite 27 with VM_WORKERS=11 and --fail-on-skip, 8 passed, 0 skipped, 157 s (reports/backup-browse-at-logs/summary.txt).
- [x] B6: new ct-tests.yml job test-e2e-backup-browse-at (template test-e2e-migrate: needs renet-embed-assets, timeout-minutes 15, VM_WORKERS '11'), running start_backup_plane then `rediacc_ci.testrun.e2e --config playwright.backup-browse-at.config.ts --fail-on-skip`, with diagnostics and the account-for-e2e.log artifact; no E2E_EXPECT_NO_CHUNK_BROWSE_AT -- acceptance: check:ci-workflows and actionlint rc=0
    (ticked) 2026-10-21T10:02:38Z by d778be9d: commit:9b7a77c20 job test-e2e-backup-browse-at; check:ci-workflows and check:ci-actionlint rc=0. DEPS-WAIVED: PLAN-chunk-store-browse-toc-and-remote has 11 of 11 boxes ticked on this branch and closes after the merge
- [x] B7: check-e2e-coverage.ts PRODUCTION_REGISTRY gains the new config; the backup_browse_at block leaves .ci/policy/.e2e-coverage-allowlist -- acceptance: check:ci-e2e-coverage rc=0
    (ticked) 2026-10-21T09:59:09Z by d778be9d: commit:9b7a77c20 PRODUCTION_REGISTRY entry and allowlist block removed; check:ci-e2e-coverage rc=0
- [ ] B8: the job runs green on the PR, and `budget_report.py --refresh --branch <PR>` records its p90 -- acceptance: CI Complete includes the job green; check:ci-lane-budget rc=0 (the seeded 9.0 is replaced by the measured p90; one above the 12-minute default needs an operator ruling in JOB_BUDGET_CAPS)

## Risks

- No CI job yet has a VM call a service on the runner; the B2 health probe makes that fail loudly rather than time out.
- `rdc machine add machine-12` runs even with one worker; if it contacts the machine, VM_WORKERS becomes '11 12'.
- rustfs/rustfs:latest and amazon/aws-cli are unpinned images under Docker Hub rate limits.
