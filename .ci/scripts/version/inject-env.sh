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
#   --strict    fail non-zero unless the version is a real, publishable version
#   --version   explicit version override (an EMPTY value is always an error)
#   --print     print resolved version to stdout (for standalone use)
#
# WHO PASSES --strict, and why it is not "everyone". Until 2026-08-07 nothing
# passed it at all: every build boundary spelled its own `|| '0.0.0-dev'` or
# `${CLI_VERSION:-0.0.0-dev}` inline, so the one guard against building a
# placeholder version into a publishable artifact had zero callers and could
# not fire. The seam is now the RELEASE PATH, not "CI":
#
#   push-to-main  -> ci-build-cli.yml / ci-build-docker.yml run a preflight
#                    `inject-env.sh --version "$NEXT_VERSION" --strict --print`,
#                    and build-cli-executables.sh / build-cli-musl.sh source
#                    this file with --strict via RELEASE_BUILD=true. These are
#                    the only artifacts CD ever promotes.
#   PR CI, forks, local `./rdc.sh --native`
#                 -> no --strict, 0.0.0-dev fallback intact, no ceremony.
#
# --strict rejects three things, not one: the 0.0.0-dev placeholder, an EMPTY
# version (the original check compared only against the literal string, so ""
# sailed through it), and anything that is not a dotted numeric version.
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
    local _ie_version_given=false
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
                _ie_version_given=true
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

    # An explicitly-supplied empty version is never a version. Falling through
    # to the resolver here is what let a release-path caller whose next_version
    # was empty quietly pick up the CURRENT tag (the version already published)
    # instead of the one it meant to build.
    if [[ "$_ie_version_given" == "true" && -z "$_ie_version_override" ]]; then
        echo "inject-env.sh: --version was given an empty value" >&2
        return 1
    fi

    local _ie_resolved
    if [[ -n "$_ie_version_override" ]]; then
        _ie_resolved="$_ie_version_override"
    elif [[ -n "${VERSION:-}" ]]; then
        _ie_resolved="$VERSION"
    elif _ie_resolved="$("$_ie_dir/resolve-version.sh" --current 2>/dev/null)" && [[ -n "$_ie_resolved" ]]; then
        :
    else
        # Covers both a failing resolver and one that exits 0 printing nothing.
        # The second case used to propagate an EMPTY version through --strict.
        _ie_resolved="0.0.0-dev"
    fi

    if [[ "$_ie_strict" == "true" ]]; then
        if [[ -z "$_ie_resolved" ]]; then
            echo "inject-env.sh: version is empty under --strict" >&2
            return 1
        fi
        if [[ "$_ie_resolved" == "0.0.0-dev" ]]; then
            echo "inject-env.sh: version resolved to 0.0.0-dev under --strict (did the checkout include tags?)" >&2
            return 1
        fi
        # A publishable version is dotted-numeric, optionally v-prefixed, with
        # an optional pre-release/build suffix. Anything else (a curl error
        # page, "none", "latest") must not reach a build define.
        if [[ ! "$_ie_resolved" =~ ^v?[0-9]+(\.[0-9]+)*([-+][0-9A-Za-z.-]+)?$ ]]; then
            echo "inject-env.sh: version '$_ie_resolved' is not a dotted numeric version, refusing under --strict" >&2
            return 1
        fi
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
