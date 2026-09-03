## SESSION 74de73ca 2026-09-03T18:58:08Z

Branch `0903-1`, PR #585, epic `24c98380`. **PUSHED** through `f1a1f55e1`; renet submodule
through `6c85007` (its PR is rediacc/renet#110). `ci:quick` 294/294 exit 0 on the committed
tree; the full gate battery is 128 passed, 0 failed (1462 assertions).

**This file is intentionally left UNCOMMITTED.** Every STATE refresh used to be pushed, and
each push cancels the in-flight cycle and restarts the clock on the one thing still
blocking. Four cycles went that way. Commit it with the next real change.

## Where CI stands

The cycle for `f1a1f55e1` is IN PROGRESS, watched by bg `b58ze2hbq`. **No cycle has been
green yet on this branch;** thirteen distinct reds fixed so far.

A run shown CANCELLED is usually SUPERSEDED by a later push -- read the JOB conclusions,
never the run's. A `--wait` worker printing `head-moved:` was overtaken by my own push and
needs re-arming; that has happened four times.

**The pattern to carry: the error named the wrong subject every single time.** Disbelieve
the SUBJECT of a failure while believing its verdict, and look EARLIER in the job than the
step that failed. Narrative: `docs/ci-overhaul/06-progress.md`, "Wave 3".

## Live facts a fresh session would get wrong

- **The battery asserts it leaves no mark on the tree** (`run-all.sh` snapshots tracked
  files before/after). A gate test must work on a COPY; give the validator a path seam, as
  `check-devcontainer-pin-freshness.ts` takes `DEVCONTAINER_DOCKERFILE`. That guard shipped
  broken once: under `set -euo pipefail` a `grep` filtering everything out exits 1, so on a
  CLEAN checkout it aborted the battery before its first line. CI's tree is always clean.
- **Solution-page video players are DEFERRED on purpose**: those mounts carry
  `data-click-to-load` and render a server-side poster, so `.tvp-root video` is absent
  until clicked. Docs mounts still build immediately. A test asserting an immediate
  solution-page player asserts the OLD contract.
- **This checkout is UNSHALLOWED** (2466 commits) and must stay so; nothing may
  `git fetch --depth` without first asking `git rev-parse --is-shallow-repository`.
- **`ci:quick` runs 294 gates**; `check:ci-format-scope` and `gate-test:fetch-depth-safety`
  are `slow: true`, so run those two directly when touching them.
- **The push guard rejects a compound command containing `git push`** (it silently skips
  `ci:quick`), so use two Bash calls. `git commit --amend` is hook-blocked.
- **`devbox exec` splits args on whitespace**; **lockfile edits need `npx -y npm@10`** plus
  `npm update <pkg> --package-lock-only` for an overrides change; **no IPv6 egress here**,
  so use `curl -4` before judging a host unreachable.

## Operator instructions being held

- **"ignore pexels related"** -- the peer session that raised it was killed;
  `private/growth` is untouched and the item is closed. Do not reopen it.
- **GitHub `pr-N` deployments: BOTH halves DONE.** 25 empty environments deleted with
  `.ci/scripts/housekeeping/cleanup-pr-environments.sh` (operator-run; CI can never hold
  Administration:write), and `ci.yml`'s deploy-preview declares no `environment:`.
  Cloudflare-side publish and cleanup were deliberately left alone.

## Next action

1. **`[?] #13d281a2` is the ONLY open item.** Run
   `scripts/dev/derive-shadow-pass-list.sh --branch 0903-1` and execute exactly the
   `gh secret delete` lines it prints -- four, unchanged across every re-derivation
   (ACCOUNT_ED25519_PUBLIC_KEY, APP_PRIVATE_KEY, CLOUDFLARE_API_TOKEN, DOCKERHUB_TOKEN),
   no more. The script refuses unless a passing compare exists, so it is safe to run now
   and will say so if the green cycle has not landed.
2. Do not push bookkeeping-only commits while a cycle is in flight.
