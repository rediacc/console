#!/bin/bash
# Console development script
# Aligned with CI workflow from .github/workflows/ci.yml
#
# ⚠️  IMPORTANT: When updating this file:
# ⚠️  1. Check if CI scripts need updates (.ci/config/constants.sh, .ci/lib/elite-backend.sh)
# ⚠️  2. Update documentation (docs/BACKEND.md)
# ⚠️  3. Test all affected commands

set -euo pipefail

# Root directory
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source configuration and utilities
source "$ROOT_DIR/.ci/config/constants.sh"
source "$ROOT_DIR/.ci/lib/local-common.sh"
source "$ROOT_DIR/.ci/lib/elite-backend.sh"
source "$ROOT_DIR/.ci/lib/service.sh"

# Backward compatibility: Load parent .env if exists
if [[ -f "$ROOT_DIR/../.env" ]]; then
    set +u # Disable unset variable errors temporarily
    source "$ROOT_DIR/../.env"
    set -u
fi

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

# Load environment file
load_env() {
    local env_file="$1"

    if [[ ! -f "$env_file" ]]; then
        log_warn "Environment file not found: $env_file"
        return 1
    fi

    # Export variables from .env file
    set -a
    source "$env_file"
    set +a

    log_debug "Loaded environment from: $env_file"
}

# Ensure private/generative submodule is initialized
ensure_generative_submodule() {
    if [[ ! -d "$ROOT_DIR/private/generative" ]]; then
        log_error "Missing private/generative directory"
        exit 1
    fi

    if [[ ! -f "$ROOT_DIR/private/generative/.git" ]] && [[ ! -d "$ROOT_DIR/private/generative/.git" ]]; then
        log_step "Initializing private/generative submodule..."
        git submodule sync -- private/generative >/dev/null 2>&1 || true
        git submodule update --init --recursive private/generative
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
        sudo apt-get install -y ffmpeg sox python3-venv python3-dev build-essential
    else
        apt-get update
        apt-get install -y ffmpeg sox python3-venv python3-dev build-essential
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
# reruns skip the rebuild when packages/cli, packages/shared(-desktop), or renet
# are unchanged. Output: dist/cli/rdc-linux-x64. Mirrors `rdc.sh --override-local`
# but installs nothing on the host.
_build_cli_sea_cached() {
    local out="$ROOT_DIR/dist/cli/rdc-linux-x64"
    local hash_file="$ROOT_DIR/dist/cli/.sea-source-hash"
    local cur
    cur="$(
        {
            find "$ROOT_DIR/packages/cli/src" "$ROOT_DIR/packages/shared/src" \
                "$ROOT_DIR/packages/shared-desktop/src" -type f \
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
    (cd "$ROOT_DIR/private/renet" &&
        CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build \
            -tags nolicense -ldflags="-s -w -X main.Version=0.0.0-dev" \
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

www_tutorials_record() {
    local force=false
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
        # All tutorial scripts share the tutorial-<slug>.sh prefix; record alphabetically.
        for script in "$tutorials_dir"/tutorial-*.sh; do
            [[ -f "$script" ]] || continue
            candidates+=("$script")
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
    provision_post_setup

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
                /tmp/rec/out/${base}.cast 100 30"
        _bridge_rsync "${bridge}:/tmp/rec/out/${base}.cast" "$output_dir/${base}.cast"
        log_info "Pulled cast → $output_dir/${base}.cast"

        # Update stored hash
        stored_hashes["$base"]="$(_tutorial_script_hash "$script")"
    done

    # Teardown VMs
    log_step "Tearing down VMs..."
    provision_stop

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

www_tutorials_generate() {
    check_node_version
    ensure_generative_submodule
    ensure_python_installed
    ensure_audio_system_deps

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

    if [[ "$destroy_venv" == "true" ]]; then
        log_step "Destroying generative Python environment..."
        rm -rf "$ROOT_DIR/private/generative/.venv"
    fi
}

www_tutorials_video() {
    check_node_version
    ensure_deps
    ensure_audio_system_deps

    local name=""
    local lang=""
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
            --keep-temp)
                passthrough+=("$1")
                shift
                ;;
            *)
                name="$1"
                shift
                ;;
        esac
    done

    local tutorials_root="$ROOT_DIR/packages/www/public/assets/tutorials"
    local timeline_root="$ROOT_DIR/packages/www/src/data/tutorial-timeline"

    local tutorials=()
    if [[ -n "$name" ]]; then
        local base="$name"
        [[ "$base" != tutorial-* ]] && base="tutorial-$base"
        [[ -f "$tutorials_root/${base}.cast" ]] || {
            log_error "Cast not found: $tutorials_root/${base}.cast"
            exit 1
        }
        tutorials+=("$base")
    else
        for cast in "$tutorials_root"/*.cast; do
            [[ -f "$cast" ]] || continue
            tutorials+=("$(basename "$cast" .cast)")
        done
    fi

    local langs=()
    if [[ -n "$lang" ]]; then
        langs+=("$lang")
    else
        for d in "$timeline_root"/*/; do
            [[ -d "$d" ]] || continue
            langs+=("$(basename "$d")")
        done
    fi

    log_step "Compiling tutorial videos (${#tutorials[@]} tutorial(s) × ${#langs[@]} lang(s))..."
    local failures=()
    (
        cd "$ROOT_DIR/packages/www"
        for t in "${tutorials[@]}"; do
            for l in "${langs[@]}"; do
                if [[ ! -f "$timeline_root/$l/${t}.json" ]]; then
                    log_debug "skip $t × $l (no timeline)"
                    continue
                fi
                if [[ ! -d "$tutorials_root/audio/$l/$t" ]]; then
                    log_debug "skip $t × $l (no audio)"
                    continue
                fi
                log_step "  → $t × $l"
                if ! npx tsx scripts/generate-tutorial-video.ts \
                    --cast "$t" --lang "$l" "${passthrough[@]}"; then
                    log_error "  ✗ failed: $t × $l"
                    echo "$t × $l" >>/tmp/_tut_video_failures.$$
                fi
            done
        done
    )
    if [[ -f "/tmp/_tut_video_failures.$$" ]]; then
        log_error "Failed tutorials:"
        cat "/tmp/_tut_video_failures.$$" >&2
        rm -f "/tmp/_tut_video_failures.$$"
        return 1
    fi
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

www_team_video_extract() {
    check_node_version
    ensure_generative_submodule
    ensure_python_installed
    ensure_audio_system_deps

    local passthrough=()
    local clean_venv=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --clean-venv)
                clean_venv=true
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

    log_step "Extracting team video transcripts via ASR..."
    npm run team-video:extract -w @rediacc/www -- "${passthrough[@]}"
}

www_team_video_scaffold_locales() {
    check_node_version
    ensure_deps
    log_step "Scaffolding team video locale transcript files..."
    npm run team-video:scaffold-locales -w @rediacc/www
}

www_team_video_generate() {
    check_node_version
    ensure_generative_submodule
    ensure_python_installed
    ensure_audio_system_deps

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

    log_step "Generating team video audio assets..."
    npm run team-video:tts:generate -w @rediacc/www -- "${passthrough[@]}"

    if [[ "$destroy_venv" == "true" ]]; then
        log_step "Destroying generative Python environment..."
        rm -rf "$ROOT_DIR/private/generative/.venv"
    fi
}

www_team_video_validate() {
    check_node_version
    ensure_deps
    log_step "Validating team video transcripts..."
    npm run validate:team-video-transcripts -w @rediacc/www
}

www_team_video_all() {
    log_step "Running full team video pipeline..."
    www_team_video_extract "$@"
    www_team_video_scaffold_locales
    www_team_video_generate "$@"
    www_team_video_validate
    log_info "Team video pipeline complete!"
}

# =============================================================================
# WWW ALL
# =============================================================================

www_all() {
    log_step "Running full www asset pipeline..."
    www_tutorials_all "$@"
    www_team_video_all "$@"
    log_info "All www assets generated!"
}

# =============================================================================
# DEVELOPMENT COMMANDS
# =============================================================================

dev() {
    check_node_version

    # Check if backend is running
    if ! backend_health &>/dev/null; then
        log_warn "Backend is not running"
        log_info ""
        log_info "Start backend with: ./run.sh backend start"
        log_info ""

        if prompt_continue "Start backend now"; then
            backend_start
        else
            exit 1
        fi
    fi

    log_step "Starting console development server"

    # Install dependencies if needed
    if [[ ! -d "$ROOT_DIR/node_modules" ]] || [[ "$ROOT_DIR/package-lock.json" -nt "$ROOT_DIR/node_modules" ]]; then
        log_info "Installing dependencies"
        npm install
    fi

    # Set environment for Vite
    export VITE_API_URL="$API_URL_LOCAL"
    export REDIACC_BUILD_TYPE="$BUILD_TYPE_DEBUG"

    # Start dev server
    PORT="$PORT_CONSOLE_DEV" npm run dev
}

# Sandbox mode (no backend required) - preserved from original
sandbox() {
    check_node_version

    local USE_DOCKER=false
    local DOCKER_PORT=8080
    local OPEN_BROWSER=true

    # Parse arguments
    for arg in "$@"; do
        case $arg in
            --docker)
                USE_DOCKER=true
                ;;
            --port=*)
                DOCKER_PORT="${arg#*=}"
                ;;
            --no-browser)
                OPEN_BROWSER=false
                ;;
            --help)
                echo "Usage: ./run.sh sandbox [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --docker        Run in Docker container (recommended for quick start)"
                echo "  --port=PORT     Docker port (default: 8080)"
                echo "  --no-browser    Don't open browser automatically"
                echo ""
                echo "Examples:"
                echo "  ./run.sh sandbox              # Run locally with npm"
                echo "  ./run.sh sandbox --docker     # Run in Docker (recommended)"
                echo ""
                return 0
                ;;
        esac
    done

    if [[ "$USE_DOCKER" == "true" ]]; then
        # Docker mode
        check_docker

        log_step "Building and running containerized console"

        # Build the Docker image
        log_info "Building Docker image"
        docker build -t rediacc-console:sandbox \
            --build-arg REDIACC_BUILD_TYPE=DEBUG . || {
            log_error "Docker build failed"
            return 1
        }

        # Stop any existing container
        docker stop rediacc-console-sandbox 2>/dev/null || true
        docker rm rediacc-console-sandbox 2>/dev/null || true

        # Run the container
        log_info "Starting container on port ${DOCKER_PORT}"
        docker run -d \
            --name rediacc-console-sandbox \
            -p ${DOCKER_PORT}:80 \
            -e INSTANCE_NAME=sandbox \
            -e BUILD_TYPE=DEBUG \
            -e ENABLE_DEBUG=true \
            rediacc-console:sandbox

        # Wait for container to be ready
        local ready=false
        for i in {1..30}; do
            if curl -s http://localhost:${DOCKER_PORT}/health &>/dev/null; then
                ready=true
                break
            fi
            sleep 1
        done

        if [[ "$ready" == "true" ]]; then
            log_info "Console is running at: http://localhost:${DOCKER_PORT}"
        else
            log_warn "Console may not be fully ready yet"
        fi

        # Show logs
        docker logs -f rediacc-console-sandbox
    else
        # Local development mode
        log_step "Starting console in sandbox mode"
        log_info "API URL: $API_URL_SANDBOX"

        # Install dependencies if needed
        if [[ ! -d "$ROOT_DIR/node_modules" ]] || [[ "$ROOT_DIR/package-lock.json" -nt "$ROOT_DIR/node_modules" ]]; then
            log_info "Installing dependencies"
            npm install
        fi

        # Set environment for Vite
        export VITE_API_URL="$API_URL_SANDBOX"
        export REDIACC_BUILD_TYPE="$BUILD_TYPE_DEBUG"
        export SANDBOX_MODE=true

        # Start dev server
        PORT="${PORT_CONSOLE_DEV}" npm run dev
    fi
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

test_cli() {
    check_node_version
    ensure_packages_built
    log_step "Running CLI tests"
    "$ROOT_DIR/.ci/scripts/test/run-cli.sh" "$@"
}

test_e2e() {
    check_node_version

    # Check if --backend is specified
    local has_backend=false
    for arg in "$@"; do
        [[ "$arg" == "--backend" || "$arg" == --backend=* ]] && has_backend=true
    done

    # Only require local backend if --backend not specified
    if [[ "$has_backend" == "false" ]]; then
        if ! backend_health &>/dev/null; then
            log_error "Backend is not running or unhealthy"
            log_info "E2E tests require a running backend"
            log_info "Start backend with: ./run.sh backend start"
            log_info "Or use external backend: ./run.sh test e2e --backend <url>"
            exit 1
        fi
        # Docker backend healthy on port 80 — inject --backend so Vite
        # proxies /api to http://localhost instead of default :7322
        log_info "Docker backend detected, using http://localhost"
        set -- "--backend" "http://localhost" "$@"
    fi

    log_step "Running E2E tests"
    "$ROOT_DIR/.ci/scripts/build/build-web.sh"
    "$ROOT_DIR/.ci/scripts/test/run-e2e.sh" "$@"
}

test_bridge() {
    check_node_version
    ensure_packages_built

    log_step "Running bridge tests"
    "$ROOT_DIR/.ci/scripts/test/run-bridge.sh" "$@"
}

test_all() {
    test_unit
    test_cli
    test_e2e --projects chromium
}

# =============================================================================
# BUILD COMMANDS
# =============================================================================

build_web() {
    check_node_version
    log_step "Building web application"
    "$ROOT_DIR/.ci/scripts/build/build-web.sh"
}

build_cli() {
    check_node_version
    log_step "Building CLI application"
    "$ROOT_DIR/.ci/scripts/build/build-cli.sh"
}

build_desktop() {
    check_node_version
    log_step "Building desktop application"
    "$ROOT_DIR/.ci/scripts/build/build-desktop.sh"
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
    build_web
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

    log_step "Building web (console)..."
    VITE_BASE_PATH=/console/ npm run build:web

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

    # Shell formatting/linting (requires shfmt + shellcheck)
    if command -v shfmt &>/dev/null; then
        quality_shell
    else
        log_warn "shfmt not found — skipping shell checks (install: go install mvdan.cc/sh/v3/cmd/shfmt@latest)"
    fi
}

quality_deps() {
    check_node_version
    "$ROOT_DIR/.ci/scripts/quality/check-deps.sh"
}

quality_actions() {
    check_node_version
    log_step "Checking GitHub Actions versions..."
    node "$ROOT_DIR/scripts/check-actions.js"
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
    if ! command -v shfmt &>/dev/null; then
        log_error "shfmt is not installed"
        log_info "Install with: go install mvdan.cc/sh/v3/cmd/shfmt@latest"
        exit 1
    fi
    find .ci -name "*.sh" -type f -exec shfmt -i 4 -ci -w {} +
    shfmt -i 4 -ci -w ./run.sh
    if [[ -d "scripts/dev" ]]; then
        find scripts/dev -name "*.sh" -type f -exec shfmt -i 4 -ci -w {} +
    fi
    log_success "Shell scripts formatted"
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

setup() {
    check_node_version

    log_step "Console development setup"
    echo ""

    # Install dependencies
    log_info "Installing npm dependencies"
    npm install

    # Start backend
    backend_start

    log_info ""
    log_info "Setup complete!"
    log_info ""
    log_info "Start development with: ./run.sh dev"
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

BACKEND COMMANDS:
  backend start              Start backend services
  backend stop               Stop backend services
  backend status             Show backend status
  backend logs [service]     Show service logs (api, sql, web, all)
  backend health             Check backend health
  backend pull               Pull latest ghcr images
  backend reset              Reset backend (deletes data)
  backend auto               Auto-start backend (idempotent, for devcontainer)

SERVICE COMMANDS:
  service start [port] [--no-build]  Build and run rediacc/web (default port: 8080)
  service stop                    Stop service containers
  service status                  Show service status
  service logs [container]        Show logs (web, rustfs, all)

ACCOUNT COMMANDS:
  account dev              Start account dev gateway (API + portal + www on one port)
  account test             Run account integration tests (vitest)
  account test e2e [opts]  Run account E2E tests (playwright, with Stripe wiring)
  account stop             Stop account Docker containers
  account reset            Reset .env + database and regenerate

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
  dev                 Start development server (auto-starts backend if needed)
  (rdc)               Use ./rdc.sh instead (standalone CLI runner)
  sandbox             Start in sandbox mode (no backend required)
  worktree <cmd>      Manage git worktrees (create, switch, prune, list)
  setup               Interactive setup wizard

WWW COMMANDS:
  www all [opts]                    Full pipeline for tutorials + team videos

  www tutorials record [name]       Record .cast files inside the bridge VM (auto-provision, change-detected; keeps local ~/.config/rediacc clean)
  www tutorials extract             Sync cast markers to transcripts (preserves text)
  www tutorials scaffold-locales    Sync locale transcripts with English
  www tutorials generate [opts]     Generate TTS audio + timelines (Python venv)
  www tutorials video [name] [--lang <code>]  Compile .mp4 from cast+storyboard+timeline+audio
  www tutorials validate            Validate transcripts + audio integrity
  www tutorials all [opts]          Full tutorial pipeline (record -> extract -> generate -> video)

  www team-video extract [opts]     ASR: extract English transcripts from video audio
  www team-video scaffold-locales   Sync locale transcripts with English
  www team-video generate [opts]    Generate dubbed audio + captions
  www team-video validate           Validate transcripts + audio integrity
  www team-video all [opts]         Full team video pipeline

TEST COMMANDS:
  test unit           Run unit tests
  test cli [opts]     Run CLI tests
  test e2e [opts]     Run E2E tests (requires backend)
  test bridge [opts]  Run bridge tests (requires VMs)
  test all            Run all tests

  Test Options (for e2e and cli):
    --backend <url|preset>  Use external backend instead of local
                            Presets: local, sandbox
                            Example: --backend https://xxx.trycloudflare.com
    --skip-health-check     Skip backend health validation

BUILD COMMANDS:
  build web           Build web application
  build cli           Build CLI application
  build renet         Build renet binary (Go, with embedded assets)
  build desktop       Build desktop application
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
  setup               Interactive setup wizard
  help                Show this help message

QUICK START:
  ./run.sh setup          # One-time setup
  ./run.sh dev            # Start web development
  ./rdc.sh auth login     # Run CLI command in dev mode

REQUIREMENTS:
  Node.js v${NODE_VERSION_REQUIRED}.x (https://nodejs.org/)
  Go (for CLI/renet development)
  Docker (for backend, and first-time renet asset extraction)

ENVIRONMENT:
  GITHUB_TOKEN        GitHub personal access token (for ghcr.io auth)
EOF
}

# =============================================================================
# MAIN DISPATCHER
# =============================================================================

main() {
    case "${1:-}" in
        # Backend commands
        backend)
            shift
            case "${1:-}" in
                start)
                    shift
                    backend_start "$@"
                    ;;
                stop) backend_stop ;;
                status) backend_status ;;
                logs)
                    shift
                    backend_logs "$@"
                    ;;
                health) backend_health ;;
                pull) backend_pull_images ;;
                reset) backend_reset ;;
                auto) backend_auto ;;
                *)
                    log_error "Unknown backend command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh backend [start|stop|status|logs|health|pull|reset|auto]"
                    exit 1
                    ;;
            esac
            ;;

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
                auto) provision_auto ;;
                *)
                    log_error "Unknown provision command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh provision [start|stop|status|auto]"
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
                *)
                    log_error "Unknown account command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh account [dev|test|stop|reset]"
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
        sandbox)
            shift
            sandbox "$@"
            ;;
        worktree)
            shift
            "$ROOT_DIR/scripts/dev/worktree.sh" "$@"
            ;;
        setup) setup ;;
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
                        validate) www_tutorials_validate ;;
                        all)
                            shift
                            www_tutorials_all "$@"
                            ;;
                        *)
                            log_error "Unknown tutorials command: ${1:-}"
                            echo ""
                            echo "Usage: ./run.sh www tutorials [record|extract|scaffold-locales|generate|video|validate|all]"
                            exit 1
                            ;;
                    esac
                    ;;
                team-video)
                    shift
                    case "${1:-}" in
                        extract)
                            shift
                            www_team_video_extract "$@"
                            ;;
                        scaffold-locales) www_team_video_scaffold_locales ;;
                        generate)
                            shift
                            www_team_video_generate "$@"
                            ;;
                        validate) www_team_video_validate ;;
                        all)
                            shift
                            www_team_video_all "$@"
                            ;;
                        *)
                            log_error "Unknown team-video command: ${1:-}"
                            echo ""
                            echo "Usage: ./run.sh www team-video [extract|scaffold-locales|generate|validate|all]"
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
                    echo "Usage: ./run.sh www [all|tutorials|team-video] ..."
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
                cli)
                    shift
                    test_cli "$@"
                    ;;
                e2e)
                    shift
                    test_e2e "$@"
                    ;;
                bridge)
                    shift
                    test_bridge "$@"
                    ;;
                all) test_all ;;
                *)
                    log_error "Unknown test command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh test [unit|cli|e2e|bridge|all]"
                    exit 1
                    ;;
            esac
            ;;

        # Build
        build)
            shift
            case "${1:-}" in
                web) build_web ;;
                cli) build_cli ;;
                renet) build_renet ;;
                desktop) build_desktop ;;
                packages) build_packages ;;
                all | "") build_all ;;
                *)
                    log_error "Unknown build command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh build [web|cli|renet|desktop|packages|all]"
                    exit 1
                    ;;
            esac
            ;;

        # Quality
        quality)
            shift
            case "${1:-}" in
                lint) quality_lint ;;
                format) quality_format ;;
                types) quality_types ;;
                submodules) quality_submodules ;;
                deps) quality_deps ;;
                actions) quality_actions ;;
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

# Execute main if run directly
[[ "${BASH_SOURCE[0]}" == "${0}" ]] && main "$@"
