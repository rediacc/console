# 04. The video fleet

Status: **planning**, verified 2026-08-27.

## The efficiency rule that shapes every wave here

Four separate decisions all change rendered pixels: the Remotion bump, the CTA cut, the
terminal cut, and the palette. Two more change the fleet SIZE: four persona videos and one
homepage video.

Rendering is the expensive step. A pair renders in 2 to 3 minutes, and narration is a
serial GPU job on one card.

    existing   21 slugs x 13 locales                    = 273
    new         5 subjects (4 personas + homepage) x 13 =  65
                                                    total 338
    x 2 orientations (landscape + vertical)             = 676 renders

At the measured pace that is an order of 15 to 30 hours of render, plus narration. Doing
it four times because four decisions landed separately is the single largest waste
available in this program.

**So: every video-affecting decision lands BEFORE any render, and the fleet is rendered
ONCE.** That is Wave 7, and Waves 2, 3 and 6 are its prerequisites. This is ordering, not
postponement (I2).

## Operator directives, this session

**V1. The pipeline is for NEW videos only.** The CTA cut and the terminal cut on the 273
EXISTING videos are direct edits to `2000_script*.json` and `5000_storyboard*.json`, not a
re-run of steps 1000 to 5000. Re-running the agent steps would re-derive scripts we already
have, re-pay the Opus judge loop 273 times, and re-open converged quality gates for a
deletion we can make deterministically.

**V2. No ElevenLabs.** `private/growth/pipeline/podcast_tts.py` is a cloud TTS path for the
podcast domain. Audio generation for this program is local GPU only, VoxCPM2 via
`private/generative`.

## Wave 3, part A: cut the CTA scenes

68 scenes across 21 slugs, always trailing, 164.6s = 12.1% of total runtime. Content is
"Start your fourteen-day trial", "14-DAY FREE TRIAL", "START FREE", "rediacc.com".

Deleting scenes changes the audio, so narration must be regenerated for every affected
(slug, locale). It is not a caption-level edit.

The authoring side currently MANDATES what is being removed, so these change together:
- `prompts/script.py:110` lists `cta` in the scene_type enum; `:182` prescribes
  "Beats 22-26 (cta): Low-friction close"; `:194` and `:265` and `:299` reference cta.
- `config.py` maps cta to SOLUTION_COLOR in the emotional-colour convention.
- `MIN_SCENE_COUNT = 16` gets tighter once 12% of beats leave.
- `CONTRACT.md`'s scene table and the `arc_impact` quality gate, which judges whether "the
  ending makes them want it".
- `remotion/src/scenes/Cta.tsx` and the `cta` template in the storyboard vocabulary.

Decide what the last beat becomes. A video that simply stops after `proof` may read as
truncated. **DECIDED (A2): the final `proof` beat holds on the Rediacc brand mark with no
offer text**, which keeps a deliberate visual ending without an ask.

## Wave 3, part B: cut the terminal scenes

18 `terminalType` scenes, 11 distinct commands, ALL invalid (D1). This is a correctness
fix wearing a simplification hat: the fleet currently teaches wrong CLI syntax in 13
languages, and `validate:landing-cli-usage` cannot catch it because it is vacuous (D2).

Two consequences to carry:
- `validate:landing-cli-usage` should be retired or given real inputs in the same change.
  Leaving a vacuous gate wired is worse than removing it, because it reads as coverage.
- `terminalType` may become an unused template. Check `CATEGORY_CAST` and
  `facts.terminal_real` before deleting the extractor: `cast_terminal.py` also feeds
  grounding for the script writer, which is legitimate even with no terminal scene.

## Wave 3, part C: the palette

38.4% of screen time is `#f87171` alarm red on a `#0b0e14` near-black frame, and that is
ENFORCED, not incidental. `config.py` sets `PROBLEM_COLOR` and `SOLUTION_COLOR`; the
`semantic_sense` visual gate FAILS a hook or problem scene rendered in calm teal and
dispatches a storyboard fix. Lightening the videos without moving the gate means the QA
loop re-darkens them.

So this wave changes three things together: the constants, the `semantic_sense` rubric in
`prompts/visual_comprehension.py`, and `CONTRACT.md`'s emotional-colour table.

This is coupled to Wave 5. A near-black video dropped into a newly-light page hero is a
black rectangle on a white page. Decide the video ground and the page ground TOGETHER.

## Wave 2: Remotion 4.0.463 to 4.0.518

Patch-level inside one major. Verified worth taking, worth skipping, and the v5 hazards:
see `01-verified-context.md`.

Two things this wave must produce beyond the version bump:

1. **An SSIM A/B on one slug**, the same instrument that proved the `--disable-gpu` switch
   at 3.87x and SSIM 0.99831. A renderer change that moves pixels across a partly
   re-rendered fleet is exactly the drift D7 says nothing can see.
2. **A `renderer` field alongside `engine` in the video manifest.** Small change to
   `publish.py` and `update-video-manifest.ts`. Without it, a mid-fleet bump splits the
   fleet invisibly, which is how 207 of 273 narrations sat stale on Qwen3 until a human
   heard it.

Do NOT chase v5.0.

## Wave 6: the new videos

Four persona pages plus the homepage.

**The blocker is a source adapter, and it is already written.** `video_pipeline`'s
`solution_source.py` regex-parses `SOLUTION_PAGES` for `contentKey` plus `category`, and
personas have neither. But `private/growth/www_pipeline/surfaces.py` ALREADY enumerates
both surfaces as `WorkItem`s: `pages.personaPages.<key>` with per-persona audience
profiles (`forCeos` exec, the other three cto), and `HOMEPAGE_GROUPS`, the 16
marketing-bearing top-level `en.json` groups with pure-UI chrome excluded. Port that
adapter rather than writing a new one.

Three gaps the port must close:
- `category` is load-bearing three times: `CATEGORY_PAINS_DOC`, `CATEGORY_CAST`,
  `CATEGORY_BLOCKSHARE_FRAMING`. Personas have `personaType` instead. Decide a mapping.
- `illustration_path(slug)` has nothing to resolve; personas carry `illustrationSlug`
  pointing at an existing solution illustration.
- Publishing hardcodes `videos/solutions/<lang>/`, and the manifest has exactly two
  namespaces, `tutorials` and `solutions`. Decide whether personas ride `solutions` with
  `for-*` keys or get a third namespace. **DECIDED (A6): a THIRD namespace.** Both CI
  gates are scoped to `src/pages/[lang]/solutions/*.astro` and would not see personas under
  either choice; a separate namespace makes the shape of the matching gate obvious.

**DECIDED (A1): motion graphics, all five.** The founder track never happened and its
shoot plan is deleted. Both persona and homepage videos go through the pipeline at 13
locales.

**The homepage video CONTENT question is still open and must not be guessed.** The site's
own taxonomy already answers "what do you show with 21 solutions": three verb anchors,
Copy 4 / Test 7 / Recover 5, plus a 5-page property ring. A video that enumerates
solutions contradicts the constellation directly beneath it.

`private/growth/research/anthropic/strategy/landing-page-video-usage.md` remains useful
for everything EXCEPT its founder recommendation: hosting, autoplay versus click-to-play,
thumbnails, page-speed cost and the video tax all still apply to a rendered video.

## Wave 3, part D: the 1.5 second lead hold (A8)

Operator decision, this session: every video holds for **1.5 seconds before narration
starts**, so a viewer can focus or go full screen. Applies to the 273 regenerated videos
as well as the 5 new subjects, so it costs nothing extra given the render-once rule.

There is a tail constant already (`config.py:207`, `END_HOLD_SECONDS = 3.0`) and a
per-beat one (`:233`, `SCENE_HOLD_S = 0.4`). There is no LEAD constant. Add
`LEAD_HOLD_SECONDS = 1.5` beside them.

**Two candidate implementation points. Pick one, do not mix.**

1. **In `step6000`, alongside where `END_HOLD_SECONDS` is applied.** Offset every scene
   `start` by +1.5s, extend `total_seconds` and `durationInFrames`, and shift every
   `word_timings` entry, which are ABSOLUTE. The mp3 is untouched, so nothing re-narrates.
   Requires delaying the `<Audio>` element, which `SolutionVideo.tsx:10` currently anchors
   at frame 0 and says is "never moved". That comment becomes wrong and must be updated.
2. **Prepend 1.5s of silence to the mastered mp3.** Everything downstream stays consistent
   for free because the timeline is derived from the waveform, and `<Audio>` keeps its
   frame-0 anchor. Costs one ffmpeg pass per (slug, locale) and makes the audio artifact
   and the timeline change together, which the cache key must reflect.

Option 2 is the lower-risk one: it keeps the sample-exact invariant
`last scene start + duration == total_seconds` true by construction, which
`tts_bridge._assert_timeline_sane` enforces in-process.

**What the hold shows matters.** Hold the FIRST SCENE'S VISUAL, not black and not a logo.
A black lead-in reads as a loading failure, and the first beat is a `hook`, which is
designed to be looked at.

**GATE COLLISION, and it will fire across the whole fleet if missed.**
`steps/step7000_visual_qa.py:156` hardcodes `timestamps = [0.5, 1.5]`, two FORCED early
samples that exist so the `hook_punch` dimension can judge the opening. With a 1.5s lead
hold, both land inside the hold, so the adjudicator judges a static held frame,
`hook_punch` collapses below its threshold of 7, and the visual loop dispatches storyboard
fixes for a problem that IS the new lead-in. Shift those two offsets by
`LEAD_HOLD_SECONDS` in the same change.

## Wave 7: one render and publish pass

Publishing is four steps and skipping one produces a silent partial publish that every
gate reports as fine: stage, upload, regenerate the manifest, purge the CDN.

Two traps recorded and still live:
- `generate-video-manifest.ts` is a SCAN, not a merge. It rebuilds from whatever media is
  on disk, and media is gitignored, so running it on a normal checkout DROPPED ten locales
  from 21 slugs. Always `sync-media-from-r2.sh` first.
- Purge verification reads the BUCKET, not the exit code, and needs
  `AWS_DEFAULT_REGION=auto` or `list-objects-v2` returns an empty list that reads as an
  empty bucket.

Media goes to R2 and never into a commit (I12).
