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
# WELL-KNOWN VALUES
# =============================================================================
# Sourced, not restated, like the pins above. .ci/config/well-known.env is the
# only place an origin, bucket, slug, image registry, owned path or address is
# written; check:ci-literal-sources fails on a copy anywhere else. Bash reads it
# through well-known.generated.sh, the projection that gate renders and holds
# equal to it: an exported WK_* is kept (the shell wins), nothing in the file
# executes, and no python3 is needed this early.
# The WK_* names are facts. The knobs below (RELEASES_BASE_URL, DOCKER_REGISTRY,
# ...) keep their `${X:-...}` override where they had one, and default to the fact.
_REDIACC_WELL_KNOWN_SH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/well-known.generated.sh"
if [[ -r "$_REDIACC_WELL_KNOWN_SH" ]]; then
    # shellcheck source=/dev/null
    . "$_REDIACC_WELL_KNOWN_SH"
else
    echo "constants.sh: well-known values missing: $_REDIACC_WELL_KNOWN_SH" >&2
    return 1 2>/dev/null || exit 1
fi
unset _REDIACC_WELL_KNOWN_SH

# =============================================================================
# VERSION REQUIREMENTS
# =============================================================================
# DERIVED FROM toolchain.env, NOT restated: NODE_VERSION is already in scope
# from the source block above. Hardcoding "22" here separately is the exact
# drift class check-toolchain-env-dockerfile-sync.sh exists to catch for
# toolchain.env vs the Dockerfile -- this pair had the identical bug one file
# over, just never caught because nothing compared it against anything.
readonly NODE_VERSION_REQUIRED="${NODE_VERSION:?NODE_VERSION not sourced from toolchain.env}"

# THE FLOOR IS SOURCED, NOT COMPOSED, and the line it replaced is the whole
# reason. It read:
#
#     readonly NODE_VERSION_MIN="${NODE_VERSION_REQUIRED}.0.0"
#
# which derives from toolchain.env and so LOOKS like it obeys the rule the block
# above states. It does not: NODE_VERSION is a bare MAJOR, and appending ".0.0"
# invents a patch floor nobody chose. It yielded 22.0.0, while package.json and
# packages/cli/package.json both required ">=22.13.0" -- so every shell path in
# this repo enforced a floor 13 minors looser than the manifests, and a host on
# Node 22.4 cleared ./run.sh setup only to fail later inside npm. Composing a
# value from a pin is the same drift class as restating one; it just hides better.
readonly NODE_VERSION_MIN="${NODE_VERSION_MIN:?NODE_VERSION_MIN not sourced from toolchain.env}"

# AND THE TWO MUST DESCRIBE THE SAME MAJOR. NODE_VERSION says which major CI and
# the image install; NODE_VERSION_MIN says the oldest release that is acceptable.
# A floor of 20.x under an installed major of 22, or 23.x over it, is not a
# stricter policy -- it is a pair of numbers that cannot both be honoured, and
# whichever consumer reads only one of them decides the answer. Caught here
# rather than in the gate because this is where anything that sources the pins
# gets its first chance to refuse.
if [[ "${NODE_VERSION_MIN%%.*}" != "$NODE_VERSION_REQUIRED" ]]; then
    echo "constants.sh: NODE_VERSION_MIN=$NODE_VERSION_MIN is not on major $NODE_VERSION_REQUIRED (NODE_VERSION)" >&2
    echo "  both live in .devcontainer/toolchain.env; move them together." >&2
    return 1 2>/dev/null || exit 1
fi

# =============================================================================
# PATHS (must be defined early, used by other sections)
# =============================================================================
readonly CONSOLE_ROOT_DIR="${CONSOLE_ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
readonly CI_DIR="$CONSOLE_ROOT_DIR/.ci"

# =============================================================================
# DOCKER REGISTRY CONFIGURATION
# =============================================================================
# DOCKER_REGISTRY can be overridden by .env for local development
DOCKER_REGISTRY="${DOCKER_REGISTRY:-$WK_IMAGE_REGISTRY}"
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
SYSTEM_ADMIN_EMAIL="${SYSTEM_ADMIN_EMAIL:-$WK_ADMIN_EMAIL_DEFAULT}"
SYSTEM_ADMIN_PASSWORD="${SYSTEM_ADMIN_PASSWORD:-admin}"
SYSTEM_ORGANIZATION_NAME="${SYSTEM_ORGANIZATION_NAME:-Default Organization}"
SYSTEM_DEFAULT_BRIDGE_NAME="${SYSTEM_DEFAULT_BRIDGE_NAME:-Global Bridges}"
SYSTEM_DEFAULT_REGION_NAME="${SYSTEM_DEFAULT_REGION_NAME:-Default Region}"
SYSTEM_DEFAULT_TEAM_NAME="${SYSTEM_DEFAULT_TEAM_NAME:-Private Team}"

# =============================================================================
# ACCOUNT DEV CONFIGURATION
# =============================================================================
readonly ACCOUNT_DEV_PORT_PREFERRED="$WK_ACCOUNT_DEV_PORT"
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
readonly DEVBOX_IMAGE="$WK_IMAGE_REGISTRY/devcontainer:latest"
# The LOCAL repository of the per-operator derived image: the base with `vscode`
# renumbered to the host's ids (.devcontainer/Dockerfile.uid). Deliberately not
# a ghcr.io/ name, so a derived tag can never be mistaken for something to push.
readonly DEVBOX_UID_IMAGE_REPO="$WK_DEVBOX_UID_IMAGE_REPO"
readonly DEVBOX_PORT_RANGE_START=17000
readonly DEVBOX_PORT_RANGE_END=17999
readonly DEVBOX_PORT_BLOCK=10
readonly DEVBOX_STATE_FILE="$CONSOLE_ROOT_DIR/.devbox-state"
# Offsets inside a block. The container publishes nothing and everything is
# reached through the proxy, so these are the ports processes bind INSIDE the
# container. (novnc/www offsets existed while ports were published.)
#
# TERM is block-derived rather than ttyd's own default 7681 for the reason the
# block exists at all: two worktrees on one machine must never collide. The fixed
# 7681 survives in .devcontainer/devcontainer.json and docker-compose.server.yml,
# where there is exactly one container and no block to derive from.
readonly DEVBOX_OFFSET_VSCODE=0
readonly DEVBOX_OFFSET_STUDIO=3
readonly DEVBOX_OFFSET_TERM=5

# Reverse proxy: ONE published port for every worktree and every service.
# Routing is by Host header, so each app still believes it is at "/" and needs no
# base-path configuration. Chrome resolves *.localhost to 127.0.0.1 itself, so a
# single forwarded port covers every worktree -- which is the whole point on
# ChromeOS, where each published port otherwise needs its own manual forward.
readonly DEVBOX_PROXY_IMAGE="traefik:v3.7.16" # same tag the product proxy pins
readonly DEVBOX_PROXY_NAME="rediacc-devbox-proxy"
readonly DEVBOX_PROXY_PORT=8090
readonly DEVBOX_NETWORK="rediacc-devbox"
readonly DEVBOX_DOMAIN="localhost"

# =============================================================================
# PUBLISHING CONFIGURATION
# =============================================================================
PUBLISH_DOCKER_REGISTRY="${PUBLISH_DOCKER_REGISTRY:-$WK_IMAGE_REGISTRY}"

# Bot identity for CI commits: the GIT_BOT_NAME / GIT_BOT_EMAIL Bitwarden secrets (ci-shared).
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
# exported together by rediacc_ci.version.inject_env so every build boundary sees
# the same value. bump.sh only updates the package.json that downstream tooling reads
# at pack/publish time (CLI npm pack).
readonly VERSION_FILES_JSON=(
    "packages/cli/package.json"
)

# =============================================================================
# RELEASE DISTRIBUTION CONFIGURATION (Cloudflare R2)
# =============================================================================
readonly RELEASES_BASE_URL="${RELEASES_BASE_URL:-$WK_RELEASES_ORIGIN}"
readonly RELEASES_BUCKET="${RELEASES_BUCKET:-$WK_RELEASES_BUCKET}"

# =============================================================================
# PACKAGE REPOSITORY CONFIGURATION
# =============================================================================
readonly PKG_NAME="rediacc-cli"
readonly PKG_BINARY_NAME="rdc"
readonly PKG_MAINTAINER="Rediacc <$WK_PKG_MAINTAINER_EMAIL>"
readonly PKG_DESCRIPTION="Rediacc CLI - automation and scripting tool"
readonly PKG_HOMEPAGE="$WK_SITE_ORIGIN"
readonly PKG_SECTION="utils"
readonly PKG_PRIORITY="optional"
readonly R2_MAX_RELEASE_VERSIONS=20

# nfpm configuration (replaces dpkg-deb + rpmbuild for package creation)
readonly NFPM_VERSION="2.48.0"
# Verified against the checksums.txt asset of the goreleaser/nfpm release tagged
# with the NFPM_VERSION above (https://github.com/goreleaser/nfpm/releases).
# The tarball is piped straight into `sudo tar` in a job that also holds release
# secrets, so an unverified download is arbitrary root-owned code. Update both
# this and NFPM_VERSION together.
readonly NFPM_SHA256_LINUX_X86_64="6d7f9a28b2f397934403950fcbba83f598b08d02edbe79a0815b3b4897341750"

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
readonly SHELLCHECK_SHA256_LINUX_AARCH64="12b331c1d2db6b9eb13cfca64306b1b157a86eb69db83023e261eaa7e7c14588"
readonly SHELLCHECK_SHA256_LINUX_X86_64="8c3be12b05d5c177a04c29e3c78ce89ac86f1595681cab149b65b97c4e227198"
# DARWIN, added 2026-09-06 to finish the fix in .ci/scripts/lib/toolchain.sh. Until these
# existed, an arm64 Mac resolved SHELLCHECK_SHA256_LINUX_AARCH64, downloaded the LINUX
# tarball, and it PASSED its checksum because that is genuinely that file. The wrong OS
# installed silently and failed much later as cannot-execute-binary-file, from a gate with
# no idea it had installed the tool for another platform. Fetched from each release asset
# and verified BY TYPE before recording (Mach-O 64-bit executables and XZ archives, not an
# error page), which is the trap CLAUDE.md records about piping an unchecked HTTP response.
readonly SHELLCHECK_SHA256_DARWIN_X86_64="3c89db4edcab7cf1c27bff178882e0f6f27f7afdf54e859fa041fca10febe4c6"
readonly SHELLCHECK_SHA256_DARWIN_AARCH64="56affdd8de5527894dca6dc3d7e0a99a873b0f004d7aabc30ae407d3f48b0a79"

# shfmt release BINARIES, for the lanes that have no Go.
#
# `go install ...@vX` is preferred where Go exists, because Go verifies the
# module against its checksum database -- a better guarantee than a hash we
# wrote down. But the CI Static lane is a BARE CHECKOUT (docs/agent-reference/
# ci-gates.md:108-110 groups lanes by what they need on disk) and has no Go at
# all, so an acquisition that requires it cannot run there. Recorded by
# downloading the pinned release (re-recorded by the pins tool on each bump);
# mvdan/sh publishes no checksums file, so this is trust-on-first-use, said plainly.
readonly SHFMT_SHA256_LINUX_AMD64="76e77641faa025814b77f153b29796b8e6fa2fca03e0c76a691608b86c7ea7bf"
readonly SHFMT_SHA256_LINUX_ARM64="5f2db09dae91fca848f7adbdd014632e921a383863a2ad7e0450ad3aba0c6489"
# DARWIN, added 2026-09-06. Same reason as the shellcheck pair above. The arch spelling
# differs between the two upstreams and that is NOT a typo: shfmt ships Go release names
# and uses amd64/arm64, shellcheck uses x86_64/aarch64. toolchain.sh keys each variable off
# the arch token that tool itself uses, so the two spellings must not be unified.
readonly SHFMT_SHA256_DARWIN_AMD64="d33eee0da0f92835b3562e9767a05cee7e4eaeef47daa03bfd09da17b4b590a6"
readonly SHFMT_SHA256_DARWIN_ARM64="b7c872db63553ccffc7253aba3ed7d4885a27d83f1ba567b1138c6315a5847e5"

# wrangler is installed globally in jobs that carry the production Cloudflare
# API token, so it is pinned rather than floating on @latest.
readonly WRANGLER_VERSION="4.156.0"

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
