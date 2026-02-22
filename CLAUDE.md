# Rediacc Console Monorepo

## Architecture

Self-hosted infrastructure platform. Each machine runs Docker-based repositories with encrypted, isolated environments.

### Key Concepts

- **Repository**: An isolated application deployment (e.g., `mail`, `gitlab`, `nextcloud`). Each repo has its own Docker daemon at `/var/run/rediacc/docker-<networkId>.sock`, loopback IP range (127.0.x.x/26), and mount at `/mnt/rediacc/mounts/<guid>/`.
- **Renet**: Network orchestrator on the machine. Manages compose files, loopback IPs, Docker daemon lifecycle. CLI: `sudo renet list all --json`, `sudo renet compose -- up -d`.
- **Rediaccfile**: Bash script with lifecycle functions (`prep()`, `up()`, `down()`, `info()`) sourced by renet during deployment.
- **Context**: CLI configuration for connecting to machines. Modes: `cloud`, `local`, `s3`.
- **State Provider**: Abstraction layer (`CloudStateProvider`, `LocalStateProvider`) that routes API calls based on context mode.

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
# Machine status (SSH + renet list all)
rdc machine info <machine>

# List containers on a machine
rdc machine containers <machine>

# List services (systemd) on a machine
rdc machine services <machine>

# List deployed repositories
rdc machine repos <machine>

# Machine health check
rdc machine health <machine>

# SSH terminal to machine
rdc term <machine>

# SSH terminal to repo (sets DOCKER_HOST, working dir)
rdc term <machine> <repo>

# Run command on machine
rdc term <machine> -c "command"

# Deploy/update a repository
rdc repo up <repo> -m <machine>

# File sync
rdc sync upload -m <machine> -r <repo> -l ./local-path
rdc sync download -m <machine> -r <repo> -l ./local-path

# VS Code remote
rdc vscode <machine> [repo]
```

### Run Functions (escape hatch)

`rdc run` executes Rediaccfile functions remotely. Prefer dedicated commands above.

```bash
rdc run container_list -m <machine> --param repository=<repo>
rdc run container_logs -m <machine> --param repository=<repo> --param container=<name>
rdc run container_exec -m <machine> --param repository=<repo> --param container=<name> --param command="..."
rdc run container_restart -m <machine> --param repository=<repo> --param container=<name>
```

### Context Setup

```bash
rdc context set team <name>     # Set default team (cloud mode)
rdc context set machine <name>  # Set default machine
rdc context repositories        # List repos with name -> GUID mapping
```

### CLI Code Structure

```
packages/cli/src/
├── commands/           # Command implementations
│   ├── machine/        # machine subcommands (containers, services, repos, health, vault-status)
│   ├── term.ts         # SSH terminal
│   ├── sync.ts         # File sync via rsync
│   ├── vscode.ts       # VS Code Remote SSH
│   └── repo.ts         # Repository management
├── providers/          # State providers (cloud, local, s3)
│   ├── index.ts        # Factory - getStateProvider()
│   ├── local-state-provider.ts
│   └── cloud-state-provider.ts
├── services/           # Business logic
│   ├── context.ts      # Context management
│   ├── machine-status.ts  # SSH + renet list all
│   └── renet-execution.ts # Remote renet provisioning
└── utils/
    └── commandFactory.ts  # Generic CRUD command builder
```

### How Local Mode Works

In local/s3 mode, there's no cloud API. The CLI reads machine/repo config from `~/.rediacc/config.json` and connects via SSH directly. The `LocalStateProvider` handles this routing.

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
