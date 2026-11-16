# Review 0d0ae336: fix(enterprise): a resumed add redeploys drifted configs and refuses a stop it cannot make

Commit: 0d0ae336adbf423c6eb68ecedd8d6895fc3b4f1e
Repo: console
Branch: 1104-1
Parent: 01d9871f7c39c7108de4eee179c8f7e012aef2e6
Patch-Id: 90d2529a1e90da6cc410af6c02c85d7cea0a0310
Reviewed-At: 2026-11-15T23:37:21Z
Model: claude-haiku-5-5
Cost: $0.0087 USD, 1 call(s), 58.1s
Diff: 20176 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes resumed enterprise adds that skipped config drift and let a finished-step stop_after exit 0; no user-facing capability added.
Dropped: 0
Body-Sig: 4721bb6dd0cc848a

## Findings

### 0d0ae336.1 [medium] .ci/rediacc_ci/enterprise/onboarding.py:367
Anchor: in-diff
Claim: When a resume finds drift and also names a finished step in stop_after (e.g. stop_after="d1"), the run prints "its configs differ ...; configs and deploy run again" and then returns the refusal at line 371 with nothing rerun, so the printed message states a rerun that never happens.
Class: doc-contradicts-code
Resolution: fixed 1c1fa6dcd9fce10e01ee17bd1481c2ffd1934507 | d778be9d 2026-11-16T00:41:58Z

### 0d0ae336.2 [medium] .ci/rediacc_ci/enterprise/onboarding.py:806
Anchor: in-diff
Claim: The configs digest now depends on plan.request.allow_ips, so a resume passed a different --allow-ips than the first add silently reruns configs and deploy with the new list; the module docstring lists only template, config-rule and module changes as drift causes, and no test covers a request-driven digest change.
Class: missing-control-test
Resolution: fixed 1c1fa6dcd9fce10e01ee17bd1481c2ffd1934507 | d778be9d 2026-11-16T00:41:58Z
