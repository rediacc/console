#!/bin/bash
# The two copies of the region list must be identical.
#
# WHY. `packages/shared/src/regions/index.ts` imports `./data.json` and its
# comment says it is "a copy of the root regions.json kept in sync by the build
# process". There is no such build process. The two files are identical today
# only because somebody copied one onto the other by hand, and nothing would
# have said so if they had drifted.
#
# The drift is silent in the worst direction: `data.json` is the BAKED-IN
# fallback the CLI uses when it cannot fetch the live list, and it cannot fetch
# the live list -- `region-discovery.ts` points at `${SITE_URL}/regions.json`,
# which returns 404 (measured 2026-08-26). So the fallback is not a fallback, it
# is the ONLY path, and a stale copy of it would be what every user actually
# gets while the root file looked authoritative.
#
# This gate does not invent the sync process the comment describes. It makes the
# comment's PROMISE enforceable, which is the cheaper and more honest half: the
# files may be maintained by hand, but they can no longer diverge unnoticed.
#
# WHAT IT CANNOT SEE: whether either file's CONTENT is correct, and whether the
# live endpoint serves anything at all. The 404 is a separate, larger finding.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
# BLOCKER: log_error / log_info and get_repo_root are used throughout this gate
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd python3

REPO_ROOT="$(get_repo_root)"
cd "$REPO_ROOT"

ROOT_FILE="${REGIONS_ROOT_FILE:-regions.json}"
BAKED_FILE="${REGIONS_BAKED_FILE:-packages/shared/src/regions/data.json}"

for f in "$ROOT_FILE" "$BAKED_FILE"; do
    if [[ ! -f "$f" ]]; then
        log_error "regions-sync: $f does not exist. Nothing to compare is not a clean tree -- if the region list moved, retarget this gate deliberately."
        exit 1
    fi
    # ANTI-VACUITY. An empty or truncated file would compare "equal" to another
    # empty one and this gate would report success over two broken files.
    if [[ ! -s "$f" ]]; then
        log_error "regions-sync: $f is EMPTY, which is never a valid region list."
        exit 1
    fi
done

# Compare the PARSED json, not the bytes: formatting differences are not drift,
# and failing on them would train people to reformat rather than to reconcile.
if ! command -v python3 >/dev/null 2>&1; then
    log_error "regions-sync: python3 is required to compare the two region lists, and a comparison that cannot run is not a pass."
    exit 1
fi

norm() { python3 -c "import json,sys;print(json.dumps(json.load(open(sys.argv[1])),sort_keys=True))" "$1"; }

a="$(norm "$ROOT_FILE")" || {
    log_error "regions-sync: $ROOT_FILE is not valid JSON"
    exit 1
}
b="$(norm "$BAKED_FILE")" || {
    log_error "regions-sync: $BAKED_FILE is not valid JSON"
    exit 1
}

# The list must not be trivially small, or two near-empty files would pass.
count="$(python3 -c "
import json,sys
d=json.load(open(sys.argv[1]))
print(len(d.get('regions', d)) if isinstance(d,(dict,list)) else 0)
" "$ROOT_FILE")"
if [[ "$count" -lt 1 ]]; then
    log_error "regions-sync: $ROOT_FILE parsed to $count region(s); an empty list would make this comparison vacuous."
    exit 1
fi

if [[ "$a" != "$b" ]]; then
    log_error "regions-sync: $ROOT_FILE and $BAKED_FILE have DIVERGED."
    log_error "  $BAKED_FILE is the baked-in fallback the CLI ships with, and because"
    log_error "  \${SITE_URL}/regions.json currently 404s, that fallback is the ONLY list"
    log_error "  users ever get. A stale copy is therefore not a cosmetic mismatch."
    log_error "  Reconcile them: cp '$ROOT_FILE' '$BAKED_FILE'"
    diff <(printf '%s\n' "$a") <(printf '%s\n' "$b") | head -20 >&2 || true
    exit 1
fi

log_info "regions-sync: $ROOT_FILE and $BAKED_FILE agree ($count region(s))"
log_info "  Blind spot: proves the two copies MATCH, not that either is correct,"
log_info "  and says nothing about whether the live endpoint serves the list."
