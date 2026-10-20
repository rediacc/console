# Review cb3d2afe: test(dev): the seam-day create asserts the fetch the refusal test scans for

Commit: cb3d2afee827e46aaacd3b90be45f6da299158ef
Repo: console
Branch: 1020-1
Parent: 8d7e5cdf8d93ee2def1c3ac2bea381d36c72ba3a
Patch-Id: a5997a4f0e38ff3a292c6566860ecf18c68e5d9f
Reviewed-At: 2026-10-20T22:50:26Z
Model: claude-haiku-5-5
Cost: $0.0019 USD, 1 call(s), 13.8s
Diff: 2638 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=docs,ci why=Only a test assertion and a comment change; the MMDD validation logic is unchanged, so no user-facing behaviour changes.
Dropped: 0
Body-Sig: 785ce48fbaf5b0c7

## Findings

### cb3d2afe.1 [low] .ci/rediacc_ci/tests/test_dev_worktree.py:452
Anchor: in-diff
Claim: The new comment says this assertion is a positive control 'for the refusal test below', but the refusal test shown below (test_create_refuses_a_seam_day_that_is_not_mmdd) asserts only rc == 1 and the MMDD error text and never checks for the absence of a fetch, so this control does not prove that test's fetch assertion can fail; the no-fetch check the commit message refers to must live elsewhere and the comment should name it.
Resolution: not-a-bug | .ci/rediacc_ci/tests/test_dev_worktree.py:462 the refusal test does assert that no " fetch " line was logged, which is the assertion the control at line 452 proves able to fail | d778be9d 2026-10-20T22:50:47Z
