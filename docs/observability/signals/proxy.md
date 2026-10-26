# Proxy Telemetry

Target design (PLAN-telemetry-export.md, boxes T13 to T15, and PLAN-proxy-cd-six-targets.md). Two senders cover the executor proxy, each with its own service name.

| Service name | Sender | Transport |
|--------------|--------|-----------|
| `rediacc-proxy` | Seven proxy Workers (`workers/proxy`), listed below | Workers Observability destinations `otlp-<r>-traces` and `otlp-<r>-logs` of the Worker's own region |
| `rediacc-proxy-executor` | The CLI in `serve --mode container`, behind the proxy | OTLP from the CLI, with the credential of the Worker's region fetched from `REDIACC_ACCOUNT_SERVER` |

## rediacc-proxy (Worker)

Seven Workers send under this one service name:

| Worker script | Config | `rediacc.region` | `deployment.environment` |
|---------------|--------|------------------|--------------------------|
| `rediacc-proxy-eu` | `workers/proxy/wrangler.eu.toml` | `eu` | `production` |
| `rediacc-proxy-us` | `wrangler.us.toml` | `us` | `production` |
| `rediacc-proxy-asia` | `wrangler.asia.toml` | `asia` | `production` |
| `edge-rediacc-proxy-eu` | `wrangler.edge-eu.toml` | `eu` | `edge` |
| `edge-rediacc-proxy-us` | `wrangler.edge-us.toml` | `us` | `edge` |
| `edge-rediacc-proxy-asia` | `wrangler.edge-asia.toml` | `asia` | `edge` |
| `rediacc-proxy-bench` | `wrangler.bench.toml` | `bench` | `bench` |

Each Worker exports through the destination pair of its own region (`otlp-eu`, `otlp-us`, `otlp-asia`, `otlp-bench`), declared with `persist = false` so the proxy's traffic does not fill Workers Observability storage. The path is in [architecture.md](../architecture.md).

The Alloy transform maps every script name matching `^(edge-)?rediacc-proxy-(eu|us|asia|bench)$` to `service.name = rediacc-proxy` and derives the `deployment.environment` and `rediacc.region` resource attributes, so the Loki streams carry those labels. The regex is the transform's target; box L8 of PLAN-proxy-cd-six-targets applies it on hostinger. Until then only the eu mapping is claimed, unverified (U6).

Attributes set on the active span by `fetch`:

| Attribute | Description |
|-----------|-------------|
| `rediacc.region` | The Worker's `REGION` var |
| `deployment.environment` | The Worker's `ENVIRONMENT` var |
| `rediacc.probe` | UUID from `X-Rediacc-Probe`, when present |
| `rediacc.proxy.outcome` | `health`, `refused:<reason>`, `forwarded`, `capacity` or `start-failed` |

A request carrying a valid probe UUID also writes one log line, `telemetry-probe <uuid>` (lower case), so the delivery check finds the trace and the log of the same request.

## Readiness: /v1/ready

An unauthenticated `GET /v1/ready` (per PLAN-proxy-cd-six-targets, box P1) obtains the issued executor token over the `ISSUER` binding and introspects it over `ACCOUNT` with `{ self: true }`. It answers 200 `{ ready: true, workerVersion }` or 503 `{ ready: false, reason }`. The result is cached for 30 seconds, so the endpoint cannot be driven into token mint storms. The deploy smoke polls it until `workerVersion` equals the deployed version id, because a successful `wrangler deploy` only means the rollout started. Requests to it carry the outcome `health` or a reason code and, like every other path, no token or org id.

A refusal records only a reason code. No token, org id or tenant key reaches a span or log.

## rediacc-proxy-executor (container CLI)

The container initialises telemetry once per process, with `deployment.environment` and `rediacc.region` from `REDIACC_REGION` and the environment the Worker's `executorEnvVars` hands it. Inside a request context an error never shuts telemetry down, and command context and readiness are per request. User attributes come from the introspected caller, not from the executor's own token. Profiling stays off in container mode.

The service name is distinct from `rediacc-cli` because the traffic is not laptop usage. A `renet-execute` span from the target machine appears in the same minute as the executor's command span.

## Querying

```
{ resource.service.name = "rediacc-proxy" }
{ resource.service.name = "rediacc-proxy-executor" }
```

```promql
sum by (service) (increase(traces_spanmetrics_calls_total{service=~"rediacc-proxy|rediacc-proxy-executor"}[1h]))
```

Per-target breakdown, expected to return seven series once box L8 of PLAN-proxy-cd-six-targets passes:

```promql
count by (deployment_environment, rediacc_region) (traces_spanmetrics_calls_total{service="rediacc-proxy"})
```

Until the live acceptance (T15, folded into L8) passes, both services are listed as expected but silent senders in the observability repo's CLAUDE.md.

## Issued executor token and the container

The proxy never holds a long-lived executor token. Per PLAN-console-executor-multi-org, the account Worker's `ExecutorIssuer` RPC entrypoint mints a 45-minute token for one org (`issue(orgId)`, the org named by `route(bearer)`) over the `ISSUER` service binding, the Worker renews it at 80% of its life, and egress swaps it in for a container placeholder on the four executor-bearer paths. The mint and every refusal are audit events of the account server (`executor_token.issued`, `executor_token.refused`), not proxy spans.

## One container per org, and the capacity outcome

Per PLAN-console-executor-multi-org, the Durable Object name is the org id alone, so each org with an active console session holds its own executor container, and an idle one sleeps after 2 minutes. `max_instances` is 25 per proxy config (at most 175 in total), the operator ruling ASKED:2026-10-26T15:26Z "Per-org, raise the cap". An org that would start the 26th concurrent container on one target gets 503 `{ code: 'EXECUTOR_CAPACITY' }` with `Retry-After: 30`, recorded as `rediacc.proxy.outcome=capacity`. Any other failed start is 503 `EXECUTOR_START_FAILED` with the outcome `start-failed`. Neither outcome carries an org id or token on a span or log.

The capacity count per target over 14 days is the input of box ML6, and the container spend is read from the weekly `cf_usage_report` against `.ci/config/cf-spend-guard.json`.
