# Tier proposal: all 154 pending functions, for bulk approval

`private/renet/pkg/license/tiermap.go` holds 162 registered bridge functions.
**8 are decided, 154 carry `pending: true`.** A pending entry evaluates to
`TierNone` today, exactly as the old `default:` did, so nothing here changes
behaviour until it is approved and applied. That is the point: the 154 are
visible and countable rather than silently free.

This proposes a tier for every one of them. Approve, amend, or reject by group.

---

## The four tiers, and what the existing 8 already establish

From `runtime.go:94-104`:

| Tier | Meaning |
|---|---|
| `TierNone` | No licence check at all. |
| `TierRepoLicenseCreate` | Validates a pre-issued repo licence; identity proofs skipped because the entity does not exist yet. |
| `TierRepoLicenseFull` | Full validation **including expiry**. |
| `TierRepoLicenseOperate` | Validation with **expiry skipped**. |

The 8 decided entries are not arbitrary; they encode a principle worth stating
explicitly, because every proposal below follows it:

- `repository_create`, `repository_fork` -> **Create**. New licensed entity.
- `repository_expand`, `repository_resize` -> **Full**. These GROW capacity,
  which is the thing being sold, so expiry must bite.
- `repository_up`, `repository_up_all` -> **Operate**. Running something that
  already exists must not break the day a licence lapses.
- `repository_delete`, `repository_down` -> **None**. You must never be locked
  out of stopping or removing your own data.

**The customer must never be trapped.** Stop, remove, inspect and diagnose stay
free in every group below. An expired licence should block growth and new
creation, not hold a running system hostage or prevent an exit.

---

## Proposal by group

### ceph (38) -- the storage substrate

| Functions | Tier | Why |
|---|---|---|
| `ceph_health`, `ceph_cluster_status`, `ceph_cluster_dashboard`, `ceph_image_info`, `ceph_image_list`, `ceph_pool_info`, `ceph_pool_list`, `ceph_pool_stats`, `ceph_snapshot_list`, `ceph_clone_list`, `ceph_client_config_export` | **None** | Pure reads. Diagnosis must work on an expired licence, or a customer cannot even see why. |
| `ceph_cluster_destroy`, `ceph_pool_delete`, `ceph_image_delete`, `ceph_snapshot_delete`, `ceph_clone_delete`, `ceph_clone_cleanup`, `ceph_image_unmap`, `ceph_client_unmount`, `ceph_clone_unmount` | **None** | Teardown and unmount. Never trap a customer's exit. |
| `ceph_cluster_create`, `ceph_bootstrap_cluster` | **Create** | Brings a new cluster into existence. |
| `ceph_pool_create`, `ceph_image_create`, `ceph_clone_create`, `ceph_clone_image`, `ceph_snapshot_create`, `ceph_image_resize` | **Full** | Each ALLOCATES capacity. This is the growth axis, so expiry bites. |
| `ceph_image_map`, `ceph_image_format`, `ceph_client_mount`, `ceph_client_config_install`, `ceph_clone_mount`, `ceph_clone_flatten`, `ceph_snapshot_protect`, `ceph_snapshot_unprotect`, `ceph_snapshot_rollback`, `ceph_install_prerequisites` | **Operate** | Routine operation of storage that already exists. |

### repository (28) -- the remaining repo verbs

| Functions | Tier | Why |
|---|---|---|
| `repository_list`, `repository_status`, `repository_info`, `repository_health`, `repository_log`, `repository_logs`, `repository_cat`, `repository_diff`, `repository_validate`, `repository_policy_get`, `repository_autostart_list` | **None** | Reads and diagnostics. |
| `repository_down_all`, `repository_unmount`, `repository_prune`, `repository_trim` | **None** | Stop and reclaim. Consistent with the decided `repository_down`. |
| `repository_merge`, `repository_promote`, `repository_template_apply` | **Full** | Create-shaped: they produce new repo state from existing state. |
| `repository_up` family already decided; `repository_mount`, `repository_exec`, `repository_commit`, `repository_commit_meta`, `repository_ownership`, `repository_policy_set`, `repository_autostart_enable`, `repository_autostart_enable_all`, `repository_autostart_disable`, `repository_autostart_disable_all` | **Operate** | Operating an existing repo. Autostart disable is arguably None, but it pairs with enable and neither traps anyone. |

### datastore (17)

| Functions | Tier | Why |
|---|---|---|
| `datastore_list`, `datastore_status`, `datastore_validate`, `datastore_snapshot_list` | **None** | Reads. |
| `datastore_delete`, `datastore_detach`, `datastore_forget`, `datastore_snapshot_delete`, `datastore_volumes_close` | **None** | Teardown and detach. |
| `datastore_create`, `datastore_fork` | **Create** | New datastore. |
| `datastore_expand`, `datastore_resize`, `datastore_snapshot_create` | **Full** | Capacity growth, mirroring `repository_expand`/`resize`. |
| `datastore_attach`, `datastore_adopt`, `datastore_volumes_open` | **Operate** | Bringing existing storage online. |

### machine (17) -- all diagnostics

| Functions | Tier | Why |
|---|---|---|
| every `machine_check_*` (12), `machine_ping`, `machine_ssh_test`, `machine_version`, `machine_fix_groups`, `machine_uninstall` | **None** | These are the probes a customer runs WHEN something is wrong, including a licence problem. Gating them would make an expired licence undiagnosable, and `machine_uninstall` is an exit path. |

### kube (16)

| Functions | Tier | Why |
|---|---|---|
| `kube_health`, `kube_kubeconfig`, `kube_join_token` | **None** | Reads and credential export. |
| `kube_uninstall`, `kube_delete`, `kube_node_remove` | **None** | Teardown. |
| `kube_install`, `kube_join`, `kube_prep_fork`, `kube_fork_dest_prep` | **Create** | New cluster or new node joining one. This is the clustering capability. |
| `kube_upgrade`, `kube_registry_up`, `kube_registry_wire`, `kube_apply`, `kube_node_label`, `kube_identity_rewrite` | **Operate** | Operating an existing cluster. |

### container (12) -- all operation, none creation

| Functions | Tier | Why |
|---|---|---|
| `container_list`, `container_inspect`, `container_logs`, `container_stats` | **None** | Reads. |
| `container_stop`, `container_kill`, `container_remove`, `container_pause`, `container_unpause` | **None** | Stopping and removing. |
| `container_start`, `container_restart`, `container_exec` | **Operate** | Running containers inside an already-licensed repo. |

### daemon (9), network (4), plugin (3), setup (1)

| Functions | Tier | Why |
|---|---|---|
| `daemon_status`, `daemon_logs`, `daemon_nop`, `plugin_status`, `network_ps_status` | **None** | Reads and the no-op probe. |
| `daemon_stop`, `daemon_teardown`, `plugin_stop`, `network_cleanup_ips`, `network_prune` | **None** | Teardown and reclaim. |
| `daemon_start`, `daemon_restart`, `daemon_setup`, `daemon_wait_docker`, `plugin_start`, `network_ensure_ips`, `setup` | **Operate** | Infrastructure lifecycle for something already licensed. |

### checkpoint (5) -- CRIU

| Functions | Tier | Why |
|---|---|---|
| `checkpoint_validate`, `checkpoint_check_compat` | **None** | Reads. |
| `checkpoint_cleanup` | **None** | Reclaim. |
| `checkpoint_create`, `checkpoint_restore` | **Full** | Live checkpoint/restore is a headline capability and consumes real storage. Expiry should bite. |

### backup (4) -- THE ONE THAT NEEDS YOUR EYE

| Functions | Tier | Why |
|---|---|---|
| `backup_list` | **None** | Read. |
| `backup_delete` | **None** | Reclaim. |
| `backup_push`, `backup_pull` | **Full** *(proposed)* | See below. |

**This group is the live finding, not a routine proposal.** `backup_push`,
`backup_pull`, `backup_delete` and `backup_list` are registered and **not
licence-gated today**, proven live: with an enforcing binary and no licence,
`repository create` exits 10 `LICENSE_REQUIRED` while `backup list` sails past
licensing and fails on a missing flag.

That contradicted the marketing copy, and the earlier decision was to correct
the copy rather than gate the functions. **Proposing `Full` for push/pull
reverses that.** It is the one group here with a real product consequence, so it
is called out separately rather than buried in a table. Say the word and it
stays `None`.

---

## What applying this changes

Nothing until it is approved. The mechanical change is dropping `pending: true`
and setting the tier on each entry. `TestTierMapCoversRegistry` already fails the
build if a registered function is missing, and the console-side gate reports the
pending count and fails when it GROWS, so neither can regress silently.

The behaviour change on the day it lands: functions moving off `TierNone` start
validating a repo licence. Everything proposed as `None` above keeps working
exactly as it does today, which is deliberate: reads, stops, removals and
diagnostics must never be the thing an expired licence blocks.

## What I could not decide for you

- **`backup_push` / `backup_pull`**: reverses a decision you already took.
- **`repository_exec` and `container_exec`**: proposed `Operate`, but an argument
  exists for `None` since exec is how a customer rescues a broken system. I
  chose `Operate` because exec into a licensed repo is normal operation, not
  rescue; rescue has `machine_*` and the stop/remove verbs, all `None`.
