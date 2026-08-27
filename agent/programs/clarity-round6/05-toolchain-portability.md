# 05. Toolchain portability

Status: **planning**, verified 2026-08-27 on the rebuilt host.

## Why this wave exists

The host was rebuilt shortly before this session, and the rebuild exposed what the
toolchain silently depends on. Both python venvs are EMPTY. Four of the five font families
the renderers NAME are absent. `agent-browser` was missing, and installing it needed three
non-obvious steps. `voxcpm`, which backs the DEFAULT TTS engine, is declared in no
dependency file at all.

None of that failed loudly. The dangerous one is D3 plus D4 together: a solution-video
render on this host today would ship all 12 non-Arabic locales in a substituted typeface,
silently, exit 0, because `remotion/src/fonts.ts` guards Arabic and nothing else.

## GPU in Docker: verified working, zero configuration

    docker run --rm --gpus all python:3.14-slim python /probe.py
      cuInit(0) rc = 0 OK
      driver API 13.4
      device: NVIDIA GeForce RTX 3060
      cuCtxCreate rc = 0
      VRAM free/total 11243/12287 MiB
      cuMemAlloc 512MiB rc = 0

Docker Desktop's WSL integration injects `/dev/dxg`, `libcuda.so.1`, `libnvidia-ml.so.1`,
the PTX JIT compiler and `nvidia-smi` as read-only mounts. `nvidia-container-toolkit` is
NOT installed and is NOT needed. VRAM inside a container is identical to the host, so
containerisation costs nothing there.

## The pattern already exists in this repo

`.ci/scripts/quality/browser-smoke.sh` is this idea, shipped. Copy its shape rather than
inventing one. It encodes, with reasons in its own header:

- container by default, `REDIACC_SMOKE_NO_DOCKER=1` escape hatch, and a graceful fallback
  when docker is absent
- `-u "$(id -u):$(id -g)"` so artifacts are not root-owned
- `-e HOME=/tmp -e npm_config_cache=/tmp/.npm`
- workspace BIND-MOUNTED at `/work`, never copied, so the gate sees the dist just built
- `--ipc=host`, because Chromium crashes on the default 64 MB `/dev/shm`
- the image tag DERIVED from the installed package at run time, never hand-pinned

The existing root `Dockerfile` (the self-hosted server image) and `docker-compose.yml`
(the observability stack) are unrelated to dev tooling. No collision, and no existing
pattern to extend for this beyond `browser-smoke.sh`.

## Proposed shape: three images, not one

| image | contents | rough size | GPU |
|---|---|---|---|
| `rediacc/tts` | CUDA base, python 3.14, torch, transformers, voxcpm, qwen-asr, ffmpeg, sox, libsndfile | about 8 GB | yes |
| `rediacc/render` | node 22, Remotion plus chrome-headless-shell, ffmpeg, ALL FIVE FONTS, resvg deps | about 3 GB | no |
| `rediacc/web` | node 22, Astro, agent-browser plus Chrome and its libs | about 2 GB | no |

Splitting matters: render and web carry no CUDA and no model weights, so they stay small
and rebuild fast, and only one image needs `--gpus all`. Model weights live in a NAMED
VOLUME shared by `tts`, because there is no `~/.cache/huggingface` on a fresh host and
`openbmb/VoxCPM2` plus `Qwen/Qwen3-ASR-1.7B` are several GB.

## What must NOT be containerised

The `claude-agent-sdk` orchestration steps. They need operator credentials, they are pure
API calls with no native dependencies beyond python, and containerising them means
threading auth through for zero portability gain. Each pipeline's `main.py` stays on the
host and shells into containers for the three things with heavy native deps: TTS, render,
browser. That also keeps `--localize`'s GPU/CPU overlap scheduling on the host, where it
can see both devices.

## Traps a naive containerisation hits, each verified

**T1. The GPU lease stops working.** `gpu_lock.py:33` defaults to `/tmp/rediacc-gpu.lock`
and `/tmp` is per-container, so a container and the host, or two containers, each hold
their own lease and both load VoxCPM. Two VoxCPM jobs do not degrade, they OOM. Fixable
with a bind-mounted lock path, but note `:20` says `RDC_GPU_LOCK_FILE` "is the only knob,
and it exists for tests", so production use widens that contract deliberately.

**T2. `/usr/lib64` is not on the Debian linker path.** The probe fell through to
`/usr/lib/wsl/drivers/.../libcuda.so.1.1` because `/usr/lib64/libcuda.so.1` would not load
in `python:3.14-slim`. An `nvidia/cuda` base sets `LD_LIBRARY_PATH` correctly; a slim base
needs it done by hand.

**T3. `--ipc=host` on every Chrome-running container**, render and agent-browser both.

**T4. Renders are `nice -n 10` and narration is deliberately never niced.** That relative
priority must survive whatever CPU limits the containers get, or renders starve the GPU
job's own CPU work.

**T5. `node_modules` must not be shadowed** by a bind mount over an image that has its own
install. `install:natives` and Remotion's compositor binaries are the ones that break.

**T6. `.npmrc` sets `ignore-scripts=true`**, so any global npm install inside an image
needs `--allow-scripts=<pkg>` or the binary is never linked. This is exactly how the
`agent-browser` install failed silently this session.

## Fonts: vendor them, do not only bake them

Fonts split three ways today: vendored (DejaVu for the cards, Noto Sans Arabic for
Remotion), system-named (`Inter`, `JetBrains Mono` for every Latin and Cyrillic locale,
`WenQuanYi Zen Hei` for zh/ja/ko), and Chrome's own fallbacks.

Baking the missing three into the image fixes the container path and leaves a bare-metal
run broken. **Vendoring all five fixes both, makes the image thinner, and is the only
option that closes D3 for a developer who runs the render outside Docker.**

**A4 note:** the agent-browser guard decided in A3/A4 is a BLOCKING `block-*.sh`, so the
`./run.sh setup` work in this wave must install agent-browser in a way the guard accepts,
i.e. it must not itself write screenshots into the repo during any smoke check.

Independently of Docker, `remotion/src/fonts.ts` should get a Latin assertion mirroring
what `assertCardFontsUsable` already does for cards. It is small, and right now it is the
only thing between this repo and twelve locales of quietly wrong typography.

## `./run.sh setup` gaps this wave closes

Operator-requested this session: make the helpers portable, and install `agent-browser`
from `setup`. The three gotchas, all hit live:

1. `.npmrc`'s `ignore-scripts=true` means `npm i -g agent-browser` installs the package
   and never links the binary. Needs `--allow-scripts=agent-browser`.
2. Its `engines` field wants node >= 24 against our 22.23.2. Cosmetic: the symlink points
   straight at the prebuilt native binary and the JS shim never runs. npm still warns
   EBADENGINE.
3. Chrome needs system libs. `sudo agent-browser install --with-deps` for the libs, then a
   PLAIN USER-LEVEL `agent-browser install` for the browser. Running the second under sudo
   re-downloads Chrome into `/root` where the user cannot reach it.

Also worth folding in: the five fonts, `voxcpm` (D5), and a torch pin (D6).

## Console CI stays out of it

`private/growth` is deliberately outside console CI (I15). Do not wire these images, the
Remotion bump or the GPU containers into console CI on this program's authority. Ask.
