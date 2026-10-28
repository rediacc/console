# Proxy Telemetry

Target design (PLAN-telemetry-export.md, boxes T13 to T15, PLAN-proxy-cd-six-targets.md and PLAN-executor-durable-object-policy.md). Two senders cover the executor proxy, each with its own service name.

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

## Durable Object policy backend (planned)

Per PLAN-executor-durable-object-policy, the executor leaves the `Container` class of `@cloudflare/containers`, which Cloudflare maintains only through 2026-12-31, for the `durable_object` scheduling policy. Status: the spike (S1) and the `ExecutorCapacity` coordinator (W2) are landed. `OrgExecutor`, `AccountEgress`, the routing, the sizing, the configs and the cost guard (W1, W3, W4, K1, G1) are not, so every target still runs the `Container` class and none of the new signals below exists yet.

- **Design A.** The spike showed per-instance outbound props holding under the policy, with zero cross answers in 40 interleaved calls. `OrgExecutor` registers `interceptOutboundHttp('account.internal', ctx.exports.AccountEgress({ props: { orgId, containerId } }))` before `start()`, and `AccountEgress` cross-checks `containerId` against `ORG_EXECUTOR.idFromName(orgId)`. Today's egress keeps the allowlist and the token swap.
- **Two backends per Worker version.** The `EXECUTOR` binding (`ExecutorContainer`) and the `ORG_EXECUTOR` binding (`OrgExecutor`, one Durable Object per org, new migration `v2`) sit side by side. The `EXECUTOR_BACKEND` var (`container` or `durable`) picks one per target and per version, never per request. A gradual rollout can briefly route one org to both, and the web client re-grants.
- **Cap in code.** The policy rejects `max_instances`, so the `ExecutorCapacity` coordinator (one per target) holds expiring leases. `EXECUTOR_CAP` is bounded by the literal `HARD_CAP = 25`, and `EXECUTOR_HEAVY_CAP` by `HARD_HEAVY_CAP = 5`. A lease lasts 180 s (the 120 s idle sleep plus 60 s of grace), so a crashed or redeployed instance frees its slot without cleanup. A running instance renews its lease on requests (throttled) and from its idle alarm while a request is in flight, so a long session keeps its slot, and a renew the coordinator no longer holds is acquired again before the instance drains. `acquire` answering `full` or `heavy-full` gives the existing 503 `EXECUTOR_CAPACITY`, and a coordinator failure gives 503 `EXECUTOR_START_FAILED` rather than an uncounted start. The `CAPACITY_ERROR` text guess is retired for this backend.
- **Sizing.** The size is chosen at each container start. An org runs `standard-1` (heavy) when `ExecutorIssuer.route` answers `tier: 'high'` (a BUSINESS or ENTERPRISE plan) or when an out-of-memory exit was recorded in the last 7 days, with at most 5 heavy slots per target. Everything else runs the custom size `{ vcpu: 0.25, memoryMib: 1024, diskMb: 4000 }`, the verdict of the spike, because `lite` (256 MiB) sat near 240 MiB idle in the earlier measurement. A high-tier org that finds the heavy slots full starts light, while an org that is heavy by an out-of-memory exit gets the capacity 503.
- **New signals.** The span attribute `rediacc.proxy.size` takes `light` or `heavy` and never carries an org id. `rediacc.proxy.outcome` gains `oom-heavy`, for an out-of-memory exit under the heavy size.
- **Cost ceiling.** Each config is held at or under $300 a month and the deployable set under $2,100, pinned awake, from the memory and disk prices of the Cloudflare pricing page: $0.0000025 per GiB-second and $0.00000007 per GB-second over 30 days awake, which is $7.21 for a light instance (1 GiB, 4 GB) and $27.37 for a heavy one (4 GiB, 8 GB), so about $281 per target at 20 light and 5 heavy. CPU is billed on active use only and is outside the ceiling.
- **Phases.** Phase 1 deploys the new class beside the old with `EXECUTOR_BACKEND = container`. Phase 2 flips a target to `durable`: bench, then the edge targets, then the stable targets. Phase 3 deletes `ExecutorContainer` (migration `v3`) after 14 days on stable. Phase 1 and Phase 3 are class lifecycle changes, so `wrangler rollback` is refused across them, and their deploy records read `forward-only` with no rollback command. Phase 2 rolls back with `wrangler rollback` to a Phase 1 or later version, or by flipping the var back. No phase touches D1.
