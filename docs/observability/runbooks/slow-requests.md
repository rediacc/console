# Finding Performance Bottlenecks

This guide helps you track down why a request, command, or operation is slow. The approach: identify the slow route from dashboard metrics, find an example trace, and read the waterfall to pinpoint the bottleneck.

## Steps

### 1. Open the right dashboard

Each service has its own dashboard with latency panels:

| Service | Dashboard | Key Panel |
|---------|-----------|-----------|
| Account Server | [Account Server](https://grafana.rediacc.io/d/account-server) | "Latency by Route (P95)" |
| CLI | [CLI Monitoring](https://grafana.rediacc.io/d/cli-monitoring) | "Command Duration P50/P95/P99" |
| Renet | [Renet Infrastructure](https://grafana.rediacc.io/d/renet-infrastructure) | "Latency Distribution" |

### 2. Identify the slow route or command

Look at the timeseries panels listed above. Each line represents a route (account server), CLI command, or renet operation. Find the line that is elevated compared to its baseline. Note the exact span name — you will need it in the next step.

### 3. Search for example traces in Tempo

1. Go to **Grafana Explore** (compass icon in the left sidebar)
2. Select the **Tempo** datasource from the dropdown at the top
3. Use the search tab with these filters:
   - **Service Name** = the affected service (e.g., `rediacc-account-server`, `rdc-cli`, `renet`)
   - **Span Name** = the route or operation you identified in step 2
   - **Duration** > your threshold (e.g., `> 1s` for API routes, `> 10s` for CLI commands, `> 30s` for renet provisioning)
4. Click **Run query**. You will get a list of traces sorted by duration.

### 4. Click a slow trace to open the waterfall view

The waterfall shows every span in the request, laid out horizontally by time. The total request duration is at the top. Each child span is indented under its parent.

### 5. Find the bottleneck

Look for the **widest span** in the waterfall — that is where most of the time is being spent. It might be:

- A single slow span (e.g., a database query that took 3 seconds)
- Many sequential spans (e.g., 50 small SSH commands executed one after another)
- A gap between spans (the application was doing CPU work not covered by a span)

### 6. Interpret common bottleneck patterns

**Account server — common slow spots:**
- **Stripe API calls** — external HTTP calls to `api.stripe.com`. Look for spans with `http.url` containing `stripe.com`. Stripe latency is outside your control but you can cache or batch.
- **D1/SQLite queries** — database spans with `db.system = sqlite`. Check the `db.statement` attribute for the actual query. Missing indexes show up as full table scans on large tables.
- **SES email sending** — spans with `messaging.system = ses`. SES calls to `email.us-east-1.amazonaws.com` can take 200-500ms each.

**CLI — common slow spots:**
- **SSH connection setup** — the initial TCP + key exchange. Look for spans named `ssh.connect`. If this is slow, it is usually network latency to the machine or DNS resolution.
- **Renet provisioning** — the full repo deployment sequence. This involves multiple SSH commands in sequence; the waterfall will show each one.
- **Large file sync** — rsync transfers. Look for spans with `sync.bytes` attribute to see how much data was transferred.

**Renet — common slow spots:**
- **SSH command execution** — remote commands on the machine. Check `ssh.command` attribute for the exact command.
- **Vault decryption** — decrypting repository secrets. Look for `vault.decrypt` spans.
- **Compose operations** — `docker compose up` or `docker compose pull`. These can be slow if images need to be pulled.

### 7. Investigate CPU-bound issues in renet

If the bottleneck is not I/O (no wide spans, just a gap in the waterfall), the issue might be CPU-bound. Renet has continuous profiling enabled:

1. Open the [Renet Infrastructure](https://grafana.rediacc.io/d/renet-infrastructure) dashboard
2. Scroll to the **CPU Flamegraph** panel (powered by Pyroscope)
3. Select the time range matching the slow request
4. The flamegraph shows which functions consumed the most CPU time. Look for hot functions that should not be expensive.

### 8. Useful PromQL queries

**P99 latency by route (account server):**

```promql
histogram_quantile(0.99, sum(rate(traces_spanmetrics_latency_bucket{service="rediacc-account-server"}[5m])) by (le, span_name))
```

This gives you the 99th percentile latency for every route over a 5-minute window. Replace `0.99` with `0.95` or `0.50` for P95 or P50.

**Request rate by route (to correlate load with latency):**

```promql
sum(rate(traces_spanmetrics_calls_total{service="rediacc-account-server"}[5m])) by (span_name) > 0
```

This shows the per-second request rate for each route. If a route suddenly got more traffic and latency increased, you might have a load-induced bottleneck.

**Apdex score (fraction of requests under a target duration):**

```promql
sum(rate(traces_spanmetrics_latency_bucket{service="rediacc-account-server", le="0.5"}[5m])) by (span_name)
/
sum(rate(traces_spanmetrics_latency_count{service="rediacc-account-server"}[5m])) by (span_name)
```

This tells you what fraction of requests complete in under 500ms. Adjust the `le="0.5"` value to change the target threshold.
