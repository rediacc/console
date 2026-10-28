## SESSION d778be9d 2026-10-28T12:57:20Z

# STATE d778be9d (branch 1023-1, unpushed, no PR; turbo batch-end)

## Durable rules
- Commit by path, message file in its own call, PR-TASK 9f92c43e, submodules first then the pointer. gen-docs drift: `npx --no-install tsx scripts/gen/gen-docs.ts --write`. Plan edits: `npm run check:ci-plan-record -- --update` then `-- --rendered-only --update`; git add a new plan BEFORE check:ci-plan-boxes --update.
- Box ticks: look up the signature by label first (a wrong sig once filed a present row on L1; corrected with an absent row).
- Stable deploys RELEASE_ASKED=ASKED:2026-10-28T07:56Z. Rulings today: sweep keep-or-archive 10:58Z; durable on bench, no rollbacks 11:11Z; prune via rdc not by hand 11:21Z; key ranges in rdc config 11:31Z; hermes retired 11:57Z.

## Big pieces
- PLAN-ssh-key-source-ranges: V1 S1 R1 A1 ticked; C1 writer running; then I1 locales, D1 docs, X1 hostinger key adopt, X2 bench E1 (= #a150016d, blocked on it).
- PLAN-repo-docker-storage-prune: R1 R2 ticked (renet f354004, fbe1d1f, fixes e3d005b); R3 writer running; then R4 R5 R6, L0 + F1 (ops VM, not beside CLI writers), L1, L2 hostinger dry run, L3 needs operator.
- PLAN-backup-restore-path: R1-R6 ticked; L1 hostinger live then R7.
- Bench proxy on durable 628b1496 (rollback 0ac1523d). hermes retired, data kept.

## Delegated
- a5a1ba95c43706e81 / #95ddf38e: prune R3 offline window + findings e3d005bb.1-2; owns pkg/dockerstore/**, pkg/prune/docker.go(+test), trim_linux.go exports; accept go test ./pkg/dockerstore/ ./pkg/prune/ ./pkg/trim/ rc 0.
- a28431c5d814161d2 / #bcd5acc1: ssh C1 verbs + findings c29ac396.1-3; owns config-access.ts, machine/access.ts, config.ts, machine/index.ts, register.ts, errors.ts, generate-cli-contract.ts, en/cli.json, access-push.ts(+test); accept vitest machine-access + access-push rc 0, tsc rc 0. Lead then runs generate:cli-contract, fix:i18n, generate:cli-docs.
- a327f08f36b2d1e45 / #2c16da2e: e2e runner password leak (buildCommonFlags --password) + findings 01fe5244.1-3; owns packages/e2e-tests/src/**, tests/**; accept e2e tsc + e2e_coverage rc 0.

## Next action
1. As each writer reports: spot-check (plant a defect where the writer did not measure red), rerun accept, commit by path (renet then pointer), tick the box by signature, review-mark findings.
2. After C1: I1 locales writer + D1 docs writer in parallel, then X1 on hostinger via eu-bench config, then X2 bench E1.
3. After R3: R4 renet verb writer, then R5 CLI, then L0/F1 on ops VMs with no CLI writer live.
4. Then ci:quick, backup push (TURBO_PUSH_REASON backup), PR with Operational-Reason, babysit.
