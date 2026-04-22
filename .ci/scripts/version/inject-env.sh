#!/bin/bash
# Central version injector: exports APP_VERSION, VITE_APP_VERSION, CLI_VERSION
# as a single synchronized value. Every build boundary sources this so there
# is exactly one place that decides what version an artifact ships with.
#
# Usage:
#   # Source to export env vars into current shell
#   source .ci/scripts/version/inject-env.sh
#   source .ci/scripts/version/inject-env.sh --version 1.2.3
#   source .ci/scripts/version/inject-env.sh --strict
#
#   # Or run standalone to echo the resolved version
#   .ci/scripts/version/inject-env.sh --print
#
# Resolution order:
#   1. --version X.Y.Z flag               (explicit caller intent)
#   2. $VERSION env var                   (already set by outer script)
#   3. resolve-version.sh --current       (latest git tag)
#   4. "0.0.0-dev"                        (local dev fallback)
#
# Flags:
#   --strict    fail non-zero if version resolves to 0.0.0-dev (required in CI)
#   --version   explicit version override
#   --print     print resolved version to stdout (for standalone use)
#
# In CI (env CI=true), callers should pass --strict so a missed resolver
# returns exit 1 instead of silently shipping 0.0.0-dev.

set -euo pipefail

_IE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

_IE_VERSION_OVERRIDE=""
_IE_STRICT=false
_IE_PRINT=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)
            _IE_VERSION_OVERRIDE="${2:-}"
            shift 2
            ;;
        --strict)
            _IE_STRICT=true
            shift
            ;;
        --print)
            _IE_PRINT=true
            shift
            ;;
        *)
            echo "inject-env.sh: unknown arg: $1" >&2
            return 1 2>/dev/null || exit 1
            ;;
    esac
done

_ie_resolve() {
    if [[ -n "$_IE_VERSION_OVERRIDE" ]]; then
        echo "$_IE_VERSION_OVERRIDE"
        return 0
    fi
    if [[ -n "${VERSION:-}" ]]; then
        echo "$VERSION"
        return 0
    fi
    if v=$("$_IE_DIR/resolve-version.sh" --current 2>/dev/null); then
        echo "$v"
        return 0
    fi
    echo "0.0.0-dev"
}

_IE_RESOLVED=$(_ie_resolve)

if [[ "$_IE_STRICT" == "true" && "$_IE_RESOLVED" == "0.0.0-dev" ]]; then
    echo "inject-env.sh: version resolved to 0.0.0-dev under --strict (did the checkout include tags?)" >&2
    return 1 2>/dev/null || exit 1
fi

export APP_VERSION="$_IE_RESOLVED"
export VITE_APP_VERSION="$_IE_RESOLVED"
export CLI_VERSION="$_IE_RESOLVED"
# TAG is the legacy name used by renet/build.sh and some Docker builds.
export TAG="$_IE_RESOLVED"

if [[ "$_IE_PRINT" == "true" ]]; then
    echo "$_IE_RESOLVED"
fi

unset _IE_DIR _IE_VERSION_OVERRIDE _IE_STRICT _IE_PRINT _IE_RESOLVED
