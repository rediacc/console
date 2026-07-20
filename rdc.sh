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

# Ensure npm dependencies are installed
ensure_deps

# Ensure shared packages are built
ensure_packages_built

# Ensure CLI is built and type-valid
ensure_cli_built

# Ensure renet is built and up-to-date
ensure_renet_built

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

# Production is the default; two explicit opt-in modes on top:
#   default       → user's real config in ~/.config/rediacc. The CLI's own
#                   resolution applies (server.json → eu.rediacc.com), same as
#                   an installed rdc binary.
#   RDC_DEV=1     → local dev gateway (REDIACC_ENVIRONMENT=development, token
#     (or --dev)    under .rdc-dev/, gateway URL sourced from
#                   private/account/.env). Requires a running dev gateway:
#                   ./run.sh account dev (default port 4800).
#   RDC_BENCH=1   → bench.rediacc.com, our internal real-D1 test environment.
#                   Uses a separate token file under .rdc-bench/ so it never
#                   collides with the local-dev or production token state.
#                   Deploy/reset bench via scripts/dev/{deploy,reset}-bench.sh.
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
if [[ "${RDC_BENCH:-0}" == "1" ]]; then
    export REDIACC_SUBSCRIPTION_TOKEN_FILE="$ROOT_DIR/.rdc-bench/api-token.json"
    export REDIACC_ACCOUNT_SERVER="https://bench.rediacc.com"
    unset REDIACC_SKIP_MACHINE_ACTIVATION
    mkdir -p "$ROOT_DIR/.rdc-bench"
    log_info "Renet available at: $renet_bin_dir/renet"
    log_step "Starting CLI (bench config — bench.rediacc.com)"
elif [[ "${RDC_DEV:-0}" == "1" ]]; then
    export REDIACC_ENVIRONMENT=development
    export REDIACC_SUBSCRIPTION_TOKEN_FILE="$ROOT_DIR/.rdc-dev/api-token.json"

    if [[ "${REDIACC_SKIP_MACHINE_ACTIVATION:-0}" != "1" ]]; then
        log_info "Renet available at: $renet_bin_dir/renet"
    fi

    # The dev gateway writes its URL into private/account/.env as
    # REDIACC_ACCOUNT_SERVER. Fail fast when it is absent — a half-configured
    # dev mode would otherwise surface as a confusing CLI error later.
    account_env="$ROOT_DIR/private/account/.env"
    if [[ -f "$account_env" ]]; then
        set -a
        # shellcheck source=/dev/null
        source "$account_env"
        set +a
    fi
    if [[ -z "${REDIACC_ACCOUNT_SERVER:-}" ]]; then
        log_error "RDC_DEV=1 but no dev gateway configured (private/account/.env missing REDIACC_ACCOUNT_SERVER)."
        log_error "Start it first: ./run.sh account dev"
        exit 1
    fi

    if [[ "${REDIACC_SKIP_MACHINE_ACTIVATION:-0}" != "1" ]]; then
        log_step "Starting CLI (dev mode — $REDIACC_ACCOUNT_SERVER)"
    fi
else
    log_info "Renet available at: $renet_bin_dir/renet"
    log_step "Starting CLI (production config)"
fi

# Run the compiled CLI bundle, passing through all arguments
node "$ROOT_DIR/packages/cli/dist/cli-bundle.cjs" "$@"
