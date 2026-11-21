# Review 0ebbba45: test(hooks): serialize the plan blob prefetch and quote its outcome when plan-renders fails

Commit: 0ebbba453bc422da816c7db2d49e5ccfd81be20e
Repo: console
Branch: 1104-1
Parent: c48a75700453336cf3642ab8f615fe69c4302884
Patch-Id: 269b2e79b3a1b6dbbe20ace111258e20f9d26075
Reviewed-At: 2026-11-14T17:13:55Z
Model: claude-haiku-5-5
Cost: $0.0040 USD, 1 call(s), 26.4s
Diff: 7911 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug why=Test-only change in the hooks test suite fixing a CI gate failure; no user-facing behaviour changes.
Dropped: 0
Body-Sig: 6c947f9b7cd54a86

## Findings

### 0ebbba45.1 [medium] .claude/rediacc_hooks/tests/test_githook_generated_artifacts.py:455
Anchor: in-diff
Claim: _missing_blobs never checks the rc of `git cat-file --batch-check`; if that command fails, stdout is empty, the function returns [], and _prefetch_main_plans returns 0 with nothing recorded in PREFETCH_REPORT, so the plan-renders message reads 'no failure recorded' for the very failure this commit set out to surface.
Class: swallowed-error
Resolution: fixed e8f2d68ee3bae305a5f468ef3a859ceb3a88e56f | d778be9d 2026-11-14T17:47:14Z

### 0ebbba45.2 [medium] .claude/rediacc_hooks/tests/test_githook_generated_artifacts.py:480
Anchor: in-diff
Claim: The new lock, re-check under lock, fetch-failure, timeout and still-absent report branches are not exercised by any test: the local run only reaches the early `if not _missing_blobs(oids): return 0` return, so a regression in the locked path would pass locally and only show up (if at all) in the next blob:none CI run.
Class: missing-control-test
Resolution: fixed e8f2d68ee3bae305a5f468ef3a859ceb3a88e56f | d778be9d 2026-11-14T17:47:14Z

### 0ebbba45.3 [low] .claude/rediacc_hooks/tests/test_githook_generated_artifacts.py:476
Anchor: in-diff
Claim: tempfile.gettempdir() is used for the lock file with no fallback; if the temp directory is not writable, open() raises inside the module-scoped fixture and every case errors, with no PREFETCH_REPORT entry explaining it.
Class: other
Resolution: fixed e8f2d68ee3bae305a5f468ef3a859ceb3a88e56f | d778be9d 2026-11-14T17:47:14Z
