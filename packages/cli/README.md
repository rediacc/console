# @rediacc/cli

Command-line interface for Rediacc operations. Manage infrastructure, queue tasks, sync files, and administer storage — via the Rediacc cloud API or self-hosted S3-compatible storage.

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

### Cloud Mode

```bash
# Create a context and log in
rdc config create production --api-url https://www.rediacc.com/api
rdc auth login --email you@example.com

# Set defaults
rdc config set team my-team
rdc config set region eu-central

# Run a function
rdc run my-function -m my-machine --watch
```

### S3 Mode (Self-Hosted)

S3 mode stores all state (queue items, vault secrets) in any S3-compatible bucket (MinIO, RustFS, AWS S3, Cloudflare R2). Functions are executed locally via the `renet` binary over SSH. No cloud account required.

```bash
# Create an S3 context
rdc config create-s3 selfhosted \
  --endpoint https://s3.example.com \
  --bucket my-rediacc-bucket \
  --access-key-id AKID... \
  --secret-access-key SECRET... \
  --ssh-key ~/.ssh/id_ed25519 \
  --region auto

# Add machines
rdc config add-machine web-server --ip 192.168.1.10 --user deploy

# Run a function
rdc run my-function -m web-server
```

## Master Password

The master password is an **optional**, **client-side-only** encryption layer. It is never transmitted to any server.

### What It Encrypts

When enabled, the master password encrypts sensitive data at rest using AES-256-GCM with PBKDF2 key derivation (100,000 iterations, SHA-256):

- **S3 mode:** S3 secret access key stored in context config, and vault contents stored as `.json.enc` files in the bucket
- **Cloud mode:** Vault secrets before they leave your machine

### When Disabled

If you skip the master password (press Enter or omit `--master-password`):

- S3 secret access key is stored in plaintext in the context config
- Vault data is stored as plain JSON in S3
- Data is still protected by S3 bucket ACLs (S3 mode) or cloud API authentication (cloud mode)

### Usage

```bash
# S3 mode — with encryption
rdc config create-s3 myctx ... --master-password <pw>

# S3 mode — without encryption (leave empty when prompted, or omit the flag)
rdc config create-s3 myctx ...

# Cloud mode
rdc auth login --master-password <pw>
```

For non-interactive usage (CI/CD), set the `REDIACC_MASTER_PASSWORD` environment variable.

## Commands

### All Modes

| Command | Description |
|---------|-------------|
| `context` | Manage named contexts (`create`, `create-s3`, `create-local`, `show`, `list`, `set`, `delete`, `add-machine`, `remove-machine`, `machines`, ...) |
| `queue` | Task lifecycle (`create`, `list`, `trace`, `cancel`, `retry`, `delete`) |
| `machine` | Machine CRUD, vault management, bridge assignment |
| `storage` | Storage system management |
| `repository` | Repository management |
| `sync` | File synchronization via rsync (`upload`, `download`, `status`) |
| `doctor` | Check environment, configuration, and connectivity |
| `update` | Self-update the CLI binary |

### Shortcuts

| Command | Description |
|---------|-------------|
| `rdc run <function>` | Execute a function |
| `rdc trace <taskId>` | Trace a task's progress |
| `rdc cancel <taskId>` | Cancel a queued task |
| `rdc retry <taskId>` | Retry a failed task |

### Cloud-Only

These commands are unavailable in S3/local mode:

| Command | Description |
|---------|-------------|
| `auth` | Login, logout, session management, 2FA |
| `team` | Team CRUD |
| `bridge` | Bridge management |
| `region` | Region listing |
| `organization` | Organization management |
| `user` | User management |
| `permission` | Permission management |
| `audit` | Audit log queries |
| `ceph` | Ceph storage operations |

### Global Options

```
-o, --output <format>    Output format: table, json, yaml, csv (default: table)
--context <name>         Use a specific named context
-l, --lang <code>        Language: en|de|es|fr|ja|ar|ru|tr|zh
-V, --version            Show version
-h, --help               Show help
```

## Contexts

Configuration is stored per-context in `~/.config/rediacc/` (XDG-compatible). Each context has a name, mode (`cloud`, `s3`, or `local`), and its own credentials/defaults.

The default context is `"default"`. Override with `--context <name>` or set a different default via the config.

```bash
rdc config list                  # List all contexts
rdc config show                  # Show current context details
rdc --context staging queue list  # Use a specific context
```

## Testing

```bash
# Unit tests (Vitest)
npm run test:unit

# S3 integration tests (requires S3_TEST_* env vars)
npm run test:unit:s3

# E2E tests (Playwright)
npm run test                # All projects
npm run test:core           # Core commands
npm run test:s3             # S3 mode
npm run test:e2e            # End-to-end
npm run test:security       # Security
npm run test:operations     # Operations
npm run test:resources      # Resources
npm run test:errors         # Error handling
npm run test:edition        # Edition checks
npm run test:ceph           # Ceph commands
npm run test:vscode         # VS Code integration

# View report
npm run test:report
```

### S3 Integration Test Environment

Set these environment variables to run S3 integration tests:

```bash
export S3_TEST_ENDPOINT=http://localhost:9000
export S3_TEST_ACCESS_KEY=minioadmin
export S3_TEST_SECRET_KEY=minioadmin
export S3_TEST_BUCKET=rediacc-test
```

## Development

```bash
npm install                    # Install dependencies
npm run dev -- <command>       # Run in dev mode (tsx)
npm run build                  # TypeScript compilation
npm run build:bundle           # Single-file CJS bundle (esbuild)
npm run build:sea              # Single Executable Application
npm run lint                   # ESLint
npm run typecheck              # Type checking
npm run export:command-tree    # Export command tree for docs
```

### Project Structure

```
src/
  cli.ts              # Command registration and global options
  commands/           # One file per command group
  providers/          # State provider abstraction (cloud, s3, local)
  services/           # Business logic (API, auth, context, S3 client, vault)
  adapters/           # Platform adapters (crypto)
  i18n/               # Internationalization (9 languages)
  types/              # TypeScript type definitions
  utils/              # Shared utilities (formatting, errors, spinners)
tests/
  tests/              # Playwright E2E tests (organized by project)
  src/utils/          # Test utilities (CliTestRunner, helpers)
```
