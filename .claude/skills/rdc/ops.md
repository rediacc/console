# rdc ops — Local VM Provisioning

Manage local VM clusters for development and testing. Uses KVM (Linux), QEMU (macOS), or Hyper-V (Windows) — auto-detected.

## Commands

### Check prerequisites
```
rdc ops check
```
Verifies virtualization tools are installed (Docker, virsh, qemu-img, etc.). Returns JSON with pass/fail per tool.

### Install prerequisites
```
rdc ops setup
```
Installs missing virtualization tools for the detected platform.

### Provision VMs
```
rdc ops up [options]
```
Options:
- `--basic` — Minimal cluster: 1 bridge + 1 worker. Use this unless you need Ceph storage nodes.
- `--parallel` — Create VMs in parallel (faster).
- `--force` — Destroy and recreate all VMs.
- `--os <name>` — OS image (e.g., `ubuntu-24.04`, `debian-12`).

The bridge VM (ID 1) runs the Docker registry and orchestration. Worker VMs (ID 11, 12, ...) run repositories.

### Show status
```
rdc ops status
```
Returns JSON array of VMs with `id`, `name`, `ip`, and `status` (running/not found).

### SSH into a VM
```
rdc ops ssh <vmId> [command...]
```
SSH directly into a VM by ID. For port forwarding, use `--port-forward`.

### Destroy cluster
```
rdc ops down
```
Destroys all VMs in the cluster.

## VM naming and IPs

| ID | Name | IP | Role |
|----|------|----|------|
| 1 | rediacc1 | 192.168.111.1 | Bridge (registry, orchestration) |
| 11 | rediacc11 | 192.168.111.11 | Worker |
| 12 | rediacc12 | 192.168.111.12 | Worker |
| 21-23 | rediacc21-23 | 192.168.111.21-23 | Ceph storage (skipped with --basic) |

## Typical usage

```bash
# First time
rdc ops check
rdc ops setup        # if checks fail
rdc ops up --basic --parallel

# Check status
rdc ops status

# Tear down when done
rdc ops down
```
