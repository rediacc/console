## SESSION d778be9d 2026-09-28T19:04:13Z

# STATE d778be9d (2026-09-28T19:10Z)

## Goal
Spec W (agent/plans/PLAN-ci-time-budget.md): every non-exempt CI job p90 <= 12 min over 10 runs (P2 exit), then T3.1 flip check:ci-lane-budget gate:true, then P4. Branch 0923-1, PR #590, PR-TASK e87fa3ce. Other plans held (operator 2026-09-26).

## Where it stands
- Run 36461941122 (957a2d05b, renet e599aa3) attempt 2: every E2E Workers leg <= 12.8 min (only opensuse 3/8 over 12), oracle legs 8.6-8.9 (were 12-14), E2E Ceph 11.3, OPS Provision <= 10.9, K8s Multinode 19.4 / K8s Ceph 13.3 (exempt, caps 25/20).
- Budget report fixed (34ac34c13, eed4e1dee, cdcd4f5a6): run `PYTHONPATH=.ci python3 -m rediacc_ci.ci.budget_report --branch 0923-1 --limit 10 --status completed` for the true p90 table; lane model per-distro (6a94a96a9).
- Unpushed on top of 957a2d05b: 61922befc (app-token probe on macOS), fa17cd84a (plan D1/D2), 234be20ed (bws-secrets retry and classification). Receipt for 234be20ed running (task bpp5rapav).

## Push recipe
1. Receipt in /home/developer/pushclone-0923 (fetch, checkout -f FETCH_HEAD, submodule update, `npx -y npm@<NPM_VERSION> ci` and `npm run install:natives` whenever a lockfile changed, npm run -s build, check:ci-doc-region-parity, ci:quick --receipt-out ...). Only check:ci-plan-implementation may fail (carried).
2. Push renet FIRST as its own command: `git -C private/renet push origin <sha>:refs/heads/0923-1` (the guard block_unpushed_submodule_pin refuses otherwise; guards judge a whole command before any clause runs).
3. Then `git push origin 0923-1` (no -q), poll the PR head, arm `.ci/scripts/ci/ci-trace.py --wait --until-final --timeout 3h` in the background.

## Open threads
- #a89b853d Account E2E flake (02-03-activity-admin-filters.test.ts:85), writer aa9b4b92c1c916195 running.
- #4eb7b457 app-token probe regression: root cause (checkout's persisted GITHUB_TOKEN extraheader) fixed 957a2d05b, macOS timeout fixed 61922befc; tick after a green CI run shows the probe passing on Linux and macOS.
- #7f148321 pre-baked images: PLAN-ci-prebaked-vm-images (6c9b297c6), D1/D2 = private GHCR; B0 measures first.
- Next P2 lever if opensuse legs stay over 12: rebalance with the refreshed model, or the pre-baked plan.

## Next action
When bpp5rapav passes: push (recipe above), arm the CI watch, then run the budget report for the p90 table and decide the P2 exit.
