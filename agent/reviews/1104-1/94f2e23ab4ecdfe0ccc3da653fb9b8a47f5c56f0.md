# Review 94f2e23a: fix(plans): R4 carries a rebase-merged done= to its landed copy

Commit: 94f2e23ab4ecdfe0ccc3da653fb9b8a47f5c56f0
Repo: console
Branch: 1104-1
Parent: 147ba8f60db35017d76dfd1b0ff7226c92aeb459
Patch-Id: a90e506f4604a9274249c6527911c704ad62ed0e
Reviewed-At: 2026-11-20T12:38:31Z
Model: claude-haiku-5-5
Cost: $0.0056 USD, 1 call(s), 37.5s
Diff: 8094 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes R4 refusing rebase-merged done= shas; internal check and hook only, no new user-facing capability.
Dropped: 0
Body-Sig: 1f36acc3ed7dc07a

## Findings

### 94f2e23a.1 [medium] .claude/hooks/stop/wl_planrec.py:323
Anchor: in-diff
Claim: resolve_done's ok branch returns resolve's second value as the full sha, but no test in this diff calls resolve_done on a token that resolves directly; the only resolve_done assertions exercise the successor path, so a wrong success value from resolve would go unnoticed.
Class: missing-control-test
Resolution: fixed f9d4291d638d0ac33ae6f4c7684ce9b94d86a354 | d778be9d 2026-11-20T12:40:46Z

### 94f2e23a.2 [low] .claude/hooks/stop/wl_planrec.py:307
Anchor: in-diff
Claim: _DONE_SUCCESSOR is keyed only by root and never invalidated, so a long-lived process that advances HEAD keeps the first map and refuses later landed copies (fails closed, but stale).
Class: other
Resolution: fixed f9d4291d638d0ac33ae6f4c7684ce9b94d86a354 | d778be9d 2026-11-20T12:40:46Z

### 94f2e23a.3 [low] .claude/hooks/stop/wl_planrec.py:313
Anchor: in-diff
Claim: When HEAD~3000 does not exist, the base falls back to the last of the root commits from rev-list, which in multi-root history is arbitrary, and the root itself is excluded by the `<base>..HEAD` window, so a rewritten root commit cannot be carried.
Class: other
Resolution: fixed f9d4291d638d0ac33ae6f4c7684ce9b94d86a354 | d778be9d 2026-11-20T12:40:46Z

### 94f2e23a.4 [low] .ci/scripts/quality/check_plan_record.py:1114
Anchor: in-diff
Claim: After a carry, the 'does not exist at that commit' message still names `done=` rather than the landed sha that was actually checked, so the message points at the wrong commit.
Class: doc-contradicts-code
Resolution: fixed f9d4291d638d0ac33ae6f4c7684ce9b94d86a354 | d778be9d 2026-11-20T12:40:46Z
