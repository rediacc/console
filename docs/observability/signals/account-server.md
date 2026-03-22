# Account Server Telemetry

Service name: `rediacc-account-server`, version `0.1.0`

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

Native tracing via `[observability]` section in `wrangler.toml`. Auto-captures:
- Request lifecycle
- D1 database queries
- Outbound fetch calls

### Node.js

Full OTel SDK initialized in `private/account/src/services/otel.ts` before the Hono app is created. This ensures all middleware and route handlers are automatically instrumented.

## Key Code Files

- `private/account/src/services/otel.ts` — OTel SDK initialization (Node.js deployment)
- `private/account/src/middleware/tracing.ts` — Hono tracing middleware
- `private/account/src/middleware/error-handler.ts` — error handling and span status logic
- `private/account/src/utils/record-error.ts` — `recordNonCriticalError()` helper
