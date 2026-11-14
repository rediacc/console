# Review 01cb26e5: test(e2e): suite 23 gains migrate ordering, failed-target and gc-race cases

Commit: 01cb26e5d4caba1429b961bececdb2bb0a61db0a
Repo: console
Branch: 1104-1
Parent: d8c6d9a30ccef46ed89a44290928f2b287c38f6e
Patch-Id: a7b1eda98a6fe49e887f2a5abfb8a9dc7753a920
Reviewed-At: 2026-11-05T10:57:33Z
Model: claude-haiku-5-5
Cost: $0.0102 USD, 1 call(s), 99.7s
Diff: 17066 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=Test-only additions and an allowlist comment reword in the e2e gate; no user-facing behaviour changes.
Dropped: 0
Body-Sig: 0a23af75d0913f24

## Findings

### 01cb26e5.1 [medium] packages/e2e-tests/tests/23-cli-migrate-routing.test.ts:348
Anchor: in-diff
Claim: Test 10's ordering assert compares the source-delete time (watcher polls every 0.1s, offset-corrected by one SSH round trip) against the target up() stamp; if the real gap between target up and source delete is smaller than that clock/poll error, the test can pass or fail spuriously, and the comment's claim that the gap exceeds the error is not established.
Resolution: fixed 6223fde91533d657ab85063e874dfaac753e71a7 | d778be9d 2026-11-05T11:21:26Z

### 01cb26e5.2 [medium] packages/e2e-tests/tests/23-cli-migrate-routing.test.ts:155
Anchor: in-diff
Claim: The afterAll GUID sweep swallows every failure with `.catch(() => undefined)` and the zero-residue check covers only APP, so a failed delete of the new APP_ORDER/APP_FAIL/APP_GC repos or the gc commit leaves residue on the machines with no failing assertion.
Resolution: fixed 6223fde91533d657ab85063e874dfaac753e71a7 | d778be9d 2026-11-05T11:21:26Z

### 01cb26e5.3 [low] packages/e2e-tests/tests/23-cli-migrate-routing.test.ts:390
Anchor: in-diff
Claim: gcRun keeps only stdout lines containing "gc_result"/"gc_summary" and test 12 then matches compact strings such as '"deleted":0'; the file's own comment says renet's logrus output rides stderr, so if the result is on stderr or pretty-printed, the skip/delete assertions fail for formatting reasons.
Resolution: fixed 6223fde91533d657ab85063e874dfaac753e71a7 | d778be9d 2026-11-05T11:21:27Z

### 01cb26e5.4 [low] packages/e2e-tests/tests/23-cli-migrate-routing.test.ts:358
Anchor: in-diff
Claim: Test 11 checks only that the w2 hostname is non-empty, not that it differs from machine-11's; if the two VMs share a hostname, the injected up() failure would also match the source, so the 'only the target fails' premise breaks.
Resolution: fixed 6223fde91533d657ab85063e874dfaac753e71a7 | d778be9d 2026-11-05T11:21:27Z

### 01cb26e5.5 [low] packages/e2e-tests/tests/23-cli-migrate-routing.test.ts:333
Anchor: in-diff
Claim: The watcher promise is not awaited on the path where `expect(mig.code)` at line 337 throws, so its remote polling loop of up to 300 seconds keeps running after the test fails.
Resolution: fixed 6223fde91533d657ab85063e874dfaac753e71a7 | d778be9d 2026-11-05T11:21:27Z
