# Review eb0426ea: fix(ci): quick-clone carriedOnly reads carried-reds.json as the push guard now does (R3 follow-up)

Commit: eb0426eaff4847c3be9ef2fb3eae1ba689dab3ed
Repo: console
Branch: 1121-1
Parent: 7de2a5ffd96bc6942197a64b21c6384250b535de
Patch-Id: bbaba6ddea198db561ef976be734a44b9daacfc0
Reviewed-At: 2026-11-28T13:52:32Z
Model: claude-haiku-5-5
Cost: $0.0052 USD, 1 call(s), 30.4s
Diff: 12848 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug,ci why=Internal ci:quick tooling fix; the commit says no user-facing change.
Dropped: 0
Body-Sig: cd4bf904409c3aa7

## Findings

### eb0426ea.1 [medium] scripts/ci-runner/quick-clone.ts:874
Anchor: in-diff
Claim: readCarry drops a pattern entry with a reason under 80 characters (`if (reason.length < 80) continue;`) before its `expires` reaches the `expires < today` check in carriedOnly, so an expired under-bar pattern does not make carriedOnly refuse, although carriedOnly's doc says it refuses on a pattern past its expiry anywhere in the file.
Class: doc-contradicts-code
Resolution: open

### eb0426ea.2 [medium] scripts/ci-runner/quick-clone.ts:922
Anchor: in-diff
Claim: When a failed gate's receipt records an empty key list (`[]`, not null), `keys.every(...)` returns true, so a keyed carry or a pattern-only carry admits that red; the old Set-size equality refused it, and the commit message says a keyless red under a keyed carry is still refused. This holds only if a receipt can hold an empty list for a failed gate, which the diff does not show.
Class: other
Resolution: open
