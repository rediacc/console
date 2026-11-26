# Review 17f9d3d7: fix(ci): review findings CL-W-CI-PY-2, the quality gates read what they claim to read

Commit: 17f9d3d7c59cf802e1955fbf3ccb0b03ffecf0aa
Repo: console
Branch: 1121-1
Parent: 3ce0afcb5238d5abc77d6f944eae6d25c7cd45dc
Patch-Id: 829cc86275b3f00e4e9d619ffd2ab081d1024ffd
Reviewed-At: 2026-11-26T18:24:48Z
Model: claude-haiku-5-5
Cost: $0.0120 USD, 1 call(s), 67.3s
Diff: 43497 bytes, 15 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug,ci why=CI quality-gate tooling and tests only; no user-facing change.
Dropped: 0
Body-Sig: 44b5802ebe31ddde

## Findings

### 17f9d3d7.1 [medium] .ci/rediacc_ci/quality/trap_registry.py:513
Anchor: in-diff
Claim: direct_run_files maps every `python3 -m a.b` to `.ci/a/b.py`, so a direct gate running a package (`-m a.b` resolving to `a/b/__init__.py`) or a non-.ci module (`-m pytest`) is judged unresolvable by gate_resolves; no selftest control covers either case.
Class: other
Resolution: open

### 17f9d3d7.2 [medium] .ci/rediacc_ci/security/ci_workflow_invariants.py:1103
Anchor: in-diff
Claim: _executed_lines drops every line starting with `echo ` or `printf `, so a step like `echo start && npm run check:ci-ops-health` (which really runs the gate) stops being found by upstream_gate_steps and the invariant reports a missing gate step; no test covers an echo-prefixed line that also executes a gate.
Class: missing-control-test
Resolution: open
