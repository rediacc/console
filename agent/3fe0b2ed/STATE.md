## SESSION 3fe0b2ed 2026-08-19T18:43:13Z

## Task

Plan ~/.claude/plans/let-s-make-a-plan-vast-cray.md: tutorial output exceeds the 107-column
recorded terminal and wraps into unreadable rows. Fix at source, re-record 18 casts,
regenerate 234 pairs, publish to R2. Operator approved the plan with "GO".

## PHASE 4 IS DONE. THE CAST GATE IS RED, AND THAT IS THE REAL STATE.

All 18 casts recorded on the downclocked host (sweep run 4, worker bt3etolpv, now finished).
The chain then ABORTED at the cast gate with 24 violations, before Phase 5. That abort is
correct: it stopped a ~5 hour render on a bad corpus.

**Phase 0 was NOT done, despite four earlier reports saying so.** Those rested on ONE sample
tutorial that never exercised the failing paths. The gate over all 18 disagreed. Treat any
"verified" claim in this file as scoped to what was actually run.

FIXED since (15 of 24), all uncommitted:
- job-remote.ts:426 `outputLine` echoed renet's machine-readable protocol verbatim
  ({"push_result":...} at 322-400 cols). New `isMachineReadableRelayLine`
  (output-lines.ts:143) drops whole-line JSON from the HUMAN stream only; stdout capture is
  separate so extractPushResult still works. 6 tests, mutation-proven, third guard in
  check:ci-guard-mutations.
- My own eslint breakage in local-executor.ts and daemon/client.ts (cognitive complexity).
  PROVEN mine by linting each file's HEAD copy clean and restoring byte-identically.
  local-executor now USES createQuietStderrPump instead of an inlined duplicate of it;
  daemon/client gained `routeLogEvent`.

## Next action

1. **#a6dd08a8** finish the remaining 9 cast-gate violations, in this order:
   a. `rdc repo up my-app:test` still leaks a 115-col `level=info` logrus line - that is the
      EIGHTH raw stderr pump; find it.
   b. `rdc doctor` prints a 232-col version table.
   c. `docker ps` (122) and `df -h` (128) are third-party: narrow them in the tutorial
      scripts (plan step 0d, never done). The df width comes from a 36-char device-mapper
      GUID.
   d. typed `ssh-copy-id` line is 111 cols.
   e. the 162-col `rdc vscode connect --browser` URL is DELIBERATELY exempt per the plan
      (breaking a URL makes it uncopyable) - the GATE must learn that, do not wrap it.
   Re-run: bash scratchpad/rebuild-and-sweep.sh, and re-lease #2de6d413 / #552b33ec to that
   new worker id.
2. **#2de6d413** Phase 5 auto-starts once the gate passes. If `generate` reports new
   synthesis, STOP: the clip cache missed.
3. **#552b33ec** Phase 6: ASK before any upload (media-pipeline.md:374).

Never run a recording in the FOREGROUND: the Bash tool caps at 10 min and SIGTERMs it
mid-flight. The driver only prints at stage boundaries, so judge liveness by
scratchpad/sweep.record.log growing, not by its silence.

## Also landed this session

- run.sh records in declared frontmatter order, not alphabetically.
- ALL 17 tutorials send setup output to $TUTORIAL_SETUP_LOG instead of /dev/null, and
  record.sh prints the preserved cast tail AND that log on failure. Without this, three
  aborts produced no output at all.
- Healthchecks calibrated for a slow host (demo-pgadmin pgadmin 300s/30, db 90s/20;
  heartbeat 90s/12), plus gate `check:ci-tutorial-healthcheck-headroom` (floor 180s,
  evidence: the config that failed had a 150s budget).
- Gate `check:ci-guard-mutations`: runs the CLI tests against a deliberately broken COPY and
  requires them to FAIL.

Green: CLI suite 2390/2390, eslint (FROM REPO ROOT), check:ci-parity, shell-format,
dead-bash, anti-vacuity battery, both new gates.

## Environment

REDIACC_ALLOW_GRAND_REPO=* is set in THIS session's env and is required for recording; it
must be exported BEFORE the agent starts, so a fresh session loses it and cannot record.
