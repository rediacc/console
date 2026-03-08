# rdc machine — Remote Machine Inspection

Query machine status, containers, services, and health.

## Commands

### Full machine info
```
rdc machine info <name> [--debug]
```
Shows system info, deployed repos, running containers, and systemd services in one view.

### List containers
```
rdc machine containers <name>
```
Returns JSON array of containers with: `name`, `status`, `state`, `health`, `cpu`, `memory`, `repository`.

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
