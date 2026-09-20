# PLAN: mutrun, a two-direction mutation runner for expensive suites
Status: compacted
Owner: 99ccf057
Full-Text-Blob: 81e70861b4491aafc5fcb60eac2ed77445c60c0e
Record-Sig: 6fbfd72a

## Why
A session added test cases and mutated a guard to verify they fire. Both cases went red—but they were red on the untouched tree too, so the red proved nothing. The root cause: without a mandatory baseline pass, a broken fixture cannot be distinguished from a working mutation. Two-direction discipline (baseline green, mutant red) was needed, but enforcing it by hand for expensive
suites (>4 min) is tedious enough that people skip the baseline.

## Outcome
Shipped and verified: `.ci/scripts/test/mutate-check.sh` (sandbox mutation harness, runs baseline + mutant, exits 0 only when mutant reds named cases and baseline is green) and `.ci/scripts/quality/check-mutate-check.sh` (gate test), registered as `check:ci-mutate-check`. Arms run sequentially, not concurrently as planned, and no suite registry was built—both optimizations. Two
defects in the throwaway were fixed: repo-root arithmetic broken by flat sandboxes, and regex filters that couldn't match the suite's output format.

## Lessons
- A missing artifact does not prove the plan was never executed. Check whether the output exists before calling a plan stranded.
- Sandbox path mirroring is load-bearing: a flat copy breaks repo-root arithmetic when the hook walks a fixed number of parents. Mirroring paths under a `.git` marker ensures the sandbox resolves its root identically.
- A parser that fails silently is the tool's own version of the defect it catches. Every invocation must cross-check its grammar against the suite's reported counters before returning a verdict.
- Cleanup via trap or finally has signal-dependent correctness: SIGTERM kills them before they run. Not touching the live tree removes the question entirely.
- The baseline was skipped once under time pressure. Concurrent arms make wall-clock cost match one-direction, removing that pressure; they were dropped only because cost proved acceptable.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: d778be9d
Compacted-At: 2026-09-20T16:42:24Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: 24c98380, e87fa3ce
Touched: package.json, docs/agent-reference/TRAPS.md, .ci/scripts/test/gates/test-claude-hooks.sh, .ci/scripts/test/run-all.sh, scripts/gates/check-ci-parity.ts, scripts/ci-runner/manifest.ts, scripts/gates/check-dead-bash.ts, scripts/ci-runner/run.ts
Gates: check:ci-gate-id-convention, check:ci-gate-reachability-coverage, check:ci-mutate-check, check:ci-parity
Why-Source: model
Read-History: `git show 81e70861b4491aafc5fcb60eac2ed77445c60c0e` recovers the text; `git log --find-object=81e70861b4491aafc5fcb60eac2ed77445c60c0e --all` names the commit

## History
- 2026-09-20T16:42:24Z compacted by d778be9d from `done` (record-sig 6fbfd72a)
