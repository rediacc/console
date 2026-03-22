# rdc ops — Local VM Provisioning

Manage local VM clusters for development and testing. Uses KVM (Linux), QEMU (macOS), or Hyper-V (Windows) — auto-detected.

For full command syntax and options, see [reference.md](reference.md).

The bridge VM (ID 1) runs the Docker registry and orchestration. Worker VMs (ID 11, 12, ...) run repositories.

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
