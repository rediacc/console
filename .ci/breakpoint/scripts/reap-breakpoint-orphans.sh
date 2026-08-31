#!/bin/bash
# Nightly sweeper for Cloudflare objects a breakpoint session left behind.
#
# WHY THIS EXISTS AT ALL
# stop-breakpoint.sh runs from `if: always()` and is the primary teardown. Two
# paths skip `always()` ENTIRELY, so nothing in-job can ever clean up after
# them:
#   1. watchdog force-cancel -- the second cancel of a run terminates the runner
#      process rather than delivering the post-job hook, so no step runs.
#   2. runner infrastructure loss -- the VM disappears mid-job; there is no
#      process left to run anything.
# In both cases the tunnel, its DNS record and its Access application survive in
# Cloudflare with nobody left who knows they exist. This script is the ONLY
# backstop for that class, which is why it enumerates CLOUDFLARE's object list
# rather than any state the dead runner might have written: it needs zero
# cooperation from the session it is cleaning up after.
#
# HOW IT ATTRIBUTES AN OBJECT
# Every name is a pure function of $GITHUB_RUN_ID (see derive-descriptor.sh), so
# the run id can be parsed back OUT of the name and handed to GitHub: "is this
# run over?". The name is the durable channel; the descriptor file is not.
#
# Usage:
#   reap-breakpoint-orphans.sh [--dry-run] [--max-deletes <n>] [--repo <o/n>]
#
# Env: BREAKPOINT_TUNNEL_TOKEN, CLOUDFLARE_ACCOUNT_ID, GH_TOKEN
# Exit: 0 swept (including "nothing to do"), 1 missing precondition.
#
# Shape is deliberately copied from .ci/scripts/housekeeping/cleanup-versions.sh
# and cleanup-stale-d1.sh: parse_args, an ARG_DRY_RUN honoured on every
# destructive path, require_cmd/require_var preconditions, log_step phase
# banners, a phase-spanning delete budget, and a closing count line.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/breakpoint-common.sh
source "$SCRIPT_DIR/../lib/breakpoint-common.sh"

bp_load_conf "$SCRIPT_DIR"
parse_args "$@"

# =============================================================================
# CONFIGURATION
# =============================================================================

DRY_RUN="${ARG_DRY_RUN:-false}"
MAX_DELETES="${ARG_MAX_DELETES:-50}"
REPO="${ARG_REPO:-${GITHUB_REPOSITORY:-}}"

ZONE_NAME="${BREAKPOINT_TUNNEL_ZONE:-rediacc.io}"

# Labels are a CLOSED SET (breakpoint.conf). The sweep regex below is built from
# this list, so a label that is USED but not LISTED is invisible to cleanup
# FOREVER -- its objects can never be attributed to a run and will never be
# deleted by anything. derive-descriptor.sh refuses unlisted labels at creation
# time precisely to keep that from happening; this comment is the other half of
# that contract.
ALLOWED_LABELS="${BREAKPOINT_TUNNEL_LABELS:-rdc-ci rdc-dev rdc-demo}"

# Never reap an object younger than this, whatever the API says about its run.
# A cancelled run's in-job teardown may still be executing inside its post-cancel
# grace window; deleting the same objects from here at the same moment races it,
# and the loser reports a spurious failure. One hour is far longer than any
# teardown takes, and the cost of waiting is one extra idle tunnel until the
# next nightly sweep.
readonly BREAKPOINT_MIN_AGE_MINUTES=60

# Reap even when GitHub still claims the run is in_progress. 300 minutes is the
# maximum session duration breakpoint permits, plus 120 minutes of slack. A
# WEDGED runner (network-partitioned, or killed without GitHub noticing) keeps
# reporting in_progress until GitHub's own 6h job cap fires, so waiting for the
# status to change means waiting six hours for every such leak. Past this age
# the status is not evidence any more.
readonly BREAKPOINT_MAX_AGE_MINUTES=420

# Bound on API pagination. 20 pages x 100 objects is two thousand tunnels, which
# is orders of magnitude beyond any plausible leak; the cap exists so a
# malformed API response cannot spin this loop forever.
readonly MAX_LIST_PAGES=20

CF_API="https://api.cloudflare.com/client/v4"
GH_API="https://api.github.com"

# =============================================================================
# PREREQUISITES
# =============================================================================

require_cmd jq
require_cmd curl
require_var BREAKPOINT_TUNNEL_TOKEN
require_var CLOUDFLARE_ACCOUNT_ID
require_var GH_TOKEN

if [[ -z "$REPO" ]]; then
    log_error "no repository to ask about run status: pass --repo <owner/name> or set GITHUB_REPOSITORY"
    exit 1
fi

# BOTH CHECKS BELOW EXIST BECAUSE parse_args TURNS A VALUELESS FLAG INTO THE
# LITERAL STRING "true", and both failure shapes were observed:
#   --max-deletes  (no value) -> `[[ n -lt true ]]` dies with "unbound variable"
#                                under set -u, HALFWAY THROUGH a live sweep, so
#                                some objects are deleted and the rest are not.
#   --repo         (no value) -> every GitHub lookup 404s against a repo named
#                                "true", which the decision table reads as "run
#                                is gone" and REAPS every object past MAX_AGE.
# A typo must never be able to mean "delete more". Refuse before touching
# anything.
if [[ ! "$MAX_DELETES" =~ ^[0-9]+$ ]]; then
    log_error "--max-deletes must be a non-negative integer, got '$MAX_DELETES'"
    exit 1
fi

if [[ ! "$REPO" =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ ]]; then
    log_error "--repo must look like <owner>/<name>, got '$REPO'"
    log_error "a repo that resolves to nothing makes every run look deleted, which reads as 'safe to reap'"
    exit 1
fi

ACCT="$CLOUDFLARE_ACCOUNT_ID"

# =============================================================================
# HELPERS
# =============================================================================

# Delete budget, shared across both phases. Same rationale as cleanup-versions.sh:
# the real ceiling is an API rate limit shared by every call in the job, and the
# sweep is idempotent, so a capped run simply drains the rest tomorrow. A low
# default (50) is right here because a healthy steady state reaps ZERO objects --
# fifty in one night already means something is systematically wrong.
DELETES_THIS_RUN=0

deletes_budget_ok() {
    [[ $DELETES_THIS_RUN -lt $MAX_DELETES ]]
}

record_delete() {
    DELETES_THIS_RUN=$((DELETES_THIS_RUN + 1))
}

# Cloudflare request helper. Same shape as stop-breakpoint.sh so the two read
# alike; the token is the breakpoint-scoped one, not the account-wide CF token.
cf_api() {
    local method="$1" path="$2"
    curl -sS -X "$method" "${CF_API}${path}" \
        -H "Authorization: Bearer ${BREAKPOINT_TUNNEL_TOKEN}" \
        -H "Content-Type: application/json" \
        --max-time 30
}

cf_ok() { echo "$1" | jq -e '.success == true' >/dev/null 2>&1; }

# A delete that 404s is SUCCESS: the object is gone, which is the goal. Verbatim
# from stop-breakpoint.sh -- the two must agree on what "already deleted" looks
# like, because they routinely race each other on the same objects.
cf_deleted_ok() {
    local resp="$1"
    cf_ok "$resp" && return 0
    echo "$resp" | jq -e '[.errors[]?.code] | any(. == 1000 or . == 1146 or . == 10000 or . == 81044)' >/dev/null 2>&1 && return 0
    grep -qiE 'not found|does not exist' <<<"$resp" && return 0
    return 1
}

# Run status for a run id, as one of:
#   <status>    the literal GitHub .status on HTTP 200
#   __gone__    HTTP 404 -- GitHub has no such run in this repo
#   __error__   anything else, including a transport failure
#
# The 404-vs-5xx distinction is the whole point of this function. Both look like
# "no answer" to a naive caller, but one means "the run does not exist" and the
# other means "we could not ask". Only the first is ever safe to act on.
#
# NOTE ON THE `|| true`: curl -w prints its format string AND exits non-zero when
# the transfer fails, so `curl -w '%{http_code}' ... || echo "000"` yields the
# string "000000" -- the written code concatenated with the fallback. Use
# `|| true` and normalise an empty/short body instead.
gh_run_status() {
    local run_id="$1" resp code body
    resp="$(curl -sS -w $'\n%{http_code}' \
        -H "Authorization: Bearer ${GH_TOKEN}" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        --max-time 30 \
        "${GH_API}/repos/${REPO}/actions/runs/${run_id}" 2>/dev/null || true)"

    if [[ -z "$resp" ]]; then
        echo "__error__"
        return 0
    fi

    code="${resp##*$'\n'}"
    body="${resp%$'\n'*}"

    case "$code" in
        200) echo "$body" | jq -r '.status // "__error__"' 2>/dev/null || echo "__error__" ;;
        404) echo "__gone__" ;;
        *) echo "__error__" ;;
    esac
}

# Age of an ISO8601 timestamp in whole minutes, or -1 when it cannot be parsed.
# -1 is a REFUSAL, not a zero: an object we cannot date is an object we must not
# delete (same rule as should_retain() in cleanup-versions.sh).
bp_age_minutes() {
    local ts="$1" epoch now
    epoch="$(date -u -d "$ts" +%s 2>/dev/null ||
        date -u -jf "%Y-%m-%dT%H:%M:%SZ" "$ts" +%s 2>/dev/null || echo 0)"
    if [[ "$epoch" -eq 0 ]]; then
        echo "-1"
        return 0
    fi
    now="$(date -u +%s)"
    echo $(((now - epoch) / 60))
}

# THE DECISION TABLE. Stdout: "<action>|<reason>" where action is one of
# reap, reap_warn (reap AND raise a GHA warning naming the run), or skip.
#
# Every branch that declines to act says WHY, because a sweeper whose output is
# a silent "0 reaped" is indistinguishable from a sweeper that is broken.
bp_verdict() {
    local status="$1" age="$2"

    if [[ "$age" -lt 0 ]]; then
        echo "skip|creation timestamp did not parse; refusing to delete an object we cannot date"
        return 0
    fi

    case "$status" in
        completed)
            if [[ "$age" -lt "$BREAKPOINT_MIN_AGE_MINUTES" ]]; then
                echo "skip|run completed but the object is only ${age}m old; in-job teardown may still be inside its post-cancel grace"
            else
                echo "reap|run completed and the object is ${age}m old (>= ${BREAKPOINT_MIN_AGE_MINUTES}m)"
            fi
            ;;
        queued | in_progress | waiting | pending | requested)
            if [[ "$age" -lt "$BREAKPOINT_MAX_AGE_MINUTES" ]]; then
                echo "skip|run is '${status}' and the object is ${age}m old; this is a live session"
            else
                echo "reap_warn|run still reports '${status}' after ${age}m (>= ${BREAKPOINT_MAX_AGE_MINUTES}m); treating the runner as wedged"
            fi
            ;;
        __gone__)
            if [[ "$age" -lt "$BREAKPOINT_MAX_AGE_MINUTES" ]]; then
                echo "skip|GitHub returned 404 for a ${age}m-old object; a YOUNG 404 is a mangled run id or the wrong repo, not a finished run"
            else
                echo "reap|GitHub returned 404 and the object is ${age}m old; expected steady state once cleanup-versions.sh prunes old workflow runs"
            fi
            ;;
        __error__)
            echo "skip|GitHub answered inconclusively (transport error or 5xx); never reap on an answer we could not read"
            ;;
        *)
            echo "skip|unrecognised run status '${status}'; treated as inconclusive"
            ;;
    esac
}

# Zone id, resolved once and memoised.
CF_ZONE_ID=""
bp_zone_id() {
    if [[ -z "$CF_ZONE_ID" ]]; then
        CF_ZONE_ID="$(cf_api GET "/zones?name=${ZONE_NAME}" | jq -r '.result[0].id // empty' 2>/dev/null || true)"
    fi
    echo "$CF_ZONE_ID"
}

# Sessions already reaped this run, keyed "<label>/<run-id>", so phase 2 does not
# redo phase 1's work object by object.
declare -A REAPED_SESSIONS=()

EXAMINED=0
REAPED=0
SKIPPED=0
FAILED_DELETES=0

# bp_reap_session <label> <run-id> <found-by>
#
# ORDER IS LOAD-BEARING: DNS, then Access, then the tunnel. Deleting the Access
# application first would leave the hostname resolving and UNAUTHENTICATED for
# the width of the remaining calls -- a brief window in which anyone who guessed
# the (public, run-id-derived) name reaches the origin. Removing DNS first ends
# reachability before the authentication in front of it is removed.
#
# Reaping the full triple from either phase is intentional: a lookup for an
# object that is already gone returns empty and no-ops, so this is idempotent and
# self-healing regardless of which listing found the session.
bp_reap_session() {
    local label="$1" run_id="$2" found_by="$3"
    local key="${label}/${run_id}"

    if [[ -n "${REAPED_SESSIONS[$key]:-}" ]]; then
        log_debug "already reaped $key (found again via $found_by)"
        return 0
    fi
    REAPED_SESSIONS["$key"]=1

    local hostname_full tunnel_name
    hostname_full="$("$SCRIPT_DIR/derive-descriptor.sh" --field hostname --label "$label" --run-id "$run_id" 2>/dev/null || true)"
    tunnel_name="$("$SCRIPT_DIR/derive-descriptor.sh" --field name --label "$label" --run-id "$run_id" 2>/dev/null || true)"

    if [[ -z "$hostname_full" ]] || [[ -z "$tunnel_name" ]]; then
        log_warn "  could not derive a descriptor for label='$label' run-id='$run_id'; skipping"
        SKIPPED=$((SKIPPED + 1))
        return 0
    fi

    local zone_id
    zone_id="$(bp_zone_id)"

    # --- DNS ----------------------------------------------------------------
    if [[ -n "$zone_id" ]]; then
        local dns_ids
        dns_ids="$(cf_api GET "/zones/${zone_id}/dns_records?name=${hostname_full}&type=CNAME" |
            jq -r '.result[]? | select(.content | endswith(".cfargotunnel.com")) | .id' 2>/dev/null || true)"
        while IFS= read -r dns_id; do
            [[ -z "$dns_id" ]] && continue
            if ! deletes_budget_ok; then
                log_warn "  hit --max-deletes=$MAX_DELETES; remaining objects deferred to the next sweep"
                return 0
            fi
            if [[ "$DRY_RUN" == "true" ]]; then
                log_warn "  [DRY-RUN] would delete DNS record ${hostname_full} (id ${dns_id})"
            else
                local resp
                resp="$(cf_api DELETE "/zones/${zone_id}/dns_records/${dns_id}")"
                if cf_deleted_ok "$resp"; then
                    log_info "  deleted DNS record ${hostname_full}"
                    record_delete
                else
                    log_error "  DNS delete FAILED for ${hostname_full}: $resp"
                    FAILED_DELETES=$((FAILED_DELETES + 1))
                fi
            fi
        done <<<"$dns_ids"
    fi

    # --- ACCESS -------------------------------------------------------------
    local app_ids
    app_ids="$(cf_api GET "/accounts/${ACCT}/access/apps" |
        jq -r --arg d "$hostname_full" '.result[]? | select(.domain == $d) | .id' 2>/dev/null || true)"
    while IFS= read -r app_id; do
        [[ -z "$app_id" ]] && continue
        if ! deletes_budget_ok; then
            log_warn "  hit --max-deletes=$MAX_DELETES; remaining objects deferred to the next sweep"
            return 0
        fi
        if [[ "$DRY_RUN" == "true" ]]; then
            log_warn "  [DRY-RUN] would delete Access application for ${hostname_full} (id ${app_id})"
        else
            local resp
            resp="$(cf_api DELETE "/accounts/${ACCT}/access/apps/${app_id}")"
            if cf_deleted_ok "$resp"; then
                log_info "  deleted Access application for ${hostname_full} (policies cascade)"
                record_delete
            else
                log_error "  Access delete FAILED for ${hostname_full}: $resp"
                FAILED_DELETES=$((FAILED_DELETES + 1))
            fi
        fi
    done <<<"$app_ids"

    # --- TUNNEL -------------------------------------------------------------
    local tunnel_id
    tunnel_id="$(cf_api GET "/accounts/${ACCT}/cfd_tunnel?name=${tunnel_name}&is_deleted=false" |
        jq -r '.result[0].id // empty' 2>/dev/null || true)"
    if [[ -n "$tunnel_id" ]]; then
        if ! deletes_budget_ok; then
            log_warn "  hit --max-deletes=$MAX_DELETES; remaining objects deferred to the next sweep"
            return 0
        fi
        if [[ "$DRY_RUN" == "true" ]]; then
            log_warn "  [DRY-RUN] would delete tunnel ${tunnel_name} (id ${tunnel_id}, cascade=true)"
        else
            # cascade=true is mandatory, not defensive: a tunnel whose connector
            # died uncleanly still holds a connection record and REFUSES a plain
            # delete. Every orphan this script reaps is by definition one whose
            # connector died uncleanly.
            local resp
            resp="$(cf_api DELETE "/accounts/${ACCT}/cfd_tunnel/${tunnel_id}?cascade=true")"
            if cf_deleted_ok "$resp"; then
                log_info "  deleted tunnel ${tunnel_name}"
                record_delete
            else
                log_error "  tunnel delete FAILED for ${tunnel_name}: $resp"
                FAILED_DELETES=$((FAILED_DELETES + 1))
            fi
        fi
    fi

    REAPED=$((REAPED + 1))
}

# bp_handle <label> <run-id> <created-at> <found-by> <human-label>
# Applies the decision table to one candidate and reaps it if the verdict says so.
bp_handle() {
    local label="$1" run_id="$2" created_at="$3" found_by="$4" human="$5"
    local age status verdict action reason

    EXAMINED=$((EXAMINED + 1))

    age="$(bp_age_minutes "$created_at")"
    status="$(gh_run_status "$run_id")"
    verdict="$(bp_verdict "$status" "$age")"
    action="${verdict%%|*}"
    reason="${verdict#*|}"

    case "$action" in
        skip)
            log_info "  SKIP $human -- $reason"
            SKIPPED=$((SKIPPED + 1))
            ;;
        reap_warn)
            bp_gha_warning "breakpoint orphan reaped while its run still reported live: ${human} (run ${REPO}#${run_id}) -- $reason"
            log_step "  REAP $human -- $reason"
            bp_reap_session "$label" "$run_id" "$found_by"
            ;;
        reap)
            log_step "  REAP $human -- $reason"
            bp_reap_session "$label" "$run_id" "$found_by"
            ;;
        *)
            log_warn "  SKIP $human -- unexpected verdict '$action'"
            SKIPPED=$((SKIPPED + 1))
            ;;
    esac
}

# Regex alternation over the closed label set, e.g. "rdc-ci|rdc-dev|rdc-demo".
LABEL_ALT=""
for allowed in $ALLOWED_LABELS; do
    if [[ -n "$LABEL_ALT" ]]; then
        LABEL_ALT="${LABEL_ALT}|"
    fi
    LABEL_ALT="${LABEL_ALT}${allowed}"
done
TUNNEL_RE="^breakpoint-(${LABEL_ALT})-([0-9]+)$"
ZONE_RE="${ZONE_NAME//./\\.}"
HOSTNAME_RE="^(${LABEL_ALT})-([0-9]+)\.${ZONE_RE}$"

# Objects returned by each listing, matching or not. Zero across all three is the
# anti-vacuity trip: it means the token cannot SEE, which looks identical to a
# clean account from the outside.
LISTED_TUNNELS=0
LISTED_DNS=0
LISTED_ACCESS=0

if [[ "$DRY_RUN" == "true" ]]; then
    log_warn "DRY-RUN: nothing will be deleted; every decision is still evaluated and printed"
fi
log_info "repo=$REPO zone=$ZONE_NAME labels='$ALLOWED_LABELS' max-deletes=$MAX_DELETES"

# =============================================================================
# PHASE 1: TUNNELS
# =============================================================================

log_step "Phase 1: Cloudflare tunnels named breakpoint-<label>-<run-id>"

page=1
while [[ $page -le $MAX_LIST_PAGES ]]; do
    resp="$(cf_api GET "/accounts/${ACCT}/cfd_tunnel?is_deleted=false&per_page=100&page=${page}" 2>/dev/null || echo '{"success":false}')"
    if ! cf_ok "$resp"; then
        log_warn "  tunnel list failed on page $page; the token may lack Cloudflare Tunnel:Read"
        break
    fi

    count="$(echo "$resp" | jq '.result | length' 2>/dev/null || echo 0)"
    LISTED_TUNNELS=$((LISTED_TUNNELS + count))

    entries="$(echo "$resp" | jq -c '.result[]? | {name: .name, created_at: .created_at}' 2>/dev/null || true)"
    while IFS= read -r entry; do
        [[ -z "$entry" ]] && continue
        name="$(echo "$entry" | jq -r '.name // empty')"
        created_at="$(echo "$entry" | jq -r '.created_at // empty')"
        [[ -z "$name" ]] && continue

        if [[ ! "$name" =~ $TUNNEL_RE ]]; then
            log_debug "  ignoring non-breakpoint tunnel '$name'"
            continue
        fi
        bp_handle "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" "$created_at" "tunnel" "tunnel '$name'"
    done <<<"$entries"

    if [[ "$count" -lt 100 ]]; then
        break
    fi
    page=$((page + 1))
done

# =============================================================================
# PHASE 2: ORPHANED SATELLITES
# =============================================================================
# Swept INDEPENDENTLY rather than by walking outward from the tunnels found in
# phase 1, because the interesting orphan is exactly the one phase 1 cannot see:
# a teardown where the tunnel delete SUCCEEDED and the DNS delete FAILED leaves a
# CNAME with no tunnel behind it. Walking outward from tunnels would never visit
# it, and it would resolve forever.

log_step "Phase 2a: orphaned CNAME records under ${ZONE_NAME}"

ZONE_ID="$(bp_zone_id)"
if [[ -z "$ZONE_ID" ]]; then
    log_warn "  could not resolve zone id for ${ZONE_NAME}; the token may lack Zone:Read (DNS sweep skipped)"
else
    page=1
    while [[ $page -le $MAX_LIST_PAGES ]]; do
        resp="$(cf_api GET "/zones/${ZONE_ID}/dns_records?type=CNAME&per_page=100&page=${page}" 2>/dev/null || echo '{"success":false}')"
        if ! cf_ok "$resp"; then
            log_warn "  DNS list failed on page $page; the token may lack Zone.DNS:Read"
            break
        fi

        count="$(echo "$resp" | jq '.result | length' 2>/dev/null || echo 0)"
        LISTED_DNS=$((LISTED_DNS + count))

        entries="$(echo "$resp" | jq -c '.result[]? | {name: .name, content: .content, created_on: .created_on}' 2>/dev/null || true)"
        while IFS= read -r entry; do
            [[ -z "$entry" ]] && continue
            name="$(echo "$entry" | jq -r '.name // empty')"
            content="$(echo "$entry" | jq -r '.content // empty')"
            created_on="$(echo "$entry" | jq -r '.created_on // empty')"
            [[ -z "$name" ]] && continue

            # Both halves must hold: the NAME proves it is ours, the CONTENT
            # proves it is a tunnel CNAME and not some hand-made record that
            # happens to collide with the grammar.
            if [[ ! "$name" =~ $HOSTNAME_RE ]]; then
                continue
            fi
            case "$content" in
                *.cfargotunnel.com) ;;
                *)
                    log_debug "  ignoring '$name': content '$content' is not a tunnel target"
                    continue
                    ;;
            esac
            bp_handle "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" "$created_on" "dns" "DNS record '$name'"
        done <<<"$entries"

        if [[ "$count" -lt 100 ]]; then
            break
        fi
        page=$((page + 1))
    done
fi

log_step "Phase 2b: orphaned Access applications"

page=1
while [[ $page -le $MAX_LIST_PAGES ]]; do
    resp="$(cf_api GET "/accounts/${ACCT}/access/apps?per_page=100&page=${page}" 2>/dev/null || echo '{"success":false}')"
    if ! cf_ok "$resp"; then
        log_warn "  Access app list failed on page $page; the token may lack Access: Apps and Policies:Read"
        break
    fi

    count="$(echo "$resp" | jq '.result | length' 2>/dev/null || echo 0)"
    LISTED_ACCESS=$((LISTED_ACCESS + count))

    entries="$(echo "$resp" | jq -c '.result[]? | {domain: .domain, created_at: .created_at}' 2>/dev/null || true)"
    while IFS= read -r entry; do
        [[ -z "$entry" ]] && continue
        domain="$(echo "$entry" | jq -r '.domain // empty')"
        created_at="$(echo "$entry" | jq -r '.created_at // empty')"
        [[ -z "$domain" ]] && continue

        if [[ ! "$domain" =~ $HOSTNAME_RE ]]; then
            continue
        fi
        bp_handle "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" "$created_at" "access" "Access app '$domain'"
    done <<<"$entries"

    if [[ "$count" -lt 100 ]]; then
        break
    fi
    page=$((page + 1))
done

# =============================================================================
# SUMMARY
# =============================================================================

# ANTI-VACUITY. Three listings returning nothing at all is far more likely to be
# a token missing Tunnel/DNS/Access READ scope than an account with no objects in
# it -- and the two are indistinguishable from the exit code. A sweeper that
# silently asserts "nothing to do" is how this entire class of bug comes back, so
# say it out loud.
if [[ $((LISTED_TUNNELS + LISTED_DNS + LISTED_ACCESS)) -eq 0 ]]; then
    bp_gha_warning "breakpoint sweeper saw ZERO objects in all three listings (tunnels, DNS, Access). Either the account is genuinely empty, or BREAKPOINT_TUNNEL_TOKEN lacks Tunnel:Read / Zone.DNS:Read / Access:Read. Verify the token before trusting this result."
fi

log_info "listings: ${LISTED_TUNNELS} tunnel(s), ${LISTED_DNS} CNAME(s), ${LISTED_ACCESS} Access app(s)"
if [[ "$DRY_RUN" == "true" ]]; then
    log_info "summary: examined ${EXAMINED} breakpoint object(s), would reap ${REAPED} session(s), skipped ${SKIPPED}"
else
    log_info "summary: examined ${EXAMINED} breakpoint object(s), reaped ${REAPED} session(s), skipped ${SKIPPED}"
fi

if [[ $FAILED_DELETES -gt 0 ]]; then
    log_error "${FAILED_DELETES} delete(s) failed; the objects are still there and the next sweep will retry them"
    exit 1
fi

log_info "sweep complete"
