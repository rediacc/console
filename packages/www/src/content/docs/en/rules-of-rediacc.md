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

- **Every repository needs a Rediaccfile**, a bash script with lifecycle functions.
- **Lifecycle functions**: `up()`, `down()`. Optional: `info()`.
- `up()` starts your services. `down()` stops them.
- `info()` provides status information (container state, recent logs, health).
- Rediaccfile is sourced by renet, it has access to shell variables, not just env vars.

### Available environment variables in Rediaccfile

| Variable | Example | Description |
|----------|---------|-------------|
| `REDIACC_WORKING_DIR` | `/mnt/rediacc/mounts/abc123/` | Root path of the mounted repo |
| `REDIACC_NETWORK_ID` | `6336` | Network isolation identifier |
| `REDIACC_REPOSITORY` | `abc123-...` | Repository GUID |
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

- **Use `renet compose`, never `docker compose`**, renet injects network isolation, host networking, loopback IPs, and service labels.
- **Do NOT set `network_mode`** in your compose file, renet forces `network_mode: host` on all services. Any value you set is overwritten.
- **Do NOT set `rediacc.*` labels**, renet auto-injects `rediacc.network_id`, `rediacc.service_ip`, and `rediacc.service_name`.
- **`ports:` mappings are ignored** in host networking mode. Add `rediacc.service_port` label for HTTP routing (services without this label don't get HTTP routes). Use `rediacc.tcp_ports`/`rediacc.udp_ports` labels for TCP/UDP forwarding.
- **Restart policies (`restart: always`, `on-failure`, etc.) are safe to use**, renet auto-strips them for CRIU compatibility. The router watchdog auto-recovers stopped containers based on the original policy saved in `.rediacc.json`.
- **Dangerous settings are blocked by default**, `privileged: true`, `pid: host`, `ipc: host`, and host bind mounts to system paths are rejected. Use `renet compose --unsafe` to override at your own risk.

### Environment variables inside containers

Renet auto-injects these into every container:

| Variable | Description |
|----------|-------------|
| `SERVICE_IP` | This container's dedicated loopback IP |
| `REDIACC_NETWORK_ID` | Network isolation ID |

### Service naming and routing

- The compose **service name** becomes the auto-route URL prefix.
- **Grand repos**: `https://{service}.{repo}.{machine}.{baseDomain}` (e.g., `https://myapp.marketing.server-1.example.com`).
- **Fork repos**: `https://{service}-fork-{tag}.{repo}.{machine}.{baseDomain}` (e.g., `https://myapp-fork-staging.marketing.server-1.example.com`). The `-fork-` separator prevents URL collisions with grand repo service names. The fork URL always uses the parent repo's existing wildcard certificate, so no new cert is needed.
- For custom domains, use Traefik labels (but note: custom domains are NOT fork-friendly, the domain belongs to the grand repo).

## Networking

- **Each repository gets its own Docker daemon** at `/var/run/rediacc/docker-<networkId>.sock`.
- **Each service gets a unique loopback IP** within a /26 subnet (e.g., `127.0.24.192/26`).
- **Binding is automatic**: Services can bind to `0.0.0.0` or `localhost` - the kernel transparently rewrites the address to the service's assigned loopback IP. Explicit `${SERVICE_IP}` binding still works but is no longer required.
- **Health checks can use `localhost`** or `${SERVICE_IP}`. Example: `healthcheck: test: ["CMD", "curl", "-f", "http://localhost:8080/health"]`
- **Cross-repo connections are kernel-blocked**: The kernel blocks connections to loopback IPs outside the repository's `/26` subnet automatically. A service in one repo cannot reach services in another repo.
- **Inter-service communication**: Use **service names** (e.g. `db`, `redis`) - renet automatically injects every service name as a hostname that resolves to the correct IP. Docker DNS names do NOT work in host mode, but service names via `/etc/hosts` do. Avoid embedding `${DB_IP}` or similar in persistent config files (e.g. connection strings stored in a database) - if forked, the raw IP carries over and points to the wrong repo. Service names always resolve correctly per repo.
- **Port conflicts are impossible** between repositories, each has its own Docker daemon and IP range.
- **TCP/UDP port forwarding**: Add labels to expose non-HTTP ports:
  ```yaml
  labels:
    - "rediacc.tcp_ports=5432,3306"
    - "rediacc.udp_ports=53"
  ```

## Storage

- **All Docker data is stored inside the encrypted repo**, Docker's `data-root` is at `{mount}/.rediacc/docker/data` inside the LUKS volume. Named volumes, images, and container layers are all encrypted, backed up, and forked automatically.
- **Bind mounts to `${REDIACC_WORKING_DIR}/...` are recommended** for clarity, but named volumes also work safely.
  ```yaml
  volumes:
    - ${REDIACC_WORKING_DIR}/data:/data        # bind mount (recommended)
    - pgdata:/var/lib/postgresql/data      # named volume (also safe)
  ```
- The LUKS volume is mounted at `/mnt/rediacc/mounts/<guid>/`.
- BTRFS snapshots capture the entire LUKS backing file, including all bind-mounted data.
- The datastore is a fixed-size BTRFS pool file on the system disk. Use `rdc machine query --name <name> --system` to see effective free space. Expand with `rdc datastore resize`.

## CRIU (Live Migration)

- **Opt-in via label**: Add `rediacc.checkpoint=true` to containers you want to checkpoint. Containers without it (databases, caches) start fresh and recover via their own mechanisms (WAL, LDF, AOF).
- **`repo down --checkpoint`** saves process state before stopping, next `repo up` auto-restores. **This is the primary same-machine flow**, verified working.
- **`backup push --checkpoint`** captures running process memory + disk state for labeled containers, then transfers the volume to another machine. Restore on the target machine via `repo up`.
- **`repo fork --checkpoint`** captures process state before forking and CoW-clones the checkpoint with the fork. ⚠️ On the same machine, the subsequent `repo up` on the fork **currently fails** with `criu failed: type RESTORE errno 0` when the parent is still running. Upstream CRIU bugs [checkpoint-restore/criu#478](https://github.com/checkpoint-restore/criu/issues/478) / [#514](https://github.com/checkpoint-restore/criu/issues/514). Use `repo down --checkpoint` for in-place save/restore, or `backup push --checkpoint` for cross-machine migration.
- **`repo up`** auto-detects checkpoint data and restores if found. Use `--skip-checkpoint` to force fresh start.
- **Dependency-aware restore**: Uses compose `depends_on` to start databases first (wait for healthy), then CRIU-restore app containers.
- **TCP connections become stale after restore**, apps must handle `ECONNRESET` and reconnect. CRIU does not preserve active TCP connection state across restore in any supported flow.
- **Docker experimental mode** is enabled automatically on per-repo daemons.
- **CRIU is installed** during `rdc config machine setup`.
- **`/etc/criu/runc.conf`** is configured with `tcp-established` by default.
- **Container security settings are auto-injected for labeled containers**, `renet compose` adds the following to containers with `rediacc.checkpoint=true`:
  - `cap_add`: `CHECKPOINT_RESTORE`, `SYS_PTRACE`, `NET_ADMIN` (minimal set for CRIU on kernel 5.9+)
  - `security_opt`: `apparmor=unconfined` (CRIU's AppArmor support is not yet stable upstream)
  - `userns_mode: host` (CRIU requires init namespace access for `/proc/pid/map_files`)
- Containers without the label run with a cleaner security posture (no extra capabilities).
- Docker's default seccomp profile is preserved, CRIU uses `PTRACE_O_SUSPEND_SECCOMP` (kernel 4.3+) to temporarily suspend filters during checkpoint/restore.
- **Do NOT set CRIU capabilities manually** in your compose file, renet handles it based on the label.
- See the [heartbeat template](https://github.com/rediacc/console/tree/main/packages/json/templates/monitoring/heartbeat) for a CRIU-compatible reference implementation.

### CRIU-compatible application patterns

- Handle `ECONNRESET` on all persistent connections (database pools, websockets, message queues).
- Use connection pool libraries that support automatic reconnection.
- Add `process.on("uncaughtException")` safety net for stale socket errors from internal library objects.
- Restart policies are auto-managed by renet (stripped for CRIU, watchdog handles recovery).
- Avoid relying on Docker DNS, use loopback IPs for inter-service communication.

### Host security policies by OS

Across the five officially supported server OSes (see [Requirements](/en/docs/requirements)), the per-repo docker daemon and the containers it runs use **default container labels**. `rdc config machine setup` does not install a custom SELinux policy or AppArmor profile.

- **Ubuntu 24.04 / openSUSE Leap 16.0**: AppArmor is enabled by default. Containers run under the default docker-container profile. The only carve-out is CRIU (`apparmor=unconfined` for `rediacc.checkpoint=true` containers, per the note above).
- **Fedora 43 / Oracle Linux 10**: SELinux runs enforcing by default. Containers get the standard `container_t` context. No extra policy installation is needed. If a setup step fails with AVC denials, see [Troubleshooting → SELinux denials](/en/docs/troubleshooting).
- **Debian 13**: AppArmor is available but not enforced by default on all domains. Containers still use the docker-container profile.

No per-OS security posture flag is required; `rdc` and `renet` detect what is running and produce the same per-repo isolation on all five distributions.

## Security

- **LUKS encryption** is mandatory for standard repositories. Each repo has its own encryption key.
- **Credentials are stored in the CLI config** (`~/.config/rediacc/rediacc.json`). Losing the config means losing access to encrypted volumes.
- **Never commit credentials** to version control. Use `env_file` and generate secrets in `up()`.
- **Repository isolation**: Each repo's Docker daemon, network, and storage are fully isolated from other repos on the same machine.
- **Agent isolation**: AI agents operate in fork-only mode by default. Each repo has its own SSH key with server-side sandbox enforcement (`sandbox-gateway` ForceCommand). All connections are sandboxed with Landlock LSM, OverlayFS home overlay, and per-repo TMPDIR. Cross-repo filesystem access is blocked by the kernel.
- **`sudo` is disabled inside a repository sandbox by design.** Landlock filesystem isolation requires `NoNewPrivs`, which prevents any privilege elevation, so `sudo` will fail with `no new privileges flag is set`. The repo's owner user already has the permissions needed for everything inside the repo's mount and Docker socket. For genuinely privileged operations (installing host packages, kernel tuning), run them outside the sandbox or from a Rediaccfile `up()` function executed by the infrastructure path.
- **Docker bridge networking is disabled on every per-repo daemon.** Each repo's `daemon.json` carries `"bridge": "none"` and `"iptables": false`, so a plain `docker run <image>` creates a container with only a loopback interface and no outbound connectivity. This is not a bug, it is how cross-repo isolation is enforced: the kernel-level eBPF hooks that block one repo from reaching another repo's loopback IPs only apply to containers that live in the host network namespace. For production services use `renet compose`, which injects `network_mode: host` automatically. For ad-hoc one-off containers in a shell, pass `--network host` explicitly.

## Deployment

- **`rdc repo up`** auto-mounts the LUKS volume if unmounted, then runs `up()` in all Rediaccfiles.
- **`rdc repo down`** runs `down()` and stops the Docker daemon.
- **`rdc repo down --unmount`** also closes the LUKS volume (locks the encrypted storage).
- **Forks** (`rdc repo fork`) create a CoW (copy-on-write) clone with a new GUID and networkId, in **constant time regardless of repo size**. BTRFS reflink duplicates the image metadata, not the data, so a 100 GB repo forks in the same few seconds as a 1 GB repo. The fork shares the parent's encryption key.
- **Takeover** (`rdc repo takeover --name <fork> -m <machine>`) replaces the grand repo's data with a fork's data. The grand keeps its identity (GUID, networkId, domains, autostart, backup chain). Old production data is preserved as a backup fork. Use for: test upgrade on fork, verify, then takeover to production. Revert with `rdc repo takeover --name <backup-fork> -m <machine>`.
- **Proxy routes** take ~3 seconds to become active after deploy. The "Proxy is not running" warning during `repo up` is informational in ops/dev environments.
- **`rdc repo up` and `rdc repo fork --up` print the URL pattern** for services labelled with `rediacc.service_port` at the end of deploy. Replace `{service}` with your exposed service name to get the exact URL. Services without `rediacc.service_port` (databases, workers) do not get routes and are not shown.

## Common mistakes

- Using `docker compose` instead of `renet compose`, containers won't get network isolation.
- Restart policies are safe, renet auto-strips them and the watchdog handles recovery.
- Using `privileged: true`, not needed, renet injects specific CRIU capabilities instead.
- Hardcoding raw IPs in persistent config files - use service names for connections to keep fork isolation intact.
- Using `rdc term connect -c` as a workaround for failed commands, report bugs instead.
- `repo delete` performs full cleanup including loopback IPs and systemd units. Run `rdc machine prune --name <name>` to clean leftovers from legacy deletions.
