# Hostinger runbook: branch renet install, restart cycle and repair (PLAN-health-checks-local H4-H7, H14)

Preconditions: fleet run 10 (`npm run vm:check -- --changed`) VERIFIED on the head being installed; the push done. Operator rulings: restarts are allowed and production data is never wiped (ASKED:2026-11-04T08:53Z); warnings are fixed automatically (2026-11-06); hub-owned volumes (`rediacc-hub-home-*`) are never pruned; `mail:pre-dms17` is kept until 2026-11-13.

State read on 2026-11-07T00:55Z (`REDIACC_NO_PROVISION=1 ./rdc.sh --config eu-bench machine health hostinger -o json`, exit 1): datastore 87%; repository db315abd-e300-47e4-bbb6-c383d6defe81 at 90%; 20 renet processes on `/usr/lib/rediacc/renet/0.0.0-dev/renet (deleted)` under `rediacc-docker-<net>` units; renet predates repository health checks.

Route (2026-11-07T03:05Z): eu-remote is stopped at the authenticator after this machine's address changed to 62.216.204.50 (#66d17658), so every machine step below runs with `--config eu-bench`, which reaches the same hostinger machine. Two reads differ: `backup usage` through eu-bench shows bench's store, not the eu store, so the production backup comparison waits for the eu-remote rebind; and backup schedule and strategy bind stay eu-remote only, never eu-bench.

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
12. Compare with steps 1-3: no repository missing, every backup lineage present, usage only lower.

## After
13. `H15`: `rdc machine repair hostinger --set-window 00:00-01:00` (the machine's maintenanceWindow).
14. Tick H4-H7, H14, H15 with the before/after files and each command's exit code; update #eb5c1323 and #22854bf1 (then backup schedule and strategy bind through eu-remote).
