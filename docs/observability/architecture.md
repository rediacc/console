# Observability Architecture

## Data Flow

```
CLI (Node.js)           ──┐
Account Server (CF/Node) ─┼── OTLP HTTP ──▶ otlp.rediacc.io (Alloy) ──┬── Tempo    (traces)
Renet (Go)              ──┘                                             ├── Prometheus (metrics)
                                                                        ├── Loki      (logs)
                                                                        └── Pyroscope  (profiling)
```

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

OTLP endpoints use Basic auth. Credentials are injected at compile time per component:

| Component      | Injection Method |
|----------------|-----------------|
| CLI            | esbuild `define` — `__OTLP_AUTH_TOKEN__` (`packages/cli/bundle.mjs`) |
| Renet          | Go ldflags — `-X pkg/telemetry.otlpUser`, `-X pkg/telemetry.otlpPass` |
| Account Server | Environment variable — `OTEL_AUTH_TOKEN` |

## Cloudflare Workers

The account server's CF Workers deployment uses native tracing via the `[observability]` section in `private/account/wrangler.toml`. This auto-captures request lifecycle, D1 queries, and outbound fetches. Data goes to both the CF dashboard and the self-hosted stack.

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
