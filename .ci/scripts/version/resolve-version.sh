#!/bin/bash
# Resolve version from git tags (replaces file-based versioning).
#
# Uses the latest v* tag as the current version and calculates the next
# version based on semver bump type.
#
# Usage:
#   resolve-version.sh --current          # Output current version (e.g., 0.8.2)
#   resolve-version.sh --bump-type patch  # Output next patch (e.g., 0.8.3)
#   resolve-version.sh --bump-type minor  # Output next minor (e.g., 0.9.0)
#   resolve-version.sh --bump-type major  # Output next major (e.g., 1.0.0)
#
# Exit codes:
#   0 - Success
#   1 - Error

set -euo pipefail

BUMP_TYPE=""
CURRENT_ONLY=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --current)
            CURRENT_ONLY=true
            shift
            ;;
        --bump-type)
            BUMP_TYPE="$2"
            shift 2
            ;;
        *)
            echo "Usage: resolve-version.sh [--current | --bump-type patch|minor|major]" >&2
            exit 1
            ;;
    esac
done

# Get latest version tag
LATEST_TAG=$(git describe --tags --match 'v*' --abbrev=0 2>/dev/null || echo "v0.0.0")
CURRENT="${LATEST_TAG#v}"

if [[ "$CURRENT_ONLY" == "true" ]]; then
    echo "$CURRENT"
    exit 0
fi

if [[ -z "$BUMP_TYPE" ]]; then
    echo "Error: --bump-type or --current required" >&2
    exit 1
fi

# Parse semver
IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT"

case "$BUMP_TYPE" in
    patch)
        PATCH=$((PATCH + 1))
        ;;
    minor)
        MINOR=$((MINOR + 1))
        PATCH=0
        ;;
    major)
        MAJOR=$((MAJOR + 1))
        MINOR=0
        PATCH=0
        ;;
    *)
        echo "Error: invalid bump type '$BUMP_TYPE' (expected patch, minor, or major)" >&2
        exit 1
        ;;
esac

echo "${MAJOR}.${MINOR}.${PATCH}"
