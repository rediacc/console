# rdc repo — Repository Lifecycle

Repositories are isolated application deployments. Each gets an encrypted LUKS volume, dedicated Docker daemon, loopback IP range, and network isolation.

## Lifecycle commands

### Create
```
rdc repo create <name> -m <machine> --size <size>
```
Creates encrypted volume. Size examples: `2G`, `5G`, `100G`, `1T`. Takes ~15-25s for LUKS formatting. The volume is left mounted and ready for `sync upload` immediately after creation.

### Deploy (start services)
```
rdc repo up <name> -m <machine> [--mount] [--checkpoint]
```
Runs the Rediaccfile lifecycle: `up()`.
- `--mount`: Mount volume first. Required after any `repo push` to a new machine, and for first deploy of forked repos.
- `--checkpoint`: Restore CRIU checkpoint instead of running up() lifecycle. When checkpoint data is found, the Rediaccfile is **not executed** — containers resume directly from saved state.
- `--grand <parent>`: Use parent repo's LUKS credential to unlock a fork. Required when deploying a forked repo that inherited the parent's encryption key.

### Stop services
```
rdc repo down <name> -m <machine> [--unmount]
```
Runs Rediaccfile `down()`. Add `--unmount` to also unmount the volume.

### Delete
```
rdc repo delete <name> -m <machine>
```
Destroys the repository and removes it from config. **Warning**: The config entry is removed globally. If the same repo exists on another machine (e.g., after `repo push`), you must re-add the mapping with `rdc config add-repository`.

### Status
```
rdc repo status <name> -m <machine>
```

### List all repos on a machine
```
rdc repo list -m <machine>
```

## Advanced operations

### Fork (copy-on-write clone)
```
rdc repo fork <parent> -m <machine> --tag <fork-name>
```
Creates an independent copy with new GUID, networkId, and IP range. Parent can remain running. Cross-machine fork: fork locally first, then `repo push` to the target.

### Resize (offline)
```
rdc repo resize <name> -m <machine> --size <new-size>
```
Supports grow and shrink. Repo must be stopped.

### Expand (online, zero downtime)
```
rdc repo expand <name> -m <machine> --size <new-size>
```
Grow-only while repo is running.

### Apply template
```
rdc repo template <name> -m <machine> --file <path> [--grand <parent>]
```
Writes Rediaccfile and docker-compose.yaml from a template file.

### Validate
```
rdc repo validate <name> -m <machine>
```

### Autostart
```
rdc repo autostart enable <name> -m <machine>
rdc repo autostart disable <name> -m <machine>
rdc repo autostart list -m <machine>
```

## Rediaccfile rules

The Rediaccfile is a bash script with lifecycle functions. Key rules:
- **Must use `renet compose`**, never `docker compose`. Renet injects network isolation and IP allocation.
- Two lifecycle functions: `up()`, `down()`.
- Optional: `info()` for status display.
- `up()`: Pull images, start services. Generate secrets on first run if needed.
- `down()`: Stop and clean up.

### Compose conventions
- `network_mode` is auto-injected by renet (`network_mode: host` on all services) — do not set it manually.
- **CRIU security settings are auto-injected**: `cap_add: [CHECKPOINT_RESTORE, SYS_PTRACE, NET_ADMIN]`, `security_opt: [apparmor=unconfined]`, and `userns_mode: host` are added to every container by renet. Default seccomp profile is preserved. Do not set these manually.
- `ports:` declarations are ignored (host networking). Services bind to allocated IPs.
- Use healthchecks in compose for dependent services.
- Persistent data: use `${REPOSITORY_PATH}/...` bind mounts, NOT Docker named volumes.
- Do NOT use `restart: always` or `restart: unless-stopped` — these conflict with CRIU checkpoint/restore. Use `restart: on-failure` or omit it.

### CRIU compatibility
- Apps must handle both `ECONNRESET` (stale socket) and `ECONNREFUSED` (service not yet ready) on persistent connections — after CRIU restore, TCP socket FDs are restored but connections are stale, and dependent services (databases) may need a few seconds to accept connections.
- Use connection pool libraries with automatic reconnection.
- Add `process.on("uncaughtException")` safety net for stale socket errors from internal library objects (e.g., `pg` library's `BoundPool`).
- See the [heartbeat template](https://github.com/rediacc/console/tree/main/packages/json/templates/monitoring/heartbeat) for a reference implementation.

### Available environment variables
In Rediaccfile shell: `${SVCNAME_IP}`, `${REPOSITORY_PATH}`, `${REPOSITORY_NETWORK_ID}`.
In containers: `SERVICE_IP`, `REPOSITORY_NETWORK_ID` (auto-injected by renet).

## Typical deployment workflow

```bash
rdc repo create my-app -m server-1 --size 5G
rdc repo sync upload -m server-1 -r my-app --local ./my-app/
rdc repo up my-app -m server-1
rdc machine containers server-1    # verify
```
