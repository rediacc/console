# Review 0bfa82fd: feat(shared): add feedback fingerprint, scrubText and wire schemas

Commit: 0bfa82fdf4dcbb0cf23160f2a33c8fb7dc83ee56
Repo: console
Branch: 1104-1
Parent: b0fb4096f70765c78bd85936d911f79761c69e18
Patch-Id: 18b7bac25b8db2b97244ee2dca8988e6b98fe99f
Reviewed-At: 2026-11-19T02:15:05Z
Model: claude-haiku-5-5
Cost: $0.0078 USD, 1 call(s), 48.8s
Diff: 15557 bytes, 8 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=feature why=Internal shared package: new feedback helpers and schemas with no user-facing change in this commit.
Dropped: 0
Body-Sig: 3025ed74dab43d4d

## Findings

### 0bfa82fd.1 [medium] packages/shared/src/feedback/fingerprint.ts:2
Anchor: in-diff
Claim: The doc comment says the same failure on different machines collapses to one id, but normalizeError does not strip hostnames or other machine-specific names, so an error that differs only by host (for example 'ssh failed for box.rediacc.io' vs 'nas.local') yields different fingerprints.
Class: doc-contradicts-code
Resolution: fixed 71610e8020016bd1c35a0a1dd31cf82df206a0fb | d778be9d 2026-11-19T02:30:17Z

### 0bfa82fd.2 [low] packages/shared/src/feedback/schema.ts:58
Anchor: in-diff
Claim: The same 'fingerprint' field is 64 hex chars in feedbackSubmitResponseSchema (line 50) but 12 hex chars in feedbackListItemSchema, so a client parsing a list item that carries the full fingerprint would fail validation; the contract difference is undocumented.
Class: other
Resolution: fixed 71610e8020016bd1c35a0a1dd31cf82df206a0fb | d778be9d 2026-11-19T02:30:17Z

### 0bfa82fd.3 [low] packages/shared/src/feedback/__tests__/schema.test.ts:28
Anchor: in-diff
Claim: The size-cap test list omits cliVersion, os and arch from FEEDBACK_LIMITS, so their max() caps are never exercised and a regression there would not fail the suite.
Class: missing-control-test
Resolution: fixed 71610e8020016bd1c35a0a1dd31cf82df206a0fb | d778be9d 2026-11-19T02:30:18Z

### 0bfa82fd.4 [low] packages/shared/src/feedback/fingerprint.ts:9
Anchor: in-diff
Claim: The IPV6 pattern matches clock-style times with two colons (for example '12:30:45' becomes '<ip>') while '12:30' becomes '<n>:<n>', so the same kind of text normalises inconsistently and distinct messages can collide.
Class: other
Resolution: fixed 71610e8020016bd1c35a0a1dd31cf82df206a0fb | d778be9d 2026-11-19T02:30:18Z

### 0bfa82fd.5 [low] packages/shared/src/feedback/scrub.ts:19
Anchor: in-diff
Claim: The unquoted KEY_VALUE value stops at whitespace, so for an input such as 'password=hunter 2' only 'hunter' is redacted and the trailing ' 2' remains in the output.
Class: other
Resolution: not-a-bug | packages/shared/src/feedback/scrub.ts:19 unquoted values end at whitespace by convention; quoted values handled by the quote alternatives on the same line | d778be9d 2026-11-19T02:26:36Z
