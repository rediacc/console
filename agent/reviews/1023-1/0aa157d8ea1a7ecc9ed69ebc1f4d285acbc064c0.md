# Review 0aa157d8: fix(cli-tests): declare sshConfig.test.ts madeHomes before the first hook and state one count (reviews 8e16a9ff.1-.2)

Commit: 0aa157d8ea1a7ecc9ed69ebc1f4d285acbc064c0
Repo: console
Branch: 1023-1
Parent: 8e16a9ffaef260452c04ad9b70792784ca5ae198
Patch-Id: b64cad277bd30687954ec1a2ed316970bdf17408
Reviewed-At: 2026-10-24T18:11:52Z
Model: claude-haiku-5-5
Cost: $0.0013 USD, 1 call(s), 11.0s
Diff: 1480 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug why=Test-only cleanup: moves the madeHomes declaration above its first use and corrects a comment count; no user-facing behaviour change.
Dropped: 0
Body-Sig: 6dbdd3a51a530b15

## Findings

### 0aa157d8.1 [low] packages/cli/src/remote/vscode/__tests__/sshConfig.test.ts:35
Anchor: in-diff
Claim: The comment hard-codes a measured count (3,623 sshconfig-* directories as of 2026-10-24) that is a snapshot of one machine's /tmp and will go stale; the diff itself shows the figure changing from 3,255 to 3,623, so it is already a number that moved once.
Resolution: open
