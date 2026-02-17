---
title: "Step-by-Step Guide"
description: "Deploy encrypted, isolated infrastructure on your own servers using Rediacc in local mode."
category: "Getting Started"
order: 2
language: en
---

# Step-by-Step Guide

This guide walks you through deploying encrypted, isolated infrastructure on your own servers using Rediacc in **local mode**. By the end, you will have a fully operational repository running containerized services on a remote machine, all managed from your workstation.

Local mode means everything runs on infrastructure you control. No cloud accounts, no SaaS dependencies. Your workstation orchestrates remote servers over SSH, and all state is stored locally on your machine and on the servers themselves.

## Architecture Overview

Rediacc uses a two-tool architecture:

```
Your Workstation                    Remote Server
┌──────────────┐        SSH        ┌──────────────────────────┐
│              │ ──────────────▶   │  renet (Go binary)       │
│  rdc (CLI)   │                   │    ├── LUKS encryption   │
│              │ ◀──────────────   │    ├── Docker daemon     │
│  config.json │    stdout/stderr  │    ├── Rediaccfile exec  │
└──────────────┘                   │    └── Traefik proxy     │
                                   └──────────────────────────┘
```

- **rdc** runs on your workstation (macOS or Linux). It reads your local configuration, connects to remote machines over SSH, and invokes renet commands.
- **renet** runs on the remote server with root privileges. It manages LUKS-encrypted disk images, isolated Docker daemons, service orchestration, and reverse proxy configuration.

Every command you type locally translates to an SSH call that executes renet on the remote machine. You never need to SSH into servers manually.

## Step 1: Create a Local Context

A **context** is a named configuration that stores your SSH credentials, machine definitions, and repository mappings. Think of it as a project workspace.

```bash
rdc context create-local my-infra --ssh-key ~/.ssh/id_ed25519
```

| Option | Required | Description |
|--------|----------|-------------|
| `--ssh-key <path>` | Yes | Path to your SSH private key. Tilde (`~`) is expanded automatically. |
| `--renet-path <path>` | No | Custom path to the renet binary on remote machines. Defaults to the standard install location. |

This creates a local context named `my-infra` and stores it in `~/.rediacc/config.json`.

> You can have multiple contexts (e.g., `production`, `staging`, `dev`). Switch between them with the `--context` flag on any command.

## Step 2: Add a Machine

Register your remote server as a machine in the context:

```bash
rdc context add-machine server-1 --ip 203.0.113.50 --user deploy
```

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--ip <address>` | Yes | - | IP address or hostname of the remote server. |
| `--user <username>` | Yes | - | SSH username on the remote server. |
| `--port <port>` | No | `22` | SSH port. |
| `--datastore <path>` | No | `/mnt/rediacc` | Path on the server where Rediacc stores encrypted repositories. |

After adding the machine, rdc automatically runs `ssh-keyscan` to fetch the server's host keys. You can also run this manually:

```bash
rdc context scan-keys server-1
```

To view all registered machines:

```bash
rdc context machines
```

## Step 3: Set Up the Machine

Provision the remote server with all required dependencies:

```bash
rdc context setup-machine server-1
```

This command:
1. Uploads the renet binary to the server via SFTP
2. Installs Docker, containerd, and cryptsetup (if not present)
3. Creates the datastore directory and prepares it for encrypted repositories

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--datastore <path>` | No | `/mnt/rediacc` | Datastore directory on the server. |
| `--datastore-size <size>` | No | `95%` | How much of the available disk to allocate for the datastore. |
| `--debug` | No | `false` | Enable verbose output for troubleshooting. |

> Setup only needs to be run once per machine. It is safe to re-run if needed.

## Step 4: Create a Repository

A **repository** is a LUKS-encrypted disk image on the remote server. When mounted, it provides:
- An isolated filesystem for your application data
- A dedicated Docker daemon (separate from the host's Docker)
- Unique loopback IPs for each service within a /26 subnet

Create a repository:

```bash
rdc repo create my-app -m server-1 --size 10G
```

| Option | Required | Description |
|--------|----------|-------------|
| `-m, --machine <name>` | Yes | Target machine where the repository will be created. |
| `--size <size>` | Yes | Size of the encrypted disk image (e.g., `5G`, `10G`, `50G`). |

The output will show three auto-generated values:

- **Repository GUID** -- A UUID that identifies the encrypted disk image on the server.
- **Credential** -- A random passphrase used to encrypt/decrypt the LUKS volume.
- **Network ID** -- An integer (starting at 2816, incrementing by 64) that determines the IP subnet for this repository's services.

> **Store the credential securely.** It is the encryption key for your repository. If lost, data cannot be recovered. The credential is stored in your local `config.json` but is not stored on the server.

## Step 5: The Rediaccfile

The **Rediaccfile** is a Bash script that defines how your services are prepared, started, and stopped. It is the core mechanism for service lifecycle management.

### What is a Rediaccfile?

A Rediaccfile is a plain Bash script containing up to three functions: `prep()`, `up()`, and `down()`. It must be named `Rediaccfile` or `rediaccfile` (case-insensitive) and placed inside the repository's mounted filesystem.

Rediaccfiles are discovered in two locations:
1. The **root** of the repository mount path
2. **First-level subdirectories** of the mount path (not recursive)

Hidden directories (names starting with `.`) are skipped.

### Lifecycle Functions

| Function | When it runs | Purpose | Error behavior |
|----------|-------------|---------|----------------|
| `prep()` | Before `up()` | Install dependencies, pull images, run migrations | **Fail-fast** -- if any `prep()` fails, the entire process stops immediately. |
| `up()` | After all `prep()` complete | Start services (e.g., `docker compose up -d`) | Root Rediaccfile failure is **critical** (stops everything). Subdirectory failures are **non-critical** (logged, continues to next). |
| `down()` | When stopping | Stop services (e.g., `docker compose down`) | **Best-effort** -- failures are logged but all Rediaccfiles are always attempted. |

All three functions are optional. If a function is not defined in a Rediaccfile, it is silently skipped.

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

The `{SERVICE}_IP` variables are auto-generated from `.rediacc.json` (see Step 6). The naming convention converts the service name to uppercase with hyphens replaced by underscores, then appends `_IP`. For example, `listmonk-app` becomes `LISTMONK_APP_IP`.

### Example Rediaccfile

A simple Rediaccfile for a web application:

```bash
#!/bin/bash

prep() {
    echo "Pulling latest images..."
    docker compose pull
}

up() {
    echo "Starting services..."
    docker compose up -d
}

down() {
    echo "Stopping services..."
    docker compose down
}
```

### Multi-Service Example

For projects with multiple independent service groups, use subdirectories:

```
/mnt/rediacc/repos/my-app/
├── Rediaccfile              # Root: shared setup (e.g., create Docker networks)
├── docker-compose.yml       # Root compose file
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

## Step 6: Service Networking (.rediacc.json)

Each repository gets a /26 subnet (64 IPs) in the `127.x.x.x` loopback range. Services bind to unique loopback IPs so they can run on the same ports without conflicts. For example, two PostgreSQL instances can both listen on port 5432, each on a different IP.

### The .rediacc.json File

The `.rediacc.json` file maps service names to **slot** numbers. Each slot corresponds to a unique IP address within the repository's subnet.

```json
{
  "services": {
    "api": {"slot": 0},
    "postgres": {"slot": 1},
    "redis": {"slot": 2}
  }
}
```

Services are written in alphabetical order.

### Auto-Generation from Docker Compose

You do not need to create `.rediacc.json` manually. When you run `rdc repo up`, Rediacc automatically:

1. Scans all directories containing a Rediaccfile for compose files (`docker-compose.yml`, `docker-compose.yaml`, `compose.yml`, or `compose.yaml`).
2. Extracts service names from the `services:` section of each compose file.
3. Assigns the next available slot to any new service.
4. Saves the result to `{repository}/.rediacc.json`.

### IP Calculation

The IP for a service is calculated from the repository's network ID and the service's slot. The network ID is split across the second, third, and fourth octets of a `127.x.y.z` loopback address. Each service gets an offset of `slot + 2` added to the network ID (offsets 0 and 1 are reserved for the network address and gateway).

For example, with network ID `2816` (`0x0B00`), the base address is `127.0.11.0` and services start at `127.0.11.2`.

**Example** for network ID `2816`:

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

The `${POSTGRES_IP}` and `${API_IP}` variables are automatically exported from `.rediacc.json` when the Rediaccfile runs.

## Step 7: Start Services

Mount the repository and start all services:

```bash
rdc repo up my-app -m server-1 --mount
```

| Option | Required | Description |
|--------|----------|-------------|
| `-m, --machine <name>` | Yes | Target machine. |
| `--mount` | No | Mount the repository first if not already mounted. Without this flag, the repo must already be mounted. |
| `--prep-only` | No | Run only the `prep()` functions, skip `up()`. Useful for pre-pulling images or running migrations. |

The execution sequence is:

1. Mount the LUKS-encrypted repository (if `--mount` is specified)
2. Start the isolated Docker daemon for this repository
3. Auto-generate `.rediacc.json` from compose files
4. Run `prep()` in all Rediaccfiles (A-Z order, fail-fast)
5. Run `up()` in all Rediaccfiles (A-Z order)

## Step 8: Stop Services

Stop all services in a repository:

```bash
rdc repo down my-app -m server-1
```

| Option | Required | Description |
|--------|----------|-------------|
| `-m, --machine <name>` | Yes | Target machine. |
| `--unmount` | No | Unmount the encrypted repository after stopping services. This also stops the isolated Docker daemon and closes the LUKS volume. |

The execution sequence is:

1. Run `down()` in all Rediaccfiles (Z-A reverse order, best-effort)
2. Stop the isolated Docker daemon (if `--unmount`)
3. Unmount and close the LUKS-encrypted volume (if `--unmount`)

## Other Common Operations

### Mount and Unmount (without starting services)

```bash
rdc repo mount my-app -m server-1     # Decrypt and mount
rdc repo unmount my-app -m server-1   # Unmount and re-encrypt
```

### Check Repository Status

```bash
rdc repo status my-app -m server-1
```

### List All Repositories

```bash
rdc repo list -m server-1
```

### Resize a Repository

```bash
rdc repo resize my-app -m server-1 --size 20G    # Set to exact size
rdc repo expand my-app -m server-1 --size 5G      # Add 5G to current size
```

### Delete a Repository

```bash
rdc repo delete my-app -m server-1
```

> This permanently destroys the encrypted disk image and all data inside it.

### Fork a Repository

Create a copy of an existing repository at its current state:

```bash
rdc repo fork my-app -m server-1 --tag my-app-staging
```

This creates a new encrypted copy with its own GUID and network ID. The fork shares the same LUKS credential as the parent.

### Validate a Repository

Check the filesystem integrity of a repository:

```bash
rdc repo validate my-app -m server-1
```

## Complete Example: Deploying a Web App

This end-to-end example deploys a web application with PostgreSQL, Redis, and an API server.

### 1. Set Up the Environment

```bash
# Install rdc
curl -fsSL https://get.rediacc.com | sh

# Create a local context
rdc context create-local production --ssh-key ~/.ssh/id_ed25519

# Register your server
rdc context add-machine prod-1 --ip 203.0.113.50 --user deploy

# Provision the server
rdc context setup-machine prod-1

# Create an encrypted repository (10 GB)
rdc repo create webapp -m prod-1 --size 10G
```

### 2. Mount and Prepare the Repository

```bash
rdc repo mount webapp -m prod-1
```

SSH into the server and create the application files inside the mounted repository. The mount path is shown in the output (typically `/mnt/rediacc/repos/{guid}`).

### 3. Create the Application Files

Inside the repository, create the following files:

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
    echo "Creating data directories..."
    mkdir -p data/postgres

    echo "Pulling images..."
    docker compose pull
}

up() {
    echo "Starting webapp services..."
    docker compose up -d

    echo "Waiting for PostgreSQL to be ready..."
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
    echo "Stopping webapp services..."
    docker compose down
}
```

### 4. Start Everything

```bash
rdc repo up webapp -m prod-1
```

This will:
1. Auto-generate `.rediacc.json` with slots for `api`, `postgres`, and `redis`
2. Run `prep()` to create directories and pull images
3. Run `up()` to start all containers

### 5. Enable Autostart

```bash
rdc repo autostart enable webapp -m prod-1
```

After a server reboot, the repository will automatically mount and start all services.
