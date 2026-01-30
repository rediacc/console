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
source "$ROOT_DIR/.ci/scripts/lib/common.sh"

# Backward compatibility: Load parent .env if exists
if [[ -f "$ROOT_DIR/../.env" ]]; then
    set +u  # Disable unset variable errors temporarily
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
ensure_deps() {
    if [[ ! -d "$ROOT_DIR/node_modules" ]] || \
       [[ "$ROOT_DIR/package-lock.json" -nt "$ROOT_DIR/node_modules" ]]; then
        log_step "Installing dependencies..."
        npm install
    fi
}

# Ensure shared packages are built (required before tests)
ensure_packages_built() {
    local shared_dist="$ROOT_DIR/packages/shared/dist"
    local shared_src="$ROOT_DIR/packages/shared/src"

    # Check if shared package needs rebuilding
    if [[ ! -d "$shared_dist" ]] || \
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

    # Build renet using the Go build script (handles embed_assets automatically)
    (cd "$renet_dir" && ./go dev)

    if [[ ! -f "$renet_bin" ]]; then
        log_error "Renet build failed: binary not found at $renet_bin"
        exit 1
    fi

    log_info "Renet built successfully"
}

# =============================================================================
# BACKEND COMMANDS
# =============================================================================

backend_start() {
    local mode="${BACKEND_MODE_DEFAULT}"

    # Parse --source flag
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --source)
                mode="$2"
                shift 2
                ;;
            --source=*)
                mode="${1#*=}"
                shift
                ;;
            *)
                shift
                ;;
        esac
    done

    log_step "Starting backend (mode: $mode)"

    # Ensure elite repo exists
    elite_clone || exit 1

    # Mode-specific preparation
    case "$mode" in
        "$BACKEND_MODE_GHCR")
            elite_pull_images || exit 1
            ;;
        "$BACKEND_MODE_LOCAL")
            elite_update || exit 1
            elite_build_images || exit 1
            ;;
        *)
            log_error "Unknown backend mode: $mode"
            log_info "Valid modes: $BACKEND_MODE_GHCR, $BACKEND_MODE_LOCAL"
            exit 1
            ;;
    esac

    # Start services
    elite_start "$mode" || exit 1

    # Wait for health check
    elite_health || exit 1

    log_info "Backend is ready!"
    log_info "API URL: $API_URL_LOCAL"
}

backend_stop() {
    elite_stop
}

backend_status() {
    elite_status
}

backend_logs() {
    elite_logs "$@"
}

backend_health() {
    elite_health
}

backend_pull() {
    elite_pull_images
}

backend_reset() {
    elite_reset
}

# =============================================================================
# DEVELOPMENT COMMANDS
# =============================================================================

dev() {
    check_node_version

    # Check if backend is running
    if ! elite_health &>/dev/null; then
        log_warn "Backend is not running"
        log_info ""
        log_info "Start backend with:"
        log_info "  ./run.sh backend start        # Use ghcr images (CI mode)"
        log_info "  ./run.sh backend start --source local # Build from source"
        log_info ""

        if prompt_continue "Start backend now (ghcr mode)"; then
            backend_start --source "$BACKEND_MODE_GHCR"
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

# Run CLI in development mode with renet available
cli() {
    check_node_version

    log_step "Preparing CLI development environment"

    # Ensure npm dependencies are installed
    ensure_deps

    # Ensure shared packages are built
    ensure_packages_built

    # Ensure renet is built and up-to-date
    ensure_renet_built

    # Add renet binary directory to PATH so CLI can find it
    local renet_bin_dir="$ROOT_DIR/private/renet/bin"
    export PATH="$renet_bin_dir:$PATH"

    log_info "Renet available at: $renet_bin_dir/renet"
    log_step "Starting CLI (dev mode)"

    # Run CLI via tsx, passing through all arguments
    npx tsx "$ROOT_DIR/packages/cli/src/index.ts" "$@"
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
        if ! elite_health &>/dev/null; then
            log_error "Backend is not running or unhealthy"
            log_info "E2E tests require a running backend"
            log_info "Start backend with: ./run.sh backend start"
            log_info "Or use external backend: ./run.sh test e2e --backend <url>"
            exit 1
        fi
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

    # Choose backend mode
    echo ""
    echo "Select backend mode:"
    echo "  1) ghcr - Pull from ghcr.io (CI mode, fastest)"
    echo "  2) local - Build from elite source (for elite development)"
    echo ""
    read -p "Choice [1-2]: " choice

    local mode="$BACKEND_MODE_GHCR"
    case "$choice" in
        2) mode="$BACKEND_MODE_LOCAL" ;;
        *) mode="$BACKEND_MODE_GHCR" ;;
    esac

    # Start backend
    backend_start --source "$mode"

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
  backend start [--source ghcr|local]  Start backend services
  backend stop                         Stop backend services
  backend status                       Show backend status
  backend logs [service]               Show service logs (api, sql, web, all)
  backend health                       Check backend health
  backend pull                         Pull latest ghcr images
  backend reset                        Reset backend (deletes data)

DEVELOPMENT COMMANDS:
  dev                 Start development server (auto-starts backend if needed)
  cli [args...]       Run CLI in dev mode (auto-builds renet with embeddings)
  sandbox             Start in sandbox mode (no backend required)
  worktree <cmd>      Manage git worktrees (create, prune, list)
  setup               Interactive setup wizard

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
  quality deps        Check for outdated dependencies
  quality audit       Run security audit (npm audit)
  quality shell       Run shellcheck on shell scripts
  quality all         Run all quality checks

FIX COMMANDS:
  fix format          Auto-fix code formatting
  fix lint            Auto-fix linting issues
  fix all             Auto-fix all issues

CHECK COMMANDS (PRE-PUSH):
  check quick         Fast checks (lint, format, types)
  check full          Full validation (quality + audit + tests)

MAINTENANCE:
  clean               Clean build artifacts
  setup               Interactive setup wizard
  help                Show this help message

QUICK START:
  ./run.sh setup          # One-time setup (chooses backend mode)
  ./run.sh dev            # Start web development
  ./run.sh cli auth login # Run CLI command in dev mode

REQUIREMENTS:
  Node.js v${NODE_VERSION_REQUIRED}.x (https://nodejs.org/)
  Go (for CLI/renet development)
  Docker (for backend, and first-time renet asset extraction)

ENVIRONMENT:
  GITHUB_TOKEN        GitHub personal access token (for ghcr.io auth)
  ELITE_LOCAL_PATH    Elite repository location (default: ~/.rediacc/elite)
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
                start) shift; backend_start "$@" ;;
                stop) backend_stop ;;
                status) backend_status ;;
                logs) shift; backend_logs "$@" ;;
                health) backend_health ;;
                pull) backend_pull ;;
                reset) backend_reset ;;
                *)
                    log_error "Unknown backend command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh backend [start|stop|status|logs|health|pull|reset]"
                    exit 1
                    ;;
            esac
            ;;

        # Development
        dev) dev ;;
        cli) shift; cli "$@" ;;
        sandbox) shift; sandbox "$@" ;;
        worktree) shift; "$ROOT_DIR/scripts/dev/worktree.sh" "$@" ;;
        setup) setup ;;

        # Tests
        test)
            shift
            case "${1:-}" in
                unit) shift; test_unit "$@" ;;
                cli) shift; test_cli "$@" ;;
                e2e) shift; test_e2e "$@" ;;
                bridge) shift; test_bridge "$@" ;;
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
                all|"") build_all ;;
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
                deps) quality_deps ;;
                actions) quality_actions ;;
                audit) quality_audit ;;
                shell) quality_shell ;;
                all|"") quality_all ;;
                *)
                    log_error "Unknown quality command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh quality [lint|format|types|deps|actions|audit|shell|all]"
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
                all|"") fix_all ;;
                *)
                    log_error "Unknown fix command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh fix [format|lint|all]"
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
        help|--help|-h|"") show_help ;;

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
