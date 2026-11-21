# Review d2b234e9: docs: stop sending the R2 CORS check and the www Worker comments to the retired edge.rediacc.com

Commit: d2b234e96ddae35afdb8ee42e65feae505c18a4f
Repo: console
Branch: 1104-1
Parent: 77dac0c2b078fb8c82ae62b35672611955f87626
Patch-Id: 67f63f12c88cd1e9f14bae664eae7883c99dfe70
Reviewed-At: 2026-11-14T10:49:15Z
Model: claude-haiku-5-5
Cost: $0.0019 USD, 1 call(s), 10.3s
Diff: 6166 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=docs why=Doc and comment edits only; no user-facing behaviour change.
Dropped: 0
Body-Sig: 0e48714f8fe982a2

## Findings

### d2b234e9.1 [low] workers/www/src/index.ts:16
Anchor: in-diff
Claim: The rewritten ACCOUNT comment still says the binding is 'Bound on stable + edge wrangler configs', although the commit says the edge worker was retired and workers/www/wrangler.toml now serves only www, so the comment still describes a config that no longer exists.
Class: doc-contradicts-code
Resolution: fixed 1b2beddca94cdf1a4bf75f144bc31f0588a3d3fb | d778be9d 2026-11-14T11:23:37Z
