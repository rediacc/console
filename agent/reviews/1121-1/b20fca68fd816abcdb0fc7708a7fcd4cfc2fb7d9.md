# Review b20fca68: feat(account-web): put the AI chat on assistant-ui, use-stick-to-bottom and streamdown

Commit: b20fca68fd816abcdb0fc7708a7fcd4cfc2fb7d9
Repo: private/account
Branch: 1121-1
Parent: 4481ddb2d817805ddabfa3b46420046d1e737955
Patch-Id: b05458e56b6729cfbf458f946ca2586369340c6d
Reviewed-At: 2026-11-26T05:10:40Z
Model: claude-haiku-5-5
Cost: $0.0068 USD, 1 call(s), 39.5s
Diff: 23092 bytes, 6 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature why=Swaps the AI chat message path onto assistant-ui, use-stick-to-bottom and Streamdown, a new user-facing capability.
Dropped: 0
Body-Sig: 43013837ac6bb2dc

## Findings

### b20fca68.1 [medium] web/src/components/ai/chat/scroll-pin.ts:37
Anchor: in-diff
Claim: The escape-reset branch `if (escapedFromLock && !wasEscaped.current) followBottom.current = false;` has no test that fails if it is deleted: the new tests mock use-stick-to-bottom with a fixed boolean and never drive a jump followed by a user scroll-up, so the old 'never overrides a user scroll-up' behaviour test was removed without an equivalent.
Class: missing-control-test
Resolution: not-a-bug | the finding asked for a missing test of the escape-reset branch; it now lives at private/account/web/src/components/ai/chat/__tests__/chat.test.tsx:20 (landed with the CL-X commit, red with the branch deleted) | d778be9d 2026-11-26T10:02:55Z

### b20fca68.2 [low] web/src/components/ai/chat/__tests__/chat.test.tsx:248
Anchor: in-diff
Claim: The test named 'maps a message to the runtime shape and a send intent back to its text' only calls toThreadMessageLike and the appendedText helper; useChatRuntime's onNew (calling onSend, dropping whitespace-only text) and onCancel (calling onStop) are never exercised.
Class: missing-control-test
Resolution: fixed 7b4a2808acd943d60428c2416ff35d99925253a6 | d778be9d 2026-11-26T10:02:35Z

### b20fca68.3 [low] web/src/components/ai/chat/__tests__/chat.test.tsx:200
Anchor: in-diff
Claim: The test titled 'caps the follow target at the streaming reply start and uncaps after a jump' never clicks jump-to-latest; the uncapping is only checked in the separate test at line 213, so the title overstates what this test covers.
Class: doc-contradicts-code
Resolution: fixed 7b4a2808acd943d60428c2416ff35d99925253a6 | d778be9d 2026-11-26T10:02:35Z

### b20fca68.4 [low] web/src/components/ai/chat/__tests__/chat.test.tsx:202
Anchor: in-diff
Claim: The HTMLElement.prototype.offsetTop override is never restored after the test, so it leaks into later tests in the same file (e.g. the streamdown/runtime describe that follows).
Class: seam-not-restored
Resolution: fixed 7b4a2808acd943d60428c2416ff35d99925253a6 | d778be9d 2026-11-26T10:02:35Z
