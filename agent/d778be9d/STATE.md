## SESSION d778be9d 2026-10-28T14:17:54Z

# STATE d778be9d (branch 1023-1, unpushed, no PR; turbo batch-end)

## Durable rules
- Commit by path; message file in its OWN Write call; >20 files needs "Sampled N files: ...". PR-TASK 9f92c43e. Check HEAD moved before ticking.
- gen-docs drift with my uncommitted V6 wiring: `git diff -- package.json scripts/ci-runner/gates.lock.json .ci/config/lane-durations.json > /tmp/v6now.patch; git apply -R`, regenerate, commit, `git apply /tmp/v6now.patch`.
- After a renet FunctionDef: regenerate the renet contract, rebuild packages/shared, add the CLI access row, tsc.
- Rulings 2026-10-28: sweep keep-or-archive 10:58Z; bench durable 11:11Z; prune via rdc 11:21Z; key ranges in rdc config 11:31Z; hermes retired 11:57Z; MCP bars access writes 13:29Z. Stable deploys: RELEASE_ASKED=ASKED:2026-10-28T07:56Z.

## Big pieces
- PLAN-ssh-key-source-ranges DONE (X2: bench E1 27-90/27-91 passed on durable 628b1496).
- Durable wave (#a150016d): L0 observation fix committed 900c1e142 (/v1/ready reports executors {total, heavy, cap, heavyCap}). NEXT: redeploy bench proxy (`PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile deploy-proxy-bench -- python3 -m rediacc_ci.deploy.deploy_proxy --target bench --record /tmp/proxy-bench-l0.json`), run the L0 drills per the dated note under the L0 box, tick L0, record E9 (live_proof record --plan PLAN-org-executor-connect-timeout-relocate --target bench), then the six-target wave, E10, C1/L7.
- PLAN-repo-docker-storage-prune: R1-R6 ticked; F1 writer running; then L0 ops-VM reproduction, L1, L2 hostinger dry run, L3 operator.
- PLAN-backup-restore-path: L1 hostinger, R7.

## Delegated
- ae2383bf37108d7a0 / #92e50cb2: prune F1 in renet pkg/daemon/setup.go + clean_runtime_test.go; accept go test ./pkg/daemon/ rc 0, build.sh dev rc 0.
- af1fefccdb3aa8bca / #50f1232a: read-only /writers-now survey into /tmp/writers-now-survey.md; reply has LOCAL-NOW batches to spawn next.
- a7a6c82c4d6718b21 / #863aa8fe: CLI core audit off under serve --mode container; owns services/core/audit.ts, its test, cli.ts.

## Next action
1. Survey reply lands: spawn writers for its LOCAL-NOW batches (disjoint files, cap 15), lease each.
2. F1 and audit writers report: verify, commit by path, tick by signature.
3. Bench L0 redeploy and drills, then E9, then the wave.
