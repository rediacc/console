# Review bb350bdb: build(deps): typescript 7.0.2 in private/account, now the lint stack no longer pins it

Commit: bb350bdbcda6ba199e9d75cdf61829d27caff6b5
Repo: private/account
Branch: 1008-1
Parent: 924dcd532c57ab327428f96331b7f6ad28b2bd4c
Patch-Id: e287ffbf125052f1869dd696cdbceb754b3b63a5
Reviewed-At: 2026-10-14T12:51:46Z
Model: claude-haiku-5-5
Cost: $0.0076 USD, 1 call(s), 34.2s
Diff: 32780 bytes, 5 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=Dev-only TypeScript toolchain bump and lockfile rewrite; no runtime or user-facing change.
Dropped: 0
Body-Sig: 6b008d3a70d57b9b

## Findings

### bb350bdb.1 [high] package-lock.json:63
Anchor: in-diff
Claim: The lock's workspace entry for ../../packages/shared now declares typescript ^7.0.2, but packages/shared/package.json is not in this commit and still declares ^6.0.3, so the lock no longer matches the manifest and `npm ci` will reject it as out of sync.
Resolution: open

### bb350bdb.2 [high] e2e/package-lock.json:27
Anchor: in-diff
Claim: The e2e lock's shared-workspace entry now declares typescript ^7.0.2, but no node_modules/typescript entry is changed and e2e/package.json is not in the diff, so the locked 6.0.3 does not satisfy the declared range and the e2e install fails out of sync.
Resolution: open

### bb350bdb.3 [medium] package.json:65
Anchor: in-diff
Claim: The root toolchain moves from TypeScript 6.0.3 to 7.0.2 (the lock also drops the tsserver bin), but the commit only verifies tsc on private/account, typecheck:web and check:ci-lockfile; lint and any tool that loads tsserver or the typescript JS API are not exercised.
Resolution: open
