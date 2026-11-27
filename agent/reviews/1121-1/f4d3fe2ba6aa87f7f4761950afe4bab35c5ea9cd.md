# Review f4d3fe2b: refactor(gates): the tutorial family is one table-driven gate with a --selftest (CR4)

Commit: f4d3fe2ba6aa87f7f4761950afe4bab35c5ea9cd
Repo: console
Branch: 1121-1
Parent: 5b65fd2135832b867310d231d5564cb88ac8c920
Patch-Id: 13235324e301ece04470a8f4ee71a86eca848c16
Reviewed-At: 2026-11-27T11:12:33Z
Model: claude-haiku-5-5
Cost: $0.0105 USD, 1 call(s), 43.4s
Diff: 52788 bytes, 17 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=Gate consolidation in CI tooling; the commit says no customer-facing change.
Dropped: 0
Body-Sig: feda1b58211c0647

## Findings

### f4d3fe2b.1 [medium] scripts/gates/check-tutorial-commands.ts:317
Anchor: in-diff
Claim: The new --selftest covers only detection cases; none of the anti-vacuity floors (empty storyboard dir at line 269, zero runnable commands at line 282, zero prompting commands derived at line 299, no tutorial scripts at line 306) is exercised, so a change that makes any of them return clean on an empty scan would still pass the selftest, even though the commit says each rule keeps its floor.
Class: missing-control-test
Resolution: open

### f4d3fe2b.2 [low] scripts/gates/check-tutorial-commands.ts:1
Anchor: in-diff
Claim: The `#!/usr/bin/env node` shebang was removed from the file, so the script can no longer be executed directly; it only works through tsx, which package.json already uses.
Class: other
Resolution: open
