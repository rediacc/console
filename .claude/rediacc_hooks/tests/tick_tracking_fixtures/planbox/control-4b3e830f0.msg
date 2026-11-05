feat(cli): dev-build seam that forces a detached-job start retry

PLAN-detached-jobs L5 step 6 needs a live run in which the first `job start` creates the job but its answer is lost, so the retry with the same request id must attach to that job instead of starting a second one.

With REDIACC_TEST_DROP_FIRST_JOB_START=1 on a dev build (isDevBuild), the first start attempt runs as a plain `job start` (no --attach) through a blind attach sink, its handle is discarded, and the attempt reports a drop, so the existing retry loop in JobRun.start runs the real launch with the same request id. A start that created no job (refusal, old renet, failure) is returned as it is. A release build ignores the flag.

Tests (detached-jobs.test.ts): the seam on a dev build (two execs, one request id, the first without --attach, one onJobStarted), a failed discarded start surfaces without a retry, the control with the flag unset, and a release build (VERSION 1.2.3) ignoring the flag.

Verification:
- cd packages/cli && npx vitest run src/services/executor/__tests__/detached-jobs.test.ts: rc 0, 12 passed
- cd packages/cli && npx vitest run src/services/executor src/services/jobs: rc 0, 472 passed
- npx tsc --noEmit --project packages/cli/tsconfig.json: rc 0
- npx biome check on both files: rc 0
- PYTHONPATH=.ci python3 -m rediacc_ci.quality.env_manifest: rc 1, UNCLASSIFIED REDIACC_TEST_DROP_FIRST_JOB_START (the registration is outside this unit's owned paths and needs npm run env:register)

PR-TASK: 09b8bdfa
(cherry picked from commit ae15f7cba6b7d260b268861ba598d60d6f6d0a39)

