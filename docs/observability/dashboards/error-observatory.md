# Error Observatory

**URL:** https://grafana.rediacc.io/d/error-observatory

**Data sources:** Prometheus (span metrics), Tempo, Loki

## When to Use

Primary error triage dashboard. Start here when investigating any error across the platform.

## Panels

| Panel | Type | Description |
|-------|------|-------------|
| Total Error Rate | stat | Aggregate error rate across all services |
| Account Server Errors | stat | Account server error rate |
| CLI Errors | stat | CLI error rate |
| Renet Errors | stat | Renet error rate |
| Error Rate Over Time | timeseries | Error rate by service over time |
| Error Rate by Route Top 10 | timeseries | Top 10 routes by error rate |
| Top Failing Operations | table | Operations sorted by error count — shows where errors concentrate |
| Error Latency P95 | timeseries | 95th percentile latency for errored requests |
| Error % by Service | gauge | Error percentage per service |
| Recent Error Traces | table (Tempo) | Latest traces filtered to `status=error` |
| Error Logs | table (Loki) | Logs filtered to error, fail, panic, and fatal |

## Important: What Counts as an Error

Only **5xx server errors** are counted as `SpanStatusCode.ERROR`. **4xx client errors are NOT counted** — they are expected responses (invalid credentials, expired tokens, bad requests).

To investigate 4xx responses specifically, filter by the `http.status_code` attribute in Tempo rather than relying on the error panels.

## Triage Flow

1. Check the four stat panels to identify which service is producing errors.
2. Look at Error Rate Over Time to determine when the issue started.
3. Use Top Failing Operations to find the specific operation.
4. Click a trace in Recent Error Traces to get the full span breakdown.
5. Cross-reference with Error Logs for stack traces and error context.
