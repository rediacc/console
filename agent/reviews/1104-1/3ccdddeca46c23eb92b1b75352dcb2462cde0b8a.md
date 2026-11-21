# Review 3ccdddec: feat(gates): check:ci-plan-bindings fails a closed plan that anything still binds

Commit: 3ccdddeca46c23eb92b1b75352dcb2462cde0b8a
Repo: console
Branch: 1104-1
Parent: 2655e28b23dcd60518a65657b636d3fda039bf01
Patch-Id: 5fbb83e7e2906be04425d62997c5d3328011d010
Reviewed-At: 2026-11-09T03:51:26Z
Model: claude-haiku-5-5
Cost: $0.0076 USD, 1 call(s), 42.0s
Diff: 26538 bytes, 7 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=feature,ci why=Adds a dev-only merge gate and CI step; no user-facing product change.
Dropped: 0
Body-Sig: 80026e76d389178f

## Findings

### 3ccdddec.1 [high] .github/workflows/ci-quality.yml:404
Anchor: in-diff
Claim: The new required step `Plan bindings` runs check_plan_bindings.py in quality-static without continue-on-error, and the commit's own verification says it exits 1 on the real tree (48 bindings over 18 closed plans). Merging this without CB5 in the same change turns quality-static red on the default branch until the migration lands.
Resolution: not-a-bug | the scenario (merging before CB5 turns main red) cannot occur: .claude/rediacc_hooks/guards/block_unverified_push.py:1811 receipt_refusal refuses any push whose ci:quick receipt is red or absent, and check:ci-plan-bindings rc 1 keeps that receipt red, so nothing reaches CI or main until the CB5 migration (#895e8be0, agent running) releases the bindings in the same batch | d778be9d 2026-11-09T04:15:44Z

### 3ccdddec.2 [medium] .ci/scripts/quality/check_plan_bindings.py:109
Anchor: in-diff
Claim: The CANNOT RUN branch for store files that fold to zero items has no control: the selftest's only empty-input case is an empty plans tree (exercising line 92), so a regression that removes or inverts this condition would still pass all 14 controls.
Resolution: fixed c018f50e80d2dce05f37a3deeb530d28a15fbac7 | d778be9d 2026-11-09T04:05:25Z

### 3ccdddec.3 [low] .ci/scripts/quality/check_plan_bindings.py:109
Anchor: in-diff
Claim: If agent/worklist/ holds no *.jsonl files at all, the floor does not trigger, items is empty, and check prints 'nothing binds to any' with 0 item(s) read and exits 0, so item bindings are unverified yet reported green.
Resolution: fixed c018f50e80d2dce05f37a3deeb530d28a15fbac7 | d778be9d 2026-11-09T04:05:25Z
