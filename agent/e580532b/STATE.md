## SESSION e580532b 2026-08-28T07:30:25Z

# Session e580532b

`clarity-round6` is DONE (`Status: done`, 19 rows). The 26 English mains are PUBLISHED and
live under `videos/solutions/en/` on `rediacc-www-media`, 78 objects, verified against the
bucket. All 26 English teasers regenerated and light.

## Running now, and it is the only work left

**Phase B, the 12 locales**: `scratchpad/full-pass.sh`, log `scratchpad/full-pass.log`,
items `1c8f1835` and `6086e2c4`. Slug 4 of 26 done, on `cloud-outage-protection`. **38
localized mains and 39 localized teasers, 0 failures.** About a day remains.

Judge liveness by LOG MTIME and by shells whose `comm` is bash; the launch pid is the
`setsid` parent and exits at once. Remaining slugs regenerate their own teasers unaided.

## Three gates guard tonight's fixes. All green.

- `check:ci-scans-tracked-paths` (console) - nothing CI executes lives under a gitignored
  path.
- `private/growth/.ci/checks/check-cache-invalidation.sh` - a `8000_teaser*.json` sentinel
  is never older than the mp4 it was cut from.
- `private/growth/.ci/checks/check-no-direct-query.sh` - nothing reaches the SDK outside a
  `sdk_utils.py::safe_query`, and every choke point raises `max_buffer_size` past 10 MB.

The two growth gates run from that repo's `.git/hooks/pre-commit` and a startup preflight
in each pipeline `main.py`. They cannot live in console CI: `private/growth` is a separate
repo, gitignored, 0 tracked files. Rationale in `private/growth/.ci/checks/README.md`.

**If cache-invalidation goes red, rebuild the slug it names. Do not touch the gate.**

## Use ./media.sh

    ./media.sh run <pipeline> [args...]
    ./media.sh teaser <slug> [lang...]   # sentinel drop AND rebuild in one step; refuses
                                         # the slug the live pass is on, which IS the wait
    ./media.sh luma <mp4>                # light is meanY ~210, pre-palette 30-50

## Operator decisions on record, 2026-08-28

English mains published: authorized, DONE. Teaser plus 13-locale pass: authorized, in
flight.

`a6546337` `[?]` OPEN: publish the regenerated teasers and locales when the pass finishes?
DEFAULT: do NOT publish; leave them measured on disk and report the numbers. The
authorization was scoped to the English mains only.

Stock footage: CLOSED, left as filmed, documented in `w10-scorecard.md` (63 of 1683
seconds below Y=100, 3.7%). A gate asserting stock matches the palette would CONTRADICT
this; do not write one unless the operator reverses it.

## A command to treat as deliberate

`get_resume_step` is honest now, so **20 of 26 English slugs read as not-done** and the
next `--until 8000` regenerates and re-judges scripts sitting behind published videos. Use
`--until 6000` for a render. Rule 1d in `.claude/agents/media-pipeline.md`.

## Peer 9d92d9b6, and what is NOT mine

They asked a third time to commit my work; I declined in
`agent/e580532b/NOTE-to-9d92d9b6.md`. Only the operator authorizes a commit; my paths are
finished and stable, so they may rebase on an authorization they hold themselves.

Theirs, do not duplicate: the `wl_ci` unreachable-checks finding, `check:ci-renet`'s Go
vulnerabilities, and `private/account/node_modules` ahead of its manifest, which makes a
local `check:deps` there a FALSE GREEN until reinstall.

`git add` in this shared worktree is not private: a peer's `git commit -F` takes the whole
INDEX, and that is how two of my staged files landed in their `449b95f09`.

## Next action

1. Spot-measure a fresh localized mp4 and teaser every few slugs with `./media.sh luma`,
   and COUNT files under `processing/*/video/`. `find` here is bfs: use a LOCAL timestamp,
   since a `Z` suffix silently compares against UTC and returns nothing.
2. Re-run `check-cache-invalidation.sh` occasionally; a red names the slug needing
   `./media.sh teaser <slug>`.
3. Watch `scratchpad/full-pass.log` for the FIRST `!!!!` line rather than the end.
4. When the pass completes, measure the fleet and answer `a6546337` with the numbers.
