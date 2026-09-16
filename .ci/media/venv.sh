#!/bin/bash
# The generative Python environment: the private/generative checkout, the system
# audio toolchain it needs, and the venv that carries tutorial_tts.
#
# Part of the media pipeline extraction (W10). Every function below was MOVED here
# from run.sh byte for byte, comments included, because the comments are the
# archaeology: each one records an incident that the code's shape is the answer to.
# Phase 2 deleted run.sh's copies, so this file is now the only definition of each name;
# the gate test .ci/scripts/test/gates/test-media-venv.sh asserts exactly that, so a
# second copy reappearing anywhere is red rather than merely duplicated.
#
# SOURCED, NEVER EXECUTED. It defines functions and nothing else, so sourcing it
# with docker, node, npm, nvcc, aws, ssh and the network all absent is a no-op.
# It expects the caller to have provided ROOT_DIR and the log_* helpers from
# .ci/scripts/lib/common.sh; .ci/media/media-entry.sh is the caller that does.

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

ensure_generative_venv() {
    local clean_venv="$1"
    local gen_dir="$ROOT_DIR/private/generative"
    local venv_dir="$gen_dir/.venv"
    local stamp_file="$venv_dir/.deps-sha256"
    local content_hash

    content_hash="$(
        cd "$gen_dir" &&
            "${MEDIA_SHA256[@]}" pyproject.toml src/tutorial_tts/*.py src/tutorial_tts/*.json | "${MEDIA_SHA256[@]}" | awk '{print $1}'
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
