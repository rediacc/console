# PLAN: a resource-profiling layer for background shells
Status: compacted
Full-Text-Blob: acfed5118c57313c4f59592e73370b780616f5ac
Record-Sig: 610e1cea

## Why
The repository lacked observability into resource consumption (CPU, memory, I/O) of background shell processes in CI gates and hook invocations. Early incidents like the shellcheck gate OOM-killing at 2714 MB went undiagnosed. Investigation revealed that naive injection approaches—setting BASH_ENV trap handlers to capture exit state—fail completely when target scripts set their own
EXIT traps or use `exec`, because Bash has only one trap slot per signal.

## Outcome
Landed 2026-09-03, all gates green. The tree now runs an exit-based recorder (`wl_resprofile.py`), a 500-ms tree sampler walking `/proc`, and a deriver synthesizing five finding classes: E1 (sequential independent fanout), E4 (undeclared concurrent writer), E5 (intra-shape memory outlier, report-only until J>=20), E6 (zombie accumulation). Bash coverage via a `wait4` supervisor
(`bashcov-sup`) as primary method and a shadow-trap fallback. Time-based corpus at `~/.claude/resprofile/` with per-shape rollups. First production run on ci:quick: 292 gate captures, zero findings after E5 tuning. Baseline seeding deliberately deferred pending real quiet-run accumulation.

## Lessons
- Bash EXIT trap via BASH_ENV fails completely when the script sets its own trap—only one slot exists per signal, and later assignments silently override. The naive approach produced zero records on the worklist suite despite appearing instrumented.
- `wchan` values `do_wait` and `anon_pipe_read` are recursion signals, not verdicts; only terminal frontier values render findings. CPU accumulation lives in `cutime` (reap-time only), not live counts, so sampling must track reap motion, not process count.
- E1's original `cpu/wall` saturation ratio failed dilation invariance under k=2.25 suite-timing variance; only R-state fractions (ratio of runnable time) survive uniform time scaling. Invariance became a testable gate (D1 control).
- Per-invocation records (54 KB per battery run) exceeded the steady-state corpus that consumes them (three-day worklist log is 416 KB total). Tier-0 must not persist; only shape-based rollups do.
- Seeding baseline thresholds from one machine's first production run enshrines its artifacts. Real quiet runs must accumulate for days before any baseline snapshot.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: landed
Compacted-By: d778be9d
Compacted-At: 2026-09-20T16:44:01Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: 24c98380, e87fa3ce
Touched: .claude/hooks/stop/test-worklist-v5.sh, scripts/ci-runner/exec.ts, .ci/scripts/quality/check-tracked-sidecars.sh, .ci/scripts/test/run-all.sh, docs/agent-reference/TRAPS.md, .ci/scripts/security/shellcheck.sh, .ci/scripts/test/gates/test-breakpoint-teardown.sh
Gates: check:ci-hook-worklist-suite, check:ci-resprofile, check:ci-workflows, check:test-shared
Why-Source: model
Read-History: `git show acfed5118c57313c4f59592e73370b780616f5ac` recovers the text; `git log --find-object=acfed5118c57313c4f59592e73370b780616f5ac --all` names the commit

## History
- 2026-09-20T16:44:01Z compacted by d778be9d from `landed` (record-sig 610e1cea)
