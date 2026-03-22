# CLI Telemetry

Service name: `rediacc-cli`

## Resource Attributes

| Attribute              | Value / Source                |
|------------------------|------------------------------|
| `service.name`         | `rediacc-cli`                |
| `service.version`      | `CLI_VERSION` (currently 0.3.6) |
| `deployment.environment` | build-time                 |
| `service.platform`     | `cli`                        |
| `os.type`              | detected at runtime          |
| `runtime.name`         | `nodejs`                     |
| `runtime.version`      | detected at runtime          |
| `session.id`           | per-invocation UUID          |

## Spans

| Span Name                    | When Created                      |
|------------------------------|-----------------------------------|
| `cli.command.{commandName}`  | Every command execution            |
| `cli.api.call`              | HTTP requests to account server    |
| `cli.error`                 | Error tracking                     |
| `cli.metric`                | Performance measurement points     |

### Span Attributes

**Command spans:** `cli.command`, `cli.args` (anonymized), `cli.options` (anonymized), `cli.version`, `cli.success`, `cli.exit_code`, `cli.error`

**API spans:** `http.method`, `http.url`, `http.status_code`, `http.duration_ms`, `api.endpoint`

## Metrics

| Metric                  | Type      | Labels                             |
|-------------------------|-----------|-------------------------------------|
| `cli.command.count`     | Counter   | command name                        |
| `cli.command.duration`  | Histogram | ms                                  |
| `cli.error.count`       | Counter   | `error.type`                        |
| `cli.api.duration`      | Histogram | ms, `http.method`, `api.endpoint`   |

## User Context

Privacy-safe user attributes attached to spans:

- `user.email_domain` (domain only, not full email)
- `user.team`, `team.name`
- `subscription.id`, `subscription.plan_code`, `subscription.status`, `subscription.source`

## Logs

Command lifecycle logs emitted at `INFO` (started/completed) and `ERROR` (failed) severity.

## Sensitive Data Handling

Passwords, tokens, secrets, and keys are redacted via `anonymizeObject()` before being attached to any span or log.

## Key Code Files

- `packages/cli/src/services/telemetry.ts` — CLI telemetry initialization and span management
- `packages/shared/src/telemetry/attributes.ts` — attribute definitions
- `packages/shared/src/telemetry/utils.ts` — `anonymizeObject()` and sanitization helpers
- `packages/shared/src/telemetry/types.ts` — shared telemetry types
