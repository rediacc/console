# Review 07bc0bfb: fix(cli): the rebind code program settles with a grandchild on the pipe, and a refused upload leaves no pin

Commit: 07bc0bfbf014bf6bd3de628fcdad7a79cb3da001
Repo: console
Branch: 1121-1
Parent: cd54ad27b58d067a381727b4a2b8f57f2a56ece0
Patch-Id: b855997d8dd883538530b3d443bf5622e1b63023
Reviewed-At: 2026-11-24T11:09:05Z
Model: claude-haiku-5-5
Cost: $0.0042 USD, 1 call(s), 24.4s
Diff: 13118 bytes, 6 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes the rebind code-program hang on a grandchild holding pipes and moves the upload guard ahead of the pin; no new user capability.
Dropped: 0
Body-Sig: 8a1fb260e13bba23

## Findings

### 07bc0bfb.1 [medium] packages/cli/src/services/preview/slot-ops.ts:20
Anchor: in-diff
Claim: The doc comment says a failure 'leaves the machine as it was' and, in the same sentence block, that a failed record write leaves the pin marker on the slot; the first clause is now false for that failure path, so a reader is told two contradictory things.
Class: doc-contradicts-code
Resolution: open
