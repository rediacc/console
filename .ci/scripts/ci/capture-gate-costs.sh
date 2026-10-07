#!/usr/bin/env bash
# Housekeeping's gate-cost capture (.github/workflows/housekeeping.yml, job gate-costs-capture), one phase per call.
#
#   capture-gate-costs.sh quick      serial ci:quick -> quick.json; fails on a hang or an unusable report
#   capture-gate-costs.sh rotation   one third of the slow gates (run.ts --slow-rotation) -> rotation.json;
#                                    never fails itself, writes rc=<n> to $GITHUB_OUTPUT instead
#   capture-gate-costs.sh merge      quick.json plus rotation.json (when ROTATION_RC=0) -> gate-costs.json
#
# Env: RUNNER_TEMP, where the runner's stderr logs go (default: a fresh mktemp -d). GITHUB_OUTPUT
# (rotation; skipped when unset). ROTATION_RC (merge). CAPTURE_NIGHT, 1-3, overrides the rotation
# index taken from the day of the year. QUICK_BOUND / ROTATION_BOUND override the outer timeouts
# (12m / 32m). CAPTURE_DIR is where the three .json files go (default: the current directory, which
# is what the workflow uploads from; a local sample points it outside the tree). CAPTURE_EXTRA_ARGS is appended to the quick run (a local `--only <ids>` sample).
#
# Local, from the repository root:
#   RUNNER_TEMP=$(mktemp -d) CAPTURE_DIR=$(mktemp -d) CAPTURE_EXTRA_ARGS='--only check:ci-npmrc' .ci/scripts/ci/capture-gate-costs.sh quick
#
# Every runner call streams its stderr (a start and a finish line per gate) live AND into
# $RUNNER_TEMP/gate-costs-<phase>.log, so a run cut short still shows the gate it was waiting on.
# On the outer timeout the runner's own SIGTERM handler names the gates still running and kills
# their process groups (scripts/ci-runner/run.ts installSignalHandlers).
set -euo pipefail

LOG_DIR="${RUNNER_TEMP:-$(mktemp -d)}"
OUT="${CAPTURE_DIR:-.}"
VALIDATE=(env PYTHONPATH=.ci python3 -m rediacc_ci.ci.gate_costs --validate-capture)

# run_bounded <bound> <out.json> <log> <run.ts args...>: prints the runner's exit status, never fails.
run_bounded() {
  local bound=$1 out=$2 log=$3
  shift 3
  local rc=0
  timeout --kill-after=30s "$bound" npx tsx scripts/ci-runner/run.ts "$@" --jobs 1 --sched slots --json \
    >"$out" 2> >(tee "$log" >&2) || rc=$?
  echo "$rc"
}

hung() { [ "$1" -eq 124 ] || [ "$1" -eq 137 ]; }

case "${1:-}" in
  quick)
    bound=${QUICK_BOUND:-12m}
    # shellcheck disable=SC2086 # CAPTURE_EXTRA_ARGS is a word list on purpose
    rc=$(run_bounded "$bound" "$OUT/quick.json" "$LOG_DIR/gate-costs-quick.log" --quick ${CAPTURE_EXTRA_ARGS:-})
    if hung "$rc"; then
      echo "::error title=Gate cost capture hung::the serial ci:quick outlived its $bound bound (exit $rc); the gates still running are named on the 'ci-runner: received SIGTERM' line above"
      exit 1
    fi
    echo "run.ts exit $rc (gate reds are expected on this checkout and do not fail the capture)"
    "${VALIDATE[@]}" "$OUT/quick.json"
    ;;
  rotation)
    bound=${ROTATION_BOUND:-32m}
    # THREE, because the repository keeps artifacts 3 days (actions/permissions/artifact-and-log-retention,
    # 2026-10-07), so gate_costs never sees more than 3 captures: every slow gate must fall inside 3 nights.
    night=${CAPTURE_NIGHT:-$((10#$(date -u +%j) % 3 + 1))}
    echo "slow rotation $night/3"
    # 600 s per gate: a 1-core grant can stretch a parallel suite past its CI step p90, and the kill names it rather than eating the night.
    rc=$(run_bounded "$bound" "$OUT/rotation.json" "$LOG_DIR/gate-costs-rotation.log" --slow-rotation "$night/3" --gate-timeout 600)
    if hung "$rc"; then
      echo "::error title=Slow-gate rotation hung::run.ts --slow-rotation $night/3 outlived its $bound bound (exit $rc); the gates still running are named on the 'ci-runner: received SIGTERM' line above"
    else
      echo "run.ts exit $rc (gate reds are expected on this checkout)"
      rc=0
      "${VALIDATE[@]}" "$OUT/rotation.json" || rc=$?
    fi
    if [ -n "${GITHUB_OUTPUT:-}" ]; then echo "rc=$rc" >>"$GITHUB_OUTPUT"; fi
    ;;
  merge)
    if [ "${ROTATION_RC:-}" = "0" ]; then
      # A prerequisite both runs ran is kept once, from the quick run; `slowRotation` records what was added.
      jq -s '.[0] as $q | .[1] as $r | ($q.gates | map(.id)) as $have
        | $q + {gates: ($q.gates + [$r.gates[] | select(.id as $i | $have | index($i) | not)]),
                slowRotation: {selection: $r.selection, gates: [$r.gates[].id]}}' \
        "$OUT/quick.json" "$OUT/rotation.json" >"$OUT/gate-costs.json"
    else
      echo "::warning::the slow rotation produced no usable capture (rc '${ROTATION_RC:-}'); uploading the quick capture alone"
      cp "$OUT/quick.json" "$OUT/gate-costs.json"
    fi
    "${VALIDATE[@]}" "$OUT/gate-costs.json"
    ;;
  *)
    echo "usage: $0 quick|rotation|merge" >&2
    exit 2
    ;;
esac
