# Review ecddc2be: chore(cmd): nolint markers leave cmd/renet, part 2

Commit: ecddc2bebf6128a0c27230a8bb5d22a7e1d13efc
Repo: private/renet
Branch: 1008-1
Parent: e77c56b943546e7682055cd22e6e4ca7f50bf985
Patch-Id: c8ca4a54f0374914e2ae50ab9c791f961e787e9d
Reviewed-At: 2026-10-13T05:25:04Z
Model: claude-haiku-5-5
Cost: $0.0036 USD, 1 call(s), 16.4s
Diff: 17996 bytes, 11 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=Lint-suppression comment removal only; no runtime or API change, so no user-facing release.
Dropped: 0
Body-Sig: 5ee1d7d537613811

## Findings

### ecddc2be.1 [low] cmd/renet/sandbox_gateway.go:138
Anchor: in-diff
Claim: The removed gosec comment was the only in-code record of why the rcfile os.Stat path is trusted (sandboxDir from datastore plus repoName from the authorized_keys command= entry). After this commit that trust reasoning exists nowhere in the code, so it survives only if the later exclusion-rule unit records it.
Resolution: fixed 716605539b35bdc0a51eabdaf11ee35f4e5fb2c1 | d778be9d 2026-10-13T05:50:40Z
