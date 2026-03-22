# System Infrastructure

**URL:** https://grafana.rediacc.io/d/system-infrastructure

**Data sources:** Prometheus (node exporter, cAdvisor, OTLP collector metrics), Loki

## When to Use

Host resource monitoring and checking whether the observability stack itself is healthy.

## Panels

| Panel | Type | Description |
|-------|------|-------------|
| CPU Usage % | timeseries | Host CPU utilization over time |
| Memory Usage | timeseries (stacked) | Memory breakdown: used, cached, buffers, free |
| Disk Usage | gauge (thresholds) | Current disk utilization with yellow/red thresholds |
| Network I/O | timeseries | Inbound and outbound network traffic |
| Disk I/O | timeseries | Read and write throughput |
| Container CPU Usage | timeseries | CPU usage per container (by name) |
| Container Memory Usage | timeseries | Memory usage per container (by name) |
| Observability Stack Health | stat | Up/down status for each observability component (Alloy, Prometheus, Tempo, Loki, Pyroscope) |
| OTLP Pipeline Stats | timeseries | Accepted, refused, and exported span counts — detects pipeline backpressure |
| System Logs | table (Loki) | Recent system-level log entries |

## Typical Investigations

- **Resource pressure** — if services are slow, check CPU and Memory panels for saturation. Container-level panels help identify which container is the offender.
- **Disk alerts** — Disk Usage gauge turns red at high utilization. Tempo and Loki are the heaviest disk consumers; consider adjusting retention if disk is filling up.
- **Observability pipeline issues** — if dashboards show gaps in data, check Observability Stack Health for down components and OTLP Pipeline Stats for refused spans.
