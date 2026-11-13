# Review d828cfae: fix(enterprise): bootstrap and invite call the company Worker under its own API key

Commit: d828cfaeae2dbde7a1bd55bd111e9ab2626fb097
Repo: console
Branch: 1104-1
Parent: 7a7a363499bae2f65770d27ec6a22ebd99391f15
Patch-Id: be3dd20356cad6cfd0068b8d55e75157a72310ee
Reviewed-At: 2026-11-13T10:30:33Z
Model: claude-haiku-5-5
Cost: $0.0026 USD, 1 call(s), 14.3s
Diff: 10469 bytes, 4 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes bootstrap/invite 401 by using the company's own API key instead of the shared environment key.
Dropped: 0
Body-Sig: d40d72c0495f1c13

## Findings

### d828cfae.1 [medium] .ci/rediacc_ci/enterprise/cli.py:101
Anchor: in-diff
Claim: The live_add wiring now passes api_key_of=onboarding.live_api_key(opts.bws_project) when --bws-project is set, but no test in this diff exercises that line, so dropping or misnaming the argument would silently revert bootstrap/invite to the 'needs the company's own key' refusal in the production path without any test failing.
Class: missing-control-test
Resolution: open
