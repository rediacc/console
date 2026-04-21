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
rdc machine query --name <machine>

# Interactive SSH shell on a machine
rdc term connect -m <machine>

# SSH into a repo (DOCKER_HOST + mount dir pre-set)
rdc term connect -m <machine> -r <repo>

# Start repository services
rdc repo up -m <machine>

# Upload local files into a repo mount
rdc repo sync upload -m <machine> -r <repo> --local ./local-path

# Set defaults so -m / -t flags are optional
rdc config set --key machine --value <alias>
rdc config set --key team --value <name>
```

---
<!-- _class: cat-teal -->

<h2><a href="setup">Context Setup</a></h2>

```bash
# Create a named config (no cloud API)
rdc config init --name <name> --ssh-key ~/.ssh/id_ed25519

# Import object storage config from rclone.conf
rdc config storage import --file rclone.conf --name <name>

# Add a machine to the active config
rdc config machine add --name <alias> --ip <ip> --user <user>

# Scan SSH host keys for all config machines
rdc config machine scan-keys -m <machine>

# Set defaults (avoids repeating -m / -t on every command)
rdc config set --key machine --value <alias>
rdc config set --key team --value <name>

# Provision a bare server (installs btrfs, Docker, renet)
rdc config machine setup --name <alias>

# List configs / machines / repo GUID mappings
rdc config list
rdc config machine list
rdc config repository list
```

---
<!-- _class: cat-blue -->

<h2><a href="monitoring">Machine Management</a></h2>

```bash
# Full status: system info, repos, containers, services
rdc machine query --name <machine>

# List all Docker containers across all repos
rdc machine containers --name <machine>

# List systemd services managed by renet
rdc machine services --name <machine>

# List deployed repositories with mount/Docker status
rdc machine repos --name <machine>

# Health check — exits 0 (healthy) / 1 (warning) / 2 (error)
rdc machine health --name <machine>

# Vault / LUKS encryption status
rdc machine vault-status --name <machine>
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
rdc term connect -m <machine>

# Repo shell (DOCKER_HOST + repo mount dir pre-set)
rdc term connect -m <machine> -r <repo>

# Run a one-off remote command
rdc term connect -m <machine> -c "df -h /mnt/rediacc/mounts/"

# Attach to an interactive container terminal
rdc term connect -m <machine> -r <repo> \
  --container <name> --container-action terminal

# Stream container logs (follow mode)
rdc term connect -m <machine> -r <repo> \
  --container <name> --container-action logs \
  --log-lines 200 --follow

# Exec a command inside a container
rdc term connect -m <machine> -r <repo> \
  --container <name> --container-action exec \
  -c "bash"

# View container resource stats
rdc term connect -m <machine> -r <repo> \
  --container <name> --container-action stats

# SSH tunnel to a container port (e.g. database)
rdc repo tunnel -m <machine> -r <repo> -c <container> --port 5432
rdc repo tunnel -m <machine> -r <repo>           # auto-detect
```

---
<!-- _class: cat-green -->

<h2><a href="repositories">Repository Lifecycle</a></h2>

```bash
# Create a new encrypted repository
rdc repo create --name <repo> -m <machine> --size 10G

# Start services (Rediaccfile orchestration)
rdc repo up -m <machine>
rdc repo up -m <machine>

# Stop services
rdc repo down -m <machine>
rdc repo down -m <machine> --unmount    # unmount after

# Start all repos on a machine (omit --name to up all)
rdc repo up -m <machine>
rdc repo up -m <machine> --parallel            # concurrent start

# Mount / unmount LUKS container only
rdc repo mount --name <repo> -m <machine>
rdc repo unmount --name <repo> -m <machine>

# CoW fork (Copy-on-Write), offline resize, online expand
rdc repo fork --parent <parent> --tag <tag> -m <machine>
rdc repo resize --name <repo> -m <machine> --size 20G
rdc repo expand --name <repo> -m <machine> --size 20G

# Validate filesystem integrity
rdc repo validate --name <repo> -m <machine>

# Autostart management (starts repo on machine boot)
rdc repo autostart enable --name <repo> -m <machine>
rdc repo autostart disable --name <repo> -m <machine>
rdc repo autostart list -m <machine>
```

---
<!-- _class: cat-purple -->

<h2><a href="tools">File Sync</a></h2>

```bash
# Upload a directory (contents merge into --remote)
rdc repo sync upload \
  -m <machine> -r <repo> \
  --local ./local-path

# Upload a single file (lands at <remote>/<basename>)
rdc repo sync upload -m <machine> -r <repo> \
  --local ./config.yml --remote conf

# Upload multiple sources in one call
rdc repo sync upload -m <machine> -r <repo> \
  --local a.yml b.yml ./assets --remote app

# Download a remote directory to a local directory
rdc repo sync download \
  -m <machine> -r <repo> \
  --local ./local-path

# Download a single remote file into a local dir
rdc repo sync download -m <machine> -r <repo> \
  --remote-file conf/config.yml --local ./local-conf

# Preview changes without transferring (dry run)
rdc repo sync upload -m <machine> -r <repo> \
  --local ./local-path --dry-run

# Compare local vs remote without syncing
rdc repo sync status -m <machine> -r <repo>
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
rdc vscode connect -m <machine>

# Open VS Code in a repo environment
rdc vscode connect -m <machine> -r <repo>

# Open to a specific remote folder
rdc vscode connect -m <machine> -r <repo> --folder /custom/path

# Open in a new VS Code window
rdc vscode connect -m <machine> --new-window

# Print the vscode:// URI without launching
rdc vscode connect -m <machine> -r <repo> --url-only

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
rdc repo push --name <repo> -m <machine> --to <storage>

# Hot backup with container checkpoint (no downtime)
rdc repo push --name <repo> -m <machine> \
  --to <storage> --checkpoint

# Fork with live state (CRIU checkpoint + CoW clone)
rdc repo fork --parent <parent> --tag <tag> -m <machine> --checkpoint

# Pull backup from storage to a machine
rdc repo pull --name <repo> -m <machine> --from <storage>

# List available backups on storage
rdc repo backup list -m <machine> --from <storage>

# Configure backup schedule
rdc config backup-strategy set --name primary \
  --cron "0 2 * * *" \
  --destination <storage> \
  --enable

# Push schedule to machine as a systemd timer
rdc machine backup schedule -m <machine>

# Push all repos to storage (omit --name to push all)
rdc repo push -m <machine> --to <storage>
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
| `-t, --team <name>` | cloud adapter | Team name |
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
