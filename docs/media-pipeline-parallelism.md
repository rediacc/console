# Overlapping GPU narration with CPU rendering

Plan for pipelining the two media pipelines so the GPU synthesizes language N+1 while the
CPU renders language N. Produced 2026-07-29 by a planning agent that read the real files;
corrections to the original brief are kept inline because several of them are load-bearing.

Status: **step 1 (GPU lease) implemented**, remainder sequenced in §9.

---

## 0. Verified on disk, and where the brief was wrong

Confirmed: `packages/www/scripts/lib/ffmpeg-video.ts:53` gates NVENC behind
`RDC_TUTORIAL_HWENC=1` (default software `libx264`); `run.sh:646 www_tutorials_video` calls
`www_tutorial_audio_restore` before anything; `run.sh:740` has a bounded `wait -n` pool;
`main.py:518 _localized_render` runs 4000 -> resync -> 6000 -> 8000 serially per lang, and
`localize_slug` phase B loops langs serially, commented "one Qwen3-TTS model on the GPU at
a time".

Measured live while writing this: RTX 3060 at **12099 / 12288 MiB, 89% util** for a single
`tutorial_tts.cli --lang fr --subtitle --force` (RSS 11.8 GB), concurrently with two `agg`
processes (433% and 278% CPU) and two `ffmpeg -c:v libx264`. Load 29 on 20 cores. So the
one-GPU-job constraint is not a headroom argument: **a single VoxCPM job is already at 98.5%
of the card.**

Six corrections:

1. **Pipeline A cannot be overlapped by reordering alone.** Every local step is `async def
   run()` wrapping a **blocking** `subprocess.run` (`step4000_voiceover.py:93`,
   `step6000_render.py:637` and `:678`, `step8000_teaser.py:41`). A task group over those
   coroutines yields *zero* concurrency. Overlap requires `anyio.to_thread.run_sync`.
2. **The `--jobs N` independence claim has a hole.** `generate-tutorial-video.ts:115` uses a
   *language-independent* cache, `public/assets/tutorials/browser-segments/`, keyed
   `${tutorial}.${scene.id}.${hash}.mp4`. The pair loop is **tutorial-major**, so `--jobs 4`
   across langs puts four langs of the same tutorial in flight; on a cold cache all four
   record and `copyFileSync` to the same path, and all four run the storyboard
   `setupCommand` live-lab hook concurrently. Pre-existing; fix is a per-tutorial `flock`.
3. **The R2 clobber risk is narrower than feared, but the bypass is still better.** Clip
   filenames are content-addressed (`<id>.<textHash[:8]>.mp3`) and `aws s3 sync` has no
   `--delete`, so *changed* narration lands under a new name. The real exposure is a
   `--force` re-synthesis of unchanged text: same name, different bytes, size differs, sync
   overwrites. Bypass the call path rather than relying on unset env vars.
4. **The readiness signal is vacuous for ar/tr/et today.** `validate-tutorial-audio.js:46`
   still lists 10 languages and returns early for anything else, while `tutorial_tts/cli.py`
   now narrates 13. Reconcile before trusting a per-lang gate for those three.
5. **`cli.py`'s timeline write is not atomic.** Harmless under per-lang-process design, but
   a 2-line `os.replace` makes "file exists and parses" a real edge.
6. **Remotion may touch the GPU.** `step6000_render.py:628` passes no `--gl`; pin headless
   Chrome's ANGLE backend to software for the same reason `RDC_TUTORIAL_HWENC` stays off.

---

## 1. Shape: two orchestrators, one shared lock

Not one unified driver.

- Pipeline B (tutorials) is bash-driven; its overlap unit is a **process boundary**. Bash +
  `xargs -P` is the whole implementation.
- Pipeline A (solutions) is one Python process per slug; its overlap unit is a **step
  boundary inside one process**. `anyio` + a thread offload is the whole implementation.
- The only shared thing is the GPU mutex, and it belongs **inside the TTS entry points**, so
  the invariant holds no matter who launches what — including hand-run jobs.

A unified Python driver was rejected: it would reimplement the tutorial job pool, the R2
cache lifecycle and the `ensure_*` preflight that `run.sh` already owns.

---

## 2. Step 1 — the GPU lease  *(IMPLEMENTED)*

`private/generative/src/tutorial_tts/gpu_lock.py`. Lives there because both pipelines
already import `tutorial_tts` in the same venv (`tts_bridge.py` imports `get_engine`;
`step4000_voiceover.py` sets `PYTHONPATH=GENERATIVE_SRC`). No new wiring.

Uses `fcntl.flock`, matching `private/growth/i18n_pipeline/ledger.py`, **not** the
mkdir+pid-liveness lock in `packages/cli`. `flock` is right precisely because the kernel
releases it when the holder dies, so a killed TTS run cannot wedge the fleet.

    gpu_lease(label)          # contextmanager
    describe_holder(fh)       # who is holding it, for the wait message
    wait_for_free_vram(...)   # closes the released-lock-but-context-still-resident race

No disable flag. `RDC_GPU_LOCK_FILE` is the only knob, for tests.

Callers: `tutorial_tts/cli.py::main` (process-lifetime lease, one invocation per language)
and `video_pipeline/tts_bridge.py::main` (already per-slug-per-lang).

Granularity note: per-pair acquisition would be fairer, but the engine keeps the model
resident across pairs, so releasing per pair would force a reload per (lang, cast) across
~19 x 13 pairs. Process-lifetime lease + per-language invocation gives exactly the overlap
unit needed.

**Independently valuable: it makes today's hand-run overlap OOM-proof before any
orchestrator exists.**

---

## 3. Step 2 — an authoritative completion signal

- **3a.** Atomic timeline write in `cli.py`: write `.json.tmp`, then `os.replace`.
- **3b.** Reuse `validate-tutorial-audio.js` as the readiness gate rather than inventing a
  done-marker. It already verifies `transcriptHash` against a recomputed hash, step count vs
  transcript events, per-step id/markerIndex/narrationText equality, replay monotonicity,
  `audioSrc` existence, and `wordTimings` structure/ordering/char-bounds. Add
  `--lang/--cast/--quiet` (~15 lines). **Dispatch renders only after the producing process
  exits** — that is what makes non-atomic intermediate state unobservable.
- **3c.** Reconcile `AUDIO_LANGUAGES` between the validator and `cli.py`. Until then the
  orchestrator must **refuse** ar/tr/et rather than dispatch behind a vacuous gate.

---

## 4. Step 3 — split `www_tutorials_video` into reusable pieces

In `run.sh`, without changing external behaviour:

- `_tutorial_video_pairs()` — prints `tutorial<TAB>lang` to **stdout**, diagnostics via
  `log_*` (already stderr, verified in `.ci/scripts/lib/common.sh:47`). That stderr
  discipline is what makes a stdout work-queue clean.
- `_tutorial_video_render_one()` — one pair, per-job failure file (never one shared appended
  file). **Add** a per-*tutorial* `flock` to close the `browser-segments` race in §0.2, and
  `nice -n 10`.
- `www_tutorials_video()` — unchanged externally.

---

## 5. Step 4 — the tutorial orchestrator

New `www_tutorials_media()` in `run.sh`:

    ./run.sh www tutorials media [name] [--langs en,de,fr] [--jobs N] [--subtitle] [--force]

The whole thing is a shell pipeline:

    _tutorial_media_producer <langs...> | xargs -d '\n' -n1 -P "$jobs" bash -c '…render…' _

Producer, per language: run TTS in the foreground with **stdout redirected to stderr** (so
Python `print()` cannot enter the work queue), then the validation gate, then emit that
language's pairs to stdout. A failing language records and `continue`s — **language N+1's
narration starts regardless.**

`xargs -P` is a globally-bounded, work-conserving, streaming pool: it dispatches as lines
arrive and never exceeds `$jobs` across language boundaries, which a per-language
`( … ) & wait` cannot do without either stalling the producer (starving the GPU, defeating
the point) or letting concurrency multiply to `groups x jobs`. It exits 123 if any child
failed, giving the aggregate signal for free.

Queue size is ~19 x 13 ~= 250 lines x ~35 bytes ~= 9 KiB, far under the 64 KiB pipe buffer,
so the producer can never block on a slow render.

Preflight once: the `ensure_*` chain, `www_tutorial_audio_restore` **exactly once up front
and never again** (structurally satisfying §0.3), and `export RDC_TUTORIAL_HWENC=0` with a
warning line if the operator had it set.

**Expected win:** sequential is `sum(TTS) + sum(Render)`; per-language overlap is
`sum(TTS) + Render(last lang)`. With 13 languages and TTS ~= Render that is **~45% off wall
clock**. A finer per-pair signal would only shave the first language's render tail, so the
plan stops at per-language.

---

## 6. Step 5 — pipeline A, minimal change

In `video_pipeline/main.py`: split `_localized_render` into `_localized_voiceover` and
`_localized_render_only`; replace the serial lang loop with a producer task that awaits
`anyio.to_thread.run_sync(voiceover, lang)` then `tg.start_soon(render, lang)`, with renders
bounded by an `anyio.CapacityLimiter(render_jobs)`.

The blocking helpers call `anyio.run(...)` on the existing step coroutines, so **no step
file changes at all**. The producer must also go through `to_thread` — calling the blocking
`subprocess.run` on the loop thread would prevent `start_soon`'d renders from ever being
scheduled, and the overlap would be zero.

`usage._current` is a `contextvars.ContextVar`, so per-task usage contexts are safe.

`--render-jobs N` defaults to **2**, not 4: Remotion is headless Chrome and RAM-heavy. Add
`--concurrency=<N>` to both remotion invocations (`step6000_render.py:628` and `:670`), since
Remotion otherwise takes ~half the cores *per render*.

---

## 7. Resource tuning

Load 27-29 on 20 cores is not itself the problem (load counts D-state), but nothing bounds
threads: `ffmpeg-video.ts` passes no `-threads`, so each `libx264 -preset medium` grabs
`nproc`.

1. **`nice -n 10` every render job; never nice the TTS process.** Highest-value knob: the
   failure mode that matters is renders starving the GPU job's own CPU work (VoxCPM's audio
   VAE, the ffmpeg mastering chain, the ASR/aligner).
2. `jobs = clamp(floor((nproc - 4) / 4), 1, 6)` -> 4 here, matching the measured-good value.
3. RAM is co-binding: TTS ~11.8 GB RSS, each render ~3 GB. Cap at `(available_gb - 16) / 4`.
4. Optional `RDC_FFMPEG_THREADS` in `videoCodecArgs()`.
5. **The acceptance metric is TTS seconds per clip, not load average.** Accept a job count
   only if the TTS rate regresses <10% against a renders-idle baseline.

---

## 8. Verification

Speed, on a fixed subset (3 languages x 3 tutorials) from an identical starting state:
time the sequential baseline against `www tutorials media`, sampling
`nvidia-smi --query-gpu=utilization.gpu,memory.used -l 5`. The headline number is **the
fraction of wall clock with a VoxCPM process resident on the device** — sequential shows a
long 0% tail, overlapped should approach 100%.

Safety invariants:

1. `max(memory.used) < 12288` MiB and zero `CUDA out of memory` anywhere.
2. At every sample, `--query-compute-apps` shows **<= 1** python process on the device. Test
   the lock deliberately: start two `cli.py --lang` runs and confirm the second **blocks and
   prints its holder line** rather than OOMing.
3. **Output equality** isolating orchestration from TTS nondeterminism: baseline, then re-run
   overlapped *without* `--force` so TTS is cache-hit, and assert mp4 hashes match. Comparing
   across a `--force` re-synthesis is meaningless — VoxCPM sampling is not deterministic.
4. `validate:tutorial-audio` and `check:ci-tutorial-parity` pass afterwards.
5. **Failure isolation tested, not assumed**: corrupt one storyboard for one language,
   confirm every other pair still renders, the run exits non-zero, and the report names
   exactly that pair.
6. No R2 writes except the single explicit upload at the end; `VIDEO_LANGS` untouched;
   nothing committed.

---

## 9. Sequencing

| # | Change | Depends on | Independently shippable |
|---|---|---|---|
| 1 | `gpu_lock.py` + wire `cli.py::main` and `tts_bridge.py::main` | — | **Yes — ship first** |
| 2 | Atomic timeline write in `cli.py` | — | Yes |
| 3 | Reconcile `AUDIO_LANGUAGES` (validator <-> `cli.py`) | — | Yes; blocks ar/tr/et overlap |
| 4 | `--lang/--cast/--quiet` on `validate-tutorial-audio.js` | 3 | Yes |
| 5 | Split `www_tutorials_video` (+ per-tutorial `flock`, + `nice`) | — | Yes; also fixes the cold-cache race |
| 6 | `www_tutorials_media` + dispatch + help | 1,4,5 | The overlap lands here |
| 7 | Point `www_tutorials_all` at it | 6 | Yes |
| 8 | Pipeline A: `_localize_phase_b` + `--render-jobs` + remotion `--concurrency`/`--gl` | 1 | Yes |
| 9 | Verification run + docs | 6,8 | — |

The tree is dirty with an in-flight VoxCPM2 migration. Every change above is additive; item
3 is the only one touching a file that migration is already editing.

## Critical files

- `run.sh` (`www_tutorials_video` ~646, pair loop ~723, pool ~740, `www_tutorials_all` ~845,
  dispatch ~1590, help ~1412)
- `private/generative/src/tutorial_tts/cli.py` (`main()` ~176, engine ~216, align barrier
  ~638, timeline write ~731, `AUDIO_LANGUAGES` :17)
- `private/growth/video_pipeline/main.py` (`_localized_render` :518, phase B ~545, parser ~660)
- `packages/www/scripts/validate-tutorial-audio.js` (`listTranscriptPairs` :118,
  `validatePair` :138, `main` :314, `AUDIO_LANGUAGES` :46)
- `private/growth/video_pipeline/steps/step6000_render.py` (`run()` :412, remotion :628, :670)
