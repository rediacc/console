# Review bf3a507b: fix(ci): the plan-implementation clock finding is keyed per plan, so a carry names plans

Commit: bf3a507b51edbb8de81fc48d6cbd90e3fe604ab7
Repo: console
Branch: 1008-1
Parent: e0284f739a5d05673c8fc3389030b110e7a41427
Patch-Id: 2121398daee994dd089e0814e893e0cdc2102e44
Reviewed-At: 2026-10-13T10:11:28Z
Model: claude-haiku-5-5
Cost: $0.0062 USD, 1 call(s), 34.8s
Diff: 19782 bytes, 7 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug,ci why=CI gate keying fix only; no user-facing product change.
Dropped: 0
Body-Sig: c5306ede6aac4ff2

## Findings

### bf3a507b.1 [medium] .ci/config/carried-reds.json:50
Anchor: in-diff
Claim: The reason says 'Each key names one plan, so a plan whose last box closes leaves this list', but the commit message states a carried plan that closes leaves a stale key in the carry until the line is deleted, so the reason misdescribes the carry's behaviour.
Resolution: open

### bf3a507b.2 [low] .ci/rediacc_ci/tests/test_quality_plan_implementation.py:1
Anchor: in-diff
Claim: No case uses a plan path containing digits, yet the new keys embed the path and the docstring says log.finding_key masks digits; the six real carried paths (e.g. PLAN-k3s-137-...) are only checked by the gate run, not by a pytest case.
Resolution: open
