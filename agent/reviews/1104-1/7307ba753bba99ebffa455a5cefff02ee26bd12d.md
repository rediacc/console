# Review 7307ba75: feat(enterprise): the shared tier binds its signer and no account Worker holds the licence private key

Commit: 7307ba753bba99ebffa455a5cefff02ee26bd12d
Repo: console
Branch: 1104-1
Parent: a1cf61cbeb5e30a94c30b0c5794cec4ef1ea2e87
Patch-Id: 944951f596a6f0fb321a439d4eab1cd03ca2d59b
Reviewed-At: 2026-11-09T13:03:40Z
Model: claude-haiku-5-5
Cost: $0.0086 USD, 1 call(s), 25.8s
Diff: 126104 bytes, 15 files, truncated: yes
Unreviewed: .ci/rediacc_ci/tests/goldens/twins/deploy.set-account-worker-secrets.jsonl
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature,ci why=Adds a shared-tier LICENSE_SIGNER binding and a deploy-signer profile, a new capability; the secret-set changes are deploy plumbing.
Dropped: 0
Body-Sig: b45aa0c79a44724f

## Findings

### 7307ba75.1 [high] .ci/rediacc_ci/ops/prune_worker_secrets.py:66
Anchor: in-diff
Claim: The new LEGACY_BWS entry maps ACCOUNT_ED25519_PRIVATE_KEY to its store key, so `prune_worker_secrets --region eu|us|asia --archive` (and bench via BENCH_LEGACY_BWS at line 79) reads the licence private key from bws and PUTs it onto the account Worker as __ARCHIVE_ACCOUNT_ED25519_PRIVATE_KEY, putting the key back on an account Worker, the exact state this commit removes.
Resolution: fixed 65d486db2e8d0fddb0b44e74e53dd94469e08919 | d778be9d 2026-11-09T13:27:42Z

### 7307ba75.2 [medium] workers/account/wrangler.eu.toml:77
Anchor: in-diff
Claim: The comment says the signer binding's deploy-time props carry the caller's identity, but `props = { tier = "shared", region = "eu" }` is static configuration fixed at deploy, not per-caller data, so anyone relying on this comment will misunderstand the authorisation model.
Resolution: fixed e7deb978060dac82a91ea9d68d88728a4a8852d1 | d778be9d 2026-11-09T13:27:42Z

### 7307ba75.3 [low] .ci/rediacc_ci/tests/test_deploy_set_account_worker_secrets.py:456
Anchor: in-diff
Claim: The docstring and test name say seventeen guards, but the same test now asserts `len(demanded) == 16`, so the description contradicts the assertion it documents.
Resolution: fixed e7deb978060dac82a91ea9d68d88728a4a8852d1 | d778be9d 2026-11-09T13:27:42Z
