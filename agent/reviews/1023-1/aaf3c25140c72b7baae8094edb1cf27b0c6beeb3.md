# Review aaf3c251: feat(configs): clean break, a pull with no envelope header gets 426 against a v3 store

Commit: aaf3c25140c72b7baae8094edb1cf27b0c6beeb3
Repo: private/account
Branch: 1023-1
Parent: 969fcf997fc7e487f982a77a9e24223f2264cbb0
Patch-Id: ddedde5c84544ca4798d937d7afcb5dbd73c0f2e
Reviewed-At: 2026-10-27T05:11:06Z
Model: claude-haiku-5-5
Cost: $0.0043 USD, 1 call(s), 20.8s
Diff: 7172 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature,docs why=Headerless pulls on v3 configs now get 426: a breaking change for old rdc builds. Consider major. CLAUDE.md updated to match.
Dropped: 0
Body-Sig: 0ced1620055eeed3

## Findings

### aaf3c251.1 [medium] src/routes/configs.ts:160
Anchor: in-diff
Claim: Against a stored v3 envelope, a pull whose x-config-envelope header is present but does not parse (for example an empty value, 'abc', or '0') still hits the early return and gets 200 with configData, so the 426 the commit adds for a missing header can be avoided by sending any non-numeric value. No test in the diff covers this case.
Resolution: fixed c28723f63cbe231fbb4fc14fb877580a8bead89d | d778be9d 2026-10-27T05:23:41Z
