# @rediacc/cli

Command-line interface for Rediacc operations. Manage machines, repositories, storages, and deployments — locally via SSH or through the encrypted config store.

| | |
|---|---|
| Binary | `rdc` |
| Node | `>=22.0.0` |
| License | MIT |

## Installation

```bash
# npm (global)
npm install -g @rediacc/cli

# Homebrew (macOS/Linux)
brew install rediacc/tap/rediacc-cli

# Verify
rdc --version
rdc doctor
```

The CLI also supports self-update via `rdc update`.

## Quick Start

```bash
# Initialise a config
rdc config init --name production --ssh-key ~/.ssh/id_ed25519

# Add a machine
rdc config machine add --name web-1 --ip 10.0.0.1 --user deploy

# Deploy a repository
rdc repo fork --parent app --tag prod -m web-1
rdc repo up --name app:prod -m web-1

# Inspect config (redacted by default; --reveal on an interactive TTY)
rdc config show

# Pointer-addressed field editing with knowledge-gate
rdc config field set /credentials/cfDnsApiToken \
    --current "$OLD_TOKEN" --new "$NEW_TOKEN"

# Full editor with redacted JSONC projection (humans only)
rdc config edit
```

See the [canonical CLI reference](https://www.rediacc.com/en/docs/cli-application) for every subcommand's arguments and options, or run `rdc <command> --help` locally.

## AI agent safety

`rdc` detects AI coding assistants (Claude Code, Cursor, Gemini CLI, Copilot CLI) via environment signals and `/proc` ancestry, then applies a reduced permission set:

- Sensitive writes require the knowledge-gate (`--current <old>`)
- Interactive editor, `--reveal`, and direct machine SSH are refused unless the operator has set an ancestry-verified `REDIACC_ALLOW_CONFIG_EDIT` override
- Every mutation / refusal / `--reveal` grant is written to a hash-chained JSONL log at `~/.config/rediacc/audit.log.jsonl` — inspect with `rdc config audit {log, tail, verify}`

See the [AI Agent Safety & Guardrails](https://www.rediacc.com/en/docs/ai-agents-safety) doc for the full firewall matrix and worked examples.

## Command surface (abbreviated)

| Command group | Purpose |
|---|---|
| `config init` / `config show` / `config list` / `config delete` | Config file lifecycle |
| `config field {get,set,unset,rotate,list}` | Pointer-addressed CRUD on any config leaf (canonical mutation surface) |
| `config edit` | Humans-only editor with redacted JSONC projection + validation loop |
| `config audit {log,tail,verify}` | Hash-chained audit log inspection |
| `config machine {add,remove,list,setup,...}` | Typed wrappers for `resources.machines.*` |
| `config storage {add,remove,list}` | Typed wrappers for `resources.storages.*` |
| `config repository {add,remove,list,...}` | Typed wrappers for `resources.repositories.*` |
| `config backup-strategy {set,remove,list,...}` | Hot/cold backup schedules |
| `config remote {enable,disable,status,refresh}` | Link to the encrypted config store |
| `machine query` | Machine status (SSH + `renet list all`) |
| `repo up / down / fork / takeover / sync` | Repository deployment + sync |
| `term connect -m <machine> -r <repo>` | SSH into a sandboxed repo context |
| `vscode connect` | VS Code Remote-SSH helper |
| `doctor` | Environment diagnosis |
| `update` | Self-update |

## Config storage and encryption

Configs live at `~/.config/rediacc/` (XDG-compatible). The shape uses `schemaVersion: 2` and is bucketed under `resources.*`, `credentials.*`, `account.*`, `infra.*`, `encryption.*` — see the [architecture doc](https://www.rediacc.com/en/docs/architecture#configuration-structure) for the full schema.

Two encryption modes:

- **`encryption.mode === "plaintext"`** (default) — keys and secrets are stored as-is, protected by filesystem permissions (`0600`). Redaction still applies to every read-path in the CLI.
- **`encryption.mode === "master-password"`** — each sensitive field is individually AES-GCM-encrypted at rest. One master-password prompt per session caches the derived key; commands that don't touch secrets skip the prompt entirely.

For zero-knowledge server-side enforcement (per-field HMAC commitments, anti-downgrade), enable `config remote` to sync the config to the encrypted config store.

## Global options

```
-o, --output <format>    Output format: table, json, yaml, csv (default: table)
--config <name>          Use a specific named config (default: rediacc)
-l, --lang <code>        Language: en|de|es|fr|ja|ar|ru|tr|zh
-V, --version            Show version
-h, --help               Show help
```

## Testing

```bash
npm run test:unit                # Unit tests (Vitest)
npm run test                     # E2E tests (Playwright) — all projects
npm run test:report              # View HTML report
```

## Development

```bash
npm install                      # Install dependencies
npm run dev -- <command>         # Run in dev mode (tsx)
npm run build                    # TypeScript compilation
npm run build:bundle             # Single-file CJS bundle (esbuild)
npm run build:sea                # Single Executable Application
npm run lint                     # ESLint
npm run typecheck                # Type checking
npm run export:command-tree      # Export command tree for the doc generator
```

### Project layout

```
src/
  cli.ts              # Command registration and global options
  commands/           # One file per command group
    config/           # field.ts, edit.ts, audit.ts (canonical surface)
  schema/             # v2 Zod schema + JSON-Pointer walker + sensitivity registry
  services/           # Business logic (config-resources, mutation-gate, audit-log)
  adapters/           # Platform adapters (config-file-storage, remote-config-adapter, crypto)
  providers/          # State provider abstraction (local vs remote)
  i18n/               # Internationalization (9 languages)
  utils/              # Shared utilities (agent-guard, editor-launcher, errors, spinners)
tests/
  tests/              # Playwright E2E tests (organized by project)
```
