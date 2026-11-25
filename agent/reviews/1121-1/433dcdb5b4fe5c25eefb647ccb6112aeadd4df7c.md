# Review 433dcdb5: fix(post-bash): a filtered git commit that did not land is said out loud

Commit: 433dcdb5b4fe5c25eefb647ccb6112aeadd4df7c
Repo: console
Branch: 1121-1
Parent: ec1021d695934757503c8141b1dca90ea97dbcce
Patch-Id: ef0840a620e96eb8f201324768ed7a3a37be9f8a
Reviewed-At: 2026-11-25T03:30:18Z
Model: claude-haiku-5-5
Cost: $0.0101 USD, 1 call(s), 69.2s
Diff: 18620 bytes, 4 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Adds a missed-commit notice to the post-bash advisory hook; no public API or user-facing command changes.
Dropped: 0
Body-Sig: 763854f041b28993

## Findings

### 433dcdb5.1 [medium] .claude/hooks/post-bash/review_commit.py:208
Anchor: in-diff
Claim: The subject witness suppresses the notice for a refused commit whose -m subject equals HEAD's current subject (e.g. a repeated 'wip' or 'fix' message), so that refusal is silent, which is the failure this commit is meant to stop.
Class: other
Resolution: open

### 433dcdb5.2 [low] .claude/rediacc_hooks/tests/test_post_bash_commit_landed.py:156
Anchor: in-diff
Claim: The subject-witness test never runs a commit in its own call (only g.py is staged after an earlier shell commit), so it passes on a not-landed commit and pins the silence from review_commit.py line 208 rather than testing a parallel landed commit.
Class: missing-control-test
Resolution: open

### 433dcdb5.3 [low] .claude/hooks/post-bash/review_commit.py:236
Anchor: in-diff
Claim: If trigger_lines raises here, main() exits before record_heads at line 238 runs, so the HEAD record stays stale and a later refused commit in that session goes unreported.
Class: other
Resolution: open

### 433dcdb5.4 [low] .claude/hooks/post-bash/review_commit.py:210
Anchor: in-diff
Claim: A `git commit --dry-run` with paths staged leaves HEAD unmoved, so it is reported as COMMIT DID NOT LAND and told to be rerun, though a dry run never intends to land; no test covers this.
Class: other
Resolution: open

### 433dcdb5.5 [low] .claude/hooks/post-bash/review_commit.py:6
Anchor: in-diff
Claim: The module docstring still says 'TWO JOBS, BOTH CHEAP' and lists only trigger and surface, while the module now also performs the commit-landed check and HEAD recording.
Class: doc-contradicts-code
Resolution: open
