#!/bin/bash
# The one GPU-accelerator decision in the media pipeline.
#
# It is its own module rather than a paragraph inside venv.sh because it is the only
# code here that probes hardware, and it is the piece most likely to be edited by
# somebody who has a GPU in front of them. Keeping it separate means the venv module
# can be reasoned about (and tested) on a machine that has no CUDA at all -- which is
# every CI runner.
#
# Part of the media pipeline extraction (W10). Moved out of run.sh byte for byte in
# phase 1, comments included; phase 2 deleted run.sh's copy, so this is the only
# definition of the name anywhere. .ci/scripts/test/gates/test-media-cuda.sh asserts that
# ownership and drives all four of this function's exits with python, nvcc and pip faked,
# so nothing here needs a GPU to be covered.
#
# SOURCED, NEVER EXECUTED. Callers supply the log_* helpers.
# install_generative_python_deps in .ci/media/venv.sh is the sole caller.

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
