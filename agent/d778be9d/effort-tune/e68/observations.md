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
