---
title: Modèle AGENTS.md pour les assistants IA
description: Modèle prêt à copier-coller pour configurer Claude Code, Cursor et d'autres assistants de programmation IA afin de gérer l'infrastructure Rediacc.
category: Reference
order: 50
language: fr
---

Utilisez ce modèle pour configurer les assistants de programmation IA (Claude Code, Cursor, Cline, Windsurf) pour la gestion autonome de l'infrastructure Rediacc. Copiez le bloc ci-dessous dans le fichier `CLAUDE.md`, `.cursorrules` ou le fichier de configuration d'agent équivalent de votre projet.

## Modèle

```markdown
# Rediacc Infrastructure

Self-hosted infrastructure platform. Each machine runs Docker-based repositories with encrypted, isolated environments.

## CLI Tool: rdc

Install: `curl -fsSL https://www.rediacc.com/install.sh | bash`

### Key Flags
- `--output json` (or `-o json`) — machine-readable JSON output
- `--yes` (or `-y`) — skip interactive confirmations
- `--quiet` (or `-q`) — suppress informational output
- `--fields name,status` — limit output fields
- Auto-JSON: when piped (non-TTY), output defaults to JSON automatically

### JSON Envelope
All JSON output uses a consistent envelope:
{"success": true, "command": "...", "data": ..., "errors": null, "warnings": [], "metrics": {"duration_ms": N}}

On error: {"success": false, "command": "...", "data": null, "errors": [{"code": "...", "message": "...", "retryable": false, "guidance": "..."}], ...}

### Common Operations

# Machine status
rdc machine info <machine> -o json

# List containers on a machine
rdc machine containers <machine> -o json

# Machine health check
rdc machine health <machine> -o json

# Deploy a repository
rdc repo up <repo> -m <machine> --yes

# Stop a repository
rdc repo down <repo> -m <machine> --yes

# SSH terminal to machine
rdc term <machine>

# SSH terminal to specific repo (sets DOCKER_HOST)
rdc term <machine> <repo>

# Run command on machine
rdc term <machine> -c "command"

# File sync
rdc sync upload -m <machine> -r <repo> -l ./local-path
rdc sync download -m <machine> -r <repo> -l ./local-path

# List all available commands with schemas
rdc agent capabilities

# Show schema for a specific command
rdc agent schema "machine info"

### Architecture
- **Repository**: Isolated application deployment with its own Docker daemon at /var/run/rediacc/docker-<networkId>.sock, loopback IP range (127.0.x.x/26), and encrypted btrfs mount at /mnt/rediacc/mounts/<guid>/
- **Config**: CLI config at ~/.config/rediacc/rediacc.json. Auto-created on first use.
- Two adapters: **local** (default, SSH-based) and **cloud** (experimental, API-based)

### Rules
- Use "local adapter" / "cloud adapter" — never say "modes"
- S3 is a resource state backend, not a separate adapter
- Default config is created automatically on first use — do not tell users to run `rdc config init`
- Always use `--output json` when parsing output programmatically
- Always use `--yes` to skip confirmations in automated workflows
- Use `--dry-run` on destructive commands (repo delete, repo up, repo down) to preview before executing
```

## Personnalisation

Remplacez `<machine>` et `<repo>` par les noms réels de votre machine et de votre dépôt. Exécutez `rdc config repositories` pour lister les dépôts disponibles avec leur correspondance nom-GUID.

### Découvrir votre configuration

```bash
# List configured machines
rdc machine info <machine-name>

# List repositories with GUIDs
rdc config repositories

# Check what commands are available
rdc agent capabilities
```

## Configuration par agent

- **Claude Code** : Enregistrez sous `CLAUDE.md` à la racine de votre projet
- **Cursor** : Enregistrez sous `.cursorrules` à la racine de votre projet
- **Cline** : Ajoutez aux instructions système ou projet dans Cline
- **Windsurf** : Enregistrez sous `.windsurfrules` à la racine de votre projet
