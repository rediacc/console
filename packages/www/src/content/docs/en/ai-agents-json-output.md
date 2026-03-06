---
title: JSON Output Reference
description: Complete reference for rdc CLI JSON output format, envelope schema, error handling, and agent discovery commands.
category: Reference
order: 51
language: en
---

All `rdc` commands support structured JSON output for programmatic consumption by AI agents and scripts.

## Enabling JSON Output

### Explicit Flag

```bash
rdc machine info prod-1 --output json
rdc machine info prod-1 -o json
```

### Auto-Detection

When `rdc` runs in a non-TTY environment (piped, subshell, or spawned by an AI agent), output automatically switches to JSON. No flag needed.

```bash
# These all produce JSON automatically
result=$(rdc machine info prod-1)
echo '{}' | rdc agent exec "machine info"
```

## JSON Envelope

Every JSON response uses a consistent envelope:

```json
{
  "success": true,
  "command": "machine info",
  "data": {
    "name": "prod-1",
    "status": "running",
    "repositories": []
  },
  "errors": null,
  "warnings": [],
  "metrics": {
    "duration_ms": 142
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `success` | `boolean` | Whether the command completed successfully |
| `command` | `string` | The full command path (e.g., `"machine info"`, `"repo up"`) |
| `data` | `object \| array \| null` | Command-specific payload on success, `null` on error |
| `errors` | `array \| null` | Error objects on failure, `null` on success |
| `warnings` | `string[]` | Non-fatal warnings collected during execution |
| `metrics` | `object` | Execution metadata |

## Error Responses

Failed commands return structured errors with recovery hints:

```json
{
  "success": false,
  "command": "machine info",
  "data": null,
  "errors": [
    {
      "code": "NOT_FOUND",
      "message": "Machine \"prod-2\" not found",
      "retryable": false,
      "guidance": "Verify the resource name with \"rdc machine info\" or \"rdc config repositories\""
    }
  ],
  "warnings": [],
  "metrics": {
    "duration_ms": 12
  }
}
```

### Error Fields

| Field | Type | Description |
|-------|------|-------------|
| `code` | `string` | Machine-readable error code |
| `message` | `string` | Human-readable description |
| `retryable` | `boolean` | Whether retrying the same command may succeed |
| `guidance` | `string` | Suggested next action to resolve the error |

### Retryable Errors

These error types are marked `retryable: true`:

- **NETWORK_ERROR** — SSH connection or network failure
- **RATE_LIMITED** — Too many requests, wait and retry
- **API_ERROR** — Transient backend failure

Non-retryable errors (authentication, not found, invalid arguments) require corrective action before retrying.

## Filtering Output

Use `--fields` to limit output to specific keys. This reduces token usage when only specific data is needed:

```bash
rdc machine containers prod-1 -o json --fields name,status,repository
```

## Dry-Run Output

Destructive commands support `--dry-run` to preview what would happen:

```bash
rdc repo delete mail -m prod-1 --dry-run -o json
```

```json
{
  "success": true,
  "command": "repo delete",
  "data": {
    "dryRun": true,
    "repository": "mail",
    "machine": "prod-1",
    "guid": "a1b2c3d4-..."
  },
  "errors": null,
  "warnings": [],
  "metrics": {
    "duration_ms": 8
  }
}
```

Commands with `--dry-run` support: `repo up`, `repo down`, `repo delete`, `snapshot delete`, `sync upload`, `sync download`.

## Agent Discovery Commands

The `rdc agent` subcommand provides structured introspection for AI agents to discover available operations at runtime.

### List All Commands

```bash
rdc agent capabilities
```

Returns the full command tree with arguments, options, and descriptions:

```json
{
  "success": true,
  "command": "agent capabilities",
  "data": {
    "version": "1.0.0",
    "commands": [
      {
        "name": "machine info",
        "description": "Show machine status",
        "arguments": [
          { "name": "machine", "description": "Machine name", "required": true }
        ],
        "options": [
          { "flags": "-o, --output <format>", "description": "Output format" }
        ]
      }
    ]
  }
}
```

### Get Command Schema

```bash
rdc agent schema "machine info"
```

Returns detailed schema for a single command, including all arguments and options with their types and defaults.

### Execute via JSON

```bash
echo '{"machine": "prod-1"}' | rdc agent exec "machine info"
```

Accepts JSON on stdin, maps keys to command arguments and options, and executes with JSON output forced. Useful for structured agent-to-CLI communication without constructing shell command strings.

## Parsing Examples

### Shell (jq)

```bash
status=$(rdc machine info prod-1 -o json | jq -r '.data.status')
```

### Python

```python
import subprocess, json

result = subprocess.run(
    ["rdc", "machine", "info", "prod-1", "-o", "json"],
    capture_output=True, text=True
)
envelope = json.loads(result.stdout)

if envelope["success"]:
    print(envelope["data"]["status"])
else:
    error = envelope["errors"][0]
    if error["retryable"]:
        # retry logic
        pass
    else:
        print(f"Error: {error['message']}")
        print(f"Fix: {error['guidance']}")
```

### Node.js

```javascript
import { execFileSync } from 'child_process';

const raw = execFileSync('rdc', ['machine', 'info', 'prod-1', '-o', 'json'], { encoding: 'utf-8' });
const { success, data, errors } = JSON.parse(raw);

if (!success) {
  const { message, retryable, guidance } = errors[0];
  throw new Error(`${message} (retryable: ${retryable}, fix: ${guidance})`);
}
```
