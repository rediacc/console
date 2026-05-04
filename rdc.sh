#!/bin/bash
# Standalone CLI runner for rdc (development mode)
# Auto-builds renet from Go source and makes it available to the CLI.

set -euo pipefail

# Root directory (portable: works on Linux, macOS, and Windows/Git Bash)
ROOT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd -P)"

# Source configuration and utilities
source "$ROOT_DIR/.ci/config/constants.sh"
source "$ROOT_DIR/.ci/lib/local-common.sh"

# --override-local: rebuild the SEA from local source and install it over the
# user's rdc binary at ~/.local/share/rediacc/bin/rdc. Useful when iterating on
# CLI internals that aren't reachable through the dev-mode `node cli-bundle.cjs`
# path (e.g. SEA-only behaviors, embedded renet, auto-update gating). The dev
# SEA self-disables auto-update via the VERSION === "0.0.0-dev" gate in
# packages/cli/src/utils/platform.ts::isUpdateDisabled, so it won't be clobbered
# on the next invocation.
#
# Steps performed (must match the manual sequence documented in CLAUDE.md):
#   1. Cross-build renet into private/bin/renet-linux-<arch> with -tags
#      nolicense so license checks are off (CI does the same for dev SEAs).
#      This is the slot the SEA's embedded provisioner reads from.
#   2. Run .ci/scripts/build/build-cli-executables.sh --platform $P --arch $A
#      to assemble the SEA at dist/cli/rdc-$P-$A.
#   3. Back up the existing user binary to *.old and replace it.
if [[ "${1:-}" == "--override-local" ]]; then
    shift
    # Detect platform + arch + executable suffix from uname. The .exe suffix
    # matters because build-cli-executables.sh emits rdc-win-<arch>.exe and
    # the auto-update housekeeping in packages/cli/src/utils/platform.ts
    # expects the backup at <base>.old<ext> (rdc.old / rdc.old.exe).
    case "$(uname -s)" in
        Linux)  _ovr_platform="linux"; _ovr_exe="" ;;
        Darwin) _ovr_platform="mac"; _ovr_exe="" ;;
        MINGW*|MSYS*|CYGWIN*) _ovr_platform="win"; _ovr_exe=".exe" ;;
        *) log_error "Unsupported platform $(uname -s) for --override-local"; exit 1 ;;
    esac
    case "$(uname -m)" in
        x86_64|amd64) _ovr_arch="x64"; _ovr_goarch="amd64" ;;
        aarch64|arm64) _ovr_arch="arm64"; _ovr_goarch="arm64" ;;
        *) log_error "Unsupported arch $(uname -m) for --override-local"; exit 1 ;;
    esac
    # The SEA bundler resolves shared-desktop / shared / provisioning through
    # their published dist/ outputs. Without rebuilding them first, edits to
    # those packages get silently dropped from the bundle.
    check_node_version "$NODE_VERSION_MIN"
    ensure_deps
    ensure_packages_built
    # The build-cli-executables script's slot for renet:
    #   private/bin/renet-${platform-key}-${goarch}  (linux only — that's
    #   what gets embedded; the SEA only ever runs on linux/mac/win but
    #   embeds a linux renet for remote provisioning).
    _ovr_embed_renet="$ROOT_DIR/private/bin/renet-linux-${_ovr_goarch}"
    log_step "Cross-building renet → $_ovr_embed_renet"
    mkdir -p "$ROOT_DIR/private/bin"
    (cd "$ROOT_DIR/private/renet" && \
        CGO_ENABLED=0 GOOS=linux GOARCH="$_ovr_goarch" go build \
            -tags nolicense \
            -ldflags="-s -w -X main.Version=0.0.0-dev" \
            -o "$_ovr_embed_renet" \
            ./cmd/renet)
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
    # Self-register as 'rdc' in ~/.local/bin so it's accessible from any terminal
    _local_bin="$HOME/.local/bin"
    mkdir -p "$_local_bin"
    if [[ "$(readlink "$_local_bin/rdc" 2>/dev/null)" != "$ROOT_DIR/rdc.sh" ]]; then
        ln -sf "$ROOT_DIR/rdc.sh" "$_local_bin/rdc"
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
    if node "$cli_dist" agent generate-reference > "$ref_tmp" 2>/dev/null && grep -q "^#" "$ref_tmp"; then
        mv "$ref_tmp" "$ref_file"
    else
        rm -f "$ref_tmp"
        log_warn "Skill reference generation failed (keeping existing)"
    fi
fi

# Add renet binary directory to PATH so CLI can find it
renet_bin_dir="$ROOT_DIR/private/renet/bin"
export PATH="$renet_bin_dir:$PATH"

# Three modes, mutually exclusive:
#   default       → local dev gateway on http://localhost:4812 (REDIACC_ENVIRONMENT=development)
#   RDC_PROD=1    → user's real config in ~/.config/rediacc (production servers)
#   RDC_BENCH=1   → bench.rediacc.com, our internal real-D1 test environment.
#                   Uses a separate token file under .rdc-bench/ so it never
#                   collides with the local-dev or production token state.
#                   Deploy/reset bench via scripts/dev/{deploy,reset}-bench.sh.
if [[ "${RDC_BENCH:-0}" == "1" ]]; then
    export REDIACC_SUBSCRIPTION_TOKEN_FILE="$ROOT_DIR/.rdc-bench/api-token.json"
    export REDIACC_ACCOUNT_SERVER="https://bench.rediacc.com"
    unset REDIACC_SKIP_MACHINE_ACTIVATION
    mkdir -p "$ROOT_DIR/.rdc-bench"
    log_info "Renet available at: $renet_bin_dir/renet"
    log_step "Starting CLI (bench config — bench.rediacc.com)"
elif [[ "${RDC_PROD:-0}" == "1" ]]; then
    log_info "Renet available at: $renet_bin_dir/renet"
    log_step "Starting CLI (prod config)"
else
    export REDIACC_ENVIRONMENT=development
    export REDIACC_SUBSCRIPTION_TOKEN_FILE="$ROOT_DIR/.rdc-dev/api-token.json"

    if [[ "${REDIACC_SKIP_MACHINE_ACTIVATION:-0}" != "1" ]]; then
        log_info "Renet available at: $renet_bin_dir/renet"
    fi

    # Load account env if available (provides REDIACC_ACCOUNT_SERVER for subscription commands)
    account_env="$ROOT_DIR/private/account/.env"
    if [[ -f "$account_env" ]]; then
        set -a
        source "$account_env"
        set +a
    fi

    if [[ "${REDIACC_SKIP_MACHINE_ACTIVATION:-0}" != "1" ]]; then
        log_step "Starting CLI (dev mode)"
    fi
fi

# Run the compiled CLI bundle, passing through all arguments
node "$ROOT_DIR/packages/cli/dist/cli-bundle.cjs" "$@"
