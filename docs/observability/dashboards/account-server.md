# Account Server

**URL:** https://grafana.rediacc.io/d/account-server

**Data sources:** Prometheus (span metrics), Tempo, Loki

## When to Use

Debugging account server issues, checking auth flow health, or monitoring license operations.

## Panels

| Panel | Type | Description |
|-------|------|-------------|
| Request Rate | stat | Current requests/s |
| Error Rate | stat (thresholds) | Current error rate. Yellow at moderate, red at high |
| P95 Latency | stat | 95th percentile response time |
| Total Requests 1h | stat | Request count over the last hour |
| Request Rate by Route | timeseries | Per-route request rate over time |
| Latency by Route P95 | timeseries | 95th percentile latency broken down by route |
| Status Code Distribution | piechart | Proportion of 2xx, 4xx, 5xx responses |
| Auth Flow | timeseries | Rates for register, login, magic-link, and device-code operations |
| License Operations | timeseries | Rates for activate, repo, batch, and report operations |
| E2E Tunnel & Webhooks | timeseries | Tunnel and webhook request rates |
| Recent Traces | table (Tempo) | Latest account server traces |
| Error Logs | table (Loki) | Recent error-level log entries |

## Key Routes to Watch

- **Auth Flow panel** — a drop in login/register rate may indicate client-side issues; a spike in errors indicates server problems.
- **License Operations panel** — batch refresh failures will cascade to CLI users who can't validate their license.
- **Status Code Distribution** — 4xx responses are expected (bad credentials, expired tokens). Focus on 5xx growth.
