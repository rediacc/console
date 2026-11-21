# Review 38bbb9d6: chore(ci): repin pr.one-plan-per-pr to the one-plan-per-PR canonical span

Commit: 38bbb9d6fcfed8af45acf9ade59b899a05e2c26b
Repo: console
Branch: 1121-1
Parent: dfbc82258d50e94cfa46b2108c2141bd62255fbb
Patch-Id: c61934bfa70dcab2093961448e0f5ff949c5441c
Reviewed-At: 2026-11-21T09:58:15Z
Model: claude-haiku-5-5
Cost: $0.0012 USD, 1 call(s), 7.2s
Diff: 572 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=Only a gate pin in CI config changes; no user-facing behaviour.
Dropped: 0
Body-Sig: c25ee50a15bda339

## Findings

### 38bbb9d6.1 [medium] .ci/config/scope-mirrors.json:111
Anchor: in-diff
Claim: The new pin 2fdfc650681f was computed on a scratch copy with the CLAUDE.md patch and mirror anchor removals applied, but this commit touches only scope-mirrors.json (STAT: 1 file changed), so on the committed tree the pinned span no longer matches the CLAUDE.md text and the scope-mirror gate will fail there.
Class: other
Resolution: open
