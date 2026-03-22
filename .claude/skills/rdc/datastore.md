# rdc datastore — Ceph RBD Datastore & Instant Fork

Manage datastore lifecycle: initialize Ceph-backed datastores, create instant zero-transfer forks, and clean up forks.

**Prerequisites**: Ceph cluster must be provisioned (`rdc ops up` with Ceph VMs), and worker machines must have `ceph-common` installed with `/etc/ceph/ceph.conf` and keyring in place. The ops provisioner handles this automatically. All commands run over SSH — see [SKILL.md prerequisites](SKILL.md#prerequisites-for-ops-vms-read-first) for SSH key configuration.

## Background

Each machine stores repositories on a **datastore** — a BTRFS filesystem mounted at `/mnt/rediacc/`. Two backends exist:

| Backend | Storage | Fork speed | Use case |
|---------|---------|------------|----------|
| `local` (default) | Loop-backed file (`/mnt/rediacc.pool`) | Slow (rsync transfer) | Single machines, no Ceph |
| `ceph` | RBD image on Ceph cluster | Instant (RBD snapshot + COW clone) | Multi-machine, testing, staging |

With Ceph, forking a 100GB datastore to another machine takes **< 2 seconds** (Ceph operation time) regardless of size. Total CLI wall time is ~4s including bootstrap overhead. Reads come from the shared RBD clone; writes go to a local COW (copy-on-write) overlay file.

## Commands

### Configure Ceph for a machine (one-time)

```
rdc config set-ceph -m <machine> --pool <pool> --image <image> [--cluster <name>]
```

Stores Ceph RBD configuration (pool, image name) in the machine's config. Required before `datastore init --backend ceph` or `datastore fork`. The `init` and `fork` commands read pool and image from this config automatically.

```bash
# Example: configure source machine (use the pool name from ops provisioner)
rdc config set-ceph -m rediacc11 --pool rediacc_rbd_pool --image ds-prod
```

On success, outputs: `Ceph config set for "rediacc11": pool=rediacc_rbd_pool, image=ds-prod`. The `--cluster` flag defaults to `ceph` and is rarely needed.

**Note**: The ops provisioner creates a pool named `rediacc_rbd_pool` by default (controlled by `CEPH_POOL_NAME` env var). Use that name, not `rbd`.

### Initialize a Ceph-backed datastore

```
rdc datastore init -m <machine> --backend ceph --size <size> [--image <name>] [--pool <name>] [--force]
```

Creates an RBD image, formats it as BTRFS, mounts at `/mnt/rediacc`, creates the directory structure, and installs a systemd unit for boot persistence.

When `--image` and `--pool` are omitted, they are read from the machine's ceph config (set via `config set-ceph`).

```bash
# If set-ceph was already called, just specify backend and size:
rdc datastore init -m rediacc11 --backend ceph --size 100G --force

# Or override image/pool explicitly:
rdc datastore init -m rediacc11 --backend ceph --size 100G --image ds-prod --pool rediacc_rbd_pool --force
```

**Use `--force`** if `setup-machine` already created a local datastore at `/mnt/rediacc` — it will be replaced. **WARNING: `--force` reformats the underlying storage (`mkfs.btrfs`). If the machine has deployed repos, this DESTROYS ALL REPOSITORY DATA. Only use `--force` on a fresh machine or when you intentionally want to wipe the datastore.** With `--force`, you may see a "No such file or directory" warning during RBD cleanup — this is expected when no prior RBD image exists and is safe to ignore.

On success, the init command prints a summary block:
```
=== Datastore Info ===
  Path: /mnt/rediacc
  Backend: ceph
  Type: btrfs
  Mounted: true
  RBD Image: rediacc_rbd_pool/ds-prod
  Total Size: 10.0 GB
  Used: 288.0 KB
  Available: 10.0 GB
```

**What happens internally**:
1. `rbd create <pool>/<image> --size N`
2. `rbd map <pool>/<image>` -> `/dev/rbd0`
3. `mkfs.btrfs /dev/rbd0`
4. Mount at `/mnt/rediacc`
5. Create `repositories/`, `mounts/` directories
6. Install systemd unit for auto-mount on boot

### Check datastore status

```
rdc datastore status -m <machine>
```

Shows backend type, size, usage, mount status. Output is JSON:

```json
{
  "type": "btrfs",
  "size": "10.0 GB",
  "used": "288.0 KB",
  "available": "10.0 GB",
  "path": "/mnt/rediacc",
  "mounted": true,
  "initialized": true,
  "backend": "ceph",
  "rbd_image": "rediacc_rbd_pool/ds-prod"
}
```

During an active fork, `cow_mode: true` is added and size fields reflect the COW overlay view (via `statfs` fallback when btrfs-progs can't query through the device-mapper layer).

### Fork a datastore (instant, zero transfer)

```
rdc datastore fork -m <source> --to <target> [--cow-size <size>]
```

**Requires**: Source machine must have a Ceph-backed datastore (verify with `datastore status` — `backend` should be `"ceph"`).

Creates an instant clone of the source machine's Ceph-backed datastore and mounts it with a COW overlay. The `--cow-size` flag sets the backing file size for writes (default: auto-sized, grows on demand as a sparse file). The fork runs on the **source machine** and creates:
1. An RBD snapshot of the source image (named `fork-<timestamp>`)
2. A protected clone from the snapshot (named `<image>-fork-<target>`)
3. A COW overlay mount (reads from RBD clone, writes to local sparse file)

```bash
# Fork rediacc11's datastore (names the clone "ds-prod-fork-rediacc12")
rdc datastore fork -m rediacc11 --to rediacc12
```

**Save the fork output** — it contains the snapshot name and clone name needed for unfork. The relevant lines appear at the end of the output, prefixed with the function name when streamed through the CLI:
```
[datastore_ceph_fork]   Snapshot: fork-1772969558
[datastore_ceph_fork]   Clone: ds-prod-fork-rediacc12
[datastore_ceph_fork]   Mount: /mnt/rediacc
```

Parse the values after `Snapshot: `, `Clone: `, and `Mount: ` (colon-space). The snapshot name format is `fork-<unix-timestamp>` (10 digits). The clone name format is `<image>-fork-<target>`. Match on the label substrings, ignoring the `[datastore_ceph_fork]` prefix.

**Do not fork to the same target twice without unforking first.** The clone name is deterministic (`<image>-fork-<target>`), so a second fork fails with `rbd: clone error: (17) File exists`. The fork rolls back the orphaned snapshot automatically, but wastes ~3s.

**Important**: The fork currently mounts on the source machine. Cross-machine fork mounting requires the target to have Ceph client access to the same cluster.

### Clean up a fork

```
rdc datastore unfork -m <machine> --source <image> --snapshot <name> --dest <clone> [--force]
```

All three identifiers are **required** — get them from the fork output:
- `--source`: the bare image name (e.g., `ds-prod`), **NOT** the pool-qualified name from `datastore status` (e.g., `rediacc_rbd_pool/ds-prod`). The pool is read from config automatically.
- `--snapshot`: the snapshot name (e.g., `fork-1772969558`)
- `--dest`: the clone image name (e.g., `ds-prod-fork-rediacc12`)

Cleans up in the correct order:
1. Unmount COW overlay
2. Remove RBD clone (`--dest`)
3. Unprotect snapshot
4. Remove snapshot

```bash
# Clean up using values from fork output
rdc datastore unfork -m rediacc11 \
  --source ds-prod \
  --snapshot fork-1772969558 \
  --dest ds-prod-fork-rediacc12 \
  --force
```

Use `--force` to continue cleanup even if individual steps fail. With `--force`, all four cleanup steps run regardless of individual failures. Common per-step errors:
- `umount: target is busy` — no COW overlay is active at the mount point (safe to ignore)
- `rbd: delete error: (2) No such file or directory` — clone already removed or never existed
- `rbd: unprotecting snap failed: (2) No such file or directory` — snapshot already removed
- `rbd: failed to remove snapshot: (2) No such file or directory` — snapshot already removed

The command exits with code 1 when any step fails, even if all resources are already clean. With all steps failing, the output shows `"unfork completed with errors: [...]"` — this means nothing was left to clean up.

On success, look for `"Unfork completed successfully — all resources cleaned up"` in the output. After unfork, the original RBD mount becomes visible again (it was never unmounted — the COW overlay was stacked on top of it). Run `datastore status` to confirm `mounted: true`, no `cow_mode` field, and that `size`/`used`/`available` fields reflect the original datastore.

## Typical workflow

Only the **source machine** needs ceph config. The `--to` machine name is used for clone naming only.

```bash
# 1. Configure Ceph on the source machine (one-time)
rdc config set-ceph -m rediacc11 --pool rediacc_rbd_pool --image ds-prod

# 2. Initialize Ceph datastore (one-time, reads image/pool from config)
rdc datastore init -m rediacc11 --backend ceph --size 100G --force

# 3. Deploy repos as usual
rdc repo up my-app -m rediacc11 --mount

# 4. Instant fork for testing (< 2 seconds, zero data transfer)
rdc datastore fork -m rediacc11 --to rediacc12
# Output: Snapshot: fork-1772969558, Clone: ds-prod-fork-rediacc12

# 5. Work on the fork — reads from Ceph, writes go to local COW
# All repos visible, data intact, writes isolated from production

# 6. Clean up when done (use exact names from fork output)
# --source is the BARE image name, not pool-qualified
rdc datastore unfork -m rediacc11 \
  --source ds-prod \
  --snapshot fork-1772969558 \
  --dest ds-prod-fork-rediacc12 \
  --force
```

## Infrastructure setup

### Ceph cluster provisioning

The ops provisioner creates Ceph VMs and bootstraps the cluster automatically:

```bash
# Full cluster: bridge (1) + workers (11, 12) + Ceph nodes (21, 22, 23)
rdc ops up
```

Environment variables for customization:

| Variable | Default | Description |
|----------|---------|-------------|
| `VM_CEPH_NODES` | `21 22 23` | Ceph node VM IDs |
| `VM_WORKERS` | `11 12` | Worker VM IDs |
| `CEPH_POOL_NAME` | `rediacc_rbd_pool` | Default RBD pool name |
| `CEPH_OSD_DEVICE` | `/dev/vdc` | OSD device path on Ceph nodes |
| `VM_CEPH_DISK_SIZE` | `32` | Secondary disk size (GB) for Ceph nodes |

After provisioning, workers automatically have `ceph-common` installed and `/etc/ceph/ceph.conf` + keyring configured. Full provisioning takes ~10-15 minutes (Ceph bootstrap alone is ~5 min).

### Verify Ceph connectivity

```bash
rdc datastore status -m <machine>
```

After init, the status output should show `"backend": "ceph"` and `"rbd_image": "<pool>/<image>"`. If it shows `"backend": "local"`, the Ceph datastore was not initialized. If init fails with Ceph errors, check that `/etc/ceph/ceph.conf` and the keyring exist on the worker (the ops provisioner installs these automatically).

## How fork works (technical)

Fork uses RBD layered cloning with a local COW overlay:

```
Source RBD image (read-write, production)
  +-- RBD snapshot (point-in-time, immutable)
       +-- RBD clone (thin copy, reads from snapshot)
            +-- Mapped read-only on machine -> /dev/rbd1
                 +-- Sparse COW file (/tmp/cowdata/*.cow)
                      +-- Loop device -> /dev/loop1
                           +-- Device mapper snapshot (origin=/dev/rbd1, cow=/dev/loop1)
                                +-- /dev/mapper/<clone>-cow
                                     +-- Mount at /mnt/rediacc (BTRFS)
```

**Reads**: Go through device mapper -> RBD clone -> Ceph cluster (cached locally)
**Writes**: Go to local COW sparse file (no network I/O)
**Storage**: COW file starts at 0 bytes, grows only with writes

## Troubleshooting

### "No such image" on fork
The source image name in `config set-ceph` must match the actual RBD image created by `datastore init`. Verify with `rdc datastore status -m <machine>` — the `rbd_image` field shows the `pool/image`.

### Unfork fails with "Device or resource busy"
The clone image still has the fork mounted. Ensure the COW mount is unmounted before removing the clone. Use `--force` to continue past errors. If a previous unfork failed partway, re-run with `--force` to clean up remaining resources.

### "Datastore already exists" on init
`setup-machine` creates a local datastore by default. Use `--force` to replace it with a Ceph-backed datastore.

### Wrong pool name
The ops provisioner creates a pool named `rediacc_rbd_pool` by default — not `rbd`. Verify with `rdc datastore status -m <machine>` — the `rbd_image` field shows `pool/image`. Or check the `CEPH_POOL_NAME` env var used during `ops up`.

### Ceph client config missing on workers
If `ops up` fails to configure Ceph clients, re-run `rdc ops up` — the provisioner relays config files through the host machine (not inter-VM SCP). The keyring at `/etc/ceph/` has 600 permissions; the provisioner stages it to `/tmp/` before download.

### "File exists" on fork
The clone name `<image>-fork-<target>` already exists from a previous fork. Unfork first, then re-fork. The fork will have created and rolled back a snapshot automatically — no manual cleanup needed.

### Fork mount conflicts
The fork mounts at `/mnt/rediacc` by default. If the machine already has a local datastore there, the fork will overlay it. Use separate machines for source and fork targets.

## Timing reference

Measured on ops VMs with a single Ceph node (rediacc21). CLI bootstrap overhead (~2s via `./run.sh`) is included in wall time but not in operation time.

| Command | Operation time | Wall time (dev) | Notes |
|---------|---------------|-----------------|-------|
| `config set-ceph` | instant | ~2s | Config-only, no remote call |
| `datastore init --backend ceph` | ~1.8s | ~4.4s | Creates RBD image, formats BTRFS, mounts, installs systemd unit |
| `datastore status` | ~150ms | ~2.6s | Single SSH command (Ceph backend reads sysfs for RBD info) |
| `datastore fork` | ~1.9s | ~4.3s | Snapshot + protect + clone + COW mount |
| `datastore unfork --force` | ~1.6–3.5s | ~4.1–5.9s | Unmount + remove clone + unprotect + remove snapshot. Higher with active Docker daemons. |

The fork and unfork operations are dominated by Ceph RPC round-trips (4 sequential calls each), not data transfer. Size of the datastore does not affect timing.
