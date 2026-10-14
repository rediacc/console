# Review f794ae92: fix(ci): any operator on the pins-soaked apply line that can replace its exit status loses the red path

Commit: f794ae92a4182cfba19cafb08ffbed5c39aa9e20
Repo: console
Branch: 1008-1
Parent: 002b98bb57be11e5dce2afe83bd18ce3a5ab3e29
Patch-Id: 9c2695cceab9035054c9b8f9a4d69b289afc74a2
Reviewed-At: 2026-10-14T18:58:59Z
Model: claude-haiku-5-5
Cost: $0.0032 USD, 1 call(s), 23.1s
Diff: 4615 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=CI invariant check fix only; no user-facing product change.
Dropped: 0
Body-Sig: fd7d6f7dac178e72

## Findings

### f794ae92.1 [high] .ci/rediacc_ci/security/ci_workflow_invariants.py:1071
Anchor: in-diff
Claim: _PINS_MASK_RE has no test for a leading `!` (e.g. `! npm run ... apply-soaked ...`), which inverts the apply status: a failed apply leaves `rc=$?` at 0 and the job stays green, so the commit's 'any operator' claim does not hold and the check still passes this bypass.
Resolution: fixed 3d0927e0a67dbff9d0782f116b8fd6ce2de81ca5 | d778be9d 2026-10-14T19:04:52Z

### f794ae92.2 [medium] .ci/rediacc_ci/security/ci_workflow_invariants.py:1076
Anchor: in-diff
Claim: The new docstring says 'nothing on the apply line can mask it', but the regex does not cover a leading `!` negation, so the stated guarantee is false for that case.
Resolution: open

### f794ae92.3 [low] .ci/rediacc_ci/security/ci_workflow_invariants.py:1071
Anchor: in-diff
Claim: The `\|` alternative also matches the noclobber override `>|`, which does not change the apply status, so such a line is reported as 'no red path' (a false positive that fails closed).
Resolution: open
