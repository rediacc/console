# Rediacc Audit Events → SIEM (OpenTelemetry Collector)

Reference deployment for routing Rediacc audit events into your SIEM.

The Rediacc account server (`private/account`) mirrors every entry it
writes to the `event_log` table to the OpenTelemetry logs pipeline via
the `getOtelLogger()` helper in `src/services/otel.ts`. This collector
receives those OTLP logs and forwards them to whichever SIEM you have
configured.

## Architecture

```
┌─────────────────────┐   OTLP/HTTP   ┌────────────────┐   exporter   ┌──────────┐
│  rediacc-account    │ ───────────▶  │ OTel Collector │ ───────────▶ │   SIEM   │
│  (event-log.svc)    │   :4318       │  (this dir)    │              └──────────┘
└─────────────────────┘                └────────────────┘
       │                                       ▲
       │ also persists to D1/SQLite            │
       ▼                                       │
   event_log table                             │
                              filter event.domain = rediacc.audit
```

## Quick start

```bash
docker compose up           # collector listens on :4317 (gRPC) and :4318 (HTTP)
```

Point the account server at the collector:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
# or, in your wrangler/Docker env:
#   OTLP_ENDPOINT=http://otel-collector:4318
```

Trigger any CLI machine operation:

```bash
rdc repo up --name myrepo -m myhost
```

Within a few seconds the collector's stdout (default `debug` exporter)
will show the audit event with all OpenTelemetry semantic attributes
(`event.domain=rediacc.audit`, `event.name=cli.repo.up`,
`enduser.id`, `organization.id`, etc.).

## Routing to your SIEM

Edit [`config.yaml`](./config.yaml) and uncomment exactly one exporter
block under the `exporters:` section, then replace `debug` in the
`logs` pipeline's `exporters:` list.

Pre-configured examples:

| SIEM | Exporter | Notes |
|---|---|---|
| OpenSearch / Elasticsearch | `opensearch` | requires `basicauth/opensearch` extension |
| Splunk Enterprise / Cloud | `splunk_hec/audit` | needs a Splunk HEC token + index |
| AWS CloudWatch Logs | `awscloudwatchlogs` | needs IAM credentials in the collector's env |
| Microsoft Sentinel | `azuremonitor` | requires App Insights connection string |

Any [OTel Collector contrib
exporter](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/exporter)
that accepts logs will work — the audit pipeline produces standard OTLP
log records.

## What's emitted

Every row inserted into `event_log` produces one OTLP log record with:

- **Body**: the event type (e.g. `cli.repo.up`).
- **Severity**: `INFO`.
- **Attributes** (OpenTelemetry semantic conventions):
  - `event.domain` = `rediacc.audit` (filter on this)
  - `event.name` = the canonical event type
  - `event.id` = UUID of the row
  - `event.source` = `cli`, `api`, `system`, …
  - `enduser.id` = initiating user
  - `enduser.role` = actor role at time of action
  - `organization.id`, `team.id`
  - `cloud.account.id` = Stripe customerId
  - `subscription.id` = license subscription
  - `audit.data.*` = flattened payload fields (e.g. `audit.data.machineName`,
    `audit.data.functionName`, `audit.data.success`, …)

## Compliance mapping

The audit pipeline satisfies the audit-logging requirements referenced
by Rediacc's compliance posture:

- **GDPR Art. 30** — records of processing activities
- **SOC 2 CC6.1 / CC7.2** — access logging + monitoring
- **HIPAA 45 CFR 164.312(b)** — audit controls
- **PCI DSS Req 10** — track and monitor all access
- **NIS2 Art. 21** — incident reporting capability
- **DORA Art. 10** — ICT-related incident detection

For full SIEM detection content, write [Sigma](https://sigmahq.io)
rules against the `rediacc.audit` event-domain attribute; rules are
SIEM-vendor-neutral and can be converted to OpenSearch / Splunk / etc.
queries via `sigma-cli`.
