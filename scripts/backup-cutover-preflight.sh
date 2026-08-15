#!/usr/bin/env bash
# backup-cutover-preflight.sh — is this deployment ready to cut over from the
# rclone/OneDrive path to the chunk store?
#
# WHY THIS EXISTS, AND WHY IT FAILS CLOSED
#
# Wave 5 of the backup-storage program migrates real machines. The credentialed
# legs (creating buckets, setting worker secrets, minting a rotation slug) are
# the operator's; everything checkable WITHOUT credentials is this script's.
#
# It fails closed on purpose. A preflight that answers "looks fine" because it
# could not reach the store is worse than no preflight: it converts an absent
# bucket into a green light, and the first thing anyone would do with that green
# light is decommission the only working restore path. Every check below either
# proves its claim or refuses; none of them degrade to a pass.
#
# It is also READ ONLY. It creates no bucket, writes no object, mints no
# credential, and makes no mutating Cloudflare or R2 call. Run it as often as
# you like against production.
#
# Usage:
#   scripts/backup-cutover-preflight.sh                  # local/plan checks only
#   BACKUP_S3_ENDPOINT=... BACKUP_S3_BUCKET=... \
#   BACKUP_S3_ACCESS_KEY_ID=... BACKUP_S3_SECRET_ACCESS_KEY=... \
#     scripts/backup-cutover-preflight.sh                # plus the live store leg
#
# Exit 0 = every check that could run PASSED and none were skipped silently.
# Exit 1 = at least one check failed, or a required input was absent.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../.ci/scripts/lib/common.sh
source "$REPO_ROOT/.ci/scripts/lib/common.sh"

FAILURES=0
CHECKS=0

pf_pass() {
    CHECKS=$((CHECKS + 1))
    log_info "$1"
}

pf_fail() {
    CHECKS=$((CHECKS + 1))
    FAILURES=$((FAILURES + 1))
    log_error "$1"
    [[ $# -lt 2 ]] || printf '      %s\n' "$2" >&2
}

# -----------------------------------------------------------------------------
# 1. The product can actually restore. Nothing else here matters if it cannot.
# -----------------------------------------------------------------------------
# This is first deliberately. The whole point of the cutover is to decommission
# rclone, and rclone is currently the ONLY way to get data back. Removing it
# before restore works is unrecoverable in the one situation backups exist for.
check_restore_verb() {
    log_step "Restore path"
    local renet="$REPO_ROOT/private/renet/bin/renet"
    if [[ ! -x "$renet" ]]; then
        pf_fail "renet binary is missing at $renet" \
            "Build it:  (cd private/renet && ./build.sh dev)"
        return
    fi
    if "$renet" backup restore --help >/dev/null 2>&1; then
        pf_pass "renet backup restore exists (probed on the binary, not assumed from source)"
    else
        pf_fail "this renet has no 'backup restore' verb" \
            "The deployed binary predates the download engine. Rebuild and redeploy."
    fi
    if "$renet" backup snapshot --help >/dev/null 2>&1; then
        pf_pass "renet backup snapshot exists"
    else
        pf_fail "this renet has no 'backup snapshot' verb"
    fi
}

# -----------------------------------------------------------------------------
# 2. The grant path the deployment will actually take
# -----------------------------------------------------------------------------
# createBackupPlane returns EARLY on the r2Binding branch, so BACKUP_S3_* is
# UNREACHABLE whenever a BACKUP_BUCKET binding exists. That is not a detail: it
# decides which grant minter production gets, and only one of the two has ever
# been accepted by live R2.
check_grant_plane() {
    log_step "Grant plane selection"
    local plane="$REPO_ROOT/private/account/src/services/backup-chunk-store.ts"
    if [[ ! -f "$plane" ]]; then
        pf_fail "private/account is not checked out; cannot verify the plane wiring"
        return
    fi
    if grep -q 'BACKUP_R2_PARENT_SECRET' "$plane"; then
        pf_pass "the R2 JWT minter is present in the tree (its selection is the question below)"
    else
        pf_fail "backup-chunk-store.ts no longer mentions BACKUP_R2_PARENT_SECRET" \
            "This preflight is out of date with the plane it checks."
    fi

    if [[ -n "${BACKUP_R2_PARENT_SECRET:-}" ]]; then
        pf_fail "BACKUP_R2_PARENT_SECRET is set, which selects the LOCALLY-SIGNED R2 JWT minter" \
            "Live R2 has never accepted a credential from that minter (see docs/backup-storage/07-execution-record.md 6.1). Unset it and use BACKUP_S3_* unless you have re-probed it."
    else
        pf_pass "BACKUP_R2_PARENT_SECRET is unset, so the unproven JWT minter is not selected"
    fi
}

# -----------------------------------------------------------------------------
# 3. The store itself — the leg that needs the operator's bucket
# -----------------------------------------------------------------------------
# FAILS CLOSED. Absent credentials are a refusal, never a skip.
check_store() {
    log_step "Chunk store reachability"
    local missing=()
    [[ -n "${BACKUP_S3_ENDPOINT:-}" ]] || missing+=(BACKUP_S3_ENDPOINT)
    [[ -n "${BACKUP_S3_BUCKET:-}" ]] || missing+=(BACKUP_S3_BUCKET)
    [[ -n "${BACKUP_S3_ACCESS_KEY_ID:-}" ]] || missing+=(BACKUP_S3_ACCESS_KEY_ID)
    [[ -n "${BACKUP_S3_SECRET_ACCESS_KEY:-}" ]] || missing+=(BACKUP_S3_SECRET_ACCESS_KEY)
    if [[ ${#missing[@]} -gt 0 ]]; then
        pf_fail "no chunk store to check: ${missing[*]} unset" \
            "This is a REFUSAL, not a skip: the cutover cannot be declared ready against a store nobody reached. Supply them, or accept that this run does not clear the cutover."
        return
    fi

    if [[ "${BACKUP_S3_BUCKET}" == "rediacc-backups" ]]; then
        pf_fail "BACKUP_S3_BUCKET is the bare production name 'rediacc-backups'" \
            "Test targets must be named distinctly (e.g. rediacc-backups-probe) so no misconfiguration can cross test and production backups."
    fi

    if ! command -v curl >/dev/null 2>&1 || ! curl --help all 2>/dev/null | grep -q -- '--aws-sigv4'; then
        pf_fail "curl lacks --aws-sigv4 (needs 7.75+), so the store leg cannot be signed"
        return
    fi

    # HEAD the bucket. Read-only, and the narrowest call that proves the triple
    # is accepted for THIS bucket rather than merely well-formed.
    #
    # `-I`, never `-X HEAD`: the latter makes curl send HEAD and then wait for a
    # response body that a HEAD reply never has, so the check hangs until the
    # timeout instead of answering. Verified the hard way.
    local code
    code=$(curl -sS -I -o /dev/null -w '%{http_code}' --max-time 20 \
        --aws-sigv4 "aws:amz:auto:s3" \
        --user "${BACKUP_S3_ACCESS_KEY_ID}:${BACKUP_S3_SECRET_ACCESS_KEY}" \
        "${BACKUP_S3_ENDPOINT%/}/${BACKUP_S3_BUCKET}" 2>/dev/null) || code=000
    case "$code" in
        200 | 204) pf_pass "the bucket ${BACKUP_S3_BUCKET} exists and the credentials are accepted for it" ;;
        403) pf_fail "403 on ${BACKUP_S3_BUCKET}: the credentials are not authorized for this bucket" ;;
        404) pf_fail "404: bucket ${BACKUP_S3_BUCKET} does not exist" "Create it before cutting over." ;;
        000) pf_fail "the endpoint ${BACKUP_S3_ENDPOINT} did not answer" ;;
        *) pf_fail "unexpected HTTP $code from ${BACKUP_S3_ENDPOINT%/}/${BACKUP_S3_BUCKET}" ;;
    esac
}

# -----------------------------------------------------------------------------
# 4. The decommission interlock
# -----------------------------------------------------------------------------
# The one ordering rule of this whole wave: nothing whose removal destroys the
# last restore path may go before the new restore is proven ON A MACHINE.
check_decommission_interlock() {
    log_step "Decommission interlock"
    local gen="$REPO_ROOT/packages/cli/src/services/backup/backup-schedule-unit-generator.ts"
    # INVERTED 2026-08-15. Until today this check demanded the rclone emission
    # still EXIST, because nothing had ever proven a restore on real hardware.
    # Both halves of that premise are now settled: e2e suite 26 is 13/13 green
    # with a byte-identical cross-machine restore driven through `rdc backup
    # restore` (the CLI, not raw renet), and the operator then decided
    # explicitly to drop OneDrive. So the emission is GONE by intent, and a
    # check still insisting on its presence would be permanently red.
    #
    # What matters now is the opposite: the generator must REFUSE a
    # non-hosted-service destination rather than emit nothing for it. Silently
    # emitting nothing is the original defect -- a timer that backs up nothing,
    # with no error anywhere -- so this asserts the refusal is still wired.
    if [[ -f "$gen" ]] && grep -q 'backup sync push' "$gen"; then
        pf_fail "the rclone schedule path is STILL PRESENT in the unit generator" \
            "It was removed on 2026-08-15 by operator decision. If it is back, either the removal was reverted or a merge resurrected it."
    elif [[ -f "$gen" ]] && grep -q 'Refusing to generate a unit that would back up nothing' "$gen"; then
        pf_pass "the rclone path is gone AND a non-hosted-service destination is refused loudly, not silently skipped"
    else
        pf_fail "the rclone path is gone but nothing refuses a non-hosted-service destination" \
            "A strategy still naming a storage destination would generate a unit that backs up NOTHING, silently. Restore the explicit throw in buildBackupCommands."
    fi
}

main() {
    log_info "Backup cutover preflight (read-only: no bucket creation, no writes, no credential minting)"
    check_restore_verb
    check_grant_plane
    check_store
    check_decommission_interlock

    printf '\n'
    if [[ $FAILURES -eq 0 ]]; then
        log_info "cutover preflight: $CHECKS checks, all passed"
        return 0
    fi
    log_error "cutover preflight: $FAILURES of $CHECKS checks FAILED — do not cut over"
    return 1
}

main "$@"
