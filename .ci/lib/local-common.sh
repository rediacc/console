#!/bin/bash
# Local development utilities for console ./run.sh script
# This file bridges console development with CI infrastructure
#
# Usage: source "$ROOT_DIR/.ci/lib/local-common.sh"

# Prevent multiple sourcing
[[ -n "${LOCAL_COMMON_LOADED:-}" ]] && return 0
LOCAL_COMMON_LOADED=1

# =============================================================================
# SETUP
# =============================================================================

# Get directories
LOCAL_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_CI_DIR="$(cd "$LOCAL_LIB_DIR/.." && pwd)"
LOCAL_ROOT_DIR="$(cd "$LOCAL_CI_DIR/.." && pwd)"

# Source CI common library for logging, validation, etc.
source "$LOCAL_CI_DIR/scripts/lib/common.sh"

# =============================================================================
# PORTABLE TOOL WRAPPERS
# =============================================================================

# Portable sha256sum (macOS uses shasum -a 256)
# Resolves once to a concrete command for use with xargs (which can't call shell functions)
if command -v sha256sum &>/dev/null; then
    _SHA256SUM_CMD="sha256sum"
elif command -v shasum &>/dev/null; then
    _SHA256SUM_CMD="shasum -a 256"
else
    _SHA256SUM_CMD=""
fi

_sha256sum() {
    if [[ -z "$_SHA256SUM_CMD" ]]; then
        log_error "No sha256 tool found (need sha256sum or shasum)"
        exit 1
    fi
    $_SHA256SUM_CMD "$@"
}

# Portable sed in-place (macOS sed requires -i '' for no backup)
_sed_i() {
    if [[ "$(uname -s)" == "Darwin" ]]; then
        sed -i '' "$@"
    else
        sed -i "$@"
    fi
}

# =============================================================================
# CONSOLE-SPECIFIC HELPERS
# =============================================================================

compute_hash_for_package_dirs() {
    local root_dir="$1"
    shift

    (
        cd "$root_dir" || exit
        find "$@" \
            \( -path '*/dist/*' -o -path '*/node_modules/*' -o -path '*/reports/*' -o -path '*/test-results/*' \) -prune -o \
            \( -name '*.tsbuildinfo' -o -name '.DS_Store' \) -prune -o \
            -type f -print0 2>/dev/null |
            LC_ALL=C sort -z |
            xargs -0 $_SHA256SUM_CMD 2>/dev/null |
            $_SHA256SUM_CMD |
            awk '{print $1}'
    )
}

# Content-derived tree fingerprint via the git index (fast path).
#
# The full find+sha256 walk above hashes EVERY file on EVERY invocation
# (~100-500ms per tree). git answers "which files differ from HEAD" from the
# index stat-cache in milliseconds, re-hashing content whenever stat info is
# inconclusive — the same correctness property, without hashing unchanged
# files. The fingerprint combines:
#   1. the HEAD tree object id per path (exact committed content), and
#   2. every staged/unstaged/deleted/untracked path with its content hash
#      (git hash-object, one batch process),
# so any content change flips the fingerprint regardless of mtime games — the
# historical `find -newer` race (checkout/stash/cp -p writing OLDER mtimes) is
# caught because git updates the index on those operations and hash-object
# reads bytes, never timestamps.
#
# Prints nothing and fails when git cannot answer authoritatively (git absent,
# not a work tree, no HEAD) — callers fall back to the full walk.
_git_tree_fingerprint() {
    local root="$1"
    shift
    (
        cd "$root" || exit 1
        command -v git >/dev/null 2>&1 || exit 1
        git rev-parse --verify -q HEAD >/dev/null 2>&1 || exit 1

        local p changed existing hashes
        changed="$(
            {
                git ls-files -m -d -z -- "$@" 2>/dev/null
                git ls-files -o --exclude-standard -z -- "$@" 2>/dev/null
                git diff --cached --name-only -z -- "$@" 2>/dev/null
            } | LC_ALL=C sort -zu | tr '\0' '\n'
        )" || exit 1

        existing=""
        if [[ -n "$changed" ]]; then
            existing="$(
                while IFS= read -r f; do
                    [[ -f "$f" ]] && printf '%s\n' "$f"
                done <<<"$changed"
            )"
        fi
        hashes=""
        if [[ -n "$existing" ]]; then
            hashes="$(git hash-object --stdin-paths <<<"$existing" 2>/dev/null)" || exit 1
        fi

        {
            for p in "$@"; do
                if [[ "$p" == "." ]]; then
                    git rev-parse -q --verify 'HEAD^{tree}' 2>/dev/null || printf 'no-tree:.\n'
                else
                    git rev-parse -q --verify "HEAD:$p" 2>/dev/null || printf 'no-tree:%s\n' "$p"
                fi
            done
            printf '%s\n' "$changed"
            printf '%s\n' "$hashes"
        } | $_SHA256SUM_CMD | awk '{print $1}'
    )
}

# Tree fingerprint with fallback: git index when available, full walk otherwise.
compute_tree_hash() {
    local root="$1"
    shift
    local fp
    if fp="$(_git_tree_fingerprint "$root" "$@")" && [[ -n "$fp" ]]; then
        printf '%s\n' "$fp"
        return 0
    fi
    compute_hash_for_package_dirs "$root" "$@"
}

read_stamp_hash() {
    local stamp_file="$1"

    if [[ -f "$stamp_file" ]]; then
        cat "$stamp_file"
    fi
}

write_stamp_hash() {
    local stamp_file="$1"
    local stamp_hash="$2"

    mkdir -p "$(dirname "$stamp_file")"
    printf '%s\n' "$stamp_hash" >"$stamp_file"
}

# Generate cpu-features' buildcheck.gypi, which its npm install script would
# normally produce.
#
# CALLED AFTER `npm install`, NEVER BEFORE, and that order is a fixed bug rather
# than a preference: on a fresh clone node_modules/cpu-features does not exist
# when ensure_deps starts, so a pre-install placement generated nothing,
# install:natives was never reached, and the stamp was written anyway -- every
# later run then reported "up-to-date" over a tree whose natives had never been
# compiled. Found 2026-08-26 by check:ci-native-rebuild.
#
# Extracted from ensure_deps 2026-08-27 so the install and its native rebuild
# sit next to each other. They were 59 lines apart, which is past the 20-line
# window check:ci-native-rebuild pairs within -- and a rebuild you have to
# scroll to find is one the next edit drops.
ensure_cpu_features_gypi() {
    local node_modules_dir="$1"
    local cpu_features_dir="$node_modules_dir/cpu-features"
    # A ZERO-BYTE gypi is worse than a missing one: the guard below is a plain
    # existence test, so a crashed run (e.g. no C compiler -> "Unable to detect
    # compiler type") leaves an empty file that every later run then SKIPS.
    # Observed on a host with no build-essential.
    if [[ -f "$cpu_features_dir/buildcheck.gypi" ]] && [[ ! -s "$cpu_features_dir/buildcheck.gypi" ]]; then
        log_debug "Removing empty buildcheck.gypi left by a failed run"
        rm -f "$cpu_features_dir/buildcheck.gypi"
    fi
    if [[ -f "$cpu_features_dir/buildcheck.js" ]] && [[ ! -f "$cpu_features_dir/buildcheck.gypi" ]]; then
        # Write to a temp file and only publish on success, so a failure cannot
        # poison the guard above.
        if ! (cd "$cpu_features_dir" && node buildcheck.js >buildcheck.gypi.tmp); then
            rm -f "$cpu_features_dir/buildcheck.gypi.tmp"
            log_error "cpu-features buildcheck failed (is a C compiler installed?)"
            return 1
        fi
        mv "$cpu_features_dir/buildcheck.gypi.tmp" "$cpu_features_dir/buildcheck.gypi"
    fi
}

# Smart dependency installation (only if needed)
# Uses a hash-based stamp so npm metadata-only mtime changes do not force reinstall
ensure_deps() {
    local node_modules_dir="$LOCAL_ROOT_DIR/node_modules"
    local stamp_file="$LOCAL_ROOT_DIR/.ci/cache/npm-install.stamp"
    local current_hash
    local saved_hash=""

    current_hash="$(
        {
            _sha256sum "$LOCAL_ROOT_DIR/package.json"
            _sha256sum "$LOCAL_ROOT_DIR/package-lock.json"
            if [[ -f "$LOCAL_ROOT_DIR/.npmrc" ]]; then
                _sha256sum "$LOCAL_ROOT_DIR/.npmrc"
            fi
            # The RUNTIME is part of the identity of node_modules, not just the
            # manifests. install:natives rebuilds ssh2/cpu-features/esbuild
            # against the local glibc, and the devbox image (Ubuntu 24.04,
            # glibc 2.39) is not the same libc as a Debian 12 host (2.36). A
            # .node built on one side fails to load on the other with a
            # GLIBC_2.38-not-found error that looks like a corrupt install.
            # Without this line the stamp matches across the flip and both
            # sides believe the tree is fresh.
            printf 'runtime=%s\n' "${REDIACC_NPM_RUNTIME:-host}"
        } | _sha256sum | awk '{print $1}'
    )"

    saved_hash="$(read_stamp_hash "$stamp_file")"

    if [[ -d "$node_modules_dir" ]] &&
        [[ -x "$node_modules_dir/.bin/tsx" ]] &&
        [[ -L "$node_modules_dir/@rediacc/cli" ]] &&
        [[ "$saved_hash" == "$current_hash" ]]; then
        log_debug "Dependencies are up-to-date (stamp matched)"
        return 0
    fi

    # Install with npm 10, which is what CI pins (.ci/scripts/quality/check-lockfile.sh)
    # and what the lockfile's nested layout describes.
    #
    # This is not cosmetic like the 27-line "dev": true flip. npm 11 HOISTS
    # differently: it flattens zod to the 3.25.76 copy that transitives drag in,
    # ignoring the workspace-local zod@4.4.3 the lockfile pins, and then
    # `npm ls zod` reports `invalid: "^4.3.6" from packages/shared`. The visible
    # symptom is packages/shared failing to compile with "Property 'uuid' does
    # not exist" (v4 API against a v3 copy), which takes `./run.sh account dev`
    # down with it. Reproduced on npm 11.9.0; npm@10 fixes it in one run.
    #
    # THERE WAS A SECOND, PLAIN `npm install` ABOVE THIS ONE until 2026-08-27,
    # left by a rebase that kept both sides of a conflict where one superseded
    # the other. It ran whatever npm is on PATH -- precisely the command this
    # comment exists to prevent -- and logged "Installing dependencies..." a
    # second time. check:ci-native-rebuild found it by noticing that the install
    # at that line had no native rebuild within its window.
    local npm_cmd=(npm)
    local npm_major
    npm_major="$(npm --version 2>/dev/null | cut -d. -f1)"
    if [[ -n "$npm_major" ]] && [[ "$npm_major" != "10" ]]; then
        log_warn "npm $npm_major detected; installing with npm@10 to match the lockfile layout"
        npm_cmd=(npx -y npm@10)
    fi

    log_step "Installing dependencies..."
    (cd "$LOCAL_ROOT_DIR" && "${npm_cmd[@]}" install)
    ensure_cpu_features_gypi "$node_modules_dir" || return 1
    # BOTH STEPS, IN THIS ORDER -- not one or the other. `.npmrc` sets
    # ignore-scripts=true, so `npm install` deliberately does NOT build ssh2,
    # cpu-features or esbuild. Dropping this line leaves a tree that installed
    # cleanly and fails later inside node-gyp; dropping the line above leaves
    # nothing to compile. The rebase offered them as alternatives because two
    # waves edited the same spot, which they are not.
    log_step "Compiling native modules (blocked at install by ignore-scripts)..."
    (cd "$LOCAL_ROOT_DIR" && npm run install:natives)
    write_stamp_hash "$stamp_file" "$current_hash"
}

# Ensure shared packages are built
# Required before running tests or building web/CLI
ensure_packages_built() {
    local stamp_file="$LOCAL_ROOT_DIR/.ci/cache/build-packages.stamp"
    local current_hash
    local saved_hash=""

    current_hash="$(
        compute_tree_hash "$LOCAL_ROOT_DIR" \
            packages/shared \
            packages/provisioning
    )"

    saved_hash="$(read_stamp_hash "$stamp_file")"

    if [[ -d "$LOCAL_ROOT_DIR/packages/shared/dist" ]] &&
        [[ -d "$LOCAL_ROOT_DIR/packages/provisioning/dist" ]] &&
        [[ "$saved_hash" == "$current_hash" ]]; then
        log_debug "Shared packages are up-to-date (stamp matched)"
        return 0
    fi

    log_step "Building shared packages..."
    "$LOCAL_CI_DIR/scripts/setup/build-packages.sh"
    write_stamp_hash "$stamp_file" "$current_hash"
}

ensure_cli_built() {
    local cli_dist="$LOCAL_ROOT_DIR/packages/cli/dist"
    local cli_entry="$cli_dist/cli-bundle.cjs"
    local stamp_file="$LOCAL_ROOT_DIR/.ci/cache/build-cli.stamp"
    local current_hash
    local saved_hash=""

    # Include shared packages stamp so CLI rebundles when dependencies change
    local packages_stamp="$LOCAL_ROOT_DIR/.ci/cache/build-packages.stamp"
    current_hash="$(
        {
            compute_tree_hash "$LOCAL_ROOT_DIR" packages/cli
            cat "$packages_stamp" 2>/dev/null
        } | _sha256sum | awk '{print $1}'
    )"

    saved_hash="$(read_stamp_hash "$stamp_file")"

    if [[ -f "$cli_entry" ]] && [[ "$saved_hash" == "$current_hash" ]]; then
        log_debug "CLI build is up-to-date (stamp matched)"
        return 0
    fi

    log_step "Building CLI..."
    (cd "$LOCAL_ROOT_DIR" && npm run build -w @rediacc/cli)
    (cd "$LOCAL_ROOT_DIR" && npm run build:bundle -w @rediacc/cli)

    if [[ ! -f "$cli_entry" ]]; then
        log_error "CLI build failed: entrypoint not found at $cli_entry"
        exit 1
    fi

    write_stamp_hash "$stamp_file" "$current_hash"
}

# Prompt user to continue with a yes/no question
# Usage: prompt_continue "Message" || exit 1
# Returns: 0 if user confirmed (y/Y), 1 otherwise
prompt_continue() {
    local message="${1:-Continue?}"
    local response

    read -p "$message (y/N): " response
    [[ "$response" =~ ^[yY]$ ]]
}

# Open browser on different platforms
# Usage: open_browser "http://localhost:3000"
open_browser() {
    local url="$1"

    case "$CI_OS" in
        macos)
            open "$url" 2>/dev/null || true
            ;;
        linux)
            if command -v xdg-open &>/dev/null; then
                xdg-open "$url" 2>/dev/null || true
            fi
            ;;
        windows)
            cmd /c start "" "$url" 2>/dev/null || true
            ;;
    esac
}

# Check if a specific package.json script exists
# Usage: has_npm_script "lint" && npm run lint
has_npm_script() {
    local script_name="$1"
    grep -q "\"$script_name\":" "$LOCAL_ROOT_DIR/package.json"
}

# Run npm script with error handling
# Usage: run_npm_script "build:web" "Building web application"
run_npm_script() {
    local script_name="$1"
    local description="${2:-Running npm script: $script_name}"

    log_step "$description"
    (cd "$LOCAL_ROOT_DIR" && npm run "$script_name")
}

# Check Node.js version meets minimum requirement
# Usage: check_node_version "18.0.0"
check_node_version() {
    local min_version="${1:-18.0.0}"
    local current_version

    if ! command -v node &>/dev/null; then
        log_error "Node.js is not installed"
        return 1
    fi

    current_version=$(node -v | cut -d'v' -f2)

    if ! printf '%s\n' "$min_version" "$current_version" | sort -V -C; then
        log_error "Node.js version $current_version is too old (minimum: $min_version)"
        return 1
    fi

    log_debug "Node.js version: $current_version"
    return 0
}

# Check if Go is installed (required for renet build)
check_go_installed() {
    if ! command -v go &>/dev/null; then
        log_error "Go is not installed (required for building renet)"
        log_info "Install Go from: https://go.dev/dl/"
        exit 1
    fi
    log_debug "Go present: $(command -v go)"
}

# Install the Go toolchain if it is missing or too old.
#
# Exists because nothing in this repo installed Go: check_go_installed above
# only prints a go.dev link and exits, which meant `./run.sh setup` could not
# satisfy its own goal on a fresh machine. The version is READ FROM go.mod so it
# cannot drift from what renet actually needs, and the distro package is
# deliberately not used -- Debian 12 ships Go 1.19, which predates the
# `toolchain` directive in private/renet/go.mod and hard-errors on it.
#
# Idempotent: returns immediately when the installed Go is new enough.
ensure_go_installed() {
    local renet_gomod="$LOCAL_ROOT_DIR/private/renet/go.mod"
    local want_version=""

    if [[ -f "$renet_gomod" ]]; then
        # Prefer the toolchain line (go1.25.13); fall back to the go line (1.25.0).
        want_version="$(sed -n 's/^toolchain go\([0-9.]*\).*/\1/p' "$renet_gomod" | head -1)"
        [[ -z "$want_version" ]] && want_version="$(sed -n 's/^go \([0-9.]*\).*/\1/p' "$renet_gomod" | head -1)"
    fi
    if [[ -z "$want_version" ]]; then
        log_error "Cannot determine the required Go version (no readable $renet_gomod)"
        return 1
    fi

    if command -v go &>/dev/null; then
        local have_version
        have_version="$(go version | sed -n 's/.*go\([0-9][0-9.]*\).*/\1/p' | head -1)"
        if _version_gte "$have_version" "$want_version"; then
            log_debug "Go $have_version present (>= $want_version)"
            return 0
        fi
        log_info "Go $have_version is older than the required $want_version"
    fi

    if [[ "$(uname -s)" != "Linux" ]]; then
        log_error "Go $want_version is required and this helper only installs it on Linux"
        log_info "Install it from https://go.dev/dl/ and re-run"
        return 1
    fi

    local arch
    case "$(uname -m)" in
        x86_64 | amd64) arch=amd64 ;;
        aarch64 | arm64) arch=arm64 ;;
        *)
            log_error "Unsupported architecture for the Go tarball: $(uname -m)"
            return 1
            ;;
    esac

    local tarball="go${want_version}.linux-${arch}.tar.gz"
    local url="https://go.dev/dl/${tarball}"
    local tmp
    tmp="$(mktemp -d)"

    log_step "Installing Go ${want_version} (${arch}) into /usr/local/go"
    log_info "$url"
    # Download to a file rather than piping into tar: a 404 page piped to tar
    # fails unreadably, and a truncated download must not half-populate
    # /usr/local/go.
    if ! curl -fL --progress-bar -o "$tmp/$tarball" "$url"; then
        rm -rf "$tmp"
        log_error "Download failed: $url"
        return 1
    fi
    if ! tar -tzf "$tmp/$tarball" >/dev/null 2>&1; then
        rm -rf "$tmp"
        log_error "Downloaded file is not a valid tarball: $tarball"
        return 1
    fi

    sudo rm -rf /usr/local/go
    sudo tar -C /usr/local -xzf "$tmp/$tarball" || {
        rm -rf "$tmp"
        log_error "Failed to unpack $tarball into /usr/local"
        return 1
    }
    rm -rf "$tmp"

    export PATH="/usr/local/go/bin:$PATH"
    if ! command -v go &>/dev/null; then
        log_error "Go was unpacked but /usr/local/go/bin/go is not on PATH"
        return 1
    fi
    log_info "Go installed: $(go version)"

    # Make it durable for future login shells without editing the operator's
    # rc files: /etc/profile.d is the conventional place for a PATH addition.
    if [[ ! -f /etc/profile.d/golang.sh ]]; then
        echo 'export PATH="/usr/local/go/bin:$PATH"' | sudo tee /etc/profile.d/golang.sh >/dev/null
        sudo chmod 0644 /etc/profile.d/golang.sh
        log_info "Added /etc/profile.d/golang.sh (new shells get go on PATH)"
    fi
    return 0
}

# Numeric version compare: is $1 >= $2 ?
_version_gte() {
    [[ "$1" == "$2" ]] && return 0
    local lower
    lower="$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -1)"
    [[ "$lower" == "$2" ]]
}

# Ensure the small host tools the build chain shells out to.
#
# Added because their absence is SILENT: private/renet/build.sh's embed_assets
# returns 1 when jq or zstd is missing (build.sh:166-171), but dev() ignores
# that return (build.sh:731), so the build prints "Renet built successfully",
# writes its stamp, and ships a binary with no embedded CRIU/rsync assets. The
# stamp then matches forever. Installing them up front stops that from being
# reachable in the first place.
ensure_host_tools() {
    local missing=()
    local tool
    for tool in jq zstd curl git; do
        command -v "$tool" &>/dev/null || missing+=("$tool")
    done
    # A C compiler is not optional here: .npmrc sets ignore-scripts, so
    # cpu-features' buildcheck and `npm run install:natives` both compile at
    # install time. Without one, `./run.sh account dev` dies inside npm with
    # "Unable to detect compiler type" -- an error that names neither the
    # missing package nor the command that needed it.
    if ! command -v cc &>/dev/null && ! command -v gcc &>/dev/null; then
        missing+=(build-essential)
    fi
    [[ ${#missing[@]} -eq 0 ]] && return 0

    if [[ "$(uname -s)" != "Linux" ]] || ! command -v apt-get &>/dev/null; then
        log_error "Missing required tools: ${missing[*]}"
        log_info "Install them with your package manager and re-run"
        return 1
    fi

    log_step "Installing host tools: ${missing[*]}"
    sudo apt-get update -qq &&
        sudo apt-get install -y -qq "${missing[@]}" || {
        log_error "Failed to install: ${missing[*]}"
        return 1
    }
    return 0
}

# Re-exec this script with the docker group applied.
#
# After `usermod -aG docker`, the CURRENT shell keeps the group set it was
# created with, so `docker ps` keeps failing until the operator logs out and
# back in -- advice that is both annoying and easy to ignore. `sg` runs a
# command with a group the user is entitled to but has not yet activated, so
# re-executing ourselves under it fixes the problem in place, once, and every
# later docker call in the run is plain `docker`.
#
# Deliberately checks membership in /etc/group rather than `id -nG`: id reports
# the CURRENT process's groups, which is exactly the stale information we are
# working around, so it would answer "no" in the one case that matters.
reexec_with_docker_group() {
    # Already re-executed, or docker already works: nothing to do.
    [[ -n "${REDIACC_DOCKER_GROUP_REEXEC:-}" ]] && return 0
    docker version &>/dev/null && return 0

    command -v docker &>/dev/null || return 0
    command -v sg &>/dev/null || return 0
    getent group docker >/dev/null 2>&1 || return 0

    # Entitled but not active? (members field of the docker group)
    local members
    members="$(getent group docker | cut -d: -f4)"
    [[ ",$members," == *",$USER,"* ]] || return 0

    # Prove it actually helps before re-executing, so a broken daemon does not
    # send us round a pointless loop.
    sg docker -c "docker version" &>/dev/null || return 0

    log_info "Applying your docker group membership to this run (no logout needed)"
    export REDIACC_DOCKER_GROUP_REEXEC=1
    local cmd
    cmd="$(printf '%q ' "$SCRIPT_ENTRYPOINT" "$@")"
    exec sg docker -c "$cmd"
}

# Ensure a working Docker engine, installed the way the rest of the product
# installs Docker.
#
# DRY, deliberately: the only Docker installer in this codebase lives in the
# renet Go binary, and `renet install-docker` documents itself as the single
# source of truth (private/renet/cmd/renet/setup_command.go:80-95). It uses the
# official docker.com apt repository -- keyring, DEB822 source, and the pinned
# set docker-ce/docker-ce-cli/containerd.io/docker-buildx-plugin/
# docker-compose-plugin. It is NOT docker.io; that only appears under
# --source=package-manager, which is never used here.
#
# Reaching that installer needs Go, and building renet does NOT need Docker:
# build.sh's embed_assets skips with a warning when docker is absent
# (private/renet/build.sh:143-149). So the bootstrap order is not circular.
ensure_docker_installed() {
    if docker version &>/dev/null; then
        log_debug "Docker present and usable: $(docker --version 2>/dev/null)"
        return 0
    fi

    # Distinguish "no docker" from "docker installed, user not in the group".
    if command -v docker &>/dev/null && sudo docker version &>/dev/null; then
        log_warn "Docker is installed but not usable as $USER (group membership not active in this shell)"
        _ensure_docker_group
        return 0
    fi

    if [[ "$(uname -s)" != "Linux" ]]; then
        log_error "Automatic Docker installation is Linux-only"
        log_info "Install Docker Desktop, then re-run"
        return 1
    fi

    log_step "Installing Docker via renet's installer (official docker.com repository)"

    ensure_host_tools || return 1
    ensure_go_installed || return 1
    ensure_renet_built || return 1

    local renet_bin="$LOCAL_ROOT_DIR/private/renet/bin/renet"
    [[ -x "$renet_bin" ]] || {
        log_error "renet was built but $renet_bin is not executable"
        return 1
    }

    if ! sudo "$renet_bin" install-docker --source=docker-repo; then
        log_error "renet install-docker failed"
        return 1
    fi

    _ensure_docker_group

    # The first renet build ran without Docker, so its embedded CRIU/rsync
    # assets were skipped -- and _renet_source_hash PRUNES pkg/embed/assets
    # (see above), so the stamp it wrote still matches and ensure_renet_built
    # would return early forever, leaving the binary permanently asset-less.
    # Drop the stamp so the next build re-embeds now that Docker exists.
    rm -f "$LOCAL_ROOT_DIR/.ci/cache/build-renet.stamp"
    log_info "Cleared the renet build stamp so assets get embedded on the next build"
    return 0
}

# Add the invoking user to the docker group and explain the login caveat.
# `renet install-docker` deliberately does not do this: group management lives
# in `renet setup`, which also creates a rediacc system user we do not want on a
# developer machine.
_ensure_docker_group() {
    if ! getent group docker >/dev/null 2>&1; then
        log_warn "No docker group exists; skipping group membership"
        return 0
    fi
    local members
    members="$(getent group docker | cut -d: -f4)"
    if [[ ",$members," == *",$USER,"* ]]; then
        if ! docker version &>/dev/null; then
            log_info "Group membership is not active in this shell; ./run.sh re-execs itself under it automatically."
            log_info "New login shells get it without help."
        fi
        return 0
    fi
    log_step "Adding $USER to the docker group"
    sudo usermod -aG docker "$USER" || {
        log_warn "usermod failed; you will need sudo for docker commands"
        return 0
    }
    log_info "Added. ./run.sh applies it to this run automatically (via sg); new shells get it on login."
    return 0
}

# Compute a content hash of every input that determines the renet binary's
# bytes: all Go/C/H sources, go.mod/go.sum, the build script, and embedded
# proxy/asset inputs. Excludes bin/ (build output) and pkg/embed/assets/*.gz
# (large, deterministic from the Docker image; their presence is checked by
# build.sh). Used to decide whether a rebuild is required.
_renet_source_hash() {
    local renet_dir="$1"
    (
        cd "$renet_dir" || exit
        find . \
            \( -path './bin' -o -path './build' -o -path './pkg/embed/assets' \) -prune -o \
            \( -name '*.go' -o -name '*.c' -o -name '*.h' \
            -o -name 'go.mod' -o -name 'go.sum' -o -name 'build.sh' \
            -o -name 'docker-compose.yml' \) \
            -type f -print0 2>/dev/null |
            LC_ALL=C sort -z |
            xargs -0 $_SHA256SUM_CMD 2>/dev/null |
            $_SHA256SUM_CMD |
            awk '{print $1}'
    )
}

# Ensure renet binary is built and up-to-date.
# Builds from Go source with embedded assets (CRIU, rsync).
#
# Staleness is decided by a CONTENT HASH of the build inputs, not file mtimes.
# The previous mtime-only heuristic (`find -newer bin/renet`) had a real race
# that wasted hours of debugging: any operation that changes a source file's
# CONTENT while giving it an OLDER mtime than the existing binary — `git
# checkout`/`stash pop`/branch switch, editor reverts, `cp -p`, `touch -d` —
# left a binary that did NOT match its source yet looked "fresh", so the build
# (and therefore the SFTP deploy that hashes this binary) was silently skipped.
# A subsequent edit that bumped an mtime past the binary finally triggered the
# rebuild, which is why "running ./rdc.sh a second time" appeared to fix it.
# Hashing the inputs and recording a stamp only after a successful build makes
# the decision exact: the binary is rebuilt iff the inputs differ from what was
# last built, regardless of mtime ordering. The build mode (license flags,
# account key) is folded into the hash so toggling RDC_BENCH / RDC_RENET_LICENSE
# also forces a rebuild.
# size:mtime of a built artifact, empty when absent. GNU stat first, BSD as
# the macOS fallback.
_renet_artifact_fp() {
    stat -c '%s:%Y' "$1" 2>/dev/null || stat -f '%z:%m' "$1" 2>/dev/null || true
}

ensure_renet_built() {
    local renet_dir="$LOCAL_ROOT_DIR/private/renet"
    local renet_bin="$renet_dir/bin/renet"

    # On Windows (Git Bash / MSYS2), Go produces .exe binaries
    case "$(uname -s)" in
        MINGW* | MSYS* | CYGWIN*) renet_bin="$renet_dir/bin/renet.exe" ;;
    esac

    check_go_installed
    # License enforcement is decided in ONE place now — build.sh dev, which
    # defaults to nolicense and opts into enforcement on RDC_RENET_LICENSE=1 /
    # RDC_BENCH=1 (both inherited from this shell's env). No local re-derivation.

    # Hash inputs that determine the binary's bytes. The build mode and the
    # account public key change ldflags, so they are part of the identity.
    # The license mode is now env-derived (build.sh dev reads it), so the stamp
    # hashes the EFFECTIVE mode — a license<->nolicense switch still forces a
    # rebuild even though this function no longer passes a flag.
    local stamp_file="$LOCAL_ROOT_DIR/.ci/cache/build-renet.stamp"
    local _license_mode="nolicense"
    if [[ "${RDC_RENET_LICENSE:-0}" == "1" || "${RDC_BENCH:-0}" == "1" ]]; then
        _license_mode="enforce"
    fi
    local _account_key="${ACCOUNT_ED25519_PUBLIC_KEY:-}"
    if [[ -z "$_account_key" ]] && [[ -f "$renet_dir/../account/.env" ]]; then
        _account_key=$(sed -n 's/^ACCOUNT_ED25519_PUBLIC_KEY=//p' "$renet_dir/../account/.env" | tr -d '\r')
    fi
    # Git-index fast path with the renet-specific full walk as fallback (the
    # generic walk lacks renet's bin//embed-assets prunes, so compute_tree_hash
    # is not usable here).
    local _src_hash
    if ! { _src_hash="$(_git_tree_fingerprint "$renet_dir" .)" && [[ -n "$_src_hash" ]]; }; then
        _src_hash="$(_renet_source_hash "$renet_dir")"
    fi
    local current_hash saved_hash=""
    current_hash="$(
        {
            printf 'src=%s\n' "$_src_hash"
            printf 'license=%s\n' "$_license_mode"
            printf 'key=%s\n' "$_account_key"
        } | _sha256sum | awk '{print $1}'
    )"
    # The stamp hashes the build INPUTS; it says nothing about the artifact.
    # A foreign `go build -o bin/renet` (another session, a stray IDE task)
    # replaces the binary without touching the stamp, and the wrong-flavored
    # binary then deploys to every VM until sources change (paid for live
    # 2026-08-04: an enforcing keyless renet failed the license drill with
    # "public key not configured" while the stamp said fresh). The stamp's
    # second line records the artifact's size:mtime; a mismatch is stale.
    local saved_stamp saved_bin
    saved_stamp="$(read_stamp_hash "$stamp_file")"
    saved_hash="$(printf '%s\n' "$saved_stamp" | sed -n 1p)"
    saved_bin="$(printf '%s\n' "$saved_stamp" | sed -n 's/^bin=//p')"

    if [[ -f "$renet_bin" ]] && [[ -n "$current_hash" ]] && [[ "$saved_hash" == "$current_hash" ]] &&
        [[ -n "$saved_bin" ]] && [[ "$saved_bin" == "$(_renet_artifact_fp "$renet_bin")" ]]; then
        log_debug "Renet binary is up-to-date (stamp matched)"
        return 0
    fi

    if [[ -f "$renet_bin" ]]; then
        log_step "Renet sources changed, rebuilding..."
    else
        log_step "Building renet (first time, requires Docker for asset extraction)..."
    fi

    # Check the build's EXIT CODE, not just whether a binary is on disk.
    # The file-existence test below cannot tell a fresh build from a stale one:
    # when a rebuild failed (e.g. asset staging aborted), the PREVIOUS binary was
    # still present, so this function reported success and wrote a content stamp
    # for sources it had not actually built. The stamp then matched forever and
    # the failure was unrepeatable. Observed live: a Docker-permission failure
    # during asset extraction produced "EXIT=0" and a stamped, asset-less binary.
    if ! (cd "$renet_dir" && ./build.sh dev); then
        log_error "renet build failed (see the output above)"
        return 1
    fi

    if [[ ! -f "$renet_bin" ]]; then
        log_error "Renet build failed: binary not found at $renet_bin"
        exit 1
    fi

    # On non-Linux, also cross-compile Linux binaries for remote provisioning.
    # The CLI uploads these to remote machines via SFTP. We always rebuild these
    # here because we only reach this point when the source hash changed (or the
    # binary was missing), so the previously cross-compiled Linux binaries are
    # likewise stale. Relying on `renet_bin -nt linux_bin` had the same mtime
    # race as the main staleness check.
    if [[ "$(uname -s)" != "Linux" ]]; then
        local _xc_key_ldflags=""
        if [[ -n "$_account_key" ]]; then
            _xc_key_ldflags="-X github.com/rediacc/renet/pkg/license/keys.ProductionPublicKey=$_account_key"
        fi
        local _xc_version
        _xc_version="$(cd "$LOCAL_ROOT_DIR" && git describe --tags --always 2>/dev/null || echo dev)-dev"

        for arch in amd64 arm64; do
            log_step "Cross-compiling renet for linux/${arch} (remote provisioning)..."
            (cd "$renet_dir" && CGO_ENABLED=0 GOOS=linux GOARCH=${arch} go build \
                -ldflags="-s -w -X main.Version=$_xc_version $_xc_key_ldflags" \
                -o "bin/renet-linux-${arch}" ./cmd/renet)
        done
    fi

    # Record the stamp ONLY after a fully successful build (binary + any
    # cross-compiled Linux binaries). If anything above failed we exited
    # non-zero and never get here, so a partial/failed build never marks the
    # tree "fresh" and the next ./rdc.sh will rebuild. Line 2 fingerprints
    # the artifact itself so a foreign overwrite of bin/renet reads as stale.
    write_stamp_hash "$stamp_file" "$current_hash
bin=$(_renet_artifact_fp "$renet_bin")"

    log_info "Renet built successfully"
}

# Export for use in subprocesses
export LOCAL_ROOT_DIR
export LOCAL_CI_DIR
export LOCAL_LIB_DIR

# -----------------------------------------------------------------------------
# GATE LANE: host or devbox, decided ONCE per machine
# -----------------------------------------------------------------------------
#
# WHY A LANE AT ALL. Measured 2026-08-25 on one machine: the host had node
# v24.14.0 / go1.25.13 / shellcheck 0.9.0 while the devbox had node v22.23.2 /
# go1.26.4, and CI installs node 22. The container already matches CI; the host
# is the outlier. A gate that runs in the drifted lane can pass locally and fail
# in CI with no signal that the two ran different code.
#
# WHY STICKY, AND NOT DECIDED PER COMMAND. ensure_deps folds REDIACC_NPM_RUNTIME
# into the node_modules stamp (see its comment above) because the host and the
# image have different glibc, so a native .node built on one side fails to load
# on the other. Every host<->devbox flip therefore costs a full reinstall plus
# native rebuild. An "auto" decision re-taken per invocation would thrash that on
# every command; the honest granularity is per machine, chosen once at setup.
gate_lane_decide() {
    declare -F devbox_state_get >/dev/null 2>&1 || {
        # shellcheck source=/dev/null
        . "${CONSOLE_ROOT_DIR:-$PWD}/.ci/lib/devbox.sh" 2>/dev/null || true
    }
    # 1. We ARE the container. Without this the re-exec recurses forever.
    [[ -n "${REDIACC_IN_DEVBOX:-}" ]] && {
        printf 'host'
        return 0
    }
    # 2. An explicit choice always wins, and is the documented escape hatch.
    case "${REDIACC_LANE:-}" in
        host | devbox)
            printf '%s' "$REDIACC_LANE"
            return 0
            ;;
    esac
    # 3. The sticky choice recorded by setup.
    local sticky
    if sticky="$(devbox_state_get gate_lane 2>/dev/null)" && [[ -n "$sticky" ]]; then
        printf '%s' "$sticky"
        return 0
    fi
    # 4. Otherwise prefer the lane that matches CI, when one is actually running.
    if devbox_container_running 2>/dev/null; then
        printf 'devbox'
    else
        printf 'host'
    fi
}

# TWO FUNCTIONS, NOT ONE, AND THE SPLIT IS THE WHOLE POINT.
#
# This was a single `gate_lane_reexec` whose return code carried two unrelated
# meanings on one channel: 1 meant BOTH "not routed, stay on host" AND "routed,
# and the gate itself exited 1"; 2 meant BOTH "unusable devbox, refuse" AND "the
# routed gate exited 2". The call site could not tell them apart, so a gate that
# FAILED inside the devbox fell through and was re-run on the HOST -- where a
# different toolchain might pass, masking the very failure the lane exists to
# surface. Found in review of 927256e7.
#
# So: a PREDICATE that only ever answers the routing question, and a RUNNER
# whose exit status is only ever the routed command's. Neither can be mistaken
# for the other.

# 0 = route to devbox, 1 = stay on the host, 2 = devbox is unusable, refuse.
gate_lane_should_route() {
    declare -F devbox_container_running >/dev/null 2>&1 || {
        # shellcheck source=/dev/null
        . "${CONSOLE_ROOT_DIR:-$PWD}/.ci/lib/devbox.sh" 2>/dev/null || {
            log_warn "cannot load devbox.sh; staying on the host"
            return 1
        }
    }
    [[ "$(gate_lane_decide)" == devbox ]] || return 1
    devbox_container_running 2>/dev/null || {
        log_warn "gate lane is 'devbox' but no container is running; staying on the host"
        log_info "Start it with ./run.sh devbox up, or pin the lane with REDIACC_LANE=host"
        return 1
    }
    # A broken mount or a wrong exec identity produces a gate that passes having
    # read nothing, so refuse to route rather than degrade to a lane that lies.
    devbox_mount_ok && devbox_identity_ok || {
        log_error "refusing to route gates into an unusable devbox (see ./run.sh devbox doctor)"
        return 2
    }
    return 0
}

# Runs the command in the devbox. Its exit status is the ROUTED COMMAND'S, with
# no other meaning layered on top -- callers must already have decided to route.
gate_lane_run() {
    log_info "lane: devbox (matches CI; REDIACC_LANE=host to opt out)"
    devbox_exec "./run.sh $*"
}
