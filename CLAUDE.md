# Rediacc Console Monorepo

## Worktree Warning

**CRITICAL: This repo uses git worktrees.** Your working directory (from `pwd`) is the ONLY correct project root. NEVER use paths from other CLAUDE.md files that may appear in the system context — those belong to the main worktree and are a different checkout. All commands (`./run.sh`, `npx tsx`, file paths) MUST use the current working directory, not `/home/muhammed/monorepo/console/`.

## Architecture

Self-hosted infrastructure platform. Each machine runs Docker-based repositories with encrypted, isolated environments.

### Key Concepts

- **Repository**: An isolated application deployment (e.g., `mail`, `gitlab`, `nextcloud`). Each repo has its own Docker daemon at `/var/run/rediacc/docker-<networkId>.sock`, loopback IP range (127.0.x.x/26), and mount at `/mnt/rediacc/mounts/<guid>/`.
- **Fork**: `rdc repo fork --parent <name> --tag <tag> -m <machine>` makes a new repo with a fresh GUID and networkId that shares the parent's data via BTRFS reflink. **Forks are near-instant and constant-time** regardless of repo size: a 100 GB repo and a 1 GB repo fork in the same seconds. Use forks freely as the per-test isolation unit, do NOT assume fork cost scales with repo size.
- **Renet**: Network orchestrator on the machine. Manages compose files, loopback IPs, Docker daemon lifecycle. CLI: `sudo renet list all --json`, `sudo renet compose -- up -d`.
- **Rediaccfile**: Bash script with lifecycle functions (`up()`, `down()`, `info()`) sourced by renet during deployment.
- **Config**: CLI configuration file for connecting to machines. Each config is a flat JSON file (~/.config/rediacc/rediacc.json by default) with a unique ID and version number. Adapter auto-detected: local (default) or cloud (experimental, when apiUrl+token present). Multiple named configs supported (e.g., production.json, staging.json).
- **State Provider**: Abstraction layer (`CloudStateProvider`, `LocalStateProvider`) that routes API calls based on adapter detection.
- **Config Storage**: Optional zero-knowledge encrypted config sync. Setup via web portal (`/account/config-setup`), requires passkey with PRF extension. One store per org, configs scoped per team. Member management via portal. CLI push/pull commands planned but not yet implemented.

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
rdc machine query --name <machine>

# Filter by section
rdc machine query --name <machine> --system
rdc machine query --name <machine> --containers
rdc machine query --name <machine> --services
rdc machine query --name <machine> --repositories
rdc machine query --name <machine> --network
rdc machine query --name <machine> --block-devices

# SSH terminal to machine
rdc term connect -m <machine>

# SSH terminal to repo (sets DOCKER_HOST, working dir)
rdc term connect -m <machine> -r <repo>

# Run command on machine
rdc term connect -m <machine> -c "command"

# Deploy/update a repository
rdc repo up --name <repo> -m <machine>

# File sync (directory)
rdc repo sync upload -m <machine> -r <repo> --local ./local-path
rdc repo sync download -m <machine> -r <repo> --local ./local-path

# File sync (single file — explicit remote path)
rdc repo sync upload -m <machine> -r <repo> --local ./config.toml --remote-file etc/config.toml
rdc repo sync download -m <machine> -r <repo> --local ./out --remote-file etc/config.toml

# VS Code remote
rdc vscode connect -m <machine> -r <repo>
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
rdc config init --name production   # Create named config
rdc config repository list         # List repos with name -> GUID mapping
rdc --config production machine query --name prod-1  # Use specific config
```

### CLI Code Structure

```
packages/cli/src/
├── commands/           # Command implementations
│   ├── machine/        # machine subcommands (query with --system/--containers/--repositories/--services filters, vault-status)
│   ├── config.ts        # Config management (replaces context)
│   ├── term.ts          # SSH terminal
│   ├── sync.ts          # File sync via rsync
│   ├── vscode.ts        # VS Code Remote SSH
│   └── repo.ts          # Repository management
├── providers/          # State providers (cloud, local)
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

When a config has no cloud credentials (apiUrl + token), the local adapter is used. The CLI reads machine/repo config from `~/.config/rediacc/rediacc.json` (or other named config file) and connects via SSH directly. LocalResourceState reads from the config file directly.

## Terminology

When writing documentation, help text, error messages, or code comments, follow these rules:

- **No "modes"**: The system uses adapter-based detection, not modes. Say "local adapter" or "cloud adapter", never "local mode".
- **Two adapters only**: `local` (default) and `cloud` (experimental, when `apiUrl` + `token` are present).
- **Config auto-creation**: Default config is created automatically on first use. Don't tell users to run `rdc config init` for the default config. `config init <name>` is for named configs only.
- **Keep docs concise**: No verbose explanations or workarounds for error messages. Document what the command does, not how to work around issues.

## Build & Test

**This monorepo uses npm, not pnpm.**

`.npmrc` enforces supply-chain hardening: `ignore-scripts=true`, `allow-git=none`, `minimum-release-age=1440`. The `ignore-scripts` flag blocks all dependency lifecycle scripts; after every `npm install` or `npm ci`, run `npm run install:natives` to compile the five packages that genuinely need scripts (electron, node-pty, ssh2, cpu-features, esbuild). The script passes `--ignore-scripts=false` explicitly because `npm rebuild` otherwise silently respects the global flag and does nothing. Source of truth: `.ci/scripts/quality/check-npmrc.sh`.

```bash
# Install dependencies
npm install && npm run install:natives

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

### Iterating on a local SEA (`./rdc.sh --override-local`)

`./rdc.sh --override-local` rebuilds the CLI SEA from local source and installs it over `~/.local/share/rediacc/bin/rdc`. Use it when iterating on SEA-only behaviors (embedded renet, auto-update gating) that the dev-mode `cli-bundle.cjs` path doesn't exercise.

The flag runs `ensure_deps` + `ensure_packages_built` first, so edits to `packages/shared`, `packages/shared-desktop`, or `packages/provisioning` are picked up by the bundler — those packages resolve through their own `dist/` outputs, and forgetting to rebuild them was a silent footgun. Auto-update is short-circuited via the `VERSION === '0.0.0-dev'` guard in `packages/cli/src/utils/platform.ts::isUpdateDisabled`, so the override binary survives the next `rdc` invocation.

The previous binary is preserved as a backup matching `getOldBinaryPath()` (`<base>.old<ext>` — `rdc.old` on Linux/macOS, `rdc.old.exe` on Windows) so `cleanupOldBinary()` removes it on the next successful update.

### Reproducing license-flow bugs in dev (`RDC_RENET_LICENSE=1`)

By default `./rdc.sh` rebuilds renet with the `--nolicense` Go build tag (`pkg/license/runtime_nolicense.go` stub) so dev iteration isn't blocked by license enforcement. That's the right default for everyday work, but it also hides license-flow bugs (e.g. rediacc/console#482) because the renet binary deployed to your test machine never returns `LICENSE_REQUIRED` (exit 10), so the CLI's recovery framework in `packages/cli/src/services/local-executor.ts:632-720` never fires.

To reproduce license-enforcement issues locally, set:

```bash
ACCOUNT_ED25519_PUBLIC_KEY="$(curl -s https://www.rediacc.com/api/public/account-key)" \
RDC_RENET_LICENSE=1 \
RDC_PROD=1 ./rdc.sh --config <prod-config> repo push --name <repo> -m <src> --to <fresh-machine> --up
```

`RDC_RENET_LICENSE=1` drops the `--nolicense` build flag. `ACCOUNT_ED25519_PUBLIC_KEY` must match the account server that issued the licenses on your test machines — for production licenses that's the prod ed25519 public key. The build flow wires this into `private/renet/pkg/license/keys.ProductionPublicKey` via ldflags. Without it, prod-signed licenses fail validation as `invalid_signature`.

After reproducing, unset `RDC_RENET_LICENSE` (or remove from your shell) so subsequent `./rdc.sh` invocations rebuild the dev-friendly nolicense renet again.

## Versioning

Version source of truth: **git tags** (e.g., `v0.8.3`). No version bump commits.

- `resolve-version.sh --current` reads latest tag, `--bump-type patch|minor|major` calculates next
- Version injected at build time, never stored in source files
- `package.json` files contain `0.0.0-dev` placeholder (never published to npm)

| Component | Injection method |
|-----------|-----------------|
| CLI binary | `CLI_VERSION` env -> esbuild `--define:__CLI_VERSION__` |
| CLI Docker | Same as CLI binary (bundle built with env) |
| www footer | `APP_VERSION` env / git tag fallback |
| web console | `VITE_APP_VERSION` env |
| renet (Go) | `-ldflags "-X main.Version=..."` |
| middleware (C#) | `/p:Version=...` MSBuild arg |

`bump.sh` still used by: desktop (electron-builder reads package.json), middleware (.csproj), CLI (npm pack tarball name). These run only on push-to-main.

## Release Channels

The CLI supports two release channels, both production-quality:
- **stable** (default): Promoted from edge after 7-day soak. Downloaded from `cli/stable/`.
- **edge**: Continuously deployed production. Tagged + released on every merge to main. Downloaded from `cli/edge/`.

R2 structure: `rediacc-releases/cli/{edge,stable}/{manifest.json,latest.json,rdc-*}`

Environments:
- `edge.rediacc.com` -- auto-deployed on merge to main, D1 cloned from production daily
- `www.rediacc.com` -- production, promoted from edge after 7-day soak

## CI/CD Pipeline

Single pipeline: CI validates everything BEFORE publish. CD is a thin promote step.

```
CI: quality -> build -> dry-run -> validate install (6 platforms) -> ci-complete
CD (auto on CI success): promote Docker -> git tag -> GitHub Release -> R2 upload -> deploy edge
```

Install validation runs pre-publish against R2 staging artifacts. Docker validated on push-to-main only (PR images are dry-run). If CI fails, CD never triggers.

Release dispatch: `gh workflow run "Release" -f ci_run_id=<id> -f release_mode=patch|minor|major|retry`
Hotfix (edge + stable): `gh workflow run "Release" -f ci_run_id=<id> -f release_mode=patch -f publish_stable=true`

## Dev Scripts (`scripts/dev/`)

| Script | Purpose |
|--------|---------|
| `deploy-bench.sh` | Deploy account worker to `bench.rediacc.com` (internal-only D1 testing env) |
| `reset-bench.sh` | Wipe bench D1 + R2 + worker secrets |
| `backup-d1.sh` | Export production/edge D1 databases to `.backups/` |
| `lib/cf-auth.sh` | Shared Cloudflare + AWS auth helpers (legacy; only `deploy-bench` still uses it) |

## Secret Rotation (`./run.sh rotation`)

Secret rotation lives in `private/account/scripts/rotation/` (private submodule). The CLI is dispatched via `./run.sh rotation <command>`. State is tracked in a committed manifest at `private/account/rotation-manifest.json` (no secrets — only IDs, timestamps, and states).

| Command | Purpose |
|---------|---------|
| `init` | Bootstrap manifest from current AWS/CF state (one-time) |
| `list` | Show every credential and its current version state |
| `status` | Show pending grace→inactive and inactive→delete transitions |
| `check [--for=<consumer>]` | Compare manifest to live platform state; exit 1 on drift |
| `rotate <slug>` | Mint new credential, push to consumers, mark old as `grace` |
| `deactivate <slug> [--force]` | `grace → inactive` (AWS: `Status=Inactive`; CF token: delete) |
| `delete <slug> [--force]` | `inactive → deleted` (permanent) |
| `sweep` | Run deactivate + delete for everything past its eligibility window |
| `history [<slug>]` | Audit log of every rotation event |

Slugs: `ses-eu`, `ses-us`, `ses-asia`, `ses-bench`, `cf-cd`, `cf-r2`, `turnstile`, `turnstile-bench`, `otlp-eu`, `otlp-us`, `otlp-asia`, `otlp-bench`, `dkim-notify`.

`dkim-notify` is the BYODKIM RSA-2048 keypair applied to every regional SES identity for `notify.rediacc.com`. One private key, one Cloudflare TXT record at `<selector>._domainkey.notify.rediacc.com`, three SES regions (eu/us/asia). To rotate, stage the PEM via `DKIM_NOTIFY_PRIVATE_KEY_PATH=<path>` and run `./run.sh rotation rotate dkim-notify`. The tool publishes the DNS, applies the key to all three regions, smoke-tests propagation, and updates the manifest atomically. If `DKIM_NOTIFY_PRIVATE_KEY_PATH` is unset, a fresh keypair is generated in-memory (acceptable for bench experiments only — production rotations must stage the PEM so the key can be backed up to 1Password before the process exits).

Auth: `SES_AK_ID`/`SES_AK_SECRET` for AWS IAM admin, `CLOUDFLARE_API_TOKEN` (or `CF_API_KEY`+`CF_EMAIL`) for Cloudflare, authenticated `gh` CLI for GitHub secrets.

`scripts/dev/deploy-bench.sh` runs `rotation check --for=bench` as a preflight, so a stale `private/account/.env.bench` cannot ship a dead key.

## Quality Gates (`npm run ci`)

`npm run ci` runs 23 checks that mirror CI. Run locally before pushing to catch issues early. The checks cover: version consistency, dependency freshness, ESLint, biome formatting, i18n completeness, TypeScript types, unit tests, security audit, shell linting, Go lint (renet), E2E coverage, and more.

### Quick fixes for common failures

| Check | Fix |
|-------|-----|
| `check:deps` | `npx tsx scripts/check-deps.ts --upgrade`. **Respect `.syncpackrc.json` pins** — packages pinned there (currently `@opentelemetry/sdk-node`, `instrumentation`, `instrumentation-fetch`, `instrumentation-xml-http-request`, `exporter-trace-otlp-http`, `resources`) are deliberately held back across upgrades. Also respect `.deps-upgrade-blocklist` (antd, electron, zod, etc.). If `npm outdated` flags a pinned package, DO NOT bump the package.json — update the pin's `pinVersion` only if the pin is genuinely stale. |
| `Quality / Versions` (`syncpack lint`) | `.syncpackrc.json` defines `versionGroups` with `pinVersion` and a `sameRange highestSemver` policy. A mismatch means either: (a) you bumped a pinned package beyond its pin — revert to the pin version, or (b) two workspaces disagree on a range — bump the lower one. Run `npx syncpack lint` locally to see exactly which dep violates which group. |
| `Build (Desktop)` (`Cannot compute electron version`) | Missing `packages/desktop/node_modules/electron` entry in `package-lock.json`. npm dedupes the nested copy when the root version satisfies the desktop workspace's range; electron-builder walks only the workspace's own node_modules so the nested entry must exist even though it duplicates the root. Restore it from `git show main:package-lock.json` (key: `packages/desktop/node_modules/electron`). |
| `Build (Desktop)` (`Cannot find module @rollup/rollup-*-*` or `lightningcss.*-*.node` or `Expected "0.25.12" but got "..."`) | Lockfile is missing platform-specific native binary entries. npm issue #4828: regenerating `package-lock.json` on a single platform drops optional `@rollup/rollup-*`, `@esbuild/*`, `lightningcss-*-*`, `@tailwindcss/oxide-*-*`, `@img/sharp-*-*`, `@biomejs/biome-*-*`, `oxc-parser-*-*`, `oxc-resolver-*-*`, `syncpack-*-*`, `unrs-resolver-*-*` entries for other OS/CPU combinations. **Never `rm package-lock.json`** on a single-platform checkout; use targeted `npm install <pkg>@<ver> -w <workspace>` instead. If you must regenerate, copy `package-lock.json` from `main` first and let `npm install` reconcile only the diffs. |
| `check:format` | `npx biome format --write packages/ private/account/` |
| `check:i18n` | `npm run i18n:generate-hashes && npm run i18n:sync`, then translate missing keys |
| `check:ci-renet` | `cd private/renet && go fmt ./...`, then fix golangci-lint issues |
| `lint` / `check:lint` | Fix ESLint errors properly (never suppress with comments). **Never revert a dev-dep bump (or pin it in `.deps-upgrade-blocklist`) just to silence new rules a plugin surfaces.** When `eslint-plugin-react-hooks` 7.x flags `react-hooks/set-state-in-effect` / `refs-in-render` / `immutability` / `preserve-manual-memoization` across existing files, fix each site per React 19 idioms: move ref writes into a dependency-less `useEffect`, derive state via the "previous value" pattern (`const [prev, setPrev] = useState(value); if (prev !== value) { setPrev(value); setDerived(...); }`), wrap effect-only side effects in `useEffectEvent` (from `react`, available in 19+), defer problematic setState with `queueMicrotask`, use `window.location.assign(url)` instead of direct `window.location.href = url` assignments, and initialize state lazily with `useState(() => ...)` instead of a post-mount effect. Downgrade is not a fix. |
| `lint:unused` | Add to `ignoreDependencies` in `knip.json` if it's a transitive/runtime dep |
| `check:ci-e2e-coverage` | Add test stubs for new bridge functions in `packages/cli/tests/tests/08-e2e/` |
| `check:ci-renet` (types) | `private/renet/bin/renet bridge generate-types --output packages/shared/src/queue-vault/data --version dev` |
| `Initialize` (PR title) | PR title must follow Conventional Commits (`type(scope): summary` or `type: summary`). Fix with `gh pr edit <N> --title "fix: ..."`. |
| `Quality / PR Description` (stale) | Description's `updatedAt` is older than 30 min and there are new commits. Run `gh pr edit <N> --body "..."` **immediately before pushing the next commit** so the fresh timestamp is visible to the next CI run (editing alone does not trigger CI). |

### CI fix cycle

When fixing CI failures, follow this loop:

1. **Run locally first**: Run `npm run ci` sub-commands locally before pushing to avoid costly CI round-trips. Use parallel sub-agents for independent checks.
2. **Push and watch**: After pushing, watch CI with `gh run watch <id> --repo rediacc/console --exit-status` in the background.
3. **Fix on notification**: When the background watch completes, check for failures with `gh run view <id> --json jobs --jq '.jobs[] | select(.conclusion == "failure") | {name}'`.
4. **Fix, commit, push, repeat**: Fix the issue, commit, push, and watch again. Continue until green.

### CI watchdog and auto-retry

The CI has a watchdog (`watchdog-monitor.cjs`) and cancellation script (`cancel-older-runs.sh`) that manage run lifecycle:

- **New push -> old runs cancelled**: `cancel-older-runs.sh` force-cancels all older in-progress runs on the same branch. **Never re-run a cancelled run** -- cancelled means superseded.
- **Job failure (attempt 1)**: Watchdog uses AI (Cloudflare Workers AI) to classify the failure:
  - **Transient** (network timeout, flaky test, npm error): Auto-retries via `rerun-failed.yml`, other jobs keep running.
  - **Code-change** (TypeScript error, lint failure, missing artifact): Force-cancels immediately, no retry.
  - **AI unavailable**: Falls back to retry (same as pre-AI behavior).
- **Job failure (attempt 2+)**: Watchdog force-cancels the entire run -- no infinite retry loops.
- **Quality / Review Gate failures**: Never auto-retry, never use AI. Fail immediately and force-cancel.

**PR labels** to control behavior:

| Label | Effect |
|-------|--------|
| `no-cancel-push` | Don't cancel older runs on new pushes |
| `no-cancel-failure` | Don't cancel run when jobs fail |
| `no-auto-retry` | Skip retry, force-cancel immediately on failure |

Re-running (`gh run rerun`) is only appropriate for transient errors (network, flaky infra) on failed — not cancelled — runs.

### Never push to `main` or cut a release without explicit user authorization

**AI agents MUST NOT push to `main` (console or any submodule) or trigger a release without an explicit, per-task user request.** Every push to `main` runs the full release pipeline (`cd-v2.yml` deploys edge on green), so an unprompted main push is an unprompted release. The default is always: create a feature branch, open a PR, and let the user merge. Approving an implementation plan is **not** authorization to push to `main` or release. Branch protection forbids direct pushes (`.github/CONTRIBUTING.md`); do not work around it. When in doubt, stop at the branch/PR and ask.

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
- **Release workflow** (`cd-v2.yml`): Uses **real org secrets** from GitHub for production deployment.
- Generated secrets are masked via `::add-mask::` in `ci-env.sh`.

## Suppression mechanisms and the BLOCKER convention

Every escape hatch in the repo (allowlists, blocklists, overrides, ignore lists) must carry a substantive `BLOCKER:` comment. CI enforces the presence and quality of each BLOCKER through a shared validator; this is the single escape mechanism — no lazy `# no fix` or `# tbd` suppressions.

### Current sites

| Mechanism | File | Reader |
|---|---|---|
| Prod npm audit allowlist | `.audit-prod-allowlist` | `.ci/scripts/security/audit.sh` |
| Dev npm audit allowlist | `.audit-allowlist` | same |
| npm dep upgrade blocklist | `.deps-upgrade-blocklist` | `scripts/check-deps.ts` |
| Go dep upgrade blocklist | `.go-deps-upgrade-blocklist` | `.ci/scripts/quality/check-go-deps.sh` |
| `package.json` overrides | `package.json`: `overrides` + `_overridesReasons` | `scripts/check-overrides-reasons.ts` |

### Format

**Comment-friendly files** (shell / conf / txt):
```
# BLOCKER: <reason explaining who pins what / why fix cannot be taken / when to revisit>
<entry>
```
A blank line resets the tracked BLOCKER, so a single BLOCKER covers a grouped list until the next blank line.

**Inline** (`.deps-upgrade-blocklist` / `.go-deps-upgrade-blocklist`):
```
package-name  # BLOCKER: <reason>
```

**JSON files** (no comment support) use a parallel `_reasons` object with identical keys:
```jsonc
"overrides":         { "follow-redirects": "^1.16.0" },
"_overridesReasons": { "follow-redirects": "BLOCKER: axios pins <1.16.0; 1.16.0 fixes GHSA-r4q5-vmmm-2653" }
```

### Quality rules

A BLOCKER reason must be at least 30 characters (after normalization) and must not match any phrase in the banned-phrase list (`no fix`, `tbd`, `todo`, `ok`, `ack`, `later`, `will fix`, `dev only`, etc.).

Full banned list + implementation: `.ci/scripts/lib/blocker-validator.sh` (bash) / `scripts/lib/blocker-validator.ts` (TypeScript). Keep the two in sync when modifying.

### Adding / extending

- **New entry to an existing list**: prepend a `# BLOCKER: <reason>` line. The validator tells you exactly what to add when the gate fails.
- **New suppression mechanism**: (a) parse the list via the shared library's `parse_blockered_list` / `parseBlockeredList`; (b) validate via `verify_all_blockers` / `verifyAllBlockers`; (c) add a gate test under `.ci/scripts/test/gates/test-<mechanism>.sh` modelled on `test-overrides-reasons.sh`.

### Age policy (planned, not yet enforced)

The shared library `.ci/scripts/lib/age-check.sh` provides `check_entry_age` which warns at 180 days and fails at 365 days. Not yet wired into every reader — planned for a follow-up.

### Running the gate tests locally

```bash
npm run test:quality-gates   # runs every .ci/scripts/test/gates/test-*.sh
npm run check:ci-security-audit       # the BLOCKER-gated npm audit
npm run check:ci-overrides-reasons    # the BLOCKER-gated package.json overrides
```

