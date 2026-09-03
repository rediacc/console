## SESSION 74de73ca 2026-09-03T15:59:59Z

Branch `0903-1`, PR #585, epic `24c98380`. **PUSHED** through `652233865`; renet submodule
through `6c85007` (its PR is rediacc/renet#110, same branch). Tree CLEAN. `ci:quick`
292/292 exit 0 on the committed tree.

## Where CI stands

Run for `652233865` is IN PROGRESS, watched by bg `b1fa3s1z9` (`ci-trace.py --wait`).
The run for `d7ffdbfd` shows CANCELLED because this push superseded it -- it was not a
failure, and its two reds were fixed before the supersession.

**No cycle has been green yet on this branch.** Six distinct reds have been diagnosed and
fixed, in this order, and each one's cause was NOT what its error named:
`4e74eba82` format-scope mis-tiered · `04dfbe4a7` sm-action's one-shot download killing
`Initialize` · `8fbf15c73` check:i18n truncating history with `git fetch --depth=50` ·
`dd2b2633e`/`d7ffdbfda` renet's go directive 6 patches behind the Dockerfile ·
`dad3748d3` two `qs` advisories in PRODUCTION deps · `652233865` age-check reading
suppression ages off a graft, plus my own new gate's fixture passing vacuously in CI.

If the next cycle is red, expect a NEW cause rather than a regression of one of those.

## Live facts a fresh session would get wrong

- **This checkout is now UNSHALLOWED** (2466 commits). It was shallow, and several gates
  answer differently on the two -- `check:ci-plan-housekeeping` defers rather than
  verdicts, and `check:ci-go-deps` cannot see real suppression ages. Do not re-shallow it.
- **`check:ci-format-scope` and `gate-test:fetch-depth-safety` are `slow: true`**, so
  `ci:quick` runs 292 gates, not 294. Run those two directly when touching them.
- **Fixture git repos must pin `--initial-branch=main` on BOTH inits plus an explicit
  `symbolic-ref`.** The CI runner's `init.defaultBranch` is not this machine's.
- `gh pr edit --body` is hook-blocked and `--body-file` hits a Projects-classic GraphQL
  deprecation. Working form:
  `gh api repos/rediacc/console/pulls/585 -X PATCH -F body=@file`.
- Lockfile changes need `npx -y npm@10` (CI pins 10; npm 11 rewrites 27 dev markers), and
  an `overrides` edit needs `npm update <pkg> --package-lock-only` -- plain
  `install --package-lock-only` answers "up to date" because this lockfile's root carries
  no `overrides` key.

## Next action

1. **`[?] #13d281a2`** -- org-secret cutover, and its precondition is ONE GREEN CYCLE.
   When `652233865` is green: `scripts/dev/derive-shadow-pass-list.sh --branch 0903-1`,
   then run exactly the `gh secret delete` lines it prints -- four, unchanged across every
   re-derivation so far (ACCOUNT_ED25519_PUBLIC_KEY, APP_PRIVATE_KEY, CLOUDFLARE_API_TOKEN,
   DOCKERHUB_TOKEN). No more than it names.
2. **`[?] #475f728c`** -- operator-only. A live 56-char Pexels key is hardcoded at
   `private/growth/video_pipeline/pexels_lib.py:22`. Nothing is published today. Never
   print the value, and do NOT delete the line without the rotation: it is in that repo's
   history from `64167a5`, so deletion buys nothing and breaks a documented fallback.
3. Read a failing JOB's conclusion, never the run's. A cancelled run did not report.
