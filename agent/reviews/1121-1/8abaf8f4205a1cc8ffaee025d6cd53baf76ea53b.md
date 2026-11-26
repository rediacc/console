# Review 8abaf8f4: fix(ci): close the CL-V-CI-PY-1 review findings in the .ci python modules, each with a test that fails on the old shape

Commit: 8abaf8f4205a1cc8ffaee025d6cd53baf76ea53b
Repo: console
Branch: 1121-1
Parent: 5fb22d3cdf4c2a96a8735a632ce1f1c0f05958e2
Patch-Id: 84e4f7a7c48dc43c4489d2ae2c11155b90cc5de3
Reviewed-At: 2026-11-26T17:49:11Z
Model: claude-haiku-5-5
Cost: $0.0095 USD, 1 call(s), 32.2s
Diff: 57167 bytes, 22 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes CI python helper defects; the group_command sudo route change is a bug-fix with a security regression noted above.
Dropped: 0
Body-Sig: 16f354202b8ae623

## Findings

### 8abaf8f4.1 [high] .ci/rediacc_ci/core/dockerx.py:794
Anchor: in-diff
Claim: group_command's sudo route now places every inheritable environment variable (tokens, REDIACC_* settings, any exported secret) on the `sudo ... env NAME=value ... bash -c` argv, so any local user reading /proc or `ps` while the re-exec runs can read those secret values; the sg route keeps them in the environment instead.
Class: security
Resolution: fixed bf87bfa2b83867a222d99b53c41e74a35d538c9c | d778be9d 2026-11-26T17:57:53Z
