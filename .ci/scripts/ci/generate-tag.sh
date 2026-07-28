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
            echo "  $0 --submodule private/renet          # -> fb33b0f"
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
    #
    # MEMBERSHIP RULE: a file belongs here when its content determines the
    # CONTENT OF THE PUBLISHED IMAGE this tag names. The tag is what
    # initialize.sh checks against GHCR to decide `renet_exists`, so an input
    # missing from this list means a changed build produces an existing tag and
    # a stale image is reused; an input that does NOT affect the image means a
    # harmless edit costs a 45-minute rebuild.
    #
    # NOT IN THE LIST, DELIBERATELY: .ci/scripts/infra/build-renet.sh. It looks
    # like it belongs (nine CI steps run it: eight in ct-tests.yml, one in
    # ci-ops-test.yml, against one step here for the build/ script). It does not.
    # It compiles a dev binary from source into private/renet/bin for those test
    # jobs, which never pull ghcr.io/rediacc/renet and are never handed this tag
    # -- ct-tests.yml takes only full_suite and pointer_bump_only, and its own
    # cache is keyed on private/renet/embed-assets.lock.json. Its edits take
    # effect immediately in all nine, so there is nothing here to invalidate.
    #
    # The first three entries are already covered by SUBMODULE_COMMIT above
    # (they live inside the submodule). They are kept because they cost nothing
    # and make the intent readable.
    BUILD_CONFIG_HASH=""
    BUILD_CONFIG_FILES=(
        "$SUBMODULE_PATH/Dockerfile"
        "$SUBMODULE_PATH/Dockerfile.native"
        "$SUBMODULE_PATH/build.sh"
        ".github/workflows/ci-build-renet.yml"
        ".github/workflows/ci-build-docker.yml"
        ".ci/scripts/build/build-renet.sh"
    )
    # A missing entry used to be skipped in silence. That is the failure mode
    # this list is most exposed to: rename or move one of these files and the
    # hash quietly stops covering it, while STILL minting a brand-new tag (the
    # remaining digests concatenate differently), so the one visible symptom --
    # a cache miss -- looks like normal behaviour. Renames happen: there are two
    # build-renet.sh scripts in this repo, in .ci/scripts/build/ and
    # .ci/scripts/infra/. Fail loudly instead.
    for f in "${BUILD_CONFIG_FILES[@]}"; do
        if [[ ! -f "$f" ]]; then
            log_error "Build-config input not found: $f"
            log_error "This file is hashed into the renet image tag. A missing entry silently"
            log_error "narrows what the tag covers, so a changed build can reuse a stale image."
            log_error "Fix the path in BUILD_CONFIG_FILES, or delete the entry if the file is gone."
            exit 1
        fi
        BUILD_CONFIG_HASH+=$(sha256sum "$f" | cut -c1-8)
    done

    # Combine the submodule commit with a hash of the build config. Keep 12 hex
    # chars (48 bits): the old 3-char (12-bit, 4096-value) hash collided often
    # enough that a build-config change could map to an existing tag and silently
    # reuse a stale image built from a DIFFERENT Dockerfile/workflow. 12 chars
    # makes that collision negligible.
    if [[ -n "$BUILD_CONFIG_HASH" ]]; then
        CONFIG_SHORT=$(echo -n "$BUILD_CONFIG_HASH" | sha256sum | cut -c1-12)
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
