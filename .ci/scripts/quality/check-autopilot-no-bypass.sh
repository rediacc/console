#!/bin/bash
# Assert the rediacc-autopilot App has NO bypass on console's branch ruleset.
#
# WHY THIS IS THE LOAD-BEARING WAVE C INVARIANT. The autopilot exists to drive a
# PR to green without a human. The only thing that makes that safe is that it is
# subject to exactly the same required checks as a human contributor: it must
# never be able to merge past `CI Complete`. A bypass entry would make every
# other Wave C control decorative, and it is added in the GitHub UI, so nothing
# in this repository would otherwise notice.
#
# THE TRAP THIS GATE IS BUILT AROUND, measured not assumed. console is public, so
#   curl https://api.github.com/repos/rediacc/console/rulesets/<id>
# answers 200 WITHOUT authentication -- and the unauthenticated payload silently
# OMITS `bypass_actors` entirely (verified: top-level keys are id, name, target,
# source_type, source, enforcement, conditions, rules, node_id, created_at,
# updated_at, _links). A naive gate would fetch that, find no autopilot in a list
# that does not exist, and report PASS forever.
#
# So presence of the field is asserted BEFORE its contents. A token that cannot
# see bypass actors makes this check BLIND, and blind is not clean.
#
# Usage:
#   GITHUB_AUTOPILOT_APP_ID=<id> .ci/scripts/quality/check-autopilot-no-bypass.sh
#
# Env:
#   GITHUB_AUTOPILOT_APP_ID  required. The App ID (org variable of the same name).
#   RULESET_REPO      optional, default rediacc/console.
#
# Exits 0 when the App is absent from bypass_actors, 1 on a bypass entry, a
# blind read, an ambiguous ruleset, or unset config.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd gh
require_cmd jq

RULESET_REPO="${RULESET_REPO:-rediacc/console}"

if [[ -z "${GITHUB_AUTOPILOT_APP_ID:-}" ]]; then
    log_error "GITHUB_AUTOPILOT_APP_ID is not set."
    log_error "It is an organisation variable; pass it explicitly rather than defaulting,"
    log_error "because a wrong-or-absent id would make this gate pass against nothing."
    exit 1
fi

log_step "Checking rediacc-autopilot (app $GITHUB_AUTOPILOT_APP_ID) has no bypass on $RULESET_REPO..."

# Find the ruleset by SHAPE, not by a pinned id: ids change when a ruleset is
# recreated, and a gate pointing at a deleted id would 404 rather than protect.
if ! rulesets="$(gh api "repos/${RULESET_REPO}/rulesets" 2>/dev/null)"; then
    log_error "Could not list rulesets for ${RULESET_REPO}."
    log_error "Reading bypass actors needs a token with Administration: read."
    exit 1
fi

ids="$(echo "$rulesets" | jq -r '.[] | select(.target == "branch" and .enforcement == "active") | .id')"
count="$(echo "$ids" | grep -c . || true)"

if [[ "$count" -eq 0 ]]; then
    log_error "No ACTIVE branch ruleset on ${RULESET_REPO}."
    log_error "Either protection was removed, or this token cannot see it. Both are failures."
    exit 1
fi

rc=0
while read -r id; do
    [[ -z "$id" ]] && continue

    if ! rs="$(gh api "repos/${RULESET_REPO}/rulesets/${id}" 2>/dev/null)"; then
        log_error "Could not read ruleset ${id}."
        rc=1
        continue
    fi

    name="$(echo "$rs" | jq -r '.name')"

    # PRESENCE FIRST. See the header: an unauthenticated (or under-permissioned)
    # read returns 200 with this key missing, which would otherwise read as "no
    # bypass actors" and pass.
    if [[ "$(echo "$rs" | jq 'has("bypass_actors")')" != "true" ]]; then
        log_error "Ruleset ${id} (${name}) came back WITHOUT a bypass_actors field."
        log_error "That is a BLIND read, not a clean one: console is public, so an"
        log_error "unauthenticated GET answers 200 and omits the field entirely."
        log_error "Use a token with Administration: read."
        rc=1
        continue
    fi

    hit="$(echo "$rs" | jq -r --arg id "$GITHUB_AUTOPILOT_APP_ID" \
        '.bypass_actors[] | select((.actor_id|tostring) == $id) | "\(.actor_type)/\(.bypass_mode)"')"

    if [[ -n "$hit" ]]; then
        log_error "rediacc-autopilot (app ${GITHUB_AUTOPILOT_APP_ID}) HAS a bypass on ruleset ${id} (${name}): ${hit}"
        log_error "Remove it. The autopilot must be subject to the same required checks"
        log_error "as a human contributor, or every other Wave C control is decorative."
        rc=1
        continue
    fi

    actors="$(echo "$rs" | jq -r '[.bypass_actors[] | "\(.actor_type):\(.actor_id)"] | join(", ")')"
    log_info "OK: ruleset ${id} (${name}) bypass actors are [${actors:-none}]; autopilot absent."
done <<<"$ids"

[[ $rc -eq 0 ]] || exit 1

log_info "OK: rediacc-autopilot holds no ruleset bypass on ${RULESET_REPO}."
