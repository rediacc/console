## SESSION d778be9d 2026-11-13T04:10:00Z

# STATE d778be9d (2026-11-13, branch 1104-1, PR 605)

## Where things stand
- PR 605 pushed aded1dde93..61d3034452 after ci:quick green, vm:check VERIFIED (tree f2760603d9d7) and backup-check VERIFIED. Unpushed since: renet retry test + allowlist warning, B1 tick 6f07910672 + accept 9dc6d476ca, digest org fix (account 7f5e8eb, 161ebc9, 8c8c96b), licence drill fixes 12803257ef, e6d99e32.
- CI run 43360983417 on 61d3034452 RED on 10 jobs in three clusters, each with a lease writer.
- Bench at a4aaa85482: proof signer 22/22 ok. region-loss broke at the company buckets step. notices and licence drills stop at the root TOTP challenge (bench root == operator account, seed REDIACC_BENCH_TOTP_SEED, profile bench-login).

## Delegated (land with ./run.sh worktree land <id>, submodules first)
- a048a3398b0ef32ce #63c267ff: pytest unraisable warnings, shards 1,4,5.
- a655f768c9db114c2 #22e2ca84: renet/proxy Go reds.
- a814243710bff3c3f #cb02f9f2: Account E2E setup red.
- abd2f2febfee485bf #04b4a244 #a1ecc191 #000fcf57: drills answer root TOTP.
- a4e7dc4d47bd7da49 #ffca9706: region-loss bucket step.

## Next action
1. Land each writer report as it arrives: spot-check, cherry-pick submodules first, run its accept on the landed tree, commit gitlinks, mark review findings, gc.
2. Drill writer landed: deploy_bench, run notices_drill and licence_expiry_drill under deploy-bench + bench-login, tick notices X2 and L1, then LP-bench (investigate, then --live-proof --write --tick, nothing committed between deploy and record).
3. Region-loss writer landed: rerun region-loss --bench, then signer plan LP-bench 89d70106.
4. CI writers landed: vm:check --changed --base 61d3034452, backup drills if backup paths, ci:quick, review-commit, push red-fix, ci-trace --wait.
5. After merge: production deploys #5ac354e6 and #bf47a483 (+ repair_org_customer_ids) via release:local (ASKED:2026-11-12T05:57Z).

## Big pieces
- PLAN-enterprise-tenants.md (C8, C11, LD1, V3, V4, T1, HO1 open); PLAN-onprem-relicence-inbox.md (L1, LP-bench, LP-hostinger live proofs owed).

## Owed ticks
- PLAN-health-checks-local.md#85f55665
- PLAN-proxy-cd-six-targets.md#abe9b4eb
- PLAN-production-key-only.md#6a1ca4a4
- PLAN-enterprise-isolation.md#2878e08d
- PLAN-enterprise-isolation.md#a8892e0c
- PLAN-enterprise-isolation.md#0a6e5712
- PLAN-enterprise-isolation.md#e8b5ad6f
- PLAN-enterprise-isolation.md#6041744e
- PLAN-enterprise-isolation.md#f4b49503
- PLAN-enterprise-isolation.md#0fbd62dc
- PLAN-enterprise-isolation.md#cc583290
- PLAN-enterprise-isolation.md#b343464b
- PLAN-backup-program.md#0a237b2e
- PLAN-backup-program.md#575e0098
- PLAN-backup-program.md#07955f58 -- live-owed: code landed; bench, hostinger or fleet runs close them.

## Overnight
- Ticked: #5f6d277d B1, #9cb71958 PR red push, #e3b3ba33 Terms, #1e9cacce lineage purge, #81bed146 relicence plan.
- Decided: org-customer-id E2E route is a test seam (kept); K1.0 vm:check rc=1 did not recur in 2 reruns, row now records output.
- Hints: 6cf2f040, 4557399b, a039fb78, b8ae082c.
