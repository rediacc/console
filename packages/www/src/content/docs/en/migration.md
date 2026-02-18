---
title: "Migration Guide"
description: "Migrate existing projects into encrypted Rediacc repositories."
category: "Guides"
order: 11
language: en
---

# Migration Guide

Migrate an existing project — files, Docker services, databases — from a traditional server or local development environment into an encrypted Rediacc repository.

## Prerequisites

- `rdc` CLI installed ([Installation](/en/docs/installation))
- A machine added and provisioned ([Setup](/en/docs/setup))
- Enough disk space on the server for your project (check with `rdc machine status`)

## Step 1: Create a Repository

Create an encrypted repository sized to fit your project. Allocate extra space for Docker images and container data.

```bash
rdc repo create my-project -m server-1 --size 20G
```

> **Tip:** You can resize later with `rdc repo resize` if needed, but the repository must be unmounted first. It's easier to start with enough space.

## Step 2: Upload Your Files

Use `rdc sync upload` to transfer your project files into the repository.

```bash
# Preview what will be transferred (no changes made)
rdc sync upload -m server-1 -r my-project --local ./my-project --dry-run

# Upload files
rdc sync upload -m server-1 -r my-project --local ./my-project
```

The repository must be mounted before uploading. If it isn't already:

```bash
rdc repo mount my-project -m server-1
```

For subsequent syncs where you want the remote to exactly match your local directory:

```bash
rdc sync upload -m server-1 -r my-project --local ./my-project --mirror
```

> The `--mirror` flag deletes files on the remote that don't exist locally. Use `--dry-run` first to verify.

## Step 3: Fix File Ownership

Uploaded files arrive with your local user's UID (e.g., 1000). Rediacc uses a universal user (UID 7111) so that VS Code, terminal sessions, and tools all have consistent access. Run the ownership command to convert:

```bash
rdc repo ownership my-project -m server-1
```

### Docker-Aware Exclusion

If Docker containers are running (or have been run), the ownership command automatically detects their writable data directories and **skips them**. This prevents breaking containers that manage their own files with different UIDs (e.g., MariaDB uses UID 999, Nextcloud uses UID 33).

The command reports what it does:

```
Excluding Docker volume: database/data
Excluding Docker volume: redis/data
Ownership set to UID 7111 (245 changed, 4 skipped, 0 errors)
```

### When to Run

- **After uploading files** — to convert your local UID to 7111
- **After starting containers** — if you want Docker volume directories to be auto-excluded. If containers haven't been started yet, there are no volumes to exclude and all directories get chowned (which is fine — the containers will recreate their data on first start)

### Force Mode

To skip Docker volume detection and chown everything, including container data directories:

```bash
rdc repo ownership my-project -m server-1 --force
```

> **Warning:** This may break running containers. Stop them first with `rdc repo down` if needed.

### Custom UID

To set a UID other than the default 7111:

```bash
rdc repo ownership my-project -m server-1 --uid 1000
```

## Step 4: Set Up Your Rediaccfile

Create a `Rediaccfile` in your project root. This Bash script defines how your services are prepared, started, and stopped.

```bash
#!/bin/bash

prep() {
    docker compose pull
}

up() {
    docker compose up -d
}

down() {
    docker compose down
}
```

The three lifecycle functions:

| Function | Purpose | Error behavior |
|----------|---------|----------------|
| `prep()` | Pull images, run migrations, install dependencies | Fail-fast: any failure stops everything |
| `up()` | Start services | Root failure is critical; subdirectory failures are logged and continue |
| `down()` | Stop services | Best-effort: always attempts all |

> **Important:** Use `docker` directly in your Rediaccfile — never `sudo docker`. The `sudo` command resets environment variables, which causes `DOCKER_HOST` to be lost and containers to be created on the system Docker daemon instead of the repository's isolated daemon. Rediaccfile functions already run with sufficient privileges. See [Services](/en/docs/services#environment-variables) for details.

See [Services](/en/docs/services) for full details on Rediaccfiles, multi-service layouts, and execution order.

## Step 5: Configure Service Networking

Rediacc runs an isolated Docker daemon per repository. Services use `network_mode: host` and bind to unique loopback IPs so they can use standard ports without conflicts across repositories.

### Adapting Your docker-compose.yml

**Before (traditional):**

```yaml
services:
  postgres:
    image: postgres:16
    ports:
      - "5432:5432"
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  app:
    image: my-app:latest
    ports:
      - "8080:8080"
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb
      REDIS_URL: redis://redis:6379
```

**After (Rediacc):**

```yaml
services:
  postgres:
    image: postgres:16
    network_mode: host
    restart: unless-stopped
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432

  redis:
    image: redis:7-alpine
    network_mode: host
    restart: unless-stopped
    command: redis-server --bind ${REDIS_IP} --port 6379

  app:
    image: my-app:latest
    network_mode: host
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql://postgres:secret@${POSTGRES_IP}:5432/mydb
      REDIS_URL: redis://${REDIS_IP}:6379
      LISTEN_ADDR: ${APP_IP}:8080
```

Key changes:

1. **Add `network_mode: host`** to every service
2. **Remove `ports:` mappings** (not needed with host networking)
3. **Bind services to `${SERVICE_IP}`** environment variables (auto-injected by Rediacc)
4. **Reference other services by their IP** instead of Docker DNS names (e.g., `${POSTGRES_IP}` instead of `postgres`)

The `{SERVICE}_IP` variables are automatically generated from your compose file's service names. The naming convention: uppercase, hyphens replaced with underscores, suffixed with `_IP`. For example, `listmonk-app` becomes `LISTMONK_APP_IP`.

See [Service Networking](/en/docs/services#service-networking-rediaccjson) for details on IP assignment and `.rediacc.json`.

## Step 6: Start Services

Mount the repository (if not already mounted) and start all services:

```bash
rdc repo up my-project -m server-1 --mount
```

This will:
1. Mount the encrypted repository
2. Start the isolated Docker daemon
3. Auto-generate `.rediacc.json` with service IP assignments
4. Run `prep()` from all Rediaccfiles
5. Run `up()` from all Rediaccfiles

Verify your containers are running:

```bash
rdc machine containers server-1
```

## Step 7: Enable Autostart (Optional)

By default, repositories must be manually mounted and started after a server reboot. Enable autostart so your services come up automatically:

```bash
rdc repo autostart enable my-project -m server-1
```

You will be prompted for the repository passphrase.

> **Security note:** Autostart stores a LUKS keyfile on the server. Anyone with root access can mount the repository without the passphrase. See [Autostart](/en/docs/services#autostart-on-boot) for details.

## Common Migration Scenarios

### WordPress / PHP with Database

```
my-wordpress/
├── Rediaccfile
├── docker-compose.yml
├── app/                    # WordPress files (UID 33 when running)
├── database/data/          # MariaDB data (UID 999 when running)
└── wp-content/uploads/     # User uploads
```

1. Upload your project files
2. Start services first (`rdc repo up`) so containers create their data directories
3. Run ownership fix — MariaDB and app data dirs are auto-excluded

### Node.js / Python with Redis

```
my-api/
├── Rediaccfile
├── docker-compose.yml
├── src/                    # Application source
├── node_modules/           # Dependencies
└── redis-data/             # Redis persistence (UID 999 when running)
```

1. Upload your project (consider excluding `node_modules` and pulling in `prep()`)
2. Run ownership fix after containers have started

### Custom Docker Project

For any project with Docker services:

1. Upload project files
2. Adapt `docker-compose.yml` (see Step 5)
3. Create a `Rediaccfile` with lifecycle functions
4. Run ownership fix
5. Start services

## Troubleshooting

### Permission Denied After Upload

Files still have your local UID. Run the ownership command:

```bash
rdc repo ownership my-project -m server-1
```

### Container Won't Start

Check that services bind to their assigned IP, not `0.0.0.0` or `localhost`:

```bash
# Check assigned IPs
rdc term server-1 my-project -c "cat .rediacc.json"

# Check container logs
rdc term server-1 my-project -c "docker logs <container-name>"
```

### Port Conflict Between Repositories

Each repository gets unique loopback IPs. If you see port conflicts, verify that your `docker-compose.yml` uses `${SERVICE_IP}` for binding instead of `0.0.0.0`. Services bound to `0.0.0.0` listen on all interfaces and will conflict with other repositories.

### Ownership Fix Breaks Containers

If you ran `rdc repo ownership --force` and a container stopped working, the container's data files were chowned. Stop the container, delete its data directory, and restart — the container will recreate it:

```bash
rdc repo down my-project -m server-1
# Delete the container's data directory (e.g., database/data)
rdc repo up my-project -m server-1
```
