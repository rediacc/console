#!/bin/bash
# Generate CI tags for Docker images
#
# Modes:
#   1. Time-based (default): YYYYMMDD-HHMMSS (UTC)
#   2. Submodule commit hash: Short git commit hash of a submodule
#
# Usage:
#   generate-tag.sh                         # Time-based tag to stdout
#   generate-tag.sh --output file.txt       # Write to file
#   generate-tag.sh --github-output         # Write to GITHUB_OUTPUT
#   generate-tag.sh --submodule path/to/sub # Get submodule commit hash
#   generate-tag.sh --self                  # Get current repo commit hash

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

OUTPUT_FILE=""
GITHUB_OUTPUT_MODE=false
SUBMODULE_PATH=""
SELF_MODE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        --github-output)
            GITHUB_OUTPUT_MODE=true
            shift
            ;;
        --submodule)
            SUBMODULE_PATH="$2"
            shift 2
            ;;
        --self)
            SELF_MODE=true
            shift
            ;;
        -h | --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Modes:"
            echo "  (default)              Generate time-based tag (YYYYMMDD-HHMMSS)"
            echo "  --submodule PATH       Get commit hash of specified submodule"
            echo "  --self                 Get commit hash of current repository"
            echo ""
            echo "Options:"
            echo "  --output FILE          Write tag to specified file"
            echo "  --github-output        Write to GITHUB_OUTPUT for GitHub Actions"
            echo "  -h, --help             Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                                    # -> 20260120-104603"
            echo "  $0 --submodule private/middleware     # -> fb33b0f"
            echo "  $0 --self                             # -> c909b05"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Determine tag based on mode
if [[ -n "$SUBMODULE_PATH" ]]; then
    # Submodule commit hash mode with build config hash
    # Includes both submodule code AND build configuration to trigger rebuilds
    # when Dockerfiles or CI workflows change
    if [[ ! -d "$SUBMODULE_PATH" ]]; then
        log_error "Submodule not found: $SUBMODULE_PATH"
        exit 1
    fi

    if [[ ! -d "$SUBMODULE_PATH/.git" ]] && [[ ! -f "$SUBMODULE_PATH/.git" ]]; then
        log_error "Not a git repository: $SUBMODULE_PATH"
        exit 1
    fi

    SUBMODULE_COMMIT=$(git -C "$SUBMODULE_PATH" rev-parse --short HEAD)

    # Include build config files in tag hash (Dockerfiles, CI build workflow)
    BUILD_CONFIG_HASH=""
    BUILD_CONFIG_FILES=(
        "$SUBMODULE_PATH/Dockerfile"
        "$SUBMODULE_PATH/Dockerfile.native"
        ".github/workflows/ci-build.yml"
        ".ci/scripts/docker/build-native-binaries.sh"
    )
    for f in "${BUILD_CONFIG_FILES[@]}"; do
        if [[ -f "$f" ]]; then
            BUILD_CONFIG_HASH+=$(sha256sum "$f" 2>/dev/null | cut -c1-8)
        fi
    done

    # Combine submodule commit with build config hash (first 7 chars each)
    if [[ -n "$BUILD_CONFIG_HASH" ]]; then
        CONFIG_SHORT=$(echo -n "$BUILD_CONFIG_HASH" | sha256sum | cut -c1-3)
        CI_TAG="${SUBMODULE_COMMIT}-${CONFIG_SHORT}"
    else
        CI_TAG="$SUBMODULE_COMMIT"
    fi
    # Log to stderr so it doesn't interfere with captured stdout
    log_info "Generated submodule tag ($SUBMODULE_PATH): $CI_TAG" >&2

elif [[ "$SELF_MODE" == "true" ]]; then
    # Current repo commit hash mode
    CI_TAG=$(git rev-parse --short HEAD)
    log_info "Generated self tag: $CI_TAG" >&2

else
    # Time-based mode (default)
    CI_TAG=$(date -u +%Y%m%d-%H%M%S)
    log_info "Generated CI tag: $CI_TAG" >&2
fi

# Output to file if requested
if [[ -n "$OUTPUT_FILE" ]]; then
    echo "$CI_TAG" >"$OUTPUT_FILE"
    log_info "Wrote CI tag to: $OUTPUT_FILE" >&2
fi

# Output to GITHUB_OUTPUT if requested
if [[ "$GITHUB_OUTPUT_MODE" == "true" ]] && [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    echo "ci_tag=$CI_TAG" >>"$GITHUB_OUTPUT"
    log_info "Set GITHUB_OUTPUT: ci_tag=$CI_TAG" >&2
fi

# Always output to stdout
echo "$CI_TAG"
