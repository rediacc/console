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
rdc machine status <machine>

# Interactive SSH shell on a machine
rdc term connect <machine>

# SSH into a repo (DOCKER_HOST + mount dir pre-set)
rdc term connect <repo>@<machine>

# Start repository services
rdc repo up <repo>@<machine>

# Upload local files into a repo mount
rdc repo sync upload <repo>@<machine> --local ./local-path

# Set defaults so -m / -t flags are optional
rdc config set machine <alias>
rdc config set team <name>
```

---
<!-- _class: cat-teal -->

<h2><a href="setup">Context Setup</a></h2>

```bash
# Create a named config (no cloud API)
rdc config init <name> --ssh-key ~/.ssh/id_ed25519

# Import object storage config from rclone.conf
rdc storage import rclone.conf --name <name>

# Add a machine to the active config
rdc machine add <alias> --ip <ip> --user <user>

# Scan SSH host keys for all config machines
rdc machine scan-keys <machine>

# Set defaults (avoids repeating -m / -t on every command)
rdc config set machine <alias>
rdc config set team <name>

# Provision a bare server (installs btrfs, Docker, renet)
rdc machine setup <alias>

# List configs / machines / repo GUID mappings
rdc config list
rdc machine list
rdc repo list
```

---
<!-- _class: cat-blue -->

<h2><a href="monitoring">Machine Management</a></h2>

```bash
# Full status: system info, repos, containers, services
rdc machine status <machine>

# List all Docker containers across all repos
rdc machine status <machine> --containers

# List systemd services managed by renet
rdc machine status <machine> --services

# List deployed repositories with mount/Docker status
rdc machine status <machine> --repositories

# Health check — exits 0 (healthy) / 1 (warning) / 2 (error)
rdc machine health <machine>

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
rdc term connect <machine>

# Repo shell (DOCKER_HOST + repo mount dir pre-set)
rdc term connect <repo>@<machine>

# Run a one-off remote command
rdc term connect <machine> -c "df -h /mnt/rediacc/mounts/"

# Attach to an interactive container terminal
rdc repo exec <repo>@<machine> -c <name> -i -- bash

# Stream container logs (follow mode)
rdc repo logs <repo>@<machine> -c <name> --lines 200 --follow

# Exec a command inside a container
rdc repo exec <repo>@<machine> -c <name> -- <command>

# Container resource stats (via the escape hatch; there is no typed verb yet)
rdc run -f container_stats -m <machine> --param repository=<repo>

# SSH tunnel to a container port (e.g. database)
rdc repo tunnel <repo> -c <container> --port 5432
rdc repo tunnel <repo>           # auto-detect
```

---
<!-- _class: cat-green -->

<h2><a href="repositories">Repository Lifecycle</a></h2>

```bash
# Create a new encrypted repository
rdc repo create <repo> -m <machine> --size 10G

# Start services (Rediaccfile orchestration)
rdc repo up <repo>@<machine>
rdc repo up <repo>@<machine>

# Stop services
rdc repo down <repo>@<machine>
rdc repo down <repo>@<machine> --unmount    # unmount after

# Start all repos on a machine (omit --name to up all)
rdc repo up <repo>@<machine>
rdc repo up --all -m <machine> --parallel            # concurrent start

# Mount / unmount LUKS container only
rdc repo up <repo>@<machine> --no-start
rdc repo down <repo>@<machine> --unmount

# CoW fork (Copy-on-Write), offline resize, online expand
rdc repo fork <parent> --tag <tag>
rdc repo resize <repo> --size 20G
rdc repo expand <repo> --size 20G

# Validate filesystem integrity
rdc repo admin validate <repo>

# Autostart management (starts repo on machine boot)
rdc repo admin autostart enable <repo>
rdc repo admin autostart disable <repo>
rdc repo admin autostart list -m <machine>
```

---
<!-- _class: cat-purple -->

<h2><a href="tools">File Sync</a></h2>

```bash
# Upload a directory (contents merge into --remote)
rdc repo sync upload <repo>@<machine> \
  --local ./local-path

# Upload a single file (lands at <remote>/<basename>)
rdc repo sync upload <repo>@<machine> \
  --local ./config.yml --remote conf

# Upload multiple sources in one call
rdc repo sync upload <repo>@<machine> \
  --local a.yml b.yml ./assets --remote app

# Download a remote directory to a local directory
rdc repo sync download <repo>@<machine> \
  --local ./local-path

# Download a single remote file into a local dir
rdc repo sync download <repo>@<machine> \
  --remote-file conf/config.yml --local ./local-conf

# Preview changes without transferring (dry run)
rdc repo sync upload <repo>@<machine> \
  --local ./local-path --dry-run

# Compare local vs remote without syncing
rdc repo sync status <repo>@<machine>
```

`--remote <path>` — directory within the repo mount
`--remote-file <path>` — single remote file (download only)
`--mirror` — delete remote files not present locally (directory sources only)
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
rdc vscode connect <machine>

# Open VS Code in a repo environment
rdc vscode connect <repo>@<machine>

# Open to a specific remote folder
rdc vscode connect <repo>@<machine> --folder /custom/path

# Open in a new VS Code window
rdc vscode connect <machine> --new-window

# Print the vscode:// URI without launching
rdc vscode connect <repo>@<machine> --url-only

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
rdc repo push <repo> --to <storage>

# Hot backup with container checkpoint (no downtime)
rdc repo push <repo> \
  --to <storage> --checkpoint

# Fork with live state (CRIU checkpoint + CoW clone)
rdc repo fork <parent> --tag <tag> --checkpoint

# Pull backup from storage to a machine
rdc repo pull <repo> --from <storage>

# List available backups on storage
rdc backup list <repo> -m <machine> --storage <storage>

# Configure backup schedule
rdc backup strategy set primary \
  --cron "0 2 * * *" \
  --destination <storage> \
  --enable

# Push schedule to machine as a systemd timer
rdc backup schedule -m <machine>

# Push all repos to storage (omit --name to push all)
rdc repo push <repo> --to <storage>
```

---
<!-- _class: cat-green -->

<h2><a href="repositories">Snapshots</a></h2>

```bash
# Create a BTRFS snapshot of a repository
rdc repo snapshot create --name <repo> -m <machine>

# Create with an explicit snapshot name
rdc repo snapshot create --name <repo> -m <machine> \
  --snapshot-name <name>

# List all snapshots on a machine
rdc repo snapshot list -m <machine>

# Delete a snapshot
rdc repo snapshot delete --name <snapshot-name> -m <machine>
```

> Snapshots are instant BTRFS subvolume snapshots of the repository mount directory — space-efficient and suitable for quick rollbacks.

---
<!-- _class: cat-amber -->

<h2><a href="cli-application">Common Flags</a></h2>

| Flag | Applies to | Meaning |
|------|-----------|---------|
| `-m, --machine <name>` | most commands | Target machine alias |
| `-r, --repository <name>` | sync, term | Repository name |
| `-t, --team <name>` | resource commands | Team name |
| `-l, --local <path>` | sync | Local directory path |
| `--output <fmt>` | list / get | `table` `json` `yaml` `csv` |
| `--dry-run` | sync, repo up | Preview without changes |
| `--param key=value` | run | Bridge function parameter |
| `--debug` | repo, run | Verbose debug output (local mode) |
| `--force` / `-y` | delete, backup | Skip confirmation prompts |

---
<!-- _class: cat-purple -->

<h2><a href="services">Rediaccfile Functions</a></h2>

```bash
# Rediaccfile lifecycle — Bash script sourced by renet:
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
