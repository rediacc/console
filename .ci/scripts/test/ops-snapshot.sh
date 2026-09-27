#!/bin/bash
# Prepared-VM snapshot for the E2E VM jobs (T2.17, PLAN-ci-time-budget).
# One subcommand per workflow step:
#
#   ops-snapshot.sh key <name>                 outputs t0, and key + enabled=true
#                                              when a snapshot can be used
#   ops-snapshot.sh restore <name> <t0>        outputs ready=true when the VMs
#                                              came back from the snapshot
#   ops-snapshot.sh prepare <name> [<config>]  outputs ready=true when the VMs
#                                              were prepared and captured
#
# The snapshot lives in $RUNNER_TEMP/ops-snapshot/<name>, and the workflow's
# cache steps carry it between runs. Every outcome appends its seconds to
# $GITHUB_STEP_SUMMARY, because the plan's 3-minute restore is a hypothesis
# until measured. Nothing here fails the job: a missing key, a failed restore
# or a failed capture leaves the test step on its normal path, which prepares
# the VMs itself and reports any real failure there.
#
# Env:
#   OPS_SNAPSHOT  'on' enables the snapshot; any other value, unset included,
#                 is the kill switch and forces the normal path.
#   GITHUB_OUTPUT, GITHUB_STEP_SUMMARY, RUNNER_TEMP  set by GitHub Actions.
#
# Outside Actions, after an E2E .env exists:
#   OPS_SNAPSHOT=on GITHUB_OUTPUT=/dev/stdout GITHUB_STEP_SUMMARY=/dev/null \
#     RUNNER_TEMP=/tmp .ci/scripts/test/ops-snapshot.sh key workers
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"
cd "$(get_repo_root)"

USAGE="usage: ops-snapshot.sh key|restore|prepare <name> [<t0>|<playwright-config>]"
CMD="${1:?$USAGE}"
NAME="${2:?$USAGE}"

# The binary the E2E harness drives (create_e2e_env --renet-path), so the key
# and the capture see the renet that provisioned the VMs.
RENET=/usr/bin/renet
ENV_FILE=packages/e2e-tests/.env
SNAP_DIR="$RUNNER_TEMP/ops-snapshot"

out() { echo "$1" >>"$GITHUB_OUTPUT"; }
note() { echo "ops-snapshot $NAME: $1" | tee -a "$GITHUB_STEP_SUMMARY"; }

case "$CMD" in
    key)
        out "t0=$(date +%s)"
        if [[ "${OPS_SNAPSHOT:-}" != "on" ]]; then
            note "off (OPS_SNAPSHOT=${OPS_SNAPSHOT:-unset}); normal preparation"
            exit 0
        fi
        require_cmd git
        if ! key="$("$RENET" ops snapshot key --name "$NAME" --env-file "$ENV_FILE")"; then
            note "no key (renet's reason is above; usually the base image is not cached yet); normal preparation"
            exit 0
        fi
        out "key=ops-snapshot-${key}-$(git -C private/renet rev-parse --short=12 HEAD)-$(date -u +%Y-%m)"
        out "enabled=true"
        ;;
    restore)
        t0="${3:?$USAGE}"
        start=$(date +%s)
        outcome=restore-failed
        if "$RENET" ops snapshot restore --name "$NAME" --from "$SNAP_DIR" --env-file "$ENV_FILE"; then
            out "ready=true"
            outcome=restored
        else
            echo "::warning title=ops snapshot::restore failed; the test step prepares the VMs the normal way"
        fi
        now=$(date +%s)
        note "cache hit, ${outcome}; restore $((now - start))s, cache download plus restore $((now - t0))s (harness steps 2-8 still run inside the test step)"
        ;;
    prepare)
        require_cmd npx
        args=(--pass-with-no-tests --grep 'ops-snapshot prepare-only run matches no test')
        [[ -n "${3:-}" ]] && args=(--config "$3" "${args[@]}")
        start=$(date +%s)
        # The suite's globalSetup (steps 1-8) runs; the grep matches no test.
        if ! (cd packages/e2e-tests && E2E_JSON_REPORT_FILE=reports/bridge-logs/ops-snapshot-prepare.json npx playwright test "${args[@]}"); then
            echo "::warning title=ops snapshot::preparation failed; the test step prepares again and reports the cause"
            note "cache miss, prepare failed after $(($(date +%s) - start))s"
            exit 0
        fi
        prepared=$(date +%s)
        outcome=save-failed
        if "$RENET" ops snapshot save --name "$NAME" --out "$SNAP_DIR" --env-file "$ENV_FILE"; then
            out "ready=true"
            outcome=saved
        else
            echo "::warning title=ops snapshot::save failed; the test step prepares the VMs the normal way"
        fi
        now=$(date +%s)
        size=$(du -sh "$SNAP_DIR" 2>/dev/null | cut -f1 || true)
        note "cache miss; prepare $((prepared - start))s, ${outcome} in $((now - prepared))s, size ${size:-0}"
        ;;
    *)
        log_error "$USAGE"
        exit 2
        ;;
esac
