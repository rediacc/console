# Renet Infrastructure

**URL:** https://grafana.rediacc.io/d/renet-infrastructure

**Data sources:** Prometheus (span metrics), Tempo, Loki, Pyroscope

## When to Use

Monitoring task processing health, investigating slow SSH operations, or CPU profiling renet.

## Panels

| Panel | Type | Description |
|-------|------|-------------|
| Bridge Task Rate | stat | Current bridge task processing rate |
| Execute Rate | stat | Current command execution rate |
| Error Rate | stat | Current error rate across renet operations |
| P95 Latency | stat | 95th percentile task latency |
| Operation Rate by Type | timeseries | Task rate broken down by operation type |
| Latency Distribution P50/P95 | timeseries | 50th and 95th percentile latency over time |
| CPU Flamegraph | flamegraph (Pyroscope) | CPU profile for renet process |
| Recent Renet Traces | table (Tempo) | Latest renet traces |
| Bridge Logs | table (Loki) | Recent renet bridge log entries |

## Typical Investigations

- **Slow tasks** — check P95 Latency and Latency Distribution. If latency is climbing, look at Operation Rate by Type to identify which operation is slow.
- **CPU hotspots** — the flamegraph panel shows where renet spends CPU time. Useful for identifying inefficient code paths during high load.
- **Bridge errors** — filter Bridge Logs for error-level entries. Cross-reference with Recent Renet Traces to get the full span context.
