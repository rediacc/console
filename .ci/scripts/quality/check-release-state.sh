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

log_step "listing git release tags"
tag_versions="$(rsv_list_git_tags)"
log_info "  $(wc -l <<<"$tag_versions") git tags"

log_step "asserting release-state bijection"
bijection_rc=0
rsv_assert_bijection "$cli_versions" "$tag_versions" "$IN_FLIGHT" || bijection_rc=$?

# ---------------------------------------------------------------------------
# The channel pointer must name a TAGGED version.
#
# The bijection above cannot see this class at all: a bump-none merge correctly
# skips both the sentinel and the tag, so the two sides stay in step -- while
# the R2 channel pointer was advanced anyway. That is how cli/edge/manifest.json
# came to advertise 1.3.1 with no v1.3.1 tag and a 404 notes URL, three times
# over (#573, #574, #576), and it would have half-applied a production release
# across eu/us/asia on 2026-09-01.
#
# ORDERING IS WHAT MAKES THIS SAFE ON THE RELEASE PATH: this gate runs BEFORE
# stage-artifacts (ci.yml says so), so the pointer it reads is the PREVIOUS
# release's. And the back-to-back case resolves itself -- if release X's tag is
# not pushed yet, IN_FLIGHT is vX and the pointer's X is excluded; if it is
# pushed, IN_FLIGHT is vX+1 and X has its tag.
# ---------------------------------------------------------------------------
pointer_rc=0
for channel in edge stable; do
    latest_ver=""
    manifest_ver=""
    if lj="$(aws s3 cp "s3://${RSV_BUCKET}/cli/${channel}/latest.json" - --endpoint-url "$R2_ENDPOINT" 2>/dev/null)"; then
        latest_ver="v$(printf '%s' "$lj" | sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1 | sed 's/^v//')"
        [[ "$latest_ver" == "v" ]] && latest_ver=""
    fi
    if mj="$(aws s3 cp "s3://${RSV_BUCKET}/cli/${channel}/manifest.json" - --endpoint-url "$R2_ENDPOINT" 2>/dev/null)"; then
        manifest_ver="v$(printf '%s' "$mj" | sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1 | sed 's/^v//')"
        [[ "$manifest_ver" == "v" ]] && manifest_ver=""
    fi
    log_step "asserting ${channel} channel pointer names a tagged version"
    rsv_assert_channel_pointer_tagged "$channel" "$latest_ver" "$manifest_ver" "$tag_versions" "$IN_FLIGHT" ||
        pointer_rc=1
done

if ((bijection_rc == 0 && pointer_rc == 0)); then
    log_info "release-state gate: PASS"
    exit 0
fi

if ((pointer_rc != 0)); then
    log_error "release-state gate: FAIL — a channel pointer names a version with no git tag"
    log_error "  every rdc on that channel auto-updates to a build whose release notes 404,"
    log_error "  and promote-stable will later check out that ref and fail AFTER promoting R2 + Docker"
    exit 1
fi

log_error "release-state gate: FAIL — drift between R2 sentinels and git tags"
log_error "  the findings above indicate an incomplete release or a missing tag"
log_error "  see .ci/scripts/lib/release-state-validator.sh for the invariant"
exit 1
