# rdc datastore — Named, Movable Storage Pools

Create named datastores, attach them to machines, snapshot them, and fork them
copy-on-write.

**Prerequisites**: the `rbd` backend needs a Ceph cluster (`rdc ops up` with Ceph VMs), and
worker machines must have `ceph-common` installed with `/etc/ceph/ceph.conf` and keyring in
place. The ops provisioner handles this automatically. All commands run over SSH; see
[SKILL.md prerequisites](SKILL.md#prerequisites-for-ops-vms-read-first) for SSH key
configuration.

## Background

A **datastore** is a named storage pool that holds repositories. It is:

- **Mobile**: attach it to a machine, then move it to another.
- **Single-mounter**: exactly one machine holds it at a time.

Each machine also has an implicit default datastore (a BTRFS pool file at
`/mnt/rediacc.pool`). That one is not managed by this noun; `rdc datastore` only manages
the additional, named ones.

| Backend | Storage | Fork | Use case |
|---------|---------|------|----------|
| `local` (default) | File-backed pool on that one machine | **Not supported** | Single machines, no Ceph |
| `rbd` | RBD image on a Ceph cluster | Instant (RBD snapshot + CoW clone) | Multi-machine, testing, staging |

A `local` datastore has no block-level clone primitive, so it **cannot fork at all**, not
even on its own machine. Repositories inside it fork one at a time by BTRFS reflink instead
(`rdc repo fork`). With `rbd`, forking a 100GB datastore is instant and its cost does not
grow with the size of the pool.

Refs follow the same grammar as repos: `name` for the datastore, `name:tag` for a fork
(e.g. `ds-prod:exp`).

## Commands

### Create a datastore

```
rdc datastore create <datastore> -m <machine> --size <size> [--backend local|rbd] [--pool <name>] [--image <name>] [--cluster <name>]
```

`-m` is required: the datastore does not exist yet, so there is no attachment to derive the
machine from. `--backend` defaults to `local`.

- `--pool` (rbd only): Ceph pool. Defaults to `rbd`. **The ops provisioner creates a pool
  named `rediacc_rbd_pool`, not `rbd`**, so pass it explicitly.
- `--image` (rbd only): RBD image name. Defaults to the datastore name.
- `--cluster`: makes this a kubernetes-world datastore, bound to that cluster. Set means
  kubernetes repositories only; unset means docker repositories only. **Fixed at creation.**

```bash
# rbd-backed datastore on the ops Ceph cluster
rdc datastore create ds-prod -m rediacc11 --backend rbd --size 100G --pool rediacc_rbd_pool

# plain local pool
rdc datastore create ds-scratch -m rediacc11 --size 50G
```

A newly created datastore is **detached**. Attach it before using it.

### Attach / detach

```
rdc datastore attach <datastore> --to <machine> [--writes local|ceph] [--cow-size <size>] [--no-auto] [--force]
rdc datastore detach <datastore> [--discard]
```

Exactly one machine holds a datastore at a time, so attaching it somewhere else **moves**
it: the old holder gives it up first, and a failed hand-off leaves the original attachment
intact.

- `--writes` is **required for a fork** and rejected for a non-fork. See "Fork" below.
- `--no-auto`: do not re-attach on boot.
- `--force`: fence a stale holder that did not give the datastore up cleanly.
- `detach --discard`: throw away a `--writes local` fork and its overlay. Not recoverable.

```bash
rdc datastore attach ds-prod --to rediacc11
rdc datastore detach ds-prod
```

### Fork a datastore (instant, zero transfer)

```
rdc datastore fork <datastore> --tag <tag> [--attach-to <machine>] [--writes local|ceph] [--cow-size <size>]
```

Requires the `rbd` backend. The result is named `<datastore>:<tag>` and is **detached** unless
you pass `--attach-to`.

A fork must say where its writes go, and the two answers have opposite durability:

| `--writes` | Where writes land | Durability |
|------------|-------------------|------------|
| `local` | Local sparse overlay file on the holding machine | **Ephemeral.** Lost on detach; detaching needs `--discard`. |
| `ceph` | A durable clone in the Ceph pool | Persistent. |

`--cow-size` sets the overlay size for `--writes local` (default: auto-sized, grows on
demand as a sparse file).

```bash
# Fork ds-prod and hand the fork straight to another machine, ephemeral writes
rdc datastore fork ds-prod --tag exp --attach-to rediacc12 --writes local

# Fork detached, attach later with durable writes
rdc datastore fork ds-prod --tag staging
rdc datastore attach ds-prod:staging --to rediacc12 --writes ceph
```

### Cleaning up a fork

There is no `datastore unfork`. Undo depends on how the fork's writes were disposed:

```bash
# --writes local: detaching destroys the overlay, so it must be explicit
rdc datastore detach ds-prod:exp --discard

# --writes ceph: detach, then destroy the clone
rdc datastore detach ds-prod:staging
rdc datastore delete ds-prod:staging
```

### Snapshots

```
rdc datastore snapshot create <datastore> [--snapshot <label>]
rdc datastore snapshot list <datastore>
```

Nothing stops to take a snapshot. A snapshot costs nothing at rest and is what a fork
clones from. The label defaults to a UTC timestamp.

### Status and listing

```
rdc datastore status <datastore>
rdc datastore list [<place>]
```

`status` shows backend, attachment, usage, repositories, and snapshots. A detached datastore
still reports its record. `list` shows every named datastore, where it is attached, and what
it holds; the optional `<place>` narrows to one cluster or one machine.

### Resize

```
rdc datastore resize <datastore> --size <size>
```

Grow or shrink. This is an **offline** operation: the repositories inside the datastore must
be stopped first.

### Delete

```
rdc datastore delete <datastore> [--force]
```

Destroys the datastore and everything in it. It detaches first; if it will not detach
cleanly, the delete fails rather than orphaning a mounted pool. `--force` deletes even though
repositories still point at it (their data goes with it).

## Typical workflow

```bash
# 1. Create an rbd-backed datastore (one-time)
rdc datastore create ds-prod -m rediacc11 --backend rbd --size 100G --pool rediacc_rbd_pool

# 2. Attach it to the machine that will hold it
rdc datastore attach ds-prod --to rediacc11

# 3. Deploy repos into it
rdc repo create my-app -m rediacc11 --datastore ds-prod --size 5G
rdc repo up my-app

# 4. Instant fork for testing (zero data transfer), handed to a second machine
rdc datastore fork ds-prod --tag exp --attach-to rediacc12 --writes local

# 5. Work on the fork: reads come from the Ceph clone, writes go to the local overlay,
#    production is untouched

# 6. Throw the experiment away
rdc datastore detach ds-prod:exp --discard
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

After provisioning, workers automatically have `ceph-common` installed and
`/etc/ceph/ceph.conf` + keyring configured. Full provisioning takes ~10-15 minutes (Ceph
bootstrap alone is ~5 min).

### Verify Ceph connectivity

```bash
rdc datastore status <datastore>
```

The status output should report the `rbd` backend and the `pool/image` it maps to. If Ceph
errors appear, check that `/etc/ceph/ceph.conf` and the keyring exist on the worker (the ops
provisioner installs these automatically).

## How fork works (technical)

Fork uses RBD layered cloning. With `--writes local`, a device-mapper snapshot stacks a local
sparse overlay on top of the read-only clone:

```
Source RBD image (read-write, production)
  +-- RBD snapshot (point-in-time, immutable)
       +-- RBD clone (thin copy, reads from snapshot)
            +-- Mapped read-only on the holding machine -> /dev/rbdN
                 +-- Sparse overlay file
                      +-- Loop device
                           +-- Device mapper snapshot (origin=clone, cow=overlay)
                                +-- Mount (BTRFS)
```

**Reads**: through device mapper -> RBD clone -> Ceph cluster (cached locally)
**Writes** (`--writes local`): to the local sparse overlay, no network I/O, discarded on detach
**Writes** (`--writes ceph`): to a durable clone in the pool
**Storage**: the overlay starts at 0 bytes and grows only with writes

## Troubleshooting

### "cannot fork a local datastore"
The `local` backend has no block-level clone primitive. Either create the datastore with
`--backend rbd`, or fork the individual repositories inside it with `rdc repo fork`.

### Attach refuses a fork without `--writes`
A fork's writes have to go somewhere, and `local` vs `ceph` have opposite durability. The
CLI refuses to guess. Pass `--writes local` (ephemeral) or `--writes ceph` (durable).

### Detach refuses a `--writes local` fork
Its overlay has nowhere to be written back to, so detaching destroys it. Confirm with
`--discard`.

### Wrong pool name
The ops provisioner creates a pool named `rediacc_rbd_pool` by default, not `rbd`, which is
what `--pool` defaults to. Pass `--pool rediacc_rbd_pool` at `datastore create`, or check the
`CEPH_POOL_NAME` env var used during `ops up`.

### Ceph client config missing on workers
If `ops up` fails to configure Ceph clients, re-run `rdc ops up`. The provisioner relays
config files through the host machine (not inter-VM SCP). The keyring at `/etc/ceph/` has 600
permissions; the provisioner stages it to `/tmp/` before download.

### A stale holder will not give the datastore up
Attaching elsewhere detaches the old holder first. If that machine is unreachable or left the
pool mounted, `rdc datastore attach <ds> --to <machine> --force` fences it.
