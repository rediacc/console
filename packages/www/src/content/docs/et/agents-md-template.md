---
title: AGENTS.md Mall AI-assistentidele
description: Kopeeritav mall Claude Code'i, Cursori ja teiste AI-koodiassistentide konfigureerimiseks Rediacc infrastruktuuriga töötamiseks.
category: Reference
order: 50
language: et
sourceHash: "468f701c500856c6"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

Siin on probleem: AI koodiassistendid (Claude Code, Cursor, Cline, Windsurf) leiutavad pidevalt `rdc` lippe, mida ei eksisteeri, ja nad ei suuda ilma iga kord küsimata öelda, milline Rediacc repositooriumi nimi vastab millisele GUID-ile. See mall lahendab selle. Kleebi alljärgnev plokk oma projekti `CLAUDE.md`-i, `.cursorrules`-i või millist agendi konfiguratsioonifaili su tööriist kasutab.

## Mall

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

## Kohandamine

Asendage `<machine>` ja `<repo>` oma tegelike masina ja repositooriumi nimedega. Käivitage `rdc config repository list`, et kuvada saadaolevad repositooriumid koos nende nime-GUID-i vastavusega.

### Oma seadistuse avastamine

```bash
# Seadistatud masinate loend
rdc machine query --name <machine-name>

# Repositooriumide loend GUID-idega
rdc config repository list

# Saadaolevate käskude kontrollimine
rdc agent capabilities
```

## Agendipõhine seadistus

- **Claude Code**: Salvestage projekti juurkaustas nimena `CLAUDE.md`
- **Cursor**: Salvestage projekti juurkaustas nimena `.cursorrules`
- **Cline**: Lisage oma Cline'i süsteemiviipasse või projekti juhistesse
- **Windsurf**: Salvestage projekti juurkaustas nimena `.windsurfrules`
