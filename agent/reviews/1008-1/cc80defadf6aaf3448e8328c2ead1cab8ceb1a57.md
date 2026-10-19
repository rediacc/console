# Review cc80defa: fix: scrub_sentinel's probe refuses the askpass fallback; the awscli plan names every pointer by its full path

Commit: cc80defadf6aaf3448e8328c2ead1cab8ceb1a57
Repo: console
Branch: 1008-1
Parent: 7643fe3e662001d07fcb9444cce1c95e4c0d1478
Patch-Id: 8c4792022d51ff4a36bae6c896091c488ba9baf8
Reviewed-At: 2026-10-19T11:28:59Z
Model: claude-haiku-5-5
Cost: $0.0035 USD, 1 call(s), 16.9s
Diff: 14281 bytes, 4 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug,docs why=Fixes a mid-plan askpass prompt path in the scrub probe (bug); the rest is plan path prose and an agent index row.
Dropped: 0
Body-Sig: dbd74756d1f570f8

## Findings

### cc80defa.1 [medium] .ci/rediacc_ci/ops/scrub_sentinel.py:105
Anchor: in-diff
Claim: The comment says SSH_ASKPASS_REQUIRE=never stops ssh's askpass fallback 'whatever core.sshCommand or GIT_SSH names', but the variable is honoured only by OpenSSH 8.4 and later; plink or an older OpenSSH with DISPLAY set can still open a graphical askpass dialog mid-plan. The test only shows the variable reaches the child env, using a fake git and GIT_SSH_COMMAND='plink -batch'.
Resolution: open

### cc80defa.2 [low] .ci/rediacc_ci/tests/test_ops_scrub_sentinel.py:265
Anchor: in-diff
Claim: The new assertion checks only the default case where the caller does not set SSH_ASKPASS_REQUIRE; nothing checks that a caller's SSH_ASKPASS_REQUIRE=force is overridden to 'never', which is the scenario named in the commit message.
Resolution: open
