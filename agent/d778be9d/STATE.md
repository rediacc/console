## SESSION d778be9d 2026-11-27T00:52:11Z

## Next action
1. Spot-check the freshness writer's tree changes (a373fb61281551433, #d0aedd6c: pins.json, Dockerfiles, toolchain.env, lockfiles, go.mod through `npm run pins`), commit each group by path with its gate rc (check:ci-pin-freshness, check:deps, check:ci-go-deps), then `npm run ci:quick > /tmp/m/ciquick12.out` with no writer live and lease #68cf6765 to that task.
2. Land the ops-down lease (a93968665955672d5, #768406eb), renet first; run check:ci-renet; commit the gitlink.
3. If run 12 is green: `npm run vm:check -- --changed` (renet touched), `git push -u origin 1121-1`, `RELEASE_ASKED=ASKED:2026-11-25T16:35Z npm run release:local -- --channel edge --branch-release --dry-run`, the real run, then record rollback ids and D1 bookmarks (#58a674f6).
4. Staff the r70 survey's startable clusters (round 6b277f00) after run 12 starts only if they stay light.

## Delegated
- a373fb61281551433 #d0aedd6c freshness reds, main checkout, no commits; lead commits.
- a93968665955672d5 #768406eb renet ops down skips VMs that do not exist; lease.
- afba1931b957c8fb4 r70 survey.

## Big pieces
- Edge release #58a674f6 after a green ci:quick (runs 7-11 red, each red fixed; run 11's freshness reds in flight).
- Windows lane with tester console-6c: first workaround-assisted ops up --basic --backend hyperv success (batch 19); O13 landed, clean from-zero run next. In-process Windows ssh in private/renet/pkg/infra/sshexec.

## Owed ticks
Legal L6 and LP-bench; AX9 live e2e; host-temp live halves; #2ec7e550 rollback siblings; CL-I boxes f1adf697 and e14b9f6a; the plan/record review findings in lead batches.

## Armed
- #0f42f15e: NOT-BEFORE 2026-12-01T00:00Z, rotation-profile delete of the old asia key.
- #08c7fe84 [?]: eu-remote rebind code for H3; its ready command is on the H3 box (PLAN-backup-integrity); DEFAULT executes at window close.
