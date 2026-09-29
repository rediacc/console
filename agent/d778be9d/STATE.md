## SESSION d778be9d 2026-09-29T09:29:15Z

# STATE d778be9d (2026-09-29T09:10Z, before an operator restart to update Claude Code)

## Goal
Spec W (agent/plans/PLAN-ci-time-budget.md) P2 exit: every non-exempt CI job p90 <= 12 min over the last 10 completed PR runs; then T3.1 (flip check:ci-lane-budget gate:true), then P4. Branch 0923-1, PR #590, PR-TASK e87fa3ce.

## Where it stands
- PR head e7494d009 (renet 21c97b3); its CI run was in flight when the watch was stopped for the restart, and it keeps going on GitHub.
- Unpushed, held so a push does not cancel that run's P2 sample: 5f84e6061 (check-lane-budget localSearch terminates) and 23507f9db (Ceph/GPU P0 results). Renet has nothing unpushed.
- P2: only OPS Provision (linux-amd64, 3/4) is over, p90 13.4, from pre-fix runs 36493227271 and 36476055403; post-fix runs take 9.1-9.2, so 3-5 more PR runs age them out. K8s Multinode 20.4/25 and K8s Ceph 15.6/20 are inside their exemptions.
- check:ci-plan-implementation fails only on P-A1 open boxes (spec W, bake B4/B5/B7, Ceph/GPU P1-P7).
- Operator rulings 2026-09-29 in the babysit round log: macos-intel leg dropped (ff26e55f5), port Ceph/GPU to dnf/zypper, no libvirt on the devbox.

## Open decisions (operator)
- #197b5972 baked-image store: GitHub Free has 500 MB of private package storage and one bake is 5 x 1-2 GB. DEFAULT: private R2 bucket, B4/B5 move from oras to the R2 sync scripts.
- #e4482e2b PLAN-renet-ceph-gpu-non-apt D1-D8. DEFAULT: all eight as written; P0 showed OL10/Rocky 10 need CRB + EPEL.

## Next action
1. If the session id changed: `worklist.py --adopt <me> d778be9d`, else `worklist.py --migrate <me> d778be9d`.
2. `.ci/scripts/ci/ci-trace.py` for e7494d009; when final, rerun `GITHUB_TOKEN=$(gh auth token) PYTHONPATH=.ci python3 -m rediacc_ci.ci.budget_report --branch 0923-1 --limit 10 --status completed --json-out <f>`.
3. Receipt in /home/developer/pushclone-0923 on the local head, push the console, re-arm `ci-trace.py --wait --until-final --timeout 3h` in the background, lease #e412d363 #78a8573d #9c92f68f #7f148321 to its real task id.
4. Act on #197b5972 / #e4482e2b answers, or their DEFAULTs when the windows close.

## Push recipe
Receipt: in the pushclone, `git fetch -q /home/developer/console 0923-1 && git checkout -q -f FETCH_HEAD && git -c protocol.file.allow=always submodule update --init -q`, `npm run -s build`, `npm run -s check:ci-doc-region-parity`, `GITHUB_TOKEN=$(gh auth token) npm run ci:quick -- --receipt-out /home/developer/console/.ci/cache/prepush-receipt.json`; only check:ci-plan-implementation may fail. Push a changed submodule first as its own command, then `git push origin 0923-1`. After new tracked files or env-manifest names run `npx tsx scripts/gen/gen-docs.ts --write`; shebang scripts need `git update-index --chmod=+x`; tick plan boxes with `--plan-investigate` then `--plan-tick`.
