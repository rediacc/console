## SESSION 74de73ca 2026-09-03T18:35:51Z

Branch `0903-1`, PR #585, epic `24c98380`. **PUSHED** through `da3744c31`; renet submodule
through `6c85007` (its PR is rediacc/renet#110, same branch). Tree CLEAN. `ci:quick`
294/294 exit 0 on the committed tree; the full gate battery is 128 passed, 0 failed
(1462 assertions).

## Where CI stands

The cycle for `da3744c31` is IN PROGRESS, watched by bg `b08tsdvh7`
(`ci-trace.py --wait`). **No cycle has been green yet on this branch.**

A run shown CANCELLED is usually SUPERSEDED by a later push, not failed -- read the JOB
conclusions, never the run's. Verified today: `affb53fa` had 0 failed jobs, `07c5e1c7`
had 1 (since fixed). A `--wait` worker that prints `head-moved:` was overtaken by my own
push and must be re-armed; that has happened three times.

**Twelve distinct reds diagnosed and fixed, and the pattern is the thing to carry: the
error named the wrong subject every single time.** If the next cycle is red, expect a new
cause, and disbelieve the SUBJECT of the message while believing its verdict. Full
narrative: `docs/ci-overhaul/06-progress.md`, "Wave 3".

## Live facts a fresh session would get wrong

- **This checkout is UNSHALLOWED** (2466 commits) and must stay so: `check:ci-plan-housekeeping`
  defers instead of verdicting on a truncated one, and `check:ci-go-deps` cannot see real
  suppression ages. Nothing may `git fetch --depth` without first asking
  `git rev-parse --is-shallow-repository`; `gate-test:fetch-depth-safety` enforces it.
- **The battery now fails if it leaves a tracked file modified** (`run-all.sh` snapshots
  before/after). A gate test must work on a COPY; give the validator a path seam, the way
  `check-devcontainer-pin-freshness.ts` takes `DEVCONTAINER_DOCKERFILE`.
- **Solution-page video players are DEFERRED on purpose**: those mounts carry
  `data-click-to-load` and render a server-side poster, so `.tvp-root video` is absent
  until the poster is clicked. Docs mounts still build immediately. A test asserting an
  immediate solution-page player is asserting the OLD contract.
- **`ci:quick` runs 294 gates**; `check:ci-format-scope` and `gate-test:fetch-depth-safety`
  are `slow: true` and deferred. Run those two directly when touching them.
- **The push guard rejects a compound command containing `git push`** -- it silently stops
  `ci:quick` running. Two separate Bash calls, always. `git commit --amend` is hook-blocked
  too; correct a bad commit with a NEW commit.
- **`./run.sh devbox exec` splits args on whitespace** (`bash -lc '...'` loses quoting);
  pass the command directly. **Lockfile edits need `npx -y npm@10`**, and an `overrides`
  change needs `npm update <pkg> --package-lock-only`. **This sandbox has NO IPv6 egress**,
  so use `curl -4` before concluding anything about a host's reachability.

## Operator instructions this session is holding

- **"ignore pexels related"** -- the peer session that raised it was killed.
  `private/growth` is untouched, the item is closed, do not reopen it.
- **GitHub `pr-N` deployments: BOTH halves are DONE.** 25 empty environments deleted with
  `.ci/scripts/housekeeping/cleanup-pr-environments.sh` (operator-run; CI can never hold
  Administration:write), and `ci.yml`'s deploy-preview no longer declares an
  `environment:`. Cloudflare-side publish and cleanup were deliberately left alone.

## Next action

1. **`[?] #13d281a2` is the ONLY open item**, and its precondition is ONE GREEN CYCLE.
   When `da3744c31` is green: `scripts/dev/derive-shadow-pass-list.sh --branch 0903-1`,
   then run exactly the `gh secret delete` lines it prints -- four, unchanged across every
   re-derivation (ACCOUNT_ED25519_PUBLIC_KEY, APP_PRIVATE_KEY, CLOUDFLARE_API_TOKEN,
   DOCKERHUB_TOKEN). No more than it names.
2. If CI is red, read the failing JOB's log and look EARLIER in the job than the step that
   failed.
