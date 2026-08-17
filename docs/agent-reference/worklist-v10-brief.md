# Worklist v10 brief

Operator brief of 2026-07-30, to be planned then implemented by a **fable**
sub-agent. It starts only after the PR-green agent releases `worklist.py`,
`worklist_messages.py` and `test-worklist-v5.sh`.

This file exists so the planner inherits what a full night of live use taught,
instead of rediscovering it. Every claim below was observed, not theorised.

## What the operator asked for

1. **Liveness tracing.** Every item carries a start time and a last-update time,
   stamped each iteration.
2. **Catch the empty "ongoing".** An item claiming to be in flight must be
   checked against a worker that actually exists: PID-based tracing through OS
   or Python APIs, not the event payload's word for it.
3. **A time ladder, not a binary.** About 45 minutes: ping. About 90: investigate
   what is happening. About 120: consider stopping it. The hook becomes an
   eye-opener and gap catcher rather than only a report gate.
4. **Delegation.** Remaining work may need handing to a sub-agent automatically.
5. **JSON storage** instead of the markdown file, still safe under concurrent
   use by several sessions.
6. **Less operator dependency.** Too many items read "blocked on you" when the
   operator almost always takes the recommended option. Prefer acting on the
   default and reporting it.
7. **Handover limit 250-600 becomes about 1500.**
8. **Performance.**
9. **Tidy-up:** several organised modules instead of one 3100-line file, and
   delete unused functions.
10. **Testing matters a lot.**

## Evidence the design must respect

These are the traps that actually bit, with the artefact that proves each.

- **A claimed "ongoing" is usually stale, which is exactly why item 2 exists.**
  This session reported watches as live that had already completed, and one
  watch reported a FALSE failure because a watchdog rerun flipped a terminal run
  back to `in_progress`. Two separate watches ended on runs that a later push had
  already superseded. Trusting the event's `background_tasks` is not enough.
- **The 250-600 character handover was too tight and burned rounds.** Three
  rewrites in one night landed at 649, 620 and 611 characters before fitting.
  Raising it to ~1500 removes a real tax.
- **The handover's 10-minute staleness limit is outpaced by the 5-minute poll
  cron**, so a quiet session goes stale every other poll and can never take the
  silent path.
- **A gate that cannot be satisfied deadlocks the session, and it happened.**
  `poll_fast_path` needs a baseline that only an allowed stop wrote, but any open
  task blocks the stop, so the baseline was never written all night and every
  5-minute poll paid the full battery. Fixed by operator decision in
  `860f47b04`. Any new time-based check must be built so it cannot trap the
  session the same way.
- **Thirty-plus open `- [?]` deferrals is the symptom item 6 names.** They are
  reported on every stop, which buries the two or three that are real.
- **Porcelain output is not a contract.** `submodule_pointer_moves()` parsed
  `git submodule status --cached` for a leading `+`; it works on git 2.43 and
  returned nothing on CI's 2.54, so the suite passed locally and failed in CI.
  Prefer plumbing: `git ls-files -s <path>` against `git -C <path> rev-parse
  HEAD`.
- **Swallowing output hides the cause.** That test fixture wrapped every git
  command in `>/dev/null 2>&1`, so CI could only print `got: ` with no reason.
  The same mistake cost a separate round earlier the same night when
  `gh run view --log-failed` wrote its refusal to stderr.
- **The suite CI runs is `.claude/hooks/test-hooks.sh`**, which drives
  `test-worklist-v5.sh` among ~61 other cases. Running only the worklist suite
  is how a broken case reached CI while the session reported 172/0. Run both,
  with `GITHUB_ACTIONS` set AND unset, because the hook no-ops on runners.

## Invariants not to lose in the rewrite

- `emit()` exits the process, so anything after a block never runs. Ordering is
  load-bearing.
- `STOPHOOK_CHILD` must stay the first statement of `main()`: `claude -p` re-fires
  the hook and `--settings '{"hooks":{}}'` does not suppress it.
- A crashing hook must BLOCK, never read as allow.
- A check that cannot read must say it is blind rather than pass quietly (the
  `V_PR_UNREADABLE` pattern).
- Every message constant is registered in the test's arity registry, so an
  unrendered constant cannot lurk.
- The store is shared: append, never rewrite wholesale, and hold the lock.
