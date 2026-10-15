# Review dcdd1ab6: feat(ci): per-environment backup key pairs, a one-Worker push tool with portal health, and check:ci-backup-credential-isolation

Commit: dcdd1ab65ebbf75dbfd60e315d5edcc7872322c1
Repo: console
Branch: 1008-1
Parent: 4c876aa8137b876361ae61f1e2ca6fce7191cd0c
Patch-Id: e30c4bfb28105efbe60671469452d15e52276a4f
Reviewed-At: 2026-10-15T16:17:24Z
Model: claude-haiku-5-5
Cost: $0.0157 USD, 1 call(s), 59.4s
Diff: 212264 bytes, 28 files, truncated: yes
Unreviewed: .ci/rediacc_ci/quality/backup_credential_isolation.py, .ci/rediacc_ci/tests/gates/test_gate_backup_credential_isolation.py, .ci/rediacc_ci/tests/test_bench_captcha_switch.py, .ci/rediacc_ci/tests/test_deploy_set_account_worker_secrets.py, .ci/rediacc_ci/tests/test_ops_cf_family.py, .ci/rediacc_ci/tests/test_ops_portal_health.py, .ci/rediacc_ci/tests/test_ops_push_backup_credentials.py, .ci/rediacc_ci/tests/test_ops_units.py, .ci/scripts/quality/check_backup_credential_isolation.py, .github/workflows/cd-deploy-account.yml, .github/workflows/ci-quality.yml, CLAUDE.md, docs/ci-overhaul/07-port-brief.md, package.json, scripts/ci-runner/gates.lock.json, scripts/ci-runner/manifest.ts, scripts/data/doc-registry.md
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug,feature,ci why=Ops and CI tooling only: new push and health scripts, gate and per-environment secret plumbing; no product-facing change, and the deploy-bench fallback removal is a fix to the bench deploy path.
Dropped: 0
Body-Sig: d97a89bda3d940b5

## Findings

### dcdd1ab6.1 [medium] .ci/rediacc_ci/ops/push_backup_credentials.py:360
Anchor: in-diff
Claim: main() returns 2 when plan() raises PushError, and plan() also raises for a regions.json vs wrangler-config mismatch, which is a refusal; the module docstring says 1 means any refusal and 2 means usage only, so this refusal exits 2 and a caller that branches on 1 misreads it.
Resolution: fixed 9b69d3d6c214c076d2a9fdc1d7ac78a4f88800ad | d778be9d 2026-10-15T17:19:13Z

### dcdd1ab6.2 [low] .ci/rediacc_ci/ops/push_backup_credentials.py:191
Anchor: in-diff
Claim: secret_names() slices from the first '[' to the last ']' of wrangler's stdout, so any bracketed text printed before the JSON (e.g. a '[WARNING]' line on stdout) makes json.loads fail and the run refuses, contrary to the docstring's claim that text printed around the array is ignored.
Resolution: fixed 9b69d3d6c214c076d2a9fdc1d7ac78a4f88800ad | d778be9d 2026-10-15T17:19:14Z
