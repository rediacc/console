# rdc repo — Repository Lifecycle

For full command syntax and options, see [reference.md](reference.md).

Repositories are isolated application deployments. Each gets an encrypted LUKS volume, dedicated Docker daemon, loopback IP range, and network isolation.

## Lifecycle commands

### Create
Creates encrypted volume. Size examples: `2G`, `5G`, `100G`, `1T`. Takes ~15-25s for LUKS formatting. The volume is left mounted and ready for `sync upload` immediately after creation.

### Deploy (start services)
Runs the Rediaccfile lifecycle: `up()`.
- `--mount`: Mount volume first. Required after any `repo push` to a new machine, and for first deploy of forked repos.
- `--checkpoint`: Restore CRIU checkpoint instead of running up() lifecycle. When checkpoint data is found, the Rediaccfile is **not executed** — containers resume directly from saved state.
- `--grand <parent>`: Use parent repo's LUKS credential to unlock a fork. Required when deploying a forked repo that inherited the parent's encryption key.

### Stop services
Runs Rediaccfile `down()`. Stops containers but does NOT unmount — the repo stays mounted and can be restarted with `repo up`. Use `--unmount` to also close the LUKS volume.

### Delete
Destroys containers, volumes, and encrypted image. Credential is archived for recovery via `config restore-archived`. **Warning**: Config mapping is removed globally — if the repo exists on another machine (after `repo push`), re-add with `config add-repository`.

### Prune orphaned resources
Removes empty mount dirs, orphan immovable markers, and stale lock files left behind by deleted repos or failed operations. Only removes resources with no matching repository image. Non-empty mount directories are never removed.

### Status
Shows mount state, Docker daemon, container count, disk usage.

## Advanced operations

### Fork (copy-on-write clone)
Creates an independent copy using the name:tag model — the fork is named `<parent>:<tag>` (e.g., `my-app:staging`). It gets a new GUID, networkId, and IP range while sharing the parent's name. Parent can remain running. Cross-machine fork: fork locally first, then `repo push` to the target.

**Agent guard**: AI agents operate in fork-only mode by default — they can only modify fork repositories. Use `repo fork` to create a fork first, then operate on the fork. Grand repo access requires `REDIACC_ALLOW_GRAND_REPO=<name>` or `--allow-grand` on the MCP server.

### Resize (offline)
Supports grow and shrink. Must be unmounted first (`repo down --unmount`).

### Expand (online, zero downtime)
Grow-only while repo is running. Cannot shrink — use `repo resize` for that.

### Apply template
Writes Rediaccfile and docker-compose.yaml from a template file.

### Validate
Checks LUKS container, filesystem consistency, and configuration. Use after unexpected shutdowns or to verify backup health.

## Rediaccfile rules

The Rediaccfile is a bash script with lifecycle functions. Key rules:
- **Must use `renet compose`**, never `docker compose`. Renet injects network isolation and IP allocation.
- Two lifecycle functions: `up()`, `down()`.
- Optional: `info()` for status display.
- `up()`: Pull images, start services. Generate secrets on first run if needed.
- `down()`: Stop and clean up.

### Compose conventions
- Use `renet compose -- "$@"` in Rediaccfiles (no `--network-id` flag — renet passes the network ID automatically via `REPOSITORY_NETWORK_ID` env var).
- `network_mode` is auto-injected by renet (`network_mode: host` on all services) — do not set it manually.
- **CRIU security settings are auto-injected**: `cap_add: [CHECKPOINT_RESTORE, SYS_PTRACE, NET_ADMIN]`, `security_opt: [apparmor=unconfined]`, and `userns_mode: host` are added to every container by renet. Default seccomp profile is preserved. Do not set these manually.
- `ports:` declarations are ignored (host networking). Services bind to allocated IPs. Add `rediacc.service_port` label for HTTP routing — services without it don't get HTTP routes.
- Use healthchecks in compose for dependent services.
- Persistent data: both `${REPOSITORY_PATH}/...` bind mounts and Docker named volumes are safe (Docker data-root is inside the encrypted LUKS mount).
- Dangerous settings (`privileged: true`, `pid: host`, `ipc: host`) are blocked by default. Use `renet compose --unsafe` to override.
- Restart policies are safe — renet auto-strips them for CRIU compatibility. The router watchdog auto-recovers stopped containers based on the saved policy in `.rediacc.json`.

### SERVICE_IP binding
- Renet injects `SERVICE_IP` into each service's environment when running `renet compose`.
- Services binding to well-known ports (5432, 3306, 6379, etc.) should listen on `SERVICE_IP` instead of `0.0.0.0` to avoid port conflicts when multiple repositories run the same service.
- Use `$${SERVICE_IP:-0.0.0.0}` in compose commands (`$$` so Compose passes `$` literally to the container shell):
  ```yaml
  command: ["sh", "-c", "exec docker-entrypoint.sh postgres -c listen_addresses=$${SERVICE_IP:-0.0.0.0}"]
  ```
- Healthchecks should also use `$${SERVICE_IP:-localhost}`:
  ```yaml
  test: ["CMD-SHELL", "pg_isready -U postgres -h $${SERVICE_IP:-localhost}"]
  ```
- For services configured via environment variables (not command flags), use `${SERVICE_IP:-0.0.0.0}` (single `$` — Compose substitutes directly).

### CRIU compatibility
- Apps must handle both `ECONNRESET` (stale socket) and `ECONNREFUSED` (service not yet ready) on persistent connections — after CRIU restore, TCP socket FDs are restored but connections are stale, and dependent services (databases) may need a few seconds to accept connections.
- Use connection pool libraries with automatic reconnection.
- Add `process.on("uncaughtException")` safety net for stale socket errors from internal library objects (e.g., `pg` library's `BoundPool`).
- See the [heartbeat template](https://github.com/rediacc/console/tree/main/packages/json/templates/monitoring/heartbeat) for a reference implementation.

### Available environment variables
In Rediaccfile shell: `${SVCNAME_IP}`, `${REPOSITORY_PATH}`, `${REPOSITORY_NETWORK_ID}`.
In containers: `SERVICE_IP`, `REPOSITORY_NETWORK_ID` (auto-injected by renet).

## Fork routing and backup behavior

- Fork auto-route URL pattern: `{service}-{tag}.{machine}.{baseDomain}` (shared machine cert)
- Custom domains are skipped for forks — the domain belongs to the grand repo
- Scheduled backups skip forks (use `rdc repo push` for manual backup)

## Takeover workflow (fork to production)

1. Fork: `rdc repo fork jfrog --tag upgrade-test -m hostinger`
2. Deploy fork: `rdc repo up jfrog:upgrade-test -m hostinger --mount`
3. Test upgrade in fork (SSH, apply changes, verify)
4. Takeover: `rdc repo takeover jfrog:upgrade-test -m hostinger`
5. Production now has upgraded data. Old data preserved as backup fork.
6. To revert: `rdc repo takeover jfrog:pre-takeover-20260317 -m hostinger`

## Storage architecture

- The datastore is a BTRFS pool file hosted on the system disk (`/mnt/rediacc.pool`)
- `rdc machine query <name> --system` shows both disk and datastore stats plus effective free space
- Effective free = min(disk free, datastore free) — the actual limit for new repos
- Expand with: `rdc datastore resize <machine>`

## Cleanup behavior

- `repo delete` cleans: storage, Docker daemon + systemd unit, loopback IPs + systemd unit, iptables rules
- `repo down` keeps: Docker daemon, loopback IPs, systemd units (for quick restart with `repo up`)
- `machine prune` removes: orphaned loopback units, unused IPs, stale Docker daemon units from legacy deletions

## Typical deployment workflow

```bash
rdc repo create my-app -m server-1 --size 5G
rdc repo sync upload -m server-1 -r my-app --local ./my-app/
rdc repo up my-app -m server-1
rdc machine containers server-1    # verify
```
