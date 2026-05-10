---
title: Modelo de AGENTS.md para Assistentes de IA
description: Modelo de copiar e colar para configurar o Claude Code, Cursor e outros assistentes de codificação com IA para trabalhar com a infraestrutura Rediacc.
category: Reference
order: 50
language: pt
---

Use este modelo para configurar assistentes de codificação com IA (Claude Code, Cursor, Cline, Windsurf) para a gestão autónoma da infraestrutura Rediacc. Copie o bloco abaixo para o ficheiro `CLAUDE.md`, `.cursorrules` ou equivalente de configuração de agente do seu projeto.

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
rdc machine query --name <machine> -o json

# List containers on a machine
rdc machine containers --name <machine> -o json

# Machine health check
rdc machine health --name <machine> -o json

# Deploy a repository
rdc repo up --name <repo> -m <machine> --yes

# Stop a repository
rdc repo down --name <repo> -m <machine> --yes

# SSH terminal to machine
rdc term connect -m <machine>

# SSH terminal to specific repo (sets DOCKER_HOST)
rdc term connect -m <machine> -r <repo>

# Run command on machine
rdc term connect -m <machine> -c "command"

# File sync
rdc repo sync upload -m <machine> -r <repo> --local ./local-path
rdc repo sync download -m <machine> -r <repo> --local ./local-path

# List all available commands with schemas
rdc agent capabilities

# Show schema for a specific command
rdc agent schema --command "machine query"

### Architecture
- **Repository**: Isolated application deployment with its own Docker daemon at /var/run/rediacc/docker-<networkId>.sock, loopback IP range (127.0.x.x/26), and encrypted btrfs mount at /mnt/rediacc/mounts/<guid>/
- **Config**: CLI config at ~/.config/rediacc/rediacc.json. Auto-created on first use.
- Two adapters: **local** (default, SSH-based) and **cloud** (experimental, API-based)

### Rules
- Use "local adapter" / "cloud adapter", never say "modes"
- S3 is a resource state backend, not a separate adapter
- Default config is created automatically on first use, do not tell users to run `rdc config init`
- Always use `--output json` when parsing output programmatically
- Always use `--yes` to skip confirmations in automated workflows
- Use `--dry-run` on destructive commands (repo delete, repo up, repo down) to preview before executing
```

## Personalização

Substitua `<machine>` e `<repo>` pelos nomes reais da sua máquina e repositório. Execute `rdc config repository list` para listar os repositórios disponíveis com o mapeamento nome-para-GUID.

### Descobrir a Sua Configuração

```bash
# Listar máquinas configuradas
rdc machine query --name <machine-name>

# Listar repositórios com GUIDs
rdc config repository list

# Verificar os comandos disponíveis
rdc agent capabilities
```

## Configuração por Agente

- **Claude Code**: Guardar como `CLAUDE.md` na raiz do projeto
- **Cursor**: Guardar como `.cursorrules` na raiz do projeto
- **Cline**: Adicionar ao prompt de sistema ou instruções de projeto do Cline
- **Windsurf**: Guardar como `.windsurfrules` na raiz do projeto
