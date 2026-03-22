#!/bin/bash
# Rotate Cloudflare account API tokens used by CI/CD.
#
# Creates (or recreates) two account-level tokens:
#   1. "Github-CD" — Workers, KV, D1, Pages, Routes, DNS (for wrangler deploy)
#   2. "Github-R2" — R2 Storage Write (S3-compatible credentials for aws cli)
#
# Then updates the corresponding GitHub org secrets.
#
# Usage:
#   CF_MANAGEMENT_TOKEN=<token> ./scripts/dev/rotate-cf-tokens.sh [--dry-run]
#   CF_API_KEY=<key> CF_EMAIL=<email> ./scripts/dev/rotate-cf-tokens.sh [--dry-run]
#   ./scripts/dev/rotate-cf-tokens.sh [--dry-run]  # interactive prompt
#
# Auth: API Token (Create Additional Tokens) or Global API Key + Email.
#
# Exit codes:
#   0 - Success
#   1 - Error

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$ROOT_DIR/.ci/scripts/lib/common.sh"

# =============================================================================
# CONFIGURATION
# =============================================================================

ACCOUNT_ID="fa51e4a18d553c30e1633288e9733d04"
GITHUB_ORG="rediacc"
CF_API_BASE="https://api.cloudflare.com/client/v4"

# --- Token 1: Github-CD (Wrangler / Workers / D1 / Pages) ---
CD_TOKEN_NAME="Github-CD"
CD_GITHUB_SECRET="CLOUDFLARE_API_TOKEN"
# Account-scoped
CD_ACCOUNT_PERMS=(
    "Workers Scripts Write"
    "Workers KV Storage Write"
    "D1 Write"
    "Pages Write"
    "Turnstile Sites Write"
)
# Zone-scoped
CD_ZONE_PERMS=(
    "Workers Routes Write"
    "DNS Read"
)

# --- Token 2: Github-R2 (S3-compatible R2 credentials) ---
# Per CF docs: Access Key ID = token id, Secret Access Key = SHA-256(token value)
# https://developers.cloudflare.com/r2/api/tokens/
R2_TOKEN_NAME="Github-R2"
R2_GITHUB_KEY_SECRET="R2_ACCESS_KEY_ID"
R2_GITHUB_SECRET_SECRET="R2_SECRET_ACCESS_KEY"
R2_GITHUB_ENDPOINT_SECRET="R2_ENDPOINT"
R2_ENDPOINT_VALUE="https://${ACCOUNT_ID}.r2.cloudflarestorage.com"
R2_ACCOUNT_PERMS=(
    "Workers R2 Storage Write"
)

# --- Turnstile secret rotation ---
# Uses existing widget sitekey, rotates the secret via CF API.
# https://developers.cloudflare.com/turnstile/get-started/widget-management/api/
TURNSTILE_GITHUB_SECRET="TURNSTILE_SECRET_KEY"

# =============================================================================
# ARGUMENT PARSING
# =============================================================================

DRY_RUN=false
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        *)
            log_error "Unknown argument: $arg"
            log_error "Usage: rotate-cf-tokens.sh [--dry-run]"
            exit 1
            ;;
    esac
done

# =============================================================================
# PREREQUISITES
# =============================================================================

require_cmd curl
require_cmd jq
require_cmd gh

# Authentication: supports API Token (Bearer) or Global API Key (X-Auth-Key + X-Auth-Email)
# Priority: CF_MANAGEMENT_TOKEN > CF_API_KEY + CF_EMAIL > interactive prompt
CF_AUTH_HEADERS=()

if [[ -n "${CF_MANAGEMENT_TOKEN:-}" ]]; then
    CF_AUTH_HEADERS=(-H "Authorization: Bearer ${CF_MANAGEMENT_TOKEN}")
elif [[ -n "${CF_API_KEY:-}" && -n "${CF_EMAIL:-}" ]]; then
    CF_AUTH_HEADERS=(-H "X-Auth-Key: ${CF_API_KEY}" -H "X-Auth-Email: ${CF_EMAIL}")
else
    echo "Authentication method:"
    echo "  1) API Token (Create Additional Tokens permission)"
    echo "  2) Global API Key + Email"
    echo -n "Choose [1/2]: "
    read -r auth_choice
    if [[ "$auth_choice" == "2" ]]; then
        echo -n "Enter email: "
        read -r CF_EMAIL
        echo -n "Enter Global API Key: "
        read -rs CF_API_KEY
        echo
        CF_AUTH_HEADERS=(-H "X-Auth-Key: ${CF_API_KEY}" -H "X-Auth-Email: ${CF_EMAIL}")
    else
        echo -n "Enter API Token: "
        read -rs CF_MANAGEMENT_TOKEN
        echo
        CF_AUTH_HEADERS=(-H "Authorization: Bearer ${CF_MANAGEMENT_TOKEN}")
    fi
fi

if [[ ${#CF_AUTH_HEADERS[@]} -eq 0 ]]; then
    log_error "Authentication credentials are required"
    exit 1
fi

# =============================================================================
# HELPERS
# =============================================================================

cf_api() {
    local method="$1" endpoint="$2"
    shift 2
    curl -s -X "$method" \
        "${CF_API_BASE}${endpoint}" \
        "${CF_AUTH_HEADERS[@]}" \
        -H "Content-Type: application/json" \
        "$@"
}

cf_check_response() {
    local response="$1" context="$2"
    local success
    success=$(echo "$response" | jq -r '.success // false')
    if [[ "$success" != "true" ]]; then
        local errors
        errors=$(echo "$response" | jq -r '.errors // [] | map(.message) | join(", ")')
        log_error "$context: $errors"
        exit 1
    fi
}

# Fetch all permission groups once (shared between both tokens)
ALL_PERM_GROUPS=""
fetch_permission_groups() {
    if [[ -n "$ALL_PERM_GROUPS" ]]; then
        return
    fi
    log_step "Fetching permission group catalog..."
    local response
    response=$(cf_api GET "/user/tokens/permission_groups")
    cf_check_response "$response" "Failed to fetch permission groups"
    ALL_PERM_GROUPS=$(echo "$response" | jq '.result')
}

# Resolve permission names to IDs
# Usage: resolve_perm_ids <scope> <name1> <name2> ...
# scope: "com.cloudflare.api.account" or "com.cloudflare.api.account.zone"
# Prints JSON array of {id} objects
resolve_perm_ids() {
    local scope="$1"
    shift
    local names_json
    names_json=$(printf '%s\n' "$@" | jq -R . | jq -s .)
    local expected=$#

    local ids
    ids=$(echo "$ALL_PERM_GROUPS" | jq --argjson names "$names_json" --arg scope "$scope" '
        [.[] | select(
            (.name as $n | $names | index($n)) and
            (.scopes | index($scope))
        ) | {id}]
    ')

    local found
    found=$(echo "$ids" | jq 'length')
    if [[ "$found" -ne "$expected" ]]; then
        log_error "Expected $expected permissions (scope: $scope), found $found"
        log_error "Required: $*"
        log_error "Available:"
        echo "$ALL_PERM_GROUPS" | jq -r --arg scope "$scope" \
            '.[] | select(.scopes | index($scope)) | "  \(.name)"' | sort
        exit 1
    fi

    echo "$ids"
}

# Find existing account token by name, print its ID (empty if not found)
find_token_by_name() {
    local name="$1"
    local page=1
    while true; do
        local response
        response=$(cf_api GET "/accounts/$ACCOUNT_ID/tokens?page=$page&per_page=50")
        cf_check_response "$response" "Failed to list account tokens"

        local token_id
        token_id=$(echo "$response" | jq -r --arg name "$name" '
            .result[] | select(.name == $name) | .id // empty
        ')
        if [[ -n "$token_id" ]]; then
            echo "$token_id"
            return
        fi

        local count
        count=$(echo "$response" | jq '.result | length')
        if [[ "$count" -lt 50 ]]; then
            break
        fi
        page=$((page + 1))
    done
}

# Delete an account token by ID
delete_token() {
    local token_id="$1" token_name="$2"
    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "[DRY-RUN] Would delete token '$token_name': $token_id"
        return
    fi
    local response
    response=$(cf_api DELETE "/accounts/$ACCOUNT_ID/tokens/$token_id")
    cf_check_response "$response" "Failed to delete token '$token_name'"
}

# Create an account token, print the full JSON response result
create_account_token() {
    local name="$1" policies="$2"
    local payload
    payload=$(jq -n \
        --arg name "$name" \
        --argjson policies "$policies" \
        '{name: $name, policies: $policies}')

    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "[DRY-RUN] Would create token '$name' with policies:"
        echo "$policies" | jq .
        return
    fi

    local response
    response=$(cf_api POST "/accounts/$ACCOUNT_ID/tokens" -d "$payload")
    cf_check_response "$response" "Failed to create token '$name'"
    echo "$response" | jq -r '.result'
}

# Update a GitHub org secret
set_github_secret() {
    local secret_name="$1" secret_value="$2"
    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "[DRY-RUN] Would update GitHub secret: $secret_name"
        return
    fi
    echo "$secret_value" | gh secret set "$secret_name" --org "$GITHUB_ORG" --visibility all
}

# Rotate a token: find existing, delete, create, return result JSON
rotate_token() {
    local name="$1" policies="$2"

    log_step "Checking for existing '$name' token..."
    local existing_id
    existing_id=$(find_token_by_name "$name")

    if [[ -n "$existing_id" ]]; then
        log_step "Found existing token ($existing_id), deleting..."
        delete_token "$existing_id" "$name"
        log_info "Deleted existing token"
    else
        log_info "No existing '$name' token found"
    fi

    log_step "Creating new '$name' token..."
    create_account_token "$name" "$policies"
}

# =============================================================================
# MAIN
# =============================================================================

log_step "Rotating Cloudflare account tokens for CI/CD"
if [[ "$DRY_RUN" == "true" ]]; then
    log_warn "DRY-RUN mode: no mutations will be performed"
fi

fetch_permission_groups

# ---- Token 1: Github-CD ----
log_step "=== Rotating CD token: $CD_TOKEN_NAME ==="

cd_acct_ids=$(resolve_perm_ids "com.cloudflare.api.account" "${CD_ACCOUNT_PERMS[@]}")
cd_zone_ids=$(resolve_perm_ids "com.cloudflare.api.account.zone" "${CD_ZONE_PERMS[@]}")

cd_policies=$(jq -n \
    --argjson acct_perms "$cd_acct_ids" \
    --argjson zone_perms "$cd_zone_ids" \
    --arg account_id "$ACCOUNT_ID" \
    '[{
        effect: "allow",
        resources: { ("com.cloudflare.api.account." + $account_id): "*" },
        permission_groups: ($acct_perms + $zone_perms)
    }]')

cd_result=$(rotate_token "$CD_TOKEN_NAME" "$cd_policies")

if [[ "$DRY_RUN" != "true" ]]; then
    cd_token_value=$(echo "$cd_result" | jq -r '.value')
    log_info "Created $CD_TOKEN_NAME token"

    log_step "Updating GitHub secret: $CD_GITHUB_SECRET..."
    set_github_secret "$CD_GITHUB_SECRET" "$cd_token_value"
    log_info "Updated $CD_GITHUB_SECRET"
fi

# ---- Token 2: Github-R2 ----
log_step "=== Rotating R2 token: $R2_TOKEN_NAME ==="

r2_acct_ids=$(resolve_perm_ids "com.cloudflare.api.account" "${R2_ACCOUNT_PERMS[@]}")

r2_policies=$(jq -n \
    --argjson acct_perms "$r2_acct_ids" \
    --arg account_id "$ACCOUNT_ID" \
    '[{
        effect: "allow",
        resources: { ("com.cloudflare.api.account." + $account_id): "*" },
        permission_groups: $acct_perms
    }]')

r2_result=$(rotate_token "$R2_TOKEN_NAME" "$r2_policies")

if [[ "$DRY_RUN" != "true" ]]; then
    # Per CF docs: Access Key ID = token id, Secret Access Key = SHA-256(token value)
    r2_access_key=$(echo "$r2_result" | jq -r '.id')
    r2_token_value=$(echo "$r2_result" | jq -r '.value')
    r2_secret_key=$(echo -n "$r2_token_value" | sha256sum | awk '{print $1}')
    log_info "Created $R2_TOKEN_NAME token"

    log_step "Updating GitHub secrets: R2 credentials..."
    set_github_secret "$R2_GITHUB_KEY_SECRET" "$r2_access_key"
    set_github_secret "$R2_GITHUB_SECRET_SECRET" "$r2_secret_key"
    set_github_secret "$R2_GITHUB_ENDPOINT_SECRET" "$R2_ENDPOINT_VALUE"
    log_info "Updated $R2_GITHUB_KEY_SECRET, $R2_GITHUB_SECRET_SECRET, $R2_GITHUB_ENDPOINT_SECRET"
fi

# ---- Turnstile secret rotation ----
log_step "=== Rotating Turnstile secret ==="

# Discover sitekey by listing widgets
turnstile_widgets=$(cf_api GET "/accounts/$ACCOUNT_ID/challenges/widgets")
if echo "$turnstile_widgets" | jq -e '.success' >/dev/null 2>&1; then
    turnstile_sitekey=$(echo "$turnstile_widgets" | jq -r '.result[0].sitekey // empty')
    if [[ -n "$turnstile_sitekey" ]]; then
        log_info "Found Turnstile widget: $turnstile_sitekey"

        if [[ "$DRY_RUN" == "true" ]]; then
            log_warn "[DRY-RUN] Would rotate Turnstile secret for sitekey: $turnstile_sitekey"
        else
            rotate_response=$(cf_api POST "/accounts/$ACCOUNT_ID/challenges/widgets/$turnstile_sitekey/rotate_secret" \
                -d '{"invalidate_immediately": false}')
            cf_check_response "$rotate_response" "Failed to rotate Turnstile secret"
            new_turnstile_secret=$(echo "$rotate_response" | jq -r '.result.secret')
            log_info "Rotated Turnstile secret"

            log_step "Updating GitHub secret: $TURNSTILE_GITHUB_SECRET..."
            set_github_secret "$TURNSTILE_GITHUB_SECRET" "$new_turnstile_secret"
            log_info "Updated $TURNSTILE_GITHUB_SECRET"
        fi
    else
        log_warn "No Turnstile widgets found, skipping"
    fi
else
    log_warn "Could not list Turnstile widgets (missing permission?), skipping"
fi

# ---- Summary ----
log_step "All tokens rotated successfully"
log_info "  CD token: $CD_TOKEN_NAME -> $CD_GITHUB_SECRET"
log_info "  R2 token: $R2_TOKEN_NAME -> $R2_GITHUB_KEY_SECRET, $R2_GITHUB_SECRET_SECRET"
log_info "  R2 endpoint: $R2_ENDPOINT_VALUE"
log_info "  Turnstile: $TURNSTILE_GITHUB_SECRET"
