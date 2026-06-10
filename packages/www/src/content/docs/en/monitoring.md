---
title: "Monitoring"
description: "Monitor machine health, containers, services, repositories, and run diagnostics."
category: "Guides"
order: 9
language: en
---

# Monitoring

Rediacc ships monitoring commands for machine health, running containers, services, repository status, and system diagnostics.

## Machine Health

Get a full health report for a machine:

```bash
rdc machine health --name server-1
```

This reports:
- **System**: uptime, disk usage, datastore usage
- **Containers**: running, healthy, unhealthy counts
- **Storage**: SMART health status
- **Issues**: identified problems

Use `--output json` for machine-readable output.

## List Containers

View all running containers across all repositories on a machine:

```bash
rdc machine containers --name server-1
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
rdc machine services --name server-1
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
rdc machine repos --name server-1
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
rdc machine query --name server-1 --storage-health
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

The result of the last scrub is saved outside the BTRFS volume (at `/var/lib/rediacc/scrub-last-result.json`) so it remains readable even if the volume has issues. The `rdc machine query --system` output includes a `scrub_status` field:

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
rdc term connect -m server-1 -c "sudo renet maintenance scrub --datastore /mnt/rediacc"
```

The result is saved to the same JSON file and immediately visible in the next `rdc machine query --system`.

## Vault Status

Get a complete overview of a machine including deployment information:

```bash
rdc machine vault-status --name server-1
```

This provides:
- Hostname and uptime
- Memory, disk, and datastore usage
- Total repositories, mounted count, Docker running count
- Detailed per-repository information

Use `--output json` for machine-readable output.

## Test Connection

> **Cloud adapter only.** In local mode, use `rdc term connect -m server-1 -c "hostname"` to verify connectivity.

Verify SSH connectivity to a machine:

```bash
rdc machine test-connection --ip 203.0.113.50 --user deploy
```

Reports:
- Connection status (success/failed)
- Authentication method used
- SSH key configuration
- Public key deployment status
- Known hosts entry

Options:
- `--port <number>`, SSH port (default: 22)
- `--save -m server-1`, Save verified host key to machine config

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
