# Review dcd1a513: fix(hooks): name the bench allowlist fix when a bench request answers 403

Commit: dcd1a513bf07e12b7656ffc8cf412dfb3b98ddbc
Repo: console
Branch: 1104-1
Parent: ce09a22da26d677dbc98dab08e15758eb3425639
Patch-Id: ce43f33aa09954e9395152594ae8ee1653e7769f
Reviewed-At: 2026-11-10T05:47:49Z
Model: claude-haiku-5-5
Cost: $0.0122 USD, 1 call(s), 57.6s
Diff: 54363 bytes, 12 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug,docs,ci why=Dev-tooling hooks and CI ops-health messages only; no product CLI behaviour changes.
Dropped: 0
Body-Sig: 29466b4f4a2d6e90

## Findings

### dcd1a513.1 [medium] .claude/hooks/stop/wl_benchblock.py:48
Anchor: in-diff
Claim: ALLOWLIST_TOLD hard-codes "bench_access add-current" and LOGIN_TOLD hard-codes "login:bench", although the docstring says fix texts are imported, never copied. If bench_access.COMMAND is renamed, ops_health's 403 hint (built from the imported command) no longer suppresses this note, so the allowlist note is shown on top of it.
Resolution: fixed 6631d6d099c3243080658719a809371c466be8b9 | d778be9d 2026-11-10T06:03:54Z

### dcd1a513.2 [medium] .claude/hooks/stop/wl_benchblock.py:97
Anchor: in-diff
Claim: Any 403 shape from a bench command (including a CLI envelope "HTTP 403" from an app-level permission refusal) is told unconditionally that it is the IP allowlist, NOT a rate limit, and that waiting does not clear it; no test covers a bench 403 that is not a WAF block, so an agent is steered to re-run the allowlist command for it.
Resolution: fixed 6631d6d099c3243080658719a809371c466be8b9 | d778be9d 2026-11-10T06:03:55Z

### dcd1a513.3 [medium] .ci/rediacc_ci/ops/ops_health.py:534
Anchor: in-diff
Claim: With stdout_tail=False, a failed repair whose stdout is plain-text error output (not the actions JSON) and whose stderr is empty now reports "no action reported", discarding the printed error and making that text false.
Resolution: fixed 6631d6d099c3243080658719a809371c466be8b9 | d778be9d 2026-11-10T06:03:55Z

### dcd1a513.4 [low] .ci/rediacc_ci/ops/ops_health.py:278
Anchor: in-diff
Claim: BENCH_CONFIG_NAMES covers only login_bench.CONFIG (eu-bench), while wl_benchblock.py treats `--config bench` as a bench config, so a 403 from `--config bench` in the machines check gets no allowlist hint.
Resolution: fixed 6631d6d099c3243080658719a809371c466be8b9 | d778be9d 2026-11-10T06:03:55Z

### dcd1a513.5 [low] .claude/hooks/stop/wl_benchblock.py:168
Anchor: in-diff
Claim: When sources() fails, the message is emitted for any Bash call that passes the prefilter (a bench word plus a 403 fragment) before is_bench_command is checked, so a non-bench command that merely mentions bench and 403 gets a bench-block message.
Resolution: fixed 6631d6d099c3243080658719a809371c466be8b9 | d778be9d 2026-11-10T06:03:55Z
