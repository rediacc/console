# Rediacc Console Monorepo

## Worktree Warning

**CRITICAL: This repo uses git worktrees.** Your working directory (from `pwd`) is the ONLY correct project root. NEVER use paths from other CLAUDE.md files that may appear in the system context — those belong to the main worktree and are a different checkout. All commands (`./run.sh`, `npx tsx`, file paths) MUST use the current working directory, not `/home/muhammed/monorepo/console/`.

## Architecture

Self-hosted infrastructure platform. Each machine runs Docker-based repositories with encrypted, isolated environments.

### Key Concepts

- **Repository**: An isolated application deployment (e.g., `mail`, `gitlab`, `nextcloud`). Each repo has its own Docker daemon at `/var/run/rediacc/docker-<networkId>.sock`, loopback IP range (127.0.x.x/26), and mount at `/mnt/rediacc/mounts/<guid>/`.
- **Renet**: Network orchestrator on the machine. Manages compose files, loopback IPs, Docker daemon lifecycle. CLI: `sudo renet list all --json`, `sudo renet compose -- up -d`.
- **Rediaccfile**: Bash script with lifecycle functions (`up()`, `down()`, `info()`) sourced by renet during deployment.
- **Config**: CLI configuration file for connecting to machines. Each config is a flat JSON file (~/.config/rediacc/rediacc.json by default) with a unique ID and version number. Adapter auto-detected: local (default) or cloud (experimental, when apiUrl+token present). Multiple named configs supported (e.g., production.json, staging.json).
- **Store**: External sync backend for config files. Supports S3, local file, Bitwarden, and Git. Credentials stored in ~/.config/rediacc/.credentials.json.
- **State Provider**: Abstraction layer (`CloudStateProvider`, `LocalStateProvider`) that routes API calls based on adapter detection.

### Packages

| Package | Description |
|---------|-------------|
| `packages/cli/` | `rdc` CLI tool (Commander.js) |
| `packages/web/` | Console web application |
| `packages/www/` | Marketing website (Astro) |
| `packages/desktop/` | Electron desktop app |
| `packages/shared/` | Shared types, config, services |
| `packages/shared-desktop/` | Shared SSH, SFTP, sync utilities |

## CLI (`packages/cli/`)

### Common Commands

```bash
# Full machine status (SSH + renet list all)
rdc machine query <machine>

# Filter by section
rdc machine query <machine> --system
rdc machine query <machine> --containers
rdc machine query <machine> --services
rdc machine query <machine> --repositories
rdc machine query <machine> --network
rdc machine query <machine> --block-devices

# SSH terminal to machine
rdc term <machine>

# SSH terminal to repo (sets DOCKER_HOST, working dir)
rdc term <machine> <repo>

# Run command on machine
rdc term <machine> -c "command"

# Deploy/update a repository
rdc repo up <repo> -m <machine>

# File sync
rdc repo sync upload -m <machine> -r <repo> -l ./local-path
rdc repo sync download -m <machine> -r <repo> -l ./local-path

# VS Code remote
rdc vscode <machine> [repo]
```

### Run Functions (escape hatch, debugging only)

`rdc run` executes Rediaccfile functions remotely. These are for debugging only — prefer dedicated commands above.

```bash
rdc run container_list -m <machine> --param repository=<repo>
rdc run container_logs -m <machine> --param repository=<repo> --param container=<name>
rdc run container_exec -m <machine> --param repository=<repo> --param container=<name> --param command="..."
rdc run container_restart -m <machine> --param repository=<repo> --param container=<name>
```

### Config Setup

```bash
# Default config (~/.config/rediacc/rediacc.json) is created automatically on first use
rdc config init production         # Create named config
rdc config repository list         # List repos with name -> GUID mapping
rdc --config production machine query prod-1  # Use specific config
```

### CLI Code Structure

```
packages/cli/src/
├── commands/           # Command implementations
│   ├── machine/        # machine subcommands (query with --system/--containers/--repositories/--services filters, vault-status)
│   ├── config.ts        # Config management (replaces context)
│   ├── store.ts         # Store sync management
│   ├── term.ts          # SSH terminal
│   ├── sync.ts          # File sync via rsync
│   ├── vscode.ts        # VS Code Remote SSH
│   └── repo.ts          # Repository management
├── providers/          # State providers (cloud, local, s3)
│   ├── index.ts        # Factory - getStateProvider()
│   ├── local-state-provider.ts
│   └── cloud-state-provider.ts
├── services/           # Business logic
│   ├── config-base.ts      # Config service base
│   ├── config-resources.ts # Config resource CRUD
│   ├── machine-status.ts   # SSH + renet list all
│   └── renet-execution.ts  # Remote renet provisioning
└── utils/
    └── commandFactory.ts  # Generic CRUD command builder
```

### How Local Adapter Works

When a config has no cloud credentials (apiUrl + token), the local adapter is used. The CLI reads machine/repo config from `~/.config/rediacc/rediacc.json` (or other named config file) and connects via SSH directly. If `config.s3` is populated, S3StateService is used for remote resource state; otherwise LocalResourceState reads from the config file directly.

## Terminology

When writing documentation, help text, error messages, or code comments, follow these rules:

- **No "modes"**: The system uses adapter-based detection, not modes. Say "local adapter" or "cloud adapter", never "local mode" or "s3 mode".
- **No "s3 mode"**: S3 is a resource state backend, not a separate mode. A config with `s3` field populated uses S3 for state — it's still the local adapter.
- **Two adapters only**: `local` (default) and `cloud` (experimental, when `apiUrl` + `token` are present).
- **Config auto-creation**: Default config is created automatically on first use. Don't tell users to run `rdc config init` for the default config. `config init <name>` is for named configs only.
- **Keep docs concise**: No verbose explanations or workarounds for error messages. Document what the command does, not how to work around issues.

## Build & Test

**This monorepo uses npm, not pnpm.**

```bash
# Install dependencies
npm install

# Build shared package (required before www or cli)
cd packages/shared && npm run build

# Type check
npx tsc --noEmit --project packages/cli/tsconfig.json

# Run tests
cd packages/cli && npm test

# Build website
cd packages/www && npm run build

# Dev server (website)
cd packages/www && npm run dev
```

## Quality Gates (`npm run ci`)

`npm run ci` runs 23 checks that mirror CI. Run locally before pushing to catch issues early. The checks cover: version consistency, dependency freshness, ESLint, biome formatting, i18n completeness, TypeScript types, unit tests, security audit, shell linting, Go lint (renet), E2E coverage, and more.

### Quick fixes for common failures

| Check | Fix |
|-------|-----|
| `check:deps` | `npx tsx scripts/check-deps.ts --upgrade` |
| `check:format` | `npx biome format --write packages/ private/account/` |
| `check:i18n` | `npm run i18n:generate-hashes && npm run i18n:sync`, then translate missing keys |
| `check:ci-renet` | `cd private/renet && go fmt ./...`, then fix golangci-lint issues |
| `lint` / `check:lint` | Fix ESLint errors properly (never suppress with comments) |
| `lint:unused` | Add to `ignoreDependencies` in `knip.json` if it's a transitive/runtime dep |
| `check:ci-e2e-coverage` | Add test stubs for new bridge functions in `packages/cli/tests/tests/08-e2e/` |
| `check:ci-renet` (types) | `private/renet/bin/renet bridge generate-types --output packages/shared/src/queue-vault/data --version dev` |

### CI fix cycle

When fixing CI failures, follow this loop:

1. **Run locally first**: Run `npm run ci` sub-commands locally before pushing to avoid costly CI round-trips. Use parallel sub-agents for independent checks.
2. **Push and watch**: After pushing, watch CI with `gh run watch <id> --repo rediacc/console --exit-status` in the background.
3. **Fix on notification**: When the background watch completes, check for failures with `gh run view <id> --json jobs --jq '.jobs[] | select(.conclusion == "failure") | {name}'`.
4. **Fix, commit, push, repeat**: Fix the issue, commit, push, and watch again. Continue until green.

### CI watchdog and auto-retry

The CI has a watchdog (`watchdog-monitor.cjs`) and cancellation script (`cancel-older-runs.sh`) that manage run lifecycle:

- **New push → old runs cancelled**: `cancel-older-runs.sh` force-cancels all older in-progress runs on the same branch. **Never re-run a cancelled run** — cancelled means superseded.
- **Job failure (attempt 1)**: Watchdog auto-retries only the failed jobs via `rerun-failed.yml`.
- **Job failure (attempt 2+)**: Watchdog force-cancels the entire run — no infinite retry loops.
- **Quality / Review Gate failures**: Never auto-retry. Fail immediately and force-cancel.

**PR labels** to control behavior:

| Label | Effect |
|-------|--------|
| `no-cancel-push` | Don't cancel older runs on new pushes |
| `no-cancel-failure` | Don't cancel run when jobs fail |
| `no-auto-retry` | Skip retry, force-cancel immediately on failure |

Re-running (`gh run rerun`) is only appropriate for transient errors (network, flaky infra) on failed — not cancelled — runs.

### Submodule commit order

Always commit submodules before the parent repo:

```bash
# 1. Commit in submodule(s)
cd private/renet && git add -A && git commit -m "fix: ..." && git push origin <branch>
cd private/account && git add -A && git commit -m "fix: ..." && git push origin HEAD

# 2. Commit in parent (updates submodule pointer)
cd /path/to/console && git add -A && git commit -m "fix: ..." && git push
```

### Secrets in CI vs CD

- **CI workflows** (`ci.yml`, `ci-quality.yml`, `ct-tests.yml`, `standalone-run.yml`): Use **generated throwaway keys** via `ci-env.sh`. Never pass production secrets.
- **CD workflows** (`cd-v2.yml`): Use **real org secrets** from GitHub for production deployment.
- Generated secrets are masked via `::add-mask::` in `ci-env.sh`.
