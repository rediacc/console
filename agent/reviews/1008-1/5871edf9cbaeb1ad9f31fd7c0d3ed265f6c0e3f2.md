# Review 5871edf9: fix(ci): the argv taint, the run_stop walk and the vitest workspace scan each cover the spellings they claim

Commit: 5871edf9cbaeb1ad9f31fd7c0d3ed265f6c0e3f2
Repo: console
Branch: 1008-1
Parent: ea7385266d83a039117787c725da8110f71ebbb9
Patch-Id: 004d364c69cf69d86e99bec606ce7f78e547dc8a
Reviewed-At: 2026-10-14T19:32:57Z
Model: claude-haiku-5-5
Cost: $0.0079 USD, 1 call(s), 52.7s
Diff: 14660 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug,ci why=CI test-tooling fix only; no user-facing product change.
Dropped: 0
Body-Sig: 2dc6e25ed88afc06

## Findings

### 5871edf9.1 [high] .ci/rediacc_ci/tests/test_vitest_cache_isolation.py:48
Anchor: in-diff
Claim: The new lookahead `(?![\w./-])` also rejects `vitest` followed by '/', so a script that runs vitest by path, such as `node node_modules/vitest/vitest.mjs run`, no longer matches and runs_vitest returns False. The workspace is then skipped by the config and cache-isolation checks, which can no longer catch the shared-cache bug for it. The old pattern matched this spelling.
Resolution: fixed 61e6bead075d0b5b7d05f17e0be9978b622bb051 | d778be9d 2026-10-14T19:51:43Z

### 5871edf9.2 [low] .ci/rediacc_ci/tests/gates/test_gate_shrink_only_composition.py:140
Anchor: in-diff
Claim: The method-on-tainted-receiver rule does not cover a tainted argv passed as an argument to a method on a constant, such as `" ".join(sys.argv)`, so an assert on that joined string is still treated as an output check and skipped. This is a gap the commit does not claim to close.
Resolution: fixed 61e6bead075d0b5b7d05f17e0be9978b622bb051 | d778be9d 2026-10-14T19:51:43Z
