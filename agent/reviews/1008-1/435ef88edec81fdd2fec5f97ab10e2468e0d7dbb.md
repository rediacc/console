# Review 435ef88e: fix(ci): gate model, deploy and log modules drop their inline markers, and the plan gate binds its clock in one dict instead of a global

Commit: 435ef88edec81fdd2fec5f97ab10e2468e0d7dbb
Repo: console
Branch: 1008-1
Parent: f5b251a75fcba5b6eca2da5d78aa0116e52c1357
Patch-Id: 3081fbbaa8b86696371424c2736298c2a1b8062a
Reviewed-At: 2026-10-14T10:38:12Z
Model: claude-haiku-5-5
Cost: $0.0150 USD, 1 call(s), 71.4s
Diff: 66204 bytes, 16 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=Internal CI and test tooling refactor: inline suppressions removed, globals replaced by a dict or functools.cache. No user-facing change.
Dropped: 0
Body-Sig: f5458c7fafd6f992

## Findings

### 435ef88e.1 [medium] .ci/scripts/quality/check_plan_implementation.py:2237
Anchor: in-diff
Claim: _orphan_commit_controls now evaluates sys.modules[__name__]; if this file is executed by importlib without being registered in sys.modules, that lookup raises KeyError when controls_fired runs, where the removed `global REPO_ROOT` never looked the module up.
Resolution: open

### 435ef88e.2 [low] .ci/rediacc_ci/infra/docker_pull_ghcr.py:104
Anchor: in-diff
Claim: The comment above MISSING_AUTH_MSG still says S105 fires on the name `TOKEN` and that the suppression is the same as elsewhere, but the suppression was removed and the name no longer contains TOKEN, so the rationale is stale.
Resolution: open

### 435ef88e.3 [low] .ci/rediacc_ci/infra/ci_pull_images.py:116
Anchor: in-diff
Claim: The comment above MISSING_AUTH_MSG still describes S105 firing on the name `TOKEN` and a shared suppression, both of which this commit removed, so the rationale no longer matches the code.
Resolution: open

### 435ef88e.4 [low] .ci/rediacc_ci/tests/gates/test_gate_plan_housekeeping.py:27
Anchor: in-diff
Claim: The comment block about the module-scoped filler template now sits above `_run`, after `_TEMPLATE` was removed, so it no longer sits beside the `_template` function it describes.
Resolution: open
