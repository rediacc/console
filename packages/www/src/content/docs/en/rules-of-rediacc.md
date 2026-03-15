---
title: "Rules of Rediacc"
description: "Essential rules and conventions for building applications on the Rediacc platform. Covers Rediaccfile, compose, networking, storage, CRIU, and deployment."
category: "Guides"
order: 5
language: en
---

# Rules of Rediacc

Every Rediacc repository runs inside an isolated environment with its own Docker daemon, encrypted LUKS volume, and dedicated IP range. These rules ensure your application works correctly within this architecture.

## Rediaccfile

- **Every repository needs a Rediaccfile** — a bash script with lifecycle functions.
- **Lifecycle functions**: `up()`, `down()`. Optional: `info()`.
- `up()` starts your services. `down()` stops them.
- `info()` provides status information (container state, recent logs, health).
- Rediaccfile is sourced by renet — it has access to shell variables, not just env vars.

### Available environment variables in Rediaccfile

| Variable | Example | Description |
|----------|---------|-------------|
| `REPOSITORY_PATH` | `/mnt/rediacc/mounts/abc123/` | Root path of the mounted repo |
| `REPOSITORY_NETWORK_ID` | `6336` | Network isolation identifier |
| `REPOSITORY_NAME` | `abc123-...` | Repository GUID |
| `{SVCNAME}_IP` | `HEARTBEAT_IP=127.0.24.195` | Per-service loopback IP (uppercase service name) |

### Minimal Rediaccfile

```bash
#!/bin/bash

_compose() {
  renet compose -- "$@"
}

up() {
  _compose up -d
}

down() {
  _compose down
}
```

## Compose

- **Use `renet compose`, never `docker compose`** — renet injects network isolation, host networking, loopback IPs, and service labels.
- **Do NOT set `network_mode`** in your compose file — renet forces `network_mode: host` on all services. Any value you set is overwritten.
- **Do NOT set `rediacc.*` labels** — renet auto-injects `rediacc.network_id`, `rediacc.service_ip`, and `rediacc.service_name`.
- **`ports:` mappings are ignored** in host networking mode. Use `rediacc.service_port` label for proxy routing to non-80 ports.
- **Do NOT use `restart: always` or `restart: unless-stopped`** — these conflict with CRIU checkpoint/restore. Use `restart: on-failure` or omit it.
- **Do NOT use Docker named volumes** — they live outside the encrypted repo and won't be included in backups or forks.

### Environment variables inside containers

Renet auto-injects these into every container:

| Variable | Description |
|----------|-------------|
| `SERVICE_IP` | This container's dedicated loopback IP |
| `REPOSITORY_NETWORK_ID` | Network isolation ID |

### Service naming and routing

- The compose **service name** becomes the auto-route URL prefix.
- Example: service `myapp` at networkId 6336 with base domain `example.com` becomes `https://myapp-6336.example.com`.
- For custom domains, use Traefik labels (but note: custom domains are NOT fork-friendly).

## Networking

- **Each repository gets its own Docker daemon** at `/var/run/rediacc/docker-<networkId>.sock`.
- **Each service gets a unique loopback IP** within a /26 subnet (e.g., `127.0.24.192/26`).
- **Bind to `SERVICE_IP`**, not `0.0.0.0` — host networking means `0.0.0.0` would conflict with other repos.
- **Inter-service communication**: Use loopback IPs or `SERVICE_IP` env var. Docker DNS names do NOT work in host mode.
- **Port conflicts are impossible** between repositories — each has its own Docker daemon and IP range.
- **TCP/UDP port forwarding**: Add labels to expose non-HTTP ports:
  ```yaml
  labels:
    - "rediacc.tcp_ports=5432,3306"
    - "rediacc.udp_ports=53"
  ```

## Storage

- **All persistent data must use `${REPOSITORY_PATH}/...` bind mounts.**
  ```yaml
  volumes:
    - ${REPOSITORY_PATH}/data:/data
    - ${REPOSITORY_PATH}/config:/etc/myapp
  ```
- Docker named volumes live outside the LUKS repo — they are **not encrypted**, **not backed up**, and **not included in forks**.
- The LUKS volume is mounted at `/mnt/rediacc/mounts/<guid>/`.
- BTRFS snapshots capture the entire LUKS backing file, including all bind-mounted data.

## CRIU (Live Migration)

- **`backup push --checkpoint`** captures running process memory + disk state.
- **`repo up --mount --checkpoint`** restores containers from checkpoint (no fresh start).
- **TCP connections become stale after restore** — apps must handle `ECONNRESET` and reconnect.
- **Docker experimental mode** is enabled automatically on per-repo daemons.
- **CRIU is installed** during `rdc config machine setup`.
- **`/etc/criu/runc.conf`** is configured with `tcp-established` for TCP connection preservation.
- **Container security settings are auto-injected by renet** — `renet compose` automatically adds the following to every container for CRIU compatibility:
  - `cap_add`: `CHECKPOINT_RESTORE`, `SYS_PTRACE`, `NET_ADMIN` (minimal set for CRIU on kernel 5.9+)
  - `security_opt`: `apparmor=unconfined` (CRIU's AppArmor support is not yet stable upstream)
  - `userns_mode: host` (CRIU requires init namespace access for `/proc/pid/map_files`)
- Docker's default seccomp profile is preserved — CRIU uses `PTRACE_O_SUSPEND_SECCOMP` (kernel 4.3+) to temporarily suspend filters during checkpoint/restore.
- **Do NOT set these manually** in your compose file — renet handles it. Setting them yourself risks duplicates or conflicts.
- See the [heartbeat template](https://github.com/rediacc/console/tree/main/packages/json/templates/monitoring/heartbeat) for a CRIU-compatible reference implementation.

### CRIU-compatible application patterns

- Handle `ECONNRESET` on all persistent connections (database pools, websockets, message queues).
- Use connection pool libraries that support automatic reconnection.
- Add `process.on("uncaughtException")` safety net for stale socket errors from internal library objects.
- Avoid `restart: always` — it interferes with CRIU restore.
- Avoid relying on Docker DNS — use loopback IPs for inter-service communication.

## Security

- **LUKS encryption** is mandatory for standard repositories. Each repo has its own encryption key.
- **Credentials are stored in the CLI config** (`~/.config/rediacc/rediacc.json`). Losing the config means losing access to encrypted volumes.
- **Never commit credentials** to version control. Use `env_file` and generate secrets in `up()`.
- **Repository isolation**: Each repo's Docker daemon, network, and storage are fully isolated from other repos on the same machine.
- **Agent isolation**: AI agents operate in fork-only mode by default. Each repo has its own SSH key with server-side sandbox enforcement (`sandbox-gateway` ForceCommand). All connections are sandboxed with Landlock LSM, OverlayFS home overlay, and per-repo TMPDIR. Cross-repo filesystem access is blocked by the kernel.

## Deployment

- **`rdc repo up`** runs `up()` in all Rediaccfiles.
- **`rdc repo up --mount`** opens the LUKS volume first, then runs lifecycle. Required after `backup push` to a new machine.
- **`rdc repo down`** runs `down()` and stops the Docker daemon.
- **`rdc repo down --unmount`** also closes the LUKS volume (locks the encrypted storage).
- **Forks** (`rdc repo fork`) create a CoW (copy-on-write) clone with a new GUID and networkId. The fork shares the parent's encryption key.
- **Proxy routes** take ~3 seconds to become active after deploy. The "Proxy is not running" warning during `repo up` is informational in ops/dev environments.

## Common mistakes

- Using `docker compose` instead of `renet compose` — containers won't get network isolation.
- Using `restart: always` — prevents CRIU restore and interferes with `repo down`.
- Using Docker named volumes — data is not encrypted, not backed up, not forked.
- Binding to `0.0.0.0` — causes port conflicts between repos in host networking mode.
- Hardcoding IPs — use `SERVICE_IP` env var; IPs are allocated dynamically per networkId.
- Forgetting `--mount` on first deploy after `backup push` — LUKS volume needs explicit opening.
- Using `rdc term -c` as a workaround for failed commands — report bugs instead.
