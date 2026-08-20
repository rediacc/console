## SESSION 3fe0b2ed 2026-08-20T04:06:15Z

## Task

Plan ~/.claude/plans/let-s-make-a-plan-vast-cray.md: tutorial output exceeded the 107-column
recorded terminal and wrapped into unreadable rows. Fix at source, re-record 18 casts,
regenerate 234 pairs, publish to R2.

## THE ORIGINAL TASK IS DONE. PHASE 5 IS DONE. ONLY PUBLISH REMAINS.

Cast gate CLEAN: `node packages/www/scripts/validate-tutorial-cast-output.js` exits 0 over
18 recordings (was 24 violations).
Phase 5 COMPLETE at 04:02:14Z, exit 0: 234 of 234 mp4s rendered, no error lines.

Operator decisions already applied, do NOT re-ask:
- **Publishing to R2 is APPROVED.** Credentials in private/account/.env.
- **Leave everything UNCOMMITTED.** Chosen explicitly.
- fr/pt em dashes removed; Russian's 36 KEPT (copula dash, grammatically required).

## Live work

`blyk2kowl` is re-rendering the 15 pairs whose content actually changed: 9 en
(scratchpad/rerender-en.txt) plus fork-isolation / storage-management / vscode-browser in
fr and pt. Both re-narrations are already done and neither uploaded: en 12 clips, fr/pt 8
clips, each logging "skipping tutorial-audio cache upload".

## Next action

1. When `blyk2kowl` exits 0, PUBLISH. That is the last step:
   - `npm run tutorials:publish-video -w @rediacc/www -- --all` (1170 files, sequential)
   - verify `check:ci-locale-tutorial-assets` (it reads src/data/video-manifest.json, never
     the filesystem, so a missing entry is a 404 no local check would catch)
   - `.ci/scripts/deploy/purge-media-cache.sh` ONCE, at the end
   - `check:ci-tutorial-caption-sync` LAST (it fetches from media.rediacc.com and
     false-reds for the whole publish window)
   - NEVER run generate-video-manifest.ts: it rebuilds from a filesystem scan and drops
     every locale whose media is not checked out.
2. Report what actually landed with an `aws s3api list-objects-v2` listing, not an exit code.

## Hazards paid for tonight

- `www tutorials generate` UPLOADS to R2 when R2_MEDIA_* is set (restores first, uploads
  last). Every run was safe only because those vars are absent from this shell, which the
  logs state. After sourcing private/account/.env, use `www tutorials media` instead, which
  never restores or uploads.
- `list-tutorial-render-pairs --stale-only` reports ALL 234 stale because generate rewrites
  every timeline file. It is a MTIME artifact; acting on it re-renders ~220 identical pairs.
  git-vs-HEAD is equally useless (the sweep changed every marker timestamp). The honest
  signal is which mp3 files were regenerated.
- validate:tutorial-audio runs in the i18n job against R2-RESTORED audio, so publishing is a
  PRECONDITION for that gate, not a consequence.
- Do not undo with git here: `git checkout-index` on a planted control silently reverted
  fr/tutorial-forking.json to HEAD. Repaired with scaffold-locales, verified against en.

## Gates

Green: cast gate, CLI 2394/2394, eslint (FROM REPO ROOT), ci-parity, tutorial-parity,
shell-format, dead-bash, tutorial-commands, tutorial-noninteractive, healthcheck-headroom,
guard-mutations, em-dash surfaces, hook suite 773.

## Environment

REDIACC_ALLOW_GRAND_REPO=* is set here, needed for RECORDING only. Never run a recording in
the FOREGROUND (Bash caps at 10 min). Sleeps over 20s are hook-blocked.
