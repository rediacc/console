# Renet Telemetry

Renet is not a long-running daemon. The console CLI invokes it as a
short-lived subprocess over SSH for each operation: `renet execute` runs a
single task (repo up, fork, backup, and the other Rediaccfile functions) and
`renet list` reports machine status. Each invocation starts its own
OpenTelemetry collector, emits spans, metrics, and logs for that one
operation, flushes, and exits.

## Service Names

| Service Name    | Context                                                          |
|-----------------|------------------------------------------------------------------|
| `renet-execute` | Task execution (`renet execute`), run over SSH by the CLI for `rdc repo up`, forks, backups, etc. |
| `renet-list`    | Machine status (`renet list all`), run over SSH for `rdc machine query` |

## Resource Attributes

| Attribute                | Value / Source                          |
|--------------------------|-----------------------------------------|
| `service.name`           | `renet-execute` or `renet-list`         |
| `service.version`        | Injected at build time via ldflags      |
| `deployment.environment` | Build-time                              |
| `host.name`              | Machine hostname                        |
| `host.arch`              | CPU architecture                        |
| `os.type`                | Operating system                        |
| `runtime.name`           | `go`                                    |
| `runtime.version`        | Go version                              |

## Spans

Spans are created with `Collector.StartSpan(ctx, name, kind)` and closed when
the operation returns; errors are attached via `RecordError`.

| Span name      | Kind     | What it traces                             |
|----------------|----------|--------------------------------------------|
| `execute.task` | `bridge` | A single task run by the local executor    |
| `list.all`     | `bridge` | A `renet list all` machine-status snapshot |

The `bridge` span-kind constant is a legacy label left over from the removed
middleware queue processor. Renaming it rides along with the wider
`pkg/bridge` to `pkg/functions` cleanup and does not change the emitted data.

### Common Span Attributes

| Attribute                | Description                                   |
|--------------------------|-----------------------------------------------|
| `task.id`                | Unique task identifier                        |
| `machine.name`           | Target machine                                |
| `team.name`              | Team context                                  |
| `function.name`          | Rediaccfile function being called             |
| `executor.type`          | Executor that ran the task (`local`, `ssh`)   |
| `repository.guid`        | Target repository GUID (repo-scoped tasks)    |
| `subscription.id`        | Subscription identifier (from the repo license) |
| `subscription.plan_code` | Plan code (from the repo license)             |
| `subscription.status`    | Subscription status (from the repo license)   |

## Metrics

| Metric                | Type      | Description                   |
|-----------------------|-----------|-------------------------------|
| `renet.task.count`    | Counter   | Total tasks processed         |
| `renet.task.duration` | Histogram | Task execution time (ms)      |
| `renet.error.count`   | Counter   | Total errors                  |
| `renet.ssh.duration`  | Histogram | SSH operation time (ms)       |

## Error Handling

- Errors are recorded on spans via `RecordError()`.
- The `renet.error.count` metric is incremented on each error.

## Profiling

Pyroscope continuous profiling at `profiles.rediacc.io`:
- CPU profiling
- Heap allocation profiling
- Goroutine profiling

## Logs

Dual logging setup:
- **OTLP structured logs** via `EmitLog()`, sent to Loki through the collector.
- **logrus**, console output for local debugging.

## Key Code Files

- `private/renet/pkg/telemetry/telemetry.go`: OTel SDK init, span/metric helpers, shutdown
- `private/renet/pkg/telemetry/profiling.go`: Pyroscope integration
- `private/renet/pkg/telemetry/attributes.go`: attribute definitions and span helpers
- `private/renet/pkg/bridge/executor_bridge.go`: in-process task executor behind `renet execute`
- `private/renet/cmd/renet/execute_command.go`: `renet execute` entry point
- `private/renet/cmd/renet/list_commands.go`: `renet list` entry point
