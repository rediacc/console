# Review c8deb1ae: fix(cli): a command span ends with the exit status the command set

Commit: c8deb1ae833de912edd09ca9b22eecbc5ee443d7
Repo: console
Branch: 1023-1
Parent: fefa28e92f83cfd8a439e697422c1ef3833419d1
Patch-Id: 0ef2e4dc46237db16b8b4967bf7ccbd00d4a7c87
Reviewed-At: 2026-11-01T03:39:09Z
Model: claude-haiku-5-5
Cost: $0.0014 USD, 1 call(s), 11.1s
Diff: 1598 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes telemetry span status so a command that sets a non-zero exit code ends its span as an error; internal telemetry correctness, no new capability.
Dropped: 0
Body-Sig: d0a586318d670182

## Findings

### c8deb1ae.1 [medium] packages/cli/src/cli.ts:357
Anchor: in-diff
Claim: `typeof requested === 'number' ? requested : 0` maps any non-number exit code to 0, so if process.exitCode holds a string such as '1' (allowed by Node's exitCode type), a failing command on a laptop still ends its span as success, the same OK-where-ERROR bug this commit fixes.
Resolution: fixed dd55298f0b4f8cbccc673b5a63135b9b88ad7b2c | d778be9d 2026-11-01T03:39:55Z
