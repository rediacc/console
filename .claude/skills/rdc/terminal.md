# rdc term — SSH Terminal Access

SSH into machines and repositories. Auto-configures DOCKER_HOST when targeting a repository.

For full command syntax and options, see [reference.md](reference.md).

## Targeting

`rdc term connect <target>` takes a single positional target. The target is either a
**machine name** (`server-1`) or a **repo ref** (`my-app`, `my-app:staging`), and `term`
picks the right one. There is no `-m` / `-r` flag pair any more.

## When to use `term` vs other commands

`term` is for interactive SSH access or running OS-level commands that have no `rdc` equivalent (e.g., `df -h`, `uptime`, system debugging). **Do NOT use `term connect -c` as a general-purpose SSH escape hatch.**

| Task | Use this | NOT this |
|------|----------|----------|
| List containers | `rdc machine status <m> --containers` | `rdc term connect <m> -c "docker ps"` |
| View container logs | `rdc repo logs <repo> -c <container>` | `rdc term connect <m> -c "docker logs"` |
| Exec into container | `rdc repo exec <repo> -c <container> -- <cmd>` | `rdc term connect <m> -c "docker exec"` |
| Check machine health | `rdc machine health` | `rdc term connect <m> -c "systemctl status"` |
| List repos | `rdc repo list -m <m>` | `rdc term connect <m> -c "ls /mnt/rediacc"` |
| Backup/push repos | `rdc repo push` | `rdc term connect <m> -c "rsync ..."` |
| Checkpoint containers | `rdc repo push --checkpoint` | `rdc term connect <m> -c "docker checkpoint"` |

With `rdc repo exec`, everything after `--` is sent to the container verbatim, so the
CLI's own flags (`-c`, `-i`, `-u`, `--debug`) must come **before** `--`. A `--debug`
placed after `--` is passed to the remote command instead of enabling CLI debug output.

## Sandbox isolation

Each repo has its own SSH key. Repo connections are enforced server-side via `sandbox-gateway` (ForceCommand in `authorized_keys`). The sandbox provides:

- **Landlock LSM**: Kernel-level filesystem restriction to the repo's mount path
- **OverlayFS home**: Writes to `$HOME` captured per-repo, reads fall through to real home
- **Per-repo TMPDIR**: Isolated temp at `<datastore>/.interim/sandbox/<name>/tmp/`
- **Docker access**: Repo's isolated Docker socket via `.envrc` auto-loading
- **`--reset-home`**: Clears per-repo home overlay for a fresh start

Machine-level connections (`rdc term connect <machine>`, where the target is a machine
name rather than a repo ref) use the team key and are not sandboxed.

## Examples

```bash
# Check disk usage on a machine (no rdc equivalent)
rdc term connect server-1 -c "df -h"

# Interactive shell into a repo environment (target is a repo ref)
rdc term connect my-app

# Same, for a fork
rdc term connect my-app:staging
```
