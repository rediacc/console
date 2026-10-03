# w9: the Docker switch, finished on artifacts

Session e580532b, 2026-08-27. Finish line as ordered: real narrations produced INSIDE the
container, read back from disk. No render, no publish, no R2.

## 1. Image state

`rediacc/tts:local` sha256:4575e2c9e2db, 15.4 GB on disk (5.29 GB content). Built from
`/home/developer/console/.ci/docker/tts/Dockerfile` in two passes: the in-flight build I
inherited (log `scratchpad/tts-image4.log`, 410 s) plus a cached rebuild
(`tts-image5.log`) that added two layers I wrote:

- The build assertion now covers the FULL bridge stack, not just torch:
  `import torch, voxcpm, qwen_asr, qwen_tts, soundfile` plus `command -v ffmpeg`,
  `ffprobe`, `sox`. Build output: `torch 2.13.0+cu130 tts stack ok`, `/usr/bin/ffmpeg`,
  `/usr/bin/ffprobe`, `/usr/bin/sox`. Module names were verified importable in the
  working host venv first, so a failure here is an image defect, not a moving target.
- `RUN install -d -m 1777 /models`. Load-bearing: the runner starts the container as the
  calling uid, and a fresh named volume is root-owned without this, so HF's first
  download dies EACCES. Proven by control after deleting the stale volume:
  `docker run -u 1000 ... touch /models/write-probe` succeeded on a fresh volume
  (`drwxrwxrwt`, copy-up from the image).

The sequential `rediacc-generative[tts]` then `qwen-tts` install order was already in the
Dockerfile and was preserved. `rediacc/render:local` (1.1 GB, five-font build assertion)
and `rediacc/web:local` (634 MB) unchanged.

## 2. In-container narration proof (artifacts read, not logs)

`tts_bridge.py` run through `.ci/docker/run-in-tts.sh` with a 2-scene English input,
`--captions` on, models served from the bind-mounted host HF cache. Artifacts read back:

- `voiceover.mp3`: 216,621 bytes, ffprobe duration 8.960 s, equal to timing.json's
  `total_seconds` 8.96.
- `timing.json`: `engine: voxcpm2`, `sample_rate: 48000`, `lead_hold_seconds: 1.5`, both
  scenes `boundary_source: "aligned"` (so Qwen3-ASR plus the ForcedAligner also ran in
  the container), 14 word timings with real varied `start_sec`/`end_sec` values starting
  at exactly 1.5 s (the lead). An earlier readout of all-zero word timings was my own
  wrong key name (`start` vs `start_sec`), not a defect.

Proof artifacts preserved at `scratchpad/docker-proof/{voiceover.mp3,timing.json}`
(moved out of the processing tree).

The FIRST proof attempt failed loudly and honestly: `PermissionError` on
`/gpulock/rediacc-gpu.lock`, because a root container from an earlier session had left
the lease file root-owned at `/var/tmp/rediacc-gpu/rediacc-gpu.lock` and gpu_lock opens
it `a+`. Fixed: file replaced mode 666, and the wrapper now pre-creates the lease file
world-writable and FAILS CLOSED with a named reason when it exists but is not writable.
A lease the narrating user cannot hold protects nothing.

## 3. Wrapper defects found and fixed (this is why w8's wiring could never have worked)

`.ci/docker/run-in-tts.sh` as inherited mounted the repo at `/work`, while
step4000/tts_bridge pass ABSOLUTE host paths and set an absolute cwd, and the PYTHONPATH
that step4000 sets was never forwarded into `docker run`. Every containerised narration
would have died on "No such file or directory" at the bridge script path. Rewritten:

- workspace bind-mounted at its IDENTICAL host path (`-v "$ROOT":"$ROOT"`), `-w` mirrors
  the caller's cwd when under the root;
- `PYTHONPATH` and every set `TTS_*`/`QWEN_*`/`VOXCPM_*` var forwarded with `-e`
  (only when set, so unset knobs stay unset inside);
- model weights: the host `~/.cache/huggingface` (11 GB, all three models) is preferred
  when present, named volume `rediacc-hf-models` as the fresh-host fallback
  (`RDC_HF_CACHE` / `RDC_MODELS_VOLUME` to override);
- lease-file hardening per section 2. `--gpus all`, `--ipc=host`, `-u` caller uid,
  `HF_HOME=/models`, shared `RDC_GPU_LOCK_FILE` retained.

`run-in-render.sh` and `run-in-web.sh` had the same `/work` mount; both now mount
identical-path with pwd-mirroring workdir (web also had a copy-pasted usage header
naming render). Render wrapper controls run INSIDE the container, all passing:
correct pwd, node v22.23.2, `require.resolve("remotion")` from the mounted
node_modules, the five families visible to fontconfig, and
`./chrome-cpu-raster.sh --version` executing the mounted chrome-headless-shell:
`Chromium 149.0.7790.0`. That is the strongest proof available short of a render, which
this task forbids.

## 4. Wiring

`step4000_voiceover.py` (was already wired for the container by w8): one fix. The
host-venv existence check ran unconditionally at the top of `run()` and would have
blocked the container path on exactly the fresh host the container exists for. The
docker decision now happens first; the venv is required only on the host path. The
"narrating via container (.ci/docker/run-in-tts.sh)" log line fired on all six runs.

`step6000_render.py`: new `_render_launcher()` (mirrors step4000's shape: container by
default, `REDIACC_NO_DOCKER=1` forces host, logs "rendering via container
(.ci/docker/run-in-render.sh)" or "host node"). Both the landscape `cmd` and the
vertical `vcmd` are prefixed with the launcher. `--gl=swangle`, the
`chrome-cpu-raster.sh` browser wrapper, `--concurrency` bounds and the props/paths are
byte-for-byte untouched. Both branches unit-checked:
default `(['.../run-in-render.sh'], 'container...')`, forced `([], 'host node')`.
No render was executed (task discipline); the first real render will be the runtime
proof of this path.

## 5. Six-subject re-run: verdicts from files on disk

Driver: `scratchpad/rerun-through-docker.sh`, serial, per-subject stdout and stderr in
separate files under `scratchpad/rerun/`. Every subject's narration log contains exactly
one "narrating via container" line. Verification re-derived per subject from
`2000_script.json`, `4000_voiceover.json`, `5000_storyboard.json`, and ffprobe of the
mp3 (not from exit codes, not from the ######## markers):

| subject | script/vo/sb scenes | engine | total_s = ffprobe | mp3 bytes | words | boundaries | monotonic |
|---|---|---|---|---|---|---|---|
| for-devops | 18/18/18 | voxcpm2 | 58.46 = 58.460 | 1,404,333 | 130 | aligned | yes |
| for-ctos | 19/19/19 | voxcpm2 | 58.80 = 58.800 | 1,412,397 | 130 | aligned | yes |
| for-ceos | 20/20/20 | voxcpm2 | 54.80 = 54.800 | 1,316,781 | 130 | aligned | yes |
| for-ai-agents | 19/19/19 | voxcpm2 | 61.16 = 61.160 | 1,469,421 | 130 | aligned | yes |
| home | 19/19/19 | voxcpm2 | 57.56 = 57.560 | 1,383,021 | 129 | aligned | yes |
| vulnerability-management | 21/21/21 | voxcpm2 | 56.34 = 56.340 | 1,353,645 | 130 | aligned | yes |

All six carry `lead_hold_seconds: 1.5` and stopped at 5000 as ordered; no `6000_render*`
exists for any of them. The ~130-word counts match the English authoring budget, they
are not a cap (durations vary 54.8 to 61.2 s).

**vulnerability-management, verified rather than assumed:** the two stale layers the
brief describes were ALREADY gone before my loop ran. A prior session's `--reprocess`
(`main.py:117` is `shutil.rmtree` plus full restart) had wiped the directory at 18:22
and rebuilt 1000/2000 (21 scenes)/3000 by 18:33. I therefore ran it WITHOUT
`--reprocess`: a second one would have deleted that settled, quality-gated script and
paid opus to regenerate different content. The resume completed 3600/3650/4000/5000;
final artifacts are the 21/21/21 row above. Consequence worth knowing: the rmtree also
deleted all 12 locale scripts (including the 3 matching ones, ar/et/tr), so localization
for this slug restarts from zero when that campaign resumes.

One interruption: the harness killed my long-running background driver task at ~68
minutes, mid vulnerability-management (it was in the 3600 agent step; home had already
exited 0). The pipeline resumes by missing output file, so a fresh
`./run.sh --slug vulnerability-management --until 5000` completed it. No artifact damage;
every row above was verified after that resume.

## 6. Defects found, not owned by me

1. **Split GPU lease defaults across the boundary** (owner: `private/generative`,
   forbidden to this session). `gpu_lock.py:33` defaults to `/tmp/rediacc-gpu.lock`. The
   container wrapper leases the bind-mounted `/var/tmp/rediacc-gpu/rediacc-gpu.lock`,
   but a HOST-side narration that does not export `RDC_GPU_LOCK_FILE` (tutorial pipeline,
   or a `REDIACC_NO_DOCKER=1` solution run) leases the /tmp default instead. Those are
   different files, so a host job and a container job can both load VoxCPM and OOM the
   card. Smallest fix: default `gpu_lock.py` to `/var/tmp/rediacc-gpu/rediacc-gpu.lock`
   on the host too, or export `RDC_GPU_LOCK_FILE` in both pipelines' entry points.
2. **step6000's `_ffprobe_duration` still runs the HOST ffprobe** even when the render
   itself goes through the container. Harmless today (host has ffmpeg again) and it is
   in my file, but routing it through the wrapper adds a container spin per probe; I
   left it host-side deliberately and note the asymmetry.
3. **Harness kills long background tasks** (observed once, at ~68 min). Anything driving
   a multi-hour pipeline from a session should expect it and structure for resume, which
   this pipeline already does.

## 7. Files touched

- `/home/developer/console/.ci/docker/tts/Dockerfile` (assertion widened, /models 1777)
- `/home/developer/console/.ci/docker/run-in-tts.sh` (rewritten; see section 3)
- `/home/developer/console/.ci/docker/run-in-render.sh` (identical-path mount)
- `/home/developer/console/.ci/docker/run-in-web.sh` (identical-path mount, header fix)
- `/home/developer/console/private/growth/video_pipeline/steps/step4000_voiceover.py`
  (venv check moved behind the docker decision)
- `/home/developer/console/private/growth/video_pipeline/steps/step6000_render.py`
  (`_render_launcher`, both render invocations wrapped, path logged)
- `config.py` NOT touched; no path constant needed to change.
