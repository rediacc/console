#!/bin/bash
# Console development constants
# Single source of truth for all configuration

# Prevent re-sourcing
[[ -n "${REDIACC_CONSTANTS_LOADED:-}" ]] && return 0
readonly REDIACC_CONSTANTS_LOADED=1

# =============================================================================
# GATE TOOLCHAIN PINS
# =============================================================================
# Sourced, not restated. .devcontainer/toolchain.env is the ONLY place a gate
# tool's version is written, because it is the one file all three lanes can read:
# bash here, the Dockerfile via COPY+ARG, and Actions via $GITHUB_ENV. It lives
# under .devcontainer/ because that is the image build context
# (.github/workflows/ci-build-docker.yml:558) and COPY cannot reach outside it.
#
# Anything sourced here is a plain shell variable; the `readonly` re-exports
# below are what existing consumers already expect.
_REDIACC_TOOLCHAIN_ENV="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/.devcontainer/toolchain.env"
if [[ -r "$_REDIACC_TOOLCHAIN_ENV" ]]; then
    set -a
    # shellcheck source=/dev/null
    . "$_REDIACC_TOOLCHAIN_ENV"
    set +a
    # Tell .ci/scripts/lib/toolchain.sh the pins are already in the environment.
    # Without this it re-sources them AFTER the readonly re-exports below, and
    # every re-exported key errors with "readonly variable".
    REDIACC_TOOLCHAIN_LOADED=1
else
    echo "constants.sh: gate toolchain pins missing: $_REDIACC_TOOLCHAIN_ENV" >&2
    return 1 2>/dev/null || exit 1
fi
unset _REDIACC_TOOLCHAIN_ENV

# =============================================================================
# VERSION REQUIREMENTS
# =============================================================================
readonly NODE_VERSION_REQUIRED="22"
readonly NODE_VERSION_MIN="22.0.0"

# =============================================================================
# PATHS (must be defined early, used by other sections)
# =============================================================================
readonly CONSOLE_ROOT_DIR="${CONSOLE_ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
readonly CI_DIR="$CONSOLE_ROOT_DIR/.ci"
readonly CI_LIB_DIR="$CI_DIR/lib"

# =============================================================================
# DOCKER REGISTRY CONFIGURATION
# =============================================================================
# DOCKER_REGISTRY can be overridden by .env for local development
DOCKER_REGISTRY="${DOCKER_REGISTRY:-ghcr.io/rediacc}"
DOCKER_TAG="${DOCKER_TAG:-latest}"

# =============================================================================
# BACKEND CONFIGURATION (self-contained docker-compose)
# =============================================================================
readonly CI_DOCKER_DIR="${CONSOLE_ROOT_DIR}/.ci/docker/ci"
readonly CI_COMPOSE_FILE="${CI_DOCKER_DIR}/docker-compose.yml"

# Backend state file
readonly BACKEND_STATE_FILE="$CONSOLE_ROOT_DIR/.backend-state"

# Service mode configuration
readonly SERVICE_DOCKER_DIR="${CONSOLE_ROOT_DIR}/.ci/docker/service"
readonly SERVICE_STATE_FILE="$CONSOLE_ROOT_DIR/.service-state"

# =============================================================================
# VM PROVISIONING DEFAULTS
# =============================================================================
readonly VM_NET_BASE_DEFAULT="192.168.111"
readonly VM_BRIDGE_DEFAULT=1

# Default System Configuration (can be overridden by .env)
SYSTEM_ADMIN_EMAIL="${SYSTEM_ADMIN_EMAIL:-admin@rediacc.io}"
SYSTEM_ADMIN_PASSWORD="${SYSTEM_ADMIN_PASSWORD:-admin}"
SYSTEM_ORGANIZATION_NAME="${SYSTEM_ORGANIZATION_NAME:-Default Organization}"
SYSTEM_DEFAULT_BRIDGE_NAME="${SYSTEM_DEFAULT_BRIDGE_NAME:-Global Bridges}"
SYSTEM_DEFAULT_REGION_NAME="${SYSTEM_DEFAULT_REGION_NAME:-Default Region}"
SYSTEM_DEFAULT_TEAM_NAME="${SYSTEM_DEFAULT_TEAM_NAME:-Private Team}"

# =============================================================================
# ACCOUNT DEV CONFIGURATION
# =============================================================================
readonly ACCOUNT_DEV_PORT_PREFERRED=4800
readonly ACCOUNT_DEV_PORT_RANGE_END=5799
readonly ACCOUNT_STATE_FILE="$CONSOLE_ROOT_DIR/.account-state"
readonly ACCOUNT_LOG_DIR="$CONSOLE_ROOT_DIR/.account-logs"

# =============================================================================
# DEVBOX (browser dev environment) CONFIGURATION
# =============================================================================
# One container per worktree. The port BLOCK is derived from the worktree's
# absolute path so it is stable across restarts and reboots, and two worktrees
# can never land on the same block.
#
# The URL is a different matter: its hostname follows the BRANCH, so it changes
# when the branch does. A bookmark survives a reboot, not a checkout.
readonly DEVBOX_IMAGE="ghcr.io/rediacc/devcontainer:latest"
readonly DEVBOX_PORT_RANGE_START=17000
readonly DEVBOX_PORT_RANGE_END=17999
readonly DEVBOX_PORT_BLOCK=10
readonly DEVBOX_STATE_FILE="$CONSOLE_ROOT_DIR/.devbox-state"
# Offsets inside a block. Only two survive: the container publishes nothing and
# everything is reached through the proxy, so these are the ports processes bind
# INSIDE the container. (novnc/www offsets existed while ports were published.)
readonly DEVBOX_OFFSET_VSCODE=0
readonly DEVBOX_OFFSET_STUDIO=3

# Reverse proxy: ONE published port for every worktree and every service.
# Routing is by Host header, so each app still believes it is at "/" and needs no
# base-path configuration. Chrome resolves *.localhost to 127.0.0.1 itself, so a
# single forwarded port covers every worktree -- which is the whole point on
# ChromeOS, where each published port otherwise needs its own manual forward.
readonly DEVBOX_PROXY_IMAGE="traefik:v3.6" # same major the product proxy pins
readonly DEVBOX_PROXY_NAME="rediacc-devbox-proxy"
readonly DEVBOX_PROXY_PORT=8090
readonly DEVBOX_NETWORK="rediacc-devbox"
readonly DEVBOX_DOMAIN="localhost"

# =============================================================================
# PUBLISHING CONFIGURATION
# =============================================================================
PUBLISH_DOCKER_REGISTRY="${PUBLISH_DOCKER_REGISTRY:-ghcr.io/rediacc}"

# Bot identity for CI commits: set GIT_BOT_NAME / GIT_BOT_EMAIL org variables.
# Used by: update-homebrew-tap.sh, cd-v2.yml (git tag creation).
# NOT declared here to avoid breaking local scripts that source constants.sh.

# Docker images to publish
readonly PUBLISH_IMAGES=("renet" "rdc")

# Dockerfiles (relative to CONSOLE_ROOT_DIR)
# Associative arrays require bash 4+; skip on older bash (e.g. macOS system bash 3.2).
# These are only used by Docker build scripts which run on Linux.
if ((BASH_VERSINFO[0] >= 4)); then
    declare -A DOCKERFILES=(
        ["renet"]="private/renet/Dockerfile"
        ["rdc"]="packages/cli/Dockerfile.native"
    )

    # Build contexts (relative to CONSOLE_ROOT_DIR)
    declare -A BUILD_CONTEXTS=(
        ["renet"]="private/renet"
        ["rdc"]="."
    )
fi

# Version source of truth: git tags (e.g., v0.8.3).
# Version injection at build time: CLI via __CLI_VERSION__ esbuild define, www via
# APP_VERSION env, web via VITE_APP_VERSION env, renet via ldflags. All env vars are
# exported together by .ci/scripts/version/inject-env.sh so every build boundary sees
# the same value. bump.sh only updates the package.json that downstream tooling reads
# at pack/publish time (CLI npm pack).
readonly VERSION_FILES_JSON=(
    "packages/cli/package.json"
)

# =============================================================================
# RELEASE DISTRIBUTION CONFIGURATION (Cloudflare R2)
# =============================================================================
readonly RELEASES_BASE_URL="${RELEASES_BASE_URL:-https://releases.rediacc.com}"
readonly RELEASES_BUCKET="${RELEASES_BUCKET:-rediacc-releases}"

# =============================================================================
# PACKAGE REPOSITORY CONFIGURATION
# =============================================================================
readonly PKG_NAME="rediacc-cli"
readonly PKG_BINARY_NAME="rdc"
readonly PKG_MAINTAINER="Rediacc <info@rediacc.com>"
readonly PKG_DESCRIPTION="Rediacc CLI - automation and scripting tool"
readonly PKG_HOMEPAGE="https://www.rediacc.com"
readonly PKG_SECTION="utils"
readonly PKG_PRIORITY="optional"
readonly R2_MAX_RELEASE_VERSIONS=20

# nfpm configuration (replaces dpkg-deb + rpmbuild for package creation)
readonly NFPM_VERSION="2.45.0"
# Verified against https://github.com/goreleaser/nfpm/releases/download/v2.45.0/checksums.txt
# The tarball is piped straight into `sudo tar` in a job that also holds release
# secrets, so an unverified download is arbitrary root-owned code. Update both
# this and NFPM_VERSION together.
readonly NFPM_SHA256_LINUX_X86_64="940f0c3ba8e2c9cc5669026a1c0c20453403b9c32ea4c66fd25426bcbe605a84"

# actionlint validates workflow YAML itself: `${{ }}` expression types, matrix
# property references, runner labels, action input names, `if:` syntax. Pinned
# and checksum-verified like everything else fetched from a release page.
#
# Verified against
# https://github.com/rhysd/actionlint/releases/download/v1.7.12/actionlint_1.7.12_checksums.txt
# Update the version and BOTH checksums together.
# ACTIONLINT_VERSION now comes from .devcontainer/toolchain.env (sourced above)
# so the image build can read the same number. The checksums stay here: the
# Dockerfile has no use for them, and splitting by WHO READS IT beats splitting
# by what it is.
readonly ACTIONLINT_VERSION="${ACTIONLINT_VERSION:?ACTIONLINT_VERSION missing from toolchain.env}"
readonly ACTIONLINT_SHA256_LINUX_AMD64="8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8"
readonly ACTIONLINT_SHA256_LINUX_ARM64="325e971b6ba9bfa504672e29be93c24981eeb1c07576d730e9f7c8805afff0c6"

# The shellcheck project ships a prebuilt Haskell binary with NO published
# checksums file, so
# these were recorded by downloading the pinned release and hashing it here on
# 2026-08-25. That is trust-on-first-use, and weaker than actionlint's published
# list above -- said plainly rather than dressed up. It is still far stronger
# than what it replaces, which was "whatever version happened to be on PATH".
#
# (Note the wording above: a comment whose FIRST word is the name of a linter is
# parsed by that linter as a directive, and an earlier draft of this very block
# failed the shellcheck gate with SC1073.)
#
# shfmt deliberately has NO checksum here: it is acquired with
# `go install mvdan.cc/sh/v3/cmd/shfmt@v$SHFMT_VERSION`, which Go verifies
# against its own checksum database -- a better guarantee than a hash we wrote
# down ourselves.
readonly SHELLCHECK_SHA256_LINUX_AARCH64="324a7e89de8fa2aed0d0c28f3dab59cf84c6d74264022c00c22af665ed1a09bb"
readonly SHELLCHECK_SHA256_LINUX_X86_64="6c881ab0698e4e6ea235245f22832860544f17ba386442fe7e9d629f8cbedf87"

# shfmt release BINARIES, for the lanes that have no Go.
#
# `go install ...@vX` is preferred where Go exists, because Go verifies the
# module against its checksum database -- a better guarantee than a hash we
# wrote down. But the CI Static lane is a BARE CHECKOUT (docs/agent-reference/
# ci-gates.md:108-110 groups lanes by what they need on disk) and has no Go at
# all, so an acquisition that requires it cannot run there. Recorded by
# downloading the pinned release on 2026-08-25; mvdan/sh publishes no checksums
# file, so this is trust-on-first-use, said plainly.
readonly SHFMT_SHA256_LINUX_AMD64="fb096c5d1ac6beabbdbaa2874d025badb03ee07929f0c9ff67563ce8c75398b1"
readonly SHFMT_SHA256_LINUX_ARM64="32d92acaa5cd8abb29fc49dac123dc412442d5713967819d8af2c29f1b3857c7"

# wrangler is installed globally in jobs that carry the production Cloudflare
# API token, so it is pinned rather than floating on @latest.
readonly WRANGLER_VERSION="4.112.0"

# Homebrew tap configuration
readonly HOMEBREW_FORMULA_PATH="Formula/rediacc-cli.rb"

# =============================================================================
# LOGGING
# =============================================================================

# Color codes
readonly COLOR_RED='\033[0;31m'
readonly COLOR_GREEN='\033[0;32m'
readonly COLOR_NC='\033[0m'

# =============================================================================
# VALIDATION
# =============================================================================
if [[ -z "$NODE_VERSION_REQUIRED" ]]; then
    echo "ERROR: NODE_VERSION_REQUIRED not set" >&2
    exit 1
fi

# Export for subprocess access
export NODE_VERSION_REQUIRED
