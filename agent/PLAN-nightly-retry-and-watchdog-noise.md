# PLAN: nightly retry for failed runs, and the watchdog noise underneath it
Status: draft
Owner: 854ac1c6
Updated: 2026-08-26

## What the operator asked

1. "We should have scheduled task for such retries for all failed ones, nightly."
2. "What about adding watchdog to the cleanup job as well?"

Both are answered below, and they turn out to be the **same root cause seen from
two ends**: `watchdog-monitor.yml` emits ~77 runs/day, most of which "fail" on
purpose. That volume simultaneously (a) drowns any retry sweeper in
false-positives and (b) outruns the run-cleanup that already exists.

## Measured baseline (do not re-derive; re-measure only if it looks stale)

Three days of `rediacc/console` workflow runs, 2026-08-23..26:

| conclusion | count |
|---|---|
| success | 589 |
| skipped | 230 |
| cancelled | 117 |
| failure | **64** |

- **63 of the 64 failures are `watchdog-monitor.yml`.** They fail BY DESIGN: the
  watchdog cancels the CI run it monitors, then `core.setFailed()`s itself to
  signal it. Log ends `##[error]PIPELINE CANCELLED: Job failed: "<job>"`.
- **Exactly one** genuine non-watchdog failure in three days.
- The **117 cancelled** are overwhelmingly superseded pushes.
- Watchdog totals: **2,011 runs**, **230 of the last 1,000 runs repo-wide (23%)**.

Load-bearing behaviour, verified live: **a rerun updates the run's conclusion IN
PLACE.** `Cleanup PR Preview` 32903006150 now reads `success attempt=2`;
`Console CI` 32903007256 reads `success attempt=3`. A sweeper keyed on
`conclusion=failure` therefore never re-touches a run that has since been fixed.

## Phase 1 — the watchdog is already in the cleanup, and cannot be reached

`cleanup_workflow_runs()` (`.ci/scripts/housekeeping/cleanup-versions.sh:1576`,
invoked at `:1908`, "Phase 10") already iterates **every active workflow**, so
`watchdog-monitor.yml` is nominally covered. It is structurally unreachable:

| knob | value | source |
|---|---|---|
| `GH_RUNS_MAX_PAGES_PER_WORKFLOW` | 10 (x100 = newest **1,000**) | `cleanup-versions.sh:89` |
| `GH_RUNS_RETENTION_DAYS` | **30** | `:84` |
| `GH_RUNS_KEEP_PER_WORKFLOW` | 100 | `:83` |

Watchdog run #1,000 was created **2026-08-08 — 18 days old**. Nothing inside the
reachable window is ever older than the 30-day threshold, so Phase 10 deletes
**zero** watchdog runs every night while reporting success. That is a vacuous
green in the housekeeping lane.

**Fix, smallest first — pick ONE, do not stack them:**

- **1a (preferred): per-workflow retention override.** A watchdog generation is
  pure telemetry; once the CI run it monitored is settled the generation has no
  audit value. A map keyed by workflow PATH (never display name --
  `Watchdog: run <id> (gen N)` is generated) with a short retention, e.g. 7 days,
  makes the newest-1,000 window sufficient by construction.
- **1b: raise the page cap for high-volume workflows only.** Works, but it is a
  treadmill: the cap must grow whenever run volume does, and nothing tells you it
  has fallen behind again -- the exact failure being fixed.
- **1c: enforce `KEEP_PER_WORKFLOW` independently of the age gate.** Simplest
  rule ("newest 100, delete the rest"), but it changes retention semantics for
  every workflow at once, so it is the largest blast radius of the three.

**Anti-vacuity requirement, non-negotiable:** whichever is chosen, Phase 10 must
FAIL, or at minimum warn loudly, when its scan window cannot reach the retention
threshold for any workflow. A cleanup that deletes nothing must never be
indistinguishable from a cleanup that had nothing to delete. That is what let
this sit unnoticed across 2,011 runs.

## Phase 2 — the nightly retry

**Home: a NEW JOB inside `.github/workflows/housekeeping.yml`.** Not a new
workflow, not the watchdog.

- already `cron: '0 3 * * *'` (`housekeeping.yml:18`), deliberately clear of
  ci.yml's `0 1` and promote-stable's `0 6`;
- its `housekeeping` app-token preset **already grants `actions: write`**
  (`.github/actions/app-token/action.yml:77-80`) -- exactly what
  `gh run rerun --failed` needs, so no new preset and no new secret surface;
- `.ci/scripts/housekeeping/` is the established home for the logic (four
  sibling scripts).

Rejected, with reasons: a separate `nightly-retry.yml` duplicates cron and token
wiring that already exists; extending `watchdog-monitor.yml` cannot work because
it is per-run `workflow_dispatch`, exits with its chain, and only ever knows
about Console CI (bootstrapped at `ci.yml:413`).

**The filters are the feature. Each one is load-bearing:**

1. `conclusion == "failure"` ONLY. **Never `cancelled`** -- that is the
   superseded shape, 117 of them in three days, and re-running one revives a
   dead commit's pipeline.
2. Exclude by workflow **PATH** `.github/workflows/watchdog-monitor.yml`.
   Excluding by display name is fragile because the name is generated per run.
   Without this, 63 of 64 candidates are deliberate failures.
3. **Live head only:** skip a run whose `head_sha` is no longer the tip of any
   branch or open PR. Same reason as (1), reached a different way.
4. **Attempt cap** (e.g. skip `run_attempt >= 3`), so a genuinely broken run is
   not retried every night forever.
5. **Age floor** (e.g. only runs from the last 24-48h), so the sweeper cannot
   reach back into history on its first execution.

Expected yield on the measured baseline: **one run** -- the `Cleanup PR Preview`
failure that started this. That is the honest expectation and it should be
stated in the job's own summary, because a sweeper that reports "0 retried" every
night must be distinguishable from one that is broken.

## Phase 3 — make a by-design failure legible

`watchdog-monitor.yml` reporting `failure` when it has worked correctly is the
root of both problems, and it also misleads every human scanning the Actions tab.
Options, in increasing order of change:

- **3a:** keep `setFailed()` but make the run NAME say so, e.g.
  `Watchdog: run <id> (gen N) -- pipeline cancelled as designed`.
- **3b:** exit 0 and record the cancellation in the job summary + an output,
  so `conclusion=failure` regains its plain meaning repo-wide.

**3b is the correct end state and the riskier change**: something may already
depend on that non-zero exit. Before touching it, grep for consumers of the
watchdog's conclusion (`autopilot.yml:261` reads watchdog runs by status -- check
what it does with them). Do NOT bundle 3b with Phases 1-2.

## Tests -- each must FIRE on a planted defect and stay silent when clean

Surface: **gates** (source-level wiring) plus **hook/gate suite** for the script
logic, per `.claude/skills/testing`.

1. `test-nightly-retry-filters.sh` (new, `.ci/scripts/test/gates/`), hermetic
   with a shimmed `gh`:
   - a `cancelled` run is NOT retried (plant: flip the filter to include
     cancelled -> must go red);
   - a watchdog-path run is NOT retried (plant: swap the path filter for a
     display-name match, feed it `Watchdog: run 1 (gen 2)` -> must go red);
   - a run whose head is not a branch tip is NOT retried;
   - a genuine failed run on a live head IS retried exactly once;
   - `run_attempt >= cap` is skipped.
2. Extend the existing gate for Phase 1 so that a scan window unable to reach
   the retention threshold is reported. Control: set pages=1 against a
   high-volume workflow fixture -> must fire.
3. **Do not assert on live GitHub.** Every case above is a fixture; a gate that
   needs the API up is a gate that gets skipped during an outage.

## Risks

1. **Re-running something destructive.** The retry population includes deploy and
   cleanup workflows. Mitigated by filters 1+3 (live head, failure only), but the
   review must confirm no retried workflow is non-idempotent.
2. **Phase 1c changes retention for every workflow at once.** Prefer 1a.
3. **Phase 3b may break a consumer** of the watchdog's non-zero exit. Grep first,
   ship separately.
4. **The sweeper's own failure is invisible** -- it runs at 03:00 and notifies
   nobody. `nightly-status.yml` exists for exactly this class of problem on
   Console CI; consider whether housekeeping deserves the same treatment. That is
   a separate decision, deliberately not folded in here.

## Sequencing

Phase 1 and Phase 2 are independent and can land together in one PR (both touch
housekeeping only). Phase 3 lands separately, after the grep for consumers.
