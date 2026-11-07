# Hostinger runbook: branch renet install, restart cycle, repair and maintenance window (PLAN-health-checks-local H4-H7, H14, H15)

Preconditions: fleet run 10 (`npm run vm:check -- --changed`) VERIFIED on the head being installed; the push done. Operator rulings: restarts are allowed and production data is never wiped (ASKED:2026-11-04T08:53Z); warnings are fixed automatically (2026-11-06); hub-owned volumes (`rediacc-hub-home-*`) are never pruned; `mail:pre-dms17` is kept until 2026-11-13.

State read on 2026-11-07T00:55Z (`REDIACC_NO_PROVISION=1 ./rdc.sh --config eu-remote machine health hostinger -o json`, exit 1; the command actually run, before eu-remote's address changed): datastore 87%; repository db315abd-e300-47e4-bbb6-c383d6defe81 at 90%; 20 renet processes on `/usr/lib/rediacc/renet/0.0.0-dev/renet (deleted)` under `rediacc-docker-<net>` units; renet predates repository health checks.

Route (updated 2026-11-07T08:27Z): the operator rebound eu-remote after this machine's address changed to 62.216.204.50 (#66d17658), so eu-remote works again. Machine steps run with `--config eu-bench` or `--config eu-remote`, which reach the same hostinger machine. `backup usage`, `backup schedule` and `backup strategy bind` run with `--config eu-remote` only, because eu-bench's store is bench's and not the eu store.

## Before (record each, compare after every step)
1. `REDIACC_NO_PROVISION=1 ./rdc.sh --config eu-bench repo list -m hostinger -o json > before-repos.json`
2. `REDIACC_NO_PROVISION=1 ./rdc.sh --config eu-remote backup usage -o json > before-usage.json`
3. `REDIACC_NO_PROVISION=1 ./rdc.sh --config eu-bench machine health hostinger -o json > before-health.json`

## H4: install the branch renet
4. `./rdc.sh --config eu-bench machine setup hostinger` (uploads the committed branch renet; a dirty renet tree is refused).
5. Re-read health (step 3): the "predates repository health checks" warning is gone; `repo_health` lists every repo.

## H5-H7: restart cycle, one repo at a time
6. For each repo except mail and observability: `./rdc.sh --config eu-bench machine restart-services hostinger --include-docker --repo <name>`, then re-read health and confirm that repo's replaced-binary pids are gone and its containers are up.
7. mail only inside 00:00-01:00Z: `... --repo mail`, then the mail checks (Postfix queue, 465 banner).
8. observability last, and only when no other session holds a live lease or STATE.md on it.
9. After the cycle: `stale_binary` is empty in `machine health -o json`.

## H14: repair, dry run first
10. `./rdc.sh --config eu-bench machine repair hostinger --dry-run -o json`: read the planned actions; every action is auto-safe or auto-with-backup, none touches a hub volume.
11. `./rdc.sh --config eu-bench machine repair hostinger -o json` (adds `--with-backup` only if an auto-with-backup action is listed): expect a trim for the datastore and for db315abd; the run re-checks after each action.
12. Compare with steps 1-3: no repository missing, every backup lineage present, usage only lower (`backup usage` read through `--config eu-remote`, as in step 2).

## After
13. Set the machine's maintenanceWindow (plan step H15): `./rdc.sh --config eu-bench machine repair hostinger --set-window 00:00-01:00`. The text `H15` is only a tracking label for this step and is not part of the command.
14. Tick H4-H7, H14, H15 with the before/after files and each command's exit code, and update the tracking issues #eb5c1323 and #22854bf1. Then run `./rdc.sh --config eu-remote backup schedule -m hostinger`, and `./rdc.sh --config eu-remote backup strategy bind ...` only where the strategy does not already cover a new repository.
