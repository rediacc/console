# Wave 3 parts A, B, D: video fleet surgery

Writer agent, `clarity-round6`. Everything below is inside
`/home/developer/console/private/growth/video_pipeline/`. Nothing outside that tree was
touched. Nothing was rendered, narrated, published or committed.

## What exists on disk now (counts of files, not stages)

    546 processing JSON artifacts rewritten   (273 x 2000_script*.json, 273 x 5000_storyboard*.json)
     19 source/prompt/doc files modified
      2 files deleted                          (remotion/src/scenes/Cta.tsx, TerminalType.tsx)
      3 files created                          (BrandOutro.tsx, assets/brand/logo.png, assets/brand/README.md)

`git status --short private/growth/video_pipeline/` lists 546 modified `processing/*.json`
plus these 21:

    M CONTRACT.md
    M config.py
    M prompts/quality_review.py
    M prompts/script.py
    M prompts/stock_select.py
    M prompts/storyboard.py
    M prompts/translate.py
    M prompts/visual_comprehension.py
    M remotion/src/Root.tsx
    M remotion/src/Scene.tsx
    M remotion/src/SolutionVideo.tsx
    M remotion/src/props.ts
    D remotion/src/scenes/Cta.tsx
    D remotion/src/scenes/TerminalType.tsx
    M steps/step4000_voiceover.py
    M steps/step6000_render.py
    M steps/step7000_visual_qa.py
    M steps/step8000_teaser.py
    M tts_bridge.py
    ?? assets/brand/                          (logo.png + README.md)
    ?? remotion/src/components/BrandOutro.tsx

A byte-exact snapshot of all 546 artifacts was taken before any edit and is still at
`/tmp/claude-1000/-home-developer-console/e580532b-53bf-4b76-92d8-b15b242c96d5/scratchpad/snapshot-before/`.
It was used once, to restore and re-run after the first pass got a derived field wrong.

## Part A + B: the scene cut

### Per slug (English side; the same ids were cut in all 13 locales)

| slug | scenes | cta | terminal | words | storyboard seconds |
|---|---|---|---|---|---|
| ai-pentesting | 24 -> 21 | 3 | 0 | 132 -> 116 | 69.4 -> 62.1 |
| audit-trail | 24 -> 21 | 3 | 0 | 131 -> 116 | 71.5 -> 65.0 |
| backup-verification | 23 -> 20 | 3 | 0 | 125 -> 110 | 63.4 -> 57.0 |
| cloud-outage-protection | 25 -> 20 | 4 | 1 | 125 -> 105 | 69.0 -> 58.0 |
| continuous-security-testing | 23 -> 18 | 4 | 1 | 129 -> 105 | 66.3 -> 53.5 |
| data-sovereignty | 22 -> 18 | 3 | 1 | 125 -> 106 | 62.5 -> 53.5 |
| encryption | 25 -> 19 | 3 | 3 | 134 -> 100 | 73.0 -> 53.4 |
| environment-cloning | 25 -> 21 | 3 | 1 | 128 -> 112 | 67.6 -> 58.6 |
| failover-testing | 24 -> 20 | 3 | 1 | 128 -> 112 | 64.1 -> 55.6 |
| immutable-backups | 24 -> 20 | 3 | 1 | 131 -> 115 | 67.2 -> 57.5 |
| infrastructure-costs | 26 -> 21 | 4 | 1 | 115 -> 92 | 51.2 -> 41.9 |
| instant-recovery | 25 -> 20 | 4 | 1 | 120 -> 100 | 70.3 -> 57.3 |
| integrations | 22 -> 18 | 3 | 1 | 131 -> 109 | 71.9 -> 58.4 |
| kubernetes-cluster-mobility | 24 -> 21 | 3 | 0 | 130 -> 114 | 66.8 -> 61.3 |
| migration-safety | 23 -> 19 | 3 | 1 | 119 -> 102 | 62.9 -> 52.2 |
| production-parity | 25 -> 20 | 4 | 1 | 135 -> 109 | 73.6 -> 60.3 |
| rapid-recovery | 24 -> 20 | 3 | 1 | 132 -> 114 | 65.4 -> 56.1 |
| retention-compliance | 25 -> 21 | 4 | 0 | 132 -> 113 | 70.9 -> 62.5 |
| safe-os-testing | 25 -> 22 | 3 | 0 | 133 -> 117 | 72.3 -> 66.0 |
| vendor-lock-in | 24 -> 20 | 3 | 1 | 134 -> 115 | 72.2 -> 61.4 |
| vulnerability-management | 22 -> 20 | 2 | 0 | 148 -> 134 | 42.5 -> 38.8 |

English totals: **504 -> 420 scenes**, 68 cta and 16 terminal-only (2 of the 18
terminalType scenes were themselves cta scenes, so they are counted in the cta column:
`infrastructure-costs` 24 and `production-parity` 23).

Across all 13 locales: **2162 scene records removed** (1083 from scripts, 1079 from
storyboards; the 4 extra script removals are the vulnerability-management mismatch below).
Storyboard-declared runtime for the 21 English videos drops **1394.1s -> 1190.3s, minus
203.8s / 14.6%**. Post-cut scripts run 18 to 22 scenes and 92 to 134 words.

### How removal was decided

Per file, from the file's own contents, never from a hardcoded id list: a scene is cut if
its `scene_type` is `cta`, or if its storyboard `visual.params.template` is `terminalType`.
The storyboard's terminalType ids are applied to the same-language script only when the two
files describe the same scene set (they must be cut together, because `step6000` joins
storyboard scenes to `4000_voiceover` timings by id and a scene present in one and not the
other leaves an uncovered window).

Storyboard `start` values were recomputed to close the holes: each kept scene keeps its
`duration` and the gap that originally followed it, and the new last scene's trailing gap is
dropped so the file satisfies `last.start + last.duration == total_seconds`, the same
invariant the real audio timeline carries. These numbers are decorative anyway,
`step6000_render.py:554` discards them and re-syncs from `4000_voiceover.json`, but leaving
holes in an artifact is how the next reader gets fooled.

`total_words` / `total_estimated_seconds` were recomputed from the narration for English.
Localized scripts mirror the English budget (measured: 264 of 273 files carried the English
`total_words` verbatim, and the only consumer is the quality judge, which judges English
only), so they were set to the new English values.

### Verification, with a control

`scratchpad/verify.py` compares all 546 files field by field against the snapshot rather
than re-checking only what the edit aimed at:

    files compared      : 546
    kept scenes checked : 10568
    scenes removed      : 2162
    kept-order intact   : 546
    sb starts moved     : 1767 (unchanged: 3485)
    ALL CHECKS PASS

It asserts: JSON parses; trailing-newline state preserved per file (scripts have one,
storyboards mostly do not, and that split was preserved); top-level key set unchanged; every
top-level value unchanged except the derived ones; every kept scene's key set unchanged;
every kept-scene field byte-identical except storyboard `start`; kept scenes not reordered;
no `cta` and no `terminalType` survives; storyboard scenes tile with no overlap, start at 0,
and end exactly at `total_seconds`.

**Control planted:** a copy of the snapshot was corrupted in three ways (a top-level `fps`
change, a kept scene's `narration` changed, two kept scenes reordered) and the verifier
reported exactly those three and nothing else. The clean run is therefore not a vacuous
pass.

Independent greps confirm 0 files under `processing/*/` still contain
`"scene_type": "cta"` or `terminalType`. Three `_baseline_v1/` archive files still do; those
are historical snapshots the glob deliberately never walked.

### terminalType: what I did NOT delete, and why

**`cast_terminal.py`, `CATEGORY_CAST` and `facts.terminal_real` all stay.** Deleting them
would have been the wrong call, and the evidence is specific:

1. All 9 `.cast` files in `CATEGORY_CAST` still resolve under
   `packages/www/public/assets/tutorials/`.
2. Running the extractor **today** returns valid current-CLI syntax:
   `rdc repo fork my-app --tag experiment --up`, `rdc repo secret list my-app`,
   `rdc repo push my-app --to machine-12`. Positional refs, mandatory `--tag` present.
3. So the extractor is correct and the CASTS have already been re-recorded. What is stale is
   the cached `processing/*/1000_source.json`, which still holds the pre-positional-ref
   extraction (`rdc repo secret set --name my-app --key DB_HOST ...`). `step1000_source.py:182`
   skips when its output exists, so the refresh never happened.

I also measured how the 18 invalid commands got there, because the answer is not what the
brief assumed:

    13 of 18 were VERBATIM from facts.terminal_real  (grounding rule obeyed, source stale)
     5 of 18 were INVENTED, not in terminal_real at all:
        encryption 12          rdc keygen production
        infrastructure-costs 13/24  rdc repo fork production      (terminal_real is EMPTY for this slug)
        instant-recovery 12    rdc repo push --name my-app -m machine-11 --to my-storage
        migration-safety 11    rdc repo sync push-all

`prompts/storyboard.py` carried a HARD RULE that terminalType must be verbatim from
`facts.terminal_real` and must not be used at all when that field is empty. It was violated
five times, twice on a slug where the field is empty. So the template had two independent
failure modes, a stale source and an unenforced grounding rule, and removing the template
closes both.

Because `terminal_real` no longer feeds any template, I wired its surviving purpose in
explicitly rather than leaving it as a claim: `prompts/script.py` now names it in the
FACTUAL ACCURACY section as evidence that a capability exists, with the caveat that it must
never be narrated and that its syntax is not current. Same caveat in `config.py:64` and
`CONTRACT.md`.

### A2, the ending

The final proof beat is untouched in the data. The brand hold is derived at render time so
there is nothing per-slug to drift:

- `step6000_render.py` sets `brandOutroFromSeconds` on the last scene (scene-local seconds,
  equal to its pre-extension duration) at the same place it applies `END_HOLD_SECONDS`.
- `remotion/src/components/BrandOutro.tsx` (new) dissolves to the white Rediacc wordmark on
  the brand ground across that tail, with an ambient breath so the last frame is not frozen.
  No text of any kind.
- `SolutionVideo.tsx` mounts it inside the scene's Sequence and fades the corner logo bug out
  over the same window, so the frame never carries two marks.

`assets/brand/logo.png` is new and vendored deliberately. The mark was previously staged
best-effort from `<repo>/bin/assets/logo_white-*.png`, **which does not exist in this
checkout**; the only surviving copy was the untracked `remotion/public/brand/logo.png`, and
`remotion/public/` is gitignored. That was survivable when the mark was a 0.55-opacity corner
bug. It is not survivable now that it is the closing frame, so `step6000` hard-fails without
it, the same way the Arabic font staging does.

## Part D: the 1.5 second lead hold

`LEAD_HOLD_SECONDS = 1.5` in `config.py`, beside `END_HOLD_SECONDS` and `SCENE_HOLD_S`.

**Option 2 as instructed: the silence is prepended to the mastered waveform in
`tts_bridge.py` phase C, before `_assert_timeline_sane` runs.** Scene 1 keeps `start == 0`
and absorbs the lead into its **duration**, which is what makes the hold show the first
scene's visual rather than black. Every later scene start, every segment start and every
absolute word timing shifts by exactly the sample-exact lead. The `<Audio>` element keeps its
frame-0 anchor, so the `SolutionVideo.tsx:10` comment saying it is never moved is still true
and needed no edit.

Plumbing: `tts_bridge` gains `--lead` (default 1.5, standalone fallback only);
`step4000_voiceover` passes `str(LEAD_HOLD_SECONDS)`; `timing.json` and
`4000_voiceover.json` both record `lead_hold_seconds` as the value actually applied.

**Cache key.** `step4000`'s resume guard now requires `lead_hold_seconds` to match as well as
`engine`. This is the mechanism that makes the whole wave land: audio narrated before the
lead existed has a plausible duration, a valid timeline and a zero exit code, and nothing
else on disk says it is wrong. All 273 existing `4000_voiceover*.json` now fail the guard and
will re-narrate, which is required anyway because scenes were removed.

### Verified with a structural probe and two controls

`scratchpad/probe/lead_probe.py` drives the real `tts_bridge._run` with a fake engine and a
deliberately failing aligner (no GPU, no models), twice: `--lead 0` and `--lead 1.5`.

    PASS  control run records lead_hold_seconds=0.0
    PASS  lead run records lead_hold_seconds=1.5
    PASS  scene 1 still starts at 0
    PASS  scene 1 duration absorbs the lead
    PASS  every later scene start shifts by exactly the lead
    PASS  no later scene duration changed
    PASS  every segment start shifts by exactly the lead (segment 0 included)
    PASS  total_seconds grows by exactly the lead
    PASS  last scene start+duration == total_seconds (the sample-exact invariant)
    PASS  same word count, and there are words
    PASS  every word timing shifts by the lead
    PASS  no caption word lands inside the hold
    PASS  the mastered waveform really is that long
    PASS  CONTROL: the no-lead run puts its first word inside the hold window

`_assert_timeline_sane` runs inside both, so it also passed. **Second control:** the naive
implementation (lead added to scene 0's `start` instead of its `duration`) was fed to
`_assert_timeline_sane` directly and was rejected with `first scene must start at 0`, which
proves that guard is live on this path rather than vacuous.

### The gate collision, fixed

`steps/step7000_visual_qa.py` forced samples are now
`[LEAD_HOLD_SECONDS + 0.5, LEAD_HOLD_SECONDS + 1.5]`, tied to the constant, with a comment
naming the failure they avoid.

**I found a second half of the same collision and fixed it in the same change.** Those two
offsets were not the only samples aimed at the wrong frames. The remaining timestamps are
scene midpoints read from `5000_storyboard.json`, and `step6000` renders **audio-true**: it
discards the storyboard's timing and joins `4000_voiceover.json` by id. So every midpoint
sample was already aimed at a frame the render never had, and the lead hold would have made
that error systematically 1.5s on every scene. `step7000` now performs the same id-keyed join
against `4000_voiceover.json` (storyboard as fallback) and takes `total_s` from the voiceover
plus `END_HOLD_SECONDS`.

`prompts/visual_comprehension.py`'s `hook_punch` rubric now states that the sampler already
skips the hold, and forbids dispatching a storyboard fix that asks for the lead-in to be
removed.

### A third collision I found and fixed: the teaser

`step8000_teaser.py` cut the first 11 seconds of the video. With the lead hold that is 1.5
seconds of a still frame at the front of a 11 second teaser, which is the exact opposite of
what a teaser is for. It now starts at `LEAD_HOLD_SECONDS` (`ffmpeg -ss`) and records
`start_seconds` in `8000_teaser.json`. Its docstring also claimed the teaser was "the hook
plus the closing CTA"; it never was, it only ever took the opening, and the CTA no longer
exists. Corrected.

## Authoring side, so a future run cannot re-add any of it

- **`config.py`**: `LEAD_HOLD_SECONDS = 1.5` added. `MIN_SCENE_COUNT` **16 -> 15**. The
  emotional-colour comment and the `END_HOLD_SECONDS` comment no longer mention cta. The
  `CATEGORY_CAST` block explains what `terminal_real` is still for and what it must never be
  used for.
- **`prompts/script.py`**: scene_type enum loses `cta`; scene band 18-22 -> **17-21**, minimum
  16 -> **15**; word budget 130-148 -> **112-130**; the arc is FOUR acts and the "Beats 22-26
  (cta)" line is gone; a new section **"THERE IS NO CLOSING ASK. THE VIDEO ENDS ON PROOF"**
  bans trial offers, prices, free tiers, URLs and try/start/sign-up/download instructions by
  name, states that the renderer signs off on the brand mark, and tells the writer that beat 1
  is held in silence before the first word; self-check item 10b added; the cta references at
  the old :72, :194, :240, :265, :278, :299 all reworked.
- **`prompts/quality_review.py`**: PASS 1 gains item 8, a closing ask is a **critical**
  anti-slop failure. PASS 6 budget note 130-148 -> 112-130. PASS 7 `scene_count >= 16` ->
  `>= 15` with matching fix text. PASS 9 (d) is four acts and a new (e) makes a `cta`
  scene_type a critical failure. **PASS 11 `arc_impact` reframed**: it judged "does the ending
  make them WANT it", which with no cta beat would have dispatched script fixes asking for the
  cta back, one slug at a time. It now judges RESOLUTION (does the last beat land the payoff
  and close the tension the hook opened) and explicitly forbids dispatching a fix that asks
  for a call to action.
- **`prompts/storyboard.py`**: both templates removed from the vocabulary and replaced by a
  named section explaining why, with the invalid commands quoted, so a future model does not
  reach for a template that no longer exists. Variety rule 3 ("the LAST scene must ALWAYS be
  cta") becomes "the last scene is a proof beat, do not build a closing card, the renderer
  signs off for you". Rule 4 no longer requires a terminalType. Rules renumbered. Scene-count
  context 14-18 -> 15-21. Checklist items 3 and 10 rewritten. Every incidental terminal
  reference in the caption-dedup exemption lists cleaned up.
- **`prompts/translate.py`**: the `cta` field list and the `terminalType.lines[].cmd` /
  `cta.command` keep-exactly rule removed.
- **`prompts/stock_select.py`**: scene_type enum and the mood guidance.
- **`prompts/visual_comprehension.py`**: emotional-colour check loses cta; `hook_punch` gains
  the lead-hold note.
- **Remotion**: `Cta.tsx` and `TerminalType.tsx` deleted; `CtaParams`, `TerminalTypeParams`
  and the now-unused `TerminalLine` type removed from `props.ts`; `SceneType` loses `"cta"`;
  the dispatcher cases and imports removed from `Scene.tsx`; `Root.tsx` defaultProps rebuilt
  (scene 3 terminalType -> blockShare, scene 5 cta -> a proof beat carrying
  `brandOutroFromSeconds`). `props.ts` header documents both removals and the reason.
- **`CONTRACT.md`**: 2000_script section rewritten (four acts, 15-21 scenes, 112-130 words,
  MIN_SCENE_COUNT 15, the cta cut stated with its measured cost); 4000_voiceover section
  documents `lead_hold_seconds` and both offset consumers; storyboard template table loses two
  rows and gains a "removed templates and why" block plus `brandOutroFromSeconds`; emotional
  colour table loses the cta row.

### On `MIN_SCENE_COUNT`

I moved it 16 -> 15 rather than leaving it or scaling it by the 12 percent of beats that
left. The reasoning, recorded in the comment: the floor tracks the authoring band, which was
"target 18-22, minimum 16" and is now "target 17-21, minimum 15", so it keeps the same two
beats of slack. Measured, the post-cut fleet is 18 to 22 scenes, so 15 stays below every real
script and the gate keeps its meaning instead of silently becoming binding.

Note the constant is still **dead**: nothing reads it, exactly like `WORDS_PER_SECOND`. The
number that bites is the literal in `prompts/script.py` and in `prompts/quality_review.py`
PASS 7. I changed all three and said so in the comment; I did not add a runtime gate, which
would be a behaviour change beyond this brief.

## Verification summary

| what | result |
|---|---|
| 546 artifacts vs snapshot, whole-file field diff | ALL CHECKS PASS, control catches 3 planted defects |
| `tts_bridge` lead hold, real `_run` with fake engine | 14 assertions PASS, plus a control proving the no-lead run differs |
| `_assert_timeline_sane` on the naive lead implementation | rejected, `first scene must start at 0` |
| `tsc --noEmit` on the Remotion project | exit 0; control (a deliberate type error in BrandOutro) exits 2 |
| `@remotion/bundler` bundle of `src/index.ts` | exit 0; control (a valid root importing deleted `Cta`) fails with `Can't resolve './src/scenes/Cta'` |
| all 39 pipeline `.py` files parse; 31 of 32 modules import | the one failure is `main.py` against my crude SDK stub, not a code change |

**Not proven:** no frame was rendered. `~/.cache/remotion` has no `chrome-headless-shell`, so
even a single `renderStill` would trigger a ~150 MB browser download, which is not a side
effect I will take in a job whose brief says do not render. So the brand outro is verified to
typecheck, to bundle, and to be mounted with arithmetic I can read, but **nobody has looked at
the frame**. First eyes on it should be the Wave 7 render.

## Defects found, and what I did about each

### Inside my ownership, fixed in this change (all flagged above)

1. `step7000` scene-midpoint samples read storyboard timing that `step6000` discards. Fixed
   by joining `4000_voiceover` the same way the render does.
2. `step8000` teaser would have opened on 1.5s of held frame. Fixed with `-ss`.
3. The brand mark had no tracked source in this checkout and staging was best-effort. Vendored
   to `assets/brand/logo.png` and made a hard failure.
4. `step8000`'s docstring described a teaser it never produced.

### Inside my ownership, NOT fixed, needs a decision

**1. Two narration junctions lose a pronoun antecedent.** Cutting the terminalType scene
removes real narration, and in two of sixteen cases the following line depends on it:

    encryption   cut 12 "One command. Your key is generated."
                 now reads: "Look, there is a better way." | "Only you hold it."
    integrations cut 10 "One webhook line. That is it."
                 now reads: "This costs you days every month." | "Git push triggers it. Automatically."

In both, "it" now points at nothing. The other fourteen junctions read cleanly (I printed and
read all sixteen). I did not repair these because the repair is a one-clause narration edit
that has to land in 13 languages, which needs the translate path, not a writer agent editing
English into divergence. Two options, operator's call:
  (a) have the localize/translate step re-word `encryption` scene 13 and `integrations` scene
      11 in all 13 locales; or
  (b) keep those two scenes and only swap their template away from `terminalType`. That still
      removes the invalid CLI, which is the defect Part B exists to fix, and costs no
      translation. It is a deviation from "remove those scenes", which is why I did not take
      it unilaterally.
This must be settled before Wave 7 renders, not after.

**2. Every slug lost its literal TURN beat.** Thirteen of the sixteen terminalType scenes were
the narration `"One command."`, which is the beat `prompts/script.py` and
`prompts/quality_review.py` PASS 9 both call the required, identifiable turn, and which
`prompts/storyboard.py` builds a whole "THE TURN IS THE CLIMAX" section around. The turn now
falls to the first mechanism beat (`"Rediacc copies your live setup."`,
`"Rediacc monitors your primary, always."`), which still reads as a clear entrance in every
case I checked. Flagging it because it is a structural consequence, not a typo, and because a
future quality-loop run may score `flow_ok` on it.

**3. `vulnerability-management` is broken in a way this pass did not fix.** Its storyboards
are a stale 5-scene pre-v3 artifact **in all 13 locales**, while its scripts are the current
22-scene version in en/ar/et/tr and the stale 5-scene version in the other nine. `step6000`
joins by id, so for en/ar/et/tr it would give the 5 storyboard scenes the timings of
voiceover scenes 1 to 5 and leave roughly 50 seconds of narration with no visual. `config.py`
already calls this slug "a stale pre-v3 5-scene script that must never be used as a
baseline"; nothing says the storyboards are stale too. I cut each file on its own cta beats,
left the nine stale locales' `total_words` untouched rather than inventing a number
(whitespace tokens are meaningless for ja/zh anyway), and reported every mismatch. **This slug
needs a real regeneration before Wave 7, or it will render wrong in 13 languages.**

**4. Two slugs have zero stockVideo scenes.** `infrastructure-costs` and
`vulnerability-management`, in the English storyboard and therefore in all 13 locales. The
storyboard prompt says stockVideo is REQUIRED on 1 to 2 scenes. Pre-existing, not caused by
this cut (I verified no stockVideo scene was removed anywhere, and 19 of 21 slugs still have
exactly one, so the check is not vacuous).

**5. `facts.terminal_real` is stale in every cached `1000_source.json`.** Detailed above with
the proof. The fix is `rm processing/*/1000_source.json` before Wave 7 so `step1000`
re-extracts; it is deterministic Python with no agent and no token cost. I did not run it
because the brief says this job is direct edits, not step re-runs, and because with the
terminal template gone the stale data no longer reaches a screen.

**6. `CONTRACT.md` had drifted badly from the prompts before I touched it.** It claimed a
"HARD length cap: total narration <= 45s (~84 words)", "16-26 scenes", "<=7 words" per beat
and a "115-135 (hard cap 145)" word budget, while `prompts/script.py` said 80s, 18-22 scenes,
5-10 words and 130-148 words. I corrected the section to the new authoritative numbers, but
the class of defect (a contract file nothing validates against) is wider than the part I
rewrote.

**7. `prompts/script.py` contained its own internal contradiction**, "Target 18-22 scenes"
against a "20-26 MICRO-BEATS" arc header whose zones summed to 26. Resolved to a consistent
17-21 in both places as part of the rewrite.

### Deliberately left alone

- `prompts/social_post.py:46` still asks for "last slide a soft CTA". That is the LinkedIn
  carousel, a different surface. A2 was a decision about the video's final beat. Left as is,
  named here so it is not mistaken for an oversight.
- `MAX_VIDEO_SECONDS = 80` unchanged. It is a cap, not a target, and the videos got shorter.
- `processing/*/_baseline_v1/` archives still contain cta scenes and one terminalType
  storyboard. They are historical snapshots; the surgery never walked them.

## What Wave 7 must do before it renders

1. **Settle finding 1** (the two orphaned pronouns) and **finding 3** (vulnerability-management).
2. The 273 `4000_voiceover*.json` are stale on two counts (removed scenes, missing lead hold).
   `step4000`'s cache key handles this automatically; no manual deletion needed. Confirm by
   watching for the `Re-narrating <lang>: cached audio has lead_hold_seconds=<absent>` line.
3. **Delete `processing/*/6000_render*.json` first.** `step6000_render.py:436` returns the
   cached record whenever that file exists, so without deleting them the render step
   short-circuits and the fleet publishes the old mp4s with a clean exit code. Same for
   `7000_visual_qa.json` and `8000_teaser*.json` if those loops are wanted.
4. `processing/*/audio/**/timing.json` and `_scenes.json` still describe the old scene lists.
   They are rewritten by the narration run; nothing needs to be done, but do not read them as
   truth in the meantime.
5. Look at the brand outro on the first rendered pair. Nobody has seen a frame of it.
