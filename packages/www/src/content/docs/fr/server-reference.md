---
title: "Référence serveur"
description: "Organisation des répertoires, commandes renet, services systemd et procédures pour le serveur distant."
category: "Concepts"
order: 3
language: fr
sourceHash: "fdfadf580c39b1fe"
---

# Server Reference

This page covers what you find when you SSH into a Rediacc server: the directory layout, `renet` commands, systemd services, and common workflows.

Most users manage servers through `rdc` from their workstation and never need this page. It is here for advanced debugging or when you need to work directly on the server.

For the high-level architecture, see [Architecture](/en/docs/architecture). For the difference between `rdc` and `renet`, see [rdc vs renet](/en/docs/rdc-vs-renet).

## Directory Layout

```
/mnt/rediacc/                          # Main datastore
├── repositories/                      # Encrypted disk images (LUKS)
│   └── {uuid}                         # Each is a loop device image
├── mounts/                            # Mount points for decrypted repos
│   └── {uuid}/
│       ├── .rediacc.json              # Service → IP slot mapping
│       └── {service-name}/            # Service directory
│           ├── docker-compose.yml     # Compose definition
│           ├── Rediaccfile            # Lifecycle hooks (bash)
│           └── data/                  # Persistent data
├── interim/                           # Docker overlay2 data (per-repo)
│   └── {uuid}/docker/data/
├── immovable/                         # Read-only shared content
├── .credentials/                      # Encrypted secrets
└── .backup-*/                         # BTRFS snapshots

/opt/rediacc/proxy/                    # Traefik reverse proxy
├── docker-compose.yml
├── config.env                         # BASE_DOMAIN, CERTBOT_EMAIL, CF_DNS_API_TOKEN
├── letsencrypt/                       # ACME certificates
└── traefik/dynamic/                   # Dynamic route files

/run/rediacc/docker-{id}.sock          # Per-network Docker sockets
/var/lib/rediacc/docker-{id}/          # Per-network daemon data
/var/lib/rediacc/router/               # Router state (port allocations)
```

## renet Commands

`renet` is the server-side binary. All commands need root privileges (`sudo`).

### Repository Lifecycle

```bash
# List all repositories
renet repository list

# Show repository details
renet repository status --name {uuid}

# Start a repository (mount + run Rediaccfile up)
renet repository up --name {uuid} --network-id {id} --password-stdin

# Stop a repository (run Rediaccfile down)
renet repository down --name {uuid} --network-id {id}

# Create a new repository
renet repository create --name {uuid} --network-id {id} --size 2G --encrypted

# Fork (instant copy using BTRFS reflinks)
renet repository fork --source {uuid} --target {new-uuid}

# Expand a running repository (no downtime)
renet repository expand --name {uuid} --size 4G

# Delete a repository and all its data
renet repository delete --name {uuid} --network-id {id}
```

### Docker Compose

Run compose commands against a specific repository's Docker daemon:

```bash
sudo renet compose --network-id {id} -- up -d
sudo renet compose --network-id {id} -- down
sudo renet compose --network-id {id} -- logs -f
sudo renet compose --network-id {id} -- config
```

Run docker commands directly:

```bash
sudo renet docker --network-id {id} -- ps
sudo renet docker --network-id {id} -- logs -f {container}
sudo renet docker --network-id {id} -- exec -it {container} bash
```

Vous pouvez également utiliser le socket Docker directement :

```bash
DOCKER_HOST=unix:///run/rediacc/docker-{id}.sock docker ps
```

> Always run compose from the directory that contains `docker-compose.yml`, or Docker will not find the file.

### Proxy & Routing

```bash
renet proxy status          # Check Traefik + router health
renet proxy routes          # Show all configured routes
renet proxy refresh         # Refresh routes from running containers
renet proxy up / down       # Start/stop Traefik
renet proxy logs            # View proxy logs
```

Routes are discovered automatically from container labels. See [Networking](/en/docs/networking) for how to configure Traefik labels.

### System Status

```bash
renet ps                    # Overall system status
renet list all              # Everything: system, containers, repositories
renet list containers       # All containers across all Docker daemons
renet list repositories     # Repository status and disk usage
renet list system           # CPU, memory, disk, network
renet ips --network-id {id} # IP allocations for a network
```

### Daemon Management

Chaque dépôt exécute son propre daemon Docker. Vous pouvez les gérer individuellement :

```bash
renet daemon status --network-id {id}    # Docker daemon health
renet daemon start  --network-id {id}    # Start daemon
renet daemon stop   --network-id {id}    # Stop daemon
renet daemon logs   --network-id {id}    # Daemon logs
```

### Backup & Restore

Push backups to another machine or to cloud storage:

```bash
# Push to remote machine (SSH + rsync)
renet backup push --name {uuid} --network-id {id} --target machine \
  --dest-host {host} --dest-user {user} --dest-path /mnt/rediacc --dest {uuid}.backup

# Push to cloud storage (rclone)
renet backup push --name {uuid} --network-id {id} --target storage \
  --dest {uuid}.backup --rclone-backend {backend} --rclone-bucket {bucket}

# Pull from remote
renet backup pull --name {uuid} --network-id {id} --source machine \
  --src-host {host} --src-user {user} --src-path /mnt/rediacc --src {uuid}.backup

# List remote backups
renet backup list --source machine --src-host {host} --src-user {user} --src-path /mnt/rediacc
```

> Most users should use `rdc backup push/pull` instead. The `rdc` commands handle credentials and machine resolution automatically.

### Checkpointing (CRIU)

Checkpoint saves the state of running containers so they can be restored later:

```bash
renet checkpoint create    --network-id {id}   # Save running container state
renet checkpoint restore   --network-id {id}   # Restore from checkpoint
renet checkpoint validate  --network-id {id}   # Check checkpoint integrity
```

### Maintenance

```bash
renet prune --dry-run       # Preview orphaned networks and IPs
renet prune                 # Clean up orphaned resources
renet datastore status      # BTRFS datastore health
renet datastore validate    # Filesystem integrity check
renet datastore expand      # Expand the datastore online
```

## Systemd Services

Each repository creates these systemd units:

| Unit | Purpose |
|------|---------|
| `rediacc-docker-{id}.service` | Isolated Docker daemon |
| `rediacc-docker-{id}.socket` | Docker API socket activation |
| `rediacc-loopback-{id}.service` | Loopback IP alias setup |

Global services shared across all repositories:

| Unit | Purpose |
|------|---------|
| `rediacc-router.service` | Route discovery (port 7111) |
| `rediacc-autostart.service` | Boot-time repository mounting |

## Common Workflows

### Deploy a New Service

1. Create an encrypted repository:
   ```bash
   renet repository create --name {uuid} --network-id {id} --size 2G --encrypted
   ```
2. Mount it and add your `docker-compose.yml`, `Rediaccfile`, and `.rediacc.json` files.
3. Start it:
   ```bash
   renet repository up --name {uuid} --network-id {id} --password-stdin
   ```

### Access a Running Container

```bash
sudo renet docker --network-id {id} -- exec -it {container} bash
```

### Find Which Docker Socket Runs a Container

```bash
for sock in /run/rediacc/docker-*.sock; do
  result=$(DOCKER_HOST=unix://$sock docker ps --format '{{.Names}}' 2>/dev/null | grep {name})
  [ -n "$result" ] && echo "Found on: $sock"
done
```

### Recreate a Service After Config Changes

```bash
sudo renet compose --network-id {id} -- up -d
```

Run this from the directory with `docker-compose.yml`. Changed containers are automatically recreated.

### Check All Containers Across All Daemons

```bash
renet list containers
```

## Tips

- Always use `sudo` for `renet compose`, `renet repository`, and `renet docker` commands — they need root for LUKS and Docker operations
- The `--` separator is required before passing arguments to `renet compose` and `renet docker`
- Run compose from the directory that contains `docker-compose.yml`
- `.rediacc.json` slot assignments are stable — do not change them after deployment
- Use `/run/rediacc/docker-{id}.sock` paths (systemd may change legacy `/var/run/` paths)
- Run `renet prune --dry-run` from time to time to find orphaned resources
- BTRFS snapshots (`renet backup`) are fast and cheap — use them before making risky changes
- Repositories are LUKS-encrypted — losing the password means losing the data
