# Observability Architecture

## Data Flow

```
CLI (Node.js)           ──┐
Account Server (CF/Node) ─┼── OTLP HTTP ──▶ otlp.rediacc.io (Alloy) ──┬── Tempo    (traces)
Renet (Go)              ──┘                                             ├── Prometheus (metrics)
                                                                        ├── Loki      (logs)
                                                                        └── Pyroscope  (profiling)
```

The Cloudflare Workers (account server, proxy) do not send OTLP themselves. Workers Observability exports through account-level destinations, shown under Cloudflare Workers below.

All telemetry flows over OTLP HTTP to the Alloy collector, which fans out to the appropriate backend.

## Infrastructure

Runs on the hostinger machine under the `observability` repository (network ID `3136`).

### Stack Versions

| Component  | Version | Role                |
|------------|---------|---------------------|
| Alloy      | 1.14.0  | OTLP collector/router |
| Prometheus | 3.10.0  | Metrics storage     |
| Grafana    | 12.4.1  | Dashboards/alerting |
| Loki       | 3.6.7   | Log aggregation     |
| Tempo      | 2.10.2  | Distributed tracing |
| Pyroscope  | 1.19.0  | Continuous profiling |

## Authentication

OTLP endpoints use per-region Basic auth. Traefik's basicauth middleware on Alloy (`observability/secrets.env:OTLP_BASIC_AUTH`) accepts a comma-separated list of `user:hash` entries — one per region — maintained by the rotation tool.

| Component      | Credential Source |
|----------------|-------------------|
| CLI            | Runtime fetch from the unauthenticated `GET /account/api/v1/telemetry/config` endpoint. Each regional account Worker serves its own `OTLP_CLIENT_CREDENTIALS` secret, so clients automatically get region-appropriate credentials based on which regional URL their account-server config points to. Cached in memory for the CLI process lifetime; never persisted to disk. |
| Renet          | Received as `REDIACC_OTLP_USER` / `REDIACC_OTLP_PASS` env vars, injected by the CLI when spawning `renet execute` via SSH. Renet never contacts the account server itself — it's the CLI's job to fetch and pass through. |
| Account Server | Read from the `OTLP_CLIENT_CREDENTIALS` Worker secret on each regional deployment. |

**Default-deny**: if the regional worker has no `OTLP_CLIENT_CREDENTIALS` secret, the fetch fails, or the CLI is running with `REDIACC_TELEMETRY_DISABLED=1` / `CI=...`, telemetry is completely disabled — no unauthenticated requests, no metadata leakage. When the user opts out via env var, the CLI skips the credential fetch AND injects `REDIACC_TELEMETRY_DISABLED=1` into the remote renet environment via SSH, so the remote renet process also takes its default-deny branch.

### Rotation

Per-region credentials are managed by `./run.sh rotation rotate otlp-{eu,us,asia}`:
1. Generates a random `user:pass` and an `$apr1$`-hashed htpasswd entry
2. Pushes the plaintext `{user, pass}` JSON as the `OTLP_CLIENT_CREDENTIALS` secret to the corresponding regional account Workers
3. SSHes into the observability repo and appends the new htpasswd entry to `secrets.env:OTLP_BASIC_AUTH` (preserving existing entries during grace)
4. Restarts Alloy so Traefik reloads its basicauth middleware label
5. The old entry is removed later via `./run.sh rotation deactivate otlp-<region>` after the grace window

### Historical

Before renet#51, credentials were baked at build time: esbuild `define` for the CLI, Go `-ldflags -X` for renet. Both leaked via bundle inspection and `.go.buildinfo` respectively. The runtime-fetch model fixes both leaks and enables rotation without rebuilds.

## Cloudflare Workers

Target design (PLAN-telemetry-export.md). The runtime's native tracing, enabled by the `[observability]` section of each `workers/account/wrangler.*.toml`, exports to Workers Observability destinations:

```
Account Worker (stable, edge) ─┐
                               ├─ Workers Observability ──▶ destination otlp-<r>-traces / otlp-<r>-logs
Proxy Workers (seven, see below)┘  (account: persist = true;      │  Authorization: Basic
                                    proxy: persist = false)
                                                              ▼
                                   https://otlp.rediacc.io/v1/{traces,logs} (Traefik basicauth ▶ Alloy)
                                                              │  transform: identity, redaction
                                                              ├── Tempo (traces, spanmetrics)
                                                              └── Loki  (logs)
```

Eight destinations exist, `otlp-<r>-traces` and `otlp-<r>-logs` for r in `eu`, `us`, `asia`, `bench`. Stable and edge of a region share a pair, and each proxy Worker uses the pair of its own region with `persist = false`. `./run.sh rotation rotate otlp-<r>` upserts the destination headers when it rotates the credential. The Alloy transform sets `service.name`, `deployment.environment`, `rediacc.region` and `rediacc.worker`, and redacts query strings and tokens. Details are in [signals/account-server.md](signals/account-server.md) and [signals/proxy.md](signals/proxy.md).

Seven proxy Workers send as `rediacc-proxy`: `rediacc-proxy-{eu,us,asia}`, `edge-rediacc-proxy-{eu,us,asia}` and `rediacc-proxy-bench`. The Alloy transform maps their script names, matched by `^(edge-)?rediacc-proxy-(eu|us|asia|bench)$`, to `service.name = rediacc-proxy` and sets `deployment.environment` and `rediacc.region` from the same name. That regex is the target the transform is moved to by box L8 of PLAN-proxy-cd-six-targets. Each Worker also answers `/v1/ready`, described in [signals/proxy.md](signals/proxy.md).

A silent sender is caught by the delivery check and a Grafana alert; see [runbooks/adding-new-signals.md](runbooks/adding-new-signals.md).

## Retention

| Signal  | Backend    | Retention          |
|---------|------------|--------------------|
| Traces  | Tempo      | 30 days            |
| Metrics | Prometheus | 30 days / 50 GB    |
| Logs    | Loki       | Per Loki config    |

## Opt-Out

All telemetry can be disabled:

```bash
REDIACC_TELEMETRY_DISABLED=1  # explicit opt-out
CI=true                        # auto-disabled in CI environments
```
