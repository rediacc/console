# Full-run timing baseline

Status: done
Owner: 8f55d4f0
Updated: 2026-09-06

This file exists because four different figures appear across the workstream drafts as thresholds (53.7s, 58s, and gate counts of 308, 310 and 311). None of them was measured on this tree. This is one run, recorded so no future box has to guess, and it replaces all four.

## The measurement

    npm run ci
    started 2026-09-06T16:11:33Z
    ended   2026-09-06T16:24:34Z

    437 gates: 418 ok, 19 failed, 0 skipped
    wall 780.4s   serial 7021.0s   parallelism 9.0x

The plan's stated local floor was 785s, set by `gate-test:claude-hooks`. The measured wall is 780.4s, which is close enough to be a mutual sanity check on both numbers rather than a coincidence.

## What this run was NOT, stated so the number is not read as more than it is

**It was not fully uncontended, and the runner said so.** All ten writer agents, both surveys and the permissions audit had returned before it started, so no concurrent WRITER distorted it, which is the contention invariant 13 is about: a 4.5s gate has been measured at 21s under two concurrent writers. But three `agent/` writes happened DURING the run, all mine and all forced by
the stop hook: a `--lease` append, a STATE.md rewrite, and a worklist `--add`.

None is code, config, or gate input, so the wall-clock figure stands. The narrow exposure is the handful of gates that read `agent/`, and those must be re-run on a still tree before any red among them is believed. `check:ci-plan-boxes` and `check:ci-plan-record` were both red in an earlier contended run and both green when re-run alone, which is exactly this effect.

**Nineteen gates failed**, so this is a timing receipt and not a green run. The failures are triaged separately; two are known and deliberate (`check:ci-shape-duplication`, one cluster awaiting one change, and `check:ci-secret-reachability`, which needs an admin:org token and is an operator-only door).

## The twenty slowest gates in this run

       780.4s  gate-test:claude-hooks
       686.4s  check:ci-hook-worklist-suite
       334.5s  check:ci-lint-scope-coverage
       318.2s  check:ci-pytest
       267.9s  check:ci-dead-bash
       265.1s  check:types
       220.8s  build:www
       174.8s  check:ci-shell-lint

## How to reproduce

Run it from a QUIESCED worktree, with no writer agent live and nothing appending to `agent/`, and read the runner's own tree-changed warning before believing any red. A number from a contended tree is not admissible as a threshold; that is invariant 13, and it is why this file records the conditions and not just the figure.
