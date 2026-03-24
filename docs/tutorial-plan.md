# Rediacc YouTube Tutorial — Script & Command Reference

## Introduction

### 1. Key Concepts

A repo is a single encrypted file on disk. Move it, back it up, fork it — it's
just a file. When mounted, it becomes a folder with a dedicated Docker daemon
and your app data inside.

Think of a repo like a USB drive. It's something in your hand, and when you plug
it in it becomes visible and accessible to the system.

```
/mnt/rediacc/repositories/2816/a1b2c3d4.luks   ← the "USB drive" (encrypted file)
                    ↓ mount
/mnt/rediacc/mounts/a1b2c3d4/                   ← the folder you work in
├── my-app/
│   ├── docker-compose.yml
│   ├── Rediaccfile
│   └── data/
└── .rediacc.json                                ← service → IP slot mapping
```

### 2. What is Where?

- **rdc** = CLI on your laptop (TypeScript, installed globally)
- **renet** = orchestrator on the server (Go binary, manages daemons/networks/isolation)
- RDC provisions renet automatically on first SSH connect — no manual setup on the server.

### 3. CLI Setup

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
rdc doctor     # Verify: Node, SSH key, renet, Docker — all green
```

### 4. Machine Add & Setup

```bash
rdc config machine add my-server --ip 192.168.1.100 --user muhammed
rdc config machine setup my-server        # Provisions renet + creates BTRFS datastore
```

> **What happens:** SSH key scanned, renet binary uploaded, datastore initialized at
> `/mnt/rediacc` with LUKS encryption ready.

### 5. Config File

```bash
rdc config show                            # Human-readable summary
cat ~/.config/rediacc/rediacc.json         # Raw JSON: machines, repos, storages, SSH key
```

> **One file = one environment.** Copy it to another laptop and you're ready.
> Encrypt it with `--master-password` for security.

---

## Working with a Repo

### 1. Repo Creation

```bash
rdc repo create my-app -m my-server --size 2G       # Create 2 GB encrypted repo
rdc repo up my-app -m my-server                      # Mount + run Rediaccfile up()
rdc repo list -m my-server                           # See all repos on the machine
rdc repo status my-app -m my-server                  # Check running containers
```

### 2. VS Code

```bash
rdc vscode my-server my-app              # Opens VS Code SSH — lands inside the repo sandbox
```

> You're now editing files *inside* the encrypted volume. Docker commands only see
> this repo's containers. Save, compose up, iterate — all from VS Code.

### 3. Universal User, Daemon & Isolation

- **Universal user** (`rediacc`): Same UID across every machine. Move a repo to
  another server — file ownership just works. No `chown` headaches.
- **Per-repo Docker daemon**: Each repo gets its own daemon at
  `/var/run/rediacc/docker-{networkId}.sock` with a `/26` loopback IP range (61 usable IPs).
  `docker ps` only shows THIS repo's containers.
- **Landlock + OverlayFS sandbox**: The VS Code shell is filesystem-restricted.
  You can't read other repos. Writes to `$HOME` are per-repo overlays.

### 4. Template Apply & renet dev

```bash
rdc repo template list                                        # Show embedded templates
rdc repo template apply app-postgres -m my-server -r my-app   # Deploy template into repo
rdc repo up my-app -m my-server                               # Start from CLI (full lifecycle)
```

**`rdc repo up` vs `renet dev up`:**

| | `rdc repo up` | `renet dev up` |
|---|---|---|
| **Where you run it** | Your laptop (CLI) | Inside VS Code sandbox |
| **What it does** | SSH → mount LUKS → run Rediaccfile `up()` | Directly calls Rediaccfile `up()` |
| **Use case** | CI/CD, automation, remote ops | Developer inner loop |
| **Isolation** | Orchestrates from outside | Already inside the sandbox |

> **Demo flow:** `rdc repo template apply` → `rdc vscode my-server my-app` → edit
> `docker-compose.yml` → `renet dev up` → see app running → iterate.

### 5. Term, Sync & Tunnel

**Terminal:**
```bash
rdc term my-server my-app                            # SSH into repo sandbox
rdc term my-server my-app -c "curl localhost:3000"   # Run command & exit
rdc term my-server                                   # SSH to machine (no sandbox)
```

**File Sync (rsync over SSH):**
```bash
rdc repo sync upload -m my-server -r my-app -l ./src       # Push local files to repo
rdc repo sync download -m my-server -r my-app -l ./backup  # Pull repo files to local
rdc repo sync download -m my-server -r my-app -l ./backup --dry-run  # Preview first
```

**Tunnel (SSH port-forwarding to container):**
```bash
rdc repo tunnel -m my-server -r my-app                     # Auto-detect container & port
rdc repo tunnel -m my-server -r my-app --port 5432         # Tunnel Postgres
rdc repo tunnel -m my-server -r my-app --port 5432 --local 15432  # Custom local port
```

> **Demo:** Run tunnel → open `localhost:3000` in browser → live app from remote server.

---

## Fork & Backup

### 1. Grand & Fork Repos

```bash
rdc repo fork my-app -m my-server --tag experiment --up     # Instant CoW clone + start
rdc repo list -m my-server                                  # Shows: my-app (grand) + my-app:experiment (fork)
rdc repo delete my-app:experiment -m my-server              # Delete fork, grand untouched
```

> **Instant, zero-copy clone** — BTRFS reflinks. Microseconds, no data copied.
> Blocks are shared until one side writes.

**Use cases:**
- **AI / ML:** Fork production dataset, run experiment, discard or promote
- **DevOps:** Fork → test migration → delete if bad, promote if good
- **Backup:** Fork = instant snapshot, push it offsite

### 2. Push to Another Machine

```bash
# Push repo backup to another machine
rdc repo push my-app -m my-server --to backup-server

# Push and auto-deploy on target
rdc repo push my-app -m my-server --to backup-server --up

# Push with CRIU checkpoint (live migration — preserves memory state)
rdc repo push my-app -m my-server --to new-server --checkpoint --up

# Push to a new machine that doesn't exist yet (auto-provision via cloud provider)
rdc repo push my-app -m my-server --to new-server --provision hetzner --up
```

> **Demo:** Push a running app to a brand-new server in one command.

### 3. Push to Cloud Storage (OneDrive, Google Drive, S3)

```bash
# Import your rclone config as a storage backend
rdc config storage import ~/rclone.conf

# List available storages
rdc storage list

# Push repo to cloud storage
rdc repo push my-app -m my-server --to my-s3-backup

# List backups on storage
rdc repo backup list --from my-s3-backup -m my-server
```

> `--to` auto-detects whether the target is a machine or a storage backend.
> Works with any rclone-supported provider: S3, R2, B2, OneDrive, Google Drive, SFTP, etc.

### 4. Pull from Remote to Local Machine

```bash
# Pull repo from another machine
rdc repo pull my-app -m my-server --from backup-server

# Pull from cloud storage
rdc repo pull my-app -m my-server --from my-s3-backup

# Pull and start immediately
rdc repo pull my-app -m my-server --from my-s3-backup --up
```

> **Full cycle:** Create on dev machine → push to cloud → pull on production → `--up`.
> One repo, any machine, any cloud.

---

## Proxy & SSL

### 1. Push Infrastructure Config

```bash
rdc config infra set my-server           # Configure: base domain, public IPs, port ranges
rdc config infra show my-server          # Review configuration
rdc config infra push my-server          # Push Traefik proxy config to remote
```

> **How routing works:**
> - Traefik auto-discovers containers via `rediacc.service_name` and `rediacc.service_port` labels
> - Routes: `{service}-{networkId}.{baseDomain}` → container loopback IP:port
> - SSL: Let's Encrypt via Cloudflare DNS-01 challenge (auto-renewal, wildcard certs)

### 2. Proxy Template

```bash
rdc repo template apply proxy -m my-server -r infra     # Deploy proxy into a repo
rdc repo up infra -m my-server                           # Start Traefik
```

> Traefik now routes external traffic to all repos on this machine.
> Each repo's containers automatically get HTTPS endpoints.

```bash
# Demo: navigate to https://my-app.example.com → routed to container
# TCP/UDP forwarding for databases:
#   rediacc.tcp_ports=3306,5432 → auto-allocated external ports
```

---

## Quick Reference Card

| Task | Command |
|------|---------|
| Install | `curl -fsSL https://www.rediacc.com/install.sh \| bash` |
| Add machine | `rdc config machine add <name> --ip <ip> --user <user>` |
| Setup machine | `rdc config machine setup <name>` |
| Create repo | `rdc repo create <name> -m <machine> --size <size>` |
| Start repo | `rdc repo up <name> -m <machine>` |
| VS Code | `rdc vscode <machine> <repo>` |
| Terminal | `rdc term <machine> <repo>` |
| Tunnel | `rdc repo tunnel -m <machine> -r <repo>` |
| Sync upload | `rdc repo sync upload -m <machine> -r <repo> -l <path>` |
| Fork | `rdc repo fork <repo> -m <machine> --tag <tag>` |
| Push to machine | `rdc repo push <repo> -m <machine> --to <target>` |
| Push to cloud | `rdc repo push <repo> -m <machine> --to <storage>` |
| Pull | `rdc repo pull <repo> -m <machine> --from <source>` |
| Apply template | `rdc repo template apply <tmpl> -m <machine> -r <repo>` |
| Proxy setup | `rdc config infra push <machine>` |
