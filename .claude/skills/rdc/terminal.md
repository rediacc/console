# rdc term — SSH Terminal Access

SSH into machines and repositories. Auto-configures DOCKER_HOST when targeting a repository.

## Commands

### Interactive shell to a machine
```
rdc term <machine>
```

### Interactive shell to a repository
```
rdc term <machine> <repository>
```
Sets DOCKER_HOST and working directory automatically so `docker` commands target the repo's isolated daemon.

### Run a command (non-interactive)
```
rdc term <machine> -c "<command>"
rdc term <machine> <repository> -c "<command>"
```

### Container access
```
rdc term <machine> --container <id> [--container-action <action>]
```
Actions: `terminal`, `logs`, `stats`, `exec`.

## When to use `term` vs other commands

`term` is for interactive SSH access or running OS-level commands that have no `rdc` equivalent (e.g., `df -h`, `uptime`, system debugging). **Do NOT use `term -c` as a general-purpose SSH escape hatch.**

| Task | Use this | NOT this |
|------|----------|----------|
| List containers | `rdc machine containers` | `rdc term -c "docker ps"` |
| View container logs | `rdc term <m> <repo> --container <c> --container-action logs` | `rdc term -c "docker logs"` |
| Exec into container | `rdc term <m> <repo> --container <c> --container-action exec` | `rdc term -c "docker exec"` |
| Check machine health | `rdc machine health` | `rdc term -c "systemctl status"` |
| List repos | `rdc machine repos` | `rdc term -c "ls /mnt/rediacc"` |
| Backup/push repos | `rdc backup push` | `rdc term -c "rsync ..."` |
| Checkpoint containers | `rdc backup push --checkpoint` | `rdc term -c "docker checkpoint"` |

## Examples

```bash
# Check disk usage on a machine (no rdc equivalent)
rdc term server-1 -c "df -h"

# Interactive shell into a repo environment
rdc term server-1 my-app
```
