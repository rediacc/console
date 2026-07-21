# Rediacc Console Monorepo

## Worktree Warning

**CRITICAL: This repo uses git worktrees.** Your working directory (from `pwd`) is the ONLY correct project root. NEVER use paths from other CLAUDE.md files that may appear in the system context — those belong to the main worktree and are a different checkout. All commands (`./run.sh`, `npx tsx`, file paths) MUST use the current working directory, not `/home/muhammed/monorepo/console/`.

## Session Defaults

Standing rules for every task, in this repo and its submodules. The operator should never
have to restate them.

### 1. Work stays uncommitted until asked

The default deliverable is an **uncommitted working tree**. Do not `git commit`, create a
branch, push, or open a PR unless the operator asks for it in that task. Approving a plan
is not approval to commit. (`main` and releases carry stricter rules; see *Never push to
`main` or cut a release without explicit user authorization*.)

This means there is **no safety net**, and the tree usually holds work from other sessions
and agents:

- Never `git checkout` / `restore` / `stash` / `clean` to undo your own mistake. It
  deletes uncommitted work, including work that is not yours. Repair forward instead.
- Prefer targeted edits over scripted bulk rewrites. If you must script one, re-verify the
  WHOLE file afterward, not just the part you aimed at. A find-and-replace scoped wider
  than you intended lands in a neighbouring key, function, or file, and your own
  verification will miss it if it only re-checks the target.

### 2. Findings are part of the deliverable

A session is scoped to one ask, but it walks past real defects on the way. Walking past
them silently is the failure this rule exists to prevent.

- **A workaround is a bug report.** If you route around something (a command that prints
  nothing, a flag that misbehaves, an error that explains nothing), you have found a
  defect. Say so, with the exact command and the exact output. Do not quietly take the
  long way and leave the bug for the next session to rediscover.
- **Discovery is always in scope. Fixing has a test.** Fix it on the spot, and say you
  did, when ALL THREE hold: it is in code you are already editing, the fix is small and
  local (no new abstraction, no signature change rippling outward), and the run you are
  already doing proves it. Otherwise report it with a one-line repro and ask. Do not
  silently start a second project inside the first one.
- **Unblocking and cross-boundary fixes: do the minimum, then say so loudly.** A gate or
  lint rule blocking the task, or a defect in another package or submodule, still gets
  fixed. Make the smallest change that works and flag it in the summary as something the
  operator did not ask for, rather than burying it in the diff. Never suppress a gate to
  get past it (see the BLOCKER convention).
- **Sweep the class, not the instance.** Before calling a bug fixed, grep for its
  siblings. One bad call site usually has several.
- **Ask for the big-bang, not for permission to patch one thing.** The operator prefers
  ONE comprehensive change over a trickle of small ones, and will usually say yes. So when
  findings cluster, do not ask about them one at a time and do not propose the minimal
  patch: put the whole cluster into a single plan (root cause, siblings, tests,
  regenerated artifacts, submodules included) and ask to run it. Ask as soon as the
  cluster is visible, not after you have spent the session working around it.
- **Clean break, no compatibility theater.** There is one operator and no external
  consumers. Fix the root cause; do not add migration commands, deprecation windows,
  fallbacks, or dual code paths to preserve behavior nobody depends on.
- **Once a big-bang is approved, do not descope it unilaterally.** Fan out subagents if it
  is large (rule 4). Never quietly downgrade a piece to a stub, a TODO, or a "follow-up
  issue". If something genuinely cannot be done, say which piece and why, out loud.
- **Track findings in the worklist, not in your head.** The Stop hook
  (`.claude/hooks/stop/worklist.py`) refuses to end a turn while any `- [ ]` remains.
  Get the path with `.claude/hooks/stop/worklist.py --path`. It is per-REPO, not
  per-session, so open items survive a restart and a fresh session inherits them.
  Read it at session start; append on discovery, tick on completion.
- **The worklist is shared, so ADD with `>>` and never rewrite the whole file.** A
  second session may be running in this worktree. Two read-modify-writes lose the
  loser's items silently. Append single lines, tag them `(<session-id-prefix>)` so
  another session can tell whose they are, and re-read immediately before ticking.
  If an open item is not yours and not part of your task, leave it: being blocked by
  it is the point, but doing it blind risks duplicating another session's work.
- **Defer as a QUESTION, not a note.** Three states, and only three: `- [ ]` open,
  `- [x]` done, `- [?]` needs an operator decision. A `- [?]` goes to AskUserQuestion,
  and the hook prints every one of them back to the operator on stop, so a deferral
  cannot hide in a paragraph. Reserve it for real decisions: anything you can settle
  from the code, the request, or a sensible default is autonomous, and asking about it
  wastes a round trip.
- **End with what you did NOT fix**, as a short "found, not fixed" list, and offer it as
  the next big-bang so nothing discovered gets lost.

### 3. Verify before you claim

- **Run the real thing.** Output, exit-code, and error-path defects are invisible to code
  reading and to mocked tests. Drive the actual command and read stdout and stderr
  SEPARATELY: a wrapper that swallows output, or progress text landing on stdout, only
  shows up in the raw bytes.
- **A plan's claim about code you have not read is a hypothesis.** Verify the load-bearing
  ones before relying on them. Approved plans are wrong about real code often enough that
  the first live run is part of the implementation, not a formality.
- **Do not trust a report you have not spot-checked**, including a subagent's and your own
  from earlier in the session. Check the artifact, not the summary of it.
- **Name the gates you ran, and the ones you skipped.** Before calling a failure
  pre-existing or environmental, show that none of its findings are in files you touched.
- **"Cannot be done here" is a claim, so probe it before you make it.** Closing an item
  as impossible without running the command that proves it is how work gets abandoned
  while sounding diligent. A CRIU pin bump was reported as needing infrastructure this
  session did not have; `docker version` answered in one second, and it did.

### 4. Reach for subagents on investigation and planning

Reading and thinking parallelize well here; writing does not. Use them accordingly.

- **Investigate with them by default.** Any question that means sweeping several files,
  packages, or naming conventions goes to `Explore` or `general-purpose` agents rather
  than into your own context. Read-only fan-out is cheap: run several at once. Ask each
  for conclusions with `file:line` evidence, never file dumps.
- **Plan with them on anything non-trivial.** For a design with real trade-offs, run
  `Plan` agents (up to 3, different angles) and synthesize. Their plans are proposals, not
  findings: check the load-bearing claims yourself before acting (see rule 3).
- **Writing agents: at most 2 at a time, with disjoint file ownership.** State the exact
  files each one owns and forbid it from touching any other. Two agents editing one file,
  or one agent running a repo-wide regenerate script, corrupts the tree. Also forbid
  `git checkout/restore/stash` and any `sync`/`regenerate` script in their prompts, for
  the reasons in rule 1.
- **Spot-check every agent's output against the artifact.** Their reports are accurate
  about intent and quietly wrong about placement. Verify structure across the whole file
  set they touched, not just the keys or symbols they claimed to change.
- **Model choice:** Opus for code and design, Sonnet for translation and naturalization.

## Architecture

Self-hosted infrastructure platform. Each machine runs Docker-based repositories with encrypted, isolated environments.

### Key Concepts

- **Repository**: An isolated application deployment (e.g., `mail`, `gitlab`, `nextcloud`). Each repo has its own Docker daemon at `/var/run/rediacc/docker-<networkId>.sock`, loopback IP range (127.0.x.x/26), and mount at `/mnt/rediacc/mounts/<guid>/`.
- **Fork**: `rdc repo fork <name> --tag <tag>` makes a new repo (`<name>:<tag>`) with a fresh GUID and networkId that shares the parent's data via BTRFS reflink. **Forks are near-instant and constant-time** regardless of repo size: a 100 GB repo and a 1 GB repo fork in the same seconds. Use forks freely as the per-test isolation unit, do NOT assume fork cost scales with repo size.
- **Renet**: Network orchestrator on the machine. Manages compose files, loopback IPs, Docker daemon lifecycle. CLI: `sudo renet list all --json`, `sudo renet compose -- up -d`.
- **Rediaccfile**: Bash script with lifecycle functions (`up()`, `down()`, `info()`) sourced by renet during deployment.
- **Config**: CLI configuration file for connecting to machines. Each config is a flat JSON file (~/.config/rediacc/rediacc.json by default) with a unique ID and version number. Multiple named configs supported (e.g., production.json, staging.json).
- **State Provider**: Abstraction layer (`CloudStateProvider`, `LocalStateProvider`) that routes API calls based on adapter detection.
- **Config Storage**: Optional zero-knowledge encrypted config sync. Setup via web portal (`/account/config-setup`), requires passkey with PRF extension. One store per org, configs scoped per team. Member management via portal. CLI push/pull commands planned but not yet implemented.

### Packages

| Package | Description |
|---------|-------------|
| `packages/cli/` | `rdc` CLI tool (Commander.js); includes SSH/SFTP/sync/terminal utilities under `src/shared-desktop/` |
| `packages/www/` | Marketing website (Astro) |
| `packages/shared/` | Shared types, config, services (consumed by cli, www, account) |

## CLI (`packages/cli/`)

### Common Commands

The thing a command acts on is a **positional ref**, not a `--name` flag. A repo ref is
`name`, `name:tag` for a fork, and optionally `name@machine` to assert placement. The
machine is derived from the ref, so `-m/--machine` is gone from most repo commands (it
survives where there is nothing to derive from, e.g. `repo create`, or as a batch filter,
e.g. `repo up --all -m <machine>`).

```bash
# Full machine status (SSH + renet list all)
rdc machine status <machine>

# Filter by section
rdc machine status <machine> --system
rdc machine status <machine> --containers
rdc machine status <machine> --services
rdc machine status <machine> --repositories
rdc machine status <machine> --network
rdc machine status <machine> --block-devices

# SSH terminal: one positional target, either a machine name or a repo ref
rdc term connect <machine>

# SSH terminal to repo (sets DOCKER_HOST, working dir)
rdc term connect <repo>

# Run command on machine
rdc term connect <machine> -c "command"

# Deploy/update a repository (machine derived from the ref)
rdc repo up <repo>

# File sync (directory)
rdc repo sync upload <repo> --local ./local-path
rdc repo sync download <repo> --local ./local-path

# File sync (single file, explicit remote path)
rdc repo sync upload <repo> --local ./config.toml --remote-file etc/config.toml
rdc repo sync download <repo> --local ./out --remote-file etc/config.toml

# Container logs / exec
rdc repo logs <repo> -c <container> --lines 50
rdc repo exec <repo> -c <container> -- <command>

# VS Code remote (one positional target, like term)
rdc vscode connect <repo>
```

### Run Functions (escape hatch, debugging only)

`rdc run` executes Rediaccfile functions remotely. It is hidden from help and MCP, and is for
debugging only. Prefer the dedicated commands above. The function name is passed with `-f`.

```bash
rdc run -f container_list -m <machine> --param repository=<repo>
rdc run -f container_logs -m <machine> --param repository=<repo> --param container=<name>
rdc run -f container_exec -m <machine> --param repository=<repo> --param container=<name> --param command="..."
rdc run -f container_restart -m <machine> --param repository=<repo> --param container=<name>
```

### Config Setup

```bash
# Default config (~/.config/rediacc/rediacc.json) is created automatically on first use
rdc config init production          # Create named config
rdc repo list                       # List repos with name -> GUID mapping
rdc --config production machine status prod-1  # Use specific config
```

### CLI Code Structure

```
packages/cli/src/
├── commands/           # Command implementations
│   ├── machine/        # machine subcommands (query filters, provision.ts = OpenTofu VM provision/destroy)
│   ├── config.ts        # Config management (replaces context)
│   ├── term.ts          # SSH terminal
│   ├── sync.ts          # File sync via rsync
│   ├── vscode.ts        # VS Code Remote SSH
│   └── repo.ts          # Repository management
├── remote/             # SSH, SFTP, rsync, terminal, VS Code server modules (was shared-desktop/)
├── services/           # Business logic, grouped by domain (concrete modules, no barrels)
│   ├── state.ts          # getStateProvider() - local, config-file-backed state provider
│   ├── account/          # account-client, license, cert-cache, subscription-{auth,device-auth}
│   ├── backup/           # backup-schedule{,-execute,-reconcile,-unit-generator}, backup-env-file
│   ├── config/           # config-base, config-resources{,-resolve}, config-{prune,refs-prune,network-id,server-client}, resource-state
│   ├── core/             # cross-cutting: audit{,-log}, output, mutation-gate, master-password, file-lock, embedded-assets, context-language, vscode-server-remote
│   ├── executor/         # local-executor, ops-executor
│   ├── machine/          # machine-connection, machine-status, ssh-connection
│   ├── provision/        # infra-provision, cloudflare-dns, region-discovery
│   ├── renet/            # renet-execution, renet-provisioner, renet-binary-transfer, renet-license-contract
│   ├── repo/             # repo-{key-deployment,mount-check,secrets-store,ssh-tunnel}, prune, storage-browser
│   ├── telemetry/        # telemetry{,-attrs,-setup}, otlp-credentials, profiling
│   ├── tofu/             # OpenTofu cloud-VM provisioning engine
│   ├── update/           # updater, background-updater, update-state
│   └── __tests__/        # unit tests (central, mirrors commands/__tests__)
└── utils/
    └── commandFactory.ts  # Generic CRUD command builder
```

### How the Local Adapter Works

The CLI reads machine/repo config from `~/.config/rediacc/rediacc.json` (or other named config file) and connects via SSH directly. LocalResourceState reads from the config file directly.

## Terminology

When writing documentation, help text, error messages, or code comments, follow these rules:

- **No "modes"**: Say "local adapter", never "local mode".
- **One adapter**: `local` is the only adapter. The experimental cloud adapter (middleware-backed) was removed; do not reintroduce cloud/middleware terminology.
- **Config auto-creation**: Default config is created automatically on first use. Don't tell users to run `rdc config init` for the default config. `config init <name>` is for named configs only.
- **Keep docs concise**: No verbose explanations or workarounds for error messages. Document what the command does, not how to work around issues.

## i18n / Translations

English (`packages/www/src/i18n/translations/en.json`) is the source of truth; the 12
other locales are derived. **Read `docs/i18n/CONVENTIONS.md` before touching any
translation.** Key rules:

- English must read as natural, daily language (grade 5-7 for marketing; technical for
  docs). Optimize English first, then lock it: after any English value change run
  `npm run i18n:generate-hashes`.
- Non-English values are **naturalized** (native, idiomatic phrasing, NOT literal /
  word-for-word). Never bulk-replace a locale file with machine/literal translations.
- Preserve every `{{placeholder}}`, HTML tag, number, and product name; mirror English
  keys/order/structure; change values only.
- **On English change, re-translate only the delta**: `npm run i18n:naturalize-status`
  lists the stale keys; re-naturalize just those via `private/growth/i18n_pipeline`
  (`./run.sh --lang <lang> --surface <surface>` — its ledger skips already-done keys).
- **Use `--model haiku`** (the default, cheapest capable model — English/Turkish were
  done on haiku; the ledger records the model per language). Only bump to sonnet/opus
  for a language whose haiku output reads awkward. Cost compounds ×12 languages.
- `check-i18n-naturalization` is a blocking gate in `check:i18n`: it fails when an
  already-naturalized key goes stale (English changed without re-naturalizing).

## Build & Test

**This monorepo uses npm, not pnpm.**

`.npmrc` enforces supply-chain hardening: `ignore-scripts=true`, `allow-git=none`, `minimum-release-age=1440`. The `ignore-scripts` flag blocks all dependency lifecycle scripts; after every `npm install` or `npm ci`, run `npm run install:natives` to compile the three packages that genuinely need scripts (ssh2, cpu-features, esbuild). The script passes `--ignore-scripts=false` explicitly because `npm rebuild` otherwise silently respects the global flag and does nothing. Source of truth: `.ci/scripts/quality/check-npmrc.sh`.

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

### `./rdc.sh` targets production by default (`RDC_DEV=1` for local dev)

Bare `./rdc.sh` behaves like an installed `rdc`: real config and token in
`~/.config/rediacc`, account server via `server.json` → `eu.rediacc.com`. Local
development against the dev gateway is an explicit opt-in — `RDC_DEV=1 ./rdc.sh …`
(or `./rdc.sh --dev …`), which uses the `.rdc-dev/` token file and the gateway URL
from `private/account/.env`, and fails fast if `./run.sh account dev` isn't
running. `RDC_BENCH=1` targets bench.rediacc.com as before. There is no
`RDC_PROD` any more. The renet build stays `--nolicense` in all wrapper modes;
`RDC_RENET_LICENSE=1` is the independent enforcement opt-in (below).

### Iterating on a local SEA (`./rdc.sh --native`)

`./rdc.sh --native` builds the real single-executable binary (Node SEA) from local source and installs it over `~/.local/share/rediacc/bin/rdc`, instead of running via the dev bundle. Use it when iterating on SEA-only behaviors (embedded renet, auto-update gating) that the dev-mode `cli-bundle.cjs` path doesn't exercise. It cross-builds renet for BOTH linux arches into `private/bin` (via `build.sh stage_linux`) so the produced SEA can provision an amd64 or arm64 remote.

The flag runs `ensure_deps` + `ensure_packages_built` first, so edits to `packages/shared` or `packages/provisioning` are picked up by the bundler — those packages resolve through their own `dist/` outputs, and forgetting to rebuild them was a silent footgun. Auto-update is short-circuited via the `VERSION === '0.0.0-dev'` guard in `packages/cli/src/utils/platform.ts::isUpdateDisabled`, so the `--native` binary survives the next `rdc` invocation.

The previous binary is preserved as a backup matching `getOldBinaryPath()` (`<base>.old<ext>` — `rdc.old` on Linux/macOS, `rdc.old.exe` on Windows) so `cleanupOldBinary()` removes it on the next successful update.

The SEA is injected by `.ci/scripts/build/sea-inject/` (a streaming replacement for postject, which could not inject a blob this large — see #525), so a full-fat SEA carrying the entire k8s stack for both arches builds fine.

### Reproducing license-flow bugs in dev (`RDC_RENET_LICENSE=1`)

By default `./rdc.sh` rebuilds renet with the `--nolicense` Go build tag (`pkg/license/runtime_nolicense.go` stub) so dev iteration isn't blocked by license enforcement. That's the right default for everyday work, but it also hides license-flow bugs (e.g. rediacc/console#482) because the renet binary deployed to your test machine never returns `LICENSE_REQUIRED` (exit 10), so the CLI's recovery framework in `packages/cli/src/services/local-executor.ts:632-720` never fires.

To reproduce license-enforcement issues locally, set:

```bash
ACCOUNT_ED25519_PUBLIC_KEY="$(curl -s https://www.rediacc.com/api/public/account-key)" \
RDC_RENET_LICENSE=1 \
./rdc.sh --config <prod-config> repo push <repo> --to <fresh-machine>
./rdc.sh --config <prod-config> backup restore <repo> --as <repo> -m <fresh-machine> --up
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
| renet (Go) | `-ldflags "-X main.Version=..."` |

`bump.sh` still used by: CLI (npm pack tarball name). Runs only on push-to-main.

## Release Channels

The CLI supports two release channels, both production-quality:
- **stable** (default): Promoted from edge after 7-day soak. Downloaded from `cli/stable/`.
- **edge**: Continuously deployed production. Tagged + released on every merge to main. Downloaded from `cli/edge/`.

R2 structure: `rediacc-releases/cli/{edge,stable}/{manifest.json,latest.json,rdc-*}`

Environments:
- `edge.rediacc.com` -- auto-deployed on merge to main, D1 cloned from production daily
- `www.rediacc.com` -- production, promoted from edge after 7-day soak

## Media Assets (tutorial/solution videos + tutorial-narration audio)

Tutorial/solution videos and the tutorial-narration audio cache live in
Cloudflare R2, not git: bucket `rediacc-www-media`. Videos are served at
`media.rediacc.com`; this replaced committing `.mp4` files directly under
`packages/www/public/assets/` (642 files, ~5.2GB, which bloated `.git` and
caused CI timeouts on the `ubuntu-slim` runner's hard 15-minute cap). The
`packages/www/public/assets/{tutorials/video,videos/solutions,tutorials/audio}`
directories are gitignored and no longer tracked — a fresh checkout has none
of these files locally; the site fetches videos straight from
`media.rediacc.com` at runtime (`src/utils/solution-video.ts`,
`src/plugins/remark-tutorial-embed.ts` read `src/data/video-manifest.json`
and emit CDN URLs when `PUBLIC_VIDEO_CDN_BASE_URL` is set — see
`.github/workflows/cd-deploy-worker.yml`'s "Build pages" step). The two CI
gate scripts (`check-locale-tutorial-assets.ts`, `check-solution-videos.ts`)
check the manifest, not the local filesystem, so they're unaffected by
whether media happens to be checked out locally. Because the files leave the
git tree entirely (not just history), no CI sparse-checkout workaround was
needed — even a full default `actions/checkout` no longer transfers them.

The tutorial-narration `.mp3` cache (`tutorials/audio/`) is a **different
case**: it's never served to a browser (TTS narration muxed into the final
`.mp4` at build time by `generate-tutorial-video.ts` /
`scripts/lib/ffmpeg-video.ts`), so it's synced to the same bucket under
`tutorials/audio/` purely as a build-time cache — not covered by the Cache
Rule, only reachable via the S3 API. `./run.sh www tutorials generate|video`
restores/backs it up automatically (best-effort, skips with a warning if R2
credentials aren't set) via `www_tutorial_audio_restore` /
`www_tutorial_audio_upload` in `run.sh`. Regenerating narration costs real
TTS GPU/electricity, so this cache exists specifically to avoid re-paying
that cost on a fresh checkout.

See `.ci/docs/r2-media-setup.md` for the full bucket/domain/Cache Rule setup
plus the audio-cache details (§9), `.ci/scripts/deploy/sync-media-to-r2.sh`
to push changed media (incremental, `--tutorials-only`/`--solutions-only`/
`--audio-only`), and `.ci/scripts/deploy/sync-media-from-r2.sh` to restore
media locally (needed for pipeline development / offline ffmpeg work; not
needed for normal `npm run dev` browsing). Credentials:
`R2_MEDIA_ACCESS_KEY_ID`/`R2_MEDIA_SECRET_ACCESS_KEY`/`R2_MEDIA_ENDPOINT`
(org secrets, scoped to `console`); bucket/domain names are org variables
`R2_MEDIA_BUCKET`/`MEDIA_CDN_DOMAIN`.

Remaining open item: the git-history rewrite (`git filter-repo` to shrink
`.git` itself, since the pre-migration commits still contain the old blobs)
is a separate, later, human-supervised phase — not done as part of this
migration.

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

Slugs: `ses-eu`, `ses-us`, `ses-asia`, `ses-bench`, `cf-cd`, `cf-r2`, `cf-r2-media`, `turnstile`, `turnstile-bench`, `otlp-eu`, `otlp-us`, `otlp-asia`, `otlp-bench`, `dkim-notify`.

`cf-r2-media` is bucket-scoped (`rediacc-www-media` only, not account-wide like `cf-r2`) — least-privilege token for the www video-media pipeline, see `.ci/docs/r2-media-setup.md`.

`dkim-notify` is the BYODKIM RSA-2048 keypair applied to every regional SES identity for `notify.rediacc.com`. One private key, one Cloudflare TXT record at `<selector>._domainkey.notify.rediacc.com`, three SES regions (eu/us/asia). To rotate, stage the PEM via `DKIM_NOTIFY_PRIVATE_KEY_PATH=<path>` and run `./run.sh rotation rotate dkim-notify`. The tool publishes the DNS, applies the key to all three regions, smoke-tests propagation, and updates the manifest atomically. If `DKIM_NOTIFY_PRIVATE_KEY_PATH` is unset, a fresh keypair is generated in-memory (acceptable for bench experiments only — production rotations must stage the PEM so the key can be backed up to 1Password before the process exits).

Auth: `SES_AK_ID`/`SES_AK_SECRET` for AWS IAM admin, `CLOUDFLARE_API_TOKEN` (or `CF_API_KEY`+`CF_EMAIL`) for Cloudflare, authenticated `gh` CLI for GitHub secrets.

`scripts/dev/deploy-bench.sh` runs `rotation check --for=bench` as a preflight, so a stale `private/account/.env.bench` cannot ship a dead key.

## Quality Gates and the BLOCKER convention

`npm run ci` runs the checks CI runs. Two things live in their own files because
they are lookup material, not standing rules:

- **[docs/agent/ci-gates.md](docs/agent/ci-gates.md)** — what `npm run ci` covers,
  the quick fix for each gate, CI failure triage, the fix cycle, watchdog and
  auto-retry semantics, and the rule against pushing `main` or releasing unasked.
  **Read it when a gate fails or before touching CI.**
- **[docs/agent/suppressions.md](docs/agent/suppressions.md)** — every escape hatch
  (allowlists, blocklists, overrides) and the `BLOCKER:` reason each one must carry,
  plus the liveness gate that proves a reason is still true.
  **Read it before adding an entry to any allowlist, and never suppress a gate to
  get past it.**
