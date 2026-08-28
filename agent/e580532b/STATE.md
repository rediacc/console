## SESSION e580532b 2026-08-28T07:11:27Z

# Session e580532b

`clarity-round6` is DONE (`Status: done`, 19 rows). The 26 English mains are PUBLISHED and
live under `videos/solutions/en/` on `rediacc-www-media`, 78 objects, verified against the
bucket. All 26 English teasers regenerated and light.

## Running now, and it is the only work left

**Phase B, the 12 locales**: `scratchpad/full-pass.sh`, log `scratchpad/full-pass.log`,
items `1c8f1835` and `6086e2c4`. Slug 3 of 26 done, on `backup-verification`. **35
localized mains and 36 localized teasers written, 0 failures.** About a day remains.

Judge liveness by LOG MTIME and by shells whose `comm` is bash; the pid printed at launch
is the `setsid` parent and exits at once.

The remaining 23 slugs regenerate their own localized teasers unaided: the stale sentinels
were dropped and step 8000 now compares against its input rather than its own existence.

## The gates that guard this, and what a red one means

`private/growth/.ci/checks/check-cache-invalidation.sh` (sentinel never older than the mp4
it was cut from) and `check-no-direct-query.sh` (no SDK access outside a choke point, and
every choke point raises `max_buffer_size` to at least 10 MB). Both **GREEN**. Both run from
that repo's `.git/hooks/pre-commit` and as a startup preflight in each pipeline `main.py`.

**If cache-invalidation goes red, rebuild the slug it names, do not touch the gate.** It was
red on 11 findings until `audit-trail`'s teasers were rebuilt, and that was correct.

Console CI cannot host either: `private/growth` is a separate repo, gitignored at
`.gitignore:69`, 0 tracked files. `scripts/check-gate-manifest.ts` now refuses a manifest
leaf git does not track, so that mistake cannot land again.

## Use ./media.sh

    ./media.sh run <pipeline> [args...]
    ./media.sh teaser <slug> [lang...]   # sentinel drop AND rebuild in one step; refuses
                                         # the slug the live pass is on, and that refusal
                                         # is the wait signal
    ./media.sh luma <mp4>                # light is meanY ~210, pre-palette files 30-50

## Operator decisions on record, 2026-08-28

English mains published: authorized, DONE. Teaser plus 13-locale pass: authorized, in
flight.

`a6546337` `[?]` OPEN: publish the regenerated teasers and locales when the pass finishes?
DEFAULT: do NOT publish, leave them measured on disk and report the numbers. The 2026-08-28
authorization was scoped to the English mains only.

Stock footage: CLOSED, left as filmed, documented in `w10-scorecard.md` with a 1fps scan
(63 of 1683 seconds below Y=100, 3.7%). A gate asserting stock matches the palette would
contradict this decision; do not write one unless the operator reverses it.

## A command to treat as deliberate

`get_resume_step` is honest now, so **20 of 26 English slugs read as not-done** and the next
`--until 8000` would regenerate and re-judge their scripts, which sit behind published
videos. Use `--until 6000` for a render. See Rule 1d in `.claude/agents/media-pipeline.md`.

## Do not commit, and do not duplicate

The uncommitted `packages/www/src/i18n/translations` diff is MINE; peer 9d92d9b6 has asked
TWICE and only the operator authorizes a commit. That peer also owns the `wl_ci`
unreachable-CI-checks finding and `check:ci-renet`'s Go vulnerabilities. Leave both.

## Next action

1. Spot-measure a fresh localized mp4 and teaser every few slugs with `./media.sh luma`,
   and COUNT files under `processing/*/video/`. `find` here is bfs: use a LOCAL timestamp,
   since a `Z` suffix silently compares against UTC and returns nothing.
2. Re-run `check-cache-invalidation.sh` occasionally; a red names the slug needing
   `./media.sh teaser <slug>`.
3. Phase B is in flight on `worker:full-pass`; watch for the FIRST `!!!!` line rather than
   the end.
4. When the pass completes, measure the fleet and answer `a6546337` with the numbers.
