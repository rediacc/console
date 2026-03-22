# Adding New Telemetry Signals

This guide shows you how to add new spans, metrics, and error tracking to each service. Every example is copy-pasteable — adjust the names and attributes to fit your use case.

## 1. CLI (Node.js)

The CLI uses a lightweight telemetry service that batches events and sends them on process exit.

**Key file:** `packages/cli/src/services/telemetry.ts`

### Adding a tracked event

Use `trackEvent` for discrete events (a button click, a config change, a feature flag check):

```typescript
import { telemetryService } from '../services/telemetry.js';

telemetryService.trackEvent('repo.clone.started', {
  repoName: repo.name,
  machine: machine.hostname,
});
```

### Tracking a long-running operation

For operations that have a measurable duration (deployments, file syncs, provisioning), use `startCommand` and `endCommand`:

```typescript
import { telemetryService } from '../services/telemetry.js';

telemetryService.startCommand('sync.upload');
try {
  await performSync();
  telemetryService.endCommand('sync.upload', { status: 'success', bytesTransferred: 1024 });
} catch (err) {
  telemetryService.endCommand('sync.upload', { status: 'error', error: err.message });
  throw err;
}
```

### Adding error tracking to a silent catch

If you have a `.catch()` that swallows an error (intentionally), still track it so it shows up in telemetry:

```typescript
import { telemetryService } from '../services/telemetry.js';

someOptionalOperation()
  .catch((err) => {
    telemetryService.trackError(err, { operation: 'optional.cleanup' });
    return fallbackValue;
  });
```

This records the error without crashing the CLI. It will appear in traces as a span event.

---

## 2. Account Server (Node.js / Hono)

The account server uses OpenTelemetry auto-instrumentation. Every HTTP route is automatically traced — you do not need to create spans for new routes.

**Key files:**
- `private/account/src/middleware/tracing.ts` — auto-instrumentation setup
- `private/account/src/utils/record-error.ts` — non-critical error recording utility

### Adding custom attributes to an existing span

If a route handler needs to attach extra context to its auto-created span:

```typescript
import { trace } from '@opentelemetry/api';

export async function handleSomeRoute(c) {
  const span = trace.getActiveSpan();
  span?.setAttributes({
    'user.plan': user.subscriptionPlan,
    'repo.count': repositories.length,
    'request.source': c.req.header('x-source') ?? 'unknown',
  });

  // ... rest of handler
}
```

These attributes become searchable in Tempo and appear in the span detail view.

### Recording non-critical errors

For fire-and-forget operations where failure should not break the request (sending emails, updating metadata, logging to an audit table):

```typescript
import { recordNonCriticalError } from '../utils/record-error.js';

// In a webhook handler:
sendWelcomeEmail(user.email, user.name)
  .catch((err) => recordNonCriticalError('webhook.email', err));

revokeOldTokens(user.id)
  .catch((err) => recordNonCriticalError('webhook.token_revoke', err));
```

This records a span event named `non_critical_error` on the current span with `error.context` set to the first argument. The request still returns 200. The error shows up in traces when you expand the span events.

### Creating a manual child span

For operations within a route that you want to time separately (rare — most things are auto-instrumented):

```typescript
import { trace } from '@opentelemetry/api';

const tracer = trace.getTracer('account-server');

async function complexOperation() {
  return tracer.startActiveSpan('complex.operation', async (span) => {
    try {
      span.setAttributes({ 'operation.phase': 'init' });
      const result = await doWork();
      span.setAttributes({ 'operation.result_count': result.length });
      return result;
    } catch (err) {
      span.recordException(err);
      span.setStatus({ code: 2, message: err.message }); // 2 = ERROR
      throw err;
    } finally {
      span.end();
    }
  });
}
```

---

## 3. Renet (Go)

Renet uses a custom telemetry package that wraps the OpenTelemetry Go SDK with typed helpers.

**Key files:**
- `private/renet/pkg/telemetry/telemetry.go` — core telemetry setup and span helpers
- `private/renet/pkg/telemetry/attributes.go` — attribute constants and typed constructors

### Adding a new span

Use `StartSpan` for a generic operation:

```go
import (
    "go.opentelemetry.io/otel/attribute"
    "your-module/pkg/telemetry"
)

func (s *Service) DoSomething(ctx context.Context, repoName string) error {
    ctx, span := telemetry.StartSpan(ctx, "repo.provision",
        attribute.String("repo.name", repoName),
        attribute.String("repo.action", "create"),
    )
    defer span.End()

    // ... your logic here
    // The span duration is automatically measured from creation to End()
}
```

### Using typed span helpers

For common operation categories, use the typed helpers that automatically set the right attributes:

```go
import telem "your-module/pkg/telemetry"

func (s *Service) RunSSHCommand(ctx context.Context, host string) error {
    ctx, span := telem.TrackSSHOperation(ctx, "vault_decrypt", host)
    defer span.End()

    // ... SSH logic
}
```

`TrackSSHOperation` automatically sets `ssh.host`, `operation.type`, and other standard attributes.

### Recording errors

To mark a span as failed (this makes it show up in error dashboards):

```go
import telem "your-module/pkg/telemetry"

result, err := doOperation()
if err != nil {
    telem.RecordError(span, err)  // Sets span status to ERROR, records exception
    return err
}
```

To increment an error counter metric (for alerting thresholds):

```go
telem.RecordErrorCount(ctx, "vault_decrypt_failure", err.Error())
```

This increments a Prometheus counter labeled with the error type, which you can use in alert rules.

### Emitting structured logs

Renet sends logs through the OpenTelemetry log pipeline so they are correlated with traces:

```go
import (
    otellog "go.opentelemetry.io/otel/log"
    telem "your-module/pkg/telemetry"
)

telem.EmitLog(ctx, otellog.SeverityError, "vault decryption failed",
    attribute.String("vault.path", path),
    attribute.String("error.message", err.Error()),
)
```

Logs emitted this way automatically include the trace ID and span ID, so they appear linked in Grafana when you switch between Tempo and Loki.

---

## 4. Viewing Your New Signals

After deploying your changes, here is where to find your new telemetry data:

| Signal | Backend | Appears in | Delay |
|--------|---------|-----------|-------|
| Traces (spans) | Tempo | Grafana Explore -> Tempo datasource | Seconds |
| Metrics (span metrics) | Prometheus | Grafana Explore -> Prometheus datasource | ~60 seconds |
| Logs | Loki | Grafana Explore -> Loki datasource | Seconds |

### Finding your new traces

1. Go to **Grafana Explore** -> select **Tempo** datasource
2. Search by **Service Name** = your service
3. Search by **Span Name** = the name you used in `StartSpan`, `startActiveSpan`, or `trackEvent`
4. Your spans should appear within seconds of the first request

### Querying your new metrics

Span metrics are auto-generated by Tempo from your traces. Every new span name automatically gets:

- `traces_spanmetrics_calls_total{span_name="your.span.name"}` — request count
- `traces_spanmetrics_latency_bucket{span_name="your.span.name"}` — latency histogram

To query in Grafana:

1. Go to **Grafana Explore** -> select **Prometheus** datasource
2. Enter the metric name (e.g., `traces_spanmetrics_calls_total{span_name="repo.provision"}`)
3. Metrics appear approximately 60 seconds after the first span is recorded

### Finding your new logs

1. Go to **Grafana Explore** -> select **Loki** datasource
2. Query by label: `{service_name="your-service"}` or by content: `{source="docker"} |~ "your search term"`
3. Console output from all services is captured by Alloy and shipped to Loki automatically

### Tips

- **Use consistent naming.** Span names should follow `noun.verb` or `noun.operation` format (e.g., `repo.provision`, `vault.decrypt`, `webhook.process`). This makes them easy to find and group.
- **Do not over-instrument.** Every span adds overhead. Instrument operations that are meaningful to debug (I/O calls, external APIs, complex business logic). Do not wrap every function in a span.
- **Add attributes, not spans.** If you just need to record a value (a user ID, a count, a flag), add it as an attribute on the existing span rather than creating a new child span.
- **Custom attributes are searchable.** Any attribute you set on a span can be searched in Tempo. Use this to add domain-specific context that helps you filter traces later.
