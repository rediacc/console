# 01. Verified context

Status: **verified 2026-08-27**, session `e580532b`, branch `0827-1`, on a freshly
rebuilt host.

**RE-VERIFY BANNER.** Every file:line below is a hypothesis until you check it against
the tree. Numbers taken from a dev server are marked as such and are look-only grade,
because `browser-probe.md` records that a stale dev server serves a SMALLER page without
failing. Re-take every page number against a frozen static build before acting on it.

## The host

Rebuilt shortly before this session, which is why so much below is missing rather than
wrong.

| thing | state |
|---|---|
| GPU | RTX 3060, 12287 MiB, sm_86 |
| driver | KMD 616.56, CUDA UMD / driver API 13.4, past the 580.65 floor CUDA 13 needs |
| CUDA host probe | `cuInit` 0, `cuCtxCreate` 0, `cuMemAlloc` 256 MiB 0 |
| free VRAM to a context | 11243 of 12287 MiB, 1044 MiB WDDM reserve |
| largest single alloc | 10239 MiB, a CONTIGUOUS ceiling, not a total |
| Docker | 29.7.2, Compose v5.4.0, Docker Desktop WSL integration, no dockerd in-distro |
| GPU in Docker | works with zero configuration, same 11243/12287 inside a container |
| nvidia-container-toolkit | NOT installed and NOT needed; Desktop injects the plumbing |
| disk | 378 GB free |
| RAM / cores | 56 GB, 24 |
| both python venvs | EMPTY, 0 packages, python 3.14.4 |
| agent-browser | 0.35.1, installed this session, Chrome 152 plus system libs |

VoxCPM2's recorded synthesis peak is 12105 MiB, which is 862 MiB above the free figure
here. That is a WATCH ITEM, not a prediction: the caching allocator does not need one
contiguous slab, and the 12105 figure is a single sample taken on the previous host.
Measure a real narration on THIS box before changing `MIN_FREE_MIB`.

## Verified defects, none yet fixed

**D1. Every rdc command shown on camera in the solution videos is invalid.**
18 `terminalType` scenes, 11 distinct commands. All 13 sampled fail `parseRdcCommand`
from `packages/www/scripts/lib/cli-reference-catalog.js`: unknown commands
(`rdc keygen`, `rdc security-scan`, `rdc audit`), unknown options (`--name`, `--parent`),
a missing mandatory `--tag`, excess positionals. Instrument proved first: 12 of 12
known-good `commandFull` values from the tutorial storyboards parse clean.

**D2. `validate:landing-cli-usage` is vacuous.** It exits 0 with "no landing terminal
sources exist, so there is nothing to validate". `en.json` now holds ZERO `terminal`
blocks, but all 21 `1000_source.json` still carry `facts.terminal` from a snapshot taken
before that removal. The videos are the last surviving copy of deleted site content, and
the validator that would have caught D1 guards nothing.

**D3. The Remotion renderer guards Arabic only.**
`private/growth/video_pipeline/remotion/src/fonts.ts` wraps the Arabic face in
`delayRender`/`cancelRender`. `DEFAULT_FONT_STACK` is
`'Inter', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif` with no assertion behind it.

**D4. Four of five named font families are absent on this host.** `Inter`,
`JetBrains Mono`, `WenQuanYi Zen Hei`, `Noto Sans Arabic` all MISSING; only `DejaVu Sans`
is present. Combined with D3: a render today would ship all 12 non-Arabic locales in a
substituted typeface, silently, exit 0. The card path fails closed instead
(`assertCardFontsUsable`), so only the video path is exposed.

**D5. `voxcpm` is declared nowhere.** Not in `private/generative/pyproject.toml`, not in
`run.sh`'s pip list (`pip install -e`, `qwen-tts`, `qwen-asr`). It backs the DEFAULT
engine. `from voxcpm import VoxCPM` fails on a clean venv.

**D6. `torch>=2.2` is unpinned** and today resolves to a CUDA 13 build. Fine on 616.56,
but a venv rebuild silently changes CUDA major.

**D7. The video manifest records the TTS engine and not the renderer.**
`packages/www/scripts/lib/update-video-manifest.ts:42-54` calls `engine` "the only engine
provenance CI can see". Nothing records the Remotion version, so a mid-fleet bump is
invisible in exactly the way the Qwen3 drift was.

**D8. The GPU lease cannot cross a container boundary.**
`private/generative/src/tutorial_tts/gpu_lock.py:33` defaults to `/tmp/rediacc-gpu.lock`,
and `/tmp` is per-container. `MIN_FREE_MIB = 8192` at `:51` passes at 11243 free and the
job OOMs later; `wait_for_free_vram()` WARNS AND PROCEEDS on timeout.

**D9. `agent-browser` positional flag-eating.** REPRODUCED this session.
`screenshot [selector] [path]` takes two positionals; `--full-page` is not a real flag
(the real one is `--full`), so it is eaten as `[path]`. Result: the intended path becomes
the SELECTOR, a file named `--full-page` lands in `$PWD`, exit 0, output reads
"Screenshot saved to --full-page". `browser-probe.md:119-123` already records the sibling
case: `AGENT_BROWSER_SCREENSHOT_DIR` is ignored and put three untracked PNGs in a repo.
The rule exists in prose and has no enforcement surface.

## Page density, dev-server grade, RE-MEASURE against a frozen build

| page | height | screens at 900px | words | atoms |
|---|---|---|---|---|
| `/en` | 5838px | 6.5 | 518 | 157 |
| `/en/for-ctos` | 7560px | 8.4 | 712 | 168 |
| `/en/solutions/infrastructure-costs` | 8749px | 9.7 | 851 | 255 |
| `/en/solutions/encryption` | 8719px | 9.7 | 892 | 245 |
| `/en/solutions/instant-recovery` | 8900px | 9.9 | 937 | 237 |

"Atoms" counts headings, list items, table cells, chips, stat blocks and step cards, i.e.
objects the eye must land on separately. The three solution pages sit within 3% of each
other, so this is systemic and not one bad page.

`infrastructure-costs` states FOUR claims twenty-five times: idle-and-still-paying 10x,
70% saved 4x, auto cleanup 5x, copies share disk 6x. 55 distinct numeric tokens, 86
occurrences, in 944 source words. Three of five timeline chevrons carry the identical
sentence. The `sp-stats` bar restates the "WITH REDIACC" chips roughly 100px above it.

Section heights on that page: `sp-problem` 1500px for 109 rendered words (tallest,
thinnest), `sp-cost-section` 1092px, `sp-how-it-works` 966px and 62 atoms (densest),
`sp-comparison-section` 753px and 43 atoms, `sp-tech-detail` 729px for 125 words and 1
atom (a wall).

`SPHomePage.astro` records that the homepage was measured at 7585px for 658 words and
that nine sections became five. **The solution pages are still in the state the homepage
was rescued from.**

## Video fleet

21 slugs, 13 locales, 3 files each = 819 objects, 4.8 GB, gitignored, R2-backed.
Total English runtime 22.7 minutes.

| scene_type | seconds | share |
|---|---|---|
| mechanism | 428.6 | 31.4% |
| problem | 275.2 | 20.2% |
| hook | 248.2 | 18.2% |
| proof | 247.8 | 18.2% |
| cta | 164.6 | 12.1% |

The emotional-colour convention FORCES danger red on hook and problem, so 38.4% of screen
time is alarm red on a `#0b0e14` near-black frame. `semantic_sense` FAILS a hook or problem
scene rendered in calm teal, so lightening the videos is a change to the convention, the
threshold and the gate together, not a styling tweak.

68 cta scenes across 21 slugs, always trailing, 2 to 4 per video.

## Remotion

Installed 4.0.463 (2026-05-19). Latest 4.0.518 (2026-08-26). 54 releases, 1084 changelog
bullets, 319 touching packages we could use. Most churn is Studio, Browser Studio and
`@remotion/media`, none of which a headless `npx remotion render` touches.

Worth taking: `--frames=0,10,20` multi-still (4.0.502), encode backpressure (4.0.515),
fd leak fix (4.0.505), `ExtractFrame` zero-extra-threads panic (4.0.508), fractional
OffthreadVideo frame selection (4.0.506), Fast Start finalisation (4.0.517).

Worth SKIPPING: NVENC (4.0.484). Encoding is 0.39% of render time by this repo's own
profile, and hardware encoding inflates file size with no `crf`.

`@remotion/effects` first shipped 4.0.464, one release after our pin, about 55 effects.
Adoption cost is real: effects apply to canvas components, our scenes are DOM, and nested
`HtmlInCanvas` was REVERTED in 4.0.514.

v5.0 is announced and would change output: colour space bt601 to bt709, default GL
renderer to `angle`, `<Sequence>` auto-premount 1s, `<Img>` pausing while loading, plus
mandatory telemetry for Company License holders. Do NOT chase v5 in this program.
