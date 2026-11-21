# Review 57f7d3fa: feat(enterprise): company secrets generated, stored under opaque names, minted and pushed

Commit: 57f7d3fa12f2c0af0aeac2c6ab1b0a72e7dfb791
Repo: console
Branch: 1104-1
Parent: 0f1d42cac31778967625b986f267cdf531dfe2c9
Patch-Id: f7178d967e2e407dfa18479202da94d3c6f6bce9
Reviewed-At: 2026-11-09T03:54:26Z
Model: claude-haiku-5-5
Cost: $0.0106 USD, 1 call(s), 47.8s
Diff: 48018 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=feature why=New internal CI provisioning module (.ci tooling); no shipped user-facing product change.
Dropped: 0
Body-Sig: 4daab4170ad3c441

## Findings

### 57f7d3fa.1 [high] .ci/rediacc_ci/enterprise/secrets.py:266
Anchor: in-diff
Claim: _step re-raises with `from None`, which sets __cause__ to None and suppresses display, but Python still attaches the original seam exception as __context__; a seam such as the minter's RuntimeError('mint failed, token ...') keeps its value-bearing message reachable from the SecretsError, contrary to the commit's 'no value reaches an exception' claim. The tests check __cause__ and __suppress_context__, not __context__, so they pass anyway.
Resolution: fixed 37f1b9784f360c074c92a3209fb538833d89b87e | d778be9d 2026-11-09T04:37:24Z

### 57f7d3fa.2 [medium] .ci/rediacc_ci/enterprise/secrets.py:381
Anchor: in-diff
Claim: If create-user succeeds but put-user-policy or create-access-key fails, a rerun finds no SES pair in the store and calls create-user again, which fails on the existing IAM user, so the company can never resume without manual AWS cleanup despite the 'a rerun reuses it' claim.
Resolution: fixed 37f1b9784f360c074c92a3209fb538833d89b87e | d778be9d 2026-11-09T04:37:24Z

### 57f7d3fa.3 [medium] .ci/rediacc_ci/enterprise/secrets.py:383
Anchor: in-diff
Claim: The SES pair is written as two separate creates; if the second create fails or the process dies between them, the store holds one half and every later run refuses via _check_pairs, while the minted IAM access key is orphaned and no code path completes the pair.
Resolution: fixed 37f1b9784f360c074c92a3209fb538833d89b87e | d778be9d 2026-11-09T04:37:24Z

### 57f7d3fa.4 [medium] .ci/rediacc_ci/enterprise/secrets.py:395
Anchor: in-diff
Claim: The R2 pair is also written as two creates; if the secret-half create fails after the token id is stored, the Cloudflare token exists but a rerun is refused as a half pair, not resumed, and the token cannot be recovered since its value is never stored.
Resolution: fixed 37f1b9784f360c074c92a3209fb538833d89b87e | d778be9d 2026-11-09T04:37:24Z

### 57f7d3fa.5 [medium] .ci/rediacc_ci/enterprise/secrets.py:399
Anchor: in-diff
Claim: The OTLP JSON shape is checked only here, after the SES user and R2 token have been minted and their values stored, so a malformed OBS_OTLP_CREDENTIALS value leaves a live IAM user, R2 token and store entries behind, contrary to the comment at line 351 saying the caller's half is checked before anything is written or minted.
Resolution: fixed 37f1b9784f360c074c92a3209fb538833d89b87e | d778be9d 2026-11-09T04:37:24Z
