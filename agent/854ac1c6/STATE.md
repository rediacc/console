## SESSION 854ac1c6 2026-08-26T04:50:35Z

## Where things stand

Branch **`0826-1`**, open draft **PR #576**, 17 commits, all pushed. PR #575 was
closed as superseded (filed on 08-26 from a branch dated 0825). #574 merged
earlier as `b4b5797e`; `main` green, its `bump-none` release SKIP confirmed from
the Finalize Release Sentinel log. GitLab mirror: operator pushed it, DONE.

The operator said **"implement everything go ahead. no blockers now."** Most of
it is now done.

## Landed on this branch

- ci-trace reads a PR-less branch (`--ref main` used to answer `no-verdict`).
- Gates: **A9** + **A10** on `check-toolchain-pins`, **`check:ci-devbox-exec`**,
  **`check:ci-shell-size`**, plus gate tests for the two housekeeping phases.
- `toolchain_pin_for` returning `""` with rc 0; `devbox_exec` dying wherever
  docker needs sudo; the Stop hook not seeing a gate committed in the same stop.
- **`block-stale-pr-branch-date.sh`** -- a PR must not be filed from a
  stale-dated branch. 5 cases in `test-hooks.sh`; suite **PASS=1268 FAIL=0**.
- **Phase 5b**: reaps orphaned `pr-N` preview Workers. FAILS CLOSED (unlike
  Phase 4, deliberately -- its worst case is deleting a LIVE preview).
- **Phase 1**: Phase 10 could never reach the watchdog (newest-1,000 window
  spans 18d vs 30d retention -> deleted ZERO nightly while reporting success).
  Per-workflow retention keyed by PATH + a warning when a window cannot reach
  its own threshold.
- **Phase 2**: `retry-failed-runs.sh` + a job in `housekeeping.yml`, running
  BEFORE the cleanups. Live dry-run: `considered=100 excluded=96 too-old=4
  retried=0`.

Design record is current: `docs/ci-overhaul/06-progress.md` and
`agent/PLAN-nightly-retry-and-watchdog-noise.md`.

## Next action

1. **Phase 3a** -- the only unstarted piece. `watchdog-monitor.yml` calls
   `core.setFailed()` when it has worked correctly (it cancels the CI run it
   monitors, then signals that), which is why 63 of 64 failures repo-wide are
   noise. Change the RUN NAME so a by-design failure reads as one, e.g.
   `Watchdog: run <id> (gen N) -- pipeline cancelled as designed`.
   **Consumer grep already done and clean**: `autopilot.yml:261` reads watchdog
   runs by status but only uses `display_title`; `ci-trace.py` and
   `nightly-status.yml` read the CI run, not the watchdog run. The exit-0
   variant (3b) is a SEPARATE landing -- do not bundle it.
2. Watch PR #576's CI with `.ci/scripts/ci/ci-trace.py --wait` (background).
3. Everything rides #576. Do NOT open a second PR.

## Open, needs the operator

Nothing can prove no long-lived Worker matches `^pr-[0-9]+$` without a live
Cloudflare listing; this session has no CF credentials. Stated in the gate's own
output, so it is not silently assumed.

**Do not push to `main`. Do not dispatch a release.**
