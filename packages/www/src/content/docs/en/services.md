---
title: "Services"
description: "Deploy and manage containerized services using Rediaccfiles, service networking, and autostart."
category: "Guides"
order: 5
language: en
---

# Services

This page covers how to deploy and manage containerized services: Rediaccfiles, service networking, starting/stopping, bulk operations, and autostart.

## The Rediaccfile

The **Rediaccfile** is a Bash script that defines how your services are prepared, started, and stopped. It must be named `Rediaccfile` or `rediaccfile` (case-insensitive) and placed inside the repository's mounted filesystem.

Rediaccfiles are discovered in two locations:
1. The **root** of the repository mount path
2. **First-level subdirectories** of the mount path (not recursive)

Hidden directories (names starting with `.`) are skipped.

### Lifecycle Functions

A Rediaccfile contains up to three functions:

| Function | When it runs | Purpose | Error behavior |
|----------|-------------|---------|----------------|
| `prep()` | Before `up()` | Install dependencies, pull images, run migrations | **Fail-fast** -- if any `prep()` fails, the entire process stops immediately |
| `up()` | After all `prep()` complete | Start services (e.g., `docker compose up -d`) | Root failure is **critical** (stops everything). Subdirectory failures are **non-critical** (logged, continues) |
| `down()` | When stopping | Stop services (e.g., `docker compose down`) | **Best-effort** -- failures are logged but all Rediaccfiles are always attempted |

All three functions are optional. If a function is not defined, it is silently skipped.

### Execution Order

- **Starting (`up`):** Root Rediaccfile first, then subdirectories in **alphabetical order** (A to Z).
- **Stopping (`down`):** Subdirectories in **reverse alphabetical order** (Z to A), then root last.

### Environment Variables

When a Rediaccfile function executes, the following environment variables are available:

| Variable | Description | Example |
|----------|-------------|---------|
| `REPOSITORY_PATH` | Mount path of the repository | `/mnt/rediacc/repos/abc123` |
| `REPOSITORY_NAME` | Repository GUID | `a1b2c3d4-e5f6-...` |
| `REPOSITORY_NETWORK_ID` | Network ID (integer) | `2816` |
| `DOCKER_HOST` | Docker socket for this repository's isolated daemon | `unix:///var/run/rediacc/docker-2816.sock` |
| `{SERVICE}_IP` | Loopback IP for each service defined in `.rediacc.json` | `POSTGRES_IP=127.0.11.2` |

The `{SERVICE}_IP` variables are auto-generated from `.rediacc.json`. The naming convention converts the service name to uppercase with hyphens replaced by underscores, then appends `_IP`. For example, `listmonk-app` becomes `LISTMONK_APP_IP`.

> **Warning: Do not use `sudo docker` in Rediaccfiles.** The `sudo` command resets environment variables, which means `DOCKER_HOST` is lost and Docker commands will target the system daemon instead of the repository's isolated daemon. This breaks container isolation and can cause port conflicts. Rediacc will block execution if it detects `sudo docker` without `-E`.
>
> Use `renet compose` in your Rediaccfiles — it automatically handles `DOCKER_HOST`, injects networking labels for route discovery, and configures service networking. See [Networking](/en/docs/networking) for details on how services are exposed via the reverse proxy. If calling Docker directly, use `docker` without `sudo` — Rediaccfile functions already run with sufficient privileges. If you must use sudo, use `sudo -E docker` to preserve environment variables.

### Example

```bash
#!/bin/bash

prep() {
    echo "Pulling latest images..."
    renet compose -- pull
}

up() {
    echo "Starting services..."
    renet compose -- up -d
}

down() {
    echo "Stopping services..."
    renet compose -- down
}
```

> `docker compose` also works since `DOCKER_HOST` is set automatically, but `renet compose` is preferred because it additionally injects `rediacc.*` labels needed for reverse proxy route discovery. See [Networking](/en/docs/networking) for details.

### Multi-Service Layout

For projects with multiple independent service groups, use subdirectories:

```
/mnt/rediacc/repos/my-app/
├── Rediaccfile              # Root: shared setup
├── docker-compose.yml
├── database/
│   ├── Rediaccfile          # Database services
│   └── docker-compose.yml
├── backend/
│   ├── Rediaccfile          # API server
│   └── docker-compose.yml
└── monitoring/
    ├── Rediaccfile          # Prometheus, Grafana, etc.
    └── docker-compose.yml
```

Execution order for `up`: root, then `backend`, `database`, `monitoring` (A-Z).
Execution order for `down`: `monitoring`, `database`, `backend`, then root (Z-A).

## Service Networking (.rediacc.json)

Each repository gets a /26 subnet (64 IPs) in the `127.x.x.x` loopback range. Services bind to unique loopback IPs so they can run on the same ports without conflicts.

### The .rediacc.json File

Maps service names to **slot** numbers. Each slot corresponds to a unique IP address within the repository's subnet.

```json
{
  "services": {
    "api": {"slot": 0},
    "postgres": {"slot": 1},
    "redis": {"slot": 2}
  }
}
```

### Auto-Generation from Docker Compose

You do not need to create `.rediacc.json` manually. When you run `rdc repo up`, Rediacc automatically:

1. Scans all directories containing a Rediaccfile for compose files (`docker-compose.yml`, `docker-compose.yaml`, `compose.yml`, or `compose.yaml`)
2. Extracts service names from the `services:` section
3. Assigns the next available slot to new services
4. Saves the result to `{repository}/.rediacc.json`

### IP Calculation

The IP for a service is calculated from the repository's network ID and the service's slot. The network ID is split across the second, third, and fourth octets of a `127.x.y.z` loopback address. Each service gets an offset of `slot + 2` (offsets 0 and 1 are reserved).

**Example** for network ID `2816` (`0x0B00`), base address `127.0.11.0`:

| Service | Slot | IP Address |
|---------|------|------------|
| api | 0 | `127.0.11.2` |
| postgres | 1 | `127.0.11.3` |
| redis | 2 | `127.0.11.4` |

Each repository supports up to **61 services** (slots 0 through 60).

### Using Service IPs in Docker Compose

Since each repository runs an isolated Docker daemon, services use `network_mode: host` and bind to their assigned loopback IPs:

```yaml
services:
  postgres:
    image: postgres:16
    network_mode: host
    environment:
      PGDATA: /var/lib/postgresql/data
      POSTGRES_PASSWORD: secret
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432

  api:
    image: my-api:latest
    network_mode: host
    environment:
      DATABASE_URL: postgresql://postgres:secret@${POSTGRES_IP}:5432/mydb
      LISTEN_ADDR: ${API_IP}:8080
```

## Starting Services

Mount the repository and start all services:

```bash
rdc repo up my-app -m server-1 --mount
```

| Option | Description |
|--------|-------------|
| `--mount` | Mount the repository first if not already mounted |
| `--prep-only` | Run only `prep()` functions, skip `up()` |

The execution sequence is:
1. Mount the LUKS-encrypted repository (if `--mount`)
2. Start the isolated Docker daemon
3. Auto-generate `.rediacc.json` from compose files
4. Run `prep()` in all Rediaccfiles (A-Z order, fail-fast)
5. Run `up()` in all Rediaccfiles (A-Z order)

## Stopping Services

```bash
rdc repo down my-app -m server-1
```

| Option | Description |
|--------|-------------|
| `--unmount` | Unmount the encrypted repository after stopping |

The execution sequence is:
1. Run `down()` in all Rediaccfiles (Z-A reverse order, best-effort)
2. Stop the isolated Docker daemon (if `--unmount`)
3. Unmount and close the LUKS-encrypted volume (if `--unmount`)

## Bulk Operations

Start or stop all repositories on a machine at once:

```bash
rdc repo up-all -m server-1
```

| Option | Description |
|--------|-------------|
| `--include-forks` | Include forked repositories |
| `--mount-only` | Only mount, don't start containers |
| `--dry-run` | Show what would be done |
| `--parallel` | Run operations in parallel |
| `--concurrency <n>` | Max concurrent operations (default: 3) |

## Autostart on Boot

By default, repositories must be manually mounted and started after a server reboot. **Autostart** configures repositories to automatically mount, start Docker, and run Rediaccfile `up()` when the server boots.

### How It Works

When you enable autostart for a repository:

1. A 256-byte random LUKS keyfile is generated and added to the repository's LUKS slot 1 (slot 0 remains the user passphrase)
2. The keyfile is stored at `{datastore}/.credentials/keys/{guid}.key` with `0600` permissions (root-only)
3. A systemd service (`rediacc-autostart`) runs at boot to mount all enabled repositories and start their services

On shutdown, the service gracefully stops all services (Rediaccfile `down()`), stops Docker daemons, and closes LUKS volumes.

> **Security note:** Enabling autostart stores a LUKS keyfile on the server's disk. Anyone with root access to the server can mount the repository without the passphrase. Evaluate this based on your threat model.

### Enable

```bash
rdc repo autostart enable my-app -m server-1
```

You will be prompted for the repository passphrase.

### Enable All

```bash
rdc repo autostart enable-all -m server-1
```

### Disable

```bash
rdc repo autostart disable my-app -m server-1
```

This removes the keyfile and kills LUKS slot 1.

### List Status

```bash
rdc repo autostart list -m server-1
```

## Complete Example

This deploys a web application with PostgreSQL, Redis, and an API server.

### 1. Set Up

```bash
curl -fsSL https://get.rediacc.com | sh
rdc context create-local production --ssh-key ~/.ssh/id_ed25519
rdc context add-machine prod-1 --ip 203.0.113.50 --user deploy
rdc context setup-machine prod-1
rdc repo create webapp -m prod-1 --size 10G
```

### 2. Mount and Prepare

```bash
rdc repo mount webapp -m prod-1
```

### 3. Create Application Files

Inside the repository, create:

**docker-compose.yml:**

```yaml
services:
  postgres:
    image: postgres:16
    network_mode: host
    restart: unless-stopped
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432

  redis:
    image: redis:7-alpine
    network_mode: host
    restart: unless-stopped
    command: redis-server --bind ${REDIS_IP} --port 6379

  api:
    image: myregistry/api:latest
    network_mode: host
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql://app:changeme@${POSTGRES_IP}:5432/webapp
      REDIS_URL: redis://${REDIS_IP}:6379
      LISTEN_ADDR: ${API_IP}:8080
```

**Rediaccfile:**

```bash
#!/bin/bash

prep() {
    mkdir -p data/postgres
    renet compose -- pull
}

up() {
    renet compose -- up -d

    echo "Waiting for PostgreSQL..."
    for i in $(seq 1 30); do
        if docker compose exec postgres pg_isready -q 2>/dev/null; then
            echo "PostgreSQL is ready."
            return 0
        fi
        sleep 1
    done
    echo "Warning: PostgreSQL did not become ready within 30 seconds."
}

down() {
    renet compose -- down
}
```

### 4. Start

```bash
rdc repo up webapp -m prod-1
```

### 5. Enable Autostart

```bash
rdc repo autostart enable webapp -m prod-1
```
