# PLAN: Backup presign fails closed on a missing bucket or secret; bench bucket derived from its binding
Status: executing -- triaged PLAN+SUBAGENT for worklist #ca9be012 on 2026-10-24; design by a Plan agent, implemented this session on 1023-1.
Depends-On: no-dep -- the deploy paths already supply ACCOUNT_BACKUP_S3_BUCKET; this hardens the Worker and the one hand-run path
Priority: P1 -- a Worker with ENDPOINT and KEY_ID but no BUCKET or SECRET mints nothing (the SDK throws per request) and the cron warning stays silent
Owner: d778be9d
Updated: 2026-10-24
Owns: private/account/src/services/backup-chunk-store.ts, private/account/tests/integration/backup-plane-selection.test.ts, private/account/tests/integration/cron-wiring.test.ts, .ci/rediacc_ci/ops/deploy_bench.py, .ci/rediacc_ci/tests/test_ops_cf_family.py, scripts/gates/check-backup-bucket-conformance.ts, docs/backup-storage/07-execution-record.md
Live-Proof: bench -- the bucket requirement and presign change in private/account/src/services/backup-chunk-store.ts is the account surface, whose only live target is bench.
Concurrency: parallel

## Why

Worklist #ca9be012 said Workers deploys push only three ACCOUNT_BACKUP_S3_* values. Checked against the tree, the deploy half is wrong: CD (`.github/workflows/cd-deploy-account.yml:62` and `:379-380`, then `.ci/rediacc_ci/deploy/set_account_worker_secrets.py:202`, which refuses an empty bucket at `:423-429`), `.ci/rediacc_ci/ops/deploy_bench.py:157-159` and `.ci/rediacc_ci/ops/push_backup_credentials.py:179` all push ACCOUNT_BACKUP_S3_BUCKET, derived from regions.json, and `check:ci-backup-bucket-conformance` holds regions.json equal to the six wrangler BACKUP_BUCKET bindings. What is real:

1. createBackupPlane's Workers branch (`private/account/src/services/backup-chunk-store.ts:1152-1158`) builds the presign minter when only ENDPOINT and ACCESS_KEY_ID are set, filling bucket and secret with `''`. An empty Bucket makes getSignedUrl throw "No value provided for input HTTP label: Bucket." (reproduced with the repo's SDK), so every mint fails at request time; grantMinter is not null, so the cron warning (`private/account/src/entry/cloudflare.ts:93-98`), which already names all four keys, never fires.
2. `.ci/rediacc_ci/ops/deploy_bench.py:158-159` takes the bench bucket from an env override or a hardcoded literal, not from `workers/account/wrangler.bench.toml:81-83`, and no gate covers bench.
3. `docs/backup-storage/07-execution-record.md:325` says deploy_bench pushes three values; it pushes four.

## Design

- Keep ACCOUNT_BACKUP_S3_BUCKET a Worker secret computed by the deploy from regions.json (or wrangler.bench.toml for bench). Rejected: `[vars]` (a second copy of the name, colliding with the existing secret on seven Workers and breaking push_backup_credentials' fixed name set); deriving it in the Worker (a binding does not expose its bucket name at runtime).
- Worker, fail closed: the Workers branch builds S3PresignGrantMinter only when ENDPOINT, BUCKET, ACCESS_KEY_ID and SECRET_ACCESS_KEY are all non-empty, passed through without `?? ''`; otherwise `{ store, grantMinter: null }`, so the existing warning fires. The Node branch (`:1169`) keeps its behaviour; one shared helper keeps the two branches from drifting. The doc comment at `:1113-1118` follows.
- Bench: deploy_bench reads the bucket from the BACKUP_BUCKET binding in `workers/account/wrangler.bench.toml` (reusing `push_backup_credentials._config_binding`); the env override and the literal go; an env value that differs from the binding, or a missing binding, is a DeployError before the first remote write.
- Gate: extend `check:ci-backup-bucket-conformance` (scripts/gates/check-backup-bucket-conformance.ts): a source-shape row refusing a `?? ''` fallback for the bucket in the Workers branch, and a bench row (the binding exists with a non-empty bucket_name; deploy_bench.py quotes no `rediacc-backups-` literal), each with controls that fire on a plant; the floor rises to six regional plus one bench, and the stale `:977-985` cite is fixed.

## Boxes

- [x] B1: The Workers branch requires all four ACCOUNT_BACKUP_S3_* values, with no `?? ''` for bucket or secret. Accept: `cd private/account && npx vitest run tests/integration/backup-plane-selection.test.ts tests/integration/backup-presign-grant.test.ts` rc=0
    (ticked) 2026-10-24T13:52:55Z by d778be9d: account 5dd6b14 under d2953620b; B1 accept: vitest backup-plane-selection + backup-presign-grant rc=0 (16 passed)
- [x] B2: Plane-selection tests with the R2 binding: no BUCKET gives a null grantMinter; an empty BUCKET gives null; no SECRET_ACCESS_KEY gives null; the full set gives an S3PresignGrantMinter whose store.bucket is set (control). Accept: `cd private/account && npx vitest run tests/integration/backup-plane-selection.test.ts` rc=0
    (ticked) 2026-10-24T13:52:58Z by d778be9d: account 5dd6b14 under d2953620b; B2 accept: vitest backup-plane-selection rc=0
- [x] B3: cron-wiring test: BACKUP_BUCKET bound with ENDPOINT, KEY_ID and SECRET but no BUCKET logs "grant minter is unusable"; the quiet cases stay green. Accept: `cd private/account && npx vitest run tests/integration/cron-wiring.test.ts` rc=0
    (ticked) 2026-10-24T13:53:00Z by d778be9d: account 5dd6b14 under d2953620b; B3 accept: vitest cron-wiring rc=0
- [x] B4: deploy_bench derives the bucket from wrangler.bench.toml; an env mismatch and a missing binding are DeployErrors, each with a test. Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_ops_cf_family.py -q` rc=0
    (ticked) 2026-10-24T13:53:03Z by d778be9d: d2953620b; pytest test_ops_cf_family.py rc=0 (41 passed)
- [x] B5: check:ci-backup-bucket-conformance gains the source-shape and bench rows with controls, the new floor and the fixed cite. Accept: `npm run check:ci-backup-bucket-conformance` rc=0
    (ticked) 2026-10-24T13:53:22Z by d778be9d: d2953620b; npm run check:ci-backup-bucket-conformance rc=0 (7 deployments)
- [x] B6: docs/backup-storage/07-execution-record.md:325 says deploy_bench pushes four values, the bucket derived from the binding. Accept: `grep -n "pushes four" docs/backup-storage/07-execution-record.md` rc=0
    (ticked) 2026-10-24T13:53:06Z by d778be9d: d2953620b; grep 'pushes four' 07-execution-record.md rc=0 at :325
- [ ] LP-bench [live] Fresh bench receipt (PLAN-tested-on-bench ruling 3): deploy this branch to bench with deploy_bench, then record and tick through worklist.py --live-proof.
  - Accept: `live-proof bench account-smoke`

## Risks

- Live Workers missing BUCKET or SECRET move from "mint throws" to store-only with BACKUP_NOT_CONFIGURED and a nightly warning: strictly more honest, and no Worker deployed through CD or promote should be in that state. Soak on edge, read the 03:00 UTC cron log per region, then promote.
- No wrangler config changes, so binding re-provisioning is not at risk.
- Bench is hand-run; a deploy_bench that refuses an exported ACCOUNT_BACKUP_S3_BUCKET could surprise an operator; the refusal names the binding's value.
- The source-shape gate row is textual; its needle stays tight and controlled both ways so a refactor cannot make it vacuous.
