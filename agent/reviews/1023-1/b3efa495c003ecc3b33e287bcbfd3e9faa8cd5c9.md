# Review b3efa495: fix(pins): a toolchain bump that rewrites a package.json runs the lockfile pass in that directory

Commit: b3efa495c003ecc3b33e287bcbfd3e9faa8cd5c9
Repo: console
Branch: 1023-1
Parent: 2cbbcd0af83daac40e19d1dff9bb55e57b564553
Patch-Id: 4e845d15d683ce8cd71ebe05294162116bc0dc79
Reviewed-At: 2026-10-29T04:49:43Z
Model: claude-haiku-5-5
Cost: $0.0031 USD, 1 call(s), 22.4s
Diff: 10455 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes lockfile drift when a toolchain bump rewrites package.json; no new user-facing capability.
Dropped: 0
Body-Sig: 3677d2bc96fdd1eb

## Findings

### b3efa495.1 [low] scripts/lib/pins/drivers/toolchain.ts:219
Anchor: in-diff
Claim: pinnedNpm(ctx.root) runs inside the new loop, so toolchain:wrangler planning now throws PlanRefused when .devcontainer/toolchain.env lacks NPM_VERSION, where it previously planned without that file; the commit does not mention this behaviour change.
Resolution: open

### b3efa495.2 [low] scripts/lib/pins/drivers/toolchain.ts:221
Anchor: in-diff
Claim: The loop does not check that a package-lock.json exists beside a package.json site, so a future non-npm entry whose directory has no lockfile would get a newly created lockfile declared in writes, with no test covering that case.
Resolution: open
