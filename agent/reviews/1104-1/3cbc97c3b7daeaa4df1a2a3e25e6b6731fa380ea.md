# Review 3cbc97c3: feat(setup): add the pinned gitlab backup remote to renet, account and elite

Commit: 3cbc97c3b7daeaa4df1a2a3e25e6b6731fa380ea
Repo: console
Branch: 1104-1
Parent: 7cb1253ae5769cb02b81e620ede8ee5fc091ec42
Patch-Id: 49c7d00634709dfb42943d0917a9ad375ef61c54
Reviewed-At: 2026-11-11T09:33:02Z
Model: claude-haiku-5-5
Cost: $0.0048 USD, 1 call(s), 25.1s
Diff: 19099 bytes, 5 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature why=Setup now adds a gitlab backup remote to each pinned submodule, a new capability for users running setup.
Dropped: 0
Body-Sig: 861442195591a965

## Findings

### 3cbc97c3.1 [medium] .ci/rediacc_ci/setup/backup_remotes.py:78
Anchor: in-diff
Claim: If `remote add` succeeds but the following `config --unset-all remote.gitlab.fetch` or `skipFetchAll` step fails, the remote is left with its default fetch refspec. Every later run takes `have == want` and continues silently, so the refspec is never removed and `git fetch gitlab` can write refs/remotes/gitlab/*, which the docstring says cannot happen.
Class: other
Resolution: open

### 3cbc97c3.2 [low] .ci/rediacc_ci/tests/test_setup_backup_remotes.py:1
Anchor: in-diff
Claim: No test exercises the `failed` branch of install (a git command returning non-zero), so the partial-add case above, and the return value of 1 that setup relies on, are untested.
Class: missing-control-test
Resolution: open
