# Review 0afaa8e1: fix(drills): the dev API token reaches rdc subscription login on stdin, never argv

Commit: 0afaa8e1ba37fef0a76d1b4541bbb2a57bddda30
Repo: console
Branch: 1008-1
Parent: fbc499c7782489b993932859036c9c435ef535c8
Patch-Id: cd18791f542778e1d44f4d3a341d31886d8b963f
Reviewed-At: 2026-10-15T18:00:40Z
Model: claude-haiku-5-5
Cost: $0.0077 USD, 1 call(s), 45.9s
Diff: 20763 bytes, 9 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug,ci why=Drill and CI test tooling only: moves the login token to stdin, with no user-facing change.
Dropped: 0
Body-Sig: af514006c19c078c

## Findings

### 0afaa8e1.1 [medium] .ci/rediacc_ci/drills/backup.py:1082
Anchor: in-diff
Claim: Applied without the CLI half (part B), `rdc subscription login --token -` treats `-` as the literal token, so login fails and `setup_run` aborts the backup drill with exit 2. The message says the commit 'applies on its own', which contradicts this; the dependency is only stated in the message, not enforced.
Resolution: open

### 0afaa8e1.2 [low] .ci/rediacc_ci/tests/test_drills_argv_secrets.py:133
Anchor: in-diff
Claim: `assert "abc" not in d.last_cmd` cannot fail: `last_cmd` is built only from argv, and the argv here does not contain "abc", so the test does not check that stdin_text is kept out of `last_cmd`, despite its name saying it does.
Resolution: open
