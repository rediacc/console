# Review e6b725bf: docs(design): the design specs name the per-network runtime paths, and private/renet moves to its docs commit

Commit: e6b725bfe9cde67a7fa69fc2ef94deeb89e7562e
Repo: console
Branch: 1023-1
Parent: 094d39b1c454ff771e1507b32fc354b339c43acf
Patch-Id: dcd06904bdad7bd049ab819e303c4cf127b73cfe
Reviewed-At: 2026-10-23T19:25:58Z
Model: claude-haiku-5-5
Cost: $0.0052 USD, 1 call(s), 24.2s
Diff: 21568 bytes, 5 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=docs why=Docs-only path corrections plus a private/renet submodule pointer bump; no user-facing behaviour change.
Dropped: 0
Body-Sig: 5de92a22b0c39954

## Findings

### e6b725bf.1 [low] docs/design/01-current-architecture.md:31
Anchor: in-diff
Claim: The socket path is written as /run/rediacc/net-<id>/docker-<id>.sock, while spec/02 and spec/05 in the same commit use /var/run/rediacc/...; both resolve to the same place on Linux, but a reader comparing the docs sees two spellings for one path.
Resolution: open

### e6b725bf.2 [low] docs/design/spec/04-config-schema-v3.md:547
Anchor: in-diff
Claim: The k8s Secret mount path is now given only as 'the secrets/ directory under /var/run/rediacc', so the full in-pod mount path the old line stated explicitly is no longer written out anywhere in this bullet and a reader cannot copy it directly.
Resolution: open
