# Review 3e6cdfcd: feat(account): audit bucket, grant revoker, forensics queue and vars in every account wrangler config

Commit: 3e6cdfcdedb65fa3b5aa020bda998bf944721c8b
Repo: console
Branch: 1121-1
Parent: c56a4c3e0abaecd467a7b09a1f9d64351ea1350a
Patch-Id: 2e75cb01c306ae2024604cf558ab170302735519
Reviewed-At: 2026-11-25T21:56:57Z
Model: claude-haiku-5-5
Cost: $0.0111 USD, 1 call(s), 31.7s
Diff: 86659 bytes, 19 files, truncated: yes
Unreviewed: workers/account/wrangler.eu.toml, workers/account/wrangler.us.toml
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature,ci why=Adds audit bucket, grant revoker binding, forensics queue and vars to every account config: a new capability plus gate changes.
Dropped: 0
Body-Sig: 45112eaddb7c9d46

## Findings

### 3e6cdfcd.1 [medium] .ci/rediacc_ci/ops/reset_bench.py:452
Anchor: in-diff
Claim: reset_bench skips the audit wipe with no error when the bench toml has no AUDIT_BUCKET binding (`if r2.audit_bucket:`), so the run prints 'bench has been reset' while audit objects remain; the module docstring says the wipe deletes the audit bucket, and bench_names says callers that need the bucket refuse it by name, which this caller does not do.
Class: doc-contradicts-code
Resolution: open

### 3e6cdfcd.2 [medium] .ci/rediacc_ci/ops/reset_bench.py:453
Anchor: in-diff
Claim: No test fails if the audit wipe call `_wipe_r2(r2.audit())` is removed or never reached: the region test's fake `_wipe_r2` only records ('wipe_r2',) and no test asserts the audit bucket is emptied, though the commit says reset_bench empties it.
Class: missing-control-test
Resolution: open
