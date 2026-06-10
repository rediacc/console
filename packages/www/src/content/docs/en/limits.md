---
title: Limits & Quotas
description: >-
  Reference for the limits, maximums, and quotas that apply to Rediacc
  repositories, services, networking, and storage.
category: Reference
order: 99
language: en
---

# Limits & Quotas

Rediacc deployment limits. Three are hard and cannot be changed by adding hardware: the 61-service cap per repository (network address space allocation), the kernel 6.1 minimum (CRIU requirements), and the Let's Encrypt issuance cap of 50 wildcard certificates per registered domain per week. Everything else is soft: it moves when you add hardware. Know the difference before you commit to a topology.

---

## Services per Repository

Each repository supports up to **61 services** running simultaneously.

This is a hard limit determined by the network address space allocated to each repository. Every service gets its own dedicated private IP address, and each repository's address block accommodates exactly 61 service slots.

Look: hitting 61 services in one repository usually signals an architecture problem, not a Rediacc constraint. The fix is to move sidecars and monitoring agents into their own repository with a separate isolation boundary, or to reduce the number of independently running processes in the application itself.

---

## Repositories per Machine

There is no hard cap enforced by Rediacc. The practical limit depends on your machine's resources:

| Resource | Impact |
|----------|--------|
| Disk space | Each repository is an encrypted disk image. A machine with 1 TB of usable storage can hold many repositories, but the total size of all images must fit within the datastore pool. |
| RAM | Each running repository starts its own Docker daemon and containers. Memory usage depends on your workloads. |
| CPU | Parallel repository operations (start, backup, fork) add temporary CPU load. |

**Typical deployments** run 10 to 50 repositories per machine without issue. Machines with 32 GB+ RAM and 500 GB+ storage regularly run 100+ repositories.

### System-wide network ID limit

Each repository is assigned a unique **network ID**, a number used to calculate its private IP address range. This pool is shared across all machines and repositories managed by the same Rediacc config.

| Limit | Value |
|-------|-------|
| Total available network IDs | ~261,944 |
| Scope | Per config (shared across all machines in a config) |

When a repository is deleted, its network ID is freed and becomes available for reuse. Rediacc allocates IDs sequentially and only scans for freed gaps once the forward counter approaches the ceiling. In practice you will never hit this. We have not seen it happen. Exhausting the pool would require creating and tracking hundreds of thousands of repositories under a single config.

---

## Forks

There is no limit on the number of active forks of a repository. Each fork is a full copy-on-write clone with its own encrypted storage, network addresses, and Docker daemon. Forks consume disk space proportional to the data written to them after creation (not the full parent size).

---

## External Ports

### Always-active ports

Ports are only opened once you configure a public IP with `rdc config infra set --public-ipv4`. Until then, no ports are open on the machine. Once configured:

| Port | Protocol | Purpose |
|------|----------|---------|
| 80 | TCP | HTTP: handled by Traefik; returns 404 for unconfigured domains, not passed to any service |
| 443 | TCP | HTTPS: same as above; requests without a matching route are rejected at the proxy layer |
| 10000–10010 | TCP | Dynamic range for Rediacc-managed TCP forwarding |

HTTP/HTTPS differ from raw TCP ports: even though 80 and 443 are open, every request is validated by the reverse proxy against an explicit routing table. Without a configured service and matching domain, no application code is reached and no data is exposed.

### Opt-in TCP/UDP forwarding

All other ports (databases, caches, message brokers, DNS, mail) are **closed by default** and must be explicitly opened. This keeps the machine's attack surface minimal.

To expose a port from a specific service:

```yaml
labels:
  - "rediacc.tcp_ports=5432"   # expose PostgreSQL from this container
  - "rediacc.udp_ports=53"     # expose DNS from this container
```

To open a port at the machine level (available to all services):

```bash
rdc config infra set -m server-1 --tcp-ports 25,587,993   # mail server
rdc config infra push -m server-1
```

> Never expose database or cache ports externally unless you have a specific requirement. Use HTTPS auto-routes for web services and keep storage services internal.

---

## Datastore

The datastore is a fixed-size pool created when a machine is first set up. Its size does not grow automatically.

- **Minimum recommended size**: 50 GB
- **Maximum size**: Limited by your disk. A single pool can span a full disk.
- **Resize**: Use `rdc datastore resize` to change the pool size (all repositories must be unmounted first).
- **Filesystem**: Rediacc uses BTRFS internally for copy-on-write snapshots and efficient forking. Requires a machine running **Linux kernel 6.1 or later** for full production stability.

Each repository has a maximum size set at creation time (default: 10 GB). Use `rdc repo resize` to change it by hand, or set an [automatic size policy](/en/docs/repositories#automatic-size-policy) so the machine grows it online when it fills up (bounded by an explicit per-repository ceiling and a pool free-space reserve). Auto-grow applies to individual repositories only; the pool itself is never grown automatically.

Repository images are sparse: a repository only occupies the pool with what it has actually written, and space freed by deletions returns to the pool via [`repo trim`](/en/docs/repositories#reclaim-space-trim) or a scheduled auto-trim. Quotas can therefore add up to more than the pool size, with the [storage health report](/en/docs/monitoring#storage-health) showing the real fill level.

---

## HTTP Routes

Each service with the `rediacc.service_port` label gets one HTTPS route automatically. There is no limit on the number of services with routes, subject to the 61-service maximum per repository.

Wildcard TLS certificates are provisioned per repository on the first deployment via Let's Encrypt (Cloudflare DNS-01 challenge). Let's Encrypt caps issuance at **50 certificates per registered domain per week**. Because Rediacc uses one wildcard certificate per repository (not per service), a deployment that creates 50+ new repositories in a single week will hit this cap.

Forks reuse the parent repository's existing wildcard certificate and do not consume any certificate quota.

---

## Checkpoint / Restore (CRIU)

Live migration via CRIU has the following constraints:

- **Opt-in**: Only containers with the `rediacc.checkpoint=true` label are checkpointed. Databases and stateless services are excluded by default and start fresh on restore.
- **Kernel requirement**: Linux 6.1+ on both the source and destination machine.
- **Network mode**: CRIU requires host networking mode. Containers using custom network configurations cannot be checkpointed.
- **Memory**: The checkpoint data size equals the resident memory of the checkpointed process. Large in-memory datasets (e.g., a Node.js app caching 4 GB of data) produce 4 GB checkpoint files.
- **TCP connections**: Applications must tolerate connection loss across restore. Active TCP connections are **not** preserved. The restored process sees sockets as closed and must reconnect. This applies to both same-machine and cross-machine restore paths.
- **Same-machine live fork redirects parent addresses**: `rdc repo fork --parent X --tag Y --checkpoint` followed by `rdc repo up` works while the parent keeps running. The restored processes carry the parent's loopback addresses from the moment of the checkpoint, so the system transparently redirects them to the fork's own addresses (same service, fork's copy of the data). The first use of a restored TCP connection still fails and the app must reconnect, per the TCP bullet above.

---

## Backups

| Limit | Value |
|-------|-------|
| Backup destinations per repository | Unlimited |
| Simultaneous backup jobs | 1 per repository (jobs queue if triggered concurrently) |
| Backup frequency | No minimum interval enforced; limited by your storage bandwidth. Use `rdc config backup-strategy set --name <name> --bwlimit "6M"` to cap upload speed (rclone `--bwlimit` syntax: simple `6M`, directional `6M:off`, or timetable `08:00,3M;22:00,10M`) |
| Retention | Controlled by your storage provider (S3, Cloudflare R2, etc.). Rediacc does not enforce retention policies. |
| Cross-machine backup | Supported; destination machine must have sufficient datastore space |

---

## CLI & API

| Limit | Value |
|-------|-------|
| Concurrent `rdc` commands against the same machine | Unlimited (each command opens its own SSH connection) |
| Default parallel repository start concurrency | 3 (adjustable with `--concurrency`) |
| SSH connection timeout | 30 seconds for initial connection |
| `rdc` session duration | No timeout; long-running operations keep the connection alive |

---

## Supported OS Versions

Remote machines must run one of the following to meet Rediacc's kernel, filesystem, and network isolation requirements. This list is the authoritative CI-tested set (Bridge Workers matrix) and must stay in sync with [Requirements](/en/docs/requirements):

| OS | Minimum Version | Default Kernel | Notes |
|----|-----------------|----------------|-------|
| Ubuntu | 24.04 LTS *(recommended)* | 6.8 | AppArmor default. |
| Debian | 13 (Trixie); 12 Bookworm also works | 6.12 (6.1 on Debian 12) | |
| Fedora | 43 | 6.12 | SELinux enforcing default. |
| openSUSE Leap | 16.0 | 6.4+ | AppArmor default. |
| Oracle Linux | 10 (UEK) | UEK 7+ | UEK retains btrfs; SELinux enforcing default. |

**Minimum required kernel: 6.1.** Machines running older kernels are rejected at setup time with a clear error message.

> **Why kernel 6.1?** Rediacc uses BTRFS for encrypted repository storage and copy-on-write forking. Linux 6.1 introduced critical BTRFS improvements that significantly reduce mount times for large datastores, improve snapshot deletion performance, and fix data-integrity issues present in earlier kernels. Kernel 6.1 is also required for the kernel-level network isolation hooks that enforce cross-repository isolation, transparently rewriting `bind()` calls and blocking connections between repositories.

> **Why not Rocky Linux 10 / RHEL 10 stock kernel?** RHEL 10's stock kernel ships without the `btrfs` module (`modprobe btrfs` fails with "Module btrfs not found"). Rediacc's encrypted storage backend cannot run without btrfs. **Oracle Linux 10 is the only RHEL-compatible target on the supported list** because it defaults to the Unbreakable Enterprise Kernel (UEK), which retains btrfs. See [Requirements → Why UEK?](/en/docs/requirements) for the full explanation.

### Kernel feature matrix

Read the matrix as a single-glance view of what each CI-tested OS provides out of the box. All five satisfy every requirement, so this is an operator-facing reference, not a gating criterion.

| OS | btrfs module | cgroups v2 | Landlock (ABI ≥ 1) | eBPF cgroup hooks |
|----|--------------|------------|--------------------|-------------------|
| Ubuntu 24.04 | in-tree | unified hierarchy | yes (5.13+) | yes |
| Debian 13 | in-tree | unified hierarchy | yes | yes |
| Fedora 43 | in-tree | unified hierarchy | yes | yes |
| openSUSE Leap 16.0 | in-tree | unified hierarchy | yes | yes |
| Oracle Linux 10 (UEK) | in-tree (via UEK) | unified hierarchy | yes | yes |
