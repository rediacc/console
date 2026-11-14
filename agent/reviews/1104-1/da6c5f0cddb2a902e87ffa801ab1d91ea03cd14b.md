# Review da6c5f0c: fix(ci): the generator match is anchored to a line and the bench pin reads env tables

Commit: da6c5f0cddb2a902e87ffa801ab1d91ea03cd14b
Repo: console
Branch: 1104-1
Parent: edd459ffbc2f080089a060982d4bce8b7a3f7438
Patch-Id: 4e1e572566e748006ebd1fcd0b4eff0a8433cc34
Reviewed-At: 2026-11-12T03:28:21Z
Model: claude-haiku-5-5
Cost: $0.0025 USD, 1 call(s), 16.3s
Diff: 5161 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug,ci why=CI gate and test fixes only; no user-facing behaviour change.
Dropped: 0
Body-Sig: 579efe5be0d3b178

## Findings

### da6c5f0c.1 [medium] .ci/rediacc_ci/tests/test_ops_deploy_bench.py:769
Anchor: in-diff
Claim: The new [env.<name>.vars] loop has no fixture or control case; the test reads only the real account configs, so it still passes if the env loop is deleted or never iterates, and the commit's own message gives no proof that an env-level STRIPE_CONSENT_COLLECTION would be caught.
Class: missing-control-test
Resolution: fixed de7164746eada11e6a0f7ab8c40c77d0a04a03aa | d778be9d 2026-11-12T03:42:43Z

### da6c5f0c.2 [low] scripts/gates/check-external-links.ts:83
Anchor: in-diff
Claim: The new pattern requires the generator to be the whole line at column 0, so an indented export or one with a trailing comment such as `export const getStaticPaths = getLanguagePaths; // shared` no longer exempts an unreleased page and the gate reports it BROKEN; nothing in the commit notes or tests this narrowing.
Class: other
Resolution: not-a-bug | scripts/gates/check-external-links.ts:83 deliberate fail-closed narrowing: a non-canonical generator line only costs a BROKEN line naming the link and its page, never a hidden break; every [lang] page in the tree uses the exact line | d778be9d 2026-11-12T03:42:49Z

### da6c5f0c.3 [low] .ci/rediacc_ci/tests/gates/test_gate_external_links_upstream.py:151
Anchor: in-diff
Claim: The new quoted-generator case asserts only the exit code 1, not the BROKEN line for /en/new-policy, so it would still pass if the run failed for an unrelated reason.
Class: missing-control-test
Resolution: fixed de7164746eada11e6a0f7ab8c40c77d0a04a03aa | d778be9d 2026-11-12T03:42:43Z
