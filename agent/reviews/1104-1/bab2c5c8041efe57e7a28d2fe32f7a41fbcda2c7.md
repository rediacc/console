# Review bab2c5c8: feat(ci): path-trace folds listings and name scans to lists and names

Commit: bab2c5c8041efe57e7a28d2fe32f7a41fbcda2c7
Repo: console
Branch: 1104-1
Parent: 3a4a8513d3987b00704980a9d297b446951e3b48
Patch-Id: f762cf864334ad2b5aa41e3f9c63b3c419366433
Reviewed-At: 2026-11-17T21:27:12Z
Model: claude-haiku-5-5
Cost: $0.0146 USD, 1 call(s), 71.9s
Diff: 89416 bytes, 3 files, truncated: yes
Unreviewed: scripts/ci-runner/trace-honest.ts
Verdict: findings
Attempt: 1
Labels: bump=none kind=feature,ci why=CI tooling change (path-trace/trace-honest), no user-facing product behaviour.
Dropped: 0
Body-Sig: 0946ee50a0de3124

## Findings

### bab2c5c8.1 [medium] scripts/ci-runner/path-trace.ts:460
Anchor: in-diff
Claim: `--recurse-submodules` is in LS_FILES_NAME_FLAGS, so a gate running `git ls-files --recurse-submodules` gets names: ['**'], but that scan prints names inside submodules, which the root's tracked-name hash does not cover; a file added inside a submodule changes the output with no name in the hashed set moving.
Class: other
Resolution: open

### bab2c5c8.2 [medium] scripts/ci-runner/path-trace.ts:748
Anchor: in-diff
Claim: The index-read check is skipped whenever any name-only ls-files ran, so a non-git process that reads .git/index directly (its blob shas reflect content) beside `git ls-files -z` is explained away and the gate gets names: ['**'] instead of whole-tree, missing content changes.
Class: other
Resolution: open

### bab2c5c8.3 [medium] scripts/ci-runner/path-trace.ts:640
Anchor: in-diff
Claim: The probedDir comment says a probe under an untracked ancestor such as build output names nothing tracked, but when that build directory does not exist the walk climbs to the nearest existing tracked ancestor and lists it (e.g. the root), so the comment's stated behaviour is wrong (safe over-declaration, but not what it says).
Class: doc-contradicts-code
Resolution: open
