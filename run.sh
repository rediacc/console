#!/bin/bash
# Console development script
# Aligned with CI workflow from .github/workflows/ci.yml
#
# ⚠️  IMPORTANT: When updating this file:
# ⚠️  1. Check if CI scripts need updates (.ci/config/constants.sh, .ci/lib/elite-backend.sh)
# ⚠️  2. Update documentation (docs/BACKEND.md)
# ⚠️  3. Test all affected commands

set -euo pipefail

# Root directory
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source configuration and utilities
source "$ROOT_DIR/.ci/config/constants.sh"
source "$ROOT_DIR/.ci/lib/elite-backend.sh"
source "$ROOT_DIR/.ci/lib/service.sh"
source "$ROOT_DIR/.ci/scripts/lib/common.sh"

# Backward compatibility: Load parent .env if exists
if [[ -f "$ROOT_DIR/../.env" ]]; then
    set +u # Disable unset variable errors temporarily
    source "$ROOT_DIR/../.env"
    set -u
fi

# =============================================================================
# NODE VERSION CHECK
# =============================================================================

check_node_version() {
    if ! command -v node &>/dev/null; then
        log_error "Node.js is not installed"
        log_info "Install Node.js ${NODE_VERSION_REQUIRED} from: https://nodejs.org/"
        exit 1
    fi

    local current_version
    current_version=$(node -v | cut -d'v' -f2)
    local current_major
    current_major=$(echo "$current_version" | cut -d'.' -f1)

    if [[ "$current_major" != "$NODE_VERSION_REQUIRED" ]]; then
        log_error "Node.js version mismatch"
        log_error "Required: v${NODE_VERSION_REQUIRED}.x"
        log_error "Current:  v${current_version}"
        log_info "Install Node.js ${NODE_VERSION_REQUIRED} from: https://nodejs.org/"
        exit 1
    fi

    log_debug "Node.js version: v${current_version}"
}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

# Check if Docker is running
check_docker() {
    if ! command -v docker &>/dev/null; then
        log_error "Docker is not installed"
        log_info "Install Docker from: https://docs.docker.com/get-docker/"
        exit 1
    fi

    if ! docker info &>/dev/null; then
        log_error "Docker is not running"
        log_info "Start Docker Desktop or Docker daemon"
        exit 1
    fi
}

# Check if Go is installed (required for renet build)
check_go_installed() {
    if ! command -v go &>/dev/null; then
        log_error "Go is not installed (required for building renet)"
        log_info "Install Go from: https://go.dev/dl/"
        exit 1
    fi

    log_debug "Go version: $(go version)"
}

# Load environment file
load_env() {
    local env_file="$1"

    if [[ ! -f "$env_file" ]]; then
        log_warn "Environment file not found: $env_file"
        return 1
    fi

    # Export variables from .env file
    set -a
    source "$env_file"
    set +a

    log_debug "Loaded environment from: $env_file"
}

# Prompt user to continue (y/N)
prompt_continue() {
    local message="${1:-Continue}"
    local response

    read -p "$message? (y/N): " response
    [[ "$response" =~ ^[yY]$ ]]
}

# Ensure npm dependencies are installed
# Uses a sentinel file to avoid running npm install on every invocation.
# The sentinel is only outdated when package-lock.json actually changes.
ensure_deps() {
    local sentinel="$ROOT_DIR/node_modules/.deps-installed"
    if [[ ! -d "$ROOT_DIR/node_modules" ]] ||
        [[ ! -f "$sentinel" ]] ||
        [[ "$ROOT_DIR/package-lock.json" -nt "$sentinel" ]]; then
        log_step "Installing dependencies..."
        npm install --prefer-offline --no-audit --no-fund 2>&1 | tail -1
        touch "$sentinel"
    fi
}

# Ensure shared packages are built (required before tests)
ensure_packages_built() {
    local shared_dist="$ROOT_DIR/packages/shared/dist"
    local shared_src="$ROOT_DIR/packages/shared/src"

    # Check if shared package needs rebuilding
    if [[ ! -d "$shared_dist" ]] ||
        [[ -n "$(find "$shared_src" -newer "$shared_dist" -type f 2>/dev/null | head -1)" ]]; then
        log_step "Building shared packages..."
        "$ROOT_DIR/.ci/scripts/setup/build-packages.sh"
    else
        log_debug "Shared packages are up-to-date"
    fi
}

# Ensure renet binary is built and up-to-date
# Builds from Go source with embedded assets (CRIU, rsync)
# Only rebuilds when Go sources are newer than the binary
ensure_renet_built() {
    local renet_dir="$ROOT_DIR/private/renet"
    local renet_bin="$renet_dir/bin/renet"

    # Check if binary exists and sources haven't changed
    if [[ -f "$renet_bin" ]]; then
        local newer_files
        newer_files=$(find "$renet_dir" \
            \( -name "*.go" -o -name "go.mod" -o -name "go.sum" \) \
            -newer "$renet_bin" -type f 2>/dev/null | head -1)

        if [[ -z "$newer_files" ]]; then
            log_debug "Renet binary is up-to-date"
            return 0
        fi

        log_step "Renet sources changed, rebuilding..."
    else
        log_step "Building renet (first time, requires Docker for asset extraction)..."
    fi

    check_go_installed

    # Build renet using the build script (handles embed_assets automatically)
    (cd "$renet_dir" && ./build.sh dev)

    if [[ ! -f "$renet_bin" ]]; then
        log_error "Renet build failed: binary not found at $renet_bin"
        exit 1
    fi

    log_info "Renet built successfully"
}

# Ensure private/generative submodule is initialized
ensure_generative_submodule() {
    if [[ ! -d "$ROOT_DIR/private/generative" ]]; then
        log_error "Missing private/generative directory"
        exit 1
    fi

    if [[ ! -f "$ROOT_DIR/private/generative/.git" ]] && [[ ! -d "$ROOT_DIR/private/generative/.git" ]]; then
        log_step "Initializing private/generative submodule..."
        git submodule sync -- private/generative >/dev/null 2>&1 || true
        git submodule update --init --recursive private/generative
    fi
}

ensure_python_installed() {
    if ! command -v python3 &>/dev/null; then
        log_error "python3 is required for tutorial audio generation"
        exit 1
    fi
}

ensure_audio_system_deps() {
    local missing=()
    command -v ffmpeg >/dev/null 2>&1 || missing+=("ffmpeg")
    command -v ffprobe >/dev/null 2>&1 || missing+=("ffmpeg")
    command -v sox >/dev/null 2>&1 || missing+=("sox")

    if [[ "${#missing[@]}" -eq 0 ]]; then
        return 0
    fi

    if ! command -v apt-get >/dev/null 2>&1; then
        log_error "Missing system deps: ${missing[*]}"
        log_info "Install them manually (ffmpeg, sox) and retry."
        exit 1
    fi

    log_step "Installing missing system dependencies: ${missing[*]}"
    if command -v sudo >/dev/null 2>&1; then
        sudo apt-get update
        sudo apt-get install -y ffmpeg sox python3-venv python3-dev build-essential
    else
        apt-get update
        apt-get install -y ffmpeg sox python3-venv python3-dev build-essential
    fi
}

install_generative_python_deps() {
    local gen_dir="$1"
    local stamp_file="$2"
    local content_hash="$3"
    local site_packages=""

    site_packages="$(python -c 'import site; print(site.getsitepackages()[0])' 2>/dev/null || true)"
    if [[ -n "$site_packages" ]] && [[ -d "$site_packages" ]]; then
        find "$site_packages" -maxdepth 1 -name '~ransformers*' -exec rm -rf {} + 2>/dev/null || true
    fi

    pip install --upgrade pip
    pip install -e "$gen_dir"
    pip install qwen-tts
    pip install qwen-asr
    install_flash_attn_if_supported
    echo "$content_hash" >"$stamp_file"
}

install_flash_attn_if_supported() {
    # Best-effort accelerator install. Keep generation working even if unavailable.
    if python -c "import flash_attn" >/dev/null 2>&1; then
        log_debug "flash-attn already installed"
        return 0
    fi

    local has_cuda="false"
    has_cuda="$(python -c 'import torch; print("true" if torch.cuda.is_available() else "false")' 2>/dev/null || echo "false")"
    if [[ "$has_cuda" != "true" ]]; then
        log_info "Skipping flash-attn install (CUDA not available in torch)."
        return 0
    fi

    if ! command -v nvcc >/dev/null 2>&1; then
        log_info "Skipping flash-attn install (nvcc not found for source build)."
        return 0
    fi

    log_step "Installing flash-attn acceleration..."
    pip install --upgrade packaging ninja >/dev/null 2>&1 || true
    if ! pip install flash-attn --no-build-isolation; then
        log_warn "flash-attn install failed; continuing without it."
    fi
}

ensure_generative_venv() {
    local clean_venv="$1"
    local gen_dir="$ROOT_DIR/private/generative"
    local venv_dir="$gen_dir/.venv"
    local stamp_file="$venv_dir/.deps-sha256"
    local content_hash

    content_hash="$(
        cd "$gen_dir" &&
            sha256sum pyproject.toml src/tutorial_tts/*.py src/tutorial_tts/*.json | sha256sum | awk '{print $1}'
    )"

    if [[ "$clean_venv" == "true" && -d "$venv_dir" ]]; then
        log_step "Recreating generative Python environment..."
        rm -rf "$venv_dir"
    fi

    if [[ ! -d "$venv_dir" ]]; then
        log_step "Creating generative Python environment..."
        python3 -m venv "$venv_dir"
    fi

    # shellcheck disable=SC1091
    source "$venv_dir/bin/activate"

    if [[ ! -f "$stamp_file" ]] || [[ "$(cat "$stamp_file" 2>/dev/null || true)" != "$content_hash" ]]; then
        log_step "Installing generative Python dependencies..."
        if ! install_generative_python_deps "$gen_dir" "$stamp_file" "$content_hash"; then
            log_warn "Dependency install failed; recreating Python environment and retrying once..."
            deactivate || true
            rm -rf "$venv_dir"
            python3 -m venv "$venv_dir"
            # shellcheck disable=SC1091
            source "$venv_dir/bin/activate"
            install_generative_python_deps "$gen_dir" "$stamp_file" "$content_hash"
        fi
    else
        log_debug "Generative Python dependencies are up-to-date"
    fi
}

# Compute hash of a tutorial script + shared helpers for change detection
_tutorial_script_hash() {
    local script="$1"
    local helpers="$ROOT_DIR/.ci/tutorials/lib/tutorial-helpers.sh"
    cat "$script" "$helpers" 2>/dev/null | sha256sum | awk '{print $1}'
}

www_tutorials_record() {
    local force=false
    local name=""
    local tutorials_dir="$ROOT_DIR/.ci/tutorials"
    local output_dir="$ROOT_DIR/packages/www/public/assets/tutorials"
    local hash_file="$output_dir/.recording-hashes"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --force)
                force=true
                shift
                ;;
            *)
                name="$1"
                shift
                ;;
        esac
    done

    if ! command -v asciinema &>/dev/null; then
        log_error "asciinema is not installed. Install with: pip install asciinema"
        exit 1
    fi

    ensure_deps
    ensure_packages_built
    ensure_renet_built
    export PATH="$ROOT_DIR/private/renet/bin:$PATH"
    export TUTORIAL_RDC_CMD="npx tsx $ROOT_DIR/packages/cli/src/index.ts"

    # Load stored hashes
    local -A stored_hashes
    if [[ -f "$hash_file" ]]; then
        while IFS='=' read -r key val; do
            stored_hashes["$key"]="$val"
        done <"$hash_file"
    fi

    # Determine candidate scripts
    local candidates=()
    if [[ -n "$name" ]]; then
        local script="$tutorials_dir/${name}-tutorial.sh"
        [[ -f "$script" ]] || {
            log_error "Tutorial not found: $script"
            exit 1
        }
        candidates+=("$script")
    else
        for script in "$tutorials_dir"/*-tutorial.sh; do
            candidates+=("$script")
        done
    fi

    # Filter by change detection (unless --force)
    local scripts_to_record=()
    for script in "${candidates[@]}"; do
        local base
        base="$(basename "$script" .sh)"
        if [[ "$force" == "true" ]]; then
            scripts_to_record+=("$script")
        else
            local current_hash
            current_hash="$(_tutorial_script_hash "$script")"
            if [[ "${stored_hashes[$base]:-}" != "$current_hash" ]]; then
                scripts_to_record+=("$script")
            else
                log_debug "Unchanged: $base (skipping)"
            fi
        fi
    done

    if [[ ${#scripts_to_record[@]} -eq 0 ]]; then
        log_info "No tutorial scripts changed, skipping recording"
        return 0
    fi

    # Auto-provision VMs
    log_step "Provisioning VMs for tutorial recording..."
    provision_start

    # Record each changed tutorial
    for script in "${scripts_to_record[@]}"; do
        local base
        base="$(basename "$script" .sh)"
        log_step "Recording: $base"
        "$tutorials_dir/record.sh" "$script" "$output_dir/${base}.cast"

        # Update stored hash
        stored_hashes["$base"]="$(_tutorial_script_hash "$script")"
    done

    # Teardown VMs
    log_step "Tearing down VMs..."
    provision_stop

    # Persist hashes
    : >"$hash_file"
    for key in "${!stored_hashes[@]}"; do
        echo "${key}=${stored_hashes[$key]}" >>"$hash_file"
    done
}

www_tutorials_extract() {
    check_node_version
    ensure_deps
    log_step "Extracting cast markers to transcript scaffolds..."
    npm run transcripts:extract -w @rediacc/www
}

www_tutorials_scaffold_locales() {
    check_node_version
    ensure_deps
    log_step "Scaffolding locale transcript files..."
    npm run transcripts:scaffold-locales -w @rediacc/www
}

www_tutorials_generate() {
    check_node_version
    ensure_generative_submodule
    ensure_python_installed
    ensure_audio_system_deps

    local clean_venv=false
    local destroy_venv=false
    local passthrough=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --clean-venv)
                clean_venv=true
                shift
                ;;
            --destroy-venv)
                destroy_venv=true
                shift
                ;;
            *)
                passthrough+=("$1")
                shift
                ;;
        esac
    done

    ensure_generative_venv "$clean_venv"
    ensure_deps

    export QWEN_TTS_PYTHON_BIN="$ROOT_DIR/private/generative/.venv/bin/python"

    log_step "Generating tutorial audio assets..."
    npm run tutorials:tts:generate -w @rediacc/www -- "${passthrough[@]}"

    if [[ "$destroy_venv" == "true" ]]; then
        log_step "Destroying generative Python environment..."
        rm -rf "$ROOT_DIR/private/generative/.venv"
    fi
}

www_tutorials_validate() {
    check_node_version
    ensure_deps
    log_step "Validating tutorial transcripts..."
    npm run validate:tutorial-transcripts -w @rediacc/www
    log_step "Validating tutorial audio..."
    npm run validate:tutorial-audio -w @rediacc/www
}

www_tutorials_all() {
    log_step "Running full tutorial pipeline..."
    www_tutorials_record "$@"
    www_tutorials_extract
    www_tutorials_scaffold_locales
    www_tutorials_generate "$@"
    www_tutorials_validate
    log_info "Tutorial pipeline complete!"
}

# =============================================================================
# TEAM VIDEO COMMANDS
# =============================================================================

www_team_video_extract() {
    check_node_version
    ensure_generative_submodule
    ensure_python_installed
    ensure_audio_system_deps

    local passthrough=()
    local clean_venv=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --clean-venv)
                clean_venv=true
                shift
                ;;
            *)
                passthrough+=("$1")
                shift
                ;;
        esac
    done

    ensure_generative_venv "$clean_venv"
    ensure_deps

    export QWEN_TTS_PYTHON_BIN="$ROOT_DIR/private/generative/.venv/bin/python"

    log_step "Extracting team video transcripts via ASR..."
    npm run team-video:extract -w @rediacc/www -- "${passthrough[@]}"
}

www_team_video_scaffold_locales() {
    check_node_version
    ensure_deps
    log_step "Scaffolding team video locale transcript files..."
    npm run team-video:scaffold-locales -w @rediacc/www
}

www_team_video_generate() {
    check_node_version
    ensure_generative_submodule
    ensure_python_installed
    ensure_audio_system_deps

    local clean_venv=false
    local destroy_venv=false
    local passthrough=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --clean-venv)
                clean_venv=true
                shift
                ;;
            --destroy-venv)
                destroy_venv=true
                shift
                ;;
            *)
                passthrough+=("$1")
                shift
                ;;
        esac
    done

    ensure_generative_venv "$clean_venv"
    ensure_deps

    export QWEN_TTS_PYTHON_BIN="$ROOT_DIR/private/generative/.venv/bin/python"

    log_step "Generating team video audio assets..."
    npm run team-video:tts:generate -w @rediacc/www -- "${passthrough[@]}"

    if [[ "$destroy_venv" == "true" ]]; then
        log_step "Destroying generative Python environment..."
        rm -rf "$ROOT_DIR/private/generative/.venv"
    fi
}

www_team_video_validate() {
    check_node_version
    ensure_deps
    log_step "Validating team video transcripts..."
    npm run validate:team-video-transcripts -w @rediacc/www
}

www_team_video_all() {
    log_step "Running full team video pipeline..."
    www_team_video_extract "$@"
    www_team_video_scaffold_locales
    www_team_video_generate "$@"
    www_team_video_validate
    log_info "Team video pipeline complete!"
}

# =============================================================================
# WWW ALL
# =============================================================================

www_all() {
    log_step "Running full www asset pipeline..."
    www_tutorials_all "$@"
    www_team_video_all "$@"
    log_info "All www assets generated!"
}

# =============================================================================
# DEVELOPMENT COMMANDS
# =============================================================================

dev() {
    check_node_version

    # Check if backend is running
    if ! backend_health &>/dev/null; then
        log_warn "Backend is not running"
        log_info ""
        log_info "Start backend with: ./run.sh backend start"
        log_info ""

        if prompt_continue "Start backend now"; then
            backend_start
        else
            exit 1
        fi
    fi

    log_step "Starting console development server"

    # Install dependencies if needed
    if [[ ! -d "$ROOT_DIR/node_modules" ]] || [[ "$ROOT_DIR/package-lock.json" -nt "$ROOT_DIR/node_modules" ]]; then
        log_info "Installing dependencies"
        npm install
    fi

    # Set environment for Vite
    export VITE_API_URL="$API_URL_LOCAL"
    export REDIACC_BUILD_TYPE="$BUILD_TYPE_DEBUG"

    # Start dev server
    PORT="$PORT_CONSOLE_DEV" npm run dev
}


# Sandbox mode (no backend required) - preserved from original
sandbox() {
    check_node_version

    local USE_DOCKER=false
    local DOCKER_PORT=8080
    local OPEN_BROWSER=true

    # Parse arguments
    for arg in "$@"; do
        case $arg in
            --docker)
                USE_DOCKER=true
                ;;
            --port=*)
                DOCKER_PORT="${arg#*=}"
                ;;
            --no-browser)
                OPEN_BROWSER=false
                ;;
            --help)
                echo "Usage: ./run.sh sandbox [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --docker        Run in Docker container (recommended for quick start)"
                echo "  --port=PORT     Docker port (default: 8080)"
                echo "  --no-browser    Don't open browser automatically"
                echo ""
                echo "Examples:"
                echo "  ./run.sh sandbox              # Run locally with npm"
                echo "  ./run.sh sandbox --docker     # Run in Docker (recommended)"
                echo ""
                return 0
                ;;
        esac
    done

    if [[ "$USE_DOCKER" == "true" ]]; then
        # Docker mode
        check_docker

        log_step "Building and running containerized console"

        # Build the Docker image
        log_info "Building Docker image"
        docker build -t rediacc-console:sandbox \
            --build-arg REDIACC_BUILD_TYPE=DEBUG . || {
            log_error "Docker build failed"
            return 1
        }

        # Stop any existing container
        docker stop rediacc-console-sandbox 2>/dev/null || true
        docker rm rediacc-console-sandbox 2>/dev/null || true

        # Run the container
        log_info "Starting container on port ${DOCKER_PORT}"
        docker run -d \
            --name rediacc-console-sandbox \
            -p ${DOCKER_PORT}:80 \
            -e INSTANCE_NAME=sandbox \
            -e BUILD_TYPE=DEBUG \
            -e ENABLE_DEBUG=true \
            rediacc-console:sandbox

        # Wait for container to be ready
        local ready=false
        for i in {1..30}; do
            if curl -s http://localhost:${DOCKER_PORT}/health &>/dev/null; then
                ready=true
                break
            fi
            sleep 1
        done

        if [[ "$ready" == "true" ]]; then
            log_info "Console is running at: http://localhost:${DOCKER_PORT}"
        else
            log_warn "Console may not be fully ready yet"
        fi

        # Show logs
        docker logs -f rediacc-console-sandbox
    else
        # Local development mode
        log_step "Starting console in sandbox mode"
        log_info "API URL: $API_URL_SANDBOX"

        # Install dependencies if needed
        if [[ ! -d "$ROOT_DIR/node_modules" ]] || [[ "$ROOT_DIR/package-lock.json" -nt "$ROOT_DIR/node_modules" ]]; then
            log_info "Installing dependencies"
            npm install
        fi

        # Set environment for Vite
        export VITE_API_URL="$API_URL_SANDBOX"
        export REDIACC_BUILD_TYPE="$BUILD_TYPE_DEBUG"
        export SANDBOX_MODE=true

        # Start dev server
        PORT="${PORT_CONSOLE_DEV}" npm run dev
    fi
}

# =============================================================================
# TEST COMMANDS
# =============================================================================

test_unit() {
    check_node_version
    ensure_packages_built
    log_step "Running unit tests"
    "$ROOT_DIR/.ci/scripts/test/run-unit.sh" "$@"
}

test_cli() {
    check_node_version
    ensure_packages_built
    log_step "Running CLI tests"
    "$ROOT_DIR/.ci/scripts/test/run-cli.sh" "$@"
}

test_e2e() {
    check_node_version

    # Check if --backend is specified
    local has_backend=false
    for arg in "$@"; do
        [[ "$arg" == "--backend" || "$arg" == --backend=* ]] && has_backend=true
    done

    # Only require local backend if --backend not specified
    if [[ "$has_backend" == "false" ]]; then
        if ! backend_health &>/dev/null; then
            log_error "Backend is not running or unhealthy"
            log_info "E2E tests require a running backend"
            log_info "Start backend with: ./run.sh backend start"
            log_info "Or use external backend: ./run.sh test e2e --backend <url>"
            exit 1
        fi
        # Docker backend healthy on port 80 — inject --backend so Vite
        # proxies /api to http://localhost instead of default :7322
        log_info "Docker backend detected, using http://localhost"
        set -- "--backend" "http://localhost" "$@"
    fi

    log_step "Running E2E tests"
    "$ROOT_DIR/.ci/scripts/build/build-web.sh"
    "$ROOT_DIR/.ci/scripts/test/run-e2e.sh" "$@"
}

test_bridge() {
    check_node_version
    ensure_packages_built

    log_step "Running bridge tests"
    "$ROOT_DIR/.ci/scripts/test/run-bridge.sh" "$@"
}

test_all() {
    test_unit
    test_cli
    test_e2e --projects chromium
}

# =============================================================================
# BUILD COMMANDS
# =============================================================================

build_web() {
    check_node_version
    log_step "Building web application"
    "$ROOT_DIR/.ci/scripts/build/build-web.sh"
}

build_cli() {
    check_node_version
    log_step "Building CLI application"
    "$ROOT_DIR/.ci/scripts/build/build-cli.sh"
}

build_desktop() {
    check_node_version
    log_step "Building desktop application"
    "$ROOT_DIR/.ci/scripts/build/build-desktop.sh"
}

build_packages() {
    check_node_version
    log_step "Building shared packages"
    "$ROOT_DIR/.ci/scripts/setup/build-packages.sh"
}

build_renet() {
    check_go_installed
    log_step "Building renet binary"
    local renet_dir="$ROOT_DIR/private/renet"
    (cd "$renet_dir" && ./go dev)

    if [[ ! -f "$renet_dir/bin/renet" ]]; then
        log_error "Renet build failed"
        exit 1
    fi

    log_info "Renet built: private/renet/bin/renet"
}

build_all() {
    check_node_version
    log_step "Building all components"
    build_packages
    build_web
    build_cli
}

# =============================================================================
# QUALITY COMMANDS
# =============================================================================

quality_lint() {
    check_node_version
    log_step "Running lint checks"
    npm run lint -- --max-warnings 0
    npm run lint:unused
}

quality_format() {
    check_node_version
    log_step "Checking code formatting"
    npm run check:format
}

quality_types() {
    check_node_version
    log_step "Checking TypeScript types"
    npm run typecheck
}

quality_all() {
    check_node_version
    log_step "Running all quality checks"
    npm run quality

    # Shell formatting/linting (requires shfmt + shellcheck)
    if command -v shfmt &>/dev/null; then
        quality_shell
    else
        log_warn "shfmt not found — skipping shell checks (install: go install mvdan.cc/sh/v3/cmd/shfmt@latest)"
    fi
}

quality_deps() {
    check_node_version
    "$ROOT_DIR/.ci/scripts/quality/check-deps.sh"
}

quality_actions() {
    check_node_version
    log_step "Checking GitHub Actions versions..."
    node "$ROOT_DIR/scripts/check-actions.js"
}

quality_audit() {
    check_node_version
    "$ROOT_DIR/.ci/scripts/security/audit.sh"
}

quality_shell() {
    "$ROOT_DIR/.ci/scripts/security/shellcheck.sh"
    "$ROOT_DIR/.ci/scripts/security/shfmt.sh"
}

quality_submodules() {
    log_step "Checking submodule branch alignment"
    "$ROOT_DIR/.ci/scripts/quality/check-submodule-branches.sh"
}

# =============================================================================
# FIX COMMANDS
# =============================================================================

fix_format() {
    check_node_version
    log_step "Auto-fixing code formatting"
    npm run fix:format
}

fix_lint() {
    check_node_version
    log_step "Auto-fixing linting issues"
    npm run fix:lint
}

fix_all() {
    check_node_version
    log_step "Auto-fixing all issues"
    npm run fix:all
}

fix_shell() {
    log_step "Auto-fixing shell script formatting"
    if ! command -v shfmt &>/dev/null; then
        log_error "shfmt is not installed"
        log_info "Install with: go install mvdan.cc/sh/v3/cmd/shfmt@latest"
        exit 1
    fi
    find .ci -name "*.sh" -type f -exec shfmt -i 4 -ci -w {} +
    shfmt -i 4 -ci -w ./run.sh
    if [[ -d "scripts/dev" ]]; then
        find scripts/dev -name "*.sh" -type f -exec shfmt -i 4 -ci -w {} +
    fi
    log_success "Shell scripts formatted"
}

# =============================================================================
# CHECK COMMANDS (PRE-PUSH VALIDATION)
# =============================================================================

check_quick() {
    check_node_version
    log_step "Running quick checks"
    npm run check:lint || exit 1
    npm run check:format || exit 1
    npm run typecheck || exit 1
    log_info "Quick checks passed!"
}

check_full() {
    check_node_version
    log_step "Running full validation"

    log_step "Phase 1/3: Quality Checks"
    quality_all || exit 1

    log_step "Phase 2/3: Security Audit"
    quality_audit || exit 1

    log_step "Phase 3/3: Unit Tests"
    test_unit || exit 1

    log_info "Full validation passed!"
}

# =============================================================================
# SETUP
# =============================================================================

setup() {
    check_node_version

    log_step "Console development setup"
    echo ""

    # Install dependencies
    log_info "Installing npm dependencies"
    npm install

    # Start backend
    backend_start

    log_info ""
    log_info "Setup complete!"
    log_info ""
    log_info "Start development with: ./run.sh dev"
}

# =============================================================================
# CLEAN
# =============================================================================

clean() {
    log_step "Cleaning build artifacts"
    rm -rf dist/
    rm -rf node_modules/.vite
    rm -rf packages/*/dist/
    log_info "Build artifacts cleaned"
}

# =============================================================================
# HELP
# =============================================================================

show_help() {
    cat <<EOF
Usage: ./run.sh [COMMAND] [OPTIONS]

BACKEND COMMANDS:
  backend start              Start backend services
  backend stop               Stop backend services
  backend status             Show backend status
  backend logs [service]     Show service logs (api, sql, web, all)
  backend health             Check backend health
  backend pull               Pull latest ghcr images
  backend reset              Reset backend (deletes data)
  backend auto               Auto-start backend (idempotent, for devcontainer)

SERVICE COMMANDS:
  service start [port] [--no-build]  Build and run rediacc/web (default port: 8080)
  service stop                    Stop service containers
  service status                  Show service status
  service logs [container]        Show logs (web, rustfs, all)

ACCOUNT COMMANDS:
  account dev              Start account dev gateway (API + portal + www on one port)
  account test             Run account integration tests (vitest)
  account test e2e [opts]  Run account E2E tests (playwright, with Stripe wiring)
  account stop             Stop account Docker containers
  account setup            Generate .env + start infrastructure

PROVISION COMMANDS:
  provision start            Provision KVM VMs (bridge + workers)
  provision stop             Destroy all VMs
  provision status           Show VM status

DEVELOPMENT COMMANDS:
  dev                 Start development server (auto-starts backend if needed)
  (rdc)               Use ./rdc.sh instead (standalone CLI runner)
  sandbox             Start in sandbox mode (no backend required)
  worktree <cmd>      Manage git worktrees (create, switch, prune, list)
  setup               Interactive setup wizard

WWW COMMANDS:
  www all [opts]                    Full pipeline for tutorials + team videos

  www tutorials record [name]       Record .cast files (auto-provision, change-detected)
  www tutorials extract             Sync cast markers to transcripts (preserves text)
  www tutorials scaffold-locales    Sync locale transcripts with English
  www tutorials generate [opts]     Generate TTS audio + timelines (Python venv)
  www tutorials validate            Validate transcripts + audio integrity
  www tutorials all [opts]          Full tutorial pipeline (record -> extract -> generate)

  www team-video extract [opts]     ASR: extract English transcripts from video audio
  www team-video scaffold-locales   Sync locale transcripts with English
  www team-video generate [opts]    Generate dubbed audio + captions
  www team-video validate           Validate transcripts + audio integrity
  www team-video all [opts]         Full team video pipeline

TEST COMMANDS:
  test unit           Run unit tests
  test cli [opts]     Run CLI tests
  test e2e [opts]     Run E2E tests (requires backend)
  test bridge [opts]  Run bridge tests (requires VMs)
  test all            Run all tests

  Test Options (for e2e and cli):
    --backend <url|preset>  Use external backend instead of local
                            Presets: local, sandbox
                            Example: --backend https://xxx.trycloudflare.com
    --skip-health-check     Skip backend health validation

BUILD COMMANDS:
  build web           Build web application
  build cli           Build CLI application
  build renet         Build renet binary (Go, with embedded assets)
  build desktop       Build desktop application
  build packages      Build shared packages
  build all           Build everything

QUALITY COMMANDS:
  quality lint        Run linting (ESLint + Knip)
  quality format      Check code formatting (Biome)
  quality types       Check TypeScript types
  quality submodules  Check submodule branch alignment
  quality deps        Check for outdated dependencies
  quality audit       Run security audit (npm audit)
  quality shell       Run shellcheck on shell scripts
  quality all         Run all quality checks

FIX COMMANDS:
  fix format          Auto-fix code formatting
  fix lint            Auto-fix linting issues
  fix shell           Auto-fix shell script formatting (shfmt)
  fix all             Auto-fix all issues

CHECK COMMANDS (PRE-PUSH):
  check quick         Fast checks (lint, format, types)
  check full          Full validation (quality + audit + tests)

MAINTENANCE:
  clean               Clean build artifacts
  setup               Interactive setup wizard
  help                Show this help message

QUICK START:
  ./run.sh setup          # One-time setup
  ./run.sh dev            # Start web development
  ./rdc.sh auth login     # Run CLI command in dev mode

REQUIREMENTS:
  Node.js v${NODE_VERSION_REQUIRED}.x (https://nodejs.org/)
  Go (for CLI/renet development)
  Docker (for backend, and first-time renet asset extraction)

ENVIRONMENT:
  GITHUB_TOKEN        GitHub personal access token (for ghcr.io auth)
EOF
}

# =============================================================================
# MAIN DISPATCHER
# =============================================================================

main() {
    case "${1:-}" in
        # Backend commands
        backend)
            shift
            case "${1:-}" in
                start)
                    shift
                    backend_start "$@"
                    ;;
                stop) backend_stop ;;
                status) backend_status ;;
                logs)
                    shift
                    backend_logs "$@"
                    ;;
                health) backend_health ;;
                pull) backend_pull_images ;;
                reset) backend_reset ;;
                auto) backend_auto ;;
                *)
                    log_error "Unknown backend command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh backend [start|stop|status|logs|health|pull|reset|auto]"
                    exit 1
                    ;;
            esac
            ;;

        # Service mode (rediacc/web + RustFS)
        service)
            shift
            case "${1:-}" in
                start)
                    shift
                    service_start "$@"
                    ;;
                stop) service_stop ;;
                status) service_status ;;
                logs)
                    shift
                    service_logs "$@"
                    ;;
                *)
                    log_error "Unknown service command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh service [start|stop|status|logs]"
                    exit 1
                    ;;
            esac
            ;;

        # VM Provisioning
        provision)
            shift
            case "${1:-}" in
                start)
                    shift
                    provision_start "$@"
                    ;;
                stop) provision_stop ;;
                status) provision_status ;;
                auto) provision_auto ;;
                *)
                    log_error "Unknown provision command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh provision [start|stop|status|auto]"
                    exit 1
                    ;;
            esac
            ;;

        # Account server
        account)
            shift
            source "$ROOT_DIR/.ci/lib/account.sh"
            case "${1:-}" in
                dev) account_dev ;;
                test)
                    shift
                    case "${1:-}" in
                        e2e)
                            shift
                            account_test_e2e "$@"
                            ;;
                        *)
                            account_test "$@"
                            ;;
                    esac
                    ;;
                stop) account_stop ;;
                setup) account_setup ;;
                *)
                    log_error "Unknown account command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh account [dev|test|stop|setup]"
                    exit 1
                    ;;
            esac
            ;;

        # Development
        dev) dev ;;
        sandbox)
            shift
            sandbox "$@"
            ;;
        worktree)
            shift
            "$ROOT_DIR/scripts/dev/worktree.sh" "$@"
            ;;
        setup) setup ;;
        www)
            shift
            case "${1:-}" in
                tutorials)
                    shift
                    case "${1:-}" in
                        record)
                            shift
                            www_tutorials_record "$@"
                            ;;
                        extract) www_tutorials_extract ;;
                        scaffold-locales) www_tutorials_scaffold_locales ;;
                        generate)
                            shift
                            www_tutorials_generate "$@"
                            ;;
                        validate) www_tutorials_validate ;;
                        all)
                            shift
                            www_tutorials_all "$@"
                            ;;
                        *)
                            log_error "Unknown tutorials command: ${1:-}"
                            echo ""
                            echo "Usage: ./run.sh www tutorials [record|extract|scaffold-locales|generate|validate|all]"
                            exit 1
                            ;;
                    esac
                    ;;
                team-video)
                    shift
                    case "${1:-}" in
                        extract)
                            shift
                            www_team_video_extract "$@"
                            ;;
                        scaffold-locales) www_team_video_scaffold_locales ;;
                        generate)
                            shift
                            www_team_video_generate "$@"
                            ;;
                        validate) www_team_video_validate ;;
                        all)
                            shift
                            www_team_video_all "$@"
                            ;;
                        *)
                            log_error "Unknown team-video command: ${1:-}"
                            echo ""
                            echo "Usage: ./run.sh www team-video [extract|scaffold-locales|generate|validate|all]"
                            exit 1
                            ;;
                    esac
                    ;;
                all)
                    shift
                    www_all "$@"
                    ;;
                *)
                    log_error "Unknown www command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh www [all|tutorials|team-video] ..."
                    exit 1
                    ;;
            esac
            ;;

        # Tests
        test)
            shift
            case "${1:-}" in
                unit)
                    shift
                    test_unit "$@"
                    ;;
                cli)
                    shift
                    test_cli "$@"
                    ;;
                e2e)
                    shift
                    test_e2e "$@"
                    ;;
                bridge)
                    shift
                    test_bridge "$@"
                    ;;
                all) test_all ;;
                *)
                    log_error "Unknown test command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh test [unit|cli|e2e|bridge|all]"
                    exit 1
                    ;;
            esac
            ;;

        # Build
        build)
            shift
            case "${1:-}" in
                web) build_web ;;
                cli) build_cli ;;
                renet) build_renet ;;
                desktop) build_desktop ;;
                packages) build_packages ;;
                all | "") build_all ;;
                *)
                    log_error "Unknown build command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh build [web|cli|renet|desktop|packages|all]"
                    exit 1
                    ;;
            esac
            ;;

        # Quality
        quality)
            shift
            case "${1:-}" in
                lint) quality_lint ;;
                format) quality_format ;;
                types) quality_types ;;
                submodules) quality_submodules ;;
                deps) quality_deps ;;
                actions) quality_actions ;;
                audit) quality_audit ;;
                shell) quality_shell ;;
                all | "") quality_all ;;
                *)
                    log_error "Unknown quality command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh quality [lint|format|types|submodules|deps|actions|audit|shell|all]"
                    exit 1
                    ;;
            esac
            ;;

        # Fix
        fix)
            shift
            case "${1:-}" in
                format) fix_format ;;
                lint) fix_lint ;;
                shell) fix_shell ;;
                all | "") fix_all ;;
                *)
                    log_error "Unknown fix command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh fix [format|lint|shell|all]"
                    exit 1
                    ;;
            esac
            ;;

        # Check
        check)
            shift
            case "${1:-}" in
                quick) check_quick ;;
                full) check_full ;;
                *)
                    log_error "Unknown check command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh check [quick|full]"
                    exit 1
                    ;;
            esac
            ;;

        # Maintenance
        clean) clean ;;
        help | --help | -h | "") show_help ;;

        *)
            log_error "Unknown command: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# Execute main if run directly
[[ "${BASH_SOURCE[0]}" == "${0}" ]] && main "$@"
