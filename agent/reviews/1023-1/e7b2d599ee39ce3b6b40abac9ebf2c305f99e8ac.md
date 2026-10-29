# Review e7b2d599: feat(ci): proxy_job_cost and job_latency measure the Durable Object, container and per-command cost of detached jobs (PLAN-detached-jobs J12, J23)

Commit: e7b2d599ee39ce3b6b40abac9ebf2c305f99e8ac
Repo: console
Branch: 1023-1
Parent: abafdbf1f6b1d798cf9801165fed32c8ca425603
Patch-Id: 7c03587edecddb83bc339d9885dd65c59d6a0325
Reviewed-At: 2026-10-29T11:26:07Z
Model: claude-haiku-5-5
Cost: $0.0081 USD, 1 call(s), 67.3s
Diff: 26956 bytes, 6 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=feature why=Adds internal CI ops tooling (two maintainer commands) and regenerated doc counts; no product or user-facing behaviour changes.
Dropped: 0
Body-Sig: b6f0f2554f953dcb

## Findings

### e7b2d599.1 [medium] .ci/rediacc_ci/ops/proxy_job_cost.py:13
Anchor: in-diff
Claim: The OUTPUT docstring says the container line is `container active_seconds=X apps=N scope=all|listed`, but run() prints `container active_seconds=%.2f rows=%d scope=%s`, so an operator parsing the documented `apps=N` field gets no match.
Resolution: open

### e7b2d599.2 [low] .ci/rediacc_ci/ops/job_latency.py:81
Anchor: in-diff
Claim: measure() collects rediacc.job.start_latency_ms values from every run's output unconditionally, while the docstring says collection happens under --debug; without --debug, a start_latency line is printed whenever rdc emits the attribute.
Resolution: open

### e7b2d599.3 [low] .ci/rediacc_ci/ops/job_latency.py:123
Anchor: in-diff
Claim: compare() checks only that start_latency exists in both result files, not its p50/p95/max keys, so a hand-edited file missing one of them raises an uncaught KeyError (traceback, exit 1) instead of the documented exit 2.
Resolution: open

### e7b2d599.4 [low] .ci/rediacc_ci/ops/job_latency.py:180
Anchor: in-diff
Claim: The --out write is outside the try/except LatencyError block, so an unwritable --out path raises OSError after the numbers are printed, giving a traceback and exit 1 rather than the documented exit codes.
Resolution: open
