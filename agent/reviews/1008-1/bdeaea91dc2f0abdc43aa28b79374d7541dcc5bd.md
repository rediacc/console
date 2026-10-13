# Review bdeaea91: feat(ops): bench runs without the captcha, and no production worker config can carry the switch

Commit: bdeaea91dc2f0abdc43aa28b79374d7541dcc5bd
Repo: console
Branch: 1008-1
Parent: a44378cb60f4d46dcf565333b24667c2a5c17052
Patch-Id: 79128cf4771ac7980b15b231bf5c8fea5df06c77
Reviewed-At: 2026-10-13T08:59:29Z
Model: claude-haiku-5-5
Cost: $0.0047 USD, 1 call(s), 30.3s
Diff: 10696 bytes, 7 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=feature,ci why=Change affects only the test-only bench environment and CI tests; no production surface changes.
Dropped: 0
Body-Sig: c20b5422dab5d3f1

## Findings

### bdeaea91.1 [medium] .ci/rediacc_ci/tests/test_bench_captcha_switch.py:12
Anchor: in-diff
Claim: The glob "wrangler.*.toml" does not match an unsuffixed workers/account/wrangler.toml, so a production config under that name that sets TURNSTILE_ENABLED, CI_MODE or TEST_MODE passes test_no_other_config_carries_a_captcha_or_test_switch, despite the commit saying no production config can carry the switch.
Resolution: fixed d098addfe449bdc5c20f40415d4973469c371921 | d778be9d 2026-10-13T09:06:27Z

### bdeaea91.2 [medium] .ci/rediacc_ci/tests/test_ops_cf_family.py:681
Anchor: in-diff
Claim: The build line is removed from both sides before comparing, so any later change to the bench portal build step's log output (command, outDir, env) passes test_deploy_bench_matches_bash; the test now only checks that one such line exists.
Resolution: fixed d098addfe449bdc5c20f40415d4973469c371921 | d778be9d 2026-10-13T09:06:27Z

### bdeaea91.3 [medium] .ci/rediacc_ci/ops/deploy_bench.py:42
Anchor: in-diff
Claim: With TURNSTILE_SITEKEY set to "" and TURNSTILE_ENABLED="false", the login endpoint on bench.rediacc.com accepts requests with no captcha token, so any automated client that can reach that route is no longer slowed by captcha; nothing in this diff adds a rate limit or restricts the route to authorized users.
Resolution: not-a-bug | operator ruling 2026-10-13: 'You can disable it for AI agents/humans since its for testing only' (bench only; workers/account/wrangler.bench.toml:31, registration limited by ALLOWED_EMAIL_DOMAINS) | d778be9d 2026-10-13T09:06:28Z

### bdeaea91.4 [low] .ci/rediacc_ci/tests/test_bench_captcha_switch.py:39
Anchor: in-diff
Claim: test_deploy_secrets_never_push_the_switch greps the source text for the literal "TURNSTILE_ENABLED": and does not inspect the built secrets payload, so a switch sent under a different quoting or a computed key passes the test.
Resolution: open

### bdeaea91.5 [low] workers/account/wrangler.bench.toml:31
Anchor: in-diff
Claim: test_bench_disables_turnstile only asserts the literal string "false" in the TOML; nothing in the diff shows requireTurnstile parses that string as false, so the test can pass while the captcha stays on.
Resolution: not-a-bug | live probe after deploy 2c12b0e6: bench login without a token answers 401 Invalid email or password where it answered 400 Captcha verification required; boolFromEnv parses 'false' at private/account/src/types/env.ts:8 | d778be9d 2026-10-13T09:06:28Z
