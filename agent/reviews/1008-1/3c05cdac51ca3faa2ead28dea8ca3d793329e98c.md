# Review 3c05cdac: fix(sandbox-gateway): client datastore, user and network ID are checked against machine-side sources

Commit: 3c05cdac51ca3faa2ead28dea8ca3d793329e98c
Repo: private/renet
Branch: 1008-1
Parent: c359aa4ebf18ded5d039cddae1087339678d0179
Patch-Id: 474f5cf48c146bffa0670b2720833749dbb50c6f
Reviewed-At: 2026-10-14T12:39:56Z
Model: claude-haiku-5-5
Cost: $0.0121 USD, 1 call(s), 63.8s
Diff: 38051 bytes, 6 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Security fix to a hidden SSH gateway: client-supplied datastore, user, network ID and working dir are now refused on mismatch; no new user-facing capability.
Dropped: 0
Body-Sig: 929c36cb33d60afe

## Findings

### 3c05cdac.1 [medium] cmd/renet/sandbox_gateway.go:304
Anchor: in-diff
Claim: mirrorNetworkID returns 0 on any os.ReadFile error, including permission denied for the SSH gateway user, so when the state mirror is unreadable the mirror-equality check and the omitted-variable ID default both vanish silently and the client's REDIACC_NETWORK_ID is accepted unchecked.
Resolution: open

### 3c05cdac.2 [medium] cmd/renet/sandbox_gateway.go:291
Anchor: in-diff
Claim: For a key line without --guid, resolveGatewayNetworkID skips the mirror (guard at line 273), so a client-sent positive ID passes whenever no docker unit serves it (owner == ""); this contradicts the commit's claim that omitting the variable no longer drops eBPF confinement and that the ID must match the mirror when one exists.
Resolution: open
