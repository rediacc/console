# rdc term — SSH Terminal Access

SSH into machines and repositories. Auto-configures DOCKER_HOST when targeting a repository.

For full command syntax and options, see [reference.md](reference.md).

## When to use `term` vs other commands

`term` is for interactive SSH access or running OS-level commands that have no `rdc` equivalent (e.g., `df -h`, `uptime`, system debugging). **Do NOT use `term connect -c` as a general-purpose SSH escape hatch.**

| Task | Use this | NOT this |
|------|----------|----------|
| List containers | `rdc machine query --containers` | `rdc term connect -c "docker ps"` |
| View container logs | `rdc term connect -m <m> -r <repo> --container <c> --container-action logs` | `rdc term connect -c "docker logs"` |
| Exec into container | `rdc term connect -m <m> -r <repo> --container <c> --container-action exec` | `rdc term connect -c "docker exec"` |
| Check machine health | `rdc machine health` | `rdc term connect -c "systemctl status"` |
| List repos | `rdc machine repos` | `rdc term connect -c "ls /mnt/rediacc"` |
| Backup/push repos | `rdc repo push` | `rdc term connect -c "rsync ..."` |
| Checkpoint containers | `rdc repo push --checkpoint` | `rdc term connect -c "docker checkpoint"` |

## Sandbox isolation

Each repo has its own SSH key. Repo connections are enforced server-side via `sandbox-gateway` (ForceCommand in `authorized_keys`). The sandbox provides:

- **Landlock LSM**: Kernel-level filesystem restriction to the repo's mount path
- **OverlayFS home**: Writes to `$HOME` captured per-repo, reads fall through to real home
- **Per-repo TMPDIR**: Isolated temp at `<datastore>/.interim/sandbox/<name>/tmp/`
- **Docker access**: Repo's isolated Docker socket via `.envrc` auto-loading
- **`--reset-home`**: Clears per-repo home overlay for a fresh start

Machine-level connections (`rdc term connect -m <machine>` without a repo) use the team key and are not sandboxed.

## Examples

```bash
# Check disk usage on a machine (no rdc equivalent)
rdc term connect -m server-1 -c "df -h"

# Interactive shell into a repo environment
rdc term connect -m server-1 -r my-app
```
