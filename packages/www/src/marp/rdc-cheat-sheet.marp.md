---
marp: true
theme: rediacc-cheatsheet
---

<div class="brand-header">
  <img src="/assets/images/icon-rediacc.svg" width="36" height="36" alt="">
  <span class="brand-wordmark">rediacc</span>
</div>

# RDC CLI Cheat Sheet

Quick reference for all rdc commands — contexts, repos, machines, sync, containers, and more.

---
<!-- _class: cat-teal -->

<h2><a href="quick-start">Quick Reference</a></h2>

```bash
# Full machine status (system, repos, containers, services)
rdc machine info <machine>

# Interactive SSH shell on a machine
rdc term <machine>

# SSH into a repo (DOCKER_HOST + mount dir pre-set)
rdc term <machine> <repo>

# Start repository services
rdc repo up <repo> -m <machine>

# Upload local files into a repo mount
rdc sync upload -m <machine> -r <repo> -l ./local-path

# Set defaults so -m / -t flags are optional
rdc context set machine <alias>
rdc context set team <name>
```

---
<!-- _class: cat-teal -->

<h2><a href="setup">Context Setup</a></h2>

```bash
# Create a local context (no cloud API)
rdc context create-local <name> --ssh-key ~/.ssh/id_ed25519

# Create an S3/R2 context (remote state)
rdc context create-s3 <name> --endpoint <url> \
  --bucket <bucket> --access-key-id <id>

# Add a machine to the active context
rdc context add-machine <alias> --ip <ip> --user <user>

# Scan SSH host keys for all context machines
rdc context scan-keys

# Set defaults (avoids repeating -m / -t on every command)
rdc context set machine <alias>
rdc context set team <name>

# Provision a bare server (installs btrfs, Docker, renet)
rdc context setup-machine <alias>

# List contexts / machines / repo GUID mappings
rdc context list
rdc context machines
rdc context repositories
```

---
<!-- _class: cat-blue -->

<h2><a href="monitoring">Machine Management</a></h2>

```bash
# Full status: system info, repos, containers, services
rdc machine info <machine>

# List all Docker containers across all repos
rdc machine containers <machine>

# List systemd services managed by renet
rdc machine services <machine>

# List deployed repositories with mount/Docker status
rdc machine repos <machine>

# Health check — exits 0 (healthy) / 1 (warning) / 2 (error)
rdc machine health <machine>

# Vault / LUKS encryption status
rdc machine vault-status <machine>

# Test SSH connection and capture host key
rdc machine test-connection <machine>
```

`--output table|json|yaml|csv` — change output format
`--health-check` on `containers` — exits 2 if any container is unhealthy
`--stability-check` on `services` — exits 2 if any service is failed/restarting
`--search <text>` on `repos` — filter repositories by name

---
<!-- _class: cat-amber -->

<h2><a href="tools">SSH Terminal Access</a></h2>

```bash
# Interactive shell on a machine
rdc term <machine>

# Repo shell (DOCKER_HOST + repo mount dir pre-set)
rdc term <machine> <repo>

# Run a one-off remote command
rdc term <machine> -c "df -h /mnt/rediacc/mounts/"

# Attach to an interactive container terminal
rdc term <machine> <repo> \
  --container <name> --container-action terminal

# Stream container logs (follow mode)
rdc term <machine> <repo> \
  --container <name> --container-action logs \
  --log-lines 200 --follow

# Exec a command inside a container
rdc term <machine> <repo> \
  --container <name> --container-action exec \
  -c "bash"

# View container resource stats
rdc term <machine> <repo> \
  --container <name> --container-action stats
```

---
<!-- _class: cat-green -->

<h2><a href="repositories">Repository Lifecycle</a></h2>

```bash
# Create a new encrypted repository
rdc repo create <repo> -m <machine> --size 10G

# Start services (Rediaccfile orchestration)
rdc repo up <repo> -m <machine>
rdc repo up <repo> -m <machine> --mount        # mount first
rdc repo up <repo> -m <machine> --prep-only    # prep step only

# Stop services
rdc repo down <repo> -m <machine>
rdc repo down <repo> -m <machine> --unmount    # unmount after

# Start all repos on a machine
rdc repo up-all -m <machine>
rdc repo up-all -m <machine> --parallel        # concurrent start

# Mount / unmount LUKS container only
rdc repo mount <repo> -m <machine>
rdc repo unmount <repo> -m <machine>

# CoW fork (Copy-on-Write), offline resize, online expand
rdc repo fork <parent> --tag <fork-name> -m <machine>
rdc repo resize <repo> -m <machine> --size 20G
rdc repo expand <repo> -m <machine> --size 20G

# Validate filesystem integrity
rdc repo validate <repo> -m <machine>

# Autostart management (starts repo on machine boot)
rdc repo autostart enable <repo> -m <machine>
rdc repo autostart disable <repo> -m <machine>
rdc repo autostart list -m <machine>
```

---
<!-- _class: cat-purple -->

<h2><a href="tools">File Sync</a></h2>

```bash
# Upload local directory to repo mount (rsync over SSH)
rdc sync upload \
  -m <machine> -r <repo> \
  -l ./local-path

# Download from repo mount to local directory
rdc sync download \
  -m <machine> -r <repo> \
  -l ./local-path

# Preview changes without transferring (dry run)
rdc sync upload -m <machine> -r <repo> \
  -l ./local-path --dry-run

# Interactive confirm before syncing
rdc sync upload -m <machine> -r <repo> \
  -l ./local-path --confirm

# Compare local vs remote without syncing
rdc sync status -m <machine> -r <repo>
```

`--remote <path>` — subdirectory within the repo mount
`--mirror` — delete remote files not present locally
`--verify` — verify checksums after transfer
`--exclude <pattern>` — exclude files matching pattern

---
<!-- _class: cat-rose -->

<h2><a href="services">Container Operations</a></h2>

```bash
# List all containers in a repo
rdc run container_list \
  -m <machine> \
  --param repository=<repo>

# Stream container logs
rdc run container_logs \
  -m <machine> \
  --param repository=<repo> \
  --param container=<name>

# Execute a command inside a container
rdc run container_exec \
  -m <machine> \
  --param repository=<repo> \
  --param container=<name> \
  --param command="bash"

# Restart a container
rdc run container_restart \
  -m <machine> \
  --param repository=<repo> \
  --param container=<name>
```

> `rdc run` is a low-level escape hatch — prefer `rdc term … --container` for interactive access.

---
<!-- _class: cat-blue -->

<h2><a href="tools">VS Code Remote SSH</a></h2>

```bash
# Open VS Code connected to a machine
rdc vscode <machine>

# Open VS Code in a repo environment
rdc vscode <machine> <repo>

# Open to a specific remote folder
rdc vscode <machine> <repo> --folder /custom/path

# Open in a new VS Code window
rdc vscode <machine> --new-window

# Print the vscode:// URI without launching
rdc vscode <machine> <repo> --url-only

# List SSH configs created by vscode
rdc vscode list

# Remove all vscode SSH configs
rdc vscode cleanup --all
```

> Requires the [Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh) VS Code extension.

---
<!-- _class: cat-teal -->

<h2><a href="backup-restore">Backup & Restore</a></h2>

```bash
# Push repo backup to S3/R2 storage
rdc backup push <repo> -m <machine> --to <storage>

# Hot backup with container checkpoint (no downtime)
rdc backup push <repo> -m <machine> \
  --to <storage> --checkpoint

# Pull backup from storage to a machine
rdc backup pull <repo> -m <machine> --from <storage>

# List available backups on storage
rdc backup list -m <machine> --from <storage>

# Configure backup schedule
rdc backup schedule set \
  --cron "0 2 * * *" \
  --destination <storage> \
  --enable

# Push schedule to machine as a systemd timer
rdc backup schedule push <machine>

# Bulk push all repos to storage
rdc backup sync -m <machine> --to <storage>
```

---
<!-- _class: cat-green -->

<h2><a href="repositories">Snapshots</a></h2>

```bash
# Create a BTRFS snapshot of a repository
rdc snapshot create <repo> -m <machine>

# Create with an explicit snapshot name
rdc snapshot create <repo> -m <machine> \
  --snapshot-name <name>

# List all snapshots on a machine
rdc snapshot list -m <machine>

# Delete a snapshot
rdc snapshot delete <snapshot-name> -m <machine>
```

> Snapshots are instant BTRFS subvolume snapshots of the repository mount directory — space-efficient and suitable for quick rollbacks.

---
<!-- _class: cat-amber -->

<h2><a href="cli-application">Common Flags</a></h2>

| Flag | Applies to | Meaning |
|------|-----------|---------|
| `-m, --machine <name>` | most commands | Target machine alias |
| `-r, --repository <name>` | sync, term | Repository name |
| `-t, --team <name>` | cloud mode | Team name |
| `-l, --local <path>` | sync | Local directory path |
| `--output <fmt>` | list / get | `table` `json` `yaml` `csv` |
| `--dry-run` | sync, repo up-all | Preview without changes |
| `--param key=value` | run | Bridge function parameter |
| `--debug` | repo, run | Verbose debug output (local mode) |
| `--force` / `-y` | delete, backup | Skip confirmation prompts |

---
<!-- _class: cat-purple -->

<h2><a href="services">Rediaccfile Functions</a></h2>

```bash
# Rediaccfile lifecycle — Bash script sourced by renet:
# prep()  — called before up(); pull images, write config
# up()    — start Docker Compose / services
# down()  — stop services
# info()  — print service URLs and status

# Run any bridge function directly (escape hatch)
rdc run <function> -m <machine> [--param key=value ...]

# Common bridge functions via rdc run
rdc run repository_list    -m <machine>
rdc run repository_up      -m <machine> --param repository=<repo>
rdc run repository_down    -m <machine> --param repository=<repo>
rdc run container_list     -m <machine> --param repository=<repo>
rdc run container_logs     -m <machine> \
  --param repository=<repo> --param container=<name>
rdc run container_exec     -m <machine> \
  --param repository=<repo> --param container=<name> \
  --param command="bash"
```

> Prefer `rdc repo up` / `rdc repo down` over calling bridge functions directly for day-to-day use.
