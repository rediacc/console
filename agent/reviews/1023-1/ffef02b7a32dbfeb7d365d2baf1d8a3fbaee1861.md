# Review ffef02b7: fix(ci): the kept clone fetches HEAD without recursing into submodules

Commit: ffef02b7a32dbfeb7d365d2baf1d8a3fbaee1861
Repo: console
Branch: 1023-1
Parent: d25a7d5eb8e24198dd4c94dcf7ac4a997389ebb6
Patch-Id: 8d72afbd3d15da58d520032240d80fcc40b4022a
Reviewed-At: 2026-11-02T14:06:23Z
Model: claude-haiku-5-5
Cost: $0.0025 USD, 1 call(s), 17.0s
Diff: 5020 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug,ci why=Internal CI-runner fix in scripts/ci-runner; no user-facing product change.
Dropped: 0
Body-Sig: fa38fd91f0ed9d68

## Findings

### ffef02b7.1 [medium] scripts/ci-runner/quick-clone.ts:325
Anchor: in-diff
Claim: trackedAt skips any gitlink whose submodule directory lacks a .git entry, and the new emptiness guard only fires when the whole result is empty, so if the submodules were not populated (now possible because the fetch passes --no-recurse-submodules) the enumeration silently drops those paths while the root paths keep it non-empty.
Resolution: open

### ffef02b7.2 [medium] scripts/ci-runner/quick-clone.ts:497
Anchor: in-diff
Claim: The fetch now passes --no-recurse-submodules, which changes what the kept clone receives, and no test in this diff covers that behaviour; the commit defers proof to a later chain run.
Resolution: open

### ffef02b7.3 [low] scripts/ci-runner/run.ts:4348
Anchor: in-diff
Claim: The guarded failed list is fixed, but the same message still prints receipt.exitCode unguarded, so an absent exitCode renders as the text 'exitCode undefined' in the RED message.
Resolution: open
