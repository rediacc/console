# writers-now round, 2026-11-05

The signatures in this file and in the round's briefs are unreliable: the brief script paired the sorted `open_sigs` with file-order labels, so labels are right and signatures are shuffled. Read each signature from `worklist.py --plan-tick` or the parser before using it. No tick used these.

Sixteen first-wave writers returned with no commits: their boxes are live, post-merge, held by the edge and stable hold, or need an operator answer.

## Closing commands the lead owes

- `7692f2db` and every LP-hostinger: VERIFIED `npm run vm:check -- --changed`, then `worklist.py --live-proof <me> <plan> <sig> --write --tick`, after the operator answers the provisioning question below.
- `ef318b56` LP-bench (snapshot-read-io-cap): `npm run login:bench`, then `--live-proof`, account-smoke.
- backup-program K2 `4cd2aa89` and K11 `575e0098`: the cases exist in `26-backup-storage-cli.test.ts`, lines 961-1005 and 1216-1280, and have no live run. Run suite 26 with `BACKUP_STORAGE_SUITE=1` through e2e-local, then `live_proof record`.
- backup-program I3 `4174040a`: run `rediacc_ci.drills.backup_onprem` or cite it.
- backup-local-image V1 `129cdf9a`: VERIFIED vm:check, then `--config playwright.backup-storage.config.ts --test 26-backup-storage-cli --fail-on-skip`. L1 `339bf791`: the seven steps on an ops VM.
- token-ip-rebind T9 `ccc8658a`: `rdc config remote enable` from a second IP on bench, as the box names; the earlier evidence used `subscription status`.
- cloudflare-proxy Teardown `4ebc4d0b`: the box closes with the "Keep it and finish Phase 2" ruling at agent/plans/PLAN-cloudflare-proxy.md:16 once its clauses are read.
- production-key-only L1 `03025314`: the park runs right before the merge; K6 `23378074` follows it, and the gate goes red if it lands first.

## Code outside a writer's Owns

backup-program H8 `388c4a76` (renet and `vm_bake_key.py`), J9 `42f309b5` (`ct-tests.yml`), K10 `5330ae20` (new nightly job and seed script), and the A4d, J6 wiring checks. They need a brief with the right Owns.

## Findings

- PLAN-production-key-only D6 still says the production private key never reaches a public-PR job. PLAN-free-license R2 records the operator's choice to supersede it, and the key is step-scoped (`ct-tests.yml:495`) with fork PRs unsecreted. D6's text is stale; no leak.
- PLAN-snapshot-read-io-cap L2's earlier pass moved 0 bytes, so it proves neither the read cap nor the upload. It needs a run that reads and uploads.
- `/tmp/scr/seed.sh` is named by L2 and exists only on the machine that made it: a plan box resting on an untracked script.
- `./run.sh worktree gc` listed trees of running writers as DELETE, "every rule holds", when they had not yet started a process. Global `gc --write` during a round can delete a live writer's tree; collect by `--id` after its report.

## Operator questions

1. Provision the branch renet on hostinger through eu-bench for the LP-hostinger receipts, once vm:check is VERIFIED? It restarts the router and daemons. Recommended: yes.
2. May the session insert and then remove a source-scoped iptables DROP on port 22 on the bench test machine for E9's blackhole leg? Recommended: yes.
3. Which machine takes sandbox-tenant-separation H1, and when? Recommended: one eu-bench machine, once a renet with D1-D5 is on it.

## Writer 07, stop-hook-one-plan SC13b

- SC13b `b1540084` closes only on a real stop after the next merge.
- The hook's `V_LOOP_NEXT_MERGED` arm has no match in any transcript: `/pr-merge` checks out main before the stop, so the `on-main` arm fires instead. The merged arm has only mocked coverage. Recommended at the next merge: stop once on the branch before step 6.
- The plan writes its pytest acceptance as `python3 -m pytest`, which exits 1 here; the pinned binary is `.ci/cache/toolchain/uv-tools/bin/pytest`.
- QUEUE.md `## In flight` reads a merge phase on PR #602, branch 1023-1, past its 24-hour limit while the live branch is 1104-1. Not investigated.
