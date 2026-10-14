# Review bcfabcba: fix(ci): the soaked-pins call finder, the vitest workspace scan and the argv reading each check what they claim

Commit: bcfabcbae4a2edfef1a45064e09c381b03c2ce4b
Repo: console
Branch: 1008-1
Parent: 3d0927e0a67dbff9d0782f116b8fd6ce2de81ca5
Patch-Id: 4df03f619ccc09b02bfafa18434627cfa81bf863
Reviewed-At: 2026-10-14T19:14:18Z
Model: claude-haiku-5-5
Cost: $0.0115 USD, 1 call(s), 83.4s
Diff: 20649 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug,ci why=Test and CI gate fixes only; no product-facing change.
Dropped: 0
Body-Sig: a3e9d21544ef5d21

## Findings

### bcfabcba.1 [medium] .ci/rediacc_ci/tests/gates/test_gate_shrink_only_composition.py:116
Anchor: in-diff
Claim: reads() only follows Name, Attribute, Subscript and a few calls, so a name bound from `argv = sys.argv + extra`, `args = [*sys.argv]`, `args = sys.argv or []` or `args = build_args()` stays untainted; `assert FLAG in argv` is then skipped and the writer leaves the offender list, though the old bare-name rule (ARGV_NAMES) counted it. No new test covers these spellings.
Resolution: fixed 5871edf9cbaeb1ad9f31fd7c0d3ed265f6c0e3f2 | d778be9d 2026-10-14T19:31:23Z

### bcfabcba.2 [medium] .claude/rediacc_hooks/tests/test_wl_soakedpins.py:142
Anchor: in-diff
Claim: _calls_in skips every ClassDef as well as nested defs, but a class body runs when the enclosing run_stop runs, so a `_soaked_pins_report(worklist, session_id, state_doc)` call written inside a class body in run_stop is not found and the gate test fails falsely; the docstring only justifies skipping defs.
Resolution: fixed 5871edf9cbaeb1ad9f31fd7c0d3ed265f6c0e3f2 | d778be9d 2026-10-14T19:31:23Z

### bcfabcba.3 [low] .ci/rediacc_ci/tests/test_vitest_cache_isolation.py:68
Anchor: in-diff
Claim: The content check reuses VITEST_CMD_RE, whose lookahead allows a following '/', so a script file that merely imports 'vitest/config' (or any 'vitest/' path) is counted as running vitest and its workspace is then required to own a config.
Resolution: fixed 5871edf9cbaeb1ad9f31fd7c0d3ed265f6c0e3f2 | d778be9d 2026-10-14T19:31:23Z

### bcfabcba.4 [low] .ci/rediacc_ci/tests/test_vitest_cache_isolation.py:67
Anchor: in-diff
Claim: `workspace / name` is read as-is, so a script named with '..' segments or an absolute path (matched by SCRIPT_FILE_RE) reads a file outside the workspace, such as another workspace's script, and can count it as running vitest.
Resolution: fixed 5871edf9cbaeb1ad9f31fd7c0d3ed265f6c0e3f2 | d778be9d 2026-10-14T19:31:23Z

### bcfabcba.5 [low] .ci/rediacc_ci/tests/test_vitest_cache_isolation.py:57
Anchor: in-diff
Claim: The docstring and the scan follow only one level of script file, so a workspace whose command runs a script that in turn runs another script containing vitest is still not required to own a config, despite the commit saying a workspace running vitest through a file must own one.
Resolution: fixed 5871edf9cbaeb1ad9f31fd7c0d3ed265f6c0e3f2 | d778be9d 2026-10-14T19:31:23Z
