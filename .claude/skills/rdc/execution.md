# Container & Execution Commands

For full command syntax and options, see [reference.md](reference.md).

## High-level container commands (PREFERRED)

Use `rdc term <machine> <repo> --container <name> --container-action <action>` for container operations. The repo context is required to target the correct isolated Docker daemon.

## Command reference: what to use for each task

| Task | Preferred | Alternative (`rdc run`) |
|------|-----------|------------------------|
| View container logs | `rdc term <m> <repo> --container <c> --container-action logs` | `rdc run container_logs -m <m> --param repository=<repo> --param container=<c> --param lines=<n>` |
| Exec into container | `rdc term <m> <repo> --container <c> --container-action exec` | `rdc run container_exec -m <m> --param repository=<repo> --param container=<c> --param command="..."` |
| List containers | `rdc machine containers <m>` | `rdc run container_list -m <m> --param repository=<repo>` |
| Container stats | `rdc term <m> <repo> --container <c> --container-action stats` | `rdc run container_stats -m <m> --param repository=<repo>` |
| Deploy a repo | `rdc repo up` | — |
| Stop a repo | `rdc repo down` | — |
| Check repo status | `rdc repo status` | — |
| Check machine health | `rdc machine health` | — |

Both forms work. The `term` form is preferred for interactive use; `rdc run` is acceptable for scripting or when you need specific parameter control (e.g., `--param lines=30`).

## rdc run — Low-Level Escape Hatch (hidden, debugging only)

`rdc run` executes raw bridge functions on a machine. It is **hidden from help output and MCP** but still functional as a last resort. **Do NOT use it unless there is no higher-level alternative.** It bypasses safety checks and uses internal function names that may change. Always prefer typed commands (`rdc repo`, `rdc machine`, `rdc term`) over `rdc run`.

Only use `rdc run` for operations with **no** higher-level command (e.g., `container_restart`):
```bash
rdc run container_restart -m <machine> --param repository=<repo> --param container=<name>
```
