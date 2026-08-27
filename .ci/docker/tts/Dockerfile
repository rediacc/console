# The narration image: VoxCPM2 + Qwen3-ASR on the GPU.
#
# THE ONLY IMAGE THAT GETS --gpus all. Splitting the three images is not tidiness: the
# render and web images carry no CUDA and no model weights, so they stay small and rebuild
# fast, and exactly one image needs the card.
#
# WHY nvidia/cuda AND NOT python:slim. Measured 2026-08-27: in python:3.14-slim,
# /usr/lib64/libcuda.so.1 would not load and the probe had to fall through to
# /usr/lib/wsl/drivers/.../libcuda.so.1.1, because Debian's linker path is
# /usr/lib/x86_64-linux-gnu and nothing puts /usr/lib64 on it. The CUDA base sets
# LD_LIBRARY_PATH correctly and removes a class of "works on the host, not in the box".
#
# GPU ACCESS IS ALREADY PROVEN ON THIS HOST WITH ZERO CONFIGURATION. Docker Desktop's WSL
# integration injects /dev/dxg, libcuda, libnvidia-ml and nvidia-smi as read-only mounts;
# nvidia-container-toolkit is NOT installed and NOT needed. Free VRAM inside a container
# measured identical to the host at 11243 of 12287 MiB.
#
# THE GPU LEASE DOES NOT CROSS THIS BOUNDARY BY DEFAULT, AND THAT IS A CORRECTNESS TRAP.
# tutorial_tts/gpu_lock.py:33 defaults to /tmp/rediacc-gpu.lock and /tmp is per-container,
# so a container and the host, or two containers, each take their OWN lease and both load
# VoxCPM. Two VoxCPM jobs do not degrade, they OOM. The runner MUST bind-mount a shared
# lock path and set RDC_GPU_LOCK_FILE to it. See .ci/docker/run-in-tts.sh.
ARG CUDA_TAG=13.0.1-runtime-ubuntu24.04
FROM nvidia/cuda:${CUDA_TAG}

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-venv python3-dev build-essential \
      ffmpeg sox libsndfile1 ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

# The venv package name must MATCH the interpreter version. The generic python3-venv
# metapackage pulls the distro default, which is the wrong one whenever python3 is newer,
# and the symptom is "ensurepip is not available" much later, inside python3 -m venv.
RUN set -eu; \
    v="$(python3 -c 'import sys;print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"; \
    apt-get update && apt-get install -y --no-install-recommends "python${v}-venv" || true; \
    rm -rf /var/lib/apt/lists/*; \
    python3 -c 'import ensurepip' || { echo "FATAL: ensurepip unavailable, venv creation would fail"; exit 1; }

# THE PYTHON DEPS ARE BAKED, AND THAT IS THE POINT.
#
# The first cut of this image installed no Python packages, on the theory that the repo's
# own venv at private/generative/.venv would be bind-mounted in with the workspace. That
# does not work and the reason is worth stating: a venv is not portable. Its shebangs are
# ABSOLUTE (`#!/home/developer/console/private/generative/.venv/bin/python3`), it is built
# against the HOST's glibc and Python minor version, and this base ships neither. Proven
# 2026-08-27: `python3 -c "import torch"` inside the container raised ModuleNotFoundError
# while the same venv worked on the host.
#
# So the image owns its interpreter and its dependencies, and the bind-mounted workspace
# supplies only SOURCE. That is what makes the container the unit of portability rather
# than a GPU-capable shell that still needs the host to be correct.
ENV VIRTUAL_ENV=/opt/venv PATH=/opt/venv/bin:$PATH
RUN python3 -m venv "$VIRTUAL_ENV" && pip install --no-cache-dir --upgrade pip

COPY generative-pyproject.toml /tmp/gen/pyproject.toml
# SEQUENTIALLY, not in one pip invocation. Installing the package and qwen-tts together
# makes pip resolve them JOINTLY and it fails: "Cannot install None, qwen-tts==0.0.2,
# rediacc-generative and rediacc-generative[tts]==0.2.0 because these package versions
# have conflicting dependencies". Measured 2026-08-27. The host run.sh has always done
# these as separate commands and lands qwen-tts 0.1.1; this mirrors that order.
RUN mkdir -p /tmp/gen/src/tutorial_tts && touch /tmp/gen/src/tutorial_tts/__init__.py \
    && pip install --no-cache-dir "/tmp/gen[tts]" \
    && pip install --no-cache-dir qwen-tts \
    && rm -rf /tmp/gen

# Fail the BUILD if the stack cannot import, rather than discovering it mid-narration.
# The full set the bridge needs, not just torch: qwen_asr backs caption alignment,
# qwen_tts backs the legacy engine, soundfile backs every wav write. Each was verified
# importable in the working host venv on 2026-08-27, so a failure here is an image
# defect, not a moving target. torch.cuda is NOT probed here: a build has no GPU. That
# check belongs at run time.
RUN python3 -c "import torch, voxcpm, qwen_asr, qwen_tts, soundfile; print('torch', torch.__version__, 'tts stack ok')" \
    && command -v ffmpeg && command -v ffprobe && command -v sox

# Model weights are NOT baked. openbmb/VoxCPM2 plus Qwen/Qwen3-ASR-1.7B are several GB and
# belong in a named volume (or the bind-mounted host cache) at HF_HOME, so the image stays
# rebuildable and the weights survive an image bump.
#
# Mode 1777 is load-bearing: the runner starts the container as the CALLING uid so
# artifacts are not root-owned, but a fresh named volume is root-owned, and HF would die
# on the first download with EACCES. Docker's copy-up applies this directory's mode to an
# empty volume on first mount, which is what makes the named-volume path writable.
RUN install -d -m 1777 /models
ENV HF_HOME=/models
WORKDIR /work
