# Review dbf9fdfc: docs(pins): the sibling-hint control's comment lists every way it goes red

Commit: dbf9fdfc985a7c99faccfcd8a202d962b44c25eb
Repo: console
Branch: 1008-1
Parent: 17bca580cc4896cb0907ecc6b3486dab9a99ef17
Patch-Id: 1a33758c7a7a8cf40fb90d1724cdb6701d2d491b
Reviewed-At: 2026-10-18T20:20:15Z
Model: claude-haiku-5-5
Cost: $0.0016 USD, 1 call(s), 12.3s
Diff: 2543 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=docs why=Comment-only edit to a pins self-test case; no user-facing behaviour changes.
Dropped: 0
Body-Sig: 9067585baa0686a2

## Findings

### dbf9fdfc.1 [low] scripts/pins/pins.ts:2485
Anchor: in-diff
Claim: The new comment says the control goes red when its --to guidance is lost, but the case's visible assertions (rs.rc, the 'check:fixture-tool also judges embed:zed' line, the 'npm run pins -- bump embed:tool <each behind sibling>' line, and the '--major --reason when a move is a major' line) contain no --to check, so dropping only the --to text would leave the case green unless that unseen-to-this-diff joint command string happens to carry it.
Resolution: open
