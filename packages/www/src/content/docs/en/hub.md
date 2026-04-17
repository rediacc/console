---
title: "Hub"
description: "Provide authenticated, per-user containerized environments with per-user Docker daemons, multi-template selection, CRIU checkpoint/restore, audit logs, and data-root garbage collection."
category: "Guides"
order: 14
language: en
---

# Hub

The Hub provides per-user containerized environments behind OAuth authentication. Users visit a single URL, authenticate with any OAuth2 provider, and are transparently routed to their personal container. Containers are spawned on demand, each user gets their own isolated Docker daemon, and idle sessions are CRIU-checkpointed for instant resume.

Everything is configured through `docker-compose.yml` labels. The Hub itself runs as a host systemd service materialised by the `renet hub install` command from your repo's compose file. Repos define behavior; the Hub handles authentication, routing, lifecycle, and per-user isolation.

## How It Works

1. A user visits `code.example.com` (or `term.`, `desktop.`, or any other configured prefix).
2. The Hub checks for a session cookie. If absent, the user is redirected to the configured OAuth2 provider (Nextcloud, Keycloak, GitHub, etc.).
3. After authentication, the Hub identifies the user and looks up their container.
4. If no container exists, the Hub provisions a dedicated Docker daemon for that user on the host, then spawns their container.
5. The request is reverse-proxied to the user's container over the loopback network.
6. Idle containers are CRIU-checkpointed; the per-user daemon is stopped to free memory. On the next login the daemon comes back and CRIU restores the container state in seconds.

## Quick Start

Add the Hub as a service in your repository's `docker-compose.yml`. The service is marked `install_as=systemd` so it runs as a host service rather than a Docker container (required for per-user daemon management, which uses systemd).

```yaml
services:
  hub:
    env_file:
      - ./hub/.env
    command:
      - hub
      - start
      - --docker-socket=${DOCKER_SOCKET}
      - --network-id=${REDIACC_NETWORK_ID}
      - --port=7112
      - --base-domain=${HUB_DOMAIN:-example.com}
      - --workspace-dir=${REDIACC_WORKING_DIR}/devbox/workspaces
      - --idle-timeout=30m
      - --checkpoint
    labels:
      - "rediacc.install_as=systemd"

      # Route mapping: subdomain prefix -> port on user containers
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"

      # Container template
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host __SERVICE_IP__ --port 8080"
      - "rediacc.hub.user=vscode"
      - "rediacc.hub.docker=per-user"

      # Traefik routes (file-provider; rediacc-router reads these labels too)
      - "traefik.http.routers.hub-code.rule=Host(`code.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-code.entrypoints=websecure"
      - "traefik.http.routers.hub-code.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-code.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-term.rule=Host(`term.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-term.entrypoints=websecure"
      - "traefik.http.routers.hub-term.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-term.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-desktop.rule=Host(`desktop.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-desktop.entrypoints=websecure"
      - "traefik.http.routers.hub-desktop.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-desktop.loadbalancer.server.port=7112"
```

Create `hub/.env` with your OAuth2 provider credentials:

```bash
HUB_DOMAIN=example.com
HUB_OAUTH_CLIENT_ID=your-client-id
HUB_OAUTH_CLIENT_SECRET=your-client-secret
HUB_OAUTH_AUTHORIZE_URL=https://auth.example.com/authorize
HUB_OAUTH_TOKEN_URL=https://auth.example.com/token
HUB_OAUTH_USERINFO_URL=https://auth.example.com/userinfo
HUB_OAUTH_USERINFO_PATH=preferred_username
HUB_SESSION_SECRET=64-character-hex-string
```

Install the host systemd unit (one-time, requires root):

```bash
sudo renet hub install /path/to/docker-compose.yml
```

This reads the `install_as=systemd` services and writes:

- `/etc/systemd/system/rediacc-hub.service` (the unit)
- `/etc/rediacc/hub/hub.labels.yaml` (the template labels)
- `/opt/rediacc/proxy/traefik/dynamic/rediacc-hub.yaml` (Traefik file-provider routes)

Then `systemctl daemon-reload && systemctl enable --now rediacc-hub`. To remove: `sudo renet hub uninstall /path/to/docker-compose.yml`.

## Install Command Reference

| Command | Purpose |
|---------|---------|
| `sudo renet hub install <compose-file>` | Translate `install_as=systemd` services from the compose file into host artifacts and start the unit. |
| `sudo renet hub uninstall <compose-file>` | Stop, disable, and remove all artifacts for the services. Data-roots under `<workspace>/<user>-docker/` are preserved. |
| `sudo renet hub gc <workspace-dir>` | Prune abandoned per-user data-roots (default: older than 30 days with no active daemon). Flags: `--max-age=30d`, `--dry-run`. |
| `renet hub status` | JSON status of all containers via the running Hub's API. |
| `renet hub stop <username>` | Stop a specific user's container. |

## Configuration

All Hub configuration lives in compose labels on the Hub service. Secrets (OAuth client_secret, session_secret) go in `hub/.env`, not in labels.

### Route Mapping

Map subdomain prefixes to ports on user containers. The Hub reads these labels to know where to proxy each request.

| Label | Description | Example |
|-------|-------------|---------|
| `rediacc.hub.route.{prefix}` | Maps `{prefix}.{domain}` to this port on the user's container | `rediacc.hub.route.code=8080` |

```yaml
labels:
  - "rediacc.hub.route.code=8080"      # code.example.com -> :8080
  - "rediacc.hub.route.term=7681"      # term.example.com -> :7681
  - "rediacc.hub.route.desktop=6080"   # desktop.example.com -> :6080
  - "rediacc.hub.route.jupyter=8888"   # jupyter.example.com -> :8888
```

Each route also needs a matching Traefik router pointing at the Hub's port (7112). The Hub handles the per-user routing internally based on the hostname.

### Container Template

Define what user containers look like. The Hub reads these labels and uses them when spawning a new container.

| Label | Description | Default |
|-------|-------------|---------|
| `rediacc.hub.image` | Container image | Value of `--container-image` flag |
| `rediacc.hub.command` | Startup command (bash -c compatible) | none |
| `rediacc.hub.user` | Container user (non-root recommended) | `vscode` |
| `rediacc.hub.workspace` | Workspace mount point inside container | `/workspace` |
| `rediacc.hub.shm_size` | Shared memory size in bytes | `1073741824` (1 GB) |
| `rediacc.hub.docker` | `per-user` to provision a dedicated dockerd per user (strongly recommended) | `""` |

The `command` label supports `${SERVICE_IP}` and `__SERVICE_IP__` expansion (the latter avoids compose pre-expansion) for the container's assigned loopback IP.

```yaml
labels:
  - "rediacc.hub.image=ghcr.io/my-org/dev-env:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=__SERVICE_IP__ --port=8888 --no-browser"
  - "rediacc.hub.user=vscode"
  - "rediacc.hub.workspace=/workspace"
  - "rediacc.hub.docker=per-user"
```

### Per-User Docker Daemon

When `rediacc.hub.docker=per-user` is set, each user gets a dedicated `dockerd` instance on the host, bind-mounted as `/var/run/docker.sock` inside their container. This gives:

- Full `docker ps`, `docker run`, `docker build` inside the user environment without privileged containers or Docker-in-Docker.
- Complete isolation between users (user A cannot see user B's containers or images).
- A per-user BTRFS data-root at `<workspace-dir>/<user>-docker/.rediacc/docker/data`, preserved across sessions so cached images survive idle-checkpoint cycles.

Daemons are allocated in a dedicated network-ID range starting at 32768. A `.networkid` marker file in each user's data-root records their assigned ID so returning users pick up the same daemon.

### Resource Limits

Set per-user resource limits to prevent any single user from consuming all host resources. Limits apply to both the user's container and their per-user dockerd instance (via systemd `CPUQuota=` / `MemoryMax=`).

| Label | Description | Example |
|-------|-------------|---------|
| `rediacc.hub.limits.cpu` | systemd CPUQuota value | `200%` (2 cores) |
| `rediacc.hub.limits.memory` | systemd MemoryMax value | `8G` |

```yaml
labels:
  - "rediacc.hub.limits.cpu=200%"
  - "rediacc.hub.limits.memory=8G"
```

Daemons are placed in the `rediacc.slice` systemd slice so slice-level limits are inherited.

### Multi-Template Support

Offer multiple environment types. Users pick a template at login by visiting `https://code.example.com/_hub/login?template=python` (the selection round-trips through OAuth state). Switching templates on subsequent logins rebuilds the container.

Define templates with `rediacc.hub.templates.<name>.<field>` labels. The flat `rediacc.hub.image` / `rediacc.hub.command` / etc. labels continue to define the implicit "default" template for users who don't pick one.

```yaml
labels:
  # The default template when ?template=... is omitted.
  - "rediacc.hub.template=fulldev"

  # A rich VS Code + desktop + terminal environment.
  - "rediacc.hub.templates.fulldev.image=ghcr.io/org/devcontainer:latest"
  - "rediacc.hub.templates.fulldev.command=start-desktop.sh & ttyd --writable --port 7681 bash --login & exec openvscode-server --host __SERVICE_IP__ --port 8080 --without-connection-token"
  - "rediacc.hub.templates.fulldev.user=vscode"

  # A lightweight VS Code only.
  - "rediacc.hub.templates.lite.image=ghcr.io/org/devcontainer:lite"
  - "rediacc.hub.templates.lite.command=exec openvscode-server --host __SERVICE_IP__ --port 8080"
  - "rediacc.hub.templates.lite.user=vscode"

  # Python-specific environment.
  - "rediacc.hub.templates.python.image=python:3.12-slim"
  - "rediacc.hub.templates.python.command=pip install jupyterlab && exec jupyter lab --ip=__SERVICE_IP__ --port=8888"
  - "rediacc.hub.templates.python.user=1000:1000"
```

### Lifecycle Hooks

Run commands inside the user container at lifecycle points. Hooks run as the container user (not root).

| Label | When it runs | Example |
|-------|-------------|---------|
| `rediacc.hub.hook.on_create` | After container is created (first login) | Clone repos, install dependencies |
| `rediacc.hub.hook.checkpoint.pre_dump` | Before CRIU checkpoint of an idle session | Stop daemons that can't be checkpointed (X server, dbus) |
| `rediacc.hub.hook.checkpoint.post_restore` | After CRIU restore | Restart the daemons stopped in pre_dump |

```yaml
labels:
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/repo /workspace/project"
  - "rediacc.hub.hook.checkpoint.pre_dump=start-desktop.sh stop"
  - "rediacc.hub.hook.checkpoint.post_restore=start-desktop.sh"
```

### Checkpoint / Restore

When `--checkpoint` is set, idle user containers are CRIU-checkpointed and their per-user daemon is stopped to free memory. On next login the daemon is restarted and CRIU restores the container state from disk, preserving open files, running processes, and terminal sessions. Typical resume time is a few seconds regardless of workload.

| Label | Description | Default |
|-------|-------------|---------|
| `rediacc.hub.checkpoint` | Enable CRIU checkpoint for user containers | `false` |

Pass `--checkpoint` and a non-zero `--idle-timeout` (e.g. `30m`) in the Hub command. Checkpoint directories live at `<workspace-dir>/<user>/.checkpoint/`.

If CRIU fails 3 times in a row for a user, checkpointing is disabled for that user and the fallback becomes stop-and-recreate.

### Ephemeral Mode

By default, user workspaces are persistent (survive restart). Ephemeral mode gives a clean environment each login, useful for demos, training, or CI.

| Label | Description | Default |
|-------|-------------|---------|
| `rediacc.hub.mode` | `persistent` or `ephemeral` | `persistent` |

In ephemeral mode the workspace is tmpfs (RAM-backed) and the container is auto-removed on stop.

### Idle Timeout

| Flag | Description | Default |
|------|-------------|---------|
| `--idle-timeout=<dur>` | Stop/checkpoint containers idle longer than this | `0` (disabled) |

`0` keeps containers running forever. A practical value is `30m`: idle users free memory after half an hour, and returning users resume in seconds via CRIU.

### Access Control

| Variable | Description |
|----------|-------------|
| `HUB_ALLOWED_GROUPS` | Comma-separated groups allowed to use the Hub (when your provider exposes group claims) |
| `HUB_ADMIN_USERS` | Comma-separated admin usernames. Admins see and control other users' containers in the dashboard. |

## Audit Log

Every user-initiated container/image event (create, start, stop, destroy, kill, pull, push) on the per-user daemon is appended as a line-delimited JSON record to `/var/log/rediacc/hub/<user>.log`:

```json
{"ts":"2026-04-16T05:53:12Z","user":"alice","net_id":32768,"type":"container","action":"start","resource":"abc123...","attrs":{"image":"hello-world:latest","name":"happy_pike"}}
```

Entries survive CRIU checkpoint/restore (the audit stream is re-armed on restore). Use `logrotate` to cap disk usage; a sample config:

```
/var/log/rediacc/hub/*.log {
  daily
  rotate 30
  compress
  missingok
  notifempty
  copytruncate
}
```

## Dashboard

The Hub includes a self-service dashboard at `/_hub/dashboard`. It shows:

- All running environments with their status
- Selected template
- Service links (one click to open code, terminal, desktop, or any other route)
- Idle timers
- Per-user disk usage, running container count, and image count
- Admins see all containers; regular users see only their own

Stats are sampled every 30 seconds.

## Data-Root Garbage Collection

Per-user data-roots accumulate on long-running hosts. Schedule `renet hub gc` to prune abandoned ones. A systemd timer works well:

```ini
# /etc/systemd/system/rediacc-hub-gc.service
[Unit]
Description=Rediacc Hub data-root GC

[Service]
Type=oneshot
ExecStart=/usr/lib/rediacc/renet/current/renet hub gc /mnt/rediacc/mounts/<repo-guid>/devbox/workspaces --max-age=30d
```

```ini
# /etc/systemd/system/rediacc-hub-gc.timer
[Unit]
Description=Daily Rediacc Hub GC

[Timer]
OnCalendar=daily
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

`--dry-run` logs candidates without deleting. A data-root is eligible when its `.networkid` marker is older than `--max-age` AND the recorded daemon is no longer configured on the host.

## OAuth Setup

The Hub works with any standard OAuth2 provider. Configuration is via environment variables.

| Variable | Description | Required |
|----------|-------------|----------|
| `HUB_OAUTH_CLIENT_ID` | OAuth2 client ID | Yes |
| `HUB_OAUTH_CLIENT_SECRET` | OAuth2 client secret | Yes |
| `HUB_OAUTH_AUTHORIZE_URL` | Provider's authorize endpoint | Yes |
| `HUB_OAUTH_TOKEN_URL` | Provider's token endpoint | Yes |
| `HUB_OAUTH_USERINFO_URL` | Provider's userinfo endpoint | Yes |
| `HUB_OAUTH_USERINFO_PATH` | Dot-path to extract username from JSON response | Yes |
| `HUB_OAUTH_REDIRECT_URI` | Override callback URL (auto-computed if empty) | No |
| `HUB_OAUTH_SCOPES` | Additional scopes (space-separated) | No |
| `HUB_SESSION_SECRET` | 32+ byte hex string for cookie signing | Recommended |

### Provider Examples

**Nextcloud:**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://cloud.example.com/apps/oauth2/authorize
HUB_OAUTH_TOKEN_URL=https://cloud.example.com/apps/oauth2/api/v1/token
HUB_OAUTH_USERINFO_URL=https://cloud.example.com/ocs/v2.php/cloud/user?format=json
HUB_OAUTH_USERINFO_PATH=ocs.data.id
```

**Keycloak:**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://auth.example.com/realms/master/protocol/openid-connect/auth
HUB_OAUTH_TOKEN_URL=https://auth.example.com/realms/master/protocol/openid-connect/token
HUB_OAUTH_USERINFO_URL=https://auth.example.com/realms/master/protocol/openid-connect/userinfo
HUB_OAUTH_USERINFO_PATH=preferred_username
```

**GitHub:**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://github.com/login/oauth/authorize
HUB_OAUTH_TOKEN_URL=https://github.com/login/oauth/access_token
HUB_OAUTH_USERINFO_URL=https://api.github.com/user
HUB_OAUTH_USERINFO_PATH=login
HUB_OAUTH_SCOPES=read:user
```

The `HUB_OAUTH_USERINFO_PATH` is a dot-separated path into the JSON response. For nested objects like Nextcloud's `{"ocs":{"data":{"id":"alice"}}}`, use `ocs.data.id`.

## Examples

### Development Environment (VS Code + Terminal + Desktop)

A full development environment with OpenVSCode Server, a web terminal (ttyd), and a noVNC desktop. Users get their own Docker daemon inside.

```yaml
services:
  hub:
    env_file:
      - ./hub/.env
    command:
      - hub
      - start
      - --docker-socket=${DOCKER_SOCKET}
      - --network-id=${REDIACC_NETWORK_ID}
      - --port=7112
      - --base-domain=${HUB_DOMAIN}
      - --workspace-dir=${REDIACC_WORKING_DIR}/devbox/workspaces
      - --idle-timeout=30m
      - --checkpoint
    labels:
      - "rediacc.install_as=systemd"
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash --login & exec openvscode-server --host __SERVICE_IP__ --port 8080 --without-connection-token"
      - "rediacc.hub.user=vscode"
      - "rediacc.hub.docker=per-user"
      - "rediacc.hub.limits.cpu=200%"
      - "rediacc.hub.limits.memory=8G"
      - "rediacc.hub.checkpoint=true"
      - "rediacc.hub.hook.checkpoint.pre_dump=start-desktop.sh stop"
      - "rediacc.hub.hook.checkpoint.post_restore=start-desktop.sh"
      # ... Traefik routers for each prefix ...
```

### Jupyter Notebook Environment

A data science environment with JupyterLab:

```yaml
labels:
  - "rediacc.install_as=systemd"
  - "rediacc.hub.route.notebook=8888"
  - "rediacc.hub.image=jupyter/datascience-notebook:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=__SERVICE_IP__ --port=8888 --no-browser --NotebookApp.token='' --NotebookApp.password=''"
  - "rediacc.hub.user=1000:100"
  - "rediacc.hub.workspace=/home/jovyan/work"
  - "rediacc.hub.limits.cpu=400%"
  - "rediacc.hub.limits.memory=16G"
```

### Simple Web Application (Ephemeral)

A single-service environment that starts fresh on every login:

```yaml
labels:
  - "rediacc.install_as=systemd"
  - "rediacc.hub.route.app=3000"
  - "rediacc.hub.image=node:22-alpine"
  - "rediacc.hub.command=cd /workspace && npm install && exec npm run dev -- --host __SERVICE_IP__"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.mode=ephemeral"
```

## Related Guides

- [**Services**](/en/docs/services) -- Rediaccfile lifecycle, compose patterns
- [**Networking**](/en/docs/networking) -- Docker labels, Traefik routing, TLS certificates
- [**Backup & Restore**](/en/docs/backup-restore) -- Workspace persistence and recovery
- [**Development Environments**](/en/docs/development-environments) -- Production cloning for dev environments
