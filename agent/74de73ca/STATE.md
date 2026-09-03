## SESSION 74de73ca 2026-09-03T17:57:26Z

Branch `0903-1`, PR #585, epic `24c98380`. **PUSHED** through `4f7f9dd59`; renet submodule
through `6c85007` (its PR is rediacc/renet#110, same branch). Tree CLEAN. `ci:quick`
294/294 exit 0 on the committed tree.

## Where CI stands

The cycle for `4f7f9dd59` is IN PROGRESS, watched by bg `byhty8d4b`
(`ci-trace.py --wait`). **No cycle has been green yet on this branch.**

Runs shown CANCELLED are usually SUPERSEDED by a later push, not failed -- check the
JOB conclusions, not the run's. Verified today: `affb53fa` had 0 failed jobs (my own
docs push superseded it), `07c5e1c7` had 1 (the external-links red, since fixed).

Eleven distinct reds have been diagnosed and fixed, and the pattern is the thing worth
carrying: **the error named the wrong subject every single time.** If the next cycle is
red, expect a new cause and disbelieve the subject of the message while believing its
verdict. The full narrative is `docs/ci-overhaul/06-progress.md`, "Wave 3".

## Live facts a fresh session would get wrong

- **This checkout is UNSHALLOWED** (2466 commits) and must stay so: `check:ci-plan-housekeeping`
  defers instead of verdicting on a truncated one, and `check:ci-go-deps` cannot see real
  suppression ages. Nothing in the tree may `git fetch --depth` without first asking
  `git rev-parse --is-shallow-repository` -- `gate-test:fetch-depth-safety` enforces it.
- **`ci:quick` runs 294 gates**; `check:ci-format-scope` and `gate-test:fetch-depth-safety`
  are `slow: true` and deferred. Run those two directly when touching them.
- **The push guard rejects a compound command containing `git push`** -- it silently stops
  `ci:quick` from running. Two separate Bash calls, always. `git commit --amend` is also
  hook-blocked; correct a bad commit with a NEW commit.
- **`./run.sh devbox exec` splits args on whitespace**: `bash -lc '...'` loses the quoting.
  Pass the command directly (`devbox exec -- go -C <dir> mod tidy`).
- **Lockfile edits need `npx -y npm@10`**, and an `overrides` change needs
  `npm update <pkg> --package-lock-only` -- plain `install --package-lock-only` answers
  "up to date" because this lockfile's root carries no `overrides` key.
- **This sandbox has NO IPv6 egress**, so a bare `curl` to a dual-stack host can answer
  000 for reasons that have nothing to do with the host. Use `curl -4` before concluding
  anything about reachability.
- `gh pr edit --body` is hook-blocked; `--body-file` hits a Projects-classic GraphQL
  deprecation. Working form:
  `gh api repos/rediacc/console/pulls/585 -X PATCH -F body=@file`.

## Operator instructions this session is holding

- **"ignore pexels related"** -- the operator killed the peer session that raised it.
  `private/growth` is untouched and that item is closed. Do not reopen it.
- **GitHub `pr-N` deployments: both halves are DONE.** 25 empty environments deleted with
  `.ci/scripts/housekeeping/cleanup-pr-environments.sh` (operator-run; CI can never hold
  Administration:write), and `ci.yml`'s deploy-preview no longer declares an
  `environment:`. Cloudflare-side publish and cleanup were deliberately left alone.

## Next action

1. **`[?] #13d281a2` is the ONLY open item**, and its precondition is ONE GREEN CYCLE.
   When `4f7f9dd59` is green: `scripts/dev/derive-shadow-pass-list.sh --branch 0903-1`,
   then run exactly the `gh secret delete` lines it prints -- four, unchanged across every
   re-derivation (ACCOUNT_ED25519_PUBLIC_KEY, APP_PRIVATE_KEY, CLOUDFLARE_API_TOKEN,
   DOCKERHUB_TOKEN). No more than it names.
2. If CI is red, read the failing JOB's log before concluding anything, and look EARLIER
   in the job than the step that failed.
