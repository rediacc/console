---
title: Modelo de AGENTS.md para Assistentes de IA
description: Modelo de copiar e colar para configurar o Claude Code, Cursor e outros assistentes de codificação com IA para trabalhar com a infraestrutura Rediacc.
category: Reference
order: 50
language: pt
sourceHash: "1edff3471ded906d"
sourceCommit: "23543669cd22bce3f14d69a0886bac8a12061412"
---

O problema é este: os assistentes de codificação com IA (Claude Code, Cursor, Cline, Windsurf) continuam a inventar flags do `rdc` que não existem, e não conseguem saber qual o nome de repositório Rediacc que mapeia para qual GUID sem perguntar todas as vezes. Este modelo resolve isso. Cole o bloco abaixo no seu `CLAUDE.md`, `.cursorrules` ou em qualquer ficheiro de configuração de agente que a sua ferramenta utilize.

## Modelo

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

## Personalização

Substitua `<machine>` e `<repo>` pelos nomes reais da sua máquina e repositório. Execute `rdc repo list` para listar os repositórios disponíveis com o mapeamento nome-para-GUID.

### Descobrir a Sua Configuração

```bash
# Listar máquinas configuradas
rdc machine status <machine-name>

# Listar repositórios com GUIDs
rdc repo list

# Verificar os comandos disponíveis
rdc --help-all
```

## Configuração por Agente

- **Claude Code**: Guardar como `CLAUDE.md` na raiz do projeto
- **Cursor**: Guardar como `.cursorrules` na raiz do projeto
- **Cline**: Adicionar ao prompt de sistema ou instruções de projeto do Cline
- **Windsurf**: Guardar como `.windsurfrules` na raiz do projeto
