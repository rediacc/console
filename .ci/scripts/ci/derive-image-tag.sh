#!/bin/bash
# Derive Docker image tag from Git ref or explicit input
#
# Logic:
#   1. If explicit version provided via --version → use it
#   2. If running from a Git tag (GITHUB_REF_TYPE=tag) → use tag name
#   3. If running from a branch → use 'latest'
#
# Usage:
#   derive-image-tag.sh                           # Auto-derive to stdout
#   derive-image-tag.sh --version v1.2.3          # Explicit version
#   derive-image-tag.sh --github-output           # Write to GITHUB_OUTPUT
#   derive-image-tag.sh --env-file                # Write TAG vars to GITHUB_ENV
#
# Environment variables (from GitHub Actions):
#   GITHUB_REF_TYPE  - 'branch' or 'tag'
#   GITHUB_REF_NAME  - Branch or tag name
#   GITHUB_OUTPUT    - Path to output file (for --github-output)
#   GITHUB_ENV       - Path to env file (for --env-file)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Defaults
VERSION=""
GITHUB_OUTPUT_MODE=false
ENV_FILE_MODE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)
            VERSION="${2?--version requires an argument}"
            shift 2
            ;;
        --github-output)
            GITHUB_OUTPUT_MODE=true
            shift
            ;;
        --env-file)
            ENV_FILE_MODE=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Derive Docker image tag from Git ref or explicit input."
            echo ""
            echo "Options:"
            echo "  --version TAG      Use explicit version tag"
            echo "  --github-output    Write 'tag=VALUE' to GITHUB_OUTPUT"
            echo "  --env-file         Write TAG, API_TAG, WEB_TAG, BRIDGE_TAG to GITHUB_ENV"
            echo "  -h, --help         Show this help message"
            echo ""
            echo "Auto-derivation (when --version not provided):"
            echo "  - Git tag (e.g., v1.2.3)  → uses tag name"
            echo "  - Branch (e.g., main)     → uses 'latest'"
            echo ""
            echo "Examples:"
            echo "  $0                              # Auto-derive, output to stdout"
            echo "  $0 --version v1.2.3             # Explicit: v1.2.3"
            echo "  $0 --env-file                   # Auto-derive, set GITHUB_ENV vars"
            echo "  $0 --version latest --env-file  # Explicit with env export"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Determine version
if [[ -n "$VERSION" ]]; then
    # Explicit version provided
    TAG="$VERSION"
    log_info "Using explicit version: $TAG" >&2
elif [[ "${GITHUB_REF_TYPE:-}" == "tag" ]]; then
    # Running from a Git tag - GITHUB_REF_NAME must be set
    TAG="${GITHUB_REF_NAME?GITHUB_REF_NAME is not set for a tag build}"
    log_info "Auto-derived from tag: $TAG" >&2
else
    # Running from a branch (or local/unknown)
    TAG="latest"
    BRANCH="${GITHUB_REF_NAME:-local}"
    log_info "Auto-derived from branch ($BRANCH): $TAG" >&2
fi

# Validate tag format (alphanumeric, dots, hyphens, underscores)
if [[ ! "$TAG" =~ ^[a-zA-Z0-9._-]+$ ]]; then
    log_error "Invalid tag format: $TAG"
    log_error "Tags must contain only alphanumeric characters, dots, hyphens, and underscores"
    exit 1
fi

# Validate length (Docker tags max 128 chars)
if [[ ${#TAG} -gt 128 ]]; then
    log_error "Tag too long: ${#TAG} characters (max 128)"
    exit 1
fi

# Output to GITHUB_OUTPUT if requested
if [[ "$GITHUB_OUTPUT_MODE" == "true" ]]; then
    if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
        echo "tag=$TAG" >> "$GITHUB_OUTPUT"
        log_info "Set GITHUB_OUTPUT: tag=$TAG" >&2
    else
        log_warn "GITHUB_OUTPUT not set, skipping --github-output" >&2
    fi
fi

# Output to GITHUB_ENV if requested
if [[ "$ENV_FILE_MODE" == "true" ]]; then
    if [[ -n "${GITHUB_ENV:-}" ]]; then
        {
            echo "TAG=$TAG"
            echo "API_TAG=$TAG"
            echo "WEB_TAG=$TAG"
            echo "BRIDGE_TAG=$TAG"
        } >> "$GITHUB_ENV"
        log_info "Set GITHUB_ENV: TAG=$TAG, API_TAG=$TAG, WEB_TAG=$TAG, BRIDGE_TAG=$TAG" >&2
    else
        log_warn "GITHUB_ENV not set, skipping --env-file" >&2
    fi
fi

# Always output to stdout
echo "$TAG"
