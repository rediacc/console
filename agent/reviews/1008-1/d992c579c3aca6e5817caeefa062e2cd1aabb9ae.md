# Review d992c579: feat(pins): a docker leaf per FROM image, and a newer major red after a 40-day grace

Commit: d992c579c3aca6e5817caeefa062e2cd1aabb9ae
Repo: console
Branch: 1008-1
Parent: dd1d1e937437299333000c293d9a0ff4d2bffa18
Patch-Id: 8f588694a02fd072a1363eede87993b04ddaa289
Reviewed-At: 2026-10-14T21:40:26Z
Model: claude-haiku-5-5
Cost: $0.0126 USD, 1 call(s), 42.4s
Diff: 134893 bytes, 17 files, truncated: yes
Unreviewed: scripts/gates/check-pin-freshness.ts, scripts/lib/pins/drivers/docker.ts, scripts/lib/pins/status.ts, scripts/lib/policy-paths.ts, scripts/lib/suppression-liveness.ts, scripts/pins/pins.ts
Verdict: findings
Attempt: 1
Labels: bump=none kind=feature,ci why=Changes CI gates, pin registry and policy files only; no user-facing product behaviour.
Dropped: 0
Body-Sig: df64fad552cf5c5d

## Findings

### d992c579.1 [medium] scripts/gates/check-docker-image-freshness.ts:648
Anchor: in-diff
Claim: The new green line says every scanned FROM is 'each claimed by a docker leaf', but the count is pins.length, and parsePins (regex at line 189, unchanged) skips any FROM with a flag such as `FROM --platform=$BUILDPLATFORM node:20 AS build`; such a line is neither claimed nor freshness-checked while the gate still prints green, so the claim overstates the coverage.
Resolution: open

### d992c579.2 [low] scripts/gates/check-docker-image-freshness.ts:189
Anchor: in-diff
Claim: parsePins accepts indented FROM lines (`^\s*FROM`), but every leaf match added in pins.json is anchored `^FROM `, so an indented FROM is reported unclaimed and the printed advice to add a leaf with a version site whose match covers the line cannot clear it unless the new match also allows leading whitespace.
Resolution: open
