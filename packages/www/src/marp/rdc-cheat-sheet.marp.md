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

# Read a pre-retirement archive (needs rclone on PATH;
# storage is no longer a backup destination)
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
rdc machine status <machine> --containers

# Stream container logs
rdc repo logs <repo>@<machine> -c <name> --follow

# Execute a command inside a container
rdc repo exec <repo>@<machine> -c <name> -i -- bash

# Restart a container (no first-class verb yet)
rdc run -f container_restart \
  -m <machine> \
  --param repository=<repo> \
  --param container=<name>
```

> `rdc run` is a low-level escape hatch — prefer `repo logs` and `repo exec` for day-to-day container access.

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
# Take a point-in-time snapshot into the chunk store
rdc backup snapshot <repo>

# Quiesce containers first (app-consistent)
rdc backup snapshot <repo> --cold

# List the snapshots the chunk store holds
rdc backup manifests <repo-ref>

# List the files a repository contains (local read)
rdc backup browse <repo-ref>

# Restore a point in time
rdc backup restore <repo> --at <snapshot> \
  --as <name> --up

# Copy a repository to another machine
rdc repo push <repo> --to <machine>

# Fork with live state (CRIU checkpoint + CoW clone)
rdc repo fork <parent> --tag <tag> --checkpoint

# Configure backup schedule
rdc backup strategy set primary \
  --cron "0 2 * * *" \
  --destination <destination> \
  --enable

# Push schedule to machine as a systemd timer
rdc backup schedule -m <machine>

# Stored bytes against your quota
rdc backup usage
```

---
<!-- _class: cat-green -->

<h2><a href="repositories">Snapshots</a></h2>

```bash
# Snapshot a whole datastore
rdc datastore snapshot create <datastore>

# Create with an explicit snapshot label
rdc datastore snapshot create <datastore> --snapshot <label>

# List a datastore's snapshots
rdc datastore snapshot list <datastore>

# Snapshot a whole cluster (control plane, then PVs)
rdc cluster snapshot create <cluster> --snapshot <label>
```

> Snapshots are taken at the datastore or cluster level, not per repository. For a point-in-time copy of a single repo, fork it: `rdc repo fork <repo> --tag <tag>` is instant and constant-time.

---
<!-- _class: cat-amber -->

<h2><a href="cli-application">Common Flags</a></h2>

| Flag | Applies to | Meaning |
|------|-----------|---------|
| `<ref>` (positional) | repo, term, vscode | Repository ref: `name`, `name:tag`, optionally `@machine` |
| `-m, --machine <name>` | create / batch / query | Target machine alias, where there is no ref to derive it from |
| `-t, --team <name>` | resource commands | Team name |
| `--local <paths...>` | sync | Local file or directory paths |
| `--output <fmt>` | list / get | `table` `json` `yaml` `csv` |
| `--dry-run` | sync, repo up | Preview without changes |
| `--param key=value` | run | Bridge function parameter |
| `--debug` | repo, run | Verbose debug output |
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
rdc run -f <function> -m <machine> [--param key=value ...]

# Common bridge functions via rdc run
rdc run -f repository_list    -m <machine>
rdc run -f repository_up      -m <machine> --param repository=<repo>
rdc run -f repository_down    -m <machine> --param repository=<repo>
rdc run -f container_list     -m <machine> --param repository=<repo>
rdc run -f container_logs     -m <machine> \
  --param repository=<repo> --param container=<name>
rdc run -f container_exec     -m <machine> \
  --param repository=<repo> --param container=<name> \
  --param command="bash"
```

> Prefer `rdc repo up` / `rdc repo down` over calling bridge functions directly for day-to-day use.
