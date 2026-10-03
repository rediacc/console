# The skip-on-existing-artifact class in private/growth

Scope: `video_pipeline` plus the sibling pipelines `clarity_pipeline`, `www_pipeline`,
`illustration_pipeline`, `i18n_pipeline`, `pipeline`. Every site enumerated, a verdict
recorded for each, and every site judged a bug fixed.

The class in one sentence: a step skips because its output file exists, that decision is
made without looking at the inputs the output derives from, and the run says nothing
about it. Zero failures, normal markers, no work.

## The fix, in one shape

New module per pipeline, `artifact_cache.py`, with one predicate:

    is_fresh(tag, output, inputs, what=...) -> bool     # logs at INFO in BOTH directions

- reuse prints `[8000] CACHED en teaser (2 input(s) unchanged): <absolute path>`
- rebuild prints `[8000] STALE en teaser - rebuilding 8000_teaser.json; newer input(s): ...`

`registry.StepDef` gained an `inputs: tuple[str, ...]` field. It is the ONE place a step's
derivation is declared, read by both the runner and the step's own guard, so the two
layers can no longer disagree. An empty tuple is a claim ("re-running cannot change the
answer", or "a stronger content key already exists"), documented on the StepDef, not an
omission.

Comparison is mtime, not hashing: the artifacts are mp4s, wavs and large JSON, and every
writer here writes its output strictly after reading its inputs, which is the only
property mtime ordering needs. `SAME_SECOND_SLACK = 1.0` exists because step5500 rewrites
`5000_storyboard.json` and then writes its own output in the next breath; without slack it
would rebuild forever. Where a stronger content key already exists (step1000's
`cache_key`, step4000's engine + lead-hold, i18n step1000's `delta_signature`) the mtime
check is ANDed with it, never a replacement.

## Enumeration and verdict, site by site

### video_pipeline

| site | verdict | what changed |
|---|---|---|
| `main.py:160` STEPS loop (**instance 1**) | BUG: silent AND input-blind, and it pre-empted every step's own cache logic | now `artifact_cache.is_fresh` over registry inputs; skip prints the artifact path |
| `steps/step8000_teaser.py:58` (**instance 2**) | BUG: teaser cached against its own sentinel, never against the mp4 it is cut from | compares `6000_render<suf>.json` + `video/<slug>.<lang>.mp4`; also rebuilds when the recorded teaser mp4 is gone, and when the prior sentinel recorded a SKIP (a cached failure is not a cache hit) |
| `steps/step4000_voiceover.py:87` | BUG: keyed on engine + lead-hold, both of which describe HOW a line was said, neither of which notices the line changed | script mtime ANDed in. Narration older than its script is the worst artifact here: the video says the old words with a plausible duration and a zero exit code |
| `steps/step_translate.py:124` | BUG: localized script/storyboard cached against their own existence, not against the English pair they were translated from | both halves checked against `2000_script.json` / `5000_storyboard.json`; `and` not `or`, because one fresh half plus one stale half is a mismatched pair and the render reads them together |
| `steps/step6000_render.py:461` | BUG: `6000_render.json` exists != the mp4 matches its inputs. `resync_storyboard_timing` rewrites the localized storyboard immediately before every localized render | checks storyboard + voiceover, and requires the recorded mp4 to still be on disk |
| `steps/step7000_visual_qa.py:126` | BUG: a vision verdict describes the frames it sampled; a re-rendered video makes it a green light nobody earned | checks `6000_render.json` + the mp4 |
| `steps/step5500_stockvideo.py:70` | BUG: which scenes need a clip lives in the storyboard | checks `5000_storyboard.json` |
| `steps/step5000_storyboard.py:75` | BUG: a storyboard older than its script narrates one thing and shows another | checks `2000_script.json`. Deliberately NOT `4000_voiceover`: step6000 renders audio-true and re-joins by scene id, so a re-narration cannot change the shipped frames through this artifact, and listing it would spend an opus storyboard per re-narration for zero pixel difference |
| `steps/step2000_script.py:38` | BUG: this is the exact defect step1000's own header describes ("thirteen languages shipped CLI syntax that had already been re-recorded") one step downstream | checks `1000_source.json` |
| `steps/step3000_quality.py:31` | BUG: a verdict is only valid over the text it judged | checks script + source |
| `steps/step3600_social.py:51`, `steps/step3650_social_quality.py:29` | BUG, same shape | checks source + script, and posts + source |
| `steps/step1000_source.py:287` | CORRECT CACHING, already visible. `cache_key` hashes page copy, `.cast` bytes and pains docs | left alone; registry records why it declares no mtime inputs |
| `publish.py:145` `_copy_if_changed` | BUG: compared **size only**. Size cannot see a re-render | size AND mtime; the skip now logs `UNCHANGED (same size, not re-rendered): <path>` |
| `publish.py:154` `_make_poster` | **BUG, third instance of the same defect, one directory downstream, and silent.** The poster is a frame of the video and was pinned to the FIRST render forever | rebuilds when the mp4 is newer; logs CACHED / STALE with the path. This is what a visitor sees before pressing play, and it was about to bite: the pass is re-rendering 288 localized mains |
| `publish.py:164`, `steps/step7000_visual_qa.py:57,106` | not the class (post-subprocess success checks) | unchanged |
| `assets/svg-library/build_preview.py:64`, `persona_source.py:205`, `solution_source.py:70,115`, `steps/step6000_render.py:75` | not the class (optional-input reads, path resolution, feature probes) | unchanged |
| `registry.get_resume_step` / `is_done` | BUG: reported "already fully processed" for a slug whose artifacts are all present and half of them stale | now missing OR stale. Silent on purpose: it is a query run once per slug by `--list`; the runner does the reporting |

### clarity_pipeline / www_pipeline / illustration_pipeline / pipeline

| site | verdict | what changed |
|---|---|---|
| `clarity_pipeline/main.py:121`, `www_pipeline/main.py:129`, `pipeline/main.py:122` | BUG: the identical silent `if (proc / step.output).exists(): continue` | same predicate, same visible log |
| `illustration_pipeline/main.py:212` | BUG: logged `  [5000] cached` naming the step and nothing else, and asked only whether the file existed | now names the artifact and its inputs |
| all four `get_resume_step` | BUG, same as video_pipeline | missing OR stale |
| all four registries | inputs declared from what each step actually READS (grepped per step, not guessed). `clarity`/`www` step5000 deliberately declare NO inputs: they screenshot the LIVE dev server, so their real input is outside `processing/` and mtime cannot see it. Declaring a false input would be worse than declaring none, and the registry says so | |
| step-level guards in these four | left as-is by design. Their runners now UNLINK a stale artifact before dispatch, which is how the two layers agree, and is what `_quality_loop` / `_visual_loop` in those same files already do before a re-dispatch | |
| `pipeline/steps/step1400_update_kb.py:586` | BUG, silent: prophetic-event notes are a pure function of `PROPHETIC_EVENTS`, which lives in SOURCE, so an edit froze every already-written note. No input file exists whose mtime could tell | compares CONTENT, which is exact; summary logged as written / rewritten / already-current |
| `pipeline/podcast_tts.py:479` | BUG: an mp3 cached on "a file with this label exists" cannot see that the beat's SCRIPT changed. It logged `cached`, which made it look checked | text sha256 sidecar. A beat with no sidecar is pre-existing: reused and reported as **UNVERIFIABLE** rather than silently blessed, because re-rendering a back catalogue on a paid API is not a decision a cache change gets to make alone |
| `pipeline/podcast_tts.py:197` `ensure_silence` | CORRECT CACHING. The output is fully determined by its only parameter, which is encoded in the filename (`_silence_<ms>ms.mp3`); there is no state it can be stale against | left alone, and deliberately NOT logged: it is a per-gap primitive, not a step, and an INFO line per gap would degrade the log the visibility rule exists to protect |
| `pipeline/steps/*` (20 further guards) | all already logged `Using cached X`; all now covered by the runner's input check + stale unlink | |
| `pipeline/kb_audit.py:107`, `models.py:602`, `playbook_extract.py:628`, `video_registry.py:85`, `illustration_pipeline/cheap_localize.py:65`, `steps/step1050_visual_extraction.py:98` | not the class (optional-input reads, directory listings, an unlink) | unchanged |

### i18n_pipeline

| site | verdict | what changed |
|---|---|---|
| `steps/step1000_extract.py:35` | CORRECT CACHING, already visible: `delta_signature` content key | unchanged |
| `steps/step2000_naturalize.py:102` | BUG: it WROTE `source_hash` into the artifact on every run and never read it back. Exactly the shape step1000_source in video_pipeline paid for | compares it; logs CACHED with the hash and the path, or STALE with old -> new |
| `steps/step9000_apply.py:19` | BUG: an apply report older than the rewrite it claims to have applied | compares `2000_rewrite.json`; logs with the path |
| `ledger.py:41`, `adapters/locale_adapter.py:71` | not the class | unchanged |

## The one-slug experiment: for-devops, end to end, measured

Not a simulation. `6000_render.json` was dropped and the English main genuinely
re-rendered through `./media.sh run video_pipeline --slug for-devops --until 6000`
(61.5 s of video, 7.0 MB, exit 0). Step 8000 was then driven WITHOUT deleting its
sentinel, deliberately not via `./media.sh teaser`, which unlinks first and would have
masked the behaviour under test.

Instance 1, before vs after. Under the old code the resume through nine already-complete
steps printed NOTHING. Now:

    07:34:39 [1000] CACHED source (no declared inputs): .../for-devops/1000_source.json
    07:34:39 [2000] CACHED script (1 input(s) unchanged): .../for-devops/2000_script.json
    07:34:39 [3000] CACHED quality (2 input(s) unchanged): .../for-devops/3000_quality.json
    ... 3600, 3650, 4000, 5000, 5500 ...
    07:34:39 [6000] Rendering video (en)...

Instance 2, on artifacts:

| | before | after |
|---|---|---|
| `for-devops.en.mp4` mtime | 04:39:53 | 07:37:09 (re-rendered) |
| `8000_teaser.json` mtime | 04:44:31 | 07:40:52 |
| `for-devops.teaser.en.mp4` mtime | 04:44:31 | **07:40:52 (rebuilt on its own)** |
| teaser sha256 | f786c3c2... | f786c3c2... (identical) |
| main meanY / teaser meanY | 211.1 / 174.2 | 211.1 / 174.2 |

The step announced the reason itself:

    [8000] STALE en teaser - rebuilding 8000_teaser.json; newer input(s): 6000_render.json, for-devops.en.mp4

A second run is a visible cache hit:

    [8000] CACHED en teaser (2 input(s) unchanged): .../for-devops/8000_teaser.json

The bytes are identical because the render is deterministic and the inputs did not change
in CONTENT, only in mtime. That is a useful control (a rebuild from unchanged inputs
cannot corrupt anything) but it does not prove the teaser follows its source, so I
measured that separately, on artifacts, against the real `step8000_teaser` module in a
throwaway processing dir:

| | pre-fix guard (control) | current code |
|---|---|---|
| teaser cut from a BLACK main | meanY 16.0 | meanY 16.0 |
| main replaced with a WHITE one, **sentinel left in place** | meanY **16.0** (never rebuilt) | meanY **233.0** |
| verdict | FAIL: the teaser did not follow its source | PASS |

## The gate

You wrote `private/growth/.ci/checks/check-cache-invalidation.sh` and wired it into that
repo's `pre-commit`. I had already written one before your correction arrived; I moved it
OUT of the repo rather than ship a second gate, and kept it as my own verification
harness at
`/tmp/claude-1000/-home-developer-console/e580532b-53bf-4b76-92d8-b15b242c96d5/scratchpad/teaser-oracle.sh`.
It is a behavioural oracle rather than an artifact-state check: it renders a real fixture
mp4 with ffmpeg, drives the real step module against a throwaway `PROCESSING_DIR`, and
asserts rebuild-on-newer-source, reuse-on-unchanged, and that the skip names the artifact.

- `--selftest` plants the verbatim pre-fix guard in a copy of the module and requires the
  oracle to reject it. It does, on both assertions: `VISIBILITY: the cached skip never
  named the artifact` and `STALENESS: the mp4 was re-rendered and the teaser was NOT
  rebuilt`.
- Against the current code, all three assertions pass.
- Two failures the oracle found while I was building it: one real
  (`pipeline/steps/step1400_update_kb.py:586`, now fixed) and one in the oracle itself,
  which watched only the STEP module's logger and therefore reported `<silence>` for a run
  that was in fact perfectly loud. Worth naming because it is the same mistake the oracle
  exists to catch, made by the oracle.

## FOUND, NOT FIXED: your gate is blind to English, which is instance 1's population

I am not touching the file, because you asked me to leave it alone.

`check-cache-invalidation.sh:29-32` derives the source path from the sentinel name:

    suf=$(basename "$sentinel" .json); suf="${suf#8000_teaser}"
    src="$dir/video/${slug}${suf}.mp4"
    [ -f "$src" ] || continue          # nothing derived yet, nothing to invalidate

For an English sentinel `8000_teaser.json`, `suf` is empty, so `src` is
`video/<slug>.mp4`. The English main is named **`<slug>.en.mp4`**. The file never exists,
`continue` fires, and the check moves on in silence.

Measured on the real tree: 26 English sentinels, 25 non-English. The gate examines the 25
and silently skips all 26. Direct proof, taken while `for-devops`'s main was 2h53m newer
than its sentinel and the gate reported it as clean:

    for-devops: gate looks for video/for-devops.mp4 -> MISSING; actual is video/for-devops.en.mp4 -> EXISTS

The English half is exactly what instance 1 hit (phase A, 21 of 26 slugs). One line:

    src="$dir/video/${slug}${suf:-.en}.mp4"

Consider also failing rather than `continue`ing when a sentinel has no resolvable source:
today that path is indistinguishable from "checked and clean", which is the class the gate
is for.

Current gate state after my fix: exit 1, **9 findings, all `audit-trail`**, which is the
slug the live pass is inside. Nothing else on the tree is red.

## What the live pass did and did not see

The pass (PID 1685110, 3h55m in) spawns one `python3 main.py` per slug, so it read
`main.py` into memory before my edits and keeps the old code for `audit-trail`. It is
still logging `[8000] Using cached teaser` for that slug, as expected, and it has thrown
no traceback. Slug 3 onward (`backup-verification`) gets the new code.

I measured the blast radius on the pass's remaining 24 slugs BEFORE changing anything, so
this is not a hope:

| | pairs affected |
|---|---|
| re-translate | 72, and all 72 are the six new slugs that have no translations at all, so they would translate regardless |
| re-narrate | 288 (already forced by the existing lead-hold key; my change adds nothing) |
| re-render | 288 (already forced; the render markers were deleted earlier tonight) |
| **re-teaser** | **287, which is the entire point and the only new work: about 3 s of ffmpeg each** |

## Something you should decide, because the code now tells the truth about it

`get_resume_step` is honest now, and the honest answer for the English pipeline is not
"done":

    15 slugs resume at [2000] script     1000_source.json (08-27 16:51) is NEWER than 2000_script.json (08-27 16:14)
     5 slugs resume at [3000] quality    2000_script.json (08-27 17:57) is NEWER than 3000_quality.json (07-22)
     5 slugs DONE                        the six new subjects
     1 slug  resume at [7000] visual_qa  for-devops, because I re-rendered its main

That 16:51 timestamp is not a bulk touch: `step1000_source` does not rewrite on a cache
hit, so the 20 old slugs genuinely re-derived their source brief at 16:51 while their
scripts date from 16:14. Under the old code a `--until 8000` run silently accepted all of
it. Under the new code the same command will regenerate those scripts (sonnet), re-judge
(opus), and cascade. That is correct behaviour and it is what "fix the staleness" means,
but it is a real bill, it is loud rather than silent, and it is your call whether to spend
it. I did not spend it and did not suppress it.

## Deliberately left alone (the live pass owns them)

- `audit-trail`: 9 stale localized teasers. It is the in-flight slug and `./media.sh
  teaser` correctly refuses it. With the fix in place they rebuild by themselves on any
  later `--localize` of that slug, because its mains are now newer than its sentinels.
- `ai-pentesting`: already clean, its teasers were rebuilt at 07:10 to 07:15.
- I edited no `.sh` and did not touch `video_pipeline/run.sh`.

## Also found, not owned

- `pipeline/main.py` cannot be imported at all: `pipeline/steps/strategy.py:8` imports
  `claude_code_sdk` (the old SDK name; every other pipeline uses `claude_agent_sdk`).
  Pre-existing, unrelated to this work, and it means that pipeline is currently unrunnable.
  Verified by `py_compile` passing on every file I touched there while the import fails on
  that line.
- Five of the six pipelines' own `.venv`s lack `anyio`, so only `video_pipeline/.venv` can
  actually import them. I ran every import check through that venv.
- The growth repo is linted by nothing: `ruff --config ruff.toml` reports 1726 pre-existing
  findings across these six pipelines. My new modules are clean apart from TC003, which is
  the house style throughout (every sibling file has it).

## Files changed

New:
- `/home/developer/console/private/growth/video_pipeline/artifact_cache.py`
- `/home/developer/console/private/growth/clarity_pipeline/artifact_cache.py`
- `/home/developer/console/private/growth/www_pipeline/artifact_cache.py`
- `/home/developer/console/private/growth/illustration_pipeline/artifact_cache.py`
- `/home/developer/console/private/growth/pipeline/artifact_cache.py`

Modified:
- `video_pipeline/`: `main.py`, `registry.py`, `publish.py`, `steps/step2000_script.py`,
  `step3000_quality.py`, `step3600_social.py`, `step3650_social_quality.py`,
  `step4000_voiceover.py`, `step5000_storyboard.py`, `step5500_stockvideo.py`,
  `step6000_render.py`, `step7000_visual_qa.py`, `step8000_teaser.py`, `step_translate.py`
- `clarity_pipeline/`: `main.py`, `registry.py`
- `www_pipeline/`: `main.py`, `registry.py`
- `illustration_pipeline/`: `main.py`, `registry.py`
- `pipeline/`: `main.py`, `registry.py`, `podcast_tts.py`, `steps/step1400_update_kb.py`
- `i18n_pipeline/`: `steps/step2000_naturalize.py`, `steps/step9000_apply.py`
