---
title: "Monitoring"
description: "Monitor machine health, containers, services, repositories, and run diagnostics."
category: "Guides"
tags:
  - operations
subcategory: operations
order: 9
language: en
---

# Monitoring

Rediacc ships monitoring commands for machine health, running containers, services, repository status, and system diagnostics.

## Machine Health

Get a full health report for a machine:

```bash
rdc machine health server-1
```

This reports:
- **System**: uptime, memory (warning above 80%, error above 90%), disk and datastore usage (warning above 85%, error above 95%)
- **Containers**: running, healthy, unhealthy counts; a container in a `Restarting` loop is critical
- **Services**: failed systemd units (an error) and units that keep restarting (critical)
- **Storage**: SMART health status (a failing disk is critical) and disk temperature
- **Repositories**: autostart repositories that are not mounted, and each repository's filesystem usage (warning above 85%, error above 95%)
- **Backups**: repositories not backed up in over 10 days, behind their schedule or target, or whose last verify failed
- **Licenses**: expired, missing, mismatched or invalid repository licenses, and licenses due for refresh
- **Renet processes**: daemons still running a replaced renet binary
- **Repository health**: each mounted repository's own `health()` result (see below)
- **Certificates**: the proxy's certificates close to expiry, and shared ACME challenge CNAMEs
- **Issues**: identified problems

The exit code is the verdict: `0` healthy, `1` warning, `2` error, `3` critical (a failing disk, or a container or service in a restart loop). Use `--output json` for machine-readable output; it carries `repo_health` (one report per repository) and `findings`, each with a code, a severity (`info`, `warning`, `error` or `critical`), a subject, a detail and, where a fix exists, `fix` (see [Repair](#repair)).

## Repository Health

A Rediaccfile can define a `health()` function that checks the repository's own services ([Services](/en/docs/services)): exit `0` ok, `1` warning, `2` error. Run it for one repository:

```bash
rdc repo health my-app@server-1
```

The command exits with the worst level across the repository's Rediaccfiles. A repository where no Rediaccfile defines `health()` prints **no check** and exits `0`; it is never reported as healthy. A `health()` that times out, is killed or exits with any other code is an error, and so is a failure to reach the machine (exit `2`).

`rdc machine health` runs every mounted repository's `health()` in one call and folds the worst level into its own exit code, with one finding per repository at warning (`repo.health.warning`) or error (`repo.health.error`). Repositories without a check are listed, not reported. When the machine's renet predates repository health checks, the result is one warning, `renet.repo-health.unsupported`, until `rdc machine setup` updates it.

## Certificate Expiry and ACME Challenges

`rdc machine health` reads the proxy's ACME certificates and reports `cert.expiry.near` for each one under 21 days from expiry (a warning) or under 7 days (an error). The proxy renews 30 days ahead, so a certificate under 21 days means its renewal has failed for at least nine days.

It also reports `acme.challenge.cname-shared` when the `_acme-challenge.<name>` record of a certificate name follows a CNAME to a name that is not itself an `_acme-challenge.` name, or when two names end at the same name. A wildcard record that is a CNAME produces this shape: every challenge lands on one name and the renewals collide. A deliberate delegation (for example `_acme-challenge.mail.example.com` pointing at `_acme-challenge.mail.example.io`) is not reported; list any other intended delegation in `ACME_DELEGATED_NAMES` (a comma list of certificate names) in the proxy's `config.env`.

## Repair

Every finding carries a code, and where a safe fix exists, a `fix` with an `action`, a safety `class` and `window_only`. `rdc machine health` stays read-only; `rdc machine repair` is the command that acts:

```bash
rdc machine repair server-1 --dry-run     # list what would run
rdc machine repair server-1               # run the auto-safe fixes, then re-check
rdc machine repair server-1 --code cert.expiry.near
```

| Class | Meaning |
|---|---|
| `auto-safe` | Runs by default: restart a container or Traefik, trim and prune, write the ACME anchor |
| `auto-with-backup` | Runs only with `--with-backup`, after a successful snapshot of the repository; a failed snapshot cancels the fix |
| `operator-only` | Never runs. The command prints the exact command to run by hand. Everything that deletes named data or spends money is here |

`window_only` is a condition on top of the class: the fix runs only inside the machine's maintenance window, `HH:MM-HH:MM` in UTC (it may wrap midnight). A machine without a window never runs these fixes on its own; `--window-override` runs them by hand. Set or clear the window with:

```bash
rdc machine repair server-1 --set-window 00:00-03:00
rdc machine repair server-1 --set-window off
```

Each fix first checks that its finding is still there, so a second run reports nothing to do. Fixes that act on the same thing run once (one Traefik restart covers every certificate). Each fix is logged to the machine journal with the tag `rediacc-repair` and in the JSON `actions` (`code`, `subject`, `action`, `class`, `result`, `before`, `after`), and the run ends with a full re-check. The exit code is `0` when nothing is left, `1` when warnings or operator-only items are left, and `2` when an error is left or a fix failed.

| Finding | Fix | Class |
|---|---|---|
| `datastore.usage.high`, `repo.disk.high` | Trim, then prune stopped containers, anonymous dangling volumes and unused images | auto-safe |
| `container.unhealthy`, `container.restart-loop` | Restart the container | auto-safe |
| `renet.binary.replaced` | Restart the affected repository supervisors (`rdc machine restart-services --include-docker`, scoped to them) | auto-safe, window only |
| `cert.expiry.near` | Restart Traefik so it retries the renewal | auto-safe |
| `acme.challenge.cname-shared` | Write the ACME anchor (below) | auto-safe |
| `repo.health.warning`, `repo.health.error` | Run the repository's `repair()` ([Services](/en/docs/services)) | the class the Rediaccfile declares |
| `repo.unmounted`, `service.failed`, `service.restart-loop`, `backup.*`, `license.*`, `renet.repo-health.unsupported` | Printed as the command to run | operator-only |

Findings with no fix (SMART failures, temperature, memory, the system disk, a failed verify) are reported and left to the operator.

The prune never touches the hub: containers labelled `rediacc.hub.*` and volumes labelled `rediacc.hub.user` or named `rediacc-hub-home-*` are excluded, so a hub user's home survives every reclaim. A residue that trim and prune cannot free (named volumes, large application data) stays an operator decision.

### Repository repair

```bash
rdc repo repair my-app@server-1 --dry-run
rdc repo repair my-app@server-1
```

`rdc repo repair` runs the repository's `repair()` functions with the same classes: `auto-safe` runs, `auto-with-backup` needs `--with-backup`, and an undeclared (`operator-only`) `repair()` runs only after its prompt is answered or with `--yes`. `health()` runs again afterwards, and the exit code follows the level it ends at: `0` ok or no check, `1` warning, `2` error or a failed `repair()`.

### The ACME anchor

A wildcard DNS record that is a CNAME makes every `_acme-challenge.<host>` name follow it, so all challenges land on one name and the renewals collide (`acme.challenge.cname-shared`). The fix writes a TXT record with the value `rediacc-acme-anchor` at each colliding `_acme-challenge.<name>` through the proxy's Cloudflare token, then restarts Traefik. An explicit record takes the name out of the wildcard's reach, so the challenge lands where it belongs. The fix only adds records, and an existing anchor is left as it is.

Names listed in `ACME_DELEGATED_NAMES` (a comma list of certificate names in the proxy's `config.env`) are deliberate delegations: they are never anchored and never reported. When the proxy has no usable Cloudflare token, the fix falls back to `LEGO_DISABLE_CNAME_SUPPORT=true` in `config.env`, but only when no delegated name is declared, because that variable switches CNAME following off for every name; with a delegation declared, the finding stays operator-only. The same fix runs at every proxy install (`rdc machine infra push`), and on its own with `renet proxy acme-fix` on the machine.

## List Containers

View all running containers across all repositories on a machine:

```bash
rdc machine status server-1 --containers
```

| Column | Description |
|--------|-------------|
| Name | Container name |
| Status | Uptime or exit reason |
| State | Running, exited, etc. |
| Health | Healthy, unhealthy, none |
| CPU | CPU usage percentage |
| Memory | Memory usage / limit |
| Repository | Which repository owns the container |

Options:
- `--health-check`, Perform active health checks on containers
- `--output json`, Machine-readable JSON output

JSON output includes full container details (`labels`, `port_mappings`, `image`, `id`) plus `repository` (resolved name), `repository_guid` (original GUID), `domain`, and `autoRoute`.

## List Services

View systemd services related to Rediacc on a machine:

```bash
rdc machine status server-1 --services
```

| Column | Description |
|--------|-------------|
| Name | Service name |
| State | Active, inactive, failed |
| Sub-state | Running, dead, etc. |
| Restarts | Restart count |
| Memory | Service memory usage |
| Repository | Associated repository |

Options:
- `--stability-check`, Flag unstable services (failed, >3 restarts, auto-restart)
- `--output json`, Machine-readable JSON output

JSON output includes full service details with `repository` (resolved name) and `repository_guid` (original GUID).

## List Repositories

View repositories on a machine with detailed stats:

```bash
rdc machine status server-1 --repositories
```

| Column | Description |
|--------|-------------|
| Name | Repository name |
| Size | Disk image size |
| Mount | Mounted or unmounted |
| Docker | Docker daemon running or stopped |
| Containers | Container count |
| Disk Usage | Actual disk usage within the repository |
| Modified | Last modification time |

Options:
- `--search <text>`, Filter by name or mount path
- `--output json`, Machine-readable JSON output

JSON output includes `name` (resolved) and `guid` (original GUID), and nests each repository's `containers` (with `domain`, `autoRoute`, `repository`/`repository_guid`) and `services` arrays.

## Storage Health

Inspect BTRFS fragmentation and reflink sharing across all repositories on a machine:

```bash
rdc machine status server-1 --storage-health
```

| Column | Description |
|--------|-------------|
| Quota | The repository's maximum size (its growth ceiling, set at creation or by resize/auto-grow) |
| Allocated | What the sparse image actually occupies in the pool right now |
| Unique | Actual unique data owned only by this repo |
| Shared | Data blocks reused across repos via BTRFS reflinks (free copies) |
| Reclaimable | The allocated-vs-used gap that [`repo trim`](/en/docs/repositories#reclaim-space-trim) can return to the pool. Shows `-` for unmounted repos |
| Discards | Whether the encrypted volume passes discards through (`on` for any repository mounted by a current version) |
| Divergence | Percent of the image unique to this repo rather than shared (higher means more reclaimable if deleted) |
| Frag | Extents per GB in the copy-on-write image (informational only) |

Quota and allocation are different numbers on purpose: a repository with a 20 GB quota that stores 6 GB of data only costs the pool what it has allocated. The pool can therefore promise more total quota than it physically has, and the Reclaimable column shows how much of each repository's allocation is no longer used and can be trimmed back.

Below the table, a pool summary reports the datastore fill level and how much space backup snapshots are pinning:

```
Pool: 265.4 GB used, 95.2 GB free (73.6% full)
Backup snapshots pin 2.1 GB (1 active, 0 stale; stale ones are removed by 'rdc machine prune')
```

While a backup runs, its snapshot keeps referencing every block it shares with live repositories, so deletions and trims free less pool space until that backup cycle finishes. Stale snapshots from interrupted backups are removed automatically by the storage maintainer within minutes.

The summary shows total savings from BTRFS reflinks:

```
14 repos, 224.3 GB virtual size
Unique data: 323.7 MB | Shared: 224.0 GB | Efficiency: 99.9%
```

- **Virtual size** is the sum of all repo image sizes. This is what the repos look like, but it double-counts blocks shared via reflinks.
- **Unique data** is the actual storage consumed by repo data that exists in only one repo. This is what you would free by deleting a repo.
- **Shared** is data reused across repos via BTRFS reflinks. Forking a repo creates reflink copies that share blocks until either side writes new data, at which point blocks diverge.
- **Efficiency** is the percentage of data reused via reflinks. Higher is better. A machine with many forks from the same parent will show near-100% efficiency.

The Frag column is informational. It counts extents of the copy-on-write image file, not the files your application reads inside it, so it reads high under normal random-write workloads (databases, container layers) and does not predict read performance on SSD-backed storage. Rediacc deliberately offers no defragment command: `btrfs filesystem defragment` unshares reflinked forks and snapshots, which on a near-full pool can inflate usage dramatically while benchmarks show no measurable read gain. For the full measurements and reasoning, see [Your Fragmentation Number Looks Terrifying. I Benchmarked What It Costs.](/en/blog/i-benchmarked-btrfs-fragmentation).

The scan runs in parallel and takes 5-15 seconds depending on the number and size of repos. When `--storage-health` is not specified, a one-line hint appears after the query output as a reminder.

## BTRFS Scrub

Rediacc automatically schedules a weekly BTRFS scrub on every machine. The scrub reads every data block on the datastore, verifies checksums, and reports any corruption. This catches silent data corruption (bitrot) before it propagates to backups and forks.

The scrub runs every Sunday at 02:00 local time (machine timezone) with a randomized delay of up to 1 hour. It runs at the lowest I/O priority (`ionice idle`, `nice 19`) so it does not interfere with running services. On SSD-backed machines, expect roughly 8 minutes per 100 GB of datastore.

The scrub timer is installed automatically on the first daemon start after a renet upgrade. When the scrub policy changes in a future renet version, it updates itself on the next daemon start with no user action needed.

### Scrub status

The result of the last scrub is saved outside the BTRFS volume (at `/var/lib/rediacc/scrub-last-result.json`) so it remains readable even if the volume has issues. The `rdc machine status --system` output includes a `scrub_status` field:

```json
"scrub_status": {
  "last_run_human": "3 days ago",
  "status": "ok",
  "total_errors": 0,
  "uncorrectable": 0,
  "duration_seconds": 312
}
```

| Status | Meaning |
|--------|---------|
| `ok` | Last scrub completed with no errors |
| `never_run` | Scrub has not run yet (timer was just installed) |
| `overdue` | Last scrub was more than 14 days ago |
| `errors_found` | Scrub found checksum mismatches (check the `total_errors` and `uncorrectable` counts) |
| `failed` | Scrub process exited with a non-zero code |

If `uncorrectable` is greater than zero, the affected blocks cannot be repaired automatically (single-disk BTRFS has no redundant copy). Restore the affected repository from the most recent backup.

### Manual scrub

To run a scrub immediately (e.g. after a power failure or disk migration):

```bash
rdc term connect server-1 -c "sudo renet maintenance scrub --datastore /mnt/rediacc"
```

The result is saved to the same JSON file and immediately visible in the next `rdc machine status --system`.

## Machine Overview

Get a complete overview of a machine including deployment information:

```bash
rdc machine status server-1
```

This provides:
- Hostname and uptime
- Memory, disk, and datastore usage
- Total repositories, mounted count, Docker daemon running count
- Detailed per-repository information

Use `--output json` for machine-readable output.

## Test Connection

Verify SSH connectivity to a machine:

```bash
rdc term connect server-1 -c "hostname"
```

The command prints the remote hostname on success and a connection error
otherwise, which verifies DNS, the SSH port, and key authentication in one
step.

## Diagnostics (doctor)

Run a full diagnostic check of your Rediacc environment:

```bash
rdc doctor
```

| Category | Checks |
|----------|--------|
| **Environment** | Node.js version, CLI version, SEA mode, Go installation, Docker availability |
| **Renet** | Binary location, version, CRIU, rsync, SEA embedded assets |
| **Configuration** | Active config, adapter, machines, SSH key |
| **Virtualization** | Checks if your system can run local virtual machines (`rdc ops`) |

Each check reports **OK**, **Warning**, or **Error**. Use this as a first step when troubleshooting any issue.

Exit codes: `0` = all passed, `1` = warnings, `2` = errors.

## Service Readiness Checks

During `repo up`, renet waits for HTTP services to accept connections before declaring them ready. The wait is health-check aware:

- Containers that Docker reports **healthy** are trusted immediately, with no TCP probe.
- Containers still inside their health check's `start_period` log an informational note, not a warning; the proxy keeps retrying until they bind.
- Compose services with no running container (for example, behind an inactive profile) are skipped.
- Everything else is probed over TCP for up to 15 seconds (set `REDIACC_READINESS_TIMEOUT`, in seconds, to change this).

Defining a [Docker health check](https://docs.docker.com/reference/dockerfile/#healthcheck) on slow-booting services gives renet an authoritative ready signal and removes probe noise from deploy output.
