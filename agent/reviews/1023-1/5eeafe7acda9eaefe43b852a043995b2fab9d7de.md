# Review 5eeafe7a: feat(console): web job poll loop and reducer over the Design 4 poll body (PLAN-detached-jobs C6 prep for J7)

Commit: 5eeafe7acda9eaefe43b852a043995b2fab9d7de
Repo: private/account
Branch: 1023-1
Parent: d124c0d68d53dd19a009e357baba73e7fef97f79
Patch-Id: 3ed6f679b49b03467c3e9f88f0085210cf30e96e
Reviewed-At: 2026-10-29T13:48:37Z
Model: claude-haiku-5-5
Cost: $0.0036 USD, 1 call(s), 30.4s
Diff: 11976 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=feature why=New poll loop and reducer that is not wired into any user-facing path yet (J7 wires it), so no user-visible change.
Dropped: 0
Body-Sig: 5b46b3aa248816a9

## Findings

### 5eeafe7a.1 [low] web/src/lib/job-poll.ts:142
Anchor: in-diff
Claim: turn() awaits opts.sleep(delayMs, opts.signal) with no try/catch, and the injected sleep type is Promise<void>, so if a real sleep rejects on abort, runJobPoll rejects instead of returning phase 'stopped' when unmount happens during a backoff wait. No test covers a rejecting sleep (the abort test's mock resolves), so this path is unverified.
Resolution: fixed 911a89dc899f62e1af864a74f197d03081bd8283 | d778be9d 2026-10-29T14:32:24Z
