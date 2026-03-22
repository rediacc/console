# Observability

Rediacc uses OpenTelemetry to collect traces, metrics, and logs from all services. Data flows to a self-hosted Grafana stack (Tempo, Prometheus, Loki, Pyroscope) via an Alloy OTLP collector.

## Quick Links

| Resource | URL |
|----------|-----|
| Grafana | [grafana.rediacc.io](https://grafana.rediacc.io) |
| OTLP Ingest | `https://otlp.rediacc.io` (Basic auth) |
| Pyroscope | `https://profiles.rediacc.io` (Basic auth) |

## Dashboards

| Dashboard | Purpose | Link |
|-----------|---------|------|
| [Platform Overview](dashboards/platform-overview.md) | Cross-service request rates, errors, latency | [Open](https://grafana.rediacc.io/d/platform-overview) |
| [Account Server](dashboards/account-server.md) | HTTP routes, auth flows, license ops, webhooks | [Open](https://grafana.rediacc.io/d/account-server) |
| [CLI Monitoring](dashboards/cli-monitoring.md) | Command usage, duration, version adoption | [Open](https://grafana.rediacc.io/d/cli-monitoring) |
| [Renet Infrastructure](dashboards/renet-infrastructure.md) | Task throughput, SSH latency, flamegraphs | [Open](https://grafana.rediacc.io/d/renet-infrastructure) |
| [Error Observatory](dashboards/error-observatory.md) | Error triage across all services | [Open](https://grafana.rediacc.io/d/error-observatory) |
| [System & Infrastructure](dashboards/system-infrastructure.md) | Host CPU/memory/disk, container metrics | [Open](https://grafana.rediacc.io/d/system-infrastructure) |

## Services

| Service | Service Name | Language | Signals |
|---------|-------------|----------|---------|
| [CLI](signals/cli.md) | `rediacc-cli` | Node.js | Traces, Metrics, Logs |
| [Account Server](signals/account-server.md) | `rediacc-account-server` | Node.js/Hono | Traces, Logs |
| [Renet Bridge](signals/renet.md) | `renet-bridge` | Go | Traces, Metrics, Logs, Profiling |
| [Renet Execute](signals/renet.md) | `renet-execute` | Go | Traces, Metrics, Logs, Profiling |

## Something Broken? Start Here

1. **Errors spiking?** Open the [Error Observatory](dashboards/error-observatory.md) and follow the [Investigating Errors](runbooks/investigating-errors.md) runbook.
2. **Slow requests?** Check [Slow Requests](runbooks/slow-requests.md) runbook.
3. **Payment/webhook issue?** See [Failed Payments](runbooks/failed-payments.md) runbook.
4. **Adding telemetry?** See [Adding New Signals](runbooks/adding-new-signals.md).

## Reference

- [Architecture](architecture.md) — Stack components, data flow, auth
- [Endpoints](reference/endpoints.md) — URLs, ports, auth details
- [Span Attributes](reference/span-attributes.md) — Complete attribute catalog
- [Prometheus Metrics](reference/prometheus-metrics.md) — Metric names and PromQL
