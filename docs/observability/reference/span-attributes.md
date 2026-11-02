# Span Attributes

## Custom Attributes

Defined in `packages/shared/src/telemetry/attributes.ts`.

| Attribute | Key | Used By | Example |
|-----------|-----|---------|---------|
| Subscription ID | `subscription.id` | CLI, Renet | `sub_abc123` |
| Plan Code | `subscription.plan_code` | CLI, Renet | `ENTERPRISE` |
| Subscription Status | `subscription.status` | CLI, Renet | `active` |
| Subscription Source | `subscription.source` | CLI | `stored_token` |
| Machine ID | `machine.id` | CLI, Renet | `3a62c0cf...` |
| Machine Name | `machine.name` | CLI, Renet | `hostinger` |
| Repository GUID | `repository.guid` | Renet | `550e8400-...` |
| Repository Kind | `repository.kind` | Renet | `grand` |
| Team Name | `team.name` | CLI | `Default` |
| Function Name | `function.name` | Renet | `repository_up` |
| Executor Type | `executor.type` | Renet | `local` |
| Task ID | `task.id` | Renet | `local-177...` |

## HTTP Attributes (Account Server)

Standard OpenTelemetry HTTP attributes set by the account server instrumentation:

| Attribute | Key | Example |
|-----------|-----|---------|
| HTTP Method | `http.method` | `POST` |
| HTTP URL | `http.url` | `/api/v1/license/activate` |
| HTTP Status Code | `http.status_code` | `200` |
| HTTP Duration | `http.duration_ms` | `42` |
| HTTP User Agent | `http.user_agent` | `rdc/1.5.0` |

## Workers Identity and Routing Attributes

Set on spans and logs of the account and proxy Workers (target design, PLAN-telemetry-export.md). Identity attributes are written by the Alloy transform (the account middleware also sets `deployment.environment` and `rediacc.region` from its bindings); the rest by the Workers' `ctx.tracing`.

| Attribute | Key | Example |
|-----------|-----|---------|
| Deployment Environment | `deployment.environment` | `edge` |
| Region | `rediacc.region` | `us` |
| Worker Script | `rediacc.worker` | `edge-rediacc-account-us` |
| Route | `http.route` | `/account/api/v1/health` |
| Response Status | `http.response.status_code` | `200` |
| Probe | `rediacc.probe` | UUID from `X-Rediacc-Probe` |
| Proxy Outcome | `rediacc.proxy.outcome` | `health`, `refused:<reason>`, `forwarded` |

## Error Attributes

Set on spans that encounter errors:

| Attribute | Key | Example |
|-----------|-----|---------|
| Error Type | `error.type` | `LicenseExpiredError` |
| Error Message | `error.message` | `License expired on 2026-01-15` |
| Error Stack | `error.stack` | `Error: License expired...\n  at ...` |
| Error Code | `error.code` | `LICENSE_EXPIRED` |
| Error Context | `error.context` | `batch_refresh` |
