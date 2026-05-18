---
title: SIEM Integration
description: Route Rediacc audit events to Splunk, OpenSearch, Sentinel, or any OpenTelemetry-compatible SIEM
category: Guides
order: 15
language: en
---

# SIEM Integration

Every machine-level operation issued through the Rediacc CLI is logged
to the account server's `event_log` table and simultaneously emitted as
an OpenTelemetry log record. Operators route those records into a SIEM
(Splunk, OpenSearch, Microsoft Sentinel, AWS CloudWatch, etc.) by
pointing the account server at an OpenTelemetry Collector that exports
to the SIEM of their choice.

This page covers how to wire it up. The audit-event schema and
collector reference deployment are in the public monorepo at
[`compose/otel-collector/`](https://github.com/rediacc/console/tree/main/compose/otel-collector).

## What gets logged

Every entry written to the account server's `event_log` table — and
that includes both account-level events (auth, config storage, license)
and machine-level CLI events (`cli.repo.up`, `cli.repo.fork`,
`cli.backup.push`, `cli.sync.upload`, `cli.term.session`, …) — is
mirrored to the OTLP logs pipeline.

The event-type vocabulary is a closed discriminated union defined in
[`packages/shared/src/audit/event-schema.ts`](https://github.com/rediacc/console/blob/main/packages/shared/src/audit/event-schema.ts).
Adding a new event type requires a code change and is gated by CI, so
SIEM rule authors can rely on the vocabulary being stable.

Each log record carries OpenTelemetry semantic attributes:

| Attribute | Meaning |
|---|---|
| `event.domain` | Fixed `rediacc.audit` — filter on this to ignore unrelated logs |
| `event.name` | The canonical event type (e.g. `cli.repo.up`) |
| `event.source` | `cli`, `api`, `system`, … |
| `enduser.id` | Initiating user |
| `organization.id`, `team.id` | Org/team scope |
| `cloud.account.id` | Stripe customer ID |
| `subscription.id` | License subscription |
| `audit.data.*` | Flattened operation payload |

## Wiring it up

### 1. Deploy the collector

```bash
git clone https://github.com/rediacc/console
cd console/compose/otel-collector
docker compose up -d
```

By default the collector listens on `:4318` (OTLP/HTTP) and writes to
its own stdout via the `debug` exporter — useful for verifying the
pipeline before routing anywhere expensive.

### 2. Point the account server at it

In the account server's environment (`private/account/.env` or your
Docker/Wrangler equivalent):

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
```

Restart the account server. Audit events will begin flowing to the
collector immediately.

### 3. Configure your SIEM exporter

Edit `compose/otel-collector/config.yaml`. The file ships with four
commented exporter examples:

- **OpenSearch / Elasticsearch** — `opensearch` exporter, requires
  `basicauth/opensearch` extension.
- **Splunk HEC** — `splunk_hec` exporter, requires an HEC token + index.
- **AWS CloudWatch Logs** — `awscloudwatchlogs` exporter, requires IAM
  credentials in the collector's env.
- **Microsoft Sentinel** — via the `azuremonitor` exporter with an App
  Insights connection string.

Uncomment exactly one, swap it for `debug` in the `logs:` pipeline's
`exporters:` list, and restart the collector.

Any [OTel Collector contrib
exporter](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/exporter)
that accepts logs will work — the audit pipeline produces standard
OTLP log records.

## Detection content

Audit events are designed for [Sigma](https://sigmahq.io) rule authoring.
Sigma rules are vendor-neutral and convert via `sigma-cli` to native
queries for OpenSearch, Splunk, Sentinel, and others.

Example rule (failed `repo.fork` from an unexpected user):

```yaml
title: Unexpected Rediacc repo fork
detection:
  selection:
    event.domain: rediacc.audit
    event.name: cli.repo.fork
    audit.data.success: false
  condition: selection
level: medium
```

## Compliance posture

The audit pipeline is the foundation for the audit-logging requirements
referenced in Rediacc's compliance documentation:

- **GDPR Art. 30** — records of processing activities
- **SOC 2 CC6.1 / CC7.2** — access logging + monitoring
- **HIPAA 45 CFR 164.312(b)** — audit controls
- **PCI DSS Req 10** — track and monitor all access
- **NIS2 Art. 21** — incident reporting capability
- **DORA Art. 10** — ICT-related incident detection

## Reliability

OTLP emission is fire-and-forget — a collector outage will never block
or fail a Rediacc API request, and every event is still persisted to
the account server's `event_log` table regardless. Combined with the
collector's batching and retry behavior, this makes the pipeline safe
to deploy in front of any SIEM.
