# Renet Telemetry

## Service Names

| Service Name     | Context                                         |
|------------------|--------------------------------------------------|
| `renet-bridge`   | Middleware-triggered queue processor              |
| `renet-execute`  | CLI-triggered direct execution (`rdc run`, `rdc repo up`) |

## Resource Attributes

| Attribute              | Value / Source                          |
|------------------------|----------------------------------------|
| `service.name`         | `renet-bridge` or `renet-execute`      |
| `service.version`      | Injected at build time via ldflags     |
| `deployment.environment` | Build-time                           |
| `host.name`            | Machine hostname                       |
| `host.arch`            | CPU architecture                       |
| `os.type`              | Operating system                       |
| `runtime.name`         | `go`                                   |
| `runtime.version`      | Go version                             |

## Span Types

| Tracker Function       | Span Type | What It Traces                      |
|------------------------|-----------|--------------------------------------|
| `TrackQueueOperation`  | `queue`   | Task queue processing                |
| `TrackSSHOperation`    | `ssh`     | SSH command execution                |
| `TrackAPICall`         | `api`     | Outbound API requests                |
| `TrackVaultOperation`  | `vault`   | Vault secret operations              |
| `TrackBridgeEvent`     | `bridge`  | Bridge lifecycle events              |

### Common Span Attributes

| Attribute                 | Description                     |
|---------------------------|---------------------------------|
| `task.id`                 | Unique task identifier          |
| `machine.name`            | Target machine                  |
| `team.name`               | Team context                    |
| `function.name`           | Rediaccfile function being called |
| `priority`                | Task priority                   |
| `executor.type`           | `bridge` or `execute`           |
| `repository.guid`         | Target repository GUID          |
| `subscription.id`         | Subscription identifier         |
| `subscription.plan_code`  | Plan code                       |
| `subscription.status`     | Subscription status             |

## Metrics

| Metric                | Type      | Description                   |
|-----------------------|-----------|-------------------------------|
| `renet.task.count`    | Counter   | Total tasks processed         |
| `renet.task.duration` | Histogram | Task execution time (ms)      |
| `renet.error.count`   | Counter   | Total errors                  |
| `renet.ssh.duration`  | Histogram | SSH operation time (ms)       |

## Error Handling

- Errors are recorded on spans via `RecordError()`
- `ErrorCount` metric is incremented on each error
- Auth failures tracked with a consecutive counter — after 5 consecutive auth failures, the bridge shuts down

### Panic Recovery

Worker goroutines in `pkg/bridge/worker.go` use `defer`/`recover`. Panics are logged with full stack traces and do not crash the process.

## Profiling

Pyroscope continuous profiling at `profiles.rediacc.io`:
- CPU profiling
- Heap allocation profiling
- Goroutine profiling

## Logs

Dual logging setup:
- **OTLP structured logs** via `EmitLog()` — sent to Loki through the collector
- **logrus** — console output for local debugging

## Key Code Files

- `private/renet/pkg/telemetry/telemetry.go` — OTel SDK initialization and shutdown
- `private/renet/pkg/telemetry/profiling.go` — Pyroscope integration
- `private/renet/pkg/telemetry/attributes.go` — attribute definitions and span helpers
- `private/renet/pkg/bridge/bridge.go` — bridge lifecycle and task dispatch
- `private/renet/pkg/bridge/worker.go` — worker goroutines with panic recovery
- `private/renet/cmd/renet/execute_command.go` — CLI-triggered execution entry point
