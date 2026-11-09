# Review 6ef3eced: fix(ci): the preview account Worker binds LICENSE_SIGNER to signer-bench-eu, so it serves after S3

Commit: 6ef3ecedaafa17ae29545da0ad50ef7c83852bac
Repo: console
Branch: 1104-1
Parent: 144530719371beb225a18615d0f47f9b1eef19b5
Patch-Id: 590b557980c9cfe84c8b44940d0be6303fc66fa4
Reviewed-At: 2026-11-09T16:07:22Z
Model: claude-haiku-5-5
Cost: $0.0069 USD, 1 call(s), 17.2s
Diff: 48718 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug,ci why=Preview-only CI deploy config fix; no user-facing product change.
Dropped: 0
Body-Sig: 8b2b80054e0c9b47

## Findings

### 6ef3eced.1 [low] .ci/rediacc_ci/deploy/deploy_www.py:193
Anchor: in-diff
Claim: The new props line is the only LICENSE_SIGNER binding guard, and the commit does not order the deploy: if a PR preview deploys before signer-bench-eu exists, the Worker still deploys and every licence request fails at runtime, with no CI check that the service is present.
Resolution: not-a-bug | .ci/rediacc_ci/deploy/deploy_www.py:187 wrangler refuses a deploy whose service binding names a missing Worker, so a preview cannot deploy before signer-bench-eu exists; the order is documented in the comment there | d778be9d 2026-11-09T19:50:38Z

### 6ef3eced.2 [low] .ci/rediacc_ci/tests/test_deploy_deploy_www.py:759
Anchor: in-diff
Claim: The absence check asserts only that the literal string "ED25519_PRIVATE_KEY" is missing from the TOML; if the account Worker's real private-key variable has another name, the assertion passes vacuously and does not guard the 'no private key' claim it is named for.
Resolution: open
