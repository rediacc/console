# Effort tuner run, session d778be9d, context epoch 68 (2026-10-14T22:28:11Z)

Window: 14 day(s), 152 ledger row(s). Columns: rows (work, paperwork, overruled, expired) precision.

| key | block | advise | off | quiet before a miss |
|---|---|---|---|---|
| agent-hint | 0 (w0 p0 o0 e0) | 8 (w1 p7 o0 e0) 0.12 | 0 (w0 p0 o0 e0) | 5 |
| agent-state | 0 (w0 p0 o0 e0) | 9 (w0 p8 o0 e1) 0.00 | 0 (w0 p0 o0 e0) | 5 |
| ask-refusals | 0 (w0 p0 o0 e0) | 1 (w0 p0 o0 e1) 0.00 | 0 (w0 p0 o0 e0) | 0 |
| bg-orphan | 0 (w0 p0 o0 e0) | 5 (w0 p5 o0 e0) 0.00 | 0 (w0 p0 o0 e0) | 4 |
| bg-report | 2 (w2 p0 o0 e0) 1.00 | 0 (w0 p0 o0 e0) | 0 (w0 p0 o0 e0) | 0 |
| commit-remind | 0 (w0 p0 o0 e0) | 2 (w0 p2 o0 e0) 0.00 | 0 (w0 p0 o0 e0) | 1 |
| commit-review | 9 (w7 p2 o0 e0) 0.78 | 0 (w0 p0 o0 e0) | 0 (w0 p0 o0 e0) | 0 |
| commit-review-note | 0 (w0 p0 o0 e0) | 24 (w18 p5 o0 e1) 0.75 | 0 (w0 p0 o0 e0) | 10 |
| defer-expired | 3 (w2 p0 o0 e1) 0.67 | 0 (w0 p0 o0 e0) | 0 (w0 p0 o0 e0) | 0 |
| found-not-fixed | 1 (w1 p0 o0 e0) 1.00 | 0 (w0 p0 o0 e0) | 0 (w0 p0 o0 e0) | 0 |
| hint-proposals | 0 (w0 p0 o0 e0) | 0 (w0 p0 o0 e0) | 2 (w0 p2 o0 e0) 0.00 | 1 |
| ladder-gone | 1 (w1 p0 o0 e0) 1.00 | 0 (w0 p0 o0 e0) | 0 (w0 p0 o0 e0) | 0 |
| no-remaining | 0 (w0 p0 o0 e0) | 10 (w7 p2 o0 e1) 0.70 | 0 (w0 p0 o0 e0) | 2 |
| open-items | 1 (w1 p0 o0 e0) 1.00 | 0 (w0 p0 o0 e0) | 0 (w0 p0 o0 e0) | 0 |
| out-of-sync | 0 (w0 p0 o0 e0) | 4 (w4 p0 o0 e0) 1.00 | 0 (w0 p0 o0 e0) | 3 |
| plan-backlog | 0 (w0 p0 o0 e0) | 5 (w3 p1 o0 e1) 0.60 | 0 (w0 p0 o0 e0) | 2 |
| plan-pr-open | 0 (w0 p0 o0 e0) | 1 (w0 p0 o0 e1) 0.00 | 0 (w0 p0 o0 e0) | 0 |
| plan-tasks | 0 (w0 p0 o0 e0) | 1 (w0 p0 o0 e1) 0.00 | 0 (w0 p0 o0 e0) | 0 |
| receipt-behind | 0 (w0 p0 o0 e0) | 25 (w24 p1 o0 e0) 0.96 | 0 (w0 p0 o0 e0) | 11 |
| reg-flood | 0 (w0 p0 o0 e0) | 2 (w2 p0 o0 e0) 1.00 | 0 (w0 p0 o0 e0) | 2 |
| reg-queue | 0 (w0 p0 o0 e0) | 1 (w1 p0 o0 e0) 1.00 | 0 (w0 p0 o0 e0) | 0 |
| roster-dead | 10 (w9 p1 o0 e0) 0.90 | 0 (w0 p0 o0 e0) | 0 (w0 p0 o0 e0) | 0 |
| roster-unleased | 4 (w0 p3 o0 e1) 0.00 | 0 (w0 p0 o0 e0) | 0 (w0 p0 o0 e0) | 0 |
| scheduled-unreadable | 0 (w0 p0 o0 e0) | 1 (w0 p1 o0 e0) 0.00 | 0 (w0 p0 o0 e0) | 1 |
| submodule | 0 (w0 p0 o0 e0) | 3 (w3 p0 o0 e0) 1.00 | 0 (w0 p0 o0 e0) | 1 |
| unblocked | 0 (w0 p0 o0 e0) | 1 (w0 p1 o0 e0) 0.00 | 0 (w0 p0 o0 e0) | 1 |

## Candidate changes

- promote no-remaining: {"block": "high", "advise": "smart"} -> {"block": "smart", "advise": "smart"}. advised 10 time(s), 7/10 led to work. Rows: eo-39d733e9, eo-7b9cfade, eo-fa20bec6, eo-95cffaba, eo-fdadb35f, eo-a847d62a, eo-1931478e, eo-fc097b32, eo-2955b892, eo-dfed90e8
- promote plan-backlog: {"advise": "smart"} -> {"advise": "low"}. advised 5 time(s), 3/5 led to work. Rows: eo-5b51a195, eo-4a48cdfe, eo-2c8ce2cb, eo-2e161bd7, eo-426369d0

## The candidate table against the effort-table rule

- clean

## Replay: recorded emissions whose verdict changes

- session d778be9d epoch 66 stop 1: no-remaining at smart advise -> block (outcome work, eo-39d733e9)
- session d778be9d epoch 66 stop 3: no-remaining at smart advise -> block (outcome work, eo-7b9cfade)
- session d778be9d epoch 66 stop 4: no-remaining at smart advise -> block (outcome work, eo-fa20bec6)
- session d778be9d epoch 66 stop 6: no-remaining at smart advise -> block (outcome expired, eo-95cffaba)
- session d778be9d epoch 66 stop 9: no-remaining at smart advise -> block (outcome paperwork, eo-fdadb35f)
- session d778be9d epoch 66 stop 12: no-remaining at smart advise -> block (outcome work, eo-a847d62a)
- session d778be9d epoch 67 stop 13: no-remaining at smart advise -> block (outcome work, eo-1931478e)
- session d778be9d epoch 67 stop 22: no-remaining at smart advise -> block (outcome work, eo-fc097b32)
- session d778be9d epoch 68 stop 49: no-remaining at smart advise -> block (outcome paperwork, eo-2955b892)
- session d778be9d epoch 68 stop 55: no-remaining at smart advise -> block (outcome work, eo-dfed90e8)

## Dead keys (no row in a window of at least 20 stops)

- agent-absent
- agent-bootstrap
- agent-corpus-err
- agent-pushback
- archived
- audit
- backup-push
- broken-schedule
- ci-hold
- ci-queue
- ci-report
- ci-verdict
- ci-waiting
- cl-door
- cl-flip
- cl-foreign
- cl-foreign-waves
- cl-owner
- cl-producing
- cl-waves
- claim-check
- commit-review-malformed
- completion
- defer-settle
- deferred-finding
- deflected-finding
- diverged
- effort-tune
- focus-ended
- focus-pr-items
- focus-pr-unreadable
- github-recovered
- github-status
- giveup-claim
- handoff
- hint-corpus-err
- idle
- idle-stall
- intent-expired
- ladder
- ladder-idle
- ladder-investigate
- ladder-resolve
- loop-died
- loop-next
- main-push-unreadable
- many-work-crons
- mislabelled
- orphans
- pending-ask
- phantom-blind
- phantom-gate
- phantom-identity
- plan-adopted
- plan-drift
- plan-fidelity
- plan-unimplemented
- planfid-degraded
- pr-finish
- pr-review
- pr-stale
- pr-unreadable
- prscope-broken
- queue-slot
- reg-capped
- reg-forgot
- reg-settled
- resprofile
- roster-concurrency
- roster-silent
- scheduled-green
- scheduled-red
- scheduled-red-bug
- scheduled-red-peer
- settings-problem
- shapedup
- shapedup-wide
- shapedup-wide-note
- soaked-pins
- solo-grind
- stale-local
- stuck
- sweep-moment
- sweep-ungrounded
- trapfires-retire
- turbo-next
- unblocked-claim
- uncited
- unconfirmed
- undefaulted
- unjustified
- unstated

## Tuned keys due for review

- none

## Proposed judge rules

- none

## The session's observations

# Observations, d778be9d context epoch 68 (2026-10-14)

## Useful checks
- review-block (open findings at or above the block threshold): every high it raised was a real defect (e.g. 37e7186d.1 multi-commit push judged on HEAD, 5871edf9.1 vitest-by-path missed, f794ae92.1 `!` prefix inverting the apply status, e109ab6e.1 worktree guard binding gap). Keep blocking.
- roster-dead / roster-unleased: both fired correctly when a writer finished or was spawned without a lease; each was fixed in one call. Useful, cheap.
- defer-expired: caught #c33b8946 whose DEFAULT could not yet run; led to the NOT-BEFORE token (2d3a184fe, 7594fde9.., e2fa11361). Useful after that fix.
- PURE BACKGROUND WAIT check-in with stream-growth evidence: the POSSIBLY STUCK flag on a writer quiet 28 min was right to raise; the writer was slow under ci:quick load, not dead.

## Useless or harmful
- The stop-gate judge repeatedly misread state:
  - cited the stale original text of #97a7ced2 (findings closed that morning) as open work, three times, even after a LATEST update said STALE TEXT;
  - called pins T13 due at 22:11Z and 22:19Z while the item carried NOT-BEFORE:2026-10-15T00:00Z and `pins status` said deferred; it appears to read the user's local date as UTC;
  - demanded "list every open id" on stops that already listed them grouped.
  These cost several full stop round trips with no work moved. Judge errors, not check errors.
- review-block while the finding is owned by a live leased writer: blocks a stop that can only wait (recorded as a hint).

## Judge errors to turn into rules
1. A deferral with a future NOT-BEFORE is not due (the judge must call wl_core.not_before_pending or read the token).
2. An item whose LATEST note begins "STALE TEXT ABOVE" is judged by the LATEST, not the original text.
3. Time comparisons use UTC from `date -u`, never the environment's local date line.
