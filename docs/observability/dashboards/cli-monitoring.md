# CLI Monitoring

**URL:** https://grafana.rediacc.io/d/cli-monitoring

**Data sources:** Prometheus (span metrics), Tempo

## When to Use

Understanding CLI usage patterns, identifying slow commands, and tracking version adoption across the user base.

## Panels

| Panel | Type | Description |
|-------|------|-------------|
| Command Rate | timeseries | Command execution rate over time, broken down by `span_name` |
| Success vs Error | timeseries | Successful vs failed command rate |
| Command Duration P50/P95/P99 | timeseries | Latency percentiles across all commands |
| Top Commands 1h | barchart | Most frequently executed commands in the last hour |
| Version Distribution | piechart | Breakdown of CLI versions reporting telemetry |
| Environment Distribution | piechart | Breakdown by deployment environment |
| Recent CLI Traces | table (Tempo) | Latest CLI traces with command details |

## Typical Investigations

- **Slow commands** — check Command Duration P95/P99. Click a trace for the slow command to see which span is the bottleneck (SSH connection, remote execution, license check, etc.).
- **Version rollout** — use Version Distribution to confirm users are upgrading after a release.
- **Error spikes** — Success vs Error panel shows the ratio. Filter Recent CLI Traces by `status=error` to find failing commands.
