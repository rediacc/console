# Platform Overview

**URL:** https://grafana.rediacc.io/d/platform-overview

**Data sources:** Prometheus (span metrics), Tempo, Loki

## When to Use

First stop for an overall health check. Shows all services at a glance and identifies which one has issues before you drill into a service-specific dashboard.

## Panels

| Panel | Type | Description |
|-------|------|-------------|
| Account Server Req/s | stat | Current request rate for the account server |
| CLI Commands/s | stat | Current CLI command execution rate |
| Renet Tasks/s | stat | Current renet task processing rate |
| Total Errors/s | stat (thresholds) | Aggregate error rate across all services. Yellow/red thresholds flag elevated error rates |
| Request Rate by Service | timeseries | Per-service request rate over time |
| Error Rate by Service | timeseries | Per-service error rate over time |
| P95 Latency by Service | timeseries | 95th percentile latency per service |
| OTLP Pipeline | timeseries | Accepted vs exported spans — shows whether the telemetry pipeline is keeping up |
| Recent Traces | table (Tempo) | Latest traces across all services |
| Recent Logs | table (Loki) | Latest log entries across all services |

## Triage Flow

1. Check the four stat panels at the top for anomalies.
2. If Total Errors/s is elevated, look at Error Rate by Service to find the culprit.
3. Use P95 Latency by Service to spot latency regressions.
4. Click a trace in Recent Traces to jump into Tempo for full span details.
5. If the OTLP Pipeline shows refused or backed-up spans, check the [System Infrastructure](system-infrastructure.md) dashboard for resource issues.
