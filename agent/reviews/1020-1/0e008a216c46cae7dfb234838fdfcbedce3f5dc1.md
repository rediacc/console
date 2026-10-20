# Review 0e008a21: fix(scripts): an entry reached through a symlink still runs main(), and remote paths are quoted

Commit: 0e008a216c46cae7dfb234838fdfcbedce3f5dc1
Repo: private/account
Branch: 1020-1
Parent: cfb62722af72dcc7d3d0511467007ca59fc9fa95
Patch-Id: 4e720ceb58fbba14efc044cecaa06efcdc6fbc96
Reviewed-At: 2026-10-20T12:20:36Z
Model: claude-haiku-5-5
Cost: $0.0054 USD, 1 call(s), 36.6s
Diff: 10476 bytes, 5 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes CLI entries silently exiting 0 when reached through a symlink and quotes remote secrets paths; no new capability.
Dropped: 0
Body-Sig: 99868842dc568310

## Findings

### 0e008a21.1 [medium] tests/integration/rotation-bws-write.test.ts:185
Anchor: in-diff
Claim: The new comment says the token never appears in stderr, but the replacement assertion on the next line checks only VALUE, never FAKE_BWS_ACCESS_TOKEN, so a token leak to stderr would pass the test.
Resolution: fixed c477b348de542613ec1823b01813ca45abbf1662 | d778be9d 2026-10-20T12:23:47Z

### 0e008a21.2 [medium] scripts/generate-catalog-seed.ts:36
Anchor: in-diff
Claim: The entry guard changed from a URL comparison to realpathSync comparison, but no test covers the symlinked-entry case for this script, so a regression back to the old guard would not be caught.
Resolution: fixed c477b348de542613ec1823b01813ca45abbf1662 | d778be9d 2026-10-20T12:23:48Z

### 0e008a21.3 [medium] scripts/generate-exam-seed.ts:134
Anchor: in-diff
Claim: The entry guard changed to realpathSync comparison with no test for a symlinked invocation, so the fix for this script is unverified and a regression would pass CI.
Resolution: fixed c477b348de542613ec1823b01813ca45abbf1662 | d778be9d 2026-10-20T12:23:48Z

### 0e008a21.4 [medium] scripts/rotation/commands/rotate.ts:1358
Anchor: in-diff
Claim: secretsEnvWriteCommand now shell-escapes the secrets path and its .new twin, but no test exercises a path that needs quoting, so the changed behaviour is unverified.
Resolution: fixed c477b348de542613ec1823b01813ca45abbf1662 | d778be9d 2026-10-20T12:23:48Z

### 0e008a21.5 [low] scripts/rotation/bws-write.ts:124
Anchor: in-diff
Claim: realpathSync throws ENOENT at module load when process.argv[1] names a nonexistent path, where the old comparison returned false and skipped main; importers whose argv[1] is not a real file now crash on import.
Resolution: fixed c477b348de542613ec1823b01813ca45abbf1662 | d778be9d 2026-10-20T12:23:48Z

### 0e008a21.6 [low] scripts/rotation/commands/rotate.ts:1358
Anchor: in-diff
Claim: The sha in `[ "$(sha256sum ...)" = ${sha} ]` is still interpolated unquoted in the same command the commit hardens, so the quoting fix is incomplete for that operand.
Resolution: fixed c477b348de542613ec1823b01813ca45abbf1662 | d778be9d 2026-10-20T12:23:49Z
