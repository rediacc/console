#!/bin/bash
# BLOCKER drift gate: assert R2 `.released` sentinels match git tags.
#
# Enforces the invariant documented in .ci/scripts/lib/release-state-validator.sh.
# Runs on every push to main, before stage-artifacts. Fails loud on any drift
# finding so that a half-committed release from a prior cancelled run cannot
# silently burn a version number.
#
# Env:
#   R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT  (required)
#   RELEASES_BUCKET                                      (optional, default rediacc-releases)
#   IN_FLIGHT_VERSION                                    (optional; falls back to resolve-version.sh)
#
# Exit 0 on bijection, 1 on drift. Drift is never auto-healed; the error lines
# include remediation pointers for the human.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"
# shellcheck source=../lib/release-state-validator.sh
source "$SCRIPT_DIR/../lib/release-state-validator.sh"

require_cmd aws
require_var R2_ACCESS_KEY_ID
require_var R2_SECRET_ACCESS_KEY
require_var R2_ENDPOINT
export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
export AWS_DEFAULT_REGION="auto"

IN_FLIGHT="${IN_FLIGHT_VERSION:-}"
if [[ -z "$IN_FLIGHT" ]]; then
    # Mirror what ci.yml initialize computes; keeps this gate runnable standalone.
    IN_FLIGHT="v$("$REPO_ROOT/.ci/scripts/version/resolve-version.sh" --bump-type patch)"
fi
log_info "in-flight version (excluded from bijection check): ${IN_FLIGHT}"

log_step "listing cli sentinels"
cli_versions="$(rsv_list_sentinels cli)"
log_info "  ${cli_versions:+$(wc -l <<<"$cli_versions") cli sentinels}${cli_versions:-none}"

log_step "listing desktop sentinels"
desktop_versions="$(rsv_list_sentinels desktop)"
log_info "  ${desktop_versions:+$(wc -l <<<"$desktop_versions") desktop sentinels}${desktop_versions:-none}"

log_step "listing git release tags"
tag_versions="$(rsv_list_git_tags)"
log_info "  $(wc -l <<<"$tag_versions") git tags"

log_step "asserting release-state bijection"
if rsv_assert_bijection "$cli_versions" "$desktop_versions" "$tag_versions" "$IN_FLIGHT"; then
    log_info "release-state gate: PASS"
    exit 0
fi

log_error "release-state gate: FAIL — drift between R2 sentinels and git tags"
log_error "  the findings above indicate an incomplete release or a missing tag"
log_error "  see .ci/scripts/lib/release-state-validator.sh for the invariant"
exit 1
