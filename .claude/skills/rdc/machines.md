# rdc machine — Remote Machine Inspection

Query machine status, containers, services, and health.

## Commands

### Full machine info
```
rdc machine info <name> [--debug]
```
Shows infrastructure config (base domain, public IPs, TLS), system info, deployed repos, running containers, and systemd services in one view. Use this to check a machine's base domain, public IPs, or any infrastructure setting.

### List containers
```
rdc machine containers <name>
```
Returns containers with: `name`, `status`, `state`, `health`, `cpu`, `memory`, `domain` (custom domain from labels), `autoRoute` (`{service}.{repo}.{machine}.{baseDomain}`), `repository`. JSON output includes full `labels` map with all Docker labels (Traefik rules, rediacc routing, etc.).

### List deployed repositories
```
rdc machine repos <name>
```

### List systemd services
```
rdc machine services <name>
```

### Health check
```
rdc machine health <name> [--output json]
```
Quick health check suitable for CI/CD pipelines.

### Machine status
```
rdc machine status <name>
```

### Deploy backup schedule to machine
```
rdc machine deploy-backup <name>
```
Pushes the configured backup strategy (from `rdc config backup-strategy set`) to the machine as a systemd timer.

## Output formats

All machine commands support the global `--output` flag:
```
rdc --output json machine containers server-1
rdc --output table machine info server-1
```

## Container health states

- `"health": "healthy"` — Container has a healthcheck and it's passing.
- `"health": "none"` — Container has no healthcheck defined (this is normal for app containers).
- `"health": "unhealthy"` — Healthcheck is failing.

## Examples

```bash
# Quick overview of everything on a machine
rdc machine info server-1

# Check if containers are running after deploy
rdc machine containers server-1

# CI/CD health gate
rdc machine health server-1 --output json
```
