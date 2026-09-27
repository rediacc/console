#!/bin/bash
# Write this leg's `{file, outcome}` JSON for ct-e2e-probe.yml's
# `probe-file` job (T2.12, PLAN-ci-time-budget). Called with `if: always()`
# after the file's own E2E run, so it fires whether that run passed or
# failed; `$2` is the job's own conclusion so far (`${{ job.status }}`),
# read rather than the step's `continue-on-error` outcome -- that flag is
# banned by check:ci-workflows, and `job.status` already reflects a failed
# prior step without it.
#
# Usage: record-e2e-probe-outcome.sh <file> <job-status>
set -euo pipefail

FILE="${1:?usage: record-e2e-probe-outcome.sh <file> <job-status>}"
JOB_STATUS="${2:?usage: record-e2e-probe-outcome.sh <file> <job-status>}"

OUTCOME="fail"
[[ "$JOB_STATUS" == "success" ]] && OUTCOME="pass"

OUT_DIR="${RUNNER_TEMP:-/tmp}/e2e-probe"
mkdir -p "$OUT_DIR"
printf '{"file":"%s","outcome":"%s"}\n' "$FILE" "$OUTCOME" >"$OUT_DIR/result.json"
