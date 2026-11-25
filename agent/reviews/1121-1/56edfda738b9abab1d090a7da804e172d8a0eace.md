# Review 56edfda7: feat(console): /console/ai/chat and /console/ai/test forward to the executor AI routes

Commit: 56edfda738b9abab1d090a7da804e172d8a0eace
Repo: private/account
Branch: 1121-1
Parent: daaf48f48ed69f05fd1ee1202cad7ae49e9c6ec5
Patch-Id: 9525f16fc59ccdac153421fa45e55bccabb1b3a5
Reviewed-At: 2026-11-25T04:33:06Z
Model: claude-haiku-5-5
Cost: $0.0054 USD, 1 call(s), 23.0s
Diff: 21610 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature why=New /console/ai/chat and /console/ai/test routes forwarding to the executor; new capability.
Dropped: 0
Body-Sig: f941895b2699d08f

## Findings

### 56edfda7.1 [medium] src/routes/console-ai.ts:140
Anchor: in-diff
Claim: The commit says a client disconnect aborts the upstream turn via `signal: c.req.raw.signal`, but no test in tests/integration/console-ai.test.ts aborts a request or checks the upstream signal, so a regression that drops the signal would pass the suite.
Class: missing-control-test
Resolution: open

### 56edfda7.2 [low] src/routes/console-ai.ts:102
Anchor: in-diff
Claim: The comment says `opts.forceRateLimit` exists for a test that proves the per-org budget, but no test in this diff forces the limiter or checks the 30-per-minute cap, so the budget is unverified.
Class: missing-control-test
Resolution: open

### 56edfda7.3 [low] src/routes/console-ai.ts:144
Anchor: in-diff
Claim: When the executor returns ok with an empty body, the 502 message says 'The executor rejected the request', which misdescribes a successful response with no body.
Class: other
Resolution: open
