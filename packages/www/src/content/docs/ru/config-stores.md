---
title: "Config & Stores"
description: "Управление файлами конфигурации CLI и синхронизация с внешними хранилищами: Git, Bitwarden, S3, HashiCorp Vault или локальные файлы."
category: "Guides"
order: 8
language: ru
sourceHash: "ed28acf48284b9dc"
---

# Конфигурация и хранилища

Rediacc CLI uses flat JSON config files stored in `~/.config/rediacc/`. Each config file is an independent unit with its own UUID and version number. **Stores** let you sync these configs to external backends for backup, sharing, or multi-device access.

## Файлы конфигурации

Файл конфигурации по умолчанию — `~/.config/rediacc/rediacc.json`. Вы можете создавать именованные конфигурации для разных окружений:

```bash
# Default config (created automatically on first use)
rdc config show

# Create a named config
rdc config init production

# Use a specific config for a command
rdc --config production machine info prod-1

# Or set via environment variable
export REDIACC_CONFIG=production
rdc machine info prod-1
```

Each config file contains:

- **id** — UUID v4, unique to this file, never changes
- **version** — Monotonically increasing, incremented on every write
- Machine definitions (SSH connection details)
- Repository mappings (name to GUID)
- Storage providers (rclone vaults)
- SSH configuration
- Default settings (machine, language, etc.)

### Обнаружение адаптера

The CLI automatically detects which adapter to use based on the config contents:

- **Local adapter** (default) — No cloud credentials. Connects to machines via SSH directly.
- **Cloud adapter** (experimental) — Has `apiUrl` + `token`. Routes through the Rediacc cloud API.
- **S3 resource state** — Local adapter with `s3` config populated. Stores resource state in an S3/R2 bucket.

## Хранилища

A store is an external backend where config files can be synced. This enables:

- **Backup** — Keep a copy of your config in case of local disk loss
- **Multi-device** — Sync the same config across multiple workstations
- **Team sharing** — Share configs via a shared Git repo or S3 bucket

Store credentials are saved in `~/.config/rediacc/.credentials.json` (permissions `0600`).

### Типы хранилищ

| Type | Backend | Best For |
|------|---------|----------|
| `git` | Git repository | Team sharing, version history |
| `bitwarden` | Bitwarden vault (secure notes) | Personal encrypted backup |
| `s3` | S3-compatible bucket | Automated sync, CI/CD |
| `vault` | HashiCorp Vault KV v2 | Teams using Vault, audit trail |
| `local-file` | Local directory | Simple file-based backup |

### Разрешение конфликтов

Every config file has a UUID (`id`) and a `version` number. When pushing to a store:

1. If the remote has a **different UUID** — push is rejected (GUID mismatch). This prevents overwriting a different config.
2. If the remote has a **higher version** — push is rejected (version conflict). Run `rdc store pull` first to get the latest.
3. Otherwise — push succeeds, writing the config to the store.

---

## Git-хранилище

Stores configs as JSON files in a Git repository. Each push clones the repo, writes the config, commits, and pushes.

### Настройка

```bash
# Add a Git store
rdc store add team-configs --type git \
  --git-url git@github.com:yourorg/rdc-configs.git

# Optional: custom branch and path
rdc store add team-configs --type git \
  --git-url git@github.com:yourorg/rdc-configs.git \
  --git-branch main \
  --git-path configs
```

### Как это работает

- Configs are stored at `configs/{name}.json` in the repo (default path: `configs/`)
- Each push creates a commit: `Update config {name} v{version}`
- Works with empty repos (initializes on first push)
- Supports any Git remote (GitHub, GitLab, self-hosted, SSH, HTTPS)

### Требования

- `git` CLI installed
- Push access to the repository (SSH key or HTTPS credentials configured)

---

## Bitwarden-хранилище

Сохраняет каждую конфигурацию как отдельную **защищённую заметку** в хранилище Bitwarden. Элементы именуются с префиксом `rdc:` (напр., `rdc:rediacc`, `rdc:production`).

### Настройка

```bash
# Install Bitwarden CLI
npm install -g @bitwarden/cli

# Login and unlock
bw login
export BW_SESSION=$(bw unlock --raw)

# Add the store
rdc store add my-vault --type bitwarden

# Optional: organize configs in a specific BW folder
rdc store add my-vault --type bitwarden \
  --bw-folder-id <folder-id>
```

### Как это работает

- Each config becomes a secure note named `rdc:{configName}`
- The JSON config is stored in the note's `notes` field
- Auto-discovers items by name — no manual item ID management
- Optional folder filtering with `--bw-folder-id`

### Требования

- `bw` CLI installed ([bitwarden.com/help/cli](https://bitwarden.com/help/cli/))
- Logged in and vault unlocked (`BW_SESSION` env var set)

### Управление сессиями

The adapter checks for `BW_SESSION` in your environment. If not set, it checks the vault status and provides actionable error messages:

```bash
# If you see "vault is locked":
export BW_SESSION=$(bw unlock --raw)

# If you see "not logged in":
bw login
export BW_SESSION=$(bw unlock --raw)
```

> **Tip**: Add `export BW_SESSION=$(bw unlock --raw)` to your shell profile for persistent sessions.

---

## S3-хранилище

Stores configs as JSON objects in an S3-compatible bucket (AWS S3, Cloudflare R2, MinIO, etc.).

### Настройка

```bash
# Add an S3 store (Cloudflare R2 example)
rdc store add cloud-backup --type s3 \
  --s3-endpoint https://<account-id>.r2.cloudflarestorage.com \
  --s3-bucket rdc-configs \
  --s3-region auto \
  --s3-access-key-id <key-id> \
  --s3-secret-access-key <secret>

# Optional: key prefix
rdc store add cloud-backup --type s3 \
  --s3-endpoint https://<account-id>.r2.cloudflarestorage.com \
  --s3-bucket rdc-configs \
  --s3-prefix team-a/
```

### Как это работает

- Configs are stored at `configs/{name}.json` in the bucket (or `{prefix}configs/{name}.json`)
- Uses the `@aws-sdk/client-s3` package for S3 operations

### Требования

- S3-compatible bucket with read/write access
- Access key ID and secret access key

---

## Vault-хранилище

Stores configs as versioned secrets in a HashiCorp Vault KV v2 secrets engine. Each push creates a new version in Vault's built-in version history.

### Настройка

```bash
# Add a Vault store
rdc store add vault-backup --type vault \
  --vault-addr http://vault.internal:8200 \
  --vault-token $VAULT_TOKEN

# Optional: custom mount path and prefix
rdc store add vault-backup --type vault \
  --vault-addr http://vault.internal:8200 \
  --vault-token $VAULT_TOKEN \
  --vault-mount secret \
  --vault-prefix team-a/configs

# Enterprise: specify namespace
rdc store add vault-backup --type vault \
  --vault-addr https://vault.company.com:8200 \
  --vault-token $VAULT_TOKEN \
  --vault-namespace admin/team-a
```

### Как это работает

- Configs are stored at `rdc/configs/{name}` in the KV v2 engine (default mount: `secret/`)
- Each push creates a new version in Vault's built-in version history
- Token auth — pass `--vault-token` or set `VAULT_TOKEN` env var (prompted interactively if neither is set)
- Enterprise namespace support via `--vault-namespace`

### Требования

- HashiCorp Vault server (self-hosted or HCP Vault)
- KV v2 secrets engine enabled (default mount: `secret/`)
- Valid token with read/write/list/delete on the config path

---

## Локальное файловое хранилище

Stores configs as JSON files in a local directory. Useful for simple backups to a mounted drive, NFS share, or Dropbox/Syncthing folder.

### Настройка

```bash
# Backup to a local directory
rdc store add usb-backup --type local-file \
  --local-path /mnt/usb-drive/rdc-configs

# Backup to a synced folder
rdc store add dropbox --type local-file \
  --local-path ~/Dropbox/rdc-configs
```

### Как это работает

- Configs are written as `{path}/{name}.json`
- Uses atomic writes (temp file + rename) for safety
- Version and UUID validation on push, same as other stores

---

## Команды хранилища

```bash
# Add a store
rdc store add <name> --type <git|bitwarden|s3|vault|local-file> [options]

# List all stores
rdc store list

# Push current config to a specific store
rdc store push --store <name>

# Push current config to all stores
rdc store push --all

# Pull config from a store
rdc store pull --store <name>

# Pull a specific config name
rdc store pull --store <name> --config production

# Sync (pull latest, then push)
rdc store sync --store <name>

# Remove a store (does not delete remote data)
rdc store remove <name>
```

## Шифрование

Any store can be wrapped with per-store AES-256-GCM encryption:

```bash
rdc store add secure-backup --type git \
  --git-url git@github.com:yourorg/configs.git \
  --encryption-key "your-secret-key"
```

When encryption is enabled:
- Config JSON is encrypted before pushing to the store
- Pulled configs are decrypted transparently
- The encryption key is stored in `~/.config/rediacc/.credentials.json`
- The remote store only ever sees encrypted data
