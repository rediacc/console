---
title: AI Asistanları için AGENTS.md Şablonu
description: >-
  Claude Code, Cursor ve diğer AI kodlama asistanlarını Rediacc altyapısıyla
  çalışacak şekilde yapılandırmak için kopyala-yapıştır şablonu.
category: Reference
order: 50
language: tr
sourceHash: "1edff3471ded906d"
sourceCommit: "23543669cd22bce3f14d69a0886bac8a12061412"
---

İşte sorun: AI kodlama asistanları (Claude Code, Cursor, Cline, Windsurf) var olmayan `rdc` bayrakları üretiyor ve sizi her seferinde hangi Rediacc depo adının hangi GUID'e karşılık geldiğini sormadan anlayamıyorlar. Bu şablon bunu düzeltiyor. Aşağıdaki bloğu projenizin `CLAUDE.md`, `.cursorrules` veya aracınızın kullandığı ajan yapılandırma dosyasına yapıştırın.

## Şablon

```markdown
# Rediacc Infrastructure

Self-hosted infrastructure platform. Each machine runs Docker-based repositories with encrypted, isolated environments.

## CLI Tool: rdc

Install: `curl -fsSL https://www.rediacc.com/install.sh | bash`

### Key Flags
- `--output json` (or `-o json`), machine-readable JSON output
- `--yes` (or `-y`), skip interactive confirmations
- `--quiet` (or `-q`), suppress informational output
- `--fields name,status`, limit output fields
- Auto-JSON: when piped (non-TTY), output defaults to JSON automatically

### JSON Envelope
All JSON output uses a consistent envelope:
{"success": true, "command": "...", "data": ..., "errors": null, "warnings": [], "metrics": {"duration_ms": N}}

On error: {"success": false, "command": "...", "data": null, "errors": [{"code": "...", "message": "...", "retryable": false, "guidance": "..."}], ...}

### Common Operations

# Machine status
rdc machine status <machine> -o json

# List containers on a machine
rdc machine status <machine> --containers -o json

# Machine health check
rdc machine health <machine> -o json

# Deploy a repository
rdc repo up <repo>@<machine> --yes

# Stop a repository
rdc repo down <repo>@<machine> --yes

# SSH terminal to machine
rdc term connect <machine> 
# SSH terminal to specific repo (sets DOCKER_HOST)
rdc term connect <repo>@<machine>

# Run command on machine
rdc term connect <machine> -c "command"

# File sync
rdc repo sync upload <repo>@<machine> --local ./local-path
rdc repo sync download <repo>@<machine> --local ./local-path

# List all available commands
rdc --help-all

### Architecture
- **Repository**: Isolated application deployment with its own Docker daemon at /var/run/rediacc/docker-<networkId>.sock, loopback IP range (127.0.x.x/26), and encrypted btrfs mount at /mnt/rediacc/mounts/<guid>/
- **Config**: CLI config at ~/.config/rediacc/rediacc.json. Auto-created on first use.
- One adapter: **local** (SSH-based)

### Rules
- Say "local adapter", never "local mode"
- S3 is a resource state backend, not a separate adapter
- Default config is created automatically on first use, do not tell users to run `rdc config init`
- Always use `--output json` when parsing output programmatically
- Always use `--yes` to skip confirmations in automated workflows
- Use `--dry-run` on destructive commands (repo delete, repo up, repo down) to preview before executing
```

## Özelleştirme

`<machine>` ve `<repo>` ifadelerini gerçek makine ve depo adlarınızla değiştirin. Mevcut depoları ad-GUID eşlemesiyle listelemek için `rdc repo list` komutunu çalıştırın.

### Kurulumunuzu Keşfetme

```bash
# List configured machines
rdc machine status <machine-name>

# List repositories with GUIDs
rdc repo list

# Check what commands are available
rdc --help-all
```

## Ajan Başına Kurulum

- **Claude Code**: Proje kök dizininize `CLAUDE.md` olarak kaydedin
- **Cursor**: Proje kök dizininize `.cursorrules` olarak kaydedin
- **Cline**: Cline sistem komutunuza veya proje talimatlarınıza ekleyin
- **Windsurf**: Proje kök dizininize `.windsurfrules` olarak kaydedin
