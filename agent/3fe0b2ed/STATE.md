## SESSION 3fe0b2ed 2026-08-20T05:08:06Z

## Task

Plan ~/.claude/plans/let-s-make-a-plan-vast-cray.md: tutorial output exceeded the 107-column
recorded terminal and wrapped into unreadable rows. Fix at source, re-record 18 casts,
regenerate 234 pairs, publish to R2.

## THE WHOLE PLAN IS DONE AND PUBLISHED. One follow-up defect is being fixed.

- Cast gate CLEAN: validate-tutorial-cast-output.js exits 0 over 18 recordings (was 24).
- Phase 5 COMPLETE: 234/234 rendered, exit 0.
- **PUBLISHED to R2 (operator approved): 1170 files, 1170 manifest entries in one pass, 0
  failures.** Verified against the bucket itself, not an exit code: every locale holds 90
  objects (18 x 5), manifest is 18 tutorials x 13 locales x 5 fields,
  check:ci-locale-tutorial-assets PASSES, CDN purged ONCE, and a fetched words.json is
  byte-identical to local.
- Everything stays UNCOMMITTED. The operator chose that explicitly.

## Live work

`barut3ako` re-aligns tutorial-backup-restore captions in 8 locales (de en es fr it ja pt
tr): 42-76 FLAT cues each, evenly-distributed estimates instead of real ASR alignment.
Verified REAL, not the usual post-publish stale-cache false alarm, because the purge
happened first and the CDN was proven byte-identical.

## Next action

1. When `barut3ako` exits 0, re-publish ONLY that tutorial and purge once:
   `npm run tutorials:publish-video -w @rediacc/www -- --cast tutorial-backup-restore`
   then `.ci/scripts/deploy/purge-media-cache.sh`, then re-run
   `check:ci-tutorial-caption-sync`. Estonian is permanently exempt (no aligner); do not
   try to "fix" et.
2. If flat cues survive a second re-align, do NOT re-publish the same bytes again. The
   remedy is re-alignment, and a repeat means _align_into is failing for a reason worth
   reading in scratchpad/fix.generate.log.

## Hazards, all paid for tonight

- `www tutorials generate` calls www_tutorial_audio_restore FIRST and uploads LAST when
  R2_MEDIA_* is set. Keep those vars OUT of any shell that runs it; source
  private/account/.env only in a subshell scoped to a publish or purge.
- The AWS CLI inherits `eu-central-1` from ambient config; R2 needs `AWS_DEFAULT_REGION=auto`
  or `list-objects-v2` returns an EMPTY listing that looks like an empty bucket.
- `list-tutorial-render-pairs --stale-only` reports all 234 stale after any generate (mtime
  artifact). The honest signal for "what changed" is which mp3 files were regenerated.
- `find -newermt` takes LOCAL time while the drivers log UTC. That mismatch made a complete
  15-pair re-render look like 9.
- Six `tutorials/video/en/*.debug.json` objects in R2 date from 2026-07-01, are unreferenced
  by the manifest, and are NOT mine to delete.

## Gates

Green: cast gate, tutorial-parity, tutorial-card-fonts, validate:tutorial-audio,
locale-tutorial-assets, CLI 2394/2394, eslint (FROM REPO ROOT), ci-parity, shell-format,
dead-bash, tutorial-commands, tutorial-noninteractive, healthcheck-headroom,
guard-mutations, em-dash surfaces, hook suite 773.
Red: check:ci-tutorial-caption-sync, being fixed above.

## Environment

REDIACC_ALLOW_GRAND_REPO=* is set here, needed for RECORDING only. Sleeps over 20s are
hook-blocked; never run a recording in the FOREGROUND.
