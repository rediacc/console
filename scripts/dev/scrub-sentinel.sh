#!/bin/bash
# Scrub a release sentinel and its versioned bytes from R2.
#
# Used as the recovery path referenced by the drift gate when it flags
# "cli sentinel present, git tag missing". A sentinel exists only if
# write-release-sentinel.sh completed successfully, which means the bytes are
# considered released by the invariant. If the downstream tag never happened
# (CD failed after finalize), the operator has two choices:
#   1. Re-run CD to create the missing tag (preferred — keeps the bytes).
#   2. Scrub the sentinel + bytes via this script so the version number is
#      freed and the next CI run can reclaim it.
#
# This script is interactive-safe: dry-run is default, an explicit --execute
# is required to delete. Deletions are recoverable only if the R2 bucket has
# object versioning enabled (we assume it does not; the scrub is authoritative).
#
# Usage:
#   scripts/dev/scrub-sentinel.sh v1.0.5                  # dry-run
#   scripts/dev/scrub-sentinel.sh v1.0.5 --execute        # actually delete
#   scripts/dev/scrub-sentinel.sh v1.0.5 --execute --yes  # skip confirmation
#
# Env (required):
#   R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT
#   RELEASES_BUCKET (optional, default rediacc-releases)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=../../.ci/scripts/lib/common.sh
source "$REPO_ROOT/.ci/scripts/lib/common.sh"
# shellcheck source=../../.ci/scripts/lib/release-state-validator.sh
source "$REPO_ROOT/.ci/scripts/lib/release-state-validator.sh"

VERSION=""
EXECUTE=false
SKIP_CONFIRM=false

for arg in "$@"; do
    case "$arg" in
        --execute) EXECUTE=true ;;
        --yes | -y) SKIP_CONFIRM=true ;;
        --help | -h)
            sed -n '2,30p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        v[0-9]*)
            [[ -n "$VERSION" ]] && { log_error "only one version argument"; exit 2; }
            VERSION="$arg"
            ;;
        *) log_error "unknown argument: $arg"; exit 2 ;;
    esac
done

if [[ -z "$VERSION" ]]; then
    log_error "usage: scrub-sentinel.sh v<MAJOR>.<MINOR>.<PATCH> [--execute] [--yes]"
    exit 2
fi
if [[ ! "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    log_error "invalid version '$VERSION' (expected strict semver, e.g. v1.0.5)"
    exit 2
fi

require_cmd aws
require_var R2_ACCESS_KEY_ID
require_var R2_SECRET_ACCESS_KEY
require_var R2_ENDPOINT
export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
export AWS_DEFAULT_REGION="auto"

log_step "scrub plan for ${VERSION}"
for product in cli desktop; do
    local_prefix="${product}/${VERSION}/"
    echo "  s3://${RSV_BUCKET}/${local_prefix}"
    if rsv_sentinel_exists "$product" "$VERSION"; then
        echo "    sentinel: PRESENT (will be deleted)"
    else
        echo "    sentinel: absent"
    fi
    count="$(aws s3 ls "s3://${RSV_BUCKET}/${local_prefix}" \
        --endpoint-url "$R2_ENDPOINT" --recursive 2>/dev/null | wc -l)"
    echo "    objects: ${count}"
done

# Safety cross-check: if a git tag exists for this version, refuse to scrub
# without explicit acknowledgment. A scrub that removes bytes behind a live
# release tag is almost always a mistake.
if git -C "$REPO_ROOT" rev-parse --verify "refs/tags/${VERSION}" >/dev/null 2>&1; then
    log_warn "git tag ${VERSION} exists in ${REPO_ROOT}"
    log_warn "  scrubbing bytes that back a live release tag will break installs"
    log_warn "  reconsider re-running CD for ${VERSION} instead"
    if [[ "$EXECUTE" == "true" && "$SKIP_CONFIRM" == "false" ]]; then
        read -r -p "type 'YES I UNDERSTAND' to proceed: " confirm
        [[ "$confirm" == "YES I UNDERSTAND" ]] || { log_error "aborted"; exit 1; }
    fi
fi

if [[ "$EXECUTE" != "true" ]]; then
    log_info "dry-run: pass --execute to delete"
    exit 0
fi

if [[ "$SKIP_CONFIRM" != "true" ]]; then
    read -r -p "delete the listed prefixes? [y/N] " ack
    [[ "$ack" == "y" || "$ack" == "Y" ]] || { log_error "aborted"; exit 1; }
fi

for product in cli desktop; do
    local_prefix="${product}/${VERSION}/"
    log_step "deleting s3://${RSV_BUCKET}/${local_prefix}"
    aws s3 rm "s3://${RSV_BUCKET}/${local_prefix}" \
        --endpoint-url "$R2_ENDPOINT" \
        --recursive
done
log_info "scrubbed ${VERSION}"
