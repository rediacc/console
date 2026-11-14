# Review b09cfbce: feat(signer): the routeless signer Worker and its deploy module

Commit: b09cfbcef1da11aede06aeed58cf5a6f70013edf
Repo: console
Branch: 1104-1
Parent: 85109d008c575323151290a91af727194cd99f30
Patch-Id: 64288522f445ba269776588a24608c8e3a594978
Reviewed-At: 2026-11-09T09:53:40Z
Model: claude-haiku-5-5
Cost: $0.0099 USD, 1 call(s), 41.6s
Diff: 102188 bytes, 12 files, truncated: yes
Unreviewed: workers/signer/package-lock.json
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature,ci why=Adds a new routeless signer Worker and its deploy module, a new capability with no change to existing user-facing behaviour.
Dropped: 0
Body-Sig: d8e135e5592f4302

## Findings

### b09cfbce.1 [medium] .ci/rediacc_ci/deploy/deploy_signer.py:354
Anchor: in-diff
Claim: When `wrangler deployments list` fails or prints unparsable output on a redeploy, newest_version returns None, so the record gets previous_version_id null and this line prints 'Rollback: none (first deploy)' even though a previous version exists.
Resolution: fixed 759876e38b57f30d824629cc423a79b1e13fef41 | d778be9d 2026-11-09T17:30:55Z

### b09cfbce.2 [medium] .ci/rediacc_ci/deploy/deploy_signer.py:325
Anchor: in-diff
Claim: The new version is deployed at line 311 before `wrangler secret bulk`; if that bulk call fails here, the run raises and never writes the record or prints a rollback command, so the live new version has no recorded rollback target.
Resolution: fixed 759876e38b57f30d824629cc423a79b1e13fef41 | d778be9d 2026-11-09T17:30:55Z

### b09cfbce.3 [medium] .ci/rediacc_ci/deploy/deploy_signer.py:151
Anchor: in-diff
Claim: The bindings dict comprehension keeps only the last d1 entry per binding name, so a rendered config with two CONTROL entries passes the CONTROL check whenever the last one names the right database, even if an earlier one names a different database.
Resolution: fixed 759876e38b57f30d824629cc423a79b1e13fef41 | d778be9d 2026-11-09T17:30:55Z
