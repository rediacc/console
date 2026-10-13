# Review 0f707e35: fix(ci): a relative PYTHONPATH is pinned when the package is first imported, so a sibling started after a chdir still finds it

Commit: 0f707e35b297eb665bc78df6f82ccabdd5ddb8ed
Repo: console
Branch: 1008-1
Parent: 4f0063f11393ad78f5ce1e04296074d2526705a5
Patch-Id: eb9dda7dff5e42f82fcccce37a3a1fab142aa786
Reviewed-At: 2026-10-13T05:44:43Z
Model: claude-haiku-5-5
Cost: $0.0046 USD, 1 call(s), 37.3s
Diff: 4248 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug,ci why=Fixes the CI build harness only (.ci/rediacc_ci); no user-facing product change.
Dropped: 0
Body-Sig: e71e7fc47fb65620

## Findings

### 0f707e35.1 [medium] .ci/rediacc_ci/__init__.py:33
Anchor: in-diff
Claim: The docstring says the pin 'closes it for every such spawn', but it only works when rediacc_ci was imported before the chdir. A script run as `PYTHONPATH=.ci python3 .ci/x.py` (not -m, so the package __init__ has not run) that calls os.chdir and then spawns a rediacc_ci module still hands its child the relative `.ci`, which then fails, so the comment states a guarantee the code does not give.
Resolution: fixed 133138ded8f59c42fdb45245bee5fe273c72ddc0 | d778be9d 2026-10-13T05:56:18Z

### 0f707e35.2 [medium] .ci/rediacc_ci/__init__.py:43
Anchor: in-diff
Claim: An empty PYTHONPATH (set but ''), which Python ignores, is rewritten to the absolute current directory, so every child process now gets the cwd on its sys.path; a child started from a directory with a stray module can import it. No test covers this changed behaviour.
Resolution: fixed 133138ded8f59c42fdb45245bee5fe273c72ddc0 | d778be9d 2026-10-13T05:56:19Z
