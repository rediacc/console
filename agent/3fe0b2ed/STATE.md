## SESSION 3fe0b2ed 2026-08-18T19:51:30Z

# Session 3fe0b2ed

## Task
Operator reported Arabic in generated tutorial thumbnails rendering letter-by-letter instead of
joined. Root-caused, fixed, gated. Operator then EXPLICITLY AUTHORISED the R2 publish
("its not. you must publish it"), overriding an earlier door:operator-only close.

## Next action
Work is IN FLIGHT; do not restart anything. State at 19:51Z: main sweep 43/51 (0 fail), ko 9/18;
zh publish 16/17; ar fully published.
1. Wait for "=== ALL DONE" in scratchpad/arabic/render-all.out (monitor b6ericbli reports it).
2. Wait for bg b8uubpdvo: re-render of zh then ko tutorial-backup-restore, running SEQUENTIALLY.
3. RE-RENDER tutorial-add-server for ar, zh AND ko. The sweep SKIPPED it in all three and its
   mp4s predate the final card-fonts.ts, so it is the only pair not provably current.
4. Publish, sequentially, with scratchpad/arabic/publish-lang.sh <lang> <tutorial>...:
   - ko: all 18
   - zh: tutorial-backup-restore AGAIN (it went out with bad captions before the re-align)
   - add-server for ar, zh, ko
5. Purge: .ci/scripts/deploy/purge-media-cache.sh (CF_GLOBAL_API_KEY + CF_EMAIL in
   private/account/.env).
6. Verify CDN-side, never by exit code: fetch a words.json and diff vs local; pull an ar poster
   and actually look at it.

## DO NOT PURGE UNTIL STEP 5 - the stale cache is a live diagnostic
The un-purged CDN still serves pre-fix files. That is the ONLY reason the caption regression
below was caught. Purging destroys the comparison permanently.

## Caption defect: found, swept, fixed (#2d2f8b85 ticked, #6b489ba2 in flight)
tutorial-backup-restore had been re-narrated by an earlier session WITHOUT --subtitle, so its
timeline carried zero ASR alignment and renders emitted the evenly-distributed estimate.
Measured across all 13 locales: ar was 61/61 flat, zh 58/60, ko 50/52; everything else 0-10%.
et is 91% flat and that is CORRECT - no forced aligner exists for Estonian, it is exempt.
ar: fixed, re-rendered, re-published, now 5/39 flat (better than the 6/31 that was live before).
zh+ko: re-aligned (timelines now 16 real runs, 0 flat), re-rendering under bg b8uubpdvo, still
need re-publishing.
Recipe if another pair shows it:
  cd private/generative && PYTHONPATH=src .venv/bin/python -m tutorial_tts.cli \
    --repo-root /home/muhammed/monorepo/console --lang <l> --cast <t> --subtitle --resubtitle
  Dry-run FIRST; it must say "Generated clips: 0", otherwise it would re-synthesise the audio.
  Then re-render that pair, then re-publish it.

## Publish mechanics already de-risked
- Per-pair publisher: packages/www/scripts/publish-tutorial-video-to-r2.ts --cast X --lang Y.
- NEVER run generate-video-manifest.ts: whole-tree SCAN, most media gitignored, drops locales.
- Publishes MUST be sequential: update-video-manifest.ts:113/119 is an unsynchronised
  readFileSync/writeFileSync, no lock.
- Renders: lang-major, and NEVER the same tutorial in two languages at once (browser-segment
  cache key omits language).
- ar verified at origin: list-objects-v2 showed 85 objects dated 2026-08-18 vs 5 old.

## Code state: uncommitted, partly UNTRACKED
Fix = packages/www/scripts/lib/scenes/card-fonts.ts + svg-render.ts + slide.ts + the two
_template card SVGs + vendored scripts/assets/fonts/. Plus gate check:ci-tutorial-card-fonts and
a reggate probe fix in .claude/hooks/stop/wl_reggate.py. card-fonts.ts, the gate script and the
fonts dir are UNTRACKED while their wiring (package.json:157, ci-runner/manifest.ts:1801,
ci-quality.yml:747) is TRACKED - committing wiring alone points CI at a missing script.
1061 dirty paths in this shared tree; only ~13 are mine. Never stage broadly.

## Remaining
- [>] #f7b80380 sweep -> add-server -> publish ko -> purge -> verify
- [>] #6b489ba2 zh+ko backup-restore re-render -> re-publish
