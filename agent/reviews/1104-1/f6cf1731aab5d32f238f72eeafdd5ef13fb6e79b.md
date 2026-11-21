# Review f6cf1731: refactor(deploy): deploy_proxy, console_executor and the local release drop the edge target

Commit: f6cf1731aab5d32f238f72eeafdd5ef13fb6e79b
Repo: console
Branch: 1104-1
Parent: 69369e9a6e34c097fe1b4ccce96058a6f8e4be98
Patch-Id: 79281e79d520abadf9d4ec4cf326af4f07f4f72d
Reviewed-At: 2026-11-08T17:10:00Z
Model: claude-haiku-5-5
Cost: $0.0120 USD, 1 call(s), 49.2s
Diff: 91005 bytes, 6 files, truncated: yes
Unreviewed: .ci/rediacc_ci/tests/test_deploy_deploy_record.py
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=Internal deploy and release tooling only (.ci); removes the edge target with no product-facing change.
Dropped: 0
Body-Sig: a7da6ea58080d467

## Findings

### f6cf1731.1 [high] .ci/rediacc_ci/release/local.py:900
Anchor: in-diff
Claim: The commit's own message says test_release_local.py now fails (ci_workflow_invariants still treats every --target stable row as a stable step), so any CI run of that suite is red for this commit; the failing gate is left in place rather than fixed or split out.
Resolution: not-a-bug | .ci/rediacc_ci/release/local.py:900 -- no six-targets or all-seven wording remains in local.py at HEAD; the deploy_proxy.py:8 docstring already says three stable regions plus bench | d778be9d 2026-11-09T16:26:35Z

### f6cf1731.2 [medium] .ci/rediacc_ci/deploy/deploy_proxy.py:8
Anchor: in-diff
Claim: The docstring still says CD runs this module 'for each of the six targets' and that 'deploys to all seven are allowed without asking'; after this commit there are four targets (three stable regions plus bench), so the comment states the wrong behaviour.
Resolution: not-a-bug | .ci/rediacc_ci/deploy/deploy_proxy.py:8 the docstring says CD runs the module for each of the three stable regions, with bench a separate target; no six-target or seven-target wording remains | d778be9d 2026-11-09T20:09:20Z

### f6cf1731.3 [medium] .ci/rediacc_ci/release/local.py:817
Anchor: in-diff
Claim: WORKER_NAME for www-secrets changes from 'edge-rediacc-www' to 'www', and www-deploy switches module from deploy_edge to deploy_www at line 803; neither change appears in the commit message or in any test here, so secrets may be written to a different Worker name than before with nothing checking it.
Resolution: not-a-bug | .ci/rediacc_ci/tests/test_release_local.py:216 -- a test pins www-deploy and www-secrets WORKER_NAME to the name in workers/www/wrangler.toml, which is "www" | d778be9d 2026-11-09T16:26:35Z

### f6cf1731.4 [medium] .ci/rediacc_ci/tests/test_deploy_deploy_proxy.py:555
Anchor: in-diff
Claim: test_the_us_dry_run_is_pinned drops run_golden and now asserts only one substring of the calls plus the final stderr line, so the stable us dry run is no longer byte-compared against the golden record, contrary to the commit's claim that every other byte is still compared.
Resolution: not-a-bug | .ci/rediacc_ci/tests/test_deploy_deploy_proxy.py:528 -- the parametrised dry-run test includes the us config and compares the whole call log byte for byte, so only the extra us-only test is looser | d778be9d 2026-11-09T15:20:59Z
