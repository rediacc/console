# Heartbeat Template — CRIU-Compatible Reference

A minimal PostgreSQL + Node.js heartbeat app designed as a reference for writing CRIU-compatible Rediacc templates.

## What it does

- PostgreSQL stores heartbeat records (DB counter persists across restarts)
- Node.js app writes a beat every 5 seconds with an in-memory counter
- In-memory counter resets on container restart but survives CRIU checkpoint/restore
- After CRIU restore, the counter continues from where it was checkpointed (proving live migration)

## CRIU compatibility rules

Any Rediacc template that should survive `backup push --checkpoint` must follow these rules:

### Networking

- **Renet forces `network_mode: host`** on all services during `renet compose`. Your compose file's `network_mode` is overwritten.
- Each service gets a dedicated loopback IP (e.g., `127.0.24.194`). Bind to `SERVICE_IP`, not `0.0.0.0`.
- Inter-service communication uses loopback IPs, not Docker DNS names. After CRIU restore, DNS names won't resolve but loopback IPs will.
- Use `env_file` or environment variables for connection strings — never hardcode IPs.

### TCP connection resilience

CRIU restores process memory including TCP socket file descriptors, but the underlying TCP connections are stale after cross-machine restore. Apps with persistent connections **must** handle reconnection:

- **Database pools** (`node-postgres`, `mysql2`, etc.): Listen for pool `error` events and recreate the pool.
- **Catch `ECONNRESET`**: After restore, stale sockets emit `ECONNRESET`. Handle it gracefully instead of crashing.
- **Safety net for internal emitters**: Some libraries emit errors on internal objects that bypass your error handler. Add `process.on("uncaughtException")` to catch `ECONNRESET` and `"Connection terminated unexpectedly"`.
- **Pattern** (Node.js):
  ```javascript
  function createPool() {
    const p = new Pool(config);
    p.on("error", (err) => {
      console.error(`Pool error: ${err.message}`);
      replacePool();
    });
    return p;
  }

  let pool = createPool();

  function replacePool() {
    const old = pool;
    pool = createPool();
    old.end().catch(() => {});
  }

  process.on("uncaughtException", (err) => {
    if (err.code === "ECONNRESET" || err.message.includes("Connection terminated")) {
      replacePool();
      return;
    }
    process.exit(1);
  });
  ```

### Restart policy

- **Do NOT use** `restart: always` or `restart: unless-stopped` — these conflict with CRIU checkpoint/restore.
- Use `restart: on-failure` or omit it entirely.
- Renet manages container lifecycle; restart policies interfere with checkpoint restore.

### Storage

- All persistent data **must** use `${REDIACC_WORKING_DIR}/...` bind mounts.
- Do NOT use Docker named volumes — they live outside the LUKS repo and won't be included in backups or forks.

### Compose conventions

- Do NOT add `network_mode` — renet injects `host` automatically.
- Do NOT add `rediacc.*` labels — renet injects them.
- Do NOT add `ports:` mappings for host access — they're ignored in host mode. Use `rediacc.service_port` label for proxy routing.
- The compose service name becomes the auto-route URL prefix (e.g., service `heartbeat` at networkId 6336 becomes `heartbeat-6336.example.com`).

## Files

| File | Purpose |
|------|---------|
| `docker-compose.yaml` | Service definitions (postgres + node app) |
| `Rediaccfile` | Lifecycle functions (prep, up, down, info) |
| `app/heartbeat.mjs` | Heartbeat app with CRIU-safe reconnection logic |
| `app/package.json` | Node.js dependencies |

## Testing CRIU migration

```bash
# Deploy on source
rdc repo create heartbeat-app -m source --size 2G
rdc repo template heartbeat-app -m source --file <template.json>
rdc repo up heartbeat-app -m source

# Wait for beats, note the counter value

# Checkpoint + push to target
rdc repo backup push heartbeat-app -m source --to-machine target --checkpoint

# Restore on target
rdc repo up heartbeat-app -m target --mount --checkpoint

# Verify counter continues (not restart from 1)
rdc term target heartbeat-app -c "docker logs heartbeat_app --tail 10"
```
