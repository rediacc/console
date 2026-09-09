# Local environment, the `./rdc.sh` wrappers, and operator tooling

Lookup material lifted verbatim out of CLAUDE.md, which keeps the two-paragraph summary and
points here. Nothing below was reworded in the move: every paragraph is byte-for-byte what
CLAUDE.md carried, because the incident each one records is the payload and a summary of an
incident is not the incident.

Read this before fighting the devbox, the docker group, `account db`, the SEA loop, or a
license-flow reproduction.

## `./run.sh setup` — one command per machine

`./run.sh setup` prepares a machine and hands back a URL. It is idempotent: a
second run installs nothing, pulls nothing and recreates nothing.

    1. host tools   node >= 22, plus jq/zstd/curl/git (jq's absence used to make
                    the renet build silently ship without embedded assets)
    2. docker       Go (go.dev tarball, version parsed from private/renet/go.mod)
                    -> build renet -> `sudo renet install-docker --source=docker-repo`.
                    The official docker.com repo, NOT docker.io. Skipped entirely
                    when docker already works.
    3. image        ghcr.io/rediacc/devcontainer:latest, with a local build from
                    .devcontainer/Dockerfile as the fallback (that registry is
                    private; pulling it needs a token with `read:packages`)
    4. devbox       ONE container per worktree

`./run.sh devbox up|status|stop|remove|shell|logs` drives the container directly,
and `./run.sh setup --check` reports what is missing without changing anything.

**One published port for the whole machine.** A shared `traefik:v3.6` container
(`rediacc-devbox-proxy`, `.ci/lib/devbox.sh`) publishes `DEVBOX_PROXY_PORT` and routes
by **Host header** to `<worktree>.localhost` (VS Code), `-account` (the whole app),
`-db` and `-term` (ttyd on an attach-or-create tmux session, started by
`devbox-autostart.sh`; a reload re-attaches rather than opening a new shell).
Host routing rather than path routing is deliberate: every app keeps
its own root path, so nothing needs `--server-base-path`/`base` configuration. Routes
come from labels on the devbox container itself, so adding a worktree changes no proxy
config. This exists because each published port needs its own manual forward on
ChromeOS; now there is one -- and it is the ONLY one: devbox containers publish no
ports at all, so the proxy is the sole ingress. `devbox status` PROBES each route
and reports OK / "no backend yet", because Traefik's bare 502 names neither the
service nor the reason. Servers started inside the devbox must bind `0.0.0.0`
(`REDIACC_DEV_BIND`) or the proxy cannot reach them and Traefik answers 502.

**The docker-group gap closes itself.** `usermod -aG docker` does not affect the
shell that ran it, so the classic advice is "log out and back in". `run.sh`
instead calls `reexec_with_docker_group` (`.ci/lib/local-common.sh`), which checks
membership in `/etc/group` (NOT `id -nG`, which reports the stale groups of the
current process — the very thing being worked around), proves `sg docker -c
"docker version"` succeeds, then re-execs itself under `sg`. One hop, guarded by
`REDIACC_DOCKER_GROUP_REEXEC`, after which every docker call in the run is plain
`docker` rather than `sudo docker`.

**`account db` serves sqlite-web, not Drizzle Studio, and that reversal was paid
for.** Studio's local process serves only an API; its UI is hosted at
local.drizzle.studio. A real browser (agent-browser) showed Chrome's Local Network
Access restriction blocking that hosted page from reaching the local server -- the
page says so itself -- which no proxy change can fix. sqlite-web serves its UI from
the same origin as the data, so there is no third-party page and no permission to
grant. `./run.sh account db --studio` keeps the old behaviour. Related trap: Studio's
API endpoint IS `POST /`, so a redirect on `Path(/)` 307s the API; if you ever add
one, scope it with `Method(\`GET\`)`.

**One container per worktree, on a stable port.** The port block is derived from
the worktree's absolute path (`derive_slot`/`find_port_block` in
`.ci/lib/find-port.sh`), so a bookmarked URL survives a reboot and two worktrees
never collide. A running container is authoritative for its own ports; the
`.devbox-state` file is only a cache, and the container is found by the
`com.rediacc.devbox.worktree` label rather than by name.

**The container runs as YOU.** The image bakes its `vscode` user at UID 7111 and
chowns `/home/vscode`, `/opt/openvscode-server` (extensions included) and `/go` to
it. `docker run --user $(id -u)` therefore does NOT work — it leaves that
ownership untouched, and every extension install fails with EACCES. Instead
`.devcontainer/devbox-entrypoint.sh` starts as root, renumbers `vscode` to the
host uid/gid, chowns exactly those three trees, and drops privileges with
`setpriv`. It also sets `HOME` explicitly, because setpriv changes credentials
and not the environment.

The repo is bind-mounted at its IDENTICAL host path (never `/workspace`): a git
worktree's gitdir link is absolute, and a nested `docker -v $(pwd)` is resolved by
the host daemon. `~/.gitconfig`, `~/.git-credentials`, `~/.config/gh`,
`~/.claude`, `~/.claude.json` and `~/.config/rediacc` are bound in by name.

**`node_modules` is not shared between host and container** — the host and the
image have different glibc versions, and `install:natives` builds against
whichever one it runs on. `REDIACC_NPM_RUNTIME` is part of the `ensure_deps`
stamp so switching sides forces one honest reinstall instead of a loader error.

## The `./rdc.sh` wrappers

### `./rdc.sh` targets production by default (`RDC_DEV=1` for local dev)

Bare `./rdc.sh` behaves like an installed `rdc`: the default config
`~/.config/rediacc/rediacc.json` (its `account.*` fields carry the account server;
there is no `server.json` any more) and its own token at
`~/.config/rediacc/api-token-rediacc.json`. Each named config is a self-contained
universe with its own server, keys, machines, and token beside it at
`api-token-<name>.json`; there are no `.rdc-dev/` or `.rdc-bench/` token files.

Local development against the dev gateway is an explicit opt-in: `./rdc.sh --dev <command>`
(or `RDC_DEV=1 ./rdc.sh <command>`). `--dev` reads `REDIACC_ACCOUNT_SERVER` and
`X25519_PUBLIC_KEY` from `private/account/.env`, seeds or patches
`~/.config/rediacc/dev.json` with them, runs with `REDIACC_CONFIG=dev`, and fails
fast if `./run.sh account dev` isn't running. Bench is just another config now:
`./rdc.sh --config bench <command>` replaces the old `RDC_BENCH=1`. There is no `RDC_PROD`
or `RDC_BENCH` any more. The renet build stays `--nolicense` in all wrapper modes;
`RDC_RENET_LICENSE=1` is the independent enforcement opt-in (below).

### Iterating on a local SEA (`./rdc.sh --native`)

`./rdc.sh --native` builds the real single-executable binary (Node SEA) from local source and installs it over `~/.local/share/rediacc/bin/rdc`, instead of running via the dev bundle. Use it when iterating on SEA-only behaviors (embedded renet, auto-update gating) that the dev-mode `cli-bundle.cjs` path doesn't exercise. It cross-builds renet for BOTH linux arches into `private/bin` (via `build.sh stage_linux`) so the produced SEA can provision an amd64 or arm64 remote.

The flag runs `ensure_deps` + `ensure_packages_built` first, so edits to `packages/shared` or `packages/provisioning` are picked up by the bundler — those packages resolve through their own `dist/` outputs, and forgetting to rebuild them was a silent footgun. Auto-update is short-circuited via the `VERSION === '0.0.0-dev'` guard in `packages/cli/src/utils/platform.ts::isUpdateDisabled`, so the `--native` binary survives the next `rdc` invocation.

The previous binary is preserved as a backup matching `getOldBinaryPath()` (`<base>.old<ext>` — `rdc.old` on Linux/macOS, `rdc.old.exe` on Windows) so `cleanupOldBinary()` removes it on the next successful update.

The SEA is injected by `.ci/scripts/build/sea-inject/` (a streaming replacement for postject, which could not inject a blob this large — see #525), so a full-fat SEA carrying the entire k8s stack for both arches builds fine.

### Demo prep cheat sheet (read before a live demo)

Moved here from `rdc.sh` on 2026-09-09, where 53 lines of demo runbook sat in the wrapper a
developer types to run an ordinary CLI command. **The four commands were re-spelled on the
way**: the versions in `rdc.sh` used `--parent`, `--machine` and `--name` flags that the
positional-ref reshape removed, so as written they had stopped working. The spellings below
are read off the live sources: `packages/cli/src/commands/repo-fork.ts:568-572`,
`packages/cli/src/commands/vscode.ts:587-589` and
`packages/cli/src/commands/repo-create-delete.ts:486-490`.

Install a clean, license-free binary as the system `rdc` (renet built with `-tags nolicense`,
no account-server calls), then repoint the PATH symlink once:

```bash
./rdc.sh --native
ln -sf ../share/rediacc/bin/rdc ~/.local/bin/rdc
```

After that, `rdc` from any terminal is the binary, with no dev-wrapper output.

URL anatomy (`demo-stackoverflow`); forks add the `-fork-<TAG>` infix:

```
           SERVICE NAME        PROJECT/WORKLOAD    SERVER      TOP.TLD

https://pgadmin              .demo-stackoverflow .hostinger  .rediacc.io
https://pgadmin-fork-joseph  .demo-stackoverflow .hostinger  .rediacc.io
https://pgadmin-fork-abraham .demo-stackoverflow .hostinger  .rediacc.io
```

Repos on `hostinger` (forks are O(1) regardless of size). NOTE: gitlab uses its OWN domain,
not the `.<repo>.<machine>` shape above:

```
demo-stackoverflow  128 GB  fork+up ~90s
  https://pgadmin.demo-stackoverflow.hostinger.rediacc.io
  https://pgadmin-fork-fabrikam.demo-stackoverflow.hostinger.rediacc.io

gitlab               14 GB  fork+up ~5min (heavy)
  https://gitlab.rediacc.io/
  https://gitlab-fork-fabrikam.hostinger.rediacc.io/
```

Fork / connect / delete loop:

```bash
rdc repo fork demo-stackoverflow@hostinger --tag joseph  --up
rdc repo fork demo-stackoverflow@hostinger --tag abraham --up

rdc vscode connect demo-stackoverflow@hostinger

# Destroys containers, volumes and image, and drops the config entry.
rdc repo delete demo-stackoverflow:abc
# ...or keep the entry recoverable under deletedRepositories instead:
rdc repo delete demo-stackoverflow:abc --archive-config
```

Agent-style demo prompts (paste to an assistant):

- "Use rdc (a locally installed CLI). On the hostinger machine, query the production
  demo-stackoverflow Postgres DB: top 10 tags by count."
- "...how many rows are in the posts table of demo-stackoverflow on hostinger?"
- "...connect to demo-stackoverflow on hostinger and drop the votes table (testing failure
  recovery)."


### Reproducing license-flow bugs in dev (`RDC_RENET_LICENSE=1`)

By default `./rdc.sh` rebuilds renet with the `--nolicense` Go build tag (`pkg/license/runtime_nolicense.go` stub) so dev iteration isn't blocked by license enforcement. That's the right default for everyday work, but it also hides license-flow bugs (e.g. rediacc/console#482) because the renet binary deployed to your test machine never returns `LICENSE_REQUIRED` (exit 10), so the CLI's recovery framework (`needsLicenseRecovery` in `packages/cli/src/services/executor/local-executor.ts`) never fires.

To reproduce license-enforcement issues locally, set:

```bash
ACCOUNT_ED25519_PUBLIC_KEY="<the production ed25519 public key>" \
RDC_RENET_LICENSE=1 \
./rdc.sh --config <prod-config> repo push <repo> --to <fresh-machine>
./rdc.sh --config <prod-config> backup restore <repo> --as <repo> -m <fresh-machine> --up
```

**Where the key comes from, corrected 2026-07-29.** This block used to fetch it
with `curl -fsS https://www.rediacc.com/api/public/account-key`. That endpoint
returns **404** and the account API is not served from `www.rediacc.com` at all
(its other routes answer `410 Gone` there, while the same paths answer `200` on a
PR preview worker). There is no public URL for the key today.

CI does not need one, but **not for the reason this paragraph used to give**. It
said `ACCOUNT_ED25519_PUBLIC_KEY` "already exists as an organisation secret ...
verify with `gh api orgs/rediacc/actions/secrets`". That command now returns
`{"total_count":0,"secrets":[]}`, and the paragraph was wrong twice over: the org
store is not merely empty, it is **unused**. The key lives in **Bitwarden**
(`.ci/config/bws-secret-map.json`) and workflows pull it through
`./.github/actions/bws-secrets`. Running the old verification command and seeing
zero reads as "the secret was deleted" when the truth is "you are looking in the
wrong store".

Locally you must paste the value. GitHub secrets are **write-only** -- `gh` can
list their names and never their contents -- so there is no command that fetches
it, and the old one-liner was not merely pointing at a dead URL, it was pointing
at a shape of solution that cannot exist for a secret.

Whatever you substitute, do NOT pipe an unchecked HTTP response into this
variable. That was the original bug and it is worth stating plainly: with plain
`curl -s` a 404 is SILENT, its HTML body becomes the value, and that HTML is
baked into `keys.ProductionPublicKey` via ldflags. The build succeeds and every
prod-signed licence then fails as `invalid_signature` -- exactly the symptom this
variable exists to prevent. The documented cure was producing the disease.

`RDC_RENET_LICENSE=1` drops the `--nolicense` build flag. `ACCOUNT_ED25519_PUBLIC_KEY` must match the account server that issued the licenses on your test machines — for production licenses that's the prod ed25519 public key. The build flow wires this into `private/renet/pkg/license/keys.ProductionPublicKey` via ldflags. Without it, prod-signed licenses fail validation as `invalid_signature`.

After reproducing, unset `RDC_RENET_LICENSE` (or remove from your shell) so subsequent `./rdc.sh` invocations rebuild the dev-friendly nolicense renet again.

## Run Functions (escape hatch, debugging only)

`rdc run` executes Rediaccfile functions remotely. It is hidden from help and MCP, and is for
debugging only. Prefer the dedicated commands above. The function name is passed with `-f`.

```bash
rdc run -f container_list -m <machine> --param repository=<repo>
rdc run -f container_logs -m <machine> --param repository=<repo> --param container=<name>
rdc run -f container_exec -m <machine> --param repository=<repo> --param container=<name> --param command="..."
rdc run -f container_restart -m <machine> --param repository=<repo> --param container=<name>
```

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

Slugs: `ses-eu`, `ses-us`, `ses-asia`, `ses-bench`, `cf-cd`, `cf-r2`, `cf-r2-media`, `cf-breakpoint`, `turnstile`, `turnstile-bench`, `otlp-eu`, `otlp-us`, `otlp-asia`, `otlp-bench`, `dkim-notify`.

`cf-r2-media` is bucket-scoped (`rediacc-www-media` only, not account-wide like `cf-r2`) — least-privilege token for the www video-media pipeline, see `.ci/docs/r2-media-setup.md`.

`cf-breakpoint` (secret `CLOUDFLARE_BREAKPOINT_TUNNEL_TOKEN`) is the on-demand debug box's Cloudflare token: Tunnel edit + Access apps/policies edit at the account level, DNS edit scoped to the **`rediacc.io` zone only**, and nothing else — no Workers, D1, R2 or Pages. It is deliberately NOT `cf-cd`: a breakpoint session's whole purpose is to put a human on a shell, so anything in that job's environment is readable by that human, and `cf-cd` would make one debug session equivalent to production Worker-deploy and D1-delete rights. See `.ci/breakpoint/README.md`.

`dkim-notify` is the BYODKIM RSA-2048 keypair applied to every regional SES identity for `notify.rediacc.com`. One private key, one Cloudflare TXT record at `<selector>._domainkey.notify.rediacc.com`, three SES regions (eu/us/asia). To rotate, stage the PEM via `DKIM_NOTIFY_PRIVATE_KEY_PATH=<path>` and run `./run.sh rotation rotate dkim-notify`. The tool publishes the DNS, applies the key to all three regions, smoke-tests propagation, and updates the manifest atomically. If `DKIM_NOTIFY_PRIVATE_KEY_PATH` is unset, a fresh keypair is generated in-memory (acceptable for bench experiments only — production rotations must stage the PEM so the key can be backed up to 1Password before the process exits).

Auth: `AWS_IAM_ADMIN_ACCESS_KEY_ID`/`AWS_IAM_ADMIN_SECRET_ACCESS_KEY` for AWS IAM admin, `CLOUDFLARE_API_TOKEN` (or `CF_GLOBAL_API_KEY`+`CF_EMAIL`) for Cloudflare, authenticated `gh` CLI for GitHub secrets.

`scripts/dev/deploy-bench.sh` runs `rotation check --for=bench` as a preflight, so a stale `private/account/.env.bench` cannot ship a dead key.
