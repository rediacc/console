#!/bin/bash
# Console development script
# Aligned with CI workflow from .github/workflows/ci.yml
#
# ⚠️  IMPORTANT: When updating this file:
# ⚠️  1. Check if CI scripts need updates (.ci/config/constants.sh)
# ⚠️  2. Test all affected commands

set -euo pipefail

# Root directory
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source configuration and utilities
source "$ROOT_DIR/.ci/config/constants.sh"
# The gate toolchain resolver. Sourced HERE rather than lazily, so a gate that
# needs a pinned tool fails with the version mismatch as its reason rather than
# "toolchain_check: command not found", which names the wrong problem.
source "$ROOT_DIR/.ci/scripts/lib/toolchain.sh"
source "$ROOT_DIR/.ci/lib/local-common.sh"
source "$ROOT_DIR/.ci/lib/service.sh"
source "$ROOT_DIR/.ci/lib/setup.sh"

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

# True if REDIACC_ALLOW_GRAND_REPO contains a `*` entry (machine-level wildcard).
# Accepts a single `*`, a comma-separated list, or a list with `*` mixed in
# (e.g. `repo1,*,repo2`). Whitespace around each entry is trimmed.
# Mirrors isGrandEnvWildcard() in packages/cli/src/utils/grand-env.ts.
_grand_env_is_wildcard() {
    local raw="${REDIACC_ALLOW_GRAND_REPO:-}"
    [[ -z "$raw" ]] && return 1
    local -a entries
    local IFS=','
    # read -ra splits on IFS without performing pathname expansion (critical:
    # a bare `*` in a for-loop would otherwise glob against the cwd).
    read -ra entries <<<"$raw"
    local entry
    for entry in "${entries[@]}"; do
        entry="${entry#"${entry%%[![:space:]]*}"}"
        entry="${entry%"${entry##*[![:space:]]}"}"
        [[ "$entry" == "*" ]] && return 0
    done
    return 1
}

# Check if Docker is running
check_docker() {
    if ! command -v docker &>/dev/null; then
        log_error "Docker is not installed"
        log_info "Install Docker from: https://docs.docker.com/get-docker/"
        exit 1
    fi

    if ! docker info &>/dev/null; then
        log_error "Docker is not running"
        log_info "Start Docker Desktop or Docker daemon"
        exit 1
    fi
}

# Ensure the private/generative working copy is present.
#
# It is NOT a submodule. It is an independent repository that this repo
# gitignores, so `git submodule` commands cannot initialise or recover it: it has
# no .gitmodules entry for them to act on. The previous version of this function
# was named ..._submodule and ran `git submodule sync` + `git submodule update
# --init` here, which silently did nothing and reported a missing checkout as a
# submodule problem. Fail with the real diagnosis instead.
#
# The naming mattered beyond this function: it is the most-read file in the repo,
# so "generative submodule" taught every reader — human and agent — a wrong model
# of the tree, and they then walked past uncommitted work in it.
ensure_generative_repo() {
    if [[ ! -d "$ROOT_DIR/private/generative" ]]; then
        log_error "Missing private/generative directory"
        log_error "It is a separate repository, not a submodule — clone it to private/generative"
        exit 1
    fi

    if [[ ! -e "$ROOT_DIR/private/generative/.git" ]]; then
        log_error "private/generative exists but is not a git checkout"
        log_error "It is a separate repository, not a submodule — re-clone it to private/generative"
        exit 1
    fi
}

ensure_python_installed() {
    if ! command -v python3 &>/dev/null; then
        log_error "python3 is required for tutorial audio generation"
        exit 1
    fi
}

ensure_audio_system_deps() {
    local missing=()
    command -v ffmpeg >/dev/null 2>&1 || missing+=("ffmpeg")
    command -v ffprobe >/dev/null 2>&1 || missing+=("ffmpeg")
    command -v sox >/dev/null 2>&1 || missing+=("sox")

    # The venv toolchain is a dep of this function too, and it used to be invisible here.
    # Probing only the three BINARIES meant a host with ffmpeg but without a working
    # ensurepip installed nothing and failed much later, inside `python3 -m venv`, with
    # "ensurepip is not available" and no hint about which package supplies it.
    # Measured 2026-08-27 on a rebuilt host: ffmpeg present, python3.14-venv absent,
    # every generative venv creation failing.
    local pyver
    pyver="$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || echo "")"
    if ! python3 -c 'import ensurepip' >/dev/null 2>&1; then
        # The VERSIONED name, not the generic python3-venv metapackage: on a host whose
        # python3 is newer than the distro default, the metapackage pulls the wrong one.
        missing+=("python${pyver}-venv")
    fi

    if [[ "${#missing[@]}" -eq 0 ]]; then
        return 0
    fi

    if ! command -v apt-get >/dev/null 2>&1; then
        log_error "Missing system deps: ${missing[*]}"
        log_info "Install them manually (ffmpeg, sox) and retry."
        exit 1
    fi

    log_step "Installing missing system dependencies: ${missing[*]}"
    if command -v sudo >/dev/null 2>&1; then
        sudo apt-get update
        sudo apt-get install -y ffmpeg sox python3-venv python3-dev build-essential \
            ${pyver:+"python${pyver}-venv" "python${pyver}-dev"}
    else
        apt-get update
        apt-get install -y ffmpeg sox python3-venv python3-dev build-essential \
            ${pyver:+"python${pyver}-venv" "python${pyver}-dev"}
    fi
}

install_generative_python_deps() {
    local gen_dir="$1"
    local stamp_file="$2"
    local content_hash="$3"
    local site_packages=""

    site_packages="$(python -c 'import site; print(site.getsitepackages()[0])' 2>/dev/null || true)"
    if [[ -n "$site_packages" ]] && [[ -d "$site_packages" ]]; then
        find "$site_packages" -maxdepth 1 -name '~ransformers*' -exec rm -rf {} + 2>/dev/null || true
    fi

    pip install --upgrade pip
    pip install -e "$gen_dir"
    pip install qwen-tts
    pip install qwen-asr
    install_flash_attn_if_supported
    echo "$content_hash" >"$stamp_file"
}

install_flash_attn_if_supported() {
    # Best-effort accelerator install. Keep generation working even if unavailable.
    if python -c "import flash_attn" >/dev/null 2>&1; then
        log_debug "flash-attn already installed"
        return 0
    fi

    local has_cuda="false"
    has_cuda="$(python -c 'import torch; print("true" if torch.cuda.is_available() else "false")' 2>/dev/null || echo "false")"
    if [[ "$has_cuda" != "true" ]]; then
        log_info "Skipping flash-attn install (CUDA not available in torch)."
        return 0
    fi

    if ! command -v nvcc >/dev/null 2>&1; then
        log_info "Skipping flash-attn install (nvcc not found for source build)."
        return 0
    fi

    log_step "Installing flash-attn acceleration..."
    pip install --upgrade packaging ninja >/dev/null 2>&1 || true
    if ! pip install flash-attn --no-build-isolation; then
        log_warn "flash-attn install failed; continuing without it."
    fi
}

ensure_generative_venv() {
    local clean_venv="$1"
    local gen_dir="$ROOT_DIR/private/generative"
    local venv_dir="$gen_dir/.venv"
    local stamp_file="$venv_dir/.deps-sha256"
    local content_hash

    content_hash="$(
        cd "$gen_dir" &&
            sha256sum pyproject.toml src/tutorial_tts/*.py src/tutorial_tts/*.json | sha256sum | awk '{print $1}'
    )"

    if [[ "$clean_venv" == "true" && -d "$venv_dir" ]]; then
        log_step "Recreating generative Python environment..."
        rm -rf "$venv_dir"
    fi

    if [[ ! -d "$venv_dir" ]]; then
        log_step "Creating generative Python environment..."
        python3 -m venv "$venv_dir"
    fi

    # BLOCKER: the venv activation script is generated at runtime by `python3 -m venv` into a dynamic path; shellcheck cannot follow it statically and never could
    # shellcheck disable=SC1091
    source "$venv_dir/bin/activate"

    if [[ ! -f "$stamp_file" ]] || [[ "$(cat "$stamp_file" 2>/dev/null || true)" != "$content_hash" ]]; then
        log_step "Installing generative Python dependencies..."
        if ! install_generative_python_deps "$gen_dir" "$stamp_file" "$content_hash"; then
            log_warn "Dependency install failed; recreating Python environment and retrying once..."
            deactivate || true
            rm -rf "$venv_dir"
            python3 -m venv "$venv_dir"
            # BLOCKER: the venv activation script is generated at runtime by `python3 -m venv` into a dynamic path; shellcheck cannot follow it statically and never could
            # shellcheck disable=SC1091
            source "$venv_dir/bin/activate"
            install_generative_python_deps "$gen_dir" "$stamp_file" "$content_hash"
        fi
    else
        log_debug "Generative Python dependencies are up-to-date"
    fi
}

# Compute hash of a tutorial script + shared helpers for change detection
_tutorial_script_hash() {
    local script="$1"
    local helpers="$ROOT_DIR/.ci/tutorials/lib/tutorial-helpers.sh"
    cat "$script" "$helpers" 2>/dev/null | sha256sum | awk '{print $1}'
}

# --- VM provisioning ----------------------------------------------------------
# These wrap `rdc ops`, which owns local KVM/QEMU provisioning. They existed as
# call sites with no definitions anywhere in the repo: `./run.sh provision
# start|stop|status` and the tutorial recorder both died with
# "provision_start: command not found" (exit 127). The recorder is the only way
# to regenerate tutorial casts, so that surface was completely unreachable.
#
# `rdc ops up` also writes $_BRIDGE_SSH_CONFIG (see the note below), which is
# what the bridge helpers need, so there is nothing left for a separate
# post-setup step to do -- the recorder bootstraps the bridge itself right
# after provisioning.
provision_start() {
    "$ROOT_DIR/rdc.sh" ops up "$@"
}

provision_stop() {
    "$ROOT_DIR/rdc.sh" ops down
}

provision_status() {
    "$ROOT_DIR/rdc.sh" ops status
}

# --- Bridge recording helpers -------------------------------------------------
# Tutorials are recorded INSIDE the bridge VM so the local host's
# ~/.config/rediacc is never touched and the cast captures a pristine machine.
# Host->bridge SSH uses the config that `renet ops up` generates, which carries
# the correct VM user + key for THIS environment (vscode in CI, the host user
# locally), so we never hardcode either.
_BRIDGE_SSH_CONFIG="$HOME/.renet/staging/.ssh/config"

# Resolve the bridge IP from the provision state, with a sane default.
_bridge_ip() {
    local ip=""
    if [[ -f "$ROOT_DIR/.provision-state" ]]; then
        ip="$(grep '^bridge_ip=' "$ROOT_DIR/.provision-state" 2>/dev/null | cut -d= -f2)"
    fi
    echo "${ip:-${VM_NET_BASE:-${VM_NET_BASE_DEFAULT:-192.168.111}}.${VM_BRIDGE:-${VM_BRIDGE_DEFAULT:-1}}}"
}

# Resolve the Nth worker IP (1-based) from provision state (.11, .12, ...).
_worker_ip() {
    local idx="${1:-1}"
    local ips=""
    if [[ -f "$ROOT_DIR/.provision-state" ]]; then
        ips="$(grep '^worker_ips=' "$ROOT_DIR/.provision-state" 2>/dev/null | cut -d= -f2)"
    fi
    if [[ -n "$ips" ]]; then
        echo "$ips" | cut -d, -f"$idx"
    else
        local -a workers
        read -ra workers <<<"${VM_WORKERS:-11 12}"
        echo "${VM_NET_BASE:-${VM_NET_BASE_DEFAULT:-192.168.111}}.${workers[$((idx - 1))]:-11}"
    fi
}

_bridge_ssh() {
    ssh -F "$_BRIDGE_SSH_CONFIG" -o BatchMode=yes -o StrictHostKeyChecking=no \
        -o ConnectTimeout=15 "$(_bridge_ip)" "$@"
}

_bridge_rsync() {
    rsync -a -e "ssh -F $_BRIDGE_SSH_CONFIG -o BatchMode=yes -o StrictHostKeyChecking=no" "$@"
}

# Build the linux-x64 dev rdc SEA (for the bridge), cached by source hash so
# reruns skip the rebuild when packages/cli, packages/shared, or renet
# are unchanged. Output: dist/cli/rdc-linux-x64. Mirrors `rdc.sh --native`
# but installs nothing on the host.
_build_cli_sea_cached() {
    local out="$ROOT_DIR/dist/cli/rdc-linux-x64"
    local hash_file="$ROOT_DIR/dist/cli/.sea-source-hash"
    local cur
    cur="$(
        {
            find "$ROOT_DIR/packages/cli/src" "$ROOT_DIR/packages/shared/src" \
                -type f \
                \( -name '*.ts' -o -name '*.json' \) -exec sha256sum {} + 2>/dev/null | sort
            git -C "$ROOT_DIR/private/renet" rev-parse HEAD 2>/dev/null || true
        } | sha256sum | awk '{print $1}'
    )"
    if [[ -f "$out" && -f "$hash_file" && "$(cat "$hash_file" 2>/dev/null)" == "$cur" ]]; then
        log_info "Dev SEA up-to-date (source unchanged): $out"
        return 0
    fi

    log_step "Building dev rdc SEA (linux-x64) for the bridge..."
    ensure_deps
    ensure_packages_built
    local embed_renet="$ROOT_DIR/private/bin/renet-linux-amd64"
    mkdir -p "$ROOT_DIR/private/bin"
    # Full renet, all assets. The old `slim` tag existed only because the SEA blob
    # had to stay under postject 1.0.0-alpha.6's ~300 MB injection ceiling (its
    # Emscripten build aborts above that, which is what once made tutorial
    # recording impossible, #525). The streaming injector that replaced postject
    # has no such ceiling, so the bridge now carries the complete k8s stack and a
    # cluster tutorial can be recorded like any other. Per-arch embedding keeps the
    # binary to its own architecture's assets.
    (cd "$ROOT_DIR/private/renet" &&
        CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build \
            -tags "nolicense" -ldflags="-s -w -X main.Version=0.0.0-dev" \
            -o "$embed_renet" ./cmd/renet)
    bash "$ROOT_DIR/.ci/scripts/build/build-cli-executables.sh" --platform linux --arch x64
    [[ -f "$out" ]] || {
        log_error "SEA build did not produce $out"
        exit 1
    }
    echo "$cur" >"$hash_file"
}

# Ensure the bridge has node + asciinema + the dev rdc SEA + the tutorial scripts.
# Idempotent: safe to call before every recording batch (state is ephemeral —
# the bridge is torn down with provision_stop).
_ensure_bridge_recording_tooling() {
    local bridge
    bridge="$(_bridge_ip)"

    # Wait for the bridge to be reachable, then fail loudly if it never is.
    local who="" i
    for i in $(seq 1 15); do
        who="$(_bridge_ssh 'whoami' 2>/dev/null || true)"
        [[ -n "$who" ]] && break
        sleep 2
    done
    if [[ -z "$who" ]]; then
        log_error "Bridge VM ($bridge) is not reachable over SSH."
        log_error "Check 'rdc ops status' / './run.sh provision status' and $_BRIDGE_SSH_CONFIG."
        exit 1
    fi
    log_info "Bridge reachable as user: $who"

    # node + asciinema (bridge has internet + passwordless sudo).
    if ! _bridge_ssh 'command -v node >/dev/null && command -v asciinema >/dev/null'; then
        log_step "Installing node + asciinema on the bridge..."
        _bridge_ssh 'sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq && \
            sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nodejs npm asciinema'
    fi

    # Dev rdc SEA — build (cached) and transfer only when the checksum differs.
    _build_cli_sea_cached
    local sea="$ROOT_DIR/dist/cli/rdc-linux-x64"
    local local_sum remote_sum
    local_sum="$(sha256sum "$sea" | awk '{print $1}')"
    remote_sum="$(_bridge_ssh 'sha256sum /usr/local/bin/rdc 2>/dev/null | cut -d" " -f1' || true)"
    if [[ "$local_sum" != "$remote_sum" ]]; then
        log_step "Transferring dev rdc SEA to the bridge..."
        _bridge_rsync "$sea" "${bridge}:/tmp/rdc-dev"
        _bridge_ssh 'sudo install -m0755 /tmp/rdc-dev /usr/local/bin/rdc && rm -f /tmp/rdc-dev'
    else
        log_info "Bridge rdc up-to-date (checksum match)"
    fi
    log_info "Bridge rdc version: $(_bridge_ssh 'rdc --version 2>/dev/null | tail -1')"

    # Tutorial scripts + post-processors, preserving record.sh's ROOT_DIR=../..
    # layout so it resolves the .mjs post-processors under /tmp/rec/.ci.
    log_step "Syncing tutorial scripts to the bridge..."
    _bridge_ssh 'mkdir -p /tmp/rec/.ci/tutorials /tmp/rec/.ci/scripts/docs /tmp/rec/out'
    _bridge_rsync "$ROOT_DIR/.ci/tutorials/" "${bridge}:/tmp/rec/.ci/tutorials/"
    _bridge_rsync "$ROOT_DIR/.ci/scripts/docs/" "${bridge}:/tmp/rec/.ci/scripts/docs/"
}

# Recorded terminal geometry, single source of truth. Downstream is derived, not
# duplicated: the value is written into each cast header and every renderer reads
# it back (packages/www/scripts/lib/scenes/cast.ts). The width is a legibility
# choice, not a realism one -- the player shows the video at ~800px, so 107
# columns already lands near the readable floor.
TUTORIAL_COLS=107
TUTORIAL_ROWS=32

www_tutorials_record() {
    local force=false
    local keep_vms=false
    local name=""
    local tutorials_dir="$ROOT_DIR/.ci/tutorials"
    local output_dir="$ROOT_DIR/packages/www/public/assets/tutorials"
    local hash_file="$output_dir/.recording-hashes"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --force)
                force=true
                shift
                ;;
            --keep-vms)
                keep_vms=true
                shift
                ;;
            --max-idle-ms)
                export MAX_IDLE_MS="$2"
                shift 2
                ;;
            --max-idle-ms=*)
                export MAX_IDLE_MS="${1#*=}"
                shift
                ;;
            *)
                name="$1"
                shift
                ;;
        esac
    done

    # Tutorials use term connect / repo create which require direct machine access.
    # In AI agent sessions, the user must pre-set REDIACC_ALLOW_GRAND_REPO=* before
    # starting the agent so the CLI accepts the override as legitimate. We propagate
    # it to the bridge's rdc below.
    if [[ "${CLAUDECODE:-}" == "1" || "${GEMINI_CLI:-}" == "1" || "${COPILOT_CLI:-}" == "1" || "${REDIACC_AGENT:-}" == "1" || -n "${CURSOR_TRACE_ID:-}" ]]; then
        if ! _grand_env_is_wildcard; then
            log_error "Tutorial recording requires direct machine access, which is blocked in agent mode."
            log_error ""
            log_error "Set REDIACC_ALLOW_GRAND_REPO=* in your terminal BEFORE starting the agent session:"
            log_error "  export REDIACC_ALLOW_GRAND_REPO=*"
            log_error "  claude  # then run ./run.sh www tutorials record"
            exit 1
        fi
    fi

    # Load stored hashes
    local -A stored_hashes
    if [[ -f "$hash_file" ]]; then
        while IFS='=' read -r key val; do
            stored_hashes["$key"]="$val"
        done <"$hash_file"
    fi

    # Determine candidate scripts
    local candidates=()
    if [[ -n "$name" ]]; then
        # Accept either fully-qualified slug (tutorial-installation) or short name (installation)
        local script="$tutorials_dir/${name}.sh"
        if [[ ! -f "$script" ]]; then
            script="$tutorials_dir/tutorial-${name}.sh"
        fi
        [[ -f "$script" ]] || {
            log_error "Tutorial not found: $tutorials_dir/${name}.sh or tutorial-${name}.sh"
            exit 1
        }
        candidates+=("$script")
    else
        # Record in the DECLARED sequence, never alphabetically. The tutorials are a
        # stateful chain run against one shared cluster and nothing is reset between
        # them (.ci/tutorials/run-sequence.sh), so alphabetical order puts tutorial 11
        # (backup-restore) and 15 (branching) ahead of tutorial 4 (create-repo), which
        # then fails on the state they left behind. The order lives in the docs
        # frontmatter, the same single source of truth run-sequence.sh derives from.
        local docs_dir="$ROOT_DIR/packages/www/src/content/docs/en"
        local ordered_pairs=()
        local doc slug order
        for doc in "$docs_dir"/tutorial-*.mdx; do
            [[ -f "$doc" ]] || continue
            slug="$(basename "$doc" .mdx)"
            order="$(grep -m1 '^order:' "$doc" | tr -dc '0-9')"
            if [[ -z "$order" ]]; then
                log_error "Tutorial doc has no 'order:' frontmatter: $doc"
                exit 1
            fi
            ordered_pairs+=("$(printf '%03d %s' "$order" "$slug")")
        done
        # while-read, not mapfile: bash 3.2 compat, same pattern as run-sequence.sh.
        local _line
        while IFS= read -r _line; do
            [[ -n "$_line" ]] || continue
            local ordered_script="$tutorials_dir/${_line}.sh"
            if [[ ! -f "$ordered_script" ]]; then
                log_error "Tutorial doc ${_line}.mdx has no script $ordered_script"
                exit 1
            fi
            candidates+=("$ordered_script")
        done < <(printf '%s\n' "${ordered_pairs[@]}" | sort | awk '{print $2}')
        # A script with no doc would be silently skipped by the loop above; catch it.
        local script
        for script in "$tutorials_dir"/tutorial-*.sh; do
            [[ -f "$script" ]] || continue
            case " ${candidates[*]} " in
                *" $script "*) ;;
                *)
                    log_error "Tutorial script has no doc, so it has no place in the sequence: $script"
                    exit 1
                    ;;
            esac
        done
    fi

    # Filter by change detection (unless --force)
    local scripts_to_record=()
    for script in "${candidates[@]}"; do
        local base
        base="$(basename "$script" .sh)"
        if [[ "$force" == "true" ]]; then
            scripts_to_record+=("$script")
        else
            local current_hash
            current_hash="$(_tutorial_script_hash "$script")"
            if [[ "${stored_hashes[$base]:-}" != "$current_hash" ]]; then
                scripts_to_record+=("$script")
            else
                log_debug "Unchanged: $base (skipping)"
            fi
        fi
    done

    if [[ ${#scripts_to_record[@]} -eq 0 ]]; then
        log_info "No tutorial scripts changed, skipping recording"
        return 0
    fi

    # Provision the cluster (bridge + workers) and prepare host->bridge SSH.
    log_step "Provisioning VMs for tutorial recording..."
    provision_start

    # Recording runs INSIDE the bridge VM so the local host's ~/.config/rediacc is
    # never touched and the cast captures a pristine machine. Bootstrap the bridge
    # with node + asciinema + the dev rdc SEA + the tutorial scripts.
    _ensure_bridge_recording_tooling
    local bridge
    bridge="$(_bridge_ip)"

    # Stage shared app files (some tutorials consume /tmp/tutorial-app) and push
    # them to the bridge where the recording runs.
    mkdir -p /tmp/tutorial-app
    cat >/tmp/tutorial-app/Rediaccfile <<'TEOF'
#!/bin/bash
up() { renet compose -- up -d; }
down() { renet compose -- down; }
info() { renet compose -- ps; }
TEOF
    cat >/tmp/tutorial-app/docker-compose.yml <<'TEOF'
services:
  web:
    image: nginx:alpine
    ports:
      - "80:80"
TEOF
    _bridge_ssh 'mkdir -p /tmp/tutorial-app'
    _bridge_rsync /tmp/tutorial-app/ "${bridge}:/tmp/tutorial-app/"

    # Resolve the recording env from the live cluster (worker IPs + VM user/home).
    local worker1 worker2 vm_user vm_home
    worker1="$(_worker_ip 1)"
    worker2="$(_worker_ip 2)"
    vm_user="$(_bridge_ssh 'whoami')"
    vm_home="$(_bridge_ssh 'echo $HOME')"
    log_info "Recording on bridge $bridge as $vm_user → worker $worker1 (backup ${worker2:-none})"

    # Record each changed tutorial on the bridge, then pull the cast back. The
    # cast is the only handoff artifact; downstream stages read it unchanged.
    for script in "${scripts_to_record[@]}"; do
        local base
        base="$(basename "$script" .sh)"
        log_step "Recording on bridge: $base"
        # No TUTORIAL_RDC_CMD: use the real rdc in the bridge PATH (setting it to
        # "rdc" would self-recurse — guarded in tutorial-helpers.sh regardless).
        _bridge_ssh "cd /tmp/rec && \
            TUTORIAL_MACHINE_IP='$worker1' \
            TUTORIAL_MACHINE_USER='$vm_user' \
            TUTORIAL_SSH_KEY='$vm_home/.ssh/id_rsa' \
            TUTORIAL_BACKUP_HOST='$worker2' \
            TUTORIAL_BACKUP_USER='$vm_user' \
            REDIACC_ALLOW_GRAND_REPO='${REDIACC_ALLOW_GRAND_REPO:-}' \
            MAX_IDLE_MS='${MAX_IDLE_MS:-800}' \
            bash /tmp/rec/.ci/tutorials/record.sh \
                /tmp/rec/.ci/tutorials/${base}.sh \
                /tmp/rec/out/${base}.cast $TUTORIAL_COLS $TUTORIAL_ROWS"
        _bridge_rsync "${bridge}:/tmp/rec/out/${base}.cast" "$output_dir/${base}.cast"
        log_info "Pulled cast → $output_dir/${base}.cast"

        # Update stored hash
        stored_hashes["$base"]="$(_tutorial_script_hash "$script")"
    done

    # Teardown VMs (skip with --keep-vms when the video render stage needs
    # the cluster + staged repos right after recording).
    if [[ "$keep_vms" == "true" ]]; then
        log_info "--keep-vms: leaving the cluster running"
    else
        log_step "Tearing down VMs..."
        provision_stop
    fi

    # Persist hashes
    : >"$hash_file"
    for key in "${!stored_hashes[@]}"; do
        echo "${key}=${stored_hashes[$key]}" >>"$hash_file"
    done
}

www_tutorials_extract() {
    check_node_version
    ensure_deps
    log_step "Extracting cast markers to transcript scaffolds..."
    npm run transcripts:extract -w @rediacc/www
}

www_tutorials_scaffold_locales() {
    check_node_version
    ensure_deps
    log_step "Scaffolding locale transcript files..."
    npm run transcripts:scaffold-locales -w @rediacc/www
}

www_tutorial_audio_restore() {
    # Best-effort: the tutorial-narration mp3 cache is synced to R2, not
    # committed to git (see .ci/docs/r2-media-setup.md #3). Restoring it
    # before generate/video lets tutorial_tts/cli.py's cache-hit check
    # (keyed on the file existing locally) actually hit, instead of paying
    # for a full TTS re-synthesis on every fresh checkout. Skips with a
    # warning if R2 credentials aren't configured -- local iteration without
    # them still works, just without the cache.
    if [[ -z "${R2_MEDIA_ACCESS_KEY_ID:-}" || -z "${R2_MEDIA_SECRET_ACCESS_KEY:-}" || -z "${R2_MEDIA_ENDPOINT:-}" ]]; then
        log_warn "R2_MEDIA_* not set — skipping tutorial-audio cache restore (will regenerate via TTS as needed)"
        return 0
    fi
    log_step "Restoring tutorial-audio cache from R2..."
    "$ROOT_DIR/.ci/scripts/deploy/sync-media-from-r2.sh" --audio-only || log_warn "Audio cache restore failed, continuing without it"
}

www_tutorial_audio_upload() {
    # Counterpart to www_tutorial_audio_restore: backs up newly-synthesized
    # narration so it's not lost/re-paid-for on the next fresh checkout.
    if [[ -z "${R2_MEDIA_ACCESS_KEY_ID:-}" || -z "${R2_MEDIA_SECRET_ACCESS_KEY:-}" || -z "${R2_MEDIA_ENDPOINT:-}" ]]; then
        log_warn "R2_MEDIA_* not set — skipping tutorial-audio cache upload"
        return 0
    fi
    log_step "Backing up tutorial-audio cache to R2..."
    "$ROOT_DIR/.ci/scripts/deploy/sync-media-to-r2.sh" --audio-only || log_warn "Audio cache upload failed"
}

www_tutorials_generate() {
    check_node_version
    ensure_generative_repo
    ensure_python_installed
    ensure_audio_system_deps
    www_tutorial_audio_restore

    local clean_venv=false
    local destroy_venv=false
    local passthrough=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --clean-venv)
                clean_venv=true
                shift
                ;;
            --destroy-venv)
                destroy_venv=true
                shift
                ;;
            *)
                passthrough+=("$1")
                shift
                ;;
        esac
    done

    ensure_generative_venv "$clean_venv"
    ensure_deps

    export QWEN_TTS_PYTHON_BIN="$ROOT_DIR/private/generative/.venv/bin/python"

    log_step "Generating tutorial audio assets..."
    npm run tutorials:tts:generate -w @rediacc/www -- "${passthrough[@]}"

    www_tutorial_audio_upload

    if [[ "$destroy_venv" == "true" ]]; then
        log_step "Destroying generative Python environment..."
        rm -rf "$ROOT_DIR/private/generative/.venv"
    fi
}

# Thin wrapper over the ONE readiness predicate. The bash enumeration this replaces
# duplicated the same query and had already drifted from it (it silently dropped the
# audio-directory precondition). Emitting "tutorial<TAB>lang" keeps the pool's stdin
# contract unchanged.
#
# Anything after the first two arguments is forwarded to the predicate verbatim, so the
# watch can ask the narrower question (--stale-only --require-provider voxcpm2) without a
# second copy of the invocation existing anywhere.
_tutorial_render_pairs() {
    local name="$1" lang="$2"
    shift 2
    local args=()
    [[ -n "$name" ]] && args+=(--cast "$name")
    [[ -n "$lang" ]] && args+=(--lang "$lang")
    node "$ROOT_DIR/packages/www/scripts/list-tutorial-render-pairs.js" "${args[@]}" "$@"
}

# Default render concurrency from the machine, not a constant. Renders are RAM-heavy
# (headless Chrome ~3 GB each) and must leave room for the narration process, which is
# ~11.8 GB RSS on its own, so both CPU and memory bound the answer.
#
# Shared by `media` and `watch` because both render WHILE narration holds the GPU and so
# face the identical constraint. A second copy of this arithmetic is exactly how the two
# would drift apart. Prints the number on stdout; every log_* line goes to stderr.
_tutorial_auto_jobs() {
    local cores mem_gb by_cpu by_mem jobs
    cores="$(nproc)"
    mem_gb="$(awk '/MemAvailable/ {print int($2/1024/1024)}' /proc/meminfo)"
    by_cpu=$(((cores - 4) / 4))
    by_mem=$(((mem_gb - 16) / 4))
    jobs=$((by_cpu < by_mem ? by_cpu : by_mem))
    [[ "$jobs" -lt 1 ]] && jobs=1
    [[ "$jobs" -gt 6 ]] && jobs=6
    log_step "auto --jobs $jobs (${cores} cores, ${mem_gb} GB available)"
    echo "$jobs"
}

# Render exactly one (tutorial, lang) pair. Writes its OWN failure file rather than
# appending to a shared one, so nothing depends on single-line-append atomicity.
_tutorial_video_render_one() {
    local t="$1"
    local l="$2"
    local failure_file="$3"
    shift 3

    # Guards the language-independent browser-segments cache described above. With
    # lang-major emission this lock is essentially never contended; it exists so that a
    # hand-run invocation, or two orchestrator languages straddling a batch boundary,
    # cannot both record the same scene and copyFileSync over each other.
    local seg_lock="/tmp/rediacc-tut-seg.${t}.lock"

    log_step "  → $t × $l"
    (
        cd "$ROOT_DIR/packages/www" || exit 1
        # nice: renders must never starve the GPU job's own CPU work (the audio VAE, the
        # ffmpeg mastering chain, ASR). Narration is deliberately NOT niced.
        flock "$seg_lock" nice -n 10 \
            npx tsx scripts/generate-tutorial-video.ts --cast "$t" --lang "$l" "$@"
    ) || {
        log_error "  ✗ failed: $t × $l"
        echo "$t × $l" >"$failure_file"
        return 1
    }
}

www_tutorials_video() {
    check_node_version
    ensure_deps
    ensure_audio_system_deps
    www_tutorial_audio_restore

    local name=""
    local lang=""
    local jobs=1
    local passthrough=()
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --lang)
                lang="$2"
                shift 2
                ;;
            --lang=*)
                lang="${1#*=}"
                shift
                ;;
            --jobs)
                jobs="$2"
                shift 2
                ;;
            --jobs=*)
                jobs="${1#*=}"
                shift
                ;;
            --keep-temp | --captions-only | --debug | --refresh-browser-cache | --no-browser-cache)
                passthrough+=("$1")
                shift
                ;;
            *)
                name="$1"
                shift
                ;;
        esac
    done

    if ! [[ "$jobs" =~ ^[0-9]+$ ]] || [[ "$jobs" -lt 1 ]]; then
        log_error "--jobs must be a positive integer, got: $jobs"
        exit 1
    fi

    local pairs=()
    local pair
    while IFS= read -r pair; do
        pairs+=("$pair")
    done < <(_tutorial_render_pairs "$name" "$lang")

    log_step "Compiling tutorial videos (${#pairs[@]} pair(s), --jobs $jobs)..."
    local failure_prefix="/tmp/_tut_video_failures.$$"
    rm -f "${failure_prefix}".*

    _tutorial_video_pool "$jobs" "$failure_prefix" "${passthrough[@]}" < <(printf '%s\n' "${pairs[@]}")

    if compgen -G "${failure_prefix}.*" >/dev/null; then
        log_error "Failed tutorials:"
        cat "${failure_prefix}".* >&2
        rm -f "${failure_prefix}".*
        return 1
    fi
}

# Bounded, STREAMING, globally-bounded render pool. Reads "tutorial<TAB>lang" lines from
# stdin and keeps at most $jobs renders in flight.
#
# It reads from a pipe rather than taking an array because that is what makes the
# orchestrator's overlap possible: work is dispatched as each line ARRIVES, so renders
# for a finished language start while the next language is still being narrated on the
# GPU. A per-language `( ... ) & wait` would instead force a barrier at every language
# boundary -- which either stalls the producer (starving the GPU, defeating the point) or
# multiplies concurrency to jobs×languages.
_tutorial_video_pool() {
    local jobs="$1"
    local failure_prefix="$2"
    shift 2
    local passthrough=("$@")

    local running=0
    local idx=0
    local t l
    while IFS=$'\t' read -r t l; do
        [[ -n "$t" && -n "$l" ]] || continue
        idx=$((idx + 1))
        _tutorial_video_render_one "$t" "$l" "${failure_prefix}.${idx}" "${passthrough[@]}" &
        running=$((running + 1))
        if [[ "$running" -ge "$jobs" ]]; then
            wait -n
            running=$((running - 1))
        fi
    done
    wait
}

# Narrate one language at a time on the GPU, and emit each language's render work to
# STDOUT the moment that language is finished and validated. Everything else goes to
# stderr, including all TTS output, so a stray Python print() can never be mistaken for
# a work item.
_tutorial_media_producer() {
    local name="$1"
    local tts_flags="$2"
    local failure_prefix="$3"
    shift 3
    local langs=("$@")

    local gen_dir="$ROOT_DIR/private/generative"
    local idx=0
    local l
    for l in "${langs[@]}"; do
        idx=$((idx + 1))
        log_step "narrating [$idx/${#langs[@]}] $l (GPU)" >&2

        # Invoked directly rather than through www_tutorials_generate ON PURPOSE. That
        # function calls www_tutorial_audio_restore first, which pulls PUBLISHED audio
        # from R2 and would overwrite narration we just generated, and
        # www_tutorial_audio_upload last, which publishes. This orchestrator generates
        # and renders only; publishing stays an explicit, separate operator decision.
        if ! (
            cd "$gen_dir" &&
                PYTHONPATH=src .venv/bin/python -m tutorial_tts.cli \
                    --repo-root "$ROOT_DIR" --lang "$l" \
                    ${name:+--cast "$name"} $tts_flags
        ) >&2; then
            log_error "narration failed for $l — skipping its renders, continuing to the next language"
            echo "narration: $l" >"${failure_prefix}.tts.${idx}"
            continue
        fi

        # Readiness gate. Not a done-marker written by the producer: this re-derives
        # every transcript hash, step count, replay range and wordTimings ordering from
        # the artifacts, and fails closed when nothing matched. Dispatching renders only
        # AFTER the narration process has exited is also what makes any intermediate
        # state of its timeline writes unobservable.
        if ! node "$ROOT_DIR/packages/www/scripts/validate-tutorial-audio.js" \
            --lang "$l" ${name:+--cast "$name"} --quiet >&2; then
            log_error "validation failed for $l — skipping its renders, continuing to the next language"
            echo "validation: $l" >"${failure_prefix}.val.${idx}"
            continue
        fi

        log_info "$l narrated and validated — dispatching its renders (CPU)" >&2
        _tutorial_render_pairs "$name" "$l"
    done
}

# Narrate on the GPU and render on the CPU AT THE SAME TIME.
#
# The two halves of tutorial media production use disjoint hardware: narration is a
# VoxCPM2 job that saturates the GPU, rendering is headless Chrome plus a software
# x264 encode. Running them in sequence leaves one of the two idle throughout, so the
# wall clock is sum(narrate) + sum(render). Overlapping makes it
# sum(narrate) + render(last language) -- roughly 45% off across 13 languages when the
# two halves cost about the same.
#
# Correctness rests on three things that are enforced elsewhere, not on scheduling luck:
# the GPU lease in tutorial_tts/gpu_lock.py means a second narration can never co-reside
# with the first; timelines are written with os.replace, so a render reading one while
# another language is being narrated sees whole JSON or nothing; and the per-language
# validation gate refuses to dispatch renders for narration that did not finish clean.
www_tutorials_media() {
    check_node_version
    ensure_generative_repo
    ensure_python_installed
    ensure_audio_system_deps

    local name=""
    local langs_csv=""
    local jobs=""
    local clean_venv=false
    local tts_flags=""
    local passthrough=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --langs) langs_csv="$2" && shift 2 ;;
            --langs=*) langs_csv="${1#*=}" && shift ;;
            --jobs) jobs="$2" && shift 2 ;;
            --jobs=*) jobs="${1#*=}" && shift ;;
            --clean-venv) clean_venv=true && shift ;;
            --subtitle | --force | --resubtitle | --keep-wav)
                tts_flags="$tts_flags $1"
                shift
                ;;
            --keep-temp | --captions-only | --debug | --refresh-browser-cache | --no-browser-cache)
                passthrough+=("$1")
                shift
                ;;
            *) name="$1" && shift ;;
        esac
    done

    ensure_generative_venv "$clean_venv"
    ensure_deps

    local langs=()
    if [[ -n "$langs_csv" ]]; then
        IFS=',' read -r -a langs <<<"$langs_csv"
    else
        local d
        for d in "$ROOT_DIR/packages/www/src/data/tutorial-timeline"/*/; do
            [[ -d "$d" ]] || continue
            langs+=("$(basename "$d")")
        done
    fi
    if [[ ${#langs[@]} -eq 0 ]]; then
        log_error "No languages to process."
        return 1
    fi

    if [[ -z "$jobs" ]]; then
        jobs="$(_tutorial_auto_jobs)"
    fi
    if ! [[ "$jobs" =~ ^[0-9]+$ ]] || [[ "$jobs" -lt 1 ]]; then
        log_error "--jobs must be a positive integer, got: $jobs"
        return 1
    fi

    # Hardware encoding stays OFF. h264_nvenc would put the render back on the very
    # device the narration job needs, which is the entire premise of overlapping them.
    if [[ "${RDC_TUTORIAL_HWENC:-0}" == "1" ]]; then
        log_warn "RDC_TUTORIAL_HWENC=1 was set; forcing it to 0 so renders stay off the GPU"
    fi
    export RDC_TUTORIAL_HWENC=0

    # Deliberately NOT calling www_tutorial_audio_restore. It pulls published narration
    # from R2 and would overwrite exactly what this run is about to generate.
    log_step "Tutorial media: narrating ${#langs[@]} language(s) on GPU, rendering on CPU with --jobs $jobs"

    local failure_prefix="/tmp/_tut_media_failures.$$"
    rm -f "${failure_prefix}".*

    _tutorial_media_producer "$name" "$tts_flags" "$failure_prefix" "${langs[@]}" |
        _tutorial_video_pool "$jobs" "$failure_prefix" "${passthrough[@]}"

    if compgen -G "${failure_prefix}.*" >/dev/null; then
        log_error "Failures:"
        cat "${failure_prefix}".* >&2
        rm -f "${failure_prefix}".*
        return 1
    fi
    log_info "Tutorial media complete for: ${langs[*]}"
}

# Emit each (tutorial, lang) pair to STDOUT the moment THAT PAIR's narration is final.
#
# The unit of readiness is the PAIR, not the language: tutorial_tts/cli.py finishes one
# (lang, cast) completely -- synthesis, the deferred alignment barrier, then an atomic
# os.replace of the timeline -- before starting the next. A per-language trigger left the
# CPU idle at load 2.4 for ~20 minutes while 13 already-narrated tutorials sat unrendered.
#
# STDOUT IS THE WORK QUEUE. Every diagnostic goes to stderr (log_step/log_info/log_error
# already do); one stray echo here becomes a bogus render.
#
# The emit-once memo is keyed by the pair's TIMELINE MTIME, and that key choice is doing
# two jobs at once:
#   - no duplicate dispatch while a render is in flight (the pair is still stale, because
#     its mp4 is not written yet, so it is still listed every round);
#   - no hot spin on a pair that keeps failing to render (it stays stale forever, and
#     without the memo it would be re-listed and re-dispatched as fast as the loop turns,
#     never reaching the idle sleep).
# Re-narration bumps the mtime, which changes the key, so a genuinely UPDATED pair IS
# re-emitted. That self-correction is the whole reason readiness is read from artifacts
# rather than from bookkeeping, and it must survive any change here.
_tutorial_watch_producer() {
    local poll="$1"
    local once="$2"
    local langs_csv="$3"
    local queue_file="$4"

    local timeline_root="$ROOT_DIR/packages/www/src/data/tutorial-timeline"
    declare -A emitted=()
    local round=0

    while :; do
        round=$((round + 1))

        # Sample narration liveness BEFORE listing, never after. A pair that lands
        # between the two samples must be caught by the NEXT list rather than lost to a
        # "nothing stale, nothing running" verdict reached on stale evidence.
        #
        # `ps -eo cmd` plus a bracketed pattern, never `pgrep -f`: pgrep -f matches THIS
        # shell, whose own command line contains the pattern, and has already produced a
        # false "alive" verdict in this pipeline. The output is captured into a variable
        # first because `ps | grep -q` under `set -o pipefail` can come back 141 -- grep -q
        # closes the pipe, ps takes SIGPIPE -- which reads as "not running".
        local ps_out narrating=0
        ps_out="$(ps -eo cmd 2>/dev/null || true)"
        if grep -q '[t]utorial_tts\.cli' <<<"$ps_out"; then
            narrating=1
        fi

        # The ONE readiness predicate, asked the narrow question. Failure stops the watch:
        # it refuses on an empty tree on purpose, and a daemon that treated "the predicate
        # broke" as "nothing to do" would idle forever looking healthy.
        if ! _tutorial_render_pairs "" "$langs_csv" --stale-only --require-provider voxcpm2 >"$queue_file"; then
            log_error "readiness predicate failed — stopping the watch instead of guessing"
            return 1
        fi

        local emitted_now=0 stale_now=0
        local t l key mtime timeline
        while IFS=$'\t' read -r t l; do
            [[ -n "$t" && -n "$l" ]] || continue
            stale_now=$((stale_now + 1))
            timeline="$timeline_root/$l/$t.json"
            mtime="$(stat -c %Y "$timeline" 2>/dev/null || stat -f %m "$timeline" 2>/dev/null || echo 0)"
            key="$l/$t@$mtime"
            [[ -n "${emitted[$key]:-}" ]] && continue
            emitted["$key"]=1
            emitted_now=$((emitted_now + 1))
            printf '%s\t%s\n' "$t" "$l"
        done <"$queue_file"

        if [[ "$emitted_now" -gt 0 ]]; then
            log_info "round $round: dispatched $emitted_now newly-ready pair(s) of $stale_now stale"
        fi

        if [[ "$once" == "true" ]]; then
            return 0
        fi

        # Done when there is nothing new to dispatch AND no narrator is left to produce
        # any. Anything still stale at this point has already been emitted, so the pool's
        # final `wait` drains it; stopping here rather than on stale_now == 0 is what keeps
        # a permanently-failing pair from holding the daemon open forever.
        if [[ "$emitted_now" -eq 0 && "$narrating" -eq 0 ]]; then
            log_info "nothing new to render and no tutorial_tts.cli running — producer done after $round round(s)"
            return 0
        fi

        sleep "$poll"
    done
}

# Render each (tutorial, language) pair as soon as that pair's narration is final.
#
# Renders ONLY. It never narrates, and it deliberately does not go through
# www_tutorials_video or www_tutorials_generate: both call www_tutorial_audio_restore,
# which pulls PUBLISHED audio down from R2 and would overwrite exactly the fresh local
# narration this watch exists to consume.
#
# It also never touches the GPU lease. That lease (tutorial_tts/gpu_lock.py) is taken
# LAZILY by the TTS engine at its first real model load; wrapping a renderer in it
# self-deadlocks, which has already happened once in tts_bridge.py.
www_tutorials_watch() {
    # Preflight output is forced onto stderr because stdout belongs to the work queue.
    # ensure_deps shells out to `npm install`, whose "up to date, audited 1105 packages"
    # chatter goes to stdout -- 12 lines of it landed in the --dry-run pair list before
    # this redirect existed, which is exactly the shape of a bogus render.
    {
        check_node_version
        ensure_deps
        ensure_audio_system_deps
    } >&2

    local langs_csv=""
    local jobs=""
    local poll=30
    local once=false
    local dry_run=false
    local passthrough=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --langs) langs_csv="$2" && shift 2 ;;
            --langs=*) langs_csv="${1#*=}" && shift ;;
            --jobs) jobs="$2" && shift 2 ;;
            --jobs=*) jobs="${1#*=}" && shift ;;
            --poll) poll="$2" && shift 2 ;;
            --poll=*) poll="${1#*=}" && shift ;;
            --once) once=true && shift ;;
            --dry-run) dry_run=true && shift ;;
            --keep-temp | --captions-only | --debug | --refresh-browser-cache | --no-browser-cache)
                passthrough+=("$1")
                shift
                ;;
            *)
                log_error "Unknown watch option: $1"
                log_info "Usage: ./run.sh www tutorials watch [--jobs N] [--langs a,b] [--poll N] [--once] [--dry-run]"
                return 1
                ;;
        esac
    done

    if [[ -z "$jobs" ]]; then
        jobs="$(_tutorial_auto_jobs)"
    fi
    if ! [[ "$jobs" =~ ^[0-9]+$ ]] || [[ "$jobs" -lt 1 ]]; then
        log_error "--jobs must be a positive integer, got: $jobs"
        return 1
    fi
    if ! [[ "$poll" =~ ^[0-9]+$ ]] || [[ "$poll" -lt 1 ]]; then
        log_error "--poll must be a positive integer (seconds), got: $poll"
        return 1
    fi

    # Repo-local and session-agnostic, so a watch started from one shell is inspectable
    # from any other. artifacts/ is gitignored.
    local watch_dir="$ROOT_DIR/artifacts/tutorial-render-watch"
    mkdir -p "$watch_dir"
    local lock_file="$watch_dir/watch.lock"
    local pid_file="$watch_dir/watch.pid"
    local queue_file="$watch_dir/queue.txt"
    local log_file
    log_file="$watch_dir/watch-$(date -u +%Y%m%dT%H%M%SZ).log"

    # SINGLE INSTANCE, enforced by the kernel. The per-tutorial flock inside
    # _tutorial_video_render_one serialises two renders of the SAME tutorial; it does
    # nothing to stop two daemons from both deciding to rewrite the same mp4. The kernel
    # lock is the truth and is released when the holder dies, so a killed watch leaves
    # nothing to clean up. The pid file is observability only -- written after the lock is
    # held, and only ever read to name the holder in this error.
    exec 9>"$lock_file"
    if ! flock -n 9; then
        local holder=""
        [[ -f "$pid_file" ]] && holder="$(cat "$pid_file" 2>/dev/null || true)"
        log_error "another tutorial render watch already holds $lock_file (pid ${holder:-unknown})"
        log_info "wait for it to drain, or stop it, before starting a second one"
        return 1
    fi
    echo "$$" >"$pid_file"

    # Everything diagnostic in this pipeline is on stderr (log_step/log_info/log_error
    # all are), so tee'ing stderr once here captures the WHOLE run -- header included --
    # while still showing it live in the foreground. stdout is untouched because it is the
    # work queue: under --dry-run the pair list must stay clean enough to diff.
    exec 2> >(tee -a "$log_file" >&2)

    # Hardware encoding stays OFF: h264_nvenc would put the render back on the very
    # device the narration needs, which is the entire premise of overlapping them.
    if [[ "${RDC_TUTORIAL_HWENC:-0}" == "1" ]]; then
        log_warn "RDC_TUTORIAL_HWENC=1 was set; forcing it to 0 so renders stay off the GPU"
    fi
    export RDC_TUTORIAL_HWENC=0

    local failure_prefix="$watch_dir/failures.$$"
    rm -f "${failure_prefix}".*

    log_step "Tutorial render watch: --jobs $jobs, --poll ${poll}s${langs_csv:+, langs $langs_csv}"
    log_info "pid $$, lock $lock_file, log $log_file"

    local status=0
    if [[ "$dry_run" == "true" ]]; then
        # The producer's stdout IS the work queue, so printing it is the dry run: the pool
        # is never started and not one render is dispatched.
        _tutorial_watch_producer "$poll" "$once" "$langs_csv" "$queue_file" || status=$?
    else
        _tutorial_watch_producer "$poll" "$once" "$langs_csv" "$queue_file" |
            _tutorial_video_pool "$jobs" "$failure_prefix" "${passthrough[@]}" || status=$?
    fi

    rm -f "$pid_file"

    if compgen -G "${failure_prefix}.*" >/dev/null; then
        log_error "Render failures (recorded and NOT retried — re-narrate the pair to make it eligible again):"
        cat "${failure_prefix}".* >&2
        rm -f "${failure_prefix}".*
        status=1
    fi

    if [[ "$status" -ne 0 ]]; then
        return "$status"
    fi
    log_info "Tutorial render watch finished cleanly"
}

www_tutorials_validate() {
    check_node_version
    ensure_deps
    log_step "Validating tutorial cast output..."
    npm run validate:tutorial-cast-output -w @rediacc/www
    log_step "Validating tutorial transcripts..."
    npm run validate:tutorial-transcripts -w @rediacc/www
    log_step "Validating tutorial audio..."
    npm run validate:tutorial-audio -w @rediacc/www
    # Web<->video parity (cast markers vs storyboard vs transcript vs MDX, incl.
    # card.commandFull). Mirrors CI's check:ci-tutorial-parity so local runs catch drift.
    log_step "Checking tutorial web/video parity..."
    npm run check:ci-tutorial-parity
}

www_tutorials_all() {
    # Split args: --lang / --keep-temp / --clean-venv / --destroy-venv only flow
    # to the steps that understand them. Everything else is treated as a
    # tutorial-name positional and passed to record + generate + video.
    local lang_args=()
    local audio_args=()
    local video_args=()
    local record_args=()
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --lang)
                lang_args+=("$1" "$2")
                shift 2
                ;;
            --lang=*)
                lang_args+=("$1")
                shift
                ;;
            --keep-temp)
                video_args+=("$1")
                shift
                ;;
            --clean-venv | --destroy-venv | --subtitle)
                audio_args+=("$1")
                shift
                ;;
            --force)
                record_args+=("$1")
                shift
                ;;
            --max-idle-ms)
                record_args+=("$1" "$2")
                shift 2
                ;;
            --max-idle-ms=*)
                record_args+=("$1")
                shift
                ;;
            *)
                record_args+=("$1")
                shift
                ;;
        esac
    done

    log_step "Running full tutorial pipeline..."
    www_tutorials_record ${record_args[@]+"${record_args[@]}"}
    www_tutorials_extract
    www_tutorials_scaffold_locales
    www_tutorials_generate ${audio_args[@]+"${audio_args[@]}"} ${lang_args[@]+"${lang_args[@]}"}
    www_tutorials_video ${video_args[@]+"${video_args[@]}"} ${lang_args[@]+"${lang_args[@]}"}
    www_tutorials_validate
    log_info "Tutorial pipeline complete!"
}

# =============================================================================
# TEAM VIDEO COMMANDS
# =============================================================================

# =============================================================================
# WWW ALL
# =============================================================================

www_all() {
    log_step "Running full www asset pipeline..."
    www_tutorials_all "$@"
    log_info "All www assets generated!"
}

# =============================================================================
# DEVELOPMENT COMMANDS
# =============================================================================

dev() {
    check_node_version

    log_step "Starting www development server"

    # Same reasoning as setup(): ensure_deps carries the hash stamp, and its
    # mtime test here was a weaker duplicate of it.
    ensure_deps

    # Start dev server (marketing site)
    npm run dev -w @rediacc/www
}

# =============================================================================
# TEST COMMANDS
# =============================================================================

test_unit() {
    check_node_version
    ensure_packages_built
    log_step "Running unit tests"
    "$ROOT_DIR/.ci/scripts/test/run-unit.sh" "$@"
}

test_bridge() {
    check_node_version
    ensure_packages_built

    log_step "Running E2E tests"
    "$ROOT_DIR/.ci/scripts/test/run-e2e.sh" "$@"
}

test_all() {
    test_unit
}

# =============================================================================
# BUILD COMMANDS
# =============================================================================

build_cli() {
    check_node_version
    log_step "Building CLI application"
    "$ROOT_DIR/.ci/scripts/build/build-cli.sh"
}

build_packages() {
    check_node_version
    log_step "Building shared packages"
    "$ROOT_DIR/.ci/scripts/setup/build-packages.sh"
}

build_renet() {
    check_go_installed
    log_step "Building renet binary"
    local renet_dir="$ROOT_DIR/private/renet"
    (cd "$renet_dir" && ./go dev)

    if [[ ! -f "$renet_dir/bin/renet" ]]; then
        log_error "Renet build failed"
        exit 1
    fi

    log_info "Renet built: private/renet/bin/renet"
}

build_all() {
    check_node_version
    log_step "Building all components"
    build_packages
    build_cli
}

# =============================================================================
# PR COMMANDS
# =============================================================================

pr_publish() {
    check_node_version
    require_var CLOUDFLARE_API_TOKEN

    if ! command -v gh &>/dev/null; then
        log_error "GitHub CLI (gh) is not installed"
        log_info "Install from: https://cli.github.com/"
        exit 1
    fi

    # Auto-discover Cloudflare account ID from GitHub repo variables
    if [[ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]]; then
        log_step "Fetching CLOUDFLARE_ACCOUNT_ID from repo variables..."
        CLOUDFLARE_ACCOUNT_ID=$(gh variable get CLOUDFLARE_ACCOUNT_ID 2>/dev/null) || {
            log_error "Failed to fetch CLOUDFLARE_ACCOUNT_ID from repo variables"
            log_info "Set CLOUDFLARE_ACCOUNT_ID env var or check 'gh auth status'"
            exit 1
        }
        export CLOUDFLARE_ACCOUNT_ID
    fi

    log_step "Discovering PR number..."
    local pr_number
    pr_number=$(gh pr view --json number -q .number 2>/dev/null) || {
        log_error "No PR found for current branch"
        log_info "Push your branch and open a PR first"
        exit 1
    }
    log_info "PR #${pr_number} → https://pr-${pr_number}.rediacc.workers.dev"

    # Source private/account/.env for secrets and R2 credentials
    local account_env="$ROOT_DIR/private/account/.env"
    local env_vars=""
    if [[ -f "$account_env" ]]; then
        env_vars=$(set -a && source "$account_env" && set +a && env)
    fi
    _env() { echo "$env_vars" | grep "^$1=" | head -1 | cut -d= -f2-; }

    # Build shared packages
    log_step "Building shared packages..."
    build_packages

    # Build static sites (set PUBLIC_SITE_URL so install commands point to the preview)
    local preview_url="https://pr-${pr_number}.rediacc.workers.dev"

    log_step "Building www (marketing site)..."
    PUBLIC_SITE_URL="$preview_url" PUBLIC_REPO_CHANNEL="pr-${pr_number}" npm run build:www

    log_step "Building json (template catalog)..."
    npm run build:json

    # Build CLI binary (linux-x64) and upload to R2 channel via wrangler
    local cli_version
    cli_version=$(git describe --tags --match 'v*' --abbrev=0 2>/dev/null | sed 's/^v//' || echo "0.0.0-dev")
    local channel="pr-${pr_number}"

    log_step "Building CLI binary (linux-x64)..."
    "$ROOT_DIR/.ci/scripts/build/build-cli-executables.sh" --platform linux --arch x64

    log_step "Generating CLI manifest..."
    bash "$ROOT_DIR/.ci/scripts/build/generate-cli-manifest.sh" \
        --version "$cli_version" --input dist/cli/

    log_step "Uploading CLI binary to R2 (channel: ${channel})..."
    local r2_bucket="rediacc-releases"
    for f in dist/cli/rdc-*; do
        [[ -f "$f" ]] || continue
        local fname
        fname="$(basename "$f")"
        npx wrangler r2 object put "${r2_bucket}/cli/${channel}/${fname}" --file "$f" --content-type application/octet-stream --remote
    done
    if [[ -f "dist/cli/manifest.json" ]]; then
        npx wrangler r2 object put "${r2_bucket}/cli/${channel}/manifest.json" --file dist/cli/manifest.json --content-type application/json --remote
    fi
    echo "{\"version\":\"${cli_version}\"}" >/tmp/latest.json
    npx wrangler r2 object put "${r2_bucket}/cli/${channel}/latest.json" --file /tmp/latest.json --content-type application/json --remote
    rm -f /tmp/latest.json
    log_info "CLI binary uploaded to R2 channel: ${channel}"

    # Assemble pages into workers/www/dist/
    log_step "Assembling pages..."
    "$ROOT_DIR/.ci/scripts/build/build-pages.sh" --output dist/pages

    # Install script defaults (channel, server URL) are rewritten at runtime
    # by the worker based on the deployment hostname. No sed needed.

    # Build account portal
    log_step "Building account portal..."
    (cd "$ROOT_DIR/private/account/web" && npm install && npx vite build --outDir ../../../workers/www/dist/account)

    # Install www worker deps
    (cd "$ROOT_DIR/workers/www" && npm install)

    # Deploy
    log_step "Deploying pr-${pr_number}..."
    "$ROOT_DIR/.ci/scripts/deploy/deploy-www.sh" --name "pr-${pr_number}"

    # Set worker secrets from private/account/.env (secrets persist across deploys)
    local worker_name="pr-${pr_number}"
    if [[ -f "$account_env" ]] && [[ -n "$(_env ED25519_PRIVATE_KEY)" ]]; then
        log_step "Setting worker secrets for ${worker_name} (from private/account/.env)..."

        # Build secrets JSON, omitting empty values to avoid zod .min(1) failures
        jq -n \
            --arg ed25519_priv "$(_env ED25519_PRIVATE_KEY)" \
            --arg ed25519_pub "$(_env ED25519_PUBLIC_KEY)" \
            --arg x25519_priv "$(_env X25519_PRIVATE_KEY)" \
            --arg x25519_pub "$(_env X25519_PUBLIC_KEY)" \
            --arg api_key "$(_env API_KEY)" \
            --arg jwt "$(_env JWT_SECRET)" \
            --arg stripe "$(_env STRIPE_SANDBOX_SECRET_KEY)" \
            --arg stripe_wh "$(_env STRIPE_WEBHOOK_SECRET)" \
            --arg admin "$(_env ROOT_EMAIL)" \
            --arg ses_key "$(_env AWS_SES_ACCESS_KEY_ID)" \
            --arg ses_secret "$(_env AWS_SES_SECRET_ACCESS_KEY)" \
            --arg ses_region "$(_env AWS_SES_REGION)" \
            --arg ses_from "$(_env AWS_SES_FROM)" \
            --arg ses_cs "$(_env AWS_SES_CONFIGURATION_SET)" \
            --arg turnstile "$(_env TURNSTILE_SECRET_KEY)" \
            '{
              ED25519_PRIVATE_KEY: $ed25519_priv,
              ED25519_PUBLIC_KEY: $ed25519_pub,
              X25519_PRIVATE_KEY: $x25519_priv,
              X25519_PUBLIC_KEY: $x25519_pub,
              API_KEY: $api_key,
              JWT_SECRET: $jwt,
              STRIPE_SECRET_KEY: $stripe,
              STRIPE_WEBHOOK_SECRET: $stripe_wh,
              ROOT_EMAIL: $admin,
              AWS_SES_ACCESS_KEY_ID: $ses_key,
              AWS_SES_SECRET_ACCESS_KEY: $ses_secret,
              AWS_SES_REGION: $ses_region,
              AWS_SES_FROM: $ses_from,
              AWS_SES_CONFIGURATION_SET: $ses_cs,
              TURNSTILE_SECRET_KEY: $turnstile
            } | with_entries(select(.value != ""))' | npx wrangler secret bulk --name "$worker_name"

        log_info "Secrets set for ${worker_name}"
    else
        log_warn "Skipping secrets (private/account/.env missing or empty)"
        log_info "Secrets persist across deploys. Run './run.sh account reset' to generate .env."
    fi

    log_info "Published to https://pr-${pr_number}.rediacc.workers.dev"
}

# =============================================================================
# QUALITY COMMANDS
# =============================================================================

quality_lint() {
    check_node_version
    log_step "Running lint checks"
    npm run lint -- --max-warnings 0
    npm run lint:unused
}

quality_format() {
    check_node_version
    log_step "Checking code formatting"
    npm run check:format
}

quality_types() {
    check_node_version
    log_step "Checking TypeScript types"
    npm run typecheck
}

quality_all() {
    check_node_version
    log_step "Running all quality checks"
    npm run quality

    # Shell formatting/linting. THIS USED TO SKIP AND RETURN SUCCESS.
    #
    # `command -v shfmt` + log_warn + fall through meant that on any machine
    # without shfmt -- which is every non-Debian host, and was this very box
    # until someone hand-installed it -- `./run.sh quality all` reported GREEN
    # having never run a shell gate. A gate that cannot run must not be
    # indistinguishable from a gate that passed.
    #
    # It is also not enough for shfmt to merely EXIST: a different version
    # formats differently, so an unpinned binary on PATH silently decides the
    # verdict. toolchain_check accepts it only AT the pin.
    if toolchain_check shfmt >/dev/null 2>&1; then
        quality_shell
    else
        log_error "shell gates cannot run here:"
        toolchain_check shfmt 2>&1 | sed 's/^/    /' >&2
        log_info "Run them in the devbox instead: ./run.sh devbox exec -- ./run.sh quality shell"
        log_info "Or see what every lane has: .ci/scripts/lib/toolchain.sh --report"
        return 1
    fi
}

quality_deps() {
    check_node_version
    "$ROOT_DIR/.ci/scripts/quality/check-deps.sh"
}

quality_actions() {
    check_node_version
    log_step "Checking GitHub Actions versions..."
    npx tsx "$ROOT_DIR/scripts/check-actions.ts"
}

quality_dead_bash() {
    check_node_version
    log_step "Checking for dead shell functions and orphaned scripts..."
    npx tsx "$ROOT_DIR/scripts/check-dead-bash.ts"
}

quality_suppressions() {
    check_node_version
    log_step "Checking suppression liveness (are allowlist entries still needed?)..."
    npx tsx "$ROOT_DIR/scripts/check-suppression-liveness.ts"
}

quality_audit() {
    check_node_version
    "$ROOT_DIR/.ci/scripts/security/audit.sh"
}

quality_shell() {
    "$ROOT_DIR/.ci/scripts/security/shellcheck.sh"
    "$ROOT_DIR/.ci/scripts/security/shfmt.sh"
}

quality_submodules() {
    log_step "Checking submodule branch alignment"
    "$ROOT_DIR/.ci/scripts/quality/check-submodule-branches.sh"
}

# =============================================================================
# FIX COMMANDS
# =============================================================================

fix_format() {
    check_node_version
    log_step "Auto-fixing code formatting"
    npm run fix:format
}

fix_lint() {
    check_node_version
    log_step "Auto-fixing linting issues"
    npm run fix:lint
}

fix_all() {
    check_node_version
    log_step "Auto-fixing all issues"
    npm run fix:all
}

fix_shell() {
    log_step "Auto-fixing shell script formatting"
    # THE SAME BINARY THE GATE VERIFIES WITH. This used to take whatever `shfmt`
    # was on PATH while .ci/scripts/security/shfmt.sh checked with the pinned
    # one, so `./run.sh fix shell` could reformat a file into a state the gate
    # then rejected -- the nastiest shape of a version split, because the tool
    # that is supposed to fix the problem creates it.
    local shfmt_bin
    if ! shfmt_bin="$(toolchain_acquire shfmt)"; then
        log_error "shfmt is unusable, so formatting would not match the gate"
        log_info "Every lane's toolchain: .ci/scripts/lib/toolchain.sh --report"
        exit 1
    fi
    find .ci -name "*.sh" -type f -exec "$shfmt_bin" -i 4 -ci -w {} +
    "$shfmt_bin" -i 4 -ci -w ./run.sh
    if [[ -d "scripts/dev" ]]; then
        find scripts/dev -name "*.sh" -type f -exec "$shfmt_bin" -i 4 -ci -w {} +
    fi
    # log_info, not log_success: the latter is defined locally inside
    # .ci/scripts/security/shellcheck.sh and is NOT in the shared common.sh this
    # script sources, so the call died with "log_success: command not found"
    # after the formatting had already succeeded.
    log_info "Shell scripts formatted"
}

# =============================================================================
# CHECK COMMANDS (PRE-PUSH VALIDATION)
# =============================================================================

check_quick() {
    check_node_version
    log_step "Running quick checks"
    npm run check:lint || exit 1
    npm run check:format || exit 1
    npm run typecheck || exit 1
    log_info "Quick checks passed!"
}

check_full() {
    check_node_version
    log_step "Running full validation"

    log_step "Phase 1/3: Quality Checks"
    quality_all || exit 1

    log_step "Phase 2/3: Security Audit"
    quality_audit || exit 1

    log_step "Phase 3/3: Unit Tests"
    test_unit || exit 1

    log_info "Full validation passed!"
}

# =============================================================================
# SETUP
# =============================================================================

# Prepare this machine for development and hand back a URL.
#
# Idempotent by construction: every phase is guarded, so a second run installs
# nothing, pulls nothing and recreates nothing -- it just prints the URL again.
#
#   1. toolchain node/gcc/Go/gh/jq          (INSTALLED, not just checked)
#   2. account   git identity + credentials (asked once, then remembered)
#   3. docker    Go -> renet -> install-docker (skipped entirely if docker works)
#   4. image     pull the devcontainer image  (skipped if present)
#   5. devbox    one container per worktree; port from its path, hostname from its branch
#   6. report    the URL to open
setup() {
    local do_check=false force_pull=false do_start=true

    # Make docker usable in THIS run if the group was added but not activated.
    SCRIPT_ENTRYPOINT="$ROOT_DIR/run.sh" reexec_with_docker_group setup "$@"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --check)
                do_check=true
                shift
                ;;
            --pull)
                force_pull=true
                shift
                ;;
            --no-start)
                do_start=false
                shift
                ;;
            --help | -h)
                cat <<'EOF'
Usage: ./run.sh setup [OPTIONS]

  --check      Report what is missing and change nothing
  --pull       Re-pull the devcontainer image even if present
  --no-start   Prepare the host and image, but do not create the container
  --help       Show this help

Related: ./run.sh devbox [up|status|stop|remove|shell|logs]
EOF
                return 0
                ;;
            *)
                log_error "Unknown option for setup: $1"
                return 2
                ;;
        esac
    done

    # shellcheck source=/dev/null
    source "$ROOT_DIR/.ci/lib/devbox.sh"

    if [[ "$do_check" == true ]]; then
        setup_check
        return $?
    fi

    log_step "Rediacc console setup"
    echo ""

    # TOOLCHAIN, AND IT IS ALLOWED TO INSTALL. Two waves wrote this function on
    # the same day and the rebase offered them as either/or, which they are not:
    # 0826-2 built the devcontainer flow whose step 1 CHECKED for tooling and
    # never installed it, and 0826-3 built the installers because a bare machine
    # stopped at that check with a bare report. The check was the gap; these are
    # what fills it.
    setup_node_toolchain || return 1
    check_node_version "${NODE_VERSION_MIN:-22.0.0}" || return 1
    echo ""

    # Before npm install: install:natives hard-requires a compiler.
    setup_system_tools || return 1
    echo ""

    # Submodules BEFORE the first phase that READS one, and the merge moved
    # which phase that is. 0826-2 put this immediately before the docker phase,
    # correctly, because that phase read private/renet/go.mod. 0826-3's
    # setup_go_toolchain reads the SAME file and now runs earlier, so leaving
    # the init where it was would resurrect the exact failure the comment below
    # describes -- on a fresh clone, "Cannot determine the required Go version",
    # a message that never mentions submodules. check:ci-setup-idempotency
    # caught this ordering, which is the whole reason that gate exists.
    #
    # Best-effort (`|| true`) for the same reason devcontainer.json is: a
    # developer without access to every private submodule should still get a
    # working devbox.
    if [[ -f "$ROOT_DIR/.gitmodules" ]]; then
        log_step "Initializing submodules"
        bash "$ROOT_DIR/.devcontainer/init-submodules.sh" --quiet || true
        echo ""
    fi

    # Mandatory: ./rdc.sh rebuilds renet from source and stops dead without Go.
    setup_go_toolchain || return 1
    echo ""

    # Mandatory: the PR guards fail closed without gh.
    setup_gh_cli || return 1
    echo ""

    # KEPT, not replaced. ensure_host_tools also checks zstd, curl and git,
    # which none of the installers above cover, so deleting it would quietly
    # narrow the preflight while looking like a simplification. After the
    # installers it should pass; if it does not, it names what is still missing.
    ensure_host_tools || return 1
    echo ""

    log_step "Git and GitHub account"
    setup_git_identity
    setup_git_credentials || return 1
    echo ""

    # Dependencies THROUGH ensure_deps, never a raw npm install: it hashes
    # package.json, package-lock.json and .npmrc and skips on a match, so a
    # second setup does not recompile cpu-features through node-gyp for nothing.
    ensure_deps

    # Credential-drift REPORT, advisory and never fatal. The bench equivalent in
    # scripts/dev/deploy-bench.sh blocks and is right to -- it guards a DEPLOY.
    # Setup ships nothing, and blocking a developer's bootstrap on a credential
    # only an ops owner can rotate strands the one person who cannot fix it.
    # Reported at all because nothing else reports it: a rotated-out SES key sat
    # in private/account/.env until the stop hook's operator email began 403ing
    # days later, with the symptom several steps removed from the cause. That
    # consumer has since been removed; the exposure has not, because run.sh
    # itself pushes the same quartet into the account worker's secrets.
    #
    # It compares IDENTIFIERS against rotation-manifest.json, never secrets, and
    # never contacts a provider: liveness is `rotation check`'s job and needs
    # admin credentials. Skips loudly when the private submodule is absent.
    if [[ "${SKIP_ENV_DRIFT_CHECK:-}" != "1" ]] && [[ -f "$ROOT_DIR/private/account/.env" ]]; then
        echo ""
        log_step "Credential drift check"
        if ! npm run --silent check:env-credential-drift; then
            log_warn "A credential in private/account/.env is not in the rotation manifest."
            log_warn "ROTATION IS AN OPS TASK, NOT A DEVELOPER ONE, so this does not stop setup."
            log_warn "It surfaces later as an unrelated failure (a 403 from an API days on),"
            log_warn "and the developer who hits that is not the person who can fix it."
            log_warn "Whoever owns rotation: ./run.sh rotation rotate <slug>"
        fi
    fi

    if ! ensure_docker_installed; then
        log_error "Docker could not be prepared; cannot continue"
        return 1
    fi

    if ! devbox_ensure_image "$force_pull"; then
        log_error "Could not obtain $DEVBOX_IMAGE"
        return 1
    fi

    if [[ "$do_start" != true ]]; then
        log_info "Host prepared. Create the container with: ./run.sh devbox up"
        return 0
    fi

    devbox_up || return 1

    # THE URLS ARE THE DELIVERABLE. devbox_up has already printed the probed
    # route table, so these two lines are the bookmark, not the report: the pair
    # a person actually needs after a fresh machine setup. Terminal is named
    # explicitly because it is new and nothing else would tell anyone it exists.
    echo ""
    log_info "Setup complete."
    log_info "  VS Code:  $(devbox_url)"
    log_info "  Terminal: $(devbox_url term)   tmux in the browser"
    echo ""
    log_info "Everything below runs INSIDE the devbox:"
    log_info "  ./run.sh account dev    start the account dev stack"
    log_info "  ./run.sh account db     browse the dev database"
    log_info "  ./run.sh devbox shell   a shell in the container"
    return 0
}

# Report-only counterpart of setup(). Must never mutate anything: it is what an
# operator runs to find out why setup would do work, and what the CI gate drives.
setup_check() {
    local pending=0

    log_step "Setup status for $(devbox_worktree)"
    echo ""

    if command -v node &>/dev/null; then
        printf '  node        %s\n' "$(node --version)"
    else
        printf '  node        MISSING (install Node >= %s)\n' "$NODE_VERSION_MIN"
        pending=$((pending + 1))
    fi

    if command -v go &>/dev/null; then
        printf '  go          %s\n' "$(go version | awk '{print $3}')"
    else
        printf '  go          absent (setup installs it only if docker is missing)\n'
    fi

    # THE PHASES THE MERGE ADDED TO setup() MUST ALSO BE REPORTED HERE. This
    # function's whole contract is to be the report-only counterpart -- what an
    # operator runs to find out why setup would do work -- so a phase that setup
    # performs and check does not mention makes the count a lie. Caught by
    # running `--check` after merging the two waves' setup(): it said "2 item(s)
    # would be acted on" while setup would also have installed gh and written a
    # git identity.
    if command -v gh &>/dev/null; then
        printf '  gh          %s\n' "$(gh --version | head -1 | awk '{print $3}')"
    else
        printf '  gh          MISSING (setup installs it; the PR guards fail closed without it)\n'
        pending=$((pending + 1))
    fi

    if command -v cc &>/dev/null || command -v gcc &>/dev/null; then
        printf '  compiler    %s\n' "$( (cc --version 2>/dev/null || gcc --version) | head -1 | awk '{print $1, $NF}')"
    else
        printf '  compiler    MISSING (setup installs build-essential; install:natives needs it)\n'
        pending=$((pending + 1))
    fi

    if [[ -n "$(git config --global user.email 2>/dev/null)" ]]; then
        printf '  git identity %s\n' "$(git config --global user.email)"
    else
        printf '  git identity UNSET (setup asks for it once, then remembers)\n'
        pending=$((pending + 1))
    fi

    if docker version &>/dev/null; then
        printf '  docker      %s\n' "$(docker --version | sed 's/,.*//')"
    elif command -v docker &>/dev/null; then
        printf '  docker      installed but NOT usable as %s (log out/in, or newgrp docker)\n' "$USER"
        pending=$((pending + 1))
    else
        printf '  docker      MISSING (setup installs it via renet install-docker --source=docker-repo)\n'
        pending=$((pending + 1))
    fi

    if devbox_image_present; then
        printf '  image       present (%s)\n' "$DEVBOX_IMAGE"
    else
        printf '  image       MISSING (%s)\n' "$DEVBOX_IMAGE"
        pending=$((pending + 1))
    fi

    # THE '?' FALLBACK WAS A LANDMINE. run.sh is `set -euo pipefail`, and
    # $(('?' + N)) is an arithmetic syntax error ("operand expected"), so the
    # printf never ran and setup_check ABORTED. The visible symptom would have
    # been check-setup-idempotency failing with "setup --check never mentioned
    # 'port block'" -- a gate failure naming the wrong cause entirely. It is
    # unreachable today only because find_port_block walks all 100 slots before
    # giving up, which is luck, not design.
    local base_port
    base_port="$(devbox_base_port 2>/dev/null || echo '')"
    if [[ "$base_port" =~ ^[0-9]+$ ]]; then
        printf '  port block  %s-%s\n' "$base_port" "$((base_port + DEVBOX_PORT_BLOCK - 1))"
    else
        printf '  port block  unavailable (no free block in %s-%s)\n' \
            "$DEVBOX_PORT_RANGE_START" "$DEVBOX_PORT_RANGE_END"
    fi

    if devbox_container_running; then
        printf '  devbox      running (%s)\n' "$(devbox_container_name)"
    elif [[ -n "$(devbox_container_id 2>/dev/null)" ]]; then
        printf '  devbox      stopped (%s)\n' "$(devbox_container_name)"
        pending=$((pending + 1))
    else
        printf '  devbox      not created\n'
        pending=$((pending + 1))
    fi

    echo ""
    if [[ "$pending" -eq 0 ]]; then
        log_info "Nothing to do; ./run.sh setup would be a no-op"
        devbox_status
        return 0
    fi
    log_warn "$pending item(s) would be acted on by ./run.sh setup"
    return 1
}

# =============================================================================
# CLEAN
# =============================================================================

clean() {
    log_step "Cleaning build artifacts"
    rm -rf dist/
    rm -rf node_modules/.vite
    rm -rf packages/*/dist/
    log_info "Build artifacts cleaned"
}

# =============================================================================
# HELP
# =============================================================================

show_help() {
    cat <<EOF
Usage: ./run.sh [COMMAND] [OPTIONS]

SERVICE COMMANDS:
  service start [port] [--no-build]  Build and run rediacc/web (default port: 8080)
  service stop                    Stop service containers
  service status                  Show service status
  service logs [container]        Show logs (web, rustfs, all)

ACCOUNT COMMANDS:
  account dev              Start account dev gateway (API + portal + www on one port)
  account db               Browse the dev database (Drizzle Studio on account.db)
  account test             Run account integration tests (vitest)
  account test e2e [opts]  Run account E2E tests (playwright, with Stripe wiring)
  account stop             Stop account Docker containers
  account reset            Reset .env + database and regenerate
  account totp [email]     Print the current 2FA code for a dev user (default dev-user@rediacc.io)

ROTATION COMMANDS (private/account/scripts/rotation/):
  rotation init            Bootstrap manifest from current platform state
  rotation list            Show every credential and its current state
  rotation check           Compare manifest to live state (exit 1 on drift)
  rotation rotate <slug>   Mint new credential; old transitions to grace
  rotation deactivate <s>  grace → inactive
  rotation delete <slug>   inactive → deleted (permanent)
  rotation sweep           Run deactivate + delete for everything eligible
  rotation history [<s>]   Show audit history

PROVISION COMMANDS:
  provision start            Provision KVM VMs (bridge + workers)
  provision stop             Destroy all VMs
  provision status           Show VM status

DEVELOPMENT COMMANDS:
  dev                 Start the www (marketing site) development server
  (rdc)               Use ./rdc.sh instead (standalone CLI runner)
  worktree <cmd>      Manage git worktrees (create, switch, prune, list)
  setup [--check]     Prepare this machine: INSTALL the toolchain (node, gcc, Go,
                      gh, jq), set the git identity and credentials, then docker,
                      the devcontainer image, and a browser VS Code for THIS
                      worktree. Idempotent -- a second run installs nothing.
  devbox <cmd>        up | status | stop | remove | shell | logs | proxy

WWW COMMANDS:
  www all [opts]                    Full pipeline for tutorials + team videos

  www tutorials record [name]       Record .cast files inside the bridge VM (auto-provision, change-detected; keeps local ~/.config/rediacc clean)
  www tutorials extract             Sync cast markers to transcripts (preserves text)
  www tutorials scaffold-locales    Sync locale transcripts with English
  www tutorials generate [opts]     Generate TTS audio + timelines (Python venv)
  www tutorials video [name] [--lang <code>] [--jobs N] [--captions-only]  Compile .mp4 from cast+storyboard+timeline+audio
                                     (--jobs N runs N compiles concurrently, default 1; ffmpeg-bound,
                                     safe to raise on a multi-core box -- e.g. --jobs 6 on 20 cores)
                                     (--captions-only recovers scene timing analytically and re-emits
                                     just the vtt/chapters/words.json sidecars, skipping the ffmpeg
                                     re-encode entirely -- use after a --subtitle realignment when the
                                     mp4 itself hasn't changed. Falls back to a full render per-tutorial
                                     if a browser scene's silent-segment cache is cold.)
  www tutorials media [name] [--langs a,b] [--jobs N] [--subtitle] [--force]
                                    Narrate on the GPU and render on the CPU CONCURRENTLY:
                                    each language's videos start rendering as soon as its
                                    narration passes validation, while the next language is
                                    still being narrated. Generates and renders only; never
                                    restores from or uploads to R2.
  www tutorials watch [--jobs N] [--langs a,b] [--poll N] [--once] [--dry-run]
                                    Render each (tutorial, LANGUAGE) PAIR the moment that
                                    pair's narration is final, for narration running in
                                    another shell. Exits once nothing new is ready and no
                                    tutorial_tts.cli is left running. Single instance
                                    (flock on artifacts/tutorial-render-watch/watch.lock);
                                    logs to that same directory. Renders only: never
                                    narrates, never restores from or uploads to R2.
  www tutorials validate            Validate transcripts + audio integrity
  www tutorials all [opts]          Full tutorial pipeline (record -> extract -> generate -> video)


TEST COMMANDS:
  test unit           Run unit tests
  test bridge [opts]  Run bridge tests (requires VMs)
  test all            Run all tests

DRILL COMMANDS (scripted walkthroughs; non-zero exit on any failed assertion):
  drill universe      Config isolation, source labels, per-config tokens (headless)
  drill transfer      Config-storage battery vs ./run.sh account dev (headless)
  drill license       Live licensing battery on the ops VMs (declares its VM cost)
  drill backup        Live chunk-store battery: session mint, seed and incremental
                      upload, byte-identical restore, quota refusal (no VMs needed)
  drill <name> --selftest
                      Plant one failing assertion; the run MUST exit non-zero

BUILD COMMANDS:
  build cli           Build CLI application
  build renet         Build renet binary (Go, with embedded assets)
  build packages      Build shared packages
  build all           Build everything

QUALITY COMMANDS:
  quality lint        Run linting (ESLint + Knip)
  quality format      Check code formatting (Biome)
  quality types       Check TypeScript types
  quality submodules  Check submodule branch alignment
  quality deps        Check for outdated dependencies
  quality audit       Run security audit (npm audit)
  quality shell       Run shellcheck on shell scripts
  quality all         Run all quality checks

FIX COMMANDS:
  fix format          Auto-fix code formatting
  fix lint            Auto-fix linting issues
  fix shell           Auto-fix shell script formatting (shfmt)
  fix all             Auto-fix all issues

PR COMMANDS:
  pr publish          Build and deploy to PR preview (pr-N.rediacc.workers.dev)
                      Auto-discovers PR number and Cloudflare account ID via gh CLI.
                      Sets worker secrets from private/account/.env if present.
                      Requires: CLOUDFLARE_API_TOKEN

CHECK COMMANDS (PRE-PUSH):
  check quick         Fast checks (lint, format, types)
  check full          Full validation (quality + audit + tests)

MAINTENANCE:
  clean               Clean build artifacts
  setup               Interactive setup: npm deps + native modules + git identity
  help                Show this help message

QUICK START:
  ./run.sh setup          # One-time setup
  ./run.sh dev            # Start www development
  ./rdc.sh subscription login # Run CLI command in dev mode

REQUIREMENTS:
  Node.js v${NODE_VERSION_REQUIRED}.x (https://nodejs.org/)
  Go (for CLI/renet development)
  Docker (for first-time renet asset extraction)

ENVIRONMENT:
  GITHUB_TOKEN        GitHub personal access token (for ghcr.io auth)
EOF
}

# =============================================================================
# MAIN DISPATCHER
# =============================================================================

main() {
    case "${1:-}" in
        # Service mode (rediacc/web + RustFS)
        service)
            shift
            case "${1:-}" in
                start)
                    shift
                    service_start "$@"
                    ;;
                stop) service_stop ;;
                status) service_status ;;
                logs)
                    shift
                    service_logs "$@"
                    ;;
                *)
                    log_error "Unknown service command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh service [start|stop|status|logs]"
                    exit 1
                    ;;
            esac
            ;;

        # VM Provisioning
        provision)
            shift
            case "${1:-}" in
                start)
                    shift
                    provision_start "$@"
                    ;;
                stop) provision_stop ;;
                status) provision_status ;;
                *)
                    log_error "Unknown provision command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh provision [start|stop|status]"
                    exit 1
                    ;;
            esac
            ;;

        # Account server
        account)
            shift
            source "$ROOT_DIR/.ci/lib/account.sh"
            case "${1:-}" in
                dev) account_dev ;;
                db) account_db ;;
                test)
                    shift
                    case "${1:-}" in
                        e2e)
                            shift
                            account_test_e2e "$@"
                            ;;
                        *)
                            account_test "$@"
                            ;;
                    esac
                    ;;
                stop) account_stop ;;
                reset) account_reset ;;
                seed-demo)
                    shift
                    account_seed_demo "$@"
                    ;;
                totp)
                    shift
                    account_totp "$@"
                    ;;
                *)
                    log_error "Unknown account command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh account [dev|test|stop|reset|seed-demo|totp]"
                    exit 1
                    ;;
            esac
            ;;

        # Secret rotation (delegates to private/account/scripts/rotation/)
        rotation)
            shift
            source "$ROOT_DIR/.ci/lib/account.sh"
            account_rotation "$@"
            ;;

        # Development
        dev) dev ;;
        worktree)
            shift
            "$ROOT_DIR/scripts/dev/worktree.sh" "$@"
            ;;
        setup)
            shift
            setup "$@"
            ;;
        devbox)
            shift
            # shellcheck source=/dev/null
            source "$ROOT_DIR/.ci/lib/devbox.sh"
            SCRIPT_ENTRYPOINT="$ROOT_DIR/run.sh" reexec_with_docker_group devbox "$@"
            case "${1:-status}" in
                # `up` forwards its remaining args so --no-rehost reaches devbox_up.
                # Without this the flag existed in the library and NOTHING could
                # pass it -- the drift banner advised DEVBOX_NO_REHOST=1 precisely
                # because the CLI form was unreachable.
                up)
                    shift
                    devbox_up false "${1:-}"
                    ;;
                status) devbox_status ;;
                # `url` prints the hostname URL and nothing else, so callers can
                # capture it. `worktree create` needs exactly this to show the URL
                # in its summary; parsing it back out of `status` would couple a
                # script to a human-facing layout.
                #
                # The optional suffix reaches the other routes -- `url term`,
                # `url account`, `url db` -- because a scriptable URL for one
                # service and a status-table scrape for the rest is the coupling
                # this subcommand exists to avoid.
                url)
                    shift
                    devbox_url "${1:-}"
                    ;;
                stop) devbox_stop ;;
                proxy)
                    shift
                    case "${1:-status}" in
                        up) devbox_proxy_ensure ;;
                        stop) devbox_proxy_stop ;;
                        status)
                            if devbox_proxy_running; then
                                log_info "Proxy running on :$DEVBOX_PROXY_PORT"
                            else
                                log_warn "Proxy is not running"
                                exit 1
                            fi
                            ;;
                        *)
                            log_error "Unknown devbox proxy command: $1"
                            exit 1
                            ;;
                    esac
                    ;;
                remove) devbox_remove ;;
                shell) devbox_shell ;;
                exec)
                    shift
                    [[ "${1:-}" == "--" ]] && shift
                    [[ $# -gt 0 ]] || {
                        log_error "devbox exec needs a command: ./run.sh devbox exec -- <cmd>"
                        exit 1
                    }
                    devbox_exec "$@"
                    ;;
                doctor) devbox_doctor ;;
                logs)
                    shift
                    devbox_logs "$@"
                    ;;
                *)
                    log_error "Unknown devbox command: $1"
                    log_info "Usage: ./run.sh devbox [up|status|url [term|account|db]|stop|remove|shell|logs]"
                    exit 1
                    ;;
            esac
            ;;
        www)
            shift
            case "${1:-}" in
                tutorials)
                    shift
                    case "${1:-}" in
                        record)
                            shift
                            www_tutorials_record "$@"
                            ;;
                        extract) www_tutorials_extract ;;
                        scaffold-locales) www_tutorials_scaffold_locales ;;
                        generate)
                            shift
                            www_tutorials_generate "$@"
                            ;;
                        video)
                            shift
                            www_tutorials_video "$@"
                            ;;
                        media)
                            shift
                            www_tutorials_media "$@"
                            ;;
                        watch)
                            shift
                            www_tutorials_watch "$@"
                            ;;
                        validate) www_tutorials_validate ;;
                        all)
                            shift
                            www_tutorials_all "$@"
                            ;;
                        *)
                            log_error "Unknown tutorials command: ${1:-}"
                            echo ""
                            echo "Usage: ./run.sh www tutorials [record|extract|scaffold-locales|generate|media|watch|video|validate|all]"
                            exit 1
                            ;;
                    esac
                    ;;
                all)
                    shift
                    www_all "$@"
                    ;;
                *)
                    log_error "Unknown www command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh www [all|tutorials] ..."
                    exit 1
                    ;;
            esac
            ;;

        # Tests
        test)
            shift
            case "${1:-}" in
                unit)
                    shift
                    test_unit "$@"
                    ;;
                bridge)
                    shift
                    test_bridge "$@"
                    ;;
                all) test_all ;;
                *)
                    log_error "Unknown test command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh test [unit|bridge|all]"
                    exit 1
                    ;;
            esac
            ;;

        # Drills: the campaign's manual walkthroughs, scripted. Each one owns
        # its setup, numbered assertions and teardown, and exits non-zero on any
        # failed assertion. Dispatched by literal path (not "$1.sh") so
        # check-dead-bash.ts can see each file is referenced.
        drill)
            shift
            case "${1:-}" in
                universe)
                    shift
                    "$ROOT_DIR/scripts/drills/universe.sh" "$@"
                    ;;
                transfer)
                    shift
                    "$ROOT_DIR/scripts/drills/transfer.sh" "$@"
                    ;;
                license)
                    shift
                    "$ROOT_DIR/scripts/drills/license.sh" "$@"
                    ;;
                backup)
                    shift
                    "$ROOT_DIR/scripts/drills/backup.sh" "$@"
                    ;;
                *)
                    log_error "Unknown drill: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh drill [universe|transfer|license|backup] [--selftest]"
                    exit 1
                    ;;
            esac
            ;;

        # Build
        build)
            shift
            case "${1:-}" in
                cli) build_cli ;;
                renet) build_renet ;;
                packages) build_packages ;;
                all | "") build_all ;;
                *)
                    log_error "Unknown build command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh build [cli|renet|packages|all]"
                    exit 1
                    ;;
            esac
            ;;

        # Quality
        quality)
            # ROUTED. The container's toolchain matches CI's and the host's
            # generally does not, so a quality run belongs in the lane that can
            # reach the same verdict CI will. Only GATE verbs route: setup,
            # devbox, provision, www and drill are host runtimes with host-
            # specific dependencies (KVM, GPU, ffmpeg, SSH keys that are
            # deliberately not bound into the container).
            # The lane probe talks to docker, so apply the group first -- without
            # it `devbox_container_running` reports "not running" for a container
            # that is running, and the routed lane silently degrades to the host.
            SCRIPT_ENTRYPOINT="$ROOT_DIR/run.sh" reexec_with_docker_group "$@"
            # Ask FIRST, then run. Collapsing these into one call is what let a
            # gate that failed in the devbox fall through and re-run on the
            # host, where a different toolchain could pass and hide it.
            # `|| _route=$?` is not style: run.sh runs under `set -euo pipefail`
            # (line 9), so a BARE call returning non-zero aborts the whole
            # script. The predicate returns 1 for the ordinary "stay on host"
            # case, so unguarded it killed every host-lane run silently -- the
            # trace ended at `return 1` with no output at all.
            _route=0
            gate_lane_should_route || _route=$?
            case "$_route" in
                0)
                    gate_lane_run "$@"
                    exit $?
                    ;;
                2) exit 2 ;; # unusable devbox: refuse, never degrade
            esac
            shift
            case "${1:-}" in
                lint) quality_lint ;;
                format) quality_format ;;
                types) quality_types ;;
                submodules) quality_submodules ;;
                deps) quality_deps ;;
                actions) quality_actions ;;
                suppressions) quality_suppressions ;;
                dead-bash) quality_dead_bash ;;
                audit) quality_audit ;;
                shell) quality_shell ;;
                all | "") quality_all ;;
                *)
                    log_error "Unknown quality command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh quality [lint|format|types|submodules|deps|actions|audit|shell|all]"
                    exit 1
                    ;;
            esac
            ;;

        # Fix
        fix)
            shift
            case "${1:-}" in
                format) fix_format ;;
                lint) fix_lint ;;
                shell) fix_shell ;;
                all | "") fix_all ;;
                *)
                    log_error "Unknown fix command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh fix [format|lint|shell|all]"
                    exit 1
                    ;;
            esac
            ;;

        # Check
        check)
            shift
            case "${1:-}" in
                quick) check_quick ;;
                full) check_full ;;
                *)
                    log_error "Unknown check command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh check [quick|full]"
                    exit 1
                    ;;
            esac
            ;;

        # PR commands
        pr)
            shift
            case "${1:-}" in
                publish) pr_publish ;;
                *)
                    log_error "Unknown pr command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh pr [publish]"
                    exit 1
                    ;;
            esac
            ;;

        # Maintenance
        clean) clean ;;
        help | --help | -h | "") show_help ;;

        *)
            log_error "Unknown command: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# Execute main if run directly.
#
# An `if` block, not `[[ … ]] && main "$@"`. With the `&&` form the whole file's exit status is
# the FAILED test when the file is SOURCED, so `source ./run.sh` returned 1 and killed any
# caller running under `set -e` — silently, with no output, because nothing had failed. The
# `if` form returns 0 when sourced while still propagating main's real exit code when run
# directly.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
