#!/bin/bash
# Standalone CLI runner for rdc (development mode)
# Auto-builds renet from Go source and makes it available to the CLI.
#
# ============================================================================
# DEMO PREP CHEAT-SHEET  (read this before a live demo)
# ============================================================================
# Install a clean, license-free binary as the system `rdc` (renet built with
# -tags nolicense, no account-server calls), then repoint the PATH symlink once:
#
#     ./rdc.sh --native
#     ln -sf ../share/rediacc/bin/rdc ~/.local/bin/rdc
#
# After that, `rdc` from any terminal is the binary (no dev-wrapper output).
#
# ----------------------------------------------------------------------------
# URL anatomy (demo-stackoverflow); forks add the -fork-<TAG> infix:
#
#            SERVICE NAME        PROJECT/WORKLOAD    SERVER      TOP.TLD
#
# https://pgadmin              .demo-stackoverflow .hostinger  .rediacc.io
# https://pgadmin-fork-joseph  .demo-stackoverflow .hostinger  .rediacc.io
# https://pgadmin-fork-abraham .demo-stackoverflow .hostinger  .rediacc.io
#
# ----------------------------------------------------------------------------
# Repos on `hostinger` (forks are O(1) regardless of size). NOTE: gitlab uses
# its OWN domain, not the .<repo>.<machine> shape above:
#
# demo-stackoverflow  128 GB  fork+up ~90s
#   https://pgadmin.demo-stackoverflow.hostinger.rediacc.io
#   https://pgadmin-fork-fabrikam.demo-stackoverflow.hostinger.rediacc.io
#
# gitlab               14 GB  fork+up ~5min (heavy)
#   https://gitlab.rediacc.io/
#   https://gitlab-fork-fabrikam.hostinger.rediacc.io/
#
# ----------------------------------------------------------------------------
# Fork / connect / delete loop:
#
# rdc repo fork --parent demo-stackoverflow --machine hostinger --tag joseph  --up
# rdc repo fork --parent demo-stackoverflow --machine hostinger --tag abraham --up
#
# rdc vscode connect --machine hostinger -r demo-stackoverflow
#
# rdc repo delete --name demo-stackoverflow:abc --machine hostinger   # destroys containers/volumes/image
# rdc config repository remove --name demo-stackoverflow:abc          # delete keeps the config entry; this drops it
#
# ----------------------------------------------------------------------------
# Agent-style demo prompts (paste to an assistant):
#
# "Use rdc (a locally installed CLI). On the hostinger machine, query the
#  production demo-stackoverflow Postgres DB: top 10 tags by count."
# "...how many rows are in the posts table of demo-stackoverflow on hostinger?"
# "...connect to demo-stackoverflow on hostinger and drop the votes table
#  (testing failure recovery)."
# ============================================================================

set -euo pipefail

# Root directory (portable: works on Linux, macOS, and Windows/Git Bash)
ROOT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd -P)"

# Source configuration and utilities
source "$ROOT_DIR/.ci/config/constants.sh"
source "$ROOT_DIR/.ci/lib/local-common.sh"

# --native: build the real single-executable binary (Node SEA) from local source
# and install it over the user's rdc at ~/.local/share/rediacc/bin/rdc, instead of
# running via the dev bundle. Use it to exercise SEA-only behaviors the bundle
# cannot reach (embedded-renet extraction, auto-update gating). The dev SEA
# self-disables auto-update via the VERSION === "0.0.0-dev" gate in
# packages/cli/src/utils/platform.ts::isUpdateDisabled, so it won't be clobbered
# on the next invocation.
#
# Steps performed (must match the manual sequence documented in CLAUDE.md):
#   1. Cross-build renet for BOTH linux arches into private/bin/renet-linux-<arch>
#      with -tags nolicense, so the SEA can provision an amd64 OR arm64 remote
#      (the embedded provisioner picks the arch matching each machine's uname -m).
#   2. Run .ci/scripts/build/build-cli-executables.sh --platform $P --arch $A
#      to assemble the SEA at dist/cli/rdc-$P-$A (injected by sea-inject/, which
#      streams the blob and has no size ceiling — full k8s assets embed fine).
#   3. Back up the existing user binary to *.old and replace it.
if [[ "${1:-}" == "--native" ]]; then
    shift
    # Detect platform + arch + executable suffix from uname. The .exe suffix
    # matters because build-cli-executables.sh emits rdc-win-<arch>.exe and
    # the auto-update housekeeping in packages/cli/src/utils/platform.ts
    # expects the backup at <base>.old<ext> (rdc.old / rdc.old.exe).
    case "$(uname -s)" in
        Linux)
            _ovr_platform="linux"
            _ovr_exe=""
            ;;
        Darwin)
            _ovr_platform="mac"
            _ovr_exe=""
            ;;
        MINGW* | MSYS* | CYGWIN*)
            _ovr_platform="win"
            _ovr_exe=".exe"
            ;;
        *)
            log_error "Unsupported platform $(uname -s) for --native"
            exit 1
            ;;
    esac
    case "$(uname -m)" in
        x86_64 | amd64)
            _ovr_arch="x64"
            ;;
        aarch64 | arm64)
            _ovr_arch="arm64"
            ;;
        *)
            log_error "Unsupported arch $(uname -m) for --native"
            exit 1
            ;;
    esac
    # The SEA bundler resolves shared / provisioning through their published
    # dist/ outputs (the SSH/SFTP/sync code now lives inside packages/cli
    # under src/remote). Without rebuilding them first, edits to those packages
    # get silently dropped from the bundle.
    check_node_version "$NODE_VERSION_MIN"
    ensure_deps
    ensure_packages_built
    # Build renet for BOTH linux arches into the slots build-cli-executables.sh
    # embeds (private/bin/renet-linux-<arch>). The SEA embeds linux renet binaries
    # for remote provisioning, and a remote machine may be amd64 or arm64 — the
    # embedded provisioner sends the one matching each machine's `uname -m`, so
    # both must be present. Delegated to build.sh's stage_linux so the per-arch
    # cross-compile lives in exactly one place (shared with dev/build).
    log_step "Cross-building renet (both linux arches) → private/bin"
    (cd "$ROOT_DIR/private/renet" && ./build.sh stage_linux "$ROOT_DIR/private/bin")
    log_step "Building SEA for $_ovr_platform/$_ovr_arch"
    bash "$ROOT_DIR/.ci/scripts/build/build-cli-executables.sh" \
        --platform "$_ovr_platform" --arch "$_ovr_arch"
    _ovr_built="$ROOT_DIR/dist/cli/rdc-${_ovr_platform}-${_ovr_arch}${_ovr_exe}"
    if [[ ! -f "$_ovr_built" ]]; then
        log_error "Built SEA not found at $_ovr_built"
        exit 1
    fi
    _ovr_dest="$HOME/.local/share/rediacc/bin/rdc${_ovr_exe}"
    if [[ ! -d "$(dirname "$_ovr_dest")" ]]; then
        log_error "Install dir $(dirname "$_ovr_dest") does not exist — is rdc installed?"
        exit 1
    fi
    # Backup naming matches getOldBinaryPath() in
    # packages/cli/src/utils/platform.ts so cleanupOldBinary() finds it:
    # rdc.old on Linux/macOS, rdc.old.exe on Windows.
    _ovr_backup="${_ovr_dest%${_ovr_exe}}.old${_ovr_exe}"
    if [[ -f "$_ovr_dest" ]]; then
        cp -f "$_ovr_dest" "$_ovr_backup"
    fi
    cp -f "$_ovr_built" "$_ovr_dest"
    chmod +x "$_ovr_dest"
    log_step "Installed dev SEA → $_ovr_dest (backup at $_ovr_backup)"
    "$_ovr_dest" --version
    exit 0
fi

check_node_version "$NODE_VERSION_MIN"

if [[ "${REDIACC_SKIP_MACHINE_ACTIVATION:-0}" == "1" ]]; then
    # Self-register as 'rdc' in ~/.local/bin so it's accessible from any terminal,
    # but ONLY when nothing is already installed there. A real SEA binary (from
    # `./rdc.sh --native`) installs to ~/.local/share/rediacc/bin/rdc and
    # points this symlink at it; forcibly repointing it back to the wrapper would
    # silently undo that install. So we never overwrite an existing rdc on PATH —
    # we only bootstrap the link when it is entirely absent (no file, no symlink,
    # not even a dangling one).
    _local_bin="$HOME/.local/bin"
    mkdir -p "$_local_bin"
    if [[ ! -e "$_local_bin/rdc" && ! -L "$_local_bin/rdc" ]]; then
        ln -s "$ROOT_DIR/rdc.sh" "$_local_bin/rdc"
    fi
    unset _local_bin
else
    log_step "Preparing CLI development environment"
fi

# Ensure the toolchain is current. All build/progress output goes to STDERR:
# stdout belongs to the CLI command — a rebuild triggered by an edit must not
# corrupt an `rdc ... -o json` pipeline with npm build logs (observed live:
# the first post-edit invocation broke JSON.parse for the caller).
ensure_deps >&2
ensure_packages_built >&2
ensure_cli_built >&2
ensure_renet_built >&2

# Regenerate skill reference if CLI has changed
ref_file="$ROOT_DIR/.claude/skills/rdc/reference.md"
cli_dist="$ROOT_DIR/packages/cli/dist/cli-bundle.cjs"
if [[ ! -f "$ref_file" ]] || [[ "$cli_dist" -nt "$ref_file" ]]; then
    log_step "Regenerating skill reference"
    ref_tmp="$(mktemp)"
    if npx tsx "$ROOT_DIR/packages/cli/scripts/generate-skill-reference.ts" >"$ref_tmp" 2>/dev/null && grep -q "^#" "$ref_tmp"; then
        mv "$ref_tmp" "$ref_file"
    else
        rm -f "$ref_tmp"
        log_warn "Skill reference generation failed (keeping existing)"
    fi
fi

# Add renet binary directory to PATH so CLI can find it
renet_bin_dir="$ROOT_DIR/private/renet/bin"
export PATH="$renet_bin_dir:$PATH"

# Production is the default; dev is the one explicit opt-in mode on top. Every
# universe is now a named CLI config (one config = server URL + E2E key + update
# channel + token), so there are no per-mode token-file or env exports here —
# selecting a config is all that changes:
#   default       → user's real config "rediacc" in ~/.config/rediacc. The CLI's
#                   own resolution applies: account server + update channel come
#                   from that config's account section, falling back to the
#                   built-in production defaults, same as an installed rdc.
#   RDC_DEV=1     → the named config "dev" (REDIACC_CONFIG=dev). We auto-seed
#     (or --dev)    ~/.config/rediacc/dev.json with the gateway URL and E2E
#                   public key READ (never sourced) from private/account/.env.
#                   Requires a running dev gateway: ./run.sh account dev
#                   (default port 4800); we probe its /server-info first.
#   bench         → no dedicated flag. Use the named config "bench":
#                     ./rdc.sh --config bench <cmd>
#                   Seed it once (token lands in api-token-bench.json, isolated
#                   from dev and production by config name):
#                     ./rdc.sh --config bench subscription login \
#                         --server https://bench.rediacc.com
#
# Independent renet build modifier:
#   RDC_RENET_LICENSE=1 → Build dev renet WITHOUT the --nolicense build tag, so
#                         the local binary enforces repo licenses like a prod
#                         release. Used to reproduce license-flow bugs locally
#                         (e.g. rediacc/console#482) without a release cycle.
#                         When set, also export ACCOUNT_ED25519_PUBLIC_KEY to
#                         the production key to validate prod-issued licenses.
if [[ "${1:-}" == "--dev" ]]; then
    RDC_DEV=1
    shift
fi
if [[ "${RDC_DEV:-0}" == "1" ]]; then
    # Read EXACTLY two values from the dev gateway's env file, by grep. NEVER
    # `source` it (not even with `set -a`): private/account/.env also holds
    # ACCOUNT_ED25519_PRIVATE_KEY, ACCOUNT_X25519_PRIVATE_KEY, ACCOUNT_JWT_SECRET and ACCOUNT_SERVER_API_KEY, and
    # sourcing would leak every one of those secrets into the CLI process
    # environment. grep + cut extracts only the two public values the dev
    # config needs — the gateway URL and the server's X25519 public key.
    account_env="$ROOT_DIR/private/account/.env"
    dev_server=$(grep -E '^REDIACC_ACCOUNT_SERVER=' "$account_env" 2>/dev/null | tail -1 | cut -d= -f2-)
    dev_e2e_key=$(grep -E '^ACCOUNT_X25519_PUBLIC_KEY=' "$account_env" 2>/dev/null | tail -1 | cut -d= -f2-)

    # Fail fast when the gateway is not configured — a half-configured dev mode
    # would otherwise surface as a confusing CLI error later.
    if [[ -z "$dev_server" ]]; then
        log_error "RDC_DEV=1 but no dev gateway configured (private/account/.env missing REDIACC_ACCOUNT_SERVER)."
        log_error "Start it first: ./run.sh account dev"
        exit 1
    fi

    # Probe liveness so a stale/unstarted gateway fails here with a clear
    # message instead of a confusing CLI error deep in a later request.
    if ! curl -fsS --max-time 2 "$dev_server/account/api/v1/.well-known/server-info" >/dev/null 2>&1; then
        log_error "Dev gateway not responding at $dev_server"
        log_error "Start it first: ./run.sh account dev"
        exit 1
    fi

    # Seed/patch the "dev" named config. node is guaranteed present (we exec it
    # below); jq is not. The seeder writes a minimal v3 config when the file is
    # absent and merges only the account fields when it exists, leaving every
    # other key intact. `rdc config set` cannot reach account fields, so this
    # small node snippet is the mechanism.
    node -e '
      const fs = require("fs"), path = require("path"), p = process.argv[1];
      let c;
      try {
        c = JSON.parse(fs.readFileSync(p, "utf8"));
      } catch {
        c = { schemaVersion: 3, id: require("crypto").randomUUID(), version: 1, encryption: { mode: "plaintext" } };
      }
      c.account = {
        ...(c.account ?? {}),
        accountServer: process.argv[2],
        ...(process.argv[3] ? { e2ePublicKey: process.argv[3] } : {}),
      };
      fs.mkdirSync(path.dirname(p), { recursive: true, mode: 0o700 });
      fs.writeFileSync(p, JSON.stringify(c, null, 2) + "\n", { mode: 0o600 });
    ' "$HOME/.config/rediacc/dev.json" "$dev_server" "$dev_e2e_key"

    # The only export the dev path adds: select the "dev" config. Everything
    # else (server URL, E2E key) now lives inside that config file.
    export REDIACC_CONFIG=dev

    if [[ "${REDIACC_SKIP_MACHINE_ACTIVATION:-0}" != "1" ]]; then
        log_info "Renet available at: $renet_bin_dir/renet"
        log_step "Starting CLI (dev config — $dev_server)"
    fi
else
    log_info "Renet available at: $renet_bin_dir/renet"
    log_step "Starting CLI (production config)"
fi

# Run the compiled CLI bundle, passing through all arguments
# exec, not a child: signals sent to this wrapper must reach the CLI directly
# (a bash layer between kill and node defers SIGINT until the child exits,
# which hangs tutorial prewarm/interrupt patterns — see tutorial-helpers.sh).
#
# NODE_COMPILE_CACHE: V8 spends ~120ms compiling the 15MB bundle on EVERY
# invocation (measured, --cpu-prof); the on-disk compile cache cuts that to a
# few ms after the first run. Env-var form on purpose — it covers the entry
# file itself, which module.enableCompileCache() cannot. Invalidated
# automatically by node version + file content. (The SEA keeps
# useCodeCache:false — code cache is platform-bound and the SEAs are
# cross-compiled.)
export NODE_COMPILE_CACHE="${NODE_COMPILE_CACHE:-$ROOT_DIR/.ci/cache/v8-compile-cache}"
exec node "$ROOT_DIR/packages/cli/dist/cli-bundle.cjs" "$@"
