# Review 4a6fafcf: fix(cli,e2e): empty range flags refuse, a failed machine delete keeps its access bindings, and the token vault carries strings only

Commit: 4a6fafcfba90d5dfd08e3dedd50c1327a1bf08e4
Repo: console
Branch: 1023-1
Parent: 84fa85425f464354b55844eff69b64c63c6f2fb7
Patch-Id: 1c928d80cb4f89ab274f2a813ff9ce825c0ace14
Reviewed-At: 2026-10-28T13:19:55Z
Model: claude-haiku-5-5
Cost: $0.0062 USD, 1 call(s), 52.4s
Diff: 16916 bytes, 8 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes CLI handling of empty range flags and a rollback gap in machine removal; the new refusal is a bug fix with no new capability.
Dropped: 0
Body-Sig: 9d1f28f9e0bcfc50

## Findings

### 4a6fafcf.1 [medium] packages/cli/src/services/config/config-resources.ts:272
Anchor: in-diff
Claim: If the rollback updateAccess call itself throws, its error replaces the setMachines error in the catch, so the user sees an access-write failure while the machine stays with its bindings already dropped, contrary to the comment on line 271 that says its bindings come back.
Resolution: open

### 4a6fafcf.2 [low] packages/cli/src/services/__tests__/config-resources.test.ts:156
Anchor: in-diff
Claim: The updateAccess mock calls the edit but never applies its result to mockAccess, so the test cannot show that the restore reinstates the stored bindings; it only checks the value passed to the second edit.
Resolution: open

### 4a6fafcf.3 [low] packages/cli/src/services/__tests__/config-resources.test.ts:163
Anchor: in-diff
Claim: The assertion expect(mockMachines).toHaveProperty('m3') passes even without the fix, because removeMachine deletes from the spread copy returned by getMachines, so this line adds no coverage of the rollback.
Resolution: open

### 4a6fafcf.4 [low] packages/cli/src/commands/config-access.ts:53
Anchor: in-diff
Claim: The rangesFromOptions doc comment still says it returns undefined when no range flag was given and does not mention that a given but empty --ipv4 or --ipv6 now throws, so a caller reading the doc would not expect that error.
Resolution: open
