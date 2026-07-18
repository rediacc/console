# Container & Execution Commands

For full command syntax and options, see [reference.md](reference.md).

## High-level container commands (PREFERRED)

Container operations are first-class `repo` verbs. They take a repo ref positionally
(`my-app`, `my-app:staging`) and derive the machine from it. The container is selected
with `-c` and is only needed when the repo runs more than one.

```bash
rdc repo logs <repo> -c <container> --lines 50      # logs (add -f to follow)
rdc repo exec <repo> -c <container> -- <cmd>        # run a command; exit code passes through
rdc repo exec <repo> -c <container> -i -- bash      # interactive shell in the container
```

## Command reference: what to use for each task

| Task | Command |
|------|---------|
| View container logs | `rdc repo logs <repo> -c <container> --lines <n>` |
| Follow container logs | `rdc repo logs <repo> -c <container> -f` |
| Exec into container | `rdc repo exec <repo> -c <container> -- <cmd>` |
| List containers | `rdc machine status <machine> --containers` |
| Container CPU/memory | `rdc machine status <machine> --containers --output json` (`cpu_percent`, `memory_usage`) |
| Deploy a repo | `rdc repo up <repo>` |
| Stop a repo | `rdc repo down <repo>` |
| Check repo status | `rdc repo status <repo>` |
| Check machine health | `rdc machine health` |

`rdc repo exec` passes the container command's own exit code straight through, so it
works in scripts and conditionals.

**Flag placement:** everything after `--` is sent to the container verbatim, so the CLI's
own flags (`-c`, `-i`, `-u`, `--debug`) must come **before** `--`. A `--debug` written
after `--` becomes an argument of the remote command and never turns on CLI debug output.

## rdc run — Low-Level Escape Hatch (hidden, debugging only)

`rdc run` executes raw bridge functions on a machine. It is **hidden from help output and MCP** but still functional as a last resort. **Do NOT use it unless there is no higher-level alternative.** It bypasses safety checks and uses internal function names that may change. Always prefer typed commands (`rdc repo`, `rdc machine`, `rdc term`) over `rdc run`.

The function name is passed with `-f`, not positionally:

```bash
rdc run -f <function> -m <machine> --param <key>=<value>
```

Only use `rdc run` for operations with **no** higher-level command (e.g., `container_restart`):
```bash
rdc run -f container_restart -m <machine> --param repository=<repo> --param container=<name>
```
