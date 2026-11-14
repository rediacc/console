# Review df2460af: fix(cli): report entries rsync skips on upload, read from stdout

Commit: df2460afdcaabce8d52feba7e35b299b9ca2c0e8
Repo: console
Branch: 1104-1
Parent: 5d4de2c16d50ee27421a8d148ab35ddce88db309
Patch-Id: 803582486e296965446ea5c10fa5796b4b2c5259
Reviewed-At: 2026-11-06T12:44:11Z
Model: claude-haiku-5-5
Cost: $0.0025 USD, 1 call(s), 17.7s
Diff: 4987 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes skip warnings silently missing for privileged uploads; no new capability, so patch.
Dropped: 0
Body-Sig: 396a0415d319d12c

## Findings

### df2460af.1 [low] packages/cli/src/remote/sync/rsync.ts:359
Anchor: in-diff
Claim: stdoutText accumulates every stdout chunk for the whole rsync run and is never trimmed, so a very long sync with progress output holds all of it in memory; stderrText already grows the same way, so this roughly doubles that growth.
Resolution: fixed 942f387f2e5d096c802d789bac53155f1d63c527 | d778be9d 2026-11-06T21:33:32Z

### df2460af.2 [low] packages/cli/src/remote/sync/__tests__/rsync-skipped.test.ts:109
Anchor: in-diff
Claim: The assertion that run.stderr yields [] pins which stream rsync uses for the message, so a different rsync version that also writes it to stderr would fail this test even though the stdout fix is correct.
Resolution: fixed 942f387f2e5d096c802d789bac53155f1d63c527 | d778be9d 2026-11-06T21:33:32Z
