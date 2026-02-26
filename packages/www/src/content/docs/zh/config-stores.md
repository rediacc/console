---
title: "Config & Stores"
description: "管理 CLI 配置文件，并与 Git、Bitwarden、S3、HashiCorp Vault 或本地文件等外部后端同步。"
category: "Guides"
order: 8
language: zh
sourceHash: "ed28acf48284b9dc"
---

# 配置与存储

Rediacc CLI 使用存储在 `~/.config/rediacc/` 中的扁平 JSON 配置文件。每个配置文件都是一个独立的单元，拥有自己的 UUID 和版本号。**存储**允许您将这些配置同步到外部后端进行备份、共享或多设备访问。

## 配置文件

默认配置文件为 `~/.config/rediacc/rediacc.json`。您可以为不同的环境创建命名配置：

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

每个配置文件包含：

- **id** — UUID v4, unique to this file, never changes
- **version** — Monotonically increasing, incremented on every write
- Machine definitions (SSH connection details)
- Repository mappings (name to GUID)
- Storage providers (rclone vaults)
- SSH configuration
- Default settings (machine, language, etc.)

### 适配器检测

CLI 根据配置内容自动检测使用哪个适配器：

- **Local adapter** (default) — No cloud credentials. Connects to machines via SSH directly.
- **Cloud adapter** (experimental) — Has `apiUrl` + `token`. Routes through the Rediacc cloud API.
- **S3 resource state** — Local adapter with `s3` config populated. Stores resource state in an S3/R2 bucket.

## 存储

存储是一个可以同步配置文件的外部后端。这使得以下功能成为可能：

- **Backup** — Keep a copy of your config in case of local disk loss
- **Multi-device** — Sync the same config across multiple workstations
- **Team sharing** — Share configs via a shared Git repo or S3 bucket

存储凭据保存在 `~/.config/rediacc/.credentials.json` 中（权限 `0600`）。

### 存储类型

| Type | Backend | Best For |
|------|---------|----------|
| `git` | Git repository | Team sharing, version history |
| `bitwarden` | Bitwarden vault (secure notes) | Personal encrypted backup |
| `s3` | S3-compatible bucket | Automated sync, CI/CD |
| `vault` | HashiCorp Vault KV v2 | Teams using Vault, audit trail |
| `local-file` | Local directory | Simple file-based backup |

### 冲突解决

每个配置文件都有一个 UUID（`id`）和一个 `version` 号。推送到存储时：

1. If the remote has a **different UUID** — push is rejected (GUID mismatch). This prevents overwriting a different config.
2. If the remote has a **higher version** — push is rejected (version conflict). Run `rdc store pull` first to get the latest.
3. Otherwise — push succeeds, writing the config to the store.

---

## Git 存储

将配置作为 JSON 文件存储在 Git 仓库中。每次推送都会克隆仓库、写入配置、提交并推送。

### 设置

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

### 工作原理

- Configs are stored at `configs/{name}.json` in the repo (default path: `configs/`)
- Each push creates a commit: `Update config {name} v{version}`
- Works with empty repos (initializes on first push)
- Supports any Git remote (GitHub, GitLab, self-hosted, SSH, HTTPS)

### 要求

- `git` CLI installed
- Push access to the repository (SSH key or HTTPS credentials configured)

---

## Bitwarden 存储

将每个配置作为单独的**安全笔记**存储在您的 Bitwarden 保险库中。条目以 `rdc:` 前缀命名（例如 `rdc:rediacc`、`rdc:production`）。

### 设置

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

### 工作原理

- Each config becomes a secure note named `rdc:{configName}`
- The JSON config is stored in the note's `notes` field
- Auto-discovers items by name — no manual item ID management
- Optional folder filtering with `--bw-folder-id`

### 要求

- `bw` CLI installed ([bitwarden.com/help/cli](https://bitwarden.com/help/cli/))
- Logged in and vault unlocked (`BW_SESSION` env var set)

### 会话管理

适配器在您的环境中检查 `BW_SESSION`。如果未设置，它会检查保险库状态并提供可操作的错误消息：

```bash
# If you see "vault is locked":
export BW_SESSION=$(bw unlock --raw)

# If you see "not logged in":
bw login
export BW_SESSION=$(bw unlock --raw)
```

> **Tip**: Add `export BW_SESSION=$(bw unlock --raw)` to your shell profile for persistent sessions.

---

## S3 存储

将配置作为 JSON 对象存储在 S3 兼容存储桶中（AWS S3、Cloudflare R2、MinIO 等）。

### 设置

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

### 工作原理

- Configs are stored at `configs/{name}.json` in the bucket (or `{prefix}configs/{name}.json`)
- Uses the `@aws-sdk/client-s3` package for S3 operations

### 要求

- S3-compatible bucket with read/write access
- Access key ID and secret access key

---

## Vault 存储

将配置作为版本化密钥存储在 HashiCorp Vault KV v2 密钥引擎中。每次推送都会在 Vault 的内置版本历史中创建新版本。

### 设置

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

### 工作原理

- Configs are stored at `rdc/configs/{name}` in the KV v2 engine (default mount: `secret/`)
- Each push creates a new version in Vault's built-in version history
- Token auth — pass `--vault-token` or set `VAULT_TOKEN` env var (prompted interactively if neither is set)
- Enterprise namespace support via `--vault-namespace`

### 要求

- HashiCorp Vault server (self-hosted or HCP Vault)
- KV v2 secrets engine enabled (default mount: `secret/`)
- Valid token with read/write/list/delete on the config path

---

## 本地文件存储

将配置作为 JSON 文件存储在本地目录中。适用于挂载驱动器、NFS 共享或 Dropbox/Syncthing 文件夹的简单备份。

### 设置

```bash
# Backup to a local directory
rdc store add usb-backup --type local-file \
  --local-path /mnt/usb-drive/rdc-configs

# Backup to a synced folder
rdc store add dropbox --type local-file \
  --local-path ~/Dropbox/rdc-configs
```

### 工作原理

- Configs are written as `{path}/{name}.json`
- Uses atomic writes (temp file + rename) for safety
- Version and UUID validation on push, same as other stores

---

## 存储命令

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

## 加密

任何存储都可以使用每个存储的 AES-256-GCM 加密进行包装：

```bash
rdc store add secure-backup --type git \
  --git-url git@github.com:yourorg/configs.git \
  --encryption-key "your-secret-key"
```

启用加密时：
- Config JSON is encrypted before pushing to the store
- Pulled configs are decrypted transparently
- The encryption key is stored in `~/.config/rediacc/.credentials.json`
- The remote store only ever sees encrypted data
