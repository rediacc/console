# Review 5ffd3a31: feat(ci): check:ci-inline-suppressions holds the tree to zero and admits no baseline

Commit: 5ffd3a3121edcbb5e600bfce47c230d3ab2ff99f
Repo: console
Branch: 1008-1
Parent: e5469e1f01d949e70c7430a9585afe1ce83372a2
Patch-Id: aff9f5dac93453de8ef18633eede599bba802e77
Reviewed-At: 2026-10-14T15:18:11Z
Model: claude-haiku-5-5
Cost: $0.0111 USD, 1 call(s), 50.8s
Diff: 57883 bytes, 8 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=docs,ci why=Gate tooling and docs only; no user-facing product behaviour changes.
Dropped: 0
Body-Sig: 9e7f4ea5b68195b4

## Findings

### 5ffd3a31.1 [low] .ci/rediacc_ci/quality/inline_suppressions.py:229
Anchor: in-diff
Claim: The untokenizable-Python fallback numbers lines with str.splitlines(), which also breaks on form feed, \x1c-\x1e, \x85 and , while the tokenize path counts only \n; in a file tokenize cannot read that contains one of those characters before a marker, the gate's file:line report names the wrong line.
Resolution: fixed a940571734a4a5eb53e246984854fde274b9c6fb | d778be9d 2026-10-14T15:51:37Z

### 5ffd3a31.2 [low] .ci/scripts/quality/check_inline_suppressions.py:1
Anchor: in-diff
Claim: Any refused argument, including a bare --first-seed, prints the '--write-baseline is retired' message, so a caller who typed --first-seed alone is told about the wrong flag.
Resolution: not-a-bug | .ci/scripts/quality/check_inline_suppressions.py only delegates to .ci/rediacc_ci/quality/inline_suppressions.py argv_refusal, where a94057173 makes the refusal name the retired flags given; test_a_retired_or_unknown_flag_is_refused_not_ignored pins a bare --first-seed naming itself | d778be9d 2026-10-14T15:52:00Z
