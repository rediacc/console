# Review 8d7e5cdf: fix(dev): WORKTREE_TODAY must be a real ASCII MMDD, checked before the main-repo sync

Commit: 8d7e5cdf8d93ee2def1c3ac2bea381d36c72ba3a
Repo: console
Branch: 1020-1
Parent: 3aa3641857ef79011fdce8ffe62d59f592dc2c9a
Patch-Id: 924fac0b35da63e3ab0dcd5c7205d510cda11ccb
Reviewed-At: 2026-10-20T22:44:03Z
Model: claude-haiku-5-5
Cost: $0.0030 USD, 1 call(s), 22.8s
Diff: 3630 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug why=Fixes input validation in internal dev/CI tooling (.ci worktree script); no shipped product behaviour changes.
Dropped: 0
Body-Sig: d2278c2ddc8c1971

## Findings

### 8d7e5cdf.1 [medium] .ci/rediacc_ci/tests/test_dev_worktree.py:460
Anchor: in-diff
Claim: The new no-fetch assertion passes vacuously if call_log('git') records fetch calls in a format without ' fetch ' surrounded by spaces (for example a bare 'git fetch' line). The committed test has no positive control showing the assertion can fail. The commit message says a valid create was checked to log a fetch, but that check lives only in the scratch test, not in this diff.
Resolution: fixed cb3d2afee827e46aaacd3b90be45f6da299158ef | d778be9d 2026-10-20T22:44:57Z

### 8d7e5cdf.2 [low] .ci/rediacc_ci/dev/worktree.py:560
Anchor: in-diff
Claim: The comment says WORKTREE_TODAY is 'checked as a real MMDD', but the regex at line 562 accepts impossible dates such as 0231, 0230 and 0431, so the comment overstates what is validated. The commit message describes the rule as month 01-12 and day 01-31, which is what the code implements.
Resolution: fixed cb3d2afee827e46aaacd3b90be45f6da299158ef | d778be9d 2026-10-20T22:44:58Z
