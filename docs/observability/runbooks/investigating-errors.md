# Investigating Errors

This guide walks you through finding the root cause of errors showing up in production. The general approach: start with the high-level dashboard, narrow down to a specific service and operation, then dive into the trace to read the actual error.

## Steps

1. **Open the [Error Observatory](https://grafana.rediacc.io/d/error-observatory) dashboard.** This is the single pane of glass for all errors across services. It aggregates span-level error data from Tempo via span metrics in Prometheus.

2. **Check the top stat panels.** Each panel represents a service (account server, renet, CLI). Look for which service has an elevated error count or error rate compared to its baseline. If you are new to the team and do not know the baseline yet, anything above 1% error rate warrants investigation.

3. **Look at the "Error Rate Over Time" timeseries.** Ask yourself:
   - Is this a sudden spike (deployment? infrastructure issue?) or a sustained elevation (bug in code? upstream dependency down)?
   - Does it correlate with a deployment marker? Grafana annotations show deploy times as vertical lines.

4. **Check the "Top Failing Operations" table.** This tells you which specific endpoint or operation is failing the most. The table columns include the span name (usually the route or function), error count, and error rate. Sort by error count to find the noisiest offender.

5. **Click a trace in the "Recent Error Traces" panel.** This opens the Tempo trace view in a new tab. You now have the full distributed trace for a single failed request.

6. **In the trace detail, find spans with ERROR status.** These are highlighted in red in the waterfall view. Expand the span and check these attributes:
   - `error.type` — the error class name (e.g., `DatabaseError`, `StripeAPIError`, `SSHConnectionError`)
   - `error.message` — a human-readable description of what went wrong
   - `error.stack` — the stack trace pointing to the exact line in code

7. **For account server errors, check for structured error codes.** The error handler sets an `error.code` attribute for known error conditions. Examples:
   - `EMAIL_EXISTS` — user tried to register with an already-registered email
   - `SUBSCRIPTION_EXPIRED` — action requires an active subscription
   - `INVALID_TOKEN` — API token is malformed or revoked
   - `STRIPE_WEBHOOK_SIGNATURE_INVALID` — Stripe signature verification failed

   These codes make it easy to distinguish between "expected" errors (user mistakes) and real bugs.

8. **For non-critical errors, look at span events instead of span errors.** Some operations are fire-and-forget: if they fail, the request still succeeds. These show up as span events, not span-level errors. In the trace detail, expand the parent span and look for events named `non_critical_error`. Check the `error.context` attribute to understand what failed:
   - `webhook.email` — a transactional email (welcome, cancellation, payment failed) was not sent
   - `billing.token_revoke` — API token revocation after a subscription change did not complete
   - `webhook.event_log` — audit log write to the database failed
   - `webhook.stripe_metadata` — Stripe metadata update failed

9. **Cross-reference with Loki.** The "Error Logs" panel at the bottom of the Error Observatory dashboard shows log lines that match the same time window. Click a log line to expand it and see the full error message. This is especially useful when the error message is too long for a span attribute or when you need surrounding log context (e.g., the request body that caused the error).

10. **For renet errors, check authentication and task patterns.** Renet tracks consecutive SSH auth failures in the bridge component. If you see auth-related errors:
    - Open the [Renet Infrastructure](https://grafana.rediacc.io/d/renet-infrastructure) dashboard
    - Check the "Task Failure Patterns" panel for recurring failures
    - Look at the "Auth Failure Rate" panel to see if a specific machine is rejecting connections
    - Check if the machine's SSH key has been rotated recently

## Important: What counts as an error

Only **5xx server errors** are counted in error rate metrics. 4xx client errors (validation failures, auth challenges, not-found responses) are **not** errors — they are expected behavior and do not trigger alerts.

If you need to investigate 4xx responses (e.g., a user reports getting 403s), query Prometheus directly:

```promql
traces_spanmetrics_calls_total{http_status_code=~"4.."}
```

This returns all spans with 4xx status codes, broken down by service, route, and exact status code.
