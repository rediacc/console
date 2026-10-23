# Proxy Telemetry

Target design (PLAN-telemetry-export.md, boxes T13 to T15). Two senders cover the executor proxy, each with its own service name.

| Service name | Sender | Transport |
|--------------|--------|-----------|
| `rediacc-proxy` | The proxy Worker `rediacc-proxy-eu` (`workers/proxy`) | Workers Observability destinations `otlp-eu-traces` and `otlp-eu-logs` |
| `rediacc-proxy-executor` | The CLI in `serve --mode container`, behind the proxy | OTLP from the CLI, with the otlp-eu credential fetched from `REDIACC_ACCOUNT_SERVER` |

## rediacc-proxy (Worker)

The Worker exports through the eu destination pair; the path is in [architecture.md](../architecture.md). The Alloy transform maps the script name `rediacc-proxy-eu` to `service.name = rediacc-proxy`.

Attributes set on the active span by `fetch`:

| Attribute | Description |
|-----------|-------------|
| `rediacc.region` | `eu` |
| `deployment.environment` | `production` |
| `rediacc.probe` | UUID from `X-Rediacc-Probe`, when present |
| `rediacc.proxy.outcome` | `health`, `refused:<reason>` or `forwarded` |

A refusal records only a reason code. No token, org id or tenant key reaches a span or log.

## rediacc-proxy-executor (container CLI)

The container initialises telemetry once per process, with `deployment.environment = production` and `rediacc.region` from `REDIACC_REGION` (set to `eu` by the Worker's `executorEnvVars`). Inside a request context an error never shuts telemetry down, and command context and readiness are per request. User attributes come from the introspected caller, not from the executor's own token. Profiling stays off in container mode.

The service name is distinct from `rediacc-cli` because the traffic is not laptop usage. A `renet-execute` span from the target machine appears in the same minute as the executor's command span.

## Querying

```
{ resource.service.name = "rediacc-proxy" }
{ resource.service.name = "rediacc-proxy-executor" }
```

```promql
sum by (service) (increase(traces_spanmetrics_calls_total{service=~"rediacc-proxy|rediacc-proxy-executor"}[1h]))
```

Until the live acceptance (T15) passes, both services are listed as expected but silent senders in the observability repo's CLAUDE.md.
