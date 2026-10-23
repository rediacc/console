# Account Server Telemetry

Service name: `rediacc-account-server`, version `0.1.0` on Node. On Cloudflare Workers the service name reaches the stack as the Worker script name and is normalised to `rediacc-account-server` on arrival (see Identity).

## Auto-Instrumentation

Every HTTP request gets a span automatically via Hono middleware. No manual instrumentation needed for basic request tracing.

### Span Name Format

```
{METHOD} {path}
```

Examples: `POST /account/api/v1/auth/login`, `GET /account/api/v1/licenses/activate`

### Span Attributes

| Attribute            | Description                        |
|----------------------|------------------------------------|
| `http.method`        | HTTP method                        |
| `http.url`           | Request URL                        |
| `http.user_agent`    | Client user agent                  |
| `http.status_code`   | Response status code               |
| `http.duration_ms`   | Request duration in milliseconds   |

### Error Attributes (5xx only)

| Attribute       | Description                              |
|-----------------|------------------------------------------|
| `error.type`    | Error class name                         |
| `error.message` | Error message                            |
| `error.stack`   | Stack trace (truncated to 1000 chars)    |
| `error.code`    | Application error code (for `AppError`)  |

## Status Code Logic

- **5xx** responses set `SpanStatusCode.ERROR` — these are server failures that need attention.
- **4xx** responses set `SpanStatusCode.OK` — client errors are expected behavior. Still queryable via `http.status_code` attribute.

## Non-Critical Errors

`recordNonCriticalError()` adds span events (not span status errors) with context attributes:

| Attribute        | Description              |
|------------------|--------------------------|
| `error.context`  | Where the error occurred |
| `error.type`     | Error class name         |
| `error.message`  | Error message            |

Used for errors that shouldn't mark the request as failed:
- Webhook email delivery failures
- Token revocation errors
- Stripe API errors
- Email delivery failures

## Routes

70+ HTTP endpoints across:

- **Auth:** register, login, 2FA, magic-link
- **Portal:** subscription, billing, refund
- **Admin:** management endpoints
- **Device codes:** CLI login flow
- **Licenses:** activate, report, batch refresh
- **API tokens:** CRUD
- **Webhooks:** Stripe, email
- **Tunnel:** E2E encrypted communication

## Deployment Modes

### Cloudflare Workers

Target design (PLAN-telemetry-export.md; not yet implemented where a box is open). The Worker runtime creates the spans, and Workers Observability exports traces and logs to the self-hosted stack through account-level OTLP destinations. No OTel SDK runs inside the Worker.

Auto-captured by the runtime: request lifecycle, D1 queries, outbound fetch calls.

Destinations: `otlp-<r>-traces` and `otlp-<r>-logs` for r in `eu`, `us`, `asia`, `bench`, posting to `https://otlp.rediacc.io/v1/traces` and `/v1/logs` with that region's Basic credential. The stable and edge Workers of a region share the pair. Each `wrangler.*.toml` names its pair in `[observability.traces]` and `[observability.logs]` (`destinations`, `persist = true`, `head_sampling_rate = 1`). `./run.sh rotation rotate otlp-<r>` upserts the destination headers, so delivery continues through a rotation. The credential travels only in the API request body.

#### Identity

Cloudflare reports `service.name` as the Worker script name (for example `edge-rediacc-account-us`) and only on some spans. An Alloy transform maps it onto the identity set on every span and log:

| Attribute | Values |
|-----------|--------|
| `service.name` | `rediacc-account-server` for `(edge-)rediacc-account-*` |
| `deployment.environment` | `production`, `edge`, `bench` |
| `rediacc.region` | `eu`, `us`, `asia` (bench is `eu`, told apart by `deployment.environment=bench`) |
| `rediacc.worker` | the original script name |

Cloudflare also sets `cloudflare.script_name`, `faas.name`, `cloudflare.script_version.id` and `cloudflare.colo`; fetch spans carry `url.full`, `url.path` and `geo.*`. Their placement across spans is recorded from a live probe before the transform is written.

#### Attributes set by the tracing middleware

When `executionCtx.tracing` exists, the middleware sets these on the active span and records exceptions:

| Attribute | Description |
|-----------|-------------|
| `http.route` | Route pattern, not the raw path |
| `http.response.status_code` | Response status code |
| `deployment.environment` | `ENVIRONMENT` of the deployment |
| `rediacc.region` | `REGION` of the deployment |
| `rediacc.probe` | UUID from the `X-Rediacc-Probe` header, only when the value is a UUID |

The raw user agent and the query string are not copied.

#### Probe header

`GET /account/api/v1/health` with `X-Rediacc-Probe: <uuid4>` marks the request. The Worker sets `rediacc.probe` on the span and logs `telemetry-probe <uuid>`. The delivery check (`python3 -m rediacc_ci.ops.telemetry_delivery`) sends one probe to each of the seven hosts and searches Tempo and Loki for it:

```
{ resource.service.name = "rediacc-account-server" && span.rediacc.probe = "<uuid>" }
```

#### Redaction

One-time tokens travel in URL queries (magic link, password reset, email confirm, invite), so `url.full` would carry live tokens. The Alloy transform:

- strips the query from `url.full`
- keeps `geo.locality.*` (city-level location, operator ruling 2026-10-23)
- rewrites `token=<value>` in log bodies

#### Limits

Workers infrastructure and custom metrics cannot be exported over OpenTelemetry; request metrics come from Tempo spanmetrics. Trace ids are not propagated outside Cloudflare, so CLI and account traces do not join.

### Node.js

Span name is `{METHOD} {routePath}`. Full OTel SDK initialized in `private/account/src/services/otel.ts` before the Hono app is created. This ensures all middleware and route handlers are automatically instrumented.

## Key Code Files

- `private/account/src/services/otel.ts` — OTel SDK initialization (Node.js deployment)
- `private/account/src/middleware/tracing.ts` — Hono tracing middleware
- `private/account/src/middleware/error-handler.ts` — error handling and span status logic
- `private/account/src/utils/record-error.ts` — `recordNonCriticalError()` helper
