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
#   export CF_API_KEY="<global-api-key>"
#   export CF_EMAIL="<cloudflare-account-email>"
#   export AWS_SES_ADMIN_KEY_ID="<iam-admin-access-key-id>"
#   export AWS_SES_ADMIN_SECRET="<iam-admin-secret-access-key>"
#   ./scripts/dev/rotate-secrets.sh [--dry-run] [--rotate-turnstile] [--keep-credentials]
#
# Auth:
#   Cloudflare:
#     CF_API_KEY + CF_EMAIL  - Global API Key (simplest, auto-creates a scoped token)
#     CF_MANAGEMENT_TOKEN    - Pre-created scoped API token (if you have one)
#     Interactive prompt     - Asks for either of the above
#     Get your Global API Key: https://dash.cloudflare.com/profile/api-tokens
#
#   AWS SES:   AWS_SES_ADMIN_KEY_ID + AWS_SES_ADMIN_SECRET
#     IAM admin/root credentials with permission to manage keys for rediacc-ses-eu and rediacc-ses-us.
#     Your own credentials: https://us-east-1.console.aws.amazon.com/iam/home#/security_credentials
#     SES EU user:          https://us-east-1.console.aws.amazon.com/iam/home#/users/details/rediacc-ses-eu?section=security_credentials
#     SES US user:          https://us-east-1.console.aws.amazon.com/iam/home#/users/details/rediacc-ses-us?section=security_credentials
#
# Flags:
#   --dry-run           Show what would be done without making changes
#   --rotate-turnstile  Include Turnstile secret rotation (skipped by default due to 2hr grace period)
#   --keep-credentials  Skip self-destruct (keep CF token + AWS admin key alive after rotation)
#
# Exit codes:
#   0 - Success
#   1 - Error

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$ROOT_DIR/.ci/scripts/lib/common.sh"
source "$SCRIPT_DIR/lib/cf-auth.sh"

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
    "Workers R2 Storage Write"
    "Workers AI Read"
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

# --- AWS SES credential rotation (multi-region) ---
# Each region has a dedicated IAM user scoped to its SES region.
# Auth: AWS_SES_ADMIN_KEY_ID + AWS_SES_ADMIN_SECRET env vars (IAM admin that can manage both users).
AWS_IAM_USER_EU="rediacc-ses-eu"
SES_EU_GITHUB_KEY_SECRET="AWS_SES_ACCESS_KEY_ID_EU"
SES_EU_GITHUB_SECRET_SECRET="AWS_SES_SECRET_ACCESS_KEY_EU"

AWS_IAM_USER_US="rediacc-ses-us"
SES_US_GITHUB_KEY_SECRET="AWS_SES_ACCESS_KEY_ID_US"
SES_US_GITHUB_SECRET_SECRET="AWS_SES_SECRET_ACCESS_KEY_US"

# TODO: Non-worker secret stores that also need updating after rotation:
#
# 1. Docker containers on machines:
#    - private/middleware/docker-compose.yml: TURNSTILE_SECRET_KEY (TurnstileValidator.cs)
#    - private/account/docker-compose.yml: AWS_SES_ACCESS_KEY_ID, AWS_SES_SECRET_ACCESS_KEY,
#      TURNSTILE_SECRET_KEY, CLOUDFLARE_API_TOKEN
#    Requires restarting containers with updated env after rotation.
#
# 2. SQL HA cluster:
#    - private/sql/coordinator/wrangler.toml: CLOUDFLARE_API_TOKEN (runtime secret for DNS/certs/failover)
#    - private/sql/lib/dns.sh, commands/cert.sh, commands/ha.sh: CLOUDFLARE_API_TOKEN
#    Needs wrangler secret put or manual env update on machines.
#
# 3. Local development:
#    - private/account/.env: updated automatically by this script (if file exists, skipped in CI)

# =============================================================================
# ARGUMENT PARSING
# =============================================================================

DRY_RUN=false
ROTATE_TURNSTILE=false
KEEP_CREDENTIALS=false
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --rotate-turnstile) ROTATE_TURNSTILE=true ;;
        --keep-credentials) KEEP_CREDENTIALS=true ;;
        *)
            log_error "Unknown argument: $arg"
            log_error "Usage: rotate-secrets.sh [--dry-run] [--rotate-turnstile] [--keep-credentials]"
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
require_cmd aws

resolve_cf_auth
resolve_aws_auth

if [[ "$KEEP_CREDENTIALS" != "true" ]]; then
    check_self_destruct_capable
fi

# =============================================================================
# PREFLIGHT CHECKS (all-or-nothing: verify everything before any mutations)
# =============================================================================

log_step "Running preflight checks..."
preflight_failed=false

# 1. Cloudflare API access
cf_verify=$(curl -s -X GET "${CF_API_BASE}/user/tokens/verify" "${CF_AUTH_HEADERS[@]}" -H "Content-Type: application/json" 2>/dev/null)
if ! echo "$cf_verify" | jq -e '.success' >/dev/null 2>&1; then
    # Global API Key uses a different verification endpoint
    cf_verify=$(curl -s -X GET "${CF_API_BASE}/user" "${CF_AUTH_HEADERS[@]}" -H "Content-Type: application/json" 2>/dev/null)
    if ! echo "$cf_verify" | jq -e '.success' >/dev/null 2>&1; then
        log_error "Preflight: Cloudflare API authentication failed"
        preflight_failed=true
    fi
fi
[[ "$preflight_failed" != "true" ]] && log_info "Cloudflare API: authenticated"

# 2. GitHub CLI access
if ! gh auth status >/dev/null 2>&1; then
    log_error "Preflight: GitHub CLI not authenticated (run 'gh auth login')"
    preflight_failed=true
else
    log_info "GitHub CLI: authenticated"
fi

# 3. AWS SES credentials
if ! aws sts get-caller-identity >/dev/null 2>&1; then
    log_error "Preflight: AWS_SES_ADMIN_KEY_ID/AWS_SES_ADMIN_SECRET credentials are invalid"
    preflight_failed=true
else
    log_info "AWS IAM: accessible"
fi

# 4. Turnstile widget exists (skip check if --skip-turnstile)
if [[ "$ROTATE_TURNSTILE" != "true" ]]; then
    log_info "Turnstile: skipped (pass --rotate-turnstile to include)"
else
    ts_preflight=$(curl -s -X GET "${CF_API_BASE}/accounts/$ACCOUNT_ID/challenges/widgets" "${CF_AUTH_HEADERS[@]}" -H "Content-Type: application/json" 2>/dev/null)
    if ! echo "$ts_preflight" | jq -e '.success' >/dev/null 2>&1; then
        log_error "Preflight: Cannot access Turnstile API"
        preflight_failed=true
    elif [[ -z "$(echo "$ts_preflight" | jq -r '.result[0].sitekey // empty')" ]]; then
        log_error "Preflight: No Turnstile widgets found in account"
        preflight_failed=true
    else
        log_info "Turnstile: widget found"
    fi
fi

# 5. Can list workers (needed for sync step)
wk_preflight=$(curl -s -X GET "${CF_API_BASE}/accounts/$ACCOUNT_ID/workers/scripts" "${CF_AUTH_HEADERS[@]}" -H "Content-Type: application/json" 2>/dev/null)
if ! echo "$wk_preflight" | jq -e '.success' >/dev/null 2>&1; then
    log_error "Preflight: Cannot list Cloudflare Workers"
    preflight_failed=true
else
    wk_count=$(echo "$wk_preflight" | jq '.result | length')
    log_info "Workers API: $wk_count worker(s) found"
fi

if [[ "$preflight_failed" == "true" ]]; then
    log_error "Preflight checks failed. Aborting to prevent partial rotation."
    log_error "Fix the issues above and re-run."
    exit 1
fi
log_info "All preflight checks passed"

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
    echo "$secret_value" | gh secret set "$secret_name" --org "$GITHUB_ORG" --visibility selected --repos "console"
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

# Push a single secret to a deployed Worker via CF API.
# Returns 0 on success, 1 on failure (does NOT exit the script).
sync_worker_secret() {
    local worker="$1" secret_name="$2" secret_value="$3"
    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "[DRY-RUN] Would sync secret '$secret_name' to worker '$worker'"
        return 0
    fi
    local payload
    payload=$(jq -n \
        --arg name "$secret_name" \
        --arg text "$secret_value" \
        '{name: $name, text: $text, type: "secret_text"}')
    local response
    response=$(cf_api PUT "/accounts/$ACCOUNT_ID/workers/scripts/$worker/secrets" -d "$payload") || return 1
    local success
    success=$(echo "$response" | jq -r '.success // false')
    if [[ "$success" != "true" ]]; then
        local errors
        errors=$(echo "$response" | jq -r '.errors // [] | map(.message) | join(", ")')
        log_error "Failed to sync '$secret_name' to worker '$worker': $errors"
        return 1
    fi
    return 0
}

# Sync rotated secrets to live workers.
# For each worker, queries its actual bound secrets via CF API, intersects with
# what was rotated, and only pushes the overlap. No assumptions about which
# secrets a worker uses -- we check every time.
# Returns the number of workers that had at least one sync failure.
# Determine the data region for a given worker name.
# EU workers get EU SES credentials, US workers get US SES credentials.
# Returns "eu" or "us".
worker_region() {
    local worker="$1"
    case "$worker" in
        rediacc-account-us | edge-rediacc-account-us) echo "us" ;;
        *) echo "eu" ;;
    esac
}

sync_secrets_to_workers() {
    log_step "=== Syncing rotated secrets to live workers ==="

    # Collect rotated secrets that are allowed to be synced to workers.
    # Only runtime secrets go here -- never CI/CD-only tokens (CLOUDFLARE_API_TOKEN, R2_*).
    # An attacker who binds a CI/CD secret name to a worker should not receive the real value.
    #
    # Global secrets: same value for all workers (e.g., Turnstile).
    # Regional secrets: same secret NAME on the worker, but different VALUE per region.
    # Workers use AWS_SES_ACCESS_KEY_ID/AWS_SES_SECRET_ACCESS_KEY regardless of region --
    # the regional value is injected here based on worker name.
    local -a global_names=() global_values=()
    local -a eu_names=() eu_values=()
    local -a us_names=() us_values=()

    if [[ -n "${new_turnstile_secret:-}" ]]; then
        global_names+=("TURNSTILE_SECRET_KEY")
        global_values+=("$new_turnstile_secret")
    fi
    if [[ -n "${new_ses_key_id_eu:-}" ]]; then
        eu_names+=("AWS_SES_ACCESS_KEY_ID")
        eu_values+=("$new_ses_key_id_eu")
    fi
    if [[ -n "${new_ses_secret_eu:-}" ]]; then
        eu_names+=("AWS_SES_SECRET_ACCESS_KEY")
        eu_values+=("$new_ses_secret_eu")
    fi
    if [[ -n "${new_ses_key_id_us:-}" ]]; then
        us_names+=("AWS_SES_ACCESS_KEY_ID")
        us_values+=("$new_ses_key_id_us")
    fi
    if [[ -n "${new_ses_secret_us:-}" ]]; then
        us_names+=("AWS_SES_SECRET_ACCESS_KEY")
        us_values+=("$new_ses_secret_us")
    fi

    local total=$((${#global_names[@]} + ${#eu_names[@]} + ${#us_names[@]}))
    if [[ "$total" -eq 0 ]]; then
        log_info "No secrets were rotated, skipping worker sync"
        return 0
    fi

    log_info "Rotated global secrets: ${global_names[*]:-(none)}"
    log_info "Rotated EU SES secrets: ${eu_names[*]:-(none)}"
    log_info "Rotated US SES secrets: ${us_names[*]:-(none)}"

    # Discover live workers
    log_step "Listing workers in account..."
    local page=1 all_workers=""
    while true; do
        local response
        response=$(cf_api GET "/accounts/$ACCOUNT_ID/workers/scripts?page=$page&per_page=100")
        cf_check_response "$response" "Failed to list workers"
        local names
        names=$(echo "$response" | jq -r '.result[].id // empty')
        all_workers+=$'\n'"$names"
        local count
        count=$(echo "$response" | jq '.result | length')
        if [[ "$count" -lt 100 ]]; then
            break
        fi
        page=$((page + 1))
    done

    # Filter to target workers (current + future regional workers)
    local -a target_workers=()
    while IFS= read -r name; do
        [[ -z "$name" ]] && continue
        case "$name" in
            rediacc-www | edge-rediacc-www | rediacc-account-eu | edge-rediacc-account-eu | rediacc-account-us | edge-rediacc-account-us | pr-*)
                target_workers+=("$name")
                ;;
        esac
    done <<<"$all_workers"

    if [[ ${#target_workers[@]} -eq 0 ]]; then
        log_warn "No target workers found"
        return 0
    fi

    log_info "Target workers (${#target_workers[@]}): ${target_workers[*]}"

    # For each worker: query its secrets, intersect with rotated, push matches
    local failed_workers=0
    for worker in "${target_workers[@]}"; do
        log_step "Checking secrets on worker: $worker"

        local region
        region=$(worker_region "$worker")

        # Build the effective secret list for this worker: global + regional
        local -a effective_names=("${global_names[@]}")
        local -a effective_values=("${global_values[@]}")
        if [[ "$region" == "us" ]]; then
            effective_names+=("${us_names[@]}")
            effective_values+=("${us_values[@]}")
        else
            effective_names+=("${eu_names[@]}")
            effective_values+=("${eu_values[@]}")
        fi

        if [[ ${#effective_names[@]} -eq 0 ]]; then
            log_info "No rotated secrets applicable to $worker ($region)"
            continue
        fi

        # Fetch the worker's actual secret names
        local worker_secrets_response
        worker_secrets_response=$(cf_api GET "/accounts/$ACCOUNT_ID/workers/scripts/$worker/secrets")
        if ! echo "$worker_secrets_response" | jq -e '.success' >/dev/null 2>&1; then
            log_warn "Failed to list secrets for worker '$worker', skipping"
            failed_workers=$((failed_workers + 1))
            continue
        fi
        local worker_secret_names
        worker_secret_names=$(echo "$worker_secrets_response" | jq -r '.result[].name')

        # Intersect: only push rotated secrets that the worker actually has
        local worker_failed=false
        local synced=0
        for i in "${!effective_names[@]}"; do
            if echo "$worker_secret_names" | grep -qx "${effective_names[$i]}"; then
                if [[ "$DRY_RUN" == "true" ]]; then
                    log_warn "[DRY-RUN] Would sync secret '${effective_names[$i]}' to worker '$worker' ($region)"
                else
                    if ! sync_worker_secret "$worker" "${effective_names[$i]}" "${effective_values[$i]}"; then
                        worker_failed=true
                    fi
                fi
                synced=$((synced + 1))
            fi
        done

        if [[ "$synced" -eq 0 ]]; then
            log_info "No matching secrets on worker: $worker"
        elif [[ "$worker_failed" == "true" ]]; then
            log_warn "One or more secrets failed to sync to worker: $worker"
            failed_workers=$((failed_workers + 1))
        else
            log_info "Synced $synced secret(s) to worker: $worker ($region)"
        fi
    done

    return "$failed_workers"
}

# =============================================================================
# MAIN
# =============================================================================

log_step "Rotating Cloudflare account tokens for CI/CD"
if [[ "$DRY_RUN" == "true" ]]; then
    log_warn "DRY-RUN mode: no mutations will be performed"
fi

# Rotation order: runtime secrets first (Turnstile, SES), then CI/CD-only (CD, R2).
# If a runtime rotation fails, we abort before touching CI/CD tokens -- no partial state.

# ---- 1. Turnstile secret rotation (runtime) ----
if [[ "$ROTATE_TURNSTILE" != "true" ]]; then
    log_step "=== Skipping Turnstile secret (pass --rotate-turnstile to include) ==="
else
    log_step "=== Rotating Turnstile secret ==="

    # Discover sitekey by listing widgets (preflight already verified access)
    turnstile_widgets=$(cf_api GET "/accounts/$ACCOUNT_ID/challenges/widgets")
    cf_check_response "$turnstile_widgets" "Failed to list Turnstile widgets"
    turnstile_sitekey=$(echo "$turnstile_widgets" | jq -r '.result[0].sitekey')

    log_info "Found Turnstile widget: $turnstile_sitekey"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "[DRY-RUN] Would rotate Turnstile secret for sitekey: $turnstile_sitekey"
        new_turnstile_secret="<dry-run>"
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
fi

# ---- 2. AWS SES credentials (runtime, multi-region) ----
log_step "=== Rotating AWS SES credentials (EU + US) ==="

# Preflight already verified AWS CLI + profile access

# Helper: rotate SES keys for one IAM user
rotate_ses_user() {
    local iam_user="$1" gh_key_secret="$2" gh_secret_secret="$3" label="$4"

    local old_keys new_key_json key_id secret

    old_keys=$(aws iam list-access-keys --user-name "$iam_user" \
        --query 'AccessKeyMetadata[].AccessKeyId' --output text)

    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "[DRY-RUN] Would rotate keys for IAM user: $iam_user"
        log_warn "[DRY-RUN] Current keys: $old_keys"
        key_id="<dry-run>"
        secret="<dry-run>"
    else
        log_step "Creating new access key for $iam_user..."
        new_key_json=$(aws iam create-access-key --user-name "$iam_user")
        key_id=$(echo "$new_key_json" | jq -r '.AccessKey.AccessKeyId')
        secret=$(echo "$new_key_json" | jq -r '.AccessKey.SecretAccessKey')
        log_info "Created new key: $key_id"

        log_step "Updating GitHub secrets: SES $label credentials..."
        set_github_secret "$gh_key_secret" "$key_id"
        set_github_secret "$gh_secret_secret" "$secret"
        log_info "Updated $gh_key_secret, $gh_secret_secret"
    fi

    # Export results via global variables (caller reads these)
    _ses_old_keys="$old_keys"
    _ses_new_key_id="$key_id"
    _ses_new_secret="$secret"
}

# Rotate EU
log_step "Rotating EU SES credentials ($AWS_IAM_USER_EU)..."
rotate_ses_user "$AWS_IAM_USER_EU" "$SES_EU_GITHUB_KEY_SECRET" "$SES_EU_GITHUB_SECRET_SECRET" "EU"
ses_old_keys_eu="$_ses_old_keys"
new_ses_key_id_eu="$_ses_new_key_id"
new_ses_secret_eu="$_ses_new_secret"

# Rotate US
log_step "Rotating US SES credentials ($AWS_IAM_USER_US)..."
rotate_ses_user "$AWS_IAM_USER_US" "$SES_US_GITHUB_KEY_SECRET" "$SES_US_GITHUB_SECRET_SECRET" "US"
ses_old_keys_us="$_ses_old_keys"
new_ses_key_id_us="$_ses_new_key_id"
new_ses_secret_us="$_ses_new_secret"

# Old key deletion is deferred until after worker secret sync (see below)

# ---- 3. Github-CD token (CI/CD only) ----
log_step "=== Rotating CD token: $CD_TOKEN_NAME ==="

fetch_permission_groups

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

if [[ "$DRY_RUN" == "true" ]]; then
    cd_token_value="<dry-run>"
else
    cd_token_value=$(echo "$cd_result" | jq -r '.value')
    log_info "Created $CD_TOKEN_NAME token"

    log_step "Updating GitHub secret: $CD_GITHUB_SECRET..."
    set_github_secret "$CD_GITHUB_SECRET" "$cd_token_value"
    log_info "Updated $CD_GITHUB_SECRET"
fi

# ---- 4. Github-R2 token (CI/CD only) ----
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

if [[ "$DRY_RUN" == "true" ]]; then
    r2_access_key="<dry-run>"
    r2_secret_key="<dry-run>"
else
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

# ---- Sync rotated secrets to live workers ----
worker_sync_failures=0
sync_secrets_to_workers || worker_sync_failures=$?

# ---- Update local .env (skip in CI) ----
ENV_FILE="$ROOT_DIR/private/account/.env"
if [[ -f "$ENV_FILE" ]] && ! is_ci; then
    log_step "Updating local .env"
    [[ -n "${new_turnstile_secret:-}" && "$new_turnstile_secret" != "<dry-run>" ]] &&
        update_env_file "$ENV_FILE" "TURNSTILE_SECRET_KEY" "$new_turnstile_secret"
    # Local dev uses EU SES credentials (dev runs against eu-central-1)
    [[ -n "${new_ses_key_id_eu:-}" && "$new_ses_key_id_eu" != "<dry-run>" ]] &&
        update_env_file "$ENV_FILE" "AWS_SES_ACCESS_KEY_ID" "$new_ses_key_id_eu"
    [[ -n "${new_ses_secret_eu:-}" && "$new_ses_secret_eu" != "<dry-run>" ]] &&
        update_env_file "$ENV_FILE" "AWS_SES_SECRET_ACCESS_KEY" "$new_ses_secret_eu"
    # R2 credentials for local testing (promotion simulation, pr publish R2 uploads)
    [[ -n "${r2_access_key:-}" && "$r2_access_key" != "<dry-run>" ]] &&
        update_env_file "$ENV_FILE" "R2_ACCESS_KEY_ID" "$r2_access_key"
    [[ -n "${r2_secret_key:-}" && "$r2_secret_key" != "<dry-run>" ]] &&
        update_env_file "$ENV_FILE" "R2_SECRET_ACCESS_KEY" "$r2_secret_key"
    update_env_file "$ENV_FILE" "R2_ENDPOINT" "$R2_ENDPOINT_VALUE"
    log_info "Updated $ENV_FILE"
elif is_ci; then
    log_info "Skipping .env update (CI environment)"
fi

# ---- Deferred: Delete old AWS SES keys ----
# Only delete old keys AFTER workers have been updated, so workers are never
# left with deleted credentials. If any worker sync failed, keep old keys alive.
delete_old_ses_keys() {
    local iam_user="$1" old_keys="$2" new_key_id="$3" label="$4"

    [[ -z "$old_keys" || -z "$new_key_id" ]] && return

    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "[DRY-RUN] Would delete old $label SES keys: $old_keys"
        return
    fi
    if [[ "$worker_sync_failures" -gt 0 ]]; then
        log_warn "Skipping old $label SES key deletion: $worker_sync_failures worker(s) failed secret sync"
        log_warn "Old keys still active ($label): $old_keys"
        return
    fi
    for old_key in $old_keys; do
        if [[ "$old_key" != "$new_key_id" ]]; then
            log_step "Deleting old $label SES key: $old_key"
            if ! aws iam delete-access-key --user-name "$iam_user" \
                --access-key-id "$old_key" 2>&1; then
                log_warn "Failed to delete old $label SES key: $old_key"
                log_warn "Manually delete it: aws iam delete-access-key --user-name $iam_user --access-key-id $old_key"
            fi
        fi
    done
}

delete_old_ses_keys "$AWS_IAM_USER_EU" "${ses_old_keys_eu:-}" "${new_ses_key_id_eu:-}" "EU"
delete_old_ses_keys "$AWS_IAM_USER_US" "${ses_old_keys_us:-}" "${new_ses_key_id_us:-}" "US"

if [[ "$worker_sync_failures" -eq 0 ]]; then
    log_info "Old AWS SES key cleanup done"
fi

# ---- Summary ----
log_step "Rotation complete"
log_info "  CD token: $CD_TOKEN_NAME -> $CD_GITHUB_SECRET"
log_info "  R2 token: $R2_TOKEN_NAME -> $R2_GITHUB_KEY_SECRET, $R2_GITHUB_SECRET_SECRET"
log_info "  R2 endpoint: $R2_ENDPOINT_VALUE"
log_info "  Turnstile: $TURNSTILE_GITHUB_SECRET"
log_info "  AWS SES EU: $SES_EU_GITHUB_KEY_SECRET, $SES_EU_GITHUB_SECRET_SECRET (user: $AWS_IAM_USER_EU)"
log_info "  AWS SES US: $SES_US_GITHUB_KEY_SECRET, $SES_US_GITHUB_SECRET_SECRET (user: $AWS_IAM_USER_US)"
if [[ "$worker_sync_failures" -gt 0 ]]; then
    log_warn "  Worker sync: $worker_sync_failures worker(s) had failures (old AWS SES keys preserved)"
    exit 1
else
    log_info "  Worker sync: all live workers updated"
fi

# ---- Self-destruct: burn credentials used to run this script ----
if [[ "$KEEP_CREDENTIALS" != "true" ]]; then
    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "[DRY-RUN] Would delete CF management token and AWS admin key"
    else
        self_destruct_credentials --aws
    fi
fi
