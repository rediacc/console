#!/bin/bash
# Shared Cloudflare + AWS authentication for dev scripts.
#
# Source this file after common.sh. It provides:
#   - resolve_cf_auth:       Sets CF_AUTH_HEADERS array from env vars or interactive prompt
#   - resolve_aws_auth:      Exports AWS_ACCESS_KEY_ID/SECRET from AWS_SES_ADMIN_* env vars
#   - self_destruct_credentials: Deletes the CF token and/or AWS key used to run the script
#
# Env vars:
#   CF_MANAGEMENT_TOKEN  - Scoped API token (recommended, supports self-destruct)
#   CF_API_KEY + CF_EMAIL - Global API Key (legacy, cannot self-destruct)
#   AWS_SES_ADMIN_KEY_ID + AWS_SES_ADMIN_SECRET - IAM admin credentials

CF_API_BASE="https://api.cloudflare.com/client/v4"
CF_AUTH_HEADERS=()

# Update or append a key=value in a .env file.
update_env_file() {
    local file="$1" key="$2" value="$3"
    if grep -q "^${key}=" "$file" 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$file"
    else
        echo "${key}=${value}" >>"$file"
    fi
}

# Resolve Cloudflare authentication.
# Sets CF_AUTH_HEADERS array for use with curl.
# If CF_API_KEY + CF_EMAIL are provided (Global API Key), auto-creates a scoped
# management token so self-destruct works. The token is deleted at the end.
resolve_cf_auth() {
    if [[ -n "${CF_MANAGEMENT_TOKEN:-}" ]]; then
        CF_AUTH_HEADERS=(-H "Authorization: Bearer ${CF_MANAGEMENT_TOKEN}")
    elif [[ -n "${CF_API_KEY:-}" && -n "${CF_EMAIL:-}" ]]; then
        log_step "Creating scoped management token from Global API Key..."
        CF_MANAGEMENT_TOKEN=$(_create_management_token)
        if [[ -z "$CF_MANAGEMENT_TOKEN" || "$CF_MANAGEMENT_TOKEN" == "null" ]]; then
            log_error "Failed to create management token from Global API Key"
            exit 1
        fi
        CF_AUTH_HEADERS=(-H "Authorization: Bearer ${CF_MANAGEMENT_TOKEN}")
        log_info "Management token created (will self-destruct after run)"
    else
        echo "Authentication method:"
        echo "  1) Global API Key + Email (auto-creates scoped token)"
        echo "  2) Scoped API Token (if you have one ready)"
        echo -n "Choose [1/2]: "
        read -r auth_choice
        if [[ "$auth_choice" == "1" ]]; then
            echo -n "Enter email: "
            read -r CF_EMAIL
            echo -n "Enter Global API Key: "
            read -rs CF_API_KEY
            echo
            log_step "Creating scoped management token..."
            CF_MANAGEMENT_TOKEN=$(_create_management_token)
            if [[ -z "$CF_MANAGEMENT_TOKEN" || "$CF_MANAGEMENT_TOKEN" == "null" ]]; then
                log_error "Failed to create management token"
                exit 1
            fi
            CF_AUTH_HEADERS=(-H "Authorization: Bearer ${CF_MANAGEMENT_TOKEN}")
            log_info "Management token created (will self-destruct after run)"
        else
            echo -n "Enter API Token: "
            read -rs CF_MANAGEMENT_TOKEN
            echo
            CF_AUTH_HEADERS=(-H "Authorization: Bearer ${CF_MANAGEMENT_TOKEN}")
        fi
    fi

    if [[ ${#CF_AUTH_HEADERS[@]} -eq 0 ]]; then
        log_error "Cloudflare authentication credentials are required"
        exit 1
    fi
}

# Create a scoped management token using the Global API Key.
# Requires CF_API_KEY, CF_EMAIL, and ACCOUNT_ID to be set.
# Prints the token value to stdout.
_create_management_token() {
    local account_id="${ACCOUNT_ID:-fa51e4a18d553c30e1633288e9733d04}"

    # Get user ID for user-level permissions
    local user_id
    user_id=$(curl -s -X GET "${CF_API_BASE}/user" \
        -H "X-Auth-Key: ${CF_API_KEY}" -H "X-Auth-Email: ${CF_EMAIL}" \
        -H "Content-Type: application/json" | jq -r '.result.id // empty')

    if [[ -z "$user_id" ]]; then
        return 1
    fi

    # Account permissions:
    #   Account API Tokens Read + Write (manage account tokens)
    #   Turnstile Sites Write (rotate Turnstile secret)
    #   Workers Scripts Read + Write (list workers, push secrets)
    # User permissions:
    #   API Tokens Read + Write (list permission groups, self-destruct)
    local response
    response=$(curl -s -X POST "${CF_API_BASE}/user/tokens" \
        -H "X-Auth-Key: ${CF_API_KEY}" -H "X-Auth-Email: ${CF_EMAIL}" \
        -H "Content-Type: application/json" \
        -d "$(jq -n --arg account_id "$account_id" --arg user_id "$user_id" '{
            name: "auto-rotation-management",
            policies: [
                {
                    effect: "allow",
                    resources: { ("com.cloudflare.api.account." + $account_id): "*" },
                    permission_groups: [
                        { id: "eb56a6953c034b9d97dd838155666f06" },
                        { id: "5bc3f8b21c554832afc660159ab75fa4" },
                        { id: "755c05aa014b4f9ab263aa80b8167bd8" },
                        { id: "1a71c399035b4950a1bd1466bbe4f420" },
                        { id: "e086da7e2179491d91ee5f35b3ca210a" }
                    ]
                },
                {
                    effect: "allow",
                    resources: { ("com.cloudflare.api.user." + $user_id): "*" },
                    permission_groups: [
                        { id: "0cc3a61731504c89b99ec1be78b77aa0" },
                        { id: "686d18d5ac6c441c867cbf6771e58a0a" }
                    ]
                }
            ]
        }')")

    echo "$response" | jq -r '.result.value // empty'
}

# Resolve AWS SES admin authentication.
# Exports standard AWS env vars for the aws CLI.
resolve_aws_auth() {
    if [[ -z "${AWS_SES_ADMIN_KEY_ID:-}" || -z "${AWS_SES_ADMIN_SECRET:-}" ]]; then
        log_error "AWS_SES_ADMIN_KEY_ID and AWS_SES_ADMIN_SECRET are required"
        exit 1
    fi
    export AWS_ACCESS_KEY_ID="$AWS_SES_ADMIN_KEY_ID"
    export AWS_SECRET_ACCESS_KEY="$AWS_SES_ADMIN_SECRET"
    export AWS_DEFAULT_REGION="${AWS_SES_ADMIN_REGION:-eu-central-1}"
}

# Verify self-destruct is possible (requires CF_MANAGEMENT_TOKEN).
# After resolve_cf_auth, CF_MANAGEMENT_TOKEN is always set (auto-created from Global API Key if needed).
check_self_destruct_capable() {
    if [[ -z "${CF_MANAGEMENT_TOKEN:-}" ]]; then
        log_error "Self-destruct requires Cloudflare authentication"
        log_error "Set CF_MANAGEMENT_TOKEN or CF_API_KEY + CF_EMAIL"
        exit 1
    fi
}

# Destroy credentials used to run the script.
# Deletes the CF management token (self-destruct) and optionally the AWS admin key.
# Args: [--aws] to also delete the AWS admin key
self_destruct_credentials() {
    local destroy_aws=false
    for arg in "$@"; do
        [[ "$arg" == "--aws" ]] && destroy_aws=true
    done

    log_step "=== Self-destruct: destroying credentials used for this run ==="

    # 1. AWS admin key (if requested)
    if [[ "$destroy_aws" == "true" && -n "${AWS_SES_ADMIN_KEY_ID:-}" ]]; then
        log_step "Deleting AWS admin key: $AWS_SES_ADMIN_KEY_ID"
        if ! aws iam delete-access-key --access-key-id "$AWS_SES_ADMIN_KEY_ID" 2>&1; then
            log_warn "Failed to delete AWS admin key: $AWS_SES_ADMIN_KEY_ID"
            log_warn "Manually delete it from: https://us-east-1.console.aws.amazon.com/iam/home#/security_credentials"
        else
            log_info "AWS admin key deleted"
        fi
    fi

    # 2. CF management token (self-destruct)
    if [[ -n "${CF_MANAGEMENT_TOKEN:-}" ]]; then
        log_step "Deleting CF management token..."
        local token_id
        token_id=$(curl -s -X GET "${CF_API_BASE}/user/tokens/verify" \
            "${CF_AUTH_HEADERS[@]}" -H "Content-Type: application/json" | jq -r '.result.id // empty')
        if [[ -n "$token_id" ]]; then
            curl -s -X DELETE "${CF_API_BASE}/user/tokens/$token_id" \
                "${CF_AUTH_HEADERS[@]}" -H "Content-Type: application/json" >/dev/null 2>&1
            log_info "CF management token deleted (self-destruct)"
        else
            log_warn "Could not determine CF token ID for self-destruct"
        fi
    fi
}
