# rdc machine — Remote Machine Inspection

Query machine status, containers, services, and health.

For full command syntax and options, see [reference.md](reference.md).

## Output details

**machine query** — Shows infrastructure config (base domain, public IPs, TLS), system info, deployed repos, running containers, and systemd services in one view. Use this to check a machine's base domain, public IPs, or any infrastructure setting.

**machine containers** — Table shows: `name`, `state`, `health`, `domain`, `autoRoute`, `repository`. JSON output includes full `ContainerInfo` with all fields (`labels`, `port_mappings`, `image`, `id`, `state`, `health`, `cpu_percent`, `memory_usage`, etc.) plus enriched fields: `repository` (resolved name), `repository_guid` (original GUID), `domain` (from labels), `autoRoute` (`{service}.{repo}.{machine}.{baseDomain}`).

**machine repos** — Table shows: name, GUID, size, mount status, Docker state, container count, disk usage, modified date, Rediaccfile present. JSON output includes `name` (resolved) and `guid` (original GUID), nests each repo's `containers` (with `domain`, `autoRoute`, `repository`/`repository_guid`) and `services` arrays. Use `--search` to filter by name or GUID.

**machine services** — Table shows: name, state, sub-state, restart count, memory, repository. JSON output includes full `ServiceInfo` with `repository` (resolved name) and `repository_guid` (original GUID). Use `--stability-check` to exit code 2 if any failed/restarting (CI/CD).

**machine health** — Quick health check suitable for CI/CD pipelines.

**machine deploy-backup** — Pushes the configured backup strategy (from `rdc config backup-strategy set`) to the machine as a systemd timer.

## Output formats

All machine commands support the global `--output` flag (`json` or `table`).

## Container health states

- `"health": "healthy"` — Container has a healthcheck and it's passing.
- `"health": "none"` — Container has no healthcheck defined (this is normal for app containers).
- `"health": "unhealthy"` — Healthcheck is failing.

## Examples

```bash
# Quick overview of everything on a machine
rdc machine query server-1

# Check if containers are running after deploy
rdc machine containers server-1

# CI/CD health gate
rdc machine health server-1 --output json
```
