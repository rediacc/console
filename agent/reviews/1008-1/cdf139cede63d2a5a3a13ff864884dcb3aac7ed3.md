# Review cdf139ce: fix(pins): the lock is taken under one rename-installed claim judged by pid and start time, never by age

Commit: cdf139cede63d2a5a3a13ff864884dcb3aac7ed3
Repo: console
Branch: 1008-1
Parent: 1c7f9fdb20239a1889c2aa414b2429c6561a65e4
Patch-Id: 0e2fa6aab80c5612de3b64625f7b4080ff7beecf
Reviewed-At: 2026-10-14T19:20:39Z
Model: claude-haiku-5-5
Cost: $0.0207 USD, 1 call(s), 159.5s
Diff: 26852 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes lock/claim races in the pins transaction; internal script behaviour, no new capability.
Dropped: 0
Body-Sig: dcb640410b4c816c

## Findings

### cdf139ce.1 [medium] scripts/lib/pins/txn.ts:621
Anchor: in-diff
Claim: A claim whose live owner never finishes (for example a SIGSTOPped taker) is never judged dead, so after claimWaitMs every later takeLock returns null as if a run held the lock; the previous ten-second age clearing is gone and no control exercises a stalled claim holder.
Resolution: fixed 01ec37ab9fde3d3f8ca3feada024f52950feb950 | d778be9d 2026-10-14T20:22:49Z

### cdf139ce.2 [low] scripts/lib/pins/txn.ts:626
Anchor: in-diff
Claim: Each dead claim is moved to a `.lock.claim.dead.<hash>` tomb that nothing ever removes (the sweep regex matches only `<pid>` private names), so every crash while claimed leaves a permanent directory, which conflicts with the commit's 'no debris left' verification.
Resolution: fixed 01ec37ab9fde3d3f8ca3feada024f52950feb950 | d778be9d 2026-10-14T20:22:49Z

### cdf139ce.3 [low] scripts/lib/pins/txn.ts:613
Anchor: in-diff
Claim: A non-empty `.lock.claim` with no owner file makes takeLock throw after about 100 ms on every run until someone removes it by hand, and no control covers this path.
Resolution: fixed 01ec37ab9fde3d3f8ca3feada024f52950feb950 | d778be9d 2026-10-14T20:22:49Z

### cdf139ce.4 [low] scripts/lib/pins/txn.ts:638
Anchor: in-diff
Claim: When the put-back of a non-judged claim is refused because a new claim was installed meanwhile, the error is swallowed, so that live claim stays stranded in its tomb and its holder's dropClaim then renames a different claim or throws; the comment above says the put-back 'cannot replace one installed meanwhile' and does not mention this outcome.
Resolution: fixed 01ec37ab9fde3d3f8ca3feada024f52950feb950 | d778be9d 2026-10-14T20:22:50Z

### cdf139ce.5 [low] scripts/lib/pins/txn.ts:585
Anchor: in-diff
Claim: The doc says a stale lock is moved to `.lock.stale.<pid>.<nonce>`, but fillSlot at line 672 uses randomBytes(4), an 8-hex suffix, not the 16-hex nonce used by the private names.
Resolution: fixed 01ec37ab9fde3d3f8ca3feada024f52950feb950 | d778be9d 2026-10-14T20:22:50Z

### cdf139ce.6 [low] scripts/lib/pins/txn-selftest.ts:142
Anchor: in-diff
Claim: The rmSync hook `p === claim && runPeer()` never fires because no code path rmSync's the claim path, and the existsSync hook at line 187 is never invoked either, so these 'one-shot fs hooks' are dead and the peers run only through seams.
Resolution: fixed 01ec37ab9fde3d3f8ca3feada024f52950feb950 | d778be9d 2026-10-14T20:22:50Z
