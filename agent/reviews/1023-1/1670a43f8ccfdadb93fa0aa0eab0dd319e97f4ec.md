# Review 1670a43f: fix(account): executor session ids are bounded, grants capped per executor, console comments name the re-grant code, and the review test gaps closed

Commit: 1670a43f8ccfdadb93fa0aa0eab0dd319e97f4ec
Repo: private/account
Branch: 1023-1
Parent: 257625a82e188c404df23dc45a64924921bbe572
Patch-Id: 7de5aee24005df478229bbfe67b29bcde3377cf0
Reviewed-At: 2026-10-26T08:27:16Z
Model: claude-haiku-5-5
Cost: $0.0071 USD, 1 call(s), 42.0s
Diff: 26363 bytes, 12 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug,docs why=Tightens executor route input validation and adds a grant cap (a fix); no new capability is exposed to users.
Dropped: 0
Body-Sig: 5b3e36a4cc54a209

## Findings

### 1670a43f.1 [medium] src/services/config.service.ts:2322
Anchor: in-diff
Claim: The per-executor cap counts every configExecutorGrants row for the principal, because the where clause filters only on store and executorTokenId and not on expiresAt, so expired grants count against the 1000 'live grants' limit and can lock an executor out (new grants refused) even when it holds no live grant, unless some other code purges expired rows (not visible in this diff).
Resolution: open

### 1670a43f.2 [medium] src/services/config.service.ts:2330
Anchor: in-diff
Claim: The new EXECUTOR_GRANTS_PER_PRINCIPAL_MAX refusal path (ExecutorSessionDeniedError 'too many live session grants') has no test in this commit, so a regression in the count or the threshold would pass the suite unnoticed.
Resolution: open

### 1670a43f.3 [medium] tests/integration/license-renew-rate-limit.test.ts:33
Anchor: in-diff
Claim: The 'lets a normal renewal cadence through' assertion changed from exactly 500 to not.toBe(429), so it now passes for any non-429 status, including a 404 from a broken route, and no longer shows the request reached the handler.
Resolution: open

### 1670a43f.4 [low] src/middleware/rate-limit.ts:160
Anchor: in-diff
Claim: When the map is at the cap and many live keys have suppressed > 0, the victim scan walks all ~10,000 entries on every insert of a new key, adding an O(n) cost to each logged event during a flood of distinct keys.
Resolution: open

### 1670a43f.5 [low] tests/integration/rotation-rdc-config.test.ts:29
Anchor: in-diff
Claim: sources() now reads every non-.json file as text, including Markdown and binary files, so any non-comment prose or binary content mentioning ./rdc.sh will be flagged as a violation by the gate, a scope the test was not written for.
Resolution: open
