# Review 320c0dbd: fix(account): review findings CL-V-ACC-SRC-2, org run visibility, executor chain rotation, records truncation flag

Commit: 320c0dbdb0d5ee8b9c2caf00009e8d2ca4cffe8f
Repo: private/account
Branch: 1121-1
Parent: fac9519327b99efd2e10552fa116274120551591
Patch-Id: 737ccebd16443fa89303a1509113ca470983d19c
Reviewed-At: 2026-11-27T01:01:01Z
Model: claude-haiku-5-5
Cost: $0.0043 USD, 1 call(s), 20.7s
Diff: 14325 bytes, 7 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes legacy executor chain revocation, org run visibility leak, grant TTL cut, and truncation flag; no new capability.
Dropped: 0
Body-Sig: 95266d73aa847786

## Findings

### 320c0dbd.1 [low] src/services/config.service.ts:1723
Anchor: in-diff
Claim: The grant-window slide runs before the org passphrase is decrypted, so a rotation that then returns decryption_failed (line 1742) has still extended the grant's expiresAt, although the commit says a rotation is a use.
Class: other
Resolution: fixed 035f13218b20064db33646072148ada3bd966692 | d778be9d 2026-11-27T01:16:32Z
