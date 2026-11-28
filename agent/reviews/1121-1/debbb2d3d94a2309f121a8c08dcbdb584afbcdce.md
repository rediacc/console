# Review debbb2d3: fix(ci): source-rule, unused-export and regions-sync reds from the AI credit landings

Commit: debbb2d3d94a2309f121a8c08dcbdb584afbcdce
Repo: console
Branch: 1121-1
Parent: cd85c34763d069c93c90a35f3247bb5829dd23b3
Patch-Id: ceb15a344e67efa678086536f11d9940377a1d66
Reviewed-At: 2026-11-26T02:44:26Z
Model: claude-haiku-5-5
Cost: $0.0054 USD, 1 call(s), 15.2s
Diff: 28501 bytes, 5 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=Lint and CI gate cleanup plus test and data changes with no user-facing behaviour change.
Dropped: 0
Body-Sig: 75c77b0c157a3812

## Findings

### debbb2d3.1 [medium] knip.jsonc:223
Anchor: in-diff
Claim: The unchanged comment says the vitest plugin supplies the tests and that entry points need no `entry`, but this commit adds an explicit `entry` for workers/account because its vitest plugin is off, so the comment is wrong for that worker.
Class: doc-contradicts-code
Resolution: fixed 423f50045c14a11eed9089d9bb631dc76987e7ed | d778be9d 2026-11-26T15:19:35Z
