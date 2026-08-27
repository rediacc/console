# ci-watch: the incidents that bought the script

Evidence for [SKILL.md](SKILL.md). Both files are capped at 60 lines by
`check:ci-skill-size`, so a new entry means compressing an old one.

## Four failures in one afternoon (2026-08-25, console#574)

All four were hand-rolled `gh` loops written from prose. They are why
`.ci/scripts/ci/ci-trace.py` exists and why the ad-hoc form is now blocked.

1. **Stale in nine places.** A manual sweep found six copies; the gate found
   three more in hook *scripts* the sweep's `*.md` grep could not see. Two were
   worse than stale: `block-long-sleep.sh` explained that "attempt 2 lands on
   the SAME Console CI run" while printing a loop that could not survive it,
   and `cancel-old-ci.sh` recommended the tool this repo rejects 4/4.
2. **A superseded attempt reported as final.** The watch on run `32810322315`
   returned `cancelled` / `CI Complete` failed. Moments later the run read
   `in_progress`: `run_attempt` had gone to **2** because the watchdog
   re-dispatched a hung `OPS Provision (macos-intel)` leg. Attempt 2 passed.
3. **A verdict from an already-cancelled run.** A later push cancelled the run
   being watched; the loop reported its corpse.
4. **A swallowed network blip.** `network is unreachable` mid-poll, survived
   only because that particular retry arm happened to be written correctly.

The fix is structural: keying on the PR head makes 2 and 3 inexpressible.

## The compound watch that swallowed a red run (2026-08-24)

A watch that waited for CI and THEN for a review marker printed its verdict —
`failed: ["Quality / Static"]` — into its output file and never exited, having
moved into a second wait for a review that a red run never posts. Nothing woke
the session for ninety minutes; it surfaced only when the operator pasted the
failing job's URL, asking "don't you watch?". The background check-in kept
reporting a live worker, because the worker *was* live. Hence one wait per
command — and now one script that owns the waiting.

## A killed watch answered as a no-op (2026-08-24)

A round-4 watch was killed rather than completing; treated as "no response
requested" and the session stopped. The run had gone **green** and sat
unwatched, PR still in draft, until the operator asked.

## `--ref main` cannot see a dispatched run (2026-08-26)

A branch's `statusCheckRollup` has NO `workflow_dispatch` check runs at all:
Release run `32968110599` was `in_progress` per the REST check-runs API while
`--wait --ref main` read the rollup as SUCCESS, none in flight, and printed
GREEN -- twice, including with `--until-final`. Certified a release that had
not run. Fix: `--run <id>` reads per-JOB conclusions directly, not the branch.

## The banned tool is a convenience, not a contract

`gh run watch`'s `--exit-status` returns non-zero on failure, but it dropped
**four times out of four** in one campaign and has exited 1 mid-run.

## Why the mechanism is what it is

Confirmed against the docs: background output is written to a file read on
demand, and the wake-up is the process exiting
(<https://code.claude.com/docs/en/interactive-mode>).
