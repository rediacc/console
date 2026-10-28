## SESSION d778be9d 2026-10-28T13:42:57Z

# STATE d778be9d (branch 1023-1, unpushed, no PR; turbo batch-end)

## Durable rules
- Commit by path; message file in its OWN Write/printf call, never in the same Bash call as the commit; >20 files needs a "Sampled N files: ..." line. PR-TASK 9f92c43e. Submodules first, then pointer. After a renet FunctionDef change: regenerate the renet contract, rebuild packages/shared, add the CLI RENET_FUNCTION_ACCESS row, then tsc.
- Box ticks: look up the signature by label (note >= 40 chars) before --plan-investigate --write.
- Contract bundles: regenerate only when no locale writer is mid-edit; commit only the bundles that match committed locale files.
- Rulings 2026-10-28: sweep keep-or-archive 10:58Z; bench durable, no rollbacks 11:11Z; prune via rdc, not by hand 11:21Z; key ranges in rdc config 11:31Z; hermes retired 11:57Z; MCP bars machine access set/push 13:29Z (#ca47af25).

## Big pieces
- PLAN-ssh-key-source-ranges: V1 S1 R1 A1 C1 I1 D1 ticked; binding fix cc8a2aeb6 (plain binding = true). X1 next: eu-bench already holds key console-probe (fingerprint SHA256:73fR5Z5q...); re-run `./rdc.sh --config eu-bench machine access set hostinger --key console-probe`, then `machine access push hostinger --dry-run -o json` (expect one adopt at line 15 of 17), then the real push, re-push (unchanged), grep rdc-access on hostinger, devbox negative ssh. Then X2 = bench E1 27-90/27-91 (closes #a150016d).
- PLAN-repo-docker-storage-prune: R1-R4 ticked (renet f354004 fbe1d1f 98d5f09 e5185cb). R5 R6 writers running; then L0/F1 on ops VMs (no CLI writer live), L1, L2 hostinger dry run, L3 needs the operator.
- PLAN-backup-restore-path: R1-R6 ticked; L1 hostinger live, then R7.
- Bench proxy durable 628b1496 (rollback 0ac1523d). hermes retired, data kept.

## Delegated
- a6d6fae77918cb280 / #9f61ada2 + #ca47af25: prune R5 rdc repo prune + MCP bar; owns repo-prune.ts, repo-extended.ts, command-policy.ts, command-metadata.ts, command-planes.ts, plane-coverage test, cli locales; lead regenerates the contract, hashes and docs.
- a18564018669fb5a9 / #aaa257ee: prune R6 suite 04 caller; accept e2e_coverage rc 0.
- abb239ebd5e47e9ad / #1dd80993: renet findings e5185cbd.1-5.
- afec249ccbd13699b / #24fa4d53 + #d00f4c1e: pre-ask guard "push" false positive; push no-op drops empty objects in whole-stored subtrees.

## Next action
1. As each writer reports: spot-check, rerun accept, commit by path, tick by signature, review-mark findings. Open findings: 3fabddff.1, 4bb8651c.1, 714a25c3.1, cc8a2aeb.2.
2. When R5 lands (CLI quiet): run X1 on hostinger, then X2 bench E1.
3. Then L0/F1 on ops VMs, then ci:quick, a backup push (TURBO_PUSH_REASON backup), the PR with Operational-Reason, and babysit; the PR plan's A1a preview smoke needs the PR.
