## SESSION 74de73ca 2026-09-03T16:29:06Z

Branch `0903-1`, PR #585, epic `24c98380`. **PUSHED** through `6cedf5f02`; renet submodule
through `6c85007` (its PR is rediacc/renet#110, same branch). Tree CLEAN. `ci:quick`
293/293 exit 0 on the committed tree.

## Where CI stands

Cycle for `6cedf5f02` is IN PROGRESS, watched by bg `b2opfcvbe` (`ci-trace.py --wait`).
A run shown CANCELLED on an older SHA was superseded by a push, not failed.

**No cycle has been green yet on this branch**, and eight distinct reds have been fixed.
Each one's cause was NOT what its error named, which is the pattern to expect from the
next one too:

`4e74eba82` format-scope mis-tiered · `04dfbe4a7` sm-action's one-shot download killing
`Initialize` (its cargo fallback could never work here) · `8fbf15c73` check:i18n
truncating history with `git fetch --depth=50` · `dd2b2633e`/`d7ffdbfda` renet's go
directive six patches behind the Dockerfile · `dad3748d3` two `qs` advisories in
PRODUCTION deps · `652233865` age-check reading suppression ages off a graft ·
`433925cca` bare fixtures with no branch pin · `6cedf5f02` `quality-security` using
`${PYYAML_VERSION}` with no step providing it (pip reported it, three steps later).

## Live facts a fresh session would get wrong

- **This checkout is UNSHALLOWED** (2466 commits) and must stay that way: several gates
  answer differently on a truncated one. `check:ci-plan-housekeeping` defers instead of
  verdicting, and `check:ci-go-deps` cannot see real suppression ages.
- **`ci:quick` runs 293 gates, not 295**: `check:ci-format-scope` and
  `gate-test:fetch-depth-safety` are `slow: true`. Run those two directly when touching
  them.
- **The push guard rejects a compound command containing `git push`** -- it silently stops
  `ci:quick` from running. Two separate Bash calls, always.
- **`./run.sh devbox exec` splits its args on whitespace**: `bash -lc '...'` loses the
  quoting. Pass the command directly (`devbox exec -- go -C <dir> mod tidy`).
- **Lockfile edits need `npx -y npm@10`** (CI pins 10), and an `overrides` change needs
  `npm update <pkg> --package-lock-only` -- plain `install --package-lock-only` answers
  "up to date" because this lockfile's root carries no `overrides` key.
- `gh pr edit --body` is hook-blocked; `--body-file` hits a Projects-classic GraphQL
  deprecation. Working form:
  `gh api repos/rediacc/console/pulls/585 -X PATCH -F body=@file`.

## Next action

1. **`[?] #13d281a2`** -- org-secret cutover, precondition ONE GREEN CYCLE. When
   `6cedf5f02` is green: `scripts/dev/derive-shadow-pass-list.sh --branch 0903-1`, then
   run exactly the `gh secret delete` lines it prints -- four, unchanged across every
   re-derivation (ACCOUNT_ED25519_PUBLIC_KEY, APP_PRIVATE_KEY, CLOUDFLARE_API_TOKEN,
   DOCKERHUB_TOKEN). No more than it names.
2. **`[?] #475f728c`** -- operator-only. A live 56-char Pexels key is hardcoded at
   `private/growth/video_pipeline/pexels_lib.py:22`. Nothing is published today. Never
   print the value, and do NOT delete the line without the rotation: it is in that repo's
   history from `64167a5`, so deletion buys nothing and breaks a documented fallback.
3. Read a failing JOB's conclusion, never the run's. A cancelled run did not report.
