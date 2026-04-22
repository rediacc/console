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
#
# This file is meant to be sourced. All logic is wrapped in a function so
# `set -euo pipefail` stays scoped to this script and does not leak into the
# caller shell. The function and helpers are unset before returning so the
# caller's namespace stays clean even on early-return paths.

_inject_env_main() {
    set -euo pipefail

    local _ie_dir
    _ie_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    local _ie_version_override=""
    local _ie_strict=false
    local _ie_print=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --version)
                if [[ $# -lt 2 ]]; then
                    echo "inject-env.sh: --version requires an argument" >&2
                    return 1
                fi
                _ie_version_override="$2"
                shift 2
                ;;
            --strict)
                _ie_strict=true
                shift
                ;;
            --print)
                _ie_print=true
                shift
                ;;
            *)
                echo "inject-env.sh: unknown arg: $1" >&2
                return 1
                ;;
        esac
    done

    local _ie_resolved
    if [[ -n "$_ie_version_override" ]]; then
        _ie_resolved="$_ie_version_override"
    elif [[ -n "${VERSION:-}" ]]; then
        _ie_resolved="$VERSION"
    elif _ie_resolved="$("$_ie_dir/resolve-version.sh" --current 2>/dev/null)"; then
        :
    else
        _ie_resolved="0.0.0-dev"
    fi

    if [[ "$_ie_strict" == "true" && "$_ie_resolved" == "0.0.0-dev" ]]; then
        echo "inject-env.sh: version resolved to 0.0.0-dev under --strict (did the checkout include tags?)" >&2
        return 1
    fi

    export APP_VERSION="$_ie_resolved"
    export VITE_APP_VERSION="$_ie_resolved"
    export CLI_VERSION="$_ie_resolved"
    # TAG is the legacy name used by renet/build.sh and some Docker builds.
    export TAG="$_ie_resolved"

    if [[ "$_ie_print" == "true" ]]; then
        echo "$_ie_resolved"
    fi
}

if _inject_env_main "$@"; then
    unset -f _inject_env_main
    return 0 2>/dev/null || exit 0
else
    _ie_st=$?
    unset -f _inject_env_main
    return "$_ie_st" 2>/dev/null || exit "$_ie_st"
fi
