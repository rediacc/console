# rdc repo — Repository Lifecycle

For full command syntax and options, see [reference.md](reference.md).

Repositories are isolated application deployments. Each gets an encrypted LUKS volume, dedicated Docker daemon, loopback IP range, and network isolation.

## Lifecycle commands

### Create
`rdc repo create <name> -m <machine> --size 5G` creates the encrypted volume. Size examples: `2G`, `5G`, `100G`, `1T`. Takes ~15-25s for LUKS formatting. The volume is left mounted and ready for `sync upload` immediately after creation. This is one of the few repo commands that still takes `-m`: the repo does not exist yet, so there is no placement to derive the machine from.

### Deploy (start services)
`rdc repo up <ref>` runs the Rediaccfile lifecycle: `up()`. The machine is derived from the ref.
- Mounting is automatic. First deploy and forks are mounted for you, so the old `repo mount` command is gone, and so is `repo up --mount`.
- `--no-start`: Mount and prepare the repo without running `up()`. This is what folded in the retired `repo mount`.
- `--skip-checkpoint`: Force a fresh start instead of restoring a CRIU checkpoint. Checkpoint restore is auto-detected by default; when checkpoint data is found the Rediaccfile is **not executed** and containers resume from saved state.
- Fork credentials are resolved automatically. A fork inherits the parent's encryption key, so there is no `--grand` flag on `repo up` any more.
- `--all -m <machine>`: Batch form. Deploy every repository whose home is that machine.

### Stop services
`rdc repo down <ref>` runs Rediaccfile `down()`. Stops containers but does NOT unmount: the repo stays mounted and can be restarted with `repo up`. Use `--unmount` to also close the LUKS volume (this folded in the retired `repo unmount`).

### Delete
`rdc repo delete <ref>` destroys containers, volumes, and encrypted image. The config entry is preserved by default; pass `--archive-config` to move the credentials into the archive, recoverable with `rdc repo admin archive restore <name>`. A bare name resolves to the grand line and is refused when several repos share the base name, so pass `name:tag` to target a fork.

### Prune orphaned resources
`rdc machine prune <machine>` removes empty mount dirs, orphan immovable markers, and stale lock files left behind by deleted repos or failed operations. Only removes resources with no matching repository image. Non-empty mount directories are never removed. Add `--orphaned-repos` to also delete repo images that are in no config.

### Garbage-collect commits
`rdc repo gc -m <machine>` deletes immutable commit objects that no branch or HEAD reaches. Dry-run by default; pass `--apply` to actually delete. It never touches a mounted object or a working fork.

### Status
`rdc repo status <ref>` shows mount state, Docker daemon, container count, disk usage.

## Advanced operations

### Fork (copy-on-write clone)
`rdc repo fork <parent-ref> --tag <tag>` creates an independent copy using the name:tag model, so the fork is named `<parent>:<tag>` (e.g., `my-app:staging`). It gets a new GUID, networkId, and IP range while sharing the parent's name. Parent can remain running. Use `--checkpoint` to capture CRIU process state before forking; the fork auto-restores on first `repo up` (in-memory state preserved for containers with `rediacc.checkpoint=true` label). Cross-machine fork: fork locally first, then `repo push` to the target.

**Agent guard**: AI agents operate in fork-only mode by default — they can only modify fork repositories. Use `repo fork` to create a fork first, then operate on the fork. Grand repo access requires `REDIACC_ALLOW_GRAND_REPO=<name>` (or a comma-separated list like `repo1,repo2`, or `*` for all repos) or `--allow-grand` on the MCP server.

### Naming & targeting (grand vs forks): READ BEFORE delete/promote
Every repo is addressed by a positional **ref**: `name[:tag][@place]`. The **grand** (production) repo is the bare `name`, which is exactly `name:base` (`base` is the reserved birth tag; writing `:base` explicitly is refused). A **fork** is always `name:tag` with some other tag (e.g. `my-app:staging`).

- `rdc repo up app` → the **grand**; `rdc repo up app:test` → that **fork**. Always pass the explicit `:tag` when acting on a fork, across `up` / `down` / `delete` / `term` / `sync`.
- `@place` is an **assertion**, not a selector. `rdc repo up app@server-1` says "app had better be on server-1" and fails if it is not. The machine is derived from the ref either way; `@place` cannot move a repo or pick a copy.
- **Danger:** when several repos share a base name, a bare ref is ambiguous and `repo delete` refuses it rather than guessing. Target the precise `name:tag`. Disambiguate with `rdc machine status <machine> --repositories` (check `is_fork` / `grand_guid`). The grand guard still refuses deleting a production grand from an agent session, but don't rely on it: target by tag.

### Resize (offline)
`rdc repo resize <ref> --size <size>` supports grow and shrink. Must be unmounted first (`repo down --unmount`).

### Expand (online, zero downtime)
`rdc repo expand <ref> --size <size>` is grow-only while the repo is running. Cannot shrink; use `repo resize` for that.

### Apply template
`rdc repo admin template apply <ref> --template <name>` writes Rediaccfile and docker-compose.yaml from a template. `rdc repo admin template list` shows the built-ins.

### Validate
`rdc repo admin validate <ref>` checks the LUKS container, filesystem consistency, and configuration. Use after unexpected shutdowns or to verify backup health.

### Admin verbs
Maintenance verbs live under `rdc repo admin`: `archive {list,restore,purge}`, `fsck`, `validate`, `autostart {enable,disable,list}`, `ownership`, `template {list,apply}`.

## Rediaccfile rules

The Rediaccfile is a bash script with lifecycle functions. Key rules:
- **Must use `renet compose`**, never `docker compose`. Renet injects network isolation and IP allocation.
- Two lifecycle functions: `up()`, `down()`.
- Optional: `info()` for status display.
- `up()`: Pull images, start services. Generate secrets on first run if needed.
- `down()`: Stop and clean up.

### Compose conventions
- Use `renet compose -- "$@"` in Rediaccfiles (no `--network-id` flag — renet passes the network ID automatically via `REDIACC_NETWORK_ID` env var).
- `network_mode` is auto-injected by renet (`network_mode: host` on all services) — do not set it manually.
- **CRIU security settings are auto-injected**: `cap_add: [CHECKPOINT_RESTORE, SYS_PTRACE, NET_ADMIN]`, `security_opt: [apparmor=unconfined]`, and `userns_mode: host` are added to every container by renet. Default seccomp profile is preserved. Do not set these manually.
- `ports:` declarations are ignored (host networking). Services bind to allocated IPs. Add `rediacc.service_port` label for HTTP routing — services without it don't get HTTP routes.
- Use healthchecks in compose for dependent services.
- Persistent data: both `${REDIACC_WORKING_DIR}/...` bind mounts and Docker named volumes are safe (Docker data-root is inside the encrypted LUKS mount).
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
In Rediaccfile shell: `${SVCNAME_IP}`, `${REDIACC_WORKING_DIR}`, `${REDIACC_NETWORK_ID}`.
In containers: `SERVICE_IP`, `REDIACC_NETWORK_ID` (auto-injected by renet).

## Fork routing and backup behavior

- Fork auto-route URL pattern: `{service}-{tag}.{machine}.{baseDomain}` (shared machine cert)
- Custom domains are skipped for forks — the domain belongs to the grand repo
- Scheduled backups skip forks (use `rdc repo push` for manual backup)

## Promote workflow (fork to production)

`repo promote` replaced `repo takeover`. It makes a validated fork the production repo under
its parent's name: the parent keeps its identity (GUID, networkId, domains, autostart, backup
chain) and receives the fork's data. The old production data is preserved as a backup fork.
Promote never fetches bytes; use `repo push` or `backup restore` for that.

1. Fork: `rdc repo fork jfrog --tag upgrade-test`
2. Deploy fork: `rdc repo up jfrog:upgrade-test`
3. Test upgrade in fork (SSH, apply changes, verify)
4. Promote: `rdc repo promote jfrog:upgrade-test`
5. Production now has upgraded data. Old data preserved as backup fork.
6. To revert: `rdc repo promote jfrog:pre-promote-20260317`

Pass an explicit `name:tag`. A bare ref resolves to the parent and is rejected with "not a fork".

## Storage architecture

- A repository lives in a **datastore**: a named, movable storage pool. The implicit default datastore on each machine is a BTRFS pool file on the system disk (`/mnt/rediacc.pool`); additional named datastores are created with `rdc datastore create`.
- `rdc machine status <name> --system` shows both disk and datastore stats plus effective free space
- `rdc machine status <name> --datastores` lists the datastores attached to the machine
- Effective free = min(disk free, datastore free) — the actual limit for new repos
- Grow a named datastore with: `rdc datastore resize <datastore> --size <size>`

## Cleanup behavior

- `repo delete` cleans: storage, Docker daemon + systemd unit, loopback IPs + systemd unit, iptables rules
- `repo down` keeps: Docker daemon, loopback IPs, systemd units (for quick restart with `repo up`)
- `machine prune` removes: orphaned loopback units, unused IPs, stale Docker daemon units from legacy deletions

## Typical deployment workflow

```bash
rdc repo create my-app -m server-1 --size 5G
rdc repo sync upload my-app --local ./my-app/
rdc repo up my-app
rdc machine status server-1 --containers    # verify
```
